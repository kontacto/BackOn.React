"""Rotas de controle (limites de desconto e dados da empresa)."""
from fastapi import APIRouter

from services import controle_service

router = APIRouter()


@router.get("/controle/desconto-limites")
async def desconto_limites(servidor: str, banco: str):
    return await controle_service.get_limites(servidor, banco)


@router.get("/controle/empresa")
async def controle_empresa(servidor: str, banco: str):
    return await controle_service.get_empresa(servidor, banco)


@router.get("/controle/mensagens-pdv")
async def controle_mensagens_pdv(servidor: str, banco: str):
    return await controle_service.get_mensagens_pdv(servidor, banco)
