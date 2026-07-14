"""Metas de Combustível (Posto de Combustível) — tabela `combustivel_meta`.

Legado: `frmcadmet.frm` ("Metas dos Combustíveis"). Chave natural composta
(`grupo`, `ano`, `mes`) — a tabela não tem coluna de PK própria; upsert
por essa combinação, mesmo padrão do legado (SELECT antes de decidir
INSERT ou UPDATE).

NOTA (2026-07-13): não confundir com `FrmCadMeta.frm` (nome parecido,
pasta `Posto`) — aquele arquivo é um rascunho abandonado que grava na
tabela `Bomba` (copy-paste do form de Bombas com o caption trocado),
nunca chega a tocar `combustivel_meta`. Confirmado com o usuário que a
fonte de verdade é `frmcadmet.frm` (ver PENDENCIAS.md).

Schema conferido ao vivo em GERDELL/BARESTELA: `combustivel_grupo`
(codigo smallint, descricao nvarchar(20)) e `combustivel_meta` (grupo
smallint NOT NULL, ano int NOT NULL, mes smallint NOT NULL, meta float) —
bate exatamente com o que o `.frm` espera, sem surpresa de nome de coluna.
"""
import asyncio

from db.connection import _open_conn
from services.posto_common import modulo_posto_ativo, MODULO_DESATIVADO_MSG as _MODULO_DESATIVADO_MSG


def _list_grupos_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG, "items": []}
        cur.execute("SELECT codigo, descricao FROM combustivel_grupo ORDER BY descricao")
        items = [
            {"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()}
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _list_metas_sync(servidor: str, banco: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG, "items": []}
        cur.execute(
            "SELECT m.grupo, m.ano, m.mes, m.meta, g.descricao AS grupo_descricao "
            "FROM combustivel_meta m JOIN combustivel_grupo g ON g.codigo = m.grupo "
            "ORDER BY m.ano, m.mes, g.descricao"
        )
        items = [
            {
                "grupo": int(r["grupo"]),
                "grupo_descricao": (r.get("grupo_descricao") or "").strip(),
                "ano": int(r["ano"]),
                "mes": int(r["mes"]),
                "meta": float(r.get("meta") or 0),
            }
            for r in cur.fetchall()
        ]
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_meta_sync(servidor: str, banco: str, grupo: int, ano: int, mes: int, meta: float) -> dict:
    if mes is None or not (1 <= int(mes) <= 12):
        return {"success": False, "message": "Mês inválido — informe um valor entre 1 e 12."}
    if ano is None or not (2000 <= int(ano) <= 2100):
        return {"success": False, "message": "Ano inválido."}
    if grupo is None:
        return {"success": False, "message": "Selecione o grupo de combustível."}

    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG}
        cur.execute("SELECT 1 AS ok FROM combustivel_grupo WHERE codigo=%s", (grupo,))
        if not cur.fetchone():
            return {"success": False, "message": "Grupo de combustível não encontrado."}
        cur.execute(
            "SELECT 1 AS ok FROM combustivel_meta WHERE grupo=%s AND ano=%s AND mes=%s",
            (grupo, ano, mes),
        )
        existe = cur.fetchone() is not None
        if existe:
            cur.execute(
                "UPDATE combustivel_meta SET meta=%s WHERE grupo=%s AND ano=%s AND mes=%s",
                (meta, grupo, ano, mes),
            )
        else:
            cur.execute(
                "INSERT INTO combustivel_meta (grupo, ano, mes, meta) VALUES (%s,%s,%s,%s)",
                (grupo, ano, mes, meta),
            )
        conn.commit()
        return {"success": True, "message": "Meta gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_meta_sync(servidor: str, banco: str, grupo: int, ano: int, mes: int) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        if not modulo_posto_ativo(cur):
            return {"success": False, "message": _MODULO_DESATIVADO_MSG}
        cur.execute(
            "DELETE FROM combustivel_meta WHERE grupo=%s AND ano=%s AND mes=%s",
            (grupo, ano, mes),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"success": False, "message": "Meta não encontrada."}
        conn.commit()
        return {"success": True, "message": "Meta excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


async def list_grupos(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_grupos_sync, servidor, banco)


async def list_metas(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_metas_sync, servidor, banco)


async def save_meta(servidor: str, banco: str, grupo: int, ano: int, mes: int, meta: float) -> dict:
    return await asyncio.to_thread(_save_meta_sync, servidor, banco, grupo, ano, mes, meta)


async def delete_meta(servidor: str, banco: str, grupo: int, ano: int, mes: int) -> dict:
    return await asyncio.to_thread(_delete_meta_sync, servidor, banco, grupo, ano, mes)
