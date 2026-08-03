"""Rotas de Gestão de Compras > Ressuprimento — ver
services/gestao_compras_service.py. Tela em si é só de consulta/relatório
(sem Gravar/Excluir, sem log de auditoria) — exceto "Gerar Pedido de
Compra" (`/gestao-compras/ressuprimento/gerar-pedidos`), que grava de
verdade (via `pedido_compra_service`) e por isso loga com
`tela="PEDIDO_COMPRA"` (mesma tela/comando que a rota normal de gravar
cabeçalho de Pedido de Compra usa)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.pedido_compra import AtualizarAlertasEstoqueRequest, GerarPedidosRessuprimentoRequest
from services import gestao_compras_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/gestao-compras/curvas")
async def list_curvas(servidor: str, banco: str):
    return await gestao_compras_service.list_curvas(servidor, banco)


@router.get("/gestao-compras/ressuprimento")
async def list_ressuprimento(
    servidor: str, banco: str,
    curva_abc: Optional[str] = None, curva_abc_fin: Optional[str] = None,
    fornecedor: Optional[int] = None, nivel: Optional[str] = None,
    abaixo_minimo: bool = False, abaixo_ressuprimento: bool = False, acima_maximo: bool = False,
    zerado_negativo: bool = False,
    order_by: str = "descricao",
):
    return await gestao_compras_service.list_ressuprimento(
        servidor, banco, curva_abc, curva_abc_fin, fornecedor, nivel,
        abaixo_minimo, abaixo_ressuprimento, acima_maximo, zerado_negativo, order_by,
    )


@router.get("/gestao-compras/ressuprimento/{codigo_int}/ultimas-compras")
async def ultimas_compras(codigo_int: str, servidor: str, banco: str):
    return await gestao_compras_service.ultimas_compras(servidor, banco, codigo_int)


@router.get("/gestao-compras/alertas-estoque")
async def resumo_alertas_estoque(servidor: str, banco: str):
    """Resumo pro card de alertas de estoque na Tela Principal (Gerente/
    Supervisor/Master) — só LÊ o cache compartilhado, nunca recalcula (ver
    `gestao_compras_service._resumo_alertas_estoque_sync`)."""
    return await gestao_compras_service.resumo_alertas_estoque(servidor, banco)


@router.post("/gestao-compras/alertas-estoque/atualizar")
async def atualizar_alertas_estoque(req: AtualizarAlertasEstoqueRequest, request: Request):
    """Recalcula de verdade e grava no cache compartilhado — botão
    "Atualizar" do card, ver `gestao_compras_service._atualizar_alertas_estoque_sync`."""
    result = await gestao_compras_service.atualizar_alertas_estoque(req)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="ALERTAS_ESTOQUE", comando="ATUALIZAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Alertas de estoque recalculados manualmente",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/gestao-compras/ressuprimento/gerar-pedidos")
async def gerar_pedidos_ressuprimento(req: GerarPedidosRessuprimentoRequest, request: Request):
    """"Gerar Pedido de Compra" a partir da seleção — ver
    `gestao_compras_service.gerar_pedidos_ressuprimento` pro racional
    completo (agrupamento por fornecedor preferencial, custo sugerido)."""
    result = await gestao_compras_service.gerar_pedidos_ressuprimento(req)
    if result.get("success"):
        for pedido in result.get("pedidos_criados") or []:
            await log_auditoria_service.registrar_log(
                req.servidor, req.banco, tela="PEDIDO_COMPRA", comando="GRAVAR",
                usuario=req.usuario_alteracao, classe=req.classe,
                referencia=str(pedido["codigo"]),
                descricao=(
                    f"Pedido de Compra {pedido['codigo']} gerado automaticamente a partir dos alertas de "
                    f"estoque (Ressuprimento) — fornecedor {pedido['fornecedor']}, "
                    f"{pedido['itens']}/{pedido['itens_total']} item(ns) incluído(s)"
                ),
                ip_origem=_ip(request), plataforma=req.plataforma,
            )
    return result
