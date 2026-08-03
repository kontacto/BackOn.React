"""Rotas de Contas (Financeiro > Fluxo de Caixa) — ver services/contas_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.contas import ContaDeleteRequest, ContaSaveRequest
from services import contas_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contas-caixa")
async def list_contas(servidor: str, banco: str, busca: Optional[str] = None):
    return await contas_service.list_contas(servidor, banco, busca)


@router.get("/contas-caixa/{codigo}")
async def get_conta(codigo: int, servidor: str, banco: str):
    return await contas_service.get_conta(servidor, banco, codigo)


@router.post("/contas-caixa")
async def save_conta(req: ContaSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    era_novo = req.codigo is None
    result = await contas_service.save_conta(req.servidor, req.banco, dados)
    if result.get("success"):
        descricao_log = f"{'Cadastro' if era_novo else 'Alteração'} da conta \"{req.descricao}\"."
        if result.get("ajuste_saldo"):
            descricao_log += (
                f" Saldo inicial alterado de {result.get('saldo_inicial_anterior')} para {req.saldo_inicial} "
                f"(saldo atual recalculado para {result.get('saldo_atual_novo')})."
            )
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo"),
            descricao=descricao_log,
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/contas-caixa/{codigo}")
async def delete_conta(codigo: int, req: ContaDeleteRequest, request: Request):
    result = await contas_service.delete_conta(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao="Exclusão de conta.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
