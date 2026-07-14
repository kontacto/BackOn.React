"""Estoque de Combustível (Posto de Combustível) — tabela `estoque`.

Legado: `frmmanest.frm` ("Manutenção de Estoque..."). Chave natural
composta (`combustivel`, `data`, `turno_estoque`) — a tabela tem um
`cod_est` IDENTITY (surrogate), mas o legado nunca o referencia, só usa a
composição natural pra achar/gravar o registro (mesmo padrão de Metas
Combustível). Upsert por essa combinação.

Schema conferido ao vivo em GERDELL/BARESTELA: `estoque` (cod_est int
IDENTITY, combustivel smallint, data date, venda float, estoque float,
turno_estoque smallint, VENDA2 float).

**Bug do legado corrigido aqui, não replicado** (`Command2_Click`
original / Excluir): o legado deleta `WHERE combustivel=... AND data=...`
**sem filtrar por turno_estoque** — ou seja, excluir um registro de
estoque no legado apaga TODOS os turnos daquele dia pra aquele
combustível, não só o turno selecionado na tela. Isso é uma perda de
dados silenciosa, não uma regra de negócio intencional (Gravar/Consulta
sempre usam a chave composta completa, incluindo turno) — aqui o Excluir
usa a mesma chave composta (`combustivel+data+turno`), evitando apagar
outros turnos por engano.
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _list_sync(servidor: str, banco: str, combustivel: int = None, data: str = None) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        where = []
        params = []
        if combustivel is not None:
            where.append("e.combustivel=%s")
            params.append(combustivel)
        if data:
            where.append("e.data=%s")
            params.append(data)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        cur.execute(
            f"SELECT e.combustivel, e.data, e.turno_estoque, e.venda, e.venda2, e.estoque, "
            f"c.descricao AS combustivel_descricao "
            f"FROM estoque e LEFT JOIN combustivel c ON c.codigo = e.combustivel "
            f"{clause} ORDER BY e.data DESC, e.turno_estoque",
            tuple(params),
        )
        items = [
            {
                "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
                "data": str(r["data"]) if r.get("data") else None,
                "turno_estoque": int(r["turno_estoque"]) if r.get("turno_estoque") is not None else None,
                "venda": float(r.get("venda") or 0),
                "venda2": float(r.get("venda2") or 0),
                "estoque": float(r.get("estoque") or 0),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, combustivel: int, data: str, turno: int, venda: float, venda2: float) -> dict:
    if combustivel is None:
        return {"success": False, "message": "Selecione o combustível."}
    if not data:
        return {"success": False, "message": "Informe a data."}
    if turno is None:
        return {"success": False, "message": "Informe o turno."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM combustivel WHERE codigo=%s", (combustivel,))
        if not cur.fetchone():
            return {"success": False, "message": "Combustível não encontrado."}
        cur.execute(
            "SELECT 1 AS ok FROM estoque WHERE combustivel=%s AND data=%s AND turno_estoque=%s",
            (combustivel, data, turno),
        )
        existe = cur.fetchone() is not None
        if existe:
            cur.execute(
                "UPDATE estoque SET venda=%s, venda2=%s WHERE combustivel=%s AND data=%s AND turno_estoque=%s",
                (venda, venda2, combustivel, data, turno),
            )
        else:
            cur.execute(
                "INSERT INTO estoque (combustivel, data, venda, venda2, turno_estoque) VALUES (%s,%s,%s,%s,%s)",
                (combustivel, data, venda, venda2, turno),
            )
        conn.commit()
        return {"success": True, "message": "Estoque gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, combustivel: int, data: str, turno: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute(
            "DELETE FROM estoque WHERE combustivel=%s AND data=%s AND turno_estoque=%s",
            (combustivel, data, turno),
        )
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


async def list_estoque(servidor: str, banco: str, combustivel: int = None, data: str = None) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, combustivel, data)


async def save_estoque(servidor: str, banco: str, combustivel: int, data: str, turno: int, venda: float, venda2: float) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, combustivel, data, turno, venda, venda2)


async def delete_estoque(servidor: str, banco: str, combustivel: int, data: str, turno: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, combustivel, data, turno)
