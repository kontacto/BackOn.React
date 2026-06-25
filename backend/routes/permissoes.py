"""Rotas do módulo de Permissões (sistema 50)."""
from fastapi import APIRouter

from models.permissoes import SalvarPermissoesRequest
from services import permissoes_service

router = APIRouter()


@router.get("/permissoes/catalogo")
async def catalogo():
    """Árvore declarativa de telas/ações (sem dependência de banco)."""
    return {
        "success": True,
        "sistema": permissoes_service.SISTEMA,
        "catalogo": permissoes_service.CATALOGO,
    }


@router.get("/permissoes/classes")
async def classes(servidor: str, banco: str):
    """Grupos de usuário (classes_usuarios) para o combobox."""
    return await permissoes_service.list_classes(servidor, banco)


@router.get("/permissoes")
async def listar(servidor: str, banco: str, classe: int):
    """Permissões já concedidas para a classe (sistema 50)."""
    return await permissoes_service.list_permissoes(servidor, banco, classe)


@router.post("/permissoes/salvar")
async def salvar(payload: SalvarPermissoesRequest):
    return await permissoes_service.salvar_permissoes(payload)
