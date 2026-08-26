"""Rotas de Geração de Boletos — ver services/geracao_boletos_service.py,
services/boleto_pdf_service.py."""
from fastapi import APIRouter, Request
from fastapi.responses import Response

from models.geracao_boletos import ListarTitulosRequest, TitulosBoletoRequest
from models.log_auditoria import AuditFields
from services import geracao_boletos_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request):
    return request.client.host if request.client else None


async def _log(req: AuditFields, request: Request, servidor: str, banco: str, *, comando: str, referencia, descricao: str):
    await log_auditoria_service.registrar_log(
        servidor, banco, tela="GERACAO_BOLETOS", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


@router.post("/geracao-boletos/{cod_banco}/titulos")
async def listar_titulos(cod_banco: int, req: ListarTitulosRequest):
    filtros = req.model_dump(exclude={"servidor", "banco"})
    return await geracao_boletos_service.listar_titulos(req.servidor, req.banco, cod_banco, filtros)


@router.post("/geracao-boletos/{cod_banco}/pdf")
async def baixar_pdf(cod_banco: int, req: TitulosBoletoRequest, request: Request):
    result = await geracao_boletos_service.baixar_pdf(req.servidor, req.banco, cod_banco, req.titulos)
    if not result.get("success"):
        return result
    await _log(req, request, req.servidor, req.banco, comando="PDF", referencia=cod_banco, descricao=f"PDF gerado para {len(req.titulos)} título(s) do banco {cod_banco}")
    return Response(
        content=result["conteudo"],
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="boletos.pdf"'},
    )


@router.post("/geracao-boletos/{cod_banco}/enviar-email")
async def enviar_email(cod_banco: int, req: TitulosBoletoRequest, request: Request):
    result = await geracao_boletos_service.enviar_email(req.servidor, req.banco, cod_banco, req.titulos)
    if result.get("success"):
        enviados = sum(1 for r in result.get("resultados", []) if r.get("success"))
        await _log(req, request, req.servidor, req.banco, comando="EMAIL", referencia=cod_banco, descricao=f"Boleto enviado por e-mail: {enviados}/{len(req.titulos)} com sucesso")
    return result
