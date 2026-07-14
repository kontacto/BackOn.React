"""Rotas de Módulos e Recursos (tabela `controle_configuracao`)."""
import unicodedata
from typing import Dict, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from services import controle_config_service as svc
from services import log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _sort_key(label: str) -> str:
    """Chave de ordenação sem acentos (mesmo padrão de
    `permissoes_service._sort_key`) — .lower() sozinho erra acentuação
    ('Área' iria pro fim, depois de todo ASCII)."""
    norm = unicodedata.normalize("NFKD", label or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


class SalvarControleRequest(BaseModel):
    servidor: str
    banco: str
    valores: Dict[str, bool] = {}
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


@router.get("/controle-config/campos")
async def campos():
    # Ordenado alfabeticamente por label na hora de servir — `svc.CAMPOS` em si
    # fica na ordem que for mais conveniente de editar/ler (mesmo padrão já
    # usado no catálogo de Permissões, `permissoes_service.sort_catalogo`).
    itens = sorted(
        ({"campo": c, "label": lbl} for c, lbl in svc.CAMPOS),
        key=lambda x: _sort_key(x["label"]),
    )
    return {"success": True, "campos": itens}


@router.get("/controle-config")
async def get_config(servidor: str, banco: str):
    return await svc.read_config(servidor, banco)


@router.post("/controle-config/salvar")
async def salvar(payload: SalvarControleRequest, request: Request):
    antes = await svc.read_config(payload.servidor, payload.banco)
    result = await svc.save_config(payload.servidor, payload.banco, payload.valores)
    if result.get("success"):
        campos_validos = {c for c, _ in svc.CAMPOS}
        campos_alvo = [c for c in payload.valores if c in campos_validos]
        campos = log_auditoria_service.diff_campos(
            antes.get("valores") if antes.get("success") else None,
            payload.valores, campos_alvo,
        )
        await log_auditoria_service.registrar_log(
            payload.servidor, payload.banco,
            tela="CONTROLE_CONFIG", comando="GRAVAR",
            usuario=payload.usuario_alteracao, classe=payload.classe,
            referencia=None, descricao=f"Módulos e recursos atualizados ({len(campos)} alteração(ões))",
            campos_alterados=campos or None,
            ip_origem=_ip(request), plataforma=payload.plataforma,
        )
    return result
