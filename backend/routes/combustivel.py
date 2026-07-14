"""Rotas de Posto de Combustível > Combustíveis — ver
services/combustivel_service.py para o desenho completo (campos fora de
escopo desta fase, justificados no docstring do service)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import combustivel_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class CombustivelDados(BaseModel):
    descricao: str
    venda: float
    venda2: Optional[float] = 0
    codigo_automacao: Optional[int] = None
    indImport: Optional[str] = None
    cUFOrig: Optional[str] = None
    pOrig: Optional[float] = 0


class CombustivelSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    dados: CombustivelDados


class CombustivelDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/combustiveis")
async def list_combustiveis(servidor: str, banco: str):
    return await combustivel_service.list_combustiveis(servidor, banco)


@router.get("/posto/combustiveis/{codigo}")
async def get_combustivel(codigo: int, servidor: str, banco: str):
    return await combustivel_service.get_combustivel(servidor, banco, codigo)


@router.post("/posto/combustiveis")
async def save_combustivel(req: CombustivelSaveRequest, request: Request):
    result = await combustivel_service.save_combustivel(req.servidor, req.banco, req.codigo, req.dados.dict())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_COMBUST", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(req.codigo),
            descricao=f"Combustível {req.codigo} ('{req.dados.descricao}') gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/combustiveis/{codigo}/excluir")
async def delete_combustivel(codigo: int, req: CombustivelDeleteRequest, request: Request):
    result = await combustivel_service.delete_combustivel(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_COMBUST", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Combustível {codigo} excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
