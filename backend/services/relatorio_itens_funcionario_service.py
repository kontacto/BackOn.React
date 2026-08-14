"""Itens por Funcionário — Painel de Relatórios > Vendas.

Migração de `Geral\\FrmRelVenFun.frm` (866 linhas). Toggle Vendedores/
Executores no legado lia `movimentacao`/`comanda` (`Vendedor`) e `os`/
`os_produto` (`executor`) respectivamente — generalizado nesta migração
(mesma diretriz 2026-08-07 já usada em Apuração de Vendas-DRE/Resumo de
Venda) pra ler `pedido_venda_prod`/`pedido_venda` e `os_produto`/`os`
diretamente, sem passar por `comanda`.

- **Vendedores**: agrupa por `pedido_venda.vendedor` (campo do CABEÇALHO
  do Pedido, não do item — mesma assimetria já documentada em Apuração de
  Vendas-DRE/Resumo de Venda, `pedido_venda_prod` não tem vendedor
  próprio por item).
- **Executores**: agrupa por `os_produto.executor` (campo do ITEM da O.S.
  — confirmado real em `os_itens_service.py`, "executor fica por item").
- **"Considerar serviços"**: opcional, liga/desliga a inclusão de itens
  tipo serviço (resolvidos via `LEFT JOIN servicos`, sem depender de
  prefixo de código — mesmo padrão de resolução de `pedido_common.
  _resolve_produto`/`os_itens_service.py`).
- Filtro de código de fabricante do legado não portado (marginal, já
  coberto indiretamente pela busca de produto de outros relatórios).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _itens_funcionario_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    modo: str, funcionario: Optional[int], considerar_servicos: bool,
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "funcionarios": [], "totais": {}}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)

        serv_sql = "" if considerar_servicos else "AND sv.codigo IS NULL "

        if modo == "executor":
            func_sql, func_p = ("AND i.executor = %s ", [funcionario]) if funcionario else ("", [])
            query = (
                "SELECT i.executor AS func_codigo, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS func_nome, "
                "  SUM(i.quant) AS qtd, SUM(i.p_venda*i.quant) AS valor "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "JOIN funcionarios f ON f.codigo_int = i.executor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND o.data_entrada BETWEEN %s AND %s " + func_sql + serv_sql +
                "GROUP BY i.executor, COALESCE(NULLIF(f.nome_guerra,''), f.nome) "
                "ORDER BY valor DESC"
            )
            params = [data_ini, data_fim] + func_p
        else:
            func_sql, func_p = ("AND pv.vendedor = %s ", [funcionario]) if funcionario else ("", [])
            query = (
                "SELECT pv.vendedor AS func_codigo, COALESCE(NULLIF(f.nome_guerra,''), f.nome) AS func_nome, "
                "  SUM(i.qtd_pedida) AS qtd, SUM(i.p_venda*i.qtd_pedida) AS valor "
                "FROM pedido_venda_prod i "
                "JOIN pedido_venda pv ON pv.pedido = i.pedido "
                "JOIN funcionarios f ON f.codigo_int = pv.vendedor "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
                "LEFT JOIN servicos sv ON sv.codigo = i.produto "
                "WHERE pv.situacao = 'PG' AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND pv.data BETWEEN %s AND %s " + func_sql + serv_sql +
                "GROUP BY pv.vendedor, COALESCE(NULLIF(f.nome_guerra,''), f.nome) "
                "ORDER BY valor DESC"
            )
            params = [data_ini, data_fim] + func_p

        cur.execute(query, tuple(params))
        rows = cur.fetchall()
        cur.close()

        funcionarios = []
        tot_qtd = tot_valor = 0.0
        for r in rows:
            qtd = float(r.get("qtd") or 0)
            valor = float(r.get("valor") or 0)
            funcionarios.append({
                "codigo": r.get("func_codigo"),
                "nome": (r.get("func_nome") or "").strip(),
                "qtd": round(qtd, 3),
                "valor": round(valor, 2),
            })
            tot_qtd += qtd
            tot_valor += valor
        return {
            "success": True, "funcionarios": funcionarios,
            "totais": {"qtd": round(tot_qtd, 3), "valor": round(tot_valor, 2)},
        }
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "funcionarios": [], "totais": {}}
    finally:
        conn.close()


async def itens_funcionario(servidor, banco, data_ini, data_fim, modo, funcionario, considerar_servicos):
    return await asyncio.to_thread(
        _itens_funcionario_sync, servidor, banco, data_ini, data_fim, modo, funcionario, considerar_servicos
    )
