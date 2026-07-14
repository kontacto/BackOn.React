"""Rotas de Posto de Combustível > Tanque/Estoque — ver
services/tanque_estoque_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, tanque_estoque_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class TanqueEstoqueSaveRequest(AuditFields):
    servidor: str
    banco: str
    tanque: int
    data: str
    estoque: int


class TanqueEstoqueDeleteRequest(AuditFields):
    servidor: str
    banco: str
    tanque: int
    data: str


@router.get("/posto/tanque-estoque")
async def list_tanque_estoque(servidor: str, banco: str, tanque: Optional[int] = None):
    return await tanque_estoque_service.list_tanque_estoque(servidor, banco, tanque)


@router.post("/posto/tanque-estoque")
async def save_tanque_estoque(req: TanqueEstoqueSaveRequest, request: Request):
    result = await tanque_estoque_service.save_tanque_estoque(req.servidor, req.banco, req.tanque, req.data, req.estoque)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TQ_EST", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=f"{req.tanque}-{req.data}",
            descricao=f"Estoque do tanque {req.tanque} em {req.data} gravado: {req.estoque}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/tanque-estoque/excluir")
async def delete_tanque_estoque(req: TanqueEstoqueDeleteRequest, request: Request):
    result = await tanque_estoque_service.delete_tanque_estoque(req.servidor, req.banco, req.tanque, req.data)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TQ_EST", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=f"{req.tanque}-{req.data}",
            descricao=f"Estoque do tanque {req.tanque} em {req.data} excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
