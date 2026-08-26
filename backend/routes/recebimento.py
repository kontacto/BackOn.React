"""Rotas do Recebimento de Mercadoria (migração de `Geral\\FrmtraRec.frm`).
Ver `services/recebimento_service.py` pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.recebimento import (
    AtualizarRecebimentoRequest,
    CriticarRecebimentoRequest,
    ImportarXmlRecebimentoRequest,
    NovoRecebimentoRequest,
    SalvarCabecalhoRecebimentoRequest,
    SalvarItensRecebimentoRequest,
    SalvarVencimentosRecebimentoRequest,
)
from services import log_auditoria_service, recebimento_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/recebimento/novo")
async def novo_rascunho(req: NovoRecebimentoRequest):
    return await recebimento_service.novo_rascunho(req.servidor, req.banco, classe=req.classe, master=bool(req.master))


@router.get("/recebimento/{codigo}")
async def get_rascunho(codigo: int, servidor: str, banco: str):
    return await recebimento_service.get_rascunho(servidor, banco, codigo)


@router.post("/recebimento/cabecalho")
async def salvar_cabecalho(req: SalvarCabecalhoRecebimentoRequest):
    return await recebimento_service.save_cabecalho_rascunho(req.servidor, req.banco, req.codigo, req.dados)


@router.post("/recebimento/itens")
async def salvar_itens(req: SalvarItensRecebimentoRequest):
    return await recebimento_service.save_itens_rascunho(req.servidor, req.banco, req.codigo, req.itens)


@router.post("/recebimento/vencimentos")
async def salvar_vencimentos(req: SalvarVencimentosRecebimentoRequest):
    return await recebimento_service.save_vencimentos_rascunho(req.servidor, req.banco, req.codigo, req.vencimentos)


@router.post("/recebimento/criticar")
async def criticar(req: CriticarRecebimentoRequest):
    return await recebimento_service.criticar(req.servidor, req.banco, req.codigo, classe=req.classe, master=bool(req.master))


@router.post("/recebimento/importar-xml")
async def importar_xml(req: ImportarXmlRecebimentoRequest):
    return await recebimento_service.importar_xml(
        req.servidor, req.banco, req.codigo, req.conteudo_xml, classe=req.classe, master=bool(req.master),
    )


@router.post("/recebimento/atualizar")
async def atualizar(req: AtualizarRecebimentoRequest, request: Request):
    result = await recebimento_service.atualizar(
        req.servidor, req.banco, req.codigo, usuario=req.usuario_alteracao, classe=req.classe, master=bool(req.master),
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="RECEBIMENTO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo), descricao=f"Recebimento atualizado — Nota Fiscal nº {result.get('n_fiscal')}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
