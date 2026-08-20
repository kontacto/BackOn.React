"""Models da NF-e Avulsa ("Gerar NFe") — ver `services/nfe_avulsa_service.py`
pro racional completo."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class NovoRascunhoRequest(BaseModel):
    servidor: str
    banco: str
    classe: Optional[int] = None
    master: Optional[bool] = False


class SalvarCabecalhoRascunhoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    dados: dict


class SalvarItensRascunhoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    itens: list[dict]


class SalvarVencimentosRascunhoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    vencimentos: list[dict]


class SugerirTributacaoRequest(BaseModel):
    servidor: str
    banco: str
    codigo_int: str
    mov: str
    uf_destino: str
    nao_contribuinte: bool = True
    simples_nacional_cliente: bool = False
    consumidor_final: bool = False


class EmitirNfeAvulsaRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    master: Optional[bool] = False
