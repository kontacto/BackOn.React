"""Rotas do Painel de Movimentações (Financeiro > Fluxo de Caixa) —
migração de `Kontacto\\FrmPnlCon.frm` — ver
services/painel_financeiro_service.py pro escopo completo."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import PainelLancamentoDeleteRequest, PainelLancamentoSaveRequest
from services import painel_financeiro_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/painel-financeiro/resumo")
async def resumo(
    servidor: str, banco: str, conta: Optional[int] = None, periodo: str = "mes", mes_ref: Optional[str] = None,
    partir_de_hoje: bool = False, desconsiderar_pendencias: bool = False,
):
    return await painel_financeiro_service.resumo(servidor, banco, conta, periodo, mes_ref, partir_de_hoje, desconsiderar_pendencias)


@router.get("/painel-financeiro/movimentacoes")
async def listar_movimentacoes(servidor: str, banco: str, conta: Optional[int] = None, periodo: str = "mes", mes_ref: Optional[str] = None):
    return await painel_financeiro_service.listar_movimentacoes(servidor, banco, conta, periodo, mes_ref)


@router.get("/painel-financeiro/serie-saldo")
async def serie_saldo(servidor: str, banco: str, conta: Optional[int] = None, periodo: str = "mes", mes_ref: Optional[str] = None):
    return await painel_financeiro_service.serie_saldo(servidor, banco, conta, periodo, mes_ref)


@router.get("/painel-financeiro/receitas-despesas-mes")
async def receitas_despesas_mes(servidor: str, banco: str, conta: Optional[int] = None, periodo: str = "tudo", mes_ref: Optional[str] = None):
    return await painel_financeiro_service.receitas_despesas_mes(servidor, banco, conta, periodo, mes_ref)


@router.get("/painel-financeiro/duplicatas-recebidas")
async def relatorio_duplicatas_recebidas(
    servidor: str, banco: str, data_ini: str, data_fim: str, base: str = "vencimento",
    cliente: Optional[int] = None, forma_pag: Optional[str] = None, banco_cedente: Optional[int] = None,
    vendedor: Optional[int] = None, comandas: bool = True, notas_fiscais: bool = True,
):
    return await painel_financeiro_service.relatorio_duplicatas_recebidas(
        servidor, banco, data_ini=data_ini, data_fim=data_fim, base=base, cliente=cliente,
        forma_pag=forma_pag, banco_cedente=banco_cedente, vendedor=vendedor,
        comandas=comandas, notas_fiscais=notas_fiscais,
    )


@router.get("/painel-financeiro/duplicatas-pagas")
async def relatorio_duplicatas_pagas(
    servidor: str, banco: str, data_ini: str, data_fim: str, base: str = "vencimento",
    fornecedor: Optional[int] = None,
):
    return await painel_financeiro_service.relatorio_duplicatas_pagas(
        servidor, banco, data_ini=data_ini, data_fim=data_fim, base=base, fornecedor=fornecedor,
    )


@router.post("/painel-financeiro/lancamentos")
async def lancar(req: PainelLancamentoSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma", "classe_lancamento", "sub_classe_lancamento"})
    # `classe_lancamento`/`sub_classe_lancamento` -> `classe`/`sub_classe`
    # no dict interno do service (nomes reais das colunas de
    # `movimentacoes`) — ver docstring de PainelLancamentoSaveRequest.
    dados["classe"] = req.classe_lancamento
    dados["sub_classe"] = req.sub_classe_lancamento
    result = await painel_financeiro_service.lancar(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PAINEL_MOV", comando="LANCAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("codigo"),
            descricao=f"Lançamento direto — {req.memorando or req.favorecido_nome or ''}".strip(" —"),
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/painel-financeiro/lancamentos/{codigo}")
async def excluir_lancamento(codigo: int, req: PainelLancamentoDeleteRequest, request: Request):
    result = await painel_financeiro_service.excluir_lancamento(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="PAINEL_MOV", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao="Exclusão de lançamento direto.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
