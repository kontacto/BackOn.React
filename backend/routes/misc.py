"""Rotas diversas: raiz, status (Mongo legado) e download de arquivos (dev)."""
from typing import List

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from db import mongo
from models.schemas import StatusCheck, StatusCheckCreate

router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Back-On API ativo"}


@router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.dict())
    if mongo._MONGO_ENABLED:
        await mongo.db.status_checks.insert_one(status_obj.dict())
    return status_obj


@router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    if not mongo._MONGO_ENABLED:
        return []
    docs = await mongo.db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**d) for d in docs]


# =====================================================================
# DOWNLOAD TEMPORÁRIO — remover após sincronizar com GitHub
# =====================================================================
_DEV_FILES = {
    "server.py": "/app/backend/server.py",
    "requirements-windows.txt": "/app/backend/requirements-windows.txt",
    "clientes.tsx": "/app/frontend/app/clientes.tsx",
    "cliente-form.tsx": "/app/frontend/app/cliente-form.tsx",
    "principal.tsx": "/app/frontend/app/principal.tsx",
    "produtos.tsx": "/app/frontend/app/produtos.tsx",
    "pedidos.tsx": "/app/frontend/app/pedidos.tsx",
    "pedido-form.tsx": "/app/frontend/app/pedido-form.tsx",
}

_DEV_FILES_2 = {
    "server.py": "/app/backend/server.py",
    "clientes.tsx": "/app/frontend/app/clientes.tsx",
    "pedido-form.tsx": "/app/frontend/app/pedido-form.tsx",
    "pedidos.tsx": "/app/frontend/app/pedidos.tsx",
}


@router.get("/dev/file")
async def dev_file(name: str):
    path = _DEV_FILES.get(name)
    if not path:
        return PlainTextResponse(
            f"# arquivo não disponível: {name}\n# válidos: {list(_DEV_FILES.keys())}",
            status_code=404,
        )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    except Exception as e:
        return PlainTextResponse(f"# erro: {e}", status_code=500)


@router.get("/dev/file2")
async def dev_file2(name: str):
    path = _DEV_FILES_2.get(name)
    if not path:
        return PlainTextResponse(f"# nao encontrado: {name}", status_code=404)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return PlainTextResponse(f.read())
    except Exception as e:
        return PlainTextResponse(f"# erro: {e}", status_code=500)
