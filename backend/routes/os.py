"""Rotas de Ordem de Serviço (cabeçalho `os`) e seus itens (`os_produto`)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import OSListRequest, OSSaveRequest, OSItemSaveRequest, DescontoGeralRequest, FecharRequest
from services import os_service, os_itens_service, log_auditoria_service

router = APIRouter()

CAMPOS_OS = [
    "cliente", "area_atuacao", "descricao_cliente", "obs", "resumo", "status_os", "atendente", "situacao",
    "placa", "marca", "modelo", "km", "ano", "chassi", "numero_de_serie",
]
CAMPOS_ITEM_OS = ["quant", "preco_unitario", "desconto", "acrescimo", "descricao_produto_os", "vendedor", "executor"]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _depois_item_os(req: OSItemSaveRequest) -> dict:
    return {
        "quant": req.qtd, "preco_unitario": req.valor_unitario,
        "desconto": req.desconto, "acrescimo": req.acrescimo,
        "descricao_produto_os": req.complemento,
        "vendedor": req.vendedor, "executor": req.executor,
    }


def _depois_item_os_update(req: OSItemSaveRequest) -> dict:
    """Como `_depois_item_os`, mas espelha o fallback de `_update_item_sync`
    (valor_unitario omitido vira 0, não o preço padrão do produto — diferente
    do fallback do ADD, que resolve via `_resolve_produto`)."""
    d = _depois_item_os(req)
    d["preco_unitario"] = float(req.valor_unitario or 0)
    return d


def _depois_os(req: OSSaveRequest) -> dict:
    """Espelha os fallbacks de `_save_os_sync` (km/status_os/situacao viram 0/0/'A'
    quando omitidos) — sem isso, o diff comparava o valor real gravado contra o
    default cru do Pydantic (None) e acusava mudança falsa em todo update onde o
    cliente não reenviasse esses 3 campos."""
    d = req.model_dump()
    d["km"] = int(req.km) if req.km is not None else 0
    d["status_os"] = req.status_os if req.status_os is not None else 0
    d["situacao"] = (req.situacao or "A").strip().upper() if req.situacao else "A"
    return d


@router.post("/os")
async def list_os(req: OSListRequest):
    return await os_service.list_os(req)


@router.get("/os/{codigo}")
async def get_os(codigo: int, servidor: str, banco: str):
    return await os_service.get_os(servidor, banco, codigo)


@router.post("/os/create")
async def create_os(req: OSSaveRequest, request: Request):
    result = await os_service.save_os(req, None)
    if result.get("success"):
        codigo = result.get("codigo")
        campos = log_auditoria_service.diff_campos(None, _depois_os(req), CAMPOS_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. {codigo} criada",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os/{codigo}")
async def update_os(codigo: int, req: OSSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os", "codigo", codigo)
    result = await os_service.save_os(req, codigo)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, _depois_os(req), CAMPOS_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. {codigo} atualizada ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os/{codigo}/fechar")
async def fechar_os(codigo: int, req: FecharRequest, request: Request):
    result = await os_service.fechar_os(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. {codigo} fechada",
            campos_alterados=[{"campo": "situacao", "antes": "A", "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- itens da OS ----------
@router.get("/os/{codigo}/itens")
async def list_itens(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_itens(servidor, banco, codigo)


@router.post("/os/{codigo}/itens")
async def add_item(codigo: int, req: OSItemSaveRequest, request: Request):
    result = await os_itens_service.add_item(req, codigo)
    if result.get("success"):
        cod_os_prod = result.get("cod_os_prod")
        campos = log_auditoria_service.diff_campos(None, _depois_item_os(req), CAMPOS_ITEM_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="ADD_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo), descricao=f"Item '{req.produto}' incluído na O.S. {codigo} (cod {cod_os_prod})",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os/{codigo}/itens/{cod_os_prod}")
async def update_item(codigo: int, cod_os_prod: int, req: OSItemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os_produto", "cod_os_prod", cod_os_prod)
    result = await os_itens_service.update_item(req, codigo, cod_os_prod)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, _depois_item_os_update(req), CAMPOS_ITEM_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="EDIT_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo), descricao=f"Item {cod_os_prod} da O.S. {codigo} alterado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/os/{codigo}/itens/{cod_os_prod}")
async def delete_item(
    codigo: int, cod_os_prod: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    antes = await log_auditoria_service.get_row_by_pk(servidor, banco, "os_produto", "cod_os_prod", cod_os_prod)
    result = await os_itens_service.delete_item(servidor, banco, codigo, cod_os_prod)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(
            antes, ["codigo_interno", "quant", "preco_unitario", "desconto", "acrescimo"],
        )
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="OS", comando="DEL_ITEM",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(codigo), descricao=f"Item {cod_os_prod} excluído da O.S. {codigo}",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.get("/os/{codigo}/descontos")
async def list_descontos(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_descontos(servidor, banco, codigo)


@router.get("/os/{codigo}/analise")
async def analise(codigo: int, servidor: str, banco: str):
    return await os_itens_service.analise(servidor, banco, codigo)


@router.post("/os/{codigo}/desconto-geral")
async def desconto_geral(codigo: int, req: DescontoGeralRequest, request: Request):
    result = await os_itens_service.aplicar_desconto_geral(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS", comando="DESC_GERAL",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Desconto geral de R$ {req.valor:.2f} aplicado na O.S. {codigo} ({result.get('percentual', 0):g}%)",
            campos_alterados=[{"campo": "desconto_geral", "depois": f"{req.valor:.2f}"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
