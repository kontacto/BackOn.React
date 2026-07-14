"""Modelos do módulo de Permissões (tabela SQL `permissoes`, sistema=50)."""
from typing import List, Optional

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
    classe: int  # grupo ALVO sendo editado — não dá pra reusar AuditFields aqui
    # (mesma colisão de nomes documentada em routes/usuarios.py: "classe" já
    # significa outra coisa neste request). Só usuario_alteracao/plataforma
    # entram direto, pro log de auditoria.
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None
    itens: List[PermItem] = []
