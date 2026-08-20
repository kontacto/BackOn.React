"""Models do Agrupar Comandas em NF-e — ver `services/nfe_agrupada_service.py`
pro racional completo."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ListarComandasAgrupaveisRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int
    classe: Optional[int] = None
    master: Optional[bool] = False


class EmitirNfeAgrupadaRequest(AuditFields):
    servidor: str
    banco: str
    comandas: list[int]
    master: Optional[bool] = False
