"""Rotas do Gestor de Documentos (Anexos) — ver services/gestor_documentos_service.py
para o desenho completo (schema real, decisões de arquitetura)."""
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response

from models.log_auditoria import AuditFields
from services import gestor_documentos_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class SubGrupoCreateRequest(AuditFields):
    servidor: str
    banco: str
    cod_grupo: int
    descricao: str


class DocumentoDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/gestor-documentos/grupos")
async def list_grupos(servidor: str, banco: str):
    return await gestor_documentos_service.list_grupos(servidor, banco)


@router.get("/gestor-documentos/sub-grupos")
async def list_sub_grupos(servidor: str, banco: str, cod_grupo: int):
    return await gestor_documentos_service.list_sub_grupos(servidor, banco, cod_grupo)


@router.post("/gestor-documentos/sub-grupos")
async def create_sub_grupo(req: SubGrupoCreateRequest):
    return await gestor_documentos_service.get_or_create_sub_grupo(req.servidor, req.banco, req.cod_grupo, req.descricao)


@router.get("/gestor-documentos")
async def list_documentos(
    servidor: str, banco: str, cod_grupo: int, codigo_entidade: str,
    referencia: Optional[int] = None, cod_sub_grupo: Optional[int] = None,
):
    return await gestor_documentos_service.list_documentos(servidor, banco, cod_grupo, codigo_entidade, referencia, cod_sub_grupo)


@router.post("/gestor-documentos")
async def upload_documento(
    request: Request,
    servidor: str = Form(...),
    banco: str = Form(...),
    cod_grupo: int = Form(...),
    cod_sub_grupo: int = Form(...),
    codigo_entidade: str = Form(...),
    descricao: str = Form(...),
    referencia: Optional[int] = Form(None),
    validade: Optional[str] = Form(None),
    computador: str = Form(""),
    usuario_alteracao: Optional[int] = Form(None),
    classe: Optional[int] = Form(None),
    plataforma: Optional[str] = Form(None),
    adicionado_por: str = Form(""),
    arquivo: UploadFile = File(...),
):
    conteudo = await arquivo.read()
    result = await gestor_documentos_service.save_documento(
        servidor, banco,
        cod_grupo=cod_grupo, cod_sub_grupo=cod_sub_grupo, codigo_entidade=codigo_entidade,
        descricao=descricao, adicionado_por=adicionado_por, computador=computador,
        conteudo=conteudo, nome_arquivo=arquivo.filename or "arquivo",
        referencia=referencia, validade=validade,
    )
    if result.get("success"):
        req = DocumentoDeleteRequest(servidor=servidor, banco=banco, usuario_alteracao=usuario_alteracao, classe=classe, plataforma=plataforma)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_DOC", comando="ANEXAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{cod_grupo}/{codigo_entidade}",
            descricao=f"Anexo '{descricao}' incluído (grupo {cod_grupo}, entidade {codigo_entidade})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestor-documentos/{codigo}/excluir")
async def delete_documento(codigo: int, req: DocumentoDeleteRequest, request: Request):
    result = await gestor_documentos_service.delete_documento(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="GESTOR_DOC", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao=f"Anexo #{codigo} excluído", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/gestor-documentos/{codigo}/arquivo")
async def download_documento(codigo: int, servidor: str, banco: str):
    row = await gestor_documentos_service.get_arquivo_path(servidor, banco, codigo)
    if not row or not row.get("path"):
        return {"success": False, "message": "Documento não encontrado."}
    stored_path = row["path"]
    filename = row.get("path_origem") or f"anexo-{codigo}"

    # O registro guarda o destino final completo de quando foi anexado (path
    # absoluto local OU URL de blob) — se a config mudou depois (path local
    # ou Connection String do Azure), esse destino antigo continua sendo o
    # correto para ESTE documento, não é reconstruído a partir da config
    # atual. Mas se ele não existir mais de verdade (pasta apagada/
    # desmontada, blob removido, credencial revogada), falha aqui de forma
    # clara em vez de estourar erro.
    # "inline" (não "attachment"): o painel de visualização usa esta mesma
    # URL em <img>/<iframe> — com "attachment" alguns navegadores forçam
    # download em vez de renderizar embutido.
    if gestor_documentos_service.is_blob_target(stored_path):
        result = await gestor_documentos_service.baixar_blob(servidor, banco, stored_path)
        if not result.get("success"):
            return result
        return Response(
            content=result["conteudo"],
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    if not Path(stored_path).is_file():
        return {
            "success": False,
            "message": f"Arquivo não encontrado em '{stored_path}'. O caminho de armazenamento pode ter mudado ou o arquivo foi movido/apagado fora do sistema.",
        }
    return FileResponse(stored_path, filename=filename, content_disposition_type="inline")
