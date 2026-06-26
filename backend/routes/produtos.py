"""Rotas de produtos/serviços + foto do produto."""
import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from services import produtos_service

router = APIRouter()

# Foto do produto — procura em pasta configurável (env FOTOS_PRODUTOS_DIR).
# Default: /app/fotos_produtos (Linux) ou C:\desenv\fotos_produtos (Windows).
# Aceita extensões: .jpg, .jpeg, .png, .webp. Nome do arquivo = codigo_int.
_FOTOS_DIR = os.environ.get("FOTOS_PRODUTOS_DIR", "/app/fotos_produtos")


@router.get("/produtos-servicos")
async def list_produtos_servicos(
    servidor: str,
    banco: str,
    search: str = "",
    page: int = 1,
    size: int = 40,
    tipo: str = "all",
):
    return await produtos_service.list_produtos_servicos(servidor, banco, search, page, size, tipo)


@router.get("/produtos/{codigo}/reservas")
async def produto_reservas(codigo: str, servidor: str, banco: str, tipo: str = "PED"):
    return await produtos_service.reservas_produto(servidor, banco, codigo, tipo)


@router.get("/produtos/foto/{codigo}")
async def get_produto_foto(codigo: str):
    # Sanitiza pra evitar path traversal
    safe = "".join(c for c in codigo if c.isalnum() or c in "-_")
    if not safe:
        return Response(status_code=204)
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        path = os.path.join(_FOTOS_DIR, f"{safe}{ext}")
        if os.path.exists(path):
            return FileResponse(path)
    # 204 No Content quando não tem foto (frontend mostra placeholder)
    return Response(status_code=204)
