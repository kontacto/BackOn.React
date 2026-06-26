"""Rotas de Ordem de Serviço (cabeçalho `os`) e seus itens (`os_produto`)."""
from fastapi import APIRouter

from models.schemas import OSListRequest, OSSaveRequest, OSItemSaveRequest, DescontoGeralRequest, FecharRequest
from services import os_service, os_itens_service

router = APIRouter()


@router.post("/os")
async def list_os(req: OSListRequest):
    return await os_service.list_os(req)


@router.get("/os/{codigo}")
async def get_os(codigo: int, servidor: str, banco: str):
    return await os_service.get_os(servidor, banco, codigo)


@router.post("/os/create")
async def create_os(req: OSSaveRequest):
    return await os_service.save_os(req, None)


@router.put("/os/{codigo}")
async def update_os(codigo: int, req: OSSaveRequest):
    return await os_service.save_os(req, codigo)


@router.post("/os/{codigo}/fechar")
async def fechar_os(codigo: int, req: FecharRequest):
    return await os_service.fechar_os(req, codigo)


# ---------- itens da OS ----------
@router.get("/os/{codigo}/itens")
async def list_itens(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_itens(servidor, banco, codigo)


@router.post("/os/{codigo}/itens")
async def add_item(codigo: int, req: OSItemSaveRequest):
    return await os_itens_service.add_item(req, codigo)


@router.put("/os/{codigo}/itens/{cod_os_prod}")
async def update_item(codigo: int, cod_os_prod: int, req: OSItemSaveRequest):
    return await os_itens_service.update_item(req, codigo, cod_os_prod)


@router.delete("/os/{codigo}/itens/{cod_os_prod}")
async def delete_item(codigo: int, cod_os_prod: int, servidor: str, banco: str):
    return await os_itens_service.delete_item(servidor, banco, codigo, cod_os_prod)


@router.get("/os/{codigo}/descontos")
async def list_descontos(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_descontos(servidor, banco, codigo)


@router.get("/os/{codigo}/analise")
async def analise(codigo: int, servidor: str, banco: str):
    return await os_itens_service.analise(servidor, banco, codigo)


@router.post("/os/{codigo}/desconto-geral")
async def desconto_geral(codigo: int, req: DescontoGeralRequest):
    return await os_itens_service.aplicar_desconto_geral(req, codigo)
