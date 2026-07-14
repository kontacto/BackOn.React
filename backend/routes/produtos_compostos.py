"""Rotas de Produtos Compostos / Previsão de Produtos — ver
services/produtos_compostos_service.py para o desenho completo (schema
real, chave composta, escopo desta integração)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, produtos_compostos_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ProdutoCompostoSaveRequest(AuditFields):
    servidor: str
    banco: str
    principal: str
    vinculado: str
    qtd: float
    valor_no_kit: float = 0
    descricao_no_kit: str = ""


class ProdutoCompostoDeleteRequest(AuditFields):
    servidor: str
    banco: str
    principal: str


@router.get("/produtos-compostos")
async def list_composicao(principal: str, servidor: str, banco: str):
    return await produtos_compostos_service.list_composicao(servidor, banco, principal)


@router.post("/produtos-compostos")
async def save_item(req: ProdutoCompostoSaveRequest, request: Request):
    result = await produtos_compostos_service.save_item(
        req.servidor, req.banco,
        principal=req.principal, vinculado=req.vinculado,
        qtd=req.qtd, valor_no_kit=req.valor_no_kit, descricao_no_kit=req.descricao_no_kit,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO", comando="PREV_PROD_ADD",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=req.principal,
            descricao=f"Item {req.vinculado} adicionado à previsão de produtos do serviço {req.principal}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produtos-compostos/{codigo}/excluir")
async def delete_item(codigo: int, req: ProdutoCompostoDeleteRequest, request: Request):
    result = await produtos_compostos_service.delete_item(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO", comando="PREV_PROD_DEL",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=req.principal,
            descricao=f"Item removido da previsão de produtos do serviço {req.principal} (código {codigo}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
