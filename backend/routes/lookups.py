"""Rotas de lookups (área de atuação e funcionários)."""
from fastapi import APIRouter

from services import lookups_service

router = APIRouter()


@router.get("/area-atuacao")
async def list_area_atuacao(servidor: str, banco: str):
    return await lookups_service.list_area_atuacao(servidor, banco)


@router.get("/funcionarios")
async def list_funcionarios(servidor: str, banco: str):
    return await lookups_service.list_funcionarios(servidor, banco)
