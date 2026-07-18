"""Relatórios e Dashboard — rateio de totais, relatório de pedidos,
relatório de descontos & margem e dashboard do dia."""
import asyncio
from datetime import date
from typing import Optional

from db.connection import _open_conn
from services.constants import SIT_LABELS


def _ratear_totais_por_pedido(rows: list) -> dict:
    """Recebe linhas por pedido (total = pedido_venda.total; item_sum/serv_sum/custo_sum/desc_sum
    dos itens). Rateia produtos/serviços pelo pedido.total, garantindo que
    produtos + serviços == Σ pedido.total (bate com a lista de pedidos). A margem usa
    venda = Σ pedido.total (valor real do pedido) − custo de reposição dos itens."""
    produtos = servicos = venda = custo = descontos = 0.0
    qtd = 0
    for r in rows:
        qtd += 1
        total = float(r.get("total") or 0)
        item_sum = float(r.get("item_sum") or 0)
        serv_sum = float(r.get("serv_sum") or 0)
        venda += total
        custo += float(r.get("custo_sum") or 0)
        descontos += float(r.get("desc_sum") or 0)
        if item_sum > 0:
            sv = total * (serv_sum / item_sum)
            servicos += sv
            produtos += total - sv  # produtos + itens não classificados
        else:
            produtos += total
    margem = round(venda - custo, 2)
    return {
        "qtd_pedidos": qtd,
        "produtos": round(produtos, 2),
        "servicos": round(servicos, 2),
        "venda": round(venda, 2),
        "custo": round(custo, 2),
        "descontos": round(descontos, 2),
        "margem": margem,
        "margem_pct": round((margem / venda * 100), 2) if venda > 0 else 0.0,
    }


def _relatorio_pedidos_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str], situacao: Optional[str]) -> dict:
    """Lista de pedidos por período + filtros (vendedor/situação) para o Relatório de Pedidos.
    Campos: pedido, cliente, data, vendedor (nome), situacao. A análise (descontos/margem)
    é carregada sob demanda pelos endpoints já existentes ao expandir cada registro."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "pedidos": []}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(pv.data AS DATE) BETWEEN %s AND %s"]
        params: list = [data_ini, data_fim]
        if vendedor not in (None, "", "all"):
            where.append("pv.vendedor = %s")
            params.append(vendedor)
        if situacao not in (None, "", "all"):
            where.append("pv.situacao = %s")
            params.append(situacao)
        cur.execute(
            "SELECT TOP 300 pv.pedido, pv.data, pv.situacao, ISNULL(pv.total,0) AS total, "
            "       c.nome AS cliente, pv.vendedor AS vendedor_cod, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome "
            "FROM pedido_venda pv "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY pv.data DESC, pv.pedido DESC",
            tuple(params),
        )
        rows = cur.fetchall()
        # Totais por pedido (rateando produtos/serviços pelo pedido.total → bate com a lista)
        cur.execute(
            "SELECT ISNULL(pv.total,0) AS total, "
            "  ISNULL(ag.item_sum,0) AS item_sum, "
            "  ISNULL(ag.serv_sum,0) AS serv_sum, "
            "  ISNULL(ag.custo_sum,0) AS custo_sum, "
            "  ISNULL(ag.desc_sum,0) AS desc_sum "
            "FROM pedido_venda pv "
            "OUTER APPLY (SELECT "
            "    SUM(i.p_venda*i.qtd_pedida) AS item_sum, "
            "    SUM(CASE WHEN sv.codigo IS NOT NULL THEN i.p_venda*i.qtd_pedida ELSE 0 END) AS serv_sum, "
            "    SUM(COALESCE(NULLIF(pe.custo_reposicao,0), NULLIF(sv.custo_hora,0), NULLIF(i.custo_ped,0), 0) * i.qtd_pedida) AS custo_sum, "
            "    SUM(ISNULL(i.desconto,0)*i.qtd_pedida) AS desc_sum "
            "  FROM pedido_venda_prod i "
            "  LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "  LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "  WHERE i.pedido = pv.pedido AND ISNULL(i.item_cancelado,0)=0) ag "
            f"WHERE {' AND '.join(where)}",
            tuple(params),
        )
        agg = _ratear_totais_por_pedido(cur.fetchall())
        cur.close(); conn.close()
        pedidos = []
        for r in rows:
            d = r.get("data")
            pedidos.append({
                "pedido": r.get("pedido"),
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d) if d else None),
                "situacao": (r.get("situacao") or "").strip(),
                "situacao_label": SIT_LABELS.get((r.get("situacao") or "").strip(), r.get("situacao") or "—"),
                "total": float(r.get("total") or 0),
                "cliente": (r.get("cliente") or "").strip() or "—",
                "vendedor_cod": r.get("vendedor_cod"),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip() or "—",
            })
        totais = {
            "qtd_pedidos": agg["qtd_pedidos"],
            "venda": agg["venda"],
            "desconto": agg["descontos"],
            "custo": agg["custo"],
            "margem": agg["margem"],
            "margem_pct": agg["margem_pct"],
            "produtos": agg["produtos"],
            "servicos": agg["servicos"],
        }
        return {"success": True, "pedidos": pedidos, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "pedidos": []}


def _relatorio_desc_margem_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                                vendedor: Optional[str], pedido: Optional[int],
                                cliente_nome: Optional[str] = None) -> dict:
    """Relatório consolidado: por pedido (agrupado por vendedor) com venda, desconto,
    custo e margem. O CUSTO usa o custo de reposição do cadastro (pecas.custo_reposicao /
    servicos.custo_hora), com fallback para pedido_venda_prod.custo_ped. A venda é líquida
    (p_venda já é descontado), então desconto E custo influenciam a margem.
    Filtros: período + vendedor + pedido + nome do cliente (todos opcionais)."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "vendedores": [], "totais": {}}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(pv.data AS DATE) BETWEEN %s AND %s"]
        params: list = [data_ini, data_fim]
        if vendedor:
            where.append("pv.vendedor = %s")
            params.append(vendedor)
        if pedido:
            where.append("pv.pedido = %s")
            params.append(pedido)
        if cliente_nome and cliente_nome.strip():
            # Busca por nome também bate no nome fantasia — [GLOBAL] em toda
            # busca de cliente do sistema, pedido explícito do usuário,
            # 2026-07-18.
            where.append("(c.nome LIKE %s OR c.fantasia LIKE %s)")
            like_cliente = f"%{cliente_nome.strip()}%"
            params.extend([like_cliente, like_cliente])
        cur.execute(
            "SELECT pv.pedido, pv.data, pv.vendedor, pv.situacao, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, c.nome AS cliente_nome, "
            "       ISNULL(ag.venda,0) AS venda, ISNULL(ag.desconto,0) AS desconto, ISNULL(ag.custo,0) AS custo "
            "FROM pedido_venda pv "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "OUTER APPLY (SELECT "
            "    SUM(i.p_venda * i.qtd_pedida) AS venda, "
            "    SUM(ISNULL(i.desconto,0) * i.qtd_pedida) AS desconto, "
            "    SUM(COALESCE(NULLIF(pe.custo_reposicao,0), NULLIF(sv.custo_hora,0), NULLIF(i.custo_ped,0), 0) * i.qtd_pedida) AS custo "
            "  FROM pedido_venda_prod i "
            "  LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "  LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "  WHERE i.pedido = pv.pedido AND ISNULL(i.item_cancelado,0)=0) ag "
            f"WHERE {' AND '.join(where)} "
            "ORDER BY pv.vendedor, pv.pedido",
            tuple(params),
        )
        grupos: dict = {}
        tot_venda = tot_desc = tot_custo = 0.0
        for r in cur.fetchall():
            vcod = str(r.get("vendedor") or "").strip()
            vnome = (r.get("vendedor_nome") or "").strip() or (f"Vendedor {vcod}" if vcod else "Sem vendedor")
            venda = float(r.get("venda") or 0)
            desc = float(r.get("desconto") or 0)
            custo = float(r.get("custo") or 0)
            margem = round(venda - custo, 2)
            margem_pct = round((margem / venda * 100), 2) if venda > 0 else 0.0
            data_val = r.get("data")
            data_str = data_val.strftime("%Y-%m-%d") if hasattr(data_val, "strftime") else (str(data_val)[:10] if data_val else "")
            ped_obj = {
                "pedido": int(r["pedido"]),
                "data": data_str,
                "situacao": (r.get("situacao") or "").strip(),
                "cliente": (r.get("cliente_nome") or "").strip(),
                "venda": round(venda, 2),
                "desconto": round(desc, 2),
                "custo": round(custo, 2),
                "margem": margem,
                "margem_pct": margem_pct,
            }
            g = grupos.setdefault(vcod, {
                "vendedor": vcod, "vendedor_nome": vnome, "pedidos": [],
                "sub_venda": 0.0, "sub_desconto": 0.0, "sub_custo": 0.0, "sub_margem": 0.0,
            })
            g["pedidos"].append(ped_obj)
            g["sub_venda"] += venda
            g["sub_desconto"] += desc
            g["sub_custo"] += custo
            g["sub_margem"] += margem
            tot_venda += venda; tot_desc += desc; tot_custo += custo
        cur.close(); conn.close()
        vendedores = []
        for g in grupos.values():
            g["sub_venda"] = round(g["sub_venda"], 2)
            g["sub_desconto"] = round(g["sub_desconto"], 2)
            g["sub_custo"] = round(g["sub_custo"], 2)
            g["sub_margem"] = round(g["sub_margem"], 2)
            g["sub_margem_pct"] = round((g["sub_margem"] / g["sub_venda"] * 100), 2) if g["sub_venda"] > 0 else 0.0
            vendedores.append(g)
        margem_geral = round(tot_venda - tot_custo, 2)
        totais = {
            "venda": round(tot_venda, 2),
            "desconto": round(tot_desc, 2),
            "custo": round(tot_custo, 2),
            "margem": margem_geral,
            "margem_pct": round((margem_geral / tot_venda * 100), 2) if tot_venda > 0 else 0.0,
            "qtd_pedidos": sum(len(g["pedidos"]) for g in vendedores),
        }
        return {"success": True, "vendedores": vendedores, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "vendedores": [], "totais": {}}


def _dashboard_sync(servidor: str, banco: str, vendedor: Optional[str], data_iso: str,
                    situacao: Optional[str] = None) -> dict:
    """Totais e pedidos do dia (pedido_venda/pedido_venda_prod).
    vendedor None/'' = todos; situacao None/'' = todas; produtos/servicos = soma p_venda*qtd
    por tipo (pecas/servicos). Inclui margem média do dia (venda líquida - custo).

    Data de referência do filtro "hoje": normalmente `pedido_venda.data`
    (dia em que o pedido foi criado). **Exceção, 2026-07-16, user-directed**
    ("pedidos faturados (somente) hoje entra na tela principal como hoje"):
    quando `situacao='PG'` (Faturado), usa `comanda.data` (dia em que o
    Faturar foi clicado — mesma coluna já usada pelo Fechamento de Caixa,
    ver `fechamento_caixa_service.py`), não a data de criação do pedido —
    senão um pedido criado ontem e faturado hoje nunca aparecia no "hoje"
    com o filtro Faturado, mesmo o dinheiro tendo entrado hoje.

    **"Todos" (sem filtro de situação) — corrigido no mesmo dia**: usa uma
    condição de UNIÃO (Faturado pela data do Faturar, os demais pela data
    de criação), não mais só `pedido_venda.data` sozinho — senão "Todos"
    podia ficar MENOR que "Faturado" isolado (reportado pelo usuário com
    print comparando os dois: Faturado R$886,70 vs. Todos R$371,70,
    "não faz sentido"). Confirmado que Aberto/Fechado/Cancelado
    continuam só por `pedido_venda.data`, sem união — o usuário confirmou
    explicitamente que esses três não devem mudar."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}",
                "totais": {"pedidos": 0, "produtos": 0, "servicos": 0, "margem": 0, "margem_pct": 0}, "pedidos": []}
    try:
        cur = conn.cursor(as_dict=True)
        vfilter = ""
        vparams: list = []
        if vendedor not in (None, "", "all"):
            vfilter += " AND pv.vendedor = %s"
            vparams.append(vendedor)
        if situacao not in (None, "", "all"):
            vfilter += " AND pv.situacao = %s"
            vparams.append(situacao)

        if situacao == "PG":
            date_join = "JOIN COMANDA_PED cp ON cp.ped = pv.pedido JOIN comanda cm ON cm.comanda = cp.comanda "
            date_where = "CAST(cm.data AS DATE) = %s"
            date_params = [data_iso]
        elif situacao in (None, "", "all"):
            date_join = "LEFT JOIN COMANDA_PED cp ON cp.ped = pv.pedido LEFT JOIN comanda cm ON cm.comanda = cp.comanda "
            date_where = (
                "((pv.situacao = 'PG' AND CAST(cm.data AS DATE) = %s) "
                "OR (pv.situacao <> 'PG' AND CAST(pv.data AS DATE) = %s))"
            )
            date_params = [data_iso, data_iso]
        else:
            date_join = ""
            date_where = "CAST(pv.data AS DATE) = %s"
            date_params = [data_iso]

        # Totais por pedido (rateando produtos/serviços pelo pedido.total → bate com a lista)
        cur.execute(
            "SELECT ISNULL(pv.total,0) AS total, "
            "  ISNULL(ag.item_sum,0) AS item_sum, "
            "  ISNULL(ag.serv_sum,0) AS serv_sum, "
            "  ISNULL(ag.custo_sum,0) AS custo_sum, "
            "  ISNULL(ag.desc_sum,0) AS desc_sum "
            "FROM pedido_venda pv "
            f"{date_join}"
            "OUTER APPLY (SELECT "
            "    SUM(i.p_venda*i.qtd_pedida) AS item_sum, "
            "    SUM(CASE WHEN sv.codigo IS NOT NULL THEN i.p_venda*i.qtd_pedida ELSE 0 END) AS serv_sum, "
            "    SUM(COALESCE(NULLIF(pe.custo_reposicao,0), NULLIF(sv.custo_hora,0), NULLIF(i.custo_ped,0), 0) * i.qtd_pedida) AS custo_sum, "
            "    SUM(ISNULL(i.desconto,0)*i.qtd_pedida) AS desc_sum "
            "  FROM pedido_venda_prod i "
            "  LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "  LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "  WHERE i.pedido = pv.pedido AND ISNULL(i.item_cancelado,0)=0) ag "
            f"WHERE {date_where}{vfilter}",
            tuple(date_params + vparams),
        )
        agg = _ratear_totais_por_pedido(cur.fetchall())

        # --- Agregados das OS do dia (vendedor é POR ITEM em os_produto) ---
        osfilter = ""
        osparams: list = []
        if vendedor not in (None, "", "all"):
            osfilter += " AND i.vendedor = %s"
            osparams.append(vendedor)
        if situacao not in (None, "", "all"):
            osfilter += " AND o.situacao = %s"
            osparams.append(situacao)
        cur.execute(
            "SELECT ISNULL(SUM(i.p_venda*i.quant),0) AS venda, "
            "  ISNULL(SUM(CASE WHEN sv.codigo IS NOT NULL THEN i.p_venda*i.quant ELSE 0 END),0) AS serv_sum, "
            "  ISNULL(SUM(i.custo_os*i.quant),0) AS custo_sum, "
            "  ISNULL(SUM(ISNULL(i.desconto,0)*i.quant),0) AS desc_sum, "
            "  COUNT(DISTINCT i.os) AS qtd_os "
            "FROM os_produto i "
            "JOIN os o ON o.codigo = i.os "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE CAST(o.data_entrada AS DATE) = %s AND ISNULL(i.item_cancelado,0)=0" + osfilter,
            tuple([data_iso] + osparams),
        )
        osr = cur.fetchone() or {}
        os_venda = float(osr.get("venda") or 0)
        os_serv = float(osr.get("serv_sum") or 0)
        os_custo = float(osr.get("custo_sum") or 0)
        os_desc = float(osr.get("desc_sum") or 0)
        os_prod = os_venda - os_serv
        qtd_os = int(osr.get("qtd_os") or 0)

        # Totais combinados (Pedido + OS)
        venda_total = agg["venda"] + os_venda
        custo_total = agg["custo"] + os_custo
        margem_total = round(venda_total - custo_total, 2)
        totais = {
            "pedidos": agg["qtd_pedidos"],
            "os": qtd_os,
            "produtos": round(agg["produtos"] + os_prod, 2),
            "servicos": round(agg["servicos"] + os_serv, 2),
            "descontos": round(agg["descontos"] + os_desc, 2),
            "margem": margem_total,
            "margem_pct": round((margem_total / venda_total * 100), 2) if venda_total > 0 else 0.0,
        }

        # Lista de movimento do dia (Pedidos + OS) com etiqueta de tipo.
        # `situacao`/`situacao_label` sempre incluídos — [user-directed
        # 2026-07-16] "na tela principal quando for selecionado 'Todos'
        # cada registro de Pré venda tem que mostrar a sua situação", já
        # que "Todos" mistura Aberto/Fechado/Faturado/Cancelado na mesma
        # lista (a tela decide se mostra o rótulo ou não conforme o filtro
        # ativo, mas o dado já vem sempre pronto).
        movimento = []
        cur.execute(
            "SELECT TOP 50 pv.pedido, pv.situacao, c.nome AS cliente, ISNULL(pv.total,0) AS valor, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome "
            "FROM pedido_venda pv "
            f"{date_join}"
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            f"WHERE {date_where}{vfilter} "
            "ORDER BY pv.pedido DESC",
            tuple(date_params + vparams),
        )
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip().upper()
            movimento.append({
                "tipo": "PED",
                "doc": int(r.get("pedido") or 0),
                "cliente": (r.get("cliente") or "").strip(),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "valor": float(r.get("valor") or 0),
                "situacao": sit,
                "situacao_label": SIT_LABELS.get(sit, sit),
            })
        cur.execute(
            "SELECT TOP 50 i.os AS doc, MAX(o.situacao) AS situacao, MAX(c.nome) AS cliente, SUM(i.p_venda*i.quant) AS valor "
            "FROM os_produto i "
            "JOIN os o ON o.codigo = i.os "
            "LEFT JOIN cliente c ON c.codigo = o.cliente "
            "WHERE CAST(o.data_entrada AS DATE) = %s AND ISNULL(i.item_cancelado,0)=0" + osfilter + " "
            "GROUP BY i.os ORDER BY i.os DESC",
            tuple([data_iso] + osparams),
        )
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip().upper()
            movimento.append({
                "tipo": "OS",
                "doc": int(r.get("doc") or 0),
                "cliente": (r.get("cliente") or "").strip(),
                "vendedor_nome": "",
                "valor": float(r.get("valor") or 0),
                "situacao": sit,
                "situacao_label": SIT_LABELS.get(sit, sit),
            })
        cur.close()
        conn.close()
        return {"success": True, "totais": totais, "movimento": movimento, "pedidos": movimento}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro consulta dashboard: {e}",
                "totais": {"pedidos": 0, "produtos": 0, "servicos": 0}, "pedidos": []}


async def relatorio_pedidos(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str], situacao: Optional[str]) -> dict:
    return await asyncio.to_thread(_relatorio_pedidos_sync, servidor, banco, data_ini, data_fim, vendedor, situacao)

async def relatorio_desc_margem(servidor: str, banco: str, data_ini: str, data_fim: str,
                                vendedor: Optional[str], pedido: Optional[int],
                                cliente_nome: Optional[str]) -> dict:
    return await asyncio.to_thread(
        _relatorio_desc_margem_sync, servidor, banco, data_ini, data_fim, vendedor, pedido, cliente_nome
    )


async def dashboard_me(servidor: str, banco: str, vendedor: Optional[str],
                       data: Optional[str], situacao: Optional[str]) -> dict:
    # data padrão = hoje (YYYY-MM-DD); vendedor/situacao vazio/None/all = todos
    data_iso = data or date.today().isoformat()
    return await asyncio.to_thread(_dashboard_sync, servidor, banco, vendedor, data_iso, situacao)



# ===================== RELATÓRIOS DE ORDEM DE SERVIÇO =====================
def _relatorio_os_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                       vendedor: Optional[str], situacao: Optional[str]) -> dict:
    """Lista de OS por período + filtros (vendedor por item / situação) e totais.
    Quando um vendedor é informado, o total de cada OS e os totais consolidados
    consideram apenas os itens daquele vendedor."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "os": []}
    try:
        cur = conn.cursor(as_dict=True)
        vfilter = ""
        vparams: list = []
        if vendedor not in (None, "", "all"):
            vfilter = " AND i.vendedor = %s"
            vparams = [vendedor]
        sit_clause = ""
        sit_params: list = []
        if situacao not in (None, "", "all"):
            sit_clause = " AND o.situacao = %s"
            sit_params = [situacao]
        # Lista de OS (total = soma dos itens que casam o filtro de vendedor)
        only_match = " AND ag.venda IS NOT NULL" if vparams else ""
        cur.execute(
            "SELECT TOP 300 o.codigo, o.data_entrada AS data, o.situacao, "
            "       c.nome AS cliente, ISNULL(ag.venda,0) AS total "
            "FROM os o LEFT JOIN cliente c ON c.codigo = o.cliente "
            "OUTER APPLY (SELECT SUM(i.p_venda*i.quant) AS venda FROM os_produto i "
            "   WHERE i.os = o.codigo AND ISNULL(i.item_cancelado,0)=0" + vfilter + ") ag "
            "WHERE CAST(o.data_entrada AS DATE) BETWEEN %s AND %s" + sit_clause + only_match +
            " ORDER BY o.data_entrada DESC, o.codigo DESC",
            tuple(vparams + [data_ini, data_fim] + sit_params),
        )
        rows = cur.fetchall()
        # Totais consolidados (itens filtrados por vendedor/situação)
        cur.execute(
            "SELECT ISNULL(SUM(i.p_venda*i.quant),0) AS venda, "
            "  ISNULL(SUM(i.custo_os*i.quant),0) AS custo, "
            "  ISNULL(SUM(ISNULL(i.desconto,0)*i.quant),0) AS desconto, "
            "  COUNT(DISTINCT i.os) AS qtd_os "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "WHERE CAST(o.data_entrada AS DATE) BETWEEN %s AND %s AND ISNULL(i.item_cancelado,0)=0"
            + vfilter + sit_clause,
            tuple([data_ini, data_fim] + vparams + sit_params),
        )
        t = cur.fetchone() or {}
        cur.close(); conn.close()
        os_list = []
        for r in rows:
            d = r.get("data")
            os_list.append({
                "os": int(r.get("codigo") or 0),
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d) if d else None),
                "situacao": (r.get("situacao") or "").strip(),
                "situacao_label": SIT_LABELS.get((r.get("situacao") or "").strip(), r.get("situacao") or "—"),
                "total": float(r.get("total") or 0),
                "cliente": (r.get("cliente") or "").strip() or "—",
            })
        venda = float(t.get("venda") or 0)
        custo = float(t.get("custo") or 0)
        margem = round(venda - custo, 2)
        totais = {
            "qtd_pedidos": int(t.get("qtd_os") or 0),
            "venda": round(venda, 2),
            "desconto": round(float(t.get("desconto") or 0), 2),
            "custo": round(custo, 2),
            "margem": margem,
            "margem_pct": round((margem / venda * 100), 2) if venda > 0 else 0.0,
        }
        return {"success": True, "os": os_list, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "os": []}


def _relatorio_os_desc_margem_sync(servidor: str, banco: str, data_ini: str, data_fim: str,
                                   vendedor: Optional[str], os_cod: Optional[int],
                                   cliente_nome: Optional[str] = None) -> dict:
    """Consolidado de OS agrupado por vendedor (vendedor é por item em os_produto).
    Cada linha = (vendedor, OS) com venda/desconto/custo/margem dos itens daquele
    vendedor naquela OS. O campo 'pedido' carrega o código da OS p/ reuso de UI."""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "vendedores": [], "totais": {}}
    try:
        cur = conn.cursor(as_dict=True)
        where = ["CAST(o.data_entrada AS DATE) BETWEEN %s AND %s", "ISNULL(i.item_cancelado,0)=0"]
        params: list = [data_ini, data_fim]
        if vendedor:
            where.append("i.vendedor = %s")
            params.append(vendedor)
        if os_cod:
            where.append("o.codigo = %s")
            params.append(os_cod)
        if cliente_nome and cliente_nome.strip():
            # Busca por nome também bate no nome fantasia — [GLOBAL] em toda
            # busca de cliente do sistema, pedido explícito do usuário,
            # 2026-07-18.
            where.append("(c.nome LIKE %s OR c.fantasia LIKE %s)")
            like_cliente = f"%{cliente_nome.strip()}%"
            params.extend([like_cliente, like_cliente])
        cur.execute(
            "SELECT i.vendedor, o.codigo AS pedido, o.data_entrada AS data, o.situacao, "
            "       COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS vendedor_nome, c.nome AS cliente_nome, "
            "       SUM(i.p_venda*i.quant) AS venda, "
            "       SUM(ISNULL(i.desconto,0)*i.quant) AS desconto, "
            "       SUM(i.custo_os*i.quant) AS custo "
            "FROM os_produto i JOIN os o ON o.codigo = i.os "
            "LEFT JOIN funcionarios f ON f.codigo_int = i.vendedor "
            "LEFT JOIN cliente c ON c.codigo = o.cliente "
            f"WHERE {' AND '.join(where)} "
            "GROUP BY i.vendedor, o.codigo, o.data_entrada, o.situacao, f.nome_guerra, f.nome, c.nome "
            "ORDER BY i.vendedor, o.codigo",
            tuple(params),
        )
        grupos: dict = {}
        tot_venda = tot_desc = tot_custo = 0.0
        for r in cur.fetchall():
            vcod = str(r.get("vendedor") or "").strip()
            vnome = (r.get("vendedor_nome") or "").strip() or (f"Vendedor {vcod}" if vcod else "Sem vendedor")
            venda = float(r.get("venda") or 0)
            desc = float(r.get("desconto") or 0)
            custo = float(r.get("custo") or 0)
            margem = round(venda - custo, 2)
            margem_pct = round((margem / venda * 100), 2) if venda > 0 else 0.0
            data_val = r.get("data")
            data_str = data_val.strftime("%Y-%m-%d") if hasattr(data_val, "strftime") else (str(data_val)[:10] if data_val else "")
            ped_obj = {
                "pedido": int(r["pedido"]),
                "data": data_str,
                "situacao": (r.get("situacao") or "").strip(),
                "cliente": (r.get("cliente_nome") or "").strip(),
                "venda": round(venda, 2),
                "desconto": round(desc, 2),
                "custo": round(custo, 2),
                "margem": margem,
                "margem_pct": margem_pct,
            }
            g = grupos.setdefault(vcod, {
                "vendedor": vcod, "vendedor_nome": vnome, "pedidos": [],
                "sub_venda": 0.0, "sub_desconto": 0.0, "sub_custo": 0.0, "sub_margem": 0.0,
            })
            g["pedidos"].append(ped_obj)
            g["sub_venda"] += venda
            g["sub_desconto"] += desc
            g["sub_custo"] += custo
            g["sub_margem"] += margem
            tot_venda += venda; tot_desc += desc; tot_custo += custo
        cur.close(); conn.close()
        vendedores = []
        for g in grupos.values():
            g["sub_venda"] = round(g["sub_venda"], 2)
            g["sub_desconto"] = round(g["sub_desconto"], 2)
            g["sub_custo"] = round(g["sub_custo"], 2)
            g["sub_margem"] = round(g["sub_margem"], 2)
            g["sub_margem_pct"] = round((g["sub_margem"] / g["sub_venda"] * 100), 2) if g["sub_venda"] > 0 else 0.0
            vendedores.append(g)
        margem_geral = round(tot_venda - tot_custo, 2)
        totais = {
            "venda": round(tot_venda, 2),
            "desconto": round(tot_desc, 2),
            "custo": round(tot_custo, 2),
            "margem": margem_geral,
            "margem_pct": round((margem_geral / tot_venda * 100), 2) if tot_venda > 0 else 0.0,
            "qtd_pedidos": sum(len(g["pedidos"]) for g in vendedores),
        }
        return {"success": True, "vendedores": vendedores, "totais": totais}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "vendedores": [], "totais": {}}


async def relatorio_os(servidor: str, banco: str, data_ini: str, data_fim: str,
                       vendedor: Optional[str], situacao: Optional[str]) -> dict:
    return await asyncio.to_thread(_relatorio_os_sync, servidor, banco, data_ini, data_fim, vendedor, situacao)


async def relatorio_os_desc_margem(servidor: str, banco: str, data_ini: str, data_fim: str,
                                   vendedor: Optional[str], os_cod: Optional[int],
                                   cliente_nome: Optional[str]) -> dict:
    return await asyncio.to_thread(
        _relatorio_os_desc_margem_sync, servidor, banco, data_ini, data_fim, vendedor, os_cod, cliente_nome
    )
