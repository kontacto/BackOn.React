"""Rotas do Pedido Completo (web) — Fase A: cabeçalho + itens + Fechar/Cancelar.

Lista e consulta/edição/exclusão de item individual são COMPARTILHADAS com o
Pedido rápido (mesma tabela, mesmo comportamento) — reaproveitadas direto de
`pedidos_service`/`itens_service`. Só cabeçalho (campos maiores), inclusão de
item (resolução rica + kits) e Cancelar são específicos desta tela, servidos
por `pedido_completo_service`. O log de auditoria aqui sempre usa
tela="PEDIDO_COMP" (catálogo próprio, distinto de "PEDIDO") mesmo quando a
operação reaproveita um service do Pedido rápido.
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    PedidoCompletoSaveRequest, ItemSaveRequest, FecharRequest, DescontoGeralRequest,
    DividirPedidoRequest, PedidoEntregueRequest,
)
from services import itens_service, pedido_completo_service, descontos_service, log_auditoria_service

router = APIRouter()

CAMPOS_PEDIDO = [
    "cliente", "vendedor", "forma_pag", "validade", "previsao_entrega",
    "local_entrega", "infoentrega", "num_ped_cliente", "obs", "area_atuacao",
]
CAMPOS_ITEM = ["qtd_pedida", "p_normal", "desconto", "acrescimo", "descricao_produto"]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _depois_item(req: ItemSaveRequest) -> dict:
    return {
        "qtd_pedida": req.qtd, "p_normal": req.valor_unitario,
        "desconto": req.desconto, "acrescimo": req.acrescimo,
        "descricao_produto": req.complemento,
    }


@router.get("/pedido-completo/{pedido}")
async def get_pedido_completo(pedido: int, servidor: str, banco: str):
    return await pedido_completo_service.get_pedido_completo(servidor, banco, pedido)


@router.post("/pedido-completo/create")
async def create_pedido_completo(req: PedidoCompletoSaveRequest, request: Request):
    result = await pedido_completo_service.save_pedido_completo(req, None)
    if result.get("success"):
        pedido_id = result.get("pedido")
        campos = log_auditoria_service.diff_campos(None, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido_id), descricao=f"Pedido Completo {pedido_id} criado",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedido-completo/{pedido}")
async def update_pedido_completo(pedido: int, req: PedidoCompletoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda", "pedido", pedido)
    result = await pedido_completo_service.save_pedido_completo(req, pedido)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido Completo {pedido} atualizado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedido-completo/{pedido}/fechar")
async def fechar_pedido_completo(pedido: int, req: FecharRequest, request: Request):
    result = await pedido_completo_service.fechar_pedido_completo(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido Completo {pedido} fechado",
            campos_alterados=[{"campo": "situacao", "antes": "A", "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedido-completo/{pedido}/cancelar")
async def cancelar_pedido_completo(pedido: int, req: FecharRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda", "pedido", pedido)
    result = await pedido_completo_service.cancelar_pedido_completo(req, pedido)
    if result.get("success"):
        sit_antes = (antes.get("situacao") if antes else "A") or "A"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido Completo {pedido} cancelado",
            campos_alterados=[{"campo": "situacao", "antes": sit_antes, "depois": "C"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- Faturar/Reabrir/Distribuir/Entregue — mesmas funções do Pedido
# Bar (`pedidos_service`, mesma tabela `pedido_venda`), só com
# tela="PEDIDO_COMP" pra checar a permissão certa (ver
# `pedido_completo_service.py` e "as funções do Pedido Bar" em CLAUDE.md/
# memória do projeto). Pedido explícito do usuário, 2026-07-20 — traz ao
# Pedido Geral tudo que o Pedido Bar já tinha, exceto Taxa de Serviço. ----------
@router.post("/pedido-completo/{pedido}/faturar")
async def faturar_pedido_completo(pedido: int, req: FecharRequest, request: Request):
    result = await pedido_completo_service.faturar_pedido_completo(req, pedido)
    if result.get("success"):
        situacao_antes = result.get("situacao_antes") or "F"
        descricao = f"Pedido Completo {pedido} faturado (comanda {result.get('comanda')})"
        if situacao_antes == "A":
            descricao += " — fechado automaticamente antes de faturar"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=descricao,
            campos_alterados=[{"campo": "situacao", "antes": situacao_antes, "depois": "PG"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedido-completo/{pedido}/reabrir")
async def reabrir_pedido_completo(pedido: int, req: FecharRequest, request: Request):
    result = await pedido_completo_service.reabrir_pedido_completo(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido Completo {pedido} reaberto",
            campos_alterados=[{"campo": "situacao", "antes": "F", "depois": "A"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedido-completo/{pedido}/dividir")
async def dividir_pedido_completo(pedido: int, req: DividirPedidoRequest, request: Request):
    result = await pedido_completo_service.dividir_pedido_completo(req, pedido)
    if result.get("success"):
        novos = result.get("novos_pedidos") or []
        descricao = f"Pedido Completo {pedido} dividido em {len(novos)} pedido(s): {', '.join(str(n) for n in novos)}"
        if result.get("original_cancelado"):
            descricao += " (pedido original cancelado, ficou sem itens)"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="DIVIDIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=descricao,
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedido-completo/{pedido}/entregue")
async def toggle_entregue_completo(pedido: int, req: PedidoEntregueRequest, request: Request):
    result = await pedido_completo_service.toggle_entregue_completo(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="ENTREGUE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Pedido Completo {pedido} marcado como {'entregue' if req.entregue else 'não entregue'}",
            campos_alterados=[{"campo": "pedido_entregue", "depois": req.entregue}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- itens do pedido completo ----------
# Exclusão é idêntica ao Pedido rápido (mesma tabela) — reaproveitada direto
# de itens_service. Inclusão usa a resolução rica + expansão de kit
# (pedido_completo_service.add_item_completo). Edição usa
# `pedido_completo_service.update_item_completo` (não mais `itens_service.
# update_item` — passou a reconhecer item m² e recalcular a área ao editar
# dimensões, ver PENDENCIAS.md > "Metro Quadrado"; item sem dimensão segue
# o mesmo caminho de antes). Listagem usa
# `pedido_completo_service.list_itens_completo`, que por sua vez chama a MESMA
# função do Bar por dentro e só acrescenta o número de série vinculado (campo
# extra que o Bar não lê) — não duplica a query base, ver docstring lá.
@router.get("/pedido-completo/{pedido}/itens")
async def list_itens(pedido: int, servidor: str, banco: str):
    return await pedido_completo_service.list_itens_completo(servidor, banco, pedido)


@router.post("/pedido-completo/{pedido}/itens")
async def add_item(pedido: int, req: ItemSaveRequest, request: Request):
    result = await pedido_completo_service.add_item_completo(req, pedido)
    if result.get("success"):
        codautos = result.get("codautos") or []
        campos = log_auditoria_service.diff_campos(None, _depois_item(req), CAMPOS_ITEM)
        if result.get("kit"):
            desc = f"Kit '{req.produto}' expandido em {len(codautos)} item(ns) no pedido {pedido}"
        elif result.get("clinica_split"):
            desc = f"Serviço '{req.produto}' desdobrado em {len(codautos)} sessão(ões) agendável(is) no pedido {pedido}"
        else:
            desc = f"Item '{req.produto}' incluído no pedido {pedido} (cod {codautos[0] if codautos else '?'})"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="ADD_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=desc,
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedido-completo/{pedido}/itens/{codauto}")
async def update_item(pedido: int, codauto: int, req: ItemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda_prod", "codauto", codauto)
    result = await pedido_completo_service.update_item_completo(req, pedido, codauto)
    if result.get("success"):
        d = _depois_item(req)
        d["p_normal"] = float(req.valor_unitario or 0)
        campos = log_auditoria_service.diff_campos(antes, d, CAMPOS_ITEM)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="EDIT_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=f"Item {codauto} do pedido {pedido} alterado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/pedido-completo/{pedido}/itens/{codauto}")
async def delete_item(
    pedido: int, codauto: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    antes = await log_auditoria_service.get_row_by_pk(servidor, banco, "pedido_venda_prod", "codauto", codauto)
    result = await itens_service.delete_item(servidor, banco, pedido, codauto)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["produto", "qtd_pedida", "p_normal", "desconto", "acrescimo"])
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="PEDIDO_COMP", comando="DEL_ITEM",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(pedido), descricao=f"Item {codauto} excluído do pedido {pedido}",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


# ---------- descontos (idênticos ao Pedido rápido — mesma tabela pedido_venda_prod/
# descontos_concedidos, reaproveitados direto de descontos_service; só o log de
# auditoria usa tela="PEDIDO_COMP") ----------
@router.get("/pedido-completo/{pedido}/descontos")
async def list_descontos(pedido: int, servidor: str, banco: str):
    return await descontos_service.list_descontos(servidor, banco, pedido)


@router.post("/pedido-completo/{pedido}/desconto-geral")
async def aplicar_desconto_geral(pedido: int, req: DescontoGeralRequest, request: Request):
    result = await descontos_service.aplicar_desconto_geral(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="DESC_GERAL",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Desconto geral de R$ {req.valor:.2f} aplicado no pedido {pedido} ({result.get('percentual', 0):g}%)",
            campos_alterados=[{"campo": "desconto_geral", "depois": f"{req.valor:.2f}"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
