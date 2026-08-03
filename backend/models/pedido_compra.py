"""Pedido de Compra (Transações > Gestão de Compras > Compra) — ver
services/pedido_compra_service.py. Tabelas `pedido`/`pedido_itens` já
existem no schema legado."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class PedidoCabecalhoRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None  # None = cria um pedido novo
    data: str
    fornecedor: int
    pedido_fornecedor: Optional[str] = None
    prazo: Optional[int] = None
    forma_pagamento: Optional[str] = None
    ac_cliente: Optional[str] = None
    transportadora: Optional[str] = None
    data_entrega: Optional[str] = None
    obs_pedido: Optional[str] = None
    tipo_frete: int = 0  # 0=CIF, 1=FOB


class ItemFiscal(BaseModel):
    qtd_un_compra: Optional[float] = 1
    base_icms: Optional[float] = 0
    valor_icms: Optional[float] = 0
    base_ipi: Optional[float] = 0
    alqt_ipi: Optional[float] = 0
    valor_ipi: Optional[float] = 0
    base_sub: Optional[float] = 0
    valor_sub: Optional[float] = 0
    base_iss: Optional[float] = 0
    valor_iss: Optional[float] = 0
    frete: Optional[float] = 0
    seguro: Optional[float] = 0
    despesas: Optional[float] = 0
    desconto: Optional[float] = 0


class PedidoItemIncluirRequest(AuditFields):
    servidor: str
    banco: str
    produto: str
    qtd: float
    p_unit: float
    fiscal: ItemFiscal = ItemFiscal()


class PedidoItemEditarRequest(AuditFields):
    servidor: str
    banco: str
    qtd: float
    p_unit: float
    fiscal: ItemFiscal = ItemFiscal()


class PedidoItemExcluirRequest(AuditFields):
    servidor: str
    banco: str


class PedidoAcaoRequest(AuditFields):
    servidor: str
    banco: str


class GerarPedidosRessuprimentoItem(BaseModel):
    codigo_int: str
    qtd: float


class GerarPedidosRessuprimentoRequest(AuditFields):
    """"Gerar Pedido de Compra" a partir da seleção na tela de Ressuprimento
    (Gestão de Compras) — pedido explícito do usuário, 2026-07-20: fecha o
    ciclo alerta → ação sem digitar tudo de novo numa tela separada. Ver
    `gestao_compras_service._gerar_pedidos_ressuprimento_sync`."""
    servidor: str
    banco: str
    itens: list[GerarPedidosRessuprimentoItem]


class AtualizarAlertasEstoqueRequest(AuditFields):
    """Recalcula e grava no cache compartilhado (`alertas_estoque_cache`)
    os contadores do card "Alertas de Estoque" da Tela Principal — pedido
    explícito do usuário, 2026-07-21: o resultado deve ser o MESMO pra
    todos os usuários com acesso gerencial ao card (não uma busca por
    sessão/navegador), atualizado só quando alguém aperta "Atualizar". Ver
    `gestao_compras_service._atualizar_alertas_estoque_sync`."""
    servidor: str
    banco: str
    master: Optional[bool] = False
