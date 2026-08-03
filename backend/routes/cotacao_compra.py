"""Rotas de Cotação de Compra (Transações > Gestão de Compras > Compra) —
ver services/cotacao_compra_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.cotacao_compra import (
    CotacaoAcaoRequest,
    CotacaoItemExcluirRequest,
    CotacaoItemIncluirRequest,
    CotacaoRespostaExcluirRequest,
    CotacaoRespostaIncluirRequest,
)
from services import cotacao_compra_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/cotacoes-compra/produto/{codigo}")
async def find_produto(codigo: str, servidor: str, banco: str):
    return await cotacao_compra_service.find_produto(servidor, banco, codigo)


@router.get("/cotacoes-compra")
async def list_cotacoes(
    servidor: str, banco: str,
    situacao: Optional[str] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    descricao: Optional[str] = None,
):
    situacoes = [s for s in (situacao or "").split(",") if s]
    return await cotacao_compra_service.list_cotacoes(servidor, banco, situacoes, data_ini, data_fim, descricao)


@router.get("/cotacoes-compra/{codigo}")
async def get_cotacao(codigo: int, servidor: str, banco: str):
    return await cotacao_compra_service.get_cotacao(servidor, banco, codigo)


@router.post("/cotacoes-compra/itens")
async def incluir_item(req: CotacaoItemIncluirRequest, request: Request):
    result = await cotacao_compra_service.incluir_item(
        req.servidor, req.banco, req.codigo, req.descricao, req.produto, req.qtd, req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Item {req.produto} (qtd {req.qtd}) incluído na cotação {result.get('codigo')}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/itens/{cod_item}/excluir")
async def excluir_item(cod_item: int, req: CotacaoItemExcluirRequest, request: Request):
    result = await cotacao_compra_service.excluir_item(req.servidor, req.banco, cod_item)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_item),
            descricao=f"Item {cod_item} excluído da cotação.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/itens/{cod_item}/respostas")
async def incluir_resposta(cod_item: int, req: CotacaoRespostaIncluirRequest, request: Request):
    result = await cotacao_compra_service.incluir_resposta(
        req.servidor, req.banco, cod_item, req.fornecedor, req.valor_unit, req.marca, req.prazo, req.cond_pagamento,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_item),
            descricao=f"Resposta do fornecedor {req.fornecedor} lançada para o item {cod_item} (R$ {req.valor_unit}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/respostas/{cod_resposta}/excluir")
async def excluir_resposta(cod_resposta: int, req: CotacaoRespostaExcluirRequest, request: Request):
    result = await cotacao_compra_service.excluir_resposta(req.servidor, req.banco, cod_resposta)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_resposta),
            descricao=f"Resposta {cod_resposta} excluída da cotação.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/respostas/{cod_resposta}/marcar-vencedor")
async def marcar_vencedor(cod_resposta: int, req: CotacaoAcaoRequest, request: Request):
    result = await cotacao_compra_service.marcar_vencedor(req.servidor, req.banco, cod_resposta)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="VENCEDOR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_resposta),
            descricao=f"Resposta {cod_resposta} marcada como vencedora.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/{codigo}/finalizar")
async def finalizar_cotacao(codigo: int, req: CotacaoAcaoRequest, request: Request):
    result = await cotacao_compra_service.finalizar_cotacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="FINALIZAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Cotação {codigo} finalizada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/{codigo}/reabrir")
async def reabrir_cotacao(codigo: int, req: CotacaoAcaoRequest, request: Request):
    result = await cotacao_compra_service.reabrir_cotacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="REABRIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Cotação {codigo} reaberta.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cotacoes-compra/{codigo}/cancelar")
async def cancelar_cotacao(codigo: int, req: CotacaoAcaoRequest, request: Request):
    result = await cotacao_compra_service.cancelar_cotacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="COTACAO_COMPRA", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Cotação {codigo} cancelada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
