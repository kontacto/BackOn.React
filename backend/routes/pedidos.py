"""Rotas de pedidos (cabeçalho) e seus itens."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import PedidosListRequest, PedidoSaveRequest, ItemSaveRequest, FecharRequest
from services import pedidos_service, itens_service, log_auditoria_service

router = APIRouter()

CAMPOS_PEDIDO = ["cliente", "vendedor", "validade", "obs", "area_atuacao"]
CAMPOS_ITEM = ["qtd_pedida", "p_normal", "desconto", "acrescimo", "descricao_produto"]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _depois_item(req: ItemSaveRequest) -> dict:
    return {
        "qtd_pedida": req.qtd, "p_normal": req.valor_unitario,
        "desconto": req.desconto, "acrescimo": req.acrescimo,
        "descricao_produto": req.complemento,
    }


def _depois_item_update(req: ItemSaveRequest) -> dict:
    """Como `_depois_item`, mas espelha o fallback de `_update_item_sync`
    (valor_unitario omitido vira 0, não o preço padrão do produto — diferente
    do fallback do ADD, que resolve via `_resolve_produto`)."""
    d = _depois_item(req)
    d["p_normal"] = float(req.valor_unitario or 0)
    return d


@router.post("/pedidos")
async def list_pedidos(req: PedidosListRequest):
    return await pedidos_service.list_pedidos(req)


@router.get("/pedidos/{pedido}")
async def get_pedido(pedido: int, servidor: str, banco: str):
    return await pedidos_service.get_pedido(servidor, banco, pedido)


@router.post("/pedidos/create")
async def create_pedido(req: PedidoSaveRequest, request: Request):
    result = await pedidos_service.save_pedido(req, None)
    if result.get("success"):
        pedido_id = result.get("pedido")
        campos = log_auditoria_service.diff_campos(None, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido_id), descricao=f"Pedido {pedido_id} criado",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedidos/{pedido}")
async def update_pedido(pedido: int, req: PedidoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda", "pedido", pedido)
    result = await pedidos_service.save_pedido(req, pedido)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} atualizado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/fechar")
async def fechar_pedido(pedido: int, req: FecharRequest, request: Request):
    result = await pedidos_service.fechar_pedido(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} fechado",
            campos_alterados=[{"campo": "situacao", "antes": "A", "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- itens do pedido ----------
@router.get("/pedidos/{pedido}/itens")
async def list_itens(pedido: int, servidor: str, banco: str):
    return await itens_service.list_itens(servidor, banco, pedido)


@router.post("/pedidos/{pedido}/itens")
async def add_item(pedido: int, req: ItemSaveRequest, request: Request):
    result = await itens_service.add_item(req, pedido)
    if result.get("success"):
        codauto = result.get("codauto")
        campos = log_auditoria_service.diff_campos(None, _depois_item(req), CAMPOS_ITEM)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="ADD_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=f"Item '{req.produto}' incluído no pedido {pedido} (cod {codauto})",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedidos/{pedido}/itens/{codauto}")
async def update_item(pedido: int, codauto: int, req: ItemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda_prod", "codauto", codauto)
    result = await itens_service.update_item(req, pedido, codauto)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, _depois_item_update(req), CAMPOS_ITEM)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="EDIT_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=f"Item {codauto} do pedido {pedido} alterado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/pedidos/{pedido}/itens/{codauto}")
async def delete_item(
    pedido: int, codauto: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    antes = await log_auditoria_service.get_row_by_pk(servidor, banco, "pedido_venda_prod", "codauto", codauto)
    result = await itens_service.delete_item(servidor, banco, pedido, codauto)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["produto", "qtd_pedida", "p_normal", "desconto", "acrescimo"])
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="PEDIDO", comando="DEL_ITEM",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(pedido), descricao=f"Item {codauto} excluído do pedido {pedido}",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=plataforma,
        )
    return result
