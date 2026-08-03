"""Rotas de Inventário de Estoque (Transações > Inventário) — ver
services/inventario_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.inventario import (
    InventarioAbrirRequest,
    InventarioCancelarRequest,
    InventarioFecharRequest,
    InventarioItemRequest,
)
from services import inventario_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/inventario/status")
async def status(servidor: str, banco: str):
    return await inventario_service.status(servidor, banco)


@router.post("/inventario/rotinas-automaticas")
async def rotinas_automaticas(servidor: str, banco: str):
    # Fase 3 — disparo silencioso (mensal + diário contábil), chamado pelo
    # frontend uma vez por sessão (não é uma ação de tela, não precisa de
    # permissão nem log de auditoria — mesma categoria de "manutenção
    # invisível" já usada por outras chamadas de boot do app). Ver
    # services/inventario_service.py e PENDENCIAS.md > Inventário.
    return await inventario_service.executar_rotinas_automaticas(servidor, banco)


@router.get("/inventario/item/{codigo}")
async def buscar_item(codigo: str, servidor: str, banco: str):
    return await inventario_service.buscar_item(servidor, banco, codigo)


@router.get("/inventario/itens/resumo")
async def resumo_por_usuario(servidor: str, banco: str):
    return await inventario_service.resumo_por_usuario(servidor, banco)


@router.get("/inventario/itens")
async def listar_itens(servidor: str, banco: str, usuario: Optional[int] = None, sem_usuario: bool = False):
    return await inventario_service.listar_itens(servidor, banco, usuario, sem_usuario)


@router.get("/inventario/relatorio-contagem")
async def relatorio_contagem(
    servidor: str, banco: str, tipos: str = "0,1,2", somente_ativos: bool = False,
    nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = "",
):
    lista_tipos = [int(t) for t in tipos.split(",") if t.strip() != ""]
    niveis = [nivel1, nivel2, nivel3, nivel4, nivel5]
    return await inventario_service.relatorio_contagem(servidor, banco, lista_tipos, somente_ativos, niveis)


@router.get("/inventario/relatorio-conferencia")
async def relatorio_conferencia(
    servidor: str, banco: str, tipos: str = "0,1,2", listar_zerados: bool = False,
    nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = "",
):
    lista_tipos = [int(t) for t in tipos.split(",") if t.strip() != ""]
    niveis = [nivel1, nivel2, nivel3, nivel4, nivel5]
    return await inventario_service.relatorio_conferencia(servidor, banco, lista_tipos, listar_zerados, niveis)


@router.get("/inventario/relatorio-critica")
async def relatorio_critica(
    servidor: str, banco: str, data: str = "",
    nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = "",
):
    niveis = [nivel1, nivel2, nivel3, nivel4, nivel5]
    return await inventario_service.relatorio_critica(servidor, banco, niveis, data or None)


@router.get("/inventario/relatorio-resultado")
async def relatorio_resultado(
    servidor: str, banco: str, data: str = "", fonte_estoque: str = "inventario",
    nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = "",
):
    niveis = [nivel1, nivel2, nivel3, nivel4, nivel5]
    return await inventario_service.relatorio_resultado(servidor, banco, niveis, data or None, fonte_estoque)


@router.get("/inventario/relatorio-divergencia")
async def relatorio_divergencia(
    servidor: str, banco: str, data: str = "", preco: str = "venda", ordenar: str = "codigo",
    nivel1: str = "", nivel2: str = "", nivel3: str = "", nivel4: str = "", nivel5: str = "",
):
    niveis = [nivel1, nivel2, nivel3, nivel4, nivel5]
    return await inventario_service.relatorio_divergencia(servidor, banco, niveis, data or None, preco, ordenar)


@router.post("/inventario/abrir")
async def abrir(req: InventarioAbrirRequest, request: Request):
    result = await inventario_service.abrir(req.servidor, req.banco, req.data, req.tipo, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INVENTARIO", comando="ABERTURA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=req.data,
            descricao=f"Abertura de inventário {req.tipo} referente a {req.data}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/inventario/itens/incluir")
async def incluir_item(req: InventarioItemRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    result = await inventario_service.incluir_item(req.servidor, req.banco, dados, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INVENTARIO", comando="DIGITACAO",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo_interno"),
            descricao=f"Inventário: incluído {req.qtd} un. de {req.codigo} (total contado: {result.get('estoque_balanco')}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/inventario/itens/alterar")
async def alterar_item(req: InventarioItemRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    result = await inventario_service.alterar_item(req.servidor, req.banco, dados, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INVENTARIO", comando="DIGITACAO",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo_interno"),
            descricao=f"Inventário: alterada contagem de {req.codigo} para {result.get('estoque_balanco')}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/inventario/fechar")
async def fechar(req: InventarioFecharRequest, request: Request):
    result = await inventario_service.fechar(req.servidor, req.banco, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INVENTARIO", comando="FECHAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Fechamento de inventário.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/inventario/cancelar")
async def cancelar(req: InventarioCancelarRequest, request: Request):
    result = await inventario_service.cancelar(req.servidor, req.banco, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="INVENTARIO", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Cancelamento de inventário.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
