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
    # entre botões distintos). Só no Pedido Bar, mesmo escopo Bar-only do
    # TX_SERVICO/ENTREGUE abaixo — não trazido pro ACOES_PEDIDO_COMP
    # (Comanda é conceito exclusivo do segmento Bar).
    ("FATURAR", "Faturar pedido"),
    # Botão "Forma de Pagamento" (FrmForPag.frm) — tela genérica no legado,
    # reaproveitada por Pedido Bar/Completo e O.S. (confirmado pelo usuário
    # 2026-07-16). Permissão própria, mesmo raciocínio do FATURAR acima.
    ("FORMA_PAG", "Forma de pagamento"),
    # Botão "Imprimir Pedido" (FrmManPedBar.frm, Command10_Click/
    # Pedido_48_COL) — recibo estilo térmico, só no Pedido Bar (formato de
    # impressão próprio do segmento, não trazido pro ACOES_PEDIDO_COMP).
    ("IMPRIMIR", "Imprimir pedido"),
    # Botão "Imprimir Item" (FrmManPedBar.frm, Command62_Click) — ticket de
    # um item só (sem preço/total), pra cozinha/bar. Botão em cada linha da
    # lista de itens, sempre disponível (não depende de haver impressora
    # configurada por Finalidade — isso só decide o disparo AUTOMÁTICO ao
    # incluir o item, que reaproveita esta mesma permissão de ADD_ITEM, não
    # uma nova). Permissão própria, mesmo raciocínio do IMPRIMIR acima —
    # só no Pedido Bar.
    ("IMPRIMIR_ITEM", "Imprimir item"),
    # Botão "Anexo" (Gestor de Documentos) — entre "Faturar Pedido" e
    # "Imprimir" na toolbar (pedido explícito do usuário, 2026-07-16). Pedido
    # não é entidade principal do Gestor de Documentos — grava como anexo do
    # Cliente (cod_grupo=1), sub-grupo "Pedidos de Venda" (cod_sub_grupo=2)
    # + referencia=pedido, ver AnexosPedidoModal.tsx. Só no Pedido Bar por
    # ora (mesmo escopo Bar-only do IMPRIMIR/IMPRIMIR_ITEM acima) — trazer
    # pro ACOES_PEDIDO_COMP/ACOES_OS é trabalho futuro, não pedido ainda.
    ("ANEXOS", "Anexos"),
    # Botão "Reabrir" (FrmManPedBar.frm, `cmdReabrir_Click`) — entre
    # "Faturar Pedido" e "Anexo" na toolbar, ao lado de "Cancelar" (pedido
    # explícito do usuário, 2026-07-16). Só reabre pedido Fechado (F -> A) —
    # legado bloqueia Aberto/Cancelado/Faturado com a mesma mensagem, sem
    # senha de gerente (diferente do Cancelar). Reverte a baixa de estoque
    # do Fechar. Permissão própria, mesmo raciocínio do CANCELAR abaixo.
    ("REABRIR", "Reabrir pedido"),
    # Botão "Cancelar Pedido" (FrmManPedBar.frm, Command9_Click) — entre
    # "Faturar Pedido" e "Imprimir" na toolbar (pedido explícito do usuário,
    # 2026-07-16). Legado exige senha de gerente antes de cancelar; esta
    # migração usa permissão de grupo própria no lugar (mesmo raciocínio do
    # FATURAR acima — cada botão real da tela com seu checkbox, não
    # reaproveita SITUACAO). Só no Pedido Bar por ora.
    ("CANCELAR", "Cancelar pedido"),
    # Botão "Dividir Pedido" — funcionalidade NOVA, sem precedente no legado
    # (pesquisado em toda a árvore VB6, nenhum "Dividir/Separar Conta"
    # existe). Divide um pedido Aberto em 2+ pedidos novos, cada um com um
    # subconjunto dos itens (quantidade inteira ou fracionária, pra dividir
    # o valor de um item indivisível entre várias pessoas), todos sob o
    # mesmo cliente (Mesa/Comanda). Pedido explícito do usuário, 2026-07-17
    # — ver `_dividir_pedido_sync` em pedidos_service.py. Só no Pedido Bar.
    ("DIVIDIR", "Dividir pedido"),
    # Botão "Incluir Tx Serviço" (FrmManPedBar.frm) — só no Pedido Bar, não
    # trazido pro ACOES_PEDIDO_COMP (feature do segmento Bar, sem
    # equivalente no Pedido de Venda geral).
    ("TX_SERVICO", "Taxa de serviço"),
    # Checkbox "Pedido Entregue" (FrmManPedBar.frm, Check88) — grava direto
    # no clique, mesmo escopo Bar-only do TX_SERVICO acima.
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
]

# Ações da tela de Manutenção de Viagens (módulo Cilindros — FrmManViagens.frm).
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


# Ações da tela "Pedido Completo" (frmmanpedfor.frm, Fase A — núcleo:
# cabeçalho + grade de itens + Fechar/Cancelar). Mesmo vocabulário de
# comando de ACOES_PEDIDO (pré-venda rápida) para não duplicar sentido —
# "SITUACAO" cobre Fechar e Cancelar (mesma máquina de estados, mesmo
# raciocínio de "Alterar situação" único já usado lá). WHATSAPP/DESC_ITEM/
# DESC_GERAL/VER_DESCONTOS/ANALISE trazidos 2026-07-15 (pedido explícito do
# usuário, "aplicar os recursos do Pedido Mobile no Pedido Completo") —
# mesma lista de ACOES_PEDIDO, os endpoints/telas por trás são genéricos
# (chave é o `pedido`, não a tela que criou o registro). Ações das fases
# C-F ainda não trazidas (Promoção, Fiscal, Faturar/Fatura Parcial, Tray).
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
]


# Ações da tela de CFOP: além do padrão, o botão que abre o modal de
# "Vínculos de CFOP das NFe's importadas por XML" (tabela `cfop_xml`) tem
# permissão própria — é uma sub-funcionalidade separada dentro da mesma tela.
ACOES_CFOP = ACOES_PADRAO + [
    ("VINCULOS_XML", "Vínculos XML"),
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
        ]),
    ]),
    _menu("TRANSACOES", "Transações", [
        _tela("PEDIDO", "Pedido Bar", ACOES_PEDIDO),
        _tela("OS", "OS Mobile", ACOES_OS),
        _tela("PEDIDO_COMP", "Pedido Completo", ACOES_PEDIDO_COMP),
        _tela("OS_COMP", "O.S. Completa"),
    ]),
    _menu("FINANCEIRO", "Financeiro", [
        _tela("CONTAS_PAGAR", "Contas a Pagar"),
        _tela("CONTAS_RECEBER", "Contas a Receber"),
        _menu("FLUXO_CAIXA", "Fluxo de Caixa", [
            _tela("PLANO_CONTAS", "Plano de Contas"),
            _tela("CENTRO_CUSTO", "Centro de Custo"),
        ]),
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
