"""Rotas do módulo de Permissões (sistema 50)."""
from fastapi import APIRouter

from models.permissoes import SalvarPermissoesRequest
from services import controle_config_service, permissoes_service

router = APIRouter()


@router.get("/permissoes/catalogo")
async def catalogo(servidor: str | None = None, banco: str | None = None):
    """Árvore de telas/ações, já filtrada pelos módulos ligados (controle_configuracao)."""
    cat = permissoes_service.CATALOGO
    if servidor and banco:
        cfg = await controle_config_service.read_config(servidor, banco)
        if cfg.get("success"):
            disabled = permissoes_service.disabled_telas(cfg["valores"])
            cat = permissoes_service.filter_catalogo(disabled)
    return {
        "success": True,
        "sistema": permissoes_service.SISTEMA,
        "catalogo": cat,
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
