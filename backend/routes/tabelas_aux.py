"""Rotas de Tabelas Auxiliares: Marcas, Modelos, Forma de Pagamento e import FIPE.

Toda ação de Gravar/Excluir é registrada em `log_auditoria` (ver
`services/log_auditoria_service.py`) — busca o registro atual pelo PK antes de
chamar o service (que faz o UPDATE/DELETE às cegas, sem mudança nenhuma nas
funções de service existentes), compara com os valores novos do request e
grava o diff campo-a-campo. Log é best-effort: nunca impede a operação.
"""
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from models.log_auditoria import AuditFields
from services import log_auditoria_service, tabelas_aux_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, tela: str, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela=tela, comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class MarcaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str
    marca_produto: bool = False


class ModeloSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    cod_marca: str
    descricao: str


class AreaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class AreaAtuacaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str
    centro_custo: Optional[int] = None
    tipo_mov: Optional[str] = None
    modelo_os: Optional[int] = None
    modelo_pedido: Optional[int] = None
    intermediador: Optional[int] = None
    intermediador_identificacao: Optional[str] = None


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class StatusOsSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # digitado pelo usuário (campo "Tipo" no legado) — upsert-by-codigo
    descricao: str


class FuncaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    descricao: str
    permite_altera_caixa: bool = False
    cancelar_os: bool = False
    alterar_tecnico_responsavel: bool = False
    funcao_vendedor: bool = False
    funcao_executor: bool = False
    funcao_atendente: bool = False
    libera_cliente_debito: bool = False


class TipoDocSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class TipoClienteSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class MensagemSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class MensagensPdvSaveRequest(AuditFields):
    servidor: str
    banco: str
    linha1: Optional[str] = ""
    linha2: Optional[str] = ""
    linha3: Optional[str] = ""


class NumSerieSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo_int: str
    num_serie: str
    disponivel: bool = True
    detalhes: Optional[str] = ""


class TipoMovSaveRequest(AuditFields):
    servidor: str
    banco: str
    master: bool = False  # bypass da faixa protegida 00-07 no ALTERAR (não no criar — nem master cria)
    codigo: str
    descricao: str
    descricao_nf: Optional[str] = ""
    origem_destino: str  # "C" ou "F"
    atualiza_est: bool = False
    transf_livro: bool = False
    transf_pagar: bool = False
    transf_contabil: bool = False
    transf_caixa: bool = False
    cod_contabil_livro: Optional[int] = None
    cod_contabil_pag: Optional[int] = None
    cod_contabil_juros: Optional[int] = None
    cod_contabil_descontos: Optional[int] = None
    cod_contabil_acrescimos: Optional[int] = None
    tipo_mov_contra_partida: Optional[str] = None
    prazo_contra_partida: Optional[int] = None
    tipo_mov_origem: Optional[str] = None
    cfop: str
    cfop_fora: str
    tipo_doc: int
    itens: bool = False
    centro_custo: Optional[int] = None
    tipo_nf: Optional[int] = None
    estoque_atual: bool = False
    estoque_cliente: bool = False
    estoque_fornecedor: bool = False
    altera_custo: bool = False
    altera_venda: bool = False
    emite_ecf: bool = False
    situacao: Optional[str] = None
    codigo_danfe: Optional[int] = 0


class TipoMsgVincularRequest(AuditFields):
    servidor: str
    banco: str
    mov: str
    mensagens: List[int]


class TipoMsgMovRequest(AuditFields):
    servidor: str
    banco: str
    mov: str


class TipoOsSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # digitado pelo usuário (campo "Tipo" no legado) — upsert-by-codigo
    descricao: str


class ExecutorPadraoRequest(AuditFields):
    servidor: str
    banco: str
    nivel1: str = ""
    nivel2: str = ""
    nivel3: str = ""
    nivel4: str = ""
    nivel5: str = ""
    executor: Optional[int] = None  # None/0 = sem executor definido


class TipoPecaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # digitado pelo usuário (campo "Tipo" no legado) — upsert-by-codigo
    descricao: str


class TipoServicoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # digitado pelo usuário (campo "Tipo" no legado) — upsert-by-codigo
    descricao: str


class TributacaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str  # digitado pelo usuário (campo "Código" no legado) — upsert-by-codigo
    descricao: str
    aplicacao: Optional[str] = ""


class UnidSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str  # digitado pelo usuário (campo "Código" no legado) — upsert-by-codigo
    descricao: str
    permite_decimais: bool = False


class TipoOsProdSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # digitado pelo usuário (campo "Tipo" no legado) — upsert-by-codigo
    descricao: str


class GrupoPisCofinsSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str


class TamanhoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str


class SituacaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    descricao: str


class SegmentoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str


class RotaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str
    prioridade: Optional[int] = None
    codigo_regiao: int


class RegiaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class OrigemSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    descricao: str


class IcmsSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    descricao: str


class CorSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str
    cor_fabrica: Optional[str] = None


class NivelSaveRequest(AuditFields):
    servidor: str
    banco: str
    cod_nivel: Optional[int] = None
    parent_cod_nivel: Optional[int] = None
    descricao: str
    custo: Optional[int] = None
    classe_entrada: Optional[int] = None
    sub_classe_entrada: Optional[int] = None
    classe_saida: Optional[int] = None
    sub_classe_saida: Optional[int] = None


class GrupoUsuarioSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str
    exige_tipo_cliente: bool = False
    exige_canal_aquisicao_cliente: bool = False
    visualiza_pedido_aberto: bool = True
    visualiza_pedido_fechado: bool = True
    visualiza_pedido_cancelado: bool = True
    visualiza_pedido_faturado: bool = True


class FormaPagPrazoItem(BaseModel):
    prazo: int
    percentual: float = 0.0


class FormaPagamentoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[str] = None
    descricao: str
    tipo: Optional[str] = None
    taxa_adm: float = 0.0
    prazo: Optional[int] = None
    prazo_rec: Optional[int] = None
    situacao: Optional[str] = None
    periodo: Optional[int] = None
    faturar_para: Optional[str] = None
    forma_pag_garantia: bool = False
    exige_documentos: bool = False
    vale_devolucao: bool = False
    nao_totaliza_caixa: bool = False
    parcelador: Optional[str] = None
    parcela_max: Optional[int] = None
    cod_mov: Optional[str] = None
    perc_desc_comissao: float = 0.0
    valor_desc_comissao: float = 0.0
    perc_acres_comissao: float = 0.0
    valor_acres_comissao: float = 0.0
    transf_caixa: Optional[str] = None
    conta_transf_caixa: Optional[int] = None
    classe_caixa: Optional[int] = None
    sub_classe_caixa: Optional[int] = None
    prazos: List[FormaPagPrazoItem] = Field(default_factory=list)


class CfopSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    descricao: str
    descricao_nf: Optional[str] = None
    aplicacao: Optional[str] = None
    cod_contabil: Optional[int] = None


class CfopXmlSaveRequest(AuditFields):
    servidor: str
    banco: str
    cfop_xml: str
    cfop: str


class CfopPisCofinsSaveRequest(AuditFields):
    servidor: str
    banco: str
    cod_auto: Optional[int] = None
    cfop: str
    grupo_pis_cofins: int
    tributacao_qtd: bool = False
    tributacao_pis: Optional[int] = None
    perc_valor_pis: float = 0.0
    tributacao_cofins: Optional[int] = None
    perc_valor_cofins: float = 0.0
    acatar_nfe: bool = True


class ImportFipeRequest(BaseModel):
    servidor: str
    banco: str
    tipo: str = "carros"
    fipe_marca_id: str
    descricao: str


# ==================== Marcas ====================

@router.get("/tabelas/marcas")
async def list_marcas(servidor: str, banco: str, marca_produto: Optional[bool] = None, search: str = ""):
    return await tabelas_aux_service.list_marcas(servidor, banco, marca_produto, search)


@router.post("/tabelas/marcas")
async def save_marca(req: MarcaSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "marcas", "codigo", req.codigo)
    result = await tabelas_aux_service.save_marca(req.servidor, req.banco, req.codigo, req.descricao, req.marca_produto)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao, "marca_produto": req.marca_produto}, ["descricao", "marca_produto"])
        await _log(req, request, tela="MARCAS", comando="GRAVAR", referencia=codigo, descricao=f"Marca '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/marcas/{codigo}/excluir")
async def delete_marca(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "marcas", "codigo", codigo)
    result = await tabelas_aux_service.delete_marca(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "marca_produto"])
        await _log(req, request, tela="MARCAS", comando="EXCLUIR", referencia=codigo, descricao=f"Marca '{codigo}' excluída", campos=campos)
    return result


# ==================== Modelos ====================

@router.get("/tabelas/modelos")
async def list_modelos(servidor: str, banco: str, cod_marca: Optional[str] = None, search: str = ""):
    return await tabelas_aux_service.list_modelos(servidor, banco, cod_marca, search)


@router.post("/tabelas/modelos")
async def save_modelo(req: ModeloSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "modelos", "codigo", req.codigo)
    result = await tabelas_aux_service.save_modelo(req.servidor, req.banco, req.codigo, req.cod_marca, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"cod_marca": req.cod_marca, "descricao": req.descricao}, ["cod_marca", "descricao"])
        await _log(req, request, tela="MODELOS", comando="GRAVAR", referencia=codigo, descricao=f"Modelo '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/modelos/{codigo}/excluir")
async def delete_modelo(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "modelos", "codigo", codigo)
    result = await tabelas_aux_service.delete_modelo(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["cod_marca", "descricao"])
        await _log(req, request, tela="MODELOS", comando="EXCLUIR", referencia=codigo, descricao=f"Modelo '{codigo}' excluído", campos=campos)
    return result


# ==================== Área ====================

@router.get("/tabelas/area")
async def list_area(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_area(servidor, banco, search)


@router.post("/tabelas/area")
async def save_area(req: AreaSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "area", "codigo", req.codigo)
    result = await tabelas_aux_service.save_area(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="AREA", comando="GRAVAR", referencia=codigo, descricao=f"Área '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/area/{codigo}/excluir")
async def delete_area(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "area", "codigo", codigo)
    result = await tabelas_aux_service.delete_area(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="AREA", comando="EXCLUIR", referencia=codigo, descricao=f"Área '{codigo}' excluída", campos=campos)
    return result


# ==================== Área de Atuação ====================

@router.get("/tabelas/area-atuacao")
async def list_area_atuacao(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_area_atuacao_crud(servidor, banco, search)


@router.post("/tabelas/area-atuacao")
async def save_area_atuacao(req: AreaAtuacaoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "area_atuacao", "area", req.codigo)
    result = await tabelas_aux_service.save_area_atuacao(
        req.servidor, req.banco, req.codigo, req.descricao, req.centro_custo,
        req.tipo_mov, req.modelo_os, req.modelo_pedido, req.intermediador,
        req.intermediador_identificacao,
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos_map = ["descricao", "centro_custo", "tipo_mov", "modelo_os", "modelo_pedido", "intermediador", "intermediador_identificacao"]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="AREA_ATUACAO", comando="GRAVAR", referencia=codigo, descricao=f"Área de Atuação '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/area-atuacao/{codigo}/excluir")
async def delete_area_atuacao(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "area_atuacao", "area", codigo)
    result = await tabelas_aux_service.delete_area_atuacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "centro_custo", "tipo_mov"])
        await _log(req, request, tela="AREA_ATUACAO", comando="EXCLUIR", referencia=codigo, descricao=f"Área de Atuação '{codigo}' excluída", campos=campos)
    return result


# ==================== Forma de Pagamento ====================

@router.get("/tabelas/forma-pagamento")
async def list_forma_pagamento(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_forma_pagamento(servidor, banco, search)


@router.post("/tabelas/forma-pagamento")
async def save_forma_pagamento(req: FormaPagamentoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "forma_pagamento", "codigo", req.codigo)
    result = await tabelas_aux_service.save_forma_pagamento(req)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos_map = [
            "descricao", "tipo", "taxa_adm", "prazo", "prazo_rec", "situacao", "periodo", "faturar_para",
            "forma_pag_garantia", "exige_documentos", "vale_devolucao", "nao_totaliza_caixa", "parcelador",
            "parcela_max", "cod_mov", "perc_desc_comissao", "valor_desc_comissao", "perc_acres_comissao",
            "valor_acres_comissao", "transf_caixa", "conta_transf_caixa", "classe_caixa", "sub_classe_caixa",
        ]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="FORMA_PAGAMENTO", comando="GRAVAR", referencia=codigo, descricao=f"Forma de Pagamento '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/forma-pagamento/{codigo}/excluir")
async def delete_forma_pagamento(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "forma_pagamento", "codigo", codigo)
    result = await tabelas_aux_service.delete_forma_pagamento(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "tipo"])
        await _log(req, request, tela="FORMA_PAGAMENTO", comando="EXCLUIR", referencia=codigo, descricao=f"Forma de Pagamento '{codigo}' excluída", campos=campos)
    return result


# ==================== Funções ====================

@router.get("/tabelas/funcoes")
async def list_funcoes(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_funcoes(servidor, banco, search)


@router.post("/tabelas/funcoes")
async def save_funcoes(req: FuncaoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "funcoes", "codigo", req.codigo)
    result = await tabelas_aux_service.save_funcoes(
        req.servidor, req.banco, req.codigo, req.descricao,
        req.permite_altera_caixa, req.cancelar_os, req.alterar_tecnico_responsavel,
        req.funcao_vendedor, req.funcao_executor, req.funcao_atendente, req.libera_cliente_debito,
    )
    if result.get("success"):
        campos_map = [
            "descricao", "permite_altera_caixa", "cancelar_os", "alterar_tecnico_responsavel",
            "funcao_vendedor", "funcao_executor", "funcao_atendente", "libera_cliente_debito",
        ]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="FUNCOES", comando="GRAVAR", referencia=req.codigo, descricao=f"Função '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/funcoes/{codigo}/excluir")
async def delete_funcoes(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "funcoes", "codigo", codigo)
    result = await tabelas_aux_service.delete_funcoes(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="FUNCOES", comando="EXCLUIR", referencia=codigo, descricao=f"Função '{codigo}' excluída", campos=campos)
    return result


# ==================== Status de O.S. ====================

@router.get("/tabelas/status-os")
async def list_status_os(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_status_os(servidor, banco, search)


@router.post("/tabelas/status-os")
async def save_status_os(req: StatusOsSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "status_os", "codigo", req.codigo)
    result = await tabelas_aux_service.save_status_os(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="STATUS_OS", comando="GRAVAR", referencia=codigo, descricao=f"Status de O.S. '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/status-os/{codigo}/excluir")
async def delete_status_os(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "status_os", "codigo", codigo)
    result = await tabelas_aux_service.delete_status_os(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="STATUS_OS", comando="EXCLUIR", referencia=codigo, descricao=f"Status de O.S. '{codigo}' excluído", campos=campos)
    return result


# ==================== Tipo de Documento ====================

@router.get("/tabelas/tipo-doc")
async def list_tipo_doc(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_doc(servidor, banco, search)


@router.post("/tabelas/tipo-doc")
async def save_tipo_doc(req: TipoDocSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_doc", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_doc(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_DOC", comando="GRAVAR", referencia=codigo, descricao=f"Tipo de Documento '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-doc/{codigo}/excluir")
async def delete_tipo_doc(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_doc", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_doc(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_DOC", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Documento '{codigo}' excluído", campos=campos)
    return result


# ==================== Tipo Cliente/Forn. ====================

@router.get("/tabelas/tipo-cliente")
async def list_tipo_cliente(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_cliente(servidor, banco, search)


@router.post("/tabelas/tipo-cliente")
async def save_tipo_cliente(req: TipoClienteSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_cliente", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_cliente(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_CLIENTE", comando="GRAVAR", referencia=codigo, descricao=f"Tipo Cliente/Forn. '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-cliente/{codigo}/excluir")
async def delete_tipo_cliente(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_cliente", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_cliente(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_CLIENTE", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo Cliente/Forn. '{codigo}' excluído", campos=campos)
    return result


# ==================== Mensagens ====================

@router.get("/tabelas/mensagens")
async def list_mensagens(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_mensagens(servidor, banco, search)


@router.post("/tabelas/mensagens")
async def save_mensagem(req: MensagemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Mensagens", "codigo", req.codigo)
    result = await tabelas_aux_service.save_mensagem(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="MENSAGENS", comando="GRAVAR", referencia=codigo, descricao=f"Mensagem {codigo} gravada", campos=campos)
    return result


@router.post("/tabelas/mensagens/{codigo}/excluir")
async def delete_mensagem(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Mensagens", "codigo", codigo)
    result = await tabelas_aux_service.delete_mensagem(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="MENSAGENS", comando="EXCLUIR", referencia=codigo, descricao=f"Mensagem {codigo} excluída", campos=campos)
    return result


# ==================== Mensagens PDV ====================

@router.get("/tabelas/mensagens-pdv")
async def get_mensagens_pdv(servidor: str, banco: str):
    return await tabelas_aux_service.read_mensagens_pdv(servidor, banco)


@router.post("/tabelas/mensagens-pdv")
async def save_mensagens_pdv(req: MensagensPdvSaveRequest, request: Request):
    antes = await tabelas_aux_service.read_mensagens_pdv(req.servidor, req.banco)
    result = await tabelas_aux_service.save_mensagens_pdv(req.servidor, req.banco, req.linha1, req.linha2, req.linha3)
    if result.get("success"):
        depois = {"linha1": req.linha1, "linha2": req.linha2, "linha3": req.linha3}
        campos = log_auditoria_service.diff_campos(
            antes if antes.get("success") else None, depois, ["linha1", "linha2", "linha3"],
        )
        await _log(req, request, tela="MENSAGENS_PDV", comando="GRAVAR", referencia=None, descricao="Mensagens do PDV atualizadas", campos=campos)
    return result


# ==================== Números de Série ====================

@router.get("/tabelas/num-serie/produto")
async def resolver_produto_num_serie(servidor: str, banco: str, termo: str):
    return await tabelas_aux_service.resolve_produto_num_serie(servidor, banco, termo)


@router.get("/tabelas/num-serie/produtos")
async def buscar_produtos_num_serie(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.buscar_produtos_num_serie(servidor, banco, search)


@router.get("/tabelas/num-serie")
async def list_num_serie(servidor: str, banco: str, codigo_int: str):
    return await tabelas_aux_service.list_num_serie(servidor, banco, codigo_int)


@router.get("/tabelas/num-serie/buscar")
async def buscar_num_serie(servidor: str, banco: str, num_serie: str):
    return await tabelas_aux_service.buscar_num_serie(servidor, banco, num_serie)


@router.post("/tabelas/num-serie")
async def save_num_serie(req: NumSerieSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pecas_num_serie", "num_serie", req.num_serie)
    result = await tabelas_aux_service.save_num_serie(req.servidor, req.banco, req.codigo_int, req.num_serie, req.disponivel, req.detalhes)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(
            antes, {"codigo_int": req.codigo_int, "disponivel": req.disponivel, "detalhes": req.detalhes},
            ["codigo_int", "disponivel", "detalhes"],
        )
        await _log(req, request, tela="NUM_SERIE", comando="GRAVAR", referencia=req.num_serie, descricao=f"Número de série '{req.num_serie}' gravado", campos=campos)
    return result


@router.post("/tabelas/num-serie/{num_serie}/excluir")
async def delete_num_serie(num_serie: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pecas_num_serie", "num_serie", num_serie)
    result = await tabelas_aux_service.delete_num_serie(req.servidor, req.banco, num_serie)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["codigo_int", "disponivel", "detalhes"])
        await _log(req, request, tela="NUM_SERIE", comando="EXCLUIR", referencia=num_serie, descricao=f"Número de série '{num_serie}' excluído", campos=campos)
    return result


# ==================== Tipo de Movimentação ====================

CAMPOS_TIPO_MOV = [
    "descricao", "descricao_nf", "origem_destino", "atualiza_est",
    "transf_livro", "transf_pagar", "transf_contabil", "transf_caixa",
    "cod_contabil_livro", "cod_contabil_pag", "cod_contabil_juros", "cod_contabil_descontos", "cod_contabil_acrescimos",
    "tipo_mov_contra_partida", "prazo_contra_partida", "tipo_mov_origem",
    "cfop", "cfop_fora", "tipo_doc", "itens", "centro_custo", "tipo_nf",
    "estoque_atual", "estoque_cliente", "estoque_fornecedor", "altera_custo", "altera_venda",
    "emite_ecf", "situacao", "CODIGO_DANFE",
]


def _depois_tipo_mov(req: TipoMovSaveRequest) -> dict:
    return {
        "descricao": req.descricao, "descricao_nf": req.descricao_nf, "origem_destino": req.origem_destino,
        "atualiza_est": "S" if req.atualiza_est else "N",
        "transf_livro": "S" if req.transf_livro else "N", "transf_pagar": "S" if req.transf_pagar else "N",
        "transf_contabil": "S" if req.transf_contabil else "N", "transf_caixa": "S" if req.transf_caixa else "N",
        "cod_contabil_livro": req.cod_contabil_livro, "cod_contabil_pag": req.cod_contabil_pag,
        "cod_contabil_juros": req.cod_contabil_juros, "cod_contabil_descontos": req.cod_contabil_descontos,
        "cod_contabil_acrescimos": req.cod_contabil_acrescimos,
        "tipo_mov_contra_partida": req.tipo_mov_contra_partida,
        "prazo_contra_partida": req.prazo_contra_partida if req.tipo_mov_contra_partida else 0,
        "tipo_mov_origem": req.tipo_mov_origem,
        "cfop": req.cfop, "cfop_fora": req.cfop_fora, "tipo_doc": req.tipo_doc,
        "itens": "S" if req.itens else "N", "centro_custo": req.centro_custo or 0, "tipo_nf": req.tipo_nf,
        "estoque_atual": req.estoque_atual, "estoque_cliente": req.estoque_cliente,
        "estoque_fornecedor": req.estoque_fornecedor, "altera_custo": req.altera_custo, "altera_venda": req.altera_venda,
        "emite_ecf": req.emite_ecf, "situacao": req.situacao, "CODIGO_DANFE": req.codigo_danfe,
    }


@router.get("/tabelas/tipo-mov")
async def list_tipo_mov(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_mov(servidor, banco, search)


@router.get("/tabelas/tipo-mov-proximo-codigo")
async def proximo_codigo_tipo_mov(servidor: str, banco: str, natureza: str):
    return await tabelas_aux_service.proximo_codigo_tipo_mov(servidor, banco, natureza)


@router.get("/tabelas/tipo-nf")
async def list_tipo_nf(servidor: str, banco: str):
    return await tabelas_aux_service.list_tipo_nf(servidor, banco)


@router.get("/tabelas/tipo-mov/{codigo}")
async def get_tipo_mov(codigo: str, servidor: str, banco: str):
    return await tabelas_aux_service.get_tipo_mov(servidor, banco, codigo)


@router.post("/tabelas/tipo-mov")
async def save_tipo_mov(req: TipoMovSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_mov", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_mov(req.servidor, req.banco, req.model_dump(), req.master)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, _depois_tipo_mov(req), CAMPOS_TIPO_MOV)
        await _log(req, request, tela="TIPO_MOV", comando="GRAVAR", referencia=codigo, descricao=f"Tipo de Movimentação '{codigo}' gravado ({len(campos)} alteração(ões))", campos=campos)
    return result


@router.post("/tabelas/tipo-mov/{codigo}/excluir")
async def delete_tipo_mov(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_mov", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_mov(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, CAMPOS_TIPO_MOV)
        await _log(req, request, tela="TIPO_MOV", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Movimentação '{codigo}' excluído", campos=campos)
    return result


# ==================== Tipo Mov x Mensagens ====================

@router.get("/tabelas/tipo-msg")
async def list_tipo_msg(servidor: str, banco: str, mov: str):
    return await tabelas_aux_service.list_tipo_msg(servidor, banco, mov)


@router.post("/tabelas/tipo-msg/vincular")
async def vincular_tipo_msg(req: TipoMsgVincularRequest, request: Request):
    result = await tabelas_aux_service.vincular_tipo_msg(req.servidor, req.banco, req.mov, req.mensagens)
    if result.get("success"):
        await _log(
            req, request, tela="TIPO_MOV_MSG", comando="VINCULOS", referencia=req.mov,
            descricao=f"{len(req.mensagens)} mensagem(ns) vinculada(s) ao tipo '{req.mov}'",
            campos=[{"campo": "msg", "depois": ",".join(map(str, req.mensagens))}],
        )
    return result


@router.post("/tabelas/tipo-msg/desvincular")
async def desvincular_tipo_msg(req: TipoMsgVincularRequest, request: Request):
    result = await tabelas_aux_service.desvincular_tipo_msg(req.servidor, req.banco, req.mov, req.mensagens)
    if result.get("success"):
        await _log(
            req, request, tela="TIPO_MOV_MSG", comando="VINCULOS", referencia=req.mov,
            descricao=f"{len(req.mensagens)} mensagem(ns) desvinculada(s) do tipo '{req.mov}'",
            campos=[{"campo": "msg", "antes": ",".join(map(str, req.mensagens))}],
        )
    return result


@router.post("/tabelas/tipo-msg/vincular-todos")
async def vincular_todos_tipo_msg(req: TipoMsgMovRequest, request: Request):
    result = await tabelas_aux_service.vincular_todos_tipo_msg(req.servidor, req.banco, req.mov)
    if result.get("success"):
        await _log(req, request, tela="TIPO_MOV_MSG", comando="VINCULOS", referencia=req.mov, descricao=f"Todas as mensagens vinculadas ao tipo '{req.mov}'")
    return result


@router.post("/tabelas/tipo-msg/desvincular-todos")
async def desvincular_todos_tipo_msg(req: TipoMsgMovRequest, request: Request):
    result = await tabelas_aux_service.desvincular_todos_tipo_msg(req.servidor, req.banco, req.mov)
    if result.get("success"):
        await _log(req, request, tela="TIPO_MOV_MSG", comando="VINCULOS", referencia=req.mov, descricao=f"Todas as mensagens desvinculadas do tipo '{req.mov}'")
    return result


# ==================== Tipo de Pré-Venda ====================

@router.get("/tabelas/tipo-os")
async def list_tipo_os(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_os(servidor, banco, search)


@router.post("/tabelas/tipo-os")
async def save_tipo_os(req: TipoOsSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_os", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_os(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_OS", comando="GRAVAR", referencia=codigo, descricao=f"Tipo de Pré-Venda '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-os/{codigo}/excluir")
async def delete_tipo_os(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_os", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_os(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_OS", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Pré-Venda '{codigo}' excluído", campos=campos)
    return result


# ==================== Executor Padrão ====================

def _nivel_ref(n1: str, n2: str, n3: str, n4: str, n5: str) -> str:
    return "".join([n1, n2, n3, n4, n5]) or "raiz"


@router.get("/tabelas/executor-padrao")
async def get_executor_padrao(servidor: str, banco: str, nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = ""):
    return await tabelas_aux_service.get_executor_padrao(servidor, banco, nivel1, nivel2, nivel3, nivel4, nivel5)


@router.post("/tabelas/executor-padrao")
async def save_executor_padrao(req: ExecutorPadraoRequest, request: Request):
    antes = await tabelas_aux_service.get_executor_padrao(req.servidor, req.banco, req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5)
    result = await tabelas_aux_service.save_executor_padrao(
        req.servidor, req.banco, req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5, req.executor,
    )
    if result.get("success"):
        ref = _nivel_ref(req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5)
        campos = log_auditoria_service.diff_campos(
            {"executor": antes.get("executor")} if antes.get("success") else None,
            {"executor": req.executor or 0}, ["executor"],
        )
        await _log(req, request, tela="EXECUTOR_PADRAO", comando="GRAVAR", referencia=ref, descricao=f"Executor padrão do nível '{ref}' gravado", campos=campos)
    return result


@router.post("/tabelas/executor-padrao/excluir")
async def delete_executor_padrao(req: ExecutorPadraoRequest, request: Request):
    antes = await tabelas_aux_service.get_executor_padrao(req.servidor, req.banco, req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5)
    result = await tabelas_aux_service.delete_executor_padrao(req.servidor, req.banco, req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5)
    if result.get("success"):
        ref = _nivel_ref(req.nivel1, req.nivel2, req.nivel3, req.nivel4, req.nivel5)
        campos = [{"campo": "executor", "antes": str(antes.get("executor"))}] if antes.get("success") and antes.get("executor") else []
        await _log(req, request, tela="EXECUTOR_PADRAO", comando="EXCLUIR", referencia=ref, descricao=f"Executor padrão do nível '{ref}' excluído", campos=campos)
    return result


# ==================== Tipo de Produto ====================

@router.get("/tabelas/tipo-peca")
async def list_tipo_peca(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_peca(servidor, banco, search)


@router.post("/tabelas/tipo-peca")
async def save_tipo_peca(req: TipoPecaSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Tipo_Peca", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_peca(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_PECA", comando="GRAVAR", referencia=codigo, descricao=f"Tipo de Produto '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-peca/{codigo}/excluir")
async def delete_tipo_peca(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Tipo_Peca", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_peca(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_PECA", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Produto '{codigo}' excluído", campos=campos)
    return result


# ==================== Tipo de Serviço ====================

@router.get("/tabelas/tipo-servico")
async def list_tipo_servico(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_servico(servidor, banco, search)


@router.post("/tabelas/tipo-servico")
async def save_tipo_servico(req: TipoServicoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_servico", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_servico(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_SERVICO", comando="GRAVAR", referencia=codigo, descricao=f"Tipo de Serviço '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-servico/{codigo}/excluir")
async def delete_tipo_servico(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_servico", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_servico(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_SERVICO", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Serviço '{codigo}' excluído", campos=campos)
    return result


# ==================== Tributação ====================

@router.get("/tabelas/tributacao")
async def list_tributacao(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tributacao(servidor, banco, search)


@router.post("/tabelas/tributacao")
async def save_tributacao(req: TributacaoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Tributacao", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tributacao(req.servidor, req.banco, req.codigo, req.descricao, req.aplicacao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao, "Aplicacao": req.aplicacao}, ["descricao", "Aplicacao"])
        await _log(req, request, tela="TRIBUTACAO", comando="GRAVAR", referencia=codigo, descricao=f"Tributação '{codigo}' gravada", campos=campos)
    return result


@router.post("/tabelas/tributacao/{codigo}/excluir")
async def delete_tributacao(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "Tributacao", "codigo", codigo)
    result = await tabelas_aux_service.delete_tributacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "Aplicacao"])
        await _log(req, request, tela="TRIBUTACAO", comando="EXCLUIR", referencia=codigo, descricao=f"Tributação '{codigo}' excluída", campos=campos)
    return result


# ==================== Unidade de Medida ====================

@router.get("/tabelas/unid")
async def list_unid(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_unid(servidor, banco, search)


@router.post("/tabelas/unid")
async def save_unid(req: UnidSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "unid", "cod", req.codigo)
    result = await tabelas_aux_service.save_unid(req.servidor, req.banco, req.codigo, req.descricao, req.permite_decimais)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"des": req.descricao, "permite_decimais": req.permite_decimais}, ["des", "permite_decimais"])
        await _log(req, request, tela="UNID", comando="GRAVAR", referencia=codigo, descricao=f"Unidade '{codigo}' gravada", campos=campos)
    return result


@router.post("/tabelas/unid/{codigo}/excluir")
async def delete_unid(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "unid", "cod", codigo)
    result = await tabelas_aux_service.delete_unid(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["des", "permite_decimais"])
        await _log(req, request, tela="UNID", comando="EXCLUIR", referencia=codigo, descricao=f"Unidade '{codigo}' excluída", campos=campos)
    return result


# ==================== Tipo Destino Itens OS ====================

@router.get("/tabelas/tipo-os-prod")
async def list_tipo_os_prod(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tipo_os_prod(servidor, banco, search)


@router.post("/tabelas/tipo-os-prod")
async def save_tipo_os_prod(req: TipoOsProdSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_os_prod", "codigo", req.codigo)
    result = await tabelas_aux_service.save_tipo_os_prod(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_OS_PROD", comando="GRAVAR", referencia=codigo, descricao=f"Tipo Destino Itens OS '{codigo}' gravado", campos=campos)
    return result


@router.post("/tabelas/tipo-os-prod/{codigo}/excluir")
async def delete_tipo_os_prod(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_os_prod", "codigo", codigo)
    result = await tabelas_aux_service.delete_tipo_os_prod(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_OS_PROD", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo Destino Itens OS '{codigo}' excluído", campos=campos)
    return result


# ==================== Grupo PIS/COFINS ====================

@router.get("/tabelas/grupo-pis-cofins")
async def list_grupo_pis_cofins(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_grupo_pis_cofins(servidor, banco, search)


@router.post("/tabelas/grupo-pis-cofins")
async def save_grupo_pis_cofins(req: GrupoPisCofinsSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "grupo_pis_cofins", "cod_grupo", req.codigo)
    result = await tabelas_aux_service.save_grupo_pis_cofins(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="GRUPO_PISCOF", comando="GRAVAR", referencia=codigo, descricao=f"Grupo PIS/COFINS '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/grupo-pis-cofins/{codigo}/excluir")
async def delete_grupo_pis_cofins(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "grupo_pis_cofins", "cod_grupo", codigo)
    result = await tabelas_aux_service.delete_grupo_pis_cofins(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="GRUPO_PISCOF", comando="EXCLUIR", referencia=codigo, descricao=f"Grupo PIS/COFINS '{codigo}' excluído", campos=campos)
    return result


# ==================== Tamanhos ====================

@router.get("/tabelas/tamanho")
async def list_tamanho(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_tamanho(servidor, banco, search)


@router.post("/tabelas/tamanho")
async def save_tamanho(req: TamanhoSaveRequest, request: Request):
    result = await tabelas_aux_service.save_tamanho(req.servidor, req.banco, req.codigo)
    if result.get("success"):
        await _log(req, request, tela="TAMANHO", comando="GRAVAR", referencia=req.codigo, descricao=f"Tamanho '{req.codigo}' gravado")
    return result


@router.post("/tabelas/tamanho/{codigo}/excluir")
async def delete_tamanho(codigo: str, req: DeleteRequest, request: Request):
    result = await tabelas_aux_service.delete_tamanho(req.servidor, req.banco, codigo)
    if result.get("success"):
        await _log(req, request, tela="TAMANHO", comando="EXCLUIR", referencia=codigo, descricao=f"Tamanho '{codigo}' excluído")
    return result


# ==================== Situação ====================

@router.get("/tabelas/situacao")
async def list_situacao(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_situacao(servidor, banco, search)


@router.post("/tabelas/situacao")
async def save_situacao(req: SituacaoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "situacao", "codigo", req.codigo)
    result = await tabelas_aux_service.save_situacao(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="SITUACAO", comando="GRAVAR", referencia=req.codigo, descricao=f"Situação '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/situacao/{codigo}/excluir")
async def delete_situacao(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "situacao", "codigo", codigo)
    result = await tabelas_aux_service.delete_situacao(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="SITUACAO", comando="EXCLUIR", referencia=codigo, descricao=f"Situação '{codigo}' excluída", campos=campos)
    return result


# ==================== Segmentos ====================

@router.get("/tabelas/segmentos")
async def list_segmentos(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_segmentos(servidor, banco, search)


@router.post("/tabelas/segmentos")
async def save_segmento(req: SegmentoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "segmentos", "codigo", req.codigo)
    result = await tabelas_aux_service.save_segmento(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="SEGMENTOS", comando="GRAVAR", referencia=codigo, descricao=f"Segmento '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/segmentos/{codigo}/excluir")
async def delete_segmento(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "segmentos", "codigo", codigo)
    result = await tabelas_aux_service.delete_segmento(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="SEGMENTOS", comando="EXCLUIR", referencia=codigo, descricao=f"Segmento '{codigo}' excluído", campos=campos)
    return result


# ==================== Rotas ====================

@router.get("/tabelas/rotas")
async def list_rotas(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_rotas(servidor, banco, search)


@router.post("/tabelas/rotas")
async def save_rota(req: RotaSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "rotas", "codigo", req.codigo)
    result = await tabelas_aux_service.save_rota(
        req.servidor, req.banco, req.codigo, req.descricao, req.prioridade, req.codigo_regiao
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes, {"descricao": req.descricao, "prioridade": req.prioridade, "codigo_regiao": req.codigo_regiao},
            ["descricao", "prioridade", "codigo_regiao"],
        )
        await _log(req, request, tela="ROTAS", comando="GRAVAR", referencia=codigo, descricao=f"Rota '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/rotas/{codigo}/excluir")
async def delete_rota(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "rotas", "codigo", codigo)
    result = await tabelas_aux_service.delete_rota(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "codigo_regiao"])
        await _log(req, request, tela="ROTAS", comando="EXCLUIR", referencia=codigo, descricao=f"Rota '{codigo}' excluída", campos=campos)
    return result


# ==================== Regiões ====================

@router.get("/tabelas/regioes")
async def list_regioes(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_regioes(servidor, banco, search)


@router.post("/tabelas/regioes")
async def save_regiao(req: RegiaoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "regioes", "codigo", req.codigo)
    result = await tabelas_aux_service.save_regiao(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="REGIOES", comando="GRAVAR", referencia=codigo, descricao=f"Região '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/regioes/{codigo}/excluir")
async def delete_regiao(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "regioes", "codigo", codigo)
    result = await tabelas_aux_service.delete_regiao(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="REGIOES", comando="EXCLUIR", referencia=codigo, descricao=f"Região '{codigo}' excluída", campos=campos)
    return result


# ==================== Origem ====================

@router.get("/tabelas/origem")
async def list_origem(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_origem(servidor, banco, search)


@router.post("/tabelas/origem")
async def save_origem(req: OrigemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "origem", "codigo", req.codigo)
    result = await tabelas_aux_service.save_origem(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="ORIGEM", comando="GRAVAR", referencia=req.codigo, descricao=f"Origem '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/origem/{codigo}/excluir")
async def delete_origem(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "origem", "codigo", codigo)
    result = await tabelas_aux_service.delete_origem(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="ORIGEM", comando="EXCLUIR", referencia=codigo, descricao=f"Origem '{codigo}' excluída", campos=campos)
    return result


# ==================== Icms ====================

@router.get("/tabelas/icms")
async def list_icms(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_icms(servidor, banco, search)


@router.post("/tabelas/icms")
async def save_icms(req: IcmsSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "dscr_icms", "cod_icms", req.codigo)
    result = await tabelas_aux_service.save_icms(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="ICMS", comando="GRAVAR", referencia=req.codigo, descricao=f"Icms '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/icms/{codigo}/excluir")
async def delete_icms(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "dscr_icms", "cod_icms", codigo)
    result = await tabelas_aux_service.delete_icms(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="ICMS", comando="EXCLUIR", referencia=codigo, descricao=f"Icms '{codigo}' excluído", campos=campos)
    return result


# ==================== Cores ====================

@router.get("/tabelas/cores")
async def list_cores(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_cores(servidor, banco, search)


@router.post("/tabelas/cores")
async def save_cor(req: CorSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cores", "codigo", req.codigo)
    result = await tabelas_aux_service.save_cor(req.servidor, req.banco, req.codigo, req.descricao, req.cor_fabrica)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes, {"descricao": req.descricao, "cor_fabrica": req.cor_fabrica}, ["descricao", "cor_fabrica"],
        )
        await _log(req, request, tela="CORES", comando="GRAVAR", referencia=codigo, descricao=f"Cor '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/cores/{codigo}/excluir")
async def delete_cor(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cores", "codigo", codigo)
    result = await tabelas_aux_service.delete_cor(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "cor_fabrica"])
        await _log(req, request, tela="CORES", comando="EXCLUIR", referencia=codigo, descricao=f"Cor '{codigo}' excluída", campos=campos)
    return result


# ==================== Grupo Mercadológico ====================

@router.get("/tabelas/grupos-mercadologicos")
async def list_niveis(servidor: str, banco: str):
    return await tabelas_aux_service.list_niveis(servidor, banco)


@router.post("/tabelas/grupos-mercadologicos")
async def save_nivel(req: NivelSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "niveis", "cod_nivel", req.cod_nivel)
    result = await tabelas_aux_service.save_nivel(
        req.servidor, req.banco, req.cod_nivel, req.parent_cod_nivel, req.descricao, req.custo,
        req.classe_entrada, req.sub_classe_entrada, req.classe_saida, req.sub_classe_saida,
    )
    if result.get("success"):
        cod_nivel = result.get("cod_nivel", req.cod_nivel)
        campos = log_auditoria_service.diff_campos(
            antes,
            {
                "descr": req.descricao, "custo": req.custo, "classe_entrada": req.classe_entrada,
                "sub_classe_entrada": req.sub_classe_entrada, "classe_saida": req.classe_saida,
                "sub_classe_saida": req.sub_classe_saida,
            },
            ["descr", "custo", "classe_entrada", "sub_classe_entrada", "classe_saida", "sub_classe_saida"],
        )
        await _log(req, request, tela="GRUPO_MERCAD", comando="GRAVAR", referencia=cod_nivel, descricao=f"Grupo Mercadológico '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/grupos-mercadologicos/{cod_nivel}/excluir")
async def delete_nivel(cod_nivel: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "niveis", "cod_nivel", cod_nivel)
    result = await tabelas_aux_service.delete_nivel(req.servidor, req.banco, cod_nivel)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descr"])
        await _log(req, request, tela="GRUPO_MERCAD", comando="EXCLUIR", referencia=cod_nivel, descricao=f"Grupo Mercadológico #{cod_nivel} excluído", campos=campos)
    return result


# ==================== Grupo de Usuário ====================

@router.get("/tabelas/grupos-usuario")
async def list_grupos_usuario(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_grupos_usuario(servidor, banco, search)


@router.post("/tabelas/grupos-usuario")
async def save_grupo_usuario(req: GrupoUsuarioSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "classes_usuarios", "codigo", req.codigo)
    result = await tabelas_aux_service.save_grupo_usuario(
        req.servidor, req.banco, req.codigo, req.descricao,
        req.exige_tipo_cliente, req.exige_canal_aquisicao_cliente,
        req.visualiza_pedido_aberto, req.visualiza_pedido_fechado,
        req.visualiza_pedido_cancelado, req.visualiza_pedido_faturado,
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos_map = [
            "descricao", "exige_tipo_cliente", "exige_canal_aquisicao_cliente", "visualiza_pedido_aberto",
            "visualiza_pedido_fechado", "visualiza_pedido_cancelado", "visualiza_pedido_faturado",
        ]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="GRUPO_USUARIO", comando="GRAVAR", referencia=codigo, descricao=f"Grupo de Usuário '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/tabelas/grupos-usuario/{codigo}/excluir")
async def delete_grupo_usuario(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "classes_usuarios", "codigo", codigo)
    result = await tabelas_aux_service.delete_grupo_usuario(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="GRUPO_USUARIO", comando="EXCLUIR", referencia=codigo, descricao=f"Grupo de Usuário #{codigo} excluído", campos=campos)
    return result


# ==================== Cfop ====================

@router.get("/tabelas/cfop")
async def list_cfop(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_cfop(servidor, banco, search)


@router.post("/tabelas/cfop")
async def save_cfop(req: CfopSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cfops", "cfop", req.codigo)
    result = await tabelas_aux_service.save_cfop(
        req.servidor, req.banco, req.codigo, req.descricao, req.descricao_nf, req.aplicacao, req.cod_contabil,
    )
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(
            antes,
            {"descricao": req.descricao, "descricao_nf": req.descricao_nf, "aplicacao": req.aplicacao, "cod_contabil": req.cod_contabil},
            ["descricao", "descricao_nf", "aplicacao", "cod_contabil"],
        )
        await _log(req, request, tela="CFOP", comando="GRAVAR", referencia=req.codigo, descricao=f"Cfop '{req.codigo}' gravado", campos=campos)
    return result


@router.post("/tabelas/cfop/{codigo}/excluir")
async def delete_cfop(codigo: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cfops", "cfop", codigo)
    result = await tabelas_aux_service.delete_cfop(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "descricao_nf"])
        await _log(req, request, tela="CFOP", comando="EXCLUIR", referencia=codigo, descricao=f"Cfop '{codigo}' excluído", campos=campos)
    return result


@router.get("/tabelas/cfop-xml")
async def list_cfop_xml(servidor: str, banco: str):
    return await tabelas_aux_service.list_cfop_xml(servidor, banco)


@router.post("/tabelas/cfop-xml")
async def save_cfop_xml(req: CfopXmlSaveRequest, request: Request):
    result = await tabelas_aux_service.save_cfop_xml(req.servidor, req.banco, req.cfop_xml, req.cfop)
    if result.get("success"):
        await _log(req, request, tela="CFOP", comando="VINCULOS_XML", referencia=req.cfop_xml, descricao=f"Vínculo XML '{req.cfop_xml}' -> Cfop '{req.cfop}' gravado")
    return result


@router.post("/tabelas/cfop-xml/{cfop_xml}/excluir")
async def delete_cfop_xml(cfop_xml: str, req: DeleteRequest, request: Request):
    result = await tabelas_aux_service.delete_cfop_xml(req.servidor, req.banco, cfop_xml)
    if result.get("success"):
        await _log(req, request, tela="CFOP", comando="VINCULOS_XML", referencia=cfop_xml, descricao=f"Vínculo XML '{cfop_xml}' excluído")
    return result


# ==================== Cfop x Pis/Cofins ====================

@router.get("/tabelas/cfop-pis-cofins")
async def list_cfop_pis_cofins(servidor: str, banco: str, search: str = ""):
    return await tabelas_aux_service.list_cfop_pis_cofins(servidor, banco, search)


@router.post("/tabelas/cfop-pis-cofins")
async def save_cfop_pis_cofins(req: CfopPisCofinsSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cfop_pis_cofins", "Cod_Auto", req.cod_auto)
    result = await tabelas_aux_service.save_cfop_pis_cofins(
        req.servidor, req.banco, req.cod_auto, req.cfop, req.grupo_pis_cofins, req.tributacao_qtd,
        req.tributacao_pis, req.perc_valor_pis, req.tributacao_cofins, req.perc_valor_cofins, req.acatar_nfe,
    )
    if result.get("success"):
        cod_auto = result.get("cod_auto", req.cod_auto)
        campos_map = [
            "cfop", "grupo_pis_cofins", "tributacao_qtd", "tributacao_pis", "perc_valor_pis",
            "tributacao_cofins", "perc_valor_cofins", "acatar_nfe",
        ]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="CFOP_PISCOF", comando="GRAVAR", referencia=cod_auto, descricao=f"Cfop x Pis/Cofins '{req.cfop}' gravado", campos=campos)
    return result


@router.post("/tabelas/cfop-pis-cofins/{cod_auto}/excluir")
async def delete_cfop_pis_cofins(cod_auto: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "cfop_pis_cofins", "Cod_Auto", cod_auto)
    result = await tabelas_aux_service.delete_cfop_pis_cofins(req.servidor, req.banco, cod_auto)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["cfop", "grupo_pis_cofins"])
        await _log(req, request, tela="CFOP_PISCOF", comando="EXCLUIR", referencia=cod_auto, descricao=f"Cfop x Pis/Cofins #{cod_auto} excluído", campos=campos)
    return result


# ==================== FIPE (utilitário — sem log de auditoria por ora) ====================

@router.get("/fipe/marcas")
async def fipe_marcas(tipo: str = "carros"):
    return await tabelas_aux_service.fipe_marcas(tipo)


@router.get("/fipe/modelos")
async def fipe_modelos(tipo: str, marca_id: str):
    return await tabelas_aux_service.fipe_modelos(tipo, marca_id)


@router.post("/tabelas/marcas/importar-fipe")
async def import_fipe(req: ImportFipeRequest):
    return await tabelas_aux_service.import_fipe(req.servidor, req.banco, req.tipo, req.fipe_marca_id, req.descricao)


# ==================== Taxas ====================
# Ver nota grande em `tabelas_aux_service.CAMPOS_TAXAS` sobre o campo
# "Não Contribuinte" do legado gravar de fato na coluna `Simples_Nacional`.
#
# Duas variantes da mesma tela/rotina (pedido explícito do usuário: não criar
# duas telas): "nfe" grava em `taxas`, "nfce" em `taxas_nfce` — ver
# `tabelas_aux_service.TAXA_VARIANTES` pra config de tabela/PK/campos por
# variante. Permissão e log de auditoria ficam separados por variante
# (TAXAS.* / tela "TAXAS" pra NFe, TAXAS_NFCE.* / tela "TAXAS_NFCE" pra
# NFCe) — pedido explícito do usuário, pra poder liberar uma sem a outra.


class TaxaDeleteRequest(AuditFields):
    servidor: str
    banco: str
    variante: str = "nfe"


class TaxaSaveRequest(AuditFields):
    servidor: str
    banco: str
    variante: str = "nfe"  # "nfe" (tabela `taxas`) ou "nfce" (tabela `taxas_nfce`)
    sequencia: Optional[int] = None
    destino: str
    cfop: str
    cod_icms: str
    tipo_mov: str
    Simples_Nacional: bool = False
    consumidor_final: bool = False
    tributacao: Optional[str] = None
    icms: Optional[float] = 0
    reducao_base_icms: Optional[float] = 0
    icms_substituicao: Optional[float] = 0
    margem_icms_substituicao: Optional[float] = 0
    reducao_base_retido: Optional[float] = 0
    ALQT_FCP: Optional[float] = 0
    ALQT_FCP_RETIDO: Optional[float] = 0
    ALQT_FCP_ST: Optional[float] = 0
    ALQT_CF: Optional[float] = 0
    ALQT_CRED_SN: Optional[float] = 0
    protocolo_st: bool = False
    tipo_ipi: bool = False
    INFORMA_BENEFICIO_FISCAL: bool = False
    REDUCAO_BASE_PIS_COFINS: bool = False
    CST_TRIB_PIS: Optional[str] = None
    ALQT_TRIB_PIS: Optional[float] = 0
    CST_TRIB_COFINS: Optional[str] = None
    ALQT_TRIB_COFINS: Optional[float] = 0
    PIS_COFINS_CUSTO_X_VENDA: bool = False
    ALQT_ICMS_EFETIVO: Optional[float] = 0
    MARGEM_ICMS_EFETIVO: Optional[float] = 0
    REDUCAO_ICMS_EFETIVO: Optional[float] = 0
    ICMS_SUBSTITUTO: Optional[float] = 0
    dif_icms_bens: Optional[float] = 0
    ALQT_ICMS_DESONERADO: Optional[float] = 0
    MOTIVO_ICMS_DESONERADO: Optional[str] = None
    aliquota_interestadual: Optional[float] = 0
    aliquota_interna_destino: Optional[float] = 0
    percentual_origem: Optional[float] = 0
    fundo_pobreza: Optional[float] = 0
    # Reforma Tributária (IBS/CBS/IS)
    INFORMA_CBS_IBS: bool = False
    CST_IS: Optional[str] = None
    CCLASSTRIB_IS: Optional[str] = None
    ALQT_IS: Optional[float] = 0
    CST_IBS: Optional[str] = None
    CCLASSTRIB_IBS: Optional[str] = None
    ALQT_IBS_ESTADO: Optional[float] = 0
    GRUPO_DIFERIMENTO_IBS_ESTADO: bool = False
    PERC_DIFERIMENTO_IBS_ESTADO: Optional[float] = 0
    GRUPO_REDUCAO_IBS_ESTADO: bool = False
    PERC_REDUCAO_IBS_ESTADO: Optional[float] = 0
    ALQT_EFETIVA_REDUCAO_IBS_ESTADO: Optional[float] = 0
    ALQT_IBS_MUNICIPIO: Optional[float] = 0
    GRUPO_DIFERIMENTO_IBS_MUNICIPIO: bool = False
    PERC_DIFERIMENTO_IBS_MUNICIPIO: Optional[float] = 0
    GRUPO_REDUCAO_IBS_MUNICIPIO: bool = False
    PERC_REDUCAO_IBS_MUNICIPIO: Optional[float] = 0
    ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO: Optional[float] = 0
    ALQT_CBS_ESTADO: Optional[float] = 0
    GRUPO_DIFERIMENTO_CBS_ESTADO: bool = False
    PERC_DIFERIMENTO_CBS_ESTADO: Optional[float] = 0
    GRUPO_REDUCAO_CBS_ESTADO: bool = False
    PERC_REDUCAO_CBS_ESTADO: Optional[float] = 0
    ALQT_EFETIVA_REDUCAO_CBS_ESTADO: Optional[float] = 0
    GTRIBREGULAR: bool = False
    gMonoPadrao: bool = False
    gMonoReten: bool = False
    gMonoRet: bool = False
    gMonoDif: bool = False
    ALQT_ADREM_PADRAO_IBS: Optional[float] = 0
    ALQT_ADREM_PADRAO_CBS: Optional[float] = 0
    ALQT_ADREM_RETENCAO_IBS: Optional[float] = 0
    ALQT_ADREM_RETENCAO_CBS: Optional[float] = 0
    ALQT_ADREM_RETIDO_IBS: Optional[float] = 0
    ALQT_ADREM_RETIDO_CBS: Optional[float] = 0
    ALQT_ADREM_DIFERIMENTO_IBS: Optional[float] = 0
    ALQT_ADREM_DIFERIMENTO_CBS: Optional[float] = 0


# ==================== Especialidades (CRUD embutido em Funcionários) ====================
# Legado: FrmCadEsp, aberto de dentro de FrmManPro. Listagem somente-leitura
# já existe em `GET /api/especialidades` (lookups_service) — aqui só
# save/delete. Log de auditoria sob a própria tela FUNCIONARIOS (comando
# ESPECIALIDADE), mesmo padrão já usado pra Lista Negra dentro de Clientes.

class EspecialidadeSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


@router.post("/tabelas/especialidades")
async def save_especialidade(req: EspecialidadeSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "especialidades", "codigo_especialidade", req.codigo) if req.codigo else None
    result = await tabelas_aux_service.save_especialidade(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="FUNCIONARIOS", comando="ESPECIALIDADE", referencia=codigo, descricao=f"Especialidade '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/tabelas/especialidades/{codigo}/excluir")
async def delete_especialidade(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "especialidades", "codigo_especialidade", codigo)
    result = await tabelas_aux_service.delete_especialidade(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="FUNCIONARIOS", comando="ESPECIALIDADE", referencia=codigo, descricao=f"Especialidade #{codigo} excluída", campos=campos)
    return result


@router.get("/tabelas/taxas")
async def list_taxas(servidor: str, banco: str, variante: str = "nfe", tipo_mov: str = "", destino: str = "", cod_icms: str = ""):
    return await tabelas_aux_service.list_taxas(servidor, banco, variante, tipo_mov, destino, cod_icms)


@router.get("/tabelas/taxas-opcoes-filtro")
async def list_taxas_opcoes_filtro(servidor: str, banco: str, variante: str = "nfe", tipo_mov: str = "", destino: str = ""):
    return await tabelas_aux_service.list_taxas_opcoes_filtro(servidor, banco, variante, tipo_mov, destino)


@router.get("/tabelas/taxas/{sequencia}")
async def get_taxa(sequencia: int, servidor: str, banco: str, variante: str = "nfe"):
    return await tabelas_aux_service.get_taxa(servidor, banco, variante, sequencia)


@router.post("/tabelas/taxas")
async def save_taxa(req: TaxaSaveRequest, request: Request):
    cfg = tabelas_aux_service.TAXA_VARIANTES.get(req.variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, cfg["tabela"], cfg["pk"], req.sequencia) if req.sequencia else None
    dados = req.model_dump(exclude={"servidor", "banco", "variante", "sequencia"})
    result = await tabelas_aux_service.save_taxa(req.servidor, req.banco, req.variante, req.sequencia, dados)
    if result.get("success"):
        sequencia = result.get("sequencia", req.sequencia)
        campos = log_auditoria_service.diff_campos(antes, dados, cfg["campos"])
        ref = f"{req.destino}/{req.cfop}/{req.cod_icms}/{req.tipo_mov}"
        tela = "TAXAS" if req.variante == "nfe" else "TAXAS_NFCE"
        rotulo = "Taxa" if req.variante == "nfe" else "Taxa NFCe"
        await _log(req, request, tela=tela, comando="GRAVAR", referencia=sequencia, descricao=f"{rotulo} '{ref}' gravada", campos=campos)
    return result


@router.post("/tabelas/taxas/{sequencia}/excluir")
async def delete_taxa(sequencia: int, req: TaxaDeleteRequest, request: Request):
    cfg = tabelas_aux_service.TAXA_VARIANTES.get(req.variante)
    if not cfg:
        return {"success": False, "message": "Variante de taxa inválida."}
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, cfg["tabela"], cfg["pk"], sequencia)
    result = await tabelas_aux_service.delete_taxa(req.servidor, req.banco, req.variante, sequencia)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["destino", "cfop", "cod_icms", "tipo_mov"])
        tela = "TAXAS" if req.variante == "nfe" else "TAXAS_NFCE"
        rotulo = "Taxa" if req.variante == "nfe" else "Taxa NFCe"
        await _log(req, request, tela=tela, comando="EXCLUIR", referencia=sequencia, descricao=f"{rotulo} #{sequencia} excluída", campos=campos)
    return result


@router.get("/tabelas/dscr-icms")
async def list_dscr_icms(servidor: str, banco: str):
    return await tabelas_aux_service.list_dscr_icms(servidor, banco)


@router.get("/tabelas/classtrib/lookup")
async def classtrib_lookup(servidor: str, banco: str, cst: str, cclasstrib: str):
    return await tabelas_aux_service.classtrib_lookup(servidor, banco, cst, cclasstrib)


@router.get("/tabelas/classtrib/opcoes")
async def list_classtrib_opcoes(servidor: str, banco: str, cst: str = ""):
    return await tabelas_aux_service.list_classtrib_opcoes(servidor, banco, cst)
