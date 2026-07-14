"""Rotas de Posto de Combustível > Tanques — ver services/tanque_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, tanque_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class TanqueSaveRequest(AuditFields):
    servidor: str
    banco: str
    tanque: int
    capacidade: int
    combustivel: int


class TanqueDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/tanques")
async def list_tanques(servidor: str, banco: str):
    return await tanque_service.list_tanques(servidor, banco)


@router.post("/posto/tanques")
async def save_tanque(req: TanqueSaveRequest, request: Request):
    result = await tanque_service.save_tanque(req.servidor, req.banco, req.tanque, req.capacidade, req.combustivel)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TANQUE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(req.tanque),
            descricao=f"Tanque {req.tanque} gravado (capacidade {req.capacidade}, combustível {req.combustivel}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/tanques/{tanque}/excluir")
async def delete_tanque(tanque: int, req: TanqueDeleteRequest, request: Request):
    result = await tanque_service.delete_tanque(req.servidor, req.banco, tanque)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TANQUE", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(tanque),
            descricao=f"Tanque {tanque} excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
