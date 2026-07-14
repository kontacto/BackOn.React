"""Rotas de Cadastros > Entrada/Saída de Caixa (caixa operacional da loja,
não o caixa financeiro — ver módulo `entrada_saida_caixa_service`).

Toda ação de Gravar/Excluir é registrada em `log_auditoria` — mesmo padrão
de `routes/financeiro.py` (busca o registro atual pelo PK antes de chamar o
service, compara com os valores novos, grava o diff campo-a-campo).
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import entrada_saida_caixa_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


def _tabela(tipo: str) -> str:
    return "entrada_caixa" if (tipo or "").strip().upper() == "E" else "saida_caixa"


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="MOV_CAIXA", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class SaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    tipo: str  # "E" ou "S" — imutável após criado (rota não permite trocar tabela de um codigo existente)
    valor: float
    descricao: str
    forma_pag: Optional[str] = None
    conta: Optional[int] = None
    conta_destino: Optional[int] = None
    favorecido_descricao: Optional[str] = None
    classe: Optional[int] = None
    sub_classe: Optional[int] = None
    centro_custo: Optional[int] = None


class DeleteRequest(AuditFields):
    servidor: str
    banco: str
    tipo: str


@router.get("/entrada-saida-caixa/config")
async def get_config(servidor: str, banco: str):
    return await entrada_saida_caixa_service.get_config(servidor, banco)


@router.get("/entrada-saida-caixa")
async def list_lancamentos(
    servidor: str, banco: str,
    data_de: Optional[str] = None, data_ate: Optional[str] = None,
    entradas: bool = True, saidas: bool = True,
):
    return await entrada_saida_caixa_service.list_lancamentos(servidor, banco, data_de, data_ate, entradas, saidas)


@router.post("/entrada-saida-caixa")
async def save_lancamento(req: SaveRequest, request: Request):
    tabela = _tabela(req.tipo)
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, tabela, "codigo", req.codigo)
    result = await entrada_saida_caixa_service.save_lancamento(
        req.servidor, req.banco, req.codigo, req.tipo, req.valor, req.descricao, req.forma_pag,
        req.conta, req.conta_destino, req.favorecido_descricao, req.classe, req.sub_classe,
        req.centro_custo, req.usuario_alteracao,
    )
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(
            antes,
            {
                "valor": req.valor, "descricao": req.descricao, "forma_pag": req.forma_pag,
                "conta": req.conta, "classe": req.classe, "sub_classe": req.sub_classe,
                "centro_custo": req.centro_custo,
            },
            ["valor", "descricao", "forma_pag", "conta", "classe", "sub_classe", "centro_custo"],
        )
        tipo_label = "Entrada" if req.tipo.upper() == "E" else "Saída"
        await _log(
            req, request, comando="GRAVAR", referencia=codigo,
            descricao=f"{tipo_label} de Caixa #{codigo} gravada", campos=campos,
        )
    return result


@router.post("/entrada-saida-caixa/{codigo}/excluir")
async def delete_lancamento(codigo: int, req: DeleteRequest, request: Request):
    tabela = _tabela(req.tipo)
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, tabela, "codigo", codigo)
    result = await entrada_saida_caixa_service.delete_lancamento(req.servidor, req.banco, req.tipo, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["valor", "descricao"])
        tipo_label = "Entrada" if req.tipo.upper() == "E" else "Saída"
        await _log(
            req, request, comando="EXCLUIR", referencia=codigo,
            descricao=f"{tipo_label} de Caixa #{codigo} excluída", campos=campos,
        )
    return result
