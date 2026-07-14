"""Rotas de "Alterações Cadastro de Produtos Níveis" — ver produtos_niveis_service.py."""
from fastapi import APIRouter, Request

from models.produtos_niveis import (
    DesativarEstoqueRequest,
    GravarCamposRequest,
    LeiTransparenciaRequest,
    PreviewRequest,
    ReajustePrecoRequest,
    ReprocessarItemRequest,
    ReprocessarReservadosRequest,
)
from services import produtos_niveis_service

router = APIRouter(prefix="/produtos-niveis")


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.post("/preview")
async def preview(req: PreviewRequest):
    return await produtos_niveis_service.preview(req)


@router.post("/preview-itens")
async def preview_itens(req: PreviewRequest):
    return await produtos_niveis_service.preview_itens(req)


@router.post("/gravar-campos")
async def gravar_campos(req: GravarCamposRequest, request: Request):
    return await produtos_niveis_service.gravar_campos(req, _ip(request))


@router.post("/reajustar-preco")
async def reajustar_preco(req: ReajustePrecoRequest, request: Request):
    return await produtos_niveis_service.reajustar_preco(req, _ip(request))


@router.post("/lei-transparencia")
async def lei_transparencia(req: LeiTransparenciaRequest, request: Request):
    return await produtos_niveis_service.lei_transparencia(req, _ip(request))


@router.post("/desativar-estoque-negativo")
async def desativar_estoque_negativo(req: DesativarEstoqueRequest, request: Request):
    return await produtos_niveis_service.desativar_estoque_negativo(req, _ip(request))


@router.post("/desativar-estoque-zerado")
async def desativar_estoque_zerado(req: DesativarEstoqueRequest, request: Request):
    return await produtos_niveis_service.desativar_estoque_zerado(req, _ip(request))


@router.post("/reprocessar-item")
async def reprocessar_item(req: ReprocessarItemRequest, request: Request):
    return await produtos_niveis_service.reprocessar_item(req, _ip(request))


@router.post("/reprocessar-reservados")
async def reprocessar_reservados(req: ReprocessarReservadosRequest, request: Request):
    return await produtos_niveis_service.reprocessar_reservados(req, _ip(request))
