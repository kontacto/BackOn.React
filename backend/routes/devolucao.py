"""Rotas do Gestor de Devolução (migração de `Geral\\FrmManDev.frm`, Fase 1
enxuta — ver services/devolucao_service.py pro escopo completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    DevolucaoBuscarItensRequest, DevolucaoRegistrarRequest,
    DevolucaoConsultaRequest, DevolucaoCancelarRequest,
)
from services import devolucao_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/devolucao/motivos")
async def list_motivos(servidor: str, banco: str):
    return await devolucao_service.list_motivos(servidor, banco)


@router.post("/devolucao/buscar-itens")
async def buscar_itens(req: DevolucaoBuscarItensRequest):
    return await devolucao_service.list_itens_venda(req)


@router.post("/devolucao/registrar")
async def registrar_devolucao(req: DevolucaoRegistrarRequest, request: Request):
    result = await devolucao_service.registrar_devolucao(req)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="DEVOLUCAO", comando="REGISTRAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(i) for i in result.get("ids_devolucao", [])),
            descricao=f"{len(req.itens)} item(ns) devolvido(s), valor R$ {result.get('valor_total')}"
                      + (f", Vale de Devolução #{result.get('vale_devolucao')} emitido" if result.get("vale_devolucao") else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/devolucao/consulta")
async def consulta_devolucoes(req: DevolucaoConsultaRequest):
    return await devolucao_service.list_devolucoes(req)


@router.post("/devolucao/{id_devolucao}/cancelar")
async def cancelar_devolucao(id_devolucao: int, req: DevolucaoCancelarRequest, request: Request):
    result = await devolucao_service.cancelar_devolucao(req, id_devolucao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="DEVOLUCAO", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(id_devolucao), descricao=f"Devolução #{id_devolucao} cancelada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
