"""Registro CENTRAL e único de toda a checagem/aplicação de schema pendente
que este backend precisa em cada banco de cliente (colunas/tabelas novas
introduzidas por esta migração, além do schema original herdado do VB6).

Ver CLAUDE.md > "Cada app precisa se auto-atualizar no banco" — o
problema real que isso resolve: o VB6 legado depende de alguém rodar um
script de atualização de banco manualmente a cada release, o que falha
com frequência (script esquecido, aplicado fora de ordem, cliente
atrasado várias versões), deixando bancos de clientes diferentes com
colunas/tabelas divergentes entre si.

**Por que este módulo existe além dos `_ensure_*` já espalhados pelos
services** (`pedido_common.py`, `produto_completo_service.py`,
`checkout_service.py`, etc. — cada um só roda quando aquele service
específico é chamado): isso é uma correção PONTUAL, não INTEGRAL — pedido
explícito do usuário, 2026-08-11 ("a persistência não pode ser de forma
pontual. tem que ser integral"). Um cliente cuja instalação nunca
exercitou, digamos, o módulo de Contratos teria a coluna
`hora_inclusao_item` faltando indefinidamente, mesmo que o resto do
sistema já estivesse atualizado — cada `_ensure_*` só "remenda" o pedaço
do schema que a PRÓPRIA feature que o chama precisa, não o todo.

Este módulo resolve isso reunindo TODOS os `_ensure_*` de schema (DDL —
`ALTER TABLE`/`CREATE TABLE`) já existentes num único ponto, aplicado de
uma vez (`ensure_all_schema`) na PRIMEIRA conexão de cada
`servidor`+`banco` por execução do processo (cache em memória,
`_SCHEMA_JA_GARANTIDO` — evita repetir ~23 checagens `EXISTS` em toda
requisição, já que elas são idempotentes e só precisam rodar uma vez por
banco por processo). Chamado a partir de `db.connection._open_conn` — o
único ponto de abertura de conexão usado por todo o resto do backend — via
import tardio (dentro da função, não no topo do arquivo) para evitar
import circular (`db.connection` é importado por todos os services abaixo,
então um import no topo deste módulo criaria um ciclo).

Os `_ensure_*` originais NÃO foram removidos dos seus services de
origem — continuam lá como rede de segurança adicional (idempotentes e
baratos, não fazem mal nenhum rodar de novo) e para os poucos call sites
que já dependiam deles diretamente antes deste módulo existir. A garantia
de cobertura INTEGRAL agora vem daqui, não da esperança de que cada
service individual seja chamado em algum momento.

**Exclusão deliberada**: `contratos_service._ensure_forma_pag_contrato_sync`
NÃO está aqui — não é uma checagem de SCHEMA (não faz ALTER/CREATE), é
"garante uma LINHA de dado de negócio" (a forma de pagamento "CONTRATO"),
categoria diferente, e retorna um valor usado pelo chamador (não se
encaixa no formato void/fire-and-forget dos demais).

**Ao adicionar um `_ensure_*` novo em qualquer service**: registrar aqui
também, na lista `_MIGRACOES` — é isso que torna a cobertura integral em
vez de pontual de novo.
"""
import logging
from typing import Callable

from services.balanca_service import _ensure_balancas_table
from services.checkout_service import _ensure_cartao_presente_resgate_table
from services.controle_config_service import _ensure_balanca_cols
from services.cotacao_compra_service import _ensure_tables as _ensure_tables_cotacao
from services.etiqueta_produto_service import _ensure_modelo_etiqueta_table
from services.gestao_compras_service import _ensure_alertas_estoque_cache_table
from services.impressao_service import _ensure_impressao_fila_table
from services.inventario_service import _ensure_usuario_digitacao_col, _ensure_automatico_col
from services.ia_config_service import _ensure_anthropic_api_key_col
from services.layout_service import _ensure_layout_paginas_col
from services.log_auditoria_service import _ensure_log_auditoria_table
from services.modificadores_service import _ensure_tables as _ensure_tables_modificadores
from services.os_completo_service import _ensure_os_auxiliar_tecnico_col
from services.os_equipamento_service import _ensure_os_equipamento_table
from services.os_service import _ensure_os_checkin_cols
from services.pedido_common import (
    _ensure_hora_inclusao_item_col,
    _ensure_qtd_pessoas_col,
    _ensure_agenda_forma_pag_tables,
    _ensure_os_doc_origem_cols,
    _ensure_os_forma_pagamento_garantia_col,
    _ensure_osrevisao_table,
    _ensure_agenda_os_table,
    _ensure_os_produto_agenda_cols,
)
from services.produto_completo_service import _ensure_promocao_periodo_cols, _ensure_web_dias_semana_table
from services.projetos_service import _ensure_projetos_tables
from services.tabelas_aux_service import _ensure_nfse_indop_sync

# Toda checagem de schema conhecida do sistema — cada entrada é chamada
# com o cursor já aberto. Ordem não importa (cada uma mexe numa tabela/
# coluna independente das outras) — mas se uma nova migração depender de
# outra já ter rodado antes, colocar na ordem certa aqui.
_MIGRACOES: list[Callable[[object], None]] = [
    _ensure_balancas_table,
    _ensure_cartao_presente_resgate_table,
    _ensure_balanca_cols,
    _ensure_tables_cotacao,
    _ensure_modelo_etiqueta_table,
    _ensure_alertas_estoque_cache_table,
    _ensure_impressao_fila_table,
    _ensure_usuario_digitacao_col,
    _ensure_automatico_col,
    _ensure_log_auditoria_table,
    _ensure_layout_paginas_col,
    _ensure_anthropic_api_key_col,
    _ensure_tables_modificadores,
    _ensure_hora_inclusao_item_col,
    _ensure_qtd_pessoas_col,
    _ensure_agenda_forma_pag_tables,
    _ensure_os_doc_origem_cols,
    _ensure_os_forma_pagamento_garantia_col,
    _ensure_osrevisao_table,
    _ensure_agenda_os_table,
    _ensure_os_produto_agenda_cols,
    _ensure_promocao_periodo_cols,
    _ensure_web_dias_semana_table,
    _ensure_projetos_tables,
    _ensure_nfse_indop_sync,
    _ensure_os_equipamento_table,
    _ensure_os_checkin_cols,
    _ensure_os_auxiliar_tecnico_col,
]

# (servidor, banco) já garantidos NESTA execução do processo — evita
# repetir ~23 checagens EXISTS em toda requisição. Reinicia quando o
# processo reinicia (supervisor `start-backend.ps1` já reinicia sozinho
# se o processo cair, então isso nunca fica "preso" desatualizado por
# muito tempo caso um schema mude enquanto o processo está de pé).
_SCHEMA_JA_GARANTIDO: set[tuple[str, str]] = set()


def ensure_all_schema(cur, servidor: str, banco: str) -> None:
    """Aplica TODAS as migrações de schema pendentes pra este
    `servidor`+`banco`, de uma vez — chamado a partir de `_open_conn`.
    Idempotente e cacheado por processo (ver `_SCHEMA_JA_GARANTIDO`).

    Cada migração roda isolada (try/except própria) — uma falhar (bug
    pontual numa migração específica, coluna com nome conflitante nesse
    banco em particular, etc.) NUNCA pode impedir as outras 22 de rodarem;
    isso destruiria exatamente a garantia "integral" que este módulo existe
    pra dar. Falhas são logadas, não silenciosas."""
    chave = ((servidor or "").strip().upper(), (banco or "").strip().upper())
    if chave in _SCHEMA_JA_GARANTIDO:
        return
    for migracao in _MIGRACOES:
        try:
            migracao(cur)
        except Exception:
            logging.getLogger(__name__).warning(
                "Migração de schema '%s' falhou em %s/%s",
                getattr(migracao, "__name__", migracao), servidor, banco, exc_info=True,
            )
    _SCHEMA_JA_GARANTIDO.add(chave)
