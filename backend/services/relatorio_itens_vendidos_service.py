"""Itens Vendidos O.S./Balcão — Painel de Relatórios > Pré Venda.

Migração de `FrmRelVenOsB.frm` ("Itens Vendidos OS / Balcão"). Soma
quantidade e valor por produto/serviço INDIVIDUAL (diferente do Resumo de
Venda, que agrupa por nível) — combina venda direta ("Balcão") + consumo
de O.S. no período.

**Generalização** (mesmo princípio já usado em Apuração de Vendas-DRE/
Resumo de Venda/Descontos, 2026-08-07): "Balcão" nesta migração é venda
direta via Pedido (Bar ou Geral) — `pedido_venda_prod`/`pedido_venda` —,
não `comanda`+`movimentacao` como no legado (`comanda` aqui é só o
envelope de fechamento, não o ledger de item — ver
`fechamento_caixa_service.py`). O restante (consumo de O.S. via
`os_produto`/`os`) é a mesma fonte real do legado.
"""
import asyncio

from db.connection import _open_conn


def _itens_vendidos_sync(servidor: str, banco: str, data_ini: str, data_fim: str) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": []}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        query = (
            "SELECT i.produto AS codigo, COALESCE(pe.descricao, sv.descricao, i.produto) AS descricao, "
            "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND CAST(pv.data AS DATE) BETWEEN %s AND %s "
            "GROUP BY i.produto, COALESCE(pe.descricao, sv.descricao, i.produto) "
            "UNION ALL "
            "SELECT i.codigo_interno, COALESCE(pe.descricao, sv.descricao, i.codigo_interno), "
            "  SUM(i.quant), SUM(i.p_venda*i.quant) "
            "FROM os_produto i "
            "JOIN os o ON o.codigo = i.os "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND CAST(o.data_entrada AS DATE) BETWEEN %s AND %s "
            "GROUP BY i.codigo_interno, COALESCE(pe.descricao, sv.descricao, i.codigo_interno)"
        )
        cur.execute(query, (data_ini, data_fim, data_ini, data_fim))
        rows = cur.fetchall()
        cur.close()

        por_produto: dict = {}
        ordem: list = []
        for r in rows:
            cod = (r.get("codigo") or "").strip()
            item = por_produto.get(cod)
            if not item:
                item = {"codigo": cod, "descricao": (r.get("descricao") or cod).strip(), "qtd": 0.0, "valor": 0.0}
                por_produto[cod] = item
                ordem.append(cod)
            item["qtd"] += float(r.get("qtd") or 0)
            item["valor"] += float(r.get("valor") or 0)

        itens = []
        for cod in ordem:
            item = por_produto[cod]
            item["qtd"] = round(item["qtd"], 2)
            item["valor"] = round(item["valor"], 2)
            itens.append(item)
        itens.sort(key=lambda x: x["descricao"])
        total_valor = round(sum(i["valor"] for i in itens), 2)
        return {"success": True, "itens": itens, "total_valor": total_valor}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


async def itens_vendidos(servidor, banco, data_ini, data_fim):
    return await asyncio.to_thread(_itens_vendidos_sync, servidor, banco, data_ini, data_fim)
