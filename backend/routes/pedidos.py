"""Rotas de pedidos (cabeçalho) e seus itens."""
from fastapi import APIRouter

from models.schemas import PedidosListRequest, PedidoSaveRequest, ItemSaveRequest
from services import pedidos_service, itens_service

router = APIRouter()


@router.post("/pedidos")
async def list_pedidos(req: PedidosListRequest):
    return await pedidos_service.list_pedidos(req)


@router.get("/pedidos/{pedido}")
async def get_pedido(pedido: int, servidor: str, banco: str):
    return await pedidos_service.get_pedido(servidor, banco, pedido)


@router.post("/pedidos/create")
async def create_pedido(req: PedidoSaveRequest):
    return await pedidos_service.save_pedido(req, None)


@router.put("/pedidos/{pedido}")
async def update_pedido(pedido: int, req: PedidoSaveRequest):
    return await pedidos_service.save_pedido(req, pedido)


# ---------- itens do pedido ----------
@router.get("/pedidos/{pedido}/itens")
async def list_itens(pedido: int, servidor: str, banco: str):
    return await itens_service.list_itens(servidor, banco, pedido)


@router.post("/pedidos/{pedido}/itens")
async def add_item(pedido: int, req: ItemSaveRequest):
    return await itens_service.add_item(req, pedido)


@router.put("/pedidos/{pedido}/itens/{codauto}")
async def update_item(pedido: int, codauto: int, req: ItemSaveRequest):
    return await itens_service.update_item(req, pedido, codauto)


@router.delete("/pedidos/{pedido}/itens/{codauto}")
async def delete_item(pedido: int, codauto: int, servidor: str, banco: str):
    return await itens_service.delete_item(servidor, banco, pedido, codauto)
