"""Geração de Boletos (Financeiro > Cobranças) — ver
services/geracao_boletos_service.py, PENDENCIAS.md > "Geração de Boletos"."""
from typing import Optional

from pydantic import BaseModel


class ListarTitulosRequest(BaseModel):
    servidor: str
    banco: str
    emissao_de: Optional[str] = None
    emissao_ate: Optional[str] = None
    vencimento_de: Optional[str] = None
    vencimento_ate: Optional[str] = None
    duplicata: Optional[int] = None
    numero_boleto: Optional[int] = None
    cliente_codigo: Optional[int] = None  # resolvido pelo campo de busca de cliente ([GLOBAL], ver CLAUDE.md)
    so_sem_boleto: bool = False
    somente_registrados: bool = False
