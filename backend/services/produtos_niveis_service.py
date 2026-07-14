"""Alterações Cadastro de Produtos Níveis — alteração em massa de pecas/servicos
filtrando por faixa de NCM (codigo_mercosul) ou por nível (grupo mercadológico,
tabela `niveis`). Legado VB6: FrmAltNiv.

Todas as ações de escrita (gravar campos, reajustar preço, % Lei Transparência,
desativar por estoque, reprocessar estoque) exigem `confirmar=True` — a tela
sempre roda `preview()` antes e só libera o botão de confirmar depois de exibir
a contagem de produtos/serviços afetados (camada de segurança nova, pedida pelo
usuário — não existe no legado).

REPROC_ITEM/REPROC_RESERV substituem a restrição hardcoded a "KONTACTO" do
legado por um gate real via `tem_permissao()` — mesmo padrão já usado em
`os_service.py` para `OS.SITUACAO`. O mesmo gate é aplicado às demais ações
desta tela, por serem updates em massa sobre dados reais de estoque/preço.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.produtos_niveis import (
    DesativarEstoqueRequest,
    GravarCamposRequest,
    LeiTransparenciaRequest,
    PreviewRequest,
    ReajustePrecoRequest,
    ReprocessarItemRequest,
    ReprocessarReservadosRequest,
)
from services import log_auditoria_service
from services.permissoes_service import tem_permissao

TELA = "PRODUTO_NIVEIS"


# ---------------- Filtro (NCM x Nível) ----------------

def _load_nivel_levels(cur, cod_nivel: int) -> Optional[list]:
    cur.execute(
        "SELECT nivel1, nivel2, nivel3, nivel4, nivel5 FROM niveis WHERE cod_nivel=%s",
        (cod_nivel,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return [(row.get(f"nivel{i}") or "").strip() for i in range(1, 6)]


def _nivel_condicao(alias: str, levels: list, incluir_inferiores: bool) -> tuple:
    if incluir_inferiores:
        depth = sum(1 for v in levels if v)
        if depth == 0:
            return "1=1", []
        cond = " AND ".join(f"{alias}.nivel{i}=%s" for i in range(1, depth + 1))
        return cond, levels[:depth]
    cond = " AND ".join(f"{alias}.nivel{i}=%s" for i in range(1, 6))
    return cond, levels


def _build_filtro_where(alias: str, req, cur) -> tuple:
    """Retorna (where_sql, params) para a tabela `alias` (pecas/servicos), ou
    (None, None) se o filtro estiver incompleto/inválido."""
    if req.modo_filtro == "ncm":
        de = (req.ncm_de or "").strip()
        ate = (req.ncm_ate or "").strip()
        if not de or not ate or not de.isdigit() or not ate.isdigit():
            return None, None
        return (
            f"TRY_CONVERT(BIGINT, {alias}.codigo_mercosul) BETWEEN %s AND %s",
            [int(de), int(ate)],
        )
    if not req.nivel_cod_nivel:
        return None, None
    levels = _load_nivel_levels(cur, req.nivel_cod_nivel)
    if levels is None:
        return None, None
    return _nivel_condicao(alias, levels, req.nivel_incluir_inferiores)


def _descrever_filtro(cur, req) -> str:
    """Descrição legível do filtro aplicado, usada como `referencia` no log de
    auditoria (ex.: "NCM 0-99999999" ou "Nível: Cervejas (+ níveis inferiores)")."""
    if req.modo_filtro == "ncm":
        return f"NCM {req.ncm_de}-{req.ncm_ate}"
    if req.nivel_cod_nivel:
        cur.execute("SELECT descr FROM niveis WHERE cod_nivel=%s", (req.nivel_cod_nivel,))
        row = cur.fetchone()
        nome = (row.get("descr") or "").strip() if row else ""
        sufixo = " (+ níveis inferiores)" if req.nivel_incluir_inferiores else ""
        return f"Nível: {nome or req.nivel_cod_nivel}{sufixo}"
    return ""


def _preview_sync(req: PreviewRequest) -> dict:
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        total_pecas = 0
        total_servicos = 0
        if req.incluir_pecas:
            where, params = _build_filtro_where("pecas", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(f"SELECT COUNT(*) AS n FROM pecas WHERE {where}", tuple(params))
            total_pecas = int(cur.fetchone()["n"])
        if req.incluir_servicos:
            where, params = _build_filtro_where("servicos", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(f"SELECT COUNT(*) AS n FROM servicos WHERE {where}", tuple(params))
            total_servicos = int(cur.fetchone()["n"])
        return {
            "success": True, "total_pecas": total_pecas, "total_servicos": total_servicos,
            "total": total_pecas + total_servicos,
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# Limite de linhas retornadas por tabela na listagem de itens da prévia — a tela
# só usa isso para conferência visual antes de confirmar, não para paginar a
# operação em massa em si (que continua sendo feita direto no banco pelo WHERE).
PREVIEW_ITENS_LIMITE = 300


def _preview_itens_sync(req: PreviewRequest) -> dict:
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        itens = []
        if req.incluir_pecas:
            where, params = _build_filtro_where("pecas", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(
                f"SELECT TOP {PREVIEW_ITENS_LIMITE} codigo_int AS codigo, descricao, p_venda AS valor, "
                f"custo_reposicao FROM pecas WHERE {where} ORDER BY descricao",
                tuple(params),
            )
            for r in cur.fetchall():
                itens.append({
                    "tipo": "P", "codigo": (r.get("codigo") or "").strip(),
                    "descricao": (r.get("descricao") or "").strip(), "valor": float(r.get("valor") or 0),
                    "custo_reposicao": float(r["custo_reposicao"]) if r.get("custo_reposicao") is not None else None,
                })
        if req.incluir_servicos:
            where, params = _build_filtro_where("servicos", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(
                f"SELECT TOP {PREVIEW_ITENS_LIMITE} codigo, descricao, valor_hora AS valor "
                f"FROM servicos WHERE {where} ORDER BY descricao",
                tuple(params),
            )
            for r in cur.fetchall():
                itens.append({
                    "tipo": "S", "codigo": (r.get("codigo") or "").strip(),
                    "descricao": (r.get("descricao") or "").strip(), "valor": float(r.get("valor") or 0),
                    "custo_reposicao": None,
                })
        return {"success": True, "items": itens, "limite": PREVIEW_ITENS_LIMITE}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------- Gravar Campos ----------------

def _identity(v):
    return v


def _to_int(v):
    return int(v)


def _invert_bool_to_smallint(v: bool) -> int:
    # legado: "Sim" -> 0, "Não" -> 1 (paga_comissao / aceita_desconto)
    return 0 if v else 1


def _bool_to_bit(v: bool) -> int:
    return 1 if v else 0


def _upper1(v: str) -> str:
    return (v or "").strip().upper()[:1]


def _upper2(v: str) -> str:
    return (v or "").strip().upper()[:2]


# Colunas presentes tanto em `pecas` quanto em `servicos`.
SHARED_FIELD_MAP = [
    ("cst_pis", "tributacao_pis", _to_int),
    ("perc_valor_pis", "perc_valor_pis", _identity),
    ("cst_cofins", "tributacao_cofins", _to_int),
    ("perc_valor_cofins", "perc_valor_cofins", _identity),
    ("cod_icms", "cod_icms", _identity),
    ("desc_g", "desc_g", _identity),
    ("desc_s", "desc_s", _identity),
    ("desc_v", "desc_v", _identity),
    ("comissao", "comissao", _identity),
    ("valor_comissao", "valor_comissao", _identity),
    ("valor_desc_base_comissao", "valor_desc_base_comissao", _identity),
    ("comissao_e", "comissao_e", _identity),
    ("valor_comissao_e", "valor_comissao_e", _identity),
    ("valor_desc_base_comissao_e", "valor_desc_base_comissao_e", _identity),
    ("comissao_a", "comissao_a", _identity),
    ("valor_comissao_a", "valor_comissao_a", _identity),
    ("valor_desc_base_comissao_a", "valor_desc_base_comissao_a", _identity),
    ("paga_comissao", "paga_comissao", _invert_bool_to_smallint),
    ("aceita_desconto", "aceita_desconto", _invert_bool_to_smallint),
    ("tipo_garantia", "tipo_garantia", _identity),
    ("prazo_garantia", "prazo_garantia", _identity),
    ("preco_variado", "preco_variado", _bool_to_bit),
    ("situacao", "situacao", _upper2),
]

# Colunas só existentes em `pecas`.
PECAS_EXTRA_FIELD_MAP = [
    ("perc_mva", "perc_mva", _identity),
    ("outros_trib_federais", "outros_trib_federais", _identity),
    ("margem_lucro", "margem_lucro", _identity),
    ("margem_tabela", "margem_tabela", _identity),
    ("estoque_minimo", "estoque_minimo", _identity),
    ("origem", "origem", _upper1),
    ("tipo_peca", "tipo_peca", _identity),
    ("politica_preco", "politica_preco", _upper1),
]


def _collect_campos(req, field_map) -> tuple:
    sets, params = [], []
    for attr, col, transform in field_map:
        v = getattr(req, attr, None)
        if v is None:
            continue
        sets.append(f"{col}=%s")
        params.append(transform(v))
    return sets, params


def _campos_preenchidos(req, field_map) -> list:
    """Lista {campo, valor} (valor original do request, não a versão transformada
    pro SQL) só dos campos realmente preenchidos — usada no log de auditoria."""
    out = []
    for attr, _col, _transform in field_map:
        v = getattr(req, attr, None)
        if v is None:
            continue
        out.append({"campo": attr, "valor": str(v)})
    return out


def _validar_fks(cur, req: GravarCamposRequest) -> Optional[str]:
    checks = []
    if req.cst_pis:
        checks.append(("cst_pis", "CST_Pis", req.cst_pis.strip(), "CST Pis"))
    if req.cst_cofins:
        checks.append(("cst_cofins", "CST_Cofins", req.cst_cofins.strip(), "CST Cofins"))
    if req.cod_icms:
        checks.append(("dscr_icms", "cod_icms", req.cod_icms.strip(), "Código Icms"))
    if req.origem:
        checks.append(("origem", "codigo", req.origem.strip(), "Origem"))
    if req.tipo_peca is not None:
        checks.append(("tipo_peca", "codigo", req.tipo_peca, "Finalidade"))
    if req.uf_protocolo_st:
        checks.append(("uf", "codigo", req.uf_protocolo_st.strip().upper()[:2], "UF Protocolo ST"))
    for tabela, coluna, valor, label in checks:
        cur.execute(f"SELECT TOP 1 1 AS ok FROM {tabela} WHERE {coluna}=%s", (valor,))
        if not cur.fetchone():
            return f"{label} não cadastrado(a): '{valor}'."
    return None


def _gravar_campos_sync(req: GravarCamposRequest, ip_origem: Optional[str] = None) -> dict:
    if not req.confirmar:
        return {"success": False, "message": "Confirmação obrigatória."}
    if not req.incluir_pecas and not req.incluir_servicos:
        return {"success": False, "message": "Selecione ao menos Produtos ou Serviços."}
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "GRAVAR"):
            return {"success": False, "message": "Sem permissão para gravar alterações."}

        erro_fk = _validar_fks(cur, req)
        if erro_fk:
            return {"success": False, "message": erro_fk}

        try:
            shared_sets, shared_params = _collect_campos(req, SHARED_FIELD_MAP)
            pecas_extra_sets, pecas_extra_params = _collect_campos(req, PECAS_EXTRA_FIELD_MAP)
        except (TypeError, ValueError) as e:
            return {"success": False, "message": f"Valor inválido: {e}"}

        if not shared_sets and not pecas_extra_sets and not req.uf_protocolo_st:
            return {"success": False, "message": "Nenhum campo foi preenchido para alteração."}

        pecas_afetadas = 0
        servicos_afetadas = 0

        if req.incluir_pecas:
            where, wparams = _build_filtro_where("pecas", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}

            sets = list(shared_sets) + list(pecas_extra_sets)
            params = list(shared_params) + list(pecas_extra_params)
            if sets:
                sets.append("data_alteracao=CAST(GETDATE() AS DATE)")
                if req.usuario_alteracao is not None:
                    sets.append("usuario_alteracao=%s")
                    params.append(req.usuario_alteracao)
                cur.execute(f"UPDATE pecas SET {', '.join(sets)} WHERE {where}", tuple(params) + tuple(wparams))
                pecas_afetadas = cur.rowcount

            if req.uf_protocolo_st:
                uf = req.uf_protocolo_st.strip().upper()[:2]
                cur.execute(
                    f"INSERT INTO pecas_protocolo_st (codigo_int, UF) "
                    f"SELECT pecas.codigo_int, %s FROM pecas WHERE {where} "
                    f"AND NOT EXISTS (SELECT 1 FROM pecas_protocolo_st pst "
                    f"WHERE pst.codigo_int=pecas.codigo_int AND pst.UF=%s)",
                    (uf,) + tuple(wparams) + (uf,),
                )

        if req.incluir_servicos and shared_sets:
            where, wparams = _build_filtro_where("servicos", req, cur)
            if where is None:
                conn.rollback()
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(
                f"UPDATE servicos SET {', '.join(shared_sets)} WHERE {where}",
                tuple(shared_params) + tuple(wparams),
            )
            servicos_afetadas = cur.rowcount

        conn.commit()

        campos_log = _campos_preenchidos(req, SHARED_FIELD_MAP) + _campos_preenchidos(req, PECAS_EXTRA_FIELD_MAP)
        if req.uf_protocolo_st:
            campos_log.append({"campo": "uf_protocolo_st", "valor": req.uf_protocolo_st})
        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=_descrever_filtro(cur, req),
            descricao=f"{pecas_afetadas} produto(s) e {servicos_afetadas} serviço(s) alterados",
            campos_alterados=campos_log or None, ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {
            "success": True, "pecas_afetadas": pecas_afetadas, "servicos_afetadas": servicos_afetadas,
            "message": "Alterações gravadas.",
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


# ---------------- Reajuste de Preço ----------------

def _reajustar_preco_sync(req: ReajustePrecoRequest, ip_origem: Optional[str] = None) -> dict:
    if not req.confirmar:
        return {"success": False, "message": "Confirmação obrigatória."}
    if not req.incluir_pecas and not req.incluir_servicos:
        return {"success": False, "message": "Selecione ao menos Produtos ou Serviços."}
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "REAJUSTAR"):
            return {"success": False, "message": "Sem permissão para reajustar preços."}

        fator = 1 + (req.percentual / 100.0)
        pecas_afetadas = 0
        servicos_afetadas = 0

        if req.incluir_pecas:
            where, wparams = _build_filtro_where("pecas", req, cur)
            if where is None:
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            base_col = "custo_reposicao" if req.pelo_custo_reposicao else "p_venda"
            sets = [f"p_venda = {base_col} * %s"]
            params = [fator]
            if req.alterar_preco_tabela:
                sets.append(f"p_sugestao = {base_col} * %s")
                params.append(fator)
            cur.execute(f"UPDATE pecas SET {', '.join(sets)} WHERE {where}", tuple(params) + tuple(wparams))
            pecas_afetadas = cur.rowcount

            if req.arredondar:
                # regra do legado (Command4_Click): se o preço tiver centavos,
                # arredonda para cima para o próximo valor inteiro.
                cols_round = ["p_venda"] + (["p_sugestao"] if req.alterar_preco_tabela else [])
                for col in cols_round:
                    cur.execute(
                        f"UPDATE pecas SET {col} = FLOOR({col}) + 1 "
                        f"WHERE {where} AND {col} <> FLOOR({col})",
                        tuple(wparams),
                    )

        if req.incluir_servicos and not req.pelo_custo_reposicao:
            where, wparams = _build_filtro_where("servicos", req, cur)
            if where is None:
                conn.rollback()
                return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}
            cur.execute(f"UPDATE servicos SET valor_hora = valor_hora * %s WHERE {where}", (fator,) + tuple(wparams))
            servicos_afetadas = cur.rowcount

        conn.commit()

        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando="REAJUSTAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=_descrever_filtro(cur, req),
            descricao=f"{pecas_afetadas} produto(s) e {servicos_afetadas} serviço(s) reajustados em {req.percentual}%",
            campos_alterados=[
                {"campo": "percentual", "valor": str(req.percentual)},
                {"campo": "alterar_preco_tabela", "valor": str(req.alterar_preco_tabela)},
                {"campo": "pelo_custo_reposicao", "valor": str(req.pelo_custo_reposicao)},
                {"campo": "arredondar", "valor": str(req.arredondar)},
            ],
            ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {
            "success": True, "pecas_afetadas": pecas_afetadas, "servicos_afetadas": servicos_afetadas,
            "message": "Reajuste aplicado.",
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------- % Lei Transparência Fiscal ----------------

def _lei_transparencia_sync(req: LeiTransparenciaRequest, ip_origem: Optional[str] = None) -> dict:
    if not req.confirmar:
        return {"success": False, "message": "Confirmação obrigatória."}
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "LEI_TRANSP"):
            return {"success": False, "message": "Sem permissão para processar a Lei da Transparência."}

        cur.execute("SELECT uf FROM controle")
        crow = cur.fetchone()
        uf_empresa = (crow.get("uf") or "").strip() if crow else ""
        if not uf_empresa:
            return {"success": False, "message": "UF da empresa não configurada em Controle."}

        where, wparams = _build_filtro_where("pecas", req, cur)
        if where is None:
            return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}

        cur.execute(
            f"SELECT codigo_int, perc_ipi, perc_valor_pis, perc_valor_cofins, cod_icms "
            f"FROM pecas WHERE {where}",
            tuple(wparams),
        )
        rows = cur.fetchall()
        afetadas = 0
        for r in rows:
            icms_pct = 0.0
            cod_icms = (r.get("cod_icms") or "").strip()
            if cod_icms:
                cur.execute(
                    "SELECT icms FROM taxas WHERE cod_icms=%s AND tipo_mov='S01' "
                    "AND destino=%s AND tipo_destino='C'",
                    (cod_icms, uf_empresa),
                )
                trow = cur.fetchone()
                if trow and trow.get("icms") is not None:
                    icms_pct = float(trow["icms"])
            total_trib = (
                float(r.get("perc_ipi") or 0)
                + float(r.get("perc_valor_pis") or 0)
                + float(r.get("perc_valor_cofins") or 0)
                + icms_pct
            )
            outros = req.percentual - total_trib
            cur.execute("UPDATE pecas SET outros_trib_federais=%s WHERE codigo_int=%s", (outros, r["codigo_int"]))
            afetadas += 1

        conn.commit()

        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando="LEI_TRANSP",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=_descrever_filtro(cur, req),
            descricao=f"{afetadas} produto(s) processados (percentual {req.percentual}%)",
            campos_alterados=[{"campo": "percentual", "valor": str(req.percentual)}],
            ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {"success": True, "pecas_afetadas": afetadas, "message": "Processamento concluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------- Utilidades de Estoque ----------------

def _desativar_estoque_sync(req: DesativarEstoqueRequest, negativo: bool, ip_origem: Optional[str] = None) -> dict:
    if not req.confirmar:
        return {"success": False, "message": "Confirmação obrigatória."}
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        acao = "DESATIVAR_NEG" if negativo else "DESATIVAR_ZERO"
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, acao):
            return {"success": False, "message": "Sem permissão para esta ação."}

        where, wparams = _build_filtro_where("pecas", req, cur)
        if where is None:
            return {"success": False, "message": "Filtro inválido — selecione um nível ou informe a faixa de NCM."}

        cond_estoque = "(qtd+reservado+reservado_os) < 0" if negativo else "(qtd+reservado+reservado_os) = 0"
        cur.execute(f"UPDATE pecas SET situacao='D' WHERE {where} AND {cond_estoque}", tuple(wparams))
        afetadas = cur.rowcount
        conn.commit()

        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando=acao,
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=_descrever_filtro(cur, req),
            descricao=f"{afetadas} produto(s) desativados",
            ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {"success": True, "pecas_afetadas": afetadas, "message": "Produtos desativados."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _recompute_estoque_item(cur, codigo_int: str) -> None:
    """Recalcula qtd/reservado/reservado_os de UM produto a partir do histórico
    de movimentacao/orcamento/os/pedido_venda — porta a lógica de
    Command9_Click/Command10_Click do legado FrmAltNiv (substitui o padrão
    IIF(ISNULL(sum(...),'')='',0,sum(...)) do VB6/Access por ISNULL(SUM(...),0),
    equivalente em SQL Server, sem mudar o resultado)."""
    cur.execute("UPDATE pecas SET qtd=0, reservado=0, reservado_os=0 WHERE codigo_int=%s", (codigo_int,))

    # saídas normais (fora de comanda/PDV)
    cur.execute(
        "UPDATE pecas SET qtd = qtd - ("
        "  SELECT ISNULL(SUM(m.qtd),0) FROM movimentacao m, tipo_mov tm "
        "  WHERE m.serie_nf<>'CM' AND m.codigo_int=%s "
        "    AND LEFT(m.tipo,1)='S' AND m.tipo=tm.codigo AND tm.atualiza_est='S'"
        ") WHERE codigo_int=%s",
        (codigo_int, codigo_int),
    )
    # saídas via comanda (PDV) paga
    cur.execute(
        "UPDATE pecas SET qtd = qtd - ("
        "  SELECT ISNULL(SUM(m.qtd),0) FROM movimentacao m, tipo_mov tm, comanda c "
        "  WHERE c.comanda=m.num_nf AND c.situacao='PG' AND m.serie_nf='CM' AND m.codigo_int=%s "
        "    AND LEFT(m.tipo,1)='S' AND m.tipo=tm.codigo AND tm.atualiza_est='S'"
        ") WHERE codigo_int=%s",
        (codigo_int, codigo_int),
    )
    # saídas via comanda cancelada mas estornada
    cur.execute(
        "UPDATE pecas SET qtd = qtd - ("
        "  SELECT ISNULL(SUM(m.qtd),0) FROM movimentacao m, tipo_mov tm, comanda c "
        "  WHERE c.comanda=m.num_nf AND c.situacao='C' AND m.estornado=1 AND m.serie_nf='CM' AND m.codigo_int=%s "
        "    AND LEFT(m.tipo,1)='S' AND m.tipo=tm.codigo AND tm.atualiza_est='S'"
        ") WHERE codigo_int=%s",
        (codigo_int, codigo_int),
    )
    # entradas
    cur.execute(
        "UPDATE pecas SET qtd = qtd + ("
        "  SELECT ISNULL(SUM(m.qtd),0) FROM movimentacao m, tipo_mov tm "
        "  WHERE m.codigo_int=%s AND LEFT(m.tipo,1)='E' AND m.tipo=tm.codigo AND tm.atualiza_est='S'"
        ") WHERE codigo_int=%s",
        (codigo_int, codigo_int),
    )
    # reservas de orçamento fechado
    cur.execute(
        "UPDATE pecas SET "
        "  qtd = qtd - (SELECT ISNULL(SUM(op.qtd),0) FROM orcamento o, orc_produto op "
        "               WHERE o.orc=op.orc AND op.prod=%s AND o.situacao='F'), "
        "  reservado = reservado + (SELECT ISNULL(SUM(op.qtd),0) FROM orcamento o, orc_produto op "
        "                            WHERE o.orc=op.orc AND op.prod=%s AND o.situacao='F') "
        "WHERE codigo_int=%s",
        (codigo_int, codigo_int, codigo_int),
    )
    # reservas de O.S. (com/sem exigência de aprovação de item — controle_aux.exige_aprovacao_itens_os)
    cur.execute("SELECT exige_aprovacao_itens_os FROM controle_aux")
    crow = cur.fetchone()
    exige_aprovacao = int((crow or {}).get("exige_aprovacao_itens_os") or 0) == 1
    cond_aprov = "AND op.quant=op.qtd_autorizada " if exige_aprovacao else ""
    cond_situacao = (
        "((o.situacao='F' OR o.situacao='A') OR (o.situacao='PG' AND op.situacao<>0 AND op.faturado=0))"
    )
    cur.execute(
        f"UPDATE pecas SET "
        f"  qtd = qtd - (SELECT ISNULL(SUM(op.quant),0) FROM os o, os_produto op "
        f"               WHERE o.codigo=op.os AND op.codigo_interno=%s {cond_aprov}AND {cond_situacao}), "
        f"  reservado_os = reservado_os + (SELECT ISNULL(SUM(op.quant),0) FROM os o, os_produto op "
        f"                                 WHERE o.codigo=op.os AND op.codigo_interno=%s {cond_aprov}AND {cond_situacao}) "
        f"WHERE codigo_int=%s",
        (codigo_int, codigo_int, codigo_int),
    )
    # reservas de Pedido de Venda fechado
    cur.execute(
        "UPDATE pecas SET "
        "  qtd = qtd - (SELECT ISNULL(SUM(pp.qtd_pedida),0) FROM pedido_venda pv, pedido_venda_prod pp "
        "               WHERE pv.pedido=pp.pedido AND pp.produto=%s AND pv.situacao='F'), "
        "  reservado = reservado + (SELECT ISNULL(SUM(pp.qtd_pedida),0) FROM pedido_venda pv, pedido_venda_prod pp "
        "                           WHERE pv.pedido=pp.pedido AND pp.produto=%s AND pv.situacao='F') "
        "WHERE codigo_int=%s",
        (codigo_int, codigo_int, codigo_int),
    )
    cur.execute(
        "UPDATE pecas SET qtd=CAST(qtd AS NUMERIC(15,3)), "
        "reservado=CAST(reservado AS NUMERIC(15,3)), "
        "reservado_os=CAST(reservado_os AS NUMERIC(15,3)) WHERE codigo_int=%s",
        (codigo_int,),
    )


def _reprocessar_item_sync(req: ReprocessarItemRequest, ip_origem: Optional[str] = None) -> dict:
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "REPROC_ITEM"):
            return {"success": False, "message": "Sem permissão para reprocessar estoque."}

        busca = (req.busca or "").strip()
        if not busca:
            return {"success": False, "message": "Informe o código ou descrição do produto."}

        cur.execute("SELECT codigo_int FROM pecas WHERE codigo_fab=%s", (busca,))
        row = cur.fetchone()
        if not row:
            cur.execute("SELECT codigo_int FROM pecas WHERE descricao=%s", (busca,))
            row = cur.fetchone()
        if not row:
            cur.execute("SELECT codigo_int FROM pecas WHERE codigo_int=%s", (busca,))
            row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Produto não encontrado."}

        codigo_int = row["codigo_int"]
        _recompute_estoque_item(cur, codigo_int)
        cur.execute("SELECT qtd, reservado, reservado_os FROM pecas WHERE codigo_int=%s", (codigo_int,))
        r = cur.fetchone()
        conn.commit()

        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando="REPROC_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=codigo_int,
            descricao=f"qtd={r['qtd']} reservado={r['reservado']} reservado_os={r['reservado_os']}",
            ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {
            "success": True, "codigo_int": codigo_int,
            "qtd": float(r["qtd"] or 0), "reservado": float(r["reservado"] or 0),
            "reservado_os": float(r["reservado_os"] or 0),
            "message": "Estoque reprocessado.",
        }
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


def _reprocessar_reservados_sync(req: ReprocessarReservadosRequest, ip_origem: Optional[str] = None) -> dict:
    conn = _open_conn(req.servidor, req.banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, TELA, "REPROC_RESERV"):
            return {"success": False, "message": "Sem permissão para reprocessar estoques reservados."}

        cur.execute("SELECT codigo_int FROM pecas")
        codigos = [r["codigo_int"] for r in cur.fetchall()]
        for codigo_int in codigos:
            _recompute_estoque_item(cur, codigo_int)
        conn.commit()

        log_auditoria_service._registrar_log_sync(
            req.servidor, req.banco, tela=TELA, comando="REPROC_RESERV",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=None,
            descricao=f"{len(codigos)} produto(s) processados (reprocessamento global)",
            ip_origem=ip_origem, plataforma=req.plataforma,
        )

        return {"success": True, "itens_processados": len(codigos), "message": "Reprocessamento concluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}
    finally:
        conn.close()


# ---------------- Wrappers async ----------------

async def preview(req: PreviewRequest) -> dict:
    return await asyncio.to_thread(_preview_sync, req)


async def preview_itens(req: PreviewRequest) -> dict:
    return await asyncio.to_thread(_preview_itens_sync, req)


async def gravar_campos(req: GravarCamposRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_gravar_campos_sync, req, ip_origem)


async def reajustar_preco(req: ReajustePrecoRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_reajustar_preco_sync, req, ip_origem)


async def lei_transparencia(req: LeiTransparenciaRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_lei_transparencia_sync, req, ip_origem)


async def desativar_estoque_negativo(req: DesativarEstoqueRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_desativar_estoque_sync, req, True, ip_origem)


async def desativar_estoque_zerado(req: DesativarEstoqueRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_desativar_estoque_sync, req, False, ip_origem)


async def reprocessar_item(req: ReprocessarItemRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_reprocessar_item_sync, req, ip_origem)


async def reprocessar_reservados(req: ReprocessarReservadosRequest, ip_origem: Optional[str] = None) -> dict:
    return await asyncio.to_thread(_reprocessar_reservados_sync, req, ip_origem)
