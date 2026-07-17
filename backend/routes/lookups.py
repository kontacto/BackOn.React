"""Rotas de lookups (área de atuação e funcionários)."""
from fastapi import APIRouter

from services import lookups_service

router = APIRouter()


@router.get("/area-atuacao")
async def list_area_atuacao(servidor: str, banco: str):
    return await lookups_service.list_area_atuacao(servidor, banco)


@router.get("/funcionarios")
async def list_funcionarios(servidor: str, banco: str):
    return await lookups_service.list_funcionarios(servidor, banco)


@router.get("/segmentos")
async def list_segmentos(servidor: str, banco: str):
    return await lookups_service.list_segmentos(servidor, banco)


@router.get("/rotas")
async def list_rotas(servidor: str, banco: str):
    return await lookups_service.list_rotas(servidor, banco)


@router.get("/regioes")
async def list_regioes(servidor: str, banco: str):
    return await lookups_service.list_regioes(servidor, banco)


@router.get("/forma-pagamento")
async def list_forma_pagamento(servidor: str, banco: str):
    return await lookups_service.list_forma_pagamento(servidor, banco)


@router.get("/forma-pagamento-completo")
async def list_forma_pagamento_completo(servidor: str, banco: str):
    """Como /forma-pagamento, mas inclui `tipo` (DI/CH/CC/CD/DU/TI/VA/FI) —
    usado pelo modal "Forma de Pagamento" (FrmForPag.frm) pra decidir quais
    campos extras mostrar por forma escolhida."""
    return await lookups_service.list_forma_pagamento_completo(servidor, banco)


@router.get("/canal-aquisicao-cliente")
async def list_canal_aquisicao_cliente(servidor: str, banco: str):
    return await lookups_service.list_canal_aquisicao_cliente(servidor, banco)


@router.get("/dia-semana")
async def list_dia_semana(servidor: str, banco: str):
    return await lookups_service.list_dia_semana(servidor, banco)


@router.get("/status-cliente")
async def list_status_cliente(servidor: str, banco: str):
    return await lookups_service.list_status_cliente(servidor, banco)


@router.get("/centro-custo")
async def list_centro_custo(servidor: str, banco: str):
    return await lookups_service.list_centro_custo(servidor, banco)


@router.get("/contas")
async def list_contas(servidor: str, banco: str):
    return await lookups_service.list_contas(servidor, banco)


@router.get("/classes")
async def list_classes(servidor: str, banco: str):
    return await lookups_service.list_classes(servidor, banco)


@router.get("/sub-classes")
async def list_sub_classes(servidor: str, banco: str):
    return await lookups_service.list_sub_classes(servidor, banco)


@router.get("/favorecidos")
async def list_favorecidos(servidor: str, banco: str):
    return await lookups_service.list_favorecidos(servidor, banco)


@router.get("/tipo-cliente-contato")
async def list_tipo_cliente_contato(servidor: str, banco: str):
    return await lookups_service.list_tipo_cliente_contato(servidor, banco)


@router.get("/tipo-mov")
async def list_tipo_mov(servidor: str, banco: str):
    return await lookups_service.list_tipo_mov(servidor, banco)


@router.get("/tipo-mov-nf")
async def list_tipo_mov_nf(servidor: str, banco: str):
    return await lookups_service.list_tipo_mov_nf(servidor, banco)


@router.get("/tipo-doc")
async def list_tipo_doc(servidor: str, banco: str):
    return await lookups_service.list_tipo_doc(servidor, banco)


@router.get("/codigo-contabil")
async def list_codigo_contabil(servidor: str, banco: str):
    return await lookups_service.list_codigo_contabil(servidor, banco)


@router.get("/cst-pis")
async def list_cst_pis(servidor: str, banco: str):
    return await lookups_service.list_cst_pis(servidor, banco)


@router.get("/cst-cofins")
async def list_cst_cofins(servidor: str, banco: str):
    return await lookups_service.list_cst_cofins(servidor, banco)


@router.get("/tipo-peca")
async def list_tipo_peca(servidor: str, banco: str):
    return await lookups_service.list_tipo_peca(servidor, banco)


@router.get("/uf")
async def list_uf(servidor: str, banco: str):
    return await lookups_service.list_uf(servidor, banco)


@router.get("/modelo-os")
async def list_modelo_os(servidor: str, banco: str):
    return await lookups_service.list_modelo_os(servidor, banco)


@router.get("/modelo-pedido")
async def list_modelo_pedido(servidor: str, banco: str):
    return await lookups_service.list_modelo_pedido(servidor, banco)


@router.get("/funcoes")
async def list_funcoes(servidor: str, banco: str):
    return await lookups_service.list_funcoes(servidor, banco)


@router.get("/cargos")
async def list_cargos(servidor: str, banco: str):
    return await lookups_service.list_cargos(servidor, banco)


@router.get("/especialidades")
async def list_especialidades(servidor: str, banco: str):
    return await lookups_service.list_especialidades(servidor, banco)


@router.get("/cilindro-fabricante")
async def list_cilindro_fabricante(servidor: str, banco: str):
    return await lookups_service.list_cilindro_fabricante(servidor, banco)


@router.get("/cilindro-situacao")
async def list_cilindro_situacao(servidor: str, banco: str):
    return await lookups_service.list_cilindro_situacao(servidor, banco)
