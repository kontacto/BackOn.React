"""Rotas do módulo Agenda (Clínica) — item de Serviço do Pedido Geral E
agendamento avulso (direto da grade semanal), grade de disponibilidade,
troca de profissional, verificação de Revisão/Garantia e Faturar avulso. Ver
`services/agenda_service.py` e PENDENCIAS.md > "Transações" > "Pedido Geral
— Fase B: Clínica (Agendamento)"."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import AgendarItemRequest, TrocarProfissionalRequest, FaturarAgendaAvulsoRequest
from services import agenda_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/agenda/profissionais")
async def list_profissionais(servidor: str, banco: str, servico: Optional[str] = None, especialidade: Optional[int] = None):
    return await agenda_service.list_profissionais_agenda(servidor, banco, servico, especialidade)


@router.get("/agenda/grade")
async def get_grade(servidor: str, banco: str, funcionario: int, data_ini: str, data_fim: str):
    return await agenda_service.list_grade(servidor, banco, funcionario, data_ini, data_fim)


@router.get("/agenda/disponiveis")
async def get_horarios_disponiveis(servidor: str, banco: str, funcionario: int, data_ini: str, meses: int = 1):
    return await agenda_service.list_horarios_disponiveis(servidor, banco, funcionario, data_ini, meses)


@router.get("/agenda/garantia")
async def get_garantia(servidor: str, banco: str, cliente: int, servico: str):
    return await agenda_service.verificar_garantia(servidor, banco, cliente, servico)


# ---------- vinculado a um item de Pedido Geral (codauto) ----------

@router.get("/agenda/item/{codauto}")
async def get_agendamento_item(codauto: int, servidor: str, banco: str):
    return await agenda_service.get_agendamento_item(servidor, banco, codauto)


@router.post("/agenda/item/{codauto}")
async def agendar_item(codauto: int, req: AgendarItemRequest, request: Request):
    result = await agenda_service.salvar_agendamento(req, codauto)
    if result.get("success"):
        ag = result.get("agendamento") or {}
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="AGENDAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codauto),
            descricao=f"Item {codauto} agendado para {ag.get('data')} às {ag.get('hora_ini')} ({ag.get('profissional')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/agenda/item/{codauto}/cancelar")
async def cancelar_agendamento(codauto: int, req: AgendarItemRequest, request: Request):
    result = await agenda_service.cancelar_agendamento(req, codauto)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PEDIDO_COMP", comando="AGENDAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codauto), descricao=f"Agendamento do item {codauto} cancelado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- vinculado a um item de O.S. Completa (cod_os_prod) ----------

@router.get("/agenda/os-item/{cod_os_prod}")
async def get_agendamento_item_os(cod_os_prod: int, servidor: str, banco: str):
    return await agenda_service.get_agendamento_item(servidor, banco, cod_os_prod, origem="os")


@router.post("/agenda/os-item/{cod_os_prod}")
async def agendar_item_os(cod_os_prod: int, req: AgendarItemRequest, request: Request):
    result = await agenda_service.salvar_agendamento(req, cod_os_prod, origem="os", tela="OS_COMP")
    if result.get("success"):
        ag = result.get("agendamento") or {}
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="AGENDAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(cod_os_prod),
            descricao=f"Item {cod_os_prod} agendado para {ag.get('data')} às {ag.get('hora_ini')} ({ag.get('profissional')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/agenda/os-item/{cod_os_prod}/cancelar")
async def cancelar_agendamento_os(cod_os_prod: int, req: AgendarItemRequest, request: Request):
    result = await agenda_service.cancelar_agendamento(req, cod_os_prod, origem="os", tela="OS_COMP")
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="OS_COMP", comando="AGENDAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(cod_os_prod), descricao=f"Agendamento do item {cod_os_prod} cancelado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ---------- avulso (sem vir de um Pedido, criado direto na grade) ----------

@router.get("/agenda/avulso/{codagenda}")
async def get_agendamento_avulso(codagenda: int, servidor: str, banco: str):
    return await agenda_service.get_agendamento(servidor, banco, codagenda)


@router.post("/agenda/avulso")
async def criar_agendamento_avulso(req: AgendarItemRequest, request: Request):
    result = await agenda_service.salvar_agendamento(req, None)
    if result.get("success"):
        ag = result.get("agendamento") or {}
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="AGENDA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(ag.get("codagenda")),
            descricao=f"Agendamento avulso criado para {ag.get('data')} às {ag.get('hora_ini')} ({ag.get('profissional')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/agenda/{codagenda}/trocar-profissional")
async def trocar_profissional(codagenda: int, req: TrocarProfissionalRequest, request: Request):
    result = await agenda_service.trocar_profissional(req, codagenda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="AGENDA", comando="TROCAR_PROF",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codagenda),
            descricao=f"Profissional trocado no agendamento {codagenda} — autorizado por {req.autorizado_por}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/agenda/{codagenda}/faturar-avulso")
async def faturar_avulso(codagenda: int, req: FaturarAgendaAvulsoRequest, request: Request):
    result = await agenda_service.faturar_avulso(req, codagenda)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="AGENDA", comando="FATURAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codagenda),
            descricao=f"Agendamento {codagenda} faturado (comanda {result.get('comanda')})",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
