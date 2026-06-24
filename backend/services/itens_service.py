"""Itens do Pedido (pedido_venda_prod) — listagem e CRUD.

Relacionamentos:
  pedido_venda.pedido = pedido_venda_prod.pedido
  pedido_venda_prod.produto = pecas.codigo_int  (produto)  -> tipo 'P'
  pedido_venda_prod.produto = servicos.codigo    (serviço)  -> tipo 'S'
Política: só pedido com situacao='A' (Aberto) permite CRUD de itens.
Total do item = qtd_pedida * p_venda - desconto + acrescimo
pedido_venda.total = SUM dos itens não cancelados.
"""
import asyncio

from db.connection import _open_conn
from models.schemas import ItemSaveRequest
from services.constants import SITUACAO_LABEL
from services.descontos_service import _validar_limite_desconto, _log_desconto_item
from services.pedido_common import (
    _item_total, _recalc_pedido_total, _check_pedido_aberto, _resolve_produto,
)


def _list_itens_sync(servidor: str, banco: str, pedido: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": [], "subtotal": 0}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado.", "items": [], "subtotal": 0}
        cur.execute(
            "SELECT i.codauto, i.produto, i.qtd_pedida, i.p_venda, i.p_normal, i.desconto, i.acrescimo, "
            "       i.descricao_produto, i.unidade_pedido, "
            "       pe.descricao AS peca_desc, pe.codigo_fab AS peca_fab, "
            "       sv.descricao AS serv_desc "
            "FROM pedido_venda_prod i "
            "LEFT JOIN pecas pe ON pe.codigo_int = i.produto "
            "LEFT JOIN servicos sv ON sv.codigo = i.produto "
            "WHERE i.pedido = %s AND ISNULL(i.item_cancelado,0) = 0 "
            "ORDER BY i.codauto",
            (pedido,),
        )
        items = []
        subtotal = 0.0
        for r in cur.fetchall():
            is_peca = r.get("peca_desc") is not None
            tipo = "P" if is_peca else ("S" if r.get("serv_desc") is not None else "?")
            base_desc = (r.get("peca_desc") if is_peca else r.get("serv_desc")) or ""
            complemento = (r.get("descricao_produto") or "").strip()
            qtd = float(r.get("qtd_pedida") or 0)
            pv = float(r.get("p_venda") or 0)
            pnorm = float(r.get("p_normal") or 0)
            desc = float(r.get("desconto") or 0)
            acr = float(r.get("acrescimo") or 0)
            tot = _item_total(qtd, pv)
            subtotal += tot
            items.append({
                "codauto": int(r["codauto"]),
                "produto": (r.get("produto") or "").strip(),
                "tipo": tipo,
                "descricao": base_desc.strip(),
                "complemento": complemento,
                "cod_fab": (r.get("peca_fab") or r.get("produto") or "").strip(),
                "unidade": (r.get("unidade_pedido") or "").strip(),
                "qtd": qtd,
                "p_normal": pnorm,
                "valor_unitario": pv,
                "desconto": desc,
                "acrescimo": acr,
                "total": tot,
            })
        cur.close()
        conn.close()
        return {
            "success": True,
            "items": items,
            "subtotal": round(subtotal, 2),
            "situacao": sit,
            "editavel": sit == "A",
        }
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": [], "subtotal": 0}


def _add_item_sync(req: ItemSaveRequest, pedido: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        codigo = (req.produto or "").strip()
        if not codigo:
            conn.close()
            return {"success": False, "message": "Produto/serviço obrigatório."}
        prod = _resolve_produto(cur, codigo)
        if not prod:
            conn.close()
            return {"success": False, "message": f"Produto/serviço '{codigo}' não encontrado."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        # valor_unitario = p_normal (preço base/tabela no momento). desconto/acrescimo são UNITÁRIOS.
        p_normal = req.valor_unitario if req.valor_unitario is not None else prod["valor"]
        p_normal = float(p_normal or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()
        unidade = prod["unidade"]
        custo = float(prod.get("custo") or 0)  # pecas.custo_reposicao no momento da venda
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}

        cur.execute(
            "INSERT INTO pedido_venda_prod "
            "(pedido, produto, qtd_pedida, p_venda, p_normal, desconto, acrescimo, custo_ped, "
            " descricao_produto, unidade_pedido, situacao_item, item_cancelado, data_inclusao_item) "
            "OUTPUT INSERTED.codauto "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'A',0,CAST(GETDATE() AS DATE))",
            (pedido, codigo, qtd, p_venda, p_normal, desc, acr, custo, complemento, unidade),
        )
        row = cur.fetchone()
        codauto = int(row["codauto"] if isinstance(row, dict) else row[0])
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "codauto": codauto, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao adicionar item: {e}"}


def _update_item_sync(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    try:
        conn = _open_conn(req.servidor, req.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}

        qtd = float(req.qtd or 0)
        if qtd <= 0:
            conn.close()
            return {"success": False, "message": "Quantidade deve ser maior que zero."}
        # valor_unitario = p_normal (preço base). desconto/acrescimo são UNITÁRIOS.
        p_normal = float(req.valor_unitario or 0)
        desc = float(req.desconto or 0)
        acr = float(req.acrescimo or 0)
        # Defesa em profundidade: valida limite de desconto por função (master ignora)
        lim_err = _validar_limite_desconto(cur, req.funcao, req.usuario_codigo, p_normal, desc, float(req.desconto_pct or 0))
        if lim_err:
            conn.close()
            return {"success": False, "message": lim_err}
        p_venda = round(p_normal - desc + acr, 4)  # preço líquido unitário
        complemento = (req.complemento or "").strip()

        cur.execute(
            "UPDATE pedido_venda_prod SET "
            " qtd_pedida=%s, p_normal=%s, p_venda=%s, desconto=%s, acrescimo=%s, "
            " descricao_produto=%s, data_alteracao_item=CAST(GETDATE() AS DATE) "
            "WHERE codauto=%s AND pedido=%s",
            (qtd, p_normal, p_venda, desc, acr, complemento, codauto, pedido),
        )
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        _log_desconto_item(cur, pedido, codauto, float(req.desconto_pct or 0), desc, req.usuario_codigo or -2)
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao atualizar item: {e}"}


def _delete_item_sync(servidor: str, banco: str, pedido: int, codauto: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor(as_dict=True)
        existe, sit = _check_pedido_aberto(cur, pedido)
        if not existe:
            conn.close()
            return {"success": False, "message": "Pedido não encontrado."}
        if sit != "A":
            conn.close()
            return {"success": False, "message": f"Pedido '{SITUACAO_LABEL.get(sit, sit)}' não pode ser alterado."}
        cur.execute("DELETE FROM pedido_venda_prod WHERE codauto=%s AND pedido=%s", (codauto, pedido))
        if cur.rowcount == 0:
            conn.rollback(); conn.close()
            return {"success": False, "message": "Item não encontrado."}
        cur.execute(
            "DELETE FROM descontos_concedidos "
            "WHERE TIPO='PED' AND CODIGO=%s AND CODIGO_PRODUTO=%s AND TIPO_DESCONTO='I'",
            (pedido, codauto),
        )
        novo_total = _recalc_pedido_total(cur, pedido)
        conn.commit()
        cur.close()
        conn.close()
        return {"success": True, "total": novo_total}
    except Exception as e:
        try:
            conn.rollback(); conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao remover item: {e}"}


async def list_itens(servidor: str, banco: str, pedido: int) -> dict:
    return await asyncio.to_thread(_list_itens_sync, servidor, banco, pedido)


async def add_item(req: ItemSaveRequest, pedido: int) -> dict:
    return await asyncio.to_thread(_add_item_sync, req, pedido)


async def update_item(req: ItemSaveRequest, pedido: int, codauto: int) -> dict:
    return await asyncio.to_thread(_update_item_sync, req, pedido, codauto)


async def delete_item(servidor: str, banco: str, pedido: int, codauto: int) -> dict:
    return await asyncio.to_thread(_delete_item_sync, servidor, banco, pedido, codauto)
