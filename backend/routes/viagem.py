"""Rotas de Manutenção de Viagens (módulo Cilindros) — ver
services/viagem_service.py. Legado: FrmManViagens.frm. Ver PENDENCIAS.md >
"Cilindros" > "Fase 3" para o rastreio completo."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, viagem_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ViagemHeaderDados(BaseModel):
    veiculo: int = 0
    motorista: Optional[int] = None
    ajudante: Optional[int] = None
    tipo_viagem: int = 0
    descricao: str = ""
    obs: str = ""
    saida: Optional[str] = None
    hora_saida: Optional[str] = None
    km_saida: float = 0
    retorno: Optional[str] = None
    hora_retorno: Optional[str] = None
    km_retorno: float = 0


class ViagemSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    dados: ViagemHeaderDados


class ItemSaidaDados(BaseModel):
    cliente: int = 0
    cilindro: int = 0
    status_saida: str = ""
    numero_serie: str = ""
    doc_saida: int = 0
    tipo_doc_saida: int = 3
    carga_saida: str = "CHEIO"
    os_saida: str = ""
    obs_saida: str = ""


class ItemRetornoDados(BaseModel):
    cilindro_retorno: int = 0
    status_retorno: str = ""
    numero_serie_retorno: str = ""
    nf_retorno: int = 0
    os_retorno: str = ""
    carga_retorno: str = "CHEIO"
    obs_retorno: str = ""


class AddItemRequest(AuditFields):
    servidor: str
    banco: str
    dados: ItemSaidaDados


class SaveItemRetornoRequest(AuditFields):
    servidor: str
    banco: str
    dados: ItemRetornoDados


class ViagemActionRequest(AuditFields):
    servidor: str
    banco: str


class AlterarCilindroRequest(AuditFields):
    servidor: str
    banco: str
    cilindro: int


@router.get("/viagens")
async def list_viagens(
    servidor: str, banco: str, codigo: Optional[int] = None, veiculo: Optional[int] = None,
    motorista: Optional[int] = None, tipo_viagem: Optional[int] = None, situacao: Optional[str] = None,
    saida_de: Optional[str] = None, saida_ate: Optional[str] = None,
):
    filtros = {
        "codigo": codigo, "veiculo": veiculo, "motorista": motorista, "tipo_viagem": tipo_viagem,
        "situacao": situacao, "saida_de": saida_de, "saida_ate": saida_ate,
    }
    return await viagem_service.list_viagens(servidor, banco, filtros)


@router.get("/viagens/{codigo}")
async def get_viagem(codigo: int, servidor: str, banco: str):
    return await viagem_service.get_viagem(servidor, banco, codigo)


@router.post("/viagens")
async def save_viagem_header(req: ViagemSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await viagem_service.save_viagem_header(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(result.get("codigo")),
            descricao=f"Dados da viagem {result.get('codigo')} gravados.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/itens")
async def add_item(codigo: int, req: AddItemRequest, request: Request):
    dados = req.dados.model_dump()
    result = await viagem_service.add_item(req.servidor, req.banco, codigo, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="ADD_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(result.get("codigo")),
            descricao=f"Item adicionado à viagem {codigo}.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/itens/{item_codigo}/retorno")
async def save_item_retorno(item_codigo: int, req: SaveItemRetornoRequest, request: Request):
    dados = req.dados.model_dump()
    result = await viagem_service.save_item_retorno(req.servidor, req.banco, item_codigo, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="ADD_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(item_codigo),
            descricao=f"Retorno do item {item_codigo} gravado.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/itens/{item_codigo}/excluir")
async def delete_item(item_codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.delete_item(req.servidor, req.banco, item_codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="DEL_ITEM",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(item_codigo),
            descricao=f"Item {item_codigo} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/itens/{item_codigo}/alterar-cilindro")
async def alterar_cilindro(item_codigo: int, req: AlterarCilindroRequest, request: Request):
    result = await viagem_service.alterar_cilindro_item(req.servidor, req.banco, item_codigo, req.cilindro)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="ALT_CILINDRO",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(item_codigo),
            descricao=f"Cilindro do item {item_codigo} alterado para {req.cilindro}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/renumerar")
async def renumerar_itens(codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.renumerar_itens(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Itens da viagem {codigo} renumerados.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/fechar-saida")
async def fechar_saida(codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.fechar_saida(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="FECHAR_SAIDA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Saída da viagem {codigo} fechada.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/fechar-entrada")
async def fechar_entrada(codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.fechar_entrada(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="FECHAR_ENTRADA",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Entrada da viagem {codigo} fechada.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/reabrir")
async def reabrir(codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.reabrir(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="REABRIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Viagem {codigo} reaberta.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/viagens/{codigo}/cancelar")
async def cancelar_viagem(codigo: int, req: ViagemActionRequest, request: Request):
    result = await viagem_service.cancelar_viagem(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="VIAGEM", comando="CANCELAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Viagem {codigo} cancelada.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
