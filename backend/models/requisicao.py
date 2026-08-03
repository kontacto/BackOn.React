"""Requisição (Transações > Movimentações) — pedido interno de
produtos/serviços com fechamento (baixa de estoque), reabertura e
cancelamento. Legado: `FrmManReq.frm`. Tabelas: `requisicao`, `rec_prod`."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class RequisicaoItemIncluirRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None  # None = cria uma requisição nova
    descricao: str = ""
    produto: str
    qtd: float
    p_unit: float


class RequisicaoItemExcluirRequest(AuditFields):
    servidor: str
    banco: str


class RequisicaoAcaoRequest(AuditFields):
    servidor: str
    banco: str
