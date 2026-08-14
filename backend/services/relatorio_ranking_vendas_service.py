"""Ranking de Vendas — Painel de Relatórios > Vendas.

Migração de `Geral\\FrmRkgCliPro.frm` (1787 linhas, "Ranking de Vendas por
Cliente e Produto"). Top-N por Cliente, Produto ou Vendedor, ordenável por
Quantidade ou Valor — generalizado (mesma diretriz 2026-08-07 já usada em
Apuração de Vendas-DRE/Resumo de Venda) pra ler `pedido_venda_prod`/
`pedido_venda` e `os_produto`/`os` diretamente, sem passar por `comanda`.

- **Produto/Cliente**: soma Pedido + O.S., filtro opcional por vendedor
  (`pedido_venda.vendedor` no Pedido — campo de cabeçalho — e
  `os_produto.vendedor` na O.S. — campo de item, distinto de `executor`;
  mesma assimetria já documentada em Apuração de Vendas-DRE).
- **Vendedor**: soma Pedido (agrupado por `pedido_venda.vendedor`) + O.S.
  (agrupado por `os_produto.vendedor`) — o legado somava os dois juntos
  via `movimentacao.vendedor` na mesma comanda-envelope; aqui a mesma
  ideia é replicada somando as duas fontes reais.
- **Fabricante** (`pecas.fornecedor`): filtro opcional, só afeta linhas de
  produto (itens tipo serviço não têm fabricante).
- **Considerar serviços**: opcional, liga/desliga itens tipo serviço.

**Não portado**: a sub-feature "Compras" do legado (cruzamento com
`n_fiscal_itens` de entrada, mostrando histórico de compra ao lado de
cada produto do ranking) — decisão do usuário (2026-08-07): é uma feature
de compras enxertada numa tela de vendas, sem pedido explícito pra
portar; Gestão de Compras já cobre essa necessidade por outro ângulo
(Curva ABC/Ressuprimento).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _ranking_vendas_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    ranking_por: str, ordenar_por: str, top_n: int,
    vendedor: Optional[int], fabricante: Optional[int], considerar_servicos: bool,
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        serv_sql = "" if considerar_servicos else "AND sv.codigo IS NULL "
        fab_sql = "AND pe.fornecedor = %s " if fabricante else ""

        if ranking_por == "cliente":
            vend_ped_sql, vend_ped_p = ("AND pv.vendedor = %s ", [vendedor]) if vendedor else ("", [])
            vend_os_sql, vend_os_p = ("AND i.vendedor = %s ", [vendedor]) if vendedor else ("", [])
            query = (
                "SELECT pv.cliente AS codigo, cli.nome AS nome, "
                "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "JOIN cliente cli ON cli.codigo = pv.cliente "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + vend_ped_sql + fab_sql + serv_sql +
                "GROUP BY pv.cliente, cli.nome "
                "UNION ALL "
                "SELECT o.cliente, cli.nome, "
                "  SUM(i.quant), SUM(i.p_venda*i.quant) "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "JOIN cliente cli ON cli.codigo = o.cliente "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND o.data_entrada BETWEEN %s AND %s " + vend_os_sql + fab_sql + serv_sql +
                "GROUP BY o.cliente, cli.nome"
            )
            params = (
                [data_ini, data_fim] + vend_ped_p + ([fabricante] if fabricante else [])
                + [data_ini, data_fim] + vend_os_p + ([fabricante] if fabricante else [])
            )
        elif ranking_por == "vendedor":
            query = (
                "SELECT pv.vendedor AS codigo, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS nome, "
                "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "JOIN funcionarios f ON f.codigo_int = pv.vendedor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + fab_sql + serv_sql +
                "GROUP BY pv.vendedor, COALESCE(NULLIF(f.nome_guerra,''), f.nome) "
                "UNION ALL "
                "SELECT i.vendedor, COALESCE(NULLIF(f.nome_guerra,''), f.nome), "
                "  SUM(i.quant), SUM(i.p_venda*i.quant) "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "JOIN funcionarios f ON f.codigo_int = i.vendedor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND o.data_entrada BETWEEN %s AND %s " + fab_sql + serv_sql +
                "GROUP BY i.vendedor, COALESCE(NULLIF(f.nome_guerra,''), f.nome)"
            )
            params = (
                [data_ini, data_fim] + ([fabricante] if fabricante else [])
                + [data_ini, data_fim] + ([fabricante] if fabricante else [])
            )
        else:  # produto
            vend_ped_sql, vend_ped_p = ("AND pv.vendedor = %s ", [vendedor]) if vendedor else ("", [])
            vend_os_sql, vend_os_p = ("AND i.vendedor = %s ", [vendedor]) if vendedor else ("", [])
            query = (
                "SELECT i.produto AS codigo, COALESCE(pe.descricao, sv.descricao, i.produto) AS nome, "
                "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + vend_ped_sql + fab_sql + serv_sql +
                "GROUP BY i.produto, COALESCE(pe.descricao, sv.descricao, i.produto) "
                "UNION ALL "
                "SELECT i.codigo_interno, COALESCE(pe.descricao, sv.descricao, i.codigo_interno), "
                "  SUM(i.quant), SUM(i.p_venda*i.quant) "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND o.data_entrada BETWEEN %s AND %s " + vend_os_sql + fab_sql + serv_sql +
                "GROUP BY i.codigo_interno, COALESCE(pe.descricao, sv.descricao, i.codigo_interno)"
            )
            params = (
                [data_ini, data_fim] + vend_ped_p + ([fabricante] if fabricante else [])
                + [data_ini, data_fim] + vend_os_p + ([fabricante] if fabricante else [])
            )

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        por_chave: dict = {}
        for r in rows:
            chave = r.get("codigo")
            item = por_chave.setdefault(chave, {"codigo": chave, "nome": (r.get("nome") or "").strip(), "qtd": 0.0, "valor": 0.0})
            item["qtd"] += float(r.get("qtd") or 0)
            item["valor"] += float(r.get("valor") or 0)

        campo_ordem = "qtd" if ordenar_por == "qtd" else "valor"
        ranking = sorted(por_chave.values(), key=lambda x: x[campo_ordem], reverse=True)

        tot_qtd = sum(i["qtd"] for i in ranking)
        tot_valor = sum(i["valor"] for i in ranking)

        n = top_n if top_n and top_n > 0 else 10
        top = ranking[:n]
        for i, item in enumerate(top, start=1):
            item["posicao"] = i
            item["qtd"] = round(item["qtd"], 3)
            item["valor"] = round(item["valor"], 2)

        return {
            "success": True, "itens": top,
            "totais": {"qtd": round(tot_qtd, 3), "valor": round(tot_valor, 2), "registros": len(ranking)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def ranking_vendas(servidor, banco, data_ini, data_fim, ranking_por, ordenar_por, top_n, vendedor, fabricante, considerar_servicos):
    return await asyncio.to_thread(
        _ranking_vendas_sync, servidor, banco, data_ini, data_fim, ranking_por, ordenar_por, top_n, vendedor, fabricante, considerar_servicos
    )
