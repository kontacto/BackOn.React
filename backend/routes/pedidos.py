"""Rotas de pedidos (cabeçalho) e seus itens."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    PedidosListRequest, PedidoSaveRequest, ItemSaveRequest, FecharRequest,
    TaxaServicoRequest, PedidoEntregueRequest, FormaPagSimplesRequest,
    FormaPagamentoAddRequest, FormaPagamentoUpdateRequest, FormaPagamentoDeleteRequest,
)
from services import pedidos_service, itens_service, log_auditoria_service, forma_pagamento_service

router = APIRouter()

CAMPOS_PEDIDO = ["cliente", "vendedor", "validade", "obs", "area_atuacao", "previsao_entrega", "hora_entrega", "forma_pag"]
CAMPOS_ITEM = ["qtd_pedida", "p_normal", "desconto", "acrescimo", "descricao_produto"]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _depois_item(req: ItemSaveRequest) -> dict:
    return {
        "qtd_pedida": req.qtd, "p_normal": req.valor_unitario,
        "desconto": req.desconto, "acrescimo": req.acrescimo,
        "descricao_produto": req.complemento,
    }


def _depois_item_update(req: ItemSaveRequest) -> dict:
    """Como `_depois_item`, mas espelha o fallback de `_update_item_sync`
    (valor_unitario omitido vira 0, não o preço padrão do produto — diferente
    do fallback do ADD, que resolve via `_resolve_produto`)."""
    d = _depois_item(req)
    d["p_normal"] = float(req.valor_unitario or 0)
    return d


@router.post("/pedidos")
async def list_pedidos(req: PedidosListRequest):
    return await pedidos_service.list_pedidos(req)


@router.get("/pedidos/aberto-por-cliente")
async def pedido_aberto_por_cliente(cliente: int, servidor: str, banco: str):
    # Precisa vir ANTES de /pedidos/{pedido} — mesmo formato de path
    # (um segmento), "aberto-por-cliente" cairia no {pedido}:int e daria
    # 422 se essa rota viesse depois (ordem de registro importa no FastAPI).
    return await pedidos_service.pedido_aberto_por_cliente(servidor, banco, cliente)


@router.get("/pedidos/{pedido}")
async def get_pedido(pedido: int, servidor: str, banco: str):
    return await pedidos_service.get_pedido(servidor, banco, pedido)


@router.post("/pedidos/create")
async def create_pedido(req: PedidoSaveRequest, request: Request):
    result = await pedidos_service.save_pedido(req, None)
    if result.get("success"):
        pedido_id = result.get("pedido")
        campos = log_auditoria_service.diff_campos(None, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido_id), descricao=f"Pedido {pedido_id} criado",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedidos/{pedido}")
async def update_pedido(pedido: int, req: PedidoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda", "pedido", pedido)
    result = await pedidos_service.save_pedido(req, pedido)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), CAMPOS_PEDIDO)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} atualizado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/fechar")
async def fechar_pedido(pedido: int, req: FecharRequest, request: Request):
    result = await pedidos_service.fechar_pedido(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} fechado",
            campos_alterados=[{"campo": "situacao", "antes": "A", "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/faturar")
async def faturar_pedido(pedido: int, req: FecharRequest, request: Request):
    result = await pedidos_service.faturar_pedido(req, pedido)
    if result.get("success"):
        situacao_antes = result.get("situacao_antes") or "F"
        descricao = f"Pedido {pedido} faturado (comanda {result.get('comanda')})"
        if situacao_antes == "A":
            descricao += " — fechado automaticamente antes de faturar"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=descricao,
            campos_alterados=[{"campo": "situacao", "antes": situacao_antes, "depois": "PG"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/reabrir")
async def reabrir_pedido(pedido: int, req: FecharRequest, request: Request):
    result = await pedidos_service.reabrir_pedido(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} reaberto",
            campos_alterados=[{"campo": "situacao", "antes": "F", "depois": "A"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/cancelar")
async def cancelar_pedido(pedido: int, req: FecharRequest, request: Request):
    result = await pedidos_service.cancelar_pedido(req, pedido)
    if result.get("success"):
        situacao_antes = result.get("situacao_antes") or "A"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido} cancelado",
            campos_alterados=[{"campo": "situacao", "antes": situacao_antes, "depois": "C"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/entregue")
async def toggle_entregue(pedido: int, req: PedidoEntregueRequest, request: Request):
    """Checkbox 'Pedido Entregue' — grava direto no clique, fora do fluxo
    normal de Gravar (FrmManPedBar.frm, Check88_Click)."""
    result = await pedidos_service.toggle_entregue(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="ENTREGUE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Pedido {pedido} marcado como {'entregue' if req.entregue else 'não entregue'}",
            campos_alterados=[{"campo": "pedido_entregue", "depois": req.entregue}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/forma-pag-simples")
async def set_forma_pag_simples(pedido: int, req: FormaPagSimplesRequest, request: Request):
    """Combobox simples 'Forma de Pagamento' do cabeçalho — grava direto ao
    trocar, fora do fluxo normal de Gravar (ver
    `pedidos_service._set_forma_pag_simples_sync` pro porquê)."""
    result = await pedidos_service.set_forma_pag_simples(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="FORMA_PAG",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido}: forma de pagamento definida como '{req.forma_pag}'",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- forma de pagamento (FrmForPag.frm) ----------
@router.get("/pedidos/{pedido}/formas-pagamento")
async def list_formas_pagamento(pedido: int, servidor: str, banco: str):
    return await forma_pagamento_service.list_formas_pagamento(servidor, banco, "PED", pedido)


@router.post("/pedidos/{pedido}/formas-pagamento")
async def add_forma_pagamento(pedido: int, req: FormaPagamentoAddRequest, request: Request):
    req.tipo_dav = "PED"
    result = await forma_pagamento_service.add_forma_pagamento(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="FORMA_PAG",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Pedido {pedido}: forma de pagamento {req.tipo}/{req.forma_pag} lançada (R$ {req.valor})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedidos/{pedido}/formas-pagamento/{sequencia}")
async def update_forma_pagamento(pedido: int, sequencia: int, req: FormaPagamentoUpdateRequest, request: Request):
    req.sequencia = sequencia
    req.tipo_dav = "PED"
    result = await forma_pagamento_service.update_forma_pagamento(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="FORMA_PAG",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Pedido {pedido}: forma de pagamento {req.tipo}#{sequencia} atualizada (R$ {req.valor})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/pedidos/{pedido}/formas-pagamento/{sequencia}")
async def delete_forma_pagamento(pedido: int, sequencia: int, req: FormaPagamentoDeleteRequest, request: Request):
    req.sequencia = sequencia
    req.tipo_dav = "PED"
    result = await forma_pagamento_service.delete_forma_pagamento(req, pedido)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="FORMA_PAG",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(pedido), descricao=f"Pedido {pedido}: forma de pagamento {req.tipo}#{sequencia} excluída",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- itens do pedido ----------
@router.get("/pedidos/{pedido}/itens")
async def list_itens(pedido: int, servidor: str, banco: str):
    return await itens_service.list_itens(servidor, banco, pedido)


@router.post("/pedidos/{pedido}/itens")
async def add_item(pedido: int, req: ItemSaveRequest, request: Request):
    result = await itens_service.add_item(req, pedido)
    if result.get("success"):
        codauto = result.get("codauto")
        campos = log_auditoria_service.diff_campos(None, _depois_item(req), CAMPOS_ITEM)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="ADD_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=f"Item '{req.produto}' incluído no pedido {pedido} (cod {codauto})",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/pedidos/{pedido}/itens/{codauto}")
async def update_item(pedido: int, codauto: int, req: ItemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "pedido_venda_prod", "codauto", codauto)
    result = await itens_service.update_item(req, pedido, codauto)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, _depois_item_update(req), CAMPOS_ITEM)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="EDIT_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido), descricao=f"Item {codauto} do pedido {pedido} alterado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/pedidos/{pedido}/itens/{codauto}")
async def delete_item(
    pedido: int, codauto: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    antes = await log_auditoria_service.get_row_by_pk(servidor, banco, "pedido_venda_prod", "codauto", codauto)
    result = await itens_service.delete_item(servidor, banco, pedido, codauto)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["produto", "qtd_pedida", "p_normal", "desconto", "acrescimo"])
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="PEDIDO", comando="DEL_ITEM",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(pedido), descricao=f"Item {codauto} excluído do pedido {pedido}",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.post("/pedidos/{pedido}/taxa-servico")
async def add_taxa_servico(pedido: int, req: TaxaServicoRequest, request: Request):
    """Botão 'Incluir Tx Serviço [F10]' do Pedido Bar — 10% do subtotal
    atual, código de serviço reservado 'S002' (ver itens_service.py)."""
    result = await itens_service.add_taxa_servico(req, pedido)
    if result.get("success"):
        codauto = result.get("codauto")
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO", comando="TX_SERVICO",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(pedido),
            descricao=f"Taxa de serviço incluída no pedido {pedido} (cod {codauto}, R$ {result.get('valor')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
