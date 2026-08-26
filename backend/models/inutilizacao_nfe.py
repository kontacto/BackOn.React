"""Models de Inutilização de Faixa de NFe (modelo 55) — ver
`services/inutilizacao_nfe_service.py` pro racional completo."""
from typing import Optional

from models.log_auditoria import AuditFields


class InutilizarFaixaNfeRequest(AuditFields):
    servidor: str
    banco: str
    serie: str
    numero_inicial: int
    numero_final: int
    motivo: str
    master: Optional[bool] = False
