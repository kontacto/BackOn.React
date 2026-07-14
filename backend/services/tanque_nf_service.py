"""Tanque/Nota Fiscal (Posto de Combustível) — tabela `Tanque_NF`.

Legado: `frmmantnf.frm` ("Tanque / Nota Fiscal"). Chave natural composta
(`nota`, `tanque`) — sem PK própria. Upsert por essa combinação
(`Command1_Click` original). Vínculo entre uma Nota Fiscal de compra de
combustível (já migrada, `n_fiscal`/`notas_fiscais_service.py`) e o
tanque que recebeu a quantidade — reaproveita a Nota Fiscal já existente,
não a duplica.

Schema conferido ao vivo em GERDELL/BARESTELA: `Tanque_NF` (tanque
smallint, nota int, qtd int). `n_fiscal` (codigo int IDENTITY,
fornecedor int, num_nf float, serie_nf nvarchar, situacao nvarchar —
única coluna NOT NULL é `codigo`, a IDENTITY).

Busca da Nota Fiscal replicada fielmente: por código direto OU por
fornecedor+série+número (os dois caminhos que `Campo_LostFocus` do
legado usa).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _find_nota_sync(servidor: str, banco: str, codigo: int = None, fornecedor: int = None, serie_nf: str = None, num_nf: float = None) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        if codigo is not None:
            cur.execute("SELECT codigo, fornecedor, num_nf, serie_nf FROM n_fiscal WHERE codigo=%s", (codigo,))
        else:
            cur.execute(
                "SELECT codigo, fornecedor, num_nf, serie_nf FROM n_fiscal "
                "WHERE fornecedor=%s AND serie_nf=%s AND num_nf=%s",
                (fornecedor, serie_nf, num_nf),
            )
        row = cur.fetchone()
        if not row:
            return {"success": False, "message": "Nota Fiscal não cadastrada."}
        return {
            "success": True,
            "item": {
                "codigo": int(row["codigo"]),
                "fornecedor": int(row["fornecedor"]) if row.get("fornecedor") is not None else None,
                "num_nf": row.get("num_nf"),
                "serie_nf": (row.get("serie_nf") or "").strip(),
            },
        }
    finally:
        conn.close()


def _list_sync(servidor: str, banco: str, nota: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": [], "total": 0}
        cur.execute(
            "SELECT tn.tanque, tn.nota, tn.qtd, t.capacidade, c.descricao AS combustivel_descricao "
            "FROM Tanque_NF tn "
            "JOIN Tanque t ON t.tanque = tn.tanque "
            "LEFT JOIN Combustivel c ON c.codigo = t.combustivel "
            "WHERE tn.nota=%s ORDER BY tn.tanque",
            (nota,),
        )
        items = [
            {
                "tanque": int(r["tanque"]),
                "nota": int(r["nota"]),
                "qtd": int(r.get("qtd") or 0),
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        total = sum(i["qtd"] for i in items)
        return {"success": True, "items": items, "total": total}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, nota: int, tanque: int, qtd: int) -> dict:
    if nota is None:
        return {"success": False, "message": "Informe a Nota Fiscal."}
    if tanque is None:
        return {"success": False, "message": "Informe o tanque."}
    if not qtd:
        return {"success": False, "message": "Informe a quantidade."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM n_fiscal WHERE codigo=%s", (nota,))
        if not cur.fetchone():
            return {"success": False, "message": "Nota Fiscal não encontrada."}
        cur.execute("SELECT 1 AS ok FROM Tanque WHERE tanque=%s", (tanque,))
        if not cur.fetchone():
            return {"success": False, "message": "Tanque não encontrado."}
        cur.execute("SELECT 1 AS ok FROM Tanque_NF WHERE nota=%s AND tanque=%s", (nota, tanque))
        existe = cur.fetchone() is not None
        if existe:
            cur.execute("UPDATE Tanque_NF SET qtd=%s WHERE nota=%s AND tanque=%s", (qtd, nota, tanque))
        else:
            cur.execute("INSERT INTO Tanque_NF (nota, tanque, qtd) VALUES (%s,%s,%s)", (nota, tanque, qtd))
        conn.commit()
        return {"success": True, "message": "Vínculo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, nota: int, tanque: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("DELETE FROM Tanque_NF WHERE nota=%s AND tanque=%s", (nota, tanque))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Movimentação não encontrada."}
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


async def find_nota(servidor: str, banco: str, codigo: int = None, fornecedor: int = None, serie_nf: str = None, num_nf: float = None) -> dict:
    return await asyncio.to_thread(_find_nota_sync, servidor, banco, codigo, fornecedor, serie_nf, num_nf)


async def list_tanque_nf(servidor: str, banco: str, nota: int) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco, nota)


async def save_tanque_nf(servidor: str, banco: str, nota: int, tanque: int, qtd: int) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, nota, tanque, qtd)


async def delete_tanque_nf(servidor: str, banco: str, nota: int, tanque: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, nota, tanque)
