"""Rotas de Previsões (Financeiro > Fluxo de Caixa) — migração de
`Tesouraria\\FrmManPrev.frm` — ver services/previsoes_service.py pro
escopo completo, inclusive o achado corrigido sobre `cod_transf_caixa`."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import PrevisaoDeleteRequest, PrevisaoEfetivarRequest, PrevisaoSaveRequest
from services import previsoes_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/previsoes")
async def listar(
    servidor: str, banco: str, conta: Optional[int] = None, tipo: Optional[int] = None,
    filtro_data: str = "todas", busca: Optional[str] = None, mes_ref: Optional[str] = None,
):
    opcoes = {"conta": conta, "tipo": tipo, "filtro_data": filtro_data, "busca": busca, "mes_ref": mes_ref}
    return await previsoes_service.listar(servidor, banco, opcoes)


@router.get("/previsoes/{codigo}")
async def obter(codigo: int, servidor: str, banco: str):
    return await previsoes_service.obter(servidor, banco, codigo)


@router.post("/previsoes")
async def salvar(req: PrevisaoSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma", "classe_previsao", "sub_classe_previsao"})
    # `classe_previsao`/`sub_classe_previsao` -> `classe`/`sub_classe` no
    # dict interno do service (nomes reais das colunas de `previsoes`) —
    # ver docstring de PrevisaoSaveRequest pro motivo do nome diferente.
    dados["classe"] = req.classe_previsao
    dados["sub_classe"] = req.sub_classe_previsao
    era_novo = req.codigo is None
    result = await previsoes_service.salvar(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PREVISOES", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo"),
            descricao=f"{'Cadastro' if era_novo else 'Alteração'} de previsão — {req.memorando or req.favorecido_nome or ''}".strip(" —"),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/previsoes/{codigo}")
async def excluir(codigo: int, req: PrevisaoDeleteRequest, request: Request):
    result = await previsoes_service.excluir(req.servidor, req.banco, codigo, req.autorizado)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PREVISOES", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao="Exclusão de previsão.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/previsoes/efetivar")
async def efetivar(req: PrevisaoEfetivarRequest, request: Request):
    result = await previsoes_service.efetivar(req.servidor, req.banco, req.codigos, req.data_liquidacao, req.conta)
    if result.get("efetivados"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PREVISOES", comando="EFETIVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in result["efetivados"]),
            descricao=f"{len(result['efetivados'])} previsão(ões) efetivada(s) no Fluxo de Caixa"
                      + (f"; {len(result.get('falhas', []))} falha(s)" if result.get("falhas") else ""),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
