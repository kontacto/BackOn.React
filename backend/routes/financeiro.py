"""Rotas do módulo Financeiro (Fluxo de Caixa > Plano de Contas).

Toda ação de Gravar/Excluir é registrada em `log_auditoria` — ver o mesmo
padrão de `routes/tabelas_aux.py` (busca o registro atual pelo PK antes de
chamar o service, compara com os valores novos, grava o diff campo-a-campo).
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import financeiro_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, tela: str, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela=tela, comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class ClasseSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    descricao: str
    tipo: str = "D"


class SubClasseSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    classe: int
    descricao: str
    tipo: str = "D"
    ativa: bool = True


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class CentroCustoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    descricao: str
    classe_entrada: Optional[int] = None
    sub_classe_entrada: Optional[int] = None
    classe_saida: Optional[int] = None
    sub_classe_saida: Optional[int] = None


@router.get("/financeiro/plano-contas")
async def list_plano_contas(servidor: str, banco: str, search: str = ""):
    return await financeiro_service.list_plano_contas(servidor, banco, search)


@router.post("/financeiro/plano-contas/classe")
async def save_classe(req: ClasseSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "classes", "codigo", req.codigo)
    result = await financeiro_service.save_classe(req.servidor, req.banco, req.codigo, req.descricao, req.tipo)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, {"descricao": req.descricao, "tipo": req.tipo}, ["descricao", "tipo"])
        await _log(req, request, tela="PLANO_CONTAS", comando="GRAVAR", referencia=codigo, descricao=f"Classe '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/financeiro/plano-contas/classe/{codigo}/excluir")
async def delete_classe(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "classes", "codigo", codigo)
    result = await financeiro_service.delete_classe(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "tipo"])
        await _log(req, request, tela="PLANO_CONTAS", comando="EXCLUIR", referencia=codigo, descricao=f"Classe #{codigo} excluída", campos=campos)
    return result


@router.post("/financeiro/plano-contas/subclasse")
async def save_subclasse(req: SubClasseSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "sub_classes", "codigo", req.codigo)
    result = await financeiro_service.save_subclasse(
        req.servidor, req.banco, req.codigo, req.classe, req.descricao, req.tipo, req.ativa
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes, {"classe": req.classe, "descricao": req.descricao, "tipo": req.tipo, "ativa": req.ativa},
            ["classe", "descricao", "tipo", "ativa"],
        )
        await _log(req, request, tela="PLANO_CONTAS", comando="GRAVAR", referencia=codigo, descricao=f"Subclasse '{req.descricao}' gravada", campos=campos)
    return result


@router.post("/financeiro/plano-contas/subclasse/{codigo}/excluir")
async def delete_subclasse(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "sub_classes", "codigo", codigo)
    result = await financeiro_service.delete_subclasse(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao", "classe"])
        await _log(req, request, tela="PLANO_CONTAS", comando="EXCLUIR", referencia=codigo, descricao=f"Subclasse #{codigo} excluída", campos=campos)
    return result


@router.get("/financeiro/centro-custo")
async def list_centro_custo(servidor: str, banco: str, search: str = ""):
    return await financeiro_service.list_centro_custo(servidor, banco, search)


@router.post("/financeiro/centro-custo")
async def save_centro_custo(req: CentroCustoSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "centro_custo", "codigo", req.codigo)
    result = await financeiro_service.save_centro_custo(
        req.servidor, req.banco, req.codigo, req.descricao,
        req.classe_entrada, req.sub_classe_entrada, req.classe_saida, req.sub_classe_saida,
    )
    if result.get("success"):
        campos_map = ["descricao", "classe_entrada", "sub_classe_entrada", "classe_saida", "sub_classe_saida"]
        campos = log_auditoria_service.diff_campos(antes, req.model_dump(), campos_map)
        await _log(req, request, tela="CENTRO_CUSTO", comando="GRAVAR", referencia=req.codigo, descricao=f"Centro de Custo '{req.descricao}' gravado", campos=campos)
    return result


@router.post("/financeiro/centro-custo/{codigo}/excluir")
async def delete_centro_custo(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "centro_custo", "codigo", codigo)
    result = await financeiro_service.delete_centro_custo(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["descricao"])
        await _log(req, request, tela="CENTRO_CUSTO", comando="EXCLUIR", referencia=codigo, descricao=f"Centro de Custo #{codigo} excluído", campos=campos)
    return result
