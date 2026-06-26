"""Produtos (pecas) + Serviços — lista unificada para uso em pedidos."""
import asyncio

from db.connection import _open_conn


def _list_produtos_servicos_sync(
    servidor: str, banco: str, search: str, page: int, size: int, tipo: str
) -> dict:
    """tipo: 'all' | 'P' (produto/pecas) | 'S' (servico)"""
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        items: list[dict] = []
        total = 0
        like = f"%{search.strip()}%" if search else None
        offset = max(0, (page - 1) * size)

        if tipo in ("all", "P"):
            # PRODUTOS (pecas)
            where_p = ""
            params_p: tuple = ()
            if like:
                where_p = "WHERE p.descricao LIKE %s OR CAST(p.codigo_int AS NVARCHAR(20)) LIKE %s"
                params_p = (like, like)
            cur.execute(
                f"SELECT 'P' AS tipo, p.codigo_int AS codigo, p.descricao, "
                f"       p.p_venda AS valor, p.qtd, p.reservado, p.reservado_os, p.codigo_fab, p.uni "
                f"FROM pecas p {where_p} "
                f"ORDER BY p.descricao",
                params_p,
            )
            for r in cur.fetchall():
                qtd = float(r.get("qtd") or 0)
                reservado = float(r.get("reservado") or 0)
                reservado_os = float(r.get("reservado_os") or 0)
                items.append({
                    "tipo": "P",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": qtd,                       # disponível = pecas.qtd
                    "qtd": qtd,
                    "reservado": reservado,               # reservado p/ Pedido
                    "reservado_os": reservado_os,         # reservado p/ O.S.
                    "estoque_total": round(qtd + reservado + reservado_os, 3),
                    "cod_fab": (r.get("codigo_fab") or "").strip(),
                    "unidade": (r.get("uni") or "").strip(),
                })

        if tipo in ("all", "S"):
            # SERVIÇOS
            where_s = ""
            params_s: tuple = ()
            if like:
                where_s = "WHERE s.descricao LIKE %s OR CAST(s.codigo AS NVARCHAR(20)) LIKE %s"
                params_s = (like, like)
            cur.execute(
                f"SELECT 'S' AS tipo, s.codigo, s.descricao, s.valor_hora AS valor "
                f"FROM servicos s {where_s} "
                f"ORDER BY s.descricao",
                params_s,
            )
            for r in cur.fetchall():
                items.append({
                    "tipo": "S",
                    "codigo": (r.get("codigo") or "").strip() if isinstance(r.get("codigo"), str) else str(r.get("codigo") or ""),
                    "descricao": (r.get("descricao") or "").strip(),
                    "valor": float(r.get("valor") or 0),
                    "estoque": None,
                })

        total = len(items)
        # Paginação em memória (BARESTEL fica abaixo de alguns milhares, ok p/ MVP).
        items_page = items[offset:offset + size]

        cur.close()
        conn.close()
        return {"success": True, "items": items_page, "total": total, "page": page, "size": size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


async def list_produtos_servicos(servidor: str, banco: str, search: str,
                                  page: int, size: int, tipo: str) -> dict:
    return await asyncio.to_thread(
        _list_produtos_servicos_sync, servidor, banco, search, page, size, tipo
    )
