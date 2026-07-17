"""Rotas de relatórios e dashboard."""
from typing import Optional

from fastapi import APIRouter

from services import relatorios_service, fechamento_caixa_service, caixa_analitico_service

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


@router.get("/relatorios/os")
async def relatorio_os(servidor: str, banco: str, data_ini: str, data_fim: str,
                       vendedor: Optional[str] = None, situacao: Optional[str] = None):
    return await relatorios_service.relatorio_os(servidor, banco, data_ini, data_fim, vendedor, situacao)


@router.get("/relatorios/os/descontos-margem")
async def relatorio_os_descontos_margem(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[str] = None, os_cod: Optional[int] = None,
    cliente_nome: Optional[str] = None,
):
    return await relatorios_service.relatorio_os_desc_margem(
        servidor, banco, data_ini, data_fim, vendedor, os_cod, cliente_nome
    )


@router.get("/relatorios/caixa")
async def relatorio_caixa(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    atendente: Optional[int] = None, filtrar_atendente_dav: bool = False,
    area: Optional[int] = None, exibir_garantias: bool = False,
):
    return await fechamento_caixa_service.fechamento_caixa(
        servidor, banco, data_ini, data_fim, atendente, filtrar_atendente_dav, area, exibir_garantias,
    )


@router.get("/relatorios/caixa-analitico")
async def relatorio_caixa_analitico(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    agrupamento: str = "diario", dias_semana: Optional[str] = None,
):
    # dias_semana chega como CSV ("0,1,2,3,4,5,6") — querystring simples, sem
    # precisar de múltiplos parâmetros repetidos nem de um body em GET.
    dias = [int(x) for x in dias_semana.split(",") if x.strip() != ""] if dias_semana else None
    return await caixa_analitico_service.caixa_analitico(servidor, banco, data_ini, data_fim, agrupamento, dias)
