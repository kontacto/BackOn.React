"""Rotas de ação da Manutenção Automática de Índices — a config (ativo/
dias/hora, orçamento de tempo, CHECKDB) mora e é gravada junto com
"Serviço do Sistema > Atualização" (`routes/servico_sistema.py`, mesma
tabela `servico_sistema_atualizacao`); este arquivo cobre só as AÇÕES
sob demanda que não fazem parte desse round-trip de config: rodar a
manutenção na hora, listar índices nunca usados (relatório, nunca ação
automática), e checar espaço vs. teto do SQL Server Express. Ver
services/manutencao_indices_service.py pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, manutencao_indices_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ManutencaoIndicesAcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.post("/manutencao-indices/rodar-agora")
async def rodar_agora(req: ManutencaoIndicesAcaoRequest, request: Request):
    result = await manutencao_indices_service.rodar_manutencao_agora(req.servidor, req.banco)
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="MANUTENCAO_INDICES_MANUAL",
        usuario=req.usuario_alteracao, classe=req.classe,
        descricao=f"Manutenção de índices disparada manualmente — {result.get('resumo', '')}",
        ip_origem=_ip(request), plataforma=req.plataforma,
    )
    return result


@router.get("/manutencao-indices/nao-usados")
async def nao_usados(servidor: str, banco: str):
    return await manutencao_indices_service.listar_indices_nao_usados(servidor, banco)


@router.get("/manutencao-indices/espaco")
async def espaco(servidor: str, banco: str):
    return await manutencao_indices_service.verificar_espaco(servidor, banco)
