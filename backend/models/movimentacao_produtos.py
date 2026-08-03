"""Movimentação de Produtos — lançamento manual avulso de entrada/saída de
estoque (tabela `movimentacao`, sempre `serie_nf='MV'` pra distinguir de
movimentações geradas por outras telas: 'CM' = comanda/Pedido Bar,
num_nf de Nota Fiscal, etc.). Legado: `frmEntPro.frm`."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class MovimentacaoProdutoIncluirRequest(AuditFields):
    servidor: str
    banco: str
    data: str  # yyyy-mm-dd
    tipo: str
    codigo_int: str
    qtd: float
    p_unit: float
    num_nf: Optional[int] = None


class MovimentacaoProdutoExcluirRequest(AuditFields):
    servidor: str
    banco: str
