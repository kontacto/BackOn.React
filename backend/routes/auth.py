"""Rota de login."""
from fastapi import APIRouter, HTTPException

from models.schemas import LoginRequest, LoginResponse
from services import auth_service

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest):
    if not payload.servidor.strip() or not payload.banco.strip():
        raise HTTPException(status_code=400, detail="Servidor e Banco são obrigatórios.")
    if not payload.usuario.strip() or not payload.senha:
        raise HTTPException(status_code=400, detail="Usuário e senha são obrigatórios.")
    return await auth_service.login(payload)
