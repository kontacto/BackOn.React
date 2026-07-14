"""Rotas de impressão de rede (esboço — ver services/impressao_service.py
para o escopo atual e o que ainda falta)."""
from typing import Optional

from fastapi import APIRouter, Request

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
