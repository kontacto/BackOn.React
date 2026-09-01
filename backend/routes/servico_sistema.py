"""Rotas de "Serviço do Sistema" > aba "Atualização" — ver
services/servico_sistema_service.py pro desenho completo (config +
tarefa de fundo + disparo do updater/apply_update.ps1)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, servico_sistema_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class AtualizacaoDados(BaseModel):
    manifest_url: str = ""
    pasta_backend: str = ""
    pasta_frontend: str = ""
    intervalo_minutos: int = 30
    # ACHADO 2026-08-28 (Apoio Fiscal BackOn, ao mexer neste arquivo por
    # outro motivo): `canal` nunca tinha sido declarado aqui — como
    # Pydantic descarta campo não declarado no `model_dump()`, o Canal
    # escolhido na tela NUNCA chegava no service, que sempre gravava o
    # default "H". Bug real, corrigido de passagem (ver PENDENCIAS.md).
    canal: str = "H"
    cel_suporte: str = ""
    # Manutenção automática de índices (2026-08-28) — ver
    # services/manutencao_indices_service.py. Mesmo cuidado do achado
    # acima: todo campo novo tem que ser declarado aqui, senão o
    # Pydantic descarta e o service nunca recebe o valor da tela.
    manutencao_indices_ativo: bool = True
    manutencao_indices_dias_semana: str = "0,1,2,3,4,5,6"
    manutencao_indices_hora: str = "03:00"
    # Extensão 2026-08-31 (Áureo, análise DBA de RJPNEUS-TESTE) — mesmo
    # cuidado dos campos acima: declarar aqui, senão o Pydantic descarta.
    manutencao_indices_orcamento_minutos: int = 120
    checkdb_ativo: bool = True
    checkdb_dias_semana: str = "0"
    checkdb_hora: str = "04:00"


class AtualizacaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    dados: AtualizacaoDados


class AtualizacaoAcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/servico-sistema/atualizacao")
async def get_atualizacao(servidor: str, banco: str):
    return await servico_sistema_service.get_config(servidor, banco)


@router.get("/servico-sistema/atualizacao/status")
async def get_atualizacao_status(servidor: str, banco: str):
    return await servico_sistema_service.get_status(servidor, banco)


@router.post("/servico-sistema/atualizacao")
async def save_atualizacao(req: AtualizacaoSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await servico_sistema_service.save_config(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Configuração de Atualização gravada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/servico-sistema/atualizacao/verificar-agora")
async def verificar_agora_atualizacao(req: AtualizacaoAcaoRequest, request: Request):
    result = await servico_sistema_service.verificar_agora(req.servidor, req.banco)
    if result.get("success") and result.get("pendente"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="VERIFICAR_ATUALIZACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Verificação manual encontrou atualização nova.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/servico-sistema/atualizacao/aplicar")
async def aplicar_atualizacao(req: AtualizacaoAcaoRequest, request: Request):
    result = await servico_sistema_service.aplicar_atualizacao(req.servidor, req.banco)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="APLICAR_ATUALIZACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Atualização pendente aplicada — sistema reiniciando.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/servico-sistema/atualizacao/reverter")
async def reverter_atualizacao(req: AtualizacaoAcaoRequest, request: Request):
    result = await servico_sistema_service.reverter_atualizacao(req.servidor, req.banco)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="REVERTER_ATUALIZACAO",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Reversão para versão anterior disparada — sistema reiniciando.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
