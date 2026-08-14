"""Estoque — Painel de Relatórios > Estoque.

Migração de `Geral\\FrmRelPecNiv.frm` ("Relatório de Peças por Níveis").
Detalhe produto-a-produto (complementar ao agregado de "Estoque por
Nível") dentro de uma combinação de nível escolhida — o legado usa 5
combos em cascata (Nível1→Nível2→...→Nível5); aqui o frontend manda um
único código concatenado (mesmo esquema de 3 caracteres por nível já
usado em `margem_lucro_service._nivel_clause`, reaproveitado direto).

Só produtos `situacao='A'` (Ativo), mesma trava do legado. Colunas
`area`/`prateleira`/`escaninho` (localização física) e `custo_inventario`
já são reais e usadas em Produto Completo/Inventário — confirmado antes
de portar.
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from services.margem_lucro_service import _nivel_clause

_ORDEM_COL = {"codigo": "codigo_int", "descricao": "descricao"}


def _estoque_sync(servidor: str, banco: str, nivel: Optional[str], ordenar_por: Optional[str]) -> dict:
    if not (nivel or "").strip():
        return {"success": False, "message": "Selecione o nível.", "itens": []}
    coluna = _ORDEM_COL.get(ordenar_por or "codigo", "codigo_int")
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        clauses, params = _nivel_clause("p", nivel)
        where = " AND ".join(["p.situacao = 'A'"] + clauses)
        cur.execute(
            "SELECT p.codigo_int, p.codigo_fab, p.descricao, (p.qtd + p.reservado + p.reservado_os) AS quant, "
            "  p.custo_inventario, p.p_venda, p.area, p.prateleira, p.escaninho "
            f"FROM pecas p WHERE {where} "
            f"ORDER BY p.{coluna}",
            tuple(params),
        )
        itens = [{
            "codigo_int": (r.get("codigo_int") or "").strip(),
            "codigo_fab": (r.get("codigo_fab") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "quant": float(r.get("quant") or 0),
            "custo_inventario": round(float(r.get("custo_inventario") or 0), 2),
            "p_venda": round(float(r.get("p_venda") or 0), 2),
            "area": (r.get("area") or "").strip(),
            "prateleira": (r.get("prateleira") or "").strip(),
            "escaninho": (r.get("escaninho") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "itens": itens}
    except Exception as e:
        return {"success": False, "message": f"Erro: {e}", "itens": []}
    finally:
        conn.close()


async def estoque(servidor, banco, nivel, ordenar_por):
    return await asyncio.to_thread(_estoque_sync, servidor, banco, nivel, ordenar_por)
