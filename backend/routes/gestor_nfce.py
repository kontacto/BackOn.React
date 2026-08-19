"""Rotas do Gestor NFCe + Contingência NFCe (migração de `FrmTraNFC.frm` +
mínimo de `FrmConNFC.frm`). Ver `services/gestor_nfce_service.py`/
`services/contingencia_nfce_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.gestor_nfce import (
    ContingenciaAbrirRequest, ContingenciaFecharRequest, ListarNfceRequest, NfceAcaoLoteRequest, NfceInutilizarRequest,
)
from services import contingencia_nfce_service, gestor_nfce_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/gestor-nfce")
async def listar_nfce(req: ListarNfceRequest):
    return await gestor_nfce_service.list_nfce(
        req.servidor, req.banco,
        data_venda_de=req.data_venda_de, data_venda_ate=req.data_venda_ate,
        data_nfce_de=req.data_nfce_de, data_nfce_ate=req.data_nfce_ate,
        comanda=req.comanda, num_nfce=req.num_nfce, cliente=req.cliente,
        situacoes=req.situacoes, incluir_sem_nfce=req.incluir_sem_nfce, somente_gaps=req.somente_gaps,
        classe=req.classe, master=bool(req.master),
    )


@router.post("/gestor-nfce/cancelar")
async def cancelar_nfce(req: NfceAcaoLoteRequest, request: Request):
    result = await gestor_nfce_service.cancelar_nfce(
        req.servidor, req.banco, req.comandas, req.motivo or "", classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.comandas),
            descricao=f"NFC-e cancelada — comandas {req.comandas}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestor-nfce/consultar")
async def consultar_situacao(req: NfceAcaoLoteRequest):
    return await gestor_nfce_service.consultar_situacao(
        req.servidor, req.banco, req.comandas, classe=req.classe, master=bool(req.master),
    )


@router.post("/gestor-nfce/inutilizar")
async def inutilizar_faixa(req: NfceInutilizarRequest, request: Request):
    result = await gestor_nfce_service.inutilizar_faixa(
        req.servidor, req.banco, req.numeros, req.serie, req.motivo,
        usuario=req.usuario_alteracao, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="INUTILIZAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"série {req.serie}", descricao=f"Números inutilizados: {req.numeros} — motivo: {req.motivo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestor-nfce/retransmitir")
async def retransmitir(req: NfceAcaoLoteRequest, request: Request):
    result = await gestor_nfce_service.retransmitir(
        req.servidor, req.banco, req.comandas, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="RETRANSMITIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.comandas), descricao=f"NFC-e retransmitida — comandas {req.comandas}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestor-nfce/validar-contingencia")
async def validar_contingencia(req: NfceAcaoLoteRequest, request: Request):
    result = await gestor_nfce_service.validar_contingencia(
        req.servidor, req.banco, req.comandas, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="VALIDAR_CONT",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.comandas),
            descricao=f"Contingência validada/transmitida — comandas {req.comandas}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/gestor-nfce/{comanda}/xml")
async def gerar_xml(comanda: int, servidor: str, banco: str, classe: Optional[int] = None, master: bool = False):
    return await gestor_nfce_service.gerar_xml(servidor, banco, comanda, classe=classe, master=master)


@router.get("/contingencia-nfce/status")
async def status_contingencia(servidor: str, banco: str):
    return await contingencia_nfce_service.status_contingencia(servidor, banco)


@router.post("/contingencia-nfce/abrir")
async def abrir_contingencia(req: ContingenciaAbrirRequest, request: Request):
    result = await contingencia_nfce_service.abrir_contingencia(
        req.servidor, req.banco, req.motivo, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="CONTINGENCIA",
            usuario=req.usuario_alteracao, classe=req.classe, descricao=f"Contingência NFCe aberta — motivo: {req.motivo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contingencia-nfce/fechar")
async def fechar_contingencia(req: ContingenciaFecharRequest, request: Request):
    result = await contingencia_nfce_service.fechar_contingencia(
        req.servidor, req.banco, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFCE", comando="CONTINGENCIA",
            usuario=req.usuario_alteracao, classe=req.classe, descricao="Contingência NFCe fechada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
