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

from services.backup_sistema_service import _ensure_backup_sistema_table
from services.balanca_service import _ensure_balancas_table
from services.checkout_service import _ensure_cartao_presente_resgate_table
from services.comanda_service import _ensure_cancelamento_fiscal_cols
from services.controle_config_service import _ensure_balanca_cols
from services.contingencia_nfce_service import _ensure_contingencia_nfce_table
from services.contingencia_nfe_service import _ensure_contingencia_nfe_table
from services.cotacao_compra_service import _ensure_tables as _ensure_tables_cotacao
from services.etiqueta_produto_service import _ensure_modelo_etiqueta_table
from services.gestor_nfce_service import _ensure_inutilizacao_nfe_table
from services.gestao_compras_service import _ensure_alertas_estoque_cache_table
from services.impressao_service import _ensure_impressao_fila_table
from services.inventario_service import _ensure_usuario_digitacao_col, _ensure_automatico_col
from services.ia_config_service import _ensure_anthropic_api_key_col
from services.controle_sistema_service import _ensure_logo_empresa_cols
from services.bancos_service import _ensure_banco_logo_cols
from services.layout_service import _ensure_layout_paginas_col
from services.log_auditoria_service import _ensure_log_auditoria_table
from services.modificadores_service import _ensure_tables as _ensure_tables_modificadores
from services.os_completo_service import _ensure_os_auxiliar_tecnico_col, _ensure_os_codagenda_atendimento_col
from services.os_equipamento_service import _ensure_os_equipamento_table
from services.os_checklist_veiculo_service import _ensure_os_checklist_veiculo_table, _ensure_os_checklist_table
from services.os_service import _ensure_os_checkin_cols, _ensure_os_versao_atendimento_col
from services.nfe_avulsa_service import _ensure_nf_aux_paga_frete_col, _ensure_nf_aux_ids_devolucao_origem_col
from services.notas_fiscais_service import _ensure_n_fiscal_carta_correcao_table
from services.mdfe_service import _ensure_mdfe_tables
from services.recebimento_service import _ensure_nf_recebimento_gerado_col
from services.pedido_common import (
    _ensure_hora_inclusao_item_col,
    _ensure_qtd_pessoas_col,
    _ensure_agenda_forma_pag_tables,
    _ensure_os_doc_origem_cols,
    _ensure_os_forma_pagamento_garantia_col,
    _ensure_exige_chassi_os_col,
    _ensure_osrevisao_table,
    _ensure_agenda_os_table,
    _ensure_os_produto_agenda_cols,
)
from services.produto_completo_service import _ensure_promocao_periodo_cols, _ensure_web_dias_semana_table
from services.produto_imagem_service import _ensure_produto_imagem_table
from services.imagem_storage import _ensure_path_produto_imagem_col
from services.projetos_service import _ensure_projetos_tables
from services.servico_sistema_service import _ensure_servico_sistema_atualizacao_table
from services.tabelas_aux_service import _ensure_nfse_indop_sync

# Toda checagem de schema conhecida do sistema — cada entrada é chamada
# com o cursor já aberto. Ordem não importa (cada uma mexe numa tabela/
# coluna independente das outras) — mas se uma nova migração depender de
# outra já ter rodado antes, colocar na ordem certa aqui.
_MIGRACOES: list[Callable[[object], None]] = [
    _ensure_backup_sistema_table,
    _ensure_balancas_table,
    _ensure_cartao_presente_resgate_table,
    _ensure_contingencia_nfce_table,
    _ensure_contingencia_nfe_table,
    _ensure_inutilizacao_nfe_table,
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
    _ensure_exige_chassi_os_col,
    _ensure_osrevisao_table,
    _ensure_agenda_os_table,
    _ensure_os_produto_agenda_cols,
    _ensure_promocao_periodo_cols,
    _ensure_web_dias_semana_table,
    _ensure_projetos_tables,
    _ensure_nfse_indop_sync,
    _ensure_os_equipamento_table,
    _ensure_os_checklist_veiculo_table,
    _ensure_os_checklist_table,
    _ensure_os_checkin_cols,
    _ensure_os_auxiliar_tecnico_col,
    _ensure_os_codagenda_atendimento_col,
    _ensure_os_versao_atendimento_col,
    _ensure_nf_recebimento_gerado_col,
    _ensure_nf_aux_paga_frete_col,
    _ensure_nf_aux_ids_devolucao_origem_col,
    _ensure_n_fiscal_carta_correcao_table,
    _ensure_mdfe_tables,
    _ensure_cancelamento_fiscal_cols,
    _ensure_logo_empresa_cols,
    _ensure_banco_logo_cols,
    _ensure_produto_imagem_table,
    _ensure_path_produto_imagem_col,
    _ensure_servico_sistema_atualizacao_table,
]

# (servidor, banco) já garantidos NESTA execução do processo — evita
# repetir ~23 checagens EXISTS em toda requisição. Reinicia quando o
# processo reinicia (supervisor `start-backend.ps1` já reinicia sozinho
# se o processo cair, então isso nunca fica "preso" desatualizado por
# muito tempo caso um schema mude enquanto o processo está de pé).
_SCHEMA_JA_GARANTIDO: set[tuple[str, str]] = set()

# Cache próprio (não reaproveita `_SCHEMA_JA_GARANTIDO`) porque
# `ensure_auto_close_off` roda fora do lote de `_MIGRACOES` — ver
# docstring dela pro motivo (ALTER DATABASE não pode rodar dentro da
# transação única que o lote inteiro compartilha).
_AUTO_CLOSE_JA_GARANTIDO: set[tuple[str, str]] = set()


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


def ensure_auto_close_off(conn, servidor: str, banco: str) -> None:
    """Garante `AUTO_CLOSE` desligado no banco do cliente — SQL Server
    Express liga essa opção por padrão, e ela faz o SQL Server fechar o
    banco INTEIRO assim que a última conexão encerra; a próxima conexão
    tem que reabrir tudo do zero, do disco, antes de responder qualquer
    query. Em banco grande (GBs) isso é lento o bastante pra parecer
    "travou até estourar timeout" de forma intermitente — só acontece
    quando a operação chega bem depois de um período ocioso.

    Achado real 2026-08-28 investigando timeout intermitente no sistema
    legado (BackOn VB6) de um cliente real (réplica de teste
    `RJPNEUS-TESTE`/`minimachine`) — ver PENDENCIAS.md/memória de projeto
    pro diagnóstico completo (não foi a única causa achada — o banco
    também tinha estatística nunca atualizada e dezenas de índices
    redundantes/fragmentados — mas `AUTO_CLOSE` é a única que faz sentido
    corrigir automaticamente aqui; o resto exige decisão caso a caso, não
    é uma correção segura de aplicar às cegas em produção). Corrigir isso
    no app novo protege tanto ele quanto o BackOn VB6 legado quando os
    dois compartilham o mesmo banco durante a migração — é configuração
    de BANCO, não de conexão/aplicação, então o benefício vale pra
    qualquer sistema que converse com esse banco, não só pra quem aplicou
    o fix.

    **Assinatura própria (recebe `conn`, não `cur`, diferente de toda
    entrada de `_MIGRACOES` acima)**: `ALTER DATABASE` não pode rodar
    dentro de uma transação de usuário (erro 226 do SQL Server), e
    `ensure_all_schema` roda o lote inteiro dentro de UMA transação só,
    commitada de uma vez no fim por `db.connection._ensure_schema_integral`
    — por isso este passo roda separado, liga `autocommit` só pra esta 1
    instrução e devolve pro estado anterior (`autocommit(False)`) logo
    em seguida, pra nunca deixar o resto do fluxo da conexão (que espera
    poder fazer seu próprio commit/rollback manual) rodando em autocommit
    por engano."""
    chave = ((servidor or "").strip().upper(), (banco or "").strip().upper())
    if chave in _AUTO_CLOSE_JA_GARANTIDO:
        return
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT is_auto_close_on FROM sys.databases WHERE database_id = DB_ID()")
        row = cur.fetchone()
        if row and row.get("is_auto_close_on"):
            cur.execute("SELECT DB_NAME() AS db")
            nome_banco = cur.fetchone()["db"]
            nome_escapado = nome_banco.replace("]", "]]")
            conn.autocommit(True)
            try:
                cur.execute(f"ALTER DATABASE [{nome_escapado}] SET AUTO_CLOSE OFF")
            finally:
                conn.autocommit(False)
        cur.close()
    except Exception:
        logging.getLogger(__name__).warning(
            "Falha ao garantir AUTO_CLOSE OFF em %s/%s", servidor, banco, exc_info=True,
        )
    _AUTO_CLOSE_JA_GARANTIDO.add(chave)
