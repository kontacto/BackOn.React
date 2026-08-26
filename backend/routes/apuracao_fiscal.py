"""Rota de Apuração Fiscal — ver `services/apuracao_fiscal_service.py`
pro rastreio completo (fonte `Geral\\FrmCalImp.frm`). Puramente consulta,
sem escrita — não precisa de log de auditoria (mesmo critério já usado
pelos demais relatórios do sistema)."""
from typing import Optional

from fastapi import APIRouter

from services import apuracao_fiscal_service

router = APIRouter()


@router.get("/apuracao-fiscal")
async def apurar(
    servidor: str, banco: str, modo: str = "NFCE",
    data_ini: Optional[str] = None, data_fim: Optional[str] = None, cfop: Optional[str] = None,
):
    return await apuracao_fiscal_service.apurar(servidor, banco, modo=modo, data_ini=data_ini, data_fim=data_fim, cfop=cfop)
