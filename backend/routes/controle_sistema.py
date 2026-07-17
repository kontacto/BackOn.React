"""Rotas de Controle do Sistema (Configurações > Geral).

Toda ação de Gravar/Excluir é registrada em `log_auditoria` sob a tela
`CTRL_SISTEMA` — busca o registro atual antes de chamar o service (que faz o
UPDATE/DELETE às cegas, sem mudança nenhuma nas funções de service), compara com
os valores novos do request e grava o diff campo-a-campo. Log é best-effort: nunca
impede a operação (mesmo padrão de `tabelas_aux.py`).
"""
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import certificado_digital_service, controle_sistema_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, comando: str, referencia=None, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="CTRL_SISTEMA", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


def _descricao_alteracoes(diffs: list, labels: dict, prefixo: str) -> str:
    """Descrição de log legível pra grupos de campos com botão próprio (NF/NFCe/
    MDF-e) — pedido explícito do usuário, com base no comportamento do legado:
    uma linha de log específica tipo "Alteração do Número de NF de X para Y.",
    não um diff genérico de "N campos alterados"."""
    if not diffs:
        return f"{prefixo} gravado (sem alteração de valor)."
    partes = [
        f"Alteração de {labels.get(d['campo'], d['campo'])} de '{d['antes'] or '(vazio)'}' para '{d['depois'] or '(vazio)'}'."
        for d in diffs
    ]
    return " ".join(partes)


class SalvarControleRequest(AuditFields):
    servidor: str
    banco: str
    dados: dict = {}


class SalvarGrupoRequest(AuditFields):
    servidor: str
    banco: str
    dados: dict = {}


class SerieNfSaveRequest(AuditFields):
    servidor: str
    banco: str
    serie_nf: str
    numero_nf: int = 0


class SerieNfDeleteRequest(AuditFields):
    servidor: str
    banco: str


class TurnoHorarioSaveRequest(AuditFields):
    servidor: str
    banco: str
    turno: int
    hora_fim: str


class TurnoHorarioDeleteRequest(AuditFields):
    servidor: str
    banco: str


class CertificadoDeleteRequest(AuditFields):
    servidor: str
    banco: str


class SimplesRemessaSaveRequest(AuditFields):
    servidor: str
    banco: str
    tipo_mov: str
    dentro: list = []
    fora: list = []


class DirecionamentoImpressoraSaveRequest(AuditFields):
    servidor: str
    banco: str
    computador: str
    tipo: Optional[int] = None
    impressora: str
    automatica: bool = False


class DirecionamentoImpressoraDeleteRequest(AuditFields):
    servidor: str
    banco: str


# ==================== Controle / Controle Aux ====================

@router.get("/controle-sistema")
async def get_controle_sistema(servidor: str, banco: str):
    return await controle_sistema_service.get_controle_sistema(servidor, banco)


@router.post("/controle-sistema")
async def save_controle_sistema(req: SalvarControleRequest, request: Request):
    antes_c = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "controle", "empresa", controle_sistema_service.EMPRESA)
    antes_a = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "controle_aux", "empresa_aux", controle_sistema_service.EMPRESA)
    result = await controle_sistema_service.save_controle_sistema(req.servidor, req.banco, req.dados)
    if result.get("success"):
        campos = (
            log_auditoria_service.diff_campos(antes_c, req.dados, controle_sistema_service.CAMPOS_CONTROLE)
            + log_auditoria_service.diff_campos(antes_a, req.dados, controle_sistema_service.CAMPOS_CONTROLE_AUX)
        )
        await _log(req, request, comando="GRAVAR", descricao=f"Controle do Sistema atualizado ({len(campos)} alteração(ões))", campos=campos)
    return result


# ==================== Numeração NF / NFCe / MDF-e (botões e log próprios) ====================
# Achado do usuário direto na tela legada: o Gravar principal não toca nesses
# campos — cada grupo tem botão dedicado ("Gravar Alterações NFE"/"NFCE"/
# "MDF-e") e uma linha de log com descrição específica do que mudou.

@router.post("/controle-sistema/nf-principal")
async def save_nf_principal(req: SalvarGrupoRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "controle", "empresa", controle_sistema_service.EMPRESA)
    result = await controle_sistema_service.save_nf_principal(req.servidor, req.banco, req.dados)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.dados, controle_sistema_service.CAMPOS_NF_PRINCIPAL)
        descricao = _descricao_alteracoes(campos, controle_sistema_service.LABELS_NF_PRINCIPAL, "Numeração de NF")
        await _log(req, request, comando="GRAVAR_NF", descricao=descricao, campos=campos)
    return result


@router.post("/controle-sistema/nfce-numeracao")
async def save_nfce_numeracao(req: SalvarGrupoRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "controle_aux", "empresa_aux", controle_sistema_service.EMPRESA)
    result = await controle_sistema_service.save_nfce_numeracao(req.servidor, req.banco, req.dados)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.dados, controle_sistema_service.CAMPOS_NFCE_NUMERACAO)
        descricao = _descricao_alteracoes(campos, controle_sistema_service.LABELS_NFCE_NUMERACAO, "Numeração de NFCe")
        await _log(req, request, comando="GRAVAR_NFCE", descricao=descricao, campos=campos)
    return result


@router.post("/controle-sistema/mdfe-numeracao")
async def save_mdfe_numeracao(req: SalvarGrupoRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "controle_aux", "empresa_aux", controle_sistema_service.EMPRESA)
    result = await controle_sistema_service.save_mdfe_numeracao(req.servidor, req.banco, req.dados)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, req.dados, controle_sistema_service.CAMPOS_MDFE_NUMERACAO)
        descricao = _descricao_alteracoes(campos, controle_sistema_service.LABELS_MDFE_NUMERACAO, "Numeração de MDF-e")
        await _log(req, request, comando="GRAVAR_MDFE", descricao=descricao, campos=campos)
    return result


# ==================== Grid: Outras Séries NFe ====================

@router.get("/controle-sistema/series-nf")
async def list_series_nf(servidor: str, banco: str):
    return await controle_sistema_service.list_series_nf(servidor, banco)


@router.post("/controle-sistema/series-nf")
async def save_serie_nf(req: SerieNfSaveRequest, request: Request):
    result = await controle_sistema_service.save_serie_nf(req.servidor, req.banco, req.serie_nf, req.numero_nf)
    if result.get("success"):
        await _log(req, request, comando="GRAVAR_SERIE", referencia=req.serie_nf, descricao=f"Série NFe '{req.serie_nf}' gravada (número {req.numero_nf})")
    return result


@router.post("/controle-sistema/series-nf/{serie_nf}/excluir")
async def delete_serie_nf(serie_nf: str, req: SerieNfDeleteRequest, request: Request):
    result = await controle_sistema_service.delete_serie_nf(req.servidor, req.banco, serie_nf)
    if result.get("success"):
        await _log(req, request, comando="EXCLUIR_SERIE", referencia=serie_nf, descricao=f"Série NFe '{serie_nf}' excluída")
    return result


# ==================== Grid: Turno (Configurações Posto) ====================

@router.get("/controle-sistema/turno-horario")
async def list_turno_horario(servidor: str, banco: str):
    return await controle_sistema_service.list_turno_horario(servidor, banco)


@router.post("/controle-sistema/turno-horario")
async def save_turno_horario(req: TurnoHorarioSaveRequest, request: Request):
    result = await controle_sistema_service.save_turno_horario(req.servidor, req.banco, req.turno, req.hora_fim)
    if result.get("success"):
        await _log(req, request, comando="GRAVAR_TURNO", referencia=req.turno, descricao=f"Turno {req.turno} gravado (fecha às {req.hora_fim})")
    return result


@router.post("/controle-sistema/turno-horario/{turno}/excluir")
async def delete_turno_horario(turno: int, req: TurnoHorarioDeleteRequest, request: Request):
    result = await controle_sistema_service.delete_turno_horario(req.servidor, req.banco, turno)
    if result.get("success"):
        await _log(req, request, comando="EXCLUIR_TURNO", referencia=turno, descricao=f"Turno {turno} excluído")
    return result


# ==================== Certificado Digital ====================

@router.get("/controle-sistema/certificados")
async def list_certificados(servidor: str, banco: str):
    return await certificado_digital_service.list_certificados(servidor, banco)


@router.post("/controle-sistema/certificados")
async def upload_certificado(
    request: Request,
    servidor: str = Form(...),
    banco: str = Form(...),
    senha: str = Form(""),
    tipo_certificado: str = Form("A1"),
    usuario_alteracao: Optional[int] = Form(None),
    classe: Optional[int] = Form(None),
    plataforma: Optional[str] = Form(None),
    arquivo: UploadFile = File(...),
):
    conteudo = await arquivo.read()
    result = await certificado_digital_service.upload_certificado(servidor, banco, conteudo, senha, tipo_certificado)
    if result.get("success"):
        req = CertificadoDeleteRequest(servidor=servidor, banco=banco, usuario_alteracao=usuario_alteracao, classe=classe, plataforma=plataforma)
        await _log(
            req, request, comando="GRAVAR_CERT", referencia=result.get("sequencia"),
            descricao=f"Certificado Digital cadastrado (validade até {result.get('data_fim')})",
        )
    return result


@router.post("/controle-sistema/certificados/{sequencia}/excluir")
async def delete_certificado(sequencia: int, req: CertificadoDeleteRequest, request: Request):
    result = await certificado_digital_service.delete_certificado(req.servidor, req.banco, sequencia)
    if result.get("success"):
        await _log(req, request, comando="EXCLUIR_CERT", referencia=sequencia, descricao=f"Certificado Digital #{sequencia} excluído")
    return result


# ==================== Modal: NFe de Simples Remessa dos DAV's ====================

@router.get("/controle-sistema/simples-remessa")
async def get_simples_remessa(servidor: str, banco: str):
    return await controle_sistema_service.get_simples_remessa(servidor, banco)


@router.post("/controle-sistema/simples-remessa")
async def save_simples_remessa(req: SimplesRemessaSaveRequest, request: Request):
    result = await controle_sistema_service.save_simples_remessa(req.servidor, req.banco, req.tipo_mov, req.dentro, req.fora)
    if result.get("success"):
        await _log(req, request, comando="GRAVAR_SREM", descricao=f"Configuração de Simples Remessa gravada (tipo {req.tipo_mov})")
    return result


# ==================== Modal: Direcionamento de Impressão por Grupo ====================

@router.get("/controle-sistema/direcionamento-impressora")
async def list_direcionamento_impressora(servidor: str, banco: str):
    return await controle_sistema_service.list_direcionamento_impressora(servidor, banco)


@router.post("/controle-sistema/direcionamento-impressora")
async def save_direcionamento_impressora(req: DirecionamentoImpressoraSaveRequest, request: Request):
    result = await controle_sistema_service.save_direcionamento_impressora(req.servidor, req.banco, req.computador, req.tipo, req.impressora, req.automatica)
    if result.get("success"):
        await _log(req, request, comando="GRAVAR_IMPR", referencia=f"{req.computador}/{req.tipo}", descricao=f"Direcionamento de impressão gravado ({req.computador}, tipo {req.tipo} -> {req.impressora})")
    return result


@router.post("/controle-sistema/direcionamento-impressora/{codigo}/excluir")
async def delete_direcionamento_impressora(codigo: int, req: DirecionamentoImpressoraDeleteRequest, request: Request):
    result = await controle_sistema_service.delete_direcionamento_impressora(req.servidor, req.banco, codigo)
    if result.get("success"):
        await _log(req, request, comando="EXCLUIR_IMPR", referencia=codigo, descricao=f"Direcionamento de impressão #{codigo} excluído")
    return result


@router.get("/controle-sistema/direcionamento-impressora/por-finalidade")
async def direcionamento_impressora_por_finalidade(tipo: int, servidor: str, banco: str):
    """Usado pelo Pedido Bar ao incluir um item — decide se deve abrir
    (automático ou com confirmação) o preview de impressão do item.
    Ver `_get_direcionamento_por_finalidade_sync` (ignora o campo
    Computador, decisão explícita do usuário 2026-07-16)."""
    return await controle_sistema_service.get_direcionamento_por_finalidade(servidor, banco, tipo)
