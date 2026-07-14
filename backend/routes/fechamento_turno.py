"""Rotas de Posto de Combustível > Fechamento de Turno — ver
services/fechamento_turno_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import fechamento_turno_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class FecharTurnoRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/fechamento-turno/status")
async def status(servidor: str, banco: str):
    return await fechamento_turno_service.status(servidor, banco)


@router.post("/posto/fechamento-turno/fechar")
async def fechar(req: FecharTurnoRequest, request: Request):
    result = await fechamento_turno_service.fechar(req.servidor, req.banco, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_FEC_TURNO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("turno_fechado")),
            descricao=result.get("message") or "Turno fechado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
