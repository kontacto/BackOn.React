"""Produtos Reservados — Painel de Relatórios > Estoque.

Migração de `Revenda\\frmrelpecres.frm`. Lista `pecas` onde
`(reservado_os + reservado) <> 0` — snapshot atual, sem período.
`pecas.reservado`/`reservado_os` são colunas reais já usadas em outros
módulos desta migração (Checkout, Contratos, Inventário).

Ordenação simplificada em relação ao legado: o `.frm` ordena por
`LEFT(codigo_int,1), CONVERT(bigint, SUBSTRING(codigo_int,2,10))` (parse
numérico do código pra ordem "natural" 1,2,10 em vez de 1,10,2) — não
replicado; ordenação alfabética simples de `codigo_int` já é suficiente
pro volume típico de produtos reservados (não é um relatório de milhares
de linhas).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn

_ORDEM_COL = {"codigo_int": "codigo_int", "codigo_fab": "codigo_fab", "descricao": "descricao"}


def _produtos_reservados_sync(servidor: str, banco: str, ordenar_por: Optional[str]) -> dict:
    coluna = _ORDEM_COL.get(ordenar_por or "codigo_int", "codigo_int")
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int, codigo_fab, descricao, p_venda, (reservado_os + reservado) AS reserva "
            "FROM pecas WHERE (reservado_os + reservado) <> 0 "
            f"ORDER BY {coluna}"
        )
        itens = []
        total = 0.0
        for r in cur.fetchall():
            p_venda = float(r.get("p_venda") or 0)
            reserva = float(r.get("reserva") or 0)
            preco_total = round(p_venda * reserva, 2)
            itens.append({
                "codigo_int": (r.get("codigo_int") or "").strip(),
                "codigo_fab": (r.get("codigo_fab") or "").strip(),
                "descricao": (r.get("descricao") or "").strip(),
                "p_venda": round(p_venda, 2),
                "reserva": reserva,
                "preco_total": preco_total,
            })
            total += preco_total
        cur.close()
        return {"success": True, "itens": itens, "total": round(total, 2)}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": [], "total": 0.0}
    finally:
        conn.close()


async def produtos_reservados(servidor, banco, ordenar_por):
    return await asyncio.to_thread(_produtos_reservados_sync, servidor, banco, ordenar_por)
