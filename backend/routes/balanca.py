"""Rotas de Cadastro de Balanças (Automação Comercial — pré-pesagem com
etiqueta) — ver services/balanca_service.py pro fluxo completo (este backend
só gera e grava o arquivo `ITENSMGV.TXT`, nunca fala com o MGV6/MGV7 nem com
a balança diretamente)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import balanca_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class BalancaDados(BaseModel):
    descricao: str = ""
    pasta_integracao: str = ""
    ativo: bool = True


class BalancaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    dados: BalancaDados


class BalancaDeleteRequest(AuditFields):
    servidor: str
    banco: str


class BalancaExportarCargaRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/balancas")
async def list_balancas(servidor: str, banco: str, search: str = ""):
    return await balanca_service.list_balancas(servidor, banco, search)


@router.get("/balancas/{codigo}")
async def get_balanca(codigo: int, servidor: str, banco: str):
    return await balanca_service.get_balanca(servidor, banco, codigo)


@router.post("/balancas")
async def save_balanca(req: BalancaSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await balanca_service.save_balanca(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BALANCA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Balança {req.dados.descricao} gravada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/balancas/{codigo}/excluir")
async def delete_balanca(codigo: int, req: BalancaDeleteRequest, request: Request):
    result = await balanca_service.delete_balanca(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BALANCA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Balança {codigo} excluída.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/balancas/{codigo}/exportar-carga")
async def exportar_carga_balanca(codigo: int, req: BalancaExportarCargaRequest, request: Request):
    result = await balanca_service.exportar_carga(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BALANCA", comando="EXPORTAR_CARGA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Carga exportada para a balança {codigo} ({result.get('qtd_produtos')} produto(s)).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
