"""Rotas de Financeiro > Contas a Receber (ver
services/contas_receber_service.py pro escopo/rastreio completo)."""
from typing import Optional

from fastapi import APIRouter, Request

from models.schemas import (
    ContasReceberAlterarNumeroRequest, ContasReceberAvulsaRequest, ContasReceberBaixaRequest,
    ContasReceberCancelarBaixaRequest, ContasReceberEditarParcelaRequest, ContasReceberEmitirReciboRequest,
    ContasReceberExcluirRequest, ContasReceberLoteRequest, ContasReceberMontanteRequest,
    ContasReceberSituacaoVencimentoLoteRequest, ContasReceberSituacaoVencimentoRequest,
    ContasReceberVincularNfRequest,
)
from services import contas_receber_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/contas-receber")
async def listar(
    servidor: str, banco: str, situacao: Optional[str] = None, cliente: Optional[int] = None,
    busca: Optional[str] = None, data_ini: Optional[str] = None, data_fim: Optional[str] = None,
    duplicata_num: Optional[int] = None, valor: Optional[float] = None, numero_boleto: Optional[int] = None,
    situacao_duplicata: Optional[int] = None, recebido_ini: Optional[str] = None, recebido_fim: Optional[str] = None,
):
    filtros = {
        "situacao": situacao, "cliente": cliente, "busca": busca, "data_ini": data_ini, "data_fim": data_fim,
        "duplicata_num": duplicata_num, "valor": valor, "numero_boleto": numero_boleto,
        "situacao_duplicata": situacao_duplicata, "recebido_ini": recebido_ini, "recebido_fim": recebido_fim,
    }
    return await contas_receber_service.listar(servidor, banco, filtros)


@router.get("/contas-receber/{codigo}")
async def detalhe(codigo: int, servidor: str, banco: str):
    return await contas_receber_service.detalhe(servidor, banco, codigo)


@router.get("/contas-receber-tipos-mov")
async def tipos_mov(servidor: str, banco: str):
    return await contas_receber_service.list_tipos_mov(servidor, banco)


@router.post("/contas-receber/avulsa")
async def criar_avulsa(req: ContasReceberAvulsaRequest, request: Request):
    result = await contas_receber_service.criar_avulsa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo")),
            descricao=f"Lançamento avulso de duplicata a receber — cliente {req.cliente}, valor R$ {req.valor:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/baixar")
async def baixar_parcela(req: ContasReceberBaixaRequest, request: Request):
    result = await contas_receber_service.baixar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="BAIXAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao=f"Baixa manual de parcela — valor pago R$ {req.valor_pag:.2f}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/cancelar-baixa")
async def cancelar_baixa(req: ContasReceberCancelarBaixaRequest, request: Request):
    result = await contas_receber_service.cancelar_baixa(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="CANCELAR_BAIXA",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Cancelamento de baixa de parcela",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contas-receber/lote/vencimentos")
async def listar_vencimentos_lote(
    servidor: str, banco: str, modo: str = "baixar", cliente: Optional[int] = None,
    data_ini: Optional[str] = None, data_fim: Optional[str] = None,
):
    filtros = {"modo": modo, "cliente": cliente, "data_ini": data_ini, "data_fim": data_fim}
    return await contas_receber_service.listar_vencimentos_lote(servidor, banco, filtros)


@router.post("/contas-receber/lote")
async def processar_lote(req: ContasReceberLoteRequest, request: Request):
    result = await contas_receber_service.processar_lote(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        comando = "CANCELAR_LOTE" if req.modo == "cancelar" else "BAIXAR_LOTE"
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando=comando,
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(len(req.vencimentos)),
            descricao=f"{'Cancelamento' if req.modo == 'cancelar' else 'Baixa'} em lote — "
                      f"{result.get('processados', 0)} processado(s), {len(result.get('falhas', []))} falha(s)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/montante")
async def baixar_montante(req: ContasReceberMontanteRequest, request: Request):
    result = await contas_receber_service.baixar_montante(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="BAIXAR_MONTANTE",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.cliente),
            descricao=f"Baixa por Montante — R$ {req.montante:.2f}, "
                      f"{len(result.get('tocados', []))} parcela(s) tocada(s)",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/editar-parcela")
async def editar_parcela(req: ContasReceberEditarParcelaRequest, request: Request):
    result = await contas_receber_service.editar_parcela(req.servidor, req.banco, req.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao="Edição de parcela em aberto",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/vencimento/situacao")
async def alterar_situacao_vencimento(req: ContasReceberSituacaoVencimentoRequest, request: Request):
    result = await contas_receber_service.alterar_situacao_vencimento(req.servidor, req.banco, req.codigo_venc, req.situacao_duplicata)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_venc),
            descricao=f"Situação do vencimento alterada para {['Normal','Jurídico','Protestado'][req.situacao_duplicata] if 0 <= req.situacao_duplicata <= 2 else req.situacao_duplicata}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/vencimento/situacao-lote")
async def alterar_situacao_vencimento_lote(req: ContasReceberSituacaoVencimentoLoteRequest, request: Request):
    result = await contas_receber_service.alterar_situacao_vencimento_lote(req.servidor, req.banco, req.codigos_venc, req.situacao_duplicata)
    if result.get("alterados"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=",".join(str(c) for c in result["alterados"]),
            descricao=f"Situação de {len(result['alterados'])} vencimento(s) alterada em lote para "
                      f"{['Normal','Jurídico','Protestado'][req.situacao_duplicata] if 0 <= req.situacao_duplicata <= 2 else req.situacao_duplicata}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/excluir")
async def excluir(req: ContasReceberExcluirRequest, request: Request):
    result = await contas_receber_service.excluir(req.servidor, req.banco, req.codigo_duplicata)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao="Exclusão de duplicata a receber",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.get("/contas-receber/{codigo}/notas-disponiveis")
async def notas_disponiveis(codigo: int, servidor: str, banco: str):
    return await contas_receber_service.notas_disponiveis(servidor, banco, codigo)


@router.post("/contas-receber/vincular-nf")
async def vincular_nf(req: ContasReceberVincularNfRequest, request: Request):
    result = await contas_receber_service.vincular_nf(req.servidor, req.banco, req.codigo_duplicata, req.nf_fiscal)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Nota Fiscal {req.nf_fiscal} vinculada à duplicata",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/desvincular-nf")
async def desvincular_nf(req: ContasReceberVincularNfRequest, request: Request):
    result = await contas_receber_service.desvincular_nf(req.servidor, req.banco, req.codigo_duplicata, req.nf_fiscal)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Nota Fiscal {req.nf_fiscal} desvinculada da duplicata",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/emitir-recibo")
async def emitir_recibo(req: ContasReceberEmitirReciboRequest, request: Request):
    result = await contas_receber_service.emitir_recibo(
        req.servidor, req.banco, recebemos=req.recebemos, valor=req.valor, referente=req.referente,
        data_recibo=req.data_recibo, assinatura=req.assinatura,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="EMITIR_RECIBO",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=result.get("numero"),
            descricao=f"Recibo {result.get('numero')} emitido — R$ {req.valor:.2f} de {req.recebemos}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/contas-receber/alterar-numero")
async def alterar_numero(req: ContasReceberAlterarNumeroRequest, request: Request):
    result = await contas_receber_service.alterar_numero(req.servidor, req.banco, req.codigo_duplicata, req.novo_numero)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CONTAS_RECEBER", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(req.codigo_duplicata),
            descricao=f"Número da duplicata alterado para {req.novo_numero}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
