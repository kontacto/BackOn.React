"""Rotas do módulo Contratos (Transações > Contratos) — ver
`services/contratos_service.py` pro racional completo e escopo da Fase A.

Auditoria: mesmo padrão de `routes/tabelas_aux.py` — busca o registro atual
pelo PK antes de chamar o service, compara com os valores novos do request e
grava o diff campo-a-campo via `log_auditoria_service`. Best-effort, nunca
impede a operação.
"""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import contratos_service, log_auditoria_service

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


class LookupSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


# ==================== Tipo de Contrato ====================

@router.get("/contratos/tipo-contrato")
async def list_tipo_contrato(servidor: str, banco: str, search: str = ""):
    return await contratos_service.list_tipo_contrato(servidor, banco, search)


@router.post("/contratos/tipo-contrato")
async def save_tipo_contrato(req: LookupSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_contrato", "codigo", req.codigo)
    result = await contratos_service.save_tipo_contrato(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_CONTRATO", comando="GRAVAR", referencia=result.get("codigo"), descricao=f"Tipo de Contrato '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/contratos/tipo-contrato/{codigo}/excluir")
async def delete_tipo_contrato(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "tipo_contrato", "codigo", codigo)
    result = await contratos_service.delete_tipo_contrato(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_CONTRATO", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Contrato '{codigo}' excluído", campos=campos)
    return result


# ==================== Tipo de Reajuste ====================

@router.get("/contratos/tipo-reajuste")
async def list_tipo_reajuste(servidor: str, banco: str, search: str = ""):
    return await contratos_service.list_tipo_reajuste(servidor, banco, search)


@router.post("/contratos/tipo-reajuste")
async def save_tipo_reajuste(req: LookupSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "prazo_reajuste", "codigo", req.codigo)
    result = await contratos_service.save_tipo_reajuste(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="TIPO_REAJUSTE", comando="GRAVAR", referencia=result.get("codigo"), descricao=f"Tipo de Reajuste '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/contratos/tipo-reajuste/{codigo}/excluir")
async def delete_tipo_reajuste(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "prazo_reajuste", "codigo", codigo)
    result = await contratos_service.delete_tipo_reajuste(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="TIPO_REAJUSTE", comando="EXCLUIR", referencia=codigo, descricao=f"Tipo de Reajuste '{codigo}' excluído", campos=campos)
    return result


# ==================== Índice de Reajuste ====================

@router.get("/contratos/indice-reajuste")
async def list_indice_reajuste(servidor: str, banco: str, search: str = ""):
    return await contratos_service.list_indice_reajuste(servidor, banco, search)


@router.post("/contratos/indice-reajuste")
async def save_indice_reajuste(req: LookupSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "indice_reajuste", "codigo", req.codigo)
    result = await contratos_service.save_indice_reajuste(req.servidor, req.banco, req.codigo, req.descricao)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao}, ["descricao"])
        await _log(req, request, tela="INDICE_REAJUSTE", comando="GRAVAR", referencia=result.get("codigo"), descricao=f"Índice de Reajuste '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/contratos/indice-reajuste/{codigo}/excluir")
async def delete_indice_reajuste(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "indice_reajuste", "codigo", codigo)
    result = await contratos_service.delete_indice_reajuste(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="INDICE_REAJUSTE", comando="EXCLUIR", referencia=codigo, descricao=f"Índice de Reajuste '{codigo}' excluído", campos=campos)
    return result


@router.get("/contratos/indice-reajuste/{codigo}/bacen")
async def consultar_indice_bacen(codigo: int, servidor: str, banco: str, data_inicial: str, data_fim: str):
    return await contratos_service.consultar_indice_bacen(servidor, banco, codigo, data_inicial, data_fim)


# ==================== Produtos Disponíveis ====================

class ProdutoDisponivelSaveRequest(AuditFields):
    servidor: str
    banco: str
    produto: str
    preco: float = 0
    qtd: float = 0
    situacao: str = "A"
    obs: str = ""


@router.get("/contratos/produtos-disponiveis")
async def list_produtos_disponiveis(servidor: str, banco: str, search: str = ""):
    return await contratos_service.list_produtos_disponiveis(servidor, banco, search)


@router.get("/contratos/resolver-produto")
async def resolver_produto(servidor: str, banco: str, termo: str):
    return await contratos_service.resolver_produto(servidor, banco, termo)


@router.post("/contratos/produtos-disponiveis")
async def save_produto_disponivel(req: ProdutoDisponivelSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "contratos_produtos_disponiveis", "produto", req.produto)
    result = await contratos_service.save_produto_disponivel(req.servidor, req.banco, req.produto, req.preco, req.qtd, req.situacao, req.obs)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"preco": req.preco, "qtd": req.qtd, "situacao": req.situacao, "obs": req.obs}, ["preco", "qtd", "situacao", "obs"])
        await _log(req, request, tela="CONTR_PROD_DISP", comando="GRAVAR", referencia=result.get("produto"), descricao=f"Produto Disponível '{result.get('produto')}' gravado", campos=campos)
    return result


@router.post("/contratos/produtos-disponiveis/{produto}/excluir")
async def delete_produto_disponivel(produto: str, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "contratos_produtos_disponiveis", "produto", produto)
    result = await contratos_service.delete_produto_disponivel(req.servidor, req.banco, produto)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["preco", "qtd", "situacao", "obs"])
        await _log(req, request, tela="CONTR_PROD_DISP", comando="EXCLUIR", referencia=produto, descricao=f"Produto Disponível '{produto}' excluído", campos=campos)
    return result


# ==================== Contratos ====================

@router.get("/contratos/lookups")
async def lookups_contrato(servidor: str, banco: str):
    return await contratos_service.lookups_contrato(servidor, banco)


@router.get("/contratos")
async def list_contratos(servidor: str, banco: str, search: str = "", situacao: str = "", page: int = 1, size: int = 30):
    return await contratos_service.list_contratos(servidor, banco, search, situacao, page, size)


@router.get("/contratos/{codigo}")
async def get_contrato(codigo: int, servidor: str, banco: str):
    return await contratos_service.get_contrato(servidor, banco, codigo)


class ContratoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    contrato: str
    cliente: int
    servico_contrato: Optional[str] = None
    vendedor_contrato: Optional[int] = None
    assinatura: Optional[str] = None
    inicio: Optional[str] = None
    fim: Optional[str] = None
    renovado_ate: Optional[str] = None
    data_encerramento: Optional[str] = None
    dia_vencimento: int
    mes_reajuste: int
    valor_inicial: float = 0
    tipo_contrato: int
    tipo_reajuste: int
    indice_reajuste: int
    tipo_cobranca: int
    periodicidade: int
    tarifa_cobranca: bool = False
    cobra_iss: bool = False
    agrupa_nf: bool = False
    fatura_os: bool = False
    descr_nf: str
    msg_obs_nf: str = ""
    obs: str = ""
    situacao: str = "A"
    multa: float = 0
    mora_dia: float = 0
    desc_venc: float = 0
    dias_chave_renovacao: int = 0


@router.post("/contratos")
async def save_contrato(req: ContratoSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "codigo", "usuario_alteracao", "classe", "plataforma"})
    result = await contratos_service.save_contrato(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="GRAVAR", referencia=result.get("codigo"), descricao=f"Contrato '{req.contrato}' gravado")
    return result


@router.post("/contratos/{codigo}/excluir")
async def delete_contrato(codigo: int, req: DeleteRequest, request: Request):
    result = await contratos_service.delete_contrato(req.servidor, req.banco, codigo)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="EXCLUIR", referencia=codigo, descricao=f"Contrato '{codigo}' excluído")
    return result


@router.post("/contratos/{codigo}/encerrar")
async def encerrar_contrato(codigo: int, req: DeleteRequest, request: Request):
    result = await contratos_service.encerrar_contrato(req.servidor, req.banco, codigo)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="ENCERRAR", referencia=codigo, descricao=f"Contrato '{codigo}' encerrado")
    return result


# ---------- Itens ----------

class ItemContratoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    produto: str
    qtd: float
    preco: float = 0
    data_inicio: Optional[str] = None
    data_encerramento: Optional[str] = None
    obs: str = ""
    situacao: str = "A"


@router.post("/contratos/{codigo_contrato}/itens")
async def save_item_contrato(codigo_contrato: int, req: ItemContratoSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "codigo", "usuario_alteracao", "classe", "plataforma"})
    result = await contratos_service.save_item_contrato(req.servidor, req.banco, codigo_contrato, req.codigo, dados)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="GRAVAR_ITEM", referencia=codigo_contrato, descricao=f"Item '{result.get('descricao')}' gravado no contrato {codigo_contrato}")
    return result


@router.post("/contratos/{codigo_contrato}/itens/{item_codigo}/excluir")
async def delete_item_contrato(codigo_contrato: int, item_codigo: int, req: DeleteRequest, request: Request):
    result = await contratos_service.delete_item_contrato(req.servidor, req.banco, codigo_contrato, item_codigo)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="EXCLUIR_ITEM", referencia=codigo_contrato, descricao=f"Item {item_codigo} excluído do contrato {codigo_contrato}")
    return result


# ---------- Centro de Custo ----------

class CentroCustoContratoRequest(AuditFields):
    servidor: str
    banco: str
    centro_custo: int
    valor: float


@router.post("/contratos/{codigo_contrato}/centro-custo")
async def save_centro_custo(codigo_contrato: int, req: CentroCustoContratoRequest, request: Request):
    result = await contratos_service.save_centro_custo(req.servidor, req.banco, codigo_contrato, req.centro_custo, req.valor)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="GRAVAR_CCUSTO", referencia=codigo_contrato, descricao=f"Centro de Custo {req.centro_custo} gravado no contrato {codigo_contrato}")
    return result


@router.post("/contratos/{codigo_contrato}/centro-custo/{centro_custo}/excluir")
async def delete_centro_custo(codigo_contrato: int, centro_custo: int, req: DeleteRequest, request: Request):
    result = await contratos_service.delete_centro_custo(req.servidor, req.banco, codigo_contrato, centro_custo)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="EXCLUIR_CCUSTO", referencia=codigo_contrato, descricao=f"Centro de Custo {centro_custo} removido do contrato {codigo_contrato}")
    return result


@router.post("/contratos/{codigo_contrato}/centro-custo/rateio")
async def rateio_centro_custo(codigo_contrato: int, req: DeleteRequest, request: Request):
    result = await contratos_service.rateio_centro_custo(req.servidor, req.banco, codigo_contrato)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="RATEIO_CCUSTO", referencia=codigo_contrato, descricao=f"Rateio de Centro de Custo aplicado no contrato {codigo_contrato}")
    return result


# ---------- Reajuste de Valor ----------

class ReajusteContratoRequest(AuditFields):
    servidor: str
    banco: str
    valor_novo: float
    percentual: float = 0
    descricao: str = ""


@router.post("/contratos/{codigo_contrato}/reajuste")
async def aplicar_reajuste(codigo_contrato: int, req: ReajusteContratoRequest, request: Request):
    result = await contratos_service.aplicar_reajuste(req.servidor, req.banco, codigo_contrato, req.valor_novo, req.percentual, req.descricao)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="REAJUSTE", referencia=codigo_contrato, descricao=f"Reajuste de valor gravado no contrato {codigo_contrato} ({req.valor_novo})")
    return result


# ---------- Acréscimo/Desconto ----------

class CredDebContratoRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    ano: int
    mes: int
    item: str = ""
    tipo: int  # 0 = Acréscimo, 1 = Desconto
    valor: float
    compl_descr: str = ""


@router.post("/contratos/{codigo_contrato}/cred-deb")
async def save_cred_deb(codigo_contrato: int, req: CredDebContratoRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "codigo", "usuario_alteracao", "classe", "plataforma"})
    result = await contratos_service.save_cred_deb(req.servidor, req.banco, codigo_contrato, req.codigo, dados)
    if result.get("success"):
        tipo_label = "Acréscimo" if req.tipo == 0 else "Desconto"
        await _log(req, request, tela="CONTRATO", comando="GRAVAR_CREDDEB", referencia=codigo_contrato, descricao=f"{tipo_label} de {req.valor} gravado no contrato {codigo_contrato}")
    return result


@router.post("/contratos/{codigo_contrato}/cred-deb/{cred_deb_codigo}/excluir")
async def delete_cred_deb(codigo_contrato: int, cred_deb_codigo: int, req: DeleteRequest, request: Request):
    result = await contratos_service.delete_cred_deb(req.servidor, req.banco, codigo_contrato, cred_deb_codigo)
    if result.get("success"):
        await _log(req, request, tela="CONTRATO", comando="EXCLUIR_CREDDEB", referencia=codigo_contrato, descricao=f"Lançamento {cred_deb_codigo} excluído do contrato {codigo_contrato}")
    return result


# ==================== Faturar Contratos ====================

@router.get("/contratos/faturar/listar")
async def listar_contratos_faturar(
    servidor: str, banco: str, ano: int, mes: int,
    contrato_ini: str = "", contrato_fim: str = "",
    tipos_cobranca: str = "", somente_nao_faturados: bool = False,
    mes_venc: int = 0, ano_venc: int = 0, data_emissao: str = "",
):
    tipos = [int(t) for t in tipos_cobranca.split(",") if t.strip() != ""] if tipos_cobranca else []
    return await contratos_service.listar_contratos_faturar(
        servidor, banco, ano, mes, contrato_ini or None, contrato_fim or None,
        tipos, somente_nao_faturados, mes_venc or mes, ano_venc or ano, data_emissao,
    )


class ItemFaturarRequest(BaseModel):
    codigo: int
    valor_total: float
    vencimento: Optional[str] = None
    # "N"/"B"/"R" (Nota Fiscal/Boleto/Recibo) — vem de `tipo_doc` já
    # resolvido por `GET /contratos/faturar/listar`. Só informa o
    # frontend se este contrato é elegível pra mostrar os botões de
    # emissão (Nota Fiscal/Boleto) — nunca dispara emissão automática
    # (ver `POST /contratos/faturar/emitir` abaixo).
    tipo_doc: Optional[str] = None


class FaturarContratosRequest(AuditFields):
    servidor: str
    banco: str
    ano: int
    mes: int
    itens: list[ItemFaturarRequest]
    master: Optional[bool] = False


@router.post("/contratos/faturar")
async def faturar_contratos(req: FaturarContratosRequest, request: Request):
    itens = [i.model_dump() for i in req.itens]
    result = await contratos_service.faturar_contratos(
        req.servidor, req.banco, req.ano, req.mes, itens, req.usuario_alteracao,
        classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        ok = [r for r in result.get("resultados", []) if r.get("success")]
        for r in ok:
            await _log(
                req, request, tela="FATURAR_CONTR", comando="FATURAR",
                referencia=r.get("comanda"),
                descricao=f"Contrato {r.get('codigo')} faturado (comanda {r.get('comanda')}, ref. {req.mes}/{req.ano})",
            )
    return result


class EmitirDocumentoContratoRequest(AuditFields):
    servidor: str
    banco: str
    tipo: str  # "nfe" (produto) ou "nfse" (serviço)
    comanda: int
    master: Optional[bool] = False


@router.post("/contratos/faturar/emitir")
async def emitir_documento_contrato(req: EmitirDocumentoContratoRequest, request: Request):
    """Ação separada e opcional (nunca automática — ver `contratos_
    service._emitir_documento_contrato_sync`). Reaproveita os mesmos
    motores de Agrupar Comandas (NF-e/NFS-e) já usados em outras telas."""
    result = await contratos_service.emitir_documento_contrato(
        req.servidor, req.banco, req.tipo, req.comanda, req.usuario_alteracao,
        classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await _log(
            req, request, tela="FATURAR_CONTR", comando="EMITIR_NF",
            referencia=req.comanda,
            descricao=f"{'NF-e' if req.tipo == 'nfe' else 'NFS-e'} emitida pra comanda {req.comanda}",
        )
    return result


class GerarReciboRequest(AuditFields):
    servidor: str
    banco: str
    contrato: int
    comanda: int
    ano_ref: int
    mes_ref: int
    descreve_os: str = ""


@router.post("/contratos/faturar/recibo")
async def gerar_recibo(req: GerarReciboRequest, request: Request):
    result = await contratos_service.gerar_recibo(req.servidor, req.banco, req.contrato, req.comanda, req.ano_ref, req.mes_ref, req.descreve_os)
    if result.get("success"):
        await _log(req, request, tela="FATURAR_CONTR", comando="RECIBO", referencia=req.comanda, descricao=f"Recibo {result.get('numero')} gerado para a comanda {req.comanda}")
    return result


# ==================== Envio de Cobrança (Geral\FrmEnvCob.frm) ====================

@router.get("/contratos/cobrancas")
async def listar_cobrancas(
    servidor: str, banco: str,
    ano: Optional[int] = None, mes: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    status: Optional[str] = None,
):
    status_lista = [s for s in (status or "").split(",") if s.strip()] if status else None
    return await contratos_service.listar_cobrancas(servidor, banco, ano, mes, data_ini, data_fim, status_lista)


class EnviarCobrancasRequest(AuditFields):
    servidor: str
    banco: str
    ids: list[int]


@router.post("/contratos/cobrancas/enviar")
async def enviar_cobrancas(req: EnviarCobrancasRequest, request: Request):
    """Envio real de e-mail (Fase 1, sem anexo — ver `contratos_service.
    py` > "Envio de Cobrança" pro escopo confirmado). Nunca dispara
    sozinho — só quando o usuário seleciona e confirma na tela."""
    result = await contratos_service.enviar_cobrancas(req.servidor, req.banco, req.ids)
    if result.get("success"):
        ok = [r for r in result.get("resultados", []) if r.get("success")]
        for r in ok:
            await _log(
                req, request, tela="ENVIO_COBRANCA", comando="ENVIAR",
                referencia=r.get("codigo"), descricao=f"E-mail de cobrança {r.get('codigo')} enviado",
            )
    return result
