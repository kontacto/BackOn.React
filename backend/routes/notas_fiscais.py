"""Rotas de Cadastros > Notas Fiscais.

Gravar cabeçalho / criticar / cancelar / excluir são registrados em
`log_auditoria` — mesmo padrão das demais telas desta sessão. Itens,
vencimentos, resumo tributário e centro de custo usam o padrão
replace-all-on-save (mesmo padrão de Telefones/Endereços/Contatos em
Cliente Completo) e não geram log próprio — o log do cabeçalho já cobre
a intenção de "gravar a nota".
"""
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, notas_fiscais_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class CabecalhoRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    num_nf: Optional[float] = None
    serie_nf: Optional[str] = None
    fornecedor: Optional[int] = None
    mov: Optional[str] = None
    cfop: Optional[str] = None
    uf: Optional[str] = None
    data_nf: Optional[str] = None
    data_mov: Optional[str] = None
    data_saida: Optional[str] = None
    valor_total: Optional[float] = None
    base_icms: Optional[float] = None
    valor_icms: Optional[float] = None
    base_ipi: Optional[float] = None
    valor_ipi: Optional[float] = None
    base_iss: Optional[float] = None
    valor_iss: Optional[float] = None
    base_sub: Optional[float] = None
    valor_sub: Optional[float] = None
    frete: Optional[float] = None
    seguro: Optional[float] = None
    despesas: Optional[float] = None
    desconto: Optional[float] = None
    base_fcp: Optional[float] = None
    valor_fcp: Optional[float] = None
    base_fcp_retido: Optional[float] = None
    valor_fcp_retido: Optional[float] = None
    base_fcp_st: Optional[float] = None
    valor_fcp_st: Optional[float] = None
    livro: Optional[str] = None
    pagar: Optional[str] = None
    contabilidade: Optional[str] = None
    num_lcto_contabil: Optional[int] = None
    tipo_doc: Optional[int] = None
    especie: Optional[str] = None
    selo_fiscal: Optional[str] = None
    passe_fiscal: Optional[str] = None
    chave_acesso: Optional[str] = None
    protocolo_sefaz: Optional[str] = None
    obs: Optional[str] = None
    obs_livro: Optional[str] = None
    cupom_fiscal: Optional[bool] = None


def _cabecalho_dados(req: CabecalhoRequest) -> dict:
    return {
        "num_nf": req.num_nf, "serie_nf": req.serie_nf, "fornecedor": req.fornecedor,
        "mov": req.mov, "cfop": req.cfop, "uf": req.uf,
        "data_nf": req.data_nf, "data_mov": req.data_mov, "data_saida": req.data_saida,
        "valor_total": req.valor_total, "base_icms": req.base_icms, "valor_icms": req.valor_icms,
        "base_ipi": req.base_ipi, "valor_ipi": req.valor_ipi,
        "base_iss": req.base_iss, "valor_iss": req.valor_iss,
        "base_sub": req.base_sub, "valor_sub": req.valor_sub,
        "frete": req.frete, "seguro": req.seguro, "despesas": req.despesas, "desconto": req.desconto,
        "BASE_FCP": req.base_fcp, "VALOR_FCP": req.valor_fcp,
        "BASE_FCP_RETIDO": req.base_fcp_retido, "VALOR_FCP_RETIDO": req.valor_fcp_retido,
        "BASE_FCP_ST": req.base_fcp_st, "VALOR_FCP_ST": req.valor_fcp_st,
        "livro": req.livro, "pagar": req.pagar, "contabilidade": req.contabilidade,
        "num_lcto_contabil": req.num_lcto_contabil,
        "tipo_doc": req.tipo_doc, "especie": req.especie,
        "selo_fiscal": req.selo_fiscal, "passe_fiscal": req.passe_fiscal,
        "chave_acesso": req.chave_acesso, "protocolo_sefaz": req.protocolo_sefaz,
        "obs": req.obs, "obs_livro": req.obs_livro, "cupom_fiscal": req.cupom_fiscal,
    }


class ItemModel(BaseModel):
    codigo_int: str
    cod_fiscal: Optional[str] = None
    cod_contabil: Optional[int] = None
    tributacao: Optional[str] = None
    qtd: float
    qtd_un_compra: Optional[float] = None
    p_unit: float
    desconto: Optional[float] = 0
    valor_total: float
    alqt_icms: Optional[float] = None
    reducao_base_icms: Optional[float] = None
    base_icms: Optional[float] = None
    valor_icms: Optional[float] = None
    base_ipi: Optional[float] = None
    alqt_ipi: Optional[float] = None
    valor_ipi: Optional[float] = None
    base_sub: Optional[float] = None
    valor_sub: Optional[float] = None
    base_iss: Optional[float] = None
    valor_iss: Optional[float] = None
    frete: Optional[float] = None
    seguro: Optional[float] = None
    despesas: Optional[float] = None
    tributacao_pis: Optional[int] = None
    base_pis: Optional[float] = None
    alqt_pis: Optional[float] = None
    valor_pis: Optional[float] = None
    tributacao_cofins: Optional[int] = None
    base_cofins: Optional[float] = None
    alqt_cofins: Optional[float] = None
    valor_cofins: Optional[float] = None


class ItensRequest(AuditFields):
    servidor: str
    banco: str
    itens: List[ItemModel]


class VencimentoModel(BaseModel):
    data_venc: str
    valor: float


class VencimentosRequest(AuditFields):
    servidor: str
    banco: str
    vencimentos: List[VencimentoModel]


class ResumoTributarioModel(BaseModel):
    cod_fiscal: Optional[str] = None
    cod_contabil: Optional[int] = None
    tributacao: Optional[int] = None
    alqt_icms: Optional[int] = None
    valor_contabil: Optional[float] = None
    valor_base: Optional[float] = None
    valor_icms: Optional[float] = None
    valor_base_retido: Optional[float] = None
    valor_icms_retido: Optional[float] = None
    valor_base_recolher: Optional[float] = None
    valor_icms_recolher: Optional[float] = None
    dif_icms_bens: Optional[int] = None
    reducao_base_icms: Optional[float] = None
    transf_contab: Optional[bool] = None
    obs: Optional[str] = None


class ResumoTributarioRequest(AuditFields):
    servidor: str
    banco: str
    linhas: List[ResumoTributarioModel]


class CentroCustoModel(BaseModel):
    custo: Optional[int] = None
    valor_contabil: Optional[float] = None
    valor_icms: Optional[float] = None
    valor_icms_retido: Optional[float] = None
    dif_icms_bens: Optional[int] = None
    nf_classe: Optional[int] = None
    nf_sub_classe: Optional[int] = None


class CentroCustoRequest(AuditFields):
    servidor: str
    banco: str
    linhas: List[CentroCustoModel]


class SelecionarRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    num_nf: Optional[float] = None
    serie_nf: Optional[str] = None
    valor_total: Optional[float] = None
    cfop: Optional[str] = None
    mov: Optional[str] = None
    entrada: Optional[bool] = None
    saida: Optional[bool] = None
    situacao: Optional[str] = None
    tipo_pessoa: Optional[str] = None
    cliente_fornecedor_termo: Optional[str] = None
    data_nf_de: Optional[str] = None
    data_nf_ate: Optional[str] = None
    data_mov_de: Optional[str] = None
    data_mov_ate: Optional[str] = None


@router.get("/notas-fiscais/produto/{codigo_int}")
async def buscar_produto(codigo_int: str, servidor: str, banco: str):
    return await notas_fiscais_service.buscar_produto(servidor, banco, codigo_int)


@router.get("/notas-fiscais/{codigo}")
async def get(codigo: int, servidor: str, banco: str):
    return await notas_fiscais_service.get(servidor, banco, codigo)


@router.post("/notas-fiscais/cabecalho")
async def save_cabecalho(req: CabecalhoRequest, request: Request):
    result = await notas_fiscais_service.save_cabecalho(req.servidor, req.banco, req.codigo, _cabecalho_dados(req))
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="NOTAS_FISCAIS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Nota Fiscal nº {req.num_nf}/{req.serie_nf} gravada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/notas-fiscais/{codigo}/itens")
async def save_itens(codigo: int, req: ItensRequest):
    return await notas_fiscais_service.save_itens(req.servidor, req.banco, codigo, [i.model_dump() for i in req.itens])


@router.post("/notas-fiscais/{codigo}/vencimentos")
async def save_vencimentos(codigo: int, req: VencimentosRequest):
    return await notas_fiscais_service.save_vencimentos(req.servidor, req.banco, codigo, [v.model_dump() for v in req.vencimentos])


@router.post("/notas-fiscais/{codigo}/resumo-tributario")
async def save_resumo_tributario(codigo: int, req: ResumoTributarioRequest):
    return await notas_fiscais_service.save_resumo_tributario(req.servidor, req.banco, codigo, [r.model_dump() for r in req.linhas])


@router.post("/notas-fiscais/{codigo}/centro-custo")
async def save_centro_custo(codigo: int, req: CentroCustoRequest):
    return await notas_fiscais_service.save_centro_custo(req.servidor, req.banco, codigo, [r.model_dump() for r in req.linhas])


@router.post("/notas-fiscais/selecionar")
async def selecionar(req: SelecionarRequest):
    filtros = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    return await notas_fiscais_service.list_consulta(req.servidor, req.banco, filtros)


@router.post("/notas-fiscais/{codigo}/criticar")
async def criticar(codigo: int, servidor: str, banco: str):
    return await notas_fiscais_service.criticar(servidor, banco, codigo)


class AcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.post("/notas-fiscais/{codigo}/cancelar")
async def cancelar(codigo: int, req: AcaoRequest, request: Request):
    result = await notas_fiscais_service.cancelar(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="NOTAS_FISCAIS", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Nota Fiscal #{codigo} cancelada",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/notas-fiscais/{codigo}")
async def excluir(codigo: int, req: AcaoRequest, request: Request):
    result = await notas_fiscais_service.excluir(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="NOTAS_FISCAIS", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Nota Fiscal #{codigo} excluída",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
