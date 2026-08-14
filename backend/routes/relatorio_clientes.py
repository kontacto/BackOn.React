"""Rotas do grupo Clientes — Painel de Relatórios (Listagem, Inatividade,
Mala Direta)."""
from typing import Optional

from fastapi import APIRouter

from services import relatorio_listagem_clientes_service, relatorio_inatividade_clientes_service, mala_direta_service

router = APIRouter()


@router.get("/relatorios/listagem-clientes")
async def relatorio_listagem_clientes(
    servidor: str, banco: str, modo: str, termo: Optional[str] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    pessoa_fisica: bool = True, pessoa_juridica: bool = True, ordem: str = "asc",
):
    return await relatorio_listagem_clientes_service.listar_clientes(
        servidor, banco, modo, termo, data_ini, data_fim, pessoa_fisica, pessoa_juridica, ordem
    )


@router.get("/relatorios/listagem-clientes/{codigo}/detalhe")
async def relatorio_listagem_clientes_detalhe(codigo: int, servidor: str, banco: str):
    return await relatorio_listagem_clientes_service.detalhe_contato_endereco(servidor, banco, codigo)


@router.get("/relatorios/inatividade-clientes")
async def relatorio_inatividade_clientes(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[int] = None, regiao: Optional[int] = None, segmento: Optional[str] = None,
    rota: Optional[int] = None, tipo_cliente: Optional[int] = None,
    situacao_cadastro: str = "todos", situacao_contrato: str = "todos", patrimonio: str = "todos",
    modo_base: str = "ultima_compra", data_base: Optional[str] = None,
    fator1: int = 360, fator2: int = 180, fator3: int = 90,
    ultima_compra_desde: Optional[str] = None,
    exibir_contrato_faturamento: bool = False, exibir_contrato_pago: bool = False,
):
    return await relatorio_inatividade_clientes_service.inatividade_clientes(
        servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota, tipo_cliente,
        situacao_cadastro, situacao_contrato, patrimonio, modo_base, data_base,
        fator1, fator2, fator3, ultima_compra_desde, exibir_contrato_faturamento, exibir_contrato_pago,
    )


@router.get("/mala-direta/destinatarios")
async def mala_direta_destinatarios(
    servidor: str, banco: str, incluir_clientes: bool = True, incluir_fornecedores: bool = False,
    sub_modo_cliente: str = "todos", termo: Optional[str] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    return await mala_direta_service.selecionar_destinatarios(
        servidor, banco, incluir_clientes, incluir_fornecedores, sub_modo_cliente, termo, data_ini, data_fim
    )
