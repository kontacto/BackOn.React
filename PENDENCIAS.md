# Pendências de Migração

Formato e processo definidos em `promptPendencias.md` (seção 10 — "Gestão de
pendências entre telas"). Ao retomar uma tela listada aqui, ler a seção
inteira antes de continuar — não reanalisar do zero.

---

## Fechamento de Caixa

**Status: 🟢 implementado (2026-07-16)**, com uma correção de arquitetura
importante e algumas simplificações conscientes — ler esta seção inteira
antes de retomar. Migrado de `frmFechaCaixa.frm` (Kontacto, colado
completo pelo usuário nesta sessão). Card novo no grupo **Caixa** de
Relatórios (`app/(tabs)/relatorios.tsx`).

### Achado de arquitetura (o motivo pelo qual a leitura NÃO usa comanda_*)

O `.frm` original lê os lançamentos de forma de pagamento das tabelas
`comanda_dinheiro`/`comanda_cheque`/`comanda_cartao`/`comanda_debito`/
`comanda_duplicata`/`comanda_vale`/`comanda_ticket`/`comanda_financiado` —
populadas pela rotina completa de fechamento de caixa do PDV do legado
(`GeraComanda`). **Esta migração não grava nessas tabelas.** O Faturar
Pedido (`pedidos_service._faturar_pedido_sync`, ver seção "Pedido Bar"
abaixo) grava a forma de pagamento em `pedido_venda_dinheiro`/
`pedido_venda_cheque`/etc. — o mesmo esquema genérico de `DavPagamento` já
usado pela feature "Forma de Pagamento" (`pedido_common.py`). Se este
relatório tivesse sido portado lendo `comanda_dinheiro`/etc. ao pé da
letra, ele voltaria **sempre vazio** pra qualquer comanda gerada por este
app — um bug silencioso, não um "relatório vazio porque não há
movimento".

Corrigido consultando `pedido_venda_*`/`os_*` (via `COMANDA_PED`/
`comanda_os`, as tabelas de vínculo comanda→documento — ambas existem no
schema, confirmadas ao vivo) em vez de `comanda_*`. Ver a docstring de
`backend/services/fechamento_caixa_service.py` pro detalhe completo.
`COMANDA_PED`/`comanda_os` também confirmam que uma comanda pode vir tanto
de Pedido quanto de O.S. — a agregação faz `UNION ALL` das duas fontes por
tabela de forma de pagamento (hoje só Pedido Bar gera comandas de verdade;
o Faturar de O.S. com Comanda ainda não existe, ver "Transações" — mas a
query já cobre o dia em que existir, sem precisar reescrever).

### Simplificações conscientes em relação ao legado

1. **Sem "Empresas" (Filial/multi-banco).** O legado tem um combobox pra
   trocar de banco de dados dentro da mesma tela (`Filial`/
   `FiliaisConsulta`/`VetorPathBancos` — suporte a múltiplas filiais como
   bancos SQL Server fisicamente separados). Este app opera com **uma
   conexão (servidor+banco) por vez**, igual a toda outra tela migrada —
   não existe esse conceito em nenhum outro lugar (o relatório de Margem
   de Lucro é diferente: consolida MÚLTIPLAS conexões já salvas do
   usuário via `conexoes: list[dict]`, não troca de banco dentro da
   mesma sessão de tela). Não implementado — se um dia for pedido,
   reaproveitar o padrão de `margem_lucro_service.py` (lista de conexões
   vinda do frontend), não reinventar um `Filial` próprio.
2. **Sem "Impressora não fiscal".** O legado tem 2 formatos de impressão
   (`Imp_Fecha`/`Imp_Resumo` gráfico vs. `Relatorio_Nao_fiscal` condensado
   texto puro) — ambos native `Printer` do VB6. A impressão desta migração
   usa `expo-print`/`Print.printAsync` (mesmo padrão de
   `export-report.ts`/`export-margem-lucro.ts` — não o iframe custom do
   Pedido, ver `feedback_print_via_iframe_not_css_hide`), um único layout
   HTML. Checkbox não portado.
3. **Sem Troco/Gorjeta/Vale Devolução.** Nenhuma tela migrada grava
   `comanda_troco`/`comanda_gorjeta`/`vale_devolucao`/
   `comanda_vale_devolucao` ainda — portar a leitura sem nenhuma escrita
   correspondente só adicionaria seções sempre vazias no relatório. Se
   essas features forem migradas no futuro, revisitar esta tela pra somar
   essas 3 fontes de novo (a lógica de leitura do legado está documentada
   na íntegra no `.frm` original, `Imp_Resumo`/`FazTudo`, se precisar
   retomar).
4. **Sem o bloco `Select Case Combo1.ListIndex` de `cmdSelecionar_Click`**
   (monta uma `SqlStr` de listagem de Comanda por situação, casando
   erroneamente o índice do combobox de Atendente com uma situação de
   Comanda). Confirmado como **código morto** — essa `SqlStr` é montada
   mas nunca lida por `FazTudo` (que tem suas próprias queries
   independentes). Não é uma regra de negócio perdida.
5. **Área de Atuação sem escopo por usuário.** O legado restringe as
   opções do combo Área de Atuação às áreas do funcionário logado
   (`funcionarios_area_atuacao`, via `Retorna_Codigo_Func`) — só mostra
   todas se o funcionário não tiver nenhuma área vinculada. Esta migração
   mostra **todas as áreas pra qualquer usuário** (simplificação, não
   confirmada com o usuário) — pendência em aberto, não uma decisão
   definitiva. Se o controle de acesso por área for importante, revisitar
   com o usuário antes de generalizar esse padrão pra outras telas.

### Implementação

- **Backend**: `backend/services/fechamento_caixa_service.py` (novo) —
  `_resumo_forma_pagamento_sync` generaliza as 8 consultas quase-idênticas
  do legado num loop sobre `FORMA_PAG_SUFIXO_TIPO`/`FORMA_PAG_VALOR_COL`
  (já existentes em `pedido_common.py`, reaproveitados sem duplicar);
  `_entradas_saidas_sync` agrega `entrada_caixa`/`saida_caixa` (já
  gravadas pela tela "Entrada/Saída de Caixa" migrada) + `despesas`
  (tabela lida mas sem tela de cadastro migrada ainda, normalmente vazia).
  Marcação `(*)` (`forma_pagamento.nao_totaliza_caixa`) preservada — some
  do SUB TOTAL/TOTAL CAIXA mas aparece na lista, mesmo comportamento do
  legado. Filtro "Exibir Garantias" simplificado: em vez do padrão do
  legado (excluir a COMANDA inteira daquela tabela específica se ela tiver
  QUALQUER lançamento com a forma de pagamento marcada
  `FORMA_PAG_GARANTIA`), filtra a LINHA agregada diretamente
  (`fp.FORMA_PAG_GARANTIA=0`) — mesmo efeito prático pro caso comum (1
  forma por comanda), mais simples de ler/manter. Rota
  `GET /api/relatorios/caixa` em `routes/relatorios.py` (mesmo arquivo
  compartilhado de `/relatorios/pedidos`, `/relatorios/os`, etc.).
  Permissão nova `REL_CAIXA` (menu RELATORIOS, ações padrão). 13 testes
  novos (`test_fechamento_caixa_service.py`), 478 testes de backend
  passando.
- **Frontend**: `app/relatorio-caixa.tsx` (novo) — mesmo padrão visual de
  `relatorio-os.tsx`/`relatorio-descontos.tsx` (fetch cru, não
  `apiGet`/hook de pedido). Filtros: Data Inicial/Final, Atendente
  (opcional), Área de Atuação (opcional), checkboxes "Filtrar pelo
  atendente da comanda" e "Exibir Garantias". Dois cards de resultado
  ("Entradas e Saídas" e "Resumo", lado a lado no web). Botões Imprimir
  (`export-fechamento-caixa.ts`, `expo-print`) e Gerar Planilha
  (`export-xlsx.ts`, já usado no Borderô de Cilindros — 2 abas, uma por
  grid). Card "Fechamento de Caixa" adicionado ao grupo **Caixa** de
  `relatorios.tsx` (era o único grupo vazio até agora).

### Testado ao vivo (2026-07-16) — e um ajuste na Tela Principal na sequência

Validado contra uma conexão real com movimento de Pedido Bar faturado de
verdade — os números batem.

No processo, o usuário reportou o total do Fechamento de Caixa "não
bater" com a Tela Principal (filtro "Faturado", hoje). Investigação: as
duas telas usavam critérios de data diferentes —
**Fechamento de Caixa filtra por `comanda.data`** (dia em que o Faturar
foi clicado, réplica do "Comandas Emitidas em" do legado) enquanto **a
Tela Principal filtrava por `pedido_venda.data`** (dia de criação do
pedido) mesmo com o filtro "Faturado" selecionado — um pedido criado
ontem e faturado hoje não entrava no "hoje" da Tela Principal, mesmo o
Fechamento de Caixa (corretamente) contando esse dinheiro recebido hoje.

Usuário confirmou o cenário (tinha pedido assim) e pediu a correção:
`relatorios_service._dashboard_sync` agora usa `comanda.data` (via
`COMANDA_PED`) em vez de `pedido_venda.data` **só quando o filtro é
"Faturado"** — Aberto/Fechado/Cancelado continuam usando a data de criação
do pedido, confirmado explicitamente pelo usuário que essas não deveriam
mudar.

**Duas correções extras no mesmo dia** (usuário mandou outro print
mostrando Faturado R$886,70 > Todos R$371,70 — "não faz sentido"):

1. **"Todos" não unificava os critérios de data** — ficou menor que
   "Faturado" sozinho, porque continuava só em `pedido_venda.data` mesmo
   depois da correção acima. Corrigido pra usar uma condição de UNIÃO
   (`(situacao='PG' AND comanda.data=hoje) OR (situacao<>'PG' AND
   pedido_venda.data=hoje)`, via `LEFT JOIN`) — agora "Todos" é sempre
   ≥ qualquer situação isolada, como o usuário esperava.
2. **Pedido faturado sem forma de pagamento lançada some do Fechamento de
   Caixa em silêncio** — a diferença exata entre Fechamento de Caixa e o
   novo total "Faturado" era o valor de um pedido (#17606) com comanda mas
   ZERO linhas em qualquer uma das 8 tabelas `pedido_venda_*` (fechado
   antes de `_fecha_fpag_dav` existir nesta migração, provavelmente).
   Corrigido: `fechamento_caixa_service._pedidos_faturados_sem_forma_pagamento_sync`
   detecta esses casos (8 `NOT EXISTS`, um por tabela) e o relatório agora
   mostra um card de alerta amarelo com a lista + total, tanto na tela
   quanto na impressão e na planilha — em vez de sumir sem explicação.

10 testes novos no total (`test_relatorios_dashboard.py` +
`test_fechamento_caixa_service.py`), 488 testes de backend passando.
Backend reiniciado, mudanças já ao vivo. Ver memória
`project_fechamento_caixa.md` pro detalhe completo.

---

## Cilindros

**Status: 🟢 implementado (2026-07-14)** — Fase 1 (Cadastro/Consulta de
Cilindros), Fase 2 (Clientes x Cilindro, Cilindro/Nº Série), Fase 3a/3b
(Manutenção de Viagens — cabeçalho, itens, Fechar Saída/Entrada, Reabrir,
Cancelar, Renumerar) e Fase 3c (Borderô de Cilindros) concluídas — módulo
completo. Módulo de segmento (indústria/locação de gás — a lista de
fabricantes já cadastrada
em GERDELL/BARESTELA, AGA/CILBRAS/WHITE MARTINS/etc., confirma que este é
um cliente real do segmento), gated pela coluna já existente
`controle_configuracao.Cilindro` (mesmo mecanismo de Posto/Serviços — ver
`MODULE_TELAS` em `controle_config_service.py`). Fontes VB6: `FrmManCil.frm`
e `FrmManViagens.frm` (ambos colados completos pelo usuário nesta sessão,
não precisou buscar na árvore).

### O que já foi feito (Fase 1)

- Backend: `backend/services/cilindro_service.py` (CRUD completo em
  `Cilindro` — `_grupo_gas_de`/`_garantir_grupo_gas_sync` derivam e
  auto-criam o Grupo Gás a partir do `codigo`, mesmo comportamento do
  legado `Campo_LostFocus(78)`; `_save_cilindro_sync` valida produto via
  `Pecas.codigo_fab` e padrão via `Cilindro_Fabricante.fabricante`, e
  bloqueia duplicidade pela COMBINAÇÃO codigo+capacidade+pressao+padrao —
  regra real do legado `Command1_Click`, não um código único simples;
  `_delete_cilindro_sync` bloqueia exclusão com vínculo em
  `Cilindro_Cliente`/`Cilindro_Serie`/`Viagem_Cilindro`/pedido de venda
  aberto/fechado, espelhando `Command3_Click`), `backend/routes/
  cilindro.py`. Lookup novo `GET /api/cilindro-fabricante` (combo Padrão,
  PK `fabricante`) e `GET /api/cilindros/produto/{codigo_fab}` (validação
  no lostfocus do Produto de Venda). Permissão `CILINDRO` (+ `CIL_CLIENTE`,
  `CILINDRO_SERIE`, `BORDERO_CIL` reservadas pras próximas fases) no novo
  menu `CILINDRO` do catálogo, com `MODULE_TELAS["Cilindro"]` cobrindo as 4.
- Frontend: novo item de menu "Cilindros" nas abas (web-only, gated por
  `moduleOn("Cilindro")` — `app/(tabs)/_layout.tsx`), `app/(tabs)/
  cilindros.tsx` (Painel de Cilindros, só o card "Cadastro de Cilindros"
  visível por ora — os outros entram nas próximas fases), `app/
  cilindro-cadastro.tsx` (lista + formulário compacto sem abas, mesmo
  padrão de `fornecedores.tsx` — o legado também não tem controle de abas
  nesta tela).
- Testes unitários: `backend/tests/unit/test_cilindro_service.py` (15
  testes — derivação de grupo gás, validações, save com produto/padrão
  inexistente, duplicidade, criação nova, guard de exclusão por
  dependência, lookup de produto). Round-trip completo (create→get→
  update→duplicidade→delete) validado ao vivo contra GERDELL/BARESTELA,
  incluindo limpeza do `Cilindro_Grupo` auto-criado como efeito colateral
  do teste (não é cascade-deletado — comportamento correto/esperado, só
  precisou limpeza manual do artefato de teste).

### Não replicado (truque VB6, não regra de negócio)

- `temp_cilindros_<nome_do_computador>` — tabela temporária por máquina
  usada no legado só pra fazer agregação (equivalente a um `GROUP BY`
  manual, workaround de uma era sem essa capacidade fácil em Access/DAO).
  Quando o Borderô (Fase 3) precisar de totais por status, usar `GROUP BY`
  real — não replicar a tabela temp.
- `AtualizaCilindros` / tabela `Lista_Cilindros` — rotina de importação em
  massa (utilitário, não regra de negócio do cadastro em si). Fora de
  escopo da migração por ora.

### Dúvidas já resolvidas nesta sessão

- Borderô de Cilindros (Fase 3): usuário confirmou, via pergunta direta,
  que o formato de saída deve ser **consulta em tela + exportação Excel**,
  não impressão formatada como o legado.

### Arquitetura confirmada (2026-07-14, `.frm` completo recolado pelo usuário)

`FrmManCil` é um **form único** — Clientes x Cilindro (`Frame3`), Cilindro/Nº
Série (`Frame4`), Consulta Cliente x Cilindro (`Frame7`), Consulta Cilindro x
Nº Série (`Frame8`) e Borderô de Cilindros (`Frame11`) são **frames ocultos
dentro do mesmo form**, abertos por botões da tela de Cadastro (`Frame1`):
`Command7` "Cliente/Cilindro", `Command8` "Cilindro/Nº Série", `Command29`
"Bordero Cliente" (abre `Frame11` direto, sem passar por consulta). Ou seja,
no legado **não são telas/menus separados** — são popups da própria tela de
Cadastro/Consulta. Confirmado pelo usuário 2026-07-14 ("essa tela tem botões
desses modais").

**Consequência pra migração**: não criar tiles novos no hub `cilindros.tsx`
para Fase 2/3. Em vez disso, adicionar botões em `cilindro-cadastro.tsx` que
abrem **slide modals** (mesmo padrão `compactWeb` de `NiveisModal.tsx`/
Fornecedores "Caixa/Contabilidade" — ver "Modal/Selector Standard (Web)" e
"Secondary sections that are separate Frames/popups" em CLAUDE.md > "Full
CRUD Form Screen Standard"), não novas rotas/hub tiles. Os `BOTAO`s de
permissão `CIL_CLIENTE`/`CILINDRO_SERIE`/`BORDERO_CIL` já reservados no
catálogo continuam corretos — cada modal ainda é uma "tela" para fins de
permissão/log de auditoria, só não é uma rota própria.

### Fase 2 — rastreio campo-a-campo (concluído e implementado, 2026-07-14)

**Implementado como popups da tela de Cadastro** (`cilindro-cadastro.tsx`),
não como telas/rotas próprias — ver "Arquitetura confirmada" acima:
- Backend: `backend/services/cilindro_cliente_service.py` +
  `backend/services/cilindro_serie_service.py`, rotas em
  `backend/routes/cilindro.py` (`/api/cilindro-cliente`,
  `/api/cilindro-serie`), log de auditoria em `CIL_CLIENTE`/`CILINDRO_SERIE`.
  **Diferença deliberada em relação ao legado**: os dois serviços recebem o
  `cod` do Cilindro já resolvido (picker reaproveitando
  `cilindro_service.list_cilindros`), em vez de resolver por
  código+capacidade+pressão+padrão digitados à mão — o legado não tinha
  picker, esta migração já tem.
- Frontend: dois botões no cabeçalho de `cilindro-cadastro.tsx`
  ("Cliente/Cilindro", "Cilindro/Nº Série") abrem slide modals
  (`compactWeb`), cada um com busca/lista + formulário + picker de
  Cliente/Cilindro/Fornecedor compartilhados (reaproveitam
  `/api/clientes/find/search`, `/api/cilindros`, `/api/fornecedores`).
- Testes unitários: `backend/tests/unit/test_cilindro_cliente_service.py`
  (7 testes) e `test_cilindro_serie_service.py` (11 testes) — todos verdes
  junto com os 15 da Fase 1 (37 no total).
- **Não implementado** (fora de escopo, não regra de negócio): o botão
  "Excluir" de `Frame4`/`Command20` não foi decompilado em detalhe no
  `.frm` — a exclusão de Cilindro/Nº Série replicada aqui segue o mesmo
  padrão trivial de delete por `codigo` usado no resto do módulo, com
  bloqueio se houver `Viagem_Cilindro.num_serie_retorno` vinculado (tabela
  ainda vazia neste banco de teste, guard nunca disparado na prática ainda).

**Clientes x Cilindro (`Frame3`, tabela `Cilindro_Cliente`)**:
- Campos: código/capacidade/pressão/padrão do cilindro (`Campo(27/28/31/29)`,
  mesma busca por combinação já usada no Cadastro — resolve `Cilindro.Cod`
  em `Campo(32)`, oculto) + cliente (`Campo(33)`, aceita código ou CGC/CPF,
  resolve nome).
- **Gravar** (`Command14`): valida que a combinação do cilindro existe (erro
  "Código do Cilindro Não Cadastrado" senão) e que o cliente existe (erro
  "Cliente não Cadastrado" senão); só então checa se o par
  `(Cliente, Cilindro)` já existe em `Cilindro_Cliente` — se não existir,
  insere; **se já existir, não faz nada** (não há update, é só
  existência do vínculo, sem colunas adicionais). Regra real: o par é único,
  nunca duplicar.
- **Excluir** (`Command16`): remove a linha exata `(Cliente, Cilindro)`.
- **Consulta/Grid** (`Command7` ao abrir, `Grid_Cil_Cli`): lista todos os
  vínculos via `JOIN Cilindro_Cliente, Cilindro, Cliente`.
- Este é exatamente o vínculo que a análise anterior (seção "Pedido de
  Cilindro — Unificação com Pedido de Venda Geral") identificou como
  auto-criado por `FrmPedCil` na primeira venda — a tela aqui é a via manual
  de cadastro do mesmo vínculo.

**Cilindro/Nº Série (`Frame4`, tabela `Cilindro_Serie`)**:
- Chave: `Numero_De_Serie` (`Campo(39)`). Campos do cilindro pai (código/
  capacidade/pressão/padrão, `Campo(30/34/36/35)`) resolvem `Cilindro.Cod`
  (`Campo(47)`) pela mesma combinação de sempre.
- Datas: `data_compra`, `nf_compra`+`fornecedor`, `fabricacao`, `entrada`
  (última entrada), `saida` (última saída), `revisao` (última revisão).
- **Regra real**: `Prazo_Revisao` (anos, vem do cadastro do `Cilindro` pai) +
  `revisao` (última revisão) calcula automaticamente `Campo(69)` = previsão
  da próxima revisão (`DateAdd("Y", Prazo_Revisao, revisao)`) — manutenção
  preventiva agendada por unidade serializada.
- `Carga` (Cheio/Vazio) e `Destino` (Cliente/Fornecedor, `Campo(38)` código
  do destino, `0` = "Pátio"/estoque próprio) — situação física atual da
  unidade.
- `Situacao` (`Campo(48)`, valida contra tabela `Situacao` — a mesma tabela
  genérica de situação já usada em Cliente, não uma tabela dedicada).
- **Gravar** (`Command22`): cadeia de validação (produto/capacidade/pressão/
  padrão → cilindro existe; datas válidas; situação válida; carga e destino
  preenchidos) então insert/update em `Cilindro_Serie`.
- **Excluir** (`Command20`, não decompilado em detalhe — mesmo padrão trivial
  de delete por `Codigo`, revisar se necessário ao implementar).

### Fase 3 — Borderô de Cilindros: dependência RESOLVIDA (2026-07-14)

O Borderô (`Frame11` de `FrmManCil`) é um **relatório de consulta** sobre
`Viagem`/`Viagem_Cilindro`/`Viagem_Retorno` — tabelas de rastreamento de
viagens/remessas que não são criadas em nenhum botão de `FrmManCil` nem de
`FrmPedCil`. **Achada a tela de origem**: `FrmManViagens.frm`
("Manutenção de Viagens...", colada pelo usuário 2026-07-14) — é ela quem
grava `Viagem`/`Viagem_Cilindro`/`Viagem_Retorno`, e por isso é
**pré-requisito da Fase 3**, não a própria Fase 3.

#### Rastreio de `FrmManViagens` (Manutenção de Viagens)

**Cabeçalho da Viagem** (tabela `Viagem`): `codigo` (PK, autonumber),
`veiculo` (FK `veiculos_transp`), `motorista`/`ajudante` (FK `funcionarios`),
`tipo_viagem` (0=Normal, 1=Fábrica — decide se destino é Cliente ou
Fornecedor em toda a tela), `descricao`/`obs` (texto livre), `saida`/
`hora_saida`/`km_saida`, `retorno`/`hora_retorno`/`km_retorno`,
`saida_fechada`/`entrada_fechada` (bits de trava), `situacao`
(`A`=Aberta/`F`=Fechada/`C`=Cancelada).

- **Gravar Dados da Viagem** (`Command1`): cria nova viagem (situação=Aberta)
  ou atualiza a existente — mas só atualiza os campos de saída se
  `saida_fechada=0`, e só os de retorno se `entrada_fechada=0` (trava
  progressiva, mesmo princípio de "Saída Já Fechada"/"Entrada Já Fechada").

**Itens da Viagem** (tabela `Viagem_Cilindro`, grid "Itens inclusos nesta
viagem"): cada linha é um cilindro em trânsito, com dados de **saída**
(`doc_saida`+`tipo_doc_saida` 0=NF/1=Comanda/2=Pedido/3=Outros, `cliente`,
`cilindro`, `num_serie`, `status_saida`, `os_saida`, `carga_saida`,
`obs_saida`) e dados de **retorno** (`nf_retorno`, `cilindro_retorno`,
`num_serie_retorno`, `status_retorno`, `os_retorno`, `carga_retorno`,
`obs_retorno`) — os dois lados da mesma linha, preenchidos em momentos
diferentes (saída na criação, retorno depois). `ordem` é sequencial dentro
da viagem (`Command52` "Renumerar Itens" corrige buracos manualmente).

- **Status** (`Cilindro_Situacao`, tabela dedicada — não é a `Situacao`
  genérica): `LT` Livre Troca, `AP` Aplicação, `APT` Aplicação Temporária,
  `DP` Devolução de Propriedade, `DPT` Devolução Temporária, `DT` Devolução
  de Terceiros, `RT` Recolha de Terceiros, `CA` Cancelado. Cada código tem
  semântica de estoque própria — ver "Fechar Entrada" abaixo. **Confirmar
  com o usuário a tradução exata de cada um antes de implementar** (o `.frm`
  não documenta o significado de negócio, só o código de 2-3 letras — texto
  acima é inferido do padrão de uso no código, não confirmado).
- **Adicionar item manualmente** (`Command20`→`Frame5`, "Cadastrar Item
  Avulso"): formulário com lado Saída e lado Retorno lado a lado; resolve
  `Cilindro.Cod` por `codigo+capacidade+pressao+padrao` (mesmo padrão de
  sempre) e opcionalmente vincula/cria um `Cilindro_Serie` pelo número de
  série informado (`Command21_Click` — se o NDS não existe ainda para
  aquele cilindro, cria na hora). Válida O.S. obrigatória para status
  AP/APT/RT (Command21, ver nota sobre `ModPedido = 40` abaixo).
- **Adicionar itens de Pedidos** (`Command12`→`Frame3`, só p/ Tipo Normal):
  busca `Pedido_Venda`/`Pedido_Venda_Prod` com `area_venda<>0` (mesma
  convenção de `FrmPedCil` — `area_venda` = FK pro Cilindro) e replica cada
  item pedido em `Viagem_Cilindro`, status derivado de
  `pedido_venda_prod.comprimento` (1=AP,2=APT,3=DT,else=LT — **mesmo
  reaproveitamento de coluna genérica já identificado na análise do Pedido
  de Cilindro**, não replicar o campo `comprimento`, usar coluna própria).
  Marca `pedido_venda.despacho=1` pra não duplicar.
- **Adicionar itens do Pátio** (`Command30`→`Frame10`, só p/ Tipo Fábrica):
  lista cilindros com `cilindro_na_fabrica=0` (ver campo abaixo) filtrando
  por retorno pendente ou por vínculo direto `Cilindro_Serie.destino`, pra
  incluir na viagem como devolução (`LT`/`AP`).
- **Itens Avulsos de Entrada** (`Command54`→`Frame14`): fecha o retorno de
  itens que saíram em OUTRA viagem — busca por O.S. ou Nº de Série entre os
  itens com `status_retorno` já `AP`/`APT` e ainda sem `viagem_retorno`
  setado (`Viagem_Retorno.viagem_retorno = 0` = pendente), grava a baixa em
  `Viagem_Retorno`.
- **Alterar Cilindro** (`Command40`→`Frame11`): troca o cilindro de um item
  já lançado, só permitido se ainda não foi baixado (`Viagem_Retorno` sem
  vínculo) — também corrige `Contratos_Produtos.produto` se o item já tiver
  contrato de locação associado.
- **Excluir Item** (`Command29`): só permitido enquanto a Saída não estiver
  fechada (com uma exceção estranha no código para "Cilindro_1=0 e
  Cilindro_2<>0" — não fica claro no `.frm` o motivo exato dessa exceção,
  **dúvida em aberto**, não replicar sem entender).

**Fechar Saída** (`Command3`, tabela `Viagem`): trava `saida_fechada=1`.
Exige veículo, tipo de viagem, motorista, data/hora de saída preenchidos.
Para Tipo Normal, roda `AtualizaTipoDocSaida` — resolve pendências de NF
(um item pode ter sido lançado citando Comanda/Pedido antes da NF sair;
essa rotina promove pra NF real assim que existir, e **bloqueia o
fechamento se algum Pedido ainda não foi faturado** — regra real). Também
sincroniza `Cilindro_Serie.tipo_destino/destino` a partir do item da
viagem.

**Fechar Entrada** (`Command4`, o núcleo do módulo — motor de estoque +
contratos): valida data/hora de retorno preenchidas, roda um **motor de
críticas** (`GridCriticas`/`Frame9`) antes de permitir o fechamento —
bloqueia se: (a) algum item não teve o retorno confirmado/cancelado
(`cilindro_retorno=0`); (b) status `AP`/`APT` e Tipo Normal mas o cliente
não tem contrato ativo (`VerificaContratoCliente`); (c) status incompatível
entre saída e retorno (ex.: saiu como `DP`/`RT`/`DT`/`DPT` só pode retornar
com o mesmo status; saiu como `AP`/`LT`/`APT` só pode retornar como
`AP`/`APT`/`LT`); (d) uma devolução (`DP`/`DT`/`DPT`) não encontra a
aplicação/recolha em aberto correspondente pra baixar (join por
cliente+cilindro+combinação, e por O.S./Nº Série quando informado).

Só depois de passar todas as críticas, **por item, conforme o
`status_retorno`**:
- `AP`/`APT` (aplicação/aplicação temporária, Tipo Normal): cria/atualiza
  contrato de locação do cliente (`CadastraContratoCilindro` — cria
  `Contratos`+`Contratos_Produtos`+`Contratos_Centro_Custo` se necessário,
  ou reabre uma vaga existente sem `data_inicio`), marca
  `Cilindro_Serie.cilindro_na_fabrica=0`, `estoque -1` / `estoque_em_cliente
  +1`, registra a baixa como **pendente** em `Viagem_Retorno`
  (`viagem_retorno=0` até a devolução real acontecer).
- `DP`/`DPT` (devolução de propriedade): localiza a aplicação em aberto
  correspondente e marca `Viagem_Retorno.viagem_retorno` = esta viagem
  (baixa definitiva), `estoque +1` / `estoque_em_cliente -1`, encerra o
  contrato de locação (`EncerraContrato` — grava `data_encerramento`,
  deduz `valor_atual` do contrato e do centro de custo).
- `DT` (devolução de terceiros — Tipo Fábrica): `estoque -1` /
  `estoque_de_terceiro -1`, `cilindro_na_fabrica=1`, marca pendência em
  `Viagem_Retorno`.
- `RT` (recolha de terceiros — Tipo Fábrica): `estoque +1` /
  `estoque_de_terceiro +1`, `cilindro_na_fabrica=0`, localiza e baixa a
  devolução `DT` correspondente.
- `LT` (livre troca): só sincroniza `Cilindro_Serie` (`cilindro_na_fabrica`/
  `tipo_destino`/`destino`), sem efeito de estoque nem contrato.
- `CA` (cancelado): nenhum efeito.
- **Após todos os itens**: `Cilindro_Cliente` é auto-registrado
  (`CadCilCliente`, idêntico ao vínculo já implementado na Fase 2) para
  todo item com status ≠ `CA` em viagem Tipo Normal.

**Reabrir Saída ou Retorno** (`Command28`): reverte tudo o que "Fechar
Entrada" fez, item a item, seguindo a tabela de reversão por status (ex.:
`AP` reaberto → `cilindro_na_fabrica=0`→ vira 0 de novo? não, o código
inverte estoque `+1 em_cliente -1` voltando ao estado pré-fechamento) —
**bloqueia a reabertura se algum item já foi devolvido/baixado em viagem
posterior** (`viagem_retorno<>0`) ou (Tipo Normal) se o contrato já foi
faturado no mês da viagem (`comanda_contrato`/`contratos_produtos` join).

**Cancelar Viagem** (`Command31`): só permitido com saída ainda aberta;
marca `situacao='C'`, zera `cilindro_na_fabrica` dos itens e **apaga**
`Viagem_Cilindro` da viagem (delete físico, não soft-cancel dos itens).

#### Não replicar (truque VB6 / hardcode de cliente específico, não regra de negócio)

- `CodigoGuerengases` — no `Form_Load`, calcula um código de cliente a
  partir do nome fantasia da empresa ("GUEREN") e, na linha seguinte,
  **sobrescreve incondicionalmente para 0** (`CodigoGuerengases = 0`),
  tornando o cálculo anterior morto. Resíduo de uma instalação específica
  (empresa literalmente chamada "Gueren Gases"), não uma regra genérica —
  não portar.
- `EmpresaCusto` (0 ou 1, também derivado do nome fantasia "GUEREN") — usado
  só como fallback hardcoded de centro de custo (`1088`/`134`) dentro de
  `CadastraContratoCilindro` quando não existe config de centro de custo
  padrão (`Controle.tipo_mov_contrato_servico`). Não portar o hardcode
  específico — se a config padrão faltar, a migração deve **bloquear com
  mensagem clara** em vez de cair num centro de custo adivinhado.
- `ModeloPedido = 40` (de `Controle.modelo_pedido`, mesmo campo já visto em
  `FrmPedCil`) — usado em `Command21_Click` pra pular a validação de O.S.
  obrigatória nos status AP/APT/RT. Mesmo padrão já identificado antes:
  não portar como "número de modelo de impressão decidindo regra de
  negócio" — se a validação de O.S. é ou não obrigatória deve virar
  configuração explícita do módulo Cilindro, não um número de modelo de
  pedido herdado de outra tela.
- `temp_cilindros_<computador>` **não aparece aqui**, mas o mesmo princípio
  de "Não replicado" da Fase 1/2 continua valendo pro Borderô em si.

#### Dúvidas em aberto (não assumir, perguntar ao usuário antes de implementar)

1. Semântica exata de cada código de `Cilindro_Situacao`
   (LT/AP/APT/DP/DPT/DT/RT/CA) em português claro — a tradução acima foi
   inferida do padrão de uso no código-fonte, não confirmada.
2. A exceção em `Command29_Click` ("Cilindro_1 = 0 And Cilindro_2 <> 0")
   que permite excluir item mesmo com saída fechada — motivo real não claro
   no `.frm`.
3. Escopo do módulo de Contratos (`Contratos`/`Contratos_Produtos`/
   `Contratos_Centro_Custo`) — é uma tabela só de suporte ao módulo
   Cilindro (contrato de locação de cilindro) ou um módulo de Contratos
   mais amplo do sistema que também serve outros domínios? Isso muda se
   deve ser portado como parte do Cilindros ou como módulo próprio.
4. `Comanda`/`Comanda_Ped`/`Comanda_NF` (usadas em `AtualizaTipoDocSaida` e
   na consulta de contratos faturados) — módulo de "comanda" ainda não
   mapeado neste projeto; confirmar se é o mesmo conceito de comanda do
   módulo Bar (`FrmManPedBar`, ver "Pedido de Cilindro" acima) ou algo
   distinto.

#### Fase 3a/3b — implementadas (2026-07-14)

Usuário confirmou implementar tudo de uma vez (Fase 3a+3b juntas) e
confirmou a semântica dos status (LT/AP/APT/DP/DPT/DT/RT/CA) listada acima.
Schema conferido ao vivo contra GERDELL/BARESTELA antes de escrever o SQL
(agente em background) — nenhuma tabela faltando, nenhuma coluna usada
divergente do `.frm` (só PKs de tabelas de apoio nunca referenciadas
diretamente: `Viagem_Contrato.cod`, `Contratos_Centro_Custo.cc_auto`).

- Backend: `backend/services/viagem_service.py` (cabeçalho, itens — lado
  Saída via `add_item`/lado Retorno via `save_item_retorno`, delete,
  alterar cilindro, renumerar, Fechar Saída com `AtualizaTipoDocSaida`,
  Fechar Entrada com motor de críticas + reconciliação de estoque/
  contratos, Reabrir, Cancelar) + `backend/routes/viagem.py`. Permissão
  `VIAGEM` (tela "Manut. de Viagens", ações próprias
  `ADD_ITEM`/`DEL_ITEM`/`ALT_CILINDRO`/`FECHAR_SAIDA`/`FECHAR_ENTRADA`/
  `REABRIR`/`CANCELAR`/`EXPORTAR`) no menu `CILINDRO` do catálogo. Log de
  auditoria em todas as ações de escrita.
- Lookups novos: `GET /api/cilindro-situacao` (`lookups_service.
  list_cilindro_situacao`). Reaproveitados sem duplicar: `GET /api/veiculos`
  (já existia, tela própria de Cadastro de Veículos), `GET /api/veiculos/
  motoristas` e `/auxiliares` (já existiam, filtram por função "MOTORISTA"/
  "MOTORISTA AUXILIAR" — diferença deliberada do legado, que carrega todos
  os funcionários sem filtro nos dois combos; melhoria de UX, não altera
  regra de negócio), `GET /api/clientes/find/search`, `GET /api/fornecedores`,
  `GET /api/cilindros`.
- Frontend: `frontend/app/viagem-cadastro.tsx` (lista+form compacto sem
  abas) + card novo em `app/(tabs)/cilindros.tsx`. Modais: Adicionar Item,
  Registrar Retorno, pickers de Veículo/Cliente-Fornecedor/Cilindro
  (padrão `compactWeb` já usado no resto do projeto). Críticas do Fechar
  Entrada exibidas via `Alert` com a lista completa de mensagens.
- Testes unitários: `backend/tests/unit/test_viagem_service.py` (29
  testes) — 330 no total do backend, todos verdes.
- **Não implementado nesta rodada** (ver docstring de `viagem_service.py`):
  "Adicionar Pedidos" (inclusão em massa a partir de `Pedido_Venda`),
  "Adicionar Itens do Pátio" (só Tipo Fábrica), "Itens Avulsos de Entrada"
  (baixa de item de OUTRA viagem), impressão formatada (NF/relação de
  viagens/resumos), editar o lado Saída de um item já lançado (só
  Adicionar/Excluir — para corrigir, excluir e relançar enquanto a Saída
  não estiver fechada).
- **Diferenças deliberadas do legado** (gambiarra/hardcode de instalação
  específica, não regra de negócio — ver docstring completa em
  `viagem_service.py`): hardcode de empresa "Guerengases"/`EmpresaCusto`
  removido (bloqueia com mensagem se faltar config de centro de custo
  padrão); `ModeloPedido = 40` (gating por modelo de impressão) removido —
  O.S. sempre obrigatória p/ status AP/APT/RT; exclusão de item exige
  Saída não fechada, sem a exceção pouco clara do legado (dúvida #2 acima,
  não resolvida — não replicada por precaução); número de contrato
  atribuído por identity real, não por `MAX(codigo)+1` pré-calculado (o
  legado corre risco de concorrência que não existe numa instalação VB6
  single-user, mas existe nesta API multi-usuário).
- **Dúvidas #3 e #4 acima** (escopo do módulo Contratos e do módulo
  Comanda) ficaram sem resposta explícita do usuário — implementado
  assumindo que são tabelas de apoio específicas do fluxo de locação de
  cilindro (não um módulo próprio mais amplo), já que essa foi a única
  forma de fechar o motor de Fechar Entrada sem mais uma rodada de
  perguntas. Se essa suposição se provar errada quando o módulo de
  Contratos/Comanda for migrado de verdade, revisar `_cadastra_contrato_
  cilindro_sync`/`_encerra_contrato_sync`/`_atualiza_tipo_doc_saida_sync`
  em `viagem_service.py`.

#### Fase 3c — Borderô de Cilindros (concluída 2026-07-14)

Relatório de consulta sobre `Viagem`/`Viagem_Cilindro`/`Viagem_Retorno` —
filtros implementados: Tipo Viagem (Normal/Fábrica/Todas), Status
(AP/APT/DP/DPT/DT/RT, seleção múltipla), período de saída, período de
retorno, grupo de gás/capacidade/pressão/padrão, documento (O.S. saída/O.S.
retorno/NF/Nº Série — busca por igualdade em qualquer um dos quatro
campos), segmento do cliente (só aplicável a Tipo Normal, já que Fornecedor
não tem segmento), situação de contrato (simplificado para um checkbox "Só
contrato ativo" em vez de um combo de situações — ver nota abaixo), radio
Em Aberto/Todos (`Em Aberto` = item cuja baixa em `Viagem_Retorno` ainda
está pendente, `viagem_retorno=0`).

- Backend: `backend/services/bordero_service.py` (`list_bordero` — detalhe
  agrupado por cliente com subtotais Saída/Retorno/Em Aberto calculados em
  Python a partir do resultado já buscado, sem segunda consulta;
  `resumo_bordero` — cruzamento por grupo de gás/capacidade/pressão/
  padrão/status via `GROUP BY` real, substituindo a tabela temporária por
  máquina do legado) + `backend/routes/bordero.py` (`GET /api/bordero-
  cilindros`, `GET /api/bordero-cilindros/resumo` — tela só-leitura, sem
  log de auditoria porque nada é gravado).
- Frontend: `frontend/app/bordero-cilindros.tsx` (filtros + resultado
  agrupado + resumo por status recolhível) + card novo em
  `app/(tabs)/cilindros.tsx`. Web-only, mesmo padrão do resto do módulo.
- **Exportação Excel real** (confirmado com o usuário via pergunta direta:
  consulta em tela + Excel, sem impressão formatada) — **biblioteca nova**:
  nenhuma tela do projeto exportava `.xlsx` de verdade até agora (as telas
  de relatório existentes exportam PDF via `expo-print`/`expo-sharing`,
  ver `frontend/src/utils/export-report.ts`). Adicionado `xlsx` (SheetJS)
  como dependência do frontend + `frontend/src/utils/export-xlsx.ts`
  (utilitário genérico, gera o `.xlsx` a partir dos dados já carregados na
  tela e dispara o download direto no navegador — sem precisar de
  `expo-sharing`, já que o módulo Cilindros inteiro é web-only). Gera 3
  abas: Detalhe, Subtotais por Cliente, Resumo por Status.
- **Simplificação assumida sem perguntar** (risco baixo, documentando por
  transparência): "situação de contrato" virou um checkbox binário ("Só
  contrato ativo" = `Contratos.situacao='A'`, desmarcado = sem filtro) em
  vez de reproduzir o combo completo de situações do legado — evita
  inventar/assumir o conjunto real de códigos de `Contratos.situacao` sem
  confirmação (mesma dúvida #3 ainda em aberto na Fase 3a/3b sobre o
  escopo do módulo de Contratos).
- 12 testes unitários novos (`test_bordero_service.py`) — 342 no total do
  backend, todos verdes.

Com isso, o módulo Cilindros está com **todas as fases concluídas**
(Cadastro, Clientes x Cilindro, Nº Série, Manutenção de Viagens, Borderô).

---

## Produtos (Cadastro Completo)

**Status: 🟢 implementado (2026-07-14)** — CRUD completo + Fornecedores +
Similares/Secundários + Grade + Tray real. Fonte VB6 rastreada campo-a-campo
(única cópia com as 7 abas do screenshot: `C:\Desenv\VB6\SQLSERVER\Kontacto\
FrmManPec.frm`, 12.838 linhas; foto: `Geral\FrmAsoFot.frm`).

### O que já foi feito

- Backend: `backend/services/produto_completo_service.py` (CRUD completo em
  `pecas`, mapeamento de ~150 campos por aba confirmado linha a linha contra
  o `.frm` real — ver seção abaixo), `backend/services/tray_service.py`
  (cliente OAuth + POST real na API da Tray, upload de imagem pra Azure
  Blob), `backend/routes/produto_completo.py`. Permissão `PRODUTO_COMP` no
  catálogo (CADASTROS), ações: ABRIR/GRAVAR/EXCLUIR/IMPRIMIR/EXPORTAR +
  FORNECEDORES/FOTOGRAFIA/ENVIAR_SITE/GRADE.
- Frontend: `frontend/app/produto-completo.tsx` (tela cheia, 7-8 abas
  dependendo dos módulos ligados) + `frontend/src/hooks/
  useProdutoCompletoForm.ts` (form-dict + setField, mesmo padrão de
  `useControleSistemaForm.ts` — evita ~130 `useState` individuais).
  `produtos.tsx` (buscador/picker existente) agora navega pra cá ao tocar
  num produto fora do modo de seleção (web), e ganhou um FAB "Novo". Tile
  "Produtos" em Cadastros aponta pra cá no web, mantém o buscador no mobile.
- Testes unitários: `backend/tests/unit/test_produto_completo_service.py`
  (15 testes — geração de código, guards de módulo, guard de exclusão por
  dependência, geração de grade). Round-trip completo (create→get→update→
  delete) validado ao vivo contra GERDELL/BARESTELA, sem deixar dado órfão
  (ver histórico da sessão 2026-07-14 se precisar repetir).
- `boto3`, `requests`, `cryptography`, `python-multipart` instalados nos
  dois venvs do projeto (`C:\Desenv\APPIAREACT\.venv` — testes/dev — e
  `backend\.venv` — runtime real do `start-backend.ps1`) — **os dois venvs
  já estavam desatualizados em relação a `requirements.txt` antes desta
  sessão** (faltavam essas 4 libs mesmo sem nenhuma mudança minha), não é
  algo introduzido por este trabalho. Vale revisitar/recriar os venvs do
  zero numa próxima janela de manutenção.

### Mapeamento de campos por aba (resumo — ver CLAUDE.md > "Produto
Completo" para as regras de negócio; este bloco é só o de-para campo→coluna,
extraído do rastreio real do `.frm`)

- **Dados Principais**: códigos (fábrica/interno/barra/mercosul),
  descrições (padrão/PDV/embarque/NF/completa), preços (custo/venda/
  sugestão/garantia/sugerido/base/promocional/lista + variado), ANP, marca/
  modelo, fornecedor, nível (nivel1-5), produto web/frete grátis site,
  situação. Estoque (qtd/reservado/reservado_os) e custo médio são
  somente-leitura aqui (calculados por movimentação, não por este form).
- **Descontos e Comissões**: desc_g/desc_s/desc_v, comissão (padrão +
  atendente/executor + valores + desc. base), paga_comissao,
  aceita_desconto, politica_preco.
- **Configurações Fiscais**: NCM/CEST/benefício fiscal, origem, IPI (%/
  valor/CST entrada-saída/enquadramento), ICMS, PIS/COFINS, substituição
  tributária/MVA, Protocolo ST por UF (`pecas_protocolo_st`), Vínculos XML
  do Fornecedor (`pecas_xml`).
- **Dados Secundários**: unidades/dimensões/pesos, estoque mín/máx/
  ressuprimento, área/prateleira/escaninho, prazos, margens, pontuação,
  controla número de série.
- **Grade do Produto**: gera produtos-filhos de verdade por combinação
  cor×tamanho (`pecas_grade`), copia XML e cadastro fiscal do principal.
  Só habilitada com `controle_configuracao.grade` ligado (flag da empresa,
  não do produto — confirmado no `Form_Load` do legado).
- **Similares e Equivalentes**: duas seções independentes — "Produtos
  Similares" (`pecaseq`) e "Produtos Secundários" (`pecas_secundaria`) —
  nomes internos diferentes do nome da aba, não confundir uma com a outra.
- **Livro**: só habilitada com `controle_configuracao.Livraria` ligado.
  Campos próprios: autor, série, sinopse, lançamento, esgotado. Reaproveita
  (não duplica) fornecedor="Editora", tipo_peca="Tipo", desconto_compra e
  desc_v="Desconto Venda" das outras abas.
- **Fornecedores** (botão, modal): `pecas_fornecedor(peca, fornecedor,
  sequencia)`.
- **Fotografia** (botão, modal): Gestor de Documentos (grupo Produtos) +,
  se o módulo Grade estiver ligado, botão extra "Cadastrar/Atualizar
  Produto no Site" (Tray real — ver CLAUDE.md pro aviso de teste). A cor de
  cada foto é editada direto no campo "Cor" do Gestor de Documentos (mesmo
  destino do legado, `gestor_documentos.cor`), não numa tela dedicada
  separada — simplificação deliberada em relação ao `FrmAsoFot` original,
  que tinha uma grade lateral de cores só pra isso.
- **Anexos** (botão/aba): Gestor de Documentos padrão, grupo Produtos
  (`GESTOR_DOC_GRUPO_PRODUTO=4`) — **diverge do legado de propósito** (ver
  CLAUDE.md, o legado usa Grupo=3 por bug de cópia-colada).

### Pontos de atenção / dúvidas em aberto

- **Integração Tray nunca testada contra a API real** (sem credenciais de
  sandbox neste ambiente) — o contrato de request/response foi inferido do
  código-fonte VB.NET (`Controller_Tray.vb`) e das convenções públicas
  documentadas da API da Tray, não de uma chamada real bem-sucedida. Antes
  de usar em produção: validar `_montar_payload_produto`/`_get_access_token_sync`
  em `backend/services/tray_service.py` contra uma loja de teste real e
  ajustar o payload conforme a resposta.
- Upload de imagem pra Tray usa **só Azure Blob** (reaproveita
  `controle_aux.Azure_ConnectionString` do Gestor de Documentos) — o
  suporte a Amazon S3 que existia no legado (`TRAY_TIPO_BLOB=1`) não foi
  replicado (nenhuma credencial S3 existe neste app). Se um cliente
  precisar de S3 de verdade, é trabalho novo, não só "ligar uma flag".
- NCM/CEST são campos de texto livre — o legado abre uma tela dedicada de
  busca (`FrmCesNCM`) que não foi migrada. Baixa prioridade, mas registrar
  aqui caso o usuário peça depois.
- Múltiplos códigos de barra por produto (`codbarra_auxiliar`) não
  migrados — só um campo de código de barras, como no screenshot do
  usuário. Fora de escopo por ora (usuário não pediu).
- `orc_produto`/`pedido_venda_prod`/`os_produto`/`nf_recebimento_itens` são
  checados na exclusão via `try/except` silencioso (se a tabela não
  existir numa instalação específica, não bloqueia a exclusão por isso) —
  revisitar se algum cliente relatar exclusão indevida de produto com
  movimentação real que essa lista não cobriu.

### Ajustes 2026-07-14 (mesmo dia, retomado após o usuário testar a tela)

- **Layout: identidade sempre visível acima das abas.** O usuário apontou
  que no legado (`FrmManPec.frm`) os campos Código Interno/Fábrica/Barra/
  Situação/Descrição/Aplicação ficam ACIMA da barra de abas (`TabProdutos`),
  nunca escondidos ao trocar de aba — a primeira versão desta tela tinha
  colocado esses campos DENTRO da aba "Dados Principais" por engano. Corrigido
  em `produto-completo.tsx`: esses campos agora ficam num card fixo acima da
  `tabBar`; o resto de "Dados Principais" (preços, classificação, estoque,
  botões Fornecedores/Fotografia/Excluir) continua dentro da aba. Mesmo
  padrão replicado em `cliente-completo.tsx` (CPF/CNPJ + Nome/Razão Social
  fixos acima das abas — usuário confirmou via pergunta, essas 2 telas têm
  estrutura diferente então não dava pra assumir os mesmos campos). Ver
  CLAUDE.md > "Full CRUD Form Screen Standard".
- **Código Interno agora é editável com busca automática no blur.** Antes
  era só leitura (gerado pelo backend). Agora o campo aceita digitação; ao
  perder o foco com um valor preenchido, `buscarPorCodigoInt` (em
  `useProdutoCompletoForm.ts`) busca silenciosamente esse código — se
  encontrar um produto existente, carrega ele pra edição (mesmo padrão de
  `buscarPorCgc` em Cliente/Fornecedor); se não encontrar, não faz nada e o
  código digitado é ignorado na gravação (o backend continua gerando o
  código sequencial de verdade ao criar — só o *lookup* ficou editável, não
  a atribuição de código na criação).
- **Serviços agora segue o mesmo padrão de lista compartilhada que
  Produtos** (pedido explícito do usuário): `servicos.tsx` deixou de ter
  lista própria embutida (busca, FAB, toque pra editar) — agora é só o
  FORMULÁRIO, recebendo `?codigo=` da URL (mesmo padrão de
  `produto-completo.tsx`). A lista fica em `produtos.tsx?tipo=S`, a MESMA
  tela já usada pelo picker de item de Pedido/O.S. (que continua
  funcionando exatamente como antes — não foi alterado, só ganhou um
  encaminhamento adicional pro tipo "S" fora do modo de seleção). O tile
  "Serviços" em Cadastros agora abre `produtos.tsx?tipo=S` em vez de
  `/servicos` diretamente. Botão Excluir, que antes só existia na linha da
  lista, foi movido pra dentro da aba "Dados Principais" do formulário.
- **Tipo travado na lista compartilhada**: em `produtos.tsx`, quando aberta
  com `?tipo=P`/`?tipo=S` fixo (a partir de Cadastros), os chips "Tudo/
  Produtos/Serviços" ficam ESCONDIDOS — sem opção de trocar de tipo. Só
  aparecem quando aberta sem `tipo` (picker de item em Pedido/O.S., que
  precisa buscar nos dois). Título do cabeçalho também reflete o tipo
  travado.
- **Identidade fixa acima das abas, também em `servicos.tsx`**: Código/
  Descrição/Situação hoisted pra um card acima da `tabBar`, mesmo padrão
  já aplicado em Produto/Cliente Completo.
- **Correção: tile "Produtos" pulava a lista.** Numa passada anterior, o
  tile de Cadastros ia direto pra `/produto-completo` no web (sem passar
  pela lista) — inconsistente com Serviços/Cliente/etc. Corrigido: agora
  sempre abre `produtos.tsx?tipo=P` primeiro (mesma lista compartilhada,
  mesmo padrão de Serviços) — tocar num produto (ou "Novo", web) que abre
  o Cadastro de Produtos completo.

---

## Transações

**Status: 🟡 Pedido Completo Fase A implementada (2026-07-15); O.S. Completa e Fases B-F ainda não iniciadas.**

Pedido de origem: usuário pediu (mensagem `[Global]`) uma nova opção
"Transações" no menu vertical (web-only), contendo as versões **completas**
de Pedido e O.S. — distintas das pré-vendas rápidas já existentes hoje
(`pedido-form.tsx`/`os-form.tsx`, usadas por mobile e como fluxo de
pré-venda no web). Anexou print do menu "Transações" do VB6 legado (com
Produtos, Pré-Vendas, Compra, Contrato, Notas Fiscais, Gestor de Devolução,
Gestor de Projetos, Vendas, Recibos) como referência de escopo futuro.

Ver CLAUDE.md > "Transações Screens Strategy" para o racional completo da
separação rápido/completo (mesmo padrão já usado em "Cliente Screens
Strategy").

### O que já foi feito

- Aba de topo "Transações" (`frontend/app/(tabs)/_layout.tsx` +
  `frontend/app/(tabs)/transacoes.tsx`) — web-only via `href: isWeb ?
  undefined : null`, mesmo padrão de Financeiro/Posto. Guard mobile via
  `LockedView` (`Platform.OS !== "web"`).
- Catálogo de permissões: menu `MOVIMENTO` renomeado para `TRANSACOES`
  ("Transações") em `backend/services/permissoes_service.py` — os `_tela()`
  `PEDIDO`/`OS` (pré-venda rápida) permanecem como filhos, inalterados
  (mesmas ações `ACOES_PEDIDO`/`ACOES_OS`). Adicionados dois novos:
  `PEDIDO_COMP` ("Pedido Completo") e `OS_COMP` ("O.S. Completa"), ambos com
  `ACOES_PADRAO` (só ABRIR/GRAVAR — ainda não têm ações customizadas
  definidas).
- **Regra explícita do usuário**: PEDIDO/OS (pré-venda rápida mobile) ficam
  na árvore de permissões dentro de TRANSACOES, mas **não** aparecem como
  card navegável no menu Transações — só PEDIDO_COMP/OS_COMP aparecem em
  `transacoes.tsx` (gated por `can("PEDIDO_COMP.ABRIR")`/
  `can("OS_COMP.ABRIR")`). Isso já está implementado corretamente —
  `transacoes.tsx` só lista os dois cards novos.
- Placeholder genérico `frontend/app/transacao-placeholder.tsx` (mesmo
  padrão de `posto-placeholder.tsx`) — os dois cards apontam pra lá até as
  telas reais existirem.
- Verificado via API (`GET /api/permissoes/catalogo`) após restart do
  backend: menu TRANSACOES aparece com os 4 filhos (OS_COMP, OS,
  PEDIDO_COMP, PEDIDO), em ordem alfabética (regra de "Permissions Tree
  Ordering").
- `backend/tests/e2e/test_iter23_permissoes_pedido_catalog.py` e
  `test_iter24_controle_config.py` atualizados (referenciavam o menu
  `MOVIMENTO` pelo nome antigo) — 249 testes unitários seguem passando.
- Rótulos renomeados no catálogo: `PEDIDO` exibia "Pedidos Mobile" (era
  "Pedidos") e `OS` exibe "OS Mobile" (era "Ordem de Serviço") — só troca de
  label, mesma chave/comportamento. **Atualizado 2026-07-15**: `PEDIDO`
  renomeado de novo, agora para "Pedido Bar" — ver seção "## Pedido Bar"
  abaixo para o motivo (transformação do Pedido Mobile em tela dedicada ao
  segmento Bar).
- **[GLOBAL] Exclusividade mútua Mobile x Completo**: na tela Permissões,
  marcar `PEDIDO` desmarca `PEDIDO_COMP` (e seus filhos) automaticamente, e
  vice-versa; mesma regra pro par `OS`/`OS_COMP`. Implementado em
  `frontend/app/permissoes.tsx` (`EXCLUSIVE_PAIRS` +
  `applyPedidoOsExclusivity`) — direcional quando o clique é num nó do par
  (TELA ou BOTAO), com fallback (mantém Mobile, desliga Completo) pra
  toggles em bloco (menu inteiro, "Marcar todas as permissões").
- **Correção do usuário 2026-07-13**: as telas de lista (`pedidos.tsx`/
  `os.tsx`) são **compartilhadas** entre Mobile e Completo — não existe
  tela de lista separada pro Completo. `transacao-placeholder.tsx` foi
  removido; tanto os cards "Pedido Completo"/"O.S. Completa" em
  `transacoes.tsx` quanto os cards da Tela Principal
  (`ModuleTiles.tsx`) apontam direto pra `/pedidos`/`/os`. O gate de acesso
  dessas listas foi ampliado pra `can("PEDIDO.ABRIR") ||
  can("PEDIDO_COMP.ABRIR")` (mesmo padrão em OS), então qualquer uma das
  duas permissões abre a lista. O que falta de verdade é só a **tela de
  edição completa**: clicar num item da lista só navega pro formulário
  rápido (`pedido-form.tsx`/`os-form.tsx`) quando `can("PEDIDO.ABRIR")`/
  `can("OS.ABRIR")` — pra quem só tem a permissão Completo, o clique é
  deliberadamente um no-op até essa tela de edição completa existir e ser
  ligada como o destino alternativo desse mesmo clique.

### Pedido Completo Fase A — implementada (2026-07-15)

Núcleo do plano faseado (ver "Plano de implementação proposto" abaixo):
cabeçalho + grade de itens (resolução rica + kits) + Fechar/Cancelar.
Backend já existia de uma sessão anterior (não documentado neste arquivo
até agora — achado ao retomar o trabalho); o que faltava e foi feito
nesta rodada foi o **frontend**.

- Backend (já existia, confirmado registrado em `server.py`):
  `backend/services/pedido_completo_service.py` (get/save cabeçalho,
  add_item com `_resolve_produto_completo`/`_kit_componentes` de
  `pedido_common.py`, fechar, cancelar) + `backend/routes/
  pedido_completo.py` (`/api/pedido-completo/*`, log de auditoria em
  tela `PEDIDO_COMP` em toda escrita) + `ACOES_PEDIDO_COMP` no catálogo
  de permissões (ABRIR/GRAVAR/ADD_ITEM/EDIT_ITEM/DEL_ITEM/SITUACAO) +
  26 testes unitários (`test_pedido_completo_service.py`) — 368 testes
  no total do backend, todos verdes.
- Frontend (novo, 2026-07-15): `frontend/app/pedido-completo.tsx` — tela
  cheia web-only, **sem abas** (achado estrutural do rastreio:
  `frmmanpedfor.frm` não usa `SSTab` nem frames sincronizados — mesma
  exceção "compact single-view screens" do CLAUDE.md já aplicada a
  Fornecedores/Cilindros). Cabeçalho com Cliente (reaproveita
  `ClienteSection`/`ClientSearchModal` de `pedido-form.tsx`), Vendedor,
  Forma de Pagamento, Área de Atuação, Validade/Previsão de Entrega
  (`WebDateField`, não `DateField` — padrão de campo de data web do
  CLAUDE.md), Local de Entrega, Nº Pedido do Cliente, Informações de
  Entrega, Observação. Itens/Fechar/Cancelar travados até o cabeçalho
  ser gravado pela 1ª vez (mesma regra global de "related records need
  parent saved first" já aplicada em Cliente/Fornecedor Completo).
  Campos travados automaticamente quando `situacao` não é mais `'A'`
  (só Vendedor/Forma de Pagamento continuam editáveis com `'F'`, nada
  editável em `'C'`/`'PG'` — regra real do legado).
- **Reaproveitamento em vez de duplicação**: `usePedidoItens`/
  `ItemList`/`AddItemModal`/`EditItemModal` (já usados por
  `pedido-form.tsx`) ganharam prop `basePath`/`tela` numa sessão
  anterior especificamente pra isso — só precisou passar
  `basePath="/api/pedido-completo"` e `tela="PEDIDO_COMP"`. Nenhum
  componente novo de item foi criado.
- **Ajuste feito junto**: `AddItemModal`/`EditItemModal` não seguiam o
  "Modal/Selector Standard (Web)" do CLAUDE.md (bottom-sheet cru, sem a
  variante `compactWeb`) — só não tinha sido notado porque
  `pedido-form.tsx` (onde já eram usados) não tinha guard web-only pra
  forçar o formato correto. Corrigido nos dois arquivos (mesmo padrão
  de `ClientSearchModal.tsx`), já que agora são usados pela primeira
  vez numa tela 100% web.
- **`produtos.tsx` (picker de item compartilhado com Pedido/O.S. rápido)
  ganhou suporte a `?origem=completo`**: grava via
  `/api/pedido-completo/{id}/itens` em vez de `/api/pedidos/{id}/itens`
  quando aberto a partir do botão "Abrir lista completa de produtos" do
  Pedido Completo — sem isso esse atalho gravaria no endpoint errado
  (perderia a resolução rica/expansão de kit).
- `pedidos.tsx` (lista compartilhada Mobile+Completo): o tap-through
  documentado como "no-op pra quem só tem PEDIDO_COMP" (ver seção
  anterior) agora abre `/pedido-completo`; o FAB "Novo" idem.
- **Verificação feita**: `tsc --noEmit` sem novos erros (mesma baseline
  de 12 erros pré-existentes, não relacionados — o número mudou de 14
  pra 12 porque os tipos de rota do expo-router (`.expo/types/
  router.d.ts`) estavam desatualizados e foram regenerados subindo o
  Expo dev server uma vez), 368 testes unitários do backend passando,
  backend sobe limpo com `uvicorn` e todas as rotas `/api/pedido-completo/*`
  aparecem no `openapi.json`. **Não verificado**: fluxo completo no
  navegador (criar → adicionar item → fechar → cancelar) contra dados
  reais — este ambiente não tem `chromium-cli`/driver de navegador nem
  credenciais de login configuradas, e não fui atrás de credenciais de
  produção pra não arriscar side-effects num banco real sem essa
  autorização explícita. Recomendado testar manualmente antes de dar
  como definitivamente pronto.
- **Cuidado ao subir o backend localmente**: já havia uma instância do
  `uvicorn` rodando na porta 8081 quando este trabalho começou (mesmo
  alerta de `feedback_backend_supervisor_duplicado` na memória) — a
  instância extra que subi pra este smoke test foi encerrada ao final,
  a original foi deixada intacta.

### Fase A — recursos do Pedido Mobile trazidos pro Completo (2026-07-15, mesmo dia)

Pedido explícito do usuário depois de comparar as duas telas lado a lado
("aplicar a análise do Pedido Mobile no Pedido Completo. Aplicar os
recursos de adicionar item e whatsapp do Pedido Mobile no Pedido
Completo") — a Fase A inicial só tinha ABRIR/GRAVAR/ADD_ITEM/EDIT_ITEM/
DEL_ITEM/SITUACAO no catálogo, deliberadamente sem desconto/análise/
WhatsApp (documentado como "fases futuras"); o usuário pediu pra trazer
isso já, não esperar as fases C/F do plano.

- **Catálogo de permissões**: `ACOES_PEDIDO_COMP` (`permissoes_service.py`)
  ganhou `WHATSAPP`, `DESC_ITEM`, `DESC_GERAL`, `VER_DESCONTOS`, `ANALISE`
  — agora idêntico a `ACOES_PEDIDO` (pré-venda rápida).
- **Backend**: os endpoints por trás dessas ações já eram genéricos
  (chaveados só por `pedido`, não pela tela que criou o registro) —
  `descontos_service.py` (relatório de descontos + desconto geral,
  tabelas `pedido_venda_prod`/`descontos_concedidos`) e
  `GET /api/relatorios/descontos-margem` (tela "Análise do Pedido") não
  precisaram de nenhuma mudança de lógica. Só faltavam as **rotas**
  específicas pro prefixo `/pedido-completo`:
  `GET/POST /api/pedido-completo/{pedido}/descontos` e
  `/desconto-geral`, adicionadas em `routes/pedido_completo.py`
  reaproveitando `descontos_service` direto (mesmo padrão dos itens —
  log de auditoria sempre com `tela="PEDIDO_COMP"`, mesmo reaproveitando
  o service do Pedido rápido). `itens_service.update_item`/`_add_item_completo_sync`
  já chamavam `_log_desconto_item` desde a Fase A original — nada a
  mudar aí.
- **Frontend**: `pedido-completo.tsx` ganhou o botão "Analisar margem &
  descontos" (rota `/relatorio-descontos?pedido=...`, tela genérica,
  gate só no botão de entrada) e `WhatsappButton` (`documentType="PED"`,
  mesmo componente do Pedido rápido) — copiados de `pedido-form.tsx` 1:1.
  `GeneralDiscountModal`/`DiscountsReportModal` (desconto geral +
  relatório de descontos concedidos) foram importados e renderizados —
  `ItemList`/`AddItemModal` já sabiam mostrar os botões/campos de
  desconto condicionados a `can(\`${tela}.DESC_GERAL/VER_DESCONTOS/DESC_ITEM\`)`
  desde a Fase A original (prop `tela="PEDIDO_COMP"` já passada), só
  faltava a permissão existir no catálogo pra eles aparecerem.
- **Mesmo ajuste "Modal/Selector Standard (Web)" da Fase A original**:
  `GeneralDiscountModal.tsx`/`DiscountsReportModal.tsx` também usavam só
  `modalBg`/`modalCard` crus (bottom-sheet), sem a variante `compactWeb`
  — corrigido nos dois, mesmo padrão de `AddItemModal`/`EditItemModal`.
- **Backend precisou reiniciar pra pegar o código novo**: o `uvicorn`
  desta sessão roda sem `--reload` (supervisor `start-backend.ps1`) — as
  duas rotas novas só apareceram no `openapi.json` depois de encerrar o
  processo `uvicorn` filho e deixar o loop de supervisão subir um novo
  (o Expo/Metro do frontend, ao contrário, tem Fast Refresh e pegou as
  mudanças de `pedido-completo.tsx` sem precisar reiniciar).
- 368 testes unitários do backend seguem verdes (nenhum teste novo
  específico pras 2 rotas novas ainda — são repasses finos pro
  `descontos_service`, já coberto pelos testes existentes desse
  service via o Pedido rápido; considerar um teste de integração leve
  se esta área crescer mais). `tsc --noEmit` no frontend permanece na
  mesma baseline de 12 erros pré-existentes.
- **Ainda não verificado em navegador real** — mesma ressalva já
  registrada acima pra Fase A original.

### O que falta (bloqueado)

- **O.S. Completa** (`frmmanos.frm` ou equivalente) — rastreio ainda não
  feito, só Pedido (`frmmanpedfor.frm`) foi tratado nesta rodada (ver
  "Pedido Completo — rastreio campo-a-campo" abaixo). O.S. provavelmente
  compartilha boa parte da mesma estrutura/regras (mesmo padrão de
  cabeçalho+grade+popups), mas isso precisa ser confirmado rastreando a
  fonte, não assumido.
- Nenhuma ação customizada (`ACOES_*`) definida ainda para PEDIDO_COMP/
  OS_COMP — hoje usam `ACOES_PADRAO` (ABRIR/GRAVAR) só pra existir no
  catálogo; a lista real de ações precisa reflitir o rastreio abaixo
  (Gravar, Add/Editar/Excluir Item, Desconto/Rateio, Fatura Parcial,
  Fechar, Faturar, Cancelar, ações Tray, etc.).
- O menu de referência do VB6 (Produtos, Compra, Contrato, Notas Fiscais,
  Gestor de Devolução, Gestor de Projetos, Vendas, Recibos) tem bem mais
  itens que só Pedido/O.S. — fora de escopo por enquanto, usuário só pediu
  Pedido/O.S. completos nesta rodada.

### Pedido Completo — rastreio campo-a-campo (`frmmanpedfor.frm`, concluído 2026-07-14)

Fonte: `C:\Desenv\VB6\SQLSERVER\Geral\frmmanpedfor.frm` (form `FrmManPed`,
**21.038 linhas** — o maior form já rastreado neste projeto). Rastreio
feito via dois subagentes em paralelo (estrutura/campos + regras de
negócio) dado o tamanho do arquivo — resultado consolidado abaixo.
Confirma que este é o form de origem tanto pra "Pedido Completo" quanto
pra decisão de unificação com Cilindro registrada em CLAUDE.md.

#### Achado estrutural principal

O form **não usa abas de verdade** (nem `SSTab`, nem o padrão de Frames
sincronizados alternando visibilidade em grupo já visto em outras telas
deste projeto). A tela real é: `Frame2` (tira de cabeçalho: cliente,
vendedor, forma de pagamento, referência, previsão de entrega — sempre
visível) + `Frame3` (corpo principal: campos de lançamento de item + grade
`GridV` + toolbar de ações — sempre visível) + **11 popups independentes**,
cada um aberto/fechado avulsamente por um botão específico, não como um
conjunto de abas mutuamente exclusivas:

| Popup | Função |
|---|---|
| `FrmNDS` | Escolha de número de série (ver seção "controla_num_serie" abaixo) |
| `Frame5` | Reabrir/selecionar pedido relacionado |
| `Frame12` | Filtro cliente+período pra ação em lote |
| `Frame6` / `frGerente` | Senha de gerente (dois popups distintos, mesmo propósito) |
| `Frame13` | Faturamento Parcial |
| `FrmTray` | Painel de integração com o site (Tray) |
| `Frame15` | Desconto/Rateio (acerto do valor total do pedido) |
| `Frame7` | Consultar Pedidos (busca multi-critério) |
| `Frame14` | Parcelas (nº de parcelas, % na 1ª, recálculo) |
| `Frame10` (+ `Frame1`/`Frame4` aninhados) | Informações Complementares (local de entrega, validade) |

**Implicação pra migração**: a nova tela "Pedido Completo" deve seguir o
"Full CRUD Form Screen Standard" já estabelecido (cabeçalho fixo +
identidade sempre visível + Gravar no topo direito), com cada popup do
legado virando um **slide modal** (mesmo padrão já usado em Fornecedores/
Cilindros), não abas — o legado em si já não usa abas aqui.

#### Tabela gravada pelo botão Gravar (`Command1_Click`, é uma função só —
não existe botão separado de "salvar cabeçalho", o mesmo clique cria/
atualiza o cabeçalho E adiciona o item, dependendo do estado)

`pedido_venda` (INSERT): `TIPO, area_atuacao, data, cliente, vendedor,
forma_pag, local_entrega, previsao_entrega, obs, NUM_PED_CLIENTE,
infoentrega, ABERTOPOR, hora_aberto` (recupera o `pedido` gerado via
reselect por `data+cliente+vendedor+forma_pag` — **workaround**, ver
abaixo). UPDATE distingue pedido `FECHADO` (só `vendedor`/`forma_pag`
editáveis) de `Aberto` (todos os campos).

`pedido_venda_prod` (INSERT, duas variantes): campos padrão `pedido,
produto, qtd_pedida, troca, p_normal, desconto, acrescimo, p_venda,
comprimento, largura, descricao_produto, unidade_pedido, area_venda,
custo_ped, comprimento_chapa, largura_chapa` + variante com `area_minima,
ajustar, cod_Num_serie` quando aplicável.

`DESCONTOS_CONCEDIDOS` — tabela de auditoria de desconto (tipo `'I'`
individual por item, `'G'` geral/rateio), grava sempre que um desconto é
concedido — regra real, não incidental.

#### Regras de negócio reais identificadas (por área)

1. **Cabeçalho**: situação só `'A'` é editável; cliente/vendedor/área de
   atuação obrigatórios; **pedidos de origem Tray são bloqueados pra
   edição manual** (só os botões Tray dedicados mexem neles); validade do
   orçamento default = `DATESIST + Controle.prazo_validade_pedido_venda`
   dias (ou sem validade se esse prazo = -1).
2. **Item — resolução de produto**: cadeia de fallback real (não
   workaround) — tenta `SERVICOS.codigo` (se começa com "S") →
   `PECAS.codigo_fab` → `codigo_int` → `codigo_bar` →
   `CODBARRA_AUXILIAR` (múltiplos códigos de barra por produto).
3. **Item — kits/compostos** (`produtos_compostos`): um código digitado
   pode expandir em várias linhas de `pedido_venda_prod` (uma por
   componente do kit), marcadas com `produto_composto` pra exclusão em
   grupo depois. Regra real.
4. **`controla_num_serie` / `CmbNDS` / `FrmNDS`** — **a peça mais
   importante pra unificação do Cilindro** (confirma a análise já em
   CLAUDE.md): flag por produto (`PECAS.controla_num_serie`) força
   quantidade=1, busca `pecas_num_serie` disponíveis, bloqueia a inclusão
   até o usuário escolher um (ou cancelar explicitamente), grava o FK
   escolhido em `pedido_venda_prod.cod_num_serie`, e a coluna da grade
   correspondente muda de rótulo pra "Número de Série". Esse é exatamente
   o formato "atributo extra condicional por item, escolhido em modal" que
   a análise de unificação do Cilindro já previa reaproveitar.
   **Dúvida em aberto**: não foi encontrado onde `pecas_num_serie.
   disponivel` é zerado após a escolha — pode estar em outro form/trigger;
   confirmar antes de assumir que a reserva é de fato aplicada.
5. **Promoção** (`PECAS_PROMOCAO`): o mesmo campo de código de produto
   aceita um código de promoção; se encontrado, troca silenciosamente pra
   o produto+quantidade do bundle. Quantidade deve ser múltiplo exato do
   tamanho do bundle. Resíduo de arredondamento por unidade é reconciliado
   num ajuste único (`ajuste_promocao`) pra o total da linha bater exato
   com o total contratado do bundle — regra real, não é bug de
   arredondamento a "corrigir".
6. **Módulo m²/Metro_Quadrado**: ativado quando a unidade do produto é
   M2/ML/M3. Exige escolha de "tipo de preço" (até 6 níveis, cada um com
   área mínima própria) antes do cálculo. `AreaPreco` (cálculo de venda,
   com arredondamento/piso de área mínima) é **diferente** de `AreaEstoque`
   (cálculo de estoque, sempre área bruta sem piso/arredondamento) —
   **não confundir os dois na migração**, é intencional que divirjam.
   Cilindros/itens com `controla_num_serie` pulam o piso de área mínima.
7. **Módulo Clínica**: quando ativo, cada unidade de quantidade de um
   Serviço vira uma linha própria em `pedido_venda_prod` (não uma linha
   com qtd=N) — pra permitir agendamento individual por unidade. Regra
   real. "Layouts"/"Agendar" delegam pra outros forms (`FrmPreLay`/
   `FrmMarAge`) não rastreados nesta rodada (fora do escopo Pedido/O.S.).
8. **Fiscal (`SitTribut`)**: cascata de resolução de regra tributária
   (ICMS/IPI/ICMS-ST) cruzando protocolo ST × consumidor final × simples
   nacional × UF, com até ~8 tentativas de fallback progressivo. **Não
   portar sem confirmação explícita do usuário** — a ordem exata do
   fallback pode ser regra de negócio real ou acúmulo de patches; segue a
   regra de "Telas Fiscais" do CLAUDE.md §12 (nunca mudar regra fiscal sem
   confirmação, mesmo que pareça pequena).
9. **Integração Tray** (4 botões: Entrega/NFe/Rastreio/Cancelar): sequência
   de estado real (NFe → Rastreio → Entrega, cada um exige o anterior já
   confirmado) que deve ser preservada — usa o mesmo `Controller_Tray.vb`
   já referenciado em Produto Completo, **nunca testado contra a API real
   do Tray**.
10. **Faturamento Parcial**: mecanismo sofisticado de clonar o cabeçalho
    do pedido inteiro num pedido novo, movendo linhas não faturadas (ou
    dividindo linhas parcialmente faturadas por quantidade ou por valor de
    serviço) pro pedido novo, com reconciliação de total nos dois. Regra
    real e complexa. **Workaround a não replicar**: o vínculo entre pedido
    original e o novo é feito reaproveitando `NUM_PED_CLIENTE` (campo cujo
    propósito real é "nº do pedido do cliente") em vez de uma FK própria
    `pedido_origem` — a migração deve usar uma coluna dedicada.
11. **Fechar/Faturar/Cancelar** (máquina de estados `A→F→PG`, `C`
    alcançável de `A` ou `F`): cada transição tem sua própria cadeia de
    validação real (forma de pagamento, `ExigeDataEntrega`, checagem de
    débito do cliente, `ChecaNumeroDeSerie` antes de faturar, senha de
    gerente pra cancelar, reversão de reserva de estoque no cancelamento,
    limpeza de agendamento vinculado). Cancelar de pedido Tray exige
    cancelar no Tray primeiro.
12. **`ModPedido`** (modelo de impressão, resolvido por área de atuação
    ou default da empresa): confirma a conclusão já registrada em CLAUDE.md
    — não portar como um "número decidindo comportamento", os layouts de
    impressão em si (48-col, 45-col, TUBOLIT, Vidro A4, etc.) são reais,
    só devem ser desacoplados do `ModPedido` e ligados a um flag de
    módulo/segmento explícito. Achado extra: vários cases (`7`, `8`, `9`,
    `18`, `37`, e um segundo `5`) já estão **desabilitados/mortos** no
    código atual (bloqueados por `MsgBox "...desabilitado..." + Exit Sub`
    antes da chamada real) — não precisam ser portados.

#### Workarounds confirmados a não replicar (ver "Não replicar truques VB6")

- Recuperar o `pedido` recém-criado via reselect por
  `data+cliente+vendedor+forma_pag` em vez de `OUTPUT`/`RETURNING` — risco
  de concorrência real numa API multi-usuário.
- `Mid(string, offset, tamanho)` pra embutir dados (flag de área mínima,
  preço) dentro do texto exibido no combo de "tipo de preço" — usar objeto
  estruturado.
- Checagem de `App.EXEName` (`"KONTACTO"`, `"PAF-ECF"`, etc.) dentro de
  `AreaPreco` pra decidir comportamento por instalação — deve virar
  configuração explícita de módulo/empresa.
- Padrão de modal síncrono `While Frm.Visible: DoEvents: Wend` (usado em
  `FrmNDS`, `ListPrecos`, `frGerente`) — não existe em arquitetura
  cliente/servidor, vira modal assíncrono real no frontend.
- `NUM_PED_CLIENTE` reaproveitado como FK de pedido-origem no Faturamento
  Parcial (ver item 10 acima).
- Dois algoritmos de rateio quase idênticos (`Command66_Click` inline pra
  m² vs. `Desc_Acresc_Geral` pra não-m²) — consolidar em uma função só na
  migração, não portar os dois separadamente sem entender a real
  divergência entre eles primeiro.

#### Dúvidas em aberto (não implementar sem confirmar)

1. Onde `pecas_num_serie.disponivel` é zerado após a escolha (não
   encontrado neste form).
2. `ArredondaPBox` (função de arredondamento de dimensão m²) não
   localizada nesta passada — necessária pra portar o cálculo m² fiel.
3. Se a cascata de fallback do `SitTribut` é precedência de negócio real
   ou acúmulo de patches — não assumir, perguntar antes de portar.
4. Lógica de divisão de parcelas (`Fatura_Parcial_DAV_FPag`) no
   Faturamento Parcial vive fora deste form, não rastreada ainda.
5. Se `Desc_Acresc_Geral` (rateio não-m²) diverge de verdade do algoritmo
   inline de `Command66_Click` (m²) ou são a mesma regra duplicada.

#### Plano de implementação proposto (faseado — Fase A concluída, B-F não iniciadas)

Dado o tamanho (11 áreas de regra real, fiscal envolvido, Tray nunca
testado), seguir o mesmo padrão faseado já usado pro módulo Cilindro —
não tentar tudo de uma vez:

- **Fase A** (núcleo) — 🟢 **implementada 2026-07-15** (ver seção acima):
  cabeçalho (Gravar/Novo/Consultar) + grade de itens (Adicionar/Editar/
  Excluir, incluindo resolução de produto por código/fab/interno/barra e
  kits) + Fechar/Cancelar. Já é uma tela funcional de pedido completo
  sem os módulos condicionais.
- **Fase B** (módulos condicionais reaproveitando o padrão `FrmNDS`):
  `controla_num_serie` primeiro (é o que desbloqueia a unificação do
  Cilindro), depois módulo m², depois módulo Clínica.
- **Fase C**: Desconto/Rateio (com a cadeia de aprovação por senha de
  gerente) + Promoção.
- **Fase D**: Fiscal (`SitTribut`) — só após confirmar com o usuário as
  dúvidas #3 acima; isolado em módulo próprio por exigência do CLAUDE.md.
- **Fase E**: Faturar (com emissão de NFe) + Faturamento Parcial — exige
  resolver a dúvida #4 primeiro.
- **Fase F**: Integração Tray (4 ações) — sem sandbox real pra testar,
  mesmo caveat já registrado em Produto Completo.
- **Cilindro** entra dentro da Fase B, reaproveitando exatamente o padrão
  `controla_num_serie`/modal, conforme já decidido em CLAUDE.md > "Pedido
  de Cilindro — Unificação com Pedido de Venda Geral".

---

## Pedido Bar

**Status: 🟡 Passo 1 (rebatismo + gating por módulo + guarda de cliente
reservado) implementado 2026-07-15; o restante do escopo (painel "Pedidos
Abertos", Faturar/Comanda/NFC-e, impressão térmica) está BLOQUEADO —
requer confirmação do usuário antes de qualquer implementação, ver
"Perguntas em aberto" abaixo.**

Pedido de origem (mensagem `[Global]` do usuário, 2026-07-15, com print da
tela VB6 e o `.frm` completo colado em anexo):

> "transformar o Pedido Mobile em Pedido Bar, inclusive em permissões.
> Perde a regra somente para mobile. vai funcionar em todas as versões web
> e mobile. Será habilitado nas configurações de Módulos. [...] se o
> pedido de Venda Geral for selecionado em configurações de módulos o
> pedido de bar fica oculto em permissões, e vice versa. O pedido bar não
> pode alterar a descrição do cliente com parte nome fantasia MESA, OU
> NOME = M+NUMERO EX. M15 = MESA 15 [...] Como se fosse uma reserva. [...]
> mesma regra para cliente Comanda ex: nome = c1."

Fonte VB6: `FrmManPedBar.frm` (`C:\Desenv\VB6\...\SQLSERVER\Geral\`) —
colado na íntegra pelo usuário nesta sessão. Tela de PDV simplificado pra
Bar/Restaurante: Mesa/Balcão/Comanda/Entrega, seleção de mesa por
localização, cálculo de troco, controle de horário de abertura/fechamento,
emissão de comanda/NFC-e (`Backon_Controllers.Nfe`), impressão térmica.
Distinta de `frmmanpedfor.frm` (Pedido de Venda geral, já rastreado — ver
seção "Transações" acima) e de `FrmPedCil.frm` (Pedido de Cilindro, ver
CLAUDE.md).

### O que já foi feito (2026-07-15)

- **Rótulo do catálogo de permissões**: tela `PEDIDO` (chave inalterada,
  já usada por `pedido-form.tsx`) renomeada de "Pedidos Mobile" para
  "Pedido Bar" em `backend/services/permissoes_service.py`. Puro troque de
  label — mesma chave, mesmas ações (`ACOES_PEDIDO`), sem quebra de
  permissões já concedidas (grants ficam pela chave `tela`, não pelo
  rótulo — mesmo precedente já documentado em CLAUDE.md pra outros
  renomeios de label).
- **Gating por módulo trocado** (`MODULE_TELAS` em
  `backend/services/controle_config_service.py`, espelhado em
  `frontend/src/permissions/index.tsx`): antes `Pedido_venda -> [PEDIDO]`;
  agora `Pedido_venda -> [PEDIDO_COMP]` e `Bar -> [PEDIDO]`. Como
  `Bar`/`Cilindro`/`Pedido_venda` já são mutuamente exclusivos
  (`SEGMENTOS_PEDIDO_EXCLUSIVOS`, implementado na sessão anterior — só um
  desses três módulos pode ficar ligado ao mesmo tempo), isso já cumpre a
  regra `[Global]` pedida: com "Bar" ligado, só a tela "Pedido Bar"
  aparece no catálogo/árvore de permissões; com "Pedido de Venda" ligado,
  só "Pedido Completo" aparece — nunca os dois juntos, porque os módulos
  em si já são exclusivos entre si.
  - **Não implementado ainda** (fora do escopo desta rodada, não pedido
    explicitamente): `Cilindro` ainda não tem tela de Pedido própria no
    catálogo — a unificação Pedido de Cilindro + Pedido de Venda Geral
    (CLAUDE.md) continua bloqueada em "Pedido Completo" ainda não ter Fase
    B implementada.
- **"Perde a regra somente para mobile"**: a chave de permissão `PEDIDO`
  em si (`pedido-form.tsx`) já nunca teve um guard de plataforma
  (`Platform.OS`) que a restringisse a mobile — ela já é acessível tanto
  em mobile quanto em web hoje (diferente das telas "cadastro completo",
  que SÃO web-only por regra `[GLOBAL]` em CLAUDE.md). Então tecnicamente
  não havia nenhuma regra "só mobile" pra remover no código — a intenção
  do usuário aqui é sobre onde essa tela aparece *navegavelmente* (agora
  também acessível/visível em contexto web via o módulo Bar, não apenas
  no fluxo de pré-venda mobile), o que já é coberto pelo gating de módulo
  acima. Se ao testar a tela web algo nela ainda se comportar como
  mobile-only (estilo, navegação, FAB escondido em web etc.), reportar
  como achado específico — não foi encontrado nenhum durante esta análise,
  mas a tela não foi testada ao vivo no navegador nesta rodada (sem
  chromium-cli/credenciais neste sandbox).
- **Guarda de cliente Mesa/Comanda reservado** — implementada em
  `backend/services/clientes_service.py::_save_cliente_sync` (função
  `_cliente_mesa_ou_comanda`, chamada antes do `UPDATE cliente`, nunca no
  `INSERT` — criar um cliente novo chamado "M15"/"C1" continua permitido,
  é assim que esses registros são criados na implantação):
  - Detecta reservado se `nome` bate no padrão `^[MC]\d+$` (case
    insensitive — ex. `M15`, `c1`) OU `fantasia` contém a palavra "MESA".
  - Se o registro existente já é detectado como reservado e o `UPDATE`
    tentaria mudar `nome` OU `fantasia`, bloqueia com
    `{"success": false, "message": "Este cliente é uma Mesa/Comanda
    reservada do estabelecimento — nome e nome fantasia não podem ser
    alterados."}` — nenhum outro campo do cliente é bloqueado (limite de
    crédito, endereço, telefone etc. continuam editáveis normalmente).
  - 10 testes novos em `backend/tests/unit/test_clientes_service.py`
    (`TestClienteMesaOuComandaHelper` + `TestClienteMesaComandaBarBloqueiaRenomeio`)
    — 383 testes unitários passando no total.
  - **Só backend por enquanto** — nenhum guard equivalente no frontend
    (ex. desabilitar visualmente o campo Nome/Fantasia quando o cliente
    aberto é Mesa/Comanda em `cliente-form.tsx`/`cliente-completo.tsx`).
    Hoje o usuário só veria o erro genérico do backend ao tentar salvar.
    Fora de escopo desta rodada (não pedido explicitamente) — considerar
    ao retomar, pra dar feedback mais cedo (campo readonly + aviso) em vez
    de deixar o erro aparecer só no Gravar.
- `npx tsc --noEmit` rodado após as mudanças — erros pré-existentes não
  relacionados (colors.background ausente, `ModuleTiles.tsx` `calc(50%...)`,
  etc.), nenhum nos arquivos tocados nesta rodada. 383 testes unitários do
  backend passando. Backend reiniciado (matando o processo uvicorn sob o
  supervisor `start-backend.ps1`, que já relança automaticamente).

### Correções 2026-07-15 (mesmo dia, 2 bugs reportados pelo usuário com print)

1. **"Pedido Bar" não aparecia na tela Transações, mesmo com a permissão
   concedida** — `frontend/app/(tabs)/transacoes.tsx` só tinha cards pra
   `PEDIDO_COMP`/`OS_COMP` (`can("PEDIDO_COMP.ABRIR")`/
   `can("OS_COMP.ABRIR")`); a tela nunca tinha um card pra `PEDIDO`
   (Pedido Bar), porque antes dessa rodada `PEDIDO` era só mobile e não
   precisava de card web. Corrigido: novo card "Pedido Bar" (ícone
   `restaurant-outline`), gated por `can("PEDIDO.ABRIR")`, apontando pra
   `/pedidos` (mesma lista compartilhada) — o próprio `pedidos.tsx` já
   navegava pro `pedido-form.tsx` correto quando `can("PEDIDO.ABRIR")`,
   então só faltava o card de entrada.
2. **`[GLOBAL]` "se o módulo de Oficina ou Assistência não estiver
   selecionado não exibir OS pra ninguém, inclusive master, nem na tela de
   permissão — mesma regra pra Pedido"**. Investigado: a regra pra Pedido
   **já estava correta** (gating por módulo já implementado no passo
   anterior desta seção, e `GET /api/permissoes/catalogo` já remove telas
   desabilitadas da árvore inteira via `filter_catalogo` — não há bypass
   de master nessa rota, então já vale pra todo mundo). O gap real era só
   em O.S.: `disabled_telas()` (`backend/services/permissoes_service.py`)
   já escondia `OS` quando Oficina E Assistência estavam desligadas, mas
   **esquecia de esconder `OS_COMP`** — corrigido pra ocultar as duas.
   Confirma o que o print mostrava: "O.S. Completa" aparecia desmarcada
   mas visível na árvore de Permissões mesmo sem Oficina/Assistência
   ligado.
   - 10 novos testes unitários em
     `backend/tests/unit/test_permissoes_service.py` (`disabled_telas`/
     `filter_catalogo` — função pura, sem banco) — 393 testes passando no
     total. Backend reiniciado de novo.
3. Ajustes menores de UI, mesmo dia: descrição do card "Pedido Bar" em
   `transacoes.tsx` trocada pra "Pedido Bar e Restaurante"; lista de
   Pedidos (`pedidos.tsx`) agora abre com o filtro "Aberto" selecionado
   por padrão (era "Todos").
4. **Pergunta do usuário respondida (investigação, sem mudança de
   código)**: "pedidos sem cliente na lista podem ser um pedido de Mesa?"
   — **Não.** `pedidos_service.py` resolve `cliente_nome` via
   `COALESCE(c.nome, p.NOME_CLIENTE)` com `LEFT JOIN cliente c ON
   c.codigo = p.cliente`; um pedido de Mesa está vinculado a um `cliente`
   real (nome "M15"/"C1"), então apareceria com esse nome, não como
   "(sem cliente)". "(sem cliente)" só aparece quando `p.cliente` é NULL
   *e* `p.NOME_CLIENTE` também está vazio — ou seja, pedidos sem nenhum
   cliente vinculado, não pedidos de Mesa/Comanda. Relevante pro futuro
   painel "Pedidos Abertos": não dá pra usar esses registros existentes
   como proxy de "pedido de mesa" sem alteração — cada mesa/comanda
   precisa mesmo estar vinculada ao cliente reservado correspondente.

### Botão "Incluir Tx Serviço [F10]" — implementado 2026-07-15

Rastreado do `.frm`: o handler real é `Command50_Click` (o botão em si —
também disparado por F10 via `Form_KeyUp`). **`Inclui_Tx_Servico()`**, uma
segunda sub definida no mesmo arquivo com nome parecido, **nunca é chamada
de lugar nenhum** — tratada como código morto, não como a rotina real (ver
"Não replicar truques VB6" em CLAUDE.md).

- **Correção 2026-07-15, user-directed (mesmo dia)**: o legado
  (`Command50_Click`) empilhava uma nova linha `S002` a cada clique se já
  existisse uma. Decisão explícita do usuário foi **não replicar isso**:
  o comportamento final é **idempotente** — insere uma linha de serviço
  código reservado **`S002`** valendo **10% do subtotal** (excluindo a
  própria linha `S002` da base de cálculo, senão cada clique inflaria o
  valor sobre si mesmo); se já existe uma linha `S002`, um novo clique
  **atualiza o valor dela** em vez de empilhar outra. Sem pedido de
  confirmação por "já existir" — só uma confirmação simples antes de
  incluir/atualizar. Defensivo: se sobrar mais de uma linha `S002` de uma
  versão anterior, consolida numa só em vez de deixar duplicatas.
- **Bug corrigido no mesmo dia — "não está incluindo a taxa de serviço"**:
  a primeira versão usava `Alert.alert` (react-native) pro diálogo de
  confirmação. No **react-native-web, `Alert.alert` é um no-op silencioso**
  (`class Alert { static alert() {} }` — sem diálogo nativo no browser),
  então o clique no botão simplesmente não fazia nada no web, sem erro
  nenhum. Corrigido adicionando `showConfirm` ao `FeedbackProvider`
  (`src/components/feedback/FeedbackProvider.tsx`) — diálogo Sim/Não
  centralizado, estilizado igual ao resto do app, funciona igual em web e
  mobile. **Reusável daqui pra frente** — qualquer outra tela que hoje usa
  `Alert.alert` pra confirmação (`servicos.tsx`, `fornecedores.tsx`,
  `notas-fiscais.tsx`, etc. — grep por `Alert.alert` acha mais de 10
  arquivos) tem o mesmo bug latente no web e deveria migrar pra
  `useFeedback().showConfirm` quando essas telas forem tocadas de novo —
  não foi feita uma varredura retroativa agora (fora do pedido desta
  rodada), só documentado aqui.
- Backend: `TAXA_SERVICO_CODIGO`/`TAXA_SERVICO_PCT` +
  `_add_taxa_servico_sync`/`add_taxa_servico` em `itens_service.py`;
  request `TaxaServicoRequest` em `models/schemas.py`; rota
  `POST /api/pedidos/{pedido}/taxa-servico` em `routes/pedidos.py`, com
  log de auditoria (`tela=PEDIDO, comando=TX_SERVICO`).
  **Só em `pedidos.py`, não em `pedido_completo.py`** — feature exclusiva
  do segmento Bar (`frmmanpedfor.frm`, origem do Pedido Completo, não tem
  esse botão).
- Se o serviço `S002` não estiver cadastrado em `servicos`, o legado falha
  silenciosamente (`Exit Sub` sem mensagem) — **melhoria deliberada**:
  aqui retorna uma mensagem clara em vez de replicar o silêncio.
- Permissão nova: `PEDIDO.TX_SERVICO` ("Taxa de serviço") em
  `ACOES_PEDIDO` — **não** adicionada a `ACOES_PEDIDO_COMP` (mesmo
  raciocínio de escopo: só Pedido Bar).
- Frontend: botão "Tx Serviço" em `ItemList.tsx`, ao lado do pill
  "Descontos" (posição pedida explicitamente pelo usuário). Gate:
  `isAberto && can("PEDIDO.TX_SERVICO")` — como só `PEDIDO` tem essa
  permissão no catálogo, o botão nunca aparece em Pedido Completo
  automaticamente, sem precisar de prop extra.
- 14 testes unitários em `test_itens_service.py` (`TestAddTaxaServico` +
  ordenação) — 407 testes de backend passando.
- **Não testado ao vivo** (sem chromium-cli/credenciais neste sandbox) —
  só tsc/testes unitários/boot do backend.

### Ajustes de UX no mesmo dia (2026-07-15, mesma rodada)

1. **Sem confirmação** — pedido explícito do usuário: o botão não pede
   confirmação nenhuma antes de incluir/atualizar, só avisa via toast
   ("Taxa de serviço incluída/atualizada (R$ X)."). O `showConfirm` novo
   no `FeedbackProvider` ficou sem uso neste fluxo específico, mas
   continua valendo como padrão pra outras telas (ver
   `feedback_alert_alert_noop_on_web` na memória) — não foi removido.
2. **Ordenação fixa** — a linha `S002` (Taxa de Serviço) agora sempre
   aparece **por último** na lista de itens, independente de quando foi
   incluída/atualizada (`ORDER BY CASE WHEN produto='S002' THEN 1 ELSE 0
   END, codauto` em `_list_itens_sync`).
3. **Estado visual "ativo"** — o pill "Tx Serviço" fica **verde** (mesma
   cor do "Fechar Pedido") com ícone de check quando já existe uma linha
   `S002` no pedido, cinza/outline quando ainda não foi incluída.
4. **Agrupamento dos pills de ação** — "Margem", "Desconto geral" e "Tx
   Serviço" foram consolidados todos juntos na mesma faixa (ao lado do
   pill "Descontos"), abaixo do cabeçalho "Itens do Pedido". Só "Fechar
   Pedido" ficou isolado, numa faixa própria acima (ação terminal,
   visualmente mais destacada/verde já por padrão).
5. **Nunca pode haver 2 linhas de Taxa de Serviço no pedido** — reportado
   pelo usuário com print do modal "Adicionar Item" mostrando "TAXA 10%"
   listada como um item normal (com botão "+" de repetição rápida), o que
   permitiria incluir uma segunda linha `S002` pelo fluxo genérico. Dois
   reforços:
   - Backend: `_add_item_sync` (`itens_service.py`) e
     `_add_item_completo_sync` (`pedido_completo_service.py`) agora
     **bloqueiam** incluir `produto=S002` manualmente — mensagem "Taxa de
     Serviço não pode ser adicionada manualmente — use o botão 'Tx
     Serviço'." `TAXA_SERVICO_CODIGO` movida pro topo de
     `itens_service.py` (era declarada só perto de
     `_add_taxa_servico_sync`) e reexportada pra
     `pedido_completo_service.py` importar.
   - Frontend: `pedidoProdutos` (lista padrão do modal "Adicionar Item",
     ver seção "Adicionar Item" mais acima) agora **exclui** o produto
     `S002` — outros serviços continuam aparecendo normalmente ali
     (confirmado explicitamente com o usuário: só a Taxa de Serviço sai
     dessa lista, não serviços em geral).
6. **Taxa de Serviço só pode ter 1 unidade** — `_update_item_sync`
   (`itens_service.py`) agora busca o `produto` do item antes de validar
   e bloqueia qualquer tentativa de mudar a quantidade da linha `S002`
   pra um valor diferente de 1 ("Taxa de Serviço deve ter sempre 1
   unidade."). Valor/desconto/acréscimo dessa linha continuam editáveis
   normalmente pela tela de edição — só a quantidade é fixa.
7. **Taxa de Serviço se auto-atualiza quando um novo item é incluído** —
   pedido explícito do usuário: se o pedido já tem uma linha `S002` e um
   novo produto/serviço é adicionado (por qualquer um dos dois fluxos,
   `_add_item_sync`/`_add_item_completo_sync`), a taxa é recalculada (10%
   do novo subtotal, excluindo a própria taxa) e atualizada
   automaticamente — sem precisar clicar em "Tx Serviço" de novo. Lógica
   compartilhada extraída pra `sincroniza_taxa_servico_apos_alteracao`
   (chamada por ambos os fluxos de adicionar item) +
   `_recalc_valor_taxa_servico` (reaproveitada também por
   `_add_taxa_servico_sync`, elimina duplicação de SQL). **Não cria** uma
   linha nova se não existir — só atualiza se já existir; inclusão em si
   continua exclusiva do botão dedicado.
- 12 testes novos no total pra essa leva de guardas
  (`TestBloqueiaAdicionarTaxaServicoManualmente`,
  `TestUpdateItemTaxaServicoQtdFixa`,
  `TestAddItemSincronizaTaxaServicoExistente`) — 415 testes de backend
  passando.
8. **Ícone dedicado**: usuário passou uma imagem de referência (garçom
   segurando uma bandeja com redoma) pedindo esse ícone especificamente
   pra Taxa de Serviço. A imagem em si é uma foto de banco de imagens
   (marca d'água visível) — não dá pra embutir literalmente. Ionicons (o
   único conjunto de ícones usado no app até agora, via
   `src/components/Ionicons.tsx`) não tem nada parecido; o mais próximo
   disponível é `MaterialCommunityIcons`'s `room-service` (bandeja +
   redoma, a mesma peça central da imagem de referência) — já vem junto
   no pacote `@expo/vector-icons` já instalado, não é uma dependência
   nova. Aplicado em `ItemList.tsx` (linha do item na lista) e
   `AddItemModal.tsx` (resultado de busca), tanto no ícone do item quanto
   no ícone do pill "Tx Serviço" no toolbar.
   - **Caveat Windows**: `MaterialCommunityIcons` é importado direto de
     `@expo/vector-icons` (não pelo wrapper `Ionicons.tsx`/
     `Ionicons.windows.tsx` deste projeto), então carrega via `expo-font`
     — que não roda no Windows RNW (native module não portado, ver
     `windows-polyfills/setUpExpoGlobal.js`). Ficaria como "tofu box" se
     alguém abrisse essa tela no app Windows hoje. Inofensivo porque a
     plataforma Windows está **pausada** (CLAUDE.md > "Platform Scope",
     desde 2026-07-10) — se for retomada no futuro, esse ícone específico
     precisaria do mesmo tratamento que `Ionicons.windows.tsx` já dá
     (glyph map + referência direta ao `.ttf` empacotado) antes de
     funcionar lá.

### Botão "Pedido Totalizado [F9]" — implementado 2026-07-16

Rastreado do `.frm`: handler `Command65_Click` (também via F9,
`Form_KeyUp`). Diferente de todas as rotinas anteriores desta seção, **é
puramente leitura** — nenhum INSERT/UPDATE/DELETE, só agrupa os itens já
lançados no pedido numa única linha por produto com a quantidade e o
**valor total** somados, em vez da lista crua com uma linha por inclusão
(útil quando o mesmo produto foi adicionado em rodadas separadas). Mostra
o total geral no fim.

- **Correção 2026-07-16, user-directed** ("esse botão não só lista os
  produtos. Ele lista o total de cada produto"): a 1ª versão agrupava por
  `codigo_fab`+`descricao`+`p_venda` (replicando o `GROUP BY` literal do
  legado) — o que dividia o mesmo produto em várias linhas se o preço
  unitário variasse entre inclusões (ex. desconto aplicado diferente numa
  rodada). Corrigido pra agrupar só por produto (`item.produto`, a chave
  real), somando quantidade **e** valor de cada linha antes de juntar —
  cada produto sempre vira uma linha só, com o total certo mesmo com
  preços diferentes entre as inclusões. A "média" do preço unitário
  (`valorTotal / qtd`) aparece como informação secundária, não mais como
  se fosse um preço único.
- **100% client-side, sem endpoint novo** — como é só um reagrupamento do
  que já está carregado em `it.itens` (mesmos dados já exibidos na lista
  principal), a lógica inteira vive em `usePedidoItens.ts`
  (`pedidoTotalizadoGrupos`/`pedidoTotalizadoTotal`, `useMemo` sobre
  `itens`) — nenhuma chamada à API, nenhuma mudança de backend.
- **Query do legado não filtra `item_cancelado`** (ao contrário de toda
  outra query de total já portada neste projeto) — não replicado como
  workaround: `it.itens` já vem filtrado (só itens não cancelados) do
  endpoint de listagem, então o agrupamento client-side já exclui
  cancelados automaticamente, sem precisar de tratamento especial.
- Exibido em modal (`PedidoTotalizadoModal.tsx`, mesmo padrão de
  `DiscountsReportModal.tsx` — pedido explícito do usuário "mostrar em um
  modal").
- **Exclusivo do Pedido Bar** — `frmmanpedfor.frm` (origem do Pedido
  Completo) não tem esse botão; gate simples por `tela === "PEDIDO"`,
  sem permissão própria no catálogo (mesmo precedente já registrado em
  memória — sub-tela/relatório só-leitura não precisa de `BOTAO`
  dedicado).
- Botão posicionado ao lado do "Tx Serviço" (pedido explícito do
  usuário), ícone `receipt-outline`.
- **Não testado ao vivo** (sem chromium-cli/credenciais neste sandbox) —
  só tsc/boot do backend (que nem precisou reiniciar, mudança é só
  frontend).

### Cabeçalho reorganizado + campo Entrega — implementado 2026-07-16

Sequência de ajustes pedidos em cima do cabeçalho de `pedido-form.tsx`
(Pedido Bar), todos aplicados nesta rodada:

1. **Vendedor movido pro cabeçalho**, dentro da barra azul (mesma cor de
   fundo do botão "Gravar"), ao lado do título "Pedido #N". Passou por 3
   posições até chegar aqui (Dados Principais → linha abaixo do
   cabeçalho, à direita → dentro da própria barra) — decisão final do
   usuário.
   - `PedidoHeader.tsx` ganhou prop `titleExtra?: React.ReactNode`
     (conteúdo livre ao lado do título, ainda dentro da barra).
   - `SelectField.tsx` (componente compartilhado, ~56 consumidores)
     ganhou 2 props novas, ambas opt-in e retrocompatíveis:
     - `hideSub?: boolean` — esconde a linha de subtítulo (ex.: código)
       pra economizar espaço; o texto completo aparece num **tooltip**
       (`onHoverIn`/`onHoverOut` no web; sem equivalente touch no
       mobile, que não tem hover).
     - `variant?: "default" | "onDark"` — estilo pill translúcido branco
       (`rgba(255,255,255,0.18)` fundo, `rgba(255,255,255,0.3)` borda,
       texto/ícones brancos), mesmo padrão visual do botão "Gravar" —
       pra uso dentro de barras de cabeçalho (fundo `brandPrimary`).
   - Aplicado no Vendedor do cabeçalho: `variant="onDark" hideSub
     compactWeb`.
2. **`compactWeb` aplicado retroativamente** nos 2 `SelectField` que já
   existiam em `pedido-form.tsx` (Vendedor, Área de Atuação) — ambos
   estavam sem essa prop, violando o padrão já documentado ("SelectField
   sempre com compactWeb") — corrigido ao tocar no arquivo.
3. **Campo "Entrega [data] às [hora]" + checkbox "Pedido Entregue"** —
   rastreado do `.frm`: colunas reais `pedido_venda.previsao_entrega`
   (date), `pedido_venda.hora_entrega` (NVARCHAR, mesmo padrão de
   `hora_aberto`), `pedido_venda.pedido_entregue` (bit). O checkbox
   (`Check88_Click` no legado) **grava direto no clique**, fora do fluxo
   normal de Gravar — replicado fielmente via endpoint dedicado
   `POST /api/pedidos/{pedido}/entregue` (não passa pelo save normal).
   - Backend: `PedidoSaveRequest` ganhou `previsao_entrega`/
     `hora_entrega`; novo `PedidoEntregueRequest` +
     `_toggle_entregue_sync`/`toggle_entregue` em `pedidos_service.py`;
     `_get_pedido_sync`/`_save_pedido_sync` atualizados pra ler/gravar os
     3 campos. Nova permissão `PEDIDO.ENTREGUE` ("Marcar como
     entregue") — só pro checkbox (as datas em si não têm gate próprio,
     fazem parte do `GRAVAR` normal). 5 testes novos
     (`test_pedidos_service.py`, arquivo novo — não existia
     cobertura unitária pra `pedidos_service.py` antes) — 420 testes de
     backend passando.
   - Frontend: data via `DateField` (já cross-platform, reaproveitado do
     campo "Data"/"Validade" já existente nesta tela); hora via
     `WebDateField type="time"` no web (padrão obrigatório de CLAUDE.md)
     com fallback de `TextInput` livre ("HH:MM") no mobile, já que não
     existe um seletor de hora cross-platform neste projeto ainda —
     registrado aqui como gap conhecido, não resolvido agora. Checkbox
     "Pedido Entregue" só aparece com o pedido já salvo (mesmo gate
     `AlteraEntrega`/`Trim(Dados(1))=""` do legado) e gated por
     `can("PEDIDO.ENTREGUE")`.
   - **Não trazido pro Pedido Completo** — mesmo escopo Bar-only já
     estabelecido pro Tx Serviço/Pedido Totalizado (`frmmanpedfor.frm`
     não tem essa tela de Entrega).
4. **Card de telefone/endereço do cliente virou botão** — antes ficava
   sempre visível, empilhado abaixo do card de nome (largura total);
   agora fica **ao lado** do card de nome (compacto, 220px, ainda
   mostrando telefone+endereço truncados em 1 linha cada), e tocar nele
   abre um modal "Dados Principais" com o conteúdo completo (telefone,
   endereço, e-mail, sem truncar). `ClienteSection.tsx` é compartilhado
   com `pedido-completo.tsx` — a mudança de layout vale pras duas telas.
5. **Ajuste de layout do cabeçalho (mesmo dia, esclarecido via pergunta ao
   usuário — as duas frases originais pareciam se contradizer)**: Entrega
   fica confirmada na MESMA linha da situação "Aberto", à direita da tela
   (não dentro do accordion "Dados Principais") — corrigido o wrap/quebra
   de linha que estava acontecendo (`flexWrap: "nowrap"`, larguras fixas
   pros campos). O botão "Dados Principais" (`AccordionSection.tsx`,
   compartilhado com Pedido Completo) ganhou aparência de cartão real
   (fundo, borda, padding) em vez de só texto+chevron — mesma mudança
   vale pras duas telas.
- **Não testado ao vivo** (sem chromium-cli/credenciais neste sandbox) —
  só tsc/testes unitários/boot do backend em cada etapa.

### Filtros do painel "Pedidos Abertos" na lista de Pedidos — implementado 2026-07-16

Usuário pediu pra trazer os filtros da tela antiga do VB6 (print: checkboxes
Mesa/Balcão/Comanda/Entrega, radio "Ordenar por" Abertura/Tipo/Cliente,
"Data de Entrega em") pra `pedidos.tsx` (lista compartilhada Mobile/Bar +
Completo). Rastreado no `.frm`: `Sub PedidosAbertos()` + `Sub
CataTipoCliente()`.

- **Achado-chave**: os checkboxes Mesa/Balcão/Comanda/Entrega **não são um
  tipo de pedido** — filtram por `cliente.cliente_forn` (o TIPO DO
  CLIENTE), procurando linhas específicas em `tipo_cliente` com
  `descricao` exatamente 'MESA'/'BALCÃO'/'COMANDA'/'ENTREGA'.
  `CataTipoCliente()` habilita cada checkbox **só se essa linha existir**
  no banco daquela empresa (data-driven, não hardcoded) — mesmo mecanismo
  já usado pra Mesa/Comanda como "clientes reservados" (ver guarda de
  renomeio implementada antes nesta mesma sessão).
- **"Ordenar por"** (`Option7`/`Option8`/`Option9` no legado): Abertura →
  `data, hora_aberto`; Tipo → `tipo_cliente.descricao, cliente.nome`;
  Cliente (default do legado) → `cliente.nome`.
- **"Data de Entrega em"**: filtra `previsao_entrega <= data_entrega`
  (mesmo operador do legado — pedidos com entrega prevista até aquela
  data, não só naquele dia exato).
- Backend: `PedidosListRequest` ganhou `tipos_cliente`/`data_entrega`/
  `ordenar_por` (todos opcionais — sem eles, `_list_pedidos_sync` mantém
  o comportamento exato de antes, `ORDER BY p.pedido DESC`, nada quebra
  pra quem já usa essa lista). `LEFT JOIN tipo_cliente` adicionado só pra
  suportar `ordenar_por=tipo`. 7 testes novos
  (`TestListPedidosFiltrosPedidosAbertos`) — 427 testes de backend
  passando.
- Frontend: reaproveitado `GET /api/tipo-cliente` (endpoint já existente,
  usado por Cliente Completo) pra descobrir quais dos 4 tipos existem na
  empresa — só mostra checkbox pros que existirem, igual ao legado.
  **Painel inteiro gated por `moduleOn("Bar")`** — Mesa/Comanda/Balcão só
  fazem sentido no segmento Bar; Pedido Completo (Pedido de Venda geral)
  não vê esse painel, mesmo usando a mesma tela de lista.
- **Não testado ao vivo** (sem chromium-cli/credenciais neste sandbox) —
  só tsc/testes unitários/boot do backend.

### Não implementado — BLOQUEADO, requer confirmação do usuário

O `.frm` colado cobre um fluxo de PDV completo bem além do que foi pedido
explicitamente nesta rodada (rebatismo + gating + guarda de cliente). Não
implementado, registrado aqui pra não implementar em cima de suposição
(regra "Gestão de Pendências entre Telas", CLAUDE.md §10):

- **Painel "Pedidos Abertos"** — a tela real de Bar não é um formulário
  único como `pedido-form.tsx`/`pedido-completo.tsx`; é uma grade/lista de
  comandas/mesas com pedido em aberto, cada uma abrindo pro
  detalhe/inclusão de item. Isso é uma tela nova, não uma variação do
  Pedido Mobile existente — `pedido-form.tsx` hoje é um formulário
  single-record, sem esse painel de mesas.
- **Faturar / Gerar Comanda** — 🟢 **implementado 2026-07-16, só a parte
  não-fiscal** (decisão explícita do usuário via pergunta direta, ver
  "Perguntas em aberto" #2 abaixo). Botão "Faturar Pedido" ao lado de
  "Fechar Pedido" em `pedido-form.tsx` (`ItemList.tsx`, exclusivo de
  `tela==="PEDIDO"` — não aparece no Pedido Completo). **Não exige clicar
  em "Fechar Pedido" antes** (correção do usuário no mesmo dia, mesmo
  comportamento de `Command111_Click` no legado): aparece com o pedido
  Aberto OU Fechado; se ainda Aberto, o backend fecha (mesma rotina do
  endpoint `/fechar`, via helper compartilhado `_fechar_pedido_itens` em
  `pedido_common.py`) e já emenda o faturamento na mesma transação — se o
  faturamento falhar depois, o fechamento automático também é desfeito
  (rollback). Backend:
  `_faturar_pedido_sync`/`faturar_pedido` em `pedidos_service.py`, rota
  `POST /api/pedidos/{pedido}/faturar` em `routes/pedidos.py` — porta
  `Command111_Click`/`GeraComanda` (`FrmManPedBar.frm`) SEM a parte fiscal:
  valida `situacao='F'` e `pedido_venda.forma_pag` preenchido (versão
  simplificada de `Fecha_FPAG_Dav`/`QtdFormas` — este projeto usa um único
  campo `forma_pag` por pedido, não a quebra multi-forma do legado, que
  não existe em nenhuma tela desta migração ainda), insere `comanda`
  (situação 'PG'), libera `pecas.reservado` das peças (`_liberar_reservado`
  em `pedido_common.py` — a baixa de `qtd` já aconteceu no Fechar), grava
  `movimentacao` (tipo 'S01', serie_nf 'CM') pra cada item, vincula
  `COMANDA_PED` e marca `pedido_venda.situacao='PG'`. Reusa a permissão
  `PEDIDO.SITUACAO` (mesmo raciocínio já documentado de "Fechar e Cancelar
  usam a mesma ação") e loga auditoria `comando="SITUACAO"`. Schema de
  `comanda`/`movimentacao`/`COMANDA_PED` conferido ao vivo em
  `gibanweb.database.windows.net/BDREACTAPP` antes de escrever o código
  (`comanda.comanda`/`movimentacao.id_mov` são IDENTITY). 7 testes
  (`TestFaturarPedido` em `test_pedidos_service.py`) — 437 testes de
  backend passando. **Não testado com um ciclo completo Abrir→Fechar→
  Faturar (nem Abrir→Faturar direto) ao vivo** (só o caminho "pedido não
  encontrado", que não muta dado nenhum) — validar isso é o primeiro
  passo ao retomar esta área.
  A emissão de NFC-e via `Backon_Controllers.Nfe` continua bloqueada —
  regra `[GLOBAL]` de CLAUDE.md §12 ("Telas Fiscais"): exige confirmação
  explícita do usuário antes de implementar, mesmo que pareça pequena.
- **Impressão de comanda/cupom térmico** — mesmo bloqueio já registrado em
  CLAUDE.md > "Platform Scope" > nota de 2026-07-10: a decisão já tomada
  foi resolver impressão via backend+socket (rede) + agente local
  dedicado (USB), não embarcado no app. Nenhuma dessas peças existe ainda.
- **Controle de horário de abertura/fechamento, cálculo de troco,
  localização de mesa (layout)** — regras de UI/negócio específicas do
  `.frm` ainda não rastreadas campo-a-campo em detalhe (a leitura desta
  rodada focou em identificar o escopo geral e nos 4 itens pedidos
  explicitamente, não em rastrear o form inteiro linha a linha como foi
  feito com `frmmanpedfor.frm`).

### Perguntas em aberto

1. O painel "Pedidos Abertos" (mesas/comandas em aberto) deve reaproveitar
   a lista já existente `pedidos.tsx` (com um filtro/visão específica pro
   segmento Bar) ou é uma tela nova e completamente separada? `pedidos.tsx`
   hoje é uma lista genérica de registros de `pedido_venda` — não tem
   noção de "mesa"/"comanda" como agrupamento visual.
2. ~~A emissão de NFC-e no fechamento da comanda é escopo desta migração
   agora, ou fica pra uma fase fiscal separada~~ — **respondido
   2026-07-16**: por enquanto NÃO, só a parte não-fiscal do Faturar
   Pedido foi implementada (ver acima). Emissão de NFC-e continua em
   aberto pra quando (se) uma fase fiscal for iniciada — mesmo caveat de
   CLAUDE.md §12 se aplica quando isso for retomado.
3. Impressão térmica de comanda: usa a mesma infraestrutura
   backend+socket/agente local já decidida para impressão automática por
   Finalidade (ver memória `project_impressao_automatica_finalidade`), ou
   é um fluxo separado? Nenhuma das duas foi implementada ainda, então não
   há uma peça existente pra simplesmente reaproveitar hoje.
4. O padrão de mesa (M+número) e comanda (C+número) detectado no guard de
   backend foi inferido só a partir do texto do usuário e do nome
   "MESA"/`M15`/`C1` — não foi confirmado se existem outras variações de
   nomenclatura já em uso em bancos reais (ex. `MESA15` sem separador,
   `BALCAO`, `M-15` com hífen). Se ao testar em uma conexão real (a
   conexão "BAIXO BRISA", segmento Bar, anexada pelo usuário pra testes)
   aparecer um padrão diferente, ajustar `_cliente_mesa_ou_comanda` —
   confirmar antes de ampliar a regex pra não bloquear renomeio de
   clientes comuns por engano (falso positivo é pior aqui do que falso
   negativo, já que o guard é uma trava de segurança, não uma feature
   visível).

---

## Forma de Pagamento (FrmForPag.frm)

**Status**: 🟢 **implementado 2026-07-16.** Combobox simples (1 forma) +
modal completo (`[F2] Exclui / [Duplo Clique] Altera` do legado viraram
ícones de lápis/lixeira na linha, ver "Simplificações" abaixo) — pedido
`[GLOBAL]` do usuário, com print da tela legada anexado.

**Registrada e concluída em**: 2026-07-16.

### Escopo e decisão do usuário

Pedido original: "Pode ser escolhido selecionando uma combobox se o pedido
tiver somente uma forma de pagto. Caso o pedido tenha mais de uma forma de
pagto, o usuário clicará em um botão e selecionar todas com as regra da
tela." Perguntado sobre faseamento (todos os 8 tipos vs. subconjunto) —
usuário escolheu **"Todos os 8 tipos agora"** e confirmou explicitamente
que a tela `FrmForPag.frm` **atende Pedido Bar, Pedido Geral (Completo) e
O.S.** — não só Pedido Bar como a primeira leitura do rastreio VB6 tinha
como escopo.

### Rastreio VB6 (`Geral\frmforpag.frm`)

Tela genérica no legado, parametrizada por uma struct global única
(`mdl_proc.bas`):
```vb
Type Type_FormaPagPedOS
    Documento As String
    Tipo As String        ' "PED", "OS" ou "AGE"
    Forma_Padrao As String
    valor As String
    valor_garantia As String
    valor_cliente As String
    Situacao As String
End Type
Global FormaPagPedOS As Type_FormaPagPedOS
```
Chamada por `FrmManPedBar.frm` (Tipo="PED"), `frmmanpedfor.frm` (Tipo="PED")
e `FrmAtende.frm` (Tipo="OS"/"AGE" — Agenda fora de escopo, não migrada).

8 tipos (`forma_pagamento.tipo`), cada um numa tabela própria — `Command5_Click`
(Gravar) faz um `Select Case tb("tipo")` decidindo tabela/campos:

| Tipo | Tabela (PED)/`os_*` (OS) | Campos extras |
|---|---|---|
| DI Dinheiro | `pedido_venda_dinheiro` | nenhum |
| CH Cheque | `pedido_venda_cheque` | banco, agência, conta, número, nome, telefone, bom_para |
| CC Cartão Crédito | `pedido_venda_cartao` | nº cartão (4 partes), validade, parcelas, administradora, parcelador |
| CD Cartão Débito | `pedido_venda_debito` | banco, agência, conta, parcelas, administradora, parcelador |
| DU Duplicata | `pedido_venda_duplicata` | vencimento (calculado via `forma_pag_prazo` ou digitado) |
| TI Ticket | `pedido_venda_ticket` | nenhum |
| VA Vale | `pedido_venda_vale` | bom_para |
| FI Financiado | `pedido_venda_financiado` | mesmos campos de cartão + data_venc |

**Vencimento da Duplicata**: se a forma tem prazos cadastrados em
`forma_pag_prazo` (prazo/percentual), rateia o valor em N parcelas
(`vencimento = hoje + prazo`, última parcela absorve arredondamento). Sem
prazo cadastrado, o legado usa uma grade de rateio manual (`FrmFaturado`) —
**não portada** (ver Simplificações).

**Validação "dura" não é desta tela** — `FrmForPag` só avisa via `MsgBox`
se o total não bate, sem bloquear (`Form_QueryUnload`). Quem bloqueia de
verdade é `Fecha_FPAG_Dav(FormaPadrao, Tipo, Documento, valor, Fechando)`
em `FormaPagamentoDAV.bas`, chamada no **fechamento** do Pedido/O.S.
(`Command111_Click`/equivalente): se o total não bate e só existe 1 forma
lançada, corrige automaticamente o valor dela; se não há nenhuma e uma
forma padrão foi informada, lança automaticamente; se 2+ formas divergem,
bloqueia com "Informar a Forma de Pagamento corretamente!"; se zero formas
e valor>0, bloqueia com "Defina a Forma de Pagamento".

### Implementação — Backend

- **`DavPagamento`** (dataclass em `pedido_common.py`) — réplica direta do
  `Type_FormaPagPedOS` (tipo/documento/situacao/valor/forma_padrao), no
  mesmo espírito do "tipo central" já usado em `gestor_documentos_service.py`
  (`GRUPO_*`/`_JUNCAO`) — pedido explícito do usuário ("naquele esquema
  tipo do gestor, com um type global"). `DAV_PED`/`DAV_OS` mapeiam pra
  prefixo de tabela (`pedido_venda_`/`os_`) + coluna FK (`pedido_venda`/`os`).
  Agenda (`AGE`) não incluída — não migrada em nenhuma tela ainda.
- **Helpers em `pedido_common.py`**: `_totaliza_dav`/`_qtd_formas`/
  `_unica_forma_existente` (somam/contam as 8 tabelas), `_atualiza_valor_forma`,
  `_insere_duplicata_parcelada` (rateio por `forma_pag_prazo`),
  `_cadastra_forma_automatica`, `_fecha_fpag_dav` (réplica completa de
  `Fecha_FPAG_Dav`). Schema de todas as 8 tabelas PED + 8 OS +
  `forma_pag_prazo` conferido ao vivo em `gibanweb.database.windows.net/
  BDREACTAPP` antes do código (`sequencia` é IDENTITY em todas).
- **`_fechar_pedido_itens`** (já existente, usado por Fechar/Faturar do
  Pedido Bar) ganhou `subtotal`/`forma_padrao` e agora chama `_fecha_fpag_dav`
  + a checagem `QtdFormas=0` antes de mover estoque — mesma ordem do
  `Command111_Click`. **Reaproveitada também por `pedido_completo_service.py`**
  (`_fechar_pedido_completo_sync` tinha uma cópia dessa lógica sem a parte
  de forma de pagamento — consolidado numa função só, elimina duplicação
  pré-existente). `_fechar_os_sync` (`os_service.py`) ganhou a mesma
  validação (não tinha nenhuma antes).
- **`forma_pagamento_service.py`** (novo) — CRUD (list/add/update/delete)
  genérico por `tipo_dav`, camada fina sobre os helpers acima. Rotas
  espelhadas em `routes/pedidos.py` (`/api/pedidos/{pedido}/formas-pagamento`)
  e `routes/os.py` (`/api/os/{codigo}/formas-pagamento`) — Pedido Bar e
  Pedido Completo **compartilham as mesmas rotas** (`tipo_dav="PED"`, mesma
  tabela `pedido_venda`), só a **permissão** difere (`tela` no payload:
  `PEDIDO` vs `PEDIDO_COMP`, default resolvido em `_TELA_POR_DAV` se omitido).
- **`forma_pag`/`forma_pagamento` no cabeçalho**: `pedidos_service.py`
  (Pedido Bar) e `os_service.py` (O.S.) não tinham esse campo em nenhum
  lugar (schema/save/get) — adicionado (`pedido_venda.forma_pag`,
  `os.forma_pagamento` — nomes de coluna diferem entre as duas tabelas,
  confirmado ao vivo). Pedido Completo já tinha.
- **Permissão `FORMA_PAG`** ("Forma de pagamento") em `ACOES_PEDIDO`,
  `ACOES_PEDIDO_COMP` e `ACOES_OS` — checkbox próprio, não reaproveita
  `SITUACAO` (mesma regra `[GLOBAL]` de "cada botão real da tela tem seu
  checkbox", já aplicada ao `FATURAR` do Faturar Pedido no mesmo dia).
- **Novo lookup** `GET /api/forma-pagamento-completo` (`lookups_service.py`)
  — como `/api/forma-pagamento`, mas inclui `tipo`, usado pelo modal pra
  decidir quais campos extras mostrar por forma escolhida.
- **22 testes novos** (`test_pedido_common_forma_pagamento.py` —
  `_totaliza_dav`/`_qtd_formas`/`_unica_forma_existente`/`_fecha_fpag_dav`/
  `_insere_duplicata_parcelada` via um `SqlFakeCursor` que casa por
  substring de SQL, não por ordem de chamada; `test_forma_pagamento_service.py`
  — CRUD/permissão/roteamento DI vs. DU) — 465 testes de backend passando.

### Implementação — Frontend

- **`FormaPagamentoModal.tsx`** (novo, `src/components/pedido/`) —
  componente compartilhado, parametrizado por `tipoDav`/`documento`/`tela`,
  usado pelas 3 telas. Combobox de forma + valor + campos condicionais por
  tipo (cheque/cartão/débito/financiado) + grade de lançamentos com ícones
  de editar/excluir (ver Simplificações) + indicador "Lançado X / Falta Y".
- **Pedido Bar** (`pedido-form.tsx`): combobox "Forma de Pagamento" novo no
  modal "Dados Principais" (não existia nenhum campo de forma de pagamento
  nessa tela antes) + botão "Mais de uma forma" abrindo o modal.
- **Pedido Completo** (`pedido-completo.tsx`): já tinha o combobox — só
  adicionado o ícone/botão "Mais de uma forma" ao lado.
- **O.S.** (`os-form.tsx`): combobox novo (não existia) + botão, mesmo
  padrão do Pedido Bar.

### Simplificações conscientes em relação ao legado

1. **F2 (Excluir)/Duplo Clique (Alterar) viraram ícones de lápis/lixeira**
   na linha — keybinding de grid é convenção de UI do VB6, não regra de
   negócio (CLAUDE.md > "Não replicar truques VB6"). Excluir usa
   `showConfirm` (nunca `Alert.alert`/`window.confirm`, ver
   `feedback_alert_alert_noop_on_web`).
2. **Grade de rateio manual de parcelas sem `forma_pag_prazo` cadastrado**
   (`FrmFaturado`) não foi portada — Duplicata sem prazo grava 1 parcela só
   com vencimento "hoje", ajustável depois editando a linha.
3. **Vínculo com `*_vale_devolucao`** (campo condicional "Vale de
   Devolução" do legado) não foi portado — feature de baixo uso.
4. **Editar uma linha não pré-preenche os campos extras** (banco/cartão/
   etc.) — só forma/valor/vencimento. Usuário redigita os extras se
   precisar mudar algo além disso. Simplificação de escopo, não uma regra
   perdida (os dados antigos continuam no banco até serem sobrescritos).

### Não testado

**Não testado com lançamento real de múltiplas formas via UI (só smoke
test de endpoints contra pedido/OS inexistentes, que não mutam dado)** —
validar um ciclo completo (lançar 2+ formas, fechar o pedido, conferir
`Fecha_FPAG_Dav` bloqueando/corrigindo corretamente) é o próximo passo se
esta área for retomada.

### Impressão do Pedido (`Pedido_48_COL`, `FrmManPedBar.frm`)

**Adicionado 2026-07-16.** Réplica da rotina de impressão do recibo do
Pedido Bar — só a parte de conteúdo/layout, **não** a parte de hardware
(impressora térmica). Decisão explícita do usuário: **preview + impressão
do navegador** (`window.print()`), não a infraestrutura de socket/agente
local ainda pausada (ver CLAUDE.md > "Platform Scope" > seção Windows-only/
impressão automática por Finalidade).

- **`frontend/src/components/pedido/ReciboPedidoModal.tsx`** (novo) —
  modal com preview estilo recibo térmico (fonte monoespaçada, largura
  estreita) + botão "Imprimir". Toggle "Imprimir Totalizado" (default
  ligado, espelha `Check100` do legado) reaproveita
  `it.pedidoTotalizadoGrupos`/`it.pedidoTotalizadoTotal` — já implementado
  pro relatório "Pedido Totalizado" — em vez de duplicar a lógica de
  agrupamento.
  **Correção 2026-07-16 (mesmo dia, reportado pelo usuário com screenshot):
  a 1ª versão usava o truque de CSS "esconde tudo com `body *`, mostra só
  `#pedido-recibo-print`" + `window.print()` direto — saía **em branco**
  (o preview de impressão só trazia cabeçalho/rodapé nativos do Chrome,
  nada do conteúdo), provavelmente por algum ancestral — `Modal`/
  `ScrollView`/`Pressable` — cortando o conteúdo via overflow/
  posicionamento antes de a regra de visibilidade conseguir agir.**
  Trocado por um iframe oculto com documento HTML próprio
  (`src/utils/printHtml.ts`, `printHtml(html, title)` + `escHtml`) —
  isolado do resto da página, sem ancestral nenhum pra cortar nada. O
  conteúdo do recibo/ticket agora é montado DUAS vezes: como JSX (preview
  na tela, inalterado) e como string HTML (`buildHtml()` dentro do
  componente, só na hora de imprimir) — as duas precisam ser mantidas em
  sincronia manualmente se o conteúdo mudar de novo.
- **Fonte dos dados do cabeçalho/rodapé**: `controle_service._get_empresa_sync`
  estendido (endereço/número/complemento/bairro/cidade/cep/ddd/telefone/
  celular/cgc/inscr_est/cod_rel — antes só tinha empresa/fantasia/rz_social/
  uf) + rota nova `GET /api/controle/mensagens-pdv` (tabela `mensagenspdv`,
  linhas de rodapé livres). `pedido_venda.LOCALIZACAO` (mesa/balcão) também
  passou a vir no `GET /pedidos/{id}` (`localizacao_descricao`, LEFT JOIN
  com a tabela `localizacao`). Todos os nomes de coluna conferidos ao vivo
  contra `gibanweb.database.windows.net`/`BDREACTAPP`.
- **Botão "Imprimir"** em `ItemList.tsx`, ao lado de "Faturar Pedido"
  (pedido explícito do usuário) — só web (`window.print()` não existe em
  RN mobile), só `tela === "PEDIDO"` (layout de recibo é específico do Bar,
  não existe ainda pro Pedido Completo/O.S.), permissão própria
  `PEDIDO.IMPRIMIR` no catálogo (`ACOES_PEDIDO`, não em `ACOES_PEDIDO_COMP`).
- **Reaproveitado pós-Faturar**: `handleFaturar` (`pedido-form.tsx`) abre o
  modal de impressão automaticamente assim que o faturamento tem sucesso
  ("aproveitar essa implementação para emitir o pedido pós faturar o
  pedido") — o clique em "Imprimir" dentro do modal é que efetivamente
  dispara `window.print()`, não é impressão silenciosa automática. O botão
  na toolbar continua disponível pra reimprimir a qualquer momento depois.
- **Não testado**: smoke test dos endpoints novos (`/api/controle/empresa`
  estendido, `/api/controle/mensagens-pdv`) rodado contra `BDREACTAPP`
  retornou tudo vazio (tabela `controle`/`mensagenspdv` sem linhas nesse
  banco de schema) — sem erro de código, só sem dado de exemplo pra
  validar visualmente o preview renderizado. Validar com uma conexão que
  tenha dado real de empresa/mensagens antes de considerar encerrado.

### Impressão de Item (Cozinha/Bar por Finalidade)

**Adicionado 2026-07-16.** Réplica de `Command1_Click` (disparo automático
ao incluir item, linhas 6425-6447) e `Command62_Click` "&Imprimir Item"
(botão manual, linhas 7805-7902) de `FrmManPedBar.frm`, mais
`Pedido_Geral(item, condensado)` com `item <> ""` (linhas 11282-11501, o
mesmo `Pedido_Geral` já usado pelo recibo completo acima, só que num modo
mais enxuto — sem preço/total/forma de pagamento, só o essencial pra
cozinha/bar) e `CarregaImpressorasDirecionadas` (`mdl_proc.bas:28536`, o
carregamento do array `DirecionamentoImpressora`).

**Duas decisões de arquitetura confirmadas com o usuário (`AskUserQuestion`,
2026-07-16)**, ambas as recomendadas:

1. **Mecanismo = preview + `window.print()`** (não impressão silenciosa via
   TCP/ESC-POS) — mesmo padrão já usado no recibo do pedido inteiro. O VB6
   imprime direto via `Printers()` nativo do Windows, sem diálogo; um
   navegador não tem essa API. "Automática" ligada = preview abre sozinho;
   desligada = pergunta antes (`showConfirm`, nunca `Alert.alert` — ver
   `feedback_alert_alert_noop_on_web`); sem registro pra aquela Finalidade =
   nada acontece. Isso deixa a impressão silenciosa via rede (já esboçada
   em `impressao_service.py`) como um caminho futuro genuinamente
   diferente, não uma evolução incremental deste — precisaria de IP:porta
   real, layout ESC/POS de verdade, e resolver identidade de terminal (item
   2 abaixo não se aplicaria mais do mesmo jeito).
2. **Campo "Computador" do cadastro é IGNORADO** — no VB6 cada terminal
   físico sabia seu próprio hostname (`NomeComputador`, global) e só
   carregava a config daquele PC; não existe equivalente confiável no
   navegador. Decisão: qualquer registro de `direcionamento_impressora`
   cadastrado pra aquela Finalidade vale, não importa o texto em
   Computador — afinal quem escolhe a impressora física de fato agora é o
   próprio usuário, no diálogo de impressão do navegador. O campo
   Computador na tela de cadastro (Controle do Sistema) continua existindo
   e sendo salvo (não removido do cadastro), só deixou de ser filtro nesta
   consulta específica.

**Backend**:
- `services/pedido_common.py::_resolve_produto` — pecas ganhou `tipo_peca`
  no retorno (None pra serviço, que não tem essa coluna).
- `services/itens_service.py::_add_item_sync` — resposta ganhou
  `tipo_peca`, `finalidade_descricao` e `item` (snapshot pronto pro ticket:
  codauto/produto/tipo/descricao/complemento/cod_fab/unidade/qtd —
  sem preço, o ticket de item nunca mostra preço, igual ao legado).
  `_list_itens_sync` ganhou `finalidade_descricao` por item (LEFT JOIN
  `tipo_peca` em cima do JOIN já existente com `pecas`).
- `services/controle_sistema_service.py::_get_direcionamento_por_finalidade_sync`
  (nova) — `SELECT TOP 1 impressora, automatica FROM direcionamento_impressora
  WHERE tipo=%s ORDER BY automatica DESC` (ignora `computador`, decisão #2
  acima). Rota `GET /api/controle-sistema/direcionamento-impressora/por-finalidade?tipo=`.
- Permissão nova `PEDIDO.IMPRIMIR_ITEM` (`ACOES_PEDIDO`, não em
  `ACOES_PEDIDO_COMP` — mesmo escopo Bar-only do `IMPRIMIR`/`FATURAR`/
  `TX_SERVICO`). O disparo AUTOMÁTICO ao incluir item não tem permissão
  própria — reaproveita `ADD_ITEM` (não é uma ação de botão distinta, é um
  efeito colateral do Adicionar Item, igual ao legado).
- 465 testes de backend continuam passando (nenhum teste novo dedicado
  ainda — ver "Não testado" abaixo).

**Frontend**:
- `ReciboPedidoModal.tsx` ganhou um modo "item" (prop `item?: ItemPrintData`)
  — conteúdo reduzido (cabeçalho da empresa, Pedido No./Localização, rótulo
  da Finalidade, descrição do item em destaque + QTD, Obs, dados do
  cliente, "Entrega em..." se houver, mensagens de rodapé) sem
  preço/total/forma de pagamento/vendedor, réplica fiel de `Pedido_Geral`
  com item específico. Reaproveita os mesmos fetches de empresa/mensagens
  já usados pelo modo pedido-inteiro (pula o fetch de formas de pagamento,
  que o modo item não usa).
- `usePedidoItens.ts` ganhou `printPorFinalidade` (prop, só `true` no
  Pedido Bar), estado `printItem`/`setPrintItem`, e
  `checkAutoPrintItem(item, tipoPeca)` — chamado ao final de
  `handleAddItem`/`quickAddItem` (os dois pontos que incluem item),
  consulta a rota nova, e decide abrir direto ou perguntar via
  `showConfirm`. Falha na consulta é silenciosa (best-effort, nunca trava
  o fluxo de adicionar item).
- `ItemList.tsx` — botão "Imprimir Item" (ícone) em cada linha, sempre
  disponível (não condicionado a ter impressora configurada — só a checagem
  automática depende disso), só web, só `tela === "PEDIDO"`, permissão
  `PEDIDO.IMPRIMIR_ITEM`.
- `types.ts` — `ItemRow` ganhou `finalidade_descricao`; tipo novo
  `ItemPrintData` (subconjunto mínimo pro ticket, usado tanto pelo botão
  manual quanto pelo disparo automático, que só tem o item recém-incluído,
  não o `ItemRow` completo com todos os campos de preço).

**Deliberadamente não portado** (ver "Não replicar truques VB6"):
- `DirecionamentoImpressora(k).indice = 200` / busca em `Printers()` local
  — sentinela de "impressora não encontrada no Windows local", sem sentido
  aqui (não há mais correspondência com impressora nativa, quem escolhe é
  o usuário no diálogo do navegador).
- Fallback pro seletor manual de impressora (`FrmPrinter.Show`) quando não
  há `direcionamento_impressora` — não existe "seletor de impressora"
  próprio aqui; o diálogo do navegador já cumpre esse papel sempre que o
  usuário clica "Imprimir" dentro do preview.
- `FechaAutomatico And Trim(Dados(10))="A"` (fecha o pedido automaticamente
  ao imprimir) — efeito colateral do legado sem relação com a feature em
  si; entraria em conflito com o fluxo já implementado de Fechar/Faturar
  (ver seção "Faturar Pedido" acima). Não replicado.
- "Tipo: <tipo_cliente>" no cabeçalho do ticket (categoria do cliente,
  Mesa/Balcão/etc.) — informação secundária, já parcialmente visível via
  Localização/nome do cliente (que já usa `fantasia` tipo "MESA 15" pra
  cliente reservado, ver `feedback_nao_replicar_truques_vb6`/seção Pedido
  Bar acima). Puramente cosmético, não uma regra de negócio.

**Adicionado como modernização** (não estava no legado, mas parece
necessário agora): rótulo "Impressão: <FINALIDADE>" no topo do ticket de
item. No VB6 isso não era preciso porque a impressora FÍSICA já implicava
o setor (impressora ligada só à cozinha, por exemplo); aqui o usuário
escolhe a impressora no diálogo do navegador a cada vez, então o ticket
precisa deixar claro pra qual setor ele é — sem essa pista, a equipe não
saberia diferenciar um ticket de cozinha de um de bar.

**Não testado**: nenhum teste unitário de backend dedicado a
`_get_direcionamento_por_finalidade_sync`/`_resolve_produto` com
`tipo_peca` ainda (a suíte inteira passou porque a mudança é aditiva, sem
quebrar comportamento existente — mas o caminho novo em si não tem
cobertura própria). Fluxo completo (cadastrar impressora por Finalidade,
incluir item, confirmar disparo automático/manual, ver o ticket renderizar
certo) não testado ao vivo contra um pedido/produto real.

---

## Posto de Combustível

**Status**: 🟢 **13 de 13 telas migradas.** Painel completo (ver "Cluster
de Turno" abaixo pro histórico de como as últimas 3 — Fechamento/
Reabertura de Turno e Aferições/Despesas — foram desbloqueadas depois de
modelar `DATESIST`/`turno_movimento` como leitura simples e fresca de
`controle`, nunca como global).

**Registrada em**: 2026-07-13. **Concluída em**: 2026-07-13 (correção de
achado + painel completo + 13/13 telas implementadas, testadas e
documentadas — ver detalhe de cada uma nas seções abaixo).

### Correção de um achado anterior (importante pra quem retomar)

O registro original desta pendência (primeira versão desta seção) concluiu
que a pasta VB6 legada `Posto` (`C:\Desenv\VB6\...\SQLSERVER\Posto`) **não**
tinha telas exclusivas do segmento — conclusão **errada**, baseada numa
busca que não usou os nomes de arquivo certos. Uma nova varredura
(2026-07-13, a pedido do usuário, que forneceu o código-fonte de 12 delas)
confirmou que a pasta `Posto` **tem sim** um conjunto de telas exclusivas,
que só existem lá (não em `Geral`, sem divergência de conteúdo a comparar
já que não há cópia em `Geral`):

| Tela (painel) | Arquivo VB6 (pasta `Posto`) | Tabelas principais |
|---|---|---|
| Bombas ✅ | `frmcadbom.frm` | `Bomba`, `Combustivel` |
| Mov. Encerrantes ✅ | `frmmovbomba.frm` | `Mov_Bomba`, `Mov_Combustivel`, `Custo_Combustivel`, `Bomba`, `Estoque` |
| Aferições/Despesas ✅ | `FrmBaiABc2.frm` | `ABASTECIMENTO`, `controle`, `controle_turno` |
| Fechamento Turno ✅ | `FrmFecTurno.frm` | `BOMBA`, `FECHAMENTO_TURNO`, `abastecimento`, `bomba_encerrante`, `controle_turno`, `controle_turno_horario`, `mov_bomba` |
| Reabertura Turno ✅ | `FrmReaTurno.frm` | `BOMBA_ENCERRANTE`, `controle_turno`, `CONTROLE`, `mov_bomba` |
| Metas Combustível ✅ | `frmcadmet.frm` (não `FrmMetas`; `FrmCadMeta.frm` é rascunho abandonado, ver dúvida 1) | `combustivel_GRUPO`, `combustivel_meta` |
| Combustíveis ✅ | `FRMMANCOM.FRM` | `Combustivel`, `Estoque`, `TABELA_PRECO`, `bomba`, `MOVIMENTACAO` |
| Estoque Combustível ✅ | `frmmanest.frm` | `Estoque`, `combustivel` |
| Custo Combustível ✅ | `frmmancus.frm` | `Combustivel`, `Custo_Combustivel` |
| Ilhas ✅ | `frmmanilha.frm` | `bomba`, `funcionarios`, `ilha` |
| Tanques ✅ | `frmmantan.frm` | `Tanque`, `Combustivel` |
| Tanque/Estoque ✅ | `frmmantes.frm` | `Tanque`, `Tanque_Estoque`, `combustivel` |
| Tanque/Nota Fiscal ✅ | `frmmantnf.frm` | `Tanque`, `Tanque_NF`, `N_Fiscal` |

✅ = implementada e testada ponta-a-ponta (backend + frontend + testes
unitários). Ver "Cluster de Turno" abaixo pro histórico de como as 4
últimas telas (Mov. Encerrantes, Fechamento/Reabertura de Turno,
Aferições/Despesas) foram desbloqueadas.

Nenhuma tabela acima (`combustivel_grupo`, `combustivel_meta`, `tanque`,
`tanque_estoque`, `tanque_nf`, `custo_combustivel`, `bomba_encerrante`,
`controle_turno`, `abastecimento`) existe ainda em nenhum service/route
Python — confirmado por grep, como esperado (nada foi migrado). Duas
tabelas (`mov_bomba`, `ilha`) já são referenciadas indiretamente
(`backend/services/funcionarios_service.py:350-351`, guard de exclusão de
funcionário) — ou seja, **já existem no schema do banco de produção**,
mesmo sem tela própria ainda.

### O que já foi implementado nesta rodada (estrutura do painel)

**Decisões confirmadas com o usuário via AskUserQuestion (2026-07-13)**:
(1) o menu vive como aba de topo própria "Posto" (não tile em Cadastros,
decisão anterior mantida); (2) a ordenação dos 13 cards é **alfabética**,
seguindo a regra geral do projeto (CLAUDE.md > Card List Ordering) — **não**
é uma exceção pra ordem funcional/sequencial do fluxo operacional; (3) o
painel fica **só web** (mesmo padrão da aba, já gateada por
`Platform.OS === "web"` + `moduleOn("Posto")`), sem versão mobile reduzida.

- `frontend/app/(tabs)/posto-combustivel.tsx`: renomeado o título exibido
  pra "Painel Posto de Combustível" (a rota/nome de arquivo continuam
  `posto-combustivel`, só o header mudou). Populado com os 13 cards da
  tabela acima, mesmo padrão estrutural de `cadastros.tsx` (`entries:
  Entry[]`, `visible: can("POSTO_XXX.ABRIR")`, ordenado alfabeticamente).
  Cada card aponta pra `/posto-placeholder?titulo=...` até a tela real
  ser construída.
- `frontend/app/posto-placeholder.tsx` (novo): tela genérica de "em
  construção" reutilizada por todos os cards ainda não migrados — header
  padrão (voltar/logo/título) + card central com ícone e mensagem
  apontando pra este arquivo. Assim que uma tela da tabela acima for
  migrada, seu card em `posto-combustivel.tsx` passa a apontar pra rota
  real em vez do placeholder.
- `backend/services/permissoes_service.py`: `_menu("POSTO", ...)` agora
  tem as 13 `_tela(...)` (chaves `POSTO_BOMBA`, `POSTO_ENCERR`,
  `POSTO_AFERICAO`, `POSTO_FEC_TURNO`, `POSTO_REA_TURNO`, `POSTO_META`,
  `POSTO_COMBUST`, `POSTO_ESTOQUE`, `POSTO_CUSTO`, `POSTO_ILHA`,
  `POSTO_TANQUE`, `POSTO_TQ_EST`, `POSTO_TQ_NF`), cada uma com
  `ACOES_PADRAO` (Abrir/Gravar/Excluir/Imprimir/Exportar) — gating por
  card já funciona hoje, mesmo com a tela de destino ainda não existindo.
- `backend/services/controle_config_service.py`: `MODULE_TELAS["Posto"]`
  adicionado, listando as 13 chaves acima — mesmo padrão de reforço de
  módulo que `"servicos"` já tinha (ver CLAUDE.md > "Regra de Módulo
  Ativo — Gating por Entidade").
- Testado: suite de testes unitários do backend (133 testes) sem
  regressão; catálogo de permissões importado e validado (asserts de
  tamanho de coluna do `_tela`/`_menu` passam pros 13 novos nomes).

### Metas Combustível — implementada 2026-07-13 (1ª das 13)

Migração de `frmcadmet.frm`. Schema conferido ao vivo em GERDELL/BARESTELA
antes de codificar: `combustivel_grupo` (codigo smallint, descricao
nvarchar(20)) e `combustivel_meta` (grupo smallint NOT NULL, ano int NOT
NULL, mes smallint NOT NULL, meta float) — bate exatamente com o
esperado, sem surpresa de nome de coluna.

- **Backend**: `backend/services/combustivel_meta_service.py` (list
  grupos/metas, save upsert por chave composta grupo+ano+mes, delete) +
  `backend/routes/combustivel_meta.py` (`GET /api/posto/combustivel-meta/
  grupos`, `GET /api/posto/combustivel-meta`, `POST /api/posto/
  combustivel-meta`, `POST /api/posto/combustivel-meta/excluir`),
  registrado em `server.py`. Reforço de módulo aplicado (mesmo padrão de
  `servicos`): `_modulo_posto_ativo(cur)` bloqueia as 4 operações se
  `controle_configuracao.Posto` estiver desligado. Gravar/Excluir
  registram em `log_auditoria` (tela `POSTO_META`), mesmo padrão sem diff
  campo-a-campo de `routes/produtos_compostos.py` (chave composta, sem
  PK única pra comparar antes/depois). 13 testes unitários novos
  (`tests/unit/test_combustivel_meta_service.py`) + round-trip completo
  contra GERDELL/BARESTELA (grupos → insere meta → atualiza → exclui →
  confere lista vazia no final, mais grupo inexistente rejeitado) — 146
  testes no total, sem regressão.
- **Frontend**: `frontend/app/posto-meta.tsx` — tela única compacta (sem
  abas, fiel à densidade do `.frm` original: form no topo + lista embaixo,
  sem popup/modal), com guardas web-only e módulo desligado (`LockedView`,
  mesmo padrão de `tipo-servico.tsx`). Card do painel `posto-combustivel.
  tsx` atualizado de `/posto-placeholder` pra `/posto-meta`.
- Regra replicada fielmente do legado: **upsert sem trava de campos ao
  editar** — tocar num item da lista preenche o formulário pra
  conveniência, mas Gravar decide Incluir/Alterar sozinho com base nos
  valores atuais dos campos (grupo+ano+mes), igual ao `Command2_Click`
  original (não há edição "travada" nem confirmação de exclusão no
  legado — replicado assim).
- `tsc --noEmit` no frontend: nenhum erro novo introduzido (mesma
  baseline de 14 erros pré-existentes, não relacionados).

### Demais 8 telas implementadas nesta rodada (2026-07-13)

Mesmo padrão de arquitetura/testes de Metas Combustível em todas: schema
conferido ao vivo em GERDELL/BARESTELA antes de codificar, reforço de
módulo (`posto_common.modulo_posto_ativo`, extraído pra um helper
compartilhado depois de repetido em 2+ services), log de auditoria em
Gravar/Excluir, testes unitários com mock de cursor/conexão, round-trip
real contra o banco (dados descartáveis, sempre limpos ao final). Total:
78 testes unitários novos + 9 rodadas de round-trip real, 223 testes no
total no backend, sem regressão. `tsc --noEmit` no frontend permanece na
mesma baseline de 14 erros pré-existentes (nenhum novo em nenhuma tela).

- **Combustíveis** (`FRMMANCOM.FRM`): `combustivel_service.py` +
  `routes/combustivel.py` + `app/posto-combustiveis.tsx`. **Achados
  importantes**: (1) o campo "Custo" é referenciado no código de
  `CmDinclui_Click` mas **não existe nenhum controle de UI com esse
  índice no `.frm`** — dead code, provavelmente um campo removido do
  formulário sem remover o código; `CmDaltera_Click` tem o bloco
  equivalente inteiramente comentado. Esta migração **não grava
  `combustivel.custo`** (nem no insert nem no update) — evita replicar o
  bug de zerar o custo a cada alteração. (2) `combustivel.grupo` (a
  coluna, distinta de `combustivel_grupo` usada em Metas) nunca é lida
  nem gravada por este `.frm` — deixada de fora, sem tela conhecida que a
  gerencie (ver dúvida 2 abaixo). (3) O legado também faz cascata pra
  `pecas`/`estoque` (trata combustível como produto em paralelo) e
  oferece push de preço pro hardware — ambos fora de escopo (ver
  "Cluster de Turno"/Wayne Fusion abaixo, mesma dependência).
- **Tanques** (`frmmantan.frm`): `tanque_service.py` + `routes/tanque.py`
  + `app/posto-tanques.tsx`. Upsert por `tanque` (PK própria). Guard de
  exclusão adicionado (bloqueia se houver bomba/tanque_estoque/tanque_nf
  vinculados — o legado não tinha guard nenhum aqui, mas as FKs
  declaradas apontam pra essa direção).
- **Estoque Combustível** (`frmmanest.frm`): `estoque_combustivel_service.py`
  + `routes/estoque_combustivel.py` + `app/posto-estoque.tsx`. Chave
  composta (combustivel, data, turno). **Bug do legado corrigido, não
  replicado**: o `Excluir` original deleta por `combustivel+data` **sem
  filtrar turno** — apagaria todos os turnos do dia por engano; aqui usa
  a chave composta completa.
- **Custo Combustível** (`frmmancus.frm`): `custo_combustivel_service.py`
  + `routes/custo_combustivel.py` + `app/posto-custo.tsx`. **Só
  leitura+alteração, sem Incluir/Excluir** — fiel ao legado, que só tem
  botão "Altera" (navegação Anterior/Próximo/Primeiro/Último por um
  recordset, sem Incluir/Excluir). A criação de linhas em
  `Custo_Combustivel` é responsabilidade de outro processo (dúvida
  aberta: qual — ver dúvida 2).
- **Bombas** (`frmcadbom.frm`): `bomba_service.py` + `routes/bomba.py` +
  `app/posto-bombas.tsx`. **Achado importante**: o `.frm` declara um
  botão "Excluir" (`CmDexclui`) mas **não tem nenhum
  `Private Sub CmDexclui_Click()` no código-fonte** — botão morto,
  clicar nele não faz nada. Interpretado como bug/lacuna do legado (não
  regra de negócio "bomba nunca pode ser excluída") — Excluir foi
  implementado de verdade aqui, com guards (`mov_bomba`,
  `bomba_encerrante`). Nenhuma chamada ao hardware Wayne Fusion acontece
  neste formulário especificamente (as chamadas de status/preço vêm de
  OUTRAS telas que consomem os dados gravados aqui).
- **Tanque/Estoque** (`frmmantes.frm`): `tanque_estoque_service.py` +
  `routes/tanque_estoque.py` + `app/posto-tanque-estoque.tsx`. Chave
  composta (tanque, data), upsert.
- **Tanque/Nota Fiscal** (`frmmantnf.frm`): `tanque_nf_service.py` +
  `routes/tanque_nf.py` + `app/posto-tanque-nf.tsx`. Chave composta
  (nota, tanque), upsert. **Simplificação deliberada**: o legado permite
  localizar a Nota Fiscal por código OU por fornecedor+série+número; o
  frontend só expõe busca por código (mais direta) — o backend
  (`GET /posto/tanque-nf/find`) já aceita os dois caminhos, caso o
  segundo modo seja pedido depois.
- **Ilhas** (`frmmanilha.frm`): `ilha_service.py` + `routes/ilha.py` +
  `app/posto-ilhas.tsx`. **Achado de processo, não só de produto**: uma
  primeira leitura de `sys.foreign_keys` sugeriu que `ilha.ilha` referencia
  `bomba.codigo` (não `bomba.ilha`), levando a uma implementação inicial
  errada (combo populado por `bomba.codigo`). Investigando mais a fundo
  (achado nesta mesma rodada, ao mexer em Bombas/Estoque, que
  `estoque.combustivel` tinha DUAS FKs simultâneas pra tabelas
  diferentes — logicamente impossível se ativas), confirmou-se que
  **todas as FKs desta área do schema estão desabilitadas**
  (`sys.foreign_keys.is_disabled=1`) — vestígios de migração antiga, não
  regras vigentes. Revertido pro comportamento fiel ao `.frm` (combo por
  `bomba.ilha`, o número de agrupamento físico). **Lição geral**: nunca
  tratar uma linha de `sys.foreign_keys` como regra vigente sem checar
  `is_disabled`/`is_not_trusted` primeiro (ver
  `feedback_check_vb6_source_tree_first.md` na memória, que ganhou um
  adendo sobre isso).

### Cluster de Turno — CONCLUÍDO (DATESIST + turno_movimento resolvidos, 4 telas implementadas)

**Registrado em 2026-07-13**, depois de ler o código-fonte completo dos 4
`.frm` (`frmmovbomba.frm` lido nesta rodada; `FrmFecTurno.frm`/
`FrmReaTurno.frm`/`FrmBaiABc2.frm` já tinham sido colados pelo usuário
antes). Diferente das 9 telas já migradas até então (CRUDs simples/upsert
por chave composta), essas 4 formam um subsistema coeso de **fechamento
de caixa/apuração de venda por encerrante**.

#### 1. `DATESIST` — RESOLVIDO (2026-07-13)

O usuário explicou a variável diretamente: `DATESIST` é uma global do VB6
(declarada em `Mdl_Proc.bas`, o módulo de funções/globais comuns — ~40 mil
linhas, um por pasta de linha de negócio, mesmo padrão dos `.frm`), setada
uma vez na inicialização do app (`DATESIST = CONTROLE.DATA_MOVIMENTO`) e
lida daí em diante como "hoje" pra fins de movimento — funciona no VB6
porque cada instalação roda um processo próprio, conectado a um banco só.

**Decisão de arquitetura**: NÃO existe (nem deve existir) um `DATESIST`
global no backend novo — o backend é stateless e atende múltiplas
empresas (servidor+banco) na mesma instância; uma variável global de
processo vazaria a data de uma empresa pra outra, ou ficaria obsoleta
assim que `controle.data_movimento` mudasse (ex.: ao fechar um turno).
Implementado como `services/posto_common.py::data_movimento(cur)` — um
SELECT simples, escopado ao cursor/conexão já aberto da requisição
corrente, mesmo padrão já usado pra `controle.qtd_turnos` em
`ilha_service.py`. Ver CLAUDE.md > "Porting VB6 global state" (regra
geral, não específica desta tela).

#### 2. Mov. Encerrantes — IMPLEMENTADA 2026-07-13

`backend/services/mov_encerrante_service.py` + `routes/mov_encerrante.py`
+ `app/posto-mov-encerrantes.tsx`. Cascata replicada fielmente: ao gravar
o encerrante (Contador Inicial/Final + Aferição) de uma bomba/turno/data,
calcula o volume vendido (`Final - Inicial - Aferição`), atualiza
`Bomba.Contador_Final`/`Data_Ult_Mov` (só avança), upsert em `Mov_Bomba`,
decrementa `Estoque`/`Combustivel.Estoque`, e roda consumo **FIFO** de
custo contra `Custo_Combustivel` (casa o volume com os lotes "Entrada >
Saída" na ordem cronológica, criando `Mov_Combustivel` `tipo_mov='S01'`
por lote). Bloqueia lançar em data posterior à `data_movimento` corrente
(regra real do `DATESIST`, ver item 1). Testado ponta-a-ponta contra
GERDELL/BARESTELA com combustível/tanque/bomba/lote de custo descartáveis
— FIFO consumiu o lote corretamente, `Custo_Combustivel.Saida` e
`Mov_Combustivel` conferidos, tudo limpo ao final (zero linhas residuais
em nenhuma tabela envolvida).

**Truques de VB6 identificados e deliberadamente NÃO replicados** (a
pedido explícito do usuário — "tem rotina que às vezes acho que nem vale
a pena importar do VB6... muitos truques e bacalhaus"; ver
`feedback_nao_replicar_truques_vb6` na memória):
- `Command1_Click` (botão invisível): script de correção de dados
  **hardcoded pra bombas 13/14 em 2006** — lixo de debug do dev original,
  não uma feature. Não portado.
- `CmDexclui_Click` tinha uma cláusula SQL **malformada** (parêntese de
  fechamento faltando) — confirma que replicar linha-a-linha sem
  julgamento produziria código quebrado.
- Patch cross-turno silencioso em `Campo_LostFocus` (detecta que o
  contador final do turno anterior não bate e reescreve o OUTRO registro
  via um `MsgBox` de confirmação): substituído por validação simples —
  hoje não há sequer uma checagem de continuidade entre turnos vizinhos
  (fora de escopo desta primeira versão); se for pedida depois, a
  abordagem correta é validar e rejeitar com mensagem clara, nunca
  reescrever outro registro por trás.
- `Delete from Custo_Combustivel Where Entrada = Saida` (limpeza de lotes
  zerados no final de toda operação): não replicado — os lotes ficam
  registrados mesmo depois de totalmente consumidos, preservando a
  trilha de auditoria de como o custo foi calculado.
- **Excluir não foi implementado nesta fase** — o `CmDexclui_Click`
  original já estava quebrado (item acima) e reverter corretamente o
  consumo FIFO exigiria rastrear qual lote de `Custo_Combustivel` foi
  consumido por qual lançamento de `Mov_Bomba` (não existe esse vínculo
  no schema hoje). Registrado como melhoria futura, não como lacuna
  esquecida.

#### 3. "Turno aberto agora" — RESOLVIDO (2026-07-13), mesmo padrão do DATESIST

O usuário apontou diretamente: assim como `DATESIST = CONTROLE.DATA_MOVIMENTO`,
"qual turno está aberto agora" é só `controle.turno_movimento` — mesma
tabela singleton, mesmo padrão de leitura fresca por requisição. Implementado
como `posto_common.turno_movimento(cur)` + `posto_common.qtd_turnos(cur)`,
ao lado de `data_movimento(cur)`.

#### 4. Fechamento de Turno — IMPLEMENTADA 2026-07-13

`backend/services/fechamento_turno_service.py` + `routes/
fechamento_turno.py` + `app/posto-fechamento-turno.tsx`. Fecha o turno
corrente (bloqueia se já fechado, fora do horário mínimo configurado em
`controle_turno_horario`, ou com abastecimentos pendentes de baixa no
turno); grava `controle_turno`; ao fechar o ÚLTIMO turno do dia
(`turno == qtd_turnos`), também grava `FECHAMENTO_TURNO` e avança
`controle.data_movimento` pro dia seguinte, voltando `turno_movimento`
pra 1. **Não replicado**: checagem hardcoded de CNPJ que liberava fechar
com pendências pra um cliente específico; captura automática de
encerrante/impressão de relatório via hardware Wayne Fusion (`Rel_Encerra`,
Fase 2); `Computador`/`Usuario_Rede` (identidade de SO do Windows, não
aplicável numa app web — `log_auditoria` já cobre usuário/IP/plataforma).
Testado ponta-a-ponta contra GERDELL/BARESTELA (ciclo completo fechar
turno 1 → fechar turno 2 [avança dia] → confirmado, restaurado ao final).

#### 5. Reabertura de Turno — IMPLEMENTADA 2026-07-13

`backend/services/reabertura_turno_service.py` + `routes/
reabertura_turno.py` + `app/posto-reabertura-turno.tsx`. Desfaz o
fechamento mais recente (mesmo dia ou cruzando a fronteira do dia,
mesma lógica simples pros dois casos — nada de ramificação especial).
**Simplificação deliberada, não lacuna**: o legado também reatribuía
(`UPDATE ... SET turno=turno-1`) registros de `abastecimento`/`mov_bomba`/
`comanda` do turno reaberto pro anterior — desnecessário aqui porque toda
tela de movimentação já pede `data`+`turno` explicitamente ao usuário
(não herda implicitamente "o turno aberto agora" como o legado fazia),
então não existe registro pra "corrigir" depois. Também não replicada a
ramificação `CodTurno = Qtd_Turnos` do legado — investigando o código,
ela existia pra contornar um bug de sincronização do `DATESIST` (global
de processo que podia ficar desatualizado numa estação enquanto outra já
tinha fechado o dia); como aqui a leitura é sempre fresca do banco, esse
bug não existe. Testado ponta-a-ponta contra GERDELL/BARESTELA (ciclo
fechar→fechar→reabrir→reabrir→reabrir se anulou exatamente, estado
restaurado ao valor original).

#### 6. Aferições/Despesas — IMPLEMENTADA 2026-07-13

`backend/services/afericao_abastecimento_service.py` + `routes/
afericao_abastecimento.py` + `app/posto-afericoes.tsx`. Lista
abastecimentos pendentes (`status_abastecimento LIKE 'PENDEN%'`), afere
até 10 por vez (regra real do legado replicada), com opção "lançar como
despesa" + observação — atualiza `mov_bomba.afericao`/`valor_despesas`
correspondente. Lista aferições já lançadas com filtro por período.
Reverter uma aferição volta o abastecimento pra `PENDENTE`.

**Melhoria sobre o legado, não regra removida**: o join original pra
descrição do combustível passa por `pecas.codigo_fab` (comparação
textual frágil); usamos `abastecimento.combustivel` direto (a coluna já
existe), mais simples e correto.

**Bug do legado corrigido, não replicado**: o `F3` (reverter) original só
resetava `abastecimento` pra `PENDENTE`, mas **nunca desfazia o
incremento em `mov_bomba.afericao`** feito na aferição original — um
lançamento revertido ficava com valor de aferição "fantasma" no turno.
Aqui, reverter também decrementa `mov_bomba.afericao`/`valor_despesas`
pelo mesmo valor somado — testado ponta-a-ponta (aferiu, conferiu
`mov_bomba` incrementado, reverteu, conferiu `mov_bomba` de volta a
zero, tudo limpo ao final).

**Gap conhecido, não resolvido (documentado, não escondido)**: nenhuma
tela migrada cria linhas em `abastecimento` — em produção vêm do polling
do concentrador Wayne Fusion (Fase 2, fora de escopo). A lista de
"Pendentes" fica vazia até essa automação existir ou até algum outro
processo popular a tabela — a tela funciona normalmente quando isso
acontecer, sem mudança de código necessária.

**Conclusão do Cluster de Turno**: as 4 telas que dependiam desta
pendência arquitetural (Mov. Encerrantes, Fechamento/Reabertura de Turno,
Aferições/Despesas) estão implementadas. As 13 telas do módulo Posto de
Combustível estão completas.

### Perguntas em aberto / dúvidas de negócio (registrar antes de migrar cada tela)

1. ~~"Metas" tem dois arquivos VB6, não um~~ — **RESOLVIDO (2026-07-13)**.
   O usuário inicialmente apontou `FrmCadMeta.frm` como o vigente, mas ao
   abrir o arquivo o código real diverge completamente do caption: apesar
   de exibir "Cadastro de Meta" e popular o combo com `Combustivel_Grupo`,
   todo o `Form_Load`/Inclui/Altera/Exclui abre e grava na tabela **`Bomba`**
   (`Ilha`, `Ponto`, `Posicao`, `Tanque`, `Combustivel`, `Contador_Final`,
   `Data_Ult_Mov` — mesmos nomes de variável do `frmcadbom.frm`/Bombas,
   inclusive as MsgBox dizem "Bomba X Incluída/Alterada/Excluída") — a
   tabela `combustivel_meta` nunca é referenciada. Conclusão: é um rascunho
   abandonado (copy-paste do form de Bombas com o caption trocado), não a
   tela de metas de verdade. Apontado ao usuário, que confirmou usar
   **`frmcadmet.frm`** (2016, "Metas dos Combustíveis", grava de fato em
   `combustivel_meta`/`combustivel_GRUPO`) como fonte real da tela Metas.
   `FrmCadMeta.frm` deve ser ignorado ao migrar esta tela.
2. **Sobreposição parcial com telas genéricas já existentes**: "Cadastro
   de Combustíveis" (`FRMMANCOM.FRM`) referencia `TABELA_PRECO` e
   `MOVIMENTACAO`, conceitualmente próximas do cadastro de Produtos já
   migrado (`frontend/app/produtos.tsx`) — avaliar, ao migrar essa tela,
   se "Combustível" deve ser tratado como um tipo de produto (reuso) ou
   cadastro totalmente à parte (como o legado trata, tabela `Combustivel`
   própria). "Tanque/Nota Fiscal" (`frmmantnf.frm`) é só um vínculo
   tanque↔NF — reaproveita a Nota Fiscal já migrada
   (`frontend/app/notas-fiscais.tsx`), não a duplica.
3. Cada uma das 13 telas precisa seguir o "Padrão de Saída Obrigatório"
   (CLAUDE.md, seção 8) individualmente — análise, regras de negócio,
   arquitetura, backend, frontend, testes, checklist — uma de cada vez,
   não em lote. Ao concluir cada uma, atualizar a linha correspondente na
   tabela acima e marcar aqui.
4. Verificar, ao migrar cada tela, se ela precisa do mesmo reforço de
   módulo no backend que a regra "Serviço" já tem (ver CLAUDE.md > "Regra
   de Módulo Ativo") — provavelmente sim, já que todas as 13 dependem do
   módulo `Posto` estar ativo.
5. **Dependência de hardware (Wayne Fusion) — decisão confirmada
   2026-07-13**: o usuário mostrou que `Backon.Controllers` referencia
   `FusionClass.dll` (`C:\Desenv\VB6\vb.net\APICamadas\BackOn\
   Backon.Controllers\Controller_HW_Concentradores_Wayne.vb`), driver
   COM/.NET proprietário que fala com o **concentrador de bombas Wayne
   Fusion** (hardware físico do posto, via IP/serial) — sem equivalente
   Python, mesma situação arquitetural que a emissão fiscal NFe já tem
   (ver seção 12 do CLAUDE.md, "Telas Fiscais"). Afeta 4 das 13 telas:
   - **Mov. Encerrantes** — leitura automática de encerrante viria de
     `RetornaEncerrante`/`AbastecimentosFusion`.
   - **Fechamento/Reabertura de Turno** — captura automática de
     totalizador no fechamento (`Rel_Encerra` chama
     `RetornaEncerrante`).
   - **Bombas** — status ao vivo da bomba (`StatusPista`/`StatusBomba`).
   - **Combustíveis** — envio de preço pra bomba
     (`SetaPrecoBomba`/`SetaPrecoCombustivel`).
   **Decisão**: mesmo padrão já usado em Notas Fiscais — Fase 1 migra
   CRUD/dados manualmente (encerrante digitado à mão, sem status/preço
   de bomba ao vivo), documentando a automação real de hardware (leitura
   automática de encerrante, autorizar/fechar bomba remotamente, empurrar
   preço) como Fase 2, fora de escopo até uma decisão de arquitetura
   própria (bridge pro DLL .NET, ou reimplementar o protocolo Fusion em
   Python — nenhuma das duas avaliada ainda).

---

## Notas Fiscais

**Status**: 🟡 Fase 1 implementada (CRUD sem emissão fiscal) — Fases seguintes em aberto.

**Registrada em**: 2026-07-13

### O que já foi analisado e implementado

Migração de `FrmManRec.frm` ("Manutenção de Nota Fiscal") — a tela mais
complexa já migrada neste projeto (quase 3000 linhas de VB6). **Decisão de
escopo tomada explicitamente com o usuário via AskUserQuestion antes de
implementar** (a emissão fiscal real depende da DLL .NET
`Backon_Controllers.Nfe`/`NFSe`, sem equivalente Python neste projeto):
Fase 1 = CRUD completo, sem emissão fiscal real.

Implementado: backend completo
(`backend/services/notas_fiscais_service.py` + `backend/routes/
notas_fiscais.py`, registrado em `server.py`), lookups novos
(`tipo-mov-nf` — versão rica de tipo_mov com origem_destino/atualiza_est/
transf_pagar/cfop; `tipo-doc`), permissão `NOTAS_FISCAIS` em `CADASTROS`
(`ACOES_PADRAO` + `CRITICAR` + `CANCELAR`), 27 testes unitários. Frontend:
`frontend/app/notas-fiscais.tsx` (lista/consulta com filtros + formulário
com abas: Dados Principais, Itens, Vencimentos, Observações), tile em
Cadastros. Todos os nomes de coluna foram confirmados via
`INFORMATION_SCHEMA.COLUMNS` ao vivo em GERDELL/BARESTELA antes de
codificar (`n_fiscal` tem 101 colunas, `n_fiscal_itens` 162 — incluindo
campos da Reforma Tributária 2026/IBS-CBS-IS que nem o `.frm` original
conhece).

Regras replicadas fielmente do legado: duplicidade (num_nf+serie_nf+
fornecedor), nota cancelada não editável, Criticar (soma dos itens vs
Valor Total → situação E/A), Cancelar (bloqueia se já cancelada ou
consignação com devolução/faturamento, estorna estoque conforme Entrada/
Saída, remove `movimentacao`/`comanda_nf`), Excluir (só com situação='C',
cascata completa). "Alterar Número/Série/Fornecedor" **intencionalmente
não implementado** — o próprio legado tem esses 3 botões desabilitados
"PELO PAF-ECF" (restrição fiscal real, não lacuna de migração).

**Importante**: a tela "Consulta de Notas Fiscais" do 2º print do usuário
é `FrmConNF.frm`, um form **diferente** de `FrmManRec.frm` — o código-fonte
dele não foi anexado. Os filtros implementados em `_list_consulta_sync`
foram inferidos diretamente do print de tela, não do `.frm` real. Se o
`.frm` de `FrmConNF` for anexado depois, revisar os filtros contra ele.

### Perguntas em aberto / fora de escopo desta fase

1. **Emissão fiscal real** (DANFE, XML, Carta de Correção, Cancelamento/
   Inutilização online no SEFAZ, Consulta de Situação SEFAZ, Contingência)
   — precisa de um provedor NFe/NFSe Python (ou algum bridge pra DLL .NET
   `Backon_Controllers.Nfe`/`NFSe`) — **decisão de arquitetura do usuário
   antes de prosseguir**, não uma simples tarefa de código.
2. **Resumo Tributário e Centro de Custo**: backend pronto e testado
   (`n_fiscal_icms`/`n_fiscal_custo`, endpoints `/notas-fiscais/{codigo}/
   resumo-tributario` e `/centro-custo`), mas **a UI dessas duas abas ainda
   não foi construída no frontend** — ficaram de fora desta primeira
   entrega por serem seções secundárias (conciliação tributária/rateio de
   custo, tipicamente feitas em lote no fechamento) e por limite de tempo
   de uma única sessão. Próximo passo natural quando a tela for retomada.
3. **Consignação**: efeitos colaterais de estoque específicos por tipo de
   movimentação de consignação (`Sub consignacoes` do legado — E03/E05/
   S05/E06/S06/S07/S08/E07/E08, tabelas `consignacao`/`consignacao_baixa`)
   — não implementado, muito específico e arriscado de replicar sem dados
   reais de consignação pra validar.
4. **Vínculo com Cupom Fiscal** (ECF/`comanda_cupom`) — ligado ao módulo
   Bar/PDV, fora do escopo desta tela.
5. **Envio por email do XML/DANFE** — depende da emissão fiscal real
   (item 1), mesma dependência.
6. **Motor automático de cálculo de ICMS/Substituição por CFOP+UF+
   cod_icms** (tabela `taxas`, `ProcuraProd`/`ProcuraProdbkp` do legado) —
   os campos fiscais dos itens são de **entrada manual** nesta fase (o
   próprio `.frm` já permite isso quando `Label10='L'`/nota liberada
   manualmente). Auto-lookup de produto (descrição) foi implementado
   (`GET /notas-fiscais/produto/{codigo_int}`), mas não o cálculo de
   impostos.
7. **Reversão de duplicatas de contas a pagar/receber ao cancelar uma
   nota** — o legado faz isso (`Exclui_do_Contas`), mas o módulo de
   duplicatas ainda não existe nesta arquitetura nova (ver
   `project_faturamento_parcelas` na memória) — cancelar uma nota aqui
   reverte estoque mas **não** reverte nenhuma duplicata (porque não há
   nenhuma pra reverter ainda). Risco de inconsistência financeira quando
   o módulo de duplicatas for implementado — revisitar `_cancelar_sync`
   nesse momento.
8. **Campos de transporte detalhado** (placa, motorista, volumes, peso) e
   **campos da Reforma Tributária 2026** (IBS/CBS/IS, colunas já existem no
   banco mas não são controles visíveis no `.frm` original) — fora de
   escopo, não são usados pela tela legada.

---

## Telemarketing

**Status**: 🟢 implementada — pendências não bloqueantes.

**Registrada em**: 2026-07-12

### O que já foi analisado e implementado

Migração de `FrmManTMa.frm` (legado, "TeleMarketing...") — gestor de
comunicação com o cliente. Backend
(`backend/services/telemarketing_service.py` +
`backend/routes/telemarketing.py`, registrado em `server.py`), frontend
(`frontend/app/telemarketing.tsx`, tile em `(tabs)/cadastros.tsx`, com
duas visões: principal e "Selecionar Clientes" — como duas branches do
mesmo componente, não modal, por causa da grade larga de resultados).
Permissão `TELEMARKETING` em `CADASTROS` (`ACOES_PADRAO` + `WHATSAPP`). 8
testes unitários novos (`test_telemarketing_service.py`), suite completa
(117 testes, incluindo os de WhatsApp) sem regressão.

**Confirmado com o usuário (2026-07-12)**: NÃO existe tabela
`telemarketing` — "Telemarketing" é só o nome da tela. Tudo grava em
`cliente` (`historico`, `ultimo_contato`, `DATA_AGENDAMENTO_TELEMARKETING`,
`FUNCIONARIO_AGENDAMENTO_TELEMARKETING`) — exatamente como o `.frm`
original, colunas confirmadas ao vivo em GERDELL/BARESTELA.

**WhatsApp "versão completa com histórico" — IMPLEMENTADO nesta rodada**
(pedido do usuário: "colocar o recurso de whatsapp" + confirmação da
rodada anterior "SIM"): estendido `services/whatsapp/repository.py` e
`services/whatsapp/service.py` com um novo `document_type = "CLI"`
(mensagem avulsa, sem Pedido/OS associado — `document_id` = `cliente.
codigo`). Envio bem-sucedido também grava uma linha em `cliente.historico`
(`registrar_envio_whatsapp_no_historico`, mesmo formato de frase que a
produção real já usa pros logs automáticos de e-mail/boleto — confirmado
por print do usuário). `WhatsappButton.tsx` (já usado em Pedido/O.S.) foi
reaproveitado tal como é, só ampliando o tipo de `documentType` pra
aceitar `"CLI"`.

**Melhoria técnica** (não é regra de negócio): a query de "Selecionar
Clientes" usa `LEFT JOIN dia_semana` em vez do `UNION ALL` que o legado
usava pra contornar um INNER JOIN (clientes sem `dia_contato` ficariam de
fora) — mesmo resultado, sem duplicar a query inteira nem replicar um bug
real do legado (a 2ª branch do `.frm` reaproveitava incorretamente
`Camp(2)`, um campo de data, como filtro `historico LIKE`).

**`os-form.tsx` ganhou suporte a pré-preenchimento de cliente** (params
`cliente`/`cliente_nome`, mesmo padrão que `pedido-form.tsx` já tinha) —
necessário pro botão "O.S." desta tela abrir já com o cliente carregado.

### Perguntas em aberto / gaps conhecidos (nenhum bloqueia o uso da tela)

1. **`Pos_Sistema`** — mesma pendência já registrada em Equipamentos, não
   implementada (arquitetura nova é stateless).
2. **Botões "Ranking de Vendas" (`FrmRkgCliPro`) e "Vendas"
   (`FrmConCupom`)** — não implementados, as telas legadas de destino
   ainda não foram migradas pra este sistema novo. Idem "Inatividade de
   Clientes" (`FrmRelCliSMV`, botão dentro de "Selecionar Clientes").
3. **Filtro "Categoria"** (`Cmb(7)` no `.frm`) e **filtro "Endereço"**
   (`Camp(4)`) — existem na tela legada mas NUNCA são de fato usados na
   query de `Command8_Click` (bugs/campos mortos do próprio legado) — não
   implementados na tela nova (só "Bairro" funciona de verdade, igual ao
   legado).
4. **"CarteiraVendedor"** (restrição de quais vendedores aparecem no
   filtro, dependendo do usuário logado, via tabela
   `funcionarios_carteiras` — que existe e tem dados reais) — não
   implementado; o filtro de Vendedor mostra todos os funcionários pra
   todo mundo. Se isso for uma regra de permissão real (não só UX), vale
   revisitar.
5. **`WhatsappButton` "CLI"**: a mensagem padrão (sem template
   configurado) é um texto de saudação genérico — não foi pedido um
   texto/template específico pro Telemarketing, então ficou um padrão
   razoável, sujeito a ajuste.

---

## Equipamentos

**Status**: 🟢 implementada — pendências não bloqueantes.

**Registrada em**: 2026-07-12

### O que já foi analisado e implementado

Migração de `FrmManEquip.frm` (legado, "Manutenção de Equipamentos.") —
todo equipamento pertence a um cliente (pedido explícito do usuário), a
tela sempre parte da seleção de um cliente antes de listar/gerenciar.
Backend (`backend/services/equipamentos_service.py` +
`backend/routes/equipamentos.py`, registrado em `server.py`), frontend
(`frontend/app/equipamentos.tsx`, tile em `(tabs)/cadastros.tsx`).
Permissão `EQUIPAMENTOS` em `CADASTROS` com 3 sub-ações próprias
(`ALTERAR_TIPO`, `DISPONIBILIZAR`, `ALT_NUM_SERIE`), além do padrão
Abrir/Gravar/Excluir/Imprimir/Exportar. Reaproveitados os lookups já
migrados de Marca/Modelo (`GET /api/tabelas/marcas`,
`GET /api/tabelas/modelos?cod_marca=...`) e o `ClientSearchModal` já
usado em Pedido/O.S./Contatos. 16 testes unitários novos
(`backend/tests/unit/test_equipamentos_service.py`), suite completa (95
testes) sem regressão.

Schema conferido ao vivo em GERDELL/BARESTELA: `equipamentos` (24
colunas — bem mais do que este `.frm` usa, ver nota abaixo), `marcas`,
`modelos`, `contratos_produtos_disponiveis`, `contratos_produtos`,
`retifica` (todas existem e batem com o que o `.frm` espera). `codigo`
de `equipamentos` é IDENTITY, sem nenhuma FK declarada apontando pra ela.

**`equipamentos` tem colunas de outro domínio, NÃO tocadas aqui**: `casco`,
`horas`, `aquisicao`, `revenda`, `nf_compra`, `ano`, `fabricacao`, `passo`,
`oleo`, `lancha`, `marinheiro` — parecem pertencer a um cadastro de
embarcações/motores que compartilha a mesma tabela física mas não é lido
nem gravado por `FrmManEquip.frm`. Se uma tela desse outro domínio
aparecer depois, ela vai reaproveitar `equipamentos_service.py` como
base, adicionando só os campos que faltam — não duplicar a tabela.

**Regras replicadas do legado, incluindo uma bem sutil**: `numero_de_serie`
é **único globalmente** (entre TODOS os clientes, não só por cliente) — a
mensagem de erro do legado ("já cadastrado para este cliente") é
enganosa, a query real (`Command1_Click`) não filtra por cliente.
Replicado fielmente, com mensagem nova mais clara sobre o motivo real.
Excluir um equipamento cascateia a exclusão em
`contratos_produtos_disponiveis`/`contratos_produtos` (produto =
numero_de_serie) — comportamento deliberado do legado, não um guard de
bloqueio.

**Melhoria aplicada** (não é regra de negócio, é robustez técnica):
editar (`Alterar`) grava por `codigo` (PK), não por
`numero_de_serie` como o legado fazia (`UPDATE ... WHERE numero_de_serie
= ...`) — mais seguro, evita ambiguidade.

### Perguntas em aberto / gaps conhecidos (nenhum bloqueia o uso da tela)

1. **`Pos_Sistema`** — checagem de estado presente em quase todo botão do
   legado (Incluir/Alterar/Excluir/Disponibilizar), mas sua definição não
   veio no código fornecido. Parece ligado a estado de sessão de
   caixa/PDV específico do legado (mensagem `Msg_Pos_Sistema`). A nova
   arquitetura é stateless por requisição — não há equivalente óbvio, e
   por isso não foi implementado. Se isso for uma trava de negócio real
   (ex.: só permite mexer em equipamentos com o caixa fechado), precisa
   ser descrita explicitamente antes de replicar.
2. ~~Cascata de "Alterar Número de Série" NÃO inclui `os.chassi`~~ —
   **RESOLVIDO (2026-07-12, confirmado pelo usuário)**: o campo
   equivalente hoje NÃO é `os.chassi` (que virou exclusivo de OS de
   Oficina/veículo), e sim **`os.numero_de_serie`** (campo de Assistência
   Técnica — já existia separado no schema atual, confirmado em
   `models/schemas.py::OSSaveRequest`). A cascata foi implementada usando
   `os.numero_de_serie` (nunca `os.chassi`), casando por
   cliente+numero_de_serie antigo, com teste dedicado
   (`test_altera_com_sucesso_e_cascateia` já cobre isso).
3. **Reassociar cliente durante "Alterar Número de Série"** — o legado
   permite trocar o número de série E o cliente na mesma operação
   (Frame1: Campo(5)=cliente, Campo(6)=novo número). A tela nova só
   implementa a troca do número de série (o backend já aceita
   `novo_cliente` opcional, mas o frontend não expõe essa opção ainda) —
   simplificação de escopo, não uma remoção definitiva.
4. **"Tipo do Equipamento" (Avulso/Contrato) — trava por permissão, não
   por função hardcoded**: o legado só libera esse campo pra usuários com
   `cod_funcao IN ('01','07','02')` ("EuSouGerente"), hardcoded no
   Form_Load. Virou uma permissão própria (`EQUIPAMENTOS.ALTERAR_TIPO`),
   liberável por admin via tela de Permissões — mesmo espírito das
   exceções `REPROC_ITEM`/`REPROC_RESERV` já usadas em Produtos Níveis.
5. **Campo Descrição — comportamento adaptado, não replicado
   literalmente**: o legado sobrescrevia o campo Descrição com
   "Modelo Marca" **toda vez que o campo ganhava foco** (mesmo já tendo
   texto digitado — a checagem "só se vazio" está comentada no `.frm`,
   parece um bug/inconsistência do próprio legado). A tela nova usa um
   botão explícito "Sugerir (Marca/Modelo)" em vez de sobrescrever no
   foco, evitando perda de dados digitados manualmente.
6. **Impressão com 4 níveis de ordenação configurável** (Frame3 do
   `.frm`: Local/Usuário/Marca/Modelo/Controle Interno/Número Série,
   cada um crescente/decrescente, mais filtro Contrato/Avulso/Todos) —
   virou impressão simples da lista já filtrada na tela (mesma decisão de
   escopo já tomada em Entrada/Saída de Caixa e Contatos).
7. **Filtro de Marca por `marca_produto`**: a tela de Marcas/Modelos já
   migrada neste projeto tem uma distinção `marca_produto` (0 = veículo/
   O.S., 1 = Produtos) que não existia no `FrmManEquip.frm` original (o
   combo de Marca do legado lista TODAS as marcas, sem filtro). A tela
   nova replicou o comportamento do legado (sem filtro) — se
   Equipamentos deveria na verdade usar `marca_produto=0` (mesmo
   conjunto que Veículos/O.S.), é uma decisão a confirmar depois, não
   assumida aqui.

---

## Contatos

**Status**: 🟢 implementada — pendências não bloqueantes.

**Registrada em**: 2026-07-12

### O que já foi analisado e implementado

Migração de `FrmContatos.frm` (legado, "Cadastro de Contatos...") — tela
em Cadastros, combina cadastro + listagem/filtros num só lugar (mesmo
padrão de Fornecedores/Entrada-Saída de Caixa). Backend
(`backend/services/contatos_service.py` + `backend/routes/contatos.py`,
registrado em `server.py`), frontend (`frontend/app/contatos.tsx`, tile em
`(tabs)/cadastros.tsx`). Permissão `CONTATOS` em `CADASTROS`
(`ACOES_PADRAO`). Lookup novo `GET /api/tipo-cliente-contato` (tabela
não tinha lookup). Reaproveitado `ClientSearchModal` +
`GET /api/clientes/find/search` (já usados em Pedido/O.S.) pro campo
Cliente. 9 testes unitários novos
(`backend/tests/unit/test_contatos_service.py`), suite completa (79
testes) sem regressão.

Schema conferido ao vivo em GERDELL/BARESTELA: `contatos` (16 colunas,
`codigo` IDENTITY, sem nenhuma FK apontando pra ela — confirmado via
`sys.foreign_keys`, então sem guard de exclusão necessário) e
`tipo_cliente_contato` (5 linhas: Contato, Fechado, Não Contactado,
Prospect, Sem Possibilidade — bate exatamente com o screenshot fornecido).

**Melhoria aplicada** (não é regra de negócio, é robustez técnica): o
legado edita um contato existente **apagando a linha e inserindo outra
nova** (perde o `codigo` original a cada edição). Aqui virou um `UPDATE`
de verdade, preservando o `codigo` — seguro porque nada referencia
`contatos.codigo`.

### Perguntas em aberto / gaps conhecidos (nenhum bloqueia o uso da tela)

1. **`FrmConCli2.frm`** (seletor de cliente via F2 no legado) não foi
   fornecido. `contatos.cliente` já era texto livre no legado (nvarchar,
   nunca validado contra a tabela `cliente`) — a tela nova reaproveita
   `ClientSearchModal`/`GET /api/clientes/find/search` (já usado em
   Pedido/O.S.) pra escolher um nome existente, mas não trava o campo a
   um cliente cadastrado (fiel ao legado). Se o `FrmConCli2.frm` real
   aparecer depois, vale conferir se há alguma regra adicional não
   coberta aqui.
2. **`CHAMA2()`** — sub declarada no `.frm` fornecido, mas sem nenhum
   call site visível no código recebido (provavelmente chamada de dentro
   do `FrmConCli2.frm`, que não temos). Parece existir pra auto-preencher
   Telefone a partir do cliente escolhido. Implementada por inferência:
   ao escolher um cliente na busca, preenche Telefone só se ainda
   estiver vazio. Não confirmado contra a fonte real.
3. **Coluna `Telefone_1`** existe em `contatos` mas não é escrita/lida
   pelo caminho de gravação realmente usado pela UI no legado
   (`Command20_Click`) nem exibida em `chama()` (linha comentada) — não
   implementada aqui. Só vale revisitar se aparecer um motivo de negócio
   pra reativá-la.
4. **`FrmConsContatos.frm`** (tela de consulta, aberta pelo botão
   "Consultar" no cadastro) não foi fornecido — os filtros replicados na
   tela nova vêm do screenshot fornecido + do setup em `Command9_Click`
   de `FrmContatos.frm` (que só monta as listas de Tipo Cliente/
   Profissional), não de um `.frm` de consulta rastreado linha a linha.
   Comportamento de filtro (LIKE vs exato, etc.) foi inferido de forma
   razoável, não confirmado.
5. **Prefill limitado no botão "Cadastrar Cliente"**: o legado pré-
   preenche nome, email, telefone, telefone 2, endereço e bairro no
   cadastro de cliente. `cliente-form.tsx` (Cadastro Rápido já existente)
   hoje só aceita `initial_nome` via parâmetro de rota — a tela nova só
   repassa o nome; os demais campos ficam pro usuário preencher
   manualmente. Extender `cliente-form.tsx`/`useClienteForm.ts` pra
   aceitar mais parâmetros de pré-preenchimento é uma melhoria futura,
   não aplicada agora pra não alterar um hook compartilhado por um
   ganho secundário.
6. **"Nova anotação" no campo Observação — adaptação deliberada, não
   bug**: o legado dispara a inserção de uma linha datada TODA VEZ que o
   campo ganha foco (`Campo8_GotFocus`), o que em web spamaria linhas
   repetidas (foco muda com muito mais frequência que no VB6 — cliques
   pra posicionar o cursor, tab, etc.). A tela nova usa um botão
   explícito "Nova anotação" que faz a mesma coisa (prefixa data/hora),
   só que sob controle do usuário.
7. **Impressão de um contato** — o legado usa `Printer` COM com
   cabeçalho completo da empresa (`controle`, incl. logo). A tela nova
   abre uma janela de impressão do navegador com os campos do contato
   formatados, sem o cabeçalho/logo da empresa (mesma decisão de escopo
   já tomada em Entrada/Saída de Caixa).

---

## Entrada/Saída de Caixa

**Status**: 🟢 implementada — pendências não bloqueantes (nenhuma impede uso
da tela; são detalhes que só importam se/quando as áreas relacionadas forem
tocadas).

**Registrada em**: 2026-07-11

### O que já foi analisado e implementado

Migração completa de `FrmManESC.frm` (legado) — lançamentos do caixa
operacional da loja (não é o caixa financeiro). Backend
(`backend/services/entrada_saida_caixa_service.py` +
`backend/routes/entrada_saida_caixa.py`, registrado em `server.py`) e
frontend (`frontend/app/entrada-saida-caixa.tsx`, tile em
`frontend/app/(tabs)/cadastros.tsx`), tela única sem abas (mesma exceção já
usada em Fornecedores — o form legado também não tem abas). Permissão nova
`MOV_CAIXA` dentro de `CADASTROS` (`permissoes_service.py`) — **correção
2026-07-11**: foi implementada inicialmente em `FINANCEIRO > FLUXO_CAIXA`
por engano, apesar do pedido original já dizer explicitamente "Em
Cadastros"; movida pro lugar certo (tela + tile + permissão) após o usuário
apontar o erro. Lookup novo de Favorecidos (`GET /api/favorecidos`, não
existia antes). 13 testes unitários
(`backend/tests/unit/test_entrada_saida_caixa_service.py`), todos passando,
mais suite completa (70 testes) sem regressão.

Schema conferido ao vivo em GERDELL/BARESTELA antes de implementar:
`entrada_caixa`/`saida_caixa`, `movimentacoes`, `contas`, `favorecidos`,
`classes`, `sub_classes`, `centro_custo`, `forma_pagamento`, `controle_aux`
(`transf_ent_sai_caixa`), `controle`, `logs` (legado), `funcionarios`.

Regras replicadas do legado: Tipo imutável após gravar; Conta/Favorecido
obrigatórios só quando `controle_aux.transf_ent_sai_caixa` está ativo;
Conta origem ≠ Conta destino; Favorecido auto-cadastrado se a descrição
digitada não existir; lançamento já transferido para a movimentação
financeira (via `cod_movimentacao` existente em `movimentacoes`) não pode
ser alterado nem excluído; filtro de período + Entradas/Saídas na
listagem, com a mesma regra do legado de nunca deixar as duas caixas de
seleção desmarcadas ao mesmo tempo.

**Melhoria aplicada** (não é regra de negócio nova, é robustez técnica):
o código novo gera o `codigo` do INSERT via `OUTPUT INSERTED.codigo`, em
vez do padrão frágil do legado (insere e depois busca por
atendente+data+descrição pra achar o registro criado).

### Perguntas em aberto

1. **Coluna `turno` (só em `entrada_caixa`)** — existe na tabela, mas
   nenhum código de `FrmManESC.frm` a lê/grava. Não implementada aqui
   (fica sempre `NULL` nos INSERTs novos). Onde ela é preenchida no
   legado? Pertence a outro formulário (ex.: abertura/fechamento de turno
   do módulo Bar)?
2. **Coluna `transf_caixa` (`entrada_caixa`/`saida_caixa`, separada de
   `transferencia`)** — também existe na tabela e também não é tocada por
   este form. Qual sua função, e é gravada por qual rotina/tela do
   legado?
3. **Rotina que de fato transfere um lançamento pra `movimentacoes`
   (populando `cod_movimentacao`)** — não está em `FrmManESC.frm`; o form
   só CONSULTA esse campo pra bloquear edição/exclusão. Onde essa
   transferência acontece no legado (outro form? processo em lote?), e
   ela precisa ser migrada também, ou fica fora do escopo deste módulo
   por enquanto?
4. **Sobrecarga do campo `classe` em transferência entre contas** — o
   legado grava o código da conta destino dentro do campo `classe` (e
   zera `sub_classe`) quando há transferência entre duas contas
   (`transferencia='2'`). Replicado exatamente como está (ver comentário
   no service), mas é candidato a virar uma coluna `conta_destino`
   dedicada numa 2ª fase — não decidido nem aplicado, só documentado.
5. **Recibo de impressão** — o legado imprime direto numa impressora
   térmica/matricial local (COM `Printer` do VB6, cabeçalho completo da
   empresa vindo de `controle`: endereço, bairro, CEP, telefone, CNPJ,
   inscrição estadual). Como o projeto ainda não tem infraestrutura de
   impressão de POS (ver memória "Impressão automática por Finalidade" —
   decidido fazer via backend+socket/agente local, não implementado
   ainda), a versão nova abre uma janela de impressão do navegador
   (`window.print()`) com um recibo simplificado (sem o bloco de endereço
   completo da empresa). Vale revisitar quando a infraestrutura de
   impressão de POS for construída.

---

## Gestor de Documentos (Anexos)

**Status**: 🟡 parcialmente bloqueada — as 2 perguntas de negócio abaixo
seguem sem resposta, mas não bloqueiam mais o trabalho: Fornecedores,
Produto Completo e Pedido Bar foram integrados normalmente porque nenhum
dos dois pende deles (ver "Integração em Pedido de Venda" abaixo).

**Registrada em**: 2026-07-10

### O que já foi analisado e implementado

Migração do `FrmGesDoc.frm` (legado) — anexos genéricos reutilizados por
várias entidades "principais" (Cliente, Fornecedor, Funcionário, Produto,
Serviço), sem menu próprio, e também por entidades "secundárias" (Pedido de
Venda, O.S., Contrato, Orçamento, Agendamento — que não têm tabela própria
de anexos, ficam registrados como anexos do Cliente com um sub-grupo +
referência específicos).

**Backend** (`backend/services/gestor_documentos_service.py` +
`backend/routes/gestor_documentos.py`):

- CRUD completo: listar grupos/sub-grupos, listar/salvar/excluir documentos,
  baixar arquivo (`/arquivo`, `Content-Disposition: inline` para permitir
  preview).
- Schema real conferido ao vivo em GERDELL/BARESTELA (não assumido do VB6):
  - `gestor_docs_grupos(codigo, grupo)`: 1=Clientes, 2=Fornecedores,
    3=Funcionários, 4=Produtos, 5=Serviços.
  - `gestor_docs_sub_grupos(cod_sub_grupo PK, cod_grupo FK, descricao)` —
    cadastrado sob demanda por grupo. Conferido ao vivo (2026-07-10): grupo 1
    (Clientes) tem 1=Imagens, 2=Pedidos de Venda, 3=Orçamentos, 4=Ordens de
    Serviço, 5=Contratos, 6=Diversos, 14=Agendamentos; grupo 2
    (Fornecedores) tem 7=Pedido de Compra, 8=Diversos; grupo 3
    (Funcionários) tem 9=Imagens, 10=Diversos; grupo 4 (Produtos) tem
    11=Imagens, 12=Diversos; grupo 5 (Serviços) tem só 13=Diversos.
  - `gestor_documentos(codigo PK, cod_grupo, cod_sub_grupo, path, descricao,
    path_origem, adicionado_por, data, hora, computador, validade,
    referencia_texto, referencia_codigo, referencia, situacao_arquivo, cor)`.
    Tabela está **vazia** hoje (zero linhas em qualquer grupo) — não há dado
    de produção real pra conferir empiricamente os padrões de preenchimento.
  - Tabelas de junção por grupo (duplicação proposital, fiel ao legado):
    `cliente_anexos`, `fornecedor_anexos`, `funcionario_anexos` (código
    inteiro) e `pecas_anexos`, `servicos_anexos` (`codigo_int nvarchar(8)` —
    confirmado ao vivo: `pecas.codigo_int` é `nvarchar(8)` com valores tipo
    `"P100"`; `servicos.codigo` também é `nvarchar(8)` com prefixo `"S"`).
  - `referencia_codigo` (int) = código da entidade principal, usado por
    Cliente/Fornecedor/Funcionário. `referencia_texto` (string) = mesma
    coisa, usado por Produtos/Serviços (códigos alfanuméricos, não cabem em
    coluna int). Exatamente um dos dois é preenchido por linha, nunca ambos,
    nunca nenhum.
  - `referencia` = código do registro específico dentro do sub-grupo (nº do
    pedido/contrato/O.S./etc.) — vazio/0 quando o anexo foi adicionado
    direto na entidade principal, sem sub-contexto.
  - `cod_sub_grupo` é o filtro extra necessário quando quem chama não é uma
    entidade principal — ex.: Pedido nº100 e O.S. nº100 do mesmo cliente
    colidiriam se filtrasse só por `referencia`.
- Armazenamento dual: local (disco/rede) OU Azure Blob Storage, decidido em
  tempo real pelo valor de `controle_aux.path_gestor_documentos` (URL de
  blob vs. path local) — não é uma escolha fixa por instalação.
- Exclusão: hard delete em geral; exceção fiel ao legado para Produtos
  (grupo 4) — soft delete (`situacao_arquivo='D'`).

**Frontend** (`frontend/src/components/GestorDocumentosSection.tsx`):

- Componente único reutilizável, props `{api, servidor, banco, codGrupo,
  codigoEntidade, codSubGrupo?, referencia?}` — já integrado em
  `cliente-completo.tsx`, `servicos.tsx`, `fornecedores.tsx` e
  `produto-completo.tsx` (todos como aba/seção "Anexos").
- Painel de preview (`<img>`/`<iframe>` conforme extensão), campos
  Referência (bloqueado quando a prop é passada de fora) e Validade.

### Integração em Pedido de Venda (Pedido Bar) — feita em 2026-07-16

Pedido não é entidade principal do Gestor de Documentos — segue exatamente
o desenho já previsto acima ("entidades secundárias"): grava como anexo do
**Cliente** (`cod_grupo=1`), sub-grupo "Pedidos de Venda"
(`cod_sub_grupo=2`, confirmado ao vivo em GERDELL/BARESTELA:
`GET /api/gestor-documentos/sub-grupos?cod_grupo=1` retorna
`{cod_sub_grupo:2, descricao:"Pedidos de Venda"}`) + `referencia` = número
do pedido.

- **Nova peça**: `frontend/src/components/pedido/AnexosPedidoModal.tsx` —
  modal (não aba inline, já que Pedido Bar não é uma tela "Full CRUD" com
  abas) envolvendo `GestorDocumentosSection` sem modificá-lo. Largura maior
  que o tier padrão de 560px (usa 920px) porque o componente embutido tem
  lista + preview lado a lado — mesma ressalva já registrada em CLAUDE.md
  sobre a aba Anexos precisar de mais espaço.
- Botão "Anexo" na toolbar do Pedido Bar
  (`frontend/src/components/pedido/ItemList.tsx`), entre Faturar Pedido e
  Imprimir — permissão própria `PEDIDO.ANEXOS` (catálogo em
  `permissoes_service.py`).
- **As 2 perguntas em aberto abaixo NÃO bloqueiam esta integração**: a
  Pergunta 1 é sobre `referencia_texto` vs `referencia_codigo` para
  Serviços/Produtos como entidade PRINCIPAL — Pedido nunca é a entidade
  principal aqui (sempre Cliente, que já usa `referencia_codigo`, sem
  ambiguidade). A Pergunta 2 (`sub_referencia`) não tem prop equivalente
  usada por esta integração — o número do pedido é sempre numérico, cabe
  inteiro em `referencia` (não precisou de um campo alfanumérico paralelo).
- **Testado ao vivo** (upload → listagem filtrada por sub-grupo+referência
  → listagem sem filtro → exclusão) contra o pedido real #10330 (cliente
  999) em GERDELL/BARESTELA — dado de teste já removido, arquivo físico
  também confirmado removido (delete é best-effort sobre o arquivo, ver
  `gestor_documentos_service._delete_documento_sync`).
- **Não integrado ainda**: O.S. (mesma arquitetura se aplicaria, sub-grupo
  "Ordens de Serviço" = `cod_sub_grupo=4`) e Pedido Completo (web) — não
  pedidos ainda, mesmo padrão pronto pra reaproveitar quando pedirem.

**Testado ponta-a-ponta** (upload, listagem com/sem filtro de sub-grupo,
exclusão) contra Cliente e Serviços nesta sessão; dados de teste já
limpos — tabela está vazia agora, como dito acima.

### Perguntas em aberto (bloqueantes)

O usuário trouxe uma explicação nova sobre um **type global** do VB6
(`GestorDocumentos`) que é setado pela tela chamadora antes de abrir
`FrmGesDoc`, com pelo menos estes campos vistos em código real
(`Command15_Click`, tela de Funcionários):

```vb
GestorDocumentos.Grupo = 2
GestorDocumentos.sub_referencia = 0
...
GestorDocumentos.Codigo = CODFUNC
GestorDocumentos.referencia = ""
GestorDocumentos.sub_grupo = ""
```

**Pergunta 1** — O usuário afirmou: *"referencia_texto somente para
produtos como entidade, referencia_codigo para os demais."* Isso conflita
com o schema real: `servicos.codigo` (grupo 5) é `nvarchar(8)` com prefixo
"S" — não cabe em `referencia_codigo` (int), igual a Produtos. Minha
implementação atual trata Produtos **e** Serviços como `referencia_texto`
(`_GRUPOS_CODIGO_TEXTO = {GRUPO_PRODUTO, GRUPO_SERVICO}` em
`gestor_documentos_service.py`).

> **Confirmar**: Serviços (grupo 5) também deve usar `referencia_texto`
> (como a estrutura da tabela exige), ou existe alguma razão para o legado
> tratar Serviços de forma diferente de Produtos aqui — por exemplo, um
> código numérico paralelo pra Serviços que eu ainda não conheço?

**Pergunta 2** — O que é `sub_referencia` no type global? Hoje
`GestorDocumentosSection` só tem prop equivalente para `Grupo` (`codGrupo`),
`Codigo` (`codigoEntidade`), `sub_grupo` (`codSubGrupo`) e `referencia`
(`referencia`) — não há nada mapeado para `sub_referencia`.

> **Confirmar**: `sub_referencia` é um campo paralelo a `referencia`, usado
> quando o código do registro específico (não da entidade) é alfanumérico
> em vez de numérico (ex.: um Contrato com código texto)? Ou é campo legado
> sem uso real hoje, que posso ignorar? Se for um campo real em uso, preciso
> adicionar uma prop nova em `GestorDocumentosSection` e uma coluna
> correspondente (ou reaproveitar `referencia_texto`?) em
> `gestor_documentos`.

### Próximo passo ao retomar

**Atualizado 2026-07-16**: o bloqueio original ("não avançar a integração em
novas telas até essas respostas chegarem") foi revisto — Fornecedores,
Produto Completo e Pedido Bar (ver "Integração em Pedido de Venda" acima)
já foram integrados normalmente, porque nenhuma das duas perguntas se
aplica a eles (Pergunta 1 é só sobre Serviços-como-entidade-principal;
Pergunta 2/`sub_referencia` nunca teve um consumidor real ainda). As
perguntas continuam abertas só para o dia em que alguém realmente precisar
de uma dessas duas coisas — não há mais nada travado por causa delas hoje.

Se/quando a resposta chegar: (1) ajustar/confirmar `_GRUPOS_CODIGO_TEXTO`
em `gestor_documentos_service.py`; (2) se `sub_referencia` for um campo
real, mapear em `GestorDocumentosSection` (nova prop) e no schema; (3)
atualizar a memória de projeto `project_gestor_documentos.md` com a
resposta.

**Ainda não integrado** (sem pergunta pendente, só não pedido ainda): O.S.
e Pedido Completo (web) — mesmo padrão de `AnexosPedidoModal.tsx` se aplica
direto quando pedirem (O.S. usaria sub-grupo "Ordens de Serviço",
`cod_sub_grupo=4`, já confirmado ao vivo).
