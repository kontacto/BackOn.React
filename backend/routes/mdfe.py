"""Rotas do MDF-e (Manifesto Eletrônico de Documentos Fiscais) — Fase A
(cadastro sem emissão) + Fase B (emissão real/encerrar/cancelar/
consultar/gerar XML). Ver `services/mdfe_service.py` (Fase A) e
`services/mdfe_emissao_service.py` (Fase B) pro racional completo."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, mdfe_emissao_service, mdfe_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


@router.get("/mdfe")
async def listar(servidor: str, banco: str, situacao: Optional[str] = None):
    return await mdfe_service.list_mdfe(servidor, banco, situacao)


@router.get("/mdfe/{codigo}")
async def obter(codigo: int, servidor: str, banco: str):
    return await mdfe_service.get_mdfe(servidor, banco, codigo)


class SalvarMdfeRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    data_mdfe: Optional[str] = None
    veiculo: Optional[int] = None
    reboque: Optional[int] = None
    motorista: Optional[int] = None
    ajudante: Optional[int] = None
    ufini: Optional[str] = None
    uffim: Optional[str] = None
    percurso: Optional[str] = None
    tptransp: Optional[int] = None
    obs: Optional[str] = None


@router.post("/mdfe")
async def salvar(req: SalvarMdfeRequest, request: Request):
    dados = req.model_dump(exclude={"servidor", "banco", "codigo", "usuario_alteracao", "classe", "plataforma"})
    result = await mdfe_service.save_mdfe(req.servidor, req.banco, req.codigo, dados, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(result.get("codigo")),
            descricao=f"MDF-e #{result.get('codigo')} gravado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


class AcaoRequest(AuditFields):
    servidor: str
    banco: str


@router.delete("/mdfe/{codigo}")
async def excluir(codigo: int, req: AcaoRequest, request: Request):
    result = await mdfe_service.delete_mdfe(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"MDF-e #{codigo} excluído",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


class BuscarNotasRequest(BaseModel):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    num_nf: Optional[float] = None
    serie_nf: Optional[str] = None
    valor_total: Optional[float] = None
    tipo_pessoa: Optional[str] = None
    cliente_fornecedor_termo: Optional[str] = None
    data_nf_de: Optional[str] = None
    data_nf_ate: Optional[str] = None


@router.post("/mdfe/notas/buscar")
async def buscar_notas(req: BuscarNotasRequest):
    filtros = req.model_dump(exclude={"servidor", "banco"})
    return await mdfe_service.buscar_notas_elegiveis(req.servidor, req.banco, filtros)


@router.get("/mdfe/municipios")
async def buscar_municipios(servidor: str, banco: str, search: str = ""):
    return await mdfe_service.buscar_municipios(servidor, banco, search)


class AnexarNotaRequest(AuditFields):
    servidor: str
    banco: str
    nota: int


@router.post("/mdfe/{codigo}/notas")
async def anexar_nota(codigo: int, req: AnexarNotaRequest, request: Request):
    result = await mdfe_service.anexar_nota(req.servidor, req.banco, codigo, req.nota)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="ANEXAR_NOTA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Nota #{req.nota} anexada ao MDF-e #{codigo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.delete("/mdfe/{codigo}/notas/{nota}")
async def remover_nota(codigo: int, nota: int, req: AcaoRequest, request: Request):
    result = await mdfe_service.remover_nota(req.servidor, req.banco, codigo, nota)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="REMOVER_NOTA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Nota #{nota} removida do MDF-e #{codigo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ============ Fase B — emissão real, encerrar, cancelar, consultar, XML ============

@router.post("/mdfe/{codigo}/emitir")
async def emitir(codigo: int, req: AcaoRequest, request: Request):
    result = await mdfe_emissao_service.emitir_mdfe(req.servidor, req.banco, codigo, req.usuario_alteracao)
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="MDFE", comando="EMITIR",
        usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
        descricao=f"MDF-e #{codigo} — emissão {'autorizada' if result.get('success') else 'recusada'}: {result.get('message')}",
        ip_origem=_ip(request), plataforma=req.plataforma,
    )
    return result


class EncerrarMdfeRequest(AuditFields):
    servidor: str
    banco: str
    municipio_encerra: int


@router.post("/mdfe/{codigo}/encerrar")
async def encerrar(codigo: int, req: EncerrarMdfeRequest, request: Request):
    result = await mdfe_emissao_service.encerrar_mdfe(
        req.servidor, req.banco, codigo, req.municipio_encerra, req.usuario_alteracao,
    )
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="ENCERRAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"MDF-e #{codigo} encerrado",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


class CancelarMdfeRequest(AuditFields):
    servidor: str
    banco: str
    motivo: str


@router.post("/mdfe/{codigo}/cancelar")
async def cancelar(codigo: int, req: CancelarMdfeRequest, request: Request):
    result = await mdfe_emissao_service.cancelar_mdfe(req.servidor, req.banco, codigo, req.motivo, req.usuario_alteracao)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="MDFE", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"MDF-e #{codigo} cancelado — motivo: {req.motivo}",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/mdfe/{codigo}/consultar")
async def consultar(codigo: int, req: AcaoRequest, request: Request):
    result = await mdfe_emissao_service.consultar_mdfe(req.servidor, req.banco, codigo)
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="MDFE", comando="CONSULTAR",
        usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
        descricao=f"MDF-e #{codigo} — situação consultada no SEFAZ: {result.get('cstat')}",
        ip_origem=_ip(request), plataforma=req.plataforma,
    )
    return result


@router.get("/mdfe/{codigo}/xml")
async def gerar_xml(codigo: int, servidor: str, banco: str):
    return await mdfe_emissao_service.gerar_xml_mdfe(servidor, banco, codigo)
