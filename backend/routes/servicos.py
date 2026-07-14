"""Rotas de Manutenção de Serviços — ver services/servicos_service.py para
o desenho completo (schema real, campos fora de escopo, guards)."""
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from models.log_auditoria import AuditFields
from services import log_auditoria_service, servicos_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


class ServicoDados(BaseModel):
    descricao: str
    descricao_nf: str = ""
    codigo_especialidade: Optional[int] = None
    tipo: int = 0
    situacao: str = "A"
    valor_hora: float = 0
    custo_hora: float = 0
    preco_variado: bool = False
    prazo_garantia: int = 0
    tipo_garantia: int = 0
    nivel1: str = ""
    nivel2: str = ""
    nivel3: str = ""
    nivel4: str = ""
    nivel5: str = ""
    cod_lista_servico: str = ""
    cod_servico_municipio: str = ""
    cod_icms: str = ""
    indop_nfse: str = ""
    codigo_mercosul: str = ""
    classificacao_fiscal: str = ""
    construcao_civil: bool = False
    tributacao_pis: Optional[str] = None
    perc_valor_pis: float = 0
    tributacao_cofins: Optional[str] = None
    perc_valor_cofins: float = 0
    aceita_desconto: bool = False
    desc_g: float = 0
    desc_s: float = 0
    desc_v: float = 0
    paga_comissao: bool = False
    comissao: float = 0
    comissao_e: float = 0
    comissao_a: float = 0
    valor_comissao: float = 0
    valor_comissao_e: float = 0
    valor_comissao_a: float = 0
    perc_desc_base_comissao: float = 0
    perc_desc_base_comissao_e: float = 0
    perc_desc_base_comissao_a: float = 0


class ServicoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: str
    dados: ServicoDados


class ServicoDeleteRequest(AuditFields):
    servidor: str
    banco: str


@router.get("/servicos")
async def list_servicos(servidor: str, banco: str):
    return await servicos_service.list_servicos(servidor, banco)


@router.get("/servicos/{codigo}")
async def get_servico(codigo: str, servidor: str, banco: str):
    return await servicos_service.get_servico(servidor, banco, codigo)


@router.post("/servicos")
async def save_servico(req: ServicoSaveRequest, request: Request):
    result = await servicos_service.save_servico(req.servidor, req.banco, req.codigo, req.dados.model_dump())
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO", comando="GRAVAR",
            usuario=req.usuario_alteracao, classe=req.classe,
            referencia=result.get("codigo"),
            descricao=f"Serviço {result.get('codigo')} gravado ({req.dados.descricao}).",
            ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result


@router.post("/servicos/{codigo}/excluir")
async def delete_servico(codigo: str, req: ServicoDeleteRequest, request: Request):
    result = await servicos_service.delete_servico(req.servidor, req.banco, codigo)
    if result.get("success"):
        await log_auditoria_service.registrar_log(
            req.servidor, req.banco, tela="SERVICO", comando="EXCLUIR",
            usuario=req.usuario_alteracao, classe=req.classe, referencia=codigo,
            descricao=f"Serviço {codigo} excluído.", ip_origem=_ip(request), plataforma=req.plataforma,
        )
    return result
