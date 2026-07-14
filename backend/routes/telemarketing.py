"""Rotas de Cadastros > Telemarketing.

Gravar contato é registrado em `log_auditoria` — mesmo padrão das telas
recentes desta sessão (Contatos, Equipamentos). Não há Excluir nesta tela
(o legado não tem essa ação — só acrescenta ao histórico do cliente).
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, telemarketing_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class SaveContatoRequest(AuditFields):
    servidor: str
    banco: str
    cliente: int
    texto: str
    agendamento: Optional[str] = None


class SelecionarRequest(AuditFields):
    servidor: str
    banco: str
    dia_contato: Optional[int] = None
    dia_entrega: Optional[int] = None
    vendedor: Optional[int] = None
    regiao: Optional[int] = None
    segmento: Optional[str] = None
    rota: Optional[int] = None
    tipo_cliente: Optional[int] = None
    situacao: Optional[str] = None
    cliente_termo: Optional[str] = None
    cgc_cpf: Optional[str] = None
    bairro: Optional[str] = None
    ultimo_contato_de: Optional[str] = None
    ultimo_contato_ate: Optional[str] = None
    agendamento_de: Optional[str] = None
    agendamento_ate: Optional[str] = None
    ordenar_por: Optional[str] = "ultimo_contato"


@router.get("/telemarketing/cliente/{codigo}")
async def get_cliente(codigo: int, servidor: str, banco: str):
    return await telemarketing_service.get_cliente(servidor, banco, codigo)


@router.post("/telemarketing/contato")
async def save_contato(req: SaveContatoRequest, request: Request):
    result = await telemarketing_service.save_contato(
        req.servidor, req.banco, req.cliente, req.texto, req.agendamento, req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="TELEMARKETING", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.cliente),
            descricao=f"Contato registrado para cliente #{req.cliente}"
                      + (f" (agendado p/ {req.agendamento})" if req.agendamento else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/telemarketing/selecionar")
async def selecionar(req: SelecionarRequest):
    filtros = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    return await telemarketing_service.list_selecionar(req.servidor, req.banco, filtros)
