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
    # "Frete por conta" — ver nfe_emissao_service._resolver_mod_frete.
    # 1=Emitente(CIF, padrão), 2=Destinatário(FOB), 3=Terceiros,
    # 4=Próprio Remetente, 5=Próprio Destinatário, 6=Sem transporte.
    paga_frete: Optional[int] = None
    # 2 ações fiscais independentes sobre a MESMA seleção de comandas —
    # decisão direta do usuário (Leandro, 2026-08-21), ver
    # nfe_agrupada_service.py docstring. Pelo menos uma precisa ser True.
    emitir_nfe: bool = True
    emitir_nfse: bool = False
