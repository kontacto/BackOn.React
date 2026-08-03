"""Inventário de Estoque (Transações > Inventário) — Fase 1: núcleo manual
(Abertura, Digitação, Fechar, Cancelar). Legado: `FrmInvAbe.frm`,
`FrmInvDig.frm`, `Geral\\Inventario.bas` (`Fecha_Inventario`/
`Cancela_Inventario`). Ver PENDENCIAS.md > "Inventário" pro rastreio
completo (regras de negócio, tabelas confirmadas ao vivo, decisões de
escopo)."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class InventarioAbrirRequest(AuditFields):
    servidor: str
    banco: str
    data: str  # yyyy-mm-dd — data do balanço
    tipo: str  # "G" (Geral) ou "C" (Contábil)


class InventarioItemRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str  # termo de busca (codigo_int/codigo_fab/codigo_bar/chassi)
    qtd: float
    preco_custo: Optional[float] = None
    preco_venda: Optional[float] = None
    custo_inventario: Optional[float] = None
    custo_reposicao: Optional[float] = None


class InventarioFecharRequest(AuditFields):
    servidor: str
    banco: str


class InventarioCancelarRequest(AuditFields):
    servidor: str
    banco: str
