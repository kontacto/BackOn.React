"""Rotas do Borderô de Cilindros (Fase 3c) — ver services/bordero_service.py.
Tela só-leitura (consulta em tela + exportação Excel feita no frontend a
partir dos mesmos dados), sem endpoint de gravação — log de auditoria não
se aplica aqui (nada é escrito)."""
from typing import Optional

from fastapi import APIRouter

from services import bordero_service

router = APIRouter()


def _filtros(
    tipo_viagem: Optional[int], status: Optional[str], saida_de: Optional[str], saida_ate: Optional[str],
    retorno_de: Optional[str], retorno_ate: Optional[str], grupo_gas: Optional[str], capacidade: Optional[int],
    pressao: Optional[int], padrao: Optional[str], documento: Optional[str], segmento: Optional[str],
    situacao_contrato: Optional[str], em_aberto: Optional[str],
) -> dict:
    return {
        "tipo_viagem": tipo_viagem,
        "status": [s.strip().upper() for s in status.split(",") if s.strip()] if status else [],
        "saida_de": saida_de, "saida_ate": saida_ate, "retorno_de": retorno_de, "retorno_ate": retorno_ate,
        "grupo_gas": grupo_gas, "capacidade": capacidade, "pressao": pressao, "padrao": padrao,
        "documento": documento, "segmento": segmento, "situacao_contrato": situacao_contrato,
        "em_aberto": None if em_aberto is None else em_aberto.lower() == "true",
    }


@router.get("/bordero-cilindros")
async def list_bordero(
    servidor: str, banco: str,
    tipo_viagem: Optional[int] = None, status: Optional[str] = None,
    saida_de: Optional[str] = None, saida_ate: Optional[str] = None,
    retorno_de: Optional[str] = None, retorno_ate: Optional[str] = None,
    grupo_gas: Optional[str] = None, capacidade: Optional[int] = None, pressao: Optional[int] = None,
    padrao: Optional[str] = None, documento: Optional[str] = None, segmento: Optional[str] = None,
    situacao_contrato: Optional[str] = None, em_aberto: Optional[str] = None,
):
    filtros = _filtros(
        tipo_viagem, status, saida_de, saida_ate, retorno_de, retorno_ate, grupo_gas, capacidade, pressao,
        padrao, documento, segmento, situacao_contrato, em_aberto,
    )
    return await bordero_service.list_bordero(servidor, banco, filtros)


@router.get("/bordero-cilindros/resumo")
async def resumo_bordero(
    servidor: str, banco: str,
    tipo_viagem: Optional[int] = None, status: Optional[str] = None,
    saida_de: Optional[str] = None, saida_ate: Optional[str] = None,
    retorno_de: Optional[str] = None, retorno_ate: Optional[str] = None,
    grupo_gas: Optional[str] = None, capacidade: Optional[int] = None, pressao: Optional[int] = None,
    padrao: Optional[str] = None, documento: Optional[str] = None, segmento: Optional[str] = None,
    situacao_contrato: Optional[str] = None, em_aberto: Optional[str] = None,
):
    filtros = _filtros(
        tipo_viagem, status, saida_de, saida_ate, retorno_de, retorno_ate, grupo_gas, capacidade, pressao,
        padrao, documento, segmento, situacao_contrato, em_aberto,
    )
    return await bordero_service.resumo_bordero(servidor, banco, filtros)
