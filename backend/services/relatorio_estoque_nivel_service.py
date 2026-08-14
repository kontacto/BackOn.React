"""Estoque por Nível — Painel de Relatórios > Estoque.

Migração de `Geral\\FrmRelFecEst.frm`. Soma unidades em estoque
(`qtd+reservado+reservado_os`) e seu valor a custo de reposição e a preço
de venda, agrupado por nível de produto (hierarquia `niveis`) — snapshot
atual, sem período.

Mesmo padrão de agregação já usado em "Resumo de Venda" (grupo Caixa):
`GROUP BY nivel1..5` direto em SQL substitui o loop de matching contra o
FlexGrid do legado (puro workaround de VB6, ver "Não replicar truques
VB6" em CLAUDE.md); breadcrumb completo do nível é resolvido no frontend
via `buildNivelBreadcrumb`, reaproveitando o mesmo endpoint de lookup já
usado por Resumo de Venda (`GET /api/relatorios/margem-lucro/niveis`).
"""
import asyncio

from db.connection import _open_conn


def _estoque_nivel_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT nivel1, nivel2, nivel3, nivel4, nivel5, "
            "  SUM(qtd+reservado+reservado_os) AS unidades, "
            "  SUM((qtd+reservado+reservado_os) * ISNULL(custo_reposicao,0)) AS valor_custo, "
            "  SUM((qtd+reservado+reservado_os) * ISNULL(p_venda,0)) AS valor_venda "
            "FROM pecas "
            "WHERE (qtd+reservado+reservado_os) > 0 "
            "GROUP BY nivel1, nivel2, nivel3, nivel4, nivel5"
        )
        rows = cur.fetchall()
        cur.close()

        itens = []
        tot_unidades = tot_custo = tot_venda = 0.0
        for r in rows:
            partes = [(r.get(f"nivel{i}") or "").strip() for i in range(1, 6)]
            codigo = "".join(partes)
            unidades = float(r.get("unidades") or 0)
            valor_custo = round(float(r.get("valor_custo") or 0), 2)
            valor_venda = round(float(r.get("valor_venda") or 0), 2)
            itens.append({
                "codigo": codigo,
                "unidades": unidades,
                "valor_custo": valor_custo,
                "valor_venda": valor_venda,
            })
            tot_unidades += unidades
            tot_custo += valor_custo
            tot_venda += valor_venda
        itens.sort(key=lambda x: x["codigo"])

        totais = {
            "unidades": round(tot_unidades, 2),
            "valor_custo": round(tot_custo, 2),
            "valor_venda": round(tot_venda, 2),
        }
        return {"success": True, "itens": itens, "totais": totais}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "totais": {}}
    finally:
        conn.close()


async def estoque_nivel(servidor, banco):
    return await asyncio.to_thread(_estoque_nivel_sync, servidor, banco)
