"""Rotas de Posto de Combustível > Aferições/Despesas — ver
services/afericao_abastecimento_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import afericao_abastecimento_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class AferirRequest(AuditFields):
    servidor: str
    banco: str
    nums: list[int]
    lancar_despesa: bool = False
    motivo: str = ""


class ReverterRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/abastecimentos/pendentes")
async def list_pendentes(servidor: str, banco: str):
    return await afericao_abastecimento_service.list_pendentes(servidor, banco)


@router.get("/posto/abastecimentos/afericoes")
async def list_afericoes(
    servidor: str, banco: str, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    incluir_afericoes: bool = True, incluir_despesas: bool = True,
):
    return await afericao_abastecimento_service.list_afericoes(servidor, banco, data_ini, data_fim, incluir_afericoes, incluir_despesas)


@router.post("/posto/abastecimentos/aferir")
async def aferir(req: AferirRequest, request: Request):
    result = await afericao_abastecimento_service.aferir(
        req.servidor, req.banco, req.nums, req.lancar_despesa, req.motivo, req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_AFERICAO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=",".join(str(n) for n in req.nums),
            descricao=result.get("message") or "Abastecimentos aferidos.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/abastecimentos/{num}/reverter")
async def reverter(num: int, req: ReverterRequest, request: Request):
    result = await afericao_abastecimento_service.reverter(req.servidor, req.banco, num)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_AFERICAO", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(num),
            descricao=f"Aferição do abastecimento {num} revertida.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
