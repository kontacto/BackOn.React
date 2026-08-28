"""Rotas de Transferência p/Contas Pagar/Receber (migração de
`Geral\\FrmTransfContas.frm` — ver services/transferencia_contas_service.py
pro escopo completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import TransfContasTransferirRequest
from services import transferencia_contas_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/transferencia-contas/pendentes")
async def listar_pendentes(servidor: str, banco: str):
    return await transferencia_contas_service.listar_pendentes(servidor, banco)


@router.post("/transferencia-contas/transferir")
async def transferir(req: TransfContasTransferirRequest, request: Request):
    itens = [i.model_dump() for i in req.itens]
    result = await transferencia_contas_service.transferir(req.servidor, req.banco, itens)
    if result.get("transferidos"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="TRANSF_CONTAS", comando="TRANSFERIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in result["transferidos"]),
            descricao=f"{len(result['transferidos'])} item(ns) transferido(s) para Contas a Pagar/Receber"
                      + (f"; {len(result.get('falhas', []))} falha(s)" if result.get("falhas") else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
