"""Models de Contingência NFe — ver `services/contingencia_nfe_service.py`
pro racional completo."""
from typing import Optional

from models.log_auditoria import AuditFields


class ContingenciaNfeAbrirRequest(AuditFields):
    servidor: str
    banco: str
    motivo: str
    tipo_contingencia: int
    master: Optional[bool] = False


class ContingenciaNfeFecharRequest(AuditFields):
    servidor: str
    banco: str
    master: Optional[bool] = False
