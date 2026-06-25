"""Rotas de Módulos e Recursos (tabela `controle_configuracao`)."""
from typing import Dict

from fastapi import APIRouter
from pydantic import BaseModel

from services import controle_config_service as svc

router = APIRouter()


class SalvarControleRequest(BaseModel):
    servidor: str
    banco: str
    valores: Dict[str, bool] = {}


@router.get("/controle-config/campos")
async def campos():
    return {"success": True, "campos": [{"campo": c, "label": lbl} for c, lbl in svc.CAMPOS]}


@router.get("/controle-config")
async def get_config(servidor: str, banco: str):
    return await svc.read_config(servidor, banco)


@router.post("/controle-config/salvar")
async def salvar(payload: SalvarControleRequest):
    return await svc.save_config(payload.servidor, payload.banco, payload.valores)
