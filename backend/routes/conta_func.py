"""Rotas de Contas x Funcionário (Financeiro > Fluxo de Caixa) — ver
services/conta_func_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.conta_func import ContaFuncSaveRequest
from services import conta_func_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/conta-funcionario")
async def get_vinculo(servidor: str, banco: str, funcionario: int):
    return await conta_func_service.get_vinculo(servidor, banco, funcionario)


@router.get("/conta-funcionario/visiveis")
async def list_visiveis(servidor: str, banco: str, funcionario: Optional[int] = None, master: bool = False):
    """Contas que o funcionário logado pode ver em telas consumidoras (ex.:
    campo "Conta" da Geração de Boletos) — ver services/conta_func_service.py."""
    return await conta_func_service.list_visiveis(servidor, banco, funcionario, master)


@router.post("/conta-funcionario")
async def salvar_vinculo(req: ContaFuncSaveRequest, request: Request):
    result = await conta_func_service.salvar_vinculo(req.servidor, req.banco, req.funcionario, req.contas)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTA_FUNC", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=req.funcionario,
            descricao=f"Configuração de contas visíveis atualizada para o funcionário {req.funcionario} — {result.get('qtd')} conta(s) vinculada(s).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
