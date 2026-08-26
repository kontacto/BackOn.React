"""Rotas da NF-e Avulsa ("Gerar NFe", migração de `NFe\\frmtranfe.frm`).
Ver `services/nfe_avulsa_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.nfe_avulsa import (
    EmitirNfeAvulsaRequest,
    ImportarDevolucaoRequest,
    ImportarDocumentoRequest,
    NovoRascunhoRequest,
    SalvarCabecalhoRascunhoRequest,
    SalvarItensRascunhoRequest,
    SalvarVencimentosRascunhoRequest,
    SugerirTributacaoRequest,
)
from services import log_auditoria_service, nfe_avulsa_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/nfe-avulsa/novo")
async def novo_rascunho(req: NovoRascunhoRequest):
    return await nfe_avulsa_service.novo_rascunho(req.servidor, req.banco, classe=req.classe, master=bool(req.master))


@router.get("/nfe-avulsa/{codigo}")
async def get_rascunho(codigo: int, servidor: str, banco: str):
    return await nfe_avulsa_service.get_rascunho(servidor, banco, codigo)


@router.post("/nfe-avulsa/cabecalho")
async def salvar_cabecalho(req: SalvarCabecalhoRascunhoRequest):
    return await nfe_avulsa_service.save_cabecalho_rascunho(req.servidor, req.banco, req.codigo, req.dados)


@router.post("/nfe-avulsa/itens")
async def salvar_itens(req: SalvarItensRascunhoRequest):
    return await nfe_avulsa_service.save_itens_rascunho(req.servidor, req.banco, req.codigo, req.itens)


@router.post("/nfe-avulsa/vencimentos")
async def salvar_vencimentos(req: SalvarVencimentosRascunhoRequest):
    return await nfe_avulsa_service.save_vencimentos_rascunho(req.servidor, req.banco, req.codigo, req.vencimentos)


# Importação automática (6 sub-rotinas) — ver "Importação automática" em
# `services/nfe_avulsa_service.py`. Todas read-only (não escrevem em
# `nf_aux`), o frontend aplica `header`/`itens` no rascunho já em edição.
@router.post("/nfe-avulsa/importar/pedido")
async def importar_pedido(req: ImportarDocumentoRequest):
    return await nfe_avulsa_service.importar_pedido(req.servidor, req.banco, req.documento)


@router.post("/nfe-avulsa/importar/devolucao")
async def importar_devolucao(req: ImportarDevolucaoRequest):
    return await nfe_avulsa_service.importar_devolucao(req.servidor, req.banco, req.ids_devolucao)


@router.post("/nfe-avulsa/importar/compra")
async def importar_compra(req: ImportarDocumentoRequest):
    return await nfe_avulsa_service.importar_compra(req.servidor, req.banco, req.documento)


@router.post("/nfe-avulsa/importar/requisicao")
async def importar_requisicao(req: ImportarDocumentoRequest):
    return await nfe_avulsa_service.importar_requisicao(req.servidor, req.banco, req.documento)


@router.post("/nfe-avulsa/importar/nota-fiscal")
async def importar_nota_fiscal(req: ImportarDocumentoRequest):
    return await nfe_avulsa_service.importar_nota_fiscal(req.servidor, req.banco, req.documento)


@router.post("/nfe-avulsa/importar/complementar")
async def importar_complementar(req: ImportarDocumentoRequest):
    return await nfe_avulsa_service.importar_complementar(req.servidor, req.banco, req.documento)


@router.post("/nfe-avulsa/sugerir-tributacao")
async def sugerir_tributacao(req: SugerirTributacaoRequest):
    return await nfe_avulsa_service.sugerir_tributacao(
        req.servidor, req.banco, req.codigo_int, req.mov, req.uf_destino,
        req.nao_contribuinte, req.simples_nacional_cliente, req.consumidor_final,
    )


@router.post("/nfe-avulsa/emitir")
async def emitir(req: EmitirNfeAvulsaRequest, request: Request):
    result = await nfe_avulsa_service.emitir_nfe_avulsa(
        req.servidor, req.banco, req.codigo, usuario=req.usuario_alteracao, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="NFE_AVULSA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo),
            descricao=f"NF-e avulsa emitida — rascunho {req.codigo} — nota {result.get('nota_fisc')}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
