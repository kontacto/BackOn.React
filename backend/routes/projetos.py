"""Rotas do Gestor de Projetos (`projetos`/`projetos_documentos`) — Fase 1,
núcleo. Ver PENDENCIAS.md > "Gestor de Projetos" pro rastreio completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    ProjetosListRequest, ProjetoSaveRequest, ProjetoDocumentoRequest, FecharRequest,
    ProjetoAjustarValoresRequest,
)
from services import projetos_service, log_auditoria_service

router = APIRouter()

CAMPOS_PROJETO = [
    "cliente", "responsavel", "data_inicio", "data_prevista", "detalhes",
    "valor_produtos", "valor_servicos",
]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.post("/projetos")
async def list_projetos(req: ProjetosListRequest):
    return await projetos_service.list_projetos(req)


@router.get("/projetos/{codigo}")
async def get_projeto(codigo: int, servidor: str, banco: str):
    return await projetos_service.get_projeto(servidor, banco, codigo)


@router.get("/projetos-vinculo")
async def get_vinculo(servidor: str, banco: str, tipo_doc: str, num_doc: int):
    return await projetos_service.find_vinculo(servidor, banco, tipo_doc, num_doc)


@router.get("/projetos-resumo")
async def get_resumo_projetos(servidor: str, banco: str):
    return await projetos_service.resumo_projetos(servidor, banco)


@router.post("/projetos/create")
async def create_projeto(req: ProjetoSaveRequest, request: Request):
    result = await projetos_service.save_projeto(req, None)
    if result.get("success"):
        codigo = result.get("codigo")
        campos = log_auditoria_service.diff_campos(None, req.model_dump(), CAMPOS_PROJETO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Projeto {codigo} criado",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/projetos/{codigo}")
async def update_projeto(codigo: int, req: ProjetoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "projetos", "codigo", codigo)
    result = await projetos_service.save_projeto(req, codigo)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), CAMPOS_PROJETO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Projeto {codigo} atualizado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/projetos/{codigo}/finalizar")
async def finalizar_projeto(codigo: int, req: FecharRequest, request: Request):
    result = await projetos_service.finalizar_projeto(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Projeto {codigo} finalizado",
            campos_alterados=[{"campo": "situacao", "antes": result.get("situacao_antes"), "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/projetos/{codigo}/reabrir")
async def reabrir_projeto(codigo: int, req: FecharRequest, request: Request):
    result = await projetos_service.reabrir_projeto(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Projeto {codigo} reaberto",
            campos_alterados=[{"campo": "situacao", "antes": result.get("situacao_antes"), "depois": "A"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/projetos/{codigo}/cancelar")
async def cancelar_projeto(codigo: int, req: FecharRequest, request: Request):
    result = await projetos_service.cancelar_projeto(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Projeto {codigo} cancelado",
            campos_alterados=[{"campo": "situacao", "antes": result.get("situacao_antes"), "depois": "C"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/projetos/{codigo}/documentos")
async def add_documento(codigo: int, req: ProjetoDocumentoRequest, request: Request):
    result = await projetos_service.add_documento(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="VINCULAR_DOC",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Projeto {codigo}: vinculado {req.tipo_doc} nº {req.num_doc}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/projetos/{codigo}/documentos/remover")
async def remove_documento(codigo: int, req: ProjetoDocumentoRequest, request: Request):
    result = await projetos_service.remove_documento(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="DESVINCULAR_DOC",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Projeto {codigo}: removido {req.tipo_doc} nº {req.num_doc}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/projetos/{codigo}/ajustar-valores")
async def get_ajuste_valores_preview(codigo: int, servidor: str, banco: str):
    return await projetos_service.ajuste_valores_preview(servidor, banco, codigo)


@router.post("/projetos/{codigo}/ajustar-valores")
async def post_ajustar_valores(codigo: int, req: ProjetoAjustarValoresRequest, request: Request):
    result = await projetos_service.ajustar_valores(req, codigo)
    if result.get("success") and result.get("itens_ajustados"):
        tipo_label = "Produtos" if req.tipo.upper() == "P" else "Serviços"
        docs_txt = ", ".join(f"{d.tipo_doc} nº {d.num_doc}" for d in req.documentos)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PROJETOS", comando="AJUSTAR_VALORES",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=(
                f"Projeto {codigo}: valores de {tipo_label} ajustados para "
                f"{result.get('novo_valor')} ({result.get('itens_ajustados')} item(ns) em {docs_txt})"
            ),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
