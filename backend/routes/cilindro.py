"""Rotas de Cilindros (Cadastro/Consulta, Cliente x Cilindro, Nº Série) —
ver services/cilindro_service.py, cilindro_cliente_service.py,
cilindro_serie_service.py. As duas últimas são popups da tela de Cadastro
(botões "Cliente/Cilindro" e "Cilindro/Nº Série"), não telas próprias — ver
PENDENCIAS.md > "Cilindros"."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import cilindro_cliente_service, cilindro_serie_service, cilindro_service, log_auditoria_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class CilindroDados(BaseModel):
    codigo: str = ""
    capacidade: int = 0
    pressao: int = 0
    padrao: str = ""
    descricao: str = ""
    qtd_produto: float = 1
    un_qtd_produto: str = "M3"
    un_cp: str = "LT"
    fator: float = 1
    peso_liq: float = 0
    peso_bruto: float = 0
    preco_venda: float = 0
    preco_custo: float = 0
    preco_locacao: float = 0
    prazo_revisao: int = 3
    situacao: str = "A"
    E_CILINDRO: bool = True


class CilindroSaveRequest(AuditFields):
    servidor: str
    banco: str
    cod: Optional[int] = None
    dados: CilindroDados


class CilindroDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/cilindros")
async def list_cilindros(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20):
    return await cilindro_service.list_cilindros(servidor, banco, search, page, size)


@router.get("/cilindros/produto/{codigo_fab}")
async def find_produto_cilindro(codigo_fab: str, servidor: str, banco: str):
    return await cilindro_service.find_produto_por_codigo_fab(servidor, banco, codigo_fab)


@router.get("/cilindros/{cod}")
async def get_cilindro(cod: int, servidor: str, banco: str):
    return await cilindro_service.get_cilindro(servidor, banco, cod)


@router.post("/cilindros")
async def save_cilindro(req: CilindroSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await cilindro_service.save_cilindro(req.servidor, req.banco, req.cod, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CILINDRO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=str(result.get("cod")),
            descricao=f"Cilindro {req.dados.codigo} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cilindros/{cod}/excluir")
async def delete_cilindro(cod: int, req: CilindroDeleteRequest, request: Request):
    result = await cilindro_service.delete_cilindro(req.servidor, req.banco, cod)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CILINDRO", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(cod),
            descricao=f"Cilindro {cod} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ============================================================
# Clientes x Cilindro (popup "Cliente/Cilindro" da tela de Cadastro)
# ============================================================
class VinculoSaveRequest(AuditFields):
    servidor: str
    banco: str
    cliente: int
    cilindro: int


class VinculoDeleteRequest(AuditFields):
    servidor: str
    banco: str
    cliente: int


@router.get("/cilindro-cliente")
async def list_cilindro_cliente(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20):
    return await cilindro_cliente_service.list_vinculos(servidor, banco, search, page, size)


@router.post("/cilindro-cliente")
async def save_cilindro_cliente(req: VinculoSaveRequest, request: Request):
    result = await cilindro_cliente_service.save_vinculo(req.servidor, req.banco, req.cliente, req.cilindro)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CIL_CLIENTE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=f"{req.cliente}/{result.get('cilindro')}",
            descricao=f"Vínculo cliente {req.cliente} x cilindro {result.get('cilindro')} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cilindro-cliente/{cilindro}/excluir")
async def delete_cilindro_cliente(cilindro: int, req: VinculoDeleteRequest, request: Request):
    result = await cilindro_cliente_service.delete_vinculo(req.servidor, req.banco, req.cliente, cilindro)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CIL_CLIENTE", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=f"{req.cliente}/{cilindro}",
            descricao=f"Vínculo cliente {req.cliente} x cilindro {cilindro} excluído.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


# ============================================================
# Cilindro/Nº Série (popup "Cilindro/Nº Série" da tela de Cadastro)
# ============================================================
class CilindroSerieDados(BaseModel):
    numero_de_serie: str = ""
    cilindro: int = 0
    destino: int = 0
    tipo_destino: str = "C"  # "C" Cliente | "F" Fornecedor
    data_compra: Optional[str] = None
    nf_compra: Optional[int] = None
    fornecedor: Optional[int] = None
    fabricacao: Optional[str] = None
    entrada: Optional[str] = None
    saida: Optional[str] = None
    revisao: Optional[str] = None
    carga: str = "CHEIO"  # "CHEIO" | "VAZIO"
    situacao: str = "A"


class CilindroSerieSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    dados: CilindroSerieDados


class CilindroSerieDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/cilindro-serie")
async def list_cilindro_serie(servidor: str, banco: str, search: str = "", page: int = 1, size: int = 20):
    return await cilindro_serie_service.list_serie(servidor, banco, search, page, size)


@router.get("/cilindro-serie/{codigo}")
async def get_cilindro_serie(codigo: int, servidor: str, banco: str):
    return await cilindro_serie_service.get_serie(servidor, banco, codigo)


@router.post("/cilindro-serie")
async def save_cilindro_serie(req: CilindroSerieSaveRequest, request: Request):
    dados = req.dados.model_dump()
    result = await cilindro_serie_service.save_serie(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CILINDRO_SERIE", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(result.get("codigo")),
            descricao=f"Cilindro/Nº Série {req.dados.numero_de_serie} gravado.",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/cilindro-serie/{codigo}/excluir")
async def delete_cilindro_serie(codigo: int, req: CilindroSerieDeleteRequest, request: Request):
    result = await cilindro_serie_service.delete_serie(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="CILINDRO_SERIE", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=str(codigo),
            descricao=f"Cilindro/Nº Série {codigo} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
