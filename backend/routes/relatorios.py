"""Rotas de relatórios e dashboard."""
from typing import Optional

from fastapi import APIRouter

from services import (
    relatorios_service, fechamento_caixa_service, caixa_analitico_service,
    relatorio_apuracao_vendas_service, relatorio_resumo_venda_service,
    relatorio_descontos_concedidos_service, relatorio_itens_pedido_service,
    relatorio_custo_os_service, relatorio_itens_vendidos_service,
    relatorio_busca_os_service, relatorio_resumo_atendimento_service,
    relatorio_produtos_reservados_service, relatorio_estoque_nivel_service,
    relatorio_estoque_service, relatorio_movimentacao_itens_service,
    relatorio_movimentacao_nivel_service, relatorio_itens_funcionario_service,
    relatorio_ranking_vendas_service, relatorio_venda_cliente_produto_service,
    relatorio_venda_nivel_funcionario_service, relatorio_venda_regiao_service,
)

router = APIRouter()


@router.get("/relatorios/pedidos")
async def relatorio_pedidos(servidor: str, banco: str, data_ini: str, data_fim: str,
                            vendedor: Optional[str] = None, situacao: Optional[str] = None,
                            projeto: Optional[int] = None):
    return await relatorios_service.relatorio_pedidos(servidor, banco, data_ini, data_fim, vendedor, situacao, projeto)


@router.get("/relatorios/descontos-margem")
async def relatorio_descontos_margem(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[str] = None, pedido: Optional[int] = None,
    cliente_nome: Optional[str] = None, projeto: Optional[int] = None,
):
    return await relatorios_service.relatorio_desc_margem(
        servidor, banco, data_ini, data_fim, vendedor, pedido, cliente_nome, projeto
    )


@router.get("/dashboard/me")
async def dashboard_me(servidor: str, banco: str, vendedor: Optional[str] = None,
                       data: Optional[str] = None, situacao: Optional[str] = None):
    return await relatorios_service.dashboard_me(servidor, banco, vendedor, data, situacao)


@router.get("/relatorios/os")
async def relatorio_os(servidor: str, banco: str, data_ini: str, data_fim: str,
                       vendedor: Optional[str] = None, situacao: Optional[str] = None):
    return await relatorios_service.relatorio_os(servidor, banco, data_ini, data_fim, vendedor, situacao)


@router.get("/relatorios/os/descontos-margem")
async def relatorio_os_descontos_margem(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[str] = None, os_cod: Optional[int] = None,
    cliente_nome: Optional[str] = None,
):
    return await relatorios_service.relatorio_os_desc_margem(
        servidor, banco, data_ini, data_fim, vendedor, os_cod, cliente_nome
    )


@router.get("/relatorios/caixa")
async def relatorio_caixa(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    atendente: Optional[int] = None, filtrar_atendente_dav: bool = False,
    area: Optional[int] = None, exibir_garantias: bool = False,
):
    return await fechamento_caixa_service.fechamento_caixa(
        servidor, banco, data_ini, data_fim, atendente, filtrar_atendente_dav, area, exibir_garantias,
    )


@router.get("/relatorios/caixa-analitico")
async def relatorio_caixa_analitico(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    agrupamento: str = "diario", dias_semana: Optional[str] = None,
):
    # dias_semana chega como CSV ("0,1,2,3,4,5,6") — querystring simples, sem
    # precisar de múltiplos parâmetros repetidos nem de um body em GET.
    dias = [int(x) for x in dias_semana.split(",") if x.strip() != ""] if dias_semana else None
    return await caixa_analitico_service.caixa_analitico(servidor, banco, data_ini, data_fim, agrupamento, dias)


@router.get("/relatorios/apuracao-vendas")
async def relatorio_apuracao_vendas(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[int] = None, regiao: Optional[int] = None,
    segmento: Optional[str] = None, rota: Optional[int] = None,
    tipo_cliente: Optional[int] = None,
):
    return await relatorio_apuracao_vendas_service.apuracao_vendas(
        servidor, banco, data_ini, data_fim, vendedor, regiao, segmento, rota, tipo_cliente
    )


@router.get("/relatorios/resumo-venda")
async def relatorio_resumo_venda(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    vendedor: Optional[int] = None,
):
    return await relatorio_resumo_venda_service.resumo_venda(servidor, banco, data_ini, data_fim, vendedor)


@router.get("/relatorios/descontos-concedidos")
async def relatorio_descontos_concedidos(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    tipo: Optional[str] = None, cliente_nome: Optional[str] = None,
):
    return await relatorio_descontos_concedidos_service.descontos_concedidos(
        servidor, banco, data_ini, data_fim, tipo, cliente_nome
    )


@router.get("/relatorios/itens-pedido")
async def relatorio_itens_pedido(servidor: str, banco: str, data_ini: str, data_fim: str):
    return await relatorio_itens_pedido_service.itens_pedido(servidor, banco, data_ini, data_fim)


@router.get("/relatorios/custo-os")
async def relatorio_custo_os(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    agrupar_por: str = "cliente", tipo: Optional[int] = None,
):
    return await relatorio_custo_os_service.custo_os(servidor, banco, data_ini, data_fim, agrupar_por, tipo)


@router.get("/relatorios/itens-vendidos")
async def relatorio_itens_vendidos(servidor: str, banco: str, data_ini: str, data_fim: str):
    return await relatorio_itens_vendidos_service.itens_vendidos(servidor, banco, data_ini, data_fim)


@router.get("/relatorios/busca-os")
async def relatorio_busca_os(
    servidor: str, banco: str, filtro: str,
    valor1: Optional[str] = None, valor2: Optional[str] = None, ordem: str = "asc",
):
    return await relatorio_busca_os_service.busca_os(servidor, banco, filtro, valor1, valor2, ordem)


@router.get("/relatorios/busca-os/{os_codigo}/itens")
async def relatorio_busca_os_itens(os_codigo: int, servidor: str, banco: str):
    return await relatorio_busca_os_service.itens_os(servidor, banco, os_codigo)


@router.get("/relatorios/resumo-atendimento")
async def relatorio_resumo_atendimento(
    servidor: str, banco: str,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    situacao: Optional[str] = None, tipo: Optional[int] = None, tecnico: Optional[int] = None,
    cliente: Optional[int] = None, chassi: Optional[str] = None,
    incluir_cliente_pg: bool = True, incluir_contrato: bool = True, incluir_garantia: bool = True,
):
    return await relatorio_resumo_atendimento_service.resumo_atendimento(
        servidor, banco, data_ini, data_fim, situacao, tipo, tecnico, cliente, chassi,
        incluir_cliente_pg, incluir_contrato, incluir_garantia,
    )


@router.get("/relatorios/produtos-reservados")
async def relatorio_produtos_reservados(servidor: str, banco: str, ordenar_por: Optional[str] = None):
    return await relatorio_produtos_reservados_service.produtos_reservados(servidor, banco, ordenar_por)


@router.get("/relatorios/estoque-nivel")
async def relatorio_estoque_nivel(servidor: str, banco: str):
    return await relatorio_estoque_nivel_service.estoque_nivel(servidor, banco)


@router.get("/relatorios/estoque")
async def relatorio_estoque(servidor: str, banco: str, nivel: str, ordenar_por: Optional[str] = None):
    return await relatorio_estoque_service.estoque(servidor, banco, nivel, ordenar_por)


@router.get("/relatorios/movimentacao-itens")
async def relatorio_movimentacao_itens(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    produto: Optional[str] = None, tipo: Optional[str] = None,
    entrada_saida: Optional[str] = None, origem: Optional[str] = None, ordenar_por: Optional[str] = None,
):
    return await relatorio_movimentacao_itens_service.movimentacao_itens(
        servidor, banco, data_ini, data_fim, produto, tipo, entrada_saida, origem, ordenar_por
    )


@router.get("/relatorios/movimentacao-nivel")
async def relatorio_movimentacao_nivel(servidor: str, banco: str, tipo: str, data_ini: str, data_fim: str):
    return await relatorio_movimentacao_nivel_service.movimentacao_nivel(servidor, banco, tipo, data_ini, data_fim)


@router.get("/relatorios/itens-funcionario")
async def relatorio_itens_funcionario(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    modo: str = "vendedor", funcionario: Optional[int] = None, considerar_servicos: bool = True,
):
    return await relatorio_itens_funcionario_service.itens_funcionario(
        servidor, banco, data_ini, data_fim, modo, funcionario, considerar_servicos
    )


@router.get("/relatorios/ranking-vendas")
async def relatorio_ranking_vendas(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    ranking_por: str = "produto", ordenar_por: str = "valor", top_n: int = 10,
    vendedor: Optional[int] = None, fabricante: Optional[int] = None, considerar_servicos: bool = True,
):
    return await relatorio_ranking_vendas_service.ranking_vendas(
        servidor, banco, data_ini, data_fim, ranking_por, ordenar_por, top_n, vendedor, fabricante, considerar_servicos
    )


@router.get("/relatorios/venda-cliente-produto")
async def relatorio_venda_cliente_produto(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    cliente: Optional[int] = None, produto: Optional[str] = None,
):
    return await relatorio_venda_cliente_produto_service.venda_cliente_produto(
        servidor, banco, data_ini, data_fim, cliente, produto
    )


@router.get("/relatorios/venda-nivel-funcionario")
async def relatorio_venda_nivel_funcionario(
    servidor: str, banco: str, data_ini: str, data_fim: str,
    modo: str = "vendedor", funcionario: Optional[int] = None,
):
    return await relatorio_venda_nivel_funcionario_service.venda_nivel_funcionario(
        servidor, banco, data_ini, data_fim, modo, funcionario
    )


@router.get("/relatorios/venda-regiao")
async def relatorio_venda_regiao(servidor: str, banco: str, data_ini: str, data_fim: str, dimensoes: Optional[str] = None):
    return await relatorio_venda_regiao_service.venda_regiao(servidor, banco, data_ini, data_fim, dimensoes)
