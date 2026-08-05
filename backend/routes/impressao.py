"""Rotas de impressão de rede + fila de impressão pra impressoras USB locais
(polling do agente `print-agent/agente_impressao.py` — ver
services/impressao_service.py para o escopo completo)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import impressao_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ImpressaoRedeRequest(AuditFields):
    servidor: str
    banco: str
    ip: str
    porta: int = impressao_service.DEFAULT_PORT
    conteudo: str


@router.post("/impressao/rede")
async def enviar_impressao_rede(req: ImpressaoRedeRequest, request: Request):
    result = await impressao_service.enviar_rede(req.ip, req.porta, req.conteudo)
    # Best-effort, mesmo padrão dos outros endpoints deste domínio — nunca
    # impede a operação de imprimir.
    try:
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="IMPRESSAO", comando="IMPRIMIR_REDE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.ip}:{req.porta}",
            descricao=f"Impressão enviada para {req.ip}:{req.porta}" if result.get("success")
            else f"Falha ao imprimir em {req.ip}:{req.porta}: {result.get('message')}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    except Exception:
        pass
    return result


class ImpressaoFilaEnfileirarRequest(AuditFields):
    servidor: str
    banco: str
    computador: str
    impressora: Optional[str] = None
    conteudo: str
    tipo: str = "TEXTO"


class ImpressaoFilaConfirmarRequest(BaseModel):
    servidor: str
    banco: str
    sucesso: bool
    mensagem_erro: Optional[str] = None


@router.post("/impressao/fila")
async def enfileirar_impressao(req: ImpressaoFilaEnfileirarRequest, request: Request):
    """Chamado por qualquer tela (ex.: Checkout) pra pedir uma impressão
    silenciosa — o agente rodando no `computador` informado busca e
    processa por polling (`GET /impressao/fila/pendentes`)."""
    result = await impressao_service.enfileirar(
        req.servidor, req.banco, req.computador, req.impressora, req.conteudo, req.tipo,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="IMPRESSAO", comando="ENFILEIRAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("id")),
            descricao=f"Impressão enfileirada pro computador '{req.computador}'"
                      f"{f' (impressora {req.impressora})' if req.impressora else ''}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/impressao/fila/pendentes")
async def list_impressao_pendentes(servidor: str, banco: str, computador: str):
    """Chamado pelo agente local (polling) — nunca por uma tela do app."""
    return await impressao_service.list_pendentes(servidor, banco, computador)


@router.post("/impressao/fila/{job_id}/confirmar")
async def confirmar_impressao(job_id: int, req: ImpressaoFilaConfirmarRequest):
    """Chamado pelo agente local depois de tentar imprimir — marca o job
    como IMPRESSO ou ERRO (nunca por uma tela do app)."""
    return await impressao_service.confirmar(req.servidor, req.banco, job_id, req.sucesso, req.mensagem_erro)
