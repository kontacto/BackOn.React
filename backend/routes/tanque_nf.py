"""Rotas de Posto de Combustível > Tanque/Nota Fiscal — ver
services/tanque_nf_service.py."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, tanque_nf_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class TanqueNfSaveRequest(AuditFields):
    servidor: str
    banco: str
    nota: int
    tanque: int
    qtd: int


class TanqueNfDeleteRequest(AuditFields):
    servidor: str
    banco: str
    nota: int
    tanque: int


@router.get("/posto/tanque-nf/find")
async def find_nota(
    servidor: str, banco: str,
    codigo: Optional[int] = None, fornecedor: Optional[int] = None,
    serie_nf: Optional[str] = None, num_nf: Optional[float] = None,
):
    return await tanque_nf_service.find_nota(servidor, banco, codigo, fornecedor, serie_nf, num_nf)


@router.get("/posto/tanque-nf")
async def list_tanque_nf(servidor: str, banco: str, nota: int):
    return await tanque_nf_service.list_tanque_nf(servidor, banco, nota)


@router.post("/posto/tanque-nf")
async def save_tanque_nf(req: TanqueNfSaveRequest, request: Request):
    result = await tanque_nf_service.save_tanque_nf(req.servidor, req.banco, req.nota, req.tanque, req.qtd)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TQ_NF", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=f"{req.nota}-{req.tanque}",
            descricao=f"Nota Fiscal {req.nota} vinculada ao tanque {req.tanque} (qtd {req.qtd}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/tanque-nf/excluir")
async def delete_tanque_nf(req: TanqueNfDeleteRequest, request: Request):
    result = await tanque_nf_service.delete_tanque_nf(req.servidor, req.banco, req.nota, req.tanque)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_TQ_NF", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=f"{req.nota}-{req.tanque}",
            descricao=f"Vínculo da Nota Fiscal {req.nota} com o tanque {req.tanque} excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
