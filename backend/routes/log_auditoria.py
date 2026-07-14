"""Rotas do Log de Auditoria — ver services/log_auditoria_service.py."""
from typing import Optional

from fastapi import APIRouter

from services import log_auditoria_service

router = APIRouter()


@router.get("/log-auditoria")
async def listar(
    servidor: str, banco: str,
    tela: Optional[str] = None,
    comando: Optional[str] = None,
    usuario: Optional[int] = None,
    data_de: Optional[str] = None,
    data_ate: Optional[str] = None,
    referencia: Optional[str] = None,
    descricao_like: Optional[str] = None,
    page: int = 1,
    size: int = 40,
    classe: Optional[int] = None,
    master: bool = False,
):
    return await log_auditoria_service.list_logs(
        servidor, banco,
        tela=tela, comando=comando, usuario=usuario, data_de=data_de, data_ate=data_ate,
        referencia=referencia, descricao_like=descricao_like, page=page, size=size,
        classe=classe, master=master,
    )
