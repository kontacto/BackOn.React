"""Gestor de Comandas / Alterar Comandas — migração de `FrmConCupom.frm`
("Consulta de Vendas") e `FrmAltComNV.frm` ("Alteração de Vendas"). Ver
`services/comanda_service.py` para o racional completo (rastreamento
campo-a-campo) e PENDENCIAS.md > "Gestor de Comandas" para o que ficou de
fora desta rodada."""
from typing import Optional

from pydantic import BaseModel

from models.log_auditoria import AuditFields


class ListarComandasRequest(BaseModel):
    servidor: str
    banco: str
    data_ini: Optional[str] = None
    data_fim: Optional[str] = None
    comanda: Optional[int] = None
    cliente: Optional[str] = None  # código, CGC ou nome — resolvido no service
    cupom: Optional[int] = None
    nfce: Optional[int] = None
    nf: Optional[int] = None
    pedido: Optional[int] = None
    os: Optional[int] = None
    atendente: Optional[int] = None
    atendente_dav: bool = False  # filtra por atendente_dav em vez de atendente
    forma_pagamento: Optional[str] = None
    produto: Optional[str] = None
    area_atuacao: Optional[int] = None
    valor_de: Optional[float] = None
    valor_ate: Optional[float] = None
    com_nota: bool = True
    sem_nota: bool = True
    ordenar_por: str = "venda"  # "venda" ou "cliente"


class ComandaGravarRequest(AuditFields):
    servidor: str
    banco: str
    area_atuacao: Optional[int] = None
    paga_comissao: bool = True
    atendente: Optional[int] = None
    atendente_dav: Optional[int] = None
    cliente: Optional[int] = None
    faturar_para: Optional[int] = None
    master: Optional[bool] = False


class ComandaAlterarVendedorItemRequest(AuditFields):
    servidor: str
    banco: str
    id_mov: int
    vendedor: int
    aplicar_aos_demais_itens_do_vendedor_anterior: bool = False
    master: Optional[bool] = False


class ComandaAlterarFormaPagamentoRequest(AuditFields):
    servidor: str
    banco: str
    sequencia: int  # sequencia do lançamento em comanda_cartao/comanda_debito
    tipo: str  # "CC" (cartão) ou "CD" (débito) — mesma modalidade só
    forma_pag_nova: str
    master: Optional[bool] = False


class ComandaCancelarRequest(AuditFields):
    servidor: str
    banco: str
    motivo: str
    master: Optional[bool] = False


class ComandaAddNumSerieRequest(AuditFields):
    servidor: str
    banco: str
    codigo: int  # pecas_num_serie.codigo
    master: Optional[bool] = False


class EmitirNfceRequest(AuditFields):
    servidor: str
    banco: str
    master: Optional[bool] = False


class EmitirNfseRequest(AuditFields):
    servidor: str
    banco: str
    master: Optional[bool] = False
