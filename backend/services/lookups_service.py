"""Lookups auxiliares — área de atuação e funcionários (vendedores)."""
import asyncio

from db.connection import _open_conn


def _list_area_atuacao_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT area AS codigo, descricao FROM area_atuacao ORDER BY descricao")
        items = [{"codigo": int(r["codigo"]), "descricao": (r.get("descricao") or "").strip()} for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_funcionarios_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT codigo_int AS codigo, nome, nome_guerra, cod_funcao "
            "FROM funcionarios WHERE ISNULL(situacao,'A') <> 'I' ORDER BY nome"
        )
        items = [{
            "codigo": int(r["codigo"]),
            "nome": (r.get("nome") or "").strip(),
            "nome_guerra": (r.get("nome_guerra") or "").strip(),
            "cod_funcao": (r.get("cod_funcao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


async def list_area_atuacao(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_area_atuacao_sync, servidor, banco)


async def list_funcionarios(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_funcionarios_sync, servidor, banco)
