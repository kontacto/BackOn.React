"""Ordem de Serviço (tabela `os`) — listagem, leitura e CRUD do cabeçalho.

Diferenças importantes em relação ao pedido_venda:
  • `os.codigo` NÃO é IDENTITY → geramos MAX(codigo)+1 dentro da transação.
  • Vendedor/executor ficam no nível do ITEM (os_produto), não no cabeçalho.
  • Colunas NOT NULL sem default: codigo, km, OS_ORIGINAL → preenchidas no insert.
Situações reutilizam os mesmos códigos do pedido (A/F/PG/C).
"""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import OSListRequest, OSSaveRequest
from services.constants import SITUACAO_LABEL


def _list_os_sync(req: OSListRequest) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "total": 0}
    try:
        cur = conn.cursor(as_dict=True)
        where_parts: list[str] = []
        params: list = []
        term = (req.search or "").strip()
        if term:
            like = f"%{term}%"
            where_parts.append(
                "(c.nome LIKE %s OR c.cgc_cpf LIKE %s OR CAST(o.codigo AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like])
        if req.situacao:
            where_parts.append("o.situacao = %s")
            params.append(req.situacao)
        if req.data_ini:
            where_parts.append("o.data_entrada >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append("o.data_entrada <= %s")
            params.append(req.data_fim)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        cur.execute(
            f"SELECT COUNT(*) c FROM os o LEFT JOIN cliente c ON c.codigo = o.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        offset = max(0, (req.page - 1) * req.size)
        cur.execute(
            f"SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, o.valor, "
            f"       o.area_atuacao, c.nome AS cliente_nome "
            f"FROM os o "
            f"LEFT JOIN cliente c ON c.codigo = o.cliente "
            f"{where} "
            f"ORDER BY o.codigo DESC OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            items.append({
                "codigo": int(r["codigo"] or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "data": r["data_entrada"].isoformat() if r.get("data_entrada") else None,
                "hora": (r.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(r.get("valor") or 0),
            })
        cur.close()
        conn.close()
        return {"success": True, "items": items, "total": total, "page": req.page, "size": req.size}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "total": 0}


def _get_os_sync(servidor: str, banco: str, codigo: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT o.codigo, o.cliente, o.data_entrada, o.hora_entrada, o.situacao, o.valor, "
            "       o.area_atuacao, o.descricao_cliente, o.obs, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       a.descricao AS area_descricao "
            "FROM os o "
            "LEFT JOIN cliente c ON c.codigo = o.cliente "
            "LEFT JOIN area_atuacao a ON a.area = o.area_atuacao "
            "WHERE o.codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "OS não encontrada."}
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "os": {
                "codigo": int(row["codigo"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data_entrada"].isoformat() if row.get("data_entrada") else None,
                "hora": (row.get("hora_entrada") or "").strip(),
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("valor") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
                "descricao_cliente": row.get("descricao_cliente") or "",
                "obs": row.get("obs") or "",
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_os_sync(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Update: só OS Aberta ('A') pode ser alterada.
        if codigo is not None:
            cur.execute("SELECT situacao FROM os WHERE codigo=%s", (codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"OS com situação '{label}' não pode ser alterada."}

        descricao_cliente = req.descricao_cliente or ""
        obs = req.obs or ""

        if codigo is None:
            # codigo NÃO é identity → gera MAX+1. km e OS_ORIGINAL são NOT NULL.
            cur.execute("SELECT ISNULL(MAX(codigo),0)+1 AS novo FROM os")
            novo = int(cur.fetchone()["novo"] or 1)
            cur.execute(
                "INSERT INTO os "
                "(codigo, cliente, data_entrada, hora_entrada, situacao, valor, "
                " area_atuacao, descricao_cliente, obs, km, OS_ORIGINAL) "
                "VALUES (%s, %s, CAST(GETDATE() AS DATE), CONVERT(NVARCHAR(8), GETDATE(), 108), "
                "        'A', 0, %s, %s, %s, 0, 0)",
                (novo, req.cliente, req.area_atuacao, descricao_cliente, obs),
            )
            os_id = novo
        else:
            cur.execute(
                "UPDATE os SET cliente=%s, area_atuacao=%s, descricao_cliente=%s, obs=%s "
                "WHERE codigo=%s",
                (req.cliente, req.area_atuacao, descricao_cliente, obs, codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "OS não encontrada."}
            os_id = codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codigo": os_id}
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao gravar: {e}"}


async def list_os(req: OSListRequest) -> dict:
    return await asyncio.to_thread(_list_os_sync, req)


async def get_os(servidor: str, banco: str, codigo: int) -> dict:
    return await asyncio.to_thread(_get_os_sync, servidor, banco, codigo)


async def save_os(req: OSSaveRequest, codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_os_sync, req, codigo)
