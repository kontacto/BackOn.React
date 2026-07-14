"""Rotas de descontos (listagem e desconto geral)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import DescontoGeralRequest
from services import descontos_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/pedidos/{pedido}/descontos")
async def list_descontos(pedido: int, servidor: str, banco: str):
    return await descontos_service.list_descontos(servidor, banco, pedido)


@router.post("/pedidos/{pedido}/desconto-geral")
async def aplicar_desconto_geral(pedido: int, req: DescontoGeralRequest, request: Request):
    result = await descontos_service.aplicar_desconto_geral(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="DESC_GERAL",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Desconto geral de R$ {req.valor:.2f} aplicado no pedido {pedido} ({result.get('percentual', 0):g}%)",
            campos_alterados=[{"campo": "desconto_geral", "depois": f"{req.valor:.2f}"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
