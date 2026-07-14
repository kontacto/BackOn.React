"""Tanques (Posto de Combustível) — tabela `tanque`.

Legado: `frmmantan.frm` ("Manutenção de Tanques..."). Chave própria
`tanque` (smallint) — upsert por esse código (INSERT se não existe, senão
UPDATE de `capacidade`/`combustivel`), mesmo padrão do
`Command3_Click` original.

Schema conferido ao vivo em GERDELL/BARESTELA: `tanque` (tanque smallint
NOT NULL, capacidade int, combustivel smallint FK -> combustivel.codigo,
data_ativacao date). **`data_ativacao` não existe no `.frm` fornecido** —
coluna adicionada depois, fora de escopo desta migração (não lida/gravada
aqui, mesmo tratamento dado a colunas "extras" não previstas pelo legado
em outras telas já migradas).

FK real confirmada (`sys.foreign_keys`): `bomba.tanque -> tanque.tanque`,
`tanque_estoque.tanque -> tanque.tanque`, `tanque_nf.tanque ->
tanque.tanque` — ou seja, Tanques é pré-requisito de Bombas,
Tanque/Estoque e Tanque/Nota Fiscal (ainda não migradas).
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG


def _list_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT t.tanque, t.capacidade, t.combustivel, c.descricao AS combustivel_descricao "
            "FROM tanque t LEFT JOIN combustivel c ON c.codigo = t.combustivel "
            "ORDER BY t.tanque"
        )
        items = [
            {
                "tanque": int(r["tanque"]),
                "capacidade": int(r["capacidade"]) if r.get("capacidade") is not None else 0,
                "combustivel": int(r["combustivel"]) if r.get("combustivel") is not None else None,
                "combustivel_descricao": (r.get("combustivel_descricao") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_sync(servidor: str, banco: str, tanque: int, capacidade: int, combustivel: int) -> dict:
    if tanque is None:
        return {"success": False, "message": "Informe o código do tanque."}
    if capacidade is None:
        return {"success": False, "message": "Informe a capacidade."}
    if combustivel is None:
        return {"success": False, "message": "Selecione o combustível."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM combustivel WHERE codigo=%s", (combustivel,))
        if not cur.fetchone():
            return {"success": False, "message": "Combustível não encontrado."}
        cur.execute("SELECT 1 AS ok FROM tanque WHERE tanque=%s", (tanque,))
        existe = cur.fetchone() is not None
        if existe:
            cur.execute(
                "UPDATE tanque SET capacidade=%s, combustivel=%s WHERE tanque=%s",
                (capacidade, combustivel, tanque),
            )
        else:
            cur.execute(
                "INSERT INTO tanque (tanque, capacidade, combustivel) VALUES (%s,%s,%s)",
                (tanque, capacidade, combustivel),
            )
        conn.commit()
        return {"success": True, "message": "Tanque gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_sync(servidor: str, banco: str, tanque: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": MODULO_DESATIVADO_MSG}
        cur.execute("SELECT TOP 1 1 AS ok FROM bomba WHERE tanque=%s", (tanque,))
        if cur.fetchone():
            return {"success": False, "message": "Existem bombas vinculadas a este tanque — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM tanque_estoque WHERE tanque=%s", (tanque,))
        if cur.fetchone():
            return {"success": False, "message": "Existem registros de estoque vinculados a este tanque — não pode ser excluído."}
        cur.execute("SELECT TOP 1 1 AS ok FROM tanque_nf WHERE tanque=%s", (tanque,))
        if cur.fetchone():
            return {"success": False, "message": "Existem notas fiscais vinculadas a este tanque — não pode ser excluído."}
        cur.execute("DELETE FROM tanque WHERE tanque=%s", (tanque,))
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Tanque não encontrado."}
        conn.commit()
        return {"success": True, "message": "Tanque excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_tanques(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_sync, servidor, banco)


async def save_tanque(servidor: str, banco: str, tanque: int, capacidade: int, combustivel: int) -> dict:
    return await asyncio.to_thread(_save_sync, servidor, banco, tanque, capacidade, combustivel)


async def delete_tanque(servidor: str, banco: str, tanque: int) -> dict:
    return await asyncio.to_thread(_delete_sync, servidor, banco, tanque)
