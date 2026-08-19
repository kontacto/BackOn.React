"""Gestor NFCe + Contingência NFCe — migração de `Geral\\FrmTraNFC.frm` +
mínimo de `Geral\\FrmConNFC.frm`. Ver `services/gestor_nfce_service.py`/
`services/contingencia_nfce_service.py` pro racional completo."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ListarNfceRequest(BaseModel):
    servidor: str
    banco: str
    data_venda_de: Optional[str] = None
    data_venda_ate: Optional[str] = None
    data_nfce_de: Optional[str] = None
    data_nfce_ate: Optional[str] = None
    comanda: Optional[int] = None
    num_nfce: Optional[int] = None
    cliente: Optional[int] = None
    situacoes: Optional[list[str]] = None
    incluir_sem_nfce: bool = True
    somente_gaps: bool = False
    classe: Optional[int] = None
    master: Optional[bool] = False


class NfceAcaoLoteRequest(AuditFields):
    servidor: str
    banco: str
    comandas: list[int]
    motivo: Optional[str] = None
    master: Optional[bool] = False


class NfceInutilizarRequest(AuditFields):
    servidor: str
    banco: str
    numeros: list[int]
    serie: str
    motivo: str
    master: Optional[bool] = False


class ContingenciaAbrirRequest(AuditFields):
    servidor: str
    banco: str
    motivo: str
    master: Optional[bool] = False


class ContingenciaFecharRequest(AuditFields):
    servidor: str
    banco: str
    master: Optional[bool] = False
