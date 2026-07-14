"""Rotas de Posto de Combustível > Custo de Combustível — ver
services/custo_combustivel_service.py (só leitura + atualização, sem
Incluir/Excluir — fiel ao legado, que não tem esses botões)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import custo_combustivel_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class CustoUpdateRequest(AuditFields):
    servidor: str
    banco: str
    data: str
    entrada: float
    saida: float
    custo: float


@router.get("/posto/custo-combustivel")
async def list_custos(servidor: str, banco: str, combustivel: int):
    return await custo_combustivel_service.list_custos(servidor, banco, combustivel)


@router.post("/posto/custo-combustivel/{cod_cus}")
async def update_custo(cod_cus: int, req: CustoUpdateRequest, request: Request):
    result = await custo_combustivel_service.update_custo(
        req.servidor, req.banco, cod_cus, req.data, req.entrada, req.saida, req.custo,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_CUSTO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod_cus),
            descricao=f"Custo #{cod_cus} atualizado (entrada {req.entrada}, saída {req.saida}, custo {req.custo}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
