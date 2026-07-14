"""Rotas de Cadastros > Equipamentos.

Toda ação de Gravar/Excluir/Disponibilizar/Alterar Núm. Série é registrada
em `log_auditoria` — mesmo padrão de `routes/contatos.py`.
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import equipamentos_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="EQUIPAMENTOS", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class SaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    cliente: int
    numero_de_serie: str
    numero_de_serie_int: Optional[str] = None
    marca: str
    modelo: str
    portador: Optional[str] = None
    local: Optional[str] = None
    tipo_equipamento: Optional[str] = "A"
    detalhe_equipamento: Optional[str] = None
    situacao_equipamento: Optional[str] = "A"
    descricao_equipamento: Optional[str] = None
    valor: Optional[float] = 0
    revisao: Optional[str] = None


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class DisponibilizarRequest(AuditFields):
    servidor: str
    banco: str


class AlterarNumeroSerieRequest(AuditFields):
    servidor: str
    banco: str
    novo_numero_de_serie: str
    novo_cliente: Optional[int] = None


@router.get("/equipamentos/find/by-serie")
async def find_by_serie(servidor: str, banco: str, numero_de_serie: str):
    return await equipamentos_service.find_by_serie(servidor, banco, numero_de_serie)


@router.get("/equipamentos")
async def list_equipamentos(
    servidor: str, banco: str, cliente: int,
    busca: Optional[str] = None, tipo: Optional[str] = None, situacao: Optional[str] = None,
):
    return await equipamentos_service.list_equipamentos(servidor, banco, cliente, busca, tipo, situacao)


@router.post("/equipamentos")
async def save_equipamento(req: SaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "equipamentos", "codigo", req.codigo)
    result = await equipamentos_service.save_equipamento(
        req.servidor, req.banco, req.codigo, req.cliente, req.numero_de_serie, req.numero_de_serie_int,
        req.marca, req.modelo, req.portador, req.local, req.tipo_equipamento, req.detalhe_equipamento,
        req.situacao_equipamento, req.descricao_equipamento, req.valor, req.revisao,
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes,
            {
                "cliente": req.cliente, "numero_de_serie": req.numero_de_serie, "marca": req.marca,
                "modelo": req.modelo, "tipo_equipamento": req.tipo_equipamento,
                "situacao_equipamento": req.situacao_equipamento, "valor": req.valor,
            },
            ["cliente", "numero_de_serie", "marca", "modelo", "tipo_equipamento", "situacao_equipamento", "valor"],
        )
        await _log(
            req, request, comando="GRAVAR", referencia=codigo,
            descricao=f"Equipamento '{req.numero_de_serie}' (#{codigo}) gravado", campos=campos,
        )
    return result


@router.post("/equipamentos/{codigo}/excluir")
async def delete_equipamento(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "equipamentos", "codigo", codigo)
    result = await equipamentos_service.delete_equipamento(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["numero_de_serie", "cliente"])
        await _log(req, request, comando="EXCLUIR", referencia=codigo, descricao=f"Equipamento #{codigo} excluído", campos=campos)
    return result


@router.post("/equipamentos/{codigo}/disponibilizar-contrato")
async def disponibilizar_contrato(codigo: int, req: DisponibilizarRequest, request: Request):
    result = await equipamentos_service.disponibilizar_contrato(req.servidor, req.banco, codigo)
    if result.get("success"):
        await _log(req, request, comando="DISPONIBILIZAR", referencia=codigo, descricao=f"Equipamento #{codigo} disponibilizado para contrato")
    return result


@router.post("/equipamentos/{codigo}/alterar-numero-serie")
async def alterar_numero_serie(codigo: int, req: AlterarNumeroSerieRequest, request: Request):
    result = await equipamentos_service.alterar_numero_serie(
        req.servidor, req.banco, codigo, req.novo_numero_de_serie, req.novo_cliente,
    )
    if result.get("success"):
        await _log(
            req, request, comando="ALT_NUM_SERIE", referencia=codigo,
            descricao=f"Equipamento #{codigo} teve o número de série alterado para '{req.novo_numero_de_serie}'",
        )
    return result
