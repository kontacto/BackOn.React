"""Models do Recebimento de Mercadoria — ver
`services/recebimento_service.py` pro racional completo."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class NovoRecebimentoRequest(BaseModel):
    servidor: str
    banco: str
    classe: Optional[int] = None
    master: Optional[bool] = False


class SalvarCabecalhoRecebimentoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    dados: dict


class SalvarItensRecebimentoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    itens: list[dict]


class SalvarVencimentosRecebimentoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    vencimentos: list[dict]


class CriticarRecebimentoRequest(BaseModel):
    servidor: str
    banco: str
    codigo: int
    classe: Optional[int] = None
    master: Optional[bool] = False


class AtualizarRecebimentoRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int
    master: Optional[bool] = False


class ImportarXmlRecebimentoRequest(BaseModel):
    """Corpo do XML vai como texto (base64 decodificado no frontend antes
    de enviar, ou texto puro — decisão do frontend) — evita multipart só
    pra um arquivo de texto pequeno, mesmo padrão simples já usado por
    outros uploads de texto neste projeto."""
    servidor: str
    banco: str
    codigo: int
    conteudo_xml: str
    classe: Optional[int] = None
    master: Optional[bool] = False
