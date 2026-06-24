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
            "       c.nome AS cliente, pv.vendedor AS vendedor_cod, f.nome AS vendedor_nome "
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
            where.append("c.nome LIKE %s")
            params.append(f"%{cliente_nome.strip()}%")
        cur.execute(
            "SELECT pv.pedido, pv.data, pv.vendedor, pv.situacao, "
            "       f.nome AS vendedor_nome, c.nome AS cliente_nome, "
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
    por tipo (pecas/servicos). Inclui margem média do dia (venda líquida - custo)."""
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
            f"WHERE CAST(pv.data AS DATE) = %s{vfilter}",
            tuple([data_iso] + vparams),
        )
        agg = _ratear_totais_por_pedido(cur.fetchall())
        totais = {
            "pedidos": agg["qtd_pedidos"],
            "produtos": agg["produtos"],
            "servicos": agg["servicos"],
            "descontos": agg["descontos"],
            "margem": agg["margem"],
            "margem_pct": agg["margem_pct"],
        }

        # Lista de pedidos do dia
        cur.execute(
            "SELECT TOP 50 pv.pedido, c.nome AS cliente, ISNULL(pv.total,0) AS valor, "
            "       f.nome AS vendedor_nome "
            "FROM pedido_venda pv "
            "LEFT JOIN cliente c ON c.codigo = pv.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = pv.vendedor "
            f"WHERE CAST(pv.data AS DATE) = %s{vfilter} "
            "ORDER BY pv.pedido DESC",
            tuple([data_iso] + vparams),
        )
        pedidos = []
        for r in cur.fetchall():
            pedidos.append({
                "pedido": int(r.get("pedido") or 0),
                "cliente": (r.get("cliente") or "").strip(),
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "valor": float(r.get("valor") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "totais": totais, "pedidos": pedidos}
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
