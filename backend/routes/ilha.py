"""Rotas de Posto de Combustível > Ilhas — ver services/ilha_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import ilha_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class IlhaSaveRequest(AuditFields):
    servidor: str
    banco: str
    data: str
    ilha: int
    turno: int
    funcionario: int


class IlhaDeleteRequest(AuditFields):
    servidor: str
    banco: str
    data: str
    ilha: int
    turno: int


@router.get("/posto/ilhas/opcoes")
async def list_opcoes(servidor: str, banco: str):
    return await ilha_service.list_opcoes(servidor, banco)


@router.get("/posto/ilhas")
async def list_ilhas(servidor: str, banco: str, data: str):
    return await ilha_service.list_ilhas(servidor, banco, data)


@router.post("/posto/ilhas")
async def save_ilha(req: IlhaSaveRequest, request: Request):
    result = await ilha_service.save_ilha(req.servidor, req.banco, req.data, req.ilha, req.turno, req.funcionario)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_ILHA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.data}-{req.ilha}-{req.turno}",
            descricao=f"Ilha {req.ilha}/turno {req.turno} ({req.data}) atribuída ao funcionário {req.funcionario}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/ilhas/excluir")
async def delete_ilha(req: IlhaDeleteRequest, request: Request):
    result = await ilha_service.delete_ilha(req.servidor, req.banco, req.data, req.ilha, req.turno)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_ILHA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.data}-{req.ilha}-{req.turno}",
            descricao=f"Ilha {req.ilha}/turno {req.turno} ({req.data}) excluída.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
