"""Curva ABC e Estoques — ver services/curva_abc_service.py."""
from typing import List, Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class FaixaCurva(BaseModel):
    curva: str
    percentual: float


class GerarCurvaRequest(AuditFields):
    servidor: str
    banco: str
    data_ini: str
    data_fim: str
    tipo: str  # "financeira" | "quantidade"
    faixas: List[FaixaCurva]
    nivel: Optional[str] = None


class ReprocessarEstoquesRequest(AuditFields):
    servidor: str
    banco: str
    data_ini: str
    data_fim: str
    grau_atendimento: float
    nivel: Optional[str] = None
    atualizar_minimo: bool = False
    atualizar_ressuprimento: bool = False
    atualizar_maximo: bool = False
    atualizar_consumo: bool = False
