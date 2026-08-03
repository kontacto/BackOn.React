"""Cotação de Compra (Transações > Gestão de Compras > Compra) — ver
services/cotacao_compra_service.py. Tabelas novas (não existem no legado):
`cotacao_compra`, `cotacao_compra_item`, `cotacao_compra_resposta`."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class CotacaoItemIncluirRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None  # None = cria uma cotação nova
    descricao: str = ""
    produto: str
    qtd: float


class CotacaoItemExcluirRequest(AuditFields):
    servidor: str
    banco: str


class CotacaoRespostaIncluirRequest(AuditFields):
    servidor: str
    banco: str
    fornecedor: int
    valor_unit: float
    marca: Optional[str] = None
    prazo: Optional[str] = None
    cond_pagamento: Optional[str] = None


class CotacaoRespostaExcluirRequest(AuditFields):
    servidor: str
    banco: str


class CotacaoAcaoRequest(AuditFields):
    servidor: str
    banco: str
