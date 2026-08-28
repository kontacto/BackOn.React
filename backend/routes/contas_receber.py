"""Rotas de Financeiro > Contas a Receber (ver
services/contas_receber_service.py pro escopo/rastreio completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    ContasReceberAvulsaRequest, ContasReceberBaixaRequest, ContasReceberCancelarBaixaRequest,
    ContasReceberEditarParcelaRequest, ContasReceberExcluirRequest, ContasReceberLoteRequest,
    ContasReceberMontanteRequest,
)
from services import contas_receber_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contas-receber")
async def listar(
    servidor: str, banco: str, situacao: Optional[str] = None, cliente: Optional[int] = None,
    busca: Optional[str] = None, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    filtros = {"situacao": situacao, "cliente": cliente, "busca": busca, "data_ini": data_ini, "data_fim": data_fim}
    return await contas_receber_service.listar(servidor, banco, filtros)


@router.get("/contas-receber/{codigo}")
async def detalhe(codigo: int, servidor: str, banco: str):
    return await contas_receber_service.detalhe(servidor, banco, codigo)


@router.get("/contas-receber-tipos-mov")
async def tipos_mov(servidor: str, banco: str):
    return await contas_receber_service.list_tipos_mov(servidor, banco)


@router.post("/contas-receber/avulsa")
async def criar_avulsa(req: ContasReceberAvulsaRequest, request: Request):
    result = await contas_receber_service.criar_avulsa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Lançamento avulso de duplicata a receber — cliente {req.cliente}, valor R$ {req.valor:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/baixar")
async def baixar_parcela(req: ContasReceberBaixaRequest, request: Request):
    result = await contas_receber_service.baixar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="BAIXAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao=f"Baixa manual de parcela — valor pago R$ {req.valor_pag:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/cancelar-baixa")
async def cancelar_baixa(req: ContasReceberCancelarBaixaRequest, request: Request):
    result = await contas_receber_service.cancelar_baixa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="CANCELAR_BAIXA",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Cancelamento de baixa de parcela",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contas-receber/lote/vencimentos")
async def listar_vencimentos_lote(
    servidor: str, banco: str, modo: str = "baixar", cliente: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    filtros = {"modo": modo, "cliente": cliente, "data_ini": data_ini, "data_fim": data_fim}
    return await contas_receber_service.listar_vencimentos_lote(servidor, banco, filtros)


@router.post("/contas-receber/lote")
async def processar_lote(req: ContasReceberLoteRequest, request: Request):
    result = await contas_receber_service.processar_lote(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        comando = "CANCELAR_LOTE" if req.modo == "cancelar" else "BAIXAR_LOTE"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando=comando,
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(len(req.vencimentos)),
            descricao=f"{'Cancelamento' if req.modo == 'cancelar' else 'Baixa'} em lote — "
                      f"{result.get('processados', 0)} processado(s), {len(result.get('falhas', []))} falha(s)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/montante")
async def baixar_montante(req: ContasReceberMontanteRequest, request: Request):
    result = await contas_receber_service.baixar_montante(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="BAIXAR_MONTANTE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.cliente),
            descricao=f"Baixa por Montante — R$ {req.montante:.2f}, "
                      f"{len(result.get('tocados', []))} parcela(s) tocada(s)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/editar-parcela")
async def editar_parcela(req: ContasReceberEditarParcelaRequest, request: Request):
    result = await contas_receber_service.editar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Edição de parcela em aberto",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/excluir")
async def excluir(req: ContasReceberExcluirRequest, request: Request):
    result = await contas_receber_service.excluir(req.servidor, req.banco, req.codigo_duplicata)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao="Exclusão de duplicata a receber",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
