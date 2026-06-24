"""Rotas de relatórios e dashboard."""
from typing import Optional

from fastapi import APIRouter

from services import relatorios_service

router = APIRouter()


@router.get("/relatorios/pedidos")
async def relatorio_pedidos(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str] = None, situacao: Optional[str] = None):
    return await relatorios_service.relatorio_pedidos(servidor, banco, data_ini, data_fim, vendedor, situacao)


@router.get("/relatorios/descontos-margem")
async def relatorio_descontos_margem(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[str] = None, pedido: Optional[int] = None,
    cliente_nome: Optional[str] = None,
):
    return await relatorios_service.relatorio_desc_margem(
        servidor, banco, data_ini, data_fim, vendedor, pedido, cliente_nome
    )


@router.get("/dashboard/me")
async def dashboard_me(servidor: str, banco: str, vendedor: Optional[str] = None,
                       data: Optional[str] = None, situacao: Optional[str] = None):
    return await relatorios_service.dashboard_me(servidor, banco, vendedor, data, situacao)
