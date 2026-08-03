"""Rotas do Motor de Formulário Dinâmico (Cadastro de Layout +
Preenchimento) — ver `services/layout_service.py`."""
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, Request

from services import layout_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class LayoutSaveRequest(BaseModel):
    servidor: str
    banco: str
    descricao: str
    cliente: bool = False
    fornecedor: bool = False
    funcionario: bool = False
    produto: bool = False
    servico: bool = False
    pedido_venda: bool = False
    os: bool = False
    profissional: bool = False
    contrato: bool = False
    classe: Optional[int] = None
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class CampoSaveRequest(BaseModel):
    servidor: str
    banco: str
    layout: int
    campo1: str
    campo2: Optional[str] = ""
    tipo: int
    calculado: bool = False
    calc_campo1: Optional[int] = None
    calc_campo2: Optional[int] = None
    operador: Optional[str] = ""
    valor_minimo: Optional[float] = None
    valor_maximo: Optional[float] = None
    unidade_medida: Optional[str] = ""
    decimais: int = 0
    tamanho: int = 0
    campo_agrupado: bool = False
    classe: Optional[int] = None
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class RespostaCampo(BaseModel):
    codigo_campo: int
    conteudo: str


class PreencherRequest(BaseModel):
    servidor: str
    banco: str
    entidade: int
    codentidade: int
    codlayout: int
    codigo: Optional[int] = None  # código de layout_entidade, se já existir
    obs: Optional[str] = ""
    respostas: list[RespostaCampo] = []
    classe: Optional[int] = None
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


@router.get("/layout")
async def list_layouts(servidor: str, banco: str):
    return await layout_service.list_layouts(servidor, banco)


@router.post("/layout")
async def create_layout(req: LayoutSaveRequest, request: Request):
    result = await layout_service.save_layout(req.servidor, req.banco, None, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="LAYOUT", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")), descricao=f"Layout \"{req.descricao}\" criado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/layout/{codigo}")
async def update_layout(codigo: int, req: LayoutSaveRequest, request: Request):
    result = await layout_service.save_layout(req.servidor, req.banco, codigo, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="LAYOUT", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Layout \"{req.descricao}\" atualizado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/layout/{codigo}")
async def delete_layout(
    codigo: int, servidor: str, banco: str, request: Request,
    classe: Optional[int] = None, usuario_alteracao: Optional[int] = None, plataforma: Optional[str] = None,
):
    result = await layout_service.delete_layout(servidor, banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="LAYOUT", comando="EXCLUIR",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(codigo), descricao=f"Layout {codigo} excluído",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.get("/layout/tipos-campo")
async def list_tipos_campo(servidor: str, banco: str):
    return await layout_service.list_tipos_campo(servidor, banco)


@router.get("/layout/campos")
async def list_campos(servidor: str, banco: str, layout: int):
    return await layout_service.list_campos(servidor, banco, layout)


@router.post("/layout/campos")
async def create_campo(req: CampoSaveRequest, request: Request):
    result = await layout_service.save_campo(req.servidor, req.banco, None, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="LAYOUT", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.layout), descricao=f"Campo \"{req.campo1}\" incluído no layout {req.layout}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/layout/campos/{codigo}")
async def update_campo(codigo: int, req: CampoSaveRequest, request: Request):
    result = await layout_service.save_campo(req.servidor, req.banco, codigo, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="LAYOUT", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.layout), descricao=f"Campo \"{req.campo1}\" atualizado no layout {req.layout}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/layout/campos/{codigo}")
async def delete_campo(
    codigo: int, servidor: str, banco: str, request: Request,
    classe: Optional[int] = None, usuario_alteracao: Optional[int] = None, plataforma: Optional[str] = None,
):
    result = await layout_service.delete_campo(servidor, banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="LAYOUT", comando="EXCLUIR",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(codigo), descricao=f"Campo {codigo} excluído",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.get("/layout/possiveis")
async def list_possiveis(servidor: str, banco: str, entidade: int, codentidade: int):
    return await layout_service.list_possiveis(servidor, banco, entidade, codentidade)


@router.get("/layout/preenchidos")
async def list_preenchidos(servidor: str, banco: str, entidade: int, codentidade: int):
    return await layout_service.list_preenchidos(servidor, banco, entidade, codentidade)


@router.get("/layout/preenchimento/{codigo}")
async def get_preenchimento(codigo: int, servidor: str, banco: str):
    return await layout_service.get_preenchimento(servidor, banco, codigo)


@router.post("/layout/preencher")
async def preencher(req: PreencherRequest, request: Request):
    result = await layout_service.preencher(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="LAYOUT", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.entidade}/{req.codentidade}",
            descricao=f"Preenchimento do layout {req.codlayout} gravado para entidade {req.entidade}/{req.codentidade}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
