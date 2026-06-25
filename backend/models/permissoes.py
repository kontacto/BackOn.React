"""Modelos do módulo de Permissões (tabela SQL `permissoes`, sistema=50)."""
from typing import List

from pydantic import BaseModel


class PermItem(BaseModel):
    """Um nó de permissão selecionado (marcado) na árvore."""
    tipo: str            # MENU | TELA | BOTAO
    tela: str            # chave da tela/menu (ex.: CLIENTE)
    comando: str = ""    # chave da ação/botão (ex.: GRAVAR); vazio p/ menu/tela
    nome: str = ""       # rótulo amigável
    formulario: str = ""


class SalvarPermissoesRequest(BaseModel):
    servidor: str
    banco: str
    classe: int
    itens: List[PermItem] = []
