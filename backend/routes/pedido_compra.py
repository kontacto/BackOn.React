"""Rotas de Pedido de Compra (Transações > Gestão de Compras > Compra) —
ver services/pedido_compra_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.pedido_compra import (
    PedidoAcaoRequest,
    PedidoCabecalhoRequest,
    PedidoItemEditarRequest,
    PedidoItemExcluirRequest,
    PedidoItemIncluirRequest,
)
from services import log_auditoria_service, pedido_compra_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/pedidos-compra/produto/{codigo}")
async def find_produto(codigo: str, servidor: str, banco: str):
    return await pedido_compra_service.find_produto(servidor, banco, codigo)


@router.get("/pedidos-compra/fornecedor/{codigo_int}")
async def find_fornecedor_info(codigo_int: int, servidor: str, banco: str):
    return await pedido_compra_service.find_fornecedor_info(servidor, banco, codigo_int)


@router.get("/pedidos-compra")
async def list_pedidos(
    servidor: str, banco: str,
    situacao: Optional[str] = None, fornecedor: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None, termo: Optional[str] = None,
):
    situacoes = [s for s in (situacao or "").split(",") if s]
    return await pedido_compra_service.list_pedidos(servidor, banco, situacoes, fornecedor, data_ini, data_fim, termo)


@router.get("/pedidos-compra/{codigo}")
async def get_pedido(codigo: int, servidor: str, banco: str):
    return await pedido_compra_service.get_pedido(servidor, banco, codigo)


@router.post("/pedidos-compra")
async def gravar_cabecalho(req: PedidoCabecalhoRequest, request: Request):
    result = await pedido_compra_service.gravar_cabecalho(
        req.servidor, req.banco, req.codigo, req.data, req.fornecedor, req.pedido_fornecedor, req.prazo,
        req.forma_pagamento, req.ac_cliente, req.transportadora, req.data_entrega, req.obs_pedido,
        req.tipo_frete, req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(result.get("codigo")),
            descricao=f"Pedido de compra {result.get('codigo')} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/{codigo}/itens")
async def incluir_item(codigo: int, req: PedidoItemIncluirRequest, request: Request):
    result = await pedido_compra_service.incluir_item(
        req.servidor, req.banco, codigo, req.produto, req.qtd, req.p_unit, req.fiscal.model_dump(),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Item {req.produto} (qtd {req.qtd}) incluído no pedido de compra {codigo}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/itens/{seq}/editar")
async def editar_item(seq: int, req: PedidoItemEditarRequest, request: Request):
    result = await pedido_compra_service.editar_item(
        req.servidor, req.banco, seq, req.qtd, req.p_unit, req.fiscal.model_dump(),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(seq),
            descricao=f"Item {seq} do pedido de compra atualizado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/itens/{seq}/excluir")
async def excluir_item(seq: int, req: PedidoItemExcluirRequest, request: Request):
    result = await pedido_compra_service.excluir_item(req.servidor, req.banco, seq)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(seq),
            descricao=f"Item {seq} excluído do pedido de compra.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/{codigo}/aprovar")
async def aprovar(codigo: int, req: PedidoAcaoRequest, request: Request):
    result = await pedido_compra_service.aprovar(req.servidor, req.banco, codigo, None)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="APROVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Pedido de compra {codigo} aprovado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/{codigo}/rejeitar")
async def rejeitar(codigo: int, req: PedidoAcaoRequest, request: Request):
    result = await pedido_compra_service.rejeitar(req.servidor, req.banco, codigo, None)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="REJEITAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Pedido de compra {codigo} rejeitado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos-compra/{codigo}/reabrir")
async def reabrir(codigo: int, req: PedidoAcaoRequest, request: Request):
    result = await pedido_compra_service.reabrir(req.servidor, req.banco, codigo, None)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="REABRIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Pedido de compra {codigo} reaberto.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
