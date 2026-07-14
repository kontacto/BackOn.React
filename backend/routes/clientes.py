"""Rotas de clientes (listagem, busca, resumo, tipo e CRUD).

Gravar Cliente é registrado em `log_auditoria` (diff campo-a-campo, buscando o
registro atual antes de chamar `clientes_service.save_cliente`, que não muda).
Não existe endpoint de exclusão de cliente ainda, então só GRAVAR é logado.

Alguns campos do `ClienteSaveRequest` têm nome diferente da coluna real na
tabela `cliente` (ver `CLAUDE.md` > "Legacy field-to-tab mapping" — nomes
corrigidos após verificação ao vivo contra o banco); `CAMPO_COLUNA` mapeia só
essas exceções, os demais usam o mesmo nome.
"""
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from models.schemas import ClientesRequest, ClienteCreateRequest, ClienteSaveRequest
from services import clientes_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


CAMPO_COLUNA = {
    "nome_fantasia": "fantasia",
    "inativo_em": "DATA_ENCERRAMENTO_CLIENTE",
    "tributa_iss_fora_municipio": "TRIBUTA_ISS_FORA",
    "forma_pagamento": "forma_pag",
    "fatura_para": "faturamento_principal",
    "cliente_principal": "faturar",
    "status": "STATUS_CLIENTE",
}

CAMPOS_CLIENTE = [
    "cgc_cpf", "nome", "e_mail", "inscre", "tipo", "aceita_email", "nome_fantasia", "sexo", "data_nasc",
    "inscr_mun", "site", "historico", "situacao", "status", "inativo_em", "contato", "limite_credito",
    "desconto", "regime_tributario", "credita_icms", "consumidor_final", "tributa_iss_fora_municipio",
    "fatura_para", "cliente_principal", "prazo_faturamento", "indpres", "canal_aquisicao_cliente",
    "dia_contato", "dia_entrega", "forma_pagamento", "segmento", "rota", "regiao", "email_cobranca",
    "email_nfe", "centro_custo_cliente", "conta_transf_caixa", "cobra_tarifa_bancaria",
    "tipo_cobranca_tarifa", "valor_frete", "classe_caixa", "sub_classe_caixa",
]


def _colunas_cliente() -> list:
    return [CAMPO_COLUNA.get(c, c) for c in CAMPOS_CLIENTE]


def _depois_cliente(req: ClienteSaveRequest) -> dict:
    dump = req.model_dump()
    return {CAMPO_COLUNA.get(c, c): dump.get(c) for c in CAMPOS_CLIENTE}


async def _log_cliente(base: ClienteSaveRequest, request: Request, *, codigo, antes) -> None:
    campos = log_auditoria_service.diff_campos(antes, _depois_cliente(base), _colunas_cliente())
    await log_auditoria_service.registrar_log(
        base.servidor, base.banco, tela="CLIENTE", comando="GRAVAR",
        usuario=base.usuario_alteracao or base.usuario_cadastro, classe=base.classe,
        referencia=str(codigo), descricao=f"Cliente '{base.nome}' gravado",
        campos_alterados=campos or None, ip_origem=_ip(request), plataforma=base.plataforma,
    )


@router.post("/clientes")
async def list_clientes(req: ClientesRequest):
    return await clientes_service.list_clientes(req)


@router.get("/tipo-cliente")
async def list_tipo_cliente(servidor: str, banco: str):
    return await clientes_service.list_tipo_cliente(servidor, banco)


@router.get("/clientes/find/by-cgc")
async def find_cliente_by_cgc(servidor: str, banco: str, cgc: str):
    return await clientes_service.find_by_cgc(servidor, banco, cgc)


@router.get("/clientes/find/search")
async def find_clientes_search(servidor: str, banco: str, term: str = ""):
    return await clientes_service.find_clientes_search(servidor, banco, term)


@router.get("/clientes/{codigo}/resumo")
async def get_cliente_resumo(codigo: int, servidor: str, banco: str):
    return await clientes_service.cliente_resumo(servidor, banco, codigo)


@router.get("/clientes/{codigo}")
async def get_cliente(codigo: int, servidor: str, banco: str):
    return await clientes_service.get_cliente(servidor, banco, codigo)


@router.post("/clientes/create")
async def create_cliente(req: ClienteCreateRequest, request: Request):
    base = ClienteSaveRequest(**req.dict(exclude={"enderecos", "telefones", "contatos"}))
    result = await clientes_service.save_cliente(base, req.enderecos, req.telefones, None, req.contatos)
    if result.get("success"):
        await _log_cliente(base, request, codigo=result.get("codigo"), antes=None)
    return result


@router.put("/clientes/{codigo}")
async def update_cliente(codigo: int, req: ClienteCreateRequest, request: Request):
    base = ClienteSaveRequest(**req.dict(exclude={"enderecos", "telefones", "contatos"}))
    antes = await log_auditoria_service.get_row_by_pk(base.servidor, base.banco, "cliente", "codigo", codigo)
    result = await clientes_service.save_cliente(base, req.enderecos, req.telefones, codigo, req.contatos)
    if result.get("success"):
        await _log_cliente(base, request, codigo=result.get("codigo", codigo), antes=antes)
    return result


class ListaNegraSaveRequest(AuditFields):
    servidor: str
    banco: str
    motivo: str


class ListaNegraDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.post("/clientes/{codigo}/lista-negra")
async def save_lista_negra(codigo: int, req: ListaNegraSaveRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "lista_negra", "codigo", str(codigo))
    result = await clientes_service.save_lista_negra(req.servidor, req.banco, codigo, req.motivo)
    if result.get("success"):
        campos = log_auditoria_service.diff_campos(antes, {"motivo": req.motivo}, ["motivo"])
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CLIENTE", comando="LISTA_NEGRA",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Cliente {codigo} incluído/alterado na Lista Negra",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/clientes/{codigo}/lista-negra/excluir")
async def delete_lista_negra(codigo: int, req: ListaNegraDeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "lista_negra", "codigo", str(codigo))
    result = await clientes_service.delete_lista_negra(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, ["motivo"])
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CLIENTE", comando="LISTA_NEGRA",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(codigo), descricao=f"Cliente {codigo} removido da Lista Negra",
            campos_alterados=campos or None, ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
