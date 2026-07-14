"""Rotas de Veículos (tabela `veiculos_transp` + N:N `veiculos_rota`).

Tela de Cadastros (não Tabela Auxiliar) — liberada pela flag de módulo
`Cilindro` (`controle_configuracao.Cilindro`) OU para o usuário master (regra
aplicada no frontend: `app/veiculos.tsx` / hub `app/(tabs)/cadastros.tsx`).

Gravar/Excluir e vínculos de Rota são registrados em `log_auditoria`, mesmo
padrão das demais telas (busca "antes" pelo PK antes de chamar o service, que
faz o UPDATE/DELETE às cegas).
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Request

from models.log_auditoria import AuditFields
from services import log_auditoria_service, veiculos_service

router = APIRouter()


def _ip(request: Request) -> Optional[str]:
    return request.client.host if request.client else None


async def _log(req, request: Request, *, comando: str, referencia, descricao: str, campos=None):
    await log_auditoria_service.registrar_log(
        req.servidor, req.banco, tela="VEICULOS", comando=comando,
        usuario=req.usuario_alteracao, classe=req.classe,
        referencia=str(referencia) if referencia is not None else None,
        descricao=descricao, campos_alterados=campos or None,
        ip_origem=_ip(request), plataforma=req.plataforma,
    )


class VeiculoSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None
    placa: str
    descricao: Optional[str] = ""
    motorista: Optional[int] = None
    auxiliar: Optional[int] = None
    hodometro: Optional[float] = None
    km: Optional[float] = None
    data_compra: Optional[str] = None
    valor_compra: Optional[float] = None
    peso_max: Optional[int] = None
    volume_max: Optional[int] = None
    peso_min: Optional[int] = None
    volume_min: Optional[int] = None
    marca: Optional[str] = None
    modelo: Optional[str] = None
    cor: Optional[str] = None
    motor: Optional[str] = ""
    renavam: Optional[str] = ""
    chassi: Optional[str] = ""
    combustivel: Optional[str] = None
    ano_fab: Optional[int] = None
    ano_mod: Optional[int] = None
    tipo: Optional[str] = None
    situacao: Optional[str] = ""
    doc_proprietario: Optional[str] = ""
    rntrc_proprietario: Optional[str] = ""
    nome_proprietario: Optional[str] = ""
    ie_proprietario: Optional[str] = ""
    uf_proprietario: Optional[str] = ""
    tpRod: Optional[str] = ""
    tpCar: Optional[str] = ""
    UF: Optional[str] = ""


class DeleteRequest(AuditFields):
    servidor: str
    banco: str


class RotaVinculoRequest(AuditFields):
    servidor: str
    banco: str
    rota: int


CAMPOS_LOG = list(veiculos_service.CAMPOS)

# Campos onde o service aplica fallback/coerção (ver `_save_veiculo_sync`) —
# o diff de auditoria precisa espelhar o MESMO valor que efetivamente vai pro
# banco, não o `req.model_dump()` cru, senão um campo omitido no request (None)
# aparece como "alterado" mesmo quando o service já ia gravar o mesmo default
# que já estava lá (mesma lição já documentada pra O.S./Pedidos: campo com
# fallback no service precisa de helper "depois" próprio).
_ZERO_DEFAULT = {"hodometro", "km", "valor_compra", "peso_max", "volume_max", "peso_min", "volume_min"}


def _depois_veiculo(req: VeiculoSaveRequest) -> dict:
    dump = req.model_dump()
    ano_atual = date.today().year
    depois = {}
    for c in CAMPOS_LOG:
        v = dump.get(c)
        if c in _ZERO_DEFAULT:
            depois[c] = v or 0
        elif c in ("ano_fab", "ano_mod"):
            depois[c] = v or ano_atual
        elif c == "situacao":
            depois[c] = (v or "").strip().upper() or "A"
        elif c == "placa":
            depois[c] = (v or "").strip().upper()
        elif c in ("combustivel", "tipo"):
            depois[c] = str(v) if v is not None else v
        else:
            depois[c] = v
    return depois


@router.get("/veiculos")
async def list_veiculos(servidor: str, banco: str, search: str = ""):
    return await veiculos_service.list_veiculos(servidor, banco, search)


@router.get("/veiculos/motoristas")
async def list_motoristas(servidor: str, banco: str):
    return await veiculos_service.list_motoristas(servidor, banco)


@router.get("/veiculos/auxiliares")
async def list_auxiliares(servidor: str, banco: str):
    return await veiculos_service.list_auxiliares(servidor, banco)


@router.get("/veiculos/{codigo}")
async def get_veiculo(codigo: int, servidor: str, banco: str):
    return await veiculos_service.get_veiculo(servidor, banco, codigo)


@router.post("/veiculos")
async def save_veiculo(req: VeiculoSaveRequest, request: Request):
    antes = None
    if req.codigo:
        antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "veiculos_transp", "codigo", req.codigo)
        if antes and antes.get("data_compra") is not None:
            # `get_row_by_pk` traz a coluna `date` crua (objeto `datetime.date`);
            # normaliza pra string ISO aqui, senão o diff compara date(...) contra
            # a string ISO do request e sempre acusa mudança, mesmo sem alteração real.
            antes = {**antes, "data_compra": antes["data_compra"].isoformat()}
    dados = req.model_dump()
    result = await veiculos_service.save_veiculo(req.servidor, req.banco, req.codigo, dados)
    if result.get("success"):
        codigo = result.get("codigo", req.codigo)
        campos = log_auditoria_service.diff_campos(antes, _depois_veiculo(req), CAMPOS_LOG)
        await _log(req, request, comando="GRAVAR", referencia=req.placa, descricao=f"Veículo '{req.placa}' gravado", campos=campos)
    return result


@router.post("/veiculos/{codigo}/excluir")
async def delete_veiculo(codigo: int, req: DeleteRequest, request: Request):
    antes = await log_auditoria_service.get_row_by_pk(req.servidor, req.banco, "veiculos_transp", "codigo", codigo)
    result = await veiculos_service.delete_veiculo(req.servidor, req.banco, codigo)
    if result.get("success"):
        campos = log_auditoria_service.snapshot_campos(antes, CAMPOS_LOG)
        referencia = (antes or {}).get("placa", codigo)
        await _log(req, request, comando="EXCLUIR", referencia=referencia, descricao=f"Veículo '{referencia}' excluído", campos=campos)
    return result


@router.post("/veiculos/{codigo}/rotas")
async def add_veiculo_rota(codigo: int, req: RotaVinculoRequest, request: Request):
    result = await veiculos_service.add_veiculo_rota(req.servidor, req.banco, codigo, req.rota)
    if result.get("success"):
        await _log(req, request, comando="VINCULOS", referencia=codigo, descricao=f"Rota {req.rota} vinculada ao veículo {codigo}")
    return result


@router.post("/veiculos/{codigo}/rotas/{rota}/excluir")
async def remove_veiculo_rota(codigo: int, rota: int, req: DeleteRequest, request: Request):
    result = await veiculos_service.remove_veiculo_rota(req.servidor, req.banco, codigo, rota)
    if result.get("success"):
        await _log(req, request, comando="VINCULOS", referencia=codigo, descricao=f"Rota {rota} removida do veículo {codigo}")
    return result
