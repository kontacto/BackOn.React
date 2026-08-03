"""Rotas de Envio de Equipamentos para Terceiros (`retifica`) — ver
`services/retifica_service.py` pro rastreio completo da migração de
`FrmManRet.frm`. Toda gravação registrada em log_auditoria (tela="RETIFICA").
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import RetificaSaveRequest, RetificaRetornoRequest
from services import retifica_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/retifica")
async def list_retifica(servidor: str, banco: str, search: Optional[str] = None, somente_abertos: bool = False):
    return await retifica_service.list_retifica(servidor, banco, search, somente_abertos)


@router.post("/retifica")
async def create_retifica(req: RetificaSaveRequest, request: Request):
    result = await retifica_service.save_retifica(req)
    if result.get("success"):
        num = result.get("num")
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="RETIFICA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(num), descricao=f"Envio p/ Terceiro nº {num} criado (O.S. {req.os})",
            campos_alterados=[
                {"campo": "os", "depois": str(req.os)},
                {"campo": "fornecedor", "depois": str(req.fornecedor)},
                {"campo": "numero_de_serie", "depois": req.numero_de_serie},
                {"campo": "entrada", "depois": req.entrada},
            ],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/retifica/{num}")
async def update_retifica(num: int, req: RetificaSaveRequest, request: Request):
    result = await retifica_service.update_retifica(req, num)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="RETIFICA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(num), descricao=f"Envio p/ Terceiro nº {num} atualizado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/retifica/{num}/retorno")
async def retorno_retifica(num: int, req: RetificaRetornoRequest, request: Request):
    result = await retifica_service.retorno_retifica(req, num)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="RETIFICA", comando="RETORNO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(num), descricao=f"Retorno do Terceiro registrado pro protocolo nº {num}",
            campos_alterados=[{"campo": "saida", "depois": req.saida}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/retifica/{num}")
async def delete_retifica(
    num: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    result = await retifica_service.delete_retifica(servidor, banco, num)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="RETIFICA", comando="EXCLUIR",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(num), descricao=f"Envio p/ Terceiro nº {num} excluído",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result
