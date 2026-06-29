"""Relatório analítico de Margem de Lucro e Faturamento (consolidado multiempresa).

Substitui a rotina legada `RetVendasMargemLucro` (VB6/C#), eliminando a montagem
dinâmica de SQL concatenado por **consultas 100% parametrizadas** e mantendo a
compatibilidade funcional dos cálculos.

Fontes unificadas (UNION ALL) por empresa:
  • Pedidos de Venda  (pedido_venda / pedido_venda_prod)
  • Comandas          (comanda / movimentacao)  -> Vendas Diretas / Garantias
  • Ordens de Serviço (os / os_produto)
para Produtos (pecas) e Serviços (servicos).

Consolidação multiempresa: cada empresa é consultada em paralelo (asyncio.to_thread)
e os registros são totalizados por DAV → Empresa → Consolidado Geral.

Correções de bugs do legado:
  • Margem % do item agora multiplica por 100 (consistente com DAV/Geral).
  • Itens passam a aparecer no detalhamento independentemente de Resultado Operacional.
  • Filtro de nível corrigido (chunks exatos de 3 dígitos: nivel1..nivel5).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

# Máximo de DAVs detalhados retornados por empresa (protege o app de respostas
# gigantes). Os TOTAIS são sempre calculados sobre todos os registros.
MAX_DAVS_DETALHE = 1500


# --------------------------------------------------------------------------- #
# Helpers de cálculo
# --------------------------------------------------------------------------- #
def _margem_pct(venda: float, custo: float, operacional: bool) -> float:
    """Margem percentual conforme a regra do legado.

    Operacional  -> (venda - custo) / custo  * 100   (custo 0 => 100%)
    Não-oper.    -> (venda - custo) / venda  * 100   (venda 0 => 0%)
    """
    if operacional:
        if custo == 0:
            return 100.0
        return round((venda - custo) / custo * 100, 2)
    if venda == 0:
        return 0.0
    return round((venda - custo) / venda * 100, 2)


# --------------------------------------------------------------------------- #
# Builders de cláusulas WHERE (parametrizadas)
# --------------------------------------------------------------------------- #
def _situacao_clause(alias: str, f: dict) -> tuple[list, list]:
    vals = []
    if f.get("davs_abertos"):
        vals.append("A")
    if f.get("davs_fechados"):
        vals.append("F")
    if f.get("davs_faturados"):
        vals.append("PG")
    if not vals:
        return [], []
    placeholders = ",".join(["%s"] * len(vals))
    return [f"{alias}.situacao IN ({placeholders})"], list(vals)


def _nivel_clause(alias: str, nivel: Optional[str]) -> tuple[list, list]:
    clauses, params = [], []
    if nivel and nivel.strip():
        n = nivel.strip()
        parts = [n[i:i + 3] for i in range(0, len(n), 3)][:5]
        for idx, part in enumerate(parts, start=1):
            if part:
                clauses.append(f"{alias}.nivel{idx} = %s")
                params.append(part)
    return clauses, params


def _periodo_clause(coluna: str, f: dict) -> tuple[list, list]:
    return ([f"CAST({coluna} AS DATE) BETWEEN %s AND %s"],
            [f["data_ini"], f["data_fim"]])


# --------------------------------------------------------------------------- #
# Builders de blocos SELECT por fonte (retornam (sql, params))
# --------------------------------------------------------------------------- #
_COLS = ("situacao_item, cliente_nome, data_dav, doc, tipo, item_codigo, "
         "item_descricao, qtd, bruto, desconto, acrescimo, liquido, custo")


def _bloco_pedido(f: dict, item: str) -> tuple[str, list]:
    """item: 'P' (pecas) ou 'S' (servicos)."""
    params: list = []
    where = ["pv.pedido = i.pedido"]
    if item == "P":
        cad_join = "JOIN pecas pe ON pe.codigo_int = i.produto"
        cod, desc, alias_nivel = "pe.codigo_fab", "pe.descricao", "pe"
    else:
        cad_join = "JOIN servicos sv ON sv.codigo = i.produto"
        cod, desc, alias_nivel = "sv.codigo", "sv.descricao", "sv"
    pc, pp = _periodo_clause("pv.data", f); where += pc; params += pp
    sc, sp = _situacao_clause("pv", f); where += sc; params += sp
    nc, npar = _nivel_clause(alias_nivel, f.get("nivel")); where += nc; params += npar
    if f.get("cod_cliente"):
        where.append("pv.cliente = %s"); params.append(f["cod_cliente"])
    if f.get("area_atuacao"):
        where.append("pv.area_atuacao = %s"); params.append(f["area_atuacao"])
    if f.get("cod_dav"):
        where.append("pv.pedido = %s"); params.append(f["cod_dav"])
    sql = (
        f"SELECT 0 AS situacao_item, c.nome AS cliente_nome, pv.data AS data_dav, "
        f"pv.pedido AS doc, 'PED' AS tipo, CAST({cod} AS nvarchar(120)) AS item_codigo, "
        f"CAST({desc} AS nvarchar(200)) AS item_descricao, i.qtd_pedida AS qtd, "
        f"i.p_normal AS bruto, i.desconto AS desconto, i.acrescimo AS acrescimo, "
        f"i.p_venda AS liquido, i.custo_ped AS custo "
        f"FROM pedido_venda_prod i "
        f"JOIN pedido_venda pv ON pv.pedido = i.pedido "
        f"{cad_join} "
        f"LEFT JOIN cliente c ON c.codigo = pv.cliente "
        f"WHERE {' AND '.join(where)}"
    )
    return sql, params


def _bloco_comanda(f: dict, item: str) -> tuple[str, list]:
    params: list = []
    where = ["(m.Estornado = 0 OR m.Estornado IS NULL)",
             "m.serie_nf = 'CM'", "cm.comanda = m.num_nf", "cm.situacao = 'PG'"]
    if item == "P":
        cad_join = "JOIN pecas pe ON pe.codigo_int = m.codigo_int"
        cod, desc, alias_nivel = "pe.codigo_fab", "pe.descricao", "pe"
    else:
        cad_join = "JOIN servicos sv ON sv.codigo = m.codigo_int"
        cod, desc, alias_nivel = "sv.codigo", "sv.descricao", "sv"
    if not f.get("itens_os_nao_cobrados"):
        where.append("cm.tipo <> 1")
    if f.get("somente_garantias"):
        where.append("cm.tipo = 1")
    if f.get("somente_venda_direta"):
        where.append(
            "(cm.comanda NOT IN (SELECT comanda FROM comanda_os WHERE comanda = cm.comanda) "
            "AND cm.comanda NOT IN (SELECT comanda FROM comanda_ped WHERE comanda = cm.comanda))"
        )
    pc, pp = _periodo_clause("cm.data", f); where += pc; params += pp
    nc, npar = _nivel_clause(alias_nivel, f.get("nivel")); where += nc; params += npar
    if f.get("cod_cliente"):
        where.append("cm.cliente = %s"); params.append(f["cod_cliente"])
    if f.get("area_atuacao"):
        where.append("cm.area_atuacao = %s"); params.append(f["area_atuacao"])
    if f.get("cod_dav"):
        where.append("cm.comanda = %s"); params.append(f["cod_dav"])
    sql = (
        f"SELECT 0 AS situacao_item, c.nome AS cliente_nome, cm.data AS data_dav, "
        f"cm.comanda AS doc, 'COM' AS tipo, CAST({cod} AS nvarchar(120)) AS item_codigo, "
        f"CAST({desc} AS nvarchar(200)) AS item_descricao, m.qtd AS qtd, "
        f"0 AS bruto, 0 AS desconto, 0 AS acrescimo, "
        f"m.p_unit AS liquido, m.custo_mov AS custo "
        f"FROM movimentacao m "
        f"JOIN comanda cm ON cm.comanda = m.num_nf "
        f"{cad_join} "
        f"LEFT JOIN cliente c ON c.codigo = cm.cliente "
        f"WHERE {' AND '.join(where)}"
    )
    return sql, params


def _bloco_os(f: dict, item: str) -> tuple[str, list]:
    params: list = []
    where = ["os.codigo = op.os"]
    if item == "P":
        cad_join = "JOIN pecas pe ON pe.codigo_int = op.codigo_interno"
        cod, desc, alias_nivel = "pe.codigo_fab", "pe.descricao", "pe"
    else:
        cad_join = "JOIN servicos sv ON sv.codigo = op.codigo_interno"
        cod, desc, alias_nivel = "sv.codigo", "sv.descricao", "sv"
    if not f.get("itens_os_nao_cobrados"):
        where.append("op.situacao = 0")
    pc, pp = _periodo_clause("os.data_entrada", f); where += pc; params += pp
    sc, sp = _situacao_clause("os", f); where += sc; params += sp
    nc, npar = _nivel_clause(alias_nivel, f.get("nivel")); where += nc; params += npar
    if f.get("cod_cliente"):
        where.append("os.cliente = %s"); params.append(f["cod_cliente"])
    if f.get("area_atuacao"):
        where.append("os.area_atuacao = %s"); params.append(f["area_atuacao"])
    if f.get("cod_dav"):
        where.append("os.codigo = %s"); params.append(f["cod_dav"])
    sql = (
        f"SELECT op.situacao AS situacao_item, c.nome AS cliente_nome, "
        f"os.data_entrada AS data_dav, os.codigo AS doc, 'OS' AS tipo, "
        f"CAST({cod} AS nvarchar(120)) AS item_codigo, "
        f"CAST({desc} AS nvarchar(200)) AS item_descricao, op.quant AS qtd, "
        f"op.p_venda AS bruto, op.desconto AS desconto, op.acrescimo AS acrescimo, "
        f"op.preco_unitario AS liquido, op.custo_os AS custo "
        f"FROM os_produto op "
        f"JOIN os ON os.codigo = op.os "
        f"{cad_join} "
        f"LEFT JOIN cliente c ON c.codigo = os.cliente "
        f"WHERE {' AND '.join(where)}"
    )
    return sql, params


def _montar_query(f: dict) -> tuple[str, list]:
    """Monta o UNION ALL das fontes habilitadas. Retorna (sql, params)."""
    blocos: list[tuple[str, list]] = []
    if f.get("incluir_pedidos"):
        if f.get("retorna_produtos"):
            blocos.append(_bloco_pedido(f, "P"))
        if f.get("retorna_servicos"):
            blocos.append(_bloco_pedido(f, "S"))
    if f.get("incluir_comandas"):
        if f.get("retorna_produtos"):
            blocos.append(_bloco_comanda(f, "P"))
        if f.get("retorna_servicos"):
            blocos.append(_bloco_comanda(f, "S"))
    if f.get("incluir_os"):
        if f.get("retorna_produtos"):
            blocos.append(_bloco_os(f, "P"))
        if f.get("retorna_servicos"):
            blocos.append(_bloco_os(f, "S"))
    if not blocos:
        return "", []
    sql = " UNION ALL ".join(b[0] for b in blocos)
    params: list = []
    for b in blocos:
        params += b[1]
    sql = f"SELECT * FROM ({sql}) AS t ORDER BY data_dav, tipo, doc"
    return sql, params


# --------------------------------------------------------------------------- #
# Consulta por empresa (síncrona, roda em thread)
# --------------------------------------------------------------------------- #
def _agregar(rows: list, operacional: bool) -> tuple[list, float, float]:
    """Agrega linhas de itens em DAVs (pura, testável). Retorna (davs, venda, custo)."""
    davs: dict = {}
    emp_venda = emp_custo = emp_desconto = 0.0
    for r in rows:
        situ = int(r.get("situacao_item") or 0)
        qtd = float(r.get("qtd") or 0)
        custo_unit = float(r.get("custo") or 0)
        # Item de O.S. não cobrado (situacao > 0): zera valores de venda (regra legada).
        if situ > 0:
            bruto = desconto = acrescimo = liquido = 0.0
        else:
            bruto = float(r.get("bruto") or 0)
            desconto = float(r.get("desconto") or 0)
            acrescimo = float(r.get("acrescimo") or 0)
            liquido = float(r.get("liquido") or 0)
        tot_venda = round(qtd * liquido, 2)
        tot_custo = round(qtd * custo_unit, 2)
        desc_line = round(desconto * qtd, 2)
        lucro = round(tot_venda - tot_custo, 2)

        tipo = (r.get("tipo") or "").strip()
        doc = int(r.get("doc") or 0)
        data_val = r.get("data_dav")
        data_str = (data_val.strftime("%Y-%m-%d") if hasattr(data_val, "strftime")
                    else (str(data_val)[:10] if data_val else ""))
        key = f"{tipo}-{doc}"
        dav = davs.get(key)
        if dav is None:
            dav = {
                "tipo": tipo, "codigo": doc, "data": data_str,
                "cliente": (r.get("cliente_nome") or "").strip(),
                "itens": [], "total_venda": 0.0, "total_custo": 0.0, "total_desconto": 0.0,
            }
            davs[key] = dav
        dav["itens"].append({
            "codigo": (r.get("item_codigo") or "").strip(),
            "descricao": (r.get("item_descricao") or "").strip(),
            "qtd": qtd,
            "custo_unit": round(custo_unit, 4),
            "preco_bruto": round(bruto, 2),
            "desconto": round(desconto, 2),
            "acrescimo": round(acrescimo, 2),
            "preco_liquido": round(liquido, 2),
            "total_venda": tot_venda,
            "total_custo": tot_custo,
            "lucro": lucro,
            "margem_pct": _margem_pct(tot_venda, tot_custo, operacional),
        })
        dav["total_venda"] += tot_venda
        dav["total_custo"] += tot_custo
        dav["total_desconto"] += desc_line
        emp_venda += tot_venda
        emp_custo += tot_custo
        emp_desconto += desc_line

    dav_list = []
    for dav in davs.values():
        dav["total_venda"] = round(dav["total_venda"], 2)
        dav["total_custo"] = round(dav["total_custo"], 2)
        dav["lucro"] = round(dav["total_venda"] - dav["total_custo"], 2)
        dav["margem_pct"] = _margem_pct(dav["total_venda"], dav["total_custo"], operacional)
        dav_list.append(dav)
    return dav_list, round(emp_venda, 2), round(emp_custo, 2), round(emp_desconto, 2)


def _consultar_empresa_sync(empresa: str, servidor: str, banco: str, f: dict) -> dict:
    base = {"empresa": empresa, "servidor": servidor, "banco": banco}
    sql, params = _montar_query(f)
    if not sql:
        return {**base, "success": True, "davs": [],
                "total_venda": 0.0, "total_custo": 0.0, "lucro": 0.0, "margem_pct": 0.0,
                "qtd_davs": 0}
    try:
        conn = _open_conn(servidor, banco, timeout=30)
    except Exception as e:
        return {**base, "success": False, "message": f"Falha de conexão: {e}", "davs": []}
    operacional = bool(f.get("resultado_operacional"))
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(sql, tuple(params))
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {**base, "success": False, "message": f"Erro na consulta: {e}", "davs": []}

    dav_list, emp_venda, emp_custo, emp_desconto = _agregar(rows, operacional)
    # Limita o volume de detalhe enviado ao app (os totais permanecem completos).
    # Mantém os DAVs mais recentes primeiro.
    dav_list.sort(key=lambda d: d.get("data") or "", reverse=True)
    qtd_total = len(dav_list)
    truncated = qtd_total > MAX_DAVS_DETALHE
    if truncated:
        dav_list = dav_list[:MAX_DAVS_DETALHE]
    return {
        **base, "success": True, "davs": dav_list,
        "total_venda": emp_venda, "total_custo": emp_custo, "total_desconto": emp_desconto,
        "lucro": round(emp_venda - emp_custo, 2),
        "margem_pct": _margem_pct(emp_venda, emp_custo, operacional),
        "qtd_davs": qtd_total,
        "truncated": truncated,
        "davs_exibidos": len(dav_list),
    }


# --------------------------------------------------------------------------- #
# API pública (async, consolida multiempresa em paralelo)
# --------------------------------------------------------------------------- #
async def margem_lucro(conexoes: list[dict], f: dict) -> dict:
    """Executa a consulta em paralelo para cada conexão e consolida o resultado."""
    if not conexoes:
        return {"success": False, "message": "Nenhuma conexão informada.",
                "empresas": [], "consolidado": {}}

    resultados = await asyncio.gather(*[
        asyncio.to_thread(_consultar_empresa_sync,
                          c.get("empresa") or c.get("banco") or "",
                          c.get("servidor") or "", c.get("banco") or "", f)
        for c in conexoes
    ])

    operacional = bool(f.get("resultado_operacional"))
    tot_venda = tot_custo = tot_desconto = 0.0
    qtd_davs = 0
    for emp in resultados:
        if emp.get("success"):
            tot_venda += emp.get("total_venda", 0.0)
            tot_custo += emp.get("total_custo", 0.0)
            tot_desconto += emp.get("total_desconto", 0.0)
            qtd_davs += emp.get("qtd_davs", 0)

    tot_venda = round(tot_venda, 2)
    tot_custo = round(tot_custo, 2)
    consolidado = {
        "total_venda": tot_venda,
        "total_custo": tot_custo,
        "desconto": round(tot_desconto, 2),
        "lucro": round(tot_venda - tot_custo, 2),
        "margem_pct": _margem_pct(tot_venda, tot_custo, operacional),
        "qtd_davs": qtd_davs,
        "qtd_empresas": sum(1 for e in resultados if e.get("success")),
    }
    return {"success": True, "empresas": list(resultados), "consolidado": consolidado}


# --------------------------------------------------------------------------- #
# Lookup: árvore de níveis (para o seletor hierárquico do frontend)
# --------------------------------------------------------------------------- #
def _niveis_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco, timeout=20)
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT cod_nivel, nivel1, nivel2, nivel3, nivel4, nivel5, descr "
            "FROM niveis ORDER BY nivel1, nivel2, nivel3, nivel4, nivel5"
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "niveis": []}
    niveis = []
    for r in rows:
        partes = [(r.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
        codigo = "".join(p for p in partes if p)
        niveis.append({
            "cod_nivel": r.get("cod_nivel"),
            "codigo": codigo,
            "profundidade": sum(1 for p in partes if p),
            "descricao": (r.get("descr") or "").strip(),
            "niveis": partes,
        })
    return {"success": True, "niveis": niveis}


async def niveis(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_niveis_sync, servidor, banco)
