"""Rotas de Posto de Combustível > Reabertura de Turno — ver
services/reabertura_turno_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, reabertura_turno_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ReabrirTurnoRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/reabertura-turno/preview")
async def preview(servidor: str, banco: str):
    return await reabertura_turno_service.preview(servidor, banco)


@router.post("/posto/reabertura-turno/reabrir")
async def reabrir(req: ReabrirTurnoRequest, request: Request):
    result = await reabertura_turno_service.reabrir(req.servidor, req.banco)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_REA_TURNO", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("turno_reaberto")),
            descricao=result.get("message") or "Turno reaberto.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
