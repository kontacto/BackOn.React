"""Financeiro > Fluxo de Caixa > Contas — ver services/contas_service.py."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ContaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None  # None = novo registro
    descricao: str = ""
    banco_nome: str = ""
    agencia: str = ""
    numero: str = ""
    saldo_inicial: float = 0
    moeda: str = "Real"
    tipo: int = 0  # 0=Espécie / 1=Banco
    situacao: str = "A"
    conta_principal_painel: bool = False


class ContaDeleteRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
