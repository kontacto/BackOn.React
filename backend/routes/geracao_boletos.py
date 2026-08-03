"""Rotas de Geração de Boletos — ver services/geracao_boletos_service.py."""
from fastapi import APIRouter

from models.geracao_boletos import ListarTitulosRequest
from services import geracao_boletos_service

router = APIRouter()


@router.post("/geracao-boletos/{cod_banco}/titulos")
async def listar_titulos(cod_banco: int, req: ListarTitulosRequest):
    filtros = req.model_dump(exclude={"servidor", "banco"})
    return await geracao_boletos_service.listar_titulos(req.servidor, req.banco, cod_banco, filtros)
