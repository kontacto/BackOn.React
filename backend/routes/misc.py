"""Rotas diversas: raiz, versão e status (Mongo legado)."""
import json
from pathlib import Path
from typing import List

from fastapi import APIRouter

from db import mongo
from models.schemas import StatusCheck, StatusCheckCreate

router = APIRouter()

# `VERSION` fica na raiz de `backend/` (irmão de `server.py`), gravado
# dentro do zip pelo atualizador (`updater/publish/publish_release.ps1`)
# na hora de publicar uma release — nunca existe em ambiente de
# desenvolvimento local (clonado via git, sem esse arquivo), e essa
# ausência é o estado normal, não um erro. Ver PENDENCIAS.md >
# "Atualizador automático" pro desenho completo.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_VERSION_FILE = _BACKEND_ROOT / "VERSION"


@router.get("/")
async def root():
    return {"message": "Back-On API ativo"}


@router.get("/version")
async def version():
    """Commit publicado nesta instalação — pra troubleshooting remoto
    (confirmar o que está rodando numa máquina de cliente sem precisar
    de acesso direto). `commit`/`published_at` ficam `None` em
    desenvolvimento local (sem arquivo VERSION) ou se o arquivo estiver
    corrompido — nunca derruba o endpoint."""
    if not _VERSION_FILE.is_file():
        return {"commit": None, "published_at": None}
    try:
        data = json.loads(_VERSION_FILE.read_text(encoding="utf-8"))
        return {"commit": data.get("commit"), "published_at": data.get("published_at")}
    except Exception:
        return {"commit": None, "published_at": None}


@router.post("/status", response_model=StatusCheck)
async def create_status_check(input: StatusCheckCreate):
    status_obj = StatusCheck(**input.dict())
    if mongo._MONGO_ENABLED:
        await mongo.db.status_checks.insert_one(status_obj.dict())
    return status_obj


@router.get("/status", response_model=List[StatusCheck])
async def get_status_checks():
    if not mongo._MONGO_ENABLED:
        return []
    docs = await mongo.db.status_checks.find({}, {"_id": 0}).to_list(1000)
    return [StatusCheck(**d) for d in docs]
