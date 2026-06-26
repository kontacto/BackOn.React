"""Rotas de Tabelas Auxiliares: Marcas, Modelos e import FIPE."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services import tabelas_aux_service

router = APIRouter()


class MarcaSaveRequest(BaseModel):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str
    marca_produto: bool = False


class ModeloSaveRequest(BaseModel):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    cod_marca: str
    descricao: str


class DeleteRequest(BaseModel):
    servidor: str
    banco: str


class ImportFipeRequest(BaseModel):
    servidor: str
    banco: str
    tipo: str = "carros"
    fipe_marca_id: str
    descricao: str


@router.get("/tabelas/marcas")
async def list_marcas(servidor: str, banco: str, marca_produto: Optional[bool] = None, search: str = ""):
    return await tabelas_aux_service.list_marcas(servidor, banco, marca_produto, search)


@router.post("/tabelas/marcas")
async def save_marca(req: MarcaSaveRequest):
    return await tabelas_aux_service.save_marca(req.servidor, req.banco, req.codigo, req.descricao, req.marca_produto)


@router.post("/tabelas/marcas/{codigo}/excluir")
async def delete_marca(codigo: str, req: DeleteRequest):
    return await tabelas_aux_service.delete_marca(req.servidor, req.banco, codigo)


@router.get("/tabelas/modelos")
async def list_modelos(servidor: str, banco: str, cod_marca: Optional[str] = None, search: str = ""):
    return await tabelas_aux_service.list_modelos(servidor, banco, cod_marca, search)


@router.post("/tabelas/modelos")
async def save_modelo(req: ModeloSaveRequest):
    return await tabelas_aux_service.save_modelo(req.servidor, req.banco, req.codigo, req.cod_marca, req.descricao)


@router.post("/tabelas/modelos/{codigo}/excluir")
async def delete_modelo(codigo: str, req: DeleteRequest):
    return await tabelas_aux_service.delete_modelo(req.servidor, req.banco, codigo)


@router.get("/fipe/marcas")
async def fipe_marcas(tipo: str = "carros"):
    return await tabelas_aux_service.fipe_marcas(tipo)


@router.get("/fipe/modelos")
async def fipe_modelos(tipo: str, marca_id: str):
    return await tabelas_aux_service.fipe_modelos(tipo, marca_id)


@router.post("/tabelas/marcas/importar-fipe")
async def import_fipe(req: ImportFipeRequest):
    return await tabelas_aux_service.import_fipe(req.servidor, req.banco, req.tipo, req.fipe_marca_id, req.descricao)
