"""Rotas de descontos (listagem e desconto geral)."""
from fastapi import APIRouter

from models.schemas import DescontoGeralRequest
from services import descontos_service

router = APIRouter()


@router.get("/pedidos/{pedido}/descontos")
async def list_descontos(pedido: int, servidor: str, banco: str):
    return await descontos_service.list_descontos(servidor, banco, pedido)


@router.post("/pedidos/{pedido}/desconto-geral")
async def aplicar_desconto_geral(pedido: int, req: DescontoGeralRequest):
    return await descontos_service.aplicar_desconto_geral(req, pedido)
