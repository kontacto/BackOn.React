"""Rotas de Curva ABC e Estoques — ver services/curva_abc_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.curva_abc import GerarCurvaRequest, ReprocessarEstoquesRequest
from services import curva_abc_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/curva-abc/gerar")
async def gerar_curva(req: GerarCurvaRequest, request: Request):
    faixas = [f.model_dump() for f in req.faixas]
    result = await curva_abc_service.gerar_curva(
        req.servidor, req.banco, req.data_ini, req.data_fim, req.tipo, faixas, req.nivel,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CURVA_ABC", comando="GERAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao=f"Curva ABC ({req.tipo}) gerada para {result.get('total_itens')} produto(s), período {req.data_ini} a {req.data_fim}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/curva-abc/reprocessar-estoques")
async def reprocessar_estoques(req: ReprocessarEstoquesRequest, request: Request):
    result = await curva_abc_service.reprocessar_estoques(
        req.servidor, req.banco, req.data_ini, req.data_fim, req.grau_atendimento, req.nivel,
        req.atualizar_minimo, req.atualizar_ressuprimento, req.atualizar_maximo, req.atualizar_consumo,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CURVA_ABC", comando="REPROCESSAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao=f"Reprocessamento de estoques para {len(result.get('items', []))} produto(s), período {req.data_ini} a {req.data_fim}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
