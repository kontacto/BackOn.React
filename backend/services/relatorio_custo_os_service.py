"""Custo de O.S — Painel de Relatórios > Pré Venda.

Migração de `FrmCustoOS.frm`. Soma `custo_os*quant` de `os_produto` no
período (`o.data_entrada`), agrupável por **Cliente** ou por **Produto/
Serviço** (radio no legado — vira parâmetro `agrupar_por` aqui). Filtro
opcional por tipo de item (destino do item: Cliente/Garantia/Interno/
Revisão de Fábrica — `os_produto.situacao`, um FK pra `tipo_os_prod`,
**não** a situação da O.S. em si; nome de coluna enganoso já documentado
em `tabelas_aux_service.py`).

`o.situacao IN ('A','F','PG')` replica exatamente o legado
(`(situacao='A') OR (situacao='F') OR (situacao='PG')` — ou seja, tudo
que não foi cancelado). `origem<>'R'` do legado (exclui item de devolução)
não foi portado — não há evidência de uma coluna `origem`/conceito de
devolução em `os_produto` nesta migração (grep não encontrou nenhum uso);
`ISNULL(i.item_cancelado,0)=0` (coluna real, usada em toda outra query
desta migração) cobre o mesmo objetivo prático de excluir item que não
deve contar no custo.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn


def _custo_os_sync(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    agrupar_por: str, tipo: Optional[int],
) -> dict:
    if not data_ini or not data_fim:
        return {"success": False, "message": "Informe o período.", "itens": [], "total": 0.0}
    agrupar = "produto" if agrupar_por == "produto" else "cliente"
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        tipo_sql, tipo_p = ("AND i.situacao = %s", [tipo]) if tipo is not None else ("", [])
        if agrupar == "cliente":
            query = (
                "SELECT ISNULL(c.nome, 'Sem Cliente') AS label, "
                "  SUM(i.custo_os*i.quant) AS custo, SUM(i.quant) AS qtd "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "LEFT JOIN cliente c ON c.codigo = o.cliente "
                "WHERE o.situacao IN ('A','F','PG') AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND CAST(o.data_entrada AS DATE) BETWEEN %s AND %s " + tipo_sql +
                " GROUP BY c.nome ORDER BY c.nome"
            )
        else:
            query = (
                "SELECT COALESCE(pe.descricao, sv.descricao, i.codigo_interno) AS label, "
                "  SUM(i.custo_os*i.quant) AS custo, SUM(i.quant) AS qtd "
                "FROM os_produto i "
                "JOIN os o ON o.codigo = i.os "
                "LEFT JOIN pecas pe ON pe.codigo_int = i.codigo_interno "
                "LEFT JOIN servicos sv ON sv.codigo = i.codigo_interno "
                "WHERE o.situacao IN ('A','F','PG') AND ISNULL(i.item_cancelado,0) = 0 "
                "  AND CAST(o.data_entrada AS DATE) BETWEEN %s AND %s " + tipo_sql +
                " GROUP BY COALESCE(pe.descricao, sv.descricao, i.codigo_interno) ORDER BY label"
            )
        cur.execute(query, tuple([data_ini, data_fim] + tipo_p))
        rows = cur.fetchall()
        cur.close()

        itens = [{
            "label": (r.get("label") or "—").strip() if isinstance(r.get("label"), str) else (r.get("label") or "—"),
            "custo": round(float(r.get("custo") or 0), 2),
            "qtd": float(r.get("qtd") or 0),
        } for r in rows]
        total = round(sum(i["custo"] for i in itens), 2)
        return {"success": True, "itens": itens, "total": total}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "total": 0.0}
    finally:
        conn.close()


async def custo_os(servidor, banco, data_ini, data_fim, agrupar_por, tipo):
    return await asyncio.to_thread(_custo_os_sync, servidor, banco, data_ini, data_fim, agrupar_por, tipo)
