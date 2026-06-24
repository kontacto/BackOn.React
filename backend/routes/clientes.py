"""Rotas de clientes (listagem, busca, resumo, tipo e CRUD)."""
from fastapi import APIRouter

from models.schemas import ClientesRequest, ClienteCreateRequest, ClienteSaveRequest
from services import clientes_service

router = APIRouter()


@router.post("/clientes")
async def list_clientes(req: ClientesRequest):
    return await clientes_service.list_clientes(req)


@router.get("/tipo-cliente")
async def list_tipo_cliente(servidor: str, banco: str):
    return await clientes_service.list_tipo_cliente(servidor, banco)


@router.get("/clientes/find/by-cgc")
async def find_cliente_by_cgc(servidor: str, banco: str, cgc: str):
    return await clientes_service.find_by_cgc(servidor, banco, cgc)


@router.get("/clientes/find/search")
async def find_clientes_search(servidor: str, banco: str, term: str = ""):
    return await clientes_service.find_clientes_search(servidor, banco, term)


@router.get("/clientes/{codigo}/resumo")
async def get_cliente_resumo(codigo: int, servidor: str, banco: str):
    return await clientes_service.cliente_resumo(servidor, banco, codigo)


@router.get("/clientes/{codigo}")
async def get_cliente(codigo: int, servidor: str, banco: str):
    return await clientes_service.get_cliente(servidor, banco, codigo)


@router.post("/clientes/create")
async def create_cliente(req: ClienteCreateRequest):
    base = ClienteSaveRequest(**req.dict(exclude={"endereco", "telefones"}))
    return await clientes_service.save_cliente(base, req.endereco, req.telefones, None)


@router.put("/clientes/{codigo}")
async def update_cliente(codigo: int, req: ClienteCreateRequest):
    base = ClienteSaveRequest(**req.dict(exclude={"endereco", "telefones"}))
    return await clientes_service.save_cliente(base, req.endereco, req.telefones, codigo)
