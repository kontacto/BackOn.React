"""Rotas do Checkout (venda direta de balcão — migração de FrmPafOFF.frm)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    CheckoutAbrirRequest, CheckoutItemRequest, CheckoutCancelarItemRequest,
    CheckoutDescontoGeralRequest, CheckoutClienteRequest, CheckoutFecharRequest,
    CheckoutCancelarVendaRequest, CheckoutImportarDavRequest,
)
from services import checkout_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/checkout/abrir")
async def abrir_venda(req: CheckoutAbrirRequest, request: Request):
    result = await checkout_service.abrir_venda(req)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="ABRIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("comanda")), descricao=f"Venda direta {result.get('comanda')} aberta",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/checkout/produto")
async def buscar_produto(codigo: str, servidor: str, banco: str, qtd: float = 1):
    return await checkout_service.buscar_produto(servidor, banco, codigo, qtd)


@router.get("/checkout/cartoes/administradoras")
async def list_administradoras(servidor: str, banco: str):
    return await checkout_service.list_administradoras(servidor, banco)


@router.get("/checkout/cartoes/parcelas")
async def list_parcelas(servidor: str, banco: str, administradora: int, bandeira: str, parcelador: str):
    return await checkout_service.list_parcelas(servidor, banco, administradora, bandeira, parcelador)


@router.get("/checkout/{comanda}")
async def get_venda(comanda: int, servidor: str, banco: str):
    return await checkout_service.get_venda(servidor, banco, comanda)


@router.post("/checkout/{comanda}/itens")
async def add_item(comanda: int, req: CheckoutItemRequest, request: Request):
    result = await checkout_service.add_item(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="ADD_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Item {req.codigo} (qtd {req.qtd}) incluído na venda {comanda}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/checkout/{comanda}/itens/{id_mov}")
async def cancelar_item(comanda: int, id_mov: int, req: CheckoutCancelarItemRequest, request: Request):
    result = await checkout_service.cancelar_item(req, comanda, id_mov)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="DEL_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Item {id_mov} cancelado na venda {comanda}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/checkout/{comanda}/importar-dav")
async def importar_dav(comanda: int, req: CheckoutImportarDavRequest, request: Request):
    result = await checkout_service.importar_dav(req, comanda)
    if result.get("success"):
        tipo_label = "Pedido" if req.tipo_dav.upper() == "PED" else "O.S."
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="ADD_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda),
            descricao=f"{tipo_label} #{req.documento} importado ({result.get('itens_importados')} item(ns)) na venda {comanda}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/checkout/{comanda}/desconto-geral")
async def desconto_geral(comanda: int, req: CheckoutDescontoGeralRequest, request: Request):
    result = await checkout_service.desconto_geral(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="DESC_GERAL",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Desconto geral de {req.desconto_percentual}% aplicado na venda {comanda}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/checkout/{comanda}/cliente")
async def definir_cliente(comanda: int, req: CheckoutClienteRequest, request: Request):
    return await checkout_service.definir_cliente(req, comanda)


@router.post("/checkout/{comanda}/fechar")
async def fechar_venda(comanda: int, req: CheckoutFecharRequest, request: Request):
    result = await checkout_service.fechar_venda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="FECHAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda),
            descricao=f"Venda {comanda} fechada — total pago R$ {result.get('total_pago')}, troco R$ {result.get('troco')}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/checkout/{comanda}/cancelar")
async def cancelar_venda(comanda: int, req: CheckoutCancelarVendaRequest, request: Request):
    result = await checkout_service.cancelar_venda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CHECKOUT", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Venda {comanda} cancelada" + (f" — {req.motivo}" if req.motivo else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
