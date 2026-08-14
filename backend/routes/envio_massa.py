"""Rotas de Envio em Massa (WhatsApp/E-mail) — recurso reutilizável, ver
docstring de `services/envio_massa_service.py`. Não é exclusivo de nenhuma
tela — Mala Direta e Inatividade de Clientes chamam hoje, outras telas
(ex.: Consulta de Clientes) podem chamar no futuro sem mudança aqui."""
from fastapi import APIRouter
from pydantic import BaseModel

from services import envio_massa_service, log_auditoria_service

router = APIRouter()


class Destinatario(BaseModel):
    codigo: int
    nome: str
    email: str | None = None


class EnvioWhatsappRequest(BaseModel):
    servidor: str
    banco: str
    destinatarios: list[Destinatario]
    mensagem: str
    usuario: int | None = None
    classe: int | None = None


class EnvioEmailRequest(BaseModel):
    servidor: str
    banco: str
    destinatarios: list[Destinatario]
    assunto: str
    corpo: str
    usuario: int | None = None
    classe: int | None = None


@router.post("/envio-massa/whatsapp")
async def enviar_whatsapp_massa(req: EnvioWhatsappRequest):
    r = await envio_massa_service.enviar_whatsapp_massa(
        req.servidor, req.banco, [d.dict() for d in req.destinatarios], req.mensagem, req.usuario
    )
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="ENVIO_MASSA", comando="WHATSAPP",
        usuario=req.usuario, classe=req.classe,
        descricao=f"{r['totais']['enviados']} enviado(s), {r['totais']['falhas']} falha(s) de {r['totais']['total']}",
    )
    return r


@router.post("/envio-massa/email")
async def enviar_email_massa(req: EnvioEmailRequest):
    r = await envio_massa_service.enviar_email_massa(
        req.servidor, req.banco, [d.dict() for d in req.destinatarios], req.assunto, req.corpo
    )
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="ENVIO_MASSA", comando="EMAIL",
        usuario=req.usuario, classe=req.classe,
        descricao=f"{r['totais']['enviados']} enviado(s), {r['totais']['falhas']} falha(s) de {r['totais']['total']}",
    )
    return r
