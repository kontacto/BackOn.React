"""Modelos Pydantic (request/response) de toda a API Back-On."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class LoginRequest(BaseModel):
    empresa: str
    servidor: str
    banco: str
    usuario: str
    senha: str
    timeout: Optional[int] = 8


class LoginResponse(BaseModel):
    success: bool
    message: str
    empresa: Optional[str] = None
    server: Optional[str] = None
    database: Optional[str] = None
    usuario: Optional[dict] = None
    funcionario: Optional[dict] = None
    # Diagnóstico de erro
    error_step: Optional[str] = None          # connect | query_usuarios | query_funcionarios
    error_line: Optional[str] = None          # arquivo:linha
    error_code_line: Optional[str] = None     # trecho de código que falhou
    error_query: Optional[str] = None         # SQL executado (parâmetros omitidos)
    attempted: Optional[dict] = None          # dados da conexão tentada


class ClientesRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    page: int = 1
    size: int = 20


class PedidosListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    situacao: Optional[str] = ""  # vazio = todos
    vendedor: Optional[str] = None  # None/"all" = todos; número = filtra por vendedor
    data_ini: Optional[str] = None  # ISO YYYY-MM-DD
    data_fim: Optional[str] = None  # ISO YYYY-MM-DD
    page: int = 1
    size: int = 20


class PedidoSaveRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int                       # cliente.codigo
    vendedor: int                      # funcionarios.codigo_int
    validade: Optional[str] = None     # ISO date YYYY-MM-DD
    obs: Optional[str] = ""
    area_atuacao: Optional[int] = None  # area_atuacao.area (FK)


class ItemSaveRequest(BaseModel):
    servidor: str
    banco: str
    produto: Optional[str] = None          # obrigatório no create
    qtd: float = 1
    valor_unitario: Optional[float] = None  # se None, usa preço padrão do produto
    complemento: Optional[str] = ""
    desconto: Optional[float] = 0          # desconto UNITÁRIO em R$
    desconto_pct: Optional[float] = 0      # % informado (0 se foi em R$) — só para o log
    acrescimo: Optional[float] = 0         # acréscimo UNITÁRIO em R$
    usuario_codigo: Optional[int] = -2     # -2 = KONTACTO (master)
    funcao: Optional[int] = None           # 1=gerente,2=supervisor,3=vendedor (p/ validar limite)


class OSListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    situacao: Optional[str] = ""  # vazio = todas
    data_ini: Optional[str] = None  # ISO YYYY-MM-DD
    data_fim: Optional[str] = None  # ISO YYYY-MM-DD
    page: int = 1
    size: int = 20


class OSSaveRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int                          # cliente.codigo
    area_atuacao: Optional[int] = None    # area_atuacao.area (FK)
    descricao_cliente: Optional[str] = ""  # relato do cliente
    obs: Optional[str] = ""


class OSItemSaveRequest(BaseModel):
    servidor: str
    banco: str
    produto: Optional[str] = None          # obrigatório no create (pecas.codigo_int / servicos.codigo)
    qtd: float = 1
    valor_unitario: Optional[float] = None  # se None, usa preço padrão do produto
    complemento: Optional[str] = ""
    desconto: Optional[float] = 0          # desconto UNITÁRIO em R$
    desconto_pct: Optional[float] = 0      # % informado (só p/ log)
    acrescimo: Optional[float] = 0         # acréscimo UNITÁRIO em R$
    vendedor: Optional[int] = None         # funcionarios.codigo_int — POR ITEM
    executor: Optional[int] = None         # funcionarios.codigo_int — POR ITEM
    usuario_codigo: Optional[int] = -2
    funcao: Optional[int] = None


class DescontoGeralRequest(BaseModel):
    servidor: str
    banco: str
    valor: float = 0               # valor TOTAL do desconto geral em R$ (0 = remover)
    usuario_codigo: Optional[int] = -2
    funcao: Optional[int] = 1       # 1=gerente, 2=supervisor, 3=vendedor


class TelefoneInput(BaseModel):
    ddd: Optional[str] = ""
    tel: Optional[str] = ""
    descricao: Optional[str] = ""


class EnderecoInput(BaseModel):
    tipo: int = 0  # 0=Comercial, 1=Cobrança, 2=Entrega
    cep: Optional[str] = ""
    endereco: Optional[str] = ""
    numero: Optional[int] = None
    complemento: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    uf: Optional[str] = ""


class ClienteSaveRequest(BaseModel):
    servidor: str
    banco: str
    cgc_cpf: Optional[str] = ""
    nome: str
    e_mail: Optional[str] = ""
    inscre: Optional[str] = ""
    tipo: Optional[str] = ""           # FK string para tipo_cliente.codigo
    aceita_email: bool = False
    vendedor: Optional[int] = None     # funcionarios.codigo_int do usuário logado
    usuario_cadastro: Optional[int] = None
    usuario_alteracao: Optional[int] = None


class ClienteCreateRequest(ClienteSaveRequest):
    endereco: Optional[EnderecoInput] = None
    telefones: List[TelefoneInput] = Field(default_factory=list)
