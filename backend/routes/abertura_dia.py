"""Rotas de Abertura do Dia (Gerencial > Abertura do Dia) — ver docstring
de `services/abertura_dia_service.py`."""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from services import abertura_dia_service

router = APIRouter()


class AbrirDiaRequest(BaseModel):
    servidor: str
    banco: str
    nova_data: str  # ISO yyyy-mm-dd
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    master: bool = False
    plataforma: Optional[str] = None
    confirma_retrocesso: bool = False


@router.get("/abertura-dia/status")
async def abertura_dia_status(servidor: str, banco: str):
    return await abertura_dia_service.status(servidor, banco)


@router.post("/abertura-dia/abrir")
async def abertura_dia_abrir(req: AbrirDiaRequest):
    return await abertura_dia_service.abrir_dia(
        req.servidor, req.banco, req.nova_data,
        req.usuario_alteracao, req.classe, req.master,
        req.plataforma, req.confirma_retrocesso,
    )
