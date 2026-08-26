"""Rota do recurso "Sugerir com IA" (Descomplicar Taxas, Apoio Fiscal/
"João") — ver `services/taxas_ia_service.py` pro racional completo e as
regras de segurança (nunca inventa CST/CFOP/ClassTrib/alíquota livre)."""
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from services import taxas_ia_service

router = APIRouter()


class SugerirTaxaRequest(BaseModel):
    servidor: str
    banco: str
    destino: Optional[str] = None
    cfop: Optional[str] = None
    cod_icms: Optional[str] = None
    tipo_mov: Optional[str] = None
    simples_nacional: bool = False
    consumidor_final: bool = False
    descricao_operacao: Optional[str] = None


@router.post("/taxas/sugerir-ia")
async def sugerir_ia(req: SugerirTaxaRequest):
    return await taxas_ia_service.sugerir_tributacao(
        req.servidor, req.banco,
        destino=req.destino, cfop=req.cfop, cod_icms=req.cod_icms, tipo_mov=req.tipo_mov,
        simples_nacional=req.simples_nacional, consumidor_final=req.consumidor_final,
        descricao_operacao=req.descricao_operacao,
    )
