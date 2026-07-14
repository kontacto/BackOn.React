"""Constantes compartilhadas entre serviços."""

# Rótulos de situação do pedido_venda.
SITUACAO_LABEL = {"A": "Aberto", "F": "Fechado", "C": "Cancelado", "PG": "Faturado"}

# Mesma informação, mantida com a ordem usada nos relatórios.
SIT_LABELS = {"A": "Aberto", "F": "Fechado", "PG": "Faturado", "C": "Cancelado"}

# Rótulos de STATUS_CLIENTE (tabela dedicada — não confundir com cliente.situacao A/I).
# Qualquer status diferente de 'A' bloqueia nova movimentação (Pedido/O.S.).
STATUS_CLIENTE_LABEL = {
    "A": "Ativo",
    "C": "Cancelado",
    "D": "Desativado",
    "E": "Excluido",
    "F": "Fechado",
    "R": "Reservado",
    "S": "Suspenso",
}
