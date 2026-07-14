"""Clientes — listagem, busca, CRUD (cliente + cliente_end + cliente_tel) e
validação de CPF/CNPJ (incluindo CNPJ alfanumérico — RFB 2026)."""
import asyncio
from typing import List, Optional

from db.connection import _open_conn, _to_json_safe, _get_col_sizes, _trunc
from models.schemas import (
    ClientesRequest, ClienteSaveRequest, EnderecoInput, TelefoneInput, ContatoInput,
)


# =====================================================================
# Validação CPF / CNPJ (incluindo CNPJ alfanumérico — RFB 2026)
# =====================================================================
def _only_alnum_upper(s: str) -> str:
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def _valid_cpf(s: str) -> bool:
    s = "".join(ch for ch in (s or "") if ch.isdigit())
    if len(s) != 11 or s == s[0] * 11:
        return False
    for i in (9, 10):
        soma = sum(int(s[j]) * (i + 1 - j) for j in range(i))
        dv = (soma * 10) % 11
        if dv == 10:
            dv = 0
        if dv != int(s[i]):
            return False
    return True


def _valid_cnpj(s: str) -> bool:
    """Valida CNPJ numérico OU alfanumérico (2026).
    Regra alfanumérica: primeiras 12 posições aceitam A-Z e 0-9;
    duas últimas (DV) permanecem numéricas. Valor de cada caractere
    é (ord(c) - ord('0')), ou seja A=17, B=18, ..., Z=42.
    Pesos: 5,4,3,2,9,8,7,6,5,4,3,2 (DV1) e 6,5,4,3,2,9,8,7,6,5,4,3,2 (DV2).
    """
    s = _only_alnum_upper(s)
    if len(s) != 14:
        return False
    for c in s[:12]:
        if not (c.isdigit() or ("A" <= c <= "Z")):
            return False
    if not (s[12].isdigit() and s[13].isdigit()):
        return False
    # rejeita sequências repetidas (00000000000000)
    if len(set(s)) == 1:
        return False

    def val(c: str) -> int:
        return ord(c) - ord("0")

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma1 = sum(val(s[i]) * pesos1[i] for i in range(12))
    dv1 = soma1 % 11
    dv1 = 0 if dv1 < 2 else 11 - dv1
    if dv1 != int(s[12]):
        return False

    soma2 = sum(val(s[i]) * pesos2[i] for i in range(13))
    dv2 = soma2 % 11
    dv2 = 0 if dv2 < 2 else 11 - dv2
    if dv2 != int(s[13]):
        return False
    return True


def _validate_cgc_cpf(value: str) -> tuple[bool, str]:
    """Retorna (ok, msg). Vazio é considerado OK (campo opcional)."""
    raw = _only_alnum_upper(value)
    if not raw:
        return True, ""
    if len(raw) == 11:
        return (_valid_cpf(raw), "CPF inválido.")
    if len(raw) == 14:
        return (_valid_cnpj(raw), "CNPJ inválido.")
    return False, "CGC/CPF deve ter 11 (CPF) ou 14 (CNPJ) caracteres."


def _normalize_cgc(s: Optional[str]) -> str:
    return _only_alnum_upper(s or "")


# =====================================================================
# Listagem de clientes (com paginação e busca)
# =====================================================================
def _list_clientes_sync(req: ClientesRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}

    try:
        size = max(1, min(100, req.size))
        offset = max(0, (req.page - 1) * size)
        search = (req.search or "").strip()

        where = ""
        params: tuple = ()
        if search:
            where = "WHERE c.nome LIKE %s OR c.cgc_cpf LIKE %s OR c.telefone_cli LIKE %s"
            like = f"%{search}%"
            params = (like, like, like)

        cur = conn.cursor(as_dict=True)
        cur.execute(f"SELECT COUNT(*) AS total FROM cliente c {where}", params)
        total = cur.fetchone()["total"]

        cur.execute(
            f"SELECT c.codigo, c.nome, c.cgc_cpf, "
            f"       COALESCE(ct.ddd, CAST(c.ddd_cli AS NVARCHAR(4))) AS ddd_cli, "
            f"       COALESCE(ct.tel, c.telefone_cli) AS telefone_cli, "
            f"       c.e_mail, c.situacao, "
            f"       t.descricao AS tipo_descricao, "
            f"       CASE WHEN ln.codigo IS NULL THEN 0 ELSE 1 END AS lista_negra, "
            f"       ln.motivo AS lista_negra_motivo "
            f"FROM cliente c "
            f"OUTER APPLY (SELECT TOP 1 ddd, tel FROM cliente_tel WHERE codigo = c.codigo ORDER BY sequencia) ct "
            f"LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.cliente_forn AS INT) "
            f"LEFT JOIN lista_negra ln ON ln.codigo = CAST(c.codigo AS NVARCHAR(14)) "
            f"{where} "
            f"ORDER BY c.nome OFFSET {offset} ROWS FETCH NEXT {size} ROWS ONLY",
            params
        )
        rows = [_to_json_safe(r) for r in cur.fetchall()]
        for r in rows:
            r["lista_negra"] = bool(r.get("lista_negra"))
        # Telefone formatado
        for r in rows:
            ddd = r.get("ddd_cli") or ""
            tel = (r.get("telefone_cli") or "").strip()
            r["telefone"] = f"({ddd}) {tel}" if ddd and tel else tel
        cur.close()
        conn.close()
        return {"success": True, "items": rows, "total": total, "page": req.page, "size": size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


# =====================================================================
# Tipo Cliente — dropdown
# =====================================================================
def _list_tipo_cliente_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, descricao FROM tipo_cliente ORDER BY descricao")
        items = [_to_json_safe(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


# =====================================================================
# GET cliente por código (com endereço primário + telefones)
# =====================================================================
def _get_cliente_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.codigo, c.cgc_cpf, c.nome, c.e_mail, c.inscr_est AS inscre, c.cliente_forn AS tipo, "
            "       c.aceita_email, c.vendedor, c.situacao, "
            "       c.ddd_cli, c.telefone_cli, "
            "       t.descricao AS tipo_descricao, "
            "       c.fantasia AS nome_fantasia, c.sexo, c.data_nasc, c.inscr_mun, c.site, c.historico, "
            "       c.DATA_ENCERRAMENTO_CLIENTE AS inativo_em, c.STATUS_CLIENTE AS status, "
            "       c.contato, c.limite_credito, c.desconto, c.crt AS regime_tributario, "
            "       c.credita_icms, c.consumidor_final, c.TRIBUTA_ISS_FORA AS tributa_iss_fora_municipio, "
            "       c.faturamento_principal AS fatura_para, c.faturar AS cliente_principal, "
            "       c.prazo_faturamento, c.indpres, "
            "       c.canal_aquisicao_cliente, c.dia_contato, c.dia_entrega, c.forma_pag AS forma_pagamento, "
            "       c.segmento, c.rota, c.regiao, c.email_cobranca, c.email_NFE AS email_nfe, "
            "       c.centro_custo_cliente, c.conta_transf_caixa, c.cobra_tarifa_bancaria, "
            "       c.tipo_cobranca_tarifa, c.valor_frete, c.classe_caixa, c.sub_classe_caixa "
            "FROM cliente c "
            "LEFT JOIN tipo_cliente t ON t.codigo = TRY_CAST(c.cliente_forn AS INT) "
            "WHERE c.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"success": False, "message": "Cliente não encontrado."}
        cliente = _to_json_safe(row)

        # Endereços (todos os registros de cliente_end — cliente pode ter vários)
        cur.execute(
            "SELECT sequencia, tipo, endereco, numero, complemento, bairro, cidade, uf, cep "
            "FROM cliente_end WHERE codigo = %s ORDER BY sequencia",
            (codigo,),
        )
        end_rows = [_to_json_safe(r) for r in cur.fetchall()]

        # Telefones (até 3)
        cur.execute(
            "SELECT TOP 3 sequencia, ddd, tel, descricao "
            "FROM cliente_tel WHERE codigo = %s ORDER BY sequencia",
            (codigo,),
        )
        tel_rows = [_to_json_safe(r) for r in cur.fetchall()]

        # Contatos (pessoas de contato — entidade separada dos telefones)
        cur.execute(
            "SELECT sequencia, contato, setor, cargo, ddd, telefone, ddd_fax, fax, "
            "       ddd_celular, celular, e_mail, sexo "
            "FROM cliente_contato WHERE codigo = %s ORDER BY sequencia",
            (codigo,),
        )
        contato_rows = [_to_json_safe(r) for r in cur.fetchall()]

        cur.close()
        conn.close()
        return {
            "success": True,
            "cliente": cliente,
            "enderecos": end_rows,
            "telefones": tel_rows,
            "contatos": contato_rows,
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# Busca cliente por CGC/CPF (alfanumérico, sem máscara). Retorna codigo se achar.
def _find_by_cgc_sync(servidor: str, banco: str, cgc: str) -> dict:
    raw = _only_alnum_upper(cgc)
    if not raw:
        return {"success": False, "message": "CGC/CPF vazio."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT TOP 1 codigo, nome FROM cliente WHERE cgc_cpf = %s",
            (raw,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": True, "found": False}
        return {
            "success": True,
            "found": True,
            "codigo": int(row["codigo"]),
            "nome": (row.get("nome") or "").strip(),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# Busca de cliente para o pedido — por nome, cgc/cpf ou telefone.
def _find_clientes_for_pedido_sync(servidor: str, banco: str, term: str, limit: int = 15) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        like = f"%{(term or '').strip()}%"
        cur.execute(
            f"SELECT TOP {int(limit)} c.codigo, c.nome, c.cgc_cpf, "
            f"       COALESCE(ct.tel, c.telefone_cli) AS telefone "
            f"FROM cliente c "
            f"OUTER APPLY (SELECT TOP 1 tel FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia) ct "
            f"WHERE c.nome LIKE %s OR c.cgc_cpf LIKE %s OR c.telefone_cli LIKE %s OR ct.tel LIKE %s "
            f"ORDER BY c.nome",
            (like, like, like, like),
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "cgc_cpf": (r.get("cgc_cpf") or "").strip(),
            "telefone": (r.get("telefone") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


# Cliente — resumo com telefone + endereço (para exibir no form de pedido)
def _cliente_resumo_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT c.codigo, c.nome, c.cgc_cpf, c.e_mail, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + ' ' + tel) FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), '') AS telefone, "
            "  (SELECT TOP 1 LTRIM(RTRIM(ISNULL(endereco,'')+', '+ISNULL(CAST(numero AS NVARCHAR(10)),'') + ' - ' + ISNULL(bairro,'') + ' - ' + ISNULL(cidade,'') + '/' + ISNULL(uf,''))) "
            "    FROM cliente_end WHERE codigo=c.codigo ORDER BY sequencia) AS endereco "
            "FROM cliente c WHERE c.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Cliente não encontrado."}
        return {
            "success": True,
            "cliente": {
                "codigo": int(row["codigo"]),
                "nome": (row.get("nome") or "").strip(),
                "cgc_cpf": (row.get("cgc_cpf") or "").strip(),
                "e_mail": (row.get("e_mail") or "").strip(),
                "telefone": (row.get("telefone") or "").strip(),
                "endereco": (row.get("endereco") or "").strip(),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# =====================================================================
# CREATE / UPDATE cliente (cliente + cliente_end + cliente_tel)
# =====================================================================
def _save_cliente_sync(
    req: ClienteSaveRequest,
    enderecos: Optional[List[EnderecoInput]],
    telefones: List[TelefoneInput],
    codigo: Optional[int],
    contatos: Optional[List[ContatoInput]] = None,
) -> dict:
    # Validações de domínio
    nome = (req.nome or "").strip()
    if not nome:
        return {"success": False, "message": "Nome é obrigatório."}
    if len(nome) > 60:
        return {"success": False, "message": "Nome excede 60 caracteres."}

    cgc = _normalize_cgc(req.cgc_cpf)
    ok, msg = _validate_cgc_cpf(cgc)
    if not ok:
        return {"success": False, "message": msg}

    if len(telefones) > 3:
        return {"success": False, "message": "Máximo de 3 telefones."}

    enderecos = enderecos or []
    contatos = contatos or []

    # cliente.cliente_forn é SMALLINT no banco (FK p/ tipo_cliente.codigo)
    tipo_int: Optional[int] = None
    if req.tipo and str(req.tipo).strip():
        try:
            tipo_int = int(str(req.tipo).strip())
        except ValueError:
            tipo_int = None

    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}

    try:
        cur = conn.cursor()

        # Descobre tamanhos reais das colunas (cache por (banco, tabela)).
        sz_cli = _get_col_sizes(conn, req.banco, "cliente")
        sz_end = _get_col_sizes(conn, req.banco, "cliente_end")
        sz_tel = _get_col_sizes(conn, req.banco, "cliente_tel")
        sz_cont = _get_col_sizes(conn, req.banco, "cliente_contato")

        # Telefone primário — gravado nos campos inline (compat com legacy).
        # cliente.ddd_cli é SMALLINT, cliente.telefone_cli é nvarchar(8).
        primary = telefones[0] if telefones else None
        ddd_int: Optional[int] = None
        tel_inline: Optional[str] = None
        if primary:
            try:
                ddd_int = int((primary.ddd or "").strip()) if (primary.ddd or "").strip().isdigit() else None
            except ValueError:
                ddd_int = None
            tel_raw = (primary.tel or "").strip()
            if tel_raw:
                tel_inline = _trunc(tel_raw, sz_cli, "telefone_cli", 8)

        usuario_cad = req.usuario_cadastro if req.usuario_cadastro is not None else req.vendedor
        usuario_alt = req.usuario_alteracao if req.usuario_alteracao is not None else req.vendedor

        situacao = (req.situacao or "A").strip().upper()[:1] or "A"

        # Colunas comuns a INSERT e UPDATE (nome_coluna -> valor já tratado/truncado).
        campos: dict = {
            "cgc_cpf": _trunc(cgc, sz_cli, "cgc_cpf", 14) or None,
            "nome": _trunc(nome, sz_cli, "nome", 60),
            "e_mail": _trunc((req.e_mail or "").strip(), sz_cli, "e_mail", 60) or None,
            "inscr_est": _trunc((req.inscre or "").strip(), sz_cli, "inscr_est", 18) or None,
            "cliente_forn": tipo_int,
            "aceita_email": 1 if req.aceita_email else 0,
            "vendedor": req.vendedor,
            "ddd_cli": ddd_int,
            "telefone_cli": tel_inline,
            "fantasia": _trunc((req.nome_fantasia or "").strip(), sz_cli, "fantasia", 60) or None,
            "sexo": _trunc((req.sexo or "").strip(), sz_cli, "sexo", 1) or None,
            "data_nasc": req.data_nasc or None,
            "inscr_mun": _trunc((req.inscr_mun or "").strip(), sz_cli, "inscr_mun", 18) or None,
            "site": _trunc((req.site or "").strip(), sz_cli, "site", 60) or None,
            "historico": (req.historico or "").strip() or None,
            "situacao": situacao,
            "STATUS_CLIENTE": _trunc((req.status or "").strip(), sz_cli, "status_cliente", 2) or None,
            "DATA_ENCERRAMENTO_CLIENTE": req.inativo_em or None,
            "contato": _trunc((req.contato or "").strip(), sz_cli, "contato", 30) or None,
            "limite_credito": req.limite_credito,
            "desconto": req.desconto,
            "crt": req.regime_tributario,
            "credita_icms": 1 if req.credita_icms else 0,
            "consumidor_final": 1 if req.consumidor_final else 0,
            "TRIBUTA_ISS_FORA": 1 if req.tributa_iss_fora_municipio else 0,
            "faturamento_principal": 1 if req.fatura_para else 0,
            "faturar": req.cliente_principal,
            "prazo_faturamento": req.prazo_faturamento,
            "indpres": int(req.indpres) if (req.indpres or "").strip().lstrip("-").isdigit() else None,
            # canal_aquisicao_cliente é NOT NULL no banco — nunca envia NULL explícito.
            "canal_aquisicao_cliente": req.canal_aquisicao_cliente if req.canal_aquisicao_cliente is not None else 0,
            "dia_contato": req.dia_contato,
            "dia_entrega": req.dia_entrega,
            "forma_pag": _trunc((req.forma_pagamento or "").strip(), sz_cli, "forma_pag", 3) or None,
            "segmento": _trunc((req.segmento or "").strip(), sz_cli, "segmento", 3) or None,
            "rota": req.rota,
            "regiao": req.regiao,
            "email_cobranca": _trunc((req.email_cobranca or "").strip(), sz_cli, "email_cobranca", 60) or None,
            "email_NFE": _trunc((req.email_nfe or "").strip(), sz_cli, "email_nfe", 60) or None,
            "centro_custo_cliente": req.centro_custo_cliente,
            "conta_transf_caixa": req.conta_transf_caixa,
            "cobra_tarifa_bancaria": 1 if req.cobra_tarifa_bancaria else 0,
            "tipo_cobranca_tarifa": _trunc((req.tipo_cobranca_tarifa or "").strip(), sz_cli, "tipo_cobranca_tarifa", 1) or None,
            "VALOR_FRETE": req.valor_frete,
            "classe_caixa": req.classe_caixa,
            "sub_classe_caixa": req.sub_classe_caixa,
        }

        if codigo is None:
            colunas = list(campos.keys()) + ["usuario_cadastro", "data"]
            placeholders = ["%s"] * len(campos) + ["%s", "CAST(GETDATE() AS DATE)"]
            valores = list(campos.values()) + [usuario_cad]
            cur.execute(
                f"INSERT INTO cliente ({', '.join(colunas)}) "
                f"OUTPUT INSERTED.codigo "
                f"VALUES ({', '.join(placeholders)})",
                tuple(valores),
            )
            new_id_row = cur.fetchone()
            if not new_id_row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter código do novo cliente."}
            cliente_codigo = int(new_id_row[0])
        else:
            set_clause = ", ".join(f"{col}=%s" for col in campos.keys())
            cur.execute(
                f"UPDATE cliente SET {set_clause}, "
                " usuario_alteracao=%s, data_alteracao=CAST(GETDATE() AS DATE) "
                "WHERE codigo=%s",
                tuple(campos.values()) + (usuario_alt, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Cliente não encontrado para atualização."}
            cliente_codigo = codigo

            # Limpa endereço, telefones e contatos existentes para regravar
            cur.execute("DELETE FROM cliente_end WHERE codigo=%s", (cliente_codigo,))
            cur.execute("DELETE FROM cliente_tel WHERE codigo=%s", (cliente_codigo,))
            cur.execute("DELETE FROM cliente_contato WHERE codigo=%s", (cliente_codigo,))

        # INSERT endereços (cliente pode ter vários — residencial, entrega, cobrança...)
        for endereco in enderecos:
            cep = "".join(ch for ch in (endereco.cep or "") if ch.isdigit())[:8]
            uf = (endereco.uf or "").strip()[:2].upper()
            cur.execute(
                "INSERT INTO cliente_end "
                "(codigo, tipo, endereco, numero, complemento, bairro, cidade, uf, cep) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    cliente_codigo,
                    int(endereco.tipo or 0),
                    _trunc((endereco.endereco or "").strip(), sz_end, "endereco", 60) or None,
                    endereco.numero,
                    _trunc((endereco.complemento or "").strip(), sz_end, "complemento", 30) or None,
                    _trunc((endereco.bairro or "").strip(), sz_end, "bairro", 35) or None,
                    _trunc((endereco.cidade or "").strip(), sz_end, "cidade", 35) or None,
                    uf or None,
                    cep or None,
                ),
            )

        # INSERT telefones (até 3)
        for tel in telefones[:3]:
            ddd_n = _trunc((tel.ddd or "").strip(), sz_tel, "ddd", 4)
            tel_n = _trunc((tel.tel or "").strip(), sz_tel, "tel", 10)
            if not tel_n:
                continue
            cur.execute(
                "INSERT INTO cliente_tel (codigo, ddd, tel, descricao) "
                "VALUES (%s, %s, %s, %s)",
                (
                    cliente_codigo,
                    ddd_n or "21",
                    tel_n,
                    _trunc((tel.descricao or "").strip(), sz_tel, "descricao", 15) or None,
                ),
            )

        # INSERT contatos (pessoas de contato — entidade separada dos telefones)
        for contato in contatos:
            nome_contato = _trunc((contato.contato or "").strip(), sz_cont, "contato", 30)
            if not nome_contato:
                continue
            cur.execute(
                "INSERT INTO cliente_contato "
                "(codigo, contato, setor, cargo, ddd, telefone, ddd_fax, fax, ddd_celular, celular, e_mail, sexo) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    cliente_codigo,
                    nome_contato,
                    _trunc((contato.setor or "").strip(), sz_cont, "setor", 30) or None,
                    _trunc((contato.cargo or "").strip(), sz_cont, "cargo", 30) or None,
                    int(contato.ddd) if (contato.ddd or "").strip().isdigit() else None,
                    _trunc((contato.telefone or "").strip(), sz_cont, "telefone", 9) or None,
                    int(contato.ddd_fax) if (contato.ddd_fax or "").strip().isdigit() else None,
                    _trunc((contato.fax or "").strip(), sz_cont, "fax", 9) or None,
                    _trunc((contato.ddd_celular or "").strip(), sz_cont, "ddd_celular", 3) or None,
                    _trunc((contato.celular or "").strip(), sz_cont, "celular", 9) or None,
                    _trunc((contato.e_mail or "").strip(), sz_cont, "e_mail", 60) or None,
                    _trunc((contato.sexo or "").strip(), sz_cont, "sexo", 1) or None,
                ),
            )

        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": cliente_codigo}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


# =====================================================================
# Lista Negra (tabela `lista_negra` — codigo nvarchar(14) PK, motivo
# nvarchar(max)). Legado: FrmListaN ("Cadastro de Clientes na Lista Negra").
# `codigo` guarda `cliente.codigo` (int) como string — sem FK real no banco.
# Botão por cliente na listagem (`clientes.tsx`): preto se já cadastrado,
# azul caso contrário.
# =====================================================================
def _save_lista_negra_sync(servidor: str, banco: str, codigo: int, motivo: str) -> dict:
    mot = (motivo or "").strip()
    if not mot:
        return {"success": False, "message": "Preencha o motivo corretamente."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM cliente WHERE codigo=%s", (codigo,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Cliente não cadastrado."}
        cod_str = str(codigo)
        cur.execute("SELECT TOP 1 1 AS ok FROM lista_negra WHERE codigo=%s", (cod_str,))
        if cur.fetchone():
            cur.execute("UPDATE lista_negra SET motivo=%s WHERE codigo=%s", (mot, cod_str))
        else:
            cur.execute("INSERT INTO lista_negra (codigo, motivo) VALUES (%s,%s)", (cod_str, mot))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_lista_negra_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM lista_negra WHERE codigo=%s", (str(codigo),))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        cur.close()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------- wrappers assíncronos ----------
async def list_clientes(req: ClientesRequest) -> dict:
    return await asyncio.to_thread(_list_clientes_sync, req)


async def list_tipo_cliente(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_tipo_cliente_sync, servidor, banco)


async def get_cliente(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_cliente_sync, servidor, banco, codigo)


async def find_by_cgc(servidor: str, banco: str, cgc: str) -> dict:
    return await asyncio.to_thread(_find_by_cgc_sync, servidor, banco, cgc)


async def find_clientes_search(servidor: str, banco: str, term: str) -> dict:
    return await asyncio.to_thread(_find_clientes_for_pedido_sync, servidor, banco, term)


async def cliente_resumo(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_cliente_resumo_sync, servidor, banco, codigo)


async def save_cliente(req: ClienteSaveRequest, enderecos, telefones, codigo, contatos=None) -> dict:
    return await asyncio.to_thread(_save_cliente_sync, req, enderecos, telefones, codigo, contatos)


async def save_lista_negra(servidor: str, banco: str, codigo: int, motivo: str) -> dict:
    return await asyncio.to_thread(_save_lista_negra_sync, servidor, banco, codigo, motivo)


async def delete_lista_negra(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_delete_lista_negra_sync, servidor, banco, codigo)
