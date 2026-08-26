"""Rotas do Gestor NFSe (Sefin Nacional/DPS, migração de
`Geral\\FrmManNSeSefin.frm`). Ver `services/gestor_nfse_service.py` pro
racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.gestor_nfse import ListarNfseRequest, NfseBaixarDanfeRequest, NfseConsultarRequest, NfseEnviarEmailRequest
from services import gestor_nfse_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/gestor-nfse")
async def listar_nfse(req: ListarNfseRequest):
    return await gestor_nfse_service.list_nfse(
        req.servidor, req.banco,
        data_de=req.data_de, data_ate=req.data_ate, comanda=req.comanda, cliente=req.cliente,
        classe=req.classe, master=bool(req.master),
    )


@router.post("/gestor-nfse/consultar")
async def consultar_situacao(req: NfseConsultarRequest, request: Request):
    result = await gestor_nfse_service.consultar_situacao(
        req.servidor, req.banco, codigos=req.codigos, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFSE", comando="CONSULTAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.codigos), descricao=f"NFS-e consultada(s) — {req.codigos}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestor-nfse/danfe")
async def baixar_danfe(req: NfseBaixarDanfeRequest):
    return await gestor_nfse_service.baixar_danfe(req.servidor, req.banco, req.codigo, classe=req.classe, master=bool(req.master))


@router.post("/gestor-nfse/enviar-email")
async def enviar_email(req: NfseEnviarEmailRequest, request: Request):
    result = await gestor_nfse_service.enviar_email(
        req.servidor, req.banco, codigos=req.codigos, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_NFSE", comando="CONSULTAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.codigos), descricao=f"NFS-e enviada(s) por e-mail — {req.codigos}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
