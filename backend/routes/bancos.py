"""Rotas de Bancos (Financeiro > Cobranças) — ver services/bancos_service.py.
Remessa/Retorno (Fase 2a — Bradesco/237, Inter/077 completos; Santander/033,
Banco do Brasil/001 e Itaú/341 só retorno, remessa pendente de arquivo real)
— ver services/cnab_*_service.py de cada banco."""
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile

from models.bancos import (
    AplicarBaixasRequest,
    BancoDeleteRequest,
    BancoSaveRequest,
    GerarRemessaRequest,
    PreviewRetornoRequest,
    ProcessarRetornoRequest,
)
from services import (
    bancos_service,
    cnab_bb_service,
    cnab_bradesco_service,
    cnab_inter_service,
    cnab_itau_service,
    cnab_santander_service,
    cobranca_retorno_service,
    log_auditoria_service,
)

router = APIRouter()

_MOTORES_CNAB = {
    cnab_bradesco_service.BANCO_BRADESCO_CODIGO: cnab_bradesco_service,
    cnab_inter_service.BANCO_INTER_CODIGO: cnab_inter_service,
    cnab_santander_service.BANCO_SANTANDER_CODIGO: cnab_santander_service,
    cnab_bb_service.BANCO_BB_CODIGO: cnab_bb_service,
    cnab_itau_service.BANCO_ITAU_CODIGO: cnab_itau_service,
}


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _motor_cnab(servidor: str, banco: str, cod: int):
    """Dispatch por código Febraban do banco — cada motor de banco (Fase 2a)
    é um módulo próprio, ver docstring de cada services/cnab_*_service.py."""
    info = await bancos_service.get_banco(servidor, banco, cod)
    codigo = int((info or {}).get("codigo") or 0)
    return _MOTORES_CNAB.get(codigo)


@router.get("/bancos")
async def list_bancos(servidor: str, banco: str, busca: Optional[str] = None):
    return await bancos_service.list_bancos(servidor, banco, busca)


@router.get("/bancos/{cod}")
async def get_banco(cod: int, servidor: str, banco: str):
    return await bancos_service.get_banco(servidor, banco, cod)


@router.post("/bancos")
async def save_banco(req: BancoSaveRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "usuario_alteracao", "classe", "plataforma"})
    era_novo = req.cod is None
    result = await bancos_service.save_banco(req.servidor, req.banco, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BANCOS", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=result.get("cod"),
            descricao=f"{'Cadastro' if era_novo else 'Alteração'} do banco \"{req.descricao}\".",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/bancos/{cod}")
async def delete_banco(cod: int, req: BancoDeleteRequest, request: Request):
    result = await bancos_service.delete_banco(req.servidor, req.banco, cod)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BANCOS", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=cod,
            descricao="Exclusão de banco.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/bancos/{cod}/logo")
async def upload_logo_banco(
    cod: int,
    request: Request,
    servidor: str = Form(...),
    banco: str = Form(...),
    usuario_alteracao: Optional[int] = Form(None),
    classe: Optional[int] = Form(None),
    plataforma: Optional[str] = Form(None),
    arquivo: UploadFile = File(...),
):
    conteudo = await arquivo.read()
    result = await bancos_service.upload_logo_banco(servidor, banco, cod, conteudo, arquivo.content_type or "")
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            servidor, banco, tela="BANCOS", comando="GRAVAR_LOGO", usuario=usuario_alteracao, classe=classe,
            referencia=cod, descricao="Logo do banco cadastrada.", ip_origem=_ip(request), plataforma=plataforma,
        )
    return result


@router.post("/bancos/{cod}/logo/remover")
async def remover_logo_banco(cod: int, req: BancoDeleteRequest, request: Request):
    result = await bancos_service.remover_logo_banco(req.servidor, req.banco, cod)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BANCOS", comando="REMOVER_LOGO", usuario=req.usuario_alteracao, classe=req.classe,
            referencia=cod, descricao="Logo do banco removida.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/bancos/{cod}/remessa")
async def gerar_remessa(cod: int, req: GerarRemessaRequest, request: Request):
    motor = await _motor_cnab(req.servidor, req.banco, cod)
    if motor is None:
        return {"success": False, "message": "Geração de remessa implementada só para Bradesco (237), Inter (077), Santander (033), Banco do Brasil (001) e Itaú (341) nesta fase."}
    result = await motor.gerar_remessa(req.servidor, req.banco, cod, req.titulos)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BANCOS", comando="GERAR_REMESSA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=cod,
            descricao=f"Remessa nº {result.get('num_remessa')} gerada — {result.get('qtd_titulos')} título(s).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/bancos/{cod}/retorno")
async def processar_retorno(cod: int, req: ProcessarRetornoRequest, request: Request):
    motor = await _motor_cnab(req.servidor, req.banco, cod)
    if motor is None:
        return {"success": False, "message": "Processamento de retorno implementado só para Bradesco (237), Inter (077), Santander (033), Banco do Brasil (001) e Itaú (341) nesta fase."}
    result = await motor.processar_retorno(req.servidor, req.banco, cod, req.conteudo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="BANCOS", comando="IMP_RETORNO",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=cod,
            descricao=f"Retorno processado — {result.get('baixados')} baixa(s), {result.get('confirmados')} confirmação(ões).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/bancos/{cod}/retorno/preview")
async def preview_retorno(cod: int, req: PreviewRetornoRequest):
    """Lê o arquivo de retorno e devolve a grade de revisão (títulos a
    baixar + resumo de confirmações/ignorados), sem gravar nada — usado
    pela tela `Importação do Arquivo de Retorno` (RETORNO_BANC). Ver
    services/cobranca_retorno_service.py."""
    return await cobranca_retorno_service.preview_retorno(req.servidor, req.banco, cod, req.conteudo)


@router.post("/bancos/{cod}/retorno/aplicar")
async def aplicar_baixas(cod: int, req: AplicarBaixasRequest, request: Request):
    result = await cobranca_retorno_service.aplicar_baixas(req.servidor, req.banco, cod, req.itens, req.conta)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="RETORNO_BANC", comando="BAIXAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=cod,
            descricao=f"Baixa de títulos selecionados — {result.get('baixados')} baixa(s), {result.get('ja_baixados')} já baixado(s).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
