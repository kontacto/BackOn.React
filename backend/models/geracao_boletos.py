"""Geração de Boletos (Financeiro > Cobranças) — ver
services/geracao_boletos_service.py, services/boleto_pdf_service.py,
PENDENCIAS.md > "Boleto em PDF"."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


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


class TitulosBoletoRequest(AuditFields):
    servidor: str
    banco: str
    titulos: list[int]
