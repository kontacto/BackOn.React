"""Models do Gestor NFSe (Sefin Nacional/DPS) — ver
`services/gestor_nfse_service.py` pro racional completo."""
from typing import Optional

from models.log_auditoria import AuditFields


class ListarNfseRequest(AuditFields):
    servidor: str
    banco: str
    data_de: Optional[str] = None
    data_ate: Optional[str] = None
    comanda: Optional[int] = None
    cliente: Optional[int] = None
    master: Optional[bool] = False


class NfseConsultarRequest(AuditFields):
    servidor: str
    banco: str
    codigos: list[int]
    master: Optional[bool] = False


class NfseBaixarDanfeRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    master: Optional[bool] = False


class NfseEnviarEmailRequest(AuditFields):
    servidor: str
    banco: str
    codigos: list[int]
    master: Optional[bool] = False
