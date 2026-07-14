"""Tanque/Estoque (Posto de Combustível) — tabela `Tanque_Estoque`.

Legado: `frmmantes.frm` ("Manutenção de Tanques / Estoque..."). Chave
natural composta (`tanque`, `data`) — sem PK própria. Upsert por essa
combinação (`Command3_Click` original: SELECT antes de decidir INSERT ou
UPDATE, mesmo padrão de Estoque Combustível/Metas).

Schema conferido ao vivo em GERDELL/BARESTELA: `Tanque_Estoque` (tanque
smallint NOT NULL, data date NOT NULL, estoque int).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _list_sync(servidor: str, banco: str, tanque: int = None) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        where = "WHERE te.tanque=%s" if tanque is not None else ""
        params = (tanque,) if tanque is not None else ()
        cur.execute(
            f"SELECT te.tanque, te.data, te.estoque, t.capacidade, c.descricao AS combustivel_descricao "
            f"FROM Tanque_Estoque te "
            f"JOIN Tanque t ON t.tanque = te.tanque "
            f"LEFT JOIN Combustivel c ON c.codigo = t.combustivel "
            f"{where} ORDER BY te.data DESC, te.tanque",
            params,
        )
        items = [
            {
                "tanque": int(r["tanque"]),
                "data": str(r["data"]) if r.get("data") else None,
                "estoque": int(r.get("estoque") or 0),
                "capacidade": int(r.get("capacidade") or 0),
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, tanque: int, data: str, estoque: int) -> dict:
    if tanque is None:
        return {"success": False, "message": "Informe o tanque."}
    if not data:
        return {"success": False, "message": "Informe a data."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM Tanque WHERE tanque=%s", (tanque,))
        if not cur.fetchone():
            return {"success": False, "message": "Tanque não encontrado."}
        cur.execute("SELECT 1 AS ok FROM Tanque_Estoque WHERE tanque=%s AND data=%s", (tanque, data))
        existe = cur.fetchone() is not None
        if existe:
            cur.execute("UPDATE Tanque_Estoque SET estoque=%s WHERE tanque=%s AND data=%s", (estoque, tanque, data))
        else:
            cur.execute("INSERT INTO Tanque_Estoque (tanque, data, estoque) VALUES (%s,%s,%s)", (tanque, data, estoque))
        conn.commit()
        return {"success": True, "message": "Estoque de tanque gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, tanque: int, data: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("DELETE FROM Tanque_Estoque WHERE tanque=%s AND data=%s", (tanque, data))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Registro não encontrado."}
        conn.commit()
        return {"success": True, "message": "Registro excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tanque_estoque(servidor: str, banco: str, tanque: int = None) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, tanque)


async def save_tanque_estoque(servidor: str, banco: str, tanque: int, data: str, estoque: int) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, tanque, data, estoque)


async def delete_tanque_estoque(servidor: str, banco: str, tanque: int, data: str) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, tanque, data)
