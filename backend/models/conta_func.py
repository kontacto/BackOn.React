"""Financeiro > Fluxo de Caixa > Contas x Funcionário (`FrmConFunc.frm`,
"Acesso das Contas Por Funcionários...") — configura quais `Contas`
(caixa/banco) cada funcionário pode visualizar. Ver
services/conta_func_service.py e PENDENCIAS.md > "Contas x Funcionário"."""
from typing import List

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ContaFuncSaveRequest(AuditFields):
    servidor: str
    banco: str
    funcionario: int  # funcionarios.codigo_int
    contas: List[int]  # subconjunto de Contas.codigo com acesso liberado (replace-all)
