"""Pedidos (pedido_venda) — listagem, leitura e CRUD do cabeçalho."""
import asyncio
from typing import Optional

from db.connection import _open_conn
from models.schemas import PedidosListRequest, PedidoSaveRequest, FecharRequest
from services.constants import SITUACAO_LABEL
from services.pedido_common import _mover_estoque
from services.permissoes_service import tem_permissao


def _list_pedidos_sync(req: PedidosListRequest) -> dict:
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
                "(c.nome LIKE %s OR c.cgc_cpf LIKE %s OR p.NOME_CLIENTE LIKE %s "
                "OR p.TELEFONE_CLIENTE LIKE %s OR CAST(p.pedido AS NVARCHAR(20)) LIKE %s)"
            )
            params.extend([like, like, like, like, like])
        if req.situacao:
            where_parts.append("p.situacao = %s")
            params.append(req.situacao)
        if req.vendedor and str(req.vendedor).lower() != "all":
            where_parts.append("p.vendedor = %s")
            params.append(req.vendedor)
        if req.data_ini:
            where_parts.append("p.data >= %s")
            params.append(req.data_ini)
        if req.data_fim:
            where_parts.append("p.data <= %s")
            params.append(req.data_fim)
        where = ("WHERE " + " AND ".join(where_parts)) if where_parts else ""

        # Total
        cur.execute(
            f"SELECT COUNT(*) c FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente {where}",
            params,
        )
        total = int(cur.fetchone()["c"] or 0)

        offset = max(0, (req.page - 1) * req.size)
        cur.execute(
            f"SELECT p.pedido, p.data, p.validade, p.situacao, p.total, p.cliente, "
            f"       COALESCE(c.nome, p.NOME_CLIENTE) AS cliente_nome, "
            f"       p.vendedor, f.nome AS vendedor_nome, p.hora_aberto "
            f"FROM pedido_venda p "
            f"LEFT JOIN cliente c ON c.codigo = p.cliente "
            f"LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            f"{where} "
            f"ORDER BY p.pedido DESC OFFSET {offset} ROWS FETCH NEXT {req.size} ROWS ONLY",
            params,
        )
        items: list[dict] = []
        for r in cur.fetchall():
            sit = (r.get("situacao") or "").strip()
            items.append({
                "pedido": int(r["pedido"] or 0),
                "data": r["data"].isoformat() if r.get("data") else None,
                "validade": r["validade"].isoformat() if r.get("validade") else None,
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(r.get("total") or 0),
                "cliente": int(r["cliente"] or 0) if r.get("cliente") else None,
                "cliente_nome": (r.get("cliente_nome") or "").strip(),
                "vendedor": int(r["vendedor"] or 0) if r.get("vendedor") else None,
                "vendedor_nome": (r.get("vendedor_nome") or "").strip(),
                "hora_aberto": (r.get("hora_aberto") or "").strip(),
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


def _get_pedido_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT p.pedido, p.cliente, p.data, p.validade, p.vendedor, p.hora_aberto, "
            "       p.obs, p.situacao, p.total, p.NOME_CLIENTE, p.TELEFONE_CLIENTE, p.area_atuacao, "
            "       c.nome AS cliente_nome, c.cgc_cpf AS cliente_cgc, "
            "       f.nome AS vendedor_nome, a.descricao AS area_descricao "
            "FROM pedido_venda p "
            "LEFT JOIN cliente c ON c.codigo = p.cliente "
            "LEFT JOIN funcionarios f ON f.codigo_int = p.vendedor "
            "LEFT JOIN area_atuacao a ON a.area = p.area_atuacao "
            "WHERE p.pedido = %s",
            (pedido,),
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (row.get("situacao") or "").strip()
        return {
            "success": True,
            "pedido": {
                "pedido": int(row["pedido"] or 0),
                "cliente": int(row["cliente"] or 0) if row.get("cliente") else None,
                "cliente_nome": (row.get("cliente_nome") or row.get("NOME_CLIENTE") or "").strip(),
                "cliente_cgc": (row.get("cliente_cgc") or "").strip(),
                "data": row["data"].isoformat() if row.get("data") else None,
                "validade": row["validade"].isoformat() if row.get("validade") else None,
                "vendedor": int(row["vendedor"] or 0) if row.get("vendedor") else None,
                "vendedor_nome": (row.get("vendedor_nome") or "").strip(),
                "hora_aberto": (row.get("hora_aberto") or "").strip(),
                "obs": row.get("obs") or "",
                "situacao": sit,
                "situacao_label": SITUACAO_LABEL.get(sit, sit),
                "total": float(row.get("total") or 0),
                "area_atuacao": int(row["area_atuacao"]) if row.get("area_atuacao") is not None else None,
                "area_descricao": (row.get("area_descricao") or "").strip(),
            },
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}"}


def _save_pedido_sync(req: PedidoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)

        # Se for update, verifica situação — só pedido em 'A' (Aberto) pode ser editado.
        if pedido_codigo is not None:
            cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido_codigo,))
            ex = cur.fetchone()
            if not ex:
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            sit_atual = (ex.get("situacao") or "").strip().upper()
            if sit_atual != "A":
                conn.close()
                label = SITUACAO_LABEL.get(sit_atual, sit_atual)
                return {"success": False, "message": f"Pedido com situação '{label}' não pode ser alterado."}
        # Busca o nome e telefone do cliente para denormalizar em NOME_CLIENTE / TELEFONE_CLIENTE
        cur.execute(
            "SELECT TOP 1 c.nome, "
            "  COALESCE((SELECT TOP 1 LTRIM(RTRIM(CAST(ddd AS NVARCHAR(4))) + tel) "
            "            FROM cliente_tel WHERE codigo=c.codigo ORDER BY sequencia), "
            "           LTRIM(RTRIM(CAST(c.ddd_cli AS NVARCHAR(4))) + ISNULL(c.telefone_cli,''))) AS tel "
            "FROM cliente c WHERE c.codigo = %s",
            (req.cliente,),
        )
        cli_row = cur.fetchone() or {}
        nome_cli = (cli_row.get("nome") or "").strip()[:60]
        tel_cli = (cli_row.get("tel") or "").strip()[:60]

        validade = req.validade or None
        obs = req.obs or ""

        if pedido_codigo is None:
            # pedido é IDENTITY — deixar o SQL gerar e retornar via OUTPUT INSERTED.pedido
            cur.execute(
                "INSERT INTO pedido_venda "
                "(cliente, data, validade, vendedor, hora_aberto, obs, situacao, "
                " NOME_CLIENTE, TELEFONE_CLIENTE, abertopor, total, tipo, area_atuacao) "
                "OUTPUT INSERTED.pedido "
                "VALUES (%s, CAST(GETDATE() AS DATE), %s, %s, "
                "        CONVERT(NVARCHAR(8), GETDATE(), 108), %s, 'A', %s, %s, %s, 0, 0, %s)",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, req.vendedor, req.area_atuacao),
            )
            row = cur.fetchone()
            if not row:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Falha ao obter número do pedido."}
            pedido_id = int(row["pedido"] if isinstance(row, dict) else row[0])
        else:
            # Update apenas dos campos editáveis (não mexe em situacao aqui).
            cur.execute(
                "UPDATE pedido_venda SET "
                " cliente=%s, validade=%s, vendedor=%s, obs=%s, "
                " NOME_CLIENTE=%s, TELEFONE_CLIENTE=%s, area_atuacao=%s "
                "WHERE pedido=%s",
                (req.cliente, validade, req.vendedor, obs, nome_cli, tel_cli, req.area_atuacao, pedido_codigo),
            )
            if cur.rowcount == 0:
                conn.rollback()
                conn.close()
                return {"success": False, "message": "Pedido não encontrado."}
            pedido_id = pedido_codigo
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "pedido": pedido_id}
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


async def list_pedidos(req: PedidosListRequest) -> dict:
    return await asyncio.to_thread(_list_pedidos_sync, req)


async def get_pedido(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_get_pedido_sync, servidor, banco, pedido)


async def save_pedido(req: PedidoSaveRequest, pedido_codigo: Optional[int]) -> dict:
    return await asyncio.to_thread(_save_pedido_sync, req, pedido_codigo)


def _fechar_pedido_sync(req: FecharRequest, pedido: int) -> dict:
    """Fecha o Pedido (situação A -> F). Valida itens e permissão e baixa o
    estoque das PEÇAS (qtd -= q ; reservado += q). Serviços não movem estoque.
    Tudo numa única transação."""
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT situacao FROM pedido_venda WHERE pedido=%s", (pedido,))
        ex = cur.fetchone()
        if not ex:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        sit = (ex.get("situacao") or "").strip().upper()
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser fechado."}
        # Permissão (master ignora)
        if not req.master and req.classe is not None and not tem_permissao(cur, req.classe, "PEDIDO", "SITUACAO"):
            conn.close()
            return {"success": False, "message": "Sem permissão para fechar o pedido."}
        # Pelo menos 1 item (produto OU serviço)
        cur.execute(
            "SELECT produto, qtd_pedida FROM pedido_venda_prod "
            "WHERE pedido=%s AND ISNULL(item_cancelado,0)=0",
            (pedido,),
        )
        itens = cur.fetchall()
        if not itens:
            conn.close()
            return {"success": False, "message": "Inclua pelo menos um produto ou serviço antes de fechar."}
        # Baixa de estoque (somente peças)
        for it in itens:
            _mover_estoque(cur, (it.get("produto") or "").strip(), float(it.get("qtd_pedida") or 0), "reservado")
        cur.execute("UPDATE pedido_venda SET situacao='F' WHERE pedido=%s", (pedido,))
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "message": "Pré-venda Fechada.", "situacao": "F"}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao fechar: {e}"}


async def fechar_pedido(req: FecharRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_fechar_pedido_sync, req, pedido)
