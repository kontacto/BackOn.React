"""Rotas de Fotos de Produto — ver services/produto_imagem_service.py para
o desenho completo (sistema novo, isolado do Gestor de Documentos)."""
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import Response

from models.log_auditoria import AuditFields
from services import log_auditoria_service, produto_imagem_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ProdutoImagemAcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/produto-imagem")
async def list_imagens(servidor: str, banco: str, codigo_int: str):
    return await produto_imagem_service.list_imagens(servidor, banco, codigo_int)


@router.post("/produto-imagem")
async def upload_imagem(
    request: Request,
    servidor: str = Form(...),
    banco: str = Form(...),
    codigo_int: str = Form(...),
    cor: Optional[int] = Form(None),
    principal: bool = Form(False),
    usuario_alteracao: Optional[int] = Form(None),
    classe: Optional[int] = Form(None),
    plataforma: Optional[str] = Form(None),
    arquivo: UploadFile = File(...),
):
    conteudo = await arquivo.read()
    result = await produto_imagem_service.upload_imagem(
        servidor, banco,
        codigo_int=codigo_int, conteudo=conteudo, nome_original=arquivo.filename or "foto",
        cor=cor, principal=principal, usuario_inclusao=usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="PRODUTO_COMP", comando="FOTO_UPLOAD",
            usuario=usuario_alteracao, classe=classe, referencia=codigo_int,
            descricao=f"Foto incluída para o produto {codigo_int}.",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.post("/produto-imagem/{codigo}/excluir")
async def excluir_imagem(codigo: int, req: ProdutoImagemAcaoRequest, request: Request):
    result = await produto_imagem_service.excluir_imagem(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="FOTO_EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Foto #{codigo} excluída.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/produto-imagem/{codigo}/principal")
async def marcar_principal(codigo: int, req: ProdutoImagemAcaoRequest, request: Request):
    result = await produto_imagem_service.marcar_principal(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PRODUTO_COMP", comando="FOTO_PRINCIPAL",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Foto #{codigo} definida como principal.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/produto-imagem/{codigo}/arquivo")
async def download_imagem(codigo: int, servidor: str, banco: str, variante: str = "thumb"):
    result = await produto_imagem_service.arquivo(servidor, banco, codigo, variante)
    if not result.get("success"):
        return result
    return Response(
        content=result["conteudo"],
        media_type=result["content_type"],
        headers={"Content-Disposition": f'inline; filename="{result["nome_arquivo"]}"'},
    )
