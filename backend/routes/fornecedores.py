"""Rotas de Manutenção de Fornecedores — ver services/fornecedores_service.py
para o desenho completo (schema real, mismatches rótulo/coluna do legado,
guards de exclusão, fora de escopo)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import fornecedores_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class TelefoneItem(BaseModel):
    ddd: str = ""
    tel: str = ""
    descricao: str = ""


class EnderecoItem(BaseModel):
    endereco: str = ""
    numero: int = 0
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    cep: str = ""
    pais: str = ""
    tipo: int = 0


class ContatoItem(BaseModel):
    contato: str = ""
    setor: str = ""
    cargo: str = ""
    ddd: int = 0
    telefone: str = ""
    ddd_fax: int = 0
    fax: str = ""
    ddd_celular: int = 0
    celular: str = ""
    e_mail: str = ""
    sexo: str = "M"


class FornecedorDados(BaseModel):
    codigo: str
    nome: str
    fantasia: str = ""
    inscr_est: str = ""
    data: Optional[str] = None
    tipo: str = "S"
    situacao: str = "A"
    obs_forn: str = ""
    cliente_forn: Optional[int] = None
    distribuidor_texto: str = ""
    shipper_texto: str = ""
    e_mail: str = ""
    prazo_pgto: int = 0
    desconto: float = 0
    nossa_conta: str = ""
    dados_bancarios: str = ""
    conta_transf_caixa: Optional[int] = None
    classe_caixa: Optional[int] = None
    sub_classe_caixa: Optional[int] = None
    telefones: list[TelefoneItem] = []
    enderecos: list[EnderecoItem] = []
    contatos: list[ContatoItem] = []


class FornecedorSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo_int: Optional[int] = None
    dados: FornecedorDados


class FornecedorDeleteRequest(AuditFields):
    servidor: str
    banco: str


class GravarComoClienteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/fornecedores")
async def list_fornecedores(servidor: str, banco: str, search: str = ""):
    return await fornecedores_service.list_fornecedores(servidor, banco, search)


@router.get("/fornecedores/find/by-codigo")
async def find_by_codigo(codigo: str, servidor: str, banco: str):
    return await fornecedores_service.find_by_codigo(servidor, banco, codigo)


@router.get("/fornecedores/{codigo_int}")
async def get_fornecedor(codigo_int: int, servidor: str, banco: str):
    return await fornecedores_service.get_fornecedor(servidor, banco, codigo_int)


@router.post("/fornecedores")
async def save_fornecedor(req: FornecedorSaveRequest, request: Request):
    dados = req.dados.model_dump()
    dados["_distribuidor_texto"] = dados.pop("distribuidor_texto", "")
    dados["_shipper_texto"] = dados.pop("shipper_texto", "")
    result = await fornecedores_service.save_fornecedor(req.servidor, req.banco, req.codigo_int, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="FORNECEDOR", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("codigo_int")),
            descricao=f"Fornecedor {req.dados.nome} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/fornecedores/{codigo_int}/excluir")
async def delete_fornecedor(codigo_int: int, req: FornecedorDeleteRequest, request: Request):
    result = await fornecedores_service.delete_fornecedor(req.servidor, req.banco, codigo_int)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="FORNECEDOR", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo_int),
            descricao=f"Fornecedor {codigo_int} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/fornecedores/{codigo_int}/gravar-como-cliente")
async def gravar_como_cliente(codigo_int: int, req: GravarComoClienteRequest, request: Request):
    result = await fornecedores_service.gravar_como_cliente(req.servidor, req.banco, codigo_int)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="FORNECEDOR", comando="COMO_CLIENTE",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo_int),
            descricao=f"Fornecedor {codigo_int} gravado como cliente #{result.get('cliente_codigo')}.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
