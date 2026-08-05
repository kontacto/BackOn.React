"""Serviço do módulo de Permissões.

Modelo de dados (tabela SQL `permissoes`):
  codigo IDENTITY, classe int, nome nvarchar(20), tipo nvarchar(5),
  sistema smallint, tela nvarchar(15), comando nvarchar(15), FORMULARIO nvarchar(30)

Regras:
  • Este projeto = sistema 50.
  • A presença de uma linha (classe, tela, comando) significa PERMITIDO.
  • As permissões ficam ligadas ao GRUPO do usuário (classes_usuarios.codigo == permissoes.classe == usuarios.classe).

O catálogo de telas/ações é declarativo (abaixo): ao adicionar uma nova tela ou
ação aqui, ela aparece automaticamente na árvore do app — sem cadastro manual.
"""
import asyncio
import unicodedata

from db.connection import _open_conn
from models.permissoes import SalvarPermissoesRequest

SISTEMA = 50

# Ações (botões) padrão de cada tela — pedido do usuário (5a).
ACOES_PADRAO = [
    ("ABRIR", "Abrir Tela"),
    ("GRAVAR", "Gravar"),
    ("EXCLUIR", "Excluir"),
    ("IMPRIMIR", "Imprimir"),
    ("EXPORTAR", "Exportar"),
]


# Ações específicas da tela de Pedido (reflete TODOS os botões reais da tela).
# Obs.: o Pedido NÃO pode ser excluído — sua SITUAÇÃO é que muda
# (Aberto/Fechado/Faturado/Cancelado), por isso há "Alterar situação" e não "Excluir".
ACOES_PEDIDO = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar pedido"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("DESC_GERAL", "Desconto geral"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
    # Botão "Faturar Pedido" (FrmManPedBar.frm, Command111_Click — só a
    # parte não-fiscal, ver PENDENCIAS.md > "Pedido Bar") — permissão
    # própria, separada de SITUACAO (pedido `[GLOBAL]` do usuário
    # 2026-07-16: "colocar todos os botões nas regras de permissões", cada
    # botão real da tela com seu próprio checkbox, não compartilhar ação
    # entre botões distintos). **Trazido pro ACOES_PEDIDO_COMP em
    # 2026-07-20** (pedido explícito do usuário) — mesma ação/regra, ver
    # `pedidos_service._faturar_pedido_sync`.
    ("FATURAR", "Faturar pedido"),
    # Botão "Forma de Pagamento" (FrmForPag.frm) — tela genérica no legado,
    # reaproveitada por Pedido Bar/Completo e O.S. (confirmado pelo usuário
    # 2026-07-16). Permissão própria, mesmo raciocínio do FATURAR acima.
    ("FORMA_PAG", "Forma de pagamento"),
    # Botão "Imprimir Pedido" (FrmManPedBar.frm, Command10_Click/
    # Pedido_48_COL) — recibo estilo térmico. **Trazido pro
    # ACOES_PEDIDO_COMP em 2026-07-20.**
    ("IMPRIMIR", "Imprimir pedido"),
    # Botão "Imprimir Item" (FrmManPedBar.frm, Command62_Click) — ticket de
    # um item só (sem preço/total), pra cozinha/bar. Botão em cada linha da
    # lista de itens, sempre disponível (não depende de haver impressora
    # configurada por Finalidade — isso só decide o disparo AUTOMÁTICO ao
    # incluir o item, que reaproveita esta mesma permissão de ADD_ITEM, não
    # uma nova). Permissão própria, mesmo raciocínio do IMPRIMIR acima.
    # **Trazido pro ACOES_PEDIDO_COMP em 2026-07-20.**
    ("IMPRIMIR_ITEM", "Imprimir item"),
    # Botão "Anexo" (Gestor de Documentos) — entre "Faturar Pedido" e
    # "Imprimir" na toolbar (pedido explícito do usuário, 2026-07-16). Pedido
    # não é entidade principal do Gestor de Documentos — grava como anexo do
    # Cliente (cod_grupo=1), sub-grupo "Pedidos de Venda" (cod_sub_grupo=2)
    # + referencia=pedido, ver AnexosPedidoModal.tsx. **Trazido pro
    # ACOES_PEDIDO_COMP em 2026-07-20.**
    ("ANEXOS", "Anexos"),
    # Botão "Reabrir" (FrmManPedBar.frm, `cmdReabrir_Click`) — entre
    # "Faturar Pedido" e "Anexo" na toolbar, ao lado de "Cancelar" (pedido
    # explícito do usuário, 2026-07-16). Só reabre pedido Fechado (F -> A) —
    # legado bloqueia Aberto/Cancelado/Faturado com a mesma mensagem, sem
    # senha de gerente (diferente do Cancelar). Reverte a baixa de estoque
    # do Fechar. Permissão própria, mesmo raciocínio do CANCELAR abaixo.
    # **Trazido pro ACOES_PEDIDO_COMP em 2026-07-20.**
    ("REABRIR", "Reabrir pedido"),
    # Botão "Cancelar Pedido" (FrmManPedBar.frm, Command9_Click) — entre
    # "Faturar Pedido" e "Imprimir" na toolbar (pedido explícito do usuário,
    # 2026-07-16). Legado exige senha de gerente antes de cancelar; esta
    # migração usa permissão de grupo própria no lugar (mesmo raciocínio do
    # FATURAR acima — cada botão real da tela com seu checkbox, não
    # reaproveita SITUACAO). **Não trazida pro ACOES_PEDIDO_COMP** — o
    # Pedido Completo já cancelava reaproveitando SITUACAO antes desta
    # rodada (2026-07-20); mantido assim de propósito pra não exigir uma
    # reconcessão de permissão em instalações já configuradas (ver
    # `pedidos_service._cancelar_pedido_sync`).
    ("CANCELAR", "Cancelar pedido"),
    # Botão "Dividir Pedido" — funcionalidade NOVA, sem precedente no legado
    # (pesquisado em toda a árvore VB6, nenhum "Dividir/Separar Conta"
    # existe). Divide um pedido Aberto em 2+ pedidos novos, cada um com um
    # subconjunto dos itens (quantidade inteira ou fracionária, pra dividir
    # o valor de um item indivisível entre várias pessoas), todos sob o
    # mesmo cliente. Pedido explícito do usuário, 2026-07-17 — ver
    # `_dividir_pedido_sync` em pedidos_service.py. **Trazido pro
    # ACOES_PEDIDO_COMP em 2026-07-20.**
    ("DIVIDIR", "Dividir pedido"),
    # Botão "Incluir Tx Serviço" (FrmManPedBar.frm) — feature exclusiva do
    # segmento Bar (10% de taxa de serviço sobre a conta), sem equivalente
    # no Pedido de Venda geral. **Único item deliberadamente NÃO trazido
    # pro ACOES_PEDIDO_COMP** na rodada de 2026-07-20 (pedido explícito do
    # usuário: "as funções do pedido bar, com exceção da taxa de serviço").
    ("TX_SERVICO", "Taxa de serviço"),
    # Checkbox "Pedido Entregue" (FrmManPedBar.frm, Check88) — grava direto
    # no clique. **Trazido pro ACOES_PEDIDO_COMP em 2026-07-20.**
    ("ENTREGUE", "Marcar como entregue"),
]


# Ações da Ordem de Serviço (os / os_produto). Vendedor e executor são por item.
ACOES_OS = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar OS"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
    # Botão "Forma de Pagamento" (FrmForPag.frm) — mesma tela genérica
    # usada pelo Pedido, confirmado pelo usuário que também atende O.S.
    ("FORMA_PAG", "Forma de pagamento"),
    # Faturar (gera Comanda) — ação própria, separada de SITUACAO (Fechar),
    # mesmo padrão do Pedido Bar/Geral. Adicionado 2026-07-21, user-directed
    # (pré-requisito do Gestor de Comandas — sem isso, O.S. nunca aparecia
    # como venda finalizada). Exige a OS já Fechada (`_faturar_os_sync`).
    ("FATURAR", "Faturar O.S."),
]

# Ações do Checkout (venda direta de balcão — migração de FrmPafOFF.frm,
# "Emissão de Cupom Fiscal"/PDV). Fase 1 (núcleo) — ver PENDENCIAS.md >
# "Checkout" pro rastreio completo e as fases adiadas.
ACOES_CHECKOUT = [
    ("ABRIR", "Abrir tela"),
    ("ADD_ITEM", "Adicionar item"),
    ("DEL_ITEM", "Cancelar item"),
    ("DESC_ITEM", "Desconto no item"),
    ("DESC_GERAL", "Desconto geral"),
    ("FECHAR", "Fechar venda"),
    ("CANCELAR", "Cancelar venda"),
]


# Ações da tela "O.S. Completa" (migração de `FrmTraOsNew.frm`, Fase 1 —
# núcleo, 2026-07-30/31). Mesmo raciocínio de ACOES_PEDIDO_COMP em relação a
# ACOES_PEDIDO: vocabulário de comando compartilhado com ACOES_OS (mesma
# máquina de estados, mesmos endpoints por trás — `os_service.py` reaproveita
# suas próprias funções com `tela="OS_COMP"`), permissão própria neste
# catálogo. DESC_GERAL trazido aqui mesmo não existindo em ACOES_OS (a O.S.
# Mobile nunca expôs desconto geral na UI, mas `aplicar_desconto_geral` não
# tem checagem embutida — a rota `/os-completo/{codigo}/desconto-geral` é a
# primeira a expor essa ação, precisa de entrada própria no catálogo).
# REABRIR é NOVO (não existe nem na O.S. Mobile ainda — `os_service.
# reabrir_os`, só F->A, mesmo raciocínio do Pedido). ANEXOS/IMPRIMIR trazidos
# porque a tela completa tem Gestor de Documentos + recibo HTML (mesmo
# padrão do Pedido Completo). **CANCELAR fica de fora aqui de propósito** —
# reaproveita a permissão SITUACAO (mesma decisão já tomada pro Pedido
# Completo, ver comentário de ACOES_PEDIDO_COMP acima — evita exigir
# reconcessão de permissão, e nem sequer existe instalação usando Cancelar
# de O.S. ainda). Sem DIVIDIR/ENTREGUE/TX_SERVICO/IMPRIMIR_ITEM/AGENDAR —
# funcionalidades específicas do Pedido (Bar/Geral), sem equivalente na O.S.
ACOES_OS_COMP = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar OS"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("DESC_GERAL", "Desconto geral"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
    ("FORMA_PAG", "Forma de pagamento"),
    ("FATURAR", "Faturar O.S."),
    ("REABRIR", "Reabrir O.S."),
    ("ANEXOS", "Anexos"),
    ("IMPRIMIR", "Imprimir O.S."),
    # Pontuação de Técnicos (migração do frame "Pontuação", Command4_Click
    # em frmtraosa.frm) — nota 0-999 de Executor/Vendedor/Atendente por
    # item. Adicionado 2026-08-01, user-directed.
    ("PONTUACAO", "Pontuação de Técnicos"),
    # Autorização/Expedição de Itens (migração da aba "Autorização de
    # Itens", `FrmTraOsNew.frm`, Revenda) — gated também pelas flags de
    # empresa `exige_aprovacao_itens_os`/`exige_expedicao_itens_os`
    # (Controle do Sistema); estas 2 ações controlam quem PODE autorizar/
    # expedir quando a empresa exige. Adicionado 2026-08-01, user-directed.
    ("AUTORIZAR", "Autorizar/Remover Autorização de Itens"),
    ("EXPEDIR", "Autorizar/Remover Expedição de Itens"),
    # Tempo Gasto por Serviço (migração do frame "Tempo Gasto",
    # Command30_Click em Revenda\FrmTraOsNew.frm) — lançamento de
    # início/fim de atendimento por serviço/técnico, tabela `os_tempo`.
    # Adicionado 2026-08-01, user-directed.
    ("TEMPO", "Tempo Gasto por Serviço"),
    # Requisições vinculadas a O.S. (aba "Requisições vinculadas a O.S.",
    # GridReq, em Revenda\FrmTraOsNew.frm) — 100% somente leitura, sem
    # equivalente de escrita nesta tela (mesmo padrão de VER_DESCONTOS).
    # Adicionado 2026-08-01, user-directed.
    ("VER_REQUISICOES", "Ver Requisições Vinculadas"),
    # Agendar item de Serviço (módulo Assistência — mesmo fluxo/tabelas
    # `AGENDA`/`AGENDA_OS` já usados pelo Pedido Geral via `AGENDA_PEDIDO`,
    # ver `agenda_service.py`). Adicionado 2026-08-01, user-directed.
    ("AGENDAR", "Agendar item de serviço"),
    # Criar Cópia (migração do botão "Criar Cópia", Command49_Click, em
    # Revenda\FrmTraOsNew.frm) — cria uma nova O.S. Aberta a partir do
    # cabeçalho + itens (só produtos/serviços ainda ativos no cadastro) da
    # O.S. atual. Disponível em qualquer Situação no legado, sem
    # confirmação prévia. Adicionado 2026-08-02, user-directed.
    ("COPIAR", "Criar Cópia da O.S."),
    # Alteração de Executor pós-fechamento (migração do botão `CmdAltExec`,
    # branch F/PG de `CmDaltera_Click`, Revenda\FrmTraOsNew.frm) — corrige
    # o técnico executor/vendedor de um item já lançado, com a O.S.
    # Fechada ou Faturada, sem reabrir a O.S. Adicionado 2026-08-02,
    # user-directed.
    ("ALT_EXECUTOR", "Alteração de Executor pós-fechamento"),
]

# Envio de Equipamentos para Terceiros (migração de `FrmManRet.frm`,
# 2026-08-01, user-directed). Tela própria (não uma ação dentro de OS/
# OS_COMP) — no legado é um MDI child independente, com busca de O.S.
# própria (F2), não aberta a partir da tela de O.S. RETORNO tem permissão
# própria (ação distinta de GRAVAR, mesmo raciocínio de FATURAR/SITUACAO
# nas outras telas de pré-venda) — EXCLUIR é hard delete real (única
# entidade deste sistema sem soft-delete/mudança de situação, confirmado
# no código-fonte do legado).
ACOES_RETIFICA = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Envio p/ Terceiro"),
    ("RETORNO", "Retorno do Terceiro"),
    ("EXCLUIR", "Excluir protocolo"),
]

# Ações do Gestor de Comandas (migração de `FrmConCupom.frm`) — só leitura/
# relatório. Adicionado 2026-07-21, user-directed.
ACOES_COMANDA = [
    ("ABRIR", "Abrir tela"),
    ("IMPRIMIR", "Imprimir"),
    ("EXPORTAR", "Exportar"),
]

# Ações de Alterar Comandas (migração de `FrmAltComNV.frm`) — aberta a
# partir de uma linha do Gestor de Comandas. Tela própria (mesmo padrão de
# CONTRATO/FATURAR_CONTR — duas telas de UI ligadas, duas teolas de
# permissão), pra não misturar "ver o relatório" com "alterar/cancelar uma
# venda já finalizada". Adicionado 2026-07-21, user-directed.
ACOES_ALTERAR_COMANDA = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar (atendente/vendedor/cliente)"),
    ("FORMA_PAG", "Alterar forma de pagamento"),
    ("NUM_SERIE", "Números de série"),
    ("CANCELAR", "Cancelar comanda"),
    # Emissão fiscal real (NFC-e) — Fase 1 do pacote de emissão,
    # adicionado 2026-07-21, user-directed (ver nfe_emissao_service.py).
    ("EMITIR_NF", "Emitir nota fiscal"),
    # Emissão fiscal real (NFS-e, DPS Nacional) — Fase 3 do pacote de
    # emissão, adicionado 2026-07-21, user-directed (ver
    # nfse_emissao_service.py). Ação separada de EMITIR_NF porque é um
    # documento fiscal diferente (produto x serviço) — um grupo pode ter
    # permissão de emitir um sem o outro.
    ("EMITIR_NFSE", "Emitir nota fiscal de serviço"),
]

# Ações da tela de cadastro de Bancos (Financeiro > Cobranças, FrmManBan.frm).
ACOES_BANCOS = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar"),
    ("EXCLUIR", "Excluir"),
    # Fase 2a (2026-07-24) — motor CNAB, só Bradesco (237) nesta rodada. Ver
    # PENDENCIAS.md > "Bancos (Cadastro de Cobrança / Boleto / CNAB)".
    ("GERAR_REMESSA", "Gerar arquivo de remessa"),
    ("IMP_RETORNO", "Importar arquivo de retorno"),
]

# Tela dedicada "Importação do Arquivo de Retorno" (FrmImpRetBan.frm) — grade
# de revisão + aplicação seletiva de baixa, ver cobranca_retorno_service.py.
# Distinta da ação rápida BANCOS.IMP_RETORNO (modal dentro do cadastro de
# Bancos, colar+processar direto) — esta é a tela cheia, fiel ao legado.
ACOES_RETORNO_BANC = [
    ("ABRIR", "Abrir tela"),
    ("BAIXAR", "Baixar títulos selecionados"),
]

# Tela "Geração de Boletos" (frmrelbol4.frm) — filtros+grade de títulos,
# Gerar Remessa (reaproveita os motores CNAB) e Gerar Planilha. Emissão do
# PDF do boleto (com código de barras) e envio por e-mail ficam de fora
# desta fase — motor de desenho visual do boleto ainda não existe, ver
# PENDENCIAS.md > "Geração de Boletos".
ACOES_GERACAO_BOLETOS = [
    ("ABRIR", "Abrir tela"),
    ("GERAR_REMESSA", "Gerar arquivo de remessa"),
    ("EXPORTAR", "Exportar planilha"),
]


ACOES_VIAGEM = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar dados da viagem"),
    ("ADD_ITEM", "Adicionar item"),
    ("DEL_ITEM", "Excluir item"),
    ("ALT_CILINDRO", "Alterar cilindro do item"),
    ("FECHAR_SAIDA", "Fechar saída"),
    ("FECHAR_ENTRADA", "Fechar entrada"),
    ("REABRIR", "Reabrir saída ou retorno"),
    ("CANCELAR", "Cancelar viagem"),
    ("EXPORTAR", "Exportar"),
]


# Ações da tela "Pedido Completo"/"Pedido Geral" (frmmanpedfor.frm, Fase A —
# núcleo: cabeçalho + grade de itens + Fechar/Cancelar). Mesmo vocabulário de
# comando de ACOES_PEDIDO (pré-venda rápida) para não duplicar sentido —
# "SITUACAO" cobre Fechar/Cancelar/Faturar/Reabrir (mesma máquina de
# estados, mesmo raciocínio de "Alterar situação" único já usado lá, exceto
# FATURAR que já tinha ação própria no Pedido Bar — replicado igual aqui).
# WHATSAPP/DESC_ITEM/DESC_GERAL/VER_DESCONTOS/ANALISE trazidos 2026-07-15
# (pedido explícito do usuário, "aplicar os recursos do Pedido Mobile no
# Pedido Completo") — mesma lista de ACOES_PEDIDO, os endpoints/telas por
# trás são genéricos (chave é o `pedido`, não a tela que criou o registro).
#
# Faturar/Reabrir/Dividir/Anexos/Imprimir/Imprimir Item/Entregue trazidos
# 2026-07-20 (pedido explícito do usuário: "aplicar para o pedido de venda
# Geral/completo... o layout e as funções do pedido bar com exceção da taxa
# de serviço") — mesmas funções/regras do Pedido Bar (ver
# `pedido_completo_service.py`, que reaproveita `pedidos_service.py`
# diretamente em vez de duplicar), só com permissão própria neste catálogo.
# CANCELAR fica de fora aqui de propósito — o Pedido Completo já cancelava
# reaproveitando SITUACAO antes desta rodada; manter assim evita exigir uma
# reconcessão de permissão em instalações já configuradas (ver docstring de
# `pedidos_service._cancelar_pedido_sync`). **TX_SERVICO continua fora** —
# único item do Pedido Bar deliberadamente não trazido (pedido explícito do
# usuário).
ACOES_PEDIDO_COMP = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar pedido"),
    ("WHATSAPP", "Enviar por WhatsApp"),
    ("ADD_ITEM", "Adicionar item"),
    ("EDIT_ITEM", "Editar item"),
    ("DEL_ITEM", "Excluir item"),
    ("DESC_ITEM", "Desconto no item"),
    ("DESC_GERAL", "Desconto geral"),
    ("VER_DESCONTOS", "Ver descontos"),
    ("ANALISE", "Analisar margem"),
    ("SITUACAO", "Alterar situação"),
    # Botão "Forma de Pagamento" (FrmForPag.frm) — confirmado pelo usuário
    # 2026-07-16 que essa tela também atende Pedido Geral/Completo.
    ("FORMA_PAG", "Forma de pagamento"),
    ("FATURAR", "Faturar pedido"),
    ("REABRIR", "Reabrir pedido"),
    ("DIVIDIR", "Dividir pedido"),
    ("ANEXOS", "Anexos"),
    ("IMPRIMIR", "Imprimir pedido"),
    ("IMPRIMIR_ITEM", "Imprimir item"),
    ("ENTREGUE", "Marcar como entregue"),
    # Agendar item de Serviço (módulo Clínica) — ver agenda_service.py.
    ("AGENDAR", "Agendar item de serviço"),
]

# Tela "Agenda" (grade semanal de disponibilidade + agendamento avulso,
# módulo Clínica — ver agenda_service.py). Distinta de `PEDIDO_COMP.AGENDAR`
# (agendar um item de Serviço que já existe dentro de um Pedido) — aqui é a
# tela própria de calendário/atendimento avulso.
ACOES_AGENDA = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Agendar/reagendar atendimento"),
    ("TROCAR_PROF", "Trocar profissional"),
    ("FATURAR", "Faturar atendimento avulso"),
    ("ANEXOS", "Anexos"),
    ("LAYOUTS", "Preencher Layouts"),
]

# Motor de Formulário Dinâmico (Cadastro de Layout — `FrmCadLay.frm`).
# Cadastro do TEMPLATE em si (campos/tipos) — o preenchimento por entidade
# (Cliente/Agenda/etc.) usa a permissão da própria tela dona (ex.:
# `AGENDA.LAYOUTS`), não esta.
ACOES_LAYOUT = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar layout"),
    ("EXCLUIR", "Excluir layout"),
]


# Ações da tela "Movimentação de Produtos" (Transações > Movimentações,
# `frmEntPro.frm`) — não tem "Alterar" (o próprio legado desabilita essa
# ação incondicionalmente) nem Imprimir/Exportar (não existem no form
# original). "Excluir" reverte o efeito no estoque, ver
# movimentacao_produtos_service.py.
ACOES_MOV_PRODUTOS = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Incluir movimentação"),
    ("EXCLUIR", "Excluir movimentação"),
]


# Ações da tela "Requisição" (Transações > Movimentações, `FrmManReq.frm`)
# — o fluxo de autorização em 2 etapas do legado é código morto (nunca
# invocado por nenhum botão ativo do form), por isso não existe ação de
# "autorizar" aqui; só o que a tela de fato executa: incluir/excluir item,
# fechar (baixa estoque), reabrir e cancelar.
ACOES_REQUISICAO = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Incluir item"),
    ("EXCLUIR", "Excluir item"),
    ("FECHAR", "Fechar requisição"),
    ("REABRIR", "Reabrir requisição"),
    ("CANCELAR", "Cancelar requisição"),
    ("IMPRIMIR", "Imprimir requisição"),
]


# Ações da tela "Gestão de Compras" (aba Ressuprimento, `FrmGesCom.frm`) —
# só consulta/relatório, sem Gravar/Excluir. A aba "Cotações" do legado
# nunca foi desenvolvida (0 controles no próprio .frm) e fica fora desta
# rodada — ver PENDENCIAS.md.
ACOES_GESTAO_COMPRAS = [
    ("ABRIR", "Abrir tela"),
    ("IMPRIMIR", "Imprimir"),
    ("EXPORTAR", "Gerar planilha"),
]

# Ações da tela "Curva ABC e Estoques" (`FrmCurvaABC.frm`) — gera/grava a
# curva ABC e reprocessa mínimo/ressuprimento/máximo/consumo médio em
# `pecas`, ações separadas porque são 2 gravações distintas no legado
# (Command4 "Gerar Curva ABC" vs. Command6 "Processar atualização de
# estoques").
ACOES_CURVA_ABC = [
    ("ABRIR", "Abrir tela"),
    ("GERAR", "Gerar curva ABC"),
    ("REPROCESSAR", "Processar atualização de estoques"),
    ("IMPRIMIR", "Imprimir resultados"),
    ("EXPORTAR", "Gerar planilha"),
]

# Pedido de Compra (`FrmPedCom.frm`) — implementada 2026-07-18. Legado
# rastreado por completo: tabelas reais `pedido`/`pedido_itens` (já
# existentes no schema, confirmadas ao vivo em GERDELL/BARESTELA, mesmo
# schema usado pelas variantes Revenda/ValPorto/KIFESTA do `.frm`). Ações
# próprias (não o padrão genérico) — Aprovar/Rejeitar/Reabrir mudam
# `situacao` (A→F/A→C/F→A), mesmo vocabulário A/F/C de Requisição e
# Cotação de Compra. "Excluir Pedido" do legado está com `Visible=0` no
# próprio `.frm` (botão morto, nunca exibido) — não replicado. "Rateio
# Desp/Desc" e "Importar DAV" (de Pedido de Venda/Orçamento/O.S.) ficam
# fora desta rodada — Orçamento nem existe nesta migração e Importar DAV
# depende de telas "Completo" que ainda não existem — ver PENDENCIAS.md.
ACOES_PEDIDO_COMPRA = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar / incluir item"),
    ("EXCLUIR", "Excluir item"),
    ("APROVAR", "Aprovar pedido"),
    ("REJEITAR", "Rejeitar pedido"),
    ("REABRIR", "Reabrir pedido"),
    ("IMPRIMIR", "Imprimir pedido"),
]

# Cotação de Compra (2026-07-18, user-directed) — aba "Cotações" do
# `FrmGesCom.frm`, nunca desenvolvida no legado (0 controles no próprio
# .frm). Construída do zero a partir de anotações manuscritas do usuário
# ("Projeto em Andamento — Compras Mapa de Cotação", 03/05/2013) — sem
# fonte VB6 pra rastrear campo-a-campo. Ver PENDENCIAS.md > "Gestão de
# Compras" > "Cotação" pro escopo completo e o que ficou de fora (envio
# por e-mail, geração de Pedido de Compra formal — ambos confirmados como
# fora desta rodada pelo usuário).
ACOES_COTACAO_COMPRA = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Incluir item / lançar resposta"),
    ("EXCLUIR", "Excluir item / resposta"),
    ("VENCEDOR", "Marcar fornecedor vencedor"),
    ("FINALIZAR", "Finalizar cotação"),
    ("REABRIR", "Reabrir cotação"),
    ("CANCELAR", "Cancelar cotação"),
    ("IMPRIMIR", "Imprimir comparativo"),
]

# Card "Alertas de Estoque" na Tela Principal (2026-07-20, user-directed) —
# sem `.frm` legado (recurso novo). Só uma ação (ver) — a ação de gerar
# pedido de compra a partir da seleção já é coberta pela permissão própria
# de Pedido de Compra (`PEDIDO_COMPRA.GRAVAR`), não duplicada aqui. A
# visibilidade do card reforça esta permissão em cima da regra funcional já
# existente (Gerente/Supervisor/Master, `isManagerFuncao`) — as duas
# precisam estar de acordo, mesmo princípio de "reforçar, não substituir"
# já usado no gating por módulo ativo.
ACOES_ALERTAS_ESTOQUE = [
    ("ABRIR", "Ver card de alertas"),
    # Recalcula os contadores e grava o resultado no cache compartilhado da
    # empresa (`alertas_estoque_cache`) — ação própria porque, diferente de
    # ABRIR (só leitura do cache), esta grava um dado visto por TODOS os
    # usuários com acesso ao card, não só quem clicou. Adicionado
    # 2026-07-21, user-directed — ver `_atualizar_alertas_estoque_sync`.
    ("ATUALIZAR", "Atualizar contadores"),
]


# Ações da tela de CFOP: além do padrão, o botão que abre o modal de
# "Vínculos de CFOP das NFe's importadas por XML" (tabela `cfop_xml`) tem
# permissão própria — é uma sub-funcionalidade separada dentro da mesma tela.
ACOES_CFOP = ACOES_PADRAO + [
    ("VINCULOS_XML", "Vínculos XML"),
]

# Contrato (2026-07-19, user-directed) — Fase A de `FrmManContra.frm`
# (Transações > Contratos). Sem "Imprimir" — a impressão do contrato
# (`Command16_Click`) pertence ao mesmo motor de Faturar Contratos/emissão
# fiscal deixado pra uma rodada futura, ver PENDENCIAS.md > "Contratos".
ACOES_CONTRATO = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar"),
    ("EXCLUIR", "Excluir"),
    ("ITENS", "Itens do contrato"),
    ("CENTRO_CUSTO", "Centro de Custo"),
    ("REAJUSTE", "Alteração de Preço"),
    ("CRED_DEB", "Acréscimo/Desconto"),
    ("ENCERRAR", "Encerrar Contrato"),
]

# Faturar Contratos (2026-07-20) — motor de faturamento (comanda/Receber/
# Duplicata_Receber, fiel ao legado) + geração de Recibo. Nota Fiscal e
# Boleto ficam fora desta rodada, ver PENDENCIAS.md > "Contratos".
ACOES_FATURAR_CONTR = [
    ("ABRIR", "Abrir tela"),
    ("FATURAR", "Faturar"),
    ("RECIBO", "Gerar Recibo"),
]

# Gestor de Projetos (migração de frmgespro.frm, Fase 1 — núcleo,
# 2026-08-02, user-directed). ADD_PEDIDO/ADD_OS/ADD_REQUISICAO espelham
# os 3 botões "Adicionar..." granulares do legado (Orçamento não existe
# como tipo próprio nesta migração — ver CLAUDE.md > "Regras Globais de
# Pré-venda": um Pedido Aberto já cumpre esse papel, então não há um
# 4º "ADD_ORCAMENTO"). VER_CUSTOS esconde as colunas de custo/margem da
# aba Itens pra quem não tem essa permissão — separada do acesso geral,
# mesmo padrão do legado (`Command13`/`EnxergaCusto`). SITUACAO cobre
# Finalizar/Reabrir/Cancelar (mesmo padrão de uma permissão só pra todas
# as transições de situação, já usado em O.S./Pedido).
ACOES_PROJETOS = [
    ("ABRIR", "Abrir tela"),
    ("GRAVAR", "Gravar"),
    ("ADD_PEDIDO", "Vincular Pedido"),
    ("ADD_OS", "Vincular O.S."),
    ("ADD_REQUISICAO", "Vincular Requisição"),
    ("REMOVER_DOC", "Remover Documento"),
    ("SITUACAO", "Finalizar/Reabrir/Cancelar"),
    ("VER_CUSTOS", "Visualizar Custos"),
    ("ANEXOS", "Anexos"),
    # Fase 2 (2026-08-02) — "Ajustar Valores" (migração de
    # `Command17`/`Reprocessa`, `frmgespro.frm`): redistribui desconto/
    # acréscimo entre os itens dos documentos vinculados pra bater um novo
    # total de Produtos ou Serviços. Permissão própria, mesmo padrão do
    # legado (`Command17.Enabled` gateia a aba inteira).
    ("AJUSTAR_VALORES", "Ajustar Valores"),
]


# Ações da tela de Clientes: além do padrão, o botão "Lista Negra" (cadastro
# na tabela `lista_negra`, botão por cliente na listagem) tem permissão
# própria — mesmo padrão de sub-funcionalidade separada já usado em CFOP
# (VINCULOS_XML) e Produtos Níveis.
ACOES_CLIENTE = ACOES_PADRAO + [
    ("LISTA_NEGRA", "Lista Negra"),
]


# Ações da tela de Funcionários: além do padrão, o CRUD embutido de
# Especialidades (ícone dentro da aba Especialidades, tabela
# `especialidades`) tem permissão própria — mesmo padrão de
# sub-funcionalidade separada já usado em Clientes (LISTA_NEGRA).
ACOES_FUNCIONARIOS = ACOES_PADRAO + [
    ("ESPECIALIDADE", "Cad. Especialidades"),
]


# Ações da tela de Serviços: além do padrão, o botão "Previsão de Produtos"
# (abre a composição de materiais do serviço, tabela `produtos_compostos`)
# tem permissão própria — mesmo padrão de sub-funcionalidade separada já
# usado em Funcionários (ESPECIALIDADE) e Clientes (LISTA_NEGRA). Regra
# geral do usuário (2026-07-10): todo botão que abre uma tela secundária de
# CADASTRO (permite incluir/excluir, não só visualizar) precisa da sua
# própria permissão — "Exceções da Comissão" (mesma tela) é só leitura,
# não se enquadra e por isso não ganhou permissão própria aqui.
ACOES_SERVICO = ACOES_PADRAO + [
    ("PREV_PRODUTOS", "Previsão de Produtos"),
]


# Ações da tela "Produto Completo" (migração de FrmManPec.frm — Cadastro de
# Produtos, tabela `pecas`, 2026-07-14). FORNECEDORES (pecas_fornecedor) e
# GRADE (gera produtos-filhos de verdade) são sub-funcionalidades de CADASTRO
# próprias, mesmo padrão de PREV_PRODUTOS/ESPECIALIDADE/LISTA_NEGRA acima.
# FOTOGRAFIA e ENVIAR_SITE ganham permissão própria por serem ações
# irreversíveis/com efeito colateral externo (grava cor por variante,
# publica de verdade na Tray) — mesmo raciocínio de CRITICAR/CANCELAR em
# Notas Fiscais.
ACOES_PRODUTO_COMP = ACOES_PADRAO + [
    ("FORNECEDORES", "Vincular Fornecedores"),
    ("FOTOGRAFIA", "Gerenciar Fotos"),
    ("ENVIAR_SITE", "Enviar/Atualizar no Site"),
    ("GRADE", "Gerar Itens de Grade"),
]


# Ações da tela de Equipamentos: além do padrão, 3 sub-funcionalidades
# ganham permissão própria (mesmo padrão de PREV_PRODUTOS/LISTA_NEGRA/
# ESPECIALIDADE) — DISPONIBILIZAR e ALT_NUM_SERIE são ações de CADASTRO
# secundárias (mexem em outras tabelas: contratos_produtos_disponiveis/
# contratos_produtos/retifica). ALTERAR_TIPO é diferente das demais: no
# legado, o campo "Tipo do Equipamento" (Avulso/Contrato) só é editável
# por usuários "gerente" (cod_funcao IN ('01','07','02'), hardcoded) —
# aqui vira uma permissão própria em vez de checar função hardcoded,
# mesmo espírito das exceções REPROC_ITEM/REPROC_RESERV em
# ACOES_PRODUTO_NIVEIS (restrição sensível liberada por admin via
# Permissões, não por código fixo).
ACOES_EQUIPAMENTOS = ACOES_PADRAO + [
    ("ALTERAR_TIPO", "Alterar Tipo"),
    ("DISPONIBILIZAR", "Disponibilizar"),
    ("ALT_NUM_SERIE", "Alt. Núm. Série"),
]


# Ações da tela de Telemarketing: além do padrão, "WHATSAPP" segue o mesmo
# padrão já usado em Pedido/O.S. (ACOES_PEDIDO/ACOES_OS) — botão de envio
# com permissão própria, gated no frontend via can("TELEMARKETING.WHATSAPP").
ACOES_TELEMARKETING = ACOES_PADRAO + [
    ("WHATSAPP", "Enviar por WhatsApp"),
]


# Ações da tela "Notas Fiscais" (migração de FrmManRec.frm, Fase 1 — CRUD
# sem emissão fiscal real, ver notas_fiscais_service.py). CRITICAR e
# CANCELAR ganham permissão própria porque são ações irreversíveis/com
# efeito colateral em estoque — mesmo raciocínio de ALT_NUM_SERIE em
# Equipamentos.
ACOES_NOTAS_FISCAIS = ACOES_PADRAO + [
    ("CRITICAR", "Criticar"),
    ("CANCELAR", "Cancelar"),
]


# Ações da tela "Alterações Cadastro de Produtos Níveis" (alteração em massa de
# pecas/servicos por faixa de NCM ou nível — ver produtos_niveis_service.py).
# REPROC_ITEM/REPROC_RESERV substituem a restrição hardcoded a "KONTACTO" do
# legado: só quem o admin liberar explicitamente na tela de Permissões tem
# acesso a esses 2 botões (recálculo pesado de estoque).
ACOES_PRODUTO_NIVEIS = [
    ("ABRIR", "Abrir Tela"),
    ("GRAVAR", "Gravar Campos"),
    ("REAJUSTAR", "Reajustar Preço"),
    ("LEI_TRANSP", "% Lei Transparência"),
    ("DESATIVAR_NEG", "Desat. Estoque Neg."),
    ("DESATIVAR_ZERO", "Desat. Estoque Zero"),
    ("REPROC_ITEM", "Reprocessar Item"),
    ("REPROC_RESERV", "Reproc. Reservados"),
]


# "Inventário" (2026-07-22, user-directed) — card em Transações. Fase 1
# implementada: núcleo manual (Abertura/Digitação/Fechar/Cancelar), ver
# PENDENCIAS.md > "Inventário" pro rastreio completo. ABERTURA cobre tanto
# abrir quanto reabrir (mesma ação no legado, `cmbok_Click` único).
# DIGITACAO cobre Incluir e Alterar item (mesmo botão de tela no legado,
# `FrmInvDig`, ambos exigem a mesma permissão). FECHAR/CANCELAR ações
# próprias (efeito real e irreversível em estoque/situação do balanço).
ACOES_INVENTARIO = [
    ("ABRIR", "Abrir tela"),
    ("ABERTURA", "Abrir/Reabrir balanço"),
    ("DIGITACAO", "Incluir/Alterar item"),
    ("FECHAR", "Fechar balanço"),
    ("CANCELAR", "Cancelar balanço"),
    # Relatório de Contagem (2026-07-23, user-directed) — lista em branco
    # (código/descrição, sem a quantidade) pro conferente escrever a
    # contagem física no papel, que o digitador depois passa pro sistema
    # via Digitação de Estoque. Só leitura/impressão, ação própria porque
    # nem todo grupo que digita precisa poder emitir o relatório.
    ("REL_CONTAGEM", "Rel. de Contagem"),
    # Fase 2 (2026-07-23) — os outros 4 relatórios do menu legado
    # "Inventário", mesma ideia de ação própria por relatório (só leitura/
    # impressão, nem todo grupo precisa emitir todos).
    ("REL_CONFERENCIA", "Rel. de Conferência"),
    ("REL_CRITICA", "Rel. de Crítica"),
    ("REL_RESULTADO", "Rel. de Resultado"),
    ("REL_DIVERGENCIA", "Rel. de Divergência"),
]


# Limites reais das colunas da tabela SQL `permissoes` (tela/comando nvarchar(15),
# nome nvarchar(20)). `_salvar_sync` trunca silenciosamente ao gravar — um código
# de tela/comando/nome maior que isso grava um valor diferente do que o resto do
# app usa para checar permissão (`can("TELA.COMANDO")`), quebrando o acesso sem
# nenhum erro visível. Já aconteceu uma vez (GRUPO_MERCADOLOGICO, 19 chars,
# virou GRUPO_MERCADOLO no banco) — essas asserções pegam isso na hora de
# declarar o catálogo, não depois que alguém salva permissões silenciosamente erradas.
def _tela(tela: str, nome: str, acoes=ACOES_PADRAO) -> dict:
    assert len(tela) <= 15, f"tela '{tela}' tem {len(tela)} chars — coluna permissoes.tela é nvarchar(15)"
    assert len(nome) <= 20, f"nome '{nome}' tem {len(nome)} chars — coluna permissoes.nome é nvarchar(20)"
    for c, lbl in acoes:
        assert len(c) <= 15, f"comando '{c}' (tela '{tela}') tem {len(c)} chars — coluna permissoes.comando é nvarchar(15)"
    return {
        "tipo": "TELA",
        "tela": tela,
        "comando": "",
        "nome": nome,
        "children": [
            {"tipo": "BOTAO", "tela": tela, "comando": c, "nome": lbl, "children": []}
            for c, lbl in acoes
        ],
    }


def _menu(tela: str, nome: str, telas: list) -> dict:
    assert len(tela) <= 15, f"tela '{tela}' tem {len(tela)} chars — coluna permissoes.tela é nvarchar(15)"
    assert len(nome) <= 20, f"nome '{nome}' tem {len(nome)} chars — coluna permissoes.nome é nvarchar(20)"
    return {"tipo": "MENU", "tela": tela, "comando": "", "nome": nome, "children": telas}


# Árvore declarativa (Menu > Tela > Botões).
CATALOGO = [
    _menu("CADASTROS", "Cadastros", [
        _tela("CLIENTE", "Clientes", ACOES_CLIENTE),
        _tela("FORNECEDOR", "Fornecedores"),
        _tela("PRODUTO", "Produtos & Serviços"),
        _tela("PRODUTO_COMP", "Produto Completo", ACOES_PRODUTO_COMP),
        _tela("SERVICO", "Serviços", ACOES_SERVICO),
        _tela("PRODUTO_NIVEIS", "Alt. Produtos Níveis", ACOES_PRODUTO_NIVEIS),
        _tela("VEICULOS", "Veículos"),
        _tela("FUNCIONARIOS", "Funcionários", ACOES_FUNCIONARIOS),
        # Entrada/Saída de Caixa fica em Cadastros, não em Financeiro — é o
        # caixa OPERACIONAL da loja (recebe as vendas do dia), não o caixa
        # financeiro; pedido explícito do usuário (ver PENDENCIAS.md).
        _tela("MOV_CAIXA", "Entrada/Saída Caixa"),
        _tela("CONTATOS", "Contatos"),
        _tela("EQUIPAMENTOS", "Equipamentos", ACOES_EQUIPAMENTOS),
        _tela("TELEMARKETING", "Telemarketing", ACOES_TELEMARKETING),
        _tela("NOTAS_FISCAIS", "Notas Fiscais", ACOES_NOTAS_FISCAIS),
        _menu("TABAUX", "Tabelas Auxiliares", [
            _tela("MARCAS", "Marcas"),
            _tela("MODELOS", "Modelos"),
            _tela("MODIFICADORES", "Modificadores"),
            _tela("AREA", "Área"),
            _tela("AREA_ATUACAO", "Área de Atuação"),
            _tela("FORMA_PAGAMENTO", "Forma de Pagamento"),
            _tela("GRUPO_USUARIO", "Grupo de Usuário"),
            _tela("GRUPO_MERCAD", "Grupo Mercadológico"),
            _tela("CFOP", "Cfop", ACOES_CFOP),
            _tela("CFOP_PISCOF", "Cfop x Pis/Cofins"),
            _tela("CORES", "Cores"),
            _tela("ICMS", "Icms"),
            _tela("ORIGEM", "Origem"),
            _tela("REGIOES", "Regiões"),
            _tela("ROTAS", "Rotas"),
            _tela("SEGMENTOS", "Segmentos"),
            _tela("SITUACAO", "Situação"),
            _tela("TAMANHO", "Tamanhos"),
            _tela("TAXAS", "Taxas NFe/NFSe"),
            _tela("TAXAS_NFCE", "Taxas NFCe"),
            _tela("GRUPO_PISCOF", "Grupo PIS/COFINS"),
            _tela("TIPO_CLIENTE", "Tipo Cliente/Forn."),
            _tela("TIPO_DOC", "Tipo de Documento"),
            _tela("STATUS_OS", "Status de O.S."),
            _tela("FUNCOES", "Funções"),
            _tela("MENSAGENS", "Mensagens"),
            _tela("MENSAGENS_PDV", "Mensagens PDV", [("ABRIR", "Abrir Tela"), ("GRAVAR", "Gravar")]),
            _tela("NUM_SERIE", "Números de Série"),
            _tela("TIPO_MOV", "Tipo de Movimentação"),
            _tela("TIPO_MOV_MSG", "Tipo Mov x Mensagem", [("ABRIR", "Abrir Tela"), ("GRAVAR", "Gravar")]),
            _tela("TIPO_OS", "Tipo de Pré-Venda"),
            _tela("EXECUTOR_PADRAO", "Executor Padrão OS"),
            _tela("TIPO_PECA", "Tipo de Produto"),
            _tela("TIPO_OS_PROD", "Tipo Dest. Itens OS"),
            _tela("TIPO_SERVICO", "Tipo de Serviço"),
            _tela("TRIBUTACAO", "Tributação"),
            _tela("UNID", "Unidade de Medida"),
            # Cadastro de Layout (motor de formulário dinâmico —
            # `FrmCadLay.frm`, ver PENDENCIAS.md > "Pedido Geral — Fase B:
            # Clínica (Agendamento)") — cadastro do TEMPLATE em si (campos/
            # tipos), compartilhado por várias entidades (Cliente,
            # Agenda, etc.). O preenchimento por entidade usa a permissão
            # da tela dona (ex.: `AGENDA.LAYOUTS`), não esta.
            _tela("LAYOUT", "Cadastro de Layout", ACOES_LAYOUT),
        ]),
    ]),
    _menu("TRANSACOES", "Transações", [
        _tela("PEDIDO", "Pedido Bar", ACOES_PEDIDO),
        _tela("OS", "OS Mobile", ACOES_OS),
        _tela("CHECKOUT", "Checkout", ACOES_CHECKOUT),
        _tela("PEDIDO_COMP", "Pedido Completo", ACOES_PEDIDO_COMP),
        _tela("OS_COMP", "O.S. Completa", ACOES_OS_COMP),
        # "Envio para Terceiros" (migração de FrmManRet.frm, 2026-08-01,
        # user-directed) — envio/retorno de equipamento pra conserto
        # externo, vinculado a uma O.S. Tela própria, standalone (mesmo
        # padrão do form original — MDI child independente, não uma aba
        # dentro de O.S.).
        _tela("RETIFICA", "Envio para Terceiros", ACOES_RETIFICA),
        # "Gestor de Projetos" (2026-08-02, user-directed) — migração de
        # frmgespro.frm, Fase 1 (núcleo). Ver PENDENCIAS.md > "Gestor de
        # Projetos" pro rastreio completo e plano de fases.
        _tela("PROJETOS", "Gestor de Projetos", ACOES_PROJETOS),
        # "Agenda" (2026-07-28, user-directed) — grade semanal de
        # disponibilidade + agendamento avulso (módulo Clínica), ver
        # PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
        # (Agendamento)".
        _tela("AGENDA", "Agenda", ACOES_AGENDA),
        # Gestor de Comandas / Alterar Comandas (2026-07-21, user-directed) —
        # relatório de vendas finalizadas (`comanda`) + tela de alteração/
        # cancelamento aberta a partir de uma linha dele. Duas telas de
        # permissão (mesmo padrão de Contrato/Faturar Contratos).
        _tela("COMANDA", "Gestor de Comandas", ACOES_COMANDA),
        _tela("ALTERAR_COMANDA", "Alterar Comandas", ACOES_ALTERAR_COMANDA),
        # "Movimentações" (2026-07-18, user-directed) — Card novo em
        # Transações que abre um hub com estas duas telas. Só scaffolding
        # de navegação por enquanto (telas reais mostram "Em construção") —
        # ver PENDENCIAS.md > "Movimentações" pro rastreio de VB6 pendente.
        _tela("MOV_PRODUTOS", "Mov. de Produtos", ACOES_MOV_PRODUTOS),
        _tela("REQUISICAO", "Requisição", ACOES_REQUISICAO),
        # "Inventário" (2026-07-22, user-directed) — card novo em Transações,
        # hub vazio por enquanto (sem telas próprias ainda) — ver
        # PENDENCIAS.md > "Inventário".
        _tela("INVENTARIO", "Inventário", ACOES_INVENTARIO),
        # "Gestão de Compras" (2026-07-18, user-directed) — mesmo submenu
        # "Transações > Compra" do MDI legado (Pedido de Compra, Curva ABC
        # e Estoques, Gestão de Compras). Prioridade confirmada pelo
        # usuário: Gestão de Compras (Ressuprimento) + Curva ABC e Estoques
        # implementados nesta rodada; Pedido de Compra fica placeholder —
        # ver PENDENCIAS.md > "Gestão de Compras".
        _menu("COMPRA", "Compra", [
            _tela("PEDIDO_COMPRA", "Pedido de Compra", ACOES_PEDIDO_COMPRA),
            _tela("CURVA_ABC", "Curva ABC e Estoques", ACOES_CURVA_ABC),
            _tela("GESTAO_COMPRAS", "Gestão de Compras", ACOES_GESTAO_COMPRAS),
            _tela("COTACAO_COMPRA", "Cotação de Compra", ACOES_COTACAO_COMPRA),
        ]),
        # "Contratos" (2026-07-19, user-directed) — Fase A de
        # FrmManTPC/FrmManRea/FrmManInd/FrmConPDI/FrmManContra.frm, mais o
        # motor de Faturar Contratos (2026-07-20, FrmFatContrato2.frm/
        # FrmFatContrato.frm — Faturar + Recibo; Nota Fiscal/Boleto ficam
        # de fora). Envio de Cobrança (remessa bancária/e-mail em massa)
        # continua fora de escopo — ver PENDENCIAS.md > "Contratos".
        _menu("CONTRATOS", "Contratos", [
            _tela("TIPO_CONTRATO", "Tipo de Contrato"),
            _tela("TIPO_REAJUSTE", "Tipo de Reajuste"),
            _tela("INDICE_REAJUSTE", "Índices de Reajuste"),
            _tela("CONTR_PROD_DISP", "Produtos Disponíveis"),
            _tela("CONTRATO", "Contratos", ACOES_CONTRATO),
            _tela("FATURAR_CONTR", "Faturar Contratos", ACOES_FATURAR_CONTR),
        ]),
    ]),
    _menu("FINANCEIRO", "Financeiro", [
        _tela("CONTAS_PAGAR", "Contas a Pagar"),
        _tela("CONTAS_RECEBER", "Contas a Receber"),
        _menu("FLUXO_CAIXA", "Fluxo de Caixa", [
            _tela("PLANO_CONTAS", "Plano de Contas"),
            _tela("CENTRO_CUSTO", "Centro de Custo"),
            # Cadastro de contas de caixa/banco (FrmManConta.frm), ver
            # services/contas_service.py e PENDENCIAS.md > "Contas".
            _tela("CONTAS", "Contas"),
            # Configuração de quais Contas cada funcionário pode visualizar
            # (FrmConFunc.frm), ver services/conta_func_service.py e
            # PENDENCIAS.md > "Contas x Funcionário".
            _tela("CONTA_FUNC", "Contas x Funcionário"),
        ]),
        # Cadastro de Bancos para cobrança (CNAB/boleto/API) — card
        # "Cobranças" em Financeiro. Fase 1 (cadastro) + Fase 2a (motor CNAB
        # Bradesco), ver PENDENCIAS.md > "Bancos (Cadastro de Cobrança /
        # Boleto / CNAB)". Legado: FrmManBan.frm.
        _tela("BANCOS", "Cobranças", ACOES_BANCOS),
        # Ecossistema de cobranças — telas próprias baseadas em
        # frmrelbol4.frm/FrmImpRetBan.frm (Kontacto/Geral), ver
        # PENDENCIAS.md > "Geração de Boletos" / "Importação do Arquivo de
        # Retorno" pro rastreio completo.
        _tela("GERACAO_BOLETOS", "Geração de Boletos", ACOES_GERACAO_BOLETOS),
        _tela("RETORNO_BANC", "Importar Retorno", ACOES_RETORNO_BANC),
    ]),
    # Aba de topo própria (igual Financeiro), só visível no web e com o
    # módulo "Posto" ligado (controle_configuracao.Posto — ver
    # controle_config_service.CAMPOS). Correção 2026-07-13: a pasta VB6
    # legada "Posto" (C:\Desenv\VB6\...\SQLSERVER\Posto) TEM sim telas
    # exclusivas do segmento (achado anterior estava errado) — as 13
    # abaixo vêm de lá (frmcadbom, frmmovbomba, FrmBaiABc2, FrmFecTurno,
    # FrmReaTurno, frmcadmet, FRMMANCOM, frmmanest, frmmancus, frmmanilha,
    # frmmantan, frmmantes, frmmantnf). Nenhuma foi migrada ainda nesta
    # rodada — só a estrutura do painel (cards + permissão + gating de
    # módulo); cada BOTAO abaixo existe pra já habilitar o gating por
    # tela assim que a tela real for construída (ver PENDENCIAS.md).
    _menu("POSTO", "Posto de Combustível", [
        _tela("POSTO_BOMBA", "Bombas"),
        _tela("POSTO_ENCERR", "Mov. Encerrantes"),
        _tela("POSTO_AFERICAO", "Aferições/Despesas"),
        _tela("POSTO_FEC_TURNO", "Fechamento Turno"),
        _tela("POSTO_REA_TURNO", "Reabertura Turno"),
        _tela("POSTO_META", "Metas Combustível"),
        _tela("POSTO_COMBUST", "Combustíveis"),
        _tela("POSTO_ESTOQUE", "Estoque Combustível"),
        _tela("POSTO_CUSTO", "Custo Combustível"),
        _tela("POSTO_ILHA", "Ilhas"),
        _tela("POSTO_TANQUE", "Tanques"),
        _tela("POSTO_TQ_EST", "Tanque/Estoque"),
        _tela("POSTO_TQ_NF", "Tanque/Nota Fiscal"),
    ]),
    # Cilindros — módulo de segmento (indústria/locação de gás), gated por
    # controle_configuracao.Cilindro (já existia essa coluna antes desta
    # migração). Legado: FrmManCil.frm, ver PENDENCIAS.md > "Cilindros"
    # pro rastreio completo. Fase 1 (2026-07-14): só CILINDRO (Cadastro/
    # Consulta) tem tela real; as demais entram no catálogo desde já pra
    # não precisar renumerar depois, mas ainda não têm frontend.
    _menu("CILINDRO", "Cilindros", [
        _tela("CILINDRO", "Cad. de Cilindros"),
        _tela("CIL_CLIENTE", "Clientes x Cilindro"),
        _tela("CILINDRO_SERIE", "Cilindro/Nº Série"),
        _tela("VIAGEM", "Viagens", ACOES_VIAGEM),
        _tela("BORDERO_CIL", "Borderô de Cilindros"),
    ]),
    _menu("GERENCIAL", "Gerencial", [
        _tela("GERENCIAL", "Painel Gerencial", [
            ("TOTAIS", "Ver totais do dia"),
            ("MARGEM", "Ver margem média"),
            ("DESCONTOS", "Ver descontos concedidos"),
            ("TODOS_VEND", "Ver todos os vendedores"),
        ]),
        # Movido de "Compra" pra "Gerencial" 2026-07-21, user-directed —
        # "apesar de ser de compras, essa permissão tem que estar no
        # gerencial, pois é lá que aparecem os cards" (o card em si vive na
        # Tela Principal, junto do Painel Gerencial acima, não numa tela de
        # Gestão de Compras). Mudar só a posição no catálogo não afeta
        # nenhuma concessão já feita — a chave da tela continua
        # "ALERTAS_ESTOQUE", só o menu que a agrupa mudou.
        _tela("ALERTAS_ESTOQUE", "Alertas de Estoque", ACOES_ALERTAS_ESTOQUE),
    ]),
    _menu("RELATORIOS", "Relatórios", [
        _tela("REL_PEDIDOS", "Relatório de Pedidos"),
        _tela("REL_DESCONTOS", "Descontos & Margem"),
        _tela("REL_OS", "Relatório de OS"),
        _tela("REL_CAIXA", "Fechamento de Caixa"),
        _tela("REL_CX_ANALIT", "Caixa Analítico"),
    ]),
    _menu("CONFIG", "Configurações", [
        _tela("CONEXAO", "Conexões"),
        _tela("PERFIL_USUARIO", "Perfil de Usuário"),
        _tela("LOG_AUDITORIA", "Log de Auditoria", [("ABRIR", "Abrir Tela")]),
        _tela("CTRL_SISTEMA", "Controle do Sistema", [
            ("ABRIR", "Abrir Tela"), ("GRAVAR", "Gravar"),
            # Um botão por aba — controla a visibilidade de cada aba dentro da
            # tela (não só o acesso à tela como um todo). A aba "Kontacto" não
            # entra aqui: é liberada só pro usuário Master, hardcoded no
            # frontend (`isMaster`), não por permissão de grupo.
            ("EMPRESARIAL", "Aba Empresarial"), ("MOVIMENTACOES", "Aba Movimentações"),
            ("DIVERSOS", "Aba Diversos"), ("FISCAL", "Aba Fiscal"), ("OUTROS", "Aba Outros"),
            ("FINANCEIRO", "Aba Financeiro"), ("CONTRATOS", "Aba Contratos"),
        ]),
    ]),
]


# ---------------- DB ----------------
def tem_permissao(cur, classe: int, tela: str, comando: str) -> bool:
    """True se existe a linha (classe, sistema=50, tela, comando) em `permissoes`.
    Usa um cursor já aberto (mesma transação)."""
    cur.execute(
        "SELECT TOP 1 1 AS ok FROM permissoes "
        "WHERE sistema=%s AND classe=%s AND tela=%s AND comando=%s",
        (SISTEMA, classe, tela, comando),
    )
    return cur.fetchone() is not None


def _list_classes_sync(servidor: str, banco: str) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("SELECT codigo, classe FROM classes_usuarios ORDER BY classe")
        items = [
            {"codigo": int(r["codigo"]), "classe": (r.get("classe") or "").strip()}
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _list_permissoes_sync(servidor: str, banco: str, classe: int) -> dict:
    try:
        conn = _open_conn(servidor, banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}", "items": []}
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute(
            "SELECT tipo, tela, ISNULL(comando,'') AS comando "
            "FROM permissoes WHERE sistema = %s AND classe = %s",
            (SISTEMA, classe),
        )
        items = [
            {
                "tipo": (r.get("tipo") or "").strip(),
                "tela": (r.get("tela") or "").strip(),
                "comando": (r.get("comando") or "").strip(),
            }
            for r in cur.fetchall()
        ]
        cur.close()
        conn.close()
        return {"success": True, "items": items}
    except Exception as e:
        try:
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro: {e}", "items": []}


def _salvar_sync(payload: SalvarPermissoesRequest) -> dict:
    try:
        conn = _open_conn(payload.servidor, payload.banco)
    except Exception as e:
        return {"success": False, "message": f"Falha conexão: {e}"}
    try:
        cur = conn.cursor()
        # Estratégia idempotente: limpa as permissões desta classe/sistema e
        # reinsere apenas as marcadas (presença = permitido).
        cur.execute(
            "DELETE FROM permissoes WHERE sistema = %s AND classe = %s",
            (SISTEMA, payload.classe),
        )
        for it in payload.itens:
            cur.execute(
                "INSERT INTO permissoes (classe, nome, tipo, sistema, tela, comando, FORMULARIO) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    payload.classe,
                    (it.nome or "")[:20],
                    (it.tipo or "")[:5],
                    SISTEMA,
                    (it.tela or "")[:15],
                    (it.comando or "")[:15],
                    (it.formulario or it.tela or "")[:30],
                ),
            )
        conn.commit()
        gravadas = len(payload.itens)
        cur.close()
        conn.close()
        return {"success": True, "message": f"{gravadas} permissão(ões) salva(s).", "total": gravadas}
    except Exception as e:
        try:
            conn.rollback()
            conn.close()
        except Exception:
            pass
        return {"success": False, "message": f"Erro ao salvar: {e}"}


async def list_classes(servidor: str, banco: str) -> dict:
    return await asyncio.to_thread(_list_classes_sync, servidor, banco)


async def list_permissoes(servidor: str, banco: str, classe: int) -> dict:
    return await asyncio.to_thread(_list_permissoes_sync, servidor, banco, classe)


async def salvar_permissoes(payload: SalvarPermissoesRequest) -> dict:
    return await asyncio.to_thread(_salvar_sync, payload)


# ---------------- Filtro por módulos (controle_configuracao) ----------------
def disabled_telas(flags: dict) -> set:
    """Telas desligadas por módulo (flag controle_configuracao = False)."""
    from services.controle_config_service import MODULE_TELAS

    disabled = set()
    for modulo, telas in MODULE_TELAS.items():
        if not flags.get(modulo, False):
            disabled.update(telas)
    # Ordem de Serviço (Mobile e Completa): habilitada se Oficina OU
    # Assistência estiver ligada — nenhuma das duas telas de O.S. deve
    # aparecer (nem pra grupo, nem pra master) se ambos os módulos
    # estiverem desligados. [GLOBAL], 2026-07-15, user-directed.
    if not (flags.get("Oficina", False) or flags.get("Assistencia", False)):
        disabled.add("OS")
        disabled.add("OS_COMP")
        # Envio para Terceiros (RETIFICA) é sempre vinculado a uma O.S. —
        # mesmo gating. 2026-08-01, user-directed.
        disabled.add("RETIFICA")
    # Pedido Geral (PEDIDO_COMP): habilitado se QUALQUER UM dos 3 segmentos
    # não-Bar/não-Cilindro estiver ligado — Pedido de Venda (padrão), Metro
    # Quadrado ou Clínica (os 3 são variações da MESMA tela "Pedido Geral",
    # ver SEGMENTOS_PEDIDO_EXCLUSIVOS em controle_config_service.py). O loop
    # acima só sabe fazer "E" (desliga se QUALQUER módulo mapeado estiver
    # off) — como só "Pedido_venda" está mapeado pra PEDIDO_COMP em
    # MODULE_TELAS, essa correção reabre a tela quando é Metro Quadrado ou
    # Clínica que está ligado em vez de Pedido_venda. [GLOBAL], 2026-07-27,
    # user-directed.
    if flags.get("metro_quadrado", False) or flags.get("CLINICA", False):
        disabled.discard("PEDIDO_COMP")
    return disabled


def _sort_key(nome: str) -> str:
    """Chave de ordenação sem acentos (NFKD + drop de combining marks), para que
    'Área' ordene junto de palavras com A, e não depois de Z — .lower() sozinho
    compara por code point e erra acentuação (á = U+00E1 vem depois de todo ASCII)."""
    norm = unicodedata.normalize("NFKD", nome or "")
    return "".join(c for c in norm if not unicodedata.combining(c)).lower()


def sort_catalogo(nodes: list) -> list:
    """Ordena Menus e Telas alfabeticamente (por `nome`), nível a nível, preservando
    a hierarquia pai/filho. Os botões de ação de cada tela (children de uma TELA)
    mantêm a ordem de fluxo de trabalho declarada (Abrir, Gravar, Excluir, Imprimir,
    Exportar / ordem custom de Pedido e O.S.) — não são alfabetizados."""
    out = []
    for n in sorted(nodes, key=lambda x: _sort_key(x["nome"])):
        node = dict(n)
        if node.get("tipo") == "MENU" and node.get("children"):
            node["children"] = sort_catalogo(node["children"])
        out.append(node)
    return out


def filter_catalogo(disabled: set) -> list:
    """Remove telas desligadas; menus que ficam sem telas também somem."""
    out = []
    for menu in CATALOGO:
        telas = [t for t in menu["children"] if t["tela"] not in disabled]
        if telas:
            novo = dict(menu)
            novo["children"] = telas
            out.append(novo)
    return out
