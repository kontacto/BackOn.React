"""Tabelas auxiliares: Marcas e Modelos (veículo/produto) + import FIPE.

- marcas(codigo nvarchar, descricao, marca_produto bit/int)
  marca_produto = 0 -> listada na O.S. (veículo) ; 1 -> listada em Produtos.
- modelos(cod_marca, codigo nvarchar, descricao, ...)

Regras:
- Não excluir marca que possua modelos vinculados.
- Não criar modelo sem marca.
- `codigo` gerado sequencialmente (MAX numérico + 1, 3 dígitos).
Sem dependência de `requests`: usa urllib para a API FIPE.
"""
import asyncio
import json
import urllib.request
from typing import Optional

from db.connection import _open_conn

FIPE_BASE = "https://parallelum.com.br/fipe/api/v1"


def _next_codigo(cur, tabela: str) -> str:
    cur.execute(
        f"SELECT MAX(CAST(codigo AS INT)) AS mx FROM {tabela} "
        f"WHERE ISNUMERIC(codigo) = 1"
    )
    r = cur.fetchone()
    nxt = int((r.get("mx") if r else None) or 0) + 1
    return f"{nxt:03d}"


# ---------------- MARCAS ----------------
def _list_marcas_sync(servidor: str, banco: str, marca_produto: Optional[bool], search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if marca_produto is not None:
            where.append("ISNULL(marca_produto,'0') = %s")
            params.append("1" if marca_produto else "0")
        if search and search.strip():
            where.append("descricao LIKE %s")
            params.append(f"%{search.strip()}%")
        sql = "SELECT codigo, descricao, ISNULL(marca_produto,'0') AS marca_produto FROM marcas"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY descricao"
        cur.execute(sql, tuple(params))
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
            "marca_produto": str(r.get("marca_produto") or "0").strip() == "1",
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_marca_sync(servidor: str, banco: str, codigo: Optional[str], descricao: str, marca_produto: bool) -> dict:
    desc = (descricao or "").strip()
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        mp = 1 if marca_produto else 0
        if codigo:  # update
            cur.execute("UPDATE marcas SET descricao=%s, marca_produto=%s WHERE codigo=%s", (desc, mp, codigo))
            novo = codigo
        else:  # create
            novo = _next_codigo(cur, "marcas")
            cur.execute("INSERT INTO marcas (codigo, descricao, marca_produto) VALUES (%s,%s,%s)", (novo, desc, mp))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Marca gravada."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_marca_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM modelos WHERE cod_marca=%s", (codigo,))
        if cur.fetchone():
            cur.close()
            return {"success": False, "message": "Marca vinculada a modelos — não pode ser excluída."}
        cur.execute("DELETE FROM marcas WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Marca excluída."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- MODELOS ----------------
def _list_modelos_sync(servidor: str, banco: str, cod_marca: Optional[str], search: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        where = []
        params: list = []
        if cod_marca:
            where.append("cod_marca = %s")
            params.append(cod_marca)
        if search and search.strip():
            where.append("descricao LIKE %s")
            params.append(f"%{search.strip()}%")
        sql = "SELECT codigo, cod_marca, descricao FROM modelos"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY descricao"
        cur.execute(sql, tuple(params))
        items = [{
            "codigo": (r.get("codigo") or "").strip(),
            "cod_marca": (r.get("cod_marca") or "").strip(),
            "descricao": (r.get("descricao") or "").strip(),
        } for r in cur.fetchall()]
        cur.close()
        return {"success": True, "items": items}
    finally:
        conn.close()


def _save_modelo_sync(servidor: str, banco: str, codigo: Optional[str], cod_marca: str, descricao: str) -> dict:
    desc = (descricao or "").strip()
    if not (cod_marca or "").strip():
        return {"success": False, "message": "Selecione a marca do modelo."}
    if not desc:
        return {"success": False, "message": "Descrição é obrigatória."}
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT TOP 1 1 AS ok FROM marcas WHERE codigo=%s", (cod_marca,))
        if not cur.fetchone():
            cur.close()
            return {"success": False, "message": "Marca inexistente."}
        if codigo:
            cur.execute("UPDATE modelos SET cod_marca=%s, descricao=%s WHERE codigo=%s", (cod_marca, desc, codigo))
            novo = codigo
        else:
            novo = _next_codigo(cur, "modelos")
            cur.execute("INSERT INTO modelos (codigo, cod_marca, descricao) VALUES (%s,%s,%s)", (novo, cod_marca, desc))
        conn.commit()
        cur.close()
        return {"success": True, "codigo": novo, "message": "Modelo gravado."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}
    finally:
        conn.close()


def _delete_modelo_sync(servidor: str, banco: str, codigo: str) -> dict:
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("DELETE FROM modelos WHERE codigo=%s", (codigo,))
        conn.commit()
        cur.close()
        return {"success": True, "message": "Modelo excluído."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao excluir: {e}"}
    finally:
        conn.close()


# ---------------- FIPE (urllib, sem requests) ----------------
def _fipe_get(path: str) -> list:
    url = f"{FIPE_BASE}/{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "BackOn/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fipe_marcas_sync(tipo: str) -> dict:
    try:
        data = _fipe_get(f"{tipo}/marcas")
        items = [{"id": str(m.get("codigo")), "nome": m.get("nome")} for m in data]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Falha FIPE: {e}", "items": []}


def _fipe_modelos_sync(tipo: str, marca_id: str) -> dict:
    try:
        data = _fipe_get(f"{tipo}/marcas/{marca_id}/modelos")
        modelos = (data or {}).get("modelos", [])
        items = [{"id": str(m.get("codigo")), "nome": m.get("nome")} for m in modelos]
        return {"success": True, "items": items}
    except Exception as e:
        return {"success": False, "message": f"Falha FIPE: {e}", "items": []}


def _import_fipe_sync(servidor: str, banco: str, tipo: str, fipe_marca_id: str, descricao: str) -> dict:
    """Cria a marca (veículo, marca_produto=0) se não existir e importa TODOS os
    modelos da marca FIPE escolhida (ignorando duplicados por descrição)."""
    nome_marca = (descricao or "").strip()
    if not nome_marca:
        return {"success": False, "message": "Marca FIPE inválida."}
    fipe = _fipe_modelos_sync(tipo, fipe_marca_id)
    if not fipe.get("success"):
        return fipe
    conn = _open_conn(servidor, banco)
    try:
        cur = conn.cursor(as_dict=True)
        # marca (procura por descrição entre as de veículo)
        cur.execute("SELECT TOP 1 codigo FROM marcas WHERE descricao=%s AND ISNULL(marca_produto,0)=0", (nome_marca,))
        row = cur.fetchone()
        if row:
            cod_marca = (row.get("codigo") or "").strip()
        else:
            cod_marca = _next_codigo(cur, "marcas")
            cur.execute("INSERT INTO marcas (codigo, descricao, marca_produto) VALUES (%s,%s,0)", (cod_marca, nome_marca))
        # modelos existentes p/ evitar duplicar
        cur.execute("SELECT descricao FROM modelos WHERE cod_marca=%s", (cod_marca,))
        existentes = {(r.get("descricao") or "").strip().upper() for r in cur.fetchall()}
        novos = 0
        for m in fipe["items"]:
            nome = (m.get("nome") or "").strip()
            if not nome or nome.upper() in existentes:
                continue
            cod = _next_codigo(cur, "modelos")
            cur.execute("INSERT INTO modelos (codigo, cod_marca, descricao) VALUES (%s,%s,%s)", (cod, cod_marca, nome))
            existentes.add(nome.upper())
            novos += 1
        conn.commit()
        cur.close()
        return {"success": True, "cod_marca": cod_marca, "importados": novos,
                "message": f"Marca '{nome_marca}' importada · {novos} modelos."}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao importar: {e}"}
    finally:
        conn.close()


# ---------------- async wrappers ----------------
async def list_marcas(servidor, banco, marca_produto, search):
    return await asyncio.to_thread(_list_marcas_sync, servidor, banco, marca_produto, search)


async def save_marca(servidor, banco, codigo, descricao, marca_produto):
    return await asyncio.to_thread(_save_marca_sync, servidor, banco, codigo, descricao, marca_produto)


async def delete_marca(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_marca_sync, servidor, banco, codigo)


async def list_modelos(servidor, banco, cod_marca, search):
    return await asyncio.to_thread(_list_modelos_sync, servidor, banco, cod_marca, search)


async def save_modelo(servidor, banco, codigo, cod_marca, descricao):
    return await asyncio.to_thread(_save_modelo_sync, servidor, banco, codigo, cod_marca, descricao)


async def delete_modelo(servidor, banco, codigo):
    return await asyncio.to_thread(_delete_modelo_sync, servidor, banco, codigo)


async def fipe_marcas(tipo):
    return await asyncio.to_thread(_fipe_marcas_sync, tipo)


async def fipe_modelos(tipo, marca_id):
    return await asyncio.to_thread(_fipe_modelos_sync, tipo, marca_id)


async def import_fipe(servidor, banco, tipo, fipe_marca_id, descricao):
    return await asyncio.to_thread(_import_fipe_sync, servidor, banco, tipo, fipe_marca_id, descricao)
