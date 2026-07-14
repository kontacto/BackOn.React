"""Rotas de Funcionários (tabela `funcionarios` + sub-tabelas relacionadas).

Gravar/Excluir e as sub-ações (ausências, exceção de comissão) são
registradas em `log_auditoria` — mesmo padrão de `routes/veiculos.py`. O
diff de auditoria cobre os campos escalares do cadastro principal; as
listas (áreas/carteiras/especialidades/horários) não são diffadas campo a
campo (mesma simplificação já aplicada em Executor Padrão OS para relações
N:N complexas).
"""
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import funcionarios_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="FUNCIONARIOS", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class HorarioInput(BaseModel):
    dia: int
    disp_ini: Optional[str] = None
    disp_fim: Optional[str] = None
    intervalo1: Optional[int] = 0
    pausa_ini: Optional[str] = None
    pausa_fim: Optional[str] = None
    encaixe: Optional[int] = 0


class FuncionarioSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    nome_guerra: str
    situacao: Optional[str] = None
    nome: str
    cod_funcao: Optional[str] = None
    email: Optional[str] = ""
    liberar_pedido_lista_negra: bool = False
    liberar_pedido_limite_excedido: bool = False
    admissao: Optional[str] = None
    cpf_prof: Optional[str] = ""
    ident_prof: Optional[str] = ""
    cart_prof: Optional[str] = ""
    data_nasc: Optional[str] = None
    sexo_prof: Optional[str] = None
    codigo_dep: Optional[str] = ""
    docespecial: Optional[int] = None
    numespecial: Optional[str] = ""
    conselho: Optional[str] = ""
    numconselho: Optional[str] = ""
    codcargo: Optional[int] = None
    cep_prof: Optional[str] = ""
    bairr_prof: Optional[str] = ""
    endereco: Optional[str] = ""
    cid_prof: Optional[str] = ""
    est_prof: Optional[str] = ""
    tel_prof: Optional[str] = ""
    controla_carteira: bool = False
    tipo_comissao: Optional[str] = "S"
    comissaop: Optional[float] = 0
    comissaos: Optional[float] = 0
    comissao_prioridade_vendedor: bool = False
    tipo_comissao_e: Optional[str] = "S"
    comissaop_e: Optional[float] = 0
    comissaos_e: Optional[float] = 0
    comissao_prioridade_executor: bool = False
    tipo_comissao_a: Optional[str] = "S"
    comissaop_a: Optional[float] = 0
    comissaos_a: Optional[float] = 0
    comissao_prioridade_atendente: bool = False
    desconta_comissao: bool = False
    areas_estoque: List[int] = []
    areas_atuacao: List[int] = []
    carteiras: List[int] = []
    especialidades: List[int] = []
    horarios: List[HorarioInput] = []


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class AusenciaSaveRequest(AuditFields):
    servidor: str
    banco: str
    data_ini: Optional[str] = None
    data_fim: Optional[str] = None
    hora_ini: Optional[str] = None
    hora_fim: Optional[str] = None
    intervalo1: Optional[int] = 0
    obs: str


class ComissaoExcecaoSaveRequest(AuditFields):
    servidor: str
    banco: str
    item: str
    tipo: str  # V / E / A
    comissao: float


# Campos escalares diffados no log de auditoria (nome do request -> coluna real).
_FIELD_TO_COLUNA = {
    "codigo_dep": "CODIGO_DEP",
    "controla_carteira": "Controla_Carteira",
    "comissao_prioridade_vendedor": "COMISSAO_PRIORIDADE_VENDEDOR",
    "comissao_prioridade_executor": "COMISSAO_PRIORIDADE_EXECUTOR",
    "comissao_prioridade_atendente": "COMISSAO_PRIORIDADE_ATENDENTE",
    "desconta_comissao": "DESCONTA_DESCARTAVEIS",
}
_CAMPOS_DIFF = [
    "nome_guerra", "situacao", "nome", "cod_funcao", "email",
    "liberar_pedido_lista_negra", "liberar_pedido_limite_excedido",
    "admissao", "cpf_prof", "ident_prof", "cart_prof", "data_nasc", "sexo_prof",
    "codigo_dep", "docespecial", "numespecial", "conselho", "numconselho", "codcargo",
    "cep_prof", "bairr_prof", "endereco", "cid_prof", "est_prof", "tel_prof",
    "controla_carteira",
    "tipo_comissao", "comissaop", "comissaos", "comissao_prioridade_vendedor",
    "tipo_comissao_e", "comissaop_e", "comissaos_e", "comissao_prioridade_executor",
    "tipo_comissao_a", "comissaop_a", "comissaos_a", "comissao_prioridade_atendente",
    "desconta_comissao",
]
CAMPOS_LOG = [_FIELD_TO_COLUNA.get(c, c) for c in _CAMPOS_DIFF]

# Campos texto que o service grava como NULL quando vazios (ver `_coerce_vals`
# em `funcionarios_service.py`) — o "depois" do diff precisa espelhar isso,
# senão "" (valor cru do request) vs NULL (valor real gravado) sempre aparece
# como alteração falsa quando o campo já estava vazio (mesma lição já
# documentada pra Veículos: helper "depois" tem que bater com o fallback do
# service, não com o `model_dump()` cru).
_CAMPOS_TEXTO_NULLABLE = {
    "situacao", "cod_funcao", "email", "cpf_prof", "ident_prof", "cart_prof", "sexo_prof",
    "codigo_dep", "numespecial", "conselho", "numconselho", "cep_prof", "bairr_prof",
    "endereco", "cid_prof", "est_prof", "tel_prof",
}


def _depois_funcionario(dados: dict) -> dict:
    depois = {}
    for c in _CAMPOS_DIFF:
        v = dados.get(c)
        if c in _CAMPOS_TEXTO_NULLABLE:
            v = (v or "").strip() or None
        depois[_FIELD_TO_COLUNA.get(c, c)] = v
    return depois


def _normaliza_datas(antes: Optional[dict]) -> Optional[dict]:
    if not antes:
        return antes
    out = dict(antes)
    for campo in ("admissao", "data_nasc"):
        v = out.get(campo)
        if isinstance(v, date):
            out[campo] = v.isoformat()
    return out


@router.get("/funcionarios-cadastro")
async def list_funcionarios_route(servidor: str, banco: str, search: str = ""):
    return await funcionarios_service.list_funcionarios(servidor, banco, search)


@router.get("/funcionarios-cadastro/vendedores")
async def list_vendedores_route(servidor: str, banco: str, excluir: Optional[int] = None):
    return await funcionarios_service.list_vendedores(servidor, banco, excluir)


@router.get("/funcionarios-cadastro/{codigo}")
async def get_funcionario_route(codigo: int, servidor: str, banco: str):
    return await funcionarios_service.get_funcionario(servidor, banco, codigo)


@router.post("/funcionarios-cadastro")
async def save_funcionario_route(req: FuncionarioSaveRequest, request: Request):
    dados = req.model_dump()
    antes = None
    if req.codigo:
        antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "funcionarios", "codigo_int", req.codigo)
        antes = _normaliza_datas(antes)
    result = await funcionarios_service.save_funcionario(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, _depois_funcionario(dados), CAMPOS_LOG)
        await _log(req, request, comando="GRAVAR", referencia=req.nome_guerra, descricao=f"Funcionário '{req.nome_guerra}' gravado", campos=campos)
    return result


@router.post("/funcionarios-cadastro/{codigo}/excluir")
async def delete_funcionario_route(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "funcionarios", "codigo_int", codigo)
    result = await funcionarios_service.delete_funcionario(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(_normaliza_datas(antes), CAMPOS_LOG)
        referencia = (antes or {}).get("nome_guerra", codigo)
        await _log(req, request, comando="EXCLUIR", referencia=referencia, descricao=f"Funcionário '{referencia}' excluído", campos=campos)
    return result


@router.post("/funcionarios-cadastro/{codigo}/ausencias")
async def add_ausencia_route(codigo: int, req: AusenciaSaveRequest, request: Request):
    dados = req.model_dump()
    result = await funcionarios_service.add_ausencia(req.servidor, req.banco, codigo, dados)
    if result.get("success"):
        await _log(req, request, comando="AUSENCIA", referencia=codigo, descricao=f"Ausência registrada para o funcionário {codigo}")
    return result


@router.post("/funcionarios-cadastro/ausencias/{ausencia_id}/excluir")
async def delete_ausencia_route(ausencia_id: int, req: DeleteRequest, request: Request):
    result = await funcionarios_service.delete_ausencia(req.servidor, req.banco, ausencia_id)
    if result.get("success"):
        await _log(req, request, comando="AUSENCIA", referencia=ausencia_id, descricao=f"Ausência {ausencia_id} excluída")
    return result


@router.post("/funcionarios-cadastro/{codigo}/comissao-excecao")
async def save_comissao_excecao_route(codigo: int, req: ComissaoExcecaoSaveRequest, request: Request):
    result = await funcionarios_service.save_comissao_excecao(req.servidor, req.banco, codigo, req.item, req.tipo, req.comissao)
    if result.get("success"):
        await _log(req, request, comando="COMISSAO_EXCECAO", referencia=codigo, descricao=f"Exceção de comissão gravada para o funcionário {codigo} (item {req.item})")
    return result


@router.post("/funcionarios-cadastro/comissao-excecao/{excecao_id}/excluir")
async def delete_comissao_excecao_route(excecao_id: int, req: DeleteRequest, request: Request):
    result = await funcionarios_service.delete_comissao_excecao(req.servidor, req.banco, excecao_id)
    if result.get("success"):
        await _log(req, request, comando="COMISSAO_EXCECAO", referencia=excecao_id, descricao=f"Exceção de comissão {excecao_id} excluída")
    return result
