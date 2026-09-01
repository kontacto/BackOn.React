"""Rotas de "Serviço do Sistema" > "Backup Programado" — ver
services/backup_sistema_service.py pro desenho completo (config +
tarefa de fundo + registro/consulta de logs)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import backup_sistema_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class BackupConfigDados(BaseModel):
    ativo: bool = False
    dias_semana: str = "0,1,2,3,4,5,6"
    hora_inicio: str = "02:00"
    intervalo_horas: int = 24
    destino: str = "LOCAL"
    pasta_local: str = ""
    blob_container: str = "backups-sql"
    retencao_dias: int = 30


class BackupSaveRequest(AuditFields):
    servidor: str
    banco: str
    dados: BackupConfigDados


class BackupAcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/backup-sistema/config")
async def get_config(servidor: str, banco: str):
    return await backup_sistema_service.get_config(servidor, banco)


@router.get("/backup-sistema/logs")
async def listar_logs(servidor: str, banco: str, limite: int = 50):
    return await backup_sistema_service.listar_logs(servidor, banco, limite)


@router.post("/backup-sistema/config")
async def save_config(req: BackupSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await backup_sistema_service.save_config(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="GRAVAR_BACKUP",
            usuario=req.usuario_alteracao, classe=req.classe,
            descricao="Configuração de Backup Programado gravada.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/backup-sistema/executar-agora")
async def executar_agora(req: BackupAcaoRequest, request: Request):
    result = await backup_sistema_service.executar_agora(req.servidor, req.banco)
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="SERVICO_SISTEMA", comando="EXECUTAR_BACKUP_AGORA",
        usuario=req.usuario_alteracao, classe=req.classe,
        descricao=f"Backup manual disparado — {result.get('message', '')}",
        ip_origem=_ip(request), plataforma=req.plataforma,
    )
    return result
