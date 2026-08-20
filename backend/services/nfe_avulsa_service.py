"""Transações > Notas Fiscais > **Gerar NFe** (NF-e Avulsa, modelo 55) —
migração de `NFe\\frmtranfe.frm`, rastreada por completo 2026-08-19/20 —
ver PENDENCIAS.md > "Rastreio completo de `frmtranfe.frm`" pro racional
completo. Protocolo Gauntlet acionado (Leandro+Carlos+Thomé, Apoio Fisco
na tela). **NÃO confundir com `notas_fiscais_service.py`** ("Manutenção
de Notas Fiscais", migração de `FrmManRec.frm`) — essa é tela de
CONSULTA + ações pós-emissão (DANFE/cancelar/carta de correção/XML),
nunca tocada por este módulo; esta feature (`nfe_avulsa_service.py`) é a
tela de GERAR/EMITIR uma nota nova, digitada livremente.

**Achados-chave da fonte, replicados aqui**:
- Cabeçalho + itens digitados livremente, pra QUALQUER tipo de
  movimentação (`tipo_mov`, entrada ou saída) — destinatário é cliente OU
  fornecedor conforme `tipo_mov.origem_destino`.
- Arquitetura real é rascunho→definitivo: enquanto sendo digitada, tudo
  fica em `nf_aux`/`nf_aux_itens`/`nf_aux_vencimento` (tabelas espelho,
  confirmadas via `INFORMATION_SCHEMA.COLUMNS` real 2026-08-20 — nomes de
  coluna abaixo não são presumidos); só ao Emitir promove pra `n_fiscal`/
  `n_fiscal_itens`/`nf_vencimento`.

**3 decisões de negócio confirmadas com o usuário (2026-08-20)**:
1. ICMS/IPI/ISS por item são SUGERIDOS via cascata de tributação
   (`nfe_emissao_service._resolver_tributacao_sync`, mesma já usada por
   NFC-e/NF-e agrupada) mas livremente editáveis antes de gravar o
   rascunho.
2. PIS/COFINS NUNCA é digitável — calculado só no momento de Emitir,
   direto em `n_fiscal_itens` (não existe coluna pra isso em
   `nf_aux_itens`, confirmado no schema real).
3. IBS/CBS calculado só depois da promoção pra `n_fiscal`, gravado
   DIRETO nas colunas estruturadas já existentes (`CST_IBS_UF`/
   `VALOR_IBS_UF`/`CST_CBS`/`VALOR_CBS`/etc. em `n_fiscal_itens`,
   `XML_TOT_IBS_CBS` no cabeçalho) — achado desta sessão: essas colunas
   já existem e casam 1:1 com o que `ibs_cbs_service.calcular_item_ibs_
   cbs` devolve; não precisa reescrever XML.

**Simplificações desta fase, documentadas** (ver PENDENCIAS.md pra lista
completa): CFOP é só de cabeçalho (não por item — `nf_aux` não tem CFOP
por item neste desenho); fórmula de PIS/COFINS na emissão é best-effort
a partir das colunas confirmadas de `taxas` (`CST_TRIB_PIS`/`ALQT_TRIB_
PIS`/etc.) — **não foi cruzada linha-a-linha contra `SitTribut`/`Calcula`
do VB6 nesta rodada**, precisa validação antes de confiar em produção;
sem as 6 sub-rotinas de importação automática; sem reemissão de rascunho
já promovido; sem `nf_coligada`/`n_fiscal_vinculada`.

**NUNCA testado contra o SEFAZ real** — mesma ressalva de todo o resto
do pacote fiscal desta migração."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services import ibs_cbs_service, nfe_emissao_service, nfe_fiscal_common
from services.permissoes_service import tem_permissao

_CAB_CAMPOS_AUX = [
    "cod_fiscal", "fornecedor", "mov", "cfop",
    "data", "data_mov", "data_saida", "hora_saida",
    "valor_total", "base_icms", "valor_icms", "base_ipi", "valor_ipi",
    "base_iss", "valor_iss", "base_sub", "valor_sub",
    "frete", "seguro", "despesas", "desconto", "prazo",
    "BASE_FCP", "VALOR_FCP", "ALQT_FCP",
    "BASE_FCP_RETIDO", "VALOR_FCP_RETIDO", "ALQT_FCP_RETIDO",
    "BASE_FCP_ST", "VALOR_FCP_ST", "ALQT_FCP_ST",
    "cnpj_transportadora", "placa", "motorista", "volumes", "especie_volume",
    "peso_bruto", "peso_liquido",
]

_ITEM_CAMPOS_AUX = [
    "codigo_int", "cod_fiscal", "tributacao",
    "qtd", "p_unit", "desconto", "desconto_perc", "valor_total",
    "alqt_icms", "reducao_base_icms", "base_icms", "valor_icms",
    "base_ipi", "alqt_ipi", "valor_ipi",
    "base_sub", "valor_sub", "base_iss", "valor_iss",
    "frete", "seguro", "despesas", "obs_item_nf",
]


def _sem_permissao(cur, *, classe: Optional[int], master: bool, comando: str) -> bool:
    return not master and classe is not None and not tem_permissao(cur, classe, "NFE_AVULSA", comando)


# ---------------------------------------------------------------------------
# Rascunho (nf_aux/nf_aux_itens/nf_aux_vencimento)
# ---------------------------------------------------------------------------

def _novo_rascunho_sync(servidor: str, banco: str, *, classe: Optional[int] = None, master: bool = False) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para gerar NF-e avulsa."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}
        cur.execute("INSERT INTO nf_aux (valor_total) OUTPUT INSERTED.codigo VALUES (0)")
        codigo = int(cur.fetchone()["codigo"])
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _get_rascunho_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cols = ", ".join(["codigo", "num_nf"] + _CAB_CAMPOS_AUX)
        cur.execute(f"SELECT {cols} FROM nf_aux WHERE codigo=%s", (codigo,))
        row = cur.fetchone()
        if not row:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        cur.execute(
            f"SELECT id_nf_aux, {', '.join(_ITEM_CAMPOS_AUX)} FROM nf_aux_itens "
            "WHERE codigo=%s ORDER BY id_nf_aux",
            (codigo,),
        )
        itens = list(cur.fetchall())
        cur.execute(
            "SELECT SEQUENCIA_NF_AUX_VENCIMENTO AS sequencia, data_venc, valor "
            "FROM nf_aux_vencimento WHERE codigo=%s ORDER BY data_venc",
            (codigo,),
        )
        vencimentos = list(cur.fetchall())
        conn.close()
        return {
            "success": True, "cabecalho": row, "itens": itens, "vencimentos": vencimentos,
            "promovida": bool(row.get("num_nf")),
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_cabecalho_rascunho_sync(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    if not codigo:
        return {"success": False, "message": "Rascunho inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT num_nf FROM nf_aux WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if atual.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — não é possível editar o rascunho."}

        sets = ", ".join(f"{c}=%s" for c in _CAB_CAMPOS_AUX)
        valores = [dados.get(c) for c in _CAB_CAMPOS_AUX]
        cur.execute(f"UPDATE nf_aux SET {sets} WHERE codigo=%s", (*valores, codigo))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": codigo}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


def _save_itens_rascunho_sync(servidor: str, banco: str, codigo: int, itens: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da NF-e antes de lançar itens."}
    for it in itens:
        if not (it.get("codigo_int") or "").strip():
            return {"success": False, "message": "Todo item precisa de um Código de Produto/Serviço."}
        if not it.get("qtd"):
            return {"success": False, "message": "Todo item precisa de Quantidade maior que zero."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT num_nf FROM nf_aux WHERE codigo=%s", (codigo,))
        atual = cur.fetchone()
        if not atual:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if atual.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — não é possível editar o rascunho."}

        cur.execute("DELETE FROM nf_aux_itens WHERE codigo=%s", (codigo,))
        cols = ", ".join(_ITEM_CAMPOS_AUX)
        marcas = ", ".join(["%s"] * len(_ITEM_CAMPOS_AUX))
        for it in itens:
            valores = [it.get(c) for c in _ITEM_CAMPOS_AUX]
            cur.execute(f"INSERT INTO nf_aux_itens (codigo, {cols}) VALUES (%s, {marcas})", (codigo, *valores))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar itens: {e}"}


def _save_vencimentos_rascunho_sync(servidor: str, banco: str, codigo: int, vencimentos: list) -> dict:
    if not codigo:
        return {"success": False, "message": "Grave o cabeçalho da NF-e antes de lançar vencimentos."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM nf_aux_vencimento WHERE codigo=%s", (codigo,))
        for v in vencimentos:
            cur.execute(
                "INSERT INTO nf_aux_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo, v["data_venc"], v["valor"]),
            )
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar vencimentos: {e}"}


# ---------------------------------------------------------------------------
# Sugestão de tributação (ICMS/IPI/ISS) — nunca grava sozinha, só sugere;
# PIS/COFINS nunca aparece aqui (decisão 2, calculado só na emissão).
# ---------------------------------------------------------------------------

def _sugerir_tributacao_sync(
    servidor: str, banco: str, *, codigo_int: str, mov: str, uf_destino: str,
    nao_contribuinte: bool, simples_nacional_cliente: bool, consumidor_final: bool,
) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT cod_icms FROM pecas WHERE codigo_int=%s", (codigo_int,))
        p = cur.fetchone()
        if not p:
            conn.close()
            return {"success": False, "message": "Produto não encontrado — sugestão de tributação é só para Peças."}
        cod_icms = (p.get("cod_icms") or "").strip()

        cur.execute("SELECT uf FROM controle")
        controle = cur.fetchone() or {}
        uf_controle = (controle.get("uf") or "").strip().upper()

        cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf=%s AND codigo_int=%s", (uf_destino, codigo_int))
        protocolo_st = cur.fetchone() is not None

        tributos = nfe_emissao_service._resolver_tributacao_sync(
            cur, cod_icms=cod_icms, cfop_cupom_fiscal="", tipo_mov=mov,
            uf_destino=uf_destino, uf_controle=uf_controle, nao_contribuinte=nao_contribuinte,
            simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final,
            protocolo_st=protocolo_st,
        )
        conn.close()
        if not tributos:
            return {"success": False, "message": "Sem tributação cadastrada em Taxas (Tabelas Auxiliares) para este produto/UF."}
        return {
            "success": True,
            "sugestao": {
                "tributacao": tributos.get("tributacao"),
                "alqt_icms": tributos.get("aliquota_icms") or tributos.get("alqt_icms") or 0,
                "base_iss": 0, "valor_iss": 0,
                "cfop_livro": tributos.get("cfop_livro"),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Emissão — promove nf_aux/nf_aux_itens/nf_aux_vencimento pra n_fiscal/
# n_fiscal_itens/nf_vencimento, calcula PIS/COFINS e IBS/CBS só agora.
# ---------------------------------------------------------------------------

def _resolver_item_produto_sync(cur, codigo_int: str) -> dict:
    """Descrição/NCM/unidade/cod_icms não existem em `nf_aux_itens` — resolve
    via `pecas` (produto) ou `servicos` (serviço), mesmo padrão de cascata já
    usado em `_buscar_produto_sync`/`notas_fiscais_service.py`."""
    cur.execute(
        "SELECT descricao, codigo_mercosul AS ncm, uni AS unidade, cod_icms, origem "
        "FROM pecas WHERE codigo_int=%s",
        (codigo_int,),
    )
    row = cur.fetchone()
    if row:
        return {
            "descricao": (row.get("descricao") or "").strip(), "ncm": (row.get("ncm") or "").strip(),
            "unidade": (row.get("unidade") or "UN").strip(), "cod_icms": (row.get("cod_icms") or "").strip(),
            "origem": int(row.get("origem") or 0),
        }
    cur.execute("SELECT descricao FROM servicos WHERE codigo=%s", (codigo_int,))
    row = cur.fetchone()
    if row:
        return {"descricao": (row.get("descricao") or "").strip(), "ncm": "", "unidade": "UN", "cod_icms": "", "origem": 0}
    return {"descricao": codigo_int, "ncm": "", "unidade": "UN", "cod_icms": "", "origem": 0}


def _calcular_pis_cofins_item(taxa: dict, base: float) -> dict:
    """Best-effort a partir das colunas confirmadas de `taxas`
    (`CST_TRIB_PIS`/`ALQT_TRIB_PIS`/`CST_TRIB_COFINS`/`ALQT_TRIB_COFINS`) —
    **não cruzado linha-a-linha contra `SitTribut`/`Calcula` do VB6 nesta
    rodada** (ver docstring do módulo), validar antes de confiar em
    produção real."""
    alqt_pis = float(taxa.get("ALQT_TRIB_PIS") or taxa.get("alqt_trib_pis") or 0)
    alqt_cofins = float(taxa.get("ALQT_TRIB_COFINS") or taxa.get("alqt_trib_cofins") or 0)
    cst_pis = str(taxa.get("CST_TRIB_PIS") or taxa.get("cst_trib_pis") or "07").strip() or "07"
    cst_cofins = str(taxa.get("CST_TRIB_COFINS") or taxa.get("cst_trib_cofins") or "07").strip() or "07"
    valor_pis = round(base * alqt_pis / 100, 2)
    valor_cofins = round(base * alqt_cofins / 100, 2)
    return {
        "cst_pis": cst_pis, "base_pis": base, "alqt_pis": alqt_pis, "valor_pis": valor_pis,
        "cst_cofins": cst_cofins, "base_cofins": base, "alqt_cofins": alqt_cofins, "valor_cofins": valor_cofins,
    }


def _emitir_nfe_avulsa_sync(
    servidor: str, banco: str, *, codigo: int, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    if not codigo:
        return {"success": False, "message": "Rascunho inválido."}
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        if _sem_permissao(cur, classe=classe, master=master, comando="GRAVAR"):
            conn.close()
            return {"success": False, "message": "Sem permissão para emitir NF-e avulsa."}
        if not nfe_fiscal_common.modulo_nfe_ativo_sync(cur):
            conn.close()
            return {"success": False, "message": "Módulo NFe está desativado — fale com o administrador do sistema."}

        cols = ", ".join(["codigo", "num_nf"] + _CAB_CAMPOS_AUX)
        cur.execute(f"SELECT {cols} FROM nf_aux WHERE codigo=%s", (codigo,))
        cab = cur.fetchone()
        if not cab:
            conn.close()
            return {"success": False, "message": "Rascunho não encontrado."}
        if cab.get("num_nf"):
            conn.close()
            return {"success": False, "message": "Esta NF-e já foi emitida — reemissão não é suportada nesta fase."}

        pessoa_id = cab.get("fornecedor")
        mov = (cab.get("mov") or "").strip()
        cfop_cabecalho = (cab.get("cfop") or "").strip()
        if not pessoa_id or not mov or not cfop_cabecalho or not cab.get("data"):
            conn.close()
            return {"success": False, "message": "Preencha Cliente/Fornecedor, Tipo de Movimentação, CFOP e Data de Emissão antes de emitir."}

        cur.execute("SELECT codigo, origem_destino FROM tipo_mov WHERE codigo=%s", (mov,))
        tm = cur.fetchone()
        if not tm:
            conn.close()
            return {"success": False, "message": "Tipo de Movimentação não cadastrado."}
        is_fornecedor = (tm.get("origem_destino") or "").strip().upper() == "F"

        if is_fornecedor:
            dest_resultado = nfe_fiscal_common.resolver_destinatario_fornecedor_sync(cur, pessoa_id)
        else:
            dest_resultado = nfe_fiscal_common.resolver_destinatario_cliente_sync(cur, pessoa_id)
        if not dest_resultado.get("success"):
            conn.close()
            return dest_resultado
        destinatario = dest_resultado["destinatario"]
        consumidor_final = dest_resultado["consumidor_final"]
        simples_nacional_cliente = dest_resultado["simples_nacional_cliente"]

        cur.execute(
            f"SELECT id_nf_aux, {', '.join(_ITEM_CAMPOS_AUX)} FROM nf_aux_itens WHERE codigo=%s ORDER BY id_nf_aux",
            (codigo,),
        )
        itens_aux = cur.fetchall()
        if not itens_aux:
            conn.close()
            return {"success": False, "message": "Nenhum item lançado — nada a emitir."}

        cur.execute("SELECT cgc, uf, rz_social, numero_nf, serie_nf FROM controle")
        controle = cur.fetchone() or {}
        uf_sigla = (controle.get("uf") or "").strip().upper()

        cur.execute("SELECT descricao FROM tipo_mov WHERE codigo=%s", (mov,))
        tm_desc = cur.fetchone()
        natureza_operacao = (tm_desc.get("descricao") or "Nota Fiscal").strip() if tm_desc else "Nota Fiscal"

        itens_resolvidos = []
        pis_cofins_por_item = []
        valor_total = 0.0
        for item in itens_aux:
            codigo_int = (item.get("codigo_int") or "").strip()
            produto = _resolver_item_produto_sync(cur, codigo_int)
            qtd = float(item.get("qtd") or 0)
            valor_unitario = float(item.get("p_unit") or 0)
            valor_item = round(item.get("valor_total") or (qtd * valor_unitario), 2)
            valor_total += valor_item

            cur.execute("SELECT TOP 1 1 AS ok FROM PECAS_PROTOCOLO_ST WHERE uf=%s AND codigo_int=%s", (uf_sigla, codigo_int))
            protocolo_st = cur.fetchone() is not None
            tributos = nfe_emissao_service._resolver_tributacao_sync(
                cur, cod_icms=produto["cod_icms"], cfop_cupom_fiscal="", tipo_mov=mov,
                uf_destino=destinatario.get("uf") or uf_sigla, uf_controle=uf_sigla,
                nao_contribuinte=not destinatario.get("ie"),
                simples_nacional_cliente=simples_nacional_cliente, consumidor_final=consumidor_final,
                protocolo_st=protocolo_st,
            )
            if not tributos:
                conn.close()
                return {"success": False, "message": f"Produto '{codigo_int}' sem tributação cadastrada em Taxas (Tabelas Auxiliares)."}

            pis_cofins = _calcular_pis_cofins_item(tributos, valor_item)
            pis_cofins_por_item.append(pis_cofins)

            itens_resolvidos.append({
                "codigo_int": codigo_int, "descricao": produto["descricao"], "ncm": produto["ncm"],
                "cfop": cfop_cabecalho, "unidade": produto["unidade"], "qtd": qtd, "valor_unitario": valor_unitario,
                "valor_total": valor_item, "origem": produto["origem"],
                "csosn": "102" if simples_nacional_cliente else "400",
                "cst_pis": pis_cofins["cst_pis"], "cst_cofins": pis_cofins["cst_cofins"],
                "ibs_cbs_xml": "",
                # campos já confirmados/editados pelo usuário no rascunho (ICMS/IPI/ISS) —
                # não recalculados aqui (decisão 1), só repassados pra gravação em n_fiscal_itens.
                "_alqt_icms": item.get("alqt_icms"), "_reducao_base_icms": item.get("reducao_base_icms"),
                "_base_icms": item.get("base_icms"), "_valor_icms": item.get("valor_icms"),
                "_base_ipi": item.get("base_ipi"), "_alqt_ipi": item.get("alqt_ipi"), "_valor_ipi": item.get("valor_ipi"),
                "_base_sub": item.get("base_sub"), "_valor_sub": item.get("valor_sub"),
                "_base_iss": item.get("base_iss"), "_valor_iss": item.get("valor_iss"),
                "_frete": item.get("frete"), "_seguro": item.get("seguro"), "_despesas": item.get("despesas"),
                "_desconto": item.get("desconto"), "_tributacao": item.get("tributacao"),
                "_cod_fiscal": item.get("cod_fiscal"), "_obs_item_nf": item.get("obs_item_nf"),
            })

        proximo_numero = int(controle.get("numero_nf") or 0) + 1
        serie = str(controle.get("serie_nf") or "1")

        resultado = nfe_emissao_service.emitir_nfe_sync(
            cur, cnpj_emit=(controle.get("cgc") or ""), nome_emit=(controle.get("rz_social") or ""),
            uf_sigla=uf_sigla, proximo_numero=proximo_numero, serie=serie, destinatario=destinatario,
            itens_resolvidos=itens_resolvidos, valor_total=round(valor_total, 2), tp_amb="1",
            natureza_operacao=natureza_operacao, indFinal="1" if consumidor_final else "0",
        )
        if not resultado.get("success"):
            conn.close()
            return resultado

        situacao_n_fiscal = resultado.get("situacao") or "A"
        cstat_n_fiscal = resultado.get("cstat") or "100"
        cur.execute(
            "INSERT INTO n_fiscal (num_nf, serie_nf, fornecedor, mov, cfop, uf, data_nf, data_mov, data_saida, "
            "valor_total, frete, seguro, despesas, desconto, nf_aux, situacao, chave_acesso, protocolo_sefaz, "
            "dhRecbto, cstat, xml) "
            "OUTPUT INSERTED.codigo "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (
                resultado["numero"], resultado["serie"], pessoa_id, mov, cfop_cabecalho, uf_sigla,
                cab.get("data"), cab.get("data_mov"), cab.get("data_saida"),
                round(valor_total, 2), cab.get("frete"), cab.get("seguro"), cab.get("despesas"),
                cab.get("desconto"), codigo, situacao_n_fiscal,
                resultado["chave_acesso"], resultado["protocolo_sefaz"], resultado.get("dh_recbto"),
                cstat_n_fiscal, resultado["xml"],
            ),
        )
        codigo_n_fiscal = int(cur.fetchone()["codigo"])

        for item, pis_cofins in zip(itens_resolvidos, pis_cofins_por_item):
            cur.execute(
                "INSERT INTO n_fiscal_itens (codigo, codigo_int, cod_fiscal, tributacao, qtd, p_unit, "
                "alqt_icms, reducao_base_icms, base_icms, valor_icms, base_ipi, alqt_ipi, valor_ipi, "
                "base_sub, valor_sub, base_iss, valor_iss, frete, seguro, despesas, desconto, valor_total, "
                "tributacao_pis, base_pis, alqt_pis, valor_pis, tributacao_cofins, base_cofins, alqt_cofins, valor_cofins, "
                "obs_item_nf) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    codigo_n_fiscal, item["codigo_int"], item["_cod_fiscal"], item["_tributacao"],
                    item["qtd"], item["valor_unitario"],
                    item["_alqt_icms"], item["_reducao_base_icms"], item["_base_icms"], item["_valor_icms"],
                    item["_base_ipi"], item["_alqt_ipi"], item["_valor_ipi"],
                    item["_base_sub"], item["_valor_sub"], item["_base_iss"], item["_valor_iss"],
                    item["_frete"], item["_seguro"], item["_despesas"], item["_desconto"], item["valor_total"],
                    pis_cofins["cst_pis"], pis_cofins["base_pis"], pis_cofins["alqt_pis"], pis_cofins["valor_pis"],
                    pis_cofins["cst_cofins"], pis_cofins["base_cofins"], pis_cofins["alqt_cofins"], pis_cofins["valor_cofins"],
                    item["_obs_item_nf"],
                ),
            )

        cur.execute(
            "SELECT SEQUENCIA_NF_AUX_VENCIMENTO, data_venc, valor FROM nf_aux_vencimento WHERE codigo=%s",
            (codigo,),
        )
        for v in cur.fetchall():
            cur.execute(
                "INSERT INTO nf_vencimento (codigo, data_venc, valor) VALUES (%s, %s, %s)",
                (codigo_n_fiscal, v["data_venc"], v["valor"]),
            )

        # IBS/CBS (Reforma Tributária) — só agora, com `codigo_n_fiscal` já
        # existente (decisão 3). Grava DIRETO nas colunas estruturadas de
        # `n_fiscal_itens` (não reescreve XML — achado desta sessão, essas
        # colunas já existem e casam com o que `ibs_cbs_service` devolve).
        cur.execute("SELECT id FROM n_fiscal_itens WHERE codigo=%s ORDER BY id", (codigo_n_fiscal,))
        ids_itens = [r["id"] for r in cur.fetchall()]
        ibs_cbs_calculados = []
        for id_item, item in zip(ids_itens, itens_resolvidos):
            taxa_nfce = ibs_cbs_service.resolver_taxa_nfce_para_ibs_cbs_sync(
                cur, cod_icms=(_resolver_item_produto_sync(cur, item["codigo_int"])["cod_icms"]), destino=uf_sigla,
            )
            ibs_cbs_item = (
                ibs_cbs_service.calcular_item_ibs_cbs(
                    qtd=item["qtd"], p_unit=item["valor_unitario"], codigo_int=item["codigo_int"], taxa=taxa_nfce
                )
                if taxa_nfce else None
            )
            ibs_cbs_calculados.append(ibs_cbs_item)
            if ibs_cbs_item:
                cur.execute(
                    "UPDATE n_fiscal_itens SET CST_IBS_UF=%s, CLASSTRIB_IBS_UF=%s, BASE_IBS_UF=%s, ALQT_IBS_UF=%s, "
                    "VALOR_IBS_UF=%s, CST_IBS_MUNICIPIO=%s, CLASSTRIB_IBS_MUNICIPIO=%s, BASE_IBS_MUNICIPIO=%s, "
                    "ALQT_IBS_MUNICIPIO=%s, VALOR_IBS_MUNICIPIO=%s, CST_CBS=%s, CLASSTRIB_CBS=%s, BASE_CBS=%s, "
                    "ALQT_CBS=%s, VALOR_CBS=%s WHERE id=%s",
                    (
                        ibs_cbs_item["cst_ibs_uf"], ibs_cbs_item["classtrib_ibs_uf"], ibs_cbs_item["base_ibs_uf"],
                        ibs_cbs_item["alqt_ibs_uf"], ibs_cbs_item["valor_ibs_uf"],
                        ibs_cbs_item["cst_ibs_municipio"], ibs_cbs_item["classtrib_ibs_municipio"],
                        ibs_cbs_item["base_ibs_municipio"], ibs_cbs_item["alqt_ibs_municipio"], ibs_cbs_item["valor_ibs_municipio"],
                        ibs_cbs_item["cst_cbs"], ibs_cbs_item["classtrib_cbs"], ibs_cbs_item["base_cbs"],
                        ibs_cbs_item["alqt_cbs"], ibs_cbs_item["valor_cbs"], id_item,
                    ),
                )
        ibs_cbs_totais = ibs_cbs_service.calcular_totais_ibs_cbs(ibs_cbs_calculados)
        cur.execute("UPDATE n_fiscal SET XML_TOT_IBS_CBS=%s WHERE codigo=%s", (ibs_cbs_totais["xml_totais"], codigo_n_fiscal))

        cur.execute("UPDATE nf_aux SET num_nf=%s WHERE codigo=%s", (codigo_n_fiscal, codigo))
        cur.execute("UPDATE controle SET numero_nf=%s", (resultado["numero"],))
        conn.commit()
        cur.close()
        conn.close()
        resultado["nota_fisc"] = codigo_n_fiscal
        resultado["rascunho"] = codigo
        return resultado
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


# ---------------------------------------------------------------------------
# Wrappers async
# ---------------------------------------------------------------------------

async def novo_rascunho(servidor: str, banco: str, classe: Optional[int] = None, master: bool = False) -> dict:
    return await asyncio.to_thread(_novo_rascunho_sync, servidor, banco, classe=classe, master=master)


async def get_rascunho(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_rascunho_sync, servidor, banco, codigo)


async def save_cabecalho_rascunho(servidor: str, banco: str, codigo: int, dados: dict) -> dict:
    return await asyncio.to_thread(_save_cabecalho_rascunho_sync, servidor, banco, codigo, dados)


async def save_itens_rascunho(servidor: str, banco: str, codigo: int, itens: list) -> dict:
    return await asyncio.to_thread(_save_itens_rascunho_sync, servidor, banco, codigo, itens)


async def save_vencimentos_rascunho(servidor: str, banco: str, codigo: int, vencimentos: list) -> dict:
    return await asyncio.to_thread(_save_vencimentos_rascunho_sync, servidor, banco, codigo, vencimentos)


async def sugerir_tributacao(
    servidor: str, banco: str, codigo_int: str, mov: str, uf_destino: str,
    nao_contribuinte: bool, simples_nacional_cliente: bool, consumidor_final: bool,
) -> dict:
    return await asyncio.to_thread(
        _sugerir_tributacao_sync, servidor, banco, codigo_int=codigo_int, mov=mov, uf_destino=uf_destino,
        nao_contribuinte=nao_contribuinte, simples_nacional_cliente=simples_nacional_cliente,
        consumidor_final=consumidor_final,
    )


async def emitir_nfe_avulsa(
    servidor: str, banco: str, codigo: int, usuario: Optional[int] = None,
    classe: Optional[int] = None, master: bool = False,
) -> dict:
    return await asyncio.to_thread(
        _emitir_nfe_avulsa_sync, servidor, banco, codigo=codigo, usuario=usuario, classe=classe, master=master,
    )
