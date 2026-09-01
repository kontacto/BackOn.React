"""Rotas de Transferência p/Fluxo de Caixa (migração de
`Geral\\FrmTransfCaixa.frm` — ver services/transferencia_caixa_service.py
pro escopo completo, inclusive o que foi deliberadamente deixado pra
Fase 2)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    TransfCaixaAgrupadasRequest, TransfCaixaConfigAgrupamentoRequest, TransfCaixaTransferirRequest,
)
from services import transferencia_caixa_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/transferencia-caixa/pendentes")
async def listar_pendentes(
    servidor: str, banco: str,
    periodo: bool = False, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    prev_receber: bool = True, prev_pagar: bool = True,
    mov_receber: bool = True, mov_pagar: bool = True,
    entrada_caixa: bool = True, saida_caixa: bool = True,
):
    opcoes = {
        "periodo": periodo, "data_ini": data_ini, "data_fim": data_fim,
        "prev_receber": prev_receber, "prev_pagar": prev_pagar,
        "mov_receber": mov_receber, "mov_pagar": mov_pagar,
        "entrada_caixa": entrada_caixa, "saida_caixa": saida_caixa,
    }
    return await transferencia_caixa_service.listar_pendentes(servidor, banco, opcoes)


@router.get("/transferencia-caixa/tem-pendencia")
async def tem_pendencia(servidor: str, banco: str):
    return await transferencia_caixa_service.tem_pendencia(servidor, banco)


@router.post("/transferencia-caixa/transferir")
async def transferir(req: TransfCaixaTransferirRequest, request: Request):
    itens = [i.model_dump() for i in req.itens]
    result = await transferencia_caixa_service.transferir(req.servidor, req.banco, itens)
    if result.get("transferidos"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="TRANSF_CAIXA", comando="TRANSFERIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in result["transferidos"]),
            descricao=f"{len(result['transferidos'])} item(ns) transferido(s) para o Fluxo de Caixa"
                      + (f"; {len(result.get('falhas', []))} falha(s)" if result.get("falhas") else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# =============================================================================
# Fase 2 — Agrupamento de Comandas (`FrmAgrCom.frm` + `Command6_Click`)
# =============================================================================

@router.get("/transferencia-caixa/agrupamento/config")
async def obter_config_agrupamento(servidor: str, banco: str):
    return await transferencia_caixa_service.obter_config_agrupamento(servidor, banco)


@router.post("/transferencia-caixa/agrupamento/config")
async def salvar_config_agrupamento(req: TransfCaixaConfigAgrupamentoRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco"})
    result = await transferencia_caixa_service.salvar_config_agrupamento(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="TRANSF_CAIXA", comando="CONFIG_AGRUP",
            usuario=None, classe=None, referencia=None,
            descricao="Configuração de Agrupamento de Comandas atualizada",
            ip_origem=_ip(request), plataforma=None,
        )
    return result


@router.post("/transferencia-caixa/transferir-agrupadas")
async def transferir_agrupadas(req: TransfCaixaAgrupadasRequest, request: Request):
    result = await transferencia_caixa_service.transferir_agrupadas(req.servidor, req.banco, req.itens)
    if result.get("transferidos"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="TRANSF_CAIXA", comando="TRANSF_AGRUP",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in result["transferidos"]),
            descricao=f"{len(result['transferidos'])} comanda(s) transferida(s) agrupadas para o Fluxo de Caixa"
                      + (f"; {len(result.get('falhas', []))} falha(s)" if result.get("falhas") else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
