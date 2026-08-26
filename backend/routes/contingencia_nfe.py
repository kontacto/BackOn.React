"""Rotas de Contingência NFe (migração de `Geral\\FrmConNFe.frm`). Ver
`services/contingencia_nfe_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.contingencia_nfe import (
    ContingenciaNfeAbrirRequest, ContingenciaNfeFecharRequest, ContingenciaNfeValidarRequest,
)
from services import contingencia_nfe_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contingencia-nfe/status")
async def status_contingencia(servidor: str, banco: str):
    return await contingencia_nfe_service.status_contingencia(servidor, banco)


@router.post("/contingencia-nfe/abrir")
async def abrir_contingencia(req: ContingenciaNfeAbrirRequest, request: Request):
    result = await contingencia_nfe_service.abrir_contingencia(
        req.servidor, req.banco, req.motivo, req.tipo_contingencia, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONT_NFE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao=f"Contingência NFe aberta — tipo {req.tipo_contingencia} — motivo: {req.motivo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contingencia-nfe/fechar")
async def fechar_contingencia(req: ContingenciaNfeFecharRequest, request: Request):
    result = await contingencia_nfe_service.fechar_contingencia(
        req.servidor, req.banco, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONT_NFE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, descricao="Contingência NFe fechada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contingencia-nfe/pendentes")
async def listar_pendentes(servidor: str, banco: str):
    return await contingencia_nfe_service.listar_pendentes(servidor, banco)


@router.post("/contingencia-nfe/validar")
async def validar_pendentes(req: ContingenciaNfeValidarRequest, request: Request):
    result = await contingencia_nfe_service.validar_pendentes(
        req.servidor, req.banco, notas=req.notas, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONT_NFE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao=f"Contingência NFe validada — notas {req.notas}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
