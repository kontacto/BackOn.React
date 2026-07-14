"""Rotas de Cadastros > Contatos.

Toda ação de Gravar/Excluir é registrada em `log_auditoria` — mesmo padrão
de `routes/financeiro.py`/`routes/entrada_saida_caixa.py`.
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import contatos_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="CONTATOS", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class SaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    data: str
    cliente: str
    telefone: Optional[str] = None
    telefone_2: Optional[str] = None
    tipo_cliente: Optional[int] = None
    contato: Optional[str] = None
    profissional: Optional[int] = None
    data_prev: Optional[str] = None
    hora_prev: Optional[str] = None
    obs: Optional[str] = None
    e_mail: Optional[str] = None
    endereco: Optional[str] = None
    bairro: Optional[str] = None
    indicacao: Optional[str] = None


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/contatos")
async def list_contatos(
    servidor: str, banco: str,
    data_de: Optional[str] = None, data_ate: Optional[str] = None,
    prev_de: Optional[str] = None, prev_ate: Optional[str] = None,
    cliente: Optional[str] = None, contato: Optional[str] = None, telefone: Optional[str] = None,
    tipo_cliente: Optional[int] = None, profissional: Optional[int] = None,
):
    return await contatos_service.list_contatos(
        servidor, banco, data_de, data_ate, prev_de, prev_ate,
        cliente, contato, telefone, tipo_cliente, profissional,
    )


@router.post("/contatos")
async def save_contato(req: SaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "contatos", "codigo", req.codigo)
    result = await contatos_service.save_contato(
        req.servidor, req.banco, req.codigo, req.data, req.cliente, req.telefone, req.telefone_2,
        req.tipo_cliente, req.contato, req.profissional, req.data_prev, req.hora_prev, req.obs,
        req.e_mail, req.endereco, req.bairro, req.indicacao,
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes,
            {
                "data": req.data, "cliente": req.cliente, "telefone": req.telefone,
                "tipo_cliente": req.tipo_cliente, "contato": req.contato, "profissional": req.profissional,
                "data_prev": req.data_prev, "hora_prev": req.hora_prev,
            },
            ["data", "cliente", "telefone", "tipo_cliente", "contato", "profissional", "data_prev", "hora_prev"],
        )
        await _log(
            req, request, comando="GRAVAR", referencia=codigo,
            descricao=f"Contato '{req.cliente}' (#{codigo}) gravado", campos=campos,
        )
    return result


@router.post("/contatos/{codigo}/excluir")
async def delete_contato(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "contatos", "codigo", codigo)
    result = await contatos_service.delete_contato(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["cliente", "data", "contato"])
        await _log(
            req, request, comando="EXCLUIR", referencia=codigo,
            descricao=f"Contato #{codigo} excluído", campos=campos,
        )
    return result
