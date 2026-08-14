"""Rotas de Etiquetas de Produto (Painel de Relatórios > Estoque)."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services import etiqueta_produto_service

router = APIRouter()


@router.get("/etiqueta-produto/modelos")
async def listar_modelos_etiqueta(servidor: str, banco: str):
    return await etiqueta_produto_service.listar_modelos(servidor, banco)


class GravarMargemRequest(BaseModel):
    margem_lateral: float
    margem_superior: float


@router.post("/etiqueta-produto/modelos/{codigo}/margem")
async def gravar_margem_etiqueta(codigo: int, servidor: str, banco: str, req: GravarMargemRequest):
    return await etiqueta_produto_service.gravar_margem(servidor, banco, codigo, req.margem_lateral, req.margem_superior)


@router.get("/etiqueta-produto/nf")
async def buscar_nf_etiqueta(servidor: str, banco: str, num_nf: str, serie_nf: str, fornecedor: int):
    return await etiqueta_produto_service.buscar_nf(servidor, banco, num_nf, serie_nf, fornecedor)


@router.get("/etiqueta-produto/produto")
async def buscar_produto_etiqueta(servidor: str, banco: str, termo: str):
    return await etiqueta_produto_service.buscar_produto(servidor, banco, termo)


@router.get("/etiqueta-produto/grade")
async def listar_grade_etiqueta(servidor: str, banco: str, codigo_int: str):
    return await etiqueta_produto_service.listar_grade(servidor, banco, codigo_int)
