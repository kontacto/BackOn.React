"""Venda por Cliente/Produto — Painel de Relatórios > Vendas.

Migração unificada de `Geral\\FrmRelVenCli.frm` (738 linhas, "Vendas por
Cliente") + `Geral\\FrmRelVenPro.frm` (902 linhas, "Itens Vendidos por
Cliente/Comanda") — no legado são duas telas quase idênticas (mesmas
tabelas/filtros), só ordenadas/agrupadas de forma invertida (uma por
cliente com produtos aninhados, outra por produto com clientes
aninhados). Decisão do usuário (2026-08-07, `AskUserQuestion`): unificar
numa tela só, com toggle de agrupamento Cliente↔Produto — mesma query,
o frontend decide a ordenação/quebra visual.

Generalizado (mesma diretriz 2026-08-07 já usada em Apuração de Vendas-
DRE/Resumo de Venda) pra ler `pedido_venda_prod`/`pedido_venda` e
`os_produto`/`os` diretamente, sem passar por `comanda`. Cada linha é um
item vendido (Pedido ou O.S.), com cliente, produto/serviço, documento e
data — nível de detalhe igual ao legado (um registro por combinação
cliente+produto+documento+data), sem agregação adicional; o front agrupa/
subtotaliza pelo eixo escolhido.

Filtro de produto (opcional, código exato — `pecas.codigo_int` ou
`servicos.codigo`, resolvido via busca de produto no frontend, ver regra
`[GLOBAL]` "Campos de identidade precisam de mecanismo de busca") só faz
sentido no legado quando "Procurar Específico" está ativo — aqui fica
disponível em qualquer modo de agrupamento, sem restrição, já que não
muda a query em si.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _venda_cliente_produto_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    cliente: Optional[int], produto: Optional[str],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cli_sql, cli_p = ("AND pv.cliente = %s ", [cliente]) if cliente else ("", [])
        cli_sql_os, cli_p_os = ("AND o.cliente = %s ", [cliente]) if cliente else ("", [])
        prod_sql, prod_p = ("AND i.produto = %s ", [produto]) if produto else ("", [])
        prod_sql_os, prod_p_os = ("AND i.codigo_interno = %s ", [produto]) if produto else ("", [])

        query = (
            "SELECT pv.cliente AS cliente_codigo, cli.nome AS cliente_nome, "
            "  i.produto AS item_codigo, COALESCE(pe.descricao, sv.descricao, i.produto) AS item_descricao, "
            "  'PED' AS doc_tipo, pv.pedido AS doc_numero, pv.data AS data, "
            "  i.qtd_pedida AS qtd, (i.p_venda*i.qtd_pedida) AS valor "
            "FROM pedido_venda_prod i "
            "JOIN pedido_venda pv ON pv.pedido = i.pedido "
            "JOIN cliente cli ON cli.codigo = pv.cliente "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND pv.data BETWEEN %s AND %s " + cli_sql + prod_sql +
            "UNION ALL "
            "SELECT o.cliente, cli.nome, "
            "  i.codigo_interno, COALESCE(pe.descricao, sv.descricao, i.codigo_interno), "
            "  'OS', o.codigo, o.data_entrada, "
            "  i.quant, (i.p_venda*i.quant) "
            "FROM os_produto i "
            "JOIN os o ON o.codigo = i.os "
            "JOIN cliente cli ON cli.codigo = o.cliente "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
            "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
            "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
            "  AND o.data_entrada BETWEEN %s AND %s " + cli_sql_os + prod_sql_os +
            "ORDER BY cliente_nome, data"
        )
        params = [data_ini, data_fim] + cli_p + prod_p + [data_ini, data_fim] + cli_p_os + prod_p_os
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        itens = []
        tot_qtd = tot_valor = 0.0
        for r in rows:
            d = r.get("data")
            qtd = float(r.get("qtd") or 0)
            valor = float(r.get("valor") or 0)
            itens.append({
                "cliente_codigo": r.get("cliente_codigo"),
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "item_codigo": (r.get("item_codigo") or "").strip(),
                "item_descricao": (r.get("item_descricao") or "").strip(),
                "doc_tipo": r.get("doc_tipo"),
                "doc_numero": r.get("doc_numero"),
                "data": d.isoformat() if hasattr(d, "isoformat") else (str(d)[:10] if d else None),
                "qtd": round(qtd, 3),
                "valor": round(valor, 2),
            })
            tot_qtd += qtd
            tot_valor += valor
        return {
            "success": True, "itens": itens,
            "totais": {"qtd": round(tot_qtd, 3), "valor": round(tot_valor, 2)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def venda_cliente_produto(servidor, banco, data_ini, data_fim, cliente, produto):
    return await asyncio.to_thread(
        _venda_cliente_produto_sync, servidor, banco, data_ini, data_fim, cliente, produto
    )
