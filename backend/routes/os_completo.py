"""Rotas da O.S. Completa (`FrmTraOsNew.frm`, Fase 1 — núcleo). Itens/
Descontos/Desconto Geral são COMPARTILHADOS com a O.S. Mobile (mesma
tabela `os_produto`), reaproveitados direto de `os_itens_service` — só o
cabeçalho (campos extras) e Fechar/Faturar/Reabrir/Cancelar são servidos
por `os_completo_service`. O log de auditoria aqui sempre usa
tela="OS_COMP" (catálogo próprio, distinto de "OS") mesmo quando a
operação reaproveita um service da O.S. rápida — mesmo padrão já usado por
`routes/pedido_completo.py` em relação ao Pedido Bar.

Forma de Pagamento continua reaproveitando a rota já existente
`/os/{codigo}/formas-pagamento` diretamente do frontend (mesmo padrão já
usado pelo Pedido Completo — ver `pedido_completo.py`, que também não tem
rota própria de forma de pagamento)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import OSCompletoSaveRequest, OSItemSaveRequest, DescontoGeralRequest, FecharRequest, FaturarOSRequest, PontuacaoSaveRequest, AutorizacaoItensRequest, OSTempoSaveRequest, AlterarExecutorRequest
from services import os_itens_service, os_completo_service, os_tempo_service, log_auditoria_service

router = APIRouter()

CAMPOS_OS = [
    "cliente", "area_atuacao", "descricao_cliente", "obs", "resumo", "status_os", "atendente",
    "placa", "marca", "modelo", "km", "ano", "chassi", "numero_de_serie", "forma_pagamento",
    "forma_pagamento_garantia", "referencia_os", "tecnico_responsavel", "posicao_os",
    "previsao_termino", "data_termino",
]
CAMPOS_ITEM_OS = ["quant", "preco_unitario", "desconto", "acrescimo", "descricao_produto_os", "vendedor", "executor", "situacao"]


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _depois_item_os(req: OSItemSaveRequest) -> dict:
    return {
        "quant": req.qtd, "preco_unitario": req.valor_unitario,
        "desconto": req.desconto, "acrescimo": req.acrescimo,
        "descricao_produto_os": req.complemento,
        "vendedor": req.vendedor, "executor": req.executor,
    }


@router.get("/os-completo/{codigo}")
async def get_os_completo(codigo: int, servidor: str, banco: str):
    return await os_completo_service.get_os_completo(servidor, banco, codigo)


@router.post("/os-completo/create")
async def create_os_completo(req: OSCompletoSaveRequest, request: Request):
    result = await os_completo_service.save_os_completo(req, None)
    if result.get("success"):
        codigo = result.get("codigo")
        campos = log_auditoria_service.diff_campos(None, req.model_dump(), CAMPOS_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. Completa {codigo} criada",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os-completo/{codigo}")
async def update_os_completo(codigo: int, req: OSCompletoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os", "codigo", codigo)
    result = await os_completo_service.save_os_completo(req, codigo)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), CAMPOS_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. Completa {codigo} atualizada ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/fechar")
async def fechar_os_completo(codigo: int, req: FecharRequest, request: Request):
    result = await os_completo_service.fechar_os_completo(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. Completa {codigo} fechada",
            campos_alterados=[{"campo": "situacao", "antes": "A", "depois": "F"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


def _descricao_faturamento(codigo: int, result: dict) -> str:
    partes = []
    if result.get("comanda"):
        partes.append(f"comanda {result['comanda']}")
    if result.get("comanda_garantia"):
        partes.append(f"comanda garantia {result['comanda_garantia']}")
    sufixo = f" ({', '.join(partes)})" if partes else ""
    return f"O.S. Completa {codigo} faturada{sufixo}"


@router.post("/os-completo/{codigo}/faturar")
async def faturar_os_completo(codigo: int, req: FaturarOSRequest, request: Request):
    result = await os_completo_service.faturar_os_completo(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="FATURAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=_descricao_faturamento(codigo, result),
            campos_alterados=[{"campo": "situacao", "antes": result.get("situacao_antes"), "depois": "PG"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/reabrir")
async def reabrir_os_completo(codigo: int, req: FecharRequest, request: Request):
    result = await os_completo_service.reabrir_os_completo(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. Completa {codigo} reaberta",
            campos_alterados=[{"campo": "situacao", "antes": "F", "depois": "A"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/cancelar")
async def cancelar_os_completo(codigo: int, req: FecharRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os", "codigo", codigo)
    result = await os_completo_service.cancelar_os_completo(req, codigo)
    if result.get("success"):
        sit_antes = (antes.get("situacao") if antes else "A") or "A"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="SITUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"O.S. Completa {codigo} cancelada",
            campos_alterados=[{"campo": "situacao", "antes": sit_antes, "depois": "C"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/copiar")
async def copiar_os_completo(codigo: int, req: FecharRequest, request: Request):
    result = await os_completo_service.criar_copia_os(
        req.servidor, req.banco, codigo, req.usuario_alteracao, req.classe, bool(req.master),
    )
    if result.get("success"):
        novo = result.get("codigo")
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="COPIAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(novo), descricao=f"O.S. Completa {novo} criada como cópia da O.S. {codigo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- itens (compartilhados com a O.S. Mobile — mesma tabela
# os_produto, reaproveitados direto de os_itens_service; só o log de
# auditoria usa tela="OS_COMP") ----------
@router.get("/os-completo/{codigo}/itens")
async def list_itens(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_itens(servidor, banco, codigo)


@router.post("/os-completo/{codigo}/itens")
async def add_item(codigo: int, req: OSItemSaveRequest, request: Request):
    result = await os_itens_service.add_item(req, codigo)
    if result.get("success"):
        cod_os_prods = result.get("cod_os_prods") or []
        campos = log_auditoria_service.diff_campos(None, _depois_item_os(req), CAMPOS_ITEM_OS)
        if result.get("os_agenda_split"):
            desc = f"Serviço '{req.produto}' desdobrado em {len(cod_os_prods)} atendimento(s) agendável(is) na O.S. Completa {codigo}"
        else:
            desc = f"Item '{req.produto}' incluído na O.S. Completa {codigo} (cod {result.get('cod_os_prod')})"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="ADD_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo), descricao=desc,
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os-completo/{codigo}/itens/{cod_os_prod}")
async def update_item(codigo: int, cod_os_prod: int, req: OSItemSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os_produto", "cod_os_prod", cod_os_prod)
    result = await os_itens_service.update_item(req, codigo, cod_os_prod)
    if result.get("success"):
        d = _depois_item_os(req)
        d["preco_unitario"] = float(req.valor_unitario or 0)
        campos = log_auditoria_service.diff_campos(antes, d, CAMPOS_ITEM_OS)
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="EDIT_ITEM",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo), descricao=f"Item {cod_os_prod} da O.S. Completa {codigo} alterado ({len(campos)} alteração(ões))",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/os-completo/{codigo}/itens/{cod_os_prod}")
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
            servidor, banco, tela="OS_COMP", comando="DEL_ITEM",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(codigo), descricao=f"Item {cod_os_prod} excluído da O.S. Completa {codigo}",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.put("/os-completo/{codigo}/itens/{cod_os_prod}/pontuacao")
async def save_pontuacao(codigo: int, cod_os_prod: int, req: PontuacaoSaveRequest, request: Request):
    result = await os_itens_service.save_pontuacao(req, codigo, cod_os_prod)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="PONTUACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=(
                f"Pontuação do item {cod_os_prod} da O.S. Completa {codigo} gravada "
                f"(Executor={req.pontuacao_e}, Vendedor={req.pontuacao_v}, Atendente={req.pontuacao_a})"
            ),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os-completo/{codigo}/itens/{cod_os_prod}/executor")
async def alterar_executor_pos_fechamento(codigo: int, cod_os_prod: int, req: AlterarExecutorRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "os_produto", "cod_os_prod", cod_os_prod)
    result = await os_itens_service.alterar_executor(req, codigo, cod_os_prod)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(
            antes, {"vendedor": req.vendedor, "executor": req.executor}, ["vendedor", "executor"],
        )
        desc = f"Alteração de Executor/Vendedor pós-fechamento no item {cod_os_prod} da O.S. Completa {codigo}"
        propagados = result.get("propagados") or []
        if propagados:
            desc += f" (propagado pra {len(propagados)} outro(s) item(ns))"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="ALT_EXECUTOR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=desc,
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


def _autorizacao_log_desc(base: str, result: dict) -> str:
    ok_key = "autorizados" if "autorizados" in result else ("expedidos" if "expedidos" in result else "removidos")
    ok = result.get(ok_key) or []
    bloq = result.get("bloqueados") or []
    txt = f"{base}: {len(ok)} item(ns) ({ok_key})"
    if bloq:
        txt += f", {len(bloq)} bloqueado(s)"
    return txt


@router.post("/os-completo/{codigo}/itens/autorizar")
async def autorizar_itens(codigo: int, req: AutorizacaoItensRequest, request: Request):
    result = await os_itens_service.autorizar_itens(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="AUTORIZAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=_autorizacao_log_desc(f"Autorização de itens da O.S. Completa {codigo}", result),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/itens/remover-autorizacao")
async def remover_autorizacao_itens(codigo: int, req: AutorizacaoItensRequest, request: Request):
    result = await os_itens_service.remover_autorizacao_itens(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="AUTORIZAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=_autorizacao_log_desc(f"Remoção de autorização de itens da O.S. Completa {codigo}", result),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/itens/expedir")
async def expedir_itens(codigo: int, req: AutorizacaoItensRequest, request: Request):
    result = await os_itens_service.expedir_itens(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="EXPEDIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=_autorizacao_log_desc(f"Autorização de expedição de itens da O.S. Completa {codigo}", result),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/os-completo/{codigo}/itens/remover-expedicao")
async def remover_expedicao_itens(codigo: int, req: AutorizacaoItensRequest, request: Request):
    result = await os_itens_service.remover_expedicao_itens(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="EXPEDIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=_autorizacao_log_desc(f"Remoção de expedição de itens da O.S. Completa {codigo}", result),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/os-completo/{codigo}/tempo")
async def list_tempo(codigo: int, servidor: str, banco: str):
    return await os_tempo_service.list_tempo(servidor, banco, codigo)


@router.post("/os-completo/{codigo}/tempo")
async def add_tempo(codigo: int, req: OSTempoSaveRequest, request: Request):
    result = await os_tempo_service.save_tempo(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="TEMPO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Tempo Gasto incluído na O.S. Completa {codigo} (serviço '{req.codigo_interno}')",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.put("/os-completo/{codigo}/tempo/{tempo_codigo}")
async def update_tempo(codigo: int, tempo_codigo: int, req: OSTempoSaveRequest, request: Request):
    result = await os_tempo_service.save_tempo(req, codigo, tempo_codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="TEMPO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Tempo Gasto {tempo_codigo} alterado na O.S. Completa {codigo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/os-completo/{codigo}/tempo/{tempo_codigo}")
async def delete_tempo(
    codigo: int, tempo_codigo: int, servidor: str, banco: str, request: Request,
    usuario_alteracao: Optional[int] = None, classe: Optional[int] = None, plataforma: Optional[str] = None,
):
    result = await os_tempo_service.delete_tempo(servidor, banco, codigo, tempo_codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="OS_COMP", comando="TEMPO",
            usuario=usuario_alteracao, classe=classe,
            referencia=str(codigo),
            descricao=f"Tempo Gasto {tempo_codigo} excluído da O.S. Completa {codigo}",
            ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.get("/os-completo/{codigo}/requisicoes-vinculadas")
async def list_requisicoes_vinculadas(codigo: int, servidor: str, banco: str):
    return await os_completo_service.list_requisicoes_vinculadas(servidor, banco, codigo)


@router.get("/os-completo/{codigo}/descontos")
async def list_descontos(codigo: int, servidor: str, banco: str):
    return await os_itens_service.list_descontos(servidor, banco, codigo)


@router.get("/os-completo/{codigo}/analise")
async def analise(codigo: int, servidor: str, banco: str):
    return await os_itens_service.analise(servidor, banco, codigo)


@router.post("/os-completo/{codigo}/desconto-geral")
async def desconto_geral(codigo: int, req: DescontoGeralRequest, request: Request):
    result = await os_itens_service.aplicar_desconto_geral(req, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="DESC_GERAL",
            usuario=req.usuario_codigo, classe=req.classe,
            referencia=str(codigo),
            descricao=f"Desconto geral de R$ {req.valor:.2f} aplicado na O.S. Completa {codigo} ({result.get('percentual', 0):g}%)",
            campos_alterados=[{"campo": "desconto_geral", "depois": f"{req.valor:.2f}"}],
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
