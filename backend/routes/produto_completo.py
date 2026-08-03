"""Rotas do Cadastro de Produtos (completo) — ver services/produto_completo_service.py
e services/tray_service.py para o desenho completo (mapeamento de campos,
regras de negócio, integração Tray)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import produto_completo_service, tray_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class FornecedorItem(BaseModel):
    fornecedor: int
    sequencia: int = 0


class SimilarItem(BaseModel):
    equivalente: str


class SecundarioItem(BaseModel):
    peca_secundaria: str


class XmlVinculoItem(BaseModel):
    codigo_xml: str = ""
    fornecedor_xml: Optional[int] = None


class ProdutoDados(BaseModel):
    # Dados Principais
    codigo_fab: str = ""
    codigo_bar: str = ""
    codigo_mercosul: str = ""
    descricao: str = ""
    descricao_pdv: str = ""
    descricao_embarque: str = ""
    descricao_nf: str = ""
    Descricao_Completa: str = ""
    p_custo: float = 0
    p_venda: float = 0
    p_sugestao: float = 0
    p_garantia: float = 0
    p_sugerido: float = 0
    preco_base: float = 0
    preco_promocional: float = 0
    preco_lista: float = 0
    preco_variado: bool = False
    cod_anp: str = ""
    marca_produto: str = ""
    modelo_produto: str = ""
    fornecedor: Optional[int] = None
    nivel1: str = ""
    nivel2: str = ""
    nivel3: str = ""
    nivel4: str = ""
    nivel5: str = ""
    Produto_web: bool = False
    FRETE_GRATIS_SITE: bool = False
    situacao: str = "A"
    # Descontos e Comissões
    desc_g: float = 0
    desc_s: float = 0
    desc_v: float = 0
    comissao: float = 0
    comissao_a: float = 0
    comissao_e: float = 0
    valor_comissao: float = 0
    Valor_Comissão_E: float = 0
    Valor_Comissão_A: float = 0
    valor_desc_base_comissao: float = 0
    valor_desc_base_comissao_e: float = 0
    valor_desc_base_comissao_a: float = 0
    paga_comissao: bool = True
    aceita_desconto: bool = True
    politica_preco: str = ""
    # Configurações Fiscais
    codigo_cest: str = ""
    BENEFICIO_FISCAL: str = ""
    origem: str = "0"
    perc_ipi: float = 0
    valor_ipi: float = 0
    cst_ipi_entrada: str = ""
    cst_ipi_saida: str = ""
    ENQUADRAMENTO_IPI: str = ""
    cod_icms: str = ""
    cod_grupo_pis_cofins: str = ""
    tributacao_pis: Optional[int] = None
    perc_valor_pis: float = 0
    tributacao_cofins: Optional[int] = None
    perc_valor_cofins: float = 0
    outros_trib_federais: float = 0
    IBPT_FEDERAIS: float = 0
    IBPT_ESTADUAIS: float = 0
    valor_substituicao: float = 0
    perc_mva: float = 0
    # Dados Secundários
    unidade_medida: str = ""
    comprimento: float = 0
    largura: float = 0
    altura: float = 0
    peso_liquido: float = 0
    peso_bruto: float = 0
    un_compra: str = ""
    qtd_un_compra: float = 0
    un_embarque: str = ""
    qtd_un_embarque: float = 0
    QTD_UN_VENDA: float = 0
    un_fracao: str = ""
    prazo_entrega: Optional[int] = None
    prazo_fornecedor: Optional[int] = None
    prazo_garantia: Optional[int] = None
    tipo_garantia: Optional[int] = None
    estoque_minimo: float = 0
    estoque_maximo: float = 0
    estoque_ressuprimento: float = 0
    area: Optional[int] = None
    prateleira: str = ""
    escaninho: Optional[int] = None
    tipo: Optional[int] = None
    tipo_peca: Optional[int] = None
    indice_preco: str = ""
    custo_inventario: float = 0
    custo_reposicao: float = 0
    desconto_compra: float = 0
    percent_frete: float = 0
    valor_frete: float = 0
    margem_lucro: float = 0
    margem_tabela: float = 0
    pontuacao_a: Optional[int] = None
    pontuacao_e: Optional[int] = None
    pontuacao_v: Optional[int] = None
    controla_num_serie: bool = False
    peso_variado: bool = False
    # Livro (só gravado se controle_configuracao.Livraria estiver ligado)
    autor: Optional[int] = None
    serie: Optional[int] = None
    sinopse: str = ""
    lancamento: bool = False
    esgotado: bool = False
    # Relacionamentos
    fornecedores: list[FornecedorItem] = []
    similares: list[SimilarItem] = []
    secundarios: list[SecundarioItem] = []
    xml_vinculos: list[XmlVinculoItem] = []
    protocolo_st: list[str] = []


class ProdutoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo_int: Optional[str] = None
    dados: ProdutoDados


class ProdutoDeleteRequest(AuditFields):
    servidor: str
    banco: str


class GradeCombinacao(BaseModel):
    cor: str
    tamanho: str = ""


class GradeCreateRequest(AuditFields):
    servidor: str
    banco: str
    combinacoes: list[GradeCombinacao]


class TraySyncRequest(AuditFields):
    servidor: str
    banco: str
    id_tray_existente: Optional[int] = None


class PrecoQtdSaveRequest(AuditFields):
    servidor: str
    banco: str
    qtd: float
    p_venda: float


class PrecoQtdDeleteRequest(AuditFields):
    servidor: str
    banco: str
    qtd: float


class PromocaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    sequencia: Optional[int] = None
    qtd: float
    p_venda: float
    codigo_promocao: str = ""
    descricao_promocao: str = ""
    # Período opcional, combinável — tudo em branco = promoção sem
    # restrição de período (sempre válida, comportamento anterior a esta
    # extensão). Ver docstring de `_ensure_promocao_periodo_cols`.
    dias_semana: str = ""  # "0,1,2,3,4,5,6" (0=domingo..6=sábado), "" = todos os dias
    data_inicio: Optional[str] = None  # ISO yyyy-mm-dd
    data_fim: Optional[str] = None
    hora_inicio: str = ""  # "HH:MM"
    hora_fim: str = ""


class PromocaoDeleteRequest(AuditFields):
    servidor: str
    banco: str
    sequencia: int


class DiasSemanaWebSaveRequest(AuditFields):
    """Botão "Dias da Semana" ao lado do checkbox "Produto Web" — só
    habilitado com `Produto_web=True`. Configura em quais dias da semana
    este produto aparece no cardápio do Web Convidado (módulo ainda em
    fase de análise, ver WebConvidado.md — este cadastro em si foi
    liberado pro usuário implementar desde já, 2026-07-30)."""
    servidor: str
    banco: str
    dias: list[int] = []


@router.get("/produto-completo")
async def list_produtos(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20):
    return await produto_completo_service.list_produtos(servidor, banco, search, page, size)


@router.get("/produto-completo/{codigo_int}")
async def get_produto(codigo_int: str, servidor: str, banco: str):
    return await produto_completo_service.get_produto(servidor, banco, codigo_int)


@router.post("/produto-completo")
async def save_produto(req: ProdutoSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await produto_completo_service.save_produto(req.servidor, req.banco, req.codigo_int, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo_int")),
            descricao=f"Produto {req.dados.descricao} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produto-completo/{codigo_int}/excluir")
async def delete_produto(codigo_int: str, req: ProdutoDeleteRequest, request: Request):
    result = await produto_completo_service.delete_produto(req.servidor, req.banco, codigo_int)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Produto {codigo_int} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/produto-completo/{codigo_int}/grade/cores")
async def list_cores_grade(codigo_int: str, servidor: str, banco: str):
    return await produto_completo_service.list_cores_grade(servidor, banco, codigo_int)


@router.post("/produto-completo/{codigo_int}/grade")
async def criar_itens_grade(codigo_int: str, req: GradeCreateRequest, request: Request):
    combinacoes = [c.model_dump() for c in req.combinacoes]
    result = await produto_completo_service.criar_itens_grade(req.servidor, req.banco, codigo_int, combinacoes)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="GRADE",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"{len(result.get('itens') or [])} item(ns) de grade gerado(s) para {codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produto-completo/{codigo_int}/enviar-site")
async def enviar_site(codigo_int: str, req: TraySyncRequest, request: Request):
    upload = await tray_service.upload_imagens_pendentes(req.servidor, req.banco, codigo_int)
    result = await tray_service.cadastrar_ou_atualizar_produto(
        req.servidor, req.banco, codigo_int, req.id_tray_existente
    )
    result["upload_imagens"] = upload
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="ENVIAR_SITE",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Produto {codigo_int} enviado à Tray (id_tray={result.get('id_tray')}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/produto-completo/{codigo_int}/preco-qtd")
async def list_preco_qtd(codigo_int: str, servidor: str, banco: str):
    return await produto_completo_service.list_preco_qtd(servidor, banco, codigo_int)


@router.post("/produto-completo/{codigo_int}/preco-qtd")
async def save_preco_qtd(codigo_int: str, req: PrecoQtdSaveRequest, request: Request):
    result = await produto_completo_service.save_preco_qtd(req.servidor, req.banco, codigo_int, req.qtd, req.p_venda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="PRECO_QTD",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Preço por quantidade ({req.qtd}) gravado para {codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produto-completo/{codigo_int}/preco-qtd/excluir")
async def delete_preco_qtd(codigo_int: str, req: PrecoQtdDeleteRequest, request: Request):
    result = await produto_completo_service.delete_preco_qtd(req.servidor, req.banco, codigo_int, req.qtd)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="PRECO_QTD_EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Preço por quantidade ({req.qtd}) excluído de {codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/produto-completo/{codigo_int}/promocoes")
async def list_promocoes(codigo_int: str, servidor: str, banco: str):
    return await produto_completo_service.list_promocoes(servidor, banco, codigo_int)


@router.post("/produto-completo/{codigo_int}/promocoes")
async def save_promocao(codigo_int: str, req: PromocaoSaveRequest, request: Request):
    result = await produto_completo_service.save_promocao(
        req.servidor, req.banco, codigo_int, req.sequencia, req.qtd, req.p_venda,
        req.codigo_promocao, req.descricao_promocao,
        req.dias_semana, req.data_inicio, req.data_fim, req.hora_inicio, req.hora_fim,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="PROMOCAO",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Promoção gravada para {codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produto-completo/{codigo_int}/promocoes/excluir")
async def delete_promocao(codigo_int: str, req: PromocaoDeleteRequest, request: Request):
    result = await produto_completo_service.delete_promocao(req.servidor, req.banco, req.sequencia)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="PROMOCAO_EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Promoção (sequência {req.sequencia}) excluída de {codigo_int}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/produto-completo/{codigo_int}/dias-semana-web")
async def list_dias_semana_web(codigo_int: str, servidor: str, banco: str):
    return await produto_completo_service.list_dias_semana_web(servidor, banco, codigo_int)


@router.post("/produto-completo/{codigo_int}/dias-semana-web")
async def save_dias_semana_web(codigo_int: str, req: DiasSemanaWebSaveRequest, request: Request):
    result = await produto_completo_service.save_dias_semana_web(req.servidor, req.banco, codigo_int, req.dias)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="DIAS_SEMANA_WEB",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo_int,
            descricao=f"Dias da Semana (Web Convidado) gravados para {codigo_int}: {req.dias}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
