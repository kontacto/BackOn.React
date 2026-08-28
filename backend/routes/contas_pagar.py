"""Rotas de Financeiro > Contas a Pagar (ver
services/contas_pagar_service.py pro escopo/rastreio completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    ContasPagarAvulsaRequest, ContasPagarBaixaRequest,
    ContasPagarEditarParcelaRequest, ContasPagarExcluirRequest,
)
from services import contas_pagar_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contas-pagar")
async def listar(
    servidor: str, banco: str, situacao: Optional[str] = None, fornecedor: Optional[int] = None,
    busca: Optional[str] = None, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    filtros = {"situacao": situacao, "fornecedor": fornecedor, "busca": busca, "data_ini": data_ini, "data_fim": data_fim}
    return await contas_pagar_service.listar(servidor, banco, filtros)


@router.get("/contas-pagar/{codigo}")
async def detalhe(codigo: int, servidor: str, banco: str):
    return await contas_pagar_service.detalhe(servidor, banco, codigo)


@router.get("/contas-pagar-tipos-mov")
async def tipos_mov(servidor: str, banco: str):
    return await contas_pagar_service.list_tipos_mov(servidor, banco)


@router.post("/contas-pagar/avulsa")
async def criar_avulsa(req: ContasPagarAvulsaRequest, request: Request):
    result = await contas_pagar_service.criar_avulsa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Lançamento avulso de duplicata a pagar — fornecedor {req.fornecedor}, valor R$ {req.valor:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/baixar")
async def baixar_parcela(req: ContasPagarBaixaRequest, request: Request):
    result = await contas_pagar_service.baixar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="BAIXAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao=f"Baixa manual de parcela — valor pago R$ {req.valor_pag:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/editar-parcela")
async def editar_parcela(req: ContasPagarEditarParcelaRequest, request: Request):
    result = await contas_pagar_service.editar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Edição de parcela em aberto",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/excluir")
async def excluir(req: ContasPagarExcluirRequest, request: Request):
    result = await contas_pagar_service.excluir(req.servidor, req.banco, req.codigo_duplicata)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao="Exclusão de duplicata a pagar",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
