"""Rotas de Cadastro/Consulta de NCM e CEST (tabela auxiliar fiscal).

Ver `services/ncm_cest_service.py` pro rastreio completo (fonte
`Geral\\FrmCesNCM.frm`) e as 2 correções conscientes em relação ao
legado (checagem de duplicata pelo PAR ncm+cest, "não encontrado" real
no delete de vínculo).
"""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, ncm_cest_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, tela: str, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela=tela, comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class NcmSaveRequest(AuditFields):
    servidor: str
    banco: str
    ncm: str
    descricao: str


class NcmCestSaveRequest(AuditFields):
    servidor: str
    banco: str
    ncm: Optional[str] = ""
    cest: str
    descricao: Optional[str] = ""


class NcmCestDeleteRequest(AuditFields):
    servidor: str
    banco: str
    ncm: Optional[str] = ""


# ==================== NCM ====================

@router.get("/ncm")
async def list_ncm(servidor: str, banco: str, search: str = ""):
    return await ncm_cest_service.list_ncm(servidor, banco, search)


@router.get("/ncm/{ncm}")
async def get_ncm(ncm: str, servidor: str, banco: str):
    return await ncm_cest_service.get_ncm(servidor, banco, ncm)


@router.post("/ncm")
async def save_ncm(req: NcmSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "ncm", "ncm", req.ncm)
    result = await ncm_cest_service.save_ncm(req.servidor, req.banco, req.ncm, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="NCM_CEST", comando="GRAVAR", referencia=req.ncm, descricao=f"NCM '{req.ncm}' gravado", campos=campos)
    return result


@router.post("/ncm/{ncm}/excluir")
async def delete_ncm(ncm: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "ncm", "ncm", ncm)
    result = await ncm_cest_service.delete_ncm(req.servidor, req.banco, ncm)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="NCM_CEST", comando="EXCLUIR", referencia=ncm, descricao=f"NCM '{ncm}' excluído", campos=campos)
    return result


# ==================== CEST (vínculo NCM_CEST) ====================

@router.get("/ncm-cest/buscar")
async def search_cest(servidor: str, banco: str, search: str = ""):
    return await ncm_cest_service.search_cest(servidor, banco, search)


@router.post("/ncm-cest")
async def save_ncm_cest(req: NcmCestSaveRequest, request: Request):
    result = await ncm_cest_service.save_ncm_cest(req.servidor, req.banco, req.ncm or "", req.cest, req.descricao or "")
    if result.get("success"):
        ref = f"{req.ncm or '(sem NCM)'} / {req.cest}"
        await _log(req, request, tela="NCM_CEST", comando="GRAVAR", referencia=ref, descricao=f"CEST '{req.cest}' vinculado ao NCM '{req.ncm or '(sem NCM)'}'")
    return result


@router.post("/ncm-cest/{cest}/excluir")
async def delete_ncm_cest(cest: str, req: NcmCestDeleteRequest, request: Request):
    result = await ncm_cest_service.delete_ncm_cest(req.servidor, req.banco, req.ncm or "", cest)
    if result.get("success"):
        ref = f"{req.ncm or '(sem NCM)'} / {cest}"
        await _log(req, request, tela="NCM_CEST", comando="EXCLUIR", referencia=ref, descricao=f"Vínculo CEST '{cest}' / NCM '{req.ncm or '(sem NCM)'}' excluído")
    return result
