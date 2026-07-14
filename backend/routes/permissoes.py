"""Rotas do módulo de Permissões (sistema 50)."""
from fastapi import APIRouter, Request

from models.permissoes import SalvarPermissoesRequest
from services import controle_config_service, log_auditoria_service, permissoes_service

router = APIRouter()


def _ip(request: Request) -> str | None:
    return request.client.host if request.client else None


@router.get("/permissoes/catalogo")
async def catalogo(servidor: str | None = None, banco: str | None = None):
    """Árvore de telas/ações, já filtrada pelos módulos ligados (controle_configuracao)."""
    cat = permissoes_service.CATALOGO
    if servidor and banco:
        cfg = await controle_config_service.read_config(servidor, banco)
        if cfg.get("success"):
            disabled = permissoes_service.disabled_telas(cfg["valores"])
            cat = permissoes_service.filter_catalogo(disabled)
    cat = permissoes_service.sort_catalogo(cat)
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
async def salvar(payload: SalvarPermissoesRequest, request: Request):
    antes = await permissoes_service.list_permissoes(payload.servidor, payload.banco, payload.classe)
    result = await permissoes_service.salvar_permissoes(payload)
    if result.get("success"):
        antes_chaves = {
            f"{it['tela']}.{it['comando'] or 'TELA'}"
            for it in (antes.get("items") or [])
        }
        depois_chaves = {
            f"{it.tela}.{it.comando or 'TELA'}"
            for it in payload.itens
        }
        campos = log_auditoria_service.diff_set_membership(antes_chaves, depois_chaves)
        await log_auditoria_service.registrar_log(
            payload.servidor, payload.banco,
            tela="PERMISSOES", comando="GRAVAR",
            usuario=payload.usuario_alteracao, classe=payload.classe,
            referencia=str(payload.classe),
            descricao=f"Permissões do grupo {payload.classe} atualizadas ({len(campos)} alteração(ões))",
            campos_alterados=campos or None,
            ip_origem=_ip(request), plataforma=payload.plataforma,
        )
    return result
