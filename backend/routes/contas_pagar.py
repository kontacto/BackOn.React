"""Rotas de Financeiro > Contas a Pagar (ver
services/contas_pagar_service.py pro escopo/rastreio completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    ContasPagarAlterarNumeroRequest, ContasPagarAvulsaRequest, ContasPagarBaixaRequest,
    ContasPagarCancelarBaixaRequest, ContasPagarDesvincularNfRequest, ContasPagarEditarParcelaRequest,
    ContasPagarExcluirRequest, ContasPagarLoteRequest, ContasPagarVincularNfRequest,
)
from services import contas_pagar_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contas-pagar")
async def listar(
    servidor: str, banco: str, situacao: Optional[str] = None, fornecedor: Optional[int] = None,
    busca: Optional[str] = None, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    duplicata_num: Optional[int] = None, desmembramento: Optional[str] = None, valor: Optional[float] = None,
    numero_boleto: Optional[float] = None, num_doc_pag: Optional[str] = None,
    emissao_ini: Optional[str] = None, emissao_fim: Optional[str] = None,
):
    filtros = {
        "situacao": situacao, "fornecedor": fornecedor, "busca": busca, "data_ini": data_ini, "data_fim": data_fim,
        "duplicata_num": duplicata_num, "desmembramento": desmembramento, "valor": valor,
        "numero_boleto": numero_boleto, "num_doc_pag": num_doc_pag,
        "emissao_ini": emissao_ini, "emissao_fim": emissao_fim,
    }
    return await contas_pagar_service.listar(servidor, banco, filtros)


@router.get("/contas-pagar/{codigo}")
async def detalhe(codigo: int, servidor: str, banco: str):
    return await contas_pagar_service.detalhe(servidor, banco, codigo)


@router.get("/contas-pagar-tipos-mov")
async def tipos_mov(servidor: str, banco: str):
    return await contas_pagar_service.list_tipos_mov(servidor, banco)


@router.post("/contas-pagar/avulsa")
async def criar_avulsa(req: ContasPagarAvulsaRequest, request: Request):
    result = await contas_pagar_service.criar_avulsa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Lançamento avulso de duplicata a pagar — fornecedor {req.fornecedor}, valor R$ {req.valor:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/baixar")
async def baixar_parcela(req: ContasPagarBaixaRequest, request: Request):
    result = await contas_pagar_service.baixar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="BAIXAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao=f"Baixa manual de parcela — valor pago R$ {req.valor_pag:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/cancelar-baixa")
async def cancelar_baixa(req: ContasPagarCancelarBaixaRequest, request: Request):
    result = await contas_pagar_service.cancelar_baixa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="CANCELAR_BAIXA",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Cancelamento de baixa de parcela",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contas-pagar/lote/vencimentos")
async def listar_vencimentos_lote(
    servidor: str, banco: str, modo: str = "baixar", fornecedor: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    filtros = {"modo": modo, "fornecedor": fornecedor, "data_ini": data_ini, "data_fim": data_fim}
    return await contas_pagar_service.listar_vencimentos_lote(servidor, banco, filtros)


@router.post("/contas-pagar/lote")
async def processar_lote(req: ContasPagarLoteRequest, request: Request):
    result = await contas_pagar_service.processar_lote(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        comando = "CANCELAR_LOTE" if req.modo == "cancelar" else "BAIXAR_LOTE"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando=comando,
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(len(req.vencimentos)),
            descricao=f"{'Cancelamento' if req.modo == 'cancelar' else 'Baixa'} em lote — "
                      f"{result.get('processados', 0)} processado(s), {len(result.get('falhas', []))} falha(s)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/editar-parcela")
async def editar_parcela(req: ContasPagarEditarParcelaRequest, request: Request):
    result = await contas_pagar_service.editar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Edição de parcela em aberto",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/excluir")
async def excluir(req: ContasPagarExcluirRequest, request: Request):
    result = await contas_pagar_service.excluir(req.servidor, req.banco, req.codigo_duplicata)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao="Exclusão de duplicata a pagar",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contas-pagar/{codigo}/notas-disponiveis")
async def notas_disponiveis(codigo: int, servidor: str, banco: str):
    return await contas_pagar_service.notas_disponiveis(servidor, banco, codigo)


@router.post("/contas-pagar/vincular-nf")
async def vincular_nf(req: ContasPagarVincularNfRequest, request: Request):
    result = await contas_pagar_service.vincular_nf(req.servidor, req.banco, req.codigo_duplicata, req.nf_fiscal)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Nota Fiscal {req.nf_fiscal} vinculada à duplicata",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/desvincular-nf")
async def desvincular_nf(req: ContasPagarDesvincularNfRequest, request: Request):
    result = await contas_pagar_service.desvincular_nf(req.servidor, req.banco, req.codigo_duplicata, req.nf_fiscal)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Nota Fiscal {req.nf_fiscal} desvinculada da duplicata",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-pagar/alterar-numero")
async def alterar_numero(req: ContasPagarAlterarNumeroRequest, request: Request):
    result = await contas_pagar_service.alterar_numero(req.servidor, req.banco, req.codigo_duplicata, req.novo_numero)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_PAGAR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Número da duplicata alterado para {req.novo_numero}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
