"""Rotas do Agrupar Comandas em NF-e (migração de `FrmSelComandas.frm` +
o caminho de agrupamento de `FrmTraImpNFE.frm`). Ver
`services/nfe_agrupada_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.nfe_agrupada import EmitirNfeAgrupadaRequest, ListarComandasAgrupaveisRequest
from services import log_auditoria_service, nfe_agrupada_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/nfe-agrupada/comandas")
async def listar_comandas_agrupaveis(req: ListarComandasAgrupaveisRequest):
    return await nfe_agrupada_service.list_comandas_agrupaveis(
        req.servidor, req.banco, req.cliente, classe=req.classe, master=bool(req.master),
    )


@router.post("/nfe-agrupada/emitir")
async def emitir_nfe_agrupada(req: EmitirNfeAgrupadaRequest, request: Request):
    result = await nfe_agrupada_service.emitir_nfe_agrupada(
        req.servidor, req.banco, req.comandas, usuario=req.usuario_alteracao, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="NFE_AGRUPADA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in req.comandas),
            descricao=f"NF-e agrupada emitida — comandas {req.comandas} — nota {result.get('nota_fisc')}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
