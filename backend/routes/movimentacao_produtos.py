"""Rotas de Movimentação de Produtos (Transações > Movimentações) — ver
services/movimentacao_produtos_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.movimentacao_produtos import (
    MovimentacaoProdutoExcluirRequest,
    MovimentacaoProdutoIncluirRequest,
)
from services import log_auditoria_service, movimentacao_produtos_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/movimentacao-produtos/tipos")
async def list_tipos_mov(servidor: str, banco: str):
    return await movimentacao_produtos_service.list_tipos_mov(servidor, banco)


@router.get("/movimentacao-produtos/produto/{codigo}")
async def find_produto(codigo: str, servidor: str, banco: str):
    return await movimentacao_produtos_service.find_produto(servidor, banco, codigo)


@router.get("/movimentacao-produtos")
async def list_movimentacoes(
    servidor: str, banco: str,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    tipo: Optional[str] = None, codigo_int: Optional[str] = None,
):
    return await movimentacao_produtos_service.list_movimentacoes(
        servidor, banco, data_ini, data_fim, tipo, codigo_int
    )


@router.post("/movimentacao-produtos")
async def incluir_movimentacao(req: MovimentacaoProdutoIncluirRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    result = await movimentacao_produtos_service.incluir_movimentacao(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MOV_PRODUTOS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=req.codigo_int,
            descricao=f"Movimentação {req.tipo} de {req.qtd} un. do produto {req.codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/movimentacao-produtos/{id_mov}/excluir")
async def excluir_movimentacao(id_mov: int, req: MovimentacaoProdutoExcluirRequest, request: Request):
    result = await movimentacao_produtos_service.excluir_movimentacao(req.servidor, req.banco, id_mov)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MOV_PRODUTOS", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(id_mov),
            descricao=f"Movimentação {id_mov} excluída.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
