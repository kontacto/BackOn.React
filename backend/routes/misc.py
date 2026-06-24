"""Rotas diversas: raiz e status (Mongo legado)."""
from typing import List

from fastapi import APIRouter

from db import mongo
from models.schemas import StatusCheck, StatusCheckCreate

router = APIRouter()


@router.get("/")
async def root():
    return {"message": "Back-On API ativo"}


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
