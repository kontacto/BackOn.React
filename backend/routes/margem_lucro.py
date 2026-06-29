"""Rotas do relatório de Margem de Lucro e Faturamento (consolidado multiempresa)."""
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from services import margem_lucro_service

router = APIRouter()


class ConexaoEmpresa(BaseModel):
    empresa: str = ""
    servidor: str
    banco: str


class MargemLucroRequest(BaseModel):
    conexoes: List[ConexaoEmpresa]
    data_ini: str  # 'YYYY-MM-DD'
    data_fim: str

    # filtros opcionais
    cod_cliente: Optional[int] = None
    area_atuacao: Optional[int] = None
    nivel: Optional[str] = None
    cod_dav: Optional[int] = None

    # fontes
    incluir_pedidos: bool = True
    incluir_os: bool = True
    incluir_comandas: bool = True

    # situação dos DAVs
    davs_abertos: bool = True
    davs_fechados: bool = True
    davs_faturados: bool = True

    # opções
    itens_os_nao_cobrados: bool = False
    retorna_produtos: bool = True
    retorna_servicos: bool = True
    somente_garantias: bool = False
    somente_venda_direta: bool = False
    resultado_operacional: bool = False


@router.post("/relatorios/margem-lucro")
async def relatorio_margem_lucro(req: MargemLucroRequest):
    conexoes = [c.model_dump() for c in req.conexoes]
    filtros = req.model_dump(exclude={"conexoes"})
    return await margem_lucro_service.margem_lucro(conexoes, filtros)


@router.get("/relatorios/margem-lucro/niveis")
async def relatorio_margem_lucro_niveis(servidor: str, banco: str):
    return await margem_lucro_service.niveis(servidor, banco)
