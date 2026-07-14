"""Rotas de Posto de Combustível > Movimentação de Encerrantes — ver
services/mov_encerrante_service.py (escopo Incluir/Alterar apenas, sem
Excluir — justificado no docstring do service)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, mov_encerrante_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class MovEncerranteSaveRequest(AuditFields):
    servidor: str
    banco: str
    data: str
    turno: int
    bomba: int
    funcionario: int
    contador_inicial: float
    contador_final: float
    afericao: float = 0


@router.get("/posto/mov-encerrantes/opcoes")
async def list_opcoes(servidor: str, banco: str):
    return await mov_encerrante_service.list_opcoes(servidor, banco)


@router.get("/posto/mov-encerrantes")
async def list_mov(servidor: str, banco: str, data: str):
    return await mov_encerrante_service.list_mov(servidor, banco, data)


@router.post("/posto/mov-encerrantes")
async def save_mov(req: MovEncerranteSaveRequest, request: Request):
    result = await mov_encerrante_service.save_mov(
        req.servidor, req.banco, req.data, req.turno, req.bomba, req.funcionario,
        req.contador_inicial, req.contador_final, req.afericao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_ENCERR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.data}-{req.turno}-{req.bomba}",
            descricao=(
                f"Encerrante da bomba {req.bomba} (turno {req.turno}, {req.data}) gravado: "
                f"inicial {req.contador_inicial}, final {req.contador_final}, aferição {req.afericao}."
            ),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
