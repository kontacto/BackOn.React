"""Rotas de Posto de Combustível > Metas de Combustível — ver
services/combustivel_meta_service.py para o desenho completo (schema real,
chave composta, nota sobre FrmCadMeta.frm vs frmcadmet.frm).

Gravar/Excluir são registrados em `log_auditoria` (tela POSTO_META),
mesmo padrão de routes/produtos_compostos.py (chave composta, sem diff
campo-a-campo por não ter um único PK pra comparar "antes/depois")."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import combustivel_meta_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class MetaSaveRequest(AuditFields):
    servidor: str
    banco: str
    grupo: int
    ano: int
    mes: int
    meta: float = 0


class MetaDeleteRequest(AuditFields):
    servidor: str
    banco: str
    grupo: int
    ano: int
    mes: int


@router.get("/posto/combustivel-meta/grupos")
async def list_grupos(servidor: str, banco: str):
    return await combustivel_meta_service.list_grupos(servidor, banco)


@router.get("/posto/combustivel-meta")
async def list_metas(servidor: str, banco: str):
    return await combustivel_meta_service.list_metas(servidor, banco)


@router.post("/posto/combustivel-meta")
async def save_meta(req: MetaSaveRequest, request: Request):
    result = await combustivel_meta_service.save_meta(
        req.servidor, req.banco, req.grupo, req.ano, req.mes, req.meta,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_META", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.grupo}-{req.ano}-{req.mes}",
            descricao=f"Meta do grupo {req.grupo} ({req.mes}/{req.ano}) gravada: {req.meta}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/combustivel-meta/excluir")
async def delete_meta(req: MetaDeleteRequest, request: Request):
    result = await combustivel_meta_service.delete_meta(
        req.servidor, req.banco, req.grupo, req.ano, req.mes,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_META", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.grupo}-{req.ano}-{req.mes}",
            descricao=f"Meta do grupo {req.grupo} ({req.mes}/{req.ano}) excluída.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
