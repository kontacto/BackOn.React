"""Rotas do Gestor de Comandas / Alterar Comandas (migração de
`FrmConCupom.frm`/`FrmAltComNV.frm`). Ver `services/comanda_service.py`
pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.comanda import (
    ComandaAddNumSerieRequest, ComandaAlterarFormaPagamentoRequest, ComandaAlterarVendedorItemRequest,
    ComandaCancelarRequest, ComandaGravarRequest, EmitirNfceRequest, EmitirNfseRequest, ListarComandasRequest,
)
from services import comanda_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/comandas")
async def list_comandas(req: ListarComandasRequest):
    return await comanda_service.list_comandas(req)


@router.get("/comandas/{comanda}/doc-fiscal")
async def get_doc_fiscal(comanda: int, servidor: str, banco: str):
    return await comanda_service.get_doc_fiscal(servidor, banco, comanda)


@router.get("/comandas/{comanda}")
async def get_comanda(comanda: int, servidor: str, banco: str):
    return await comanda_service.get_comanda(servidor, banco, comanda)


@router.put("/comandas/{comanda}")
async def save_comanda(comanda: int, req: ComandaGravarRequest, request: Request):
    result = await comanda_service.save_comanda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Comanda {comanda} alterada (atendente/vendedor/cliente)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/comandas/{comanda}/itens/{id_mov}/vendedor")
async def alterar_vendedor_item(comanda: int, id_mov: int, req: ComandaAlterarVendedorItemRequest, request: Request):
    req.id_mov = id_mov
    result = await comanda_service.alterar_vendedor_item(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Comanda {comanda}: vendedor do item {id_mov} alterado para {req.vendedor}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/comandas/{comanda}/forma-pagamento/{sequencia}")
async def alterar_forma_pagamento(comanda: int, sequencia: int, req: ComandaAlterarFormaPagamentoRequest, request: Request):
    req.sequencia = sequencia
    result = await comanda_service.alterar_forma_pagamento(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="FORMA_PAG",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda),
            descricao=f"Comanda {comanda}: forma de pagamento #{sequencia} ({req.tipo}) alterada para {req.forma_pag_nova}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/comandas/{comanda}/num-serie")
async def list_num_serie_comanda(comanda: int, servidor: str, banco: str):
    return await comanda_service.list_num_serie_comanda(servidor, banco, comanda)


@router.post("/comandas/{comanda}/num-serie")
async def add_num_serie_comanda(comanda: int, req: ComandaAddNumSerieRequest, request: Request):
    result = await comanda_service.add_num_serie_comanda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="NUM_SERIE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Comanda {comanda}: número de série (código {req.codigo}) vinculado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/comandas/{comanda}/num-serie/{sequencia}")
async def remove_num_serie_comanda(
    comanda: int, sequencia: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
    master: bool = False,
):
    result = await comanda_service.remove_num_serie_comanda(servidor, banco, comanda, sequencia, master, classe)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="ALTERAR_COMANDA", comando="NUM_SERIE",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(comanda), descricao=f"Comanda {comanda}: vínculo de número de série #{sequencia} removido",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.post("/comandas/{comanda}/cancelar")
async def cancelar_comanda(comanda: int, req: ComandaCancelarRequest, request: Request):
    result = await comanda_service.cancelar_comanda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda), descricao=f"Comanda {comanda} cancelada — motivo: {req.motivo}",
            campos_alterados=[{"campo": "situacao", "depois": "C"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/comandas/{comanda}/emitir-nfce")
async def emitir_nfce_comanda(comanda: int, req: EmitirNfceRequest, request: Request):
    result = await comanda_service.emitir_nfce_comanda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="EMITIR_NF",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda),
            descricao=f"Comanda {comanda}: NFC-e emitida (protocolo {result.get('protocolo_sefaz')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/comandas/{comanda}/emitir-nfse")
async def emitir_nfse_comanda(comanda: int, req: EmitirNfseRequest, request: Request):
    result = await comanda_service.emitir_nfse_comanda(req, comanda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALTERAR_COMANDA", comando="EMITIR_NFSE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(comanda),
            descricao=f"Comanda {comanda}: NFS-e emitida (chave {result.get('chave_acesso')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
