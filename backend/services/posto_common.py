"""Helpers compartilhados por todos os services do módulo Posto de
Combustível (Metas, Ilhas, Combustíveis, Tanques, Bombas etc.) — reforço
de módulo aplicado no backend (não só escondido na navegação do
frontend), mesmo padrão de `pedido_common._modulo_servicos_ativo`.
"""
from datetime import date
from typing import Optional

MODULO_DESATIVADO_MSG = (
    "Módulo Posto de Combustível está desativado em Configurações do Sistema > "
    "Módulos e Recursos. Ative-o para cadastrar, consultar ou movimentar."
)


def modulo_posto_ativo(cur) -> bool:
    cur.execute("SELECT TOP 1 Posto FROM controle_configuracao")
    row = cur.fetchone()
    val = row.get("Posto") if isinstance(row, dict) else (row[0] if row else None)
    return bool(val)


def data_movimento(cur) -> Optional[date]:
    """"DATESIST" do legado — a "data de movimento" corrente do sistema
    (`controle.data_movimento`), usada pra validar lançamentos nas telas do
    cluster de Turno (Mov. Encerrantes, Fechamento/Reabertura de Turno,
    Aferições). No VB6 isso era uma variável global (`DATESIST`), setada
    uma vez na inicialização do app e mantida em memória — funcionava
    porque cada instalação do VB6 rodava um processo próprio, conectado a
    um único banco.

    Na arquitetura nova o backend é stateless e atende potencialmente
    várias empresas (servidor+banco) na mesma instância — uma variável
    global de processo vazaria a data de uma empresa pra outra. Por isso
    NÃO existe (e não deve existir) um `DATESIST` global aqui: esta função
    só faz um SELECT simples, escopado à conexão/cursor já aberto pro
    servidor+banco da requisição corrente — mesmo padrão já usado pra
    `controle.qtd_turnos` em `ilha_service.py`. Cada service que precisa da
    "data de movimento" chama esta função dentro da própria transação, não
    guarda o valor em memória entre requisições.
    """
    cur.execute("SELECT TOP 1 data_movimento FROM controle")
    row = cur.fetchone()
    val = row.get("data_movimento") if isinstance(row, dict) else (row[0] if row else None)
    return val


def turno_movimento(cur) -> int:
    """Qual turno está aberto agora (`controle.turno_movimento`) — mesmo
    padrão de `data_movimento` acima: campo simples da linha única de
    `controle`, lido fresco por requisição, nunca cacheado como global.
    Usado por Fechamento/Reabertura de Turno."""
    cur.execute("SELECT TOP 1 turno_movimento FROM controle")
    row = cur.fetchone()
    val = row.get("turno_movimento") if isinstance(row, dict) else (row[0] if row else None)
    return int(val or 1)


def qtd_turnos(cur) -> int:
    cur.execute("SELECT TOP 1 qtd_turnos FROM controle")
    row = cur.fetchone()
    val = row.get("qtd_turnos") if isinstance(row, dict) else (row[0] if row else None)
    return int(val or 0) or 1
