"""Rotas de Posto de Combustível > Estoque de Combustível — ver
services/estoque_combustivel_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import estoque_combustivel_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class EstoqueSaveRequest(AuditFields):
    servidor: str
    banco: str
    combustivel: int
    data: str
    turno: int
    venda: float
    venda2: float = 0


class EstoqueDeleteRequest(AuditFields):
    servidor: str
    banco: str
    combustivel: int
    data: str
    turno: int


@router.get("/posto/estoque-combustivel")
async def list_estoque(servidor: str, banco: str, combustivel: Optional[int] = None, data: Optional[str] = None):
    return await estoque_combustivel_service.list_estoque(servidor, banco, combustivel, data)


@router.post("/posto/estoque-combustivel")
async def save_estoque(req: EstoqueSaveRequest, request: Request):
    result = await estoque_combustivel_service.save_estoque(
        req.servidor, req.banco, req.combustivel, req.data, req.turno, req.venda, req.venda2,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_ESTOQUE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.combustivel}-{req.data}-{req.turno}",
            descricao=f"Estoque do combustível {req.combustivel} em {req.data} (turno {req.turno}) gravado: venda {req.venda}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/estoque-combustivel/excluir")
async def delete_estoque(req: EstoqueDeleteRequest, request: Request):
    result = await estoque_combustivel_service.delete_estoque(req.servidor, req.banco, req.combustivel, req.data, req.turno)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_ESTOQUE", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.combustivel}-{req.data}-{req.turno}",
            descricao=f"Estoque do combustível {req.combustivel} em {req.data} (turno {req.turno}) excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
