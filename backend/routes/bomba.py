"""Rotas de Posto de Combustível > Bombas — ver services/bomba_service.py
(nota sobre o botão "Excluir" morto no legado, guards de exclusão
adicionados aqui como melhoria)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import bomba_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class BombaDados(BaseModel):
    ilha: int
    ponto: int
    posicao: int
    tanque: int
    combustivel: int
    contador_final: Optional[float] = 0
    data_ult_mov: Optional[str] = None
    inserir_valor: Optional[str] = None
    captor: Optional[str] = None
    captor2: Optional[str] = None
    serie: Optional[str] = None
    preco2: Optional[bool] = False
    fabricante: Optional[str] = None
    modelo: Optional[str] = None
    tipo_medicao: Optional[int] = None
    numero_lacre: Optional[str] = None
    dt_lacre: Optional[str] = None


class BombaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    dados: BombaDados


class BombaDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/posto/bombas")
async def list_bombas(servidor: str, banco: str):
    return await bomba_service.list_bombas(servidor, banco)


@router.get("/posto/bombas/{codigo}")
async def get_bomba(codigo: int, servidor: str, banco: str):
    return await bomba_service.get_bomba(servidor, banco, codigo)


@router.post("/posto/bombas")
async def save_bomba(req: BombaSaveRequest, request: Request):
    result = await bomba_service.save_bomba(req.servidor, req.banco, req.codigo, req.dados.dict())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_BOMBA", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(req.codigo),
            descricao=f"Bomba {req.codigo} gravada (ponto {req.dados.ponto}, posição {req.dados.posicao}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/posto/bombas/{codigo}/excluir")
async def delete_bomba(codigo: int, req: BombaDeleteRequest, request: Request):
    result = await bomba_service.delete_bomba(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="POSTO_BOMBA", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Bomba {codigo} excluída.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
