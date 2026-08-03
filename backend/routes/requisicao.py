"""Rotas de Requisição (Transações > Movimentações) — ver
services/requisicao_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.requisicao import (
    RequisicaoAcaoRequest,
    RequisicaoItemExcluirRequest,
    RequisicaoItemIncluirRequest,
)
from services import log_auditoria_service, requisicao_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/requisicoes/produto/{codigo}")
async def find_item(codigo: str, servidor: str, banco: str):
    return await requisicao_service.find_item(servidor, banco, codigo)


@router.get("/requisicoes")
async def list_requisicoes(
    servidor: str, banco: str,
    situacao: Optional[str] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None, usuario: Optional[str] = None,
    produto: Optional[str] = None,
):
    # `situacao` chega como string única separada por vírgula (ex.: "A,F,C"
    # — ver frontend, `filtroSituacoes.join(",")`), não como múltiplos
    # parâmetros repetidos — o util `apiGet`/`connQS` do frontend só
    # suporta um valor por chave na querystring.
    situacoes = [s for s in (situacao or "").split(",") if s]
    return await requisicao_service.list_requisicoes(
        servidor, banco, situacoes, data_ini, data_fim, descricao, usuario, produto
    )


@router.get("/requisicoes/{codigo}")
async def get_requisicao(codigo: int, servidor: str, banco: str):
    return await requisicao_service.get_requisicao(servidor, banco, codigo)


@router.post("/requisicoes/itens")
async def incluir_item(req: RequisicaoItemIncluirRequest, request: Request):
    result = await requisicao_service.incluir_item(
        req.servidor, req.banco, req.codigo, req.descricao, req.produto, req.qtd, req.p_unit,
        req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="REQUISICAO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Item {req.produto} (qtd {req.qtd}) incluído na requisição {result.get('codigo')}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/requisicoes/itens/{cod_item}/excluir")
async def excluir_item(cod_item: int, req: RequisicaoItemExcluirRequest, request: Request):
    result = await requisicao_service.excluir_item(req.servidor, req.banco, cod_item)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="REQUISICAO", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_item),
            descricao=f"Item {cod_item} excluído da requisição.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/requisicoes/{codigo}/fechar")
async def fechar_requisicao(codigo: int, req: RequisicaoAcaoRequest, request: Request):
    result = await requisicao_service.fechar_requisicao(req.servidor, req.banco, codigo, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="REQUISICAO", comando="FECHAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Requisição {codigo} fechada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/requisicoes/{codigo}/reabrir")
async def reabrir_requisicao(codigo: int, req: RequisicaoAcaoRequest, request: Request):
    result = await requisicao_service.reabrir_requisicao(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="REQUISICAO", comando="REABRIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Requisição {codigo} reaberta.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/requisicoes/{codigo}/cancelar")
async def cancelar_requisicao(codigo: int, req: RequisicaoAcaoRequest, request: Request):
    result = await requisicao_service.cancelar_requisicao(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="REQUISICAO", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Requisição {codigo} cancelada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
