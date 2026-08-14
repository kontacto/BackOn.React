"""Rotas da tela "IA Key" (Configurações > Administração, master-only) —
ver `services/ia_config_service.py`."""
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Request

from services import ia_config_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class IAKeySaveRequest(BaseModel):
    servidor: str
    banco: str
    api_key: str
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


@router.get("/ia-config")
async def get_ia_config(servidor: str, banco: str):
    return await ia_config_service.get_status(servidor, banco)


@router.post("/ia-config")
async def save_ia_config(req: IAKeySaveRequest, request: Request):
    result = await ia_config_service.save(req.servidor, req.banco, req.api_key)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="IA_CONFIG", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=None, descricao="Chave de API da Anthropic (IA Key) atualizada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
