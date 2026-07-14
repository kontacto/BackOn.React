"""Rotas de manutencao de usuarios (Perfil do Usuario).

Toda ação de Incluir/Alterar/Excluir é registrada em `log_auditoria` — mesmo
padrão de `routes/tabelas_aux.py`. Atenção: `classe` aqui já é usado pelo
domínio (o grupo do usuário-alvo sendo criado/alterado), então NÃO
reaproveitamos o mixin `AuditFields` (que também tem um campo `classe`, mas
com outro significado — a classe de quem executa a ação). Por isso só
`usuario_alteracao`/`plataforma` são capturados aqui; o log fica sem a classe
de quem executou (seria um campo a mais, `autor_classe`, se algum dia for
necessário). Senha nunca entra no log (nem antes, nem depois).
"""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services import log_auditoria_service, usuarios_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class UsuarioIncluirRequest(BaseModel):
    servidor: str
    banco: str
    usuario: str
    classe: int
    senha: str
    confirmacao_senha: str
    administrador: bool = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class UsuarioAlterarRequest(BaseModel):
    servidor: str
    banco: str
    usuario: str
    classe: int
    senha_atual: Optional[str] = None
    nova_senha: Optional[str] = None
    confirmacao_senha: Optional[str] = None
    administrador: bool = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None
    # Login de quem está executando a ação (distinto de `usuario`, o alvo
    # sendo alterado) — usado no servidor pra decidir se a senha atual pode
    # ser dispensada (Gerente/Supervisor/master trocando a senha de OUTRO
    # usuário). Nunca confiar num boolean vindo do cliente pra essa decisão.
    usuario_logado: Optional[str] = None


class UsuarioDeleteRequest(BaseModel):
    servidor: str
    banco: str
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="PERFIL_USUARIO", comando=comando,
        usuario=req.usuario_alteracao, referencia=str(referencia), descricao=descricao,
        campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
    )


@router.get("/usuarios/perfil/lista")
async def list_usuarios(servidor: str, banco: str):
    return await usuarios_service.list_usuarios(servidor, banco)


@router.get("/usuarios/perfil")
async def get_usuario_perfil(servidor: str, banco: str, usuario: str):
    return await usuarios_service.get_usuario_perfil(servidor, banco, usuario)


@router.post("/usuarios/perfil/incluir")
async def incluir_usuario(req: UsuarioIncluirRequest, request: Request):
    result = await usuarios_service.incluir_usuario(
        req.servidor, req.banco, req.usuario, req.classe, req.senha, req.confirmacao_senha, req.administrador,
    )
    if result.get("success"):
        await _log(
            req, request, comando="GRAVAR", referencia=req.usuario,
            descricao=f"Usuário '{req.usuario}' incluído (classe {req.classe})",
            campos=[
                {"campo": "classe", "depois": str(req.classe)},
                {"campo": "administrador", "depois": str(req.administrador)},
            ],
        )
    return result


@router.post("/usuarios/perfil/alterar")
async def alterar_usuario(req: UsuarioAlterarRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "usuarios", "usuario", req.usuario)
    result = await usuarios_service.alterar_usuario(
        req.servidor, req.banco, req.usuario, req.classe, req.senha_atual, req.nova_senha,
        req.confirmacao_senha, req.administrador, req.usuario_logado,
    )
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(
            antes, {"classe": req.classe, "administrador": req.administrador}, ["classe", "administrador"],
        )
        if req.nova_senha:
            campos.append({"campo": "senha", "valor": "alterada"})
        await _log(req, request, comando="GRAVAR", referencia=req.usuario, descricao=f"Usuário '{req.usuario}' alterado", campos=campos)
    return result


@router.post("/usuarios/perfil/{usuario}/excluir")
async def excluir_usuario(usuario: str, req: UsuarioDeleteRequest, request: Request):
    result = await usuarios_service.excluir_usuario(req.servidor, req.banco, usuario)
    if result.get("success"):
        await _log(req, request, comando="EXCLUIR", referencia=usuario, descricao=f"Usuário '{usuario}' excluído")
    return result
