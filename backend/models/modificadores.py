"""Modificadores (Cadastros > Tabelas Auxiliares) — cadastro genuinamente
novo, sem equivalente no sistema legado VB6. Categorias de modificador
(ex.: "Ponto da Carne") associáveis a Produto e/ou Serviço; cada categoria
tem uma condição (Obrigatório/Opcional) e um modo de seleção (um único ou
vários modificadores); cada modificador dentro da categoria pode lançar um
acréscimo e/ou desconto (valor fixo em R$) no item da pré-venda. Ver
PENDENCIAS.md > "Modificadores" pro desenho completo."""
from typing import Literal, Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ModificadorItem(BaseModel):
    codigo: Optional[int] = None  # None = novo, ainda não gravado
    nome: str
    acrescimo: float = 0
    desconto: float = 0
    situacao: str = "A"  # "A" Ativo / "D" Desativado


class ItemAssociado(BaseModel):
    tipo: Literal["P", "S"]  # P = Produto (pecas), S = Serviço
    codigo: str


class ModificadorCategoriaSaveRequest(AuditFields):
    servidor: str
    banco: str
    codigo: Optional[int] = None  # None = nova categoria
    nome: str
    obrigatorio: bool = True
    selecao_multipla: bool = False
    modificadores: list[ModificadorItem] = []
    itens_associados: list[ItemAssociado] = []


class ModificadorCategoriaDeleteRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int


class AssociarItemCategoriasRequest(BaseModel):
    servidor: str
    banco: str
    categorias: list[int] = []
