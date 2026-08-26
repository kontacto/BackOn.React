"""Rotas de Inutilização de Faixa de NFe (migração de `Geral\\FrmTraINF.frm`,
lado NFe — o lado NFC-e já é uma ação embutida em `routes/gestor_nfce.py`).
Ver `services/inutilizacao_nfe_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.inutilizacao_nfe import InutilizarFaixaNfeRequest
from services import inutilizacao_nfe_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/inutilizacao-nfe/series")
async def series_disponiveis(servidor: str, banco: str):
    return await inutilizacao_nfe_service.series_disponiveis(servidor, banco)


@router.get("/inutilizacao-nfe/historico")
async def historico(servidor: str, banco: str):
    return await inutilizacao_nfe_service.historico(servidor, banco)


@router.post("/inutilizacao-nfe/inutilizar")
async def inutilizar_faixa(req: InutilizarFaixaNfeRequest, request: Request):
    result = await inutilizacao_nfe_service.inutilizar_faixa(
        req.servidor, req.banco, serie=req.serie, numero_inicial=req.numero_inicial,
        numero_final=req.numero_final, motivo=req.motivo, usuario=req.usuario_alteracao,
        classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INUTIL_NFE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao=(
                f"Inutilização de faixa NFe — série {req.serie}, "
                f"números {req.numero_inicial} a {req.numero_final} — motivo: {req.motivo}"
            ),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
