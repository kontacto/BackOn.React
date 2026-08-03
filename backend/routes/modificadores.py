"""Rotas de Modificadores (Cadastros > Tabelas Auxiliares) — ver
services/modificadores_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.modificadores import (
    AssociarItemCategoriasRequest,
    ModificadorCategoriaDeleteRequest,
    ModificadorCategoriaSaveRequest,
)
from services import log_auditoria_service, modificadores_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/modificadores/categorias")
async def list_categorias(servidor: str, banco: str, busca: Optional[str] = None):
    return await modificadores_service.list_categorias(servidor, banco, busca)


@router.get("/modificadores/categorias/{codigo}")
async def get_categoria(codigo: int, servidor: str, banco: str):
    return await modificadores_service.get_categoria(servidor, banco, codigo)


@router.post("/modificadores/categorias")
async def save_categoria(req: ModificadorCategoriaSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    era_nova = req.codigo is None
    result = await modificadores_service.save_categoria(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MODIFICADORES", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo"),
            descricao=f"{'Cadastro' if era_nova else 'Alteração'} da categoria de modificador \"{req.nome}\".",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/modificadores/categorias/{codigo}")
async def delete_categoria(codigo: int, req: ModificadorCategoriaDeleteRequest, request: Request):
    result = await modificadores_service.delete_categoria(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MODIFICADORES", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao="Exclusão de categoria de modificador.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# Retrofit: associação "pelo outro lado" — a partir do cadastro de Produto
# Completo/Serviços, ver docstring de modificadores_service.py.
@router.get("/modificadores/por-item/{tipo}/{codigo}")
async def list_categorias_por_item(tipo: str, codigo: str, servidor: str, banco: str):
    return await modificadores_service.list_categorias_por_item(servidor, banco, tipo, codigo)


# Fase 2 (seleção de modificador na hora da venda) — versão "completa" do
# endpoint acima, com os modificadores aninhados. Ver docstring de
# _get_modificadores_completo_por_item_sync.
@router.get("/modificadores/por-item/{tipo}/{codigo}/completo")
async def get_modificadores_completo_por_item(tipo: str, codigo: str, servidor: str, banco: str):
    return await modificadores_service.get_modificadores_completo_por_item(servidor, banco, tipo, codigo)


@router.post("/modificadores/por-item/{tipo}/{codigo}")
async def associar_item_categorias(tipo: str, codigo: str, req: AssociarItemCategoriasRequest):
    return await modificadores_service.associar_item_categorias(req.servidor, req.banco, tipo, codigo, req.categorias)
