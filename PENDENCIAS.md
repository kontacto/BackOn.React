# Pendências de Migração

Formato e processo definidos em `promptPendencias.md` (seção 10 — "Gestão de
pendências entre telas"). Ao retomar uma tela listada aqui, ler a seção
inteira antes de continuar — não reanalisar do zero.

---

## "Design Desktop" — Varredura de Densidade em Todas as Telas Web

**Status: 🟡 em andamento, iniciado 2026-08-13.** Ver CLAUDE.md > "'Design
Desktop' — App Web como Substituto do Desktop VB6" para a regra completa e
`feedback_design_desktop` (memória) para o histórico. Pedido explícito do
usuário ("varre as outras telas" — Pedido Bar já estava feito antes desta
rodada) para aplicar retroativamente a todas as ~180 telas web já
construídas (`frontend/app/**/*.tsx`) — trabalho de várias sessões.

### Mudança global já aplicada (beneficia toda tela de uma vez)

- `frontend/src/theme/webLayout.ts`: `WEB_CONTENT_MAX_WIDTH` 1120 → 1600.
- Novos tokens `WEB_FIELD_COL_TINY`/`WEB_FIELD_COL_NARROW`/
  `WEB_FIELD_COL_HALF`/`WEB_FIELD_COL_FLEX` — `flexBasis`+`maxWidth` em vez
  de `width: "N%"` cru, pra campo curto não esticar proporcionalmente à
  largura do container num monitor grande.

### Telas já corrigidas (2026-08-13)

- `OSEquipamentoCard.tsx` — exemplo concreto que motivou a regra (campos
  empilhados full-width + botão "Salvar" do tamanho da tela); virou
  `fieldsRow`/`colHalf` 2 colunas + botão pill pequeno à direita.
- `cliente-completo.tsx` (tela de referência do "Full CRUD Form Screen
  Standard") — `colHalf` trocado pro token compartilhado
  `WEB_FIELD_COL_HALF`; campos genuinamente curtos (Sexo, Situação,
  Status, Data Nascimento/Abertura, Limite de Crédito, Desconto%, Valor do
  Frete, Prazo de Faturamento, Dia de Contato/Entrega) movidos pro
  `colNarrow` novo (`WEB_FIELD_COL_NARROW`) — antes todos ficavam a 49% do
  container (~780px num monitor largo) mesmo sendo um combo de 2 opções.
- `funcionario-completo.tsx`, `produtos-niveis.tsx`, `log-auditoria.tsx`
  — mesmo padrão exato de `colHalf: { width: "49%" }` encontrado e
  trocado pro token compartilhado (fix mecânico, sem revisão
  campo-a-campo individual ainda).
- `produto-completo.tsx`, `fornecedores.tsx`, `servicos.tsx`,
  `contrato-completo.tsx` — padrão `rowFields`/`colFlex`/`colHalf` local
  (`flex: 1` sem `maxWidth`) ganhou `maxWidth` (280–420px conforme o
  arquivo) pra parar de esticar em container largo.
- `tsc --noEmit`: baseline de 12 erros pré-existentes inalterado em todo o
  lote (nenhum novo erro introduzido).

### Não testado visualmente ainda

Todas as mudanças acima foram só verificadas por `tsc`/leitura de código —
**nenhuma foi vista rodando no navegador** (sem ferramenta de automação de
navegador disponível neste ambiente). Antes de considerar este lote
definitivamente concluído, abrir cada tela corrigida no navegador
(`npm run web`/skill `run`) e conferir visualmente que os campos ficaram
agrupados corretamente, sem quebra de layout.

### `os-geral.tsx` — 2ª rodada de correções ao vivo (2026-08-13)

Usuário testou a tela de verdade (screenshot da O.S. #294) e apontou 5
problemas concretos, todos corrigidos na mesma rodada:

1. **Cliente aparecia tarde demais na tela** (depois do card "Revisão
   Programada") — movido pra logo depois do cabeçalho principal, mesma
   posição de destaque que tem no VB6 (`FrmTraOsNew.frm`, campo "Cliente:"
   dentro do próprio frame "Dados da OS").
2. **Faltavam campos**: `previsao_termino`/`data_termino`/
   `hora_fechamento` já existiam no state (carregados do backend e
   enviados no Gravar) mas **nunca tinham controle de tela** — achado real
   ao investigar, não só percepção do usuário. Adicionados 3 campos novos
   (Previsão de Término, Data de Término, Hora de Fechamento) no cabeçalho
   principal, ao lado dos demais, via `WebDateField`.
3. **Texto de ajuda ocupando ~metade da tela** (parágrafo fixo sob
   "Revisão Programada") — trocado por `InfoTooltip` (componente novo,
   `frontend/src/components/InfoTooltip.tsx`, tooltip no hover com texto
   multilinha, diferente de `IconButtonWithTooltip` que trunca em 1
   linha). Reaproveitar este componente no resto da varredura sempre que
   aparecer um texto de ajuda longo demais pra caber sob o campo.
4. **Cada equipamento precisa de accordion** — `OSEquipamentoCard.tsx`
   ganhou estado de expandir/recolher (nasce aberto, não regride o caso
   comum de 1 equipamento só) — importante quando a OS tem vários
   equipamentos vinculados, pra não forçar scroll gigante.
5. **Campo multilinha do banco (nvarchar(500)) não parecia multilinha na
   tela** — regressão da 1ª rodada de densidade (`inputMulti.minHeight`
   tinha sido reduzido de 44 pra 36, ficando parecendo campo de 1 linha).
   Corrigido pra 64 — ainda compacto, mas visivelmente um textarea.

`tsc --noEmit`: baseline de 12 erros inalterado.

**Ajuste no mesmo dia**: "Revisão Programada" (título+tooltip+campo
Revisões, e os campos condicionais de Doc. Origem) saiu do card próprio
e entrou na MESMA linha do cabeçalho principal, ao lado de "Hora de
Fechamento" — pedido explícito do usuário. O card `os-geral-doc-origem`
próprio deixou de existir; tudo isso agora vive dentro do card
`os-geral-topo`.

**Mais 2 ajustes no mesmo dia, mesma sessão**:
- **Cliente movido pro final do 1º card** (economia de espaço) — só
  quando a OS já existe (`editing && os`, quando o card do topo de fato
  renderiza). `ClienteSection` foi extraído pra uma variável
  (`clienteSectionEl`) reaproveitada em 2 lugares: dentro do card do
  topo (caso comum) e num card avulso, só como fallback pro caso raro de
  OS ainda não gravada (senão não haveria como escolher cliente pra
  criar a 1ª vez — o card do topo só existe depois do 1º Gravar).
- **"Serviço Executado" e "Diagnóstico" trocaram de posição** em
  `OSEquipamentoCard.tsx` — "Defeito Reclamado"/"Diagnóstico" na 1ª
  linha, "Serviço a Executar"/"Serviço Executado" na 2ª. "Defeito
  Reclamado" e "Serviço a Executar" não mudaram de lugar.

`tsc --noEmit`: baseline de 12 erros inalterado nos dois ajustes.

**Bug real corrigido, mesma sessão — "Erro: Converting circular structure
to JSON" ao clicar Gravar de verdade no navegador.** Achado ao vivo pelo
usuário (1º clique real no botão Gravar desta tela — toda validação
anterior desta sessão foi via API direta). Causa raiz: `Pressable.onPress`
do cabeçalho (`PedidoHeader.tsx`) sempre chama a função com o evento de
clique; `onSave={handleSave}` direto fazia esse evento (nó do DOM) virar o
1º argumento de `handleSave(autorizadoPor?: string)`, que ia parar dentro
do corpo JSON gravado (`autorizado_por: autorizadoPor || null`) — daí
"Converting circular structure to JSON" ao serializar. Corrigido com
`onSave={() => handleSave()}` (zero argumentos passados adiante). Também
corrigido o `catch` de `handleSave` pra usar `friendlyCatchError` em vez
do texto cru de exceção (violava "Mensagens de Erro — Linguagem
Não-Técnica" `[GLOBAL]` do CLAUDE.md). **Checado e confirmado que Pedido
Bar/Geral NÃO têm o mesmo bug** — seus `handleSave` não recebem
parâmetro nenhum, o evento forwarded é só ignorado.

**3 ajustes adicionais, mesma sessão**:
- **Requisições Vinculadas / Criar Cópia movidos pro 1º card** — antes
  ficavam soltos abaixo dos totais junto dos itens; são ações de nível OS
  (não de item), fazem mais sentido perto do resto do cabeçalho.
- **Pontuação de Técnicos inline na linha do serviço** — novo componente
  local `PontuacaoInline` em `ItemList.tsx` (componente COMPARTILHADO com
  Pedido Bar/Geral, editado de forma aditiva e gated por `tela ===
  "OS_COMP"` — zero mudança de comportamento pro Pedido, mesmo padrão já
  usado pra Agendar/Imprimir Item). 3 campos numéricos estreitos
  (Técnico/Vendedor/Atendente) + ícone de salvar, direto na linha —
  `PontuacaoModal.tsx` (edição em lote) continua existindo, só deixou de
  ser o único caminho. `ItemRow` (`pedido/types.ts`) ganhou 4 campos
  opcionais novos (`cod_os_prod`/`pontuacao_e/v/a`) pra viabilizar isso
  sem importar o tipo `OSItemRow` no componente genérico — mesmo padrão
  já usado pros campos Fase B do Pedido Geral (`num_serie`/`agendamento`/
  `comprimento` etc.).
- **Tempo Gasto acessível direto da linha do serviço** — ícone novo na
  linha (só item tipo Serviço) abre `TempoGastoModal` já com o serviço
  pré-selecionado (prop nova `preselectCodigoInterno`), em vez do fluxo
  antigo (link genérico abaixo dos totais + reescolher o serviço num
  combo). O modal em si não mudou de formato (continua listando TODOS os
  lançamentos da OS, não só do item clicado — só o ponto de entrada
  ficou mais direto).

`tsc --noEmit`: baseline de 12 erros inalterado em todo o lote.

**Mais 1 ajuste, mesma sessão — espaçamento vertical geral reduzido**:
`styles.card` (usado por TODOS os cards desta tela) teve `padding`
reduzido de `spacing.lg`(16) pra `spacing.md`(12) e `marginBottom` de
`spacing.lg`(16) pra `spacing.sm`(8); o `gap` interno do card do topo
caiu de `spacing.md`(12) pra `spacing.sm`(8); e um `marginTop` redundante
que eu tinha deixado no bloco do Cliente (empilhava em cima do `gap` que
o card já aplicava) foi removido. Efeito: espaçamento visivelmente mais
compacto em toda a tela, não só ao redor do Cliente. `tsc` limpo.

### Fora do escopo desta rodada — pontos em aberto maiores

- **Pedido (Bar e Geral) fica de fora desta varredura por enquanto,
  user-directed 2026-08-13** ("vamos deixar o pedido por enquanto fora
  dessa alteração") — inclui `pedido-form.tsx`, `pedido-geral.tsx`,
  `pedido-lista.tsx`, `pedidos.tsx`, e por extensão `PedidoHeader.tsx`
  (compartilhado também por O.S. Geral, mas não deve ser tocado enquanto
  Pedido estiver fora de escopo, já que mexer nele afeta Pedido também).
  `pedido-geral.tsx` chegou a receber o fix mecânico de `colHalf` nesta
  sessão e foi **revertido** na mesma rodada pra respeitar esta exclusão
  — não reaplicar sem pedido explícito do usuário liberando Pedido de
  novo.
- **Redesenho da barra de ação (`PedidoHeader.tsx`)**: ícones de Ajuda/
  Anexos/Formulários escondidos atrás de tooltip-no-hover, quando o
  padrão VB6 (ver referência `FrmTraOsNew.frm` no CLAUDE.md) é uma coluna
  de botões rotulados SEMPRE visível. Bloqueado pelo ponto acima (Pedido
  fora de escopo) — não iniciar.
- **Grade de itens como tabela densa** (em vez de card grande por linha)
  — não avaliado ainda em nenhuma tela.
- **Painéis independentes lado a lado** (ex.: bloco de texto + bloco de
  checkboxes na mesma faixa horizontal, como no VB6) — não avaliado ainda.

### Telas restantes da varredura (não tocadas ainda)

Lista completa de `frontend/app/*.tsx` ainda não revisada quanto a
densidade — grande demais pra revisar de uma vez, retomar por categoria:

- **Cadastro completo / formulário denso** (maior prioridade, mesmo
  formato do que já foi corrigido): `veiculos.tsx`, `cilindro-cadastro.tsx`,
  `envio-terceiros.tsx`, `viagem-cadastro.tsx`, `num-serie.tsx`,
  `notas-fiscais.tsx`, `telemarketing.tsx`, `contatos.tsx`,
  `entrada-saida-caixa.tsx`, `equipamentos.tsx`, `controle-sistema.tsx`,
  `agenda.tsx`, `gestor-comandas.tsx`, `alterar-comanda.tsx`,
  `os-form.tsx`, `contas.tsx`, `conta-funcionario.tsx`,
  `bancos.tsx`, `cobrancas.tsx`, `geracao-boletos.tsx`,
  `modificadores.tsx`, `requisicao.tsx`, `pedido-compra.tsx`,
  `cotacao-compra.tsx`. **Excluído por enquanto**: toda a família Pedido
  (`pedido-form.tsx`, `pedido-geral.tsx`, `pedido-lista.tsx`,
  `pedidos.tsx`, `PedidoHeader.tsx`) — ver "Fora do escopo" acima.
- **Tabelas Auxiliares** (prioridade menor — telas pequenas, geralmente
  lista + modal compacto, já usam o "Compact Size Variant"):
  `area.tsx`, `area-atuacao.tsx`, `cfop.tsx`, `cfop-pis-cofins.tsx`,
  `centro-custo.tsx`, `cores.tsx`, `marcas.tsx`, `modelos.tsx`,
  `origem.tsx`, `regioes.tsx`, `rotas.tsx`, `segmentos.tsx`,
  `situacao.tsx`, `status-os.tsx`, `tamanho.tsx`, `taxas.tsx`,
  `tipo-cliente.tsx`, `tipo-doc.tsx`, `tipo-mov.tsx`,
  `tipo-mov-mensagens.tsx`, `tipo-os.tsx`, `tipo-os-prod.tsx`,
  `tipo-peca.tsx`, `tipo-servico.tsx`, `tributacao.tsx`,
  `unidade-medida.tsx`, `icms.tsx`, `grupo-mercadologico.tsx`,
  `grupo-pis-cofins.tsx`, `grupo-usuario.tsx`, `funcoes.tsx`,
  `executor-padrao.tsx`, `forma-pagamento.tsx`, `mensagens.tsx`,
  `mensagens-pdv.tsx`, `plano-contas.tsx`, `tabelas-auxiliares.tsx`
  (hub).
- **Posto de Combustível** (13 telas, prioridade a avaliar):
  `posto-afericoes.tsx`, `posto-bombas.tsx`, `posto-combustiveis.tsx`,
  `posto-custo.tsx`, `posto-estoque.tsx`, `posto-fechamento-turno.tsx`,
  `posto-ilhas.tsx`, `posto-meta.tsx`, `posto-mov-encerrantes.tsx`,
  `posto-reabertura-turno.tsx`, `posto-tanque-estoque.tsx`,
  `posto-tanque-nf.tsx`, `posto-tanques.tsx`.
- **Relatórios** (prioridade menor — já são filtro+tabela, naturalmente
  mais densos; conferir se algum filtro ainda usa campo esticado):
  todas as ~28 `relatorio-*.tsx`.
- **Listas/painéis** (já são tabela/card de lista, prioridade menor):
  `clientes.tsx`, `produtos.tsx`, `fornecedores` (lista já coberta acima
  como cadastro), `os.tsx`, `os-lista.tsx`, `pedidos.tsx`,
  `pedido-lista.tsx`, `movimentacoes.tsx`, `movimentacao-produtos.tsx`,
  `inventario*.tsx`, `gestao-compras*.tsx`, `curva-abc.tsx`,
  `bordero-cilindros.tsx`, `contrato-lista.tsx`,
  `contrato-produtos-disponiveis.tsx`, `contrato-tipo*.tsx`,
  `contrato-indice-reajuste.tsx`, `contrato-faturar.tsx`, `contratos.tsx`,
  `funcionarios.tsx`, `permissoes.tsx` (árvore, padrão próprio),
  `whatsapp-config.tsx`, `perfil-usuario.tsx`, `connections.tsx`.
- Hubs/tabs (`(tabs)/*.tsx`) — já são grade de cards (`Card List
  Ordering`), prioridade baixa, mas conferir se cabem mais colunas por
  linha no container mais largo.

---

## Catálogo de Permissões não filtrava telas em submenus aninhados `[GLOBAL]` — CORRIGIDO

**Status: 🟢 Corrigido e testado ao vivo, 2026-08-13.** Pedido do usuário:
"Módulos que não estão habilitados, que carregam telas pertinentes, não
devem aparecer nem para o Master... muito menos na Lista de permissão" —
exemplos dados: Envio para Terceiros (deveria exigir Oficina OU
Assistência) e Modificadores (deveria exigir Bar).

### Achado ao investigar

O mecanismo de gating já existia inteiro e corretamente desenhado
(`MODULE_TELAS` em `controle_config_service.py` + `disabled_telas()`/
`filter_catalogo()` em `permissoes_service.py`, incluindo a lógica OR pra
Oficina/Assistência) — **não era um problema de Master bypassar nada**
(nenhuma das duas funções sequer sabe o que é "master", filtram igual pra
todo mundo). O bug real: `filter_catalogo()` só filtrava o **1º nível**
de cada menu do catálogo — um menu ANINHADO dentro de outro (ex.:
`CADASTROS > Tabelas Auxiliares > Modificadores`) nunca tinha seu próprio
conteúdo filtrado de fato. Confirmado ao vivo contra `KONTACTO-TESTE`
(Bar=false): "Modificadores" continuava aparecendo no catálogo filtrado.

**Escopo do bug era maior que os 2 exemplos citados** — todo menu
aninhado tinha o mesmo problema: `COMPRA` (dentro de Transações — Curva
ABC/Gestão de Compras/Cotação/Pedido de Compra) e `CONTRATOS` (dentro de
Transações — 6 telas) também nunca eram filtrados por
`Curva_abc`/`contratos`, mesmo com esses módulos desligados.

### Correção

`filter_catalogo()` virou recursivo (`_filter_node`, mesmo padrão já
usado por `sort_catalogo`) — percorre menus aninhados em qualquer
profundidade, removendo tela por tela e o menu inteiro se ficar vazio.
3 testes novos em `test_permissoes_service.py`
(`TestFilterCatalogoRecursaoEmMenuAninhado`).

**Testado ao vivo** contra `KONTACTO-TESTE` (Bar=false/Oficina=false/
Assistencia=true) e `GERDELL`/`BARESTELA` (Bar=false/Oficina=true/
Assistencia=false/Curva_abc=true/contratos=false): Modificadores some,
OS/OS_COMP aparece (Oficina OU Assistência, OR confirmado dos dois
lados), Curva ABC aparece, todo o submenu Contratos some por inteiro
(os 6 filhos + o próprio menu). Suíte completa (1825 testes) sem
regressão.

---

## Gestor de Devolução

**Status: 🟢 Fase 1 enxuta implementada e TESTADA AO VIVO (2026-08-05)**
contra GERDELL/BARESTELA — ciclo completo (buscar → registrar com Vale →
sumir da busca → consultar → cancelar → volta a aparecer na busca)
validado ponta a ponta.

Migração de `Geral\FrmManDev.frm` ("Gestor de Devolução...") — pedido
explícito do usuário: "implemente em Transações a tela de Gestor
devolução. no sistema vb 6 fica também em transações". Rastreado via
agente de pesquisa antes de implementar (mesma disciplina de "Legacy VB6
Source Reference" no CLAUDE.md).

### Escopo confirmado via `AskUserQuestion` (2026-08-05)

1. **Fase 1 enxuta** (não o completo com emissão de NF) — o próprio
   legado já delega a emissão de NF de devolução inteira a um subsistema
   fiscal à parte (`FrmTraNFe.ImportaDevolucao`); esta migração faz o
   mesmo: busca + registro + Vale de Devolução, sem emitir NF.
2. **Não devolve estoque** (`pecas.qtd`) — confirmado no código real do
   `.frm` que esta tela NUNCA toca em `pecas.qtd`; quem devolve estoque de
   verdade é outro caminho do legado (Recebimento de Mercadoria/
   `FrmConDev.frm`, ao dar entrada na NF de devolução) — fora de escopo
   aqui, fiel ao rastreio.

### Achados do rastreio (3 forms relacionados no `.vbp` canônico)

- **`FrmManDev.frm`** = tela principal ("Gestor de Devolução..."). Busca
  itens de venda já **PAGA** (`comanda.situacao='PG'`) — devolução
  independe de qual documento originou a venda (Pedido, O.S., Cupom,
  NFC-e, Contrato — todos convergem pra `comanda`/`movimentacao` no
  fechamento). Filtros reais: data/cupom/NFC-e/NF/comanda/cliente/
  produto/valor unitário.
- **`FrmConDev.frm`** ("Selecionar Itens para Devolução") — **não** é
  chamado a partir do Gestor de Devolução — é um segundo caminho de
  entrada, invocado de dentro do Recebimento de Mercadoria
  (`FrmtraRec.frm`) quando o usuário cadastra uma NF de entrada tipo
  "Devolução" (`tipo_nf=6`), pra vincular vendas correspondentes — **é
  esse caminho que efetivamente marca `movimentacao.Estornado=1`** (não
  implementado nesta migração, fica pro dia em que o Recebimento de
  Mercadoria com NF tipo Devolução for revisitado).
- **`FrmItensDevolucao.frm`** — apesar do nome, **sem relação real** com o
  fluxo de devolução (não referencia `devolucao_itens`/`vale_devolucao`/
  `devolucao_config` em lugar nenhum) — é um relatório genérico de vendas,
  provavelmente nome remanescente de versão antiga repropositada. Não
  usado como fonte.

### Achado importante sobre `devolucao_itens.Status`

**NÃO é um estado de fluxo** (pendente/concluído) como o nome sugeriria —
confirmado contra dado real (GERDELL/BARESTELA): é o **motivo/tipo da
devolução**, lookup `devolucao_status` com só 2 linhas reais cadastradas
(`1="Devolução Normal"`, `2="Devolução por Defeito"`). Implementado
exatamente assim — campo obrigatório por item ao registrar.

### Backend

- `backend/services/devolucao_service.py`: `_list_motivos_sync` (lookup
  `devolucao_status`), `_list_itens_venda_sync` (busca itens elegíveis —
  reaproveita `_resolver_cliente_termo`/`_resolver_produto_termo` de
  `comanda_service.py`, mesma base do Gestor de Comandas, não duplicado),
  `_registrar_devolucao_sync` (grava `devolucao_itens` + `vale_devolucao`
  opcional, valida quantidade contra saldo ainda não devolvido),
  `_list_devolucoes_sync` (consulta, réplica simplificada de
  `FrmConDev.frm`), `_cancelar_devolucao_sync` (reversão: cancela o Vale
  vinculado se houver, bloqueia se já tiver NF vinculada — mesma regra do
  legado "excluir da fila cancela o vale").
- Módulo gateado por `controle_configuracao.devolucao` (coluna já
  existente, já cadastrada em `controle_config_service.py` antes desta
  rodada — só faltava a tela nova checar) — `_modulo_devolucao_ativo`
  checado em TODAS as funções do service (mesmo padrão de "Regra de
  Módulo Ativo" no CLAUDE.md).
- Rotas em `backend/routes/devolucao.py`: `GET /devolucao/motivos`,
  `POST /devolucao/buscar-itens`, `POST /devolucao/registrar`,
  `POST /devolucao/consulta`, `POST /devolucao/{id}/cancelar`. Registrado
  em `server.py`.
- Permissão `DEVOLUCAO` no catálogo (menu Transações, dentro do mesmo
  `_menu("TRANSACOES", ...)` que já tem Contratos/Compra), ações
  ABRIR/REGISTRAR/EMITIR_VALE/CANCELAR.
- Schemas novos em `models/schemas.py`: `DevolucaoBuscarItensRequest`,
  `DevolucaoItemRegistrar`/`DevolucaoRegistrarRequest`,
  `DevolucaoConsultaRequest`, `DevolucaoCancelarRequest`.
- **Simplificação registrada**: o valor do item devolvido é
  `qtd_devolvida × p_unit`, sem o rateio de frete/outras despesas/desconto
  que o legado aplica — `devolucao_itens.frete/outras/descontos` sempre
  gravados como 0 nesta fase.
- **14 testes novos** em `test_devolucao_service.py` (busca com exclusão
  de saldo já devolvido, registrar com/sem vale, bloqueio de quantidade
  acima do saldo, bloqueio sem cliente ao emitir vale, consulta, cancelar
  com reversão de vale, bloqueio se já tem NF, gating de módulo em todas
  as operações) — 1501 testes de backend passando no total (mesmos 67
  pré-existentes de Gestão de Compras, não relacionados).

### Bug real encontrado e corrigido de passagem (não relacionado à feature nova)

Ao testar ao vivo, a descrição do produto voltava **em branco** pra itens
com `pecas.descricao_pdv` = string vazia (não NULL) — `ISNULL(p.
descricao_pdv, p.descricao)` só cai pro fallback quando o valor é NULL,
nunca quando é `''`. **Esse exato padrão já existia em 2 lugares do
`checkout_service.py`** (`_get_venda_sync` e `_buscar_produto_sync`) desde
antes desta sessão — corrigido nos 4 lugares (2 no Checkout, 2 na
Devolução) pra `ISNULL(NULLIF(p.descricao_pdv,''), p.descricao)`. Vale
revisar se esse mesmo padrão aparece em outro service que leia
`descricao_pdv` no futuro.

### Frontend

- `frontend/app/devolucao.tsx` (web-only, tela única com 2 abas internas
  — "Buscar e Registrar" / "Consulta" — não é o padrão "Full CRUD Form
  Screen Standard" porque não é um cadastro de registro único, é mais
  parecido com um relatório/utilitário, mesma categoria de Movimentação
  de Produtos/Requisição).
- Card "Gestor de Devolução" em `transacoes.tsx`, dentro do menu
  Transações (gateado por `moduleOn("devolucao") && can("DEVOLUCAO.ABRIR")`),
  ordenado alfabeticamente junto dos demais.
- Seleção de cliente pro Vale de Devolução via `ClientSearchModal`
  (mecanismo de busca obrigatório pra campo de identidade, regra
  `[GLOBAL]` já registrada) — auto-preenchido com o cliente do primeiro
  item marcado, editável.
- "Modo Didático" aplicado: ícone de Ajuda no cabeçalho + modal único
  (`AjudaPedidoModal` reaproveitado) explicando cada ação.
- `tsc --noEmit` sem erro novo (mesmos 12 pré-existentes de sempre).

### Fora de escopo desta fase (não são bugs)

- Emissão de NF de devolução (delegada no legado a `FrmTraNFe`) — se
  pedido depois, avaliar reaproveitar o módulo Notas Fiscais.
- Reposição física de estoque — fica pro Recebimento de Mercadoria (NF de
  entrada tipo Devolução), quando/se essa tela for revisitada.
- Vale de Devolução como forma de pagamento **consumível** numa venda
  futura (Checkout) — só a emissão foi implementada; o Checkout ainda não
  sabe consumir um `vale_devolucao` como forma de pagamento (mesma
  pendência já registrada em "Checkout" > "Cartão Presente/Vale de
  Devolução").
- Painel "Manutenção da Devolução" do legado (fila de itens já
  registrados aguardando NF) — coberto pela aba "Consulta" desta
  implementação, formato mais simples.
- Config de CFOP/Código ICMS por tipo de movimento/destino
  (`devolucao_config`) — só é necessária pra emissão de NF, fora de
  escopo nesta fase.

---

## Checkout

**Status: 🟡 Fase 1 (núcleo) + Fase 2 (importar Pedido/O.S. como DAV) +
Fase 3 (impressão de cupom/comprovante) implementadas (2026-08-04/05), NÃO
testadas ao vivo contra banco real.**
Migração de `FrmPafOFF.frm` ("Emissão de Cupom Fiscal"
— o PDV/venda direta de balcão do legado, `C:\Desenv\VB6\SQLSERVER\Kontacto\
backon.vbp`). Escopo faseado confirmado com o usuário via `AskUserQuestion`
(2026-08-04) dado o tamanho real do form (~14 mil linhas, dezenas de
subsistemas: cupom fiscal, TEF, cartão com administradora/parcelador,
cheque, vale-devolução, abastecimento de posto, agenda, importação de
Pedido/O.S./Orçamento como DAV, venda externa por ficha, NFC-e).

### Redesenho da tela (2026-08-05) — layout moderno + operação 100% teclado/leitor de código de barras

Depois da Fase 3, o usuário colou um screenshot do `FrmPafOFF.frm`
("Emissão de Cupom Fiscal") e pediu explicitamente pra tela ficar "mais
parecida" com ele, mais 2 outros exemplos de PDV (um estilo "SysPDV" com
destaque grande do último item bipado, outro estilo grade colorida
tipo depósito/estoque) — confirmado via `AskUserQuestion` que a direção
certa era **sintetizar os 3, não copiar nenhum literalmente**: grade de
itens com colunas claras (Descrição/Qtd/Unitário/Total), destaque grande
do último item lançado, mantendo o conceito "Demonstrativo do Cupom
Fiscal" como o painel principal — layout moderno, não cupom monoespaçado
nem grade fria de planilha.

Exigências explícitas do usuário, todas endereçadas:

- **"Não quero utilizar o mouse para navegar nos campos"** + "criar um
  checkout moderno com sua operação por teclado/leitor de barcode": campo
  Código (`checkout-codigo-input`, `codigoRef`) é o único foco necessário
  — Enter (ou o Enter automático que um leitor de código de barras manda
  depois de bipar) já **inclui o item direto na venda** (chama
  `adicionarItem()` direto, sem etapa de "confirmar" no meio), e o foco
  volta sozinho pro campo Código em seguida (`codigoRef.current?.focus()`
  dentro do `then` de sucesso de `adicionarItem`), pronto pro próximo
  bipe. Campos Quantidade/Desconto % só existem pra quem quer ajustar
  ANTES de bipar (Tab entre eles, Enter neles só move o foco de volta pro
  Código) — não fazem parte do caminho rápido padrão.
- **"Ao clicar no card Checkout, tem que abrir direto a tela"**: novo
  `useEffect` que chama `abrirVenda()` sozinho assim que `conn`/`vendedor`
  estão prontos e `comanda` é `null` — a tela "Nenhuma venda em andamento"
  com botão manual foi removida do caminho normal (só sobra como fallback
  raríssimo se abrir automaticamente falhar). Dispara de novo sozinho
  sempre que `comanda` volta a `null` (venda cancelada, ou "Nova Venda"
  clicado após fechar).
- **"Quero um demonstrativo de cupom fiscal na tela, com os produtos
  listados"**: novo componente `frontend/src/components/checkout/
  DemonstrativoCupomFiscal.tsx` — substitui o antigo card "Itens da
  Venda" (removido, consolidado num só lugar, mesmo padrão do legado onde
  a MESMA lista serve de preview E de cancelar item, aqui via ícone por
  linha em vez de duplo clique). Mostra: destaque grande do último item
  lançado (descrição + qtd x unitário = total, cores fortes), grade com
  colunas Descrição/Qtd/Unit./Total pros itens já lançados, badge Pedido/
  O.S. pra itens importados via DAV, e um box de TOTAL A PAGAR em destaque
  no rodapé do painel.
- **"Para listar vendas já temos a tela de Gestão de Comandas"**:
  confirmado — Checkout nunca teve nem ganhou uma lista de vendas
  passadas; o Demonstrativo é só da venda EM ANDAMENTO.
- Preview do campo Código também passou a mostrar **Un. Medida** e
  **Estoque Atual** (campos que o backend já retornava — `unidade`/
  `estoque` em `_buscar_produto_sync`/`GET /api/checkout/produto` — só não
  eram exibidos no frontend antes), junto com preço e limite de desconto.
- Novo rodapé de totais em 4 caixas (Total Bruto / Descontos / Acréscimos
  / Total a Pagar), calculados no frontend a partir de `itens` (`qtd ×
  preco_bruto` / `qtd × desconto_unit` / `qtd × acrescimo_unit`) — nenhum
  endpoint novo precisou ser criado, os campos já vinham em `_get_venda_
  sync`.
- **Não implementado nesta rodada** (fora do escopo do que foi pedido):
  campo "Área de Atuação" do legado (existe suporte no backend —
  `comanda.area_atuacao`, `CheckoutAbrirRequest.area_atuacao` — mas não há
  endpoint pra EDITAR depois de aberta a venda, e expor isso exigiria
  decidir esse fluxo antes; deixado de fora por ora).
- **Continua sem testar ao vivo contra banco real** (nem o núcleo, nem o
  redesenho) — próximo passo natural antes de considerar isso pronto de
  verdade.

### Decisão de arquitetura confirmada com o usuário

**Precisão importante (corrigida 2026-08-05 — a redação original desta
seção estava ambígua/incorreta neste ponto)**: Faturar em Pedido/O.S. **já
grava, sim**, em `comanda` (cabeçalho) e `movimentacao` (itens, tipo='S01',
serie_nf='CM') — `_faturar_pedido_sync`/`_faturar_os_sync` fazem
`INSERT INTO comanda ... OUTPUT INSERTED.comanda` seguido de um
`INSERT INTO movimentacao` por item, exatamente o "molde" que o Checkout
reaproveita. **O que Pedido/O.S. NUNCA grava** são as 8 tabelas de
*detalhe de forma de pagamento* — `comanda_dinheiro`/`comanda_cheque`/
`comanda_cartao`/`comanda_debito`/`comanda_duplicata`/`comanda_ticket`/
`comanda_vale`/`comanda_financiado` — a forma de pagamento do Pedido/O.S.
vai pra `pedido_venda_*`/`os_*` (ver "Correção de arquitetura" em
`fechamento_caixa_service.py`); `comanda_service.py` (Gestor de Comandas)
só *LÊ* essas 8 tabelas, e ficam vazias quando a comanda se originou de
Pedido/O.S.

**A diferença real de arquitetura do Checkout, então, é mais estreita do
que "grava em vez de ler comanda"**: é ser o único caminho do backend que
grava DIRETAMENTE nessas 8 tabelas de forma de pagamento — o `comanda`/
`movimentacao` em si o Checkout só replica o mesmo padrão que Faturar já
usa, não é território novo. Confirmado por investigação de código antes de
implementar: **hoje nenhum caminho do backend cria uma `comanda` do zero,
sem um documento (Pedido/O.S./Contrato) por trás** — é essa lacuna
específica (venda direta, sem Pedido/O.S. prévio) que o Checkout preenche,
não o ato de gravar em `comanda`/`movimentacao` em si.

**Divergência de schema real, confirmada lendo o legado** (não presumida):
`comanda_financiado` usa a coluna `valor_pago` (não `valor_pag` como em
`pedido_venda_financiado`/`os_financiado`) e não tem coluna de vencimento —
por isso `checkout_service.py` usa um mapa `_CMD_VALOR_COL`/`_CMD_VENC_COL`
LOCAL, não os dicts genéricos de `pedido_common.py` (evita arriscar o
código já testado de Pedido/O.S.). **Confirmado pelo usuário (2026-08-05):
"é isso mesmo"** — abordagem validada, sem mudança necessária.

### Fase 1 (implementada) — núcleo

- Backend: `backend/services/checkout_service.py` (abrir venda, resolver
  produto/serviço com promoção `pecas_promocao` e Preço por Quantidade
  `pecas_preco_qtd`, adicionar/cancelar item, desconto por item com limite
  por função do atendente + bypass por autorização, desconto geral da venda
  redistribuído proporcionalmente, definir cliente, fechar venda com
  múltiplas formas de pagamento + cálculo de troco, cancelar venda),
  `backend/routes/checkout.py`, schemas `Checkout*` em `models/schemas.py`.
- Cartão de Crédito/Débito: validação COMPLETA de Administradora +
  Parcelador (Loja/Administradora) + Parcelas, réplica fiel de
  `Cartao_Verifica_Parcelamento` (`Geral\Gestor_Cartoes.bas`) — decisão
  explícita do usuário (2026-08-04) de incluir isso já na Fase 1, em vez de
  adiar. Lookups `GET /api/checkout/cartoes/administradoras` e
  `GET /api/checkout/cartoes/parcelas`. **Não existia nenhum CRUD migrado
  pra `cartoes_administradoras`/`cartoes_configuracoes` antes desta rodada**
  — só um delete-guard em `bancos_service.py`; o cadastro dessas 2 tabelas
  em si (`FrmCadADM.frm`/`FrmGesCar.frm`) continua não migrado (só os
  lookups de leitura necessários pro Checkout). **Confirmado pelo usuário
  (2026-08-05): "ok"** — escopo aceito, sem pendência aqui.
- Permissão `CHECKOUT` no catálogo (menu Transações), ações ABRIR/ADD_ITEM/
  DEL_ITEM/DESC_ITEM/DESC_GERAL/FECHAR/CANCELAR — `DESC_ITEM` está
  registrada no catálogo mas ainda **não é checada** por nenhum endpoint
  (o desconto de item usa só a validação de limite por função, sem gate de
  permissão de grupo separado — mesma lacuna a fechar se vier a ser
  pedido).
- Testes unitários: `backend/tests/unit/test_checkout_service.py` (19
  testes, cobrindo abrir venda, adicionar item com/sem desconto, bloqueio
  de desconto acima do limite + bypass por autorização, cancelar item,
  desconto geral, validação de parcelamento de cartão nos 2 modos,
  fechamento com Dinheiro/Cartão/Financiado (confirma a divergência
  `valor_pago`), falta/troco, cancelar venda).
- Frontend: `frontend/app/checkout.tsx` (tela, web-only) +
  `frontend/src/components/checkout/FecharVendaModal.tsx` (modal de
  fechamento com múltiplas formas de pagamento) + card em
  `app/(tabs)/transacoes.tsx`.

### Simplificações registradas (não são bugs, decisões documentadas)

1. **Baixa de estoque na inclusão do item**: o legado tem essa linha
   COMENTADA em `Vende_Item` (`FrmPafOFF.frm`) — o VB6 original não baixa
   `pecas.qtd` por este caminho especificamente (algum outro processo do
   sistema legado cobria isso, não identificado). Esta migração decide
   baixar explicitamente no ato da inclusão (`_mover_estoque_direto`),
   mesmo princípio já usado por Pedido/O.S., só que sem uma fase
   intermediária de "reservado" — a venda aqui já é definitiva no momento
   da inclusão do item.
2. **Código de promoção digitado diretamente** (em vez do código do
   produto) — não implementado; o Checkout só resolve promoção já
   vinculada ao PRODUTO (`pecas_promocao`, mesma tabela/regra já usada por
   Produto Completo), não uma "compra pelo código da promoção" como
   caso de uso avulso.
3. **Desconto Geral**: réplica simplificada de `ProcessaDescontoGeral` —
   redistribui proporcionalmente entre os itens, mas não replica o loop de
   ajuste centavo-a-centavo nem o "joga a sobra no maior item" do legado;
   a soma pode divergir em poucos centavos do percentual pedido.
4. **`aceita_desconto` (pecas/servicos)**: achado real durante o rastreio —
   o legado usa esse campo de forma INVERTIDA em `FrmPafOFF.frm`
   (`RegProduto.Permite_Desconto = IIf(tb("aceita_desconto"), False,
   True)` — truthy BLOQUEIA desconto), enquanto `pedido_common.
   _linha_peca_completo` (usado pelo Pedido Completo) já interpreta o MESMO
   campo do jeito oposto (truthy PERMITE desconto). O Checkout desta Fase 1
   **não usa esse campo em nenhum dos dois sentidos** — só os limites
   percentuais `desc_g`/`desc_s`/`desc_v`.
   **Resolvido pelo usuário (2026-08-05)**: "não importa como hoje é lido,
   se invertido ou não, a finalidade é a mesma, se o produto ou serviço
   aceitam ou não desconto" — ou seja, o valor de verdade que interessa é
   só o FATO de negócio ("este item aceita desconto?"), não a convenção de
   bit usada pra representá-lo. Isso fecha a pergunta em aberto: não é uma
   contradição real entre Pedido Completo e o legado, são só 2
   implementações lendo o mesmo fato por convenções opostas — cada uma já
   resolve corretamente PRA SI. **Fica registrado como orientação pra
   quando o Checkout (ou qualquer tela nova) precisar checar esse campo**:
   implementar perguntando "este item aceita desconto?" como fato de
   negócio, conferindo contra dado real (ex.: um produto com
   `aceita_desconto` num valor conhecido, comparado ao comportamento
   esperado) antes de decidir o sentido do `if`, em vez de copiar a
   convenção de qualquer um dos dois lados sem verificar.

### Fase 2 (implementada, 2026-08-05) — Importar Pedido/O.S. como DAV

Migração de `Insere_Dav` (`FrmPafOFF.frm`, F4/F8 — F7/Orçamento não é um
caso separado nesta migração, ver "Regras Globais de Pré-venda" em
CLAUDE.md: Orçamento já é só um Pedido em situação Aberto).

- **Backend**: `checkout_service._importar_dav_sync` — puxa um Pedido de
  Venda ou O.S. já **Fechado** (situação='F', mesma exigência do legado,
  sem atalho de fechar automaticamente) pra dentro da venda aberta do
  Checkout. Por item: grava `movimentacao` com `tipo_dav`='P'/'O' e
  `COD_AUTO_DAV` (mesmas colunas que o legado já usa), copia preço líquido/
  bruto/desconto/acréscimo já calculados no documento de origem (sem
  recomputar), grava `comanda_desconto`/`comanda_acresc` quando aplicável,
  e **libera o reservado** (`reservado`/`reservado_os`) em vez de
  decrementar `pecas.qtd` de novo — o estoque já foi baixado quando o
  Pedido/O.S. foi Fechado. Vincula via `COMANDA_PED`/`comanda_os` e marca o
  documento de origem como `situacao='PG'` (Faturado) — mesmo efeito que
  Faturar já produz pra Pedido/O.S. avulsos, só que a `comanda` de destino
  é a venda do Checkout já aberta. O cliente do documento importado
  substitui o cliente atual da venda (mesmo efeito do legado,
  `RegVenda.codcliente = TmpClienteDav`).
- **Itens importados não podem ser cancelados individualmente** — réplica
  exata da regra do legado ("Este item pertence a um DAV ou Pré-Venda!
  Cancelamento não permitido!"). `_cancelar_item_sync` bloqueia quando
  `movimentacao.tipo_dav` está preenchido.
- **Cancelar a venda inteira com itens importados** reverte o Pedido/O.S.
  de origem de volta pra Fechado (`situacao='F'`), remove o vínculo
  `COMANDA_PED`/`comanda_os`, e **re-reserva** o estoque desses itens
  (`reservado`/`reservado_os` += qtd, sem tocar `pecas.qtd`) — mantém a
  decisão já tomada na Fase 1 de gerenciar estoque explicitamente em
  código (o legado deixa o equivalente comentado/incompleto em
  `CancelaCupom`, não replicado).
- **Rota**: `POST /api/checkout/{comanda}/importar-dav`. Reaproveita a
  permissão `CHECKOUT.ADD_ITEM` (importar é conceitualmente "adicionar
  itens", mesmo raciocínio do legado tratar F4/F7/F8 como formas
  alternativas de incluir item no cupom) — nenhuma permissão nova.
- **Frontend**: `frontend/src/components/checkout/ImportarDavModal.tsx`
  (tipo Pedido/O.S. + número) + botão "Importar Pedido/O.S." em
  `checkout.tsx` + tag "Pedido"/"O.S." nos itens importados (sem botão de
  cancelar nesses itens).
- **Testes**: 7 novos testes unitários (`TestImportarDav`,
  `TestCancelarItemBloqueiaDav`, mais um caso em `TestCancelarVenda`),
  26/26 passando.

**Simplificações registradas** (em relação ao `Insere_Dav` completo do
legado):
- Itens já cancelados no documento de origem são simplesmente ignorados
  (não copiados) — o legado tem um comportamento inconsistente aqui (soma
  no total sem gravar movimentação, `regitens()` populado mas sem INSERT),
  não replicado de propósito.
- Área de atuação do funcionário não é checada na importação (o legado
  restringe quais Pedidos/O.S. um funcionário não-master pode nem
  consultar por essa regra) — fora de escopo desta rodada.
- **O.S. com bloco Garantia/Interno/Contrato não é suportada** — só o
  bloco "cliente" (`os_produto.situacao=0`) é importado. A bifurcação de
  faturamento Garantia×Cliente (`_faturar_os_sync`, `FrmTraOsNew.frm`) é
  um subsistema à parte, não replicado aqui.
- Reconciliação de arredondamento de centavos ao final da importação (o
  legado ajusta a diferença no maior item) não é replicada — mesma decisão
  já tomada pro Desconto Geral na Fase 1.
- `item_paga_comissao` sempre gravado como 1 pros itens importados,
  independente do que o documento de origem tinha (o legado hardcoda isso
  pra Pedido também; pra O.S. seria uma coluna própria não confirmada
  como existente/populada neste schema já migrado).

### Fase 3 (implementada, 2026-08-05, DEPOIS SUBSTITUÍDA no mesmo dia) — Impressão de cupom/comprovante

Migração original de `Imprime_Comprovante` (`FrmPafOFF.frm`): preview de
recibo (JSX) + impressão via navegador (iframe oculto,
`src/utils/printHtml.ts`), atrás de um botão manual "Imprimir" —
`ReciboCheckoutModal.tsx`.

**Substituída no mesmo dia, user-directed** ("não tem botão imprimir.
tudo será de forma silenciosa no final do processo de venda. assim como
acontece no legado"): `ReciboCheckoutModal.tsx` foi **deletado por
completo** (órfão, nenhum outro consumidor) — não existe mais preview
HTML nem diálogo de impressão do navegador nesta tela. Ver "Impressão
Silenciosa — Fila + Agente Local" abaixo pro que substituiu isso:
impressão automática (silenciosa, via `POST /impressao/fila`) disparada
sozinha dentro de `fecharVenda`, sem qualquer botão. `_get_venda_sync`
(estendido nesta fase com `cliente_cgc_cpf`, `atendente_nome` sempre
`nome_guerra`, `descricao` da forma de pagamento e `troco`) continua
valendo — só o consumo no frontend mudou.

- **Não implementado**: modo "ticket de item único" (cozinha/bar) nem
  toggle de "imprimir totalizado" (agrupar itens repetidos) — o Checkout
  não tem o conceito de impressão automática por Finalidade que motivou
  isso no Pedido Bar, e sempre imprime a comanda inteira de uma vez.

### Fases ainda adiadas

- **TEF real** (integração com maquininha) — nenhum service de TEF existe
  no projeto; Cartão hoje só captura os dados manualmente (mesmo nível que
  Forma de Pagamento já faz pra Pedido/O.S.).
- **Abastecimento de posto e Agenda — IMPLEMENTADOS 2026-08-05**
  (`Mostra_Abastecimentos`/`Command10_Click` e `Mostra_Agenda`/
  `Command19_Click`, rastreados campo-a-campo em `Geral\FrmPafOFF.frm`
  antes de implementar). 2 botões INDEPENDENTES na barra de ações (não
  replica o slot único contextual F5 do legado — decisão de UI já
  registrada antes, ver histórico desta seção): "Abastecimento"
  (`moduleOn("Posto")`) e "Agendamento" (`moduleOn("CLINICA") ||
  moduleOn("Assistencia")`) — cada um só aparece com seu módulo ativo,
  podem aparecer os 2 juntos se a empresa tiver ambos.
  - **Backend** (`checkout_service.py`): `_list_abastecimentos_pendentes_
    sync`/`_importar_abastecimento_sync` e `_list_agendamentos_pendentes_
    sync`/`_importar_agendamento_sync` + rotas `GET /checkout/
    abastecimentos/pendentes`, `POST /checkout/{comanda}/importar-
    abastecimento`, `GET /checkout/agendamentos/pendentes`,
    `POST /checkout/{comanda}/importar-agendamento` (schemas
    `CheckoutImportarAbastecimentoRequest`/`CheckoutImportarAgendamentoRequest`).
  - **Diferente do legado, ambos gravam `movimentacao.tipo_dav`** ('ABA'/
    'AGE') + `COD_AUTO_DAV` (nº do abastecimento/agenda) — mesmo padrão já
    usado por `_importar_dav_sync` ('P'/'O'). O legado só marca a origem
    numa ListBox em memória (Abastecimento) ou não marca nada em
    `movimentacao` (Agenda, só a tabela de vínculo `agenda_comanda`) —
    decisão deliberada de NÃO replicar esse esquema frágil (ver "Não
    replicar truques VB6" em CLAUDE.md), pra poder bloquear cancelamento
    individual e reverter corretamente ao cancelar a venda inteira, igual
    já acontece com DAV.
  - **Abastecimento**: query real de `Mostra_Abastecimentos`
    (`abastecimento`/`bomba`/`pecas`, filtro `status_abastecimento=
    'PENDENTE'`). Importar marca `status_abastecimento='EMITIDO CF'`;
    cancelar a venda reverte pra `'PENDENTE'`. **Não decrementa
    `pecas.qtd`** — o combustível já saiu fisicamente do tanque
    (contabilizado por Mov. Encerrantes/Tanque-Estoque, outro caminho),
    mesmo princípio já usado pra itens de DAV. **Tabela `abastecimento`
    nunca é populada nesta migração** (só a integração de hardware Wayne
    Fusion, Fase 2, faria isso) — confirmado ao vivo contra GERDELL/
    BARESTELA (`GET /checkout/abastecimentos/pendentes` retorna
    `items: []`, módulo Posto ativo, query roda sem erro). O botão/tela
    funciona normalmente, só fica sem dado real pra mostrar até essa
    automação existir.
  - **Agenda**: query real de `Mostra_Agenda` (`AGENDA`/`servicos`/
    `funcionarios`/`cliente`, filtro `situacao_caixa='A'` + não vinculado
    a `AGENDA_PEDIDO`/`AGENDA_OS` — agendamentos presos a Pedido/O.S. só
    faturam por lá). Item lançado é o SERVIÇO do próprio agendamento
    (qtd=1, valor=`agenda.valor`). Grava o vínculo real `agenda_comanda`
    (mesma tabela já usada por `agenda_service._faturar_avulso_sync` —
    reaproveitada só como referência de schema, NÃO como função chamada
    diretamente: aquela fecha uma comanda NOVA de 1 item só; esta soma o
    item numa comanda JÁ aberta do Checkout). **Diferente do legado
    (`RegVenda.codcliente = agendamento.cliente`), NÃO troca o cliente da
    venda automaticamente** — decisão deliberada (trocar cliente "por
    baixo" silenciosamente é comportamento implícito demais; o operador
    usa o campo Cliente do Checkout se quiser).
  - **Frontend**: `AbastecimentoModal.tsx`/`AgendamentoModal.tsx` (tier
    "seleção", 560px) — lista + seleção direta por toque (sem etapa de
    confirmação extra, já que a lista em si já é filtrada por "pendente").
    `DemonstrativoCupomFiscal.tsx` ganhou `labelOrigem()` pra badges
    "Abastec."/"Agenda" (antes só tratava "Pedido"/"O.S.").
  - **13 testes novos** em `test_checkout_service.py` (listagem +
    importação + gating de módulo + bloqueio de cancelamento individual +
    reversão ao cancelar a venda inteira) — 40/40 passando no arquivo,
    1487 no total (mesmos 67 pré-existentes não relacionados). `tsc
    --noEmit` sem erro novo.
  - **Testado ao vivo contra GERDELL/BARESTELA**: `GET /checkout/
    abastecimentos/pendentes` (sucesso, lista vazia, módulo ativo),
    `GET /checkout/agendamentos/pendentes` (bloqueado corretamente, módulo
    Agenda inativo nesta conexão), `POST /checkout/{comanda}/importar-
    abastecimento` com número inexistente (erro tratado, sem crash) — mas
    **o caminho de sucesso completo de importação nunca rodou contra dado
    real** (abastecimento sempre vazio nesta conexão; agendamento nunca
    testado por falta de módulo ativo numa conexão de teste disponível).
- ~~**Venda Externa por ficha**~~ (`Insere_Dav` tipo 3, leitura de arquivo
  `.txt` de import de outro sistema) — **removida do escopo do projeto,
  confirmado pelo usuário (2026-08-05): "não é mais utilizada"**. Não é
  mais uma fase adiada — é uma feature do legado que não será portada,
  ponto final. Não revisitar.
- **Cartão Presente / Vale de Devolução — IMPLEMENTADO 2026-08-06**, como
  formas de pagamento consumíveis no fechamento da venda (`POST /checkout/
  {comanda}/fechar`). Pedido explícito do usuário: "implantar Cartão
  Presente / Vale de Devolução" + "na tela de checkout" + **"TEM QUE SER
  FIEL AO LEGADO"** (aplicado ao análogo mais próximo que o legado de fato
  implementou — Vale de Devolução — já que o resgate de Cartão Presente em
  si nunca existiu lá, ver abaixo). Rastreado via agente de pesquisa em
  `FrmPafOFF.frm::Finaliza_Pagamento`, `FrmManGFC.frm`, `mdl_proc.bas`
  antes de implementar; 3 decisões de design confirmadas via
  `AskUserQuestion`.
  - **Achado real do rastreio**: o legado só grava a VENDA de um Cartão
    Presente (`comanda_cartao_presente`, `situacao` nunca sai de 'A') — o
    resgate nunca foi implementado (`comanda_venda`/`id_movimentacao_venda`
    são colunas mortas, confirmado por busca exaustiva em toda a árvore
    VB6). Vale de Devolução, ao contrário, tem um ciclo de vida real e
    completo no legado — é ele que foi usado como referência de fidelidade.
  - **Vale de Devolução** (companheiro opcional de DI/DU/VA, nunca um
    "tipo" próprio): campo `codigo_vale_devolucao` em
    `CheckoutFormaPagamentoItem` — ao portador (não checa cliente da
    venda), bloqueia reuso do mesmo vale duas vezes na mesma venda, bloqueia
    vale não encontrado/já utilizado (`situacao='F'`)/cancelado
    (`situacao='C'`)/valor maior que o saldo. **Assimetria real do legado,
    replicada fielmente** (decisão do usuário, "replicar a assimetria
    exata"): só DU e VA geram um vale RESIDUAL novo (`vale_devolucao`
    clonado, mesmo cliente, `situacao='A'`, saldo = diferença) quando o
    valor lançado é menor que o saldo do vale — DI sempre consome o vale
    inteiro, nunca gera resíduo, mesmo havendo sobra. Consumo grava em
    `comanda_vale_devolucao` (tabela real do legado, só nunca usada até
    agora).
  - **Cartão Presente**: novo tipo de forma de pagamento **`CP`** (só existe
    no Checkout, sem `forma_pagamento` cadastrada — campo `forma_pag` fica
    vazio) — campo `codigo_cartao_presente` (código do cartão físico,
    `pecas_cartao_presente.cartao_presente`). Resgate **tudo ou nada** (não
    aceita usar menos que o saldo sem gerar resíduo — decisão do usuário,
    "fiel ao padrão do Vale de Devolução"), **ao portador** (decisão do
    usuário, "consistente com Vale de Devolução" — não existe conceito de
    "dono" de cartão presente no schema), bloqueia reuso do mesmo cartão
    duas vezes na mesma venda, cartão não encontrado, já resgatado
    (`situacao='F'`, reaproveitando a coluna já existente e até então morta),
    valor maior que o saldo. Quando o valor lançado é menor que o saldo, gera
    **cartão residual** — novo `pecas_cartao_presente` (código
    `"<original>-R<auto>"`) + novo `comanda_cartao_presente` (`situacao='A'`,
    saldo = diferença) — mesma mecânica do Vale de Devolução, sem a
    assimetria por tipo (Cartão Presente não tem DI/DU/VA próprios, é um
    tipo único `CP`). Consumo grava numa tabela nova,
    **`comanda_cartao_presente_resgate`** (autonum, comanda,
    comanda_cartao_presente, valor_usado — não existe no legado, espelha o
    formato de `comanda_vale_devolucao` por simetria; criada via migração
    idempotente `_ensure_cartao_presente_resgate_table`, mesmo padrão de
    `_ensure_qtd_pessoas_col`).
  - **Backend**: tudo em `checkout_service.py` — `_validar_vale_devolucao`/
    `_consumir_vale_devolucao`/`_validar_cartao_presente`/
    `_consumir_cartao_presente`, chamadas de dentro de
    `_fechar_venda_sync` (1º laço valida TODAS as formas antes de gravar
    qualquer uma — mesmo padrão já usado pra Administradora/Parcelador de
    cartão de crédito/débito; 2º laço grava, reaproveitando o resultado já
    validado, não reconsulta). `CheckoutFormaPagamentoItem` (schemas.py)
    ganhou os 2 campos novos, ambos opcionais — zero mudança pros tipos
    DI/CH/CC/CD/DU/TI/VA/FI já existentes quando não usados.
  - **20 testes novos** em `test_checkout_service.py`
    (`TestFecharVendaValeDevolucao`/`TestFecharVendaCartaoPresente` — total
    sem/com resíduo, todos os bloqueios, duplicidade na mesma venda) — 54/54
    passando no arquivo, 1515 no total (mesmos 67 pré-existentes não
    relacionados, Gestão de Compras). `tsc --noEmit` sem erro novo.
  - **Testado ao vivo, ciclo completo, contra GERDELL/BARESTELA**: abriu
    venda real (comanda 10093, cliente 90) → item real (P392, R$18) →
    semeou 1 vale de teste (R$50) + 1 cartão presente de teste (R$50) →
    fechou a venda com VA parcial (R$10 do vale) + CP parcial (R$8 do
    cartão) → confirmado: vale original `situacao='F'`, vale residual criado
    (R$40, mesmo cliente); cartão original `situacao='F'`, cartão residual
    criado (`TESTE-CP-001-R1`, R$42); `comanda_vale_devolucao`/
    `comanda_cartao_presente_resgate` gravados com o valor usado; venda
    fechada `situacao='PG'`. Todo o dado de teste foi removido ao final
    (nenhum registro pré-existente tocado).
  - **Frontend**: `FecharVendaModal.tsx` — tipo "Cartão Presente" na lista
    de tipos (troca "Forma de Pagamento" por um campo de texto "Código do
    Cartão Presente" quando selecionado, já que não tem forma cadastrada);
    campo opcional "Código do Vale de Devolução" aparece embaixo de
    qualquer linha DI/DU/VA. **Não existe (nem foi criado) um flag
    `forma_pagamento.vale_devolucao` no schema desta migração** — a coluna
    equivalente do legado nunca foi portada (ver comentário em
    `forma_pagamento_service.py`); o campo aparece pelo TIPO da linha
    (mesmo critério que o próprio backend usa), não por uma flag de
    cadastro — mais simples e já é o que a regra de negócio real exige.
    Novos itens no ícone de Ajuda do Checkout (`AJUDA_ITENS`) explicando os
    dois em linguagem de usuário final.
  - **Fora de escopo desta rodada**: nenhuma tela de consulta/relatório de
    Cartões Presentes emitidos/resgatados (só existe hoje via SQL direto);
    nenhuma tela de emissão/venda de Cartão Presente em si (pressupõe que a
    linha em `pecas_cartao_presente` já existe — de onde ela nasce
    normalmente não foi rastreado nesta rodada, só o resgate).
- **Emissão fiscal automática ao fechar** — o Checkout não emite NFC-e/NFS-e
  sozinho; reaproveita o botão já existente "Emitir NFC-e"/"Emitir NFS-e"
  do Gestor de Comandas (`comanda_service.py`) — mesma ressalva já
  registrada lá: **nunca testado contra o SEFAZ real**.
- **Impressão térmica SILENCIOSA**: já integrada (ver "Fase 3" acima e
  "Impressão Silenciosa — Fila + Agente Local" abaixo) — o mecanismo de
  fila/agente em si já foi testado ao vivo contra uma impressora física
  (máquina `GERDELL`), mas a chamada específica que o Checkout faz
  (`imprimirVendaAutomatico`, dentro de `fecharVenda`) **só foi testada
  isoladamente via curl contra o endpoint** — nunca clicado "Fechar Venda"
  de verdade na UI do Checkout pra confirmar que o cupom sai sozinho na
  impressora.
- **Ciclo completo não testado ao vivo** — abrir venda (automática) →
  adicionar item (teclado/barcode) → importar Pedido/O.S. → desconto →
  fechar com múltiplas formas → confirmar impressão automática do cupom →
  conferir no Gestor de Comandas, nunca rodado contra um banco de teste
  real (só testes unitários com cursor mockado). Este é o item que
  destrava todo o resto — sem isso, a Fase 1 (núcleo) não pode ser
  considerada "pronta de verdade".

### Ajustes de UI 2026-08-06 — revisão a partir de screenshots (PDV de referência + `FrmPafOFF.frm`)

Pedido explícito do usuário, comparando um screenshot de PDV de referência
(YZIDRO) e o próprio `FrmPafOFF.frm` legado lado a lado com a tela atual:

- **Demonstrativo do Cupom Fiscal — destaque do último item REMOVIDO**
  ("não exibir o último produto em destaque para a lista de produto ficar
  maior"). O bloco `destaque`/`destaqueVazio` (fonte grande do último item
  lançado) foi tirado por completo de `DemonstrativoCupomFiscal.tsx` — a
  grade de itens ganhou o espaço de volta.
- **Lista de itens — tamanho FIXO com barra de rolagem** ("quero a lista
  com tamanho fixo com barra de rolagem"). `gridBody` trocou de
  `maxHeight: 260` pra `height: 440` (fixo) — antes já usava `ScrollView`
  internamente, só a altura era um teto variável, não um tamanho fixo.
- **Campo Vendedor, que faltava em "Registro de Itens"** ("em registro de
  venda, faltou o vendedor" — rastreado no screenshot do `FrmPafOFF.frm`,
  combobox "Vendedor: CARLOS" acima do campo Código). Novo `SelectField`
  "Vendedor" (`itemVendedor`, estado próprio) acima do campo de código em
  `checkout.tsx` — sai preenchido com o próprio atendente (sessão), mas o
  operador pode trocar por qualquer outro funcionário
  (`GET /api/funcionarios`, mesmo padrão de `pedido-form.tsx`). Esse valor
  é o que vai em `vendedor` no `POST /checkout/{comanda}/itens` e nos
  imports de Abastecimento/Agenda — **antes desta mudança, todo item era
  sempre gravado com o vendedor = sessão logada**, sem opção de trocar.
- **Atendente do caixa (usuário logado) na barra de título** ("informar o
  atendente do caixa (usuário logado), na barra de título, que pode ser
  diferente do vendedor"). Badge translúcido no `titleExtra` do
  `PedidoHeader` ("Atendente: NOME") — nome vem direto da sessão
  (`funcionario.nome_guerra`/`nome`, disponível de imediato, sem esperar
  round-trip de rede), não mais do card no corpo da tela (removido — o
  card "Cliente" ficou sozinho onde antes tinha Atendente+Cliente juntos).
  Estado `atendenteNome` (resolvido via `_get_venda_sync`, só usado nesse
  card) removido por ficar órfão — a impressão automática do cupom
  continua lendo `atendente_nome` direto da API, sem depender desse
  estado.
- **Botão "Pedidos" separado de "O.S.", cada um já abre uma LISTA** ("Botão
  de Pedidos separado da O.S. Ao clicar, listar as pré-venda sem precisar
  procurar, conforme no legado"). O único botão "Importar Pedido/O.S."
  (que abria um modal pra DIGITAR o número do documento —
  `ImportarDavModal.tsx`, agora deletado por ficar órfão) virou 2 botões
  independentes na barra de ações: "Pedidos" e "O.S.", cada um abrindo o
  novo `DavPendentesModal.tsx` (parametrizado por `tipoDav`) já
  preenchido com a lista de documentos Fechados prontos pra importar —
  mesmo padrão visual de `AbastecimentoModal.tsx`/`AgendamentoModal.tsx`
  (lista + toque direto, sem etapa de busca). Endpoint novo
  `GET /checkout/dav/pendentes?tipo_dav=PED|OS`
  (`_list_dav_pendentes_sync`, `checkout_service.py`) — mesmo critério de
  elegibilidade já usado por `_importar_dav_sync` (`situacao='F'`), só
  como listagem em vez de busca por número; a validação real de novo
  continua acontecendo no import (nada muda em `_importar_dav_sync`). 3
  testes novos (`TestListDavPendentes`). **Testado ao vivo contra
  GERDELL/BARESTELA**: `GET /checkout/dav/pendentes?tipo_dav=PED` retornou
  4 Pedidos Fechados reais, `tipo_dav=OS` retornou 1 O.S. Fechada real —
  ambos com dados corretos (cliente, valor, data).
- **Campo Produto/Serviço ganhou mecanismo de busca** (pedido explícito do
  usuário, mid-turn: "tem que possibilitar consulta no campo produto/
  serviço" — regra `[GLOBAL]` "Campos de identidade precisam de mecanismo
  de busca", que já cobria Cliente/Fornecedor/Nível mas não tinha sido
  aplicada ainda no campo de código do Checkout, pensado originalmente só
  pra bipe/digitação direta). Ícone de lupa (`IconButtonWithTooltip`) ao
  lado do campo Código abre `ProdutoSearchModal` (componente já existente,
  reaproveitado sem duplicar — mesmo usado em Produto Completo pra
  Similares/Secundários), buscando em `GET /api/produtos-servicos` com
  `tipo` respeitando o módulo Serviços ativo (`moduleOn("servicos") ?
  "all" : "P"`, mesmo critério já usado em `usePedidoItens.ts`). Ao
  escolher um resultado, o código é preenchido e o preview é buscado na
  hora — o fluxo de bipe/digitação com Enter continua idêntico, a busca é
  só um caminho alternativo pra quem não sabe o código de cor.
- **Layout confirmado ao vivo pelo usuário (2026-08-06, print da Venda
  #17838)**: badge "Atendente: CARLOS" no título, combobox Vendedor
  ("CARLOS · #2 · CARLOS ALBERTO"), lupa no campo Produto/Serviço, botões
  "Pedidos"/"O.S." separados, lista do Demonstrativo em altura fixa sem o
  destaque do último item — tudo renderizando certinho. **Isso confirma só
  o LAYOUT/render** — clicar de fato em "Pedidos"/"O.S." pra importar um
  documento da lista, trocar o Vendedor e conferir que grava certo no
  item, e usar a lupa de Produto/Serviço pra adicionar um item ainda não
  foram clicados/exercidos ao vivo. Continua fazendo parte do "ciclo
  completo nunca testado ao vivo" registrado no bullet acima pra esses
  fluxos de ação (só a tela renderizada e a listagem de Pedidos/O.S.
  pendentes, via chamada direta ao service, foram de fato confirmadas).

### Checagem de Taxa (taxas_nfce) ao adicionar item — implementada 2026-08-06

Pedido explícito do usuário: "buscar e implantar na tela de vendas, a
rotina que verifica se existe a taxa no momento de adicionar um item" —
rastreado ao vivo via agente de pesquisa (`FrmPafOFF.frm`), com o usuário
corrigindo/direcionando a investigação em tempo real (localização exata:
`Campo_Validate` → `RetornaDadosProduto`, não `FinalizaVenda` como
inicialmente apontado).

- **Tabela real usada: `taxas_nfce`** (não `Taxas` — essa outra só alimenta
  um percentual exibido, nunca bloqueia no legado). Query fiel ao legado:
  `SELECT TOP 1 1 FROM taxas_nfce WHERE Destino=<controle.uf> AND
  Cod_Icms=<produto/serviço.cod_icms> AND Tipo_Mov='S01'` — `Destino` é a
  UF do PRÓPRIO estabelecimento (não do cliente da venda).
- **Mensagem de bloqueio** adaptada do literal do legado ("Operação não
  Cadastrada na Tabela de Taxas ou Indisponível no ECF !"), removendo a
  referência a "ECF" (impressora fiscal antiga, não existe nesta
  arquitetura): "Esta operação não está cadastrada na Tabela de Taxas
  (NFCe) para este produto/serviço e UF."
- **Gating por `controle.emite_nf_comanda` — decisão explícita do usuário,
  DIVERGE do legado de propósito**: no VB6 essa checagem roda SEMPRE,
  incondicionalmente (confirmado: nenhuma leitura de `emite_nf_comanda`/
  `IMPRIME_NFCE_NAO_FISCAL` dentro de `RetornaDadosProduto`/
  `Campo_Validate` — bloqueia até empresa configurada como não-fiscal, uma
  inconsistência real do legado). Perguntado via `AskUserQuestion`: usuário
  escolheu **não replicar essa inconsistência** — só bloqueia quando
  `controle.emite_nf_comanda=true`.
- **Achado à parte, não portado**: a verificação equivalente na EMISSÃO de
  NF (`GeraNFe`/`DAO_NFE.vb`) é mais fraca e diferente — um JOIN silencioso
  só por `cod_icms` (sem `Destino`/`Tipo_Mov`), que omite o item do XML sem
  nenhum aviso ao usuário quando não bate. Não implementado (fora do
  pedido desta rodada, que era só o momento de adicionar item).
- **Gambiarra client-specific identificada e descartada**: `controle.CGC =
  "31184997000100"` hardcoded dentro de `FinalizaVenda` — decide só se o
  comprovante impresso inclui referência a Pedido/O.S. vinculado; **sem
  relação com a checagem de Taxa**, não portado (customização de uma
  instalação específica, não regra geral).
- **Implementação**: `cod_icms` adicionado ao retorno de
  `_resolve_produto_completo`/`_linha_peca_completo` (`pedido_common.py`,
  função compartilhada com Pedido Completo — mudança aditiva, não afeta o
  outro consumidor). Nova função `_verifica_taxa_nfce` +
  chamada em `_add_item_sync`, logo após resolver o produto/serviço
  (`checkout_service.py`). 4 testes novos (`TestAddItemTaxaNfce`) — 61/61
  no arquivo, 1534 no total (mesmos 67 pré-existentes não relacionados).
- **Testado ao vivo contra GERDELL/BARESTELA** (`controle.emite_nf_comanda
  =true`, `controle.uf='RJ'`, `taxas_nfce` só tem linhas pra `cod_icms`
  '0'/'6'): produto com `cod_icms='0'` (tem taxa) → incluído com sucesso;
  serviço com `cod_icms='999'` (todos os serviços deste banco, sem
  nenhuma linha correspondente em `taxas_nfce`) → bloqueado corretamente
  com a mensagem amigável. Dado de teste removido ao final.
- **Achado colateral, não é bug desta feature**: com esta checagem ativa,
  **nenhum serviço pode ser vendido em GERDELL/BARESTELA** enquanto não
  houver uma linha em `taxas_nfce` para `cod_icms='999'`/`Tipo_Mov='S01'`/
  `Destino='RJ'` — a tabela nunca foi populada pra esse código nesta
  conexão de teste. Isso é esperado (a checagem está fazendo exatamente o
  que devia), mas vale avisar antes de testar Serviços nessa conexão.

### Referência de Pedido/O.S. no comprovante impresso — implementado 2026-08-06

Achado de passagem enquanto rastreava a checagem de Taxa acima (mesma
função `FinalizaVenda`, linhas vizinhas) — o usuário confirmou que, apesar
de ser uma gambiarra client-specific (não relacionada à Taxa), ela
**precisa ser implantada** também, fielmente (inclusive a exceção).

- **Regra geral** (`FrmPafOFF.frm::FinalizaVenda`, linhas 10750-10775):
  ao montar o texto complementar do comprovante, se a venda tem Pedido(s)
  de Venda e/ou O.S. importados (`COMANDA_PED`/`COMANDA_os`), acrescenta
  uma linha por documento: `"Pedido de Venda <n>"` / `"Ordem de serviço
  <n>"`.
- **Exceção fiel ao legado**: `controle.CGC = "31184997000100"` (CNPJ do
  PRÓPRIO estabelecimento, não de cliente) suprime essas linhas por
  completo — é uma customização de uma instalação específica, mas o
  usuário pediu pra replicar exatamente assim (não é regra geral, é
  exceção hardcoded mesmo).
- **Implementação**: `frontend/src/utils/reciboTexto.ts` —
  `CGC_SEM_REFERENCIA_PEDIDO_OS` (constante com o CNPJ, comparado após
  normalizar pontuação de `empresa.cgc`), novos campos opcionais
  `pedidosImportados`/`osImportadas` em `ReciboTextoDados`, linhas
  adicionadas logo após Atendente/Data (mesma posição relativa do
  legado), antes das mensagens complementares genéricas.
  `frontend/app/checkout.tsx`'s `imprimirVendaAutomatico` já buscava
  `pedidos_importados`/`os_importadas` de `GET /checkout/{comanda}` (dado
  já exposto desde a Fase 2, usado pros badges do Demonstrativo) — só
  precisou repassar pro `buildReciboTexto`, nenhum endpoint novo.
- **Verificado por execução direta da função** (Node + Babel, fora do
  bundler) com dado simulado — confirmado que a exceção do CNPJ
  suprime as linhas e que qualquer outro CNPJ as inclui corretamente.
  **Não testado ainda contra uma impressora física de verdade** (fluxo de
  impressão automática em si já testado antes, essa parte específica não).

---

## Impressão Silenciosa — Fila + Agente Local

**Status: 🟢 Backend + agente implementados e TESTADOS AO VIVO 2026-08-05
(2 cupons de teste impressos de verdade, sem diálogo, numa impressora
térmica USB real) + início automático instalado na máquina `GERDELL`.
NENHUMA tela do app integrada ainda (ver bullet próprio abaixo).**

Pedido do usuário (durante o trabalho de Checkout Fase 3, impressão de
cupom): *"implemente o Polling em python. assim que tiver pronto vamos
testar."* — motivado por explicar antes, em detalhe, a arquitetura de
"agente local" como solução pra impressão silenciosa (sem diálogo do
navegador) de impressoras térmicas conectadas por **USB local** numa
máquina Windows (impressoras de **rede** já são resolvidas sem agente
nenhum, ver `enviar_rede` abaixo).

- **Backend** (`backend/services/impressao_service.py`, estendido — já
  tinha `enviar_rede`/`_enviar_rede_sync` de uma rodada anterior, socket
  TCP cru pra impressoras de rede na porta 9100/RAW-JetDirect):
  - Tabela nova `impressao_fila` (migração idempotente
    `_ensure_impressao_fila_table`, mesmo padrão `IF NOT EXISTS (SELECT 1
    FROM sys.tables ...)` já usado em outras tabelas novas do projeto) —
    `computador`, `impressora` (opcional), `tipo`, `conteudo`, `status`
    (`PENDENTE` → `ENVIADO` → `IMPRESSO`/`ERRO`), `mensagem_erro`,
    `data_criacao`/`data_envio`/`data_conclusao`.
  - `_enfileirar_sync`/`enfileirar`: valida `computador`/`conteudo` não
    vazios, insere e retorna o `id` do job.
  - `_list_pendentes_sync`/`list_pendentes`: retorna jobs `PENDENTE` (ou
    `ENVIADO` há mais de `RECUPERACAO_ENVIADO_MINUTOS`=2 minutos sem
    confirmação — recuperação de agente que caiu no meio do processamento
    de um job e nunca chamou `/confirmar`), e já marca os IDs retornados
    como `ENVIADO` na mesma chamada (evita 2 agentes pegarem o mesmo job
    num polling concorrente).
  - `_confirmar_sync`/`confirmar`: marca `IMPRESSO`/`ERRO` +
    `mensagem_erro`, bloqueia com "Job não encontrado." se o `id` não
    existir (`rowcount==0`).
  - 11 testes unitários novos em `backend/tests/unit/test_impressao_service.py`
    (`TestEnfileirar`/`TestListPendentes`/`TestConfirmar`), mesmo padrão
    `FakeCursor`/`FakeConn` já usado em `test_checkout_service.py`.
- **Rotas** (`backend/routes/impressao.py`, estendido):
  `POST /api/impressao/fila` (enfileirar — qualquer tela chama),
  `GET /api/impressao/fila/pendentes?servidor=&banco=&computador=`
  (só o agente chama), `POST /api/impressao/fila/{id}/confirmar` (só o
  agente chama). Sem gate de permissão dedicado — mesmo padrão já usado em
  `POST /impressao/rede` (endpoint de infraestrutura, não uma tela de
  cadastro); log de auditoria (`tela="IMPRESSAO"`, best-effort, nunca
  bloqueia a operação) só no `enfileirar`.
- **Agente Python standalone** (`print-agent/`, fora de `backend/` — roda
  numa máquina Windows cliente, não no servidor):
  `agente_impressao.py` (loop de polling configurável via `config.json` —
  `api_base`/`servidor`/`banco`/`computador`/`impressora_padrao`/
  `intervalo_segundos`; usa `win32print` em modo `RAW` pra mandar os bytes
  direto pro spooler, sem diálogo; `cp850` como codepage, mesma escolha já
  feita em `enviar_rede`), `config.exemplo.json` (template, `config.json`
  real fica fora do git — `.gitignore` atualizado), `testar_enfileirar.py`
  (enfileira um cupom de teste sem precisar de nenhuma tela do app),
  `requirements.txt` (`requests`+`pywin32`), `README.md`+`INSTALACAO.md`
  (instruções de instalação/uso/erros comuns).
- **Início automático instalado** (`print-agent/scripts/`,
  `start-print-agent.ps1`+`install-startup-task.ps1` — mesmo padrão
  já usado pelo backend em `backend/scripts/`): tarefa agendada
  `BackOn-PrintAgent` (SYSTEM, `AtStartup`, restart automático em caso de
  queda, mesmos parâmetros de `RestartCount`/`RestartInterval` do backend)
  registrada na máquina `GERDELL` (a mesma máquina do backend/banco de
  teste nesta rodada). `start-print-agent.ps1` é um supervisor com log
  diário (`print-agent/logs/agent-AAAAMMDD.log`) que reinicia
  `agente_impressao.py` se ele cair — mesma razão/estrutura do supervisor
  do backend (`start-backend.ps1`).
- **Testado ao vivo nesta máquina (2026-08-05)**: `config.json` real
  (`servidor=GERDELL`, `banco=BARESTELA`, `computador=GERDELL`,
  `impressora_padrao="EPSON TM-T(203dpi) Receipt6"`) — 2 cupons de teste
  (`testar_enfileirar.py`) enfileirados e confirmados `IMPRESSO` na tabela
  `impressao_fila`, um deles já através da tarefa agendada rodando (não só
  execução manual). `pywin32` funcionou sem precisar de passo extra de
  pós-instalação (`pywin32_postinstall.py`) neste ambiente.
- **Observação não investigada a fundo**: tanto o processo do backend
  quanto o do agente aparecem como um par pai/filho de 2 processos Python
  com a mesma linha de comando (`Get-CimInstance Win32_Process`) nesta
  máquina — não é uma duplicação real (só uma porta/único job efetivo
  fazendo o trabalho, confirmado pelo `netstat`/pelo teste de impressão
  não sair em dobro), possivelmente um comportamento do ambiente Windows
  desta máquina na forma como lança o processo filho. Não bloqueia nada,
  só registrado caso reapareça de forma diferente no futuro.
- **Checkout já integrado com a fila (2026-08-05)** — pergunta em aberto
  resolvida via `AskUserQuestion`, depois **confirmada explicitamente pelo
  usuário**: reaproveitar `direcionamento_impressora` (Controle do Sistema)
  foi descartado — "no checkout não pode ser chaveado por tipo/finalidade
  de produto. A impressão é da comanda inteira de produtos e serviços" —
  aquele cadastro é por Tipo/Finalidade (pensado pra imprimir 1 item de
  cada vez, por Finalidade, no Pedido Bar), o Checkout sempre imprime a
  comanda inteira (todos os produtos/serviços do documento) de uma vez, o
  que já era exatamente como `buildReciboTexto`/`_get_venda_sync` foram
  implementados (nenhuma mudança de código precisou ser feita por essa
  parte — só confirma que a decisão original estava certa).
  Escolhido em vez disso: **configuração local por estação**, salva no
  navegador (não no banco) — `frontend/src/utils/storage/
  impressaoSilenciosa.ts` (mesmo padrão de `pedidosFilters.ts`, chaveado por
  empresa+banco), configurável via ícone "⚙ Configurar Impressão" novo no
  cabeçalho (`frontend/src/components/checkout/ConfiguracaoImpressaoModal.tsx`
  — 2 campos, Computador+Impressora). Novo prop `onPrintConfig` em
  `PedidoHeader.tsx` (mesmo padrão de `onAnexos`/`onHelp`).
  **Correção no mesmo dia, user-directed — não existe botão "Imprimir"**
  ("não tem botão imprimir. tudo será de forma silenciosa no final do
  processo de venda. assim como acontece no legado"): removido por
  completo o botão manual, o estado `reciboOpen` e
  `frontend/src/components/checkout/ReciboCheckoutModal.tsx` inteiro
  (arquivo deletado — órfão depois da remoção, nenhum outro consumidor).
  Impressão agora é **automática**, disparada dentro de `fecharVenda`
  logo após `POST /checkout/{comanda}/fechar` ter sucesso — mesma réplica
  do comportamento do legado (`Imprime_Comprovante` era chamada direto ao
  fechar a venda no VB6, sem botão dedicado). Nova função
  `imprimirVendaAutomatico(cmd)` em `checkout.tsx`: busca o estado FINAL da
  venda direto da API (`GET /checkout/{cmd}`, não o state local — que
  ainda não refletiu o resultado do fechar no mesmo tick de React),
  monta o texto via `buildReciboTexto` e chama `POST /impressao/fila`
  **só se a estação tiver Computador+Impressora configurados**; sem
  configuração, não tenta imprimir (não existe mais fallback de diálogo do
  navegador — não faria sentido um diálogo abrir "automaticamente" sem
  gesto do usuário) e devolve um aviso claro. O resultado (sucesso, falha,
  ou "não configurado") é concatenado num ÚNICO toast junto com "Venda
  fechada!"/troco, com `durationMs=5000` (regra `[GLOBAL]` de mensagem
  grande/importante — carrega texto novo, merece mais tempo de leitura).
  Conteúdo do cupom em texto puro (não HTML) gerado por
  `frontend/src/utils/reciboTexto.ts` (`buildReciboTexto`, 42 colunas,
  reaproveitável por outras telas). Testado ao vivo contra
  `/api/impressao/fila` (smoke test via curl) — o fluxo completo
  telinha→fila→agente→impressora física já foi validado antes disso na
  seção acima, só a chamada nova do Checkout que foi testada isoladamente
  (nunca clicado "Fechar Venda" de verdade na UI pra disparar o print
  automático).
  **Acesso à configuração restrito aos "3 Magníficos"** (pedido explícito
  do usuário, mesmo dia): o ícone "⚙" só aparece pra quem tem
  `isManagerFuncao` (Gerente/Supervisor `cod_funcao` 01/02, ou Master —
  mesmo helper já usado em `pedidos.tsx`/`usuarios_service.py` pra "ver
  todos os vendedores"/gestão de usuários, reaproveitado aqui sem criar
  critério novo). Restrição é só de QUEM PODE ABRIR/MUDAR a configuração —
  uma vez configurada por um gerente naquela estação, o botão "Imprimir"
  continua enfileirando direto pra QUALQUER operador que usar a máquina
  depois (a config é da estação, não do usuário logado).
  **Modo Didático aplicado de passagem** (pedido explícito do usuário no
  mesmo momento): tooltips adicionados aos 2 ícones-sozinhos que ainda não
  tinham (buscar cliente, cancelar item — via `IconButtonWithTooltip`,
  substituindo `Pressable` cru) e `AJUDA_ITENS` ganhou entrada explicando
  "Configurar Impressão".
- **Ciclo completo já testado ao vivo nesta máquina** (ver bullets acima)
  — falta testar em uma SEGUNDA máquina diferente da do backend (validar
  `api_base` apontando pra IP de rede em vez de `localhost`) e testar a
  sobrevivência a reboot de verdade (a tarefa foi só iniciada manualmente
  via `Start-ScheduledTask`, nunca validada num boot real do Windows).
- **Não substitui nem quebra `enviar_rede`** — impressoras de rede
  continuam usando o caminho direto (backend → socket, sem fila, sem
  agente); a fila é só para USB-local.

---

## Modificadores

**Status: 🟡 Fase 1 (cadastro) implementada e testada ao vivo (2026-07-23)**
— cadastro genuinamente novo, **sem equivalente no legado VB6** ("não
possui tabela", pedido explícito do usuário). Uma Categoria de Modificador
(ex.: "Ponto da Carne") agrupa vários Modificadores (ex.: "Mal passado"),
associável a Produto e/ou Serviço, pra abrir um seletor na hora da venda
quando o item incluído tiver modificador associado — **Fase 2 (seleção na
venda) implementada só no Pedido Bar**, ver subseção própria mais abaixo.

### Módulo gateado por "Bar" (2026-07-23, user-directed)

**"colocar o modificador ligado ao módulo de Pedido Bar. Só aparecerá para
esse módulo ativo em configurações"** — todo o módulo Modificadores (não só
a Fase 2) só funciona/aparece com `controle_configuracao.Bar` ligado, mesmo
mecanismo já usado por `servicos`/`contratos`/`Curva_abc` ("Regra de Módulo
Ativo — Gating por Entidade (Backend)" em CLAUDE.md):

- **Backend**: `pedido_common._modulo_bar_ativo(cur)` (mesmo padrão de
  `_modulo_contratos_ativo`), checado no topo de TODAS as 7 funções `_*_sync`
  de `modificadores_service.py` (list/get/save/delete categoria, list/get
  completo por-item, associar por-item) — bloqueia com
  `"Módulo Bar está desativado — fale com o administrador em Configurações >
  Módulos e Recursos."`. 7 testes novos em `TestModuloBarGating`
  (`test_modificadores_service.py`), helper `_patch` do arquivo ganhou
  parâmetro `modulo_bar_ativo` (default `True`, pra não precisar tocar nos
  outros 14 testes já existentes).
- **Catálogo de permissões**: `MODIFICADORES` adicionado a
  `controle_config_service.MODULE_TELAS["Bar"]` (`["PEDIDO", "MODIFICADORES"]`)
  — a tela some da árvore de Permissões (e `can("MODIFICADORES.*")` passa a
  retornar `False` via `disabled_telas`) junto com "Pedido Bar" quando o
  módulo é desligado.
- **Frontend**: `app/modificadores.tsx` ganhou o guard
  `if (!moduleOn("Bar")) return <LockedView .../>` (mesmo padrão de
  `contrato-tipo.tsx` etc.); tile em `tabelas-auxiliares.tsx` ganhou
  `moduleOn("Bar") &&` na condição `visible`; a aba "Modificadores" em
  `produto-completo.tsx`/`servicos.tsx` só entra no array `TABS`/passa no
  filtro quando `moduleOn("Bar")` também é verdadeiro (além da regra já
  existente de precisar do registro salvo).
- **Não gateado de novo** (já implícito): o seletor de modificador dentro
  de `AddItemModal.tsx` (Fase 2) só ativa com `tela === "PEDIDO"`, que por
  si só só é alcançável com o módulo Bar ligado (mesma amarração
  `MODULE_TELAS["Bar"] = ["PEDIDO", ...]`) — nenhum check redundante de
  `moduleOn("Bar")` foi adicionado lá.

### Escopo confirmado com o usuário (via AskUserQuestion, 2026-07-23)

1. **Onde a seleção aparece na venda** (Fase 2, futura): Pedido Bar +
   Pedido Geral + O.S., todos os pontos de inclusão de item de pré-venda.
2. **Acréscimo/Desconto do modificador**: valor FIXO em R$, não percentual.
3. **Campos do modificador**: só Nome + Acréscimo + Desconto + Situação
   (Ativo/Desativado) — sem Custo/SKU/ícone de visibilidade (esses
   apareciam nas telas de referência anexadas pelo usuário, de um sistema
   de terceiros usado só como inspiração visual, não como especificação a
   replicar literalmente).
4. **Faseamento**: Fase 1 = só cadastro (Categorias + Modificadores +
   associação com Produto/Serviço, nos 2 sentidos). Fase 2 = integração
   com a tela de venda, ainda não iniciada.

### Modelo de dados (3 tabelas novas, migração idempotente)

- `modificador_categoria` (codigo IDENTITY, nome, `obrigatorio` BIT,
  `selecao_multipla` BIT — "Apenas um"/"Vários").
- `modificador` (codigo IDENTITY, `categoria` FK, nome, acrescimo
  NUMERIC(15,2), desconto NUMERIC(15,2), situacao 'A'/'D').
- `modificador_categoria_item` — associação N:N, com `tipo` ('P'=Produto/
  'S'=Serviço) + `codigo` — **discriminador necessário porque Produto
  (`pecas.codigo_int`) e Serviço (`servicos.codigo`) são tabelas
  DIFERENTES neste sistema** (confirmado em `servicos_service.py` — Serviço
  não é uma linha de `pecas`, tabela própria).

### Backend

`backend/models/modificadores.py` + `backend/services/
modificadores_service.py` (CRUD de categoria com replace-all pros
modificadores e associações filhas, mesmo padrão já usado pra telefones/
endereços/contatos do Cliente) + `backend/routes/modificadores.py`
(registrado em `server.py`). Endpoints:
- `GET/POST /api/modificadores/categorias`, `GET/DELETE /api/modificadores/
  categorias/{codigo}` — CRUD principal.
- `GET/POST /api/modificadores/por-item/{tipo}/{codigo}` — associação "pelo
  outro lado" (a partir de Produto Completo/Serviços), reaproveitada pelo
  retrofit no frontend.
- Busca de produto/serviço pro modal de associação reaproveita o endpoint
  JÁ EXISTENTE `GET /api/produtos-servicos` (não foi criado um endpoint de
  busca novo — DRY).

Permissão nova `MODIFICADORES` (Cadastros > Tabelas Auxiliares,
ABRIR/GRAVAR/EXCLUIR padrão). Log de auditoria em Gravar/Excluir da tela
principal (tela=MODIFICADORES). O retrofit em Produto Completo/Serviços
(endpoint `por-item`) não loga auditoria própria ainda — decisão de
escopo pra não alongar mais esta rodada, considerar se fizer sentido
depois.

**Exclusão em cascata sem bloqueio**: como a Fase 2 (venda) não existe
ainda, nenhum pedido/item pode referenciar um modificador hoje — excluir
uma categoria apaga modificadores + associações em cascata livremente.
**Quando a Fase 2 for implementada, isso precisa passar a bloquear** (ou
pelo menos avisar) se houver histórico de uso, mesmo princípio de "Delete
guards required" já usado no resto do sistema.

### Frontend

- `frontend/app/modificadores.tsx` — tela principal (lista de categorias +
  modal de edição com modificadores aninhados + modal de associação de
  Produto/Serviço, busca reaproveitando `/api/produtos-servicos`). Tile
  novo em Tabelas Auxiliares (`tabelas-auxiliares.tsx`).
- `frontend/src/components/ModificadoresSection.tsx` — componente
  compartilhado (mesmo espírito de `GestorDocumentosSection.tsx`) pro
  retrofit "associação pelo outro lado". **Correção 2026-07-23, user-
  directed** ("colocar o botão dos modificadores"): não fica mais dentro
  da aba Anexos — ganhou aba PRÓPRIA ("Modificadores", ícone
  `options-outline`, mesmo ícone do tile em Tabelas Auxiliares) tanto em
  `produto-completo.tsx` quanto em `servicos.tsx`, mesmo padrão de
  "Anexos" já ser uma aba de verdade nessas 2 telas — a aba em si já é o
  "botão" que o usuário pediu. Trava até o registro ser salvo pelo menos
  uma vez (mesma regra "relacionados travados até o pai existir"); em
  Serviços a aba nem aparece na lista antes disso (mesmo filtro já usado
  pra Anexos), em Produto Completo a aba aparece mas mostra "Grave o
  produto para vincular modificadores." até lá. Não duplica a lógica de
  associação entre as 2 telas.
- **Botão "Adicionar" (2026-07-23, user-directed)**: ao lado de
  "Gerenciar", pra criar uma categoria de modificador nova SEM sair pra
  Tabelas Auxiliares ("assim não precisamos abrir o cadastro do modificador
  em tabelas auxiliares toda vez que precisarmos incluir um novo"). O modal
  de edição de categoria foi extraído de `app/modificadores.tsx` pro
  componente compartilhado `frontend/src/components/
  ModificadorCategoriaModal.tsx` (props `api/servidor/banco` + `codigo`
  nulo=nova — mesmo padrão de props de `ModificadoresSection.tsx`, usa
  `fetch()` cru, não `apiGet`/`apiSend`) — reaproveitado tanto pela tela
  principal quanto por este botão novo, evita duplicar ~250 linhas de
  formulário. Ao gravar, a categoria nova já é automaticamente associada
  ao produto/serviço atual (`handleNovaCategoriaSaved` chama o mesmo
  endpoint `por-item` que "Gerenciar" usa, com a lista de associadas +1).
  **Gated pela permissão `MODIFICADORES.GRAVAR`** (não a permissão do
  produto/serviço que gate "Gerenciar") — pedido explícito do usuário
  ("Use a mesma permissão do Modificador atual para liberar o incluir").
- Testado ao vivo contra `GERDELL`/`BARESTELA`: criar categoria com 2
  modificadores + 1 produto associado → listar → editar (3 modificadores,
  muda pra "Vários") → replace-all confirmado (códigos novos) → consultar
  pelo lado do produto (`por-item`) → excluir categoria → cascata
  confirmada (modificadores e associações removidos junto) → log de
  auditoria confirmado nas 3 operações (Cadastro/Alteração/Exclusão). 13
  testes unitários (mockados) — todos passando.
- **Não testado ao vivo num navegador de verdade** (mesma limitação já
  documentada noutros módulos desta sessão — sem ferramenta de automação
  de browser neste ambiente); só validado via `curl` direto contra a API.

### Fase 2 (venda) — implementada SÓ no Pedido Bar (2026-07-23)

**Status: 🟢 Pedido Bar implementado e com testes de backend passando.
Pedido Geral e O.S. AINDA NÃO — pedido explícito do usuário: "faça somente
em Pedidos Bar. Depois faremos nas outras pré-venda".** Não presumir esse
próximo passo sozinho quando retomar — só estender pras outras telas
quando o usuário pedir.

Layout NÃO seguiu literalmente as capturas de tela do app de delivery de
terceiros que o usuário tinha anexado como referência visual (sem "badge
verde Concluído"/progresso) — foi construído no mesmo estilo visual já
usado no resto do sistema (cards com borda, badge Obrigatório/Opcional,
checkbox ou radio conforme "Vários"/"Apenas um"), mais simples que a
referência.

Respostas às perguntas que estavam em aberto (decididas durante a
implementação, sem precisar perguntar de novo — julgamento de engenharia
dentro do escopo já confirmado):
- **Momento em que o seletor abre**: dentro da própria tela "Confirmar
  Item" de `AddItemModal.tsx` (depois de escolher o produto, antes de
  Adicionar) — não é uma tela/modal separada. O botão "+" de adição rápida
  (sem passar por "Confirmar Item") é interceptado: se o produto tem
  categoria de modificador associada, vira um `pickProduto` normal em vez
  de adicionar direto, forçando a passagem pela seleção.
- **Obrigatório sem seleção**: bloqueia a inclusão — `handleConfirmar`
  computa `categoriasObrigatoriasFaltando` e mostra
  `fb.showError("Selecione uma opção em: ...")` sem chamar
  `it.handleAddItem`. A categoria com pendência também mostra um aviso
  inline ("Selecione uma opção.") no próprio card.
- **Onde o acréscimo/desconto entra**: ajusta o preço unitário do item
  principal (mesmo mecanismo de Desc./Acrésc. já existentes em
  `AddItemModal.tsx`), **não** vira uma linha própria no pedido — somado
  em cima do que o usuário já digitou manualmente nesses campos
  (`usePedidoItens.handleAddItem` ganhou um parâmetro opcional `extra:
  {acrescimoExtra, descontoExtra, complementoExtra}`, que o `usePedidoItens`
  soma ao valor manual antes de mandar pro backend — nenhum endpoint novo
  de item foi necessário, `POST /api/pedidos/{id}/itens` já aceita
  desconto/acrescimo).
- **Modificador Desativado**: desaparece — o backend já filtra
  `situacao='A'` no novo endpoint (ver abaixo), nunca chega no frontend.

**Backend**: novo endpoint `GET /api/modificadores/por-item/{tipo}/{codigo}/
completo` (`modificadores_service.get_modificadores_completo_por_item` →
`_get_modificadores_completo_por_item_sync`) — diferente do `por-item` já
existente (que só devolve `{codigo,nome}`, usado pelo retrofit em Produto
Completo/Serviços), este devolve as categorias com `obrigatorio`/
`selecao_multipla` e os modificadores aninhados (nome/acrescimo/desconto),
só os com `situacao='A'`. 1 teste unitário novo cobrindo isso (14 no total
no arquivo agora).

**Frontend**: tudo em `frontend/src/components/pedido/AddItemModal.tsx` +
um parâmetro novo em `usePedidoItens.ts`'s `handleAddItem` — **gated por
`tela === "PEDIDO"`** (`modificadoresOn`), então Pedido Geral
(`tela="PEDIDO_COMP"`) e O.S. (que nem usa este componente, ver abaixo)
ficam com o comportamento de antes, sem nenhuma chamada extra à API. Ao
selecionar um produto (`selProd` muda), busca as categorias associadas;
card por categoria com badge Obrigatório/Opcional + Vários, checkbox
(Vários) ou radio (Apenas um) por modificador, valor +/- ao lado de cada
um. O preview de preço ("Preço líquido unit."/"Total do item") já soma os
modificadores selecionados ANTES de confirmar. Nomes dos modificadores
selecionados são concatenados (", ") e anexados ao Complemento do item
(`" | "` como separador se o usuário também digitou algo à mão) — é isso
que sai impresso como "Obs" no ticket do item do Bar
(`ReciboPedidoModal.tsx` já lê `item.complemento`, nenhuma mudança
necessária lá).

**`PainelPedidoCard.tsx`'s botão "+ Item" — gap fechado no mesmo dia
(2026-07-23)**: reportado ao vivo pelo usuário (produto "PICANHA NA PEDRA
REFEIÇÃO" com modificadores associados, adicionado via "+" do card, pulava
direto pra impressão do item sem perguntar o modificador). Confirmado via
`AskUserQuestion` que o usuário queria a mesma regra aplicada aqui também.
Implementado replicando (não compartilhando) o padrão de `AddItemModal.tsx`
— mesmo princípio arquitetural já usado neste card (CLAUDE.md > "Painel de
Pedidos": evitar instanciar hook/componente maior por card):
- `iniciarAddProduto(p)` substitui a chamada direta a `quickAddItem` no "+"
  da lista de busca — chama `buscarModificadoresProduto` (mesmo endpoint
  `GET /api/modificadores/por-item/{tipo}/{codigo}/completo`); sem
  categoria associada, comportamento idêntico a antes (`quickAddItem`
  direto); com categoria, abre uma tela de confirmação DENTRO do mesmo
  modal "Adicionar item" (não é um modal novo) com os cards de
  categoria/modificador (checkbox/radio, badge Obrigatório/Opcional —
  mesmo visual de `AddItemModal.tsx`, `modStyles` duplicado, não
  exportado/compartilhado).
- `handleConfirmarModificadores` valida `categoriasObrigatoriasFaltando`
  antes de confirmar (mesmo bloqueio de `AddItemModal.tsx`), soma
  acréscimo/desconto dos modificadores selecionados e concatena os nomes
  no `complemento`.
- `quickAddItem` ganhou parâmetro opcional `extra: {acrescimoExtra,
  descontoExtra, complementoExtra}` (mesmo formato de
  `usePedidoItens.handleAddItem`) e passou a devolver `boolean` (sucesso) —
  a tela de confirmação só fecha e volta pra lista em caso de sucesso,
  senão o usuário pode corrigir e tentar de novo sem perder a seleção.
- Pedido Geral (`pedido-geral.tsx`) e O.S. (`os-form.tsx`, implementação de
  item independente, nem usa `AddItemModal` — ver `handleSaveItem`/
  `itemModal`) continuam de fora, pra quando o usuário pedir
  explicitamente.
- **Não testado ao vivo num navegador de verdade** (mesma limitação já
  documentada noutros módulos desta sessão) — só `tsc --noEmit` confirmado
  sem novos erros vs. baseline; o fluxo do seletor em si (checkbox/radio,
  bloqueio de obrigatório, soma no preço, texto no Complemento) ainda não
  passou por um teste manual na tela, nem no `AddItemModal.tsx` original
  nem nesta extensão ao card.

---

## Emissão Fiscal Real (NFC-e/NF-e/NFS-e)

**Status: 🟡 Fases 1 e 3 implementadas 2026-07-21 (NFC-e e NFS-e síncronas), Fases 2 e 4 pendentes.**
Migração de `FrmTraImpNFE.frm` ("Impressão de Nota Fiscal" — a segunda tela
principal do sistema, depois do Gestor de Comandas). Plano completo em
`C:\Users\carlo\.claude\plans\velvet-roaming-sparrow.md`. Decisão do usuário,
não presumida: reimplementar em Python puro a lógica fiscal hoje na DLL
VB.NET `Backon_Controllers.Nfe` (não chamar via COM-interop), melhorando o
que fizer sentido — não um port 1:1.

**Estado de referência da DLL/form no momento do port** (pra comparação
futura, quando a equipe VB.NET terminar a atualização em andamento):
`Backon.Controllers/NFe.vb` e `FrmTraImpNFE.frm` rastreados/colados
2026-07-21. `GeraNFe` não calcula alíquota (só monta/assina/transmite
valores já resolvidos); a resolução de tributação real está inteira no VB6
(`SitTribut()`), portada aqui. `ImprimeDanfe` depende de
`PrintPreviewDialog` + `biopdf.PDFUtil` (COM de terceiros) — não portável,
fica pra Fase 4 (DANFCe em HTML). `EmiteNFSe` não existe na DLL — é
orquestração VB6 local ainda não localizada.

### Arquitetura de chamada de `FrmTraImpNFE` — esclarecido pelo usuário, 2026-08-06

Informação de arquitetura (não implementação ainda) — como e de onde
`FrmTraImpNFE` ("tela de impressão de nota fiscal") é chamada no legado,
pra guiar como conectar as peças já portadas quando isso for retomado:

1. **Faturar direto pelo Pedido de Venda ou O.S.** → gera a `comanda` →
   em seguida chama `FrmTraImpNFE` já com a comanda carregada. Este é o
   caminho **"Gerar Nfe Comanda"** do menu (ver abaixo) — o usuário abre a
   tela de impressão de NF manualmente logo após faturar, pra emitir
   NFe/NFSe daquela comanda específica.
2. **Tela de Vendas (Checkout/`FrmPafOFF`)**, ao final da venda, **também**
   chama `FrmTraImpNFE` — mas só pra **NFe ou NFSe**. Este é o mesmo
   `FinalizaVenda` já rastreado nesta sessão (checagem de Taxa NFCe,
   referência de Pedido/O.S. no comprovante) — ou seja, `FinalizaVenda` já
   faz esse encaminhamento como parte do que ela trata.
3. **Para NFCe especificamente, o caminho é DIFERENTE**: `FrmPafOFF` não
   passa por `FrmTraImpNFE` — chama a função da DLL **direto no código**
   (`Backon_NFe.GeraNFe`, dentro do próprio `FinalizaVenda`, já rastreado
   e documentado acima na Fase 1). **Pedido explícito do usuário**: esse
   trecho de código "tem que ser refatorado para ser usado no futuro
   Pedido Bar" — ou seja, quando o Pedido Bar ganhar sua própria emissão
   direta de NFCe (faturamento rápido tipo balcão), deve **reaproveitar**
   essa mesma lógica de emissão direta (hoje só integrada ao Checkout via
   `comanda_service._emitir_nfce_comanda_sync`/rota `POST /api/comandas/
   {comanda}/emitir-nfce`), não duplicá-la. Fica registrado como
   requisito de design pra quando o Pedido Bar for estendido — a função já
   existe e é chamável de qualquer lugar que tenha uma `comanda`, só
   precisa ser conectada lá também quando pedido.

### Blueprint do futuro menu "Gestor Fiscal" — rastreio completo das 8 telas, 2026-08-06

Menu real "Transações > Notas Fiscais" do MDI VB6, colado pelo usuário como
referência pro futuro menu **"Gestor Fiscal"** desta migração. Rastreamento
campo-a-campo de cada uma das 8 telas concluído nesta rodada (via os Click
handlers reais do MDI, `mdirevendanv.frm`/`mdi_os_nova.frm`, tags/nomes de
form confirmados contra `.vbp`). Nenhuma delas foi implementada ainda —
isto é só o levantamento, seguindo "Legacy VB6 Source Reference".

**Achado de processo, vale para qualquer rastreio futuro nesta área**: o
`.vbp` "principal" mais antigo de Kontacto (`Kontacto.vbp`, 2014) está
desatualizado — o `.vbp` realmente em uso é **`Kontacto\backon.vbp`**
(modificado 2026-07-28, o mais recente de longe), cujo MDI de startup é
**`mdi_os_nova.frm`** (não `mdirevendanv.frm`). Os handlers de menu batem
entre os dois (mesmas rotas), mas `mdi_os_nova.frm`/`backon.vbp` tem
roteamento extra mais novo (ex.: Sefin Nacional, ver item 5 abaixo) — ao
rastrear esta área de novo, conferir os dois, preferindo `backon.vbp`
quando divergirem. **Achado extra, mais geral**: `Geral\FrmTraNFe.frm`
(1046 linhas) está **desatualizado/incompleto** — a versão realmente usada
em produção (confirmado via grep no `.vbp`) é `NFe\frmtranfe.frm` (9009
linhas). Ou seja, "Geral é sempre a versão canônica" (regra geral do
projeto) tem uma exceção conhecida aqui — **sempre confirmar contra o
`.vbp` antes de tratar uma cópia de `Geral` como definitiva**, especialmente
se o tamanho do arquivo parecer pequeno demais pra complexidade esperada da
tela.

1. **Gerar Nfe Comanda** = `NFe\FrmTraImpNFE.frm` — emissão de NFe/NFSe a
   partir de comanda já faturada. Click handler confirmado:
   `Tra_nfs_Inf_Click → Exibe_Form(FrmTraImpNFE, "FrmTraImpNFe")`. Já
   coberto pelas Fases 1/3/4 acima (hoje integrado via botões no Gestor de
   Comandas, não uma tela dedicada própria ainda) — nenhum rastreio novo
   necessário.

2. **Recebimento** = `Geral\FrmtraRec.frm` (confirmado canônico via
   `.vbp`, 14.069 linhas — o maior form do sistema). **Cobre as duas
   coisas ao mesmo tempo**: digitação manual de nota de entrada
   (opcionalmente incorporando um Pedido de Compra aberto, Quantidade
   Pedida/Recebida linha a linha) **e** importação de XML de NF-e de
   entrada (`Importar XML` → `Inicia_Importacao_XML`,
   `Geral\Mdl_Imp_XML.bas`). **Isto substitui/confirma** a referência
   anterior (`FrmConDev.frm`) em [[project_recebimento_mercadoria]] — o
   form real é este.
   - **Importação de XML é string-parsing manual** (`InStr`/recorte de
     texto entre tags, sem MSXML/DOMDocument) — gambiarra de linguagem
     (VB6 não tinha parser XML DOM confortável), não regra de negócio; a
     migração deve usar parser XML real (`lxml`/`xml.etree`). Resolve
     fornecedor por CNPJ (cria se não existir) ou cliente (fluxo de
     devolução — nunca cria cliente automaticamente). Vincula produto do
     XML ao cadastro via `pecas_xml` → `codigo_fab` → EAN (nessa ordem de
     fallback); sem casar, marca pra cadastro manual. Bloqueia
     reimportação da mesma NF (núm+série+fornecedor).
   - **Regras reais**: crítica de recebimento (`CmdCritica_Click`) confere
     cada total do cabeçalho contra `SUM()` dos itens — diferença dentro
     de `Valor_Libera_Critica` é auto-ajustada, fora da tolerância
     bloqueia. "Atualizar/Confirmar" promove staging (`nf_recebimento*`) →
     definitivo (`n_fiscal*`), atualiza estoque só se
     `tipo_mov.atualiza_est='S'`, calcula **custo médio ponderado**
     (estoque anterior×custo anterior + recebido×custo recebimento, sobre
     o total) e custo de reposição/inventário somando frete/seguro/
     despesas/ICMS-ST rateados, atualiza preço de venda por margem quando
     `Altera_Venda`+`politica_preco='E'` (Entrada — mesmo campo já portado
     em Produto Completo, ver seção acima), rateia frete "fora da nota"
     proporcional ao valor de cada item. **Baixa de Pedido de Compra**
     (`BaixaPedidoCompra`) é FIFO por `pedido.codigo` mais antigo primeiro,
     contra pedidos abertos (`situacao IN ('F','RP')`) do mesmo
     fornecedor/produto. Vencimentos devem somar exatamente o valor total.
   - **Tabelas**: staging `nf_recebimento`/`_itens`/`_icms`/`_custo`/
     `_vencimento`/`_pedido`/`_frete`/`_num_serie`/`_liberado`; definitivo
     `n_fiscal`/`n_fiscal_itens`/`n_fiscal_icms`/`n_fiscal_Custo`/
     `nf_vencimento`/`pedido_nf`; auxiliares `pecas_xml`/`cfop_xml`/
     `codbarra_auxiliar`/`ncm_cest`/`tipo_mov`; efeitos colaterais em
     `pecas`/`pedido`/`pedido_itens`/`movimentacao`/`fornecedor`/
     `veiculos`/`servicos`/`devolucao_itens`/`consignacao`. Nenhuma
     chamada a `Backon_Controllers` neste fluxo.

3. **Gerar Nfe** (avulsa) = **`NFe\frmtranfe.frm`** (9009 linhas — não a
   cópia desatualizada `Geral\FrmTraNFe.frm`, ver aviso de processo acima).
   Emite NF manualmente pra **qualquer tipo de movimentação** (combo
   carrega todo `tipo_mov` ativo, entrada e saída) — e também **importa**
   itens automaticamente de um documento já existente via 6 sub-rotinas:
   `ImportaPedido`, `ImportaDevolucao`, `ImportaCompraPedido`,
   `ImportaRequisicao`, `ImportaNF`, `ImportaComplementar` (nota
   complementar a partir de Comanda).
   - **Regras reais**: máximo de 4 itens tipo Serviço por NF; Série
     obrigatória exceto em devolução; tipo de movimento com
     `transf_pagar='S'` exige vencimentos lançados antes de fechar; alerta
     de possível NF duplicada (mesma data+destinatário+movimento+valor);
     reemissão de NF já com chave de acesso consulta o SEFAZ antes de
     permitir nova tentativa; Cilindro/Estoque de terceiros ajusta
     `pecas.estoque_for`/`estoque_cli` conforme `tipo_mov.estoque_
     fornecedor`/`estoque_cliente` (entrada em consignação de/para
     terceiros); `ExigeContraPartida` — certos tipos de movimento exigem
     indicar a NF de origem, pra permitir cancelamento automático futuro.
   - **Gambiarras confirmadas**: `ImportaComplementar` insere um endereço
     **hardcoded** de uma instalação específica (`'RUA VITOR MEIRELES, Nº
     221'`, Riachuelo, Rio de Janeiro) em `cliente_end` quando o cliente da
     Comanda não tem endereço — fallback de uma instalação, não regra
     geral (mesmo padrão do CNPJ hardcoded já implementado no Checkout,
     ver seção acima). Tabelas temporárias por hostname (`tempdev`/
     `tempREQ`, filtradas por `COMPUTADOR = NomeComputador`, com
     `DROP TABLE`+`CREATE TABLE` a cada uso) — workaround pré-multiusuário
     real, substituir por parâmetro de sessão/transação real, não portar
     literalmente.
   - **Tabelas**: rascunho `nf_aux`/`nf_aux_itens`/`nf_aux_vencimento`;
     definitivo `n_fiscal`/`n_fiscal_itens`/`n_fiscal_vinculada`/
     `nf_vencimento` (a criação do registro definitivo em si não foi
     encontrada neste `.frm` — deve estar num `.bas` compartilhado, não
     rastreado ainda); `pecas`, `consignacao`/`consignacao_baixa`,
     `pedido_venda`/`pedido_venda_prod`/`pedido_nf`, `devolucao_itens`/
     `movimentacao`, `requisicao`/`tempREQ`, `tempdev`, `cliente_end`,
     `cfops`, `tipo_mov`, `devolucao_config`, `controle`/`controle_aux`.
   - **DLL**: `Backon_Controllers.Nfe.GeraNFe` (emissão real, contingência
     tratada) e `.ConsultaNFE` (status SEFAZ) — mesmo padrão já documentado
     em [[project_nfse_dps_emissao]].

4. **Despacho de NF's** (item extra do menu real, não fazia parte da
   lista original de 8 que o usuário tinha citado de memória — mas existe
   de fato no mesmo bloco de menu) = `Geral\FrmDesNf.frm` (806 linhas,
   confirmado canônico, sem divergência de `.vbp`). Tela compacta:
   registra dados de **transporte/despacho de uma NF já emitida** (não cria
   nota nova) — data/hora de saída, placa, transportador (CNPJ/CPF com
   dígito verificador), motorista, pesos bruto/líquido, volumes, espécie —
   `UPDATE N_Fiscal SET ...` puro, nunca `INSERT`. Permite agrupar várias
   notas na mesma "corrida" (mesma Placa+Data+Hora). "Excluir" zera os
   campos de despacho, não apaga a NF. Código morto identificado
   (`CmDaltera`/`List1`, handlers de controles que não existem mais no
   desenho do form) — ignorar na migração.

5. **Gestor NFSe** = `Geral\FrmManNSe.frm` (1367 linhas, confirmado
   canônico). Tela lista+ação (sem detalhe separado): filtra comandas com
   item de serviço e cruza com RPS/NFS-e já gerados numa lista com
   checkbox por linha; 6 ações — Selecionar/Imprimir RPS/Gerar NFSe/Enviar
   link por e-mail/Validar Estrutura RPS/Consultar Situação na Prefeitura.
   - **Regras reais**: só permite gerar RPS/NFSe se a comanda tiver item de
     serviço; bloqueia cliente sem endereço, CPF/CNPJ inválido, ou
     município não cadastrado antes de qualquer ação; e-mail de link da
     NFSe é montado por município (Rio, Niterói, Itaguaí, Duque de
     Caxias, São Gonçalo — cada um com formato próprio de URL de consulta
     pública —, e um formato Ginfes genérico pros demais).
   - **Achado arquitetural importante**: o roteamento real do menu (em
     `mdi_os_nova.frm`, o MDI mais novo) é **condicional**:
     `If Dados_Controle_Configuracao.Sefin_Nacional Then FrmManNSeSefin
     Else FrmManNSe` — ou seja, **as duas telas coexistem hoje no
     legado**, não é que o DPS Nacional substituiu totalmente o fluxo
     antigo de RPS municipal. Isto é relevante pra
     [[project_nfse_dps_emissao]]: a Fase 3 já implementada (DPS
     Nacional) cobre só o caminho novo; o caminho antigo (RPS por
     prefeitura, `rps`/município a município) descrito aqui **não foi
     portado** e pode ainda ser necessário pra instalações/municípios que
     não migraram pro Sefin Nacional — não presumir que Fase 3 é
     substituto completo sem confirmar com o usuário.
   - **Tabelas**: `comanda`, `cliente`, `rps`, `n_fiscal` (via `rps.nfse`),
     `movimentacao`/`servicos`, `controle`. **DLL**:
     `Backon_Controllers.NFSe` — `ImprimeRPS`, `EnviarLoteRpsEnvio`/
     `EnviarSaoGoncalo` (São Gonçalo tem classe própria,
     `NFSe_SaoGoncalo`), `ConsultarNfseRpsEnvio`/`ConsultaSaoGoncalo`,
     `ConsultarLoteRpsEnvio`.

6. **Gestor NFCe** = `Geral\FrmTraNFC.frm` (2184 linhas, confirmado
   canônico). Lista+ação mais crítica fiscalmente — cobre emissão/
   consulta/cancelamento/inutilização de NFC-e com tratamento de
   contingência. Checkboxes de situação (Transmitida/Não Transmitida/
   Contingência/Cancelada/Inutilizada/Sem NFCe). Também funciona em **modo
   picker**: aberta com `FormChamou = "FRMTRANFEVINCULADA"`, devolve itens
   marcados pro `FrmTraNFe` (item 3) — reaproveitamento de tela pro fluxo
   de Nota Fiscal de Devolução vinculada a uma NFC-e original.
   - **Regras reais**: Cancelar/Inutilizar/Consultar bloqueados durante
     contingência aberta (`Verifica_NFCe_Contingencia`, `NFe.bas`);
     Cancelar exige todos os itens marcados já com NFC-e emitida;
     Retransmitir/Validar Contingência exigem que todos os itens marcados
     estejam no MESMO estado (misturar bloqueia); Inutilização exige
     motivo com mínimo 15 caracteres e só roda após consultar o SEFAZ e
     confirmar que a nota não existe lá; detecção de buracos na numeração
     sequencial por série (`NFE_A_INUTILIZAR`, tabela temporária —
     workaround de era VB6 sem window functions, mas a regra em si —
     detectar e inutilizar lacunas — é obrigação fiscal real).
   - **Suspeitas de copy-paste/gambiarra** (sinalizadas, não confirmadas):
     captions de alguns checkboxes parecem herdados do clone de
     `FrmManNSe` sem uso real aqui; um `Case` duplicado morto referencia
     um `Campo(6)` que não existe nesta tela; um checkbox
     ("somente tributados") é reaproveitado como flag de modo em outro
     fluxo — uso duplo do mesmo controle pra dois propósitos não
     relacionados.
   - **Tabelas**: `comanda`, `comanda_nfce`, `cliente`, `movimentacao`/
     `pecas`, `contingencia_nfce`, `Logs`, `inutilizacao_nfe`,
     `mensagenspdv`, `forma_pagamento`. **DLL**: `Backon_Controllers.Nfe`
     — `GeraNFe`/`GeraXML`, `ImprimeDanfe`/`ImprimeNFceNaoFiscal`,
     `ValidaContingencia`, `RetransmiteNFCe`, `InutilizacaoNFe`,
     `CancelaNFe` (via wrapper local `cancelanfce`, `NFe.bas`).

7. **Contingência NFe** = `Geral\FrmConNFe.frm` (444 linhas, confirmado
   canônico — única cópia em toda a árvore, sem risco de divergência).
   Tela simples: abre/encerra um período de contingência (SEFAZ
   indisponível). CRUD puro em `contingencia_nfe` (data/hora início+fim,
   motivo 15-256 chars, tipo FS-IA/FS-DA). **Bloqueia abrir contingência
   nova se já existir uma aberta** (`DATA_FIM IS NULL`); bloqueia excluir
   contingência já encerrada. **Gambiarra confirmada**: o código legado usa
   `WHERE DATA_FIM=NULL` (sintaxe SQL tecnicamente incorreta, só funciona
   por `ANSI_NULLS OFF` legado) — a regra em si (só uma contingência aberta
   por vez) é real, portar com `IS NULL` correto. **Sem chamada a DLL** —
   é só um registro informativo local; o efeito real de "emitir em modo
   contingência" deve ser lido por outra tela (emissão), não confirmado
   nesta rodada.

8. **Contingência NFCe** = `Geral\FrmConNFC.frm` (467 linhas, confirmado
   canônico). Mesmo padrão exato de `FrmConNFe`, só que em
   `contingencia_nfce`. Tipos divergem (FS=5 "Formulário de Segurança"/
   Off-Line=9 — não confundir com os códigos 2/5 de NFe, são enums fiscais
   distintos por modelo). **Achado a confirmar com o usuário**: a opção
   "Formulário de Segurança" está oculta na tela (`Visible=0`) mas o código
   ainda testa o valor normalmente — pode ser um recurso descontinuado de
   propósito (só Off-Line usado na prática hoje) ou só um gap de UI; não
   assumir nenhuma das duas sem perguntar quando esta tela for retomada.

9. **Inutilização de Faixa NFe/NFCe** = `Geral\FrmTraINF.frm` (513 linhas,
   confirmado canônico). A mais complexa das telas pequenas — inutiliza
   formalmente junto à SEFAZ uma faixa de numeração não emitida. Escolhe
   Tipo (NFe/NFCe), Série, Número Inicial/Final, Motivo (mín. 15 chars).
   - **Regras reais**: bloqueia se Número Final > último número já emitido
     da série; verificação crítica pré-envio — se qualquer nota dentro da
     faixa já foi emitida, bloqueia com a lista de números encontrados
     (nunca deixa inutilizar faixa com notas reais); dupla confirmação
     explícita (processo é irreversível junto à SEFAZ); só grava em
     `inutilizacao_nfe` se a resposta do SEFAZ não for erro.
   - **Ponto em aberto**: `Pos_Sistema`/`Msg_Pos_Sistema` (globais usados
     num bloqueio inicial da tela) não foram rastreados até `mdl_proc.bas`
     nesta rodada — localizar antes de implementar essa checagem
     específica, não assumir o significado.
   - **Tabelas**: `controle`/`controle_nota_fiscal` (séries de NFe),
     `controle_aux` (série/número NFCe), `n_fiscal`/`COMANDA_NFCE`
     (checagem de notas já emitidas na faixa), `inutilizacao_nfe`
     (registro final), `Logs` (auditoria, só NFCe). **DLL**:
     `Backon_Controllers.Nfe.InutilizacaoNFe` — monta XML `<inutNFe>`
     conforme layout SEFAZ, assina com certificado, transmite (serviço 6 =
     inutilização). Nota: existe também uma cópia quase idêntica dessa
     função em `NFe2.vb` — mesmo padrão de versionamento paralelo já visto
     em outras funções desta DLL, conferir qual delas está de fato em uso
     antes de portar.

### Fase 1 — Motor de emissão de NFC-e (modelo 65), síncrona — ✅ implementada
- **`backend/services/nfe_fiscal_common.py`** (novo) — extraído de
  `nfe_cancelamento_service.py`: `carregar_certificado_sync`, `assinar_xml`,
  `montar_envelope_soap`, `transmitir`, `extrair_tag`, `resolver_endpoint`,
  `IBGE_POR_UF`, `UFS_SVRS`. `nfe_cancelamento_service.py` foi refatorado
  pra usar este módulo comum (wrappers finos, mesmos nomes de sempre — os
  17 testes de cancelamento continuam passando sem alteração).
- **`backend/services/nfe_emissao_service.py`** (novo):
  - `_resolver_tributacao_sync`/`_gerar_tentativas_tributacao` — porta
    fiel de `SitTribut()` (cascata de fallback: simples_nacional →
    consumidor_final → UF="XX" → protocolo_st, replicada explicitamente
    como lista de tentativas, não um loop compacto, pra ficar auditável
    contra a fonte). **Achado não-óbvio confirmado na fonte**: a query de
    `taxas` não filtra pelo CFOP do item — só EXCLUI `cfop = 
    CFOP_Cupom_Fiscal`; e a variável "CSN" do VB6 na verdade começa
    valendo `NaoContribuinte`, não `Cliente_Simples_Nacional` (só no
    fallback de UF="XX" é que usa o valor "real"). Documentado no código,
    não é engano do port.
  - `montar_chave_acesso`/`_dv_modulo11` — algoritmo público (mod-11) de
    chave de acesso de 44 dígitos.
  - `montar_url_qrcode` — algoritmo público do QR Code da NFCe (MOC 2.00).
  - `_montar_xml_nfce`/`_montar_envelope_autorizacao` — layout NFe 4.00.
    **Não validado contra o XSD oficial da SEFAZ** — a ordem de tags segue
    o layout público conhecido, mas precisa de validação formal antes de
    qualquer transmissão real (nem mesmo em homologação).
  - `emitir_nfce_sync` — orquestrador (assina, transmite, interpreta
    `cStat`). Endpoints só do grupo SVRS (mesma limitação do cancelamento).
  - `backend/services/comanda_service.py::_emitir_nfce_comanda_sync` —
    integra tudo: valida permissão/situação/duplicidade, resolve cliente
    (não-contribuinte/simples nacional/consumidor final), resolve
    tributação por item, chama o orquestrador, grava `n_fiscal`+
    `comanda_nfce`+`comanda_nf`, incrementa `controle_aux.numero_nfce`.
  - Rota `POST /api/comandas/{comanda}/emitir-nfce`, ação
    `ALTERAR_COMANDA.EMITIR_NF` no catálogo de permissões.
  - **Frontend**: card "Nota Fiscal" em `alterar-comanda.tsx` — mostra o
    documento já emitido, ou botão "Emitir NFC-e" quando ainda não há
    nenhum (só com a comanda faturada e permissão). Modo Didático
    atualizado.
  - **38 testes unitários novos** (`test_nfe_emissao_service.py` +
    adições em `test_comanda_service.py`) — 749 no total na suíte,
    **nunca contra certificado real nem rede real** (mesmo compromisso do
    cancelamento — só certificado autoassinado em memória + `transmitir`
    sempre mockada).
- **Não validado ao vivo contra BD_PAJE nem contra o SEFAZ** (nem
  homologação) — essa conexão tem o certificado real de um cliente em
  produção (CNPJ 49680039000196, confirmado ao vivo via
  `SELECT cgc FROM controle`) e emitir uma NFC-e de verdade teria
  consequência fiscal real. Só leituras de schema (`SELECT`/
  `INFORMATION_SCHEMA`) foram feitas contra essa conexão nesta fase.
- **Gap real descoberto ao investigar a Fase 3 (corrigido no mesmo dia)**:
  uma comanda desta empresa pode misturar item de produto e de serviço
  (ex.: peça + mão de obra de alinhamento numa auto center — confirmado ao
  vivo contra `BD_PAJE`, item `SALD`="ALINHAMENTO DIANTEIRO" existe em
  `movimentacao` de comandas reais). A query de itens da Fase 1
  (`_emitir_nfce_comanda_sync`) usava `LEFT JOIN pecas` — incluiria o item
  de serviço na NFC-e também, com colunas de tributação vazias,
  corrompendo o documento. Corrigido pra `JOIN` (inner) — itens de serviço
  agora só entram pela NFS-e (Fase 3).
- **Limitação conhecida, não resolvida**: `comanda_service._get_doc_fiscal_
  sync` devolve só o PRIMEIRO documento encontrado (NFC-e > NFS-e > NF >
  Cupom), não uma lista. Numa comanda mista que já emitiu um dos dois
  documentos, o card "Nota Fiscal" (`alterar-comanda.tsx`) mostra esse
  documento e ainda oferece o botão do outro tipo (o botão consulta o
  backend, que valida duplicidade por tipo de forma independente) — mas se
  os DOIS já foram emitidos, a tela só mostra um deles. Resolver de
  verdade exige mudar a resposta de `get_doc_fiscal` de objeto único pra
  lista — não feito nesta rodada por ser uma tela nova (baixo risco/baixa
  urgência), registrar se o usuário topar uma comanda mista de verdade.

### Fase 2 — NF-e (modelo 55), lote assíncrono — 🔴 não iniciada
Reaproveita quase tudo da Fase 1, precisa de `_consultar_recibo_sync`
(`NFeRetAutorizacao4`) já que a autorização de NF-e não é sempre síncrona.

### Fase 3 — NFS-e (DPS Nacional/Sefin Nacional) — ✅ implementada (só o caminho nacional)
`EmiteNFSe` foi localizado em `Geral\NFSe.bas` (linha 795, 2026-07-21) — não
está na DLL, é orquestração VB6 pura. Revelou escopo maior do que o
esperado: a rotina branca em **4 caminhos** conforme
`Dados_Controle_Configuracao.Sefin_Nacional` e o código do município:
1. **Sefin Nacional / DPS** — padrão nacional unificado novo.
2. São Gonçalo (3304904) — webservice próprio (`EnviarSaoGoncalo`).
3. Nova Iguaçu (3303500) — GINFES (`nota_ny.EnviarLoteRpsEnvio`).
4. ABRASF genérico por município — qualquer outro, via `NFSeDPS`.

**Decisão do usuário via `AskUserQuestion` (2026-07-21)**: implementar só
o caminho (1) por enquanto — é o padrão que a lei está unificando
nacionalmente. **Correção do próprio usuário, mesmo dia**: os caminhos
(2)-(4) (São Gonçalo, Nova Iguaçu/GINFES, ABRASF genérico) **não estão
obsoletos nem sendo descontinuados** — Nova Iguaçu especificamente
"continua existindo" (uso ativo real) — a decisão de escopo foi só
priorizar o caminho nacional primeiro, não presumir que os outros vão
sumir. Caminhos (2)-(4) **não implementados nesta rodada**, registrados
aqui como pendência futura caso a empresa precise emitir NFS-e num
município que ainda usa um desses caminhos específicos (ou em paralelo ao
nacional, conforme o município).

- **`backend/services/nfe_fiscal_common.py`** — nova função
  `transmitir_json_mtls` (POST JSON + TLS mútuo — o ADN troca mensagens em
  JSON, não SOAP/XML puro como o SEFAZ, mas ainda exige o certificado do
  contribuinte como client cert da conexão TLS; confirmado ao vivo: toda
  URL `adn.nfse.gov.br/**`, inclusive só pra ver a documentação Swagger,
  devolve HTTP 496 "certificado exigido").
- **`backend/services/nfse_emissao_service.py`** (novo):
  - `montar_id_dps` — Id de 45 posições do elemento `infDPS`
    ("DPS"+cLocEmi(7)+tpInsc(1)+inscriçãoFederal(14)+série(5)+nDPS(15)).
    **Diferente da chave de 44 dígitos NF-e/NFC-e** — não tem dígito
    verificador próprio, é só concatenação posicional; a chave de acesso
    real da NFS-e (50 posições) é devolvida pelo próprio ADN na resposta,
    não calculada aqui.
  - `_montar_xml_dps` — layout `<DPS><infDPS>` do padrão nacional
    (`prest`/`toma`/`serv`/`valores`).
  - Assinatura reaproveita `nfe_fiscal_common.assinar_xml` tal qual (mesmo
    RSA-SHA256 + C14N + enveloped da Fase 1 — confirmado ser também o
    padrão real do DPS Nacional, não só uma modernização arbitrária desta
    vez).
  - `emitir_nfse_sync` — orquestrador: monta/assina a DPS, empacota
    (gzip+base64, campo `dpsXmlGZipB64`), envia por JSON+mTLS pro ADN
    (`sefin.nfse.gov.br/SefinNacional/nfse`), interpreta `chaveAcesso`/
    `nfseXmlGZipB64` da resposta.
  - `backend/services/comanda_service.py::_emitir_nfse_comanda_sync` —
    integra tudo: valida permissão/módulo `sefin_nacional`/situação/
    duplicidade, resolve itens de SERVIÇO (`JOIN servicos`, não `pecas` —
    mesma comanda pode ter os dois tipos misturados, ver achado acima),
    resolve código de município (ver limitação abaixo), chama o
    orquestrador, grava `n_fiscal` (`situacao_nfse`)+`comanda_nf` (`tipo=2`
    — **valor já usado em dados reais de produção**, confirmado ao vivo
    contra `BD_PAJE`, não inventado nesta sessão), incrementa
    `controle_aux.numero_DPS`.
  - Rota `POST /api/comandas/{comanda}/emitir-nfse`, ação
    `ALTERAR_COMANDA.EMITIR_NFSE` no catálogo de permissões (separada de
    `EMITIR_NF` — documento fiscal diferente, grupo pode ter uma sem a
    outra).
  - **Frontend**: card "Nota Fiscal" em `alterar-comanda.tsx` ganhou o
    botão "Emitir NFS-e" ao lado do "Emitir NFC-e" (ver limitação de
    exibição registrada acima). Modo Didático atualizado.
  - **21 testes unitários novos** (`test_nfse_emissao_service.py` + adições
    em `test_comanda_service.py`) — mesmo compromisso do resto do pacote:
    nunca contra certificado real nem rede real.
- **Limitação real, sem solução no schema atual**: não existe tabela de
  município (IBGE) neste banco — `controle` só guarda `cidade` (texto
  livre) + `uf`. `_resolver_cod_municipio_ibge` (`comanda_service.py`) é
  uma tabela-semente pequena (hoje só "RIO DE JANEIRO"/RJ → 3304557, a
  cidade confirmada da empresa testada) — qualquer empresa fora dela
  bloqueia com mensagem clara em vez de adivinhar um código errado.
  Resolver de verdade exige uma tabela de municípios IBGE própria (ou um
  novo campo em `controle_aux`) — fora do escopo desta fase.
- **`cTribNac` (Código de Tributação Nacional, 6 dígitos) aproximado por
  `servicos.cod_lista_servico`** (a lista LC116 antiga) — o padrão
  nacional tem uma tabela própria nova de códigos, sem mapeamento
  cadastrado neste app ainda. Funciona como "melhor aproximação
  disponível", mas **não confirmado contra a tabela oficial de cTribNac**
  — revisar se o ADN rejeitar por código de serviço inválido.
- **Fontes técnicas do padrão nacional (não confirmadas contra o PDF
  oficial — a ferramenta de leitura de PDF não extraiu o conteúdo técnico
  do manual `gov.br/nfse` nesta sessão)**: XML de exemplo real do PoC
  oficial (`github.com/nfe/poc-nfse-nacional`), formato de request/response
  JSON e composição das chaves via relatos técnicos públicos de
  integradores (tabnews.com.br/Crazynds, tabnews.com.br/CesarMasserati).
  **Revalidar contra o Anexo I do manual oficial (`LeiautesRN_DPS_
  NFSe-SNNFSe`) antes de qualquer transmissão real, mesmo em homologação**
  — CLAUDE.md §12.
- **Nunca testado contra o ADN real** (nem produção restrita) — exigiria
  certificado ICP-Brasil genuíno + cadastro prévio no ambiente nacional,
  fora do alcance desta sessão. Mesma ressalva de segurança da Fase 1: a
  conexão de teste (`BD_PAJE`) tem certificado real de cliente em
  produção, nunca usado pra chamada real.
- **Caminhos (2)-(4) do `EmiteNFSe` original (São Gonçalo/Nova Iguaçu/
  ABRASF genérico) não implementados** — decisão explícita do usuário
  (ver acima). Retomar só se a empresa precisar emitir NFS-e num município
  que ainda não aderiu ao padrão nacional.

### Fase 4 — DANFE/DANFCe em HTML — 🟡 DANFCe/DANFSe implementados (2026-07-21), DANFE (NF-e modelo 55) pendente
Melhoria deliberada (não port 1:1): o legado usa `PrintPreviewDialog` +
driver COM de impressora virtual de terceiros (`biopdf.PDFUtil`), inviável
num backend. Substituído por HTML (reaproveitando `printHtml.ts`) — o
botão "Reimprimir documento fiscal" em `gestor-comandas.tsx` (só ali; o
card "Nota Fiscal" de `alterar-comanda.tsx` não tem reimpressão, só emitir)
agora monta um fac-símile visual de verdade pra NFC-e e NFS-e, em vez da
lista de campos crus de antes. Pedido explícito do usuário, com exemplo
real de DANFSe v2.0 colado (PDF) pra referência de layout.

- **DANFCe**: `nfe_emissao_service.parse_nfce_xml_para_exibicao(xml)` —
  parseia o XML assinado já gravado em `comanda_nfce.xml` na emissão (é o
  XML que o próprio sistema montou, `lxml`+namespace, não um schema de
  terceiro adivinhado) — devolve itens/emit/dest/qrcode estruturados.
  `frontend/src/utils/danfeFacsimile.ts::buildDanfceHtml`.
- **DANFSe**: como a emissão de NFS-e nunca foi validada contra o ADN real
  (Fase 3 acima), não há XML de resposta confiável pra parsear — emitente/
  tomador/serviço são **resolvidos de novo no backend** na hora da
  reimpressão (mesmas fontes da emissão: `controle`/`cliente`/
  `movimentacao`+`servicos`), não lidos de um snapshot gravado. Se a
  empresa/cliente mudar depois da emissão original, o fac-símile reflete o
  dado ATUAL, não o transmitido — gap conhecido, aceitável pra uma
  reimpressão (não é o documento fiscal oficial em si, que seria o XML/PDF
  devolvido pelo ADN). `numero_dps`/`serie_dps` passaram a ser gravados em
  `n_fiscal.num_nf`/`serie_nf` na emissão (reaproveitando as colunas
  genéricas, mesmo padrão já usado noutras unificações) especificamente
  pra viabilizar essa reimpressão sem precisar reabrir XML nenhum.
  `frontend/src/utils/danfeFacsimile.ts::buildDanfseHtml`.
- **Correção 2026-07-21, mesmo dia — fonte real da impressão de NFS-e
  encontrada e conferida**: o usuário apontou o módulo real
  `Geral\Mdl_Imp_XML.bas::DanfeNFSE` (linha 726), a rotina de impressão
  oficial da NFS-e (chamada por `EmiteNFSe` via `Call DanfeNFSE(Comanda)`
  quando `Sefin_Nacional=True`). Achados confirmados direto na fonte:
  - **A seção "TRIBUTAÇÃO IBS/CBS" no sistema real IMPRIME LITERALMENTE
    "-" em todo campo**, mesmo já tendo lido as variáveis do XML
    (`CST`, `cClassTrib`, `pIBSUF`, `vIBSUF`, `pIBSMun`, `vIBSMun`,
    `vIBSTot`, `pCBS`, `pAliqEfetCBS`, `vCBS` etc.) — confirmado pelo
    próprio usuário: é trabalho em andamento na versão VB6/VB.NET agora,
    ainda não preenchido nem lá. **Revertida a versão "simulada" que eu
    tinha colocado antes de achar essa fonte** (pedido anterior do
    usuário, "simule com preenchimento dos campos", foi feito sem essa
    informação) — `buildIbsCbsHtml` agora mostra "-" em todo campo,
    igual ao sistema real hoje. Quando a equipe terminar essa parte no
    VB6/VB.NET, revisitar esta seção (mesmo processo de sincronização do
    CLAUDE.md §12) — não presumir que `CalculaIBSCBS`
    (`Geral\mdl_proc.bas`, linha 36432) já alimenta esses campos hoje.
  - **Atualização 2026-08-05 — equipe VB6/VB.NET terminou, fonte
    re-rastreada do zero** (mesma disciplina do CLAUDE.md §12): confirmado
    por `ls -la` que `Geral\mdl_proc.bas` e `Geral\Mdl_Imp_XML.bas` foram
    modificados depois da sessão anterior (2026-07-27/28), e 3 arquivos
    VB.NET também (`view_nfse.vb`, `DAO_NFE.vb`, `NFSeDPS.vb`). A seção
    "TRIBUTAÇÃO IBS/CBS" do `DanfeNFSE` **não imprime mais "-"** — imprime
    valores reais, lidos por parsing de tags de dentro do XML de RETORNO
    do ambiente nacional (`tb("path_xml_nfse")`, não do XML que o sistema
    local monta antes de enviar).
    - **`CalculaIBSCBS`** (`mdl_proc.bas:36433-36985`, cresceu de ~36432
      pra essa faixa) agora calcula de verdade: IBS-UF, IBS-Município e
      CBS como 3 bases/alíquotas independentes (não uma alíquota
      combinada), com diferimento e "alíquota efetiva de redução" por
      tributo, 4 variantes de regime monofásico ad rem (`gMonoPadrao`/
      `gMonoReten`/`gMonoRet`/`gMonoDif` — usado por produtos tipo
      combustível/bebida por volume), e um grupo opcional "Tributação
      Regular" (`gTribRegular`, provável comparação alíquota-cheia vs.
      reduzida durante a transição da reforma — inferência, não confirmada
      contra a Nota Técnica oficial). Grava o resultado como XML
      serializado por item (`n_fiscal_itens.XML_IBS_CBS`/
      `comanda_rtc.XML_IBS_CBS`) + agregado (`N_FISCAL.XML_TOT_IBS_CBS`/
      `COMANDA.XML_TOT_IBS_CBS`) — não em colunas tipadas por campo.
    - **Assimetria bens × serviços, achado mais importante**: pra NF-e/
      NFC-e (bens), o XML completo já calculado (`XML_IBS_CBS`) é embutido
      literalmente no item da nota (`DAO_NFE.vb`, ~linha 5193). Pro DPS de
      serviço (NFS-e), `DAO_NFE.vb::Dados_Servico` (linhas 961-1030) manda
      só `CST`+`cClassTrib`+indicador de operação — **nenhum valor
      monetário de IBS/CBS é enviado no envio da DPS**. Hipótese (não
      confirmada): o Ambiente de Dados Nacional calcula o valor pro lado
      serviços, e o sistema só lê de volta do XML de retorno pra imprimir
      — precisa confirmação antes de decidir se o backend Python
      precisaria replicar a fórmula de valor pra serviços ou só a
      classificação fiscal.
    - **Imposto Seletivo (IS): schema pronto em 7 tabelas
      (`TAXAS`/`TAXAS_NFCE`/`N_FISCAL_ITENS`/`NF_AUX_ITENS`/
      `NF_RECEBIMENTO_ITENS`/`COMANDA_NFCE_DETALHE`/`comanda_rtc`,
      colunas `CST_IS`/`CLASSTRIB_IS`/`BASE_IS`/`ALQT_IS`/`UNIDADE_IS`/
      `VALOR_IS`), mas o ÚNICO trecho que os referencia dentro de
      `CalculaIBSCBS` está COMENTADO** (linhas 36499-36502) — a equipe
      preparou terreno, não ligou a lógica ainda. **Não portar IS ainda**
      — aguardar a equipe terminar essa parte também.
    - Tela de manutenção real já existe: `FrmManTaxas.frm`/
      `FrmManTaxNFC.frm` ganharam campos de UI (grid `RTC`) pro usuário
      parametrizar as alíquotas por perfil (`cod_icms`, mesma FK que já
      resolve ICMS/IPI hoje — não é uma tabela de código de tributação da
      reforma separada).
    - **Possível bug real na fonte, não confirmado**: `gMonoDif`
      (`mdl_proc.bas:36846`) usa `BASE_ADREM_MONO` em vez de
      `BASE_ADREM_DIFERIMENTO` (atribuída na linha imediatamente anterior)
      — pode ser intencional ou copy-paste. Não replicar sem perguntar.
    - **`indDest`/`finNFSe` fixos em `"0"` hardcoded** no envio do DPS
      (`DAO_NFE.vb:1016/1018) — confirmar se é definitivo antes de portar.
    - Análise completa (com todas as citações de linha) rodada via agente
      de pesquisa 2026-08-05 — ver memória `project_ibs_cbs_vb6_pendente`
      pro relatório na íntegra. **Ainda não portado pro backend Python**
      — próximo passo, quando/se pedido, é decidir a arquitetura só depois
      de resolver a pergunta em aberto da assimetria bens×serviços acima.
    - **Respostas do usuário ao relatório, mesmo dia (2026-08-05)**:
      1. **"Terminado" é só POR ENQUANTO** — "será mexido novamente até o
         fim desse ano" (a Reforma Tributária continua em transição em
         2026, esperar novas rodadas de mudança nesta mesma área — não
         tratar como definitivo).
      2. **Assimetria bens×serviços CONFIRMADA, e a causa raiz é diferente
         da minha hipótese**: não é o Ambiente de Dados Nacional quem
         calcula o valor pros serviços — **é o próprio sistema local**
         ("o sistema, que é como está hoje"), a `CalculaIBSCBS` já está
         pronta/preparada pro cálculo de serviços também. O que acontece é
         que, **durante a fase de transição da reforma**, o layout do XML
         de envio da DPS **deliberadamente só informa CST/cClassTrib**,
         sem mandar o valor monetário calculado — decisão de leiaute da
         fase de transição, não limitação técnica nem cálculo feito por
         outro lugar. Deve mudar quando a fase de transição acabar.
      3. **Imposto Seletivo (IS)**: existe e está preparado (schema +
         function pronta pra ligar), mas **ainda não tem legislação nem
         alíquota definida** — não é falta de trabalho da equipe, é
         esperar definição externa (Comitê Gestor/legislação federal).
         "Pode entrar a qualquer momento" — continuar monitorando, não
         assumir prazo.
      4. **Tributação monofásica (o "possível bug" do `gMonoDif`) segue
         em aberto, sem trabalho ainda — mas SEM data mínima pra começar**:
         monofásico é especificamente pra combustíveis. **Correção
         importante do usuário**: a ENTRADA EM VIGOR da reforma dos
         monofásicos é que foi adiada pra 01/11/2026 — isso só dá mais
         prazo, **não é uma trava pra começar a mexer só depois dessa
         data**. O usuário pode pedir pra revisitar isso antes, inclusive
         "já no próximo mês" — não interpretar 01/11/2026 como "não tocar
         antes disso". A pergunta sobre se `BASE_ADREM_MONO` em `gMonoDif`
         é bug ou intencional, e a inferência sobre `gTribRegular`, ficam
         em aberto até o usuário (ou a equipe VB6) trazer mais contexto
         sobre os monofásicos — pode ser a qualquer momento, não
         necessariamente depois de 01/11.
  - **Tabela `dps` — tentativa de migrar pra ela foi revertida no mesmo
    dia, pedido explícito do usuário**: `DanfeNFSE` (a rotina de
    IMPRESSÃO) lê de `dps` (`SELECT * FROM comanda, dps WHERE
    comanda.comanda = dps.comanda`, colunas confirmadas ao vivo contra
    `BD_PAJE`: `comanda`, `num_dps`, `serie_dps`, `data_dps`, `hora_dps`,
    `valor_total`, `situacao`, `STATUS`, `chave_acesso_dps`,
    `chave_acesso_nfse`, `numnfse`, `XML_NFSE`, `path_xml_nfse`,
    `PDF_NFSE`/`PDF_DANFE_NFSE`) — a partir disso eu tinha migrado
    `_emitir_nfse_comanda_sync`/`_get_doc_fiscal_sync` pra gravar/ler de
    `dps` em vez de `n_fiscal`+`comanda_nf`. **Corrigido pelo usuário na
    sequência**: "tudo, absolutamente tudo de nota fiscal no sistema gira
    em torno das tabelas n_fiscal e comanda_nf" — a função central
    `GravaNFE` (`Geral\ModNF.bas`, linha 7468) confirma isso, grava em
    `N_FISCAL`/`n_fiscal_itens`. `dps` é lida pela rotina de impressão,
    mas **não é a tabela central de gravação** — `_emitir_nfse_comanda_
    sync`/`_get_doc_fiscal_sync` foram revertidos pra `n_fiscal`+
    `comanda_nf` (tipo=2), como estavam antes desta exploração. Lição
    registrada: ver `feedback_flag_guesses_before_executing` (memória) —
    daqui pra frente, avisar explicitamente ANTES de agir quando algo for
    inferido de uma tabela nova encontrada, não só depois de já ter
    implementado.
  - **Achado real ainda em aberto, não resolvido**: nos exemplos reais de
    `dps.chave_acesso_dps` vistos ao vivo (ex.:
    `33045572249680039000196000000000000126027055475005`, 50 caracteres),
    o formato **não bate** com o Id de 45 caracteres prefixado "DPS" que
    a documentação pública (PoC oficial, relatos de integradores)
    descreve — nem no comprimento nem no prefixo. `montar_id_dps`
    continua implementada conforme a documentação pública (não
    alterada), mas **não confere com o dado real observado** — decisão do
    usuário ("manter tudo como está"): não tentar adivinhar o formato
    exato a partir de só 2-3 amostras; registrar como pendência aberta
    até haver fonte melhor (o código VB.NET que monta essa chave, ou
    confirmação direta).
  - **QR Code confirmado real**: `https://www.nfse.gov.br/ConsultaPublica/
    ?tpc=1&chave=<ChaveAcesso>` (linha 799 do módulo) — não implementado
    ainda no fac-símile Python (`buildDanfseHtml` não mostra QR nem link
    de consulta hoje), fica pra próxima passada.
  - Layout de campos da fonte real (EMITENTE/TOMADOR/SERVIÇO PRESTADO)
    confere com o que eu já tinha montado a partir da documentação
    pública — sem mudança necessária aí.
- **DANFE (NF-e modelo 55) segue sem fac-símile** — Fase 2 (NF-e) em si
  também não foi implementada ainda (lote assíncrono), então não há XML
  de NF-e pra parsear ainda.
- Achado colateral corrigido de passagem: `_get_doc_fiscal_sync` tratava
  qualquer linha de `comanda_nf` (independente de `tipo`) como NF genérica
  — agora checa `tipo = 2` (NFS-e) explicitamente ANTES da checagem
  genérica, senão uma comanda com NFS-e emitida aparecia rotulada só como
  "NF" crua.

**Contingência (modo offline) fora de escopo** em todas as fases — gap
conhecido, registrar se algum dia for pedido.

## Totais por Forma de Pagamento — Gestor de Comandas

**Adicionado 2026-07-21, user-directed.** Card "Totais" (`gestor-comandas.tsx`)
ganhou duas coisas, pedido explícito do usuário: (1) total "Sem Pagamento
Lançado" — soma de `valor_venda` das comandas sem NENHUMA linha em
nenhuma das 8 tabelas de forma de pagamento (mesmo critério já usado no
Fechamento de Caixa, `fechamento_caixa_service._pedidos_faturados_sem_
forma_pagamento_sync` — não confundir com "Sem Documento", que é sobre
documento FISCAL, não pagamento); (2) quebra "Por Forma de Pagamento" —
soma real lançada (não o valor da comanda) em cada uma das 8 tabelas,
ordenada decrescente por valor, usando os mesmos rótulos de
`fechamento_caixa_service.TIPO_LABEL` (reaproveitado, não duplicado).
Implementado em `_list_comandas_sync` (`comanda_service.py`) via
subqueries correlacionadas por tipo — mesmo estilo já usado ali pras
outras colunas derivadas (num_nfce, num_nf, atendente_nome etc.).

---

## Gestor de Comandas

**Status: 🟡 em andamento (Fases 0-2 implementadas 2026-07-21, Fase 3 pendente).**
Migração de `FrmConCupom.frm` ("Consulta de Vendas" → "Gestor de Comandas")
e `FrmAltComNV.frm` ("Alteração de Vendas" → "Alterar Comandas"). Plano
completo em `C:\Users\carlo\.claude\plans\velvet-roaming-sparrow.md`
(aprovado pelo usuário) — ler antes de retomar.

Regra global que motivou o pacote: toda venda finalizada no sistema
(Pré-Venda de O.S., Pedido de Venda, Faturar Contratos) vira um registro
em `comanda` — Gestor de Comandas é o relatório sobre essa tabela.

### Fase 0 — Faturar O.S. (pré-requisito) — ✅ concluída
`os_service.py::_faturar_os_sync`/`faturar_os` + rota
`POST /api/os/{codigo}/faturar` + ação `OS.FATURAR`. Exige a O.S. já
Fechada (diferente do Pedido Bar, que fecha-e-fatura junto). Botão
"Faturar O.S." em `os-form.tsx`. Testado (`test_os_service.py`).

### Fase 1 — Gestor de Comandas (busca/relatório) — ✅ concluída
- **Backend**: `models/comanda.py`, `services/comanda_service.py`
  (`_list_comandas_sync`, `_get_doc_fiscal_sync`), `routes/comanda.py`
  (`POST /api/comandas`, `GET /api/comandas/{comanda}/doc-fiscal`).
  Permissão `COMANDA` (ABRIR/IMPRIMIR/EXPORTAR) em Transações.
  38 testes em `tests/unit/test_comanda_service.py` (cobre todos os
  filtros + reimpressão de doc fiscal).
- **Frontend**: `app/gestor-comandas.tsx` — filtros dentro de um
  `AccordionSection` recolhível (mesmo padrão de `pedidos.tsx`), período
  sempre nascendo em "hoje", demais filtros (com/sem nota, ordenação)
  persistidos por empresa+banco via `comandasFilters.ts`. Totais no topo
  da lista (Total Geral/ECF/NFCe/NF/Sem Documento). Cada linha: número da
  comanda e referência de Pré-Venda são clicáveis (abrem Alterar Comanda /
  Pedido/O.S. de origem), mais os ícones equivalentes ao lado (mesmos
  destinos, dois caminhos pro mesmo lugar). Ícone de reimpressão do doc
  fiscal (Nota/NFCe/Cupom) quando vinculado — reimprime os DADOS
  armazenados (protocolo, chave, valores), não é uma via fac-símile do
  documento oficial (este backend não tem gerador de DANFE/cupom real,
  mesma ressalva de `notas_fiscais_service.py`). Excel (`exportSheetsToXlsx`)
  e Impressão (`print-report-header.ts`, sem mostrar o filtro escolhido).
  Ícone de Ajuda/Modo Didático no cabeçalho. Card "Gestor de Comandas" em
  `transacoes.tsx`.

### Fase 2 — Alterar Comandas (Gravar / vendedor por item / Forma de Pagamento) — ✅ concluída, Números de Série pendente
- **Backend**: `comanda_service.py::_get_comanda_sync` (cabeçalho+itens+
  formas de pagamento já lançadas+vínculos), `_save_comanda_sync` (Gravar:
  área/atendente/atendente_dav/cliente/paga_comissao),
  `_alterar_vendedor_item_sync` (troca vendedor de 1 item, com opção de
  aplicar aos demais itens do vendedor anterior),
  `_alterar_forma_pagamento_sync` (só lançamentos de Cartão/Débito ainda
  não conciliados — campo real confirmado ao vivo é `transf_receber`,
  não existe `flag_transf_caixa` nessas duas tabelas — troca só dentro da
  mesma modalidade). Permissão `ALTERAR_COMANDA` (ABRIR/GRAVAR/FORMA_PAG/
  NUM_SERIE/CANCELAR — as duas últimas ainda sem implementação por trás).
  Rotas em `routes/comanda.py`. 38 testes cobrindo as 4 funções (parte do
  mesmo arquivo de testes da Fase 1).
- **Frontend**: `app/alterar-comanda.tsx` — só acessível a partir de um
  botão em cada linha do Gestor de Comandas (pedido explícito do usuário,
  não é uma rota solta). Cabeçalho com campos numéricos simples (código de
  área/atendente/atendente_dav/cliente) — **limitação conhecida**: não usa
  picker de busca (SelectField/ClientSearchModal), só código digitado
  diretamente; considerar trocar por busca de verdade se o usuário achar o
  código cru pouco usável na prática. Modal de troca de vendedor por item.
  Modal de troca de forma de pagamento (busca `GET /api/forma-pagamento-
  completo`, filtra pelo `tipo` do lançamento). Ícone de Ajuda/Modo
  Didático no cabeçalho.
- **Números de Série — ✅ concluído 2026-07-21.** `comanda_service.py`
  ganhou `_list_num_serie_comanda_sync`/`_add_num_serie_comanda_sync`/
  `_remove_num_serie_comanda_sync` (rotas `GET/POST /api/comandas/
  {comanda}/num-serie`, `DELETE .../num-serie/{sequencia}`) — reaproveita
  a tabela auxiliar `pecas_num_serie` já gerenciada em Tabelas Auxiliares/
  Números de Série (`FrmManNDS`, `tabelas_aux_service.py`) e os endpoints
  de busca de produto/disponibilidade já existentes (`/tabelas/num-serie/
  produtos`, `/tabelas/num-serie`) em vez de duplicar essa lógica. Vínculo
  é por COMANDA (`comanda_num_serie`), não por item/`movimentacao`
  específico — confirmado pelo schema (a tabela não tem FK pra
  `movimentacao`). Vincular marca `pecas_num_serie.disponivel=0`;
  desvincular volta pra `1`. **Validado ao vivo contra BD_PAJE**
  (autorizado pelo usuário — "banco é cópia do cliente"): inserida 1 linha
  descartável em `pecas_num_serie` (`num_serie='TESTE-NDS-001'`), rodado
  o fluxo completo listar→vincular→listar→desvincular→listar contra a
  comanda real 43856 via as funções de serviço reais (não mockadas), e a
  linha de teste foi apagada ao final — nenhum dado residual deixado.
  10 testes unitários adicionais em `test_comanda_service.py` (FakeCursor,
  não tocam banco real). Frontend: seção "Números de Série" em
  `alterar-comanda.tsx` com lista + modal de vincular (busca produto →
  lista disponíveis → toque vincula) — reaproveita `AppModal` no mesmo
  padrão dos outros dois modais da tela.

### Fase 3 — Cancelar Comanda — ✅ concluída 2026-07-21 (com escopo financeiro conscientemente reduzido)
`services/nfe_cancelamento_service.py` (cancelamento fiscal REAL junto ao
SEFAZ, evento 110111, grupo SVRS/17 UFs incl. RJ, `signxml` RSA-SHA256,
SOAP 1.2, TLS mútuo com o certificado real da empresa) foi integrado a
`comanda_service._cancelar_comanda_sync`: quando a comanda tem NF/NFCe
vinculada com `protocolo_sefaz` preenchido e situação ativa, o
cancelamento chama de verdade o SEFAZ antes de reverter qualquer coisa
localmente; se o SEFAZ recusar (ou a chamada falhar), o cancelamento
inteiro é bloqueado sem tocar em nada (nem estoque, nem financeiro) — a
checagem de bloqueio financeiro roda ANTES dessa chamada irreversível,
pra nunca cancelar no SEFAZ e só depois descobrir que o resto está
bloqueado. Sem protocolo (documento nunca emitido de verdade), só marca
`situacao='C'` localmente, sem chamar o SEFAZ. **Nunca testado contra o
SEFAZ real nem contra dados reais** (mesma ressalva de sempre — só
certificado autoassinado/rede mockada nos testes).

**Descoberta que mudou o escopo original da reversão financeira**:
confirmado ao vivo (schema real) que `duplicata_receber`/
`duplicata_rec_venc`/`receber`/`previsoes` **não têm nenhuma coluna/FK de
volta pra `comanda`** — só as 8 tabelas `comanda_*` (`transf_receber`,
bit) sabem se aquele pagamento já foi "conciliado"/transferido pro
financeiro. Sem essa ligação, apagar linhas em `duplicata_receber` etc.
seria adivinhar qual linha pertence a qual comanda — violaria a regra de
nunca implementar em cima de suposição. **Decisão tomada**: se QUALQUER
lançamento de pagamento da comanda já tem `transf_receber=1`, o
cancelamento inteiro é bloqueado com mensagem clara pedindo ajuste manual
no financeiro; só quando nenhum foi conciliado ainda é que os 8
lançamentos (`comanda_dinheiro`/`cheque`/`cartao`/`debito`/`duplicata`/
`ticket`/`vale`/`financiado`) são apagados normalmente. Mais conservador
que o texto original do plano (que previa apagar diretamente linhas de
`duplicata_receber`/`contas.saldo_atual`) — decisão de segurança, não uma
simplificação por preguiça.

**Implementado**: reversão de estoque (`pecas.qtd += qtd`, nunca mexe em
`reservado`/`reservado_os` de novo — já foram liberados no Faturar;
`movimentacao.Estornado=1`, não DELETE físico — a coluna já existia
pronta, confirmado ao vivo), reversão de `pedido_venda`/`COMANDA_PED` e
`os`/`COMANDA_OS` (volta pra situação Fechado, não Cancelado — dá pra
reabrir/corrigir e faturar de novo), liberação de números de série
(`pecas_num_serie.disponivel=1`), zerar a comanda (`situacao='C',
valor_venda=0, acrescimo=0, desconto=0`) e `INSERT INTO cancelamento`
(schema confirmado: `comanda, cupom, usuario, data, hora, motivo`).
21 testes unitários cobrindo cada bloqueio e cada branch fiscal — a maior
cobertura do pacote inteiro, como o plano original pedia.

**Frontend**: botão "Cancelar" (ícone, cabeçalho — só aparece se a
comanda ainda não está cancelada) abre modal de confirmação com motivo
obrigatório (≥15 caracteres, mesma regra do backend), mensagem de erro
com 5s de exibição quando bloqueado (regra global de mensagem
grande/importante). Modo Didático explica a ação.

**Cancelamento com devolução parcial não foi portado** (decisão já
registrada no plano) — só o "caminho normal" (nenhum item devolvido
antes) foi implementado.

**Não validado ao vivo contra BD_PAJE** (diferente de Números de Série) —
decisão deliberada: cancelar mexe em estoque/situação/pagamentos de uma
comanda HISTÓRICA REAL, mutação bem mais arriscada e difícil de desfazer
com segurança do que a inserção puramente aditiva testada em Números de
Série. A cobertura de testes unitários (com nomes de coluna já
confirmados ao vivo no schema) foi considerada suficiente sem esse risco
adicional.

**Bloqueio de nota de serviço com série específica** (mencionado no plano
original, item 1 de `CmdCancel_Click`) não foi implementado — não havia
fonte VB6 suficientemente clara nesta sessão pra confirmar a regra exata;
registrar como gap conhecido, não presumir o comportamento.

---

## Movimentações

**Status: 🟢 implementado (2026-07-18)** — Card "Movimentações" em
Transações (`app/(tabs)/transacoes.tsx`) abre o hub `app/movimentacoes.tsx`
com dois cards, ambos com tela real: **Movimentação de Produtos** e
**Requisição**.

### Movimentação de Produtos — ✅ implementada 2026-07-18

Legado: `frmEntPro.frm` ("Movimentação de Produtos", colado completo pelo
usuário). Lançamento manual avulso de entrada/saída de estoque, fora do
fluxo de Pedido/O.S./Notas Fiscais. Toda linha gravada por esta tela usa
`movimentacao.serie_nf='MV'` (convenção já em uso ao vivo no banco de
testes antes mesmo desta migração — 53 linhas históricas). Schema
(`movimentacao`, `pecas`, `tipo_mov`) conferido ao vivo em
`GERDELL`/`BARESTELA` antes de implementar.

- **Backend**: `services/movimentacao_produtos_service.py` +
  `routes/movimentacao_produtos.py` + `models/movimentacao_produtos.py`.
  18 testes unitários (`tests/unit/test_movimentacao_produtos_service.py`).
  Tela `MOV_PRODUTOS` no catálogo de permissões com ações próprias
  (`ABRIR`/`GRAVAR`/`EXCLUIR` — sem Imprimir/Exportar, não existem no
  form original).
- **Frontend**: `app/movimentacao-produtos.tsx` — formulário (Data,
  Tipo de Movimentação, Código do Produto com busca "Ajuda" +
  auto-preenchimento de descrição/preço/estoque no blur, Quantidade,
  Preço Unitário, Nº Nota Fiscal, Série fixa "MV") + botão "Incluir" +
  modal "Consultar" (filtros de período/tipo/produto + exclusão por
  linha).
- **Decisões conscientes em relação ao `.frm` original** (ver docstring
  de `movimentacao_produtos_service.py` para o detalhe completo de cada
  uma — não re-derivar do zero numa sessão futura):
  1. **"Alterar" não foi portado** — o próprio legado desabilita essa
     ação incondicionalmente (`CmdAltera_Click`: mostra aviso e sempre
     sai, sem exceção).
  2. **"Excluir" foi mantido HABILITADO**, com reversão de estoque —
     `CmdApaga_Click` do legado mostra o mesmo aviso de "função
     desabilitada", mas o `Exit Sub` que a desabilitaria de fato está
     **comentado** no código-fonte colado pelo usuário; a exclusão
     acontece na prática. Decisão baseada em precedente já existente
     neste mesmo backend (`notas_fiscais_service.py` já apaga linhas de
     `movimentacao` e reverte estoque do mesmo jeito) — não foi uma
     suposição cega, mas vale confirmar com o usuário se algum dia isso
     for questionado.
  3. **Filtro "código começa com P ou A" do Consultar** — não replicado;
     no schema atual `pecas.codigo_int` é 100% prefixo 'P' (conferido ao
     vivo) e nenhum outro service do backend usa esse filtro.
  4. **Faixa de quantidade -32767..32767** do `Critica()` do legado — era
     limite de tipo Integer/Single do VB6; as colunas atuais são
     `real`/`float`. Não replicado (ver "Não replicar truques VB6" no
     CLAUDE.md).
  5. **Baixa automática de ingredientes via tabela `receita`** quando
     tipo='E50' e `ModFatPedido` é 6 ou 41 — feature de Ficha Técnica
     amarrada a um "modelo de pedido" legado sem equivalente na
     arquitetura nova; tabela `receita` não foi citada pelo usuário no
     escopo desta tela. **Fora de escopo, não implementado.**

### `FrmManMov` — fora de escopo, tela client-exclusive

O usuário colou também `FrmManMov.frm` (mesma caption "Movimentação de
Produtos", mas um form muito maior: grid de itens acumulados numa "C.I."
antes de confirmar, import/export de arquivo texto entre lojas, aprovação
de "Requisição" em lote com `Grid4`/`Check2-4` por situação
Aberta/Fechada/Cancelada, impressão dedicada). O usuário identificou
explicitamente que **este form é usado exclusivamente por um cliente** —
não é a base desta migração (`frmEntPro.frm` é). Mantido apenas como
referência caso esse cliente específico peça a funcionalidade completa de
CI em lote no futuro — não re-derivar dele sem pedido explícito.

### Requisição — ✅ implementada 2026-07-18

Legado: `FrmManReq.frm` ("Requisição...", colado completo pelo usuário —
**não** `FrmManMov`, que continua sendo o form client-exclusive de C.I. em
lote, fora de escopo). Pedido interno de produtos/serviços, com
fechamento (baixa de estoque + grava `movimentacao` tipo `S07`/serie
`RQ`), reabertura (devolve estoque) e cancelamento. Schema (`requisicao`,
`rec_prod`, mais leitura/escrita em `pecas`/`servicos`/`movimentacao`)
conferido ao vivo em `GERDELL`/`BARESTELA` antes de implementar
(`requisicao` estava com 0 linhas nesse banco de teste).

- **Backend**: `services/requisicao_service.py` +
  `routes/requisicao.py` + `models/requisicao.py`. 27 testes unitários
  (`tests/unit/test_requisicao_service.py`). Tela `REQUISICAO` no
  catálogo de permissões com ações próprias (`ABRIR`/`GRAVAR`/`EXCLUIR`/
  `FECHAR`/`REABRIR`/`CANCELAR`/`IMPRIMIR`).
- **Frontend**: `app/requisicao.tsx` — cabeçalho (Nº/Situação/Data/
  Usuário somente-leitura + Descrição editável enquanto Aberta), inclusão
  de item (produto OU serviço, com busca "Ajuda" + auto-preenchimento de
  preço/estoque no blur, aviso — não bloqueio — quando qtd > estoque),
  lista de itens com exclusão por linha, botões Fechar/Reabrir/Cancelar/
  Imprimir (reaproveita `print-report-header.ts` + `printHtml.ts`, mesmo
  padrão de impressão já usado no resto do app) e modal "Consultar" com
  filtros de situação/período/descrição.
- **Descoberta importante ao rastrear o `.frm`**: o fluxo de autorização
  em 2 etapas do legado (`Frame6`/`Grid_Prod_Man`/`Command19`, variável
  `Autoriza` 1/2/3) é **código morto** — `PrepGrid_Prod_Man` é definida
  mas nunca chamada por nenhum botão ativo; o botão real "Fechar"
  (`Command14`) chama `FechaRequisicao` direto, sem passar por nenhuma
  etapa de autorização (o parâmetro `QtdReq` da sub nem é usado no corpo
  dela). Não implementado porque não roda nem no legado hoje — não é uma
  "regra de negócio perdida", é uma feature abandonada em código morto.
- **Fora de escopo, documentado no topo de `requisicao_service.py`**:
  NFe de Requisição/Devolução (`requisicao_config_nfe`,
  `FrmTraNFe.ImportaRequisicao` — esta migração ainda não emite NFe em
  lugar nenhum); vínculo com O.S. (`os_requisicao`, campo "Documento
  vinculado" do cabeçalho — a tela O.S. Completa desta migração também
  não existe ainda); vínculo com Projeto (`ExisteDAVProjeto` — não há
  Gestor de Projetos ligado a Requisição aqui); "senha superior" quando
  qtd > estoque (sem infra de senha de gerente — virou confirm no
  frontend, não bloqueia); "Gerar Planilha"/Excel da lista (não pedido
  explicitamente; Cilindros > Borderô já tem o padrão via SheetJS se for
  pedido depois); edição de Descrição depois que a requisição já tem
  itens (o `Command12` "Gravar" do cabeçalho do legado permite isso via
  um botão dedicado — nesta versão a Descrição só é editável enquanto
  Situação = Aberta, sem um botão de salvar isolado; escopo reduzido
  conscientemente, fácil de estender se pedido).

---

## Gestão de Compras

**Status: 🟢 MÓDULO COMPLETO (2026-07-18)** — Ressuprimento, Curva ABC e
Estoques, Cotação de Compra e Pedido de Compra implementados e
validados. Único ponto realmente pendente é o envio de Cotação por
e-mail (infra de SMTP nova, deliberadamente fora de escopo) e testes
manuais na UI (só validação via curl/testes unitários até agora). Leia
esta seção inteira antes de mexer de novo neste módulo, não repita
perguntas já respondidas pelo usuário abaixo.**

**Atualizado 2026-07-19**: todo o submenu Transações > Compra passou a ser
gateado por `controle_configuracao.Curva_abc` (coluna legada "Curva ABC",
já existia na tabela), pedido explícito do usuário ("o módulo Compras
deve ser habilitado em Configurações > Módulo Curva ABC" — não existe um
flag "Compras" separado, o flag legado dessa área inteira é literalmente
`Curva_abc`). `_modulo_curva_abc_ativo(cur)` (`pedido_common.py`), checado
no topo de todas as funções `_*_sync` dos 4 services (`curva_abc_service.
py`: 2, `gestao_compras_service.py`: 3, `cotacao_compra_service.py`: 11,
`pedido_compra_service.py`: 11 — 27 pontos ao todo). `MODULE_TELAS` mapeia
`Curva_abc` → `CURVA_ABC`/`GESTAO_COMPRAS`/`COTACAO_COMPRA`/
`PEDIDO_COMPRA`. Frontend: `moduleOn("Curva_abc")` explícito nas 5 telas
(`gestao-compras.tsx` + `curva-abc.tsx` + `gestao-compras-ressuprimento.
tsx` + `cotacao-compra.tsx` + `pedido-compra.tsx`) e no card "Gestão de
Compras" de `transacoes.tsx`. Mesmo racional de "Contratos" acima
(`moduleOn` explícito, não só `can()`, por causa do bypass de master em
`disabledTelas`).

### Pedido original do usuário

Card novo em Transações → "Gestão de Compras", com 3 sub-telas espelhando
o submenu legado "Transações > Compra" do MDI VB6:

1. **Pedido de Compra** (`FrmPedCom.frm`)
2. **Curva ABC Estoques** (`FrmCurvaABC.frm`)
3. **Gestão de Compras** (form precisou ser localizado na árvore —
   confirmado que é `FrmGesCom.frm`, pasta `Geral`)

`FrmGesCom.frm` tem uma aba "Cotação" que o usuário confirmou estar **vazia
no legado** (`Tab(1).ControlCount = 0` no `.frm` bruto — não é artefato de
renderização, nunca foi construída) e pediu para eu desenvolver essa aba do
zero, "com as informações e lógica que conseguir, afim de viabilizar a
cotação no gestor de compra junto aos fornecedores", usando como base um
conjunto de anotações manuscritas que o usuário colou (projeto futuro de
"Mapa de Cotação" — comparação de cotações entre fornecedores).

### Pivô de prioridade (decisão do usuário, meio da conversa)

Depois do pedido inicial acima, o usuário redirecionou o escopo
explicitamente:

> "a ideia era pegar os resultados com a Curva ABC, Mostrar alguns
> filtros, painel com as últimas compras, hoje o cliente precisa de um
> relatório do que precisa comprar, porque pedido de compra em si os
> clientes já aboliram, depois que temos a opção de importar o xml da
> nota fiscal de entrada."

Ou seja: **Pedido de Compra foi abandonado pelos clientes reais** desde que
a importação de XML de NF de entrada existe (essa importação em si **ainda
não foi construída** nesta migração — é trabalho futuro, não confundir com
"já existe"). O que o cliente precisa de verdade é um **relatório de
ressuprimento**: o que precisa comprar, baseado na Curva ABC + posição de
estoque + últimas compras.

Perguntei explicitamente via pergunta de múltipla escolha e o usuário
confirmou:

- **Prioridade 1**: Gestão de Compras (relatório de Ressuprimento) +
  Curva ABC e Estoques — construir agora, com telas reais.
- **Prioridade 2 (adiado)**: Pedido de Compra — só placeholder por
  enquanto.
- **Prioridade 3 (adiado)**: aba Cotação — não construir ainda.
- Confirmou também que eu deveria **investigar `FrmCotacao.frm`** antes de
  assumir que ele é a base da Cotação de Compra.

### Investigação de `FrmCotacao.frm` — CONCLUÍDA, não é o form certo

`FrmCotacao.frm` (5297 linhas, "Cadastro de Cotações") foi checado via
`Form_Load` e uso de tabelas SQL (`orcamento`, `orc_produto`, `comanda`,
`cliente`) — é um form de **orçamento/cotação de VENDA para cliente**, não
tem nenhuma relação com cotação de COMPRA junto a fornecedor. **Confirmado
irrelevante** para a aba Cotação do Gestor de Compras. As anotações
manuscritas do usuário sobre "Mapa de Cotação" continuam sendo o único
material de referência para uma futura implementação dessa aba — não há
form VB6 legado equivalente para rastrear campo-a-campo; será preciso
desenhar do zero quando for retomado.

### Diretrizes de UX dadas pelo usuário para este módulo (aplicar em toda
tela nova aqui, e não só aqui — são reforços de regras já no CLAUDE.md)

- "aplicar em todas as telas formatação de redução dos campos e botões.
  Reaproveitamento de espaços agrupando os campos um do lado do outro,
  para minimizar o tamanho da tela." — campos/botões compactos, agrupados
  lado a lado (regra já em CLAUDE.md, reforçada aqui explicitamente pro
  módulo de Compras).
- "um dos problemas da gestão de compras é que as telas é classificada
  como difícil de ser usada. quero que quebre essa percepção criando algo
  intuitivo e com informações em placeholder, tooltip e design intuitivo."
- "quero que a tela ensine o usuário a utilizá-lo. dando informações como
  se fosse um guia" — telas devem ter um tom de guia/tutorial embutido
  (texto explicativo curto, tooltips, placeholders informativos), não só
  formulário cru.
- "mensagens não técnica voltado para usuários final" — reforço da regra
  já existente (`friendly_db_error`, ver CLAUDE.md).
- "automatize o máximo os componentes de ligação, curva x gestor x pedido
  x fornecedores x entrada de nota fiscal(à ser desenvolvida)" — quer
  cruzamento automático entre Curva ABC, Gestão de Compras (Ressuprimento),
  Pedido, Fornecedores e a futura importação de NF de entrada. **Achado
  ao investigar**: nem `notas-fiscais.tsx` nem `fornecedores.tsx` aceitam
  hoje um parâmetro de deep-link (`?codigo=...`) para abrir direto um
  registro — nenhum dos dois tem `useLocalSearchParams` lendo esse tipo de
  parâmetro. Pra viabilizar link direto do painel de Ressuprimento pro
  cadastro do fornecedor (por exemplo), essas duas telas precisariam
  ganhar suporte a abrir já num registro específico — **não implementado
  ainda, é o próximo passo natural depois que Ressuprimento e Curva ABC
  estiverem prontos**, considerar perguntar ao usuário antes de expandir
  escopo dessas duas telas existentes.

### ✅ Já implementado (backend 100% pronto e testado)

- **Permissões** (`backend/services/permissoes_service.py`): menu
  `TRANSACOES > COMPRA` com 3 telas —
  ```python
  _menu("COMPRA", "Compra", [
      _tela("PEDIDO_COMPRA", "Pedido de Compra", ACOES_PEDIDO_COMPRA),
      _tela("CURVA_ABC", "Curva ABC e Estoques", ACOES_CURVA_ABC),
      _tela("GESTAO_COMPRAS", "Gestão de Compras", ACOES_GESTAO_COMPRAS),
  ]),
  ```
  `ACOES_GESTAO_COMPRAS = [ABRIR, IMPRIMIR, EXPORTAR]` (relatório
  puro, sem Gravar). `ACOES_CURVA_ABC = [ABRIR, GERAR, REPROCESSAR,
  IMPRIMIR, EXPORTAR]`. `ACOES_PEDIDO_COMPRA = ACOES_PADRAO` (reservado
  pro dia em que a tela real for construída).

- **Gestão de Compras / Ressuprimento** — `services/gestao_compras_service.py`
  + `routes/gestao_compras.py` (sem log de auditoria — é relatório
  read-only) + `tests/unit/test_gestao_compras_service.py` (13 testes).
  - `GET /api/gestao-compras/curvas` — lista valores distintos de
    `pecas.curva_abc`/`curva_abc_fin` já gravados (pra popular combos de
    filtro).
  - `GET /api/gestao-compras/ressuprimento` — lista de produtos com
    filtros: curva ABC (qtd), curva ABC (financeira), fornecedor (via
    subselect em `pecas_fornecedor`), nível (reaproveita
    `_nivel_clause()` já existente em `margem_lucro_service.py`, **não
    duplicado**), abaixo do mínimo / abaixo do ressuprimento / acima do
    máximo (checkboxes), ordenação configurável (`ORDER_MAP`). Calcula
    `prev_dia`/`prev_mes` (previsão de dias/meses até faltar, baseado em
    `cmm`/consumo médio mensal já gravado em `pecas`):
    ```python
    cmm_diario = cmm / 30
    prev_dia = int(qtd / cmm_diario) if cmm_diario and qtd >= 0 else 0
    prev_mes = int(qtd / cmm) if cmm and qtd >= 0 else 0
    ```
  - `GET /api/gestao-compras/ressuprimento/{codigo_int}/ultimas-compras`
    — junta `n_fiscal` + `n_fiscal_itens` + `fornecedor`, filtro
    `nf.mov='E01' AND nf.situacao='A'` (**decisão**: substitui o
    `Tipo_Nf=0` ambíguo do legado pela convenção já usada em
    `notas_fiscais_service.py`, `situacao='A'` = nota ativa/não
    cancelada — não re-questionar essa escolha numa sessão futura, já foi
    decidida por consistência com o resto do backend).

- **Curva ABC e Estoques** — `services/curva_abc_service.py` +
  `routes/curva_abc.py` (COM log de auditoria — só as 2 ações de
  escrita) + `models/curva_abc.py` + `tests/unit/test_curva_abc_service.py`
  (17 testes, incluindo um caso numérico completo verificando os valores
  exatos).
  - `POST /api/curva-abc/gerar` — recalcula `pecas.curva_abc`/
    `curva_abc_fin` + `percent_abc`/`percent_abc_fin` pra um período,
    tipo (financeira = `SUM(qtd*p_unit)` / quantidade = `SUM(qtd)`) e
    faixas de curva (lista de `{curva: "A", percentual: 50}...`, soma
    tem que dar exatamente 100). Fonte de vendas: `movimentacao` +
    `comanda` (join `serie_nf='CM' AND situacao='PG'` — a mesma
    convenção "vendas canônicas" já usada em `fechamento_caixa_service.py`
    e `margem_lucro_service.py`). Classificação é **por quantidade de
    ITENS proporcional à faixa configurada**, não pelo corte clássico
    80/20 por valor acumulado — rastreado com precisão de
    `FrmCurvaABC.frm`'s `Command4_Click` (ex.: 4 itens, faixa A=50% →
    `max(1, int(50*4/100))=2` itens ficam com A, o resto fica com a
    próxima faixa). Antes de gravar, reseta `pecas.curva_abc[_fin]`
    (escopo afetado) pra letra seguinte à última faixa configurada
    (ex.: faixas até "C" → reset usa "D"), preservando produtos fora do
    escopo do relatório.
  - `POST /api/curva-abc/reprocessar-estoques` — recalcula
    `consumo_medio_mensal`/`estoque_minimo`/`estoque_ressuprimento`/
    `estoque_maximo` por produto, com 4 checkboxes independentes
    (atualizar mínimo/ressuprimento/máximo/consumo — só grava as colunas
    marcadas). Fórmulas exatas (replicadas literalmente do legado, ver
    teste `test_calcula_com_prazo_direto_na_peca`):
    ```python
    meses = _numero_de_meses(data_ini, data_fim)   # mínimo 1
    cmm = int(total_vendido / meses)                # mínimo... não força mínimo 1 aqui, só se total>0
    cmm_diario = cmm / 30
    tempo_reposicao = pecas.prazo_fornecedor  # ou, se nulo, MAX(fornecedor.prazo_pgto) via pecas_fornecedor
    estoque_minimo_novo = int(cmm * grau_atendimento / 100)
    estoque_ressuprimento_novo = int(cmm_diario * tempo_reposicao + estoque_minimo_novo)
    estoque_maximo_novo = int(estoque_minimo_novo + cmm_diario) * tempo_reposicao
    ```
    **Decisão consciente**: `intervalo_ressuprimento` do legado NÃO foi
    portado — é uma variável calculada no `.frm` original mas nunca lida
    na fórmula final (dead code), não re-adicionar sem confirmar que
    alguma fórmula legada realmente a usa.

- **server.py**: routers `gestao_compras` e `curva_abc` já importados e
  incluídos (`api_router.include_router(gestao_compras.router)` /
  `curva_abc.router`, logo depois de `requisicao.router`).

- **Frontend — navegação/hub**:
  - `frontend/app/(tabs)/transacoes.tsx` — card "Gestão de Compras"
    adicionado (`route: "/gestao-compras"`, visível se `can("PEDIDO_COMPRA.ABRIR")
    || can("CURVA_ABC.ABRIR") || can("GESTAO_COMPRAS.ABRIR")`).
  - `frontend/app/gestao-compras.tsx` — hub web-only com 3 cards
    (Gestão de Compras → `/gestao-compras-ressuprimento`, Curva ABC e
    Estoques → `/curva-abc`, Pedido de Compra → `/pedido-compra`), mesmo
    padrão visual de `movimentacoes.tsx`.
  - `frontend/app/pedido-compra.tsx` — `ComingSoonScreen` placeholder,
    web-only, com mensagem explicando o motivo do adiamento (clientes já
    abandonaram + apontando pra Gestão de Compras/futura importação XML).

### ✅ Concluído nesta rodada (2026-07-18)

1. **`frontend/app/gestao-compras-ressuprimento.tsx`** — implementada.
   Bloco-guia no topo explicando o relatório; filtros compactos e
   agrupados (chips de Curva ABC Qtd/Fin, seletor de Fornecedor via modal
   de busca, seletor de Nível via `NiveisModal.tsx` reaproveitado sem
   duplicar, 3 chips Abaixo do Mínimo/Ressuprimento/Acima do Máximo cada
   um com tooltip via hover, ordenação por chips); lista compacta de
   resultado com badge de situação (Crítico/Repor/Excesso/OK) e resumo de
   contagem no topo; toque no item abre modal "Últimas Compras"; ações
   Imprimir (`print-report-header.ts`+`printHtml.ts`, reaproveitados) e
   Gerar Planilha (`exportSheetsToXlsx`, reaproveitado). Sem log de
   auditoria (relatório read-only, mesmo padrão dos demais). Validado ao
   vivo contra `GERDELL`/`BARESTELA` (`GET /api/gestao-compras/curvas` e
   `/ressuprimento` responderam corretamente).

2. **`frontend/app/curva-abc.tsx`** — implementada, duas seções/cards
   independentes como planejado: **Gerar Curva ABC** (período De/Até com
   a regra global de repetir data inicial→final, chips Por Quantidade/Por
   Valor, filtro de Nível opcional via `NiveisModal`, grid editável de
   faixas com indicador visual de soma — vermelho/verde — pré-preenchido
   com um padrão sugerido A=20/B=30/C=50 pra já dar um ponto de partida
   ao usuário, botão Gerar com `showConfirm` avisando que a classificação
   atual será sobrescrita, resultado listado com badge de curva por
   produto) e **Processar Atualização de Estoques** (período De/Até
   próprio, Grau de Atendimento com tooltip explicando o conceito, filtro
   de Nível próprio, 4 chips de seleção do que atualizar, resultado
   mostrando anterior→atual de cada campo). Cada seção tem um bloco-guia
   próprio no topo explicando a ação em linguagem de negócio. **Validado
   ao vivo** contra `GERDELL`/`BARESTELA` via `POST /api/curva-abc/gerar`
   — atenção: esse teste **gravou de verdade** a classificação
   `curva_abc`/`percent_abc` em ~339 produtos reais dessa base de teste
   compartilhada (não é destrutivo — só reclassifica um campo de
   relatório que já é recalculado por design toda vez que a tela roda —
   mas fica registrado aqui porque alterou dados pré-existentes, não
   apenas linhas de teste descartáveis).

3. **Typecheck final**: `npx tsc --noEmit` limpo nas 2 telas novas — 11
   erros no total do projeto, todos pré-existentes (o mesmo baseline de
   antes desta rodada, ver `feedback_...` sobre `colors.background`),
   nenhum erro novo introduzido.

4. **Backend reiniciado** (duplicidade de processos na porta 8081
   detectada e encerrada antes do relaunch, mesmo problema recorrente já
   documentado) — rotas novas confirmadas respondendo ao vivo.

### ✅ Cotação de Compra — implementada 2026-07-18

Construída do zero a partir de anotações manuscritas do usuário
("Compras Mapa de Cotação", datado 03/05/2013) que estavam anexadas como
fotos no histórico da sessão — **recuperadas diretamente do arquivo
`.jsonl` da conversa** (extraídas via script, sem precisar pedir ao
usuário pra reenviar nada) quando ele pediu pra continuar a aba Cotação
numa sessão já compactada. Sem `.frm` de referência — a aba "Cotações" de
`FrmGesCom.frm` nunca foi desenvolvida no legado (`Tab(1).ControlCount=0`,
confirmado antes desta sessão).

**Escopo confirmado com o usuário via pergunta direta** antes de
implementar (2 decisões que as anotações não resolviam sozinhas):
- Ao marcar o fornecedor vencedor de um item, o sistema **só registra a
  decisão** — não gera um Pedido de Compra formal (essa tela continua
  parada/placeholder nesta migração).
- **Envio da cotação por e-mail como planilha anexa** (pedido explícito
  nas anotações) ficou **fora desta rodada** — não existe nenhuma
  infraestrutura de envio de e-mail real no backend hoje (só campos de
  configuração SMTP salvos em Controle do Sistema, nunca usados pra
  enviar) — fica pra decidir depois.

**Fluxo implementado**: cria-se uma Cotação com um ou mais produtos a
cotar (situação Aberta) → lança-se manualmente a resposta de cada
fornecedor consultado por item (valor, marca, prazo, condição de
pagamento — a solicitação em si continua sendo feita fora do sistema,
por telefone/e-mail/WhatsApp) → marca-se o fornecedor vencedor por item
(destaque visual, ★) → Finaliza-se a cotação (situação Finalizada;
Reabrir/Cancelar disponíveis, mesmo vocabulário A/F/C de Requisição).
Nenhuma escrita em estoque/movimentação — é puramente decisão de compra.

- **Backend**: `services/cotacao_compra_service.py` — **3 tabelas novas**
  (não existem no schema legado, criadas sob demanda via
  `_ensure_tables(cur)`, mesmo padrão `IF NOT EXISTS ... CREATE TABLE` já
  usado em `services/whatsapp/repository.py`): `cotacao_compra`
  (cabeçalho), `cotacao_compra_item` (produto+qtd a cotar, mais
  `fornecedor_vencedor`/`valor_vencedor` quando decidido),
  `cotacao_compra_resposta` (resposta de cada fornecedor por item). Busca
  de produto (`_find_produto_sync`) já devolve as referências que as
  anotações pediam antes de cotar ("Autorização de Cotação"): custo
  médio, estoque atual, e a última compra registrada (data/valor,
  reaproveitando a mesma query de `n_fiscal`/`n_fiscal_itens` já usada em
  `gestao_compras_service.py`). `routes/cotacao_compra.py` +
  `models/cotacao_compra.py`. Tela `COTACAO_COMPRA` no catálogo de
  permissões (`ABRIR`/`GRAVAR`/`EXCLUIR`/`VENCEDOR`/`FINALIZAR`/
  `REABRIR`/`CANCELAR`/`IMPRIMIR`), dentro do menu `COMPRA`. 36 testes
  unitários novos (`tests/unit/test_cotacao_compra_service.py`) — 688
  testes no total do backend, todos passando.
- **Frontend**: `app/cotacao-compra.tsx` — mesmo padrão visual/compacto
  de Requisição (cabeçalho + inclusão de item com hint de custo
  médio/estoque/última compra + lista de itens, cada um com suas
  respostas aninhadas: menor preço destacado, vencedor com fundo verde e
  ★, botões Marcar Vencedor/Excluir por resposta) + modal Consultar +
  Imprimir (comparativo por item, reaproveitando `print-report-header.ts`/
  `printHtml.ts`). Bloco-guia no topo explicando o fluxo em linguagem não
  técnica. Card "Cotação de Compra" adicionado ao hub
  `gestao-compras.tsx`. Validado ao vivo contra `GERDELL`/`BARESTELA`
  (incluir item + consultar + excluir item + cancelar, dados 100%
  descartáveis já que as tabelas são novas desta sessão).
- **Fora de escopo, documentado no topo do service**: envio de e-mail;
  geração de Pedido de Compra; grid de compras/produtos no cadastro do
  Fornecedor (pedido pelas anotações, mas pertence a `fornecedores.tsx`,
  não a esta tela); campo de % de atraso/pontualidade do fornecedor
  (depende de um Pedido de Compra real que não existe); tela de Alçada de
  compra (aprovação por comprador/grupo de produtos — feature grande e
  separada). Duas notas soltas nas anotações manuscritas (status de
  pedido do cliente tipo "Aprovação de Crédito"; e-mail no cadastro do
  funcionário) foram deixadas de fora por não parecerem ser sobre Cotação
  de compra — provavelmente de outro projeto/anotação misturada na mesma
  leva de fotos.

### ✅ Curva ABC — presets de período (6/12/24 meses) — 2026-07-18

Pedido do usuário: junto do rótulo "Gerar Curva ABC" (e, por extensão
confirmada, também "Processar Atualização de Estoques"), 3 chips de
atalho de período — 6/12/24 meses, calculados a partir de hoje — além de
uma trava de **período mínimo de 6 meses** quando o usuário prefere digitar
as datas manualmente (motivo: período curto demais dá uma classificação/
consumo médio pouco confiável, sujeito a picos pontuais — confirmado com
o usuário). Implementado **só no frontend** (`app/curva-abc.tsx`,
`monthsBetween`/`isoMinusMonths`/`PERIODO_PRESETS`) — o backend
(`curva_abc_service.py`) não foi alterado e continua aceitando qualquer
período (a trava de 6 meses é orientação de UX, não regra de negócio
travada no backend; se o usuário pedir reforço no backend depois, é
replicar a mesma lógica de `_numero_de_meses`). Clicar num chip preenche
De/Até direto; editar manualmente uma das datas limpa a seleção do chip
(mostra que o período agora é customizado). Corrigido de passagem: a
linha "Tipo de classificação" ficava desalinhada verticalmente das datas
ao lado por causa de `rowFields`'s `alignItems: "flex-end"` — trocado
para `flex-start` (afeta as 2 únicas ocorrências de `rowFields` neste
arquivo, ambas só com coluna label+campo, sem botão solto que dependesse
do alinhamento por baixo).

### ✅ Pedido de Compra — implementada 2026-07-18

**Decisão revertida**: originalmente adiado (ver histórico acima — "os
clientes já aboliram Pedido de Compra"), o usuário pediu explicitamente
pra retomar depois de Cotação de Compra pronta. `FrmPedCom.frm` (a versão
completa, ~5.600 linhas) foi recuperado do histórico da sessão e
rastreado por completo antes de implementar — achados importantes que não
devem ser re-rastreados numa sessão futura:

- **Tabelas `pedido`/`pedido_itens` já existem no schema** (confirmado ao
  vivo em `GERDELL`/`BARESTELA`, 0 linhas) — são as mesmas tabelas usadas
  pelas variantes Revenda/ValPorto/KIFESTA do `.frm` (não há cópia na
  pasta `Geral`, mas o schema bate). Não são criadas por esta migração,
  só usadas como já estavam.
- **`pedido_itens.SEQUENCIA_PEDIDO_ITENS`** (IDENTITY) é o PK real de
  cada linha — `codigo`+`codigo_int` não é chave única (o legado permite
  o mesmo produto lançado mais de uma vez).
- **Situação**: `A` Aberto/Em Aprovação, `F` Aprovado, `C` Rejeitado —
  mesmo vocabulário A/F/C de Requisição e Cotação de Compra.
  **Divergência consciente do texto literal do legado**: o botão
  "Aprovar Pedido" (`Command21_Click`) grava `situacao='F'`, mas a
  `MsgBox` de confirmação do próprio `.frm` ainda diz "Pedido fechado com
  sucesso" — nome antigo do botão, nunca atualizado no texto. Usei o
  sentido real do botão (Aprovar), não a mensagem obsoleta. Mesma coisa
  pro "Rejeitar Pedido" (`Command9_Click`, grava `situacao='C'`).
  `R`/`RP` (recebido parcial/total) existem na tabela mas **nenhum botão
  deste `.frm` os aciona** — pertencem a uma tela de recebimento de
  mercadoria que este form não tem e que esta migração não implementa
  ainda (fica pra quando a importação de XML de NF de entrada existir).
- **"Excluir Pedido" não foi portado** — no próprio `.frm` esse botão
  está `Visible = 0 'False`, nunca aparece pro usuário (código morto,
  confirmado direto na declaração do controle).
- **"Rateio Desp/Desc"** (ratear frete/seguro/despesas/desconto
  proporcionalmente entre os itens) e **"Importar DAV"** (importar itens
  de um Pedido de Venda/Orçamento/O.S. existente, via `pedido_venda_prod`/
  `orc_produto`/`os_produto`) **não foram portados** — Orçamento nem
  existe nesta migração, e Importar DAV depende de integrações que as
  telas "Completo" ainda não têm.
- **Composição fiscal completa por item foi incluída** — decisão
  explícita do usuário via pergunta direta (2026-07-18, "já com
  composição fiscal completa" em vez de só Qtd+Preço): Base/Valor de
  ICMS, IPI (com alíquota), ICMS-ST, ISS, mais frete/seguro/despesas/
  desconto — mesmas colunas do schema legado. Fica dentro de um
  `AccordionSection` colapsado por padrão ("Impostos e Custos Adicionais
  (opcional)"), pra não pesar o caso comum de só Qtd+Preço.
- `qtd_barra`/`qtd_tijuca` (colunas existentes na tabela) **não usadas**
  — nomes de filial de um cliente específico antigo (gambiarra, não
  regra de negócio geral — ver "Não replicar truques VB6"). `frete_fora`/
  `tipo_pedido`/`enviado`/`exportado` também não usados, sem regra de
  negócio clara documentada no trecho do `.frm` disponível.
- **"Histórico do pedido"** implementado como log textual simples,
  append-only, na coluna `pedido.resumo` (`_append_resumo` no service) —
  só o texto exibido na tela; quem fez o quê já é coberto pelo log de
  auditoria padrão.

**Backend**: `services/pedido_compra_service.py` + `routes/pedido_compra.py`
+ `models/pedido_compra.py`. Tela `PEDIDO_COMPRA` no catálogo de
permissões com ações próprias (`ABRIR`/`GRAVAR`/`EXCLUIR`/`APROVAR`/
`REJEITAR`/`REABRIR`/`IMPRIMIR` — substituindo o `ACOES_PADRAO` genérico
que estava reservado). 39 testes unitários novos
(`tests/unit/test_pedido_compra_service.py`) — 727 testes no total do
backend.

**Frontend**: `app/pedido-compra.tsx` substituiu o `ComingSoonScreen`
placeholder. Cabeçalho completo (Fornecedor via busca com autofill de
Prazo a partir de `fornecedor.prazo_pgto`, Pedido Fornecedor, Prazo,
Forma de Pagamento, Transportadora, Previsão de Entrega, Aos Cuidados,
Tipo de Frete CIF/FOB, Obs., Histórico do pedido em `AccordionSection`),
itens com edição inline (toque no item abre o mesmo formulário de
inclusão preenchido, "Salvar Alterações" no lugar de "Incluir"),
Aprovar/Rejeitar/Reabrir, Consultar (situação/período/termo), Imprimir
(reaproveita `print-report-header.ts`/`printHtml.ts`) e **Anexos** via
`GestorDocumentosSection` — grava como anexo do **Fornecedor**
(`GESTOR_DOC_GRUPO_FORNECEDOR=2`), sub-grupo "Pedidos de Compra"
resolvido dinamicamente via `POST /api/gestor-documentos/sub-grupos`
(get-or-create) na primeira abertura — **não hardcoded** como o
`GESTOR_DOC_SUBGRUPO_PEDIDO=2` do Pedido Bar (aquele já existia no
legado com ID conhecido; este sub-grupo é novo, então o ID pode variar
por banco de dados).

Validado ao vivo contra `GERDELL`/`BARESTELA` (rotas GET respondendo
corretamente) — **não há fornecedor cadastrado nessa base de teste**, o
fluxo completo de criar pedido→incluir item→aprovar não pôde ser
exercitado ponta-a-ponta ao vivo (só via os 39 testes unitários com
mocks). Considerar testar manualmente numa base com fornecedores reais.

### 🔴 Ainda pendente

1. **Deep-link entre telas** (item "automatize o máximo os componentes de
   ligação") — avaliar com o usuário se vale a pena adicionar suporte a
   `?codigo=...`/`?fornecedor=...` em `notas-fiscais.tsx` e
   `fornecedores.tsx` pra permitir que o painel de "Últimas Compras" do
   Ressuprimento/Cotação e o Anexos do Pedido de Compra linkem direto pro
   registro. Não iniciado.

2. **Envio de Cotação por e-mail** — confirmado fora de escopo por
   enquanto; retomar só se o usuário pedir explicitamente, já que envolve
   construir infraestrutura de SMTP real nova.

3. **Teste manual na UI** (abrir Ressuprimento, Curva ABC, Cotação e
   Pedido de Compra no navegador, exercitar os fluxos de ponta a ponta)
   — ainda não feito nesta rodada, só validação de contrato via curl
   direto nas rotas + typecheck limpo + testes unitários.

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
- **NCM/CEST são campos de texto livre** — o legado abre uma tela dedicada
  de busca (`FrmCesNCM`, via `Command31_Click` em `FrmManPec.frm`) contra
  as tabelas `NCM`/`NCM_CEST`, que não foi migrada. Confirmado 2026-07-29
  ao tentar reaproveitar essa busca pro Cadastro de Produtos: **nenhuma
  rota de backend existe pra `NCM`/`NCM_CEST`** ainda (`backend/routes` não
  tem `/ncm`/`/cest`) — é preciso criar o lookup do zero (endpoint +
  provavelmente popular a tabela `NCM` com a tabela oficial da Receita, que
  tem milhares de linhas — não é uma tabela auxiliar pequena tipo
  Origem/Unidade de Medida). Ícone de busca já adicionado no campo NCM
  (`produto-completo.tsx`, ao lado de "Classificações Fiscais") mas mostra
  "ainda não disponível" — mesma UX de "Variações de Preços"/"Preço por
  Quantidade". Baixa prioridade, mas registrar aqui caso o usuário peça
  depois — não é um esquecimento, é escopo genuinamente maior que os
  outros lookups já portados.
- **Botão de busca "CST IPI" é código morto no próprio legado** — o botão
  com tooltip "Códigos de CST de IPI" (`Command8`, ao lado de CST IPI
  Entrada/Saída/Enquadramento em `FrmManPec.frm`) **não tem nenhum
  `Command8_Click` implementado** no form (confirmado por busca — só
  `Command7_Click`/`Command9_Click` existem) e nenhum `FrmCstIpi` existe no
  projeto. Ou seja, mesmo no VB6 o botão nunca funcionou. Por isso os 3
  campos (`cst_ipi_entrada`/`cst_ipi_saida`/`ENQUADRAMENTO_IPI`) foram
  portados como texto livre simples, SEM ícone de busca — replicar o botão
  morto seria pior que não ter nada (usuário clicaria esperando algo
  acontecer). Se o usuário pedir busca aqui no futuro, é feature nova, não
  um gap de migração.
- **🟢 Preço por Quantidade / Variações de Preços (Promoções) implementados,
  2026-07-29** — os 2 ícones da aba Dados Principais/card Preços
  ("Preço por Quantidade" e "Variações de Preços") que antes mostravam
  "ainda não disponível" agora abrem modais reais. Rastreados em
  `Geral\frmvalqtd.frm` (`pecas_preco_qtd`, colunas `codigo_int/qtd/
  p_venda`) e `Geral\FrmValPro.frm` (`pecas_promocao`, colunas `sequencia/
  codigo_int/qtd/p_venda/codigo_promocao/descricao_promocao`) — nenhuma
  cópia dessas telas existe em `Kontacto\`, só em `Geral\`. Backend:
  `produto_completo_service.py` (`list/save/delete_preco_qtd`,
  `list/save/delete_promocao`) + rotas em `routes/produto_completo.py`
  (`/produto-completo/{codigo}/preco-qtd`, `/produto-completo/{codigo}/
  promocoes`, ambos com sub-rota `/excluir`). Frontend:
  `PrecoQtdModal`/`PromocaoModal` em `produto-completo.tsx`.
  - **"Código Promoção" NÃO é um agrupador multi-produto real** — confirmado
    no rastreio: é auto-gerado como `"{codigo_int}-{sequência}"` quando
    deixado em branco, e a grid do legado filtra só por `codigo_int` —
    nenhuma outra tela do Kontacto lê/agrupa por esse código entre produtos
    diferentes. Funciona hoje só como rótulo sequencial por produto. Se o
    usuário pedir "promoção que baixa o preço de vários produtos juntos"
    no futuro, isso é feature NOVA (schema/regra que não existe no
    legado), não uma correção de algo mal portado.
  - **Preço por Quantidade (`pecas_preco_qtd`) segue NÃO aplicado
    automaticamente** — no legado, é consumida por `frmtraorcnv.frm`/
    `frmmanpedEPAtuacao.frm` (telas de orçamento/pedido aplicam o preço
    escalonado por quantidade), mas o Pedido Bar/Geral desta migração
    ainda não aplicam esse preço ao incluir item — só o cadastro foi
    portado. Se o usuário pedir "o pedido já aplica o preço por quantidade
    sozinho", é trabalho novo (mesmo padrão do que foi feito pra Promoção
    logo abaixo — provavelmente dá pra reaproveitar boa parte do mesmo
    mecanismo, `_preco_promocional`/`verificarPromocao`/endpoint
    `preco-promocional`), registrar como pendência própria quando pedido.
  - Sem validação de duplicidade/faixa ascendente em nenhuma das duas
    (mesmo comportamento do legado — só valida quantidade > 0).
  - **🟢 Extensão 2026-07-29, user-directed, SEM precedente no legado**:
    `pecas_promocao` ganhou período opcional e combinável — dias da semana
    (`dias_semana`, string "0,1,2..6" onde 0=domingo), intervalo de data
    (`data_inicio`/`data_fim`, `DATE`) e intervalo de hora (`hora_inicio`/
    `hora_fim`, `NVARCHAR(5)` "HH:MM"). Colunas criadas via migração
    idempotente (`_ensure_promocao_periodo_cols`, mesmo padrão de
    `_ensure_qtd_pessoas_col` em `pedido_common.py`) — não existiam no
    legado, `FrmValPro.frm` só tinha quantidade/preço/código promoção.
    Tudo em branco = sem restrição nesse critério (comportamento anterior
    preservado).
  - **🟢 Aplicação automática no Pedido implementada, 2026-07-30,
    user-directed** ("aplicar as regras de dias/período/hora da Promoção
    ao incluir item no Pedido geral e bar e futuros pedidos que
    criarmos"). Escopo: só `pecas_promocao` (Variações de Preços) — Preço
    por Quantidade continua pendente, ver item acima. Centralizado pra
    cobrir automaticamente qualquer Pedido futuro que reaproveite o mesmo
    hook/helper, não só Bar/Geral:
    - Backend: `pedido_common._preco_promocional(cur, codigo_int, qtd)` —
      resolve a linha de `pecas_promocao` aplicável agora (checa
      dias_semana/data_inicio-fim/hora_inicio-fim, todos opcionais e
      combináveis; entre várias que batem no período, prefere a de maior
      `qtd`, mesmo critério de tier de Preço por Quantidade — decisão
      desta implementação, sem precedente no legado pra desempate). Novo
      endpoint `GET /api/produtos/{codigo}/preco-promocional?qtd=`
      (`produtos_service.preco_promocional`) — usado pelo frontend, não
      pelo próprio `_add_item_sync`/`_add_item_completo_sync` (ver decisão
      de design abaixo).
    - **Decisão de design**: o preço promocional é uma SUGESTÃO automática
      no campo "Valor unitário" do "Confirmar Item", não um valor travado
      no backend — o atendente continua podendo digitar por cima, igual a
      qualquer outro preço no sistema hoje (não existe precedente de campo
      de preço travado nesta migração). Por isso a aplicação mora no
      FRONTEND (`usePedidoItens.ts`: `verificarPromocao`, chamada ao
      escolher o produto e de novo — debounce 400ms — sempre que a
      quantidade muda; só reescreve o campo se o valor atual ainda for o
      último sugerido automaticamente, `autoValorRef`, pra nunca
      sobrescrever um valor que o atendente já editou manualmente), não no
      backend — `_add_item_sync`/`_add_item_completo_sync` não foram
      alterados. Aviso visual "Promoção aplicada: <descrição>" no
      `AddItemModal.tsx` quando ativo (`promoStyles.badge`).
    - Cobertura: `AddItemModal.tsx`/`usePedidoItens.ts` (fluxo "Confirmar
      Item" — Pedido Bar `pedido-form.tsx`, Pedido Geral `pedido-geral.tsx`,
      e o picker `produtos.tsx`, todos via o mesmo hook) E o quick-add "+"
      de `usePedidoItens.quickAddItem`/`PainelPedidoCard.tsx` (atalho de
      1 clique do Painel de Pedidos, Bar) — os dois caminhos de inclusão
      de item batem na mesma checagem, pra não dar preço diferente pro
      mesmo produto+quantidade só por ter sido incluído por um atalho
      diferente.
    - **Fora do escopo desta rodada**: O.S. (`os-form.tsx` não usa
      `usePedidoItens`, tem fluxo próprio — não tocado, usuário só pediu
      Pedido); e-mail/qualquer notificação de promoção ativa; qualquer
      indicação de promoção na tela de BUSCA de produto (antes de
      escolher) — só aparece depois de escolhido, no "Confirmar Item".
    - **Não testado ao vivo** (sem promoção com período cadastrada em
      nenhuma conexão de teste disponível nesta sessão) — revisar
      timezone/relógio do servidor SQL (`GETDATE()`, base de todo o
      cálculo de dia/hora) antes de confiar em produção se algo parecer
      errado (ex.: promoção "hoje das 18h-22h" não aparecendo/aparecendo
      fora de hora).
- Múltiplos códigos de barra por produto (`codbarra_auxiliar`) não
  migrados — só um campo de código de barras, como no screenshot do
  usuário. Fora de escopo por ora (usuário não pediu).
- `orc_produto`/`pedido_venda_prod`/`os_produto`/`nf_recebimento_itens` são
  checados na exclusão via `try/except` silencioso (se a tabela não
  existir numa instalação específica, não bloqueia a exclusão por isso) —
  revisitar se algum cliente relatar exclusão indevida de produto com
  movimentação real que essa lista não cobriu.
- **Tipo Preço (`politica_preco`) só configura, não executa** (adicionado
  2026-07-29, user-directed) — campo virou combobox "Entrada"/"Controlado"
  na aba Dados Principais, explicado pelo usuário: "Entrada" recalcula o
  preço do produto automaticamente a cada entrada no Recebimento de
  Produto; "Controlado" mantém o preço manual. **O Recebimento de
  Produto/entrada de estoque em si ainda não foi migrado** — quando for,
  checar esse campo e implementar o recálculo automático condicionado a
  ele (não implementado ainda, é só a configuração).

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

**Status: 🟡 Pedido Geral (ex-Pedido Completo) Fases A e B implementadas
(núcleo + número de série + m² + Clínica/Agenda); O.S. Completa e Fases
C-F do Pedido Geral ainda não iniciadas.**

**Atualização 2026-07-20, user-directed**: "Pedido Completo" foi renomeado
**"Pedido Geral"** — arquivo/rota `pedido-completo.tsx`/`/pedido-completo`
viraram `pedido-geral.tsx`/`/pedido-geral` (permissão `PEDIDO_COMP` e
endpoints de backend `/api/pedido-completo/...` continuam com o nome
antigo por enquanto, decisão à parte). A lista deixou de ser compartilhada
com o Pedido Bar: `pedidos.tsx` agora é exclusiva do Bar, e uma tela nova
`pedido-lista.tsx` passou a ser a lista compartilhada de toda versão de
Pedido fora do segmento Bar (hoje só o Geral, mas pensada pra futuras
versões — "vamos ter 2 ou mais versões de tela de Pedido", cada uma
podendo ganhar sua própria versão mobile simplificada mais adiante). Ver
CLAUDE.md > "Transações Screens Strategy" > "Atualização 2026-07-20" pro
detalhe completo. **As menções a "Pedido Completo"/`pedido-completo.tsx`
no restante desta seção (histórico anterior a 2026-07-20) não foram
reescritas** — refletem o nome vigente na época de cada entrada; ler
como "Pedido Geral" mentalmente ao revisitar.

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
  `controla_num_serie` — 🟢 **implementado 2026-07-27** (ver seção "Pedido
  Geral — Fase B: número de série" abaixo; é o que desbloqueia a
  unificação do Cilindro); módulo m² — 🟢 **precificação implementada
  2026-07-30** (rateio/impressão completa/etiquetas ficam pra depois, ver
  seção "Pedido Geral — Metro Quadrado" abaixo); módulo Clínica — 🟢
  **Agenda completa implementada 2026-07-28** (ver seção própria abaixo).
  Fase B está completa nos 3 sub-módulos originalmente previstos.
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

### Pedido Geral — Metro Quadrado / Clínica: módulo registrado (2026-07-27); comportamento de precificação m² 🟢 implementado (2026-07-30)

**Pedido do usuário**: "Os módulos Clinica e Metro Quadrado são variações
do Pedido de Venda. Usa a mesma tela com características próprias" —
confirmado que, junto com Bar/Cilindro/Pedido de Venda, formam um grupo de
**5 segmentos mutuamente exclusivos** da mesma tela "Pedido Geral"
(`pedido-geral.tsx`, tela `PEDIDO_COMP`). Registro do módulo (mutua
exclusividade em Módulos e Recursos + `PEDIDO_COMP` habilitado se qualquer
um dos 3 estiver ligado) implementado 2026-07-27. Pedido explícito do
usuário: "não mexer no pedido de Bar" (reforçado de novo em 2026-07-30,
"Pedidos bar não contempla m2") — nada em `pedidos.tsx`/`pedido-form.tsx`/
`itens_service.py` foi tocado em nenhuma das duas rodadas.

#### Precificação m² — implementada, 2026-07-30, user-directed ("aplique a Fase B do módulo Metro Quadrado")

Duas dúvidas de negócio que travavam a Fase B foram resolvidas nesta
sessão lendo o código-fonte VB6 diretamente (`mdl_proc.bas`,
`frmmanpedfor.frm`, `FrmGerCon.frm`):

- **Heurística "nome da empresa contém TELA" liga Metro Quadrado —
  NÃO portada.** Achada em `frmmanpedfor.frm:11785-11805`, no mesmo bloco
  de hacks hardcoded por nome de empresa específica (`"KLIFER"`,
  `"NUCLEO"`, `"CAPRIXO"`, `"GUERENGASES"`) — patch de instalação de um
  cliente, não regra de negócio (ver "Não replicar truques VB6").
- **As "6 áreas mínimas por tipo de preço" não são 6 valores de área
  diferentes** (suposição errada do rastreio original, corrigida agora) —
  são 6 **flags booleanas** (`m2_area_minima_padrao/modelado/engenharia/
  modelado_engenharia/comum_lapidacao/comum_sem_lapidacao`), cada uma
  decidindo só **se** aquele tipo de preço aplica o piso de área mínima
  **compartilhado** (`metro_quadrado_minima_metragem`, default 0,25).
  Achado extra: essa configuração inteira (as 6 flags + o piso + o flag
  "controla cabeça de chapa") **já estava implementada em Controle do
  Sistema** (`controle-sistema.tsx:1003-1012`) antes desta sessão — só
  nunca tinha sido consumida por nenhuma tela de venda.

**Decisão de arquitetura** (documentada com mais detalhe no código): o
total de uma linha m² no legado é `qtd_pedida × AreaPreco(...) × p_venda`
(3 fatores, repetidos em ~25 pontos diferentes do `.frm` — grade,
fechamento, impressão, rateio). Este app centraliza o total do item em UM
lugar só (`_item_total`/`_recalc_pedido_total`, `qtd × p_venda`). Em vez
de replicar a fórmula de 3 fatores por todo o sistema, a área é calculada
uma vez ao incluir o item e **dobrada dentro do preço unitário**
(`p_normal = preço_do_tipo × área_calculada`) — `area_venda` continua
sendo gravada na linha, mas só como dado de auditoria/exibição, nunca
como multiplicador ativo em nenhuma conta.

**Implementado**:
- `pedido_common.py`: `_arredonda_pbox`/`_area_preco` (réplica de
  `ArredondaPBox`/`AreaPreco`, `mdl_proc.bas:11969`/`12004` — os dois
  ramos, com e sem "controla cabeça de chapa"), `_trunca3` (mesmo idioma
  de `_trunca2` já usado em `inventario_service.py`),
  `_modulo_metro_quadrado_ativo` (não bloqueia como os outros módulos —
  só decide se o item entra pelo caminho m² ou pelo normal, réplica do
  `Else` do legado), `_config_m2` (lê os 8 campos de `controle_aux`),
  `TIPOS_PRECO_M2` (os 6 tipos: índice, rótulo, coluna de preço em
  `pecas`, flag de área mínima correspondente).
- `pedido_completo_service._add_item_completo_sync`: quando
  `pecas.uni` do produto é M2/ML/M3 **e** o módulo está ligado, exige
  `tipo_preco_m2`+`comprimento`+`largura`, resolve o preço pela coluna do
  tipo escolhido (`p_venda`/`p_sugestao`/`p_garantia`/`p_sugerido`/
  `preco_base`/`preco_lista` — só oferece tipos com valor > 0, mesmo
  filtro do legado), calcula a área e grava `p_normal`/`p_venda` já
  multiplicados, mais `comprimento`/`largura`/`area_venda`/
  `comprimento_chapa`/`largura_chapa` na linha (colunas legadas de
  `pedido_venda_prod` — **assumidas existentes, não confirmadas contra um
  schema real nesta sessão**, mesma suposição que já funcionou pra
  `cod_num_serie`). `_list_itens_completo_sync` enriquecida com essas 3
  dimensões (mesmo padrão do Nº de Série, sem duplicar a query base).
- Novos endpoints: `GET /produtos/{codigo}/tipos-preco-m2` (tipos
  disponíveis pro produto) e `GET /produtos/{codigo}/preco-m2-preview`
  (preview do valor calculado, reaproveita `_area_preco`/`_config_m2` —
  usado pelo frontend enquanto o usuário digita, pra não duplicar a
  matemática em JS).
- `ItemSaveRequest` ganhou `tipo_preco_m2`/`comprimento`/`largura`/
  `comprimento_chapa`/`largura_chapa` (todos opcionais).
- **Frontend** (`usePedidoItens.ts`/`AddItemModal.tsx`/`ItemList.tsx` —
  compartilhados por Bar e Geral, mas o comportamento só ativa quando
  `unidade` do produto é M2/ML/M3 **e** a tela é `PEDIDO_COMP`, mesmo
  padrão do Nº de Série com `isPedidoComp`/`exigeNumSerie`): "Confirmar
  Item" troca o campo "Valor unitário" (digitação livre) por um seletor
  de tipo de preço (rádio, com o preço de cada um) + campos Comprimento/
  Largura (e Comprimento/Largura de Chapa, só visíveis se
  `vidro_controla_cabeca_chapa` vier ligado) + preview ao vivo (debounce
  300ms) da área calculada e do valor final. Produto m² não pode pular
  pelo atalho "+" de adição rápida (precisa passar por "Confirmar Item"),
  mesma regra do Nº de Série. `ItemList.tsx` mostra "· C x L m" na
  descrição compacta do item quando presente. Modo Didático
  (`AJUDA_PEDIDO_GERAL_ITENS`) ganhou item explicando os campos.
- Testes: `TestArredondaPBox`/`TestTrunca3`/`TestAreaPreco` (puros, em
  `test_services.py`) + `TestAddItemCompletoM2` (6 casos, em
  `test_pedido_completo_service.py`) — 1182 testes de backend passando
  (excluindo as 67 falhas pré-existentes de Gestão de Compras, não
  relacionadas). `tsc --noEmit` sem novos erros nos arquivos tocados.

#### Itens que ficaram de fora — completados na rodada seguinte (2026-07-30, mesmo dia, user-directed "pode implementar o que ficou de fora")

- **🟢 `AreaEstoque` vs `AreaPreco` (baixa de estoque)** — implementado.
  `_area_estoque` (réplica de `AreaEstoque`, `mdl_proc.bas:12103` — área
  bruta, sem arredondamento nem piso) somada a `pedido_common.py`.
  `_fechar_pedido_itens` agora baixa `qtd_pedida × área_estoque` pra item
  m² (`comprimento`/`largura` gravados), continua baixando só por
  `qtd_pedida` pra item normal — sem mudança. 2 testes novos
  (`TestFecharPedidoItensEstoqueM2`, `test_pedido_common_forma_pagamento.py`,
  usando monkeypatch em `_fecha_fpag_dav`/`_mover_estoque` pra isolar só a
  lógica de estoque).
- **🟢 Rateio/Desconto Geral — checkbox "aceita desconto"** — implementado,
  mas **generalizado pra TODO item, não só m²**: o rateio proporcional já
  usado por `_aplicar_desconto_geral_sync` (`p_normal × qtd`, base do peso
  de cada item) na real já incide corretamente sobre o valor de m² (que já
  vem com a área dobrada no `p_normal`, ver decisão de arquitetura acima)
  — **não precisou de um "passo extra" pra m² como a suposição original
  desta seção presumia**, o `DESCONTO_ANTERIOR`/pulo de arredondamento do
  legado era só um artefato da fórmula de 3 fatores que este app não
  replica. O que faltava de verdade era `pecas.aceita_desconto` não ser
  respeitado pelo Desconto Geral (só bloqueava desconto de ITEM avulso,
  nunca o geral) — corrigido: item com `aceita_desconto=False` fica de
  fora da base e nunca recebe desconto no rateio geral, pra qualquer
  Pedido/produto, não só m². 5 testes novos (`test_descontos_service.py`,
  novo arquivo — não havia nenhum teste unitário de
  `_aplicar_desconto_geral_sync` antes).
- **🟢 Impressão — dimensão no recibo** — `ReciboPedidoModal.tsx` mostra
  "C x L m" tanto no recibo completo (`it.itens.forEach`) quanto no ticket
  de item único (impressão automática por Finalidade). `ItemPrintData`
  ganhou `comprimento`/`largura` opcionais. **Não** foram recriados os
  formatos de impressão específicos do legado (48-col/Vidro A4) — só o
  recibo já existente (`ReciboPedidoModal`) ganhou a informação, que é o
  único mecanismo de impressão de pedido que existe nesta migração hoje.
- **🟢 Editar item m² já incluído** — implementado. Nova
  `pedido_completo_service._update_item_completo_sync` (rota PUT do Pedido
  Geral passou a chamar essa em vez de `itens_service.update_item`, que
  continua servindo o Pedido Bar sem mudança) — reconhece item m²
  (`comprimento`/`largura` não-nulos na linha atual) e recalcula a área ao
  editar; item normal segue exatamente o comportamento antigo. **O tipo de
  preço usado originalmente não é persistido em nenhuma coluna** (mesmo
  comportamento do legado, resolvido e descartado na hora) — o atendente
  sempre reescolhe o tipo ao reabrir "Editar Item" num item m² (comprimento/
  largura vêm pré-preenchidos, tipo não). Frontend:
  `EditItemModal.tsx`/`usePedidoItens.ts` ganharam o mesmo seletor de tipo
  + preview do "Confirmar Item", só que sem os campos de chapa (Comprimento/
  Largura de Chapa) — simplificação deliberada da edição, os avançados
  continuam editáveis só reincluindo o item. 4 testes novos
  (`TestUpdateItemCompletoM2`).
- **🔴 Botão "Etiquetas" — investigado, NÃO implementado.** Achado ao
  rastrear `Command21_Click` (`frmmanpedfor.frm:7771`, botão Caption
  "&Etiquetas", Tag "Emitir Etiquetas" — confirmado que é o botão certo):
  **o handler inteiro está comentado no código-fonte legado** (`Sub
  Command21_Click() ' ... tudo comentado ... End Sub` — literalmente vazio
  em produção, clicar nesse botão hoje no VB6 não faz nada). O botão que
  de fato imprime alguma coisa é outro, `Command24_Click`, que chama
  `Imp_Etiq` — mas isso está ligado a `Frame9`/campos `Etiq(0..2)` com
  máscara de DATA ("  /  /    "), sugerindo uma etiqueta de
  validade/fabricação (rastreabilidade), não uma etiqueta de dimensão m²
  como a pendência original presumia — nunca confirmado porque `Imp_Etiq`
  em si não foi localizado/lido. **Não implementado por falta de regra
  real a portar** (mesmo princípio de "Nunca implementar regra de negócio
  em cima de suposição") — se o usuário quiser uma etiqueta de item m²
  mesmo assim, é uma feature NOVA (sem precedente funcional no legado),
  precisa de decisão explícita sobre o conteúdo/formato antes de
  implementar, não uma migração.

  **📌 Pendência registrada — Etiqueta de item m², 2026-07-30,
  user-directed** ("coloque etiqueta de item m² como pendência m2"):
  fica como pendência própria do módulo Metro Quadrado, não fechada nem
  descartada — só bloqueada até o usuário decidir o conteúdo/formato,
  já que não há regra do legado pra copiar (ver achado acima). Perguntas
  em aberto antes de implementar:
  - Conteúdo da etiqueta: código do produto, descrição, dimensão
    (comprimento x largura), valor unitário, algo mais (nº do pedido,
    cliente, data)?
  - Tamanho físico/formato de impressão (etiqueta pequena tipo impressora
    térmica de código de barras, ou papel comum)?
  - Uma etiqueta por peça (repete `qtd_pedida` vezes) ou uma por item de
    pedido, independente da quantidade?
  Quando o usuário responder, implementar reaproveitando
  `src/utils/printHtml.ts` (mesmo padrão de `ReciboPedidoModal.tsx`, ver
  "Impressão via iframe, não CSS hide" no CLAUDE.md) — endpoint de dados já
  existe (`GET /api/pedidos/{pedido}/itens` já traz `comprimento`/
  `largura`/`area_venda` por item), não precisa de rota nova, só o
  componente de impressão em si.

**Não testado ao vivo** (sem conexão com módulo Metro Quadrado disponível
nesta sessão, em nenhuma das duas rodadas) — primeiro passo ao retomar:
confirmar que `comprimento`/`largura`/`area_venda`/`comprimento_chapa`/
`largura_chapa` realmente existem em `pedido_venda_prod` num schema real,
depois um ciclo completo (produto m² → Confirmar Item → tipo+dimensões →
preview → gravar → Fechar → conferir baixa de estoque por área → Editar
Item → reabrir pedido → conferir valor e "Detalhe" na grade e no recibo
impresso).

**Implementado agora**:
- `SEGMENTOS_PEDIDO_EXCLUSIVOS` (`controle_config_service.py` e
  `modulos-recursos.tsx`) passou de 3 para 5 itens: `Bar`, `Cilindro`,
  `Pedido_venda`, `metro_quadrado`, `CLINICA` (colunas já existentes em
  `controle_configuracao`, já estavam na lista `CAMPOS` — só não entravam
  no grupo exclusivo nem no gating de tela).
- `disabled_telas()` (`permissoes_service.py`) e o espelho no frontend
  (`permissions/index.tsx`) corrigidos: como `MODULE_TELAS` só consegue
  expressar "E" (desliga a tela se QUALQUER módulo mapeado estiver off),
  adicionada uma correção explícita — `PEDIDO_COMP` só fica no
  `disabledTelas` se **nenhum** dos 3 (Pedido_venda/metro_quadrado/CLINICA)
  estiver ligado, igual ao padrão já usado pra O.S. (Oficina OU
  Assistência). Sem essa correção, `PEDIDO_COMP` ficaria sempre desabilitado
  quando Metro Quadrado ou Clínica fosse o módulo ativo (só "Pedido_venda"
  está mapeado em `MODULE_TELAS`).
- Esse gap foi descoberto porque o bug original relatado pelo usuário
  (master vendo "Pedido Bar" e "Pedido de Venda" juntos no menu Transações
  mesmo com só um módulo ligado) revelou que `can()` bypassava
  `disabledTelas` pro master — corrigido antes desta mudança (ver commit/
  sessão do mesmo dia, `frontend/src/permissions/index.tsx`).

**Rastreio campo-a-campo do `frmmanpedfor.frm` (`Geral\frmmanpedfor.frm` —
única cópia populada na árvore; `Kontacto\frmmanpedfor.frm` é 0 bytes),
pronto pra quando a Fase B for retomada — não re-derivar do zero:**

Ambos os flags (`Dados_Controle_Configuracao.Clinica` /
`.Metro_Quadrado`) são membros de `Type_Controle_Configuracao`
(`mdl_proc.bas`), carregados uma vez por sessão de `controle_configuracao`.

**Clínica** — 16 ocorrências no form, resumo por efeito:
1. **Impressão usa relatório totalmente diferente**: `ImprimeClinicaPed35`
   (`mdl_proc.bas:26770`) no lugar de `ImprimePed35`/`ImprimeFotoPed35`
   quando Clínica está ligada.
2. **Itens de Serviço (código começa com "S") não agrupam quantidade**:
   ao incluir um serviço com Qtd > 1, em vez de 1 linha com
   `qtd_pedida=N`, o legado insere **N linhas separadas** (`For QTDCLINICA
   = 1 To Campo(4)`), cada uma com `qtd_pedida=1` — pra permitir agendar
   cada unidade individualmente depois. Fora de Clínica, é sempre 1 linha
   só (comportamento atual do Pedido Geral, correto pra manter).
3. **Botões extras no cabeçalho, escondidos fora de Clínica**: "Layouts"
   (`Command77`, abre `FrmPreLay` — seletor de layout de impressão
   genérico) e "Agendar" (`Command78`, abre `FrmMarAge` — tela de
   agendamento, consulta `servicos`/`especialidades` dos itens do
   pedido).
4. **Colunas extras na grade**: "Agendamento" e "Profissional" (grid cols
   17/18) só aparecem em Clínica — populadas ao reabrir um pedido salvo
   via JOIN `AGENDA`/`AGENDA_PEDIDO`/`FUNCIONARIOS` (data/hora + 
   `nome_guerra` do profissional), com a linha pintada de verde se
   `SITUACAO_ATENDIMENTO = "ATENDIDO"` ou vermelho caso contrário.
5. Checkbox de impressão `Check17` ("Não imprimir unitários") some
   quando Clínica está ligada (única diferença de opções de impressão).

**Metro Quadrado (m²/vidro)** — duas variáveis em jogo: o flag global
(`Dados_Controle_Configuracao.Metro_Quadrado`, da tabela) e uma cópia
local no form (`Metro_Quadrado`, `Dim` de módulo) que combina o flag
global **OU** uma heurística por nome da empresa (`InStr(UCase(fantasia),
"TELA")` — cliente do ramo de vidro/tela cujo nome contém "TELA" liga o
modo mesmo com o flag desligado; não confirmado se essa heurística deve
ser portada ou é gambiarra pontual de um cliente específico — perguntar
antes de assumir).
1. **Campos Comprimento/Largura só ficam editáveis em m²**: ao selecionar
   um produto cuja unidade (`pecas.uni`) é `M2`/`ML`/`M3`, os campos
   ficam visíveis sempre mas só `.Enabled` quando Metro Quadrado está
   ligado.
2. **Seletor de 6 tipos de preço por m²**: ao escolher um produto m² com
   o módulo ligado, abre uma lista (`ListPrecos`) com 6 opções — Padrão,
   Modelado Comum, Engenharia, Comum (S/Lapidação), Modelado Engenharia,
   Comum (C/Lapidação) — cada uma lendo uma coluna de preço distinta de
   `pecas` (`p_venda`, `p_sugestao`, `p_garantia`, `p_sugerido`,
   `preco_base`, `preco_lista`) **e** sua própria área mínima faturável
   configurada (`m2_area_minima_padrao`, `m2_area_minima_modelado`, etc.
   — variáveis globais não localizadas ainda, provavelmente em
   `controle`/`controle_aux`).
3. **Precificação sempre por área calculada, nunca pela quantidade
   digitada** — `AreaPreco(comprimento, largura, area_minima, tipo_
   arredondamento, comprimento_chapa, largura_chapa)` (`mdl_proc.bas:
   12004`) é a função central; quando Metro Quadrado está ligado, o
   arredondamento respeita tamanhos padrão de chapa de vidro (quebras em
   1.8/2.4/3.21m — ver função `ArredondaPBox`, não localizada nesta
   passada). Fora de m², é `trunca3(comprimento*largura)` puro.
4. **Coluna "Localização" da grade vira "Detalhe"** (mostra a dimensão
   `(largura x comprimento)` calculada em vez do texto de
   localização/estoque) quando Metro Quadrado está ligado.
5. **Checkbox extra**: "Incidir Somente nos produtos que aceitam
   desconto" (`Check77`) só visível (e pré-marcada) em modo m² — usada no
   fechamento por valor total (rateio) pra decidir quais itens recebem o
   ajuste de desconto.
6. **Botão "Etiquetas" (`Command21`)** só visível em modo m² — impressão
   de etiquetas por item.
7. **Passo extra no rateio de desconto** (`Command37_Click`, "Fechar por
   Valor Total"): em modo m², roda um `UPDATE` de
   `DESCONTO_ANTERIOR=DESCONTO` e recarrega o pedido (`ChamaPedido`) antes
   de calcular o rateio proporcional — passo que não existe fora de m².
   E, dentro do próprio rateio (`Descontos:`), o passo final de "aplicar
   diferença de arredondamento no primeiro item" é pulado inteiramente em
   modo m² (`If Metro_Quadrado Then Return`) — o arredondamento já é
   tratado dentro do `AreaPreco`.
8. Impressão: `Metro_Quadrado` é passado como parâmetro `M2` pras mesmas
   funções de impressão do Clínica (`ImprimePed35`, `ImprimeVidroA4`,
   etc.) — controla se o relatório mostra a dimensão calculada em vez de
   texto de garantia/localização.

**Dúvidas em aberto pra quando a Fase B for retomada** (não assumir,
perguntar antes de portar):
- A heurística "nome da empresa contém TELA" liga Metro Quadrado — portar
  como regra real, ou é gambiarra de um cliente específico do legado (ver
  "Não replicar truques VB6" no CLAUDE.md)?
- Onde ficam configuradas as 6 áreas mínimas por tipo de preço
  (`m2_area_minima_*`) — que tabela/tela as define hoje no legado?
- `ArredondaPBox` (arredondamento pra tamanho padrão de chapa) precisa ser
  localizada/traçada antes de portar o cálculo m² fiel.

### Pedido Geral — Fase B: Clínica (Agendamento) — 🟢 Agenda completa implementada, 2026-07-28

**Status atualizado (mesmo dia, sessão seguinte)**: o usuário pediu
explicitamente o escopo COMPLETO ("faça ser completo então"), superando a
escolha anterior de "núcleo enxuto" — grade semanal visual, agendamento
avulso (cliente novo + serviço, direto da grade), Situação do Atendimento
(13 estados), Revisão/Garantia, Descartáveis, Hora Chegada/Saída, Troca de
Profissional (com autorização de gerente/supervisor/master), Anexos
(Gestor de Documentos), Motor de Formulário Dinâmico (Cadastro de Layout +
Preenchimento) e Faturar avulso (1 forma de pagamento, reaproveitando a
estrutura de Forma de Pagamento existente) — tudo implementado. Ver "Agenda
completa — implementado" logo abaixo pro detalhe; a subseção "Núcleo
enxuto" original fica registrada por trás dela como histórico (tudo que
ela cobria continua funcionando, apenas foi ampliado). Resto desta seção
é o rastreio VB6 que fundamentou a implementação.

#### Agenda completa — implementado (2026-07-28, mesma sessão)

- **Backend**: `agenda_service.py` reescrito por completo —
  `_list_grade_sync` (grade semanal, réplica de `MontaHorarios`, um dia por
  vez com slots livre/ocupado/pausa/ausente), `_verificar_garantia_sync`
  (Revisão/Garantia via `servicos.prazo_garantia`/`tipo_garantia` — 1=Anos,
  2=Dias, 3=Horas, 4=Meses, 5=Km, réplica de `RetornaGarantia`,
  `mdl_proc.bas:13468`; Km não é validável por data, só sinaliza),
  `_salvar_agendamento_sync` ampliado (situação/revisão/descartáveis/horas,
  cobre tanto o fluxo vinculado a um item de Pedido quanto o avulso — agora
  aceita `codagenda` pra reagendar um avulso já existente também),
  `_trocar_profissional_sync` (filtra por `controla_agenda=1` +
  especialidade + revalida disponibilidade no novo profissional),
  `_faturar_avulso_sync` (bloqueia se vinculado a Pedido/O.S. ou já
  faturado; usa o novo tipo `DAV_AGE` em `pedido_common.py` —
  `_ensure_agenda_forma_pag_tables` cria as 8 tabelas `agenda_dinheiro`/
  `agenda_cheque`/etc. sob demanda —, reaproveita `_fecha_fpag_dav` sem
  alteração, grava `comanda`+`movimentacao`(S01)+`agenda_comanda`, réplica
  reduzida de `GeraComanda` sem emissão fiscal). `_list_profissionais_agenda_sync`
  ganhou `servico` opcional — sem serviço, lista TODO profissional com
  `controla_agenda=1` (usado pelo seletor da grade, que precisa listar
  profissionais antes de qualquer serviço estar em contexto).
- **Motor de Formulário Dinâmico**: novo `services/layout_service.py` +
  `routes/layout.py` — CRUD de `layout`/`layout_campos` (só o modo "grade de
  campos", `estilo_layout=0`; RTF livre fora de escopo), `layout_tipo_campo`
  como lookup, e Possíveis/Preenchidos/Preencher sobre `layout_entidade`/
  `layout_preenchido` (`FrmPreLay2.frm`, 82% comentado no legado, usado como
  especificação funcional — decisão explícita do usuário). Pra Agenda
  (`entidade=8`, sem coluna própria em `layout`), Possíveis é resolvido por
  junção com `layout_servico`/`layout_profissional` do agendamento. Achado e
  corrigido durante os testes: `_save_layout_sync` tinha um bug real (não
  um teste mal escrito) — a coluna `profissional` nunca entrava no dict de
  flags gravados, porque `_ENTIDADE_COLUNA` (usado tanto pra montar esse
  dict quanto pro mapeamento entidade→coluna genérico) não inclui 8/Agenda
  nem, por tabela, a própria coluna `profissional`; toda chamada a
  `_save_layout_sync` quebrava com `KeyError: 'profissional'`. Corrigido
  computando a lista de colunas do dict separadamente
  (`_ENTIDADE_COLUNA.values() + ["profissional"]`).
- **Faturar avulso**: forma de pagamento "GARANTIA"/"REVISÃO" já cadastrada
  na tabela `forma_pagamento` (confirmado por screenshot do usuário) cobre
  o caso de atendimento marcado Revisão/Garantia (valor zerado, forma
  "GARANTIA" fecha o Faturar sem cobrança) — não foi necessário nenhum
  mecanismo especial de "faturamento gratuito".
- **`ItemRow.agendamento`/enriquecimento em `_list_itens_completo_sync`**
  ganhou `codagenda` (antes só data/hora/profissional/situação) — necessário
  pro botão Trocar Profissional (`POST /api/agenda/{codagenda}/trocar-profissional`)
  e pra Anexos/Layouts (`referencia`/`codentidade`), que precisam do código
  do agendamento, não só do item de pedido.
- **Frontend**:
  - `AgendarModal.tsx` (item vinculado a Pedido) ampliado com Situação (13
    estados, `SelectField`), checkbox Revisão/Garantia + botão "Verificar
    garantia" (`GET /api/agenda/garantia`), Descartáveis (valor+obs), Hora
    Chegada/Saída, e 3 ícones novos no cabeçalho do modal (`IconButtonWithTooltip`):
    Anexos, Formulários (Layouts) e Trocar Profissional (abre um seletor
    inline de novo profissional + `AuthorizationSlide` antes de confirmar).
    Sem Faturar aqui — item vinculado a Pedido sempre fatura pelo próprio
    Pedido.
  - Novo `frontend/src/components/agenda/` — `AnexosAgendamentoModal.tsx`
    (clone de `AnexosPedidoModal.tsx`, `cod_grupo=1`/`cod_sub_grupo=16`,
    ver pendência de confirmação abaixo), `LayoutPreenchimentoModal.tsx`
    (Possíveis/Preenchidos + grade de campos texto-livre, campo calculado
    exibido desabilitado/sem resolução ao vivo — fora de escopo), e
    `AtendimentoAvulsoModal.tsx` (superset do `AgendarModal.tsx` — busca de
    Serviço, busca de Cliente com "Cadastrar novo cliente" via
    `criar_agendamento=1` em `cliente-form.tsx`, e o botão Faturar
    completo com lista de forma de pagamento, mesmo padrão visual do
    "Faturar" do Painel de Pedidos).
  - `cliente-form.tsx` ganhou o clone exato do padrão `criar_pedido=1`:
    `criar_agendamento=1` + `agenda_funcionario`/`agenda_data`/
    `agenda_hora`/`agenda_servico` — ao Gravar um cliente novo vindo desse
    fluxo, cria o agendamento avulso na hora (`POST /api/agenda/avulso`) e
    volta pra `/agenda`.
  - Nova tela `frontend/app/agenda.tsx` — seletor de Profissional +
    navegação de semana (Anterior/Hoje/Próxima) + grade (linhas=horário,
    colunas=dia da semana, células livre/ocupado/pausa/ausente, clique
    abre `AtendimentoAvulsoModal` em modo novo ou edição). Modo Didático
    (ícone "i" no cabeçalho, `AjudaPedidoModal` reaproveitado com conteúdo
    próprio).
  - Nova tela `frontend/app/layout-cadastro.tsx` — Cadastro de Layout
    completo (lista + form com checkboxes de entidade + gestão de Campos
    por layout, tudo num único modal por simplicidade — sem tela separada
    de campos). Web-only, tela compacta sem abas (mesmo padrão de
    `fornecedores.tsx`).
  - `transacoes.tsx` ganhou o card "Agenda" (`moduleOn("CLINICA") &&
    can("AGENDA.ABRIR")`, rota `/agenda`).
- **Permissões + auditoria**: telas `AGENDA` (ações
  ABRIR/GRAVAR/TROCAR_PROF/FATURAR/ANEXOS/LAYOUTS) e `LAYOUT`
  (ABRIR/GRAVAR/EXCLUIR) no catálogo, dentro de TRANSACOES/TABAUX
  respectivamente. Toda rota de escrita de `routes/agenda.py` e
  `routes/layout.py` grava em `log_auditoria` (`tela="AGENDA"`/`"LAYOUT"`,
  comandos `AGENDAR`/`GRAVAR`/`TROCAR_PROF`/`FATURAR`/`EXCLUIR` —
  `TROCAR_PROFISSIONAL` teve que ser encurtado pra `TROCAR_PROF` por causa
  do limite real da coluna `permissoes.comando nvarchar(15)`, achado pela
  própria asserção de `_tela()` em `permissoes_service.py`).
- **Testes**: `test_agenda_service.py` reescrito do zero (38 testes —
  grade, garantia, salvar avulso e via-pedido, trocar profissional,
  faturar avulso, listar profissionais com/sem serviço). Novo
  `test_layout_service.py` (19 testes — CRUD de layout/campos, Possíveis
  genérico e Agenda, Preenchidos, get/preencher novo e existente). Suíte
  completa: 1084 passando (fora as 67 falhas pré-existentes de Gestão de
  Compras/Cotação/Curva ABC/CNAB Itaú, confirmadas não relacionadas —
  dependem só de `_modulo_curva_abc_ativo`, não tocado nesta rodada).
  `tsc --noEmit` limpo em todos os arquivos tocados (os mesmos 12 erros
  pré-existentes em arquivos não relacionados continuam, confirmados
  inalterados antes/depois).
- **Não testado ao vivo** (sem conexão de teste disponível nesta sessão) —
  nenhum fluxo desta rodada (grade, avulso, troca de profissional,
  garantia, layouts, faturar avulso) foi exercitado contra um banco real.

#### Pendências abertas (não bloqueiam, registradas por completude)

- ~~Confirmar `cod_sub_grupo=16` (Anexos da Agenda, grupo Cliente) contra uma
  conexão de teste real~~ — **✅ confirmado pelo usuário, 2026-07-28**:
  `cod_sub_grupo=16` está correto (valor do código-fonte VB6), não o `14`
  visto antes contra um banco de teste diferente. `AnexosAgendamentoModal.tsx`
  segue como está, sem alteração necessária.
- **Integração com O.S. Assistência Técnica** — o backend já é genérico
  (`AGENDA`/`AGENDA_PEDIDO`/`AGENDA_OS`, a mesma tabela `AGENDA` já suporta
  o vínculo `AGENDA_OS`), mas não há tela "O.S. Completa" neste app pra
  ligar ainda (ver "Transações Screens Strategy" no CLAUDE.md — só o
  scaffolding existe). Repetir o mesmo padrão de
  `pedido_completo_service.py`'s enriquecimento de `agendamento` quando essa
  tela for construída.
- **Motor de Layout**: modo RTF livre (`estilo_layout=1`, editor de texto
  com tags tipo `[[Nome do Cliente]]`), impressão do preenchimento,
  comparação/"Análise" entre preenchimentos, foto por webcam, e resolução
  AO VIVO de campo calculado (soma/subtração/multiplicação/divisão entre 2
  campos — hoje aparece desabilitado com aviso em vez de calcular errado)
  — todos fora desta rodada.
- `tipo_garantia=5` (Km) não é validável automaticamente por data — Agenda
  não rastreia odômetro, só sinaliza "não verificável" no
  `GET /api/agenda/garantia`.
- Nenhum fluxo foi testado ao vivo contra um banco real (ver acima).

---

#### Núcleo enxuto — implementado (histórico, 2026-07-28, sessão anterior — superado pelo escopo completo acima)

Escopo "núcleo enxuto" (escolhido pelo usuário via `AskUserQuestion`, entre 3
opções — réplica completa da grade de Agenda ficou fora NAQUELE momento)
implementado antes do pedido de escopo completo, no mesmo dia: desdobramento
de item de Serviço em N linhas + fluxo de Agendar (modal, sem grade semanal
de disponibilidade, validado no backend) + colunas Agendamento/Profissional
na listagem + impressão. Tudo isso continua funcionando — foi ampliado, não
substituído.

#### Núcleo enxuto — implementado

- **Backend**: `pedido_common._modulo_clinica_ativo` (clone de
  `_modulo_servicos_ativo`, lê `controle_configuracao.CLINICA`). Novo
  `services/agenda_service.py` + `routes/agenda.py`
  (`GET /api/agenda/profissionais`, `GET/POST /api/agenda/item/{codauto}`,
  `POST /api/agenda/item/{codauto}/cancelar`) — módulo desacoplado de
  `pedido_completo_service.py` (Agenda é conceito genérico no legado).
  `AgendarItemRequest` novo em `models/schemas.py`. Nova ação
  `PEDIDO_COMP.AGENDAR` em `ACOES_PEDIDO_COMP`.
  `pedido_completo_service._add_item_completo_sync` ganhou o branch de
  desdobramento (item de Serviço + Clínica ativa → N linhas, `qtd_pedida=1`
  cada, mesmo padrão de código já usado pro branch de kit — nenhuma
  duplicação da lógica de desconto/custo). `_list_itens_completo_sync`
  enriquecida com `item.agendamento` (mesmo padrão do `num_serie`).
  `funcionarios_service.py` ganhou `Controla_Agenda` (coluna
  `FUNCIONARIOS.CONTROLA_AGENDA` já existia no banco, nunca exposta por
  nenhuma tela nossa até agora — sem ela nenhum profissional apareceria
  elegível).
- **Simplificações deliberadas** (vs. o legado completo, ver "Fora de
  escopo" mais abaixo): sem cliente avulso (sempre o cliente do próprio
  pedido); sem lifecycle de 13 estados de `SITUACAO_ATENDIMENTO` — só
  "Confirmado" (ao agendar/reagendar) e "Desistência" (ao cancelar);
  `SITUACAO_CAIXA` sempre 'A' (sem faturamento avulso via Agenda); campo
  "Revisão" não portado (propósito desconhecido no legado); grade semanal
  de disponibilidade substituída por validação sob demanda no backend
  (disponibilidade/pausa/ausência/capacidade de encaixe), retornando
  mensagem de erro clara se o horário escolhido não servir.
- **Frontend**: `pedido/types.ts`'s `ItemRow.agendamento`. `usePedidoItens.ts`
  ganhou `agendarItem`/`setAgendarItem` (busca profissionais elegíveis ao
  abrir), `salvarAgendamento`/`cancelarAgendamento`, `master` como novo
  parâmetro (mesmo padrão de `classe` já existente). Novo
  `AgendarModal.tsx` (tier "confirmação pontual", 420px) — Profissional
  (`SelectField`) + Data/Hora (`WebDateField`). `ItemList.tsx`: tag
  `calendar-outline` por linha de Serviço (mesmo padrão visual do
  `imprimirItemTag`) + texto "· Agendado: DD/MM às HH:MM (Fulano)" na
  descrição do item, ambos gated por
  `tela==="PEDIDO_COMP" && moduleOn("CLINICA")`. `ReciboPedidoModal.tsx`
  (preview JSX + `buildHtml`) mostra a mesma informação por linha ao
  imprimir. `AjudaPedidoModal`/Modo Didático do Pedido Geral ganhou a
  entrada "Agendar". `funcionario-completo.tsx` ganhou o switch "Controla
  Agenda" (Cadastro de Funcionários).
- **Testes**: `backend/tests/unit/test_agenda_service.py` (novo — 15
  testes: elegibilidade de profissional, disponibilidade/pausa/ausência,
  capacidade de encaixe, criar/reagendar/cancelar) +
  `TestAddItemCompletoClinica`/`TestListItensCompletoEnriquecidoAgendamento`
  em `test_pedido_completo_service.py`. 1103 testes de backend passando
  (excluindo as 67 falhas pré-existentes de Gestão de Compras, não
  relacionadas). `tsc --noEmit` limpo nos arquivos tocados (erros
  pré-existentes em outros arquivos não relacionados, confirmados
  inalterados). Backend confirmado importando/registrando as 3 rotas novas
  sem erro (`python -c "import server"`).
- **Não testado ao vivo** (sem conexão de teste com o módulo Clínica
  disponível nesta sessão) — fluxo completo (ligar módulo → marcar
  "Controla Agenda" + especialidade/horário num funcionário → cadastrar
  Serviço com especialidade → incluir no Pedido Geral com qtd>1 → conferir
  N linhas → Agendar uma linha → conferir coluna/impressão → Cancelar
  Agendamento) fica pendente de validação manual na próxima sessão com
  acesso a uma conexão de teste.

#### Fora de escopo daquela rodada — TODOS implementados na rodada seguinte (ver "Agenda completa" acima)

- ~~Grade semanal de disponibilidade (calendário visual `FrmMarAge2.frm`).~~
  ✅ `app/agenda.tsx`.
- ~~Troca de profissional pós-agendamento~~ ✅ `_trocar_profissional_sync` +
  `AuthorizationSlide`. ~~motor de Layouts (formulário dinâmico
  `FrmPreLay.frm`)~~ ✅ `layout_service.py` (modo grade de campos; RTF livre
  segue fora). ~~foto por webcam~~ continua fora (não pedido). ~~Excel/
  impressão da própria agenda~~ continua fora (não pedido). ~~Faturamento
  avulso via Agenda~~ ✅ `_faturar_avulso_sync`.
- Dúvidas do rastreio abaixo (filtro de `controla_agenda` em Troca de
  Profissional — **respondida: SIM**, confirmado pelo usuário; par grupo/
  sub-grupo de Anexos da Agenda — **respondida e confirmada: `cod_grupo=1`/
  `cod_sub_grupo=16`**, validado contra conexão de teste real) foram todas
  respondidas e confirmadas nesta sessão.

---

**Rastreio VB6 original (fundamentou a implementação acima):**

**Status: 🟡 rastreio VB6 completo, implementação não iniciada.** Feito via 2
subagentes em paralelo + arquivos colados diretamente pelo usuário
(`FrmAtende.frm`, e o conteúdo real de `FrmMarAge2.frm` sob o nome
`FrmMarAge2.txt`). Escolhido pelo usuário via `AskUserQuestion` como o
primeiro sub-módulo de Clínica a atacar (dos 2 restantes — Clínica e Metro
Quadrado — Clínica foi escolhido por não ter dúvidas de negócio bloqueantes,
diferente de Metro Quadrado que tem 3 perguntas em aberto, ver seção acima).

#### Mapa de arquivos — achado crítico, corrige suposição inicial

- **`FrmMarAge.frm` (o arquivo com esse nome) está órfão/morto** — nenhum
  `.vbp` da árvore o referencia (`Form=` nunca aponta pra ele), e sua `Sub
  Chama()` (sem parâmetro) não bate com o call site real
  (`FrmMarAge.chama Agenda_PreVenda.Codigo`, 1 argumento). É uma revisão
  anterior do formulário, com "criar/confirmar agendamento" embutido no
  próprio form.
- **`FrmMarAge2.frm`** (mesmo `Attribute VB_Name = "FrmMarAge"` do arquivo
  órfão — é a revisão nova da MESMA classe) é o que roda em produção de
  fato. Nele, a lógica de criar/editar UM agendamento específico foi
  extraída pra um terceiro form.
- **`FrmAtende.frm`** ("Marcação de Atendimento") — não estava no escopo
  original pedido, mas é indispensável: é onde o INSERT/UPDATE real de
  `AGENDA` acontece. `FrmMarAge2.frm` nunca grava em `AGENDA` diretamente,
  só abre `FrmAtende` (`Agenda_Click`, col=1 → `IniciaAtendimento` /
  col=2 → `CarregaAtendimento`).
- **`FrmPreLay.frm`** (689 linhas) é o form real do botão "Layouts"
  (`Command77`) — **não** `FrmPreLay2.frm` (3605 linhas, órfão, não
  referenciado por ninguém além do próprio `.vbp`, apesar de mais completo).

#### Botão "Agendar" (Command78) — o que ele realmente abre e faz

`Command78_Click` (`frmmanpedfor.frm:10945`) valida pedido não-cancelado +
ao menos 1 item de Serviço com especialidade vinculada, seta só
`Agenda_PreVenda.Codigo = <número do pedido>` e chama
`FrmMarAge.chama Agenda_PreVenda.Codigo` → `CarregaPedido(Pedido)` (o
mesmo código para O.S. é `CARREGAOS`, ramo decidido por `Agenda_PreVenda.Tipo`).

**Fluxo completo** (grid da Agenda → clique numa célula → `FrmAtende` →
volta e vincula):

1. `CarregaPedido` popula um grid `PedidoItens` — 1 linha por item de
   Serviço do pedido (`JOIN servicos`), já mostrando Data/Hora/Profissional
   se algum agendamento já existe pra aquele item (via `AGENDA_PEDIDO`+
   `AGENDA`+`FUNCIONARIOS`).
2. Clicar numa linha de `PedidoItens` monta a lista de profissionais
   habilitados pra aquela especialidade e desenha o grid `Agenda`
   (calendário semanal por profissional) via `Command1_Click`/`MontaHorarios`.
3. `MontaHorarios` monta 1 linha por slot de horário (baseado em
   `funcionarios_horarios.disp_ini/disp_fim` + intervalo), cruzando:
   - **Ausência** (`funcionarios_ausencias`, por período de datas+hora) →
     slot vermelho, bloqueado.
   - **Pausa** (`funcionarios_horarios.pausa_ini/pausa_fim`) → slot
     vermelho, bloqueado.
   - **Ocupação existente** (`AGENDA` daquele funcionário+data+hora, exceto
     `situacao_atendimento='Desistência'`) → colore conforme capacidade.
   - **Capacidade de encaixe**: `funcionarios_horarios.encaixe` = quantos
     agendamentos além de 1 cabem no mesmo slot; excedente bloqueia
     completamente ("Não é permitido fazer novos agendamentos neste mesmo
     horário!").
4. Clicar numa célula **livre** (col=1) → bloqueia se o item já tem
   agendamento ("Já existe agendamento para este item! Só são permitidas
   alterações"); senão abre `FrmAtende.IniciaAtendimento(funcionario, data,
   hora, 0)` — modo criação, com Cliente/Serviço/Valor pré-travados (vêm do
   item do pedido).
5. Clicar numa célula **ocupada** (col=2) → abre
   `FrmAtende.CarregaAtendimento(codagenda)` — modo edição; bloqueia edição
   se `SITUACAO_ATENDIMENTO='Atendido'` sem permissão elevada
   (`Command120.Enabled`/`PermissoesAgendamento`).
6. `FrmAtende.Command3_Click` ("Gravar") faz o INSERT/UPDATE real em
   `AGENDA` (ver schema abaixo), revalida capacidade de encaixe,
   seta `Agenda_PreVenda.CodAgenda` e fecha (`Unload Me`).
7. **O vínculo final acontece em `Form_Activate` de `FrmMarAge2`** (disparado
   ao `FrmAtende` fechar e o foco voltar): apaga vínculo anterior daquele
   item (`DELETE FROM AGENDA_PEDIDO WHERE CODPEDIDO=<codauto>`), insere o
   novo (`INSERT INTO AGENDA_PEDIDO(CODPEDIDO, CodAgenda)`, onde
   `CODPEDIDO` — apesar do nome — guarda `pedido_venda_prod.codauto`, o
   ITEM, não o número do pedido/header), e propaga
   `UPDATE pedido_venda_prod SET data_servico=<agenda.data>,
   executor_agenda=<agenda.funcionario> WHERE codauto=<codauto>` — **são
   exatamente essas 2 colunas que `frmmanpedfor.frm` lê pras colunas
   "Agendamento"/"Profissional" da grade em modo Clínica** (confirma o
   achado anterior).

#### Regras de negócio reais a portar

1. Item de pedido só pode ter 1 agendamento ativo por vez; reagendar apaga
   o vínculo antigo antes de criar o novo.
2. Capacidade de encaixe por profissional/dia/slot (`funcionarios_horarios.
   encaixe`), validada tanto na criação quanto na alteração do agendamento.
3. Disponibilidade cruza `funcionarios_horarios` (expediente+pausa, por dia
   da semana) e `funcionarios_ausencias` (períodos de férias/afastamento).
4. Profissional só é oferecido se `FUNCIONARIOS.controla_agenda=1`,
   `situacao='A'`, e vinculado via `FUNCIONARIO_ESPECIALIDADES` à
   especialidade do serviço sendo agendado.
5. `SITUACAO_ATENDIMENTO` (13 estados livres — Aguardando, Em Atendimento,
   Atendido, Desistência, Não Confirmado, Confirmado, Avaliação, Avaliado,
   Chamando, Ausente, Medicar, Medicado, Encaminhar, Encaminhado — texto
   livre, sem tabela de lookup): "Atendido" bloqueia edição sem permissão
   elevada; **"Desistência" desfaz o vínculo** — zera
   `pedido_venda_prod.data_servico`/`executor_agenda` e apaga a linha de
   `AGENDA_PEDIDO`, liberando o item pra reagendar do zero.
6. Data mínima = hoje, só na criação (edição de agendamento já passado é
   permitida).
7. Valor default do atendimento sugerido de `servicos.valor_hora`, editável.
8. Campo "Descartáveis" (consumíveis do atendimento,
   `AGENDA.AGENDA_dESCARTAVEL`/`AGENDA_OBS_DESCARTAVEL`) auto-sugerido de
   `produtos_compostos` (BOM do serviço), só no atendimento NOVO.
9. **Desdobramento em N linhas** (`frmmanpedfor.frm:8241-8280`, dentro de
   `Command1_Click` — o mesmo botão "Gravar" do cabeçalho também inclui o
   item digitado, não existe botão "Incluir Item" separado neste form):
   quando `Left(Campo1,1)="S"` (código do produto = Serviço) e Clínica
   ativo, insere N linhas de `pedido_venda_prod` (uma por unidade de
   quantidade digitada), cada uma com `qtd_pedida=1` — **sem exceção
   encontrada** (busca ampla por flag "agendável"/"não agendável" em
   `servicos` não achou nada). O loop **não grava nada em `AGENDA`/
   `AGENDA_PEDIDO`** — só cria as linhas "vazias"; o agendamento real
   (passo 1-7 acima) é feito depois, via "Agendar". Motivo de negócio
   confirmado: 1 linha (`codauto`) = 1 sessão agendável = 1 slot de agenda
   — a impressão (ver abaixo) depende exatamente dessa granularidade.
10. **Impressão** (`ImprimeClinicaPed35`, `mdl_proc.bas:26770`) é um fork
    quase idêntico de `ImprimePed35` (não um relatório totalmente
    diferente, como a suposição inicial registrada antes deste rastreio
    dizia) — mesma estrutura, com blocos `If Clinica Then` já embutidos em
    ambas as funções. Quando o item é Serviço e Clínica ativo, a tabela de
    itens ganha 2 colunas extras "Data"/"Profissional", buscadas ao vivo
    por linha via `AGENDA`/`AGENDA_PEDIDO`/`FUNCIONARIOS` (mesmo JOIN do
    passo 7) — funciona porque cada linha tem seu próprio `codauto`/
    agendamento individual, graças ao desdobramento do item 9.

#### Correção ao rastreio anterior — botão "Layouts" NÃO é sobre impressão

O `FrmPreLay` (real, ver mapa de arquivos acima) é um **motor de formulário
dinâmico genérico** (perguntas/respostas configuráveis por template,
compartilhado por Cliente/Fornecedor/Funcionário/Produto/Serviço/O.S./
Agenda/Pedido — não exclusivo de Clínica), mais próximo de uma "ficha de
anamnese" do que de um seletor de layout de impressão. **Confirmado que não
afeta a impressão do pedido em nada** — zero ocorrências de
`layout_preenchido`/`layout_entidade` em `ImprimePed35`/`ImprimeClinicaPed35`.
O que é exclusivo de Clínica é só a **visibilidade do botão** (`Command77`),
gateado pelo mesmo `Dados_Controle_Configuracao.Clinica` do botão "Agendar".
Tabelas: `layout`, `layout_campos`, `layout_tipo_campo`, `layout_entidade`,
`layout_preenchido` (schema completo no relatório do subagente, sessão
2026-07-28).

#### Schema de `AGENDA` (INSERT real em `FrmAtende.frm`)

`AGENDA_OBS_DESCARTAVEL, AGENDA_dESCARTAVEL, funcionario, cliente,
cliente_nome, cliente_telefone, data, hora_ini, hora_fim, servico, obs,
valor, revisao, encaixe, data_agenda, hora_agenda, usuario_agenda,
situacao, HORA_CHEGADA, HORA_SAIDA, SITUACAO_ATENDIMENTO, SITUACAO_CAIXA,
VALOR_ORIGINAL, DESCONTO, acrescimo` — `cliente=0` + `cliente_nome`/
`cliente_telefone` preenchidos = cliente avulso (não cadastrado, texto
livre). `encaixe` é calculado pelo código (não digitado). `situacao` (não
confundir com `SITUACAO_ATENDIMENTO`) sempre grava `'A'`, não usado em mais
nada encontrado. `SITUACAO_CAIXA` ('A'/'P'/'R' = Aberto/Pago/Revisão) é
atualizado por um fluxo de **Faturar avulso do agendamento** (`FrmAtende`'s
`Command111`/`GeraComanda`) — independente do Faturar do Pedido, bloqueado
se o agendamento já está vinculado a uma pré-venda (exatamente o nosso
caso — ver "Fora de escopo provável" abaixo).
`AGENDA_PEDIDO(CODAGENDA, CODPEDIDO)` — `CODPEDIDO` guarda o `codauto` do
ITEM, não o pedido; `AGENDA_OS(CODAGENDA, CODOS)` mesma ideia com
`os_produto.cod_os_prod`.

#### Dúvidas em aberto (não implementar sem confirmar)

1. ~~`TrocaFuncionario` (troca de profissional de um agendamento já feito,
   `FrmMarAge2.frm:4751`) não filtra por `controla_agenda=1`~~ — **✅
   respondida pelo usuário, 2026-07-28: SIM, filtrar por
   `controla_agenda=1`** (o legado não filtrar ali foi tratado como bug do
   legado, não regra a replicar). Implementado em
   `_trocar_profissional_sync` (`agenda_service.py`).
2. ~~`Command39_Click` (Anexos) usa `GestorDocumentos.Grupo=0`/`.sub_grupo=
   "AGENDAMENTOS"` (string), mas a query que CONTA anexos no mesmo arquivo
   usa `cod_grupo=1 AND cod_sub_grupo=16` (numérico)~~ — **✅ respondida e
   confirmada, 2026-07-28: `cod_grupo=1`/`cod_sub_grupo=16`** (usuário
   escolheu o valor do código-fonte VB6 e confirmou contra conexão de
   teste real). Implementado em `AnexosAgendamentoModal.tsx`.
3. ~~Campo "Revisão" (`AGENDA.revisao`) — propósito real desconhecido~~ —
   **✅ respondida pelo usuário, 2026-07-28**: se o cliente já fez o mesmo
   serviço antes (combinação `servicos.prazo_garantia`/`tipo_garantia` —
   1=Anos, 2=Dias, 3=Horas, 4=Meses, 5=Km, `RetornaGarantia`,
   `mdl_proc.bas:13468`), pode refazê-lo gratuitamente dentro do prazo
   contado da data de execução (termo "Revisão" na Clínica, "Garantia" na
   Assistência Técnica — mesmo campo, rótulo depende do módulo).
   Implementado em `_verificar_garantia_sync`/`GET /api/agenda/garantia`.
4. Não há limite superior encontrado pra quantidade antes do loop de
   desdobramento rodar (pedir 500 sessões geraria 500 linhas sem aviso) —
   vale um limite de sanidade na porta, ou replicar sem limite?
5. Heurísticas ainda em aberto de Metro Quadrado (ver seção acima) — não
   duplicadas aqui.

#### Fora de escopo provável (a confirmar, não presumir) — status atualizado 2026-07-28

- ~~**Faturar avulso de agendamento**~~ — **✅ implementado**: o usuário
  pediu explicitamente o agendamento avulso (criado direto da grade
  semanal, sem vir de um Pedido) com Faturar próprio, 1 forma de pagamento,
  reaproveitando a estrutura de Forma de Pagamento existente. Ver
  `_faturar_avulso_sync`/`AtendimentoAvulsoModal.tsx`. Continua bloqueado
  (fatura só pelo Pedido) quando o agendamento tem vínculo real com um
  Pedido/O.S. — regra preservada.
- ~~**Motor de Layouts**~~ — **✅ implementado** (modo "grade de campos";
  RTF livre segue fora de escopo). Ver `layout_service.py`/
  `layout-cadastro.tsx`.
- **Foto via webcam do cliente** (`Command24/26/27` de `FrmMarAge2`,
  APIs Win32 `WM_CAP_*`) — mesmo padrão de decisão já usado em Produto
  Completo/Tray (sem infra de webcam no stack atual).
- **Exportar Excel** (`CriaPlanilhaExcel`, automação COM) e **Imprimir
  agenda** (`Sub Imprime`) da própria tela de Agenda — não rastreados em
  detalhe (fora do foco "regra de agendamento"); se pedidos, seguem o
  padrão já usado no projeto (xlsx/SheetJS, preview+`window.print()`), não
  automação COM.

### Pedido Geral — Fase B: número de série (`controla_num_serie`) — 🟢 implementado 2026-07-27

Primeiro sub-módulo da Fase B (ver plano acima), escolhido explicitamente
pelo usuário via `AskUserQuestion` ("Fase B — número de série primeiro").
Clona o mesmo padrão já usado pelo legado (`CmbNDS`/`FrmNDS` em
`frmmanpedfor.frm`): produto com `pecas.controla_num_serie=1` bloqueia a
inclusão do item até o usuário escolher um número de série disponível em
`pecas_num_serie` (tabela/tela já existentes em Tabelas Auxiliares >
Números de Série — nenhuma tabela nova foi criada). Reforça "não mexer no
Pedido Bar" — `pedidos.tsx`/`pedido-form.tsx`/`itens_service.py` não
foram tocados; a extensão vive inteiramente no lado `PEDIDO_COMP`.

**Backend**:
- `schemas.py`'s `ItemSaveRequest` ganhou `cod_num_serie: Optional[int] =
  None` (FK opcional pra `pecas_num_serie.codigo`) — ignorado pelo fluxo
  do Bar, que nunca lê esse campo.
- `pedido_completo_service._add_item_completo_sync`: quando
  `prod["controla_num_serie"]`, força `qtd=1` (mesma regra do legado — um
  número de série = uma unidade), exige `req.cod_num_serie` (mensagem
  clara se faltar), valida que o número de série pertence ao produto E
  está `disponivel=1` antes de gravar. INSERT do item passou a incluir a
  coluna `cod_num_serie`.
- Nova função `_list_itens_completo_sync` (+ wrapper async
  `list_itens_completo`): reaproveita `itens_service._list_itens_sync`
  (mesma função do Bar, sem duplicar) e só ENRIQUECE o resultado com
  `item["num_serie"]` (texto do número de série, via JOIN
  `pedido_venda_prod.cod_num_serie → pecas_num_serie`) quando existir —
  decisão de não tocar o service compartilhado do Bar. `routes/
  pedido_completo.py`'s rota de listar itens agora chama esse wrapper em
  vez de `itens_service.list_itens` diretamente.
- `produtos_service._list_produtos_servicos_sync` (busca de produto
  compartilhada Bar+Geral) passou a incluir `controla_num_serie` no
  SELECT e no dict de resposta — necessário pro frontend saber quando
  exigir o seletor, sem endpoint novo.
- **Decisão consciente, não assumida**: `pecas_num_serie.disponivel` NÃO
  é zerado no momento de incluir o item no pedido — só a validação de
  disponibilidade é feita na inclusão. Espelha o mesmo padrão já usado
  pelo vínculo Cilindro↔Cliente (grava o vínculo, não "reserva" a linha).
  Se precisar revisitar (ex.: dois pedidos simultâneos podendo escolher o
  mesmo número de série antes de qualquer um fechar), fica registrado
  aqui como ponto em aberto.
- Testes: `test_pedido_completo_service.py` ganhou
  `TestAddItemCompletoNumSerie` (3 casos: exige seleção, valida
  disponibilidade/pertencimento, grava com sucesso) e
  `TestListItensCompletoEnriquecido` (2 casos) — 33 testes no arquivo,
  todos passando.

**Frontend** (componentes compartilhados por Pedido Bar E Pedido Geral,
mas o comportamento só ativa quando `controla_num_serie` vem `true` do
produto escolhido — o Bar nunca teria um produto assim hoje, já que essa
característica é do universo Cilindro/produto serializado, mas os
componentes em si (`AddItemModal.tsx`/`usePedidoItens.ts`/`ItemList.tsx`)
são os mesmos dos dois lados, então a extensão ficou nesses arquivos
compartilhados em vez de bifurcar por `tela`):
- `pedido/types.ts`: `ItemRow.num_serie?: string`,
  `ProdutoServico.controla_num_serie?: boolean`.
- `usePedidoItens.ts`: novo state `selNumSerie`/`setSelNumSerie`
  (resetado ao trocar de produto/reabrir o modal); `handleAddItem` força
  `qtd=1` e bloqueia sem `selNumSerie` quando o produto exige, inclui
  `cod_num_serie` no POST.
- `AddItemModal.tsx`: busca `GET /api/tabelas/num-serie?...&codigo_int=`
  (mesmo endpoint já existente da tela de Números de Série) filtrando só
  `disponivel`, mostra lista de seleção (estilo rádio) na etapa "Confirmar
  Item", esconde o stepper de Quantidade quando o produto exige número de
  série, desabilita "Adicionar" até uma opção ser escolhida, e roteia
  produto serializado direto pra etapa de confirmação (nunca pelo atalho
  "+" de adição rápida).
- `ItemList.tsx`: mostra "· Nº Série: XXXX" na descrição compacta do item
  quando presente.
- `pedido-geral.tsx`: novo item "Número de Série" em
  `AJUDA_PEDIDO_GERAL_ITENS` (Modo Didático).

**Não verificado ao vivo** — sem acesso a navegador/DB nesta sessão;
testes unitários (`pytest`) e checagem de tipos (`tsc --noEmit`) passaram
limpos, mas o fluxo completo (escolher produto serializado → seletor →
gravar → reabrir pedido → ver Nº Série no item) ainda precisa de um teste
manual na tela antes de considerar esta sub-fase 100% fechada.

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

### Dividir Pedido — implementado 2026-07-17 (funcionalidade NOVA, sem precedente no legado)

**Pedido do usuário**: "um pedido pode se tornar 2 ou mais pedidos com alguns
produtos do pedido original. Por exemplo: tem 4 pessoas na mesa e 1 pedido
aberto. cada pessoa vai pagar por 1 ou 2 produtos ou uma certa quantidade de
um produto, outros produtos vão ser divididos."

**Pesquisado em toda a árvore VB6** (todas as linhas de negócio — Geral,
Posto, Revenda, Tesouraria, ValPorto, Cartorio, Clauwan — `.frm` e
`Mdl_Proc.bas`) por "Dividir"/"Split"/"Separar Conta" — **nada encontrado**.
Não existe `FrmComanda*.frm` nenhum. `FrmManPedBar.frm` não tem esse botão.
Confirmado explicitamente ao usuário antes de desenhar a solução — é
funcionalidade genuinamente nova, desenhada em cima da máquina de estados já
existente (A/F/C/PG).

**Decisões confirmadas com o usuário** (via `AskUserQuestion` +
confirmações diretas em mensagens seguintes):
1. Os pedidos filhos ficam sob o **mesmo cliente** do pedido original (a
   Mesa/Comanda) — relaxa de propósito a invariante de "1 pedido aberto por
   cliente" só pra pedidos originados de uma divisão. Efeito colateral
   conhecido e aceito: o atalho "digitar M15 + Enter" no campo Cliente
   (`_pedido_aberto_por_cliente_sync`) continua trazendo só o pedido mais
   recente quando há mais de um aberto pro mesmo cliente — a tela
   "Pedidos Abertos" já lista todos normalmente, então não é um beco sem
   saída, só não é o atalho de 1 clique nesse caso específico. Não
   ajustado nesta rodada — nenhuma pergunta do usuário indicou que isso
   precisa mudar agora.
2. Divisão de item compartilhado por **valor fracionário** de uma unidade
   indivisível (ex. 1 pizza dividida 4x) usa a MESMA mecânica que dividir
   por quantidade inteira — `qtd_pedida` já é numérico/decimal (produtos
   por m²/kg já usam fração), então `qtd=0.25` em cada um de 4 pedidos
   representa exatamente 25% do valor daquela unidade, sem precisar de
   nenhuma coluna nova. Validado ao vivo.
3. Só pedido **Aberto** pode ser dividido — nada de estoque/comanda/forma
   de pagamento foi lançado ainda, mais simples e seguro. Pedido
   Fechado/Faturado bloqueia com mensagem clara.
4. Rastreabilidade: reaproveita `pedido_venda.num_ped_cliente` (coluna já
   existente, já exposta no Pedido Completo como "Nº Pedido do Cliente") —
   cada pedido filho grava ali o **número do pedido original** como texto,
   em vez de criar uma coluna nova (`pedido_origem`, que foi a sugestão
   inicial e foi explicitamente rejeitada pelo usuário em favor de
   reaproveitar o campo já existente — mesmo raciocínio já usado no módulo
   Cilindro, ver "Não replicar truques VB6" em CLAUDE.md).

**Campo "Referência" (novo no Pedido Bar)**: `num_ped_cliente` nunca tinha
sido exposto no Pedido Bar antes (só existia no Pedido Completo). Agora
aparece no topo da tela, **ao lado do combobox de Forma de Pagamento**
(ambos só web — mesmo recorte que Forma de Pagamento já tinha, "sem espaço
pra mais um grupo sem quebrar" no cabeçalho). Campo livre — serve tanto
como referência solta do cliente quanto pra guardar o vínculo de divisão.

**Backend** (`backend/services/pedidos_service.py`):
- `_dividir_pedido_sync`/`dividir_pedido` — recebe uma lista de `grupos`
  (cada grupo é 1 pedido novo, com uma lista de `{codauto, qtd}` a mover).
  O que não for listado continua no pedido original automaticamente (não
  precisa ser declarado explicitamente pelo chamador).
  - Valida: pedido existe e está Aberto; cada `codauto` pertence ao pedido;
    `qtd>0`; soma pedida por item não excede a quantidade original; Taxa de
    Serviço (`S002`) não pode ser movida manualmente.
  - **Taxa de Serviço distribuída proporcionalmente — REGRA EXCLUSIVA DO
    PEDIDO BAR (2026-07-24, user-directed)**: se o pedido original (Pedido
    Bar, `tela="PEDIDO"`) já tinha uma linha `S002` lançada, CADA pedido
    novo também recebe sua própria linha `S002` — 10% do subtotal que foi
    movido pra ele (`_recalc_valor_taxa_servico`, mesma fórmula já usada em
    `_add_taxa_servico_sync`). O pedido original continua tendo a sua taxa
    recalculada sobre o que sobrou (via `sincroniza_taxa_servico_apos_alteracao`,
    já existente). **Correção de um gap real**: antes desta mudança,
    `sincroniza_taxa_servico_apos_alteracao` era chamada pro pedido novo
    também, mas é um no-op quando não existe ainda uma linha `S002` naquele
    pedido (só ATUALIZA uma linha existente, nunca cria) — na prática a
    taxa "desaparecia" da parte movida pro pedido novo.
  - **Correção no mesmo dia, user-directed**: "o rateio da taxa s002 só se
    aplica pro pedido Bar. Para o pedido Geral tem que ser listado tudo
    Produtos e serviço, e só aplica pro pedido novo aquilo que for
    informado" — no **Pedido Geral** (`tela="PEDIDO_COMP"`), nada do
    parágrafo acima se aplica: `S002` NÃO é bloqueado de seleção manual
    (`rateio_automatico_taxa = tela == "PEDIDO"` controla isso), nenhuma
    linha é criada/recalculada automaticamente em nenhum dos pedidos
    resultantes — se o usuário incluir `S002` num grupo, ela é movida pelo
    mesmo laço genérico de itens (com a quantidade/valor exatos
    informados, igual qualquer produto/serviço comum); se não incluir,
    nada acontece com ela no pedido novo. O flag de "pedido esvaziado só
    com taxa sobrando" (auto-cancelamento) também respeita essa distinção:
    no Bar, `S002` sozinha não conta como "item real" restante (comporta-
    mento de sempre); no Geral, `S002` conta como item real igual
    qualquer outro (não tem tratamento especial lá).
  - **Frontend**: `DividirPedidoModal.tsx` (compartilhado pelas 2 telas)
    só tira `S002` da lista de itens divisíveis quando `basePath ===
    "/api/pedidos"` (Pedido Bar) — pro Pedido Geral (`basePath ===
    "/api/pedido-completo"`), a lista mostra TODOS os produtos e serviços,
    inclusive `S002` se presente.
  - 4 testes novos cobrindo os 2 comportamentos, um por tela
    (`test_taxa_servico_distribuida_proporcionalmente_no_pedido_novo`/
    `test_sem_taxa_servico_no_original_pedido_novo_nao_ganha_taxa` pro
    Bar; `test_pedido_geral_permite_dividir_s002_manualmente`/
    `test_pedido_geral_sem_taxa_selecionada_nao_gera_rateio_automatico`
    pro Geral).
  - Cada pedido novo copia cliente/vendedor/área/forma de pagamento/
    localização do original; `num_ped_cliente` = nº do pedido original.
  - Item com quantidade restante ~0 no original é excluído (`DELETE`); com
    sobra, só tem a quantidade atualizada (`UPDATE`).
  - Se o pedido original fica só com Taxa de Serviço (ou vazio) depois da
    divisão, a taxa também é removida e o pedido original é **cancelado
    automaticamente** (`situacao='C'`) — evita um "Aberto" vazio sobrando
    na lista.
  - Reusa `_ensure_hora_inclusao_item_col`/`_recalc_pedido_total` já
    existentes — nenhuma migração de schema nova precisou ser criada
    (o único campo "novo" usado, `num_ped_cliente`, já existe na tabela).
- Rota `POST /pedidos/{pedido}/dividir` (`routes/pedidos.py`), permissão
  própria `PEDIDO.DIVIDIR` (mesmo raciocínio de "cada botão real da tela
  com seu checkbox" já usado pra FATURAR/CANCELAR/REABRIR/ANEXOS), log de
  auditoria (`tela="PEDIDO"`, `comando="DIVIDIR"`).
- 9 testes novos (`TestDividirPedido` em `test_pedidos_service.py`), 533
  testes de backend passando.

**Frontend**: `frontend/src/components/pedido/DividirPedidoModal.tsx` —
**pedido explícito do usuário pra ser "prático"**: não é uma grade N-grupos
(1 grupo por chamada ao endpoint, que já aceita vários se precisar no
futuro) — é uma ação simples e repetível de "arrancar um pedaço pro pedido
novo": lista os itens do pedido atual (exceto Taxa de Serviço) com um campo
de quantidade a mover por item (aceita fração, botão "½" de atalho pra
metade) e um botão "Criar Pedido Novo". Pra dividir entre 4 pessoas: usar a
ação 3 vezes (cada uma tira a parte de 1 pessoa), o que sobra no pedido
original é a 4ª parte. Botão "Dividir" (outline) na toolbar do Pedido Bar,
ao lado de "Fechar Pedido" — só com o pedido Aberto e com itens, permissão
`PEDIDO.DIVIDIR`.

**Testado ao vivo** (GERDELL/BARESTELA): item de teste incluído num pedido
existente → dividido em 2 (2 de 4 unidades movidas pro pedido novo) →
conferido que o pedido novo ficou com o mesmo cliente, `referencia` =
número do pedido original, e o pedido original manteve a quantidade
restante corretamente. **Dados de teste totalmente revertidos depois** —
inclusive corrigindo um erro do próprio processo de teste: o primeiro
smoke test reaproveitou por engano um pedido Aberto PRÉ-EXISTENTE (não
criado pelo teste) em vez de criar um do zero, cancelando-o sem querer;
percebido e revertido via UPDATE direto restaurando situação/total/item
originais antes de finalizar — ver [[feedback_no_destructive_prod_db_tests]],
reforça a regra: sempre criar o próprio dado de teste do zero, nunca
reaproveitar um registro real já existente só porque "estava ali".

**Não implementado / gaps conhecidos**:
- Mobile não tem o campo "Referência" (só aparece ao lado de Forma de
  Pagamento, que já era web-only) — pedido explícito do usuário, não uma
  omissão.
- `_pedido_aberto_por_cliente_sync` continua "1 resultado só" mesmo com
  vários pedidos abertos pro mesmo cliente pós-divisão (ver decisão #1
  acima) — não ajustado, não pedido.
- Não portado (não existe no legado pra portar): reversão automática de
  uma divisão (desfazer/remesclar pedidos já divididos) — se precisar,
  seria uma tela nova, não um "desfazer" simples.

### Não implementado — BLOQUEADO, requer confirmação do usuário

O `.frm` colado cobre um fluxo de PDV completo bem além do que foi pedido
explicitamente nesta rodada (rebatismo + gating + guarda de cliente). Não
implementado, registrado aqui pra não implementar em cima de suposição
(regra "Gestão de Pendências entre Telas", CLAUDE.md §10):

- ~~**Painel "Pedidos Abertos"**~~ — **✅ implementado, 2026-07-17** (achado
  ao revisar as pendências de Pedido em 2026-07-30, esta entrada estava
  desatualizada): virou o "Painel de Pedidos" (`app/pedidos.tsx`, gated
  `moduleOn("Bar")`) — colunas dinâmicas por tipo (Mesa/Comanda/Balcão/
  Entrega/Fiado), totalizadores, cards ricos (`PainelPedidoCard.tsx`) com
  ações rápidas (Abrir/+Item/Faturar/Imprimir), "Novo Pedido" por coluna.
  Ver CLAUDE.md > "Painel de Pedidos" pro detalhe completo — não é mais um
  gap, a pergunta #1 de "Perguntas em aberto" logo abaixo também já foi
  respondida na prática (reaproveitou `pedidos.tsx`, visão específica pro
  Bar, não virou tela separada).
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

1. ~~O painel "Pedidos Abertos" (mesas/comandas em aberto) deve reaproveitar
   a lista já existente `pedidos.tsx`~~ — **respondida na prática,
   2026-07-17**: sim, reaproveitou `pedidos.tsx` (visão em colunas
   específica pro Bar via `moduleOn("Bar")`), não virou tela separada. Ver
   "Painel de Pedidos" em CLAUDE.md.
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

1. **`FrmConCli2.frm`** (seletor de cliente via F2 no legado) — **correção
   2026-08-02**: ao rastrear o Gestor de Projetos (que também o chama via
   F2), localizado em `Geral\FrmConCli2.frm` (2510 linhas) — não é mais
   "nunca fornecido", só ainda não foi lido em detalhe/comparado contra o
   que esta tela implementa. `contatos.cliente` já era texto livre no
   legado (nvarchar, nunca validado contra a tabela `cliente`) — a tela
   nova reaproveita `ClientSearchModal`/`GET /api/clientes/find/search`
   (já usado em Pedido/O.S.) pra escolher um nome existente, mas não
   trava o campo a um cliente cadastrado (fiel ao legado). Se Contatos (ou
   outra tela que use F2 pra cliente) for retomada, ler
   `Geral\FrmConCli2.frm` de verdade antes de assumir que o comportamento
   atual já cobre tudo.
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

---

## Contratos

**Status: 🟡 Fase A implementada (2026-07-19)** — Cadastros auxiliares +
Contrato completo (dados, itens, centro de custo, reajuste de valor,
acréscimo/desconto, encerramento) + Rateio de Centro de Custo. **Faturar
Contratos implementado 2026-07-20** (Faturar + Recibo — ver seção própria
abaixo); Nota Fiscal/Boleto (dentro de Faturar Contratos) e **Envio de
Cobrança** (remessa bancária/e-mail em massa) continuam fora de escopo.

**Atualizado 2026-07-19 (mesmo dia)**: o módulo inteiro passou a ser
gateado por `controle_configuracao.contratos` (coluna legada, já existia
na tabela — não precisou de migração), pedido explícito do usuário ("o
módulo Contrato deve ser habilitado em Configurações Módulo"). Mesmo
padrão de `_modulo_servicos_ativo`/Serviços: `_modulo_contratos_ativo(cur)`
em `pedido_common.py`, checado no topo de **todas as 21** funções
`_*_sync` de `contratos_service.py` (list/get/save/delete de tudo — Tipo
de Contrato, Tipo de Reajuste, Índices de Reajuste, Produtos Disponíveis,
Contrato, Itens, Centro de Custo, Reajuste, Acréscimo/Desconto, resolver
de produto, consulta ao BACEN). `MODULE_TELAS` em
`controle_config_service.py` + cópia local em `frontend/src/permissions/
index.tsx` mapeiam `contratos` → as 5 telas do catálogo de permissões.
Frontend: `moduleOn("contratos")` explícito em todas as 7 telas
(`contratos.tsx` + os 6 arquivos `contrato-*.tsx`) e no card "Contratos"
de `transacoes.tsx` — `moduleOn` explícito e não só `can()` porque master
bypassa `disabledTelas` dentro de `can()`, mas o toggle de módulo vale
igual pra todo mundo (ver "Master Has Full Permission" no CLAUDE.md).
"Contratos" já aparecia automaticamente em Configurações > Módulos e
Recursos (a tela é 100% data-driven a partir de `CAMPOS`), não precisou de
mudança lá.

**Registrada em**: 2026-07-19, a partir do pedido do usuário: "crie em
Transações o card Contratos. Dentro desse card, teremos 6 cards: Tipo de
Contrato(frmmantpc.frm), Tipo de Reajuste(frmmanrea.frm), Indices de
Reajuste(frmmanind.frm), Produtos Disponíveis(frmcompdi.frm),
Contratos(frmmanContra.frm), Faturar Contratos(frmfatContrato2.frm), Envio
de Cobrança(frmenvcob.frm)." — 6 `.frm` colados na íntegra pelo usuário.
Faseamento (Fase A agora / Faturar+Envio depois) e fonte do índice de
reajuste (API do Banco Central, não cadastro manual) confirmados via
`AskUserQuestion` antes de implementar, dada a diferença brutal de
complexidade entre as 5 telas de cadastro/contrato e as 2 telas de
faturamento (que envolvem geração de NF-e, boleto com layout por banco,
arquivo de remessa bancária CNAB 240/400, e envio de e-mail em massa —
motores inteiros, não telas de formulário simples).

### O que já foi analisado e implementado (Fase A)

**Backend** — `backend/services/contratos_service.py` +
`backend/routes/contratos.py` (registrado em `server.py`), permissões em
`permissoes_service.py` sob `TRANSACOES > CONTRATOS` (`TIPO_CONTRATO`,
`TIPO_REAJUSTE`, `INDICE_REAJUSTE`, `CONTR_PROD_DISP`, `CONTRATO` — este
último com ações próprias `ITENS`/`CENTRO_CUSTO`/`REAJUSTE`/`CRED_DEB`/
`ENCERRAR`, sem `IMPRIMIR` porque a impressão do contrato pertence ao
mesmo motor de Faturar Contratos deixado pra depois). Auditoria via
`log_auditoria_service` em todo GRAVAR/EXCLUIR, mesmo padrão de
`routes/tabelas_aux.py`.

- **Tipo de Contrato / Tipo de Reajuste / Índices de Reajuste**
  (`tipo_contrato`, `prazo_reajuste`, `indice_reajuste` — codigo smallint
  MAX+1, descricao): cadastros simples, réplica exata do padrão
  `tabelas_aux_service._*_tipo_cliente_sync`. Guarda de exclusão real
  (bloqueia se `contratos.tipo_contrato`/`tipo_reajuste`/`indice_reajuste`
  referenciar o código).
- **Produtos Disponíveis** (`contratos_produtos_disponiveis` — produto PK,
  preco, qtd, qtd_alocada, situacao, obs): réplica de `FrmConPDI.frm`.
  `qtd=0` = ilimitado (mesma regra do legado). Resolver de produto próprio
  (`_resolve_produto_contrato_sync`), cascata Cilindro → Equipamentos →
  Peças (codigo_int/codigo_fab/codigo_bar) → Serviços — **não existia** um
  resolver compartilhado cobrindo essas 4 tabelas no restante do backend
  (`pedido_common._resolve_produto` só cobre peças/serviços), então foi
  escrito de novo, escopo próprio deste módulo. Guarda de exclusão nova
  (não existe no VB6 original, mas seguindo a regra padrão do projeto de
  nunca excluir registro com dependência ativa): bloqueia se
  `qtd_alocada > 0`.
- **Contratos** (`contratos` + `contratos_produtos` +
  `contratos_centro_custo` + `contratos_preco` + `contratos_cred_deb`):
  CRUD completo do cabeçalho do contrato, réplica campo-a-campo das
  validações de `Command14_Click` (mês reajuste 1-12, dia vencimento
  1-31, tipo contrato/reajuste/índice/cobrança/periodicidade obrigatórios,
  descrição NF obrigatória). Sub-recursos:
  - **Itens**: inclusão/edição/exclusão com a mesma regra de
    disponibilidade do legado (`Campo_LostFocus(12)`/`Command9_Click` —
    `qtd=0` na disponibilidade = ilimitado, senão bloqueia sem saldo) e a
    mesma tripla de efeitos colaterais (`contratos_produtos_disponiveis.
    qtd_alocada`, `pecas.qtd`/`estoque_cli`, `equipamentos.cliente`).
    **Decisão consciente, diferente do legado**: a checagem de
    disponibilidade também roda ao EDITAR um item (o VB6 só checa ao
    incluir — `If Not alteracao Then` pula a checagem na edição), pra
    nunca permitir estourar o saldo por edição; ver comentário em
    `_save_item_contrato_sync`.
  - **Centro de Custo**: lançamento manual (upsert por
    contrato+centro_custo) e exclusão. **Não implementado**: o botão
    "Rateio Centro Custo" (`Command29_Click`/`Acerta_Contrato_Custo`) que
    divide o valor do contrato automaticamente entre os centros de custo
    já lançados — não achado no trecho de código colado pelo usuário
    (chamada referenciada, corpo da função não veio no `.frm`), então não
    foi implementado; lançamento continua 100% manual por enquanto.
  - **Alteração de Preço (Reajuste de Valor)**: grava histórico em
    `contratos_preco` + atualiza `contratos.valor_atual`/`valor_ant`/
    `ultimo_reajuste`/`historico`, mesma regra de bloqueio do legado
    (`Command24_Click`: valor novo igual ao atual não é permitido).
  - **Acréscimo/Desconto** (`contratos_cred_deb`): mesma validação do
    legado (`Command32_Click` — ano/mês obrigatórios, item obrigatório só
    pra Acréscimo, resolvido contra Peças/Serviços). **Não replicado do
    VB6** (era um "ano mínimo 2007" hardcoded, claramente um resquício de
    quando o sistema entrou em produção, não uma regra de negócio real —
    ver "Não replicar truques VB6" no CLAUDE.md): trocado por uma faixa
    plausível de ano (2000–2100).
  - **Excluir/Encerrar Contrato**: só permitido com `situacao='A'`,
    reverte estoque/alocação/vínculo de equipamento de todos os itens
    (`_reverter_estoque_itens_sync`, réplica de `Command10_Click`/
    `Command19_Click`).
- **Reajuste automático por índice (IGPM/IPCA) — feature NOVA, sem
  equivalente no VB6** (que só permite digitar valor/percentual na mão):
  `GET /contratos/indice-reajuste/{codigo}/bacen?data_inicial&data_fim`
  consulta a API pública do Banco Central (SGS,
  `api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados`, sem
  autenticação — mesmo princípio já usado no app pra ViaCEP). Séries
  verificadas 2026-07-19 via busca na web: IGP-M (FGV) = série 189, IPCA
  (IBGE) = série 433 — ambas de variação MENSAL, não acumulada; o
  percentual acumulado do período é calculado compondo (juros compostos)
  as variações mensais publicadas no intervalo pedido, não somando. Só
  funciona quando `indice_reajuste.descricao` é literalmente "IGPM"/
  "IGP-M"/"IPCA" (case-insensitive) — qualquer outro índice cadastrado
  (ex.: "ESPECIAL" visto no print do usuário) cai num aviso pedindo
  percentual manual, sem quebrar o fluxo. **Nunca aplica sozinho** — só
  preenche os campos de sugestão na tela, o usuário confirma antes de
  gravar.
- **Bug real encontrado e corrigido durante a própria implementação**
  (não é uma pendência, registro só pra quem for mexer aqui de novo):
  `_aplicar_alocacao_sync` só atualizava `equipamentos.cliente` ao
  ALOCAR, nunca ao REVERTER — excluir/editar um item de equipamento
  deixava `equipamentos.cliente` vinculado pra sempre ao cliente antigo
  do contrato. Corrigido fazendo a função sempre gravar o `cliente`
  recebido (o chamador decide: cliente do contrato ao alocar, `_vcodcli_
  sync` — cliente "da própria empresa" — ao reverter).

**Frontend** — hub `app/contratos.tsx` (mesmo padrão de
`app/movimentacoes.tsx`), aberto por um novo card "Contratos" em
`app/(tabs)/transacoes.tsx`. Telas:
- `app/contrato-tipo.tsx` / `contrato-tipo-reajuste.tsx` /
  `contrato-indice-reajuste.tsx` — clones diretos de `app/tipo-cliente.tsx`
  (lista + FAB + modal simples).
- `app/contrato-produtos-disponiveis.tsx` — lista + modal com resolução de
  produto no blur (mesmo `resolver-produto` do backend).
- `app/contrato-lista.tsx` — lista de contratos (busca + chips de
  situação Todos/Ativo/Encerrado).
- `app/contrato-completo.tsx` — tela cheia compacta (o legado não tem
  TabStrip, só Frames que aparecem/somem por botão — mesmo padrão já
  usado em Fornecedores/Cilindros: Itens/Centro de Custo/Alteração de
  Preço/Acréscimo-Desconto viram botão + slide modal em vez de aba).
  Botão "Consultar índice no Banco Central" dentro do modal de Alteração
  de Preço já pré-preenche percentual e novo valor sugeridos a partir da
  resposta do backend.

### Pontos de atenção / dívidas técnicas conhecidas

1. ~~**Schema não validado ao vivo**~~ — ✅ **validado 2026-07-20** contra
   `gibanweb.database.windows.net`/`BDREACTAPP` (conexão real, mesma usada
   pelos e2e deste projeto). As 9 tabelas existem com exatamente os nomes/
   tipos assumidos pelo código, exceto os pontos abaixo — corrigidos na
   mesma sessão, com round-trip completo (criar → buscar → editar →
   excluir contrato, itens, centro de custo, reajuste, acréscimo/desconto,
   rateio) rodado contra dados descartáveis e removido ao final:
   - **Bug real corrigido**: `_save_contrato_sync` validava os campos
     obrigatórios com `if not dados.get(campo)` — como `tipo_cobranca=0`
     ("Recibo", a primeira opção de `TIPO_COBRANCA_OPCOES`) é falsy em
     Python, um contrato com Tipo de Cobrança "Recibo" **nunca conseguia
     ser gravado** ("Defina o Tipo de Cobrança!"). Corrigido pra
     `dados.get(campo) is None`.
   - **Bug real corrigido**: `contratos_cred_deb.item` é `nvarchar(8)` no
     banco real, mas `_resolve_item_cred_deb_sync` só devolvia a
     descrição — o valor bruto digitado pelo usuário (que pode ser um
     `Pecas.Codigo_Fab`, `nvarchar(40)`) era gravado sem normalização,
     estourando "String or binary data would be truncated" (erro técnico
     cru vazando pro usuário). Corrigido normalizando sempre pro código
     canônico (`Codigo_Int`/`Servicos.Codigo`, sempre ≤8 chars) antes de
     gravar.
   - **Divergência de schema corrigida (ALTER, decisão do usuário)**:
     `contratos.multa`/`desc_venc` eram `smallint` no banco, mas o
     formulário (`keyboardType="decimal-pad"`) e a API tratam os dois como
     percentual decimal — o SQL Server truncava silenciosamente (`2.5` →
     `2`) sem erro nem aviso. Alterado para `float` (mesmo tipo de
     `valor_inicial`/`valor_atual`/etc. na mesma tabela — `real` foi
     testado primeiro mas gerava artefato de precisão de ponto flutuante
     de precisão simples, ex. `3.7` virando `3.700000047683716`; `float`,
     que é double precision, não tem esse problema). **Esse ALTER precisa
     ser replicado em qualquer outro banco de empresa** que já tenha essas
     tabelas criadas antes desta correção (2026-07-20) — não é algo que o
     backend detecta/migra sozinho.
   - Demais tabelas/colunas conferidas sem divergência: tipos, tamanhos de
     nvarchar (inclusive `produto`/`Codigo_Int`/`numero_de_serie`, todos
     cabendo dentro de `contratos_produtos.produto nvarchar(20)`),
     nullability, colunas IDENTITY (`codigo`/`cc_auto`).
2. ~~**Anexos (Gestor de Documentos) não integrado**~~ — ✅ implementado
   2026-07-19: botão "Anexos" na tela de Contrato completo (habilitado
   junto dos demais botões relacionados, exige contrato já gravado + um
   cliente definido) abre `GestorDocumentosSection` num modal largo
   (920px, mesmo padrão de `AnexosPedidoModal.tsx`, já que a seção precisa
   de lista + preview lado a lado). Mesmo mapeamento documentado acima:
   `cod_grupo=1` (Contrato não é entidade principal, é anexo do Cliente),
   `cod_sub_grupo=5` ("Contratos", confirmado ao vivo em GERDELL/
   BARESTELA), `referencia=contratos.codigo`.
3. ~~**"Rateio Centro Custo" automático não implementado**~~ — ✅
   **implementado 2026-07-20**. A rotina não estava em `FrmManContra.frm`
   (o form principal, que foi o único `.frm` colado originalmente) — o
   botão "Centro Custo" abre um modal filho, `Geral\FrmCustoContrato.frm`
   ("Centro de Resultados Contratos..."), que tem seu próprio botão
   "Rateio Valor" (`Command28`) chamando `Acerta_Contrato_Custo(Contrato)`,
   definida em `Geral\mdl_proc.bas:2416`. Localizado via o `.vbp` do
   projeto (não grep solto — ver "Nunca marcar uma rotina como 'não
   implementada'..." no CLAUDE.md, regra nova escrita a partir deste
   caso). Lógica replicada em
   `contratos_service._rateio_centro_custo_sync`/rota
   `POST /contratos/{codigo}/centro-custo/rateio`: soma o total já
   lançado nos centros de custo do contrato, compara com
   `contratos.valor_atual`, e redistribui a diferença
   proporcionalmente ao peso de cada linha (só 1 centro de custo lançado:
   joga o valor inteiro nele, sem rateio proporcional — mesma regra do
   legado). Botão "Rateio Valor" adicionado no modal Centro de Custo de
   `contrato-completo.tsx`, ao lado de um aviso (não bloqueio) quando o
   total lançado diverge do valor atual. Testado ponta a ponta contra
   banco real (1 cc e 2 ccs, rateio proporcional confirmado:
   1000+500 → 666,67/333,33 mantendo a proporção original).
   **Não replicado do legado** (ver "Não replicar truques VB6"): o
   bloqueio de `Form_QueryUnload` ao fechar esse modal quando os valores
   divergem estava condicionado a `Not
   Dados_Controle_Configuracao.Cilindro` — um flag de módulo sem nenhuma
   relação com Centro de Custo/Contratos, quase certamente resíduo de
   copiar-colar de outra tela; a regra real (avisar da divergência) foi
   preservada, o bloqueio condicionado ao flag errado não. `Acerta_Contrato_Prod`
   (mesmo arquivo, linha 2457) é a rotina irmã de rateio pra
   `contratos_produtos` (preço dos itens) — não pedida nem implementada
   nesta rodada, registrar aqui caso seja pedida no futuro.
4. **Reajuste automático cobre só IGPM/IPCA** — qualquer outro índice
   cadastrado em "Índices de Reajuste" (o legado permite texto livre) não
   tem correspondência com uma série do Banco Central; a tela avisa e
   pede percentual manual, não é um erro/bloqueio.
5. **Cliente do contrato**: campo de busca implementado de forma
   simplificada (texto com código + botão "buscar" abrindo modal de busca
   por nome/CPF/CNPJ via `/api/clientes/find/search`) — **não** reutiliza
   `ClienteSection`/`ClientSearchModal` (componentes usados por Pedido/
   O.S.) porque esses componentes são fortemente acoplados ao formato de
   dados e ao fluxo de criação rápida de cliente do Pedido/O.S.; a tela de
   Contrato tem um formato de tela diferente (full-page, não um card de
   cabeçalho). Funciona, mas não é o padrão "Campo Cliente" documentado em
   CLAUDE.md — considerar unificar se isso incomodar no uso real.

### Faturar Contratos — implementado 2026-07-20 (Faturar + Recibo)

**Status: 🟡 parcial** — motor de faturamento completo + geração de Recibo
implementados; Nota Fiscal (emissão fiscal real) e Boleto (layout
bancário) ficam de fora, ver "Não implementado" abaixo.

**Fonte rastreada**: `Clauwan\FrmFatContrato2.frm` (2600 linhas) — achado
via `.vbp` (`Clauwan\Kontacto.vbp` referencia `FrmFatContrato.frm` sem o
"2"; nenhum `.vbp` referencia literalmente `FrmFatContrato2.frm`, mas os
dois têm o mesmo conteúdo/modelo de dados — não é um form órfão/versão
errada, conferido comparando `Geral\FrmFatContrato.frm` e
`Clauwan\FrmFatContrato.frm`, ambos usam exatamente o mesmo modelo
`comanda`/`Receber`/`Duplicata_*`). Ver CLAUDE.md > "Nunca marcar uma
rotina como não implementada..." pro método usado (mesmo caso do Rateio de
Centro de Custo, mesma sessão).

**Decisão de arquitetura confirmada via `AskUserQuestion` (2026-07-20)**:
faturar um Contrato grava fiel ao legado em `comanda`/`comanda_duplicata`/
`comanda_contrato`/`comanda_os`/`movimentacao` + `Receber`/
`Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf` — **não** em
`pedido_venda`/`pedido_venda_duplicata` (a tabela que todo o resto deste
app usa pra vendas/faturamento). Consequência real, comunicada ao usuário
antes de implementar: um contrato faturado por esta tela **não aparece**
no Painel de Pedidos, Fechamento de Caixa ou nos relatórios já migrados —
só nas telas deste módulo (e nas equivalentes telas legadas de consulta a
`comanda`/`Receber`, se algum dia forem migradas). Ambas as famílias de
tabela (`comanda*` e `pedido_venda*`) existem e têm dados possíveis no
banco real — confirmado ao vivo em `BDREACTAPP`.

**Backend** — `contratos_service.py` (seção "Faturar Contratos", final do
arquivo) + `routes/contratos.py`:
- `GET /contratos/faturar/listar` — réplica de `Command2_Click`: filtra
  contratos ativos por período de referência (ano/mês), contrato inicial/
  final, tipo de cobrança (Recibo/NF/Boleto), "contratos não faturados"
  (`NOT IN comanda_contrato` pro mês/ano). **Período "mês comercial de 30
  dias"**: `inicio_periodo` = último dia do mês ANTERIOR (ex.: referência
  Jan/2026 → 31/12/2025), `fim_periodo` = dia 30 do mês de referência
  (nunca 31, mesmo em mês de 31 dias) — a mesma base do cálculo pró-rata
  `valor/30`. **Pró-rata**: desconta 1/30 do `valor_atual` por dia em que
  o contrato ficou fora do período (começou depois do início, ou
  terminou/foi encerrado/venceu antes do fim) — réplica exata de
  `Dia_Aux`/`VALOR_CONTRATO`, testada contra banco real (contrato
  iniciado no meio do período: 900 → 450, exatamente 15 dias de desconto
  em 30). **O.S. vinculada** (`contratos.fatura_os`): soma O.S. Fechadas
  não faturadas do cliente (ou de quem "fatura para" ele, via
  `cliente.faturar`) ao valor total faturado; O.S. Abertas aparecem só
  informativamente, não entram no total. **Vencimento**: dia de
  vencimento do contrato aplicado ao mês/ano de vencimento pedido
  (decrementando o dia até achar uma data válida, ex. dia 31 num mês de
  30), nunca antes da data de emissão (clampa nela se cair antes) —
  testado.
- `POST /contratos/faturar` — para cada contrato selecionado: `
  _gerar_comanda_sync` (réplica de `GeraComanda` — cria `comanda`,
  parcela(s) em `comanda_duplicata` usando `forma_pag_prazo` do contrato
  se existir, senão parcela única na forma "CONTRATO" tipo 'DU'
  auto-criada se não existir; grava `movimentacao` do serviço do
  contrato; grava `comanda_contrato`; se `fatura_os`, agrupa as O.S.
  Fechadas na mesma comanda, marca `os.situacao='PG'`, e deduz
  `pecas.reservado_os` dos itens tipo peça) + `_transf_receber_sync`
  (réplica simplificada de `Transf_Receber` — posta em `Receber` e
  distribui em `Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf`,
  seguindo um cronograma em `nf_vencimento` se existir, senão parcela
  única na data de emissão). Cada contrato roda numa transação própria
  (commit/rollback individual) — uma falha não aborta o lote inteiro,
  mesmo espírito do "best-effort" já usado noutros lotes deste projeto.
  **Achado/decisão registrada**: `CNF.Tipo_Mov = Tipo_Mov_Contrato` no
  legado usa uma variável (`Tipo_Mov_Contrato`) **nunca declarada** em
  nenhum `.frm`/`.bas` acessível (nem em `Geral`, nem em nenhum outro
  business-line) — quase certamente resíduo morto do VB6 (variant vazio
  implícito). Substituído por `Controle.tipo_mov_contrato_servico` (o
  tipo de movimento mais próximo semanticamente já configurado pro
  contrato) — **ajustar se o usuário identificar o valor real esperado**.
- `POST /contratos/faturar/recibo` — réplica de `Recibo()` sem a
  impressão física (VB6 `Printer`): devolve o conteúdo estruturado
  (recebemos, valor, valor por extenso, referente, data, assinatura) pro
  frontend imprimir via `printHtml` (mesmo padrão de `ReciboPedidoModal`).
  Grava em `Recibos` + incrementa `Controle.Seq_Recibo`, testado.
  **Valor por extenso reimplementado do zero** em português (não é porte
  de `Extenso`/`PegaExtenso` do VB6 — essas funções fazem parsing de
  string, `PegaExtenso` não foi localizada em nenhum `.bas` acessível;
  mesmo resultado funcional: singular "Real"/"Centavo" vs plural, "e"
  entre reais e centavos), testado com vários valores (`1.0` → "UM REAL",
  `100.0` → "CEM REAIS", não "CENTO REAIS").
- Permissão nova `FATURAR_CONTRATO` (`ABRIR`/`FATURAR`/`RECIBO`) sob
  `TRANSACOES > CONTRATOS`, gateada pelo módulo `contratos` (mesmo
  mecanismo das outras 5 telas). Auditoria em `FATURAR`/`RECIBO`.

**Frontend** — `app/contrato-faturar.tsx` (novo, aberto pelo card "Faturar
Contratos" em `contratos.tsx`): filtro (mês/ano referência, contrato
inicial/final, tipos de cobrança, contratos não faturados, mês/ano de
vencimento, data de emissão) → grid de contratos selecionáveis (marcar/
desmarcar individual ou todos) com totalizador → "Faturar Selecionados" →
resultado por contrato (sucesso/falha) com botão "Gerar Recibo" por
contrato faturado com sucesso (abre a impressão via `printHtml`).

**Testado ponta a ponta contra banco real** (`BDREACTAPP`, dados
descartáveis): listar com/sem pró-rata, faturar (comanda/duplicata/
movimentacao/comanda_contrato gerados corretamente), `Receber`/
`Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf` postados
corretamente, "contratos não faturados" excluindo corretamente um
contrato já faturado no mês/ano, geração de Recibo com numeração
sequencial e valor por extenso.

**Não implementado nesta rodada** (confirmado escopo via
`AskUserQuestion`):
- **Nota Fiscal** (`EmiteNF` no legado — emissão fiscal real, provavelmente
  via `Backon.Controllers.Nfe`, ver "Legacy VB6 Source Reference" no
  CLAUDE.md) — motor de emissão fiscal completo, fora de escopo.
- **Boleto** — layout específico por banco (Itaú, Bradesco, Banco do
  Brasil, Santander, Sicredi, Sicoob, Inter, HSBC) + os campos de
  `Duplicata_Rec_Venc` relacionados (banco_cedente/carteira/
  numero_boleto/dados_remessa) já existem no schema mas não são
  preenchidos por este backend ainda.
- `CentroCustoContrato` (`n_fiscal_custo`) — distribuição de custo por
  centro atrelada à emissão real de NF, não implementada (depende de NF
  real existir).
- **Envio de Cobrança** (`FrmEnvCob.frm`) — remessa bancária CNAB 240/400 +
  e-mail em massa — continua inteiramente fora de escopo, própria
  etapa de descoberta antes de estimar. **Ver seção própria "Bancos
  (Cadastro de Cobrança)" logo abaixo** — análise feita 2026-07-23 sobre
  se essa infraestrutura CNAB ainda faz sentido tal como no legado.

---

## Bancos (Cadastro de Cobrança / Boleto / CNAB)

**Status: 🟢 Fase 1 (cadastro) implementada e testada ao vivo (2026-07-23)**
— CRUD completo contra a tabela `bancos` já existente em GERDELL/BARESTELA
(53 colunas confirmadas ao vivo via `INFORMATION_SCHEMA`, PK `cod`
IDENTITY). Nenhum motor de emissão (CNAB ou API) foi implementado —
só o cadastro dos parâmetros, como planejado. Módulo Financeiro,
card "Cobranças" (pedido explícito do usuário — nome do card na tela,
diferente do nome interno do módulo/pendência "Bancos"). Legado:
`FrmManBan.frm`
("Manutenção de Bancos para Cobrança") — parâmetros de carteira de cobrança
usados tanto pra emitir boleto quanto pra gerar/ler arquivo CNAB de
remessa/retorno. **Tabela de destino é `BANCOS` (plural)** — existe uma
tabela antiga `BANCO` (singular) **em desuso no banco de dados**, não
reaproveitar/confundir as duas (alerta explícito do usuário, 2026-07-23).

### Análise da tela legada

Os ~40 campos indexados (`Campo(0)`...`Campo(42)` + `Check1`) se agrupam em:

1. **Identificação bancária**: código do banco (Febraban), agência+DV,
   conta+DV, carteira, variação de carteira, código de transmissão,
   contrato.
2. **Emissão de boleto**: espécie doc, aceite, código cedente, tipo de
   registro, emissão do boleto (banco/empresa emite), distribuição (quem
   envia ao sacado), tarifa de cobrança, "nosso número" (`Numero_Boleto`),
   mensagens do boleto (3 linhas), título do boleto.
3. **Regras de cobrança (negócio real, não workaround)**: multa
   (tipo/percentual/valor fixo + dias de incidência), mora diária, protesto
   (dias + tipo/instrução), baixa automática (dias + tipo/código).
4. **Infraestrutura de arquivo CNAB**: diretório local de remessa/retorno,
   número/data da última remessa — **só existe por causa do modelo de
   troca de arquivo-texto com o banco**, não é regra de negócio permanente
   (mesmo princípio de "Não replicar truques VB6" do CLAUDE.md, aqui
   aplicado ao protocolo bancário, não à linguagem VB6 em si).
5. **`Check1` "Integração por API"** — campo novo, não indexado como os
   demais (sinal de que a própria equipe VB6 já começou a migrar pra fora
   do CNAB puro, de forma incremental por banco).

### Decisão do usuário (via `AskUserQuestion`, 2026-07-23): implementar OS DOIS caminhos

Não escolher um só. Palavras do usuário: "pensando nos recursos que API
pode dar pro sistema novo — ter a opção garantida, depurada, funcionando
tudo etc., e ter também essa mais evoluída, porém não testada, depurada,
etc." Ou seja:

- **CNAB tradicional (arquivo remessa/retorno)** — caminho "garantido":
  replica os campos do legado (grupo 1-4 acima), mantém compatibilidade
  com os contratos bancários que os clientes que já usam o VB6 já têm
  hoje (não depende de recontratar nenhum provedor). É o que já roda em
  produção pros clientes VB6 — migrar isso é baixo risco de regressão de
  negócio, mas motor de geração/leitura de arquivo CNAB 240/400 por banco é
  trabalho pesado (citado 3x em PENDENCIAS.md como "própria etapa de
  descoberta antes de estimar").
- **API/gateway moderno** — caminho "mais evoluído, mas não testado": banco
  oferece REST + webhook (ou via gateway agregador tipo Asaas/StarkBank/
  GerênciaNet) em vez de arquivo. Elimina o grupo 4 inteiro e reduz o
  grupo 2. Precisa de credenciais de API por banco/conta (client_id/
  secret ou token) — campo novo no cadastro, condicional ao
  `Integração por API` ligado.
- **O cadastro de `BANCOS` precisa suportar os dois modos por registro** —
  o toggle "Integração por API" (já existente no legado) decide quais
  campos aparecem/são obrigatórios: ligado → esconde o grupo 4 (arquivo) e
  pede credenciais de API; desligado → mantém o formulário CNAB completo
  (grupos 1-4), igual ao legado.

### O que falta decidir/implementar (não iniciado)

1. **Fase 1 (cadastro)** — CRUD da tela `Bancos` em si (grupos 1-3 sempre
   presentes + grupo 4 condicional ao modo CNAB + credenciais condicionais
   ao modo API), sem motor de emissão real ainda — mesmo faseamento já
   usado em outros módulos grandes deste projeto (Modificadores,
   Contratos): cadastro primeiro, motor depois.
2. **Fase 2a (motor CNAB)** — geração de arquivo remessa + leitura de
   retorno, layout por banco (Itaú, Bradesco, BB, Santander, Sicredi,
   Sicoob, Inter, HSBC) — ainda sem escopo definido, precisa de rodada de
   descoberta própria (qual layout logo de cara, quais bancos os clientes
   atuais realmente usam).
3. **Fase 2b (motor API)** — qual(is) banco(s)/gateway(s) especificamente
   integrar primeiro — **não decidido ainda**, precisa de escolha do
   usuário (API direta de um banco específico vs. gateway agregador) antes
   de começar essa fase; nenhuma credencial de sandbox existe hoje pra
   nenhum provedor (mesma ressalva já registrada pra Tray em "Produtos
   (Cadastro Completo)" — não presumir infraestrutura de teste disponível).
4. Guarda de exclusão: o legado bloqueia excluir um banco com títulos
   associados em `duplicata_rec_venc` — **essa tabela não é a correta pro
   sistema novo** (ver `project_faturamento_parcelas` na memória — as
   tabelas certas são `pedido_venda_duplicata`/`os_duplicata`), então a
   guarda de exclusão real vai precisar ser re-derivada contra o schema
   novo quando a Fase 1 for implementada, não copiada literalmente do SQL
   do legado.

### Fase 1 (cadastro) — implementada 2026-07-23

**Backend**: `backend/models/bancos.py` (`BancoSaveRequest`/
`BancoDeleteRequest`) + `backend/services/bancos_service.py` (list/get/
save/delete, sync + wrapper async, mesmo padrão de `modificadores_service.py`)
+ `backend/routes/bancos.py` (registrado em `server.py`). **Não roda
nenhuma migração/DDL** — a tabela `bancos` já existe no schema (usada
pelos clientes que ainda rodam o VB6), confirmado ao vivo (`INFORMATION_SCHEMA`)
2026-07-23: 53 colunas, PK `cod` IDENTITY, único FK real
`cartoes_configuracoes.cod_banco`. Permissão nova `BANCOS` (menu
`FINANCEIRO`, ações padrão ABRIR/GRAVAR/EXCLUIR/IMPRIMIR/EXPORTAR).
Auditoria em Gravar/Excluir (`tela="BANCOS"`).

- **Campos do schema deliberadamente fora desta Fase 1** (existem na
  tabela mas não têm mapeamento confirmado contra o `.frm` colado pelo
  usuário — nunca assumir função de campo sem confirmação): `nome_remessa`,
  `cod_carteira`, `Tarifa_Boleto` (distinta de `tarifa_cobranca`, que é a
  usada), `certificado_digital`/`certificado_digital_auxiliar` (varbinary
  — fica pra quando a Fase 2b escolher um provedor de API específico e
  confirmar se ele exige certificado cliente). `remessa`/`data_remessa`
  são só exibidos (somente leitura) — no legado `Campo(23)` é
  `Enabled=False`, preenchido automaticamente pelo motor de remessa, nunca
  pelo formulário manual.
- **Campos numéricos sem rótulo amigável conhecido**: `tipo_cobranca`,
  `tipo_multa`, `incidencia_multa`, `codigo_protesto`, `codigo_baixa`,
  `tipo_registro`, `emissao_boleto`, `distribui_boleto`, `especie_doc` eram
  preenchidos no legado por combos (`List1`..`List9`) cujo texto das opções
  está no recurso binário `.frx`, não no `.frm` texto colado — sem esse
  texto, esses campos ficam como código numérico simples na tela nova (sem
  dropdown), com uma nota de ajuda explicando que são códigos definidos
  pelo banco. **Se o `.frx` for decodificado no futuro (ou o usuário colar
  a lista real de opções de algum desses combos), trocar por
  `SelectField`s de verdade** — não é um limite arquitetural, só falta de
  dado de origem.
- **Delete guard** replica o do legado, com verificação adicional pela FK
  real: bloqueia se `cartoes_configuracoes.cod_banco` referenciar o
  registro, OU se `duplicata_rec_venc` tiver uma linha casando a
  combinação de negócio `banco_cedente=codigo AND conta_cedente=conta
  AND carteira=carteira` (join do legado, preservado fielmente — não é o
  PK `cod`, ver docstring de `_delete_banco_sync`).
- **Toggle "Integração por API"** (`integracao_api`, já existente no
  schema/no `.frm` como `Check1`, não indexado como os outros campos):
  desligado exige Diretório de Remessa/Retorno (CNAB); ligado exige nada
  de arquivo, expõe 4 campos de credencial (`chave_api_1..4`, mapeados
  pra `chave_api`/`chave_api_2/3/4` no schema — os nomes genéricos
  "Chave/Token de API 1-4" evitam inventar rótulo específico de provedor,
  já que a Fase 2b ainda não escolheu qual API/gateway integrar).
- **Testado ao vivo contra GERDELL/BARESTELA** (round trip completo:
  criar → buscar → editar → listar com busca → excluir; guarda de
  exclusão testada nos dois caminhos — `cartoes_configuracoes` e
  `duplicata_rec_venc`, cada um bloqueando e depois liberando a exclusão
  após limpar a linha de teste). 20 testes unitários (mockados,
  `test_bancos_service.py`) cobrindo validação/CRUD/guardas — todos
  passando; suite completa do backend rodada, sem regressão nova
  introduzida (falhas pré-existentes em `test_pedido_compra_service.py`
  não relacionadas a este módulo).

**Frontend**: `frontend/app/bancos.tsx` — tela única compacta sem abas
(mesmo padrão de "Exception — compact single-view screens", precedente
`fornecedores.tsx`/`cilindro-cadastro.tsx`, já que o `.frm` legado também
não tem controle de aba): lista+busca+FAB "Novo" → formulário de tela
cheia (Gravar no canto superior direito, ícone de Ajuda/Modo Didático com
o texto de cada grupo de campo em linguagem de usuário final). Estado do
formulário usa um objeto único (`BancoForm`) em vez de ~40 `useState`
soltos — única diferença de padrão em relação a `fornecedores.tsx`,
justificada pelo volume real de campos. Confirmação de exclusão usa
`useFeedback().showConfirm` (não `Alert.alert`, que é no-op no web).
Botões-ícone (Ajuda, Excluir) usam `IconButtonWithTooltip`. **Não testado
ao vivo num navegador de verdade** (mesma limitação já documentada
noutros módulos desta sessão) — só `tsc --noEmit` confirmado sem novos
erros vs. baseline.

**Reestruturado no mesmo dia, user-directed**: o card "Cobranças" em
`app/(tabs)/financeiro.tsx` não abre `bancos.tsx` diretamente — abre um
hub novo, `frontend/app/cobrancas.tsx` (mesmo padrão de
`app/contratos.tsx`/`app/movimentacoes.tsx`: grid de cards, cada um uma
tela do módulo), e é o hub que tem o card "Bancos" apontando pra
`bancos.tsx`. Preparado pra outras telas do módulo de cobrança entrarem
como cards adicionais no mesmo hub no futuro (Fase 2 CNAB/API, ou
qualquer outra tela de cobrança) — não é uma tela avulsa 1:1. A
visibilidade do tile "Cobranças" em `financeiro.tsx` segue a mesma regra
de "Contratos" em `transacoes.tsx`: OR de todas as permissões ABRIR das
telas filhas do hub (só `BANCOS.ABRIR` por enquanto).

**Fase 2 (motores CNAB/API) continua não iniciada** — ver decisão de
escopo acima (implementar os dois caminhos).

### Fase 2a (motor CNAB) — implementada 2026-07-24, só Bradesco (237)

**Status: 🟢 Remessa (CNAB240) + Retorno (CNAB400) implementados e testados
ao vivo contra GERDELL/BARESTELA.** Decisão de escopo confirmada via
`AskUserQuestion` antes de implementar: banco Bradesco primeiro (dos ~6
bancos com layout no legado — Santander/033, Bradesco/237, Sicoob/756,
Sicredi/748, Inter/077, BB/001 — todos com CNAB bem diferentes entre si,
não dava pra fazer todos numa rodada); sem arquivo real de remessa/retorno
disponível pro usuário validar; remessa+retorno juntos nesta rodada.

**Fonte legada rastreada campo-a-campo** (não presumida —
`C:\Desenv\VB6\SQLSERVER\Geral\IntegracaoBancaria.bas`, 6521 linhas,
núcleo do motor bancário; `FrmGeraArqBan.frm`/`FrmImpRetBan.frm`/
`FrmEnvCob.frm` são as telas que o chamam; todos referenciados pelo mesmo
`Kontacto\backon.vbp`): `Gera_Header_240`/`Gera_Header_Lote_240`/
`Gera_Segmento_P_240`/`Gera_Segmento_Q_240`/`Gera_Segmento_R_240`/
`Gera_Trailer_Lote_240`/`Gera_Trailer_240` (ramos `Banco = "237"`),
`GeraNossoNumero`, `Modulo_11_Bradesco`. As larguras de cada campo foram
conferidas contra os `Type Header_Arquivo_240`/`Header_Lote_240`/
`Segmento_P_240`/`Segmento_Q_240`/`Segmento_R_240`/`Trailer_Lote_240`/
`Trailer_Arquivo_240` — cada registro soma exatamente 240 caracteres
(padrão Febraban CNAB240), somado manualmente durante o rastreio E
conferido de novo programaticamente nos testes (`len(linha) == 240`).

**Backend**: `backend/services/cnab_bradesco_service.py` (novo, separado
de `bancos_service.py` — motor de arquivo vs. cadastro CRUD são
responsabilidades diferentes, mesmo princípio de `nfe_fiscal_common.py`
separado dos services de emissão). Endpoints novos em
`backend/routes/bancos.py`: `POST /api/bancos/{cod}/remessa` (gera e
retorna o conteúdo do arquivo + nome sugerido) e
`POST /api/bancos/{cod}/retorno` (recebe o conteúdo colado, processa,
devolve resumo). Ações novas no catálogo de permissões (`ACOES_BANCOS`):
`GERAR_REMESSA`/`IMP_RETORNO` (nome abreviado — `IMPORTAR_RETORNO`
estourava o limite de 15 chars da coluna `permissoes.comando`). Auditoria
em ambas as ações.

- **Remessa**: busca títulos em aberto do banco
  (`duplicata_rec_venc.situacao='A' AND banco_cedente=237`, join com
  `duplicata_receber`+`cliente`+`cliente_end` — réplica da query de
  `FrmGeraArqBan.frm:531`), gera "Nosso Número" sequencial por título
  (réplica de `GeraNossoNumero`, incrementando `bancos.numero_boleto`),
  monta Header Arquivo + Header Lote + (Segmento P + Segmento Q + Segmento
  R se `Multa_Atraso_Pag > 0`) por título + Trailer Lote + Trailer
  Arquivo, grava `bancos.remessa`/`numero_boleto`/`data_remessa`/
  `nome_remessa` e marca `duplicata_rec_venc.transf_banco=1` por título
  incluído (réplica fiel do legado). Nome do arquivo:
  `CB<dd><mm><últimos 2 dígitos da remessa>.rem` (mesmo padrão de
  `Gera_Txt_240`, ramo 237).
- **Simplificação deliberada em relação ao legado** (registrada, não é
  perda de regra): `FrmGeraArqBan.frm` deixa o usuário marcar/desmarcar
  manualmente na grid quais títulos entram; aqui a remessa inclui
  automaticamente todos os abertos ainda não enviados
  (`transf_banco = 0` — filtro que o SQL do legado não tinha explícito
  nessa query específica, dependia só da seleção manual). Evita reenviar
  por engano um título já remetido.
- **Retorno**: aceita o conteúdo colado (texto), lê registros CNAB400 tipo
  1 nas posições Febraban padrão (Nosso Número 63-70, Ocorrência 109-110,
  Data Ocorrência 111-116, Valor Principal 254-266, Juros 267-279,
  Desconto 241-253) — mesmas posições do bloco "Confirmação de títulos
  enviados" (`Option1`) de `FrmImpRetBan.frm`. Ocorrência `02` só confirma
  (não altera nada); `06`/`09`/`17` dão baixa
  (`duplicata_rec_venc.situacao='PG'`, grava `data_pag`/`valor_pag`/
  `juros_pag`/`desconto_pag`/`ultima_mov_banco`), idempotente (título já
  `'PG'` não conta de novo). Título não encontrado (numero_boleto+
  banco_cedente+conta_cedente sem match) entra na lista `nao_encontrados`
  do resumo, não bloqueia o resto do arquivo.
- **Risco conhecido, não validado**: o usuário confirmou não ter nenhum
  arquivo de retorno real do Bradesco pra testar — a implementação segue o
  layout oficial Febraban CNAB400 (que bate com um dos dois blocos
  encontrados no legado). **Existe um SEGUNDO bloco no mesmo
  `FrmImpRetBan.frm`** (usado só no fluxo de anexo de e-mail,
  `AnexoEmail_DblClick`) com posições DIFERENTES (Ocorrência em 90-91 em
  vez de 109-110) — decisão consciente de seguir o primeiro bloco (bate
  com o padrão Febraban documentado, mais confiável) e tratar o segundo
  como bug/variação da função de e-mail, não como layout de banco
  diferente — mas isso não foi confirmado com um arquivo real. **Testar
  contra um retorno real do Bradesco antes de confiar em produção.**
- **Campos do schema não tocados por esta fase** (mesma lista já registrada
  na Fase 1, reafirmada): `cod_carteira`, `Tarifa_Boleto`,
  `certificado_digital`/`certificado_digital_auxiliar` — nenhum deles
  apareceu no rastreio do motor CNAB também, continuam fora de escopo.
- **Testado ao vivo contra GERDELL/BARESTELA** (dados descartáveis, limpos
  ao final): criado banco Bradesco de teste + cliente + endereço +
  duplicata_receber + duplicata_rec_venc → gerada remessa (6 linhas, TODAS
  com exatamente 240 caracteres, conta corrente/agência/carteira/CNPJ da
  empresa conferidos no conteúdo) → confirmado `transf_banco=1` e
  `numero_boleto` gravados → montada uma linha de retorno sintética
  (ocorrência 06) → processada → confirmado `situacao='PG'` +
  `data_pag`/`valor_pag` gravados. **Bug real encontrado e corrigido
  durante esse teste**: a implementação inicial lia a chave errada
  (`conta_corrente` em vez do nome real da coluna, `contacorrente`),
  zerando o campo Conta Corrente no arquivo gerado — pego justamente
  porque o teste ao vivo comparou o valor esperado (98765) contra o
  conteúdo real, não só o comprimento da linha.
- 24 testes unitários novos (`test_cnab_bradesco_service.py`, mockados) —
  larguras de registro, `Modulo_11_Bradesco`, validações de remessa
  (banco errado, API ligada, sem títulos), ocorrências de retorno (02, 06
  não encontrado, 06 baixa, 06 idempotente). Suite completa do backend
  rodada, sem regressão nova.
- **Frontend**: botões "Gerar Remessa" (baixa o `.rem` gerado via Blob) e
  "Processar Retorno" (modal com textarea pra colar o conteúdo + resumo do
  resultado) adicionados em `bancos.tsx`, visíveis só quando o banco já
  salvo é o Bradesco (código 237) e `integracao_api` está desligado. **Não
  testado ao vivo num navegador** — só `tsc --noEmit` limpo.

**Ainda fora de escopo (nesta etapa)**: Santander, Sicoob, Sicredi, BB —
Inter foi implementado logo em seguida, ver abaixo. Fase 2b (motor API) nem
começou, ainda sem provedor escolhido.

### Fase 2a (motor CNAB) — Inter (077) implementado 2026-07-24

**Status: 🟢 Remessa (CNAB400) + Retorno (CNAB400) implementados e
VALIDADOS byte a byte contra arquivo real do Inter, colado pelo usuário no
mesmo dia.** `backend/services/cnab_inter_service.py` (novo,
mesmo padrão de módulo autocontido do Bradesco — não extraído um
`cnab_common.py`, ver docstring do módulo). Dispatch por código Febraban do
banco adicionado em `backend/routes/bancos.py` (`_motor_cnab`, escolhe
`cnab_bradesco_service` ou `cnab_inter_service` a partir de
`bancos_service.get_banco`) — os endpoints continuam os mesmos
(`POST /api/bancos/{cod}/remessa` e `/retorno`), sem rota nova.

**Diferença estrutural do Bradesco**: Inter usa CNAB400 puro (registro de
largura fixa 400, sem lotes/segmentos — header + 1 registro por título +
trailer), não CNAB240.

**Achado importante durante o rastreio**: a tela `Geral/FrmGeraArqBan.frm`
(usada pra rastrear o Bradesco) só chama as funções CNAB240 —
`Gera_Header_400`/`Gera_Detalhe_400`/`Gera_Trailer_400`/`Gera_Txt_400`
(as funções do Inter, em `IntegracaoBancaria.bas`) pareciam código morto a
princípio (nenhum caller visível nessa tela, e o próprio `Gera_Detalhe_400`
tem uma variável `X` calculada no layout Febraban genérico mas nunca usada,
descartada em favor de um `INSERT` com posições totalmente diferentes,
específicas do Inter — cheiro de código abandonado/inacabado). **Busca mais
ampla encontrou o caller real**: `Kontacto/frmrelbol4.frm` (tela de emissão
de boletos em PDF que também gera remessa quando uma opção `Check5` está
marcada, dispatch por código do banco incluindo 77) — confirma que é código
real/alcançável na linha de negócio Kontacto, não abandonado, só não
cabeado na tela `Geral` usada pelo Bradesco. Segui o `INSERT` realmente
executado (não a variável `X` descartada) — ver docstring do módulo pro
detalhe completo desse achado.

**Retorno tinha mais ambiguidade de posição do que o Bradesco no
código-fonte legado, resolvida contra arquivo real no mesmo dia**: a função
`Processa_Retorno_inter` (`Geral/FrmImpRetBan.frm`) monta um struct
genérico (`Nosso_Numero` em 108, `Valor_Principal` em 254 etc.) que, olhando
com atenção, não é o que a lógica de negócio realmente usa — os ramos
`If Ocorrencia = "02"/"03"/"06"` usam outro conjunto de posições hardcoded
separadamente. A implementação inicial seguiu esse segundo conjunto (nº do
boleto em 71, valor do título em 125, valor pago em 160, data de pagamento
em 173) por ser o que o código realmente executa — e o usuário colou um
retorno real do Inter (8 títulos, ocorrências 02/06/07 misturadas) logo em
seguida. **Resultado**: `Ocorrência` (90-91), `Valor_Título` (125-137),
`Valor_Pago` (160-172) e `Data_Pagamento` (173-178) bateram exatamente com
o arquivo real, sem precisar de ajuste — confirmando que seguir o código
realmente executado (não o struct genérico) era o caminho certo. **Um erro
real foi encontrado e corrigido**: a posição do Nosso Número (nosso próprio
identificador, o que usamos pra casar com `duplicata_rec_venc.
numero_boleto`) estava em 71-81 (copiada por engano da leitura ambígua do
código-fonte) — o arquivo real mostrou que essa posição é na verdade um ID
interno do BANCO, e o nosso próprio Nosso Número (o mesmo valor que
gravamos na remessa) volta ecoado em 98-107. Corrigido em
`cnab_inter_service.py`, com um teste de regressão novo
(`test_arquivo_real_do_inter_2026_07_24` em `test_cnab_inter_service.py`)
usando o conteúdo real colado pelo usuário como golden file. Ocorrência
"07" também apareceu no arquivo real (não documentada em nenhum `ElseIf`
do legado) — tratada como ignorada, mesmo comportamento do legado (nenhum
ramo cobre esse código).

A remessa (header+detalhe+trailer) gerada por `_montar_header_400`/
`_montar_detalhe_400`/`_montar_trailer_400` bateu **byte a byte, sem
nenhuma diferença**, contra um arquivo de remessa real (header+1 título+
trailer) que o usuário também colou — validação forte de que o rastreio
inicial da remessa (inclusive a decisão de seguir o `INSERT` real em vez da
variável `X` descartada) estava correto desde o início.

**Achado cross-banco durante o rastreio, NÃO implementado (nem aqui nem no
Bradesco)**: a baixa real do legado (`Baixa_Titulo`, chamada pelo botão
"Confirma Baixa dos Títulos Selecionados", compartilhado por todos os
bancos que passam por `FrmImpRetBan.frm`) também incrementa
`Duplicata_Receber.Parcelas_Pagas` e, quando todas as parcelas de uma
duplicata estão pagas, marca `Duplicata_Receber.Situacao = 'PG'` — nenhuma
das duas coisas está implementada em `cnab_bradesco_service.py` nem em
`cnab_inter_service.py`; os dois só atualizam `duplicata_rec_venc`. Fica
como pendência pros dois motores, não só o Inter.

**Simplificação deliberada, para ficar simétrico ao Bradesco**: o legado
não aplica a baixa direto durante a leitura do retorno — monta uma grade de
revisão + tabela de staging `Boletos_Pendentes`, exigindo confirmação
manual separada. Este projeto já decidiu pro Bradesco aplicar direto (colar
→ processar → resumo, sem etapa de revisão), e o Inter segue a mesma
decisão pelos mesmos motivos (contrato de API/frontend já construído nesse
formato).

- 23 testes unitários (`test_cnab_inter_service.py`, mockados, incluindo o
  golden file real citado acima) — larguras de registro (header/detalhe/
  trailer somam exatamente 400, e batem byte a byte com a remessa real),
  validações de remessa (banco errado, API ligada, sem títulos, geração
  com 1 título sintético), ocorrências de retorno (02 confirma, 06 não
  encontrado, 06 baixa, 06 idempotente, ocorrência não mapeada ignorada,
  cabeçalho inválido, CNPJ não confere, arquivo real completo). Suite
  completa do backend rodada, sem regressão nova (as 66 falhas
  pré-existentes de `test_pedido_compra_service.py` continuam as mesmas,
  não relacionadas a este módulo).
- **Frontend**: `bancos.tsx` — os botões "Gerar Remessa"/"Processar
  Retorno" e os títulos das seções agora aparecem tanto pro Bradesco (237)
  quanto pro Inter (077), com o rótulo do banco dinâmico. Não testado ao
  vivo num navegador.
- **O que AINDA falta validar**: mesmo com o parsing/geração de arquivo
  100% conferido contra dado real, o fluxo de ESCRITA no banco (`UPDATE
  duplicata_rec_venc` na baixa, marcação de `transf_banco`/`numero_boleto`
  na remessa) só foi testado com cursor falso — nenhum round trip ao vivo
  contra GERDELL/BARESTELA ainda (diferente do Bradesco, que teve isso
  feito). Recomendo o mesmo teste ao vivo (criar banco Inter de teste +
  cliente + duplicata, gerar remessa, processar o retorno real já validado
  aqui trocando os números de referência pelos do teste, limpar) antes de
  considerar essa fase pronta pra produção.

### Fase 2a — Santander (033) e Banco do Brasil (001), só retorno, 2026-07-24

**Status: 🟡 Retorno implementado e testado (mockado); remessa BLOQUEADA —
decisão explícita do usuário.** Pedido do usuário foi implantar Itaú,
Santander e BB juntos; rastreando os três, achei uma ambiguidade real no
cabeçalho de remessa CNAB240 (`Gera_Header_240`, função COMPARTILHADA por
todos os bancos CNAB240 desta fase, inclusive o Bradesco já implantado) —
pelo menos três campos (`RazaoSocial`, `Nome_Banco`, um campo interno
`Cnab_01`) são montados sem `Format()` de largura fixa, e a soma dos campos
confirmados fecha 15 caracteres a menos que os 240 exigidos. Diferente do
Bradesco (que teve round trip ao vivo validado, então essa mesma ambiguidade
nunca foi tropeçada em teste real) e do Itaú/Inter (que tiveram arquivo real
pra resolver a mesma classe de problema), Santander/BB não têm arquivo real
disponível ainda. Perguntado ao usuário via `AskUserQuestion` — escolheu
"aguardar arquivo real" em vez de chutar a largura. **Geração de remessa
pros dois bancos fica pendente até aparecer um arquivo real** (mesmo
caminho que resolveu Itaú/Inter nesta sessão).

**Retorno é seguro e já está implementado** — `backend/services/
cnab_santander_service.py` e `backend/services/cnab_bb_service.py`.
Achado: `Retorno_Santander` e `Retorno_Bancodobrasil`
(`Geral/FrmImpRetBan.frm`) são **funções idênticas** no legado (mesmo
motor CNAB240 "Segmento T/U", leitura por posição fixa sem ambiguidade —
arquivo que o banco gera, não um que nós montamos). Cada título vem em duas
linhas consecutivas (Segmento T = identificação + ocorrência; Segmento U =
valores/datas de pagamento) — implementado com um `titulo_atual` de estado
entre as duas linhas. Mesma simplificação já usada em todos os motores
desta fase (baixa aplicada direto no `POST /retorno`, sem o staging de duas
etapas do legado). 17 testes unitários novos (`test_cnab_santander_service.py`
+ `test_cnab_bb_service.py`), todos passando.

**Dispatch**: `routes/bancos.py` já resolve os dois bancos pelo código
Febraban (033/001) — `POST /retorno` funciona normal; `POST /remessa`
responde com uma mensagem clara de "ainda não implementado" (não um erro
genérico) até a ambiguidade acima ser resolvida.

### Fase 2a — Itaú (341), remessa+retorno completos, VALIDADO 2026-07-24

**Status: 🟢 Remessa (CNAB400) + Retorno (CNAB400) implementados. Remessa
validada byte a byte contra um arquivo real do Itaú colado pelo usuário no
mesmo dia (dados reais de produção: cliente RACING LUB DO BRASIL IMP. EXP.,
carteira 109, título de R$ 1.079,40 da JUNIOR E HUGO MOTO PECAS LTDA,
vencimento 21/08/2026).** `backend/services/cnab_itau_service.py`.

Mesma ambiguidade encontrada no cabeçalho CNAB240 (ver Santander/BB acima)
apareceu no REGISTRO DE DETALHE CNAB400 do Itaú (`Gera_Detalhe_400`, ramo
`Else` — usado por qualquer banco que não seja 748/Sicredi ou 077/Inter,
os dois únicos com ramo próprio): 42 caracteres sem dono claro, dois campos
sem `Format()`. Perguntado ao usuário — mesma resposta, "aguardar arquivo
real". **O usuário colou o arquivo real de remessa do Itaú logo em
seguida**, ainda na mesma resposta em que decidiu esperar por um arquivo —
resolvendo a ambiguidade na hora:

- `Carteira` é um parâmetro `Byte` (0-255) concatenado cru, sem `Format()`
  — **largura variável**, não fixa. Carteira 109 (real) ocupa exatamente 3
  caracteres, sem zero à esquerda. Implementado como `str(int(carteira))`.
- `Documento` (`Format(Num_Duplicata, "#########0")`, sem zeros à
  esquerda) na verdade ocupa exatamente **10 caracteres** — mesma largura
  do campo "Documento" já usado pela leitura do PRÓPRIO retorno do Itaú
  (`Trim(Mid(Registro, 117, 10))`), confirmando os 10 caracteres por dois
  caminhos independentes.
- De brinde, dois campos que eu ia deixar zerados por padrão também
  bateram contra o arquivo real: `instrucao_1`/`instrucao_2`
  (`bancos.instr_cobranca_1`/`instr_cobranca_2`, não hardcoded em zero) e
  `juros_1_dia` (mesma fórmula `valor_boleto × bancos.mora_dia_pag / 100`
  já usada pelo Inter/Bradesco — `mora_dia_pag=0.5` reproduziu exatamente
  os R$ 5,40 de juros do título real).
- Confirmado também: Nome/Logradouro/Bairro/Cidade do Itaú **não** passam
  por `EscreveMatricial` (maiúsculas + sem acento) como Sicredi/Inter usam
  — o arquivo real preserva acentuação ("PRAÇA DA BAN...").
- Header e trailer (ramo `Else` de `Gera_Header_400`/`Gera_Trailer_400`)
  bateram 100% desde a primeira tentativa, sem ajuste.

**Achado de "bug" real do legado, replicado fielmente**: o campo
`Codigo_inscricao` aparece duas vezes na string final (uma vez "da
empresa", perto do início; outra vez "do cliente", perto do
`numero_de_inscricao`) mas é a MESMA variável no código-fonte, reatribuída
pro tipo do cliente antes de qualquer leitura — as duas ocorrências no
arquivo real têm o MESMO valor ("02"), confirmando que a posição "da
empresa" na prática sempre mostra o tipo do cliente. Replicado fielmente.

**Retorno usa `Processa_Retorno`** (mesma função genérica do Sicredi/748,
não implementado) — mesmo achado já registrado na seção do Inter acima:
o struct genérico lê Nosso Número na posição 63, mas a lógica de negócio
real (`ElseIf Ocorrencia = "06"`) usa a posição 86 — segui a posição 86.
**Isso não foi replicado no Bradesco já implantado** — perguntei ao
usuário se queria corrigir o Bradesco também; resposta: "todo banco tem
seu layout próprio" — ou seja, não presumir que a correção vale pro
Bradesco sem confirmação própria (o Bradesco nem passa por esse
`Processa_Retorno` no legado). Bradesco não foi tocado.

**O que ainda falta**: o RETORNO do Itaú não foi validado contra arquivo
real (só a remessa foi) — mesmo risco residual que Bradesco/Santander/BB
têm hoje. Nenhum round trip ao vivo contra GERDELL/BARESTELA ainda (só
testes mockados, incluindo golden-file da remessa real —
`test_cnab_itau_service.py`, 15 testes, todos passando).

**Frontend**: `bancos.tsx` — Itaú entrou no mesmo grupo de "remessa
completa" que Bradesco/Inter (botão "Gerar Remessa" visível); Santander/BB
mostram só "Processar Retorno" (o botão de remessa fica oculto pra eles,
já que ainda respondem "não implementado"). Não testado ao vivo num
navegador.

---

## Geração de Boletos (2 abas: Geração/Envio + Importação Retorno)

**Status: 🟡 Implementada 2026-07-24** — não testada ao vivo num
navegador. Tela única em Financeiro > Cobranças
(`frontend/app/geracao-boletos.tsx`, card único no hub `cobrancas.tsx`).

**Unificação 2026-07-24, user-directed** ("todo o processamento de
remessa e retorno é através da tela Geração de Boletos... pode colocar as
2 telas em uma única tela de Geração de Boletos com 2 Abas: Geração/Envio
e Importação Retorno"): a tela `frontend/app/retorno-bancario.tsx`
("Importação do Arquivo de Retorno", ver histórico abaixo) foi **removida
como arquivo/rota separada** — seu conteúdo virou a segunda aba
("Importação Retorno") dentro de `geracao-boletos.tsx`. O card próprio
"Importação do Arquivo de Retorno" saiu do hub `cobrancas.tsx`; o card
"Geração de Boletos" agora fica visível se o usuário tiver
`GERACAO_BOLETOS.ABRIR` **ou** `RETORNO_BANC.ABRIR` (as duas permissões
continuam distintas — quem só tem uma delas abre a tela direto na aba
correspondente e não vê a barra de abas, já que só há uma aba liberada
pra ele). Backend/rotas/permissões (`GERACAO_BOLETOS`/`RETORNO_BANC`)
**não mudaram** — só a camada de tela/hub foi consolidada.

Melhorias aplicadas na mesma rodada da unificação:
- **Banco**: primeiro item da lista já vem pré-selecionado ao carregar,
  nas duas abas (evita 1 clique a mais no fluxo mais comum — só 1 banco
  cadastrado na maioria das instalações).
- **Conta** (aba Importação Retorno): pré-selecionada com a conta marcada
  como `conta_principal_painel` (ver `project_contas_fluxo_caixa`),
  buscada via `GET /api/contas-caixa` em vez do lookup genérico
  `GET /api/contas` (que não expõe essa flag).
- **Conteúdo do arquivo de retorno deixou de ser colável** — antes exigia
  colar o texto do arquivo num `<textarea>`; agora é só um seletor de
  arquivo nativo do sistema operacional (`<input type="file">` oculto,
  acionado pelo botão "Selecionar Arquivo"): o usuário escolhe o arquivo
  no explorador, e a leitura (`FileReader.readAsText`) + chamada ao
  preview acontecem automaticamente em segundo plano, sem nenhum passo
  manual de copiar/colar.
- **Botões de ação movidos pra ANTES da lista**, nas 2 abas (user-directed
  2026-07-25, a partir de um screenshot mostrando "Marcar Todos /
  Desmarcar Todos / Baixar Títulos Selecionados") — antes ficavam depois
  da grade (exigia rolar até o fim pra achar os botões numa lista longa);
  agora ficam logo no topo do card, antes do cabeçalho da grade.

**Seleção de títulos pra "Gerar Remessa" (2026-07-25, user-directed)** —
antes desta mudança, "Gerar Remessa" sempre gerava a remessa com TODOS os
títulos pendentes do banco, sem seleção de linha (ver "Simplificação
deliberada" mais abaixo — motivo original: os motores CNAB não aceitavam
uma lista específica). Corrigido:
- A grade da aba Geração/Envio ganhou checkbox por linha, `Marcar Todos`/
  `Desmarcar Todos` (mesmo padrão da aba Retorno) — ao clicar
  "Selecionar", todos os títulos encontrados já vêm marcados por padrão
  ("Padrão todos selecionados", pedido explícito do usuário).
- **Os 3 motores de remessa implementados (Bradesco/Inter/Itaú) agora
  aceitam uma lista opcional de `duplicata_rec_venc.codigo`** —
  `_titulos_para_remessa_sync(cur, banco_febraban, titulos=None)` ganhou
  um `AND drv.codigo IN (...)` condicional nos 3 arquivos
  (`cnab_bradesco_service.py`/`cnab_inter_service.py`/
  `cnab_itau_service.py`), thread­ado por `_gerar_remessa_sync` →
  `gerar_remessa` (async) → `POST /api/bancos/{cod}/remessa` (novo campo
  `titulos: Optional[List[int]]` em `GerarRemessaRequest`,
  `models/bancos.py`). Santander/BB (remessa ainda não implementada)
  também ganharam o parâmetro na assinatura só por compatibilidade de
  dispatch genérico (a rota chama `motor.gerar_remessa(...)` igual pra
  todo banco) — continuam retornando a mensagem de "não implementado",
  ignorando o parâmetro.
- **Frontend só envia a lista quando a grade já foi carregada**
  (`itens.length > 0`) — se o usuário clicar direto em "Gerar Remessa"
  sem antes clicar "Selecionar" (a grade nunca foi populada), o
  comportamento antigo é preservado (`titulos: undefined` → todos os
  títulos pendentes do banco, sem filtro) — decisão deliberada pra não
  quebrar o atalho de quem já usava a tela assim. Com a grade carregada e
  nenhuma linha marcada, bloqueia com "Selecione ao menos um título."
  antes de chamar a API.
- 2 testes novos em `test_cnab_bradesco_service.py` (mensagem específica
  quando nenhum dos títulos selecionados está pendente + verificação de
  que o `IN (...)` realmente entra na query) — suite completa (CNAB +
  Cobranças) sem regressão, 140 testes passando.

**Sub-seção original (Fase 1, aba Geração/Envio)**: baseada em
`Kontacto/frmrelbol4.frm` ("Impressão de Boletas Bancárias"), colado pelo
usuário via prints da tela legada.

**Descoberta que definiu o escopo desta rodada**: o botão "Imprimir"
(`Command2`, relabelado "Gerar Remessa para Registro" quando o checkbox
"Gera Arquivo Remessa Bancária" está marcado) chama `Sub Boleto()`, que por
sua vez chama `BoletoItau`/`BoletoBradesco`/`BoletoSantander`/`BoletoHSBC`/
`BoletoSicoob`/`BoletoBancoDoBrasil` (todas em `IntegracaoBancaria.bas`,
~500-600 linhas cada) e `BoletoInter` (arquivo próprio,
`Kontacto/BancoInter.bas`) — mais `GeraPDF` (`Geral/mdl_proc.bas`). Cada
uma dessas funções tem DUAS partes bem distintas:
1. **Cálculo da linha digitável/código de barras** (dígito verificador,
   fator de vencimento, módulo 10/11) — padrão Febraban documentado,
   **portável** (mesmo tipo de trabalho já feito nos motores CNAB desta
   sessão).
2. **Desenho visual do boleto** (linhas, caixas, logo do banco, posição de
   texto) — preso ao objeto `Printer` do VB6, impresso numa impressora PDF
   virtual (**bioPDF** — `CreateObject("biopdf.PDFUtil")`, confirmado em
   `GeraPDF`). **Sem equivalente direto num backend web/Python** — exigiria
   reconstruir o layout inteiro do zero com uma biblioteca de PDF real
   (ex.: reportlab) + geração de código de barras, motor que não existe
   neste projeto hoje.

Perguntado ao usuário via `AskUserQuestion` como proceder — escolheu
"Localizar os módulos de boleto antes de decidir" (feito, achado acima) e,
depois de ver o mapeamento, confirmou seguir com a Fase 1 reduzida (sem
PDF/e-mail), deixando o motor de desenho como pendência separada.

**Implementado (Fase 1)**:
- Backend: `backend/services/geracao_boletos_service.py` — query de
  títulos elegíveis replica `Command1_Click` (`frmrelbol4.frm:750`), join
  `duplicata_receber`+`cliente`+`duplicata_rec_venc`, `situacao='A'`,
  filtros (emissão de/até, vencimento de/até, duplicata, nº do boleto,
  cliente por nome/fantasia, só sem boleto, somente registrados). Taxa
  bancária/multa/mora na grade são **estimativas informativas** (mesma
  fórmula já usada nos motores CNAB — `bancos.tarifa_cobranca` quando
  `cliente.cobra_tarifa_bancaria`, `Multa_Atraso_Pag`/`mora_dia_pag` sobre
  o valor) — o legado tinha um campo de override manual (`Campo(3)`) só
  usado no fluxo de impressão, que não existe aqui. Rota
  `POST /api/geracao-boletos/{cod_banco}/titulos`. Permissão nova
  `GERACAO_BOLETOS` (menu FINANCEIRO, ações ABRIR/GERAR_REMESSA/EXPORTAR).
  7 testes unitários, todos passando.
- **"Gerar Remessa" reaproveita o endpoint genérico já existente**
  (`POST /api/bancos/{cod}/remessa`, os 3 motores completos — Bradesco/
  Inter/Itaú). **Superado 2026-07-25** (ver bloco "Seleção de títulos pra
  'Gerar Remessa'" logo acima) — a limitação original ("os motores CNAB
  não aceitam uma lista específica de títulos, gera sempre pra TODOS os
  pendentes, sem seleção de linha") não existe mais: os 3 motores
  aceitam um filtro opcional por `duplicata_rec_venc.codigo`, e a grade
  ganhou checkbox por linha + Marcar/Desmarcar Todos, com todos marcados
  por padrão. O comportamento "todos pendentes, sem filtro" só continua
  ativo como fallback pra quem clica "Gerar Remessa" sem antes clicar
  "Selecionar" (grade nunca carregada).
- "Gerar Planilha" — exportação Excel real (reaproveita
  `frontend/src/utils/export-xlsx.ts`, já usado pelo Borderô de
  Cilindros) dos títulos atualmente na grade (já filtrados).

**Fora de escopo desta rodada, registrado**: "Gerar PDF" (boleto com
código de barras) e "Enviar por Email" (com o PDF anexado) — dependem do
motor de desenho descrito acima. O SERVIÇO DE E-MAIL EM SI já está pronto
e testado (ver seção "Serviço de E-mail de Cobrança" abaixo) — só falta o
PDF pra anexar. "Somente registrados"/"Só duplicatas sem boleto" foram
portados como filtros; o cruzamento com nota fiscal/comanda
(`duplicata_rec_nf`/`n_fiscal`/`comanda_nf`, usado no legado só pra exibir
"Comanda" na grade de impressão) não foi portado — não necessário pro
fluxo de remessa/planilha.

---

## Aba Importação Retorno (dentro de Geração de Boletos)

**Status: 🟡 Implementada 2026-07-24** (grade de revisão de baixas +
aplicação seletiva) — não testada ao vivo num navegador. **Fundida em
`frontend/app/geracao-boletos.tsx` no mesmo dia** (ver seção "Geração de
Boletos" acima) — não é mais uma tela/rota própria
(`retorno-bancario.tsx` foi removido). Baseada em `Geral/FrmImpRetBan.frm`,
colado pelo usuário via prints da tela legada.

Reaproveita os 5 motores de leitura de retorno já implementados na Fase 2a
(Bradesco/Inter/Santander/BB/Itaú) — cada um ganhou uma função
`_parse_linhas` extraída do `_processar_retorno_sync` já existente (mesma
lógica, sem tocar no banco de dados), refatoração feita com testes
completos rodados antes/depois de cada bank pra garantir zero regressão.
Novo módulo compartilhado `backend/services/cobranca_retorno_service.py`
faz o dispatch por banco + enriquece cada registro de baixa com dados de
exibição (cliente, vencimento, valor do título — join
`duplicata_rec_venc`+`duplicata_receber`+`cliente`).

**Simplificação deliberada em relação ao legado**: só o fluxo de **baixa**
(ocorrência 06/09/17 — a ação com impacto financeiro real, quita o título)
vira uma grade selecionável linha a linha. **Confirmação (ocorrência
02/03) vira só uma contagem-resumo**, não uma lista selecionável — nos
bancos CNAB400 (Inter/Itaú), o registro de confirmação usa um
identificador diferente (`AutoNumDRV`, uma referência interna) do que o
usado pra achar o título na baixa (`Nosso Número`), e o parsing atual
desses dois bancos não extrai esse identificador pro caso de confirmação
(só usa pra CONTAR, replicando fielmente o que `_processar_retorno_sync`
já fazia). Extrair isso pros bancos CNAB400 é trabalho adicional, não
incluído nesta rodada. O botão "Confirmar Títulos Selecionados" e o campo
`duplicata_rec_venc.registrado` (que o legado grava nesse fluxo,
`Command5_Click`) também ficaram de fora por essa mesma razão.

**Implementado**:
- Backend: `backend/services/cobranca_retorno_service.py` —
  `preview_retorno` (lê o arquivo, resolve cada título de baixa contra o
  banco, sem gravar nada) e `aplicar_baixas` (réplica de `Baixa_Titulo`,
  idempotente — título já `'PG'` conta como `ja_baixados`, não reaplica).
  Rotas `POST /api/bancos/{cod}/retorno/preview` e `/aplicar`. Permissão
  nova `RETORNO_BANC` ("Importar Retorno" — nome/tela abreviados pra caber
  nos limites de `permissoes.tela`/`nome`, nvarchar(15)/(20)), ações
  ABRIR/BAIXAR. 10 testes unitários novos
  (`test_cobranca_retorno_service.py`), todos passando.
- **Campo "Conta" opcional** (lookup `GET /api/contas-caixa`, pré-
  seleciona a conta marcada como padrão do painel — ver seção "Geração de
  Boletos" acima) — se selecionado, grava em qual conta de caixa/banco o
  valor recebido entrou (`duplicata_rec_venc.conta`), mesmo comportamento
  do parâmetro `Conta` de `Baixa_Titulo` no legado.
- Frontend: grade com checkbox por linha (títulos já baixados aparecem
  esmaecidos e não selecionáveis), Marcar/Desmarcar Todos, resumo de
  confirmações/ignorados/não encontrados, ícone de Ajuda (Modo Didático),
  arquivo escolhido via seletor nativo (não colado).

**Correção 2026-07-24, mesmo dia, user-directed** ("tem que listar os
títulos para importação. Possibilitar selecionar quais os títulos quero
importar. Padrão todos selecionados") — achado ao testar ao vivo contra
um arquivo de retorno real do Inter: quando um título do arquivo não
casava com nenhum `duplicata_rec_venc` local, ele só entrava numa frase-
resumo ("21 não encontrado(s): 2696, 2618, ...") — nenhuma linha aparecia
na grade, sumindo da tela por completo (a seleção "todos marcados por
padrão" já existia pros títulos ENCONTRADOS, mas ficava invisível quando
0 títulos casavam). Corrigido:
- `_preview_retorno_sync` (`cobranca_retorno_service.py`) agora também
  devolve `itens_nao_encontrados` (lista de dicts, mesmo formato de
  `itens_baixa` mas com `drv_codigo=None`/`cliente_nome=None`/
  `vencimento=None`/`valor_titulo=None`, preenchido só com o que o
  ARQUIVO trouxe — número do boleto, ocorrência, data/valor pago, juros,
  desconto) — além do já existente `nao_encontrados` (lista de números
  crus, mantida por compatibilidade/resumo). Novo campo `encontrado`
  (bool) em ambas as listas, usado pelo frontend pra decidir o que é
  selecionável.
- Frontend: a grade agora mistura `itens_baixa` + `itens_nao_encontrados`
  numa lista só — linhas não encontradas aparecem esmaecidas (mesmo
  estilo de "já baixado"), rotuladas "(não encontrado)", sem checkbox
  clicável (chave de seleção trocada de `drv_codigo` — sempre `null`
  nessas linhas — pra `numero_boleto`, único por arquivo). Continuam sem
  poder ser selecionadas/baixadas (não existe título local pra
  atualizar) — a mudança é só torná-las VISÍVEIS pra conferência, não
  torná-las acionáveis.
- 1 teste novo (`test_bradesco_titulo_nao_encontrado`, estendido) +
  suite completa sem regressão.

**O que ainda falta**: nenhum round trip ao vivo contra GERDELL/BARESTELA
ainda (só testes mockados) — recomendo testar com o mesmo retorno real do
Inter já usado pra validar `cnab_inter_service.py` nesta sessão, trocando
os números de referência pra bater com dados de teste. Ao testar, também
vale investigar SE os "não encontrados" reais são um problema de dado de
teste (título realmente não cadastrado nessa empresa) ou um bug de
casamento (`numero_boleto`/`banco_cedente`/`conta_cedente` extraídos
errado do arquivo) — a correção desta rodada só resolveu a VISIBILIDADE,
não investigou a causa raiz de por que tantos títulos não casaram no
teste ao vivo do usuário.

---

## Serviço de E-mail de Cobrança

**Status: 🟢 Implementado e testado com envio real 2026-07-24.**
`backend/services/email_cobranca_service.py` — motor novo, sem
equivalente 1:1 no legado (o legado só tinha os campos de configuração
"Email de Cobrança" em Controle do Sistema > aba Outros, nunca um envio de
fato implementado — confirmado por busca no backend inteiro, `smtplib`
não aparecia em nenhum lugar antes desta sessão).

Lê a configuração já existente em `controle_aux`
(`e_mail_COBRANCA`/`ident_COBRANCA`/`smtp_COBRANCA`/`porta_smtp_COBRANCA`/
`login_COBRANCA`/`senha_COBRANCA`/`ssl_COBRANCA` — mesmos campos expostos
em `frontend/app/controle-sistema.tsx`, aba Outros > Configuração de
Emails > Email de Cobrança) e envia via `smtplib` puro, sem dependência de
serviço externo. Detecção de criptografia por porta: 465 usa `SMTP_SSL`
(SSL implícito), qualquer outra porta com `ssl_COBRANCA` ligado usa `SMTP`
+ `starttls()` (STARTTLS) — o único checkbox "Requer SSL" do legado cobria
as duas convenções.

**Validado com envio real** (2026-07-24, mesmo dia): o usuário forneceu as
credenciais reais da conta `adm@kontacto.com.br` (Titan Email, SMTP
`smtp.titan.email`, porta 587, STARTTLS) — salvas em `controle_aux` de
GERDELL/BARESTELA (não em nenhum arquivo do repositório). Um e-mail de
teste foi enviado com sucesso para `carlos@kontacto.com.br`, confirmando
autenticação e envio funcionando de ponta a ponta. 5 testes unitários
(`test_email_cobranca_service.py`, SMTP mockado), todos passando.

**Reutilizável, ainda sem tela que o consuma de verdade com anexo** — a
única tela que precisaria dele hoje ("Enviar por Email" em Geração de
Boletos) depende do PDF do boleto, que ainda não existe (ver seção
"Geração de Boletos" acima). O serviço já suporta anexos
(`MIMEApplication`), só falta o gerador de PDF pra produzir o que anexar.

---

## Contas (Financeiro > Fluxo de Caixa)

**Status: 🟢 Implementada 2026-07-24** — não testada ao vivo num navegador.
Tela nova em Financeiro > Fluxo de Caixa (`frontend/app/contas.tsx`, card
no hub `fluxo-caixa.tsx`), baseada em `FrmManConta.frm` ("Conta"), colado
pelo usuário. Tabela `Contas` já existia e já era usada por vários pontos
do app (`lookups_service.list_contas`, "Conta" na Importação do Arquivo de
Retorno) — esta é a primeira tela com CRUD completo sobre ela.

**Regra de negócio real, replicada fielmente** (`Command6_Click`, ramo de
UPDATE): ao editar o Saldo Inicial de uma conta já existente, o Saldo
Atual é recalculado proporcionalmente pela diferença — preserva o
"extrato" (soma de movimentações) já lançado, só desloca o ponto de
partida. O legado escreve isso como duas ramificações `If`/`Else`
(matematicamente equivalentes, conferido a mão); implementado como uma
soma só. Toast de sucesso avisa explicitamente quando isso acontece
("Saldo atual recalculado para X").

**Não replicado, decisão registrada** ("Não replicar truques VB6"): o
botão "Alterar Descrição" (`Command2_Click`, um `InputBox` dedicado) era
um workaround pro campo `Nome` do legado ser um ComboBox vinculado à
lista de contas existentes, não um campo de texto livre. Aqui o
Nome/Descrição é só mais um campo do formulário normal — a regra real por
trás daquele botão (não permitir duas contas com o mesmo nome) foi
preservada, mas aplicada de forma **mais consistente** que o legado (lá só
rodava dentro do fluxo "Alterar Descrição"; aqui roda sempre que a
descrição é gravada, criação ou edição).

**Fora de escopo**: campo "Contabilidade" (`Campo(20)`/
`conta_transf_contabil`, FK pra `Plano_<ano_exercicio>` — tabela ano a
ano) — mesma decisão já tomada em `financeiro_service.py` pro campo
homônimo de Classes/Sub-Classes (qual "ano_exercicio" usar é uma pergunta
em aberto, ver CLAUDE.md > Cliente Completo, mesma pendência
cross-referenciada).

**Implementado**:
- Backend: `backend/services/contas_service.py` — list/get/save/delete.
  Rotas `GET/POST /api/contas-caixa`, `GET /api/contas-caixa/{codigo}`,
  `DELETE /api/contas-caixa/{codigo}` — **atenção ao nome da rota**:
  `/api/contas` já existe (lookup genérico código/descrição em
  `lookups_service.py`, usado por outras telas), por isso esta tela usa
  `/api/contas-caixa` pra não colidir. Permissão nova `CONTAS` (menu
  FLUXO_CAIXA, ações padrão ABRIR/GRAVAR/EXCLUIR/IMPRIMIR/EXPORTAR — só
  GRAVAR/EXCLUIR/ABRIR de fato usados nesta fase). 15 testes unitários
  (`test_contas_service.py`), todos passando.
- **Delete guard fiel ao legado** (`Command3_Click`): bloqueia exclusão se
  a conta tiver lançamentos em `previsoes` OU `movimentacoes` —
  `(tipo<>2 AND conta=codigo) OR (tipo=2 AND classe=codigo)` nas duas
  tabelas (`tipo=2` marca transferência entre contas, onde a coluna
  `classe` é reaproveitada pra guardar a conta de destino — mesmo truque
  de reaproveitamento de coluna já documentado em
  `entrada_saida_caixa_service.py`, confirmado que `movimentacoes` é a
  MESMA tabela que Entrada/Saída de Caixa já escreve). `previsoes` não é
  escrita por nenhuma tela já migrada deste app — a checagem continua
  incluída porque a tabela é real e compartilhada com o legado.
- Frontend: tela única compacta sem abas (mesmo padrão de
  `fornecedores.tsx`/`bancos.tsx` — o `.frm` legado também não tem aba),
  Saldo Atual sempre somente leitura (nunca editável, só exibido ao
  editar uma conta existente), ícone de Ajuda/Modo Didático explicando a
  regra de recálculo do Saldo Atual e "Conta Padrão no Painel".

---

## Contas x Funcionário (Financeiro > Fluxo de Caixa)

**Status: 🟢 Implementada 2026-07-25** — não testada ao vivo num
navegador. Tela nova em Financeiro > Fluxo de Caixa
(`frontend/app/conta-funcionario.tsx`, card no hub `fluxo-caixa.tsx`),
baseada em `FrmConFunc.frm` ("Acesso das Contas Por Funcionários..."),
colado pelo usuário.

**Propósito, nas palavras do usuário**: "é a tela de Configurações de
contas que o funcionário poderá visualizar: telas como geração de
Boletos, futura tela de Painel de movimentação e Previsão suas
visualizações de contas estarão sujeitas a configuração dessa tela." —
ou seja, esta tela é a FONTE da configuração; ela mesma não filtra nada,
só grava o vínculo. **Nenhuma tela consumidora foi retroalimentada ainda**
(ver "Pendência aberta" abaixo) — só o pedido explícito ("crie uma tela")
foi implementado nesta rodada.

**Mapeamento do `.frm`**: `Conta1` (esquerda, "Contas Disponíveis...") /
`Conta2` (direita, "Contas c/ acesso...") são um transfer-list clássico —
duplo clique move um item entre as duas listas; `Command1`/`Command2`
("Adicionar Todas"/"Remover Todas") movem a lista inteira de uma vez;
`Command3` ("Gravar") é replace-all-on-save: `DELETE FROM conta_func
WHERE func=X` seguido de um `INSERT` por item que ficou em `Conta2`.
`Funcs_LostFocus` recarrega as duas listas ao trocar de funcionário —
parte de `contas` (tabela `Contas`, situação implícita — a query original
não filtra por `situacao`, mas o cadastro novo de `Contas` já tem esse
campo, então a versão migrada filtra `situacao='A'`, mesma decisão já
usada em outras migrações desta sessão de preferir dado "ativo" por
padrão) e resolve quais já têm vínculo via `conta_func`.

**Adaptação de UI, decisão consciente**: duplo clique (paradigma
desktop/mouse) foi trocado por toque simples em cada linha — a tela é
web-only, mas um único toque move o item na hora (ícone de seta indicando
a direção do movimento em cada lista), mais direto que replicar
duplo-clique num app que também roda em touch/mobile no futuro. Mesmo
princípio de "não replicar truque de UI específico do VB6 quando existe
uma forma mais direta/moderna de fazer a mesma coisa" já usado noutras
telas.

**Implementado**:
- Backend: `backend/services/conta_func_service.py` — `get_vinculo`
  (devolve TODAS as `Contas` ativas + a lista de códigos já vinculados
  àquele funcionário, pro frontend montar as duas colunas) e
  `salvar_vinculo` (replace-all: `DELETE` + `INSERT` por item, dentro de
  uma única transação/commit). Rotas `GET/POST /api/conta-funcionario`.
  Tabela `conta_func` (conta, func) **já existia** no schema — já era
  usada como delete-guard em `funcionarios_service._delete_funcionario_sync`
  ("Contas de Funcionário"), mas sem CRUD próprio até agora. Permissão
  nova `CONTA_FUNC` ("Contas x Funcionário", nome exatamente 20 chars —
  no limite de `permissoes.nome` nvarchar(20)), menu FLUXO_CAIXA, ações
  padrão (só ABRIR/GRAVAR de fato usados). 5 testes unitários
  (`test_conta_func_service.py`), todos passando.
- Lista de funcionários reaproveita `GET /api/funcionarios-cadastro`
  (endpoint já existente, usado pelas telas de cadastro de funcionário) —
  filtro `situacao === "A"` aplicado no frontend (o endpoint não tem
  parâmetro de filtro por situação; replicar o filtro client-side foi
  mais simples que estender o endpoint só para este caso).
- Frontend: tela única compacta sem abas (mesmo padrão de `contas.tsx`),
  duas listas lado a lado com toque-para-mover, "Adicionar Todas"/
  "Remover Todas", Gravar no cabeçalho (padrão "Full CRUD Form Screen
  Standard"), ícone de Ajuda/Modo Didático.

**Pendência original (acima) parcialmente resolvida em 2026-07-25** — o
usuário pediu explicitamente pra ligar o crivo na Geração de Boletos.
Perguntado via `AskUserQuestion` as duas regras que ficaram em aberto
acima; respostas do usuário:
1. Funcionário sem NENHUM vínculo em `conta_func` → **não vê nenhuma
   conta** (padrão restritivo — precisa ser configurado explicitamente em
   "Contas x Funcionário" antes de aparecer qualquer conta pra ele).
2. Usuário **master sempre vê todas as contas ativas**, ignorando a
   configuração (mesmo padrão de bypass de `can()`).

**Implementado**: `conta_func_service._list_visiveis_sync`/
`list_visiveis` (novo) — `is_master=True` devolve todas as `Contas`
ativas; senão, só as vinculadas ao `funcionario` via JOIN com
`conta_func` (lista vazia se não há vínculo nenhum). Rota
`GET /api/conta-funcionario/visiveis?funcionario=&master=`. 4 testes
novos (`TestListVisiveis`), suite completa sem regressão.

**Consumido em `frontend/app/geracao-boletos.tsx`** (aba Importação
Retorno, campo "Conta") — trocou `GET /api/contas-caixa` (todas as
contas, sem crivo) por `GET /api/conta-funcionario/visiveis`, passando
`usuarioCodigo`/`isMaster` de `usePermissions()`. Efeito de carregamento
separado do efeito de mount (`useEffect([conn, isMaster,
usuarioCodigo])`) porque esses dois campos só ficam prontos depois de um
carregamento assíncrono próprio do hook de permissões — se ficassem no
mesmo efeito do mount (`[router]`), a busca rodaria cedo demais com
`isMaster=false`/`usuarioCodigo=null` (valores iniciais) e nunca
re-executaria. Lista vazia (funcionário não-master sem nenhuma conta
liberada) mostra um aviso inline sob o campo, apontando pra "Contas x
Funcionário".

**Ainda não estendido** às demais telas que hoje mostram/filtram contas
de caixa sem crivo nenhum (ex.: Entrada/Saída de Caixa, e as futuras
"Painel de Movimentação"/"Previsão", que nem existem ainda) — só o campo
pedido explicitamente (Geração de Boletos) foi ligado nesta rodada. Ao
tocar em qualquer tela nova/existente que liste contas de caixa/banco
por conta própria, considerar se o mesmo crivo deveria se aplicar, e
confirmar com o usuário antes de estender — não é gatilho de varredura
retroativa automática.

---

**Status: 🟢 Fases 1, 2 e 3 implementadas e testadas ao vivo (2026-07-22/23)**
— núcleo manual (Abertura nos 3 tipos Geral/Parcial/Contábil, Digitação de
Estoque, Fechar, Cancelar) + lista de "quem digitou o quê" + os 5
relatórios (Contagem, Conferência, Crítica, Resultado, Divergência) + os 2
disparos automáticos (mensal + diário contábil). Backend restaurado pelo
usuário em produção (porta 8081) 2026-07-23, código mais recente confirmado
ao vivo. Só falta o item 8 do menu legado ("Registro de Inventário",
código morto no VB6, proposta é não portar — ver pergunta #3, histórico).
**UI no navegador ainda não clicada manualmente por um humano de ponta a
ponta** — todo teste de backend foi via `curl`/script Python direto contra
uma instância temporária (ver nota no fim desta seção); vários bugs reais
já foram achados e corrigidos pelo usuário clicando na tela de verdade
durante esta sessão, então a Digitação/Painel/Relatórios já foram testados
manualmente em partes — só falta um passe completo e deliberado.

### Fase 3 — disparos automáticos (2026-07-23, user-directed "comece a fase 3")

Rastreei o código-fonte exato antes de implementar (não presumir em cima
do resumo já registrado abaixo em "Funções de inicialização automática")
— `Geral\Mdl_Proc.bas`, subs `InventarioAutomatico` (linha 26305),
`InventarioPostoAutomatico` (linha 26233) e o ramo `inventario_contabil`
de `MudaDataSistema` (linhas 6933-6942), lidos por completo.

- **Mensal, sem módulo Posto** (`_inventario_automatico_mensal_sync`,
  porta `InventarioAutomatico`): snapshot de TODO `pecas` com estoque
  (`qtd+reservado+reservado_os>0 OR estoque_cli>0 OR estoque_for>0`, e
  `qtd<1000000` como guarda de qualidade de dado, não regra de negócio)
  direto em `inventario_old`, na data do dia 1 do mês corrente — não abre
  balanço de verdade, zero efeito em `pecas.qtd`/`movimentacao`.
- **Mensal, com módulo Posto** (`_inventario_posto_automatico_mensal_sync`,
  porta `InventarioPostoAutomatico`, substitui inteiramente a rotina
  acima nesse segmento — regra confirmada pelo usuário no levantamento
  original, nunca as duas juntas): snapshot do estoque de combustível a
  partir de `tanque_estoque` (mesma fonte já lida pelo módulo Posto), não
  de `pecas.qtd`. Só marca como fechado quando TODO combustível cadastrado
  já tem alguma leitura no mês; senão fica em aberto e tenta de novo na
  próxima chamada (mesmo comportamento do legado). **Melhoria em relação
  ao legado**: idempotência também POR COMBUSTÍVEL (checa se já existe
  linha em `inventario_old` antes de inserir) — o original reinseria tudo
  de novo a cada tentativa incompleta (loop sem checar duplicata), gambiarra
  de falta de rastreio granular, não regra de negócio.
- **Diário, sem módulo Posto** (`_inventario_contabil_diario_sync`, porta
  o ramo `inventario_contabil` de `MudaDataSistema` — o ramo IRMÃO dessa
  mesma sub, de reconciliação de estoque hardcoded por CNPJ, foi
  descartado por completo no levantamento original, "pode ser
  desconsiderada"): snapshot diário de TODO `pecas` ativo + itens de O.S.
  aberta/fechada cujo código começa com "P", em `inventario_contabil`/
  `inventario_contabil_os` — puro arquivo histórico, zero efeito em
  estoque. Retenção de 60 dias (`DELETE ... WHERE data<=hoje-60`, mesma
  regra do legado). **Bug real do legado corrigido, não replicado**: o
  INSERT de `inventario_contabil_os` usava uma data/hora HARDCODED
  literal (`'2021-04-15','12:27:39'`, claramente sobra de teste/
  desenvolvimento nunca corrigida — o INSERT irmão de `inventario_contabil`,
  logo acima no mesmo bloco, já usa `Date`/`Time` dinâmicos normalmente) —
  aqui os dois usam a data/hora de HOJE.
- **Idempotência sem o sentinela mágico do legado**: `usuario_abertura=-2`
  (legado, "sistema") virou uma coluna própria `inventario_controle.
  automatico BIT NULL` (migração idempotente) — mesma "melhoria proposta"
  já registrada no levantamento original.
- **Orquestrador** (`_executar_rotinas_automaticas_sync`): módulo Posto
  ativo → só a rotina mensal de Posto (sem o diário contábil pra esse
  segmento); sem Posto → a rotina mensal genérica E o diário contábil, as
  duas. Regra de negócio confirmada pelo usuário no levantamento original,
  sobrepõe a leitura literal do gate do VB6 (`Posto And NFCe_Ws`, que o
  próprio código de `InventarioAutomatico` contradiz internamente ao ter
  seu próprio branch condicional pra quando Posto está ativo — mantido
  como achado de leitura, mas não replicado, já que a intenção real
  confirmada é exclusividade total entre as duas rotinas mensais).
- **Disparo**: endpoint `POST /api/inventario/rotinas-automaticas` (sem
  permissão nem log de auditoria — não é ação de tela, é manutenção
  invisível de sistema), chamado pelo frontend (`useDashboard.ts`) uma vez
  por sessão do app, no boot da Tela Principal, silencioso (erro engolido,
  nunca gera toast) — mesmo padrão já usado por `loadEmpresa`. Endpoint em
  si já é idempotente (reverifica antes de fazer qualquer coisa), o ref do
  frontend só evita repetir a chamada de rede a cada foco de tela dentro
  da mesma sessão.
- **Testado ao vivo contra `GERDELL`/`BARESTELA`** (instância temporária,
  porta 8091): confirmou módulo Posto ativo nesta conexão → rodou só a
  rotina mensal de Posto (fechou imediatamente, 0 combustíveis cadastrados
  = `0>=0`, mesmo comportamento trivial do legado nesse caso) e pulou o
  diário; 2ª chamada confirmou idempotência (`mensal_executado`/
  `diario_executado` ambos `false`). **Validação extra de sintaxe SQL**:
  chamei as funções do caminho NÃO-Posto (mensal genérico + diário
  contábil) diretamente, fora do orquestrador, com `rollback()` explícito
  ao final (sem `commit`) só pra confirmar que a SQL roda sem erro contra
  o schema real, sem persistir nada — as duas rodaram sem erro. 10 testes
  novos (mockados) — 68 testes no arquivo, todos passando.
- **Não testado ao vivo**: o caminho Posto COM combustíveis cadastrados de
  verdade (nenhuma conexão de teste disponível tinha isso) — a lógica en
  si (join com `tanque_estoque`, idempotência por combustível) foi só
  validada por teste unitário mockado, não contra dados reais.

### Tipo de balanço "Parcial" adicionado 2026-07-23, user-directed ("o mais importante")

Terceiro tipo de balanço, confirmado pelo usuário via foto da tela real do
legado (`FrmInvAbe.frm` — combo "Tipo de balanço" com 3 opções: Geral,
Parcial, Contábil, "Parcial" pré-selecionado por padrão) — resolve
definitivamente a "pergunta aberta #1" do levantamento original (o
screenshot mostrava "Parcial" como valor padrão do combo, que não batia
com nenhuma letra testada no código na época).

- **Regra de negócio** (confirmada pelo usuário): não pré-carrega o
  estoque nenhum na Abertura — `inventario` fica vazio até a Digitação de
  Estoque incluir item por item. No Fechamento, só os itens que FORAM
  digitados entram no ajuste de estoque; o resto do catálogo (nunca
  contado) não é tocado — nem zerado, nem alterado de forma nenhuma.
  Diferente do Geral, que pré-carrega TUDO e por isso "zera" (ajusta pra
  baixo) todo item não recontado no Fechamento.
- **Implementação**: `tipo_balanco='P'`, `TIPOS_BALANCO["P"]="Parcial"`.
  `_abrir_sync` ganhou um 3º branch que não faz NENHUM insert em
  `inventario` pro tipo Parcial (só o arquivamento do balanço anterior via
  `inventario_old` roda, igual pros outros tipos). **Nenhuma mudança foi
  necessária em `_fechar_sync`** — o `INNER JOIN` já existente contra
  `inventario` naturalmente só afeta as linhas que existem (ou seja, só o
  que foi digitado), então o comportamento certo "vem de graça" só por
  Parcial não pré-carregar nada; o `if tipo_balanco != "C"` já cobria "P"
  desde sempre (só "C" era excluído).
- **Frontend**: opção adicionada ao combo de Abertura (`inventario.tsx`,
  ordem Geral/Parcial/Contábil igual ao legado), **Parcial é o padrão
  pré-selecionado** (`tipoAbertura` inicial = "P", não "G" — confirmado
  pelo usuário, mesmo comportamento do combo real). Badge de divergência e
  diálogo de confirmação do Fechar reescritos pra 3 variantes de texto
  (Geral: ajusta tudo, inclusive zera não-digitado; Parcial: ajusta só o
  digitado; Contábil: nunca ajusta). Contador "Total Digitados" no Painel
  mostra só "X Produtos" pro tipo Parcial (sem "de Y", já que Y sempre é
  igual a X nesse tipo — toda linha em `inventario` só existe porque foi
  digitada).
- **Bug de documentação encontrado de passagem**: o texto de Ajuda ("Modo
  Didático") do Painel dizia que o tipo Contábil "não pré-carrega nada" —
  **isso estava errado**, era na verdade a descrição do Parcial (o texto
  original foi escrito antes de Parcial ser confirmado como tipo
  distinto, na época em que só se cogitava 2 tipos). Corrigido pros 3
  tipos com a descrição certa de cada um.
- **Testado ao vivo contra `GERDELL`/`BARESTELA`**: abriu Parcial → status
  confirmou nada pré-carregado (0 de 0) → buscou item não-cadastrado no
  balanço (`ja_contado: false`, sem linha prévia) → incluiu 1 item com
  valor divergente do sistema → Divergência mostrou só esse item → Fechou
  → confirmado que só aquele item foi ajustado (dado de teste,
  intencionalmente deixado como está a pedido do usuário, não restaurado).
  4 testes unitários novos (Abrir sem pré-carregar, Fechar ajustando
  Parcial) — 70 testes no arquivo, todos passando.

### Bug real corrigido 2026-07-23 — Crítica/Divergência mostravam item nunca contado

Achado ao vivo pelo usuário: abriu um balanço Geral novo, sem digitar
nada, e o Relatório de Divergência (e o badge do Painel, mesmo endpoint)
já mostrava itens divergentes. Mesma causa raiz do bug de "Total
Digitados" corrigido antes nesta sessão, só que vazando pro relatório em
vez do contador: `_relatorio_critica_sync`/`_relatorio_divergencia_sync`
comparavam `estoque_balanco <> estoque_atual+reservado` sem checar se o
item tinha sido REALMENTE contado — num balanço Geral, todo item com
estoque no sistema nasce "divergente" por padrão (estoque_balanco fica em
0 até alguém digitar), então o relatório confundia "ainda não contado"
com "contado e divergente de verdade".

Corrigido acrescentando `AND i.contado_em IS NOT NULL` nos dois
relatórios — mesma coluna já usada pro contador. Único cuidado: esse
filtro só entra quando a query lê o balanço CORRENTE (`inventario`);
consultar um balanço fechado antigo via `data` (`inventario_old`) não tem
essa coluna (não existe no schema dessa tabela — nunca foi copiada pra lá
na Abertura), então o filtro fica de fora nesse caso e o relatório
histórico continua mostrando pela regra antiga (sem essa distinção,
porque não tem como saber retroativamente).

Testado ao vivo: balanço Geral aberto, 0 digitado → Divergência/Crítica
vazios (antes mostrava itens). Contou 1 item IGUAL ao sistema → continua
fora dos dois relatórios (contado mas não diverge). Contou 1 item
DIFERENTE do sistema → aparece nos dois (contado E diverge, o cenário
real que os relatórios devem capturar). 4 testes ajustados (referência de
índice de query fixa trocada por "a última query", já que
`_ensure_usuario_digitacao_col` passou a rodar também dentro dessas duas
funções, deslocando os índices).

### Bug real corrigido 2026-07-23 — grupo expandido não atualizava ao gravar

Achado ao vivo pelo usuário: gravar um item (Incluir/Alterar) não
atualizava a lista de um accordion de usuário já expandido — só o
resumo/contagem do cabeçalho era refeito (`carregarContados`), a lista de
itens em si (`itensPorGrupo`) só é buscada quando o accordion é clicado
(`toggleGrupoUsuario`, "a quebra de lista só é atualizada se clicar no
usuário" — pedido explícito de performance, ver "Rastreio de quem digitou
cada item" acima). Consequência: quem estava com o próprio grupo aberto
digitando vários itens seguidos não via a lista crescer, precisava
recolher e clicar de novo pra ver o item recém-gravado. Corrigido
extraindo a busca de itens de UM grupo pra uma função própria
(`carregarItensGrupo`), reaproveitada tanto pelo toggle (ao expandir)
quanto por uma nova `refrescarGruposAbertos` (chamada depois de todo
gravar bem-sucedido, refaz a busca de TODO grupo que já estiver
expandido — não só o do usuário atual, já que outro gerente pode estar
com o grupo de um colega aberto na tela ao mesmo tempo) — mantém o
princípio original de só buscar de novo o que já está visível, sem virar
uma recarga geral da tela inteira.

### Bug real corrigido 2026-07-23 — campo Quantidade sem `selectTextOnFocus`

Achado ao vivo pelo usuário na conexão real "Pajé": digitou 4249 num item
já contado antes, clicou Alterar, e gravou 42 (o valor ANTIGO, sem
alteração nenhuma). Causa provável: o campo Quantidade pré-preenche com o
valor já contado quando o item é reaberto pra edição (pedido explícito do
usuário, ver "Rastreio de quem digitou cada item" acima), mas — diferente
do campo Código, que já usa `selectTextOnFocus` desde o início — não
selecionava o conteúdo ao focar. Sem isso, a primeira tecla digitada é
INSERIDA em vez de SUBSTITUIR o valor antigo; numa conexão lenta, o foco
automático (que só dispara depois que a resposta da busca chega) pode
atrasar o suficiente pra atrapalhar quem já começou a digitar, fazendo o
valor novo não "pegar" direito. Corrigido adicionando `selectTextOnFocus`
+ o mesmo bloqueio de autofill do navegador já usado no campo Código
(`autoComplete="new-password"` etc.) — não confirmado 100% contra a
conexão Pajé (não temos acesso direto pra reproduzir), mas é uma correção
de UX real e segura independente da causa exata, replicando o padrão já
estabelecido pro campo Código nesta mesma tela. **Pendente**: confirmação
do usuário de que o problema não se repete depois desta correção.

### Bug real corrigido 2026-07-23 — "Total Digitados"/"já contado" quebrava no tipo Contábil

Achado ao vivo pelo usuário logo depois da Fase 2 acima: abriu um balanço
**Contábil**, sem digitar nada, e a tela já mostrava "Total Digitados: 236
de 236 Produtos" e o badge de divergência "Nenhuma divergência até agora".

**Causa raiz**: o critério "já contado" usado em `_status_sync`
(contador do Painel), `_buscar_item_sync` (`ja_contado`),
`_resumo_por_usuario_sync` e `_listar_itens_sync` era
`estoque_balanco<>0` — funciona pro tipo **Geral** (a coluna nasce em 0,
`DEFAULT` do banco, até alguém digitar), mas **quebra pro tipo Contábil**:
a própria Abertura Contábil já pré-carrega `estoque_balanco` = saldo do
sistema (`qtd+reservado+reservado_os`, sempre não-zero pra item com
estoque) pra TODO item, por desenho (`_abrir_sync`, branch `else`) — então
"linha com valor não-zero" nunca vira sinal de "alguém digitou" nesse
tipo, é assim desde a Abertura.

**Fix**: coluna nova `inventario.contado_em` (DATETIME NULL, migração
idempotente em `_ensure_usuario_digitacao_col` — mesmo helper, nome não
mudou pra não quebrar as chamadas já espalhadas pelo arquivo), setada só
por Incluir/Alterar (`GETDATE()`), nunca pela Abertura. Critério "já
contado" trocado pra `contado_em IS NOT NULL` nos 4 lugares acima —
funciona igual pros 2 tipos de balanço, e de quebra corrige outro caso
(item contado como ZERO de propósito não fica mais marcado como "não
contado", o que acontecia com `estoque_balanco<>0`). **Backfill** incluído
na mesma migração (`UPDATE inventario SET contado_em=GETDATE() WHERE
usuario_digitacao IS NOT NULL`, só roda uma vez — guardado por `NOT
EXISTS (SELECT 1 FROM inventario WHERE contado_em IS NOT NULL)`) pra não
"zerar" a contagem de um balanço que já tinha itens digitados antes desta
coluna existir.

**Gotcha de SQL Server descoberto testando ao vivo**: a primeira versão
tentava `ALTER TABLE ... ADD contado_em` e o backfill `UPDATE` que
referencia essa coluna no MESMO batch (dentro de um único `IF NOT
EXISTS(...) BEGIN ... END`) — deu "Invalid column name 'contado_em'"
porque o SQL Server faz bind de nome de coluna em tempo de PARSE do batch
inteiro, antes de decidir se o `IF` roda ou não. Corrigido separando em 2
`cur.execute()` distintos (ALTER numa chamada, backfill guardado em
outra) — mesma lição já registrada noutro lugar deste arquivo sobre erro
de sintaxe SQL Server só aparecer no teste ao vivo, nunca no teste
unitário com cursor mockado.

**Badge de divergência — reversão parcial no mesmo dia, user-directed**:
a primeira versão deste fix escondia o badge inteiro pro tipo Contábil
(`tipo_balanco !== "G"` → não busca/mostra nada). O usuário pediu de volta
("mostrar a frase resumida de divergência se houver nesse card como
antes") — o badge volta a aparecer pros 2 tipos, só o TEXTO muda por tipo:
Geral mantém a frase original ("é o que o Fechamento vai ajustar no
estoque"); Contábil troca pra deixar claro que o Fechamento não ajusta
estoque nesse tipo, independente da divergência mostrada ("balanço
Contábil não ajusta o estoque no Fechamento"). Lição: a prévia de
divergência é informação útil por si só (ver o que diverge), mesmo em um
tipo de balanço onde o Fechar não age em cima disso — não devia ter sido
escondida, só a frase que sugeria causalidade com o Fechar precisava
mudar.

Testado ao vivo contra `GERDELL`/`BARESTELA`: abriu Contábil → status
mostrou corretamente "0 de 1" (não "1 de 1") → busca do item mostrou
`ja_contado: false` mesmo com `estoque_balanco_atual: 10.0` pré-carregado
→ incluiu contagem → status virou "1 de 1", `ja_contado: true` → resumo
por usuário e lista de itens também corretos (só o 1 item realmente
digitado, não os pré-carregados) → cancelou o balanço de teste ao final. 2
testes unitários reescritos (`TestBuscarItem`, `TestListarItens`) + 1
teste novo (`test_abertura_contabil_pre_carrega_saldo_mas_nao_e_ja_contado`)
— 57 testes no arquivo, todos passando.

### Fase 2 — os 4 relatórios restantes (2026-07-23, user-directed "continuar com o módulo de inventário")

Implementados **Conferência**, **Crítica**, **Resultado** e **Divergência**
— só o eixo de agrupamento **Nível** foi portado (mesmo escopo já usado no
Relatório de Contagem); os eixos "Área/Prateleira" (`FrmInvCar.frm`) e
"Descrição/Fornecedor" (`FrmInvDes.frm`) do legado, que replicam os MESMOS
4 relatórios só trocando o agrupamento, não foram portados — não pedido,
ficaria pra uma extensão futura se for solicitado.

- **Fonte VB6 retraçada por completo** (`FrmRelInvConf.frm`,
  `FrmRelInvCrit.frm`, `FrmRelInvRes.frm`, `FrmRelInvDiv.frm`) — nenhum dos
  4 chama `Inventario.bas` (achado importante: as rotinas de impressão
  desse `.bas` pertencem à família "por Área"/"por Descrição", não à
  família "por Nível"). Cada `.frm` monta o SQL inline no próprio
  `Mostra()`.
- **Achado de modelagem crítico, confirmado no próprio código do Abrir já
  existente** (`_abrir_sync`, tipo Geral): `custo_inventario`/
  `custo_reposicao`/`preco_venda` usados em Resultado e Divergência vêm de
  `inventario`/`inventario_old` (congelados no momento do balanço), **não**
  do preço/custo atual de `pecas` — os 4 relatórios novos leem sempre da
  tabela de balanço, nunca de `pecas` pra esses valores.
- **Conferência** (`_relatorio_conferencia_sync`): 3 grupos SEMPRE
  separados por `tipo_peca` (Revenda/Consumo/Imobilizado — nunca somados
  entre si, mesmo comportamento das 3 abas fixas do legado), agrupado por
  Nível 1 dentro de cada tipo, com toggle "listar zerados". Sempre lê o
  balanço CORRENTE — o legado nunca permite escolher outra data aqui.
- **Crítica** (`_relatorio_critica_sync`): só itens onde `estoque_balanco
  <> estoque_atual+reservado`. O legado esconde deliberadamente a
  quantidade do sistema (recontagem "às cegas") — replicado como padrão
  (oculto), mas com toggle "Mostrar estoque do sistema" no frontend (dado
  já vem na resposta, `estoque_sistema`; melhoria em relação ao legado, que
  não permitia revelar). Suporta consultar um balanço fechado antigo via
  `data` (`inventario_old`).
- **Resultado** (`_relatorio_resultado_sync`): valoriza a quantidade
  contada nos 3 preços/custos congelados. Réplica a assimetria real do
  cálculo legado — **arredonda o preço unitário primeiro (half-up), só
  depois multiplica pela quantidade e TRUNCA o total** (não os dois
  arredondados nem os dois truncados; confirmado com teste dedicado,
  `test_arredonda_unitario_antes_e_trunca_total_depois`). "Estoque
  Fornecedor" troca a quantidade usada só do lado `pecas` (o lado
  `veiculos` nunca usa essa opção, mesmo comportamento do legado — decisão
  consciente de replicar, não um bug). **2 inconsistências do legado
  identificadas e deliberadamente NÃO replicadas** (ver achado do rastreio
  em detalhe no commit/histórico desta sessão): a condição `TeN2`
  inconsistente no subtotal de nível 2 (não existe mais no port — a
  agregação virou um `reduce` correto, não um loop de quebra-de-controle) e
  o filtro extra `estoque_balanco>0` que só existia numa combinação
  específica de opções.
- **Divergência** (`_relatorio_divergencia_sync`): mesma condição de
  Crítica, mas mostrando os dois valores lado a lado e valorizados em 1 dos
  3 preços à escolha, com 5 critérios de ordenação. **Bug real do legado
  corrigido, não replicado**: o lado `veiculos` do `UNION` usava uma
  variável `um` nunca declarada em lugar nenhum do projeto (VB6 sem
  `Option Explicit` aceita como `Variant` vazio) — gerava SQL malformado
  (`as totq` sem expressão antes) que quebrava a consulta inteira sempre
  que existisse algum veículo no filtro. O port usa a mesma fórmula do lado
  `pecas` (`estoque_atual+reservado`) pro lado `veiculos`, claramente a
  intenção original (confirmado: o padrão é idêntico ao SELECT de peças
  logo acima, só trocando tabela/coluna de código).
- **Prévia de divergência no Painel antes de Fechar** (melhoria proposta já
  registrada na seção de levantamento, regra de negócio 9 — "é literalmente
  uma prévia do que o Fechamento vai lançar"): `app/inventario.tsx` busca
  um resumo (contagem + valor total em preço de venda) sempre que há
  balanço aberto e o usuário tem `INVENTARIO.REL_DIVERGENCIA`, mostrando um
  aviso destacado acima dos botões de ação — toque nele abre o relatório
  completo. Gated por permissão; quem não tem `REL_DIVERGENCIA` não vê o
  aviso, mas continua podendo Fechar normalmente.
- **Frontend**: tela nova `app/inventario-relatorios.tsx` — consolida os 4
  relatórios num seletor único (em vez de replicar a tela do Relatório de
  Contagem 4 vezes), reaproveitando a mesma cascata de Nível 1-5. Cada
  relatório só aparece no seletor se o usuário tiver a permissão
  correspondente (`INVENTARIO.REL_CONFERENCIA`/`REL_CRITICA`/
  `REL_RESULTADO`/`REL_DIVERGENCIA`, mesmo padrão de `REL_CONTAGEM` da Fase
  1). Botão "Relatórios" no Painel (`inventario.tsx`), ao lado do já
  existente "Relatório de Contagem", visível se o usuário tem qualquer uma
  das 4 permissões novas. Impressão segue o padrão já estabelecido
  (`print-report-header.ts`, cabeçalho da empresa, sem mostrar filtro da
  tela). Modo Didático: `AjudaInventarioModal.tsx` foi parametrizado
  (`titulo`/`itens`, mesmo padrão de `AjudaPedidoModal.tsx`) — o painel
  continua com seu conteúdo original, a tela de relatórios usa seu próprio
  conjunto de itens de ajuda.
- **Regra [GLOBAL] "feedback visual >3s"** (adicionada no CLAUDE.md nesta
  mesma sessão, motivada pelo bug do Fechar Inventário "parecia
  congelado") aplicada retroativamente às telas já existentes do módulo
  tocadas nesta rodada: botão "Gerar Relatório" (Contagem e Relatórios),
  Buscar/Incluir/Alterar em Digitação de Estoque (Incluir/Alterar viraram
  `salvandoAcao` em vez de um `salvando` booleano genérico, pra mostrar o
  spinner só no botão certo), e o "Carregando…" de cada accordion de
  usuário ganhou um `ActivityIndicator` ao lado do texto.
- **Testes**: 30 testes novos em `test_inventario_service.py`
  (`TestRelatorioConferencia`/`TestRelatorioCritica`/`TestRelatorioResultado`
  /`TestRelatorioDivergencia`), mockados (cursor/conexão fake, sem tocar
  banco real) — 56 testes no arquivo inteiro, todos passando. Testado
  também ao vivo contra `GERDELL`/`BARESTELA` (instância temporária de
  backend, porta 8091, mesmo padrão da Fase 1): abriu um balanço Geral de
  teste, rodou os 4 endpoints novos (Conferência com `listar_zerados=true`,
  Crítica antes/depois de digitar um item, Resultado com as 2 fontes de
  estoque, Divergência com filtro de nível e data histórica via
  `inventario_old`), confirmou os 4 rodam sem erro de SQL e devolvem dados
  corretos, e cancelou o balanço de teste ao final (estado do banco restaurado).
- **Correção incidental encontrada nesta rodada**: um `.` solto sobrando de
  uma edição anterior em `inventario_service.py` (linha 633, dentro de um
  comentário) quebrava a sintaxe do arquivo inteiro (`SyntaxError`),
  impedindo até a coleta dos testes — corrigido antes de começar a Fase 2.
  Os 4 testes de `TestFechar` que cobriam o ajuste de estoque também
  precisaram ser reescritos (estavam mockando a implementação antiga, em
  loop por item, de antes da reescrita set-based da sessão anterior).

### Rastreio de quem digitou cada item (2026-07-23, user-directed)

Cenário real: vários usuários digitando o mesmo balanço em paralelo, cada
um cobrindo uma área/nível de produto diferente — faz sentido saber quem
contou o quê. Coluna nova `inventario.usuario_digitacao` (INT NULL, FK
`funcionarios.codigo_int`) — **primeira coluna genuinamente nova deste
módulo**, sem equivalente no legado (o legado só audita Abertura/
Fechamento/Cancelamento em `inventario_controle`, nunca por item contado).
Migração idempotente (`_ensure_usuario_digitacao_col`, mesmo padrão de
`pedido_common._ensure_qtd_pessoas_col`) — aplicada sozinha na primeira
chamada de Incluir/Alterar/Listar, sem passo de migração manual.

- `POST /api/inventario/itens/incluir`/`alterar` agora gravam
  `usuario_alteracao` do request nessa coluna.
- `GET /api/inventario/itens` (novo) lista os itens já contados no balanço
  aberto — código, descrição (cascata pecas/veiculos), quantidade contada
  e nome de quem digitou (`COALESCE(NULLIF(nome_guerra,''), nome)`, mesmo
  critério nome_guerra-primeiro já usado em outros papéis de funcionário
  no resto do app).
- Frontend (`app/inventario-digitacao.tsx`): card novo abaixo do
  formulário, lista os itens contados com quem digitou cada um, atualiza
  sozinha após cada Incluir/Alterar (mais um ícone de atualizar manual).
- **Bug de sintaxe SQL Server achado e corrigido testando ao vivo**:
  escrevi a ordenação como `ORDER BY x IS NULL, ...` (válido em Postgres/
  MySQL) — SQL Server não aceita `IS NULL` como expressão fora de WHERE/
  CASE, dava erro 156 "Incorrect syntax near 'IS'". Corrigido pra
  `ORDER BY CASE WHEN x IS NULL THEN 1 ELSE 0 END, ...`. Reforça que os
  testes unitários (cursor mockado) não pegam erro de sintaxe SQL real —
  só o teste ao vivo contra o banco pegou este.
- Atalho de teclado adicionado no mesmo dia (pedido explícito do usuário):
  Enter no campo Quantidade já grava sem precisar do mouse — Incluir se o
  item ainda não foi contado, Alterar direto (sem confirmação) se já foi.
  Foco pula pra Quantidade sozinho assim que a busca do código encontra o
  item.
- Autofill do Chrome desabilitado no campo Código (estava disparando o
  popup "Salvar documento de identificação") — mesmo padrão já usado no
  campo Cliente (`autoComplete="new-password"` etc.).

### Fase 1 — núcleo manual — implementada

- **Backend**: `backend/models/inventario.py`, `backend/services/
  inventario_service.py` (`status`/`abrir`/`buscar_item`/`incluir_item`/
  `alterar_item`/`fechar`/`cancelar`), `backend/routes/inventario.py`
  (7 endpoints, registrado em `server.py`). Permissão `INVENTARIO` ganhou
  4 ações novas (`ABERTURA`, `DIGITACAO`, `FECHAR`, `CANCELAR`) além do
  `ABRIR` que já existia. 26 testes unitários em
  `backend/tests/unit/test_inventario_service.py` (cursor/conexão
  mockados, sem tocar banco real) — todos passando.
- **Frontend**: `app/inventario.tsx` (Painel — status do balanço,
  form de Abertura com Data+Tipo, botões Fechar/Cancelar com confirmação)
  e `app/inventario-digitacao.tsx` (busca por código/chassi + grava
  contagem, Incluir soma / Alterar substitui). Ambas com Modo Didático
  (`src/components/inventario/AjudaInventarioModal.tsx` + tooltips via
  `IconButtonWithTooltip`). Card do hub em `transacoes.tsx` atualizado
  (não mostra mais "Em construção").
- **Decisões conscientes tomadas na implementação** (documentadas em
  comentário no topo de `inventario_service.py` também):
  - Checkboxes Revenda/Consumo/Imobilizado da Abertura legada são código
    morto no VB6 (`Vtipos` calculado e descartado antes de qualquer
    branch) — **não portados**, nem os checkboxes nem um filtro
    equivalente. A Abertura nova sempre inclui todos os tipos.
  - Bloco de export pra `.mdb`/PAF-ECF (`Check5` do `FrmInvAbe`) — fora
    de escopo, mesmo já declarado pra Produto Completo.
  - Gatilho de reagendamento Tray dentro do Fechamento legado — não
    portado nesta rodada (Produto Completo já tem o mecanismo Tray real;
    um gatilho a mais no Fechamento fica pra quando for pedido).
  - "Registro de Inventário" — não portado (código morto no legado, ver
    achado original do levantamento).
  - Ajuste de estoque no Fechamento pra item de `veiculos`: o legado
    grava uma `Movimentacao` órfã (o `UPDATE veiculos` correspondente
    está comentado/morto) — não replicado; item de veículo divergente
    simplesmente não gera `movimentacao` nem tenta atualizar nada.
  - `movimentacao.serie_nf='IV'` (Inventário) — série própria, mesma
    convenção de `'MV'` (Mov. de Produtos) e `'CM'` (Comanda/Pedido Bar).
- **Correção de nomenclatura, achada ao registrar o router em
  `server.py`**: já existe um router/service `veiculos` no backend, mas
  é a tabela **`veiculos_transp`** (frota própria de entrega/rotas,
  `routes/veiculos.py`+`services/veiculos_service.py`) — **totalmente
  diferente** da tabela `veiculos` (estoque de veículos à venda, chassi/
  nf_compra/nf_venda) que o Inventário usa. Mesmo nome em português, duas
  tabelas/domínios distintos — não confundir numa sessão futura.
- **Testado ao vivo contra `GERDELL`/`BARESTELA` 2026-07-23** (backend
  completo, via instância temporária do uvicorn numa porta separada —
  ver "Nota sobre o teste" abaixo): abrir (G) → buscar item → incluir →
  incluir de novo (soma) → alterar (substitui) → fechar → confirma
  `movimentacao` (`tipo='S00'`, `serie_nf='IV'`) e `pecas.qtd` ajustados
  corretamente, `inventario_controle.fechamento` e `controle.
  situacao_balanco='F'` gravados. Depois: abrir (C) → tentar abrir de
  novo (bloqueado com a mensagem certa) → cancelar → `inventario` da
  data zerado, `pecas.qtd` intocado, `controle.situacao_balanco='C'`.
  Dado de teste restaurado ao final (estoque de `P609` devolvido pro
  valor original, movimentação de teste apagada).
- **Bug real encontrado e corrigido durante o teste ao vivo**:
  `inventario.estoque_balanco` tem `DEFAULT ((0))` no banco (não NULL) —
  uma Abertura Geral já cria a linha em `inventario` pra TODO produto com
  estoque, com essa coluna zerada por padrão do próprio SQL Server, antes
  de qualquer digitação. `_buscar_item_sync` tratava "linha existe" como
  "já contado", mostrando "já contado: 0" pra item nenhum ter sido
  contado ainda. Corrigido pra usar o mesmo critério do legado
  (`FrmInvDig.CmDinclui_Click`: `estoque_balanco <> 0`) — só considera
  "já contado" quando o valor é diferente de zero. Frontend também
  ajustado: o botão "Alterar" não fica mais escondido até `ja_contado`
  (achado do mesmo bug) — fica sempre visível quando um item é
  encontrado, deixando o backend validar se a linha existe de verdade
  (mesmo comportamento do `FrmInvDig` legado, que também não escondia o
  botão). Teste de regressão adicionado
  (`test_linha_existente_com_saldo_zero_nao_e_ja_contado`).
- **Nota sobre o teste**: a instância de backend "de produção" desta
  sessão (porta 8081) foi registrada como Tarefa Agendada do Windows
  rodando como `SYSTEM` (ver seção de instalação de servidores mais
  acima neste arquivo/histórico da sessão) — sessões de terminal não
  elevadas não conseguem reiniciá-la (`Acesso negado` mesmo com
  `taskkill /F`), então ela ainda está rodando o código de ANTES desta
  Fase 1. Os testes de backend acima rodaram contra uma instância
  temporária própria (porta 8091, mesmo banco), já finalizada ao fim do
  teste. **Teste de UI no navegador não foi feito** — este ambiente não
  tem uma ferramenta de automação de navegador (`chromium-cli`/
  Playwright) disponível; só confirmei que o bundle do Metro compila
  os 3 arquivos novos (`inventario.tsx`, `inventario-digitacao.tsx`,
  `AjudaInventarioModal.tsx`) sem erro, via `curl` no bundle servido.
  **Pendente**: reiniciar o backend real (porta 8081, numa janela
  PowerShell Administrador — mesmo processo já usado antes nesta sessão
  pra registrar as tarefas agendadas) e clicar no fluxo manualmente no
  navegador antes de considerar isto validado ponta a ponta.

---

## Inventário — levantamento original (histórico, ver Fase 1 acima pro estado atual)

O usuário pediu explicitamente: **primeiro
levantar todo o ecossistema do módulo, só depois partir pra execução** —
não implementar nada desta seção ainda sem confirmação.

### Fonte VB6 rastreada

Menu legado "Inventário" (screenshot colado pelo usuário) tem 9 itens:
Abertura, Digitação Estoque, Relatório de Contagem, Relatório de
Conferência, Relatório de Crítica, Relatório de Divergência, Relatório de
Resultados, Registro de Inventário, Fechar Inventário, Cancelar
Inventário. Fontes:
- `Geral\FrmInvAbe.frm` — Abertura de Inventário.
- `Geral\FrmInvDig.frm` — Digitação dos Valores do Inventário (inclui
  importação de planilha Excel).
- `Geral\FrmRelInv.frm` — dispatcher genérico de relatório (usa a global
  `CodRelInventario` setada ANTES de carregar o form pra decidir qual dos
  6 relatórios abrir — 0=Conferência, 1=Contagem, 2=Resultado,
  3=Crítica, 4=Registro, 5=não usado — e delega pra um dos 3 forms de
  agrupamento conforme o rádio Ordenado-por escolhido: `Opt(0)`=Nível
  → `FrmRelInvConf`/`FrmRelInvCon`/`FrmRelInvRes`/`FrmRelInvCrit`,
  `Opt(1)`=Área/Prateleira → `FrmInvCar`, `Opt(2)`/`Opt(3)`=Descrição/
  Fornecedor → `FrmInvDes`).
- `Geral\FrmRelInvConf.frm` — Conferência por Nível (3 abas fixas:
  Revenda/Consumo/Imobilizado, uma grid por aba).
- `Geral\FrmRelInvCon.frm` — Contagem por Nível (grid única, checkboxes
  Revenda/Consumo/Imobilizado, "Listar somente ativos").
- `Geral\FrmRelInvRes.frm` — Resultado por Nível (grid única, valores
  R$ Custo Inventário/Reposição/Venda × quantidade, com opção rara
  "Estoque Fornecedor" — só visível pra `App.EXEName` = LIVRARIA/JAMER ou
  `App.Minor=6`, ou seja **não se aplica a este client** — ver pergunta
  aberta #6).
- `Geral\FrmRelInvCrit.frm` — Crítica por Nível (mostra `estoque_balanco`
  + coluna em branco "Recontagem" pra anotar à mão/reimprimir).
- `Geral\FrmRelInvDiv.frm` — Relatório de Divergência (Resultado ×
  0/2/3/4/5 do menu = combina Nível 1-5 filtráveis em cascata + 3 opções
  de preço unitário Venda/Custo Inventário/Custo Reposição + 5 critérios
  de ordenação; a única tela do grupo com Imprimir dedicado próprio, e
  filtra só os itens DIVERGENTES — `estoque_atual+reservado <>
  estoque_balanco`).
- `Geral\FrmInvCar.frm` — os mesmos 4 relatórios (Conferência/Contagem/
  Resultado/Crítica), agrupados por Área+Prateleira em vez de Nível
  (`CodRelInventario` decide qual chamar). Tem "Gerar Planilha" (Excel).
- `Geral\FrmInvDes.frm` — os mesmos 4 relatórios agrupados por
  Descrição/Fornecedor (com combo de filtro por Fornecedor). Também tem
  "Gerar Planilha".
- `Geral\Inventario.bas` — módulo global com as 2 rotinas de negócio real
  (`Fecha_Inventario`, `Cancela_Inventario`, chamadas por "Fechar"/
  "Cancelar" do menu) + as 8 rotinas de impressão que implementam os 4
  relatórios × 2 eixos de agrupamento (Área, Descrição) — mesma lógica de
  consulta/agrupamento já visível nas 4 telas "por Nível" acima, só
  trocando a cláusula de agrupamento. Rastreado por completo via `Read`
  direto (achado em `C:\Desenv\VB6\SQLSERVER\Geral\Inventario.bas` — não
  em "Diario Access-SQL\SQLSERVER" como uma nota antiga do CLAUDE.md
  sugere; o caminho real hoje é só `C:\Desenv\VB6\SQLSERVER\`).

### Ecossistema de dados (tabelas envolvidas)

- **`controle`** (linha única por empresa, já mapeada por outras telas):
  `data_balanco` (data do inventário aberto/mais recente),
  `situacao_balanco` (`A`=Aberto, `F`=Fechado, `C`=Cancelado — confirmado
  direto no código, não suposição), `tipo_balanco` (`G`=Geral, `C`=algo
  ainda não confirmado — ver pergunta #1), `cod_rel` (já usado por outra
  tela: `I`=exibe/ordena por Código Interno, outro valor=Código de
  Fábrica — mesmo campo documentado em `controle_service.py`).
- **`inventario`** (tabela "corrente" — o balanço ABERTO agora):
  `codigo_interno`, `data`, `preco_custo`, `preco_venda`,
  `custo_inventario`, `custo_reposicao`, `estoque_atual`, `custo_medio`,
  `estoque_balanco` (a quantidade contada/digitada), `reservado`,
  `reservado_os`, `estoque_cli`, `estoque_for`. **Confirmado ao vivo
  contra `GERDELL`/`BARESTELA`** (2026-07-22) — todas as colunas batem
  exatamente com o que o VB6 assume, nenhum mismatch de nome/tipo
  (diferente do que rolou com Cliente) — 198 linhas hoje (balanço mais
  recente, já fechado).
- **`inventario_old`** — histórico: toda vez que um novo inventário abre,
  `FrmInvAbe.cmbok_Click` primeiro copia o conteúdo inteiro de
  `inventario` pra cá (`INSERT ... SELECT ... FROM inventario`) e só
  depois faz `DELETE FROM inventario` — ou seja, `inventario` é sempre só
  o balanço ATUAL, `inventario_old` acumula TODOS os anteriores (a coluna
  `data` diferencia qual balanço é qual). Relatórios que recebem uma data
  diferente da atual (`DataDif`/`DataBal`, setados em `FrmRelInvDiv`)
  buscam em `inventario_old` em vez de `inventario`.
- **`Inventario_Controle`** — 1 linha por data de balanço, auditoria pura:
  `Data`, `Abertura`/`Hora_Abertura`/`Usuario_Abertura`,
  `Reabertura`/`Hora_Reabertura`/`Usuario_Reabertura`,
  `Fechamento`/`Hora_Fechamento`/`Usuario_Fechamento`,
  `ReFechado`/`Hora_Refechado`/`Usuario_Refechado`,
  `Cancelamento`/`Hora_Cancelamento`/`Usuario_Cancelamento`. Todo
  Abrir/Reabrir/Fechar/Cancelar grava aqui, além de logar em `Logs`
  (tabela de auditoria antiga do VB6 — o equivalente novo já migrado é
  `log_auditoria`, ver "Log de auditoria" na memória de projeto).
- **`pecas`**: `tipo_peca` (0=Revenda,1=Consumo,2=Imobilizado — já
  confirmado existir, usado em Serviços/Produto Completo),
  `area`/`prateleira`/`escaninho` (posição física — já existem, migrados
  junto de Produto Completo), `situacao` (`A`=Ativo, usado no filtro
  "Listar somente ativos"), `classificacao_fiscal`, `fornecedor`,
  `codigo_fab`, `codigo_int`, `qtd`, `reservado`, `reservado_os`,
  `Estoque_Cli`, `Estoque_For` — todos já existentes (Produto Completo já
  migrou ~150 colunas de `pecas`).
- **`niveis`** (`nivel1..nivel5`, `descr`, `cod_nivel`) — **já migrada e
  em uso** por "Alterações Cadastro de Produtos Níveis"
  (`produtos_niveis_service.py`) — reaproveitável direto, não precisa
  recriar.
- **`area`** (`codigo` smallint, `descricao` nvarchar) — lookup físico de
  área de estoque, referenciado por `DescArea()` em `Inventario.bas`.
  **Confirmado ao vivo**: a tabela existe, só 2 linhas cadastradas hoje —
  ainda não confirmado se é a MESMA "Área" já citada em Tabelas
  Auxiliares (CLAUDE.md > "Card List Ordering") ou uma tabela paralela;
  com só 2 linhas de teste não dá pra decidir pelos dados sozinhos —
  checar o código-fonte de Tabelas Auxiliares antes de reaproveitar.
- **`veiculos`** — toda query do módulo Inventário faz `UNION` entre
  `pecas` e `veiculos` (chassi como código, mesmas colunas).
  **Confirmado ao vivo: a tabela existe no schema, mas com 0 (zero)
  linhas** — reforça a suspeita da pergunta aberta #2 (parte da variante
  "Revenda"/concessionária do legado, não usada por este cliente) — mas
  existir vazia não é prova definitiva de que nunca será usada, só
  evidência forte; confirmar com o usuário antes de decidir se o Painel
  novo cobre `pecas` apenas ou também `veiculos`.
- **`produtos_site`/`produtos_atualizar_site`** — integração Tray
  (`TRAY.TRAY_INTEGRACAO`) disparada dentro de `Fecha_Inventario`: ao
  fechar o balanço, agenda reatualização de estoque no site pra todo
  produto com `id_tray<>0`. Página de Produto Completo já tem integração
  Tray real (ver "Produto Completo" na memória de projeto) — esse gatilho
  seria só mais um ponto de disparo do mesmo mecanismo já existente, não
  uma integração nova.
- **`Movimentacao`** — `Fecha_Inventario` insere um registro de ajuste de
  estoque aqui (`tipo='E00'` entrada / `'S00'` saída) pra cada item cuja
  contagem diverge do sistema, e SÓ ENTÃO atualiza `pecas.qtd` direto.
  Precisa checar se este app já tem uma tabela `Movimentacao`/
  equivalente migrada (candidato óbvio: `movimentacao-produtos.tsx` /
  `movimentacao_produtos_service.py`, ver "Movimentações" acima) — se
  for a mesma tabela, o fechamento de inventário deveria gerar as MESMAS
  linhas que aquela tela já gera pra manter um único histórico de
  estoque, não uma tabela paralela.

### Regras de negócio confirmadas (direto do código, não suposição)

1. **Só pode existir 1 inventário aberto por vez** (`controle.
   situacao_balanco = 'A'`) — abrir um novo bloqueia com mensagem se já
   houver um aberto; a única forma de destravar é Fechar ou Cancelar o
   atual.
2. **Digitação só é permitida com inventário Aberto** — `FrmInvDig`
   confere `situacao_balanco='A'` antes de liberar a tela.
3. **Tipo "Geral" (`tipo_balanco='G'`) zera o estoque não digitado**:
   ao abrir, `inventario` é populado com TODO o estoque atual de
   `pecas`+`veiculos` (menos o texto de confirmação explícito ao
   usuário: "Inventários do tipo GERAL, zeram o estoque dos produtos não
   digitados no mesmo!") — ou seja, ao Fechar, qualquer item que não
   teve sua contagem alterada nesse snapshot inicial permanece com o
   valor do estoque atual (não zera de fato sozinho — o snapshot já
   nasce = estoque atual; "zerar" aqui significa que o usuário PRECISA
   digitar todo item que exista fisicamente, porque um item que sumiu do
   estoque físico mas não foi zerado manualmente vai ficar sobrando).
4. **Outro tipo de balanço não pré-carrega estoque nenhum** — o código
   só tem branches pra `Left(Combo1.Text,1) = "G"` e `="C"`; se o combo
   tiver uma 3ª opção (o screenshot mostra "Parcial" como valor padrão
   atual, que não bate com nenhuma das letras testadas no código), a
   abertura não insere NADA em `inventario` — os itens só entram por
   `FrmInvDig`'s "Inclui" um a um. Ver pergunta aberta #1.
5. **Fechamento gera ajuste de estoque automático** — para cada item cuja
   `estoque_balanco` (contado) difere de `estoque_atual + reservado`
   (sistema), grava uma `Movimentacao` de entrada ou saída E atualiza
   `pecas.qtd` diretamente — esse é o efeito real e definitivo do
   Fechamento (a auditoria/Tray são efeitos colaterais, este é o núcleo).
6. **Fechamento tipo Cíclico (`tipo_balanco='C'`) pula esse ajuste** —
   `Fecha_Inventario` vai direto pro rótulo `fecha:` sem tocar em
   `Movimentacao`/`pecas.qtd` quando `tipo_balanco='C'` — supõe-se
   que esse tipo já teria ajustado estoque em algum outro momento (ou é
   só um balanço informativo/de conferência sem efeito de estoque) — ver
   pergunta aberta #1, já que não ficou claro o que "C" representa.
7. **Cancelamento apaga tudo do balanço aberto sem tocar em estoque** —
   `DELETE FROM Inventario WHERE data = <data aberta>` + situação volta
   pra `'C'` — nenhum ajuste de `pecas.qtd`/`Movimentacao` acontece
   (diferente de Fechar).
8. **Confirmação obrigatória em Fechar/Cancelar** (`MsgBox ... vbYesNo`)
   — telas de confirmação já mostradas pelo usuário nos screenshots.
9. **Relatório de Divergência só mostra itens onde a contagem realmente
   diverge** do sistema — critério idêntico ao usado no ajuste de
   Fechamento (regra 5) — ou seja, é literalmente uma PRÉVIA do que o
   Fechamento vai lançar em `Movimentacao`/`pecas.qtd`, antes de
   confirmar. Isso sugere que o Painel novo deveria deixar essa prévia
   bem em destaque antes do botão Fechar (melhoria, ver abaixo).
10. Todo relatório tem a mesma dupla dimensão **Nível 1-5** OU
    **Área/Prateleira** OU **Descrição/Fornecedor** como eixo de
    agrupamento — nunca os 3 ao mesmo tempo — e os mesmos 3 checkboxes
    Revenda/Consumo/Imobilizado (`pecas.tipo_peca`) como filtro, quando
    aplicável.
11. **"Registro de Inventário" (item 8 do menu, `CodRelInventario=4`)
    parece estar MORTO no legado atual** — o código que de fato
    popularia esse relatório (`Vid_Rel_Inventario`, no fim de
    `FrmRelInv.frm`) está inteiramente comentado (prefixo `'''''` em
    TODA linha da sub) — a chamada ativa hoje (`Command1_Click`, Case 4)
    só faz `Call Exibe_Form(FrmRegInv, "FrmRegInv")` sem popular nada.
    **Não presumir que isso é uma regra de negócio real a portar** — é
    provavelmente um relatório abandonado/substituído por outro (talvez
    o próprio Resultado) — ver pergunta aberta #3, não implementar sem
    confirmação (mesmo princípio de "Não replicar truques VB6").

### Melhorias propostas (o que muda em relação ao VB6)

- **Um Painel único de Gestão de Inventário**, não 9 telas separadas —
  já é a intenção explícita do usuário. Sugestão de agrupamento (a
  confirmar): Abertura + Digitação + status do balanço aberto vivem numa
  tela/cabeçalho principal; os 6 relatórios (Conferência/Contagem/
  Resultado/Crítica/Divergência + o "Registro" se sobreviver à pergunta
  #3) viram abas/filtros de uma única tela de Relatórios com um seletor
  de eixo de agrupamento (Nível/Área/Descrição) em vez de 3 conjuntos de
  telas quase idênticas — elimina a triplicação real hoje existente no
  VB6 (mesma lógica de relatório copiada 3x por eixo de agrupamento).
- **Prévia de divergência sempre visível antes de Fechar** (ver regra 9) —
  o usuário vê exatamente o que vai virar `Movimentacao`/ajuste de
  estoque antes de confirmar, não só num relatório separado que precisa
  ser aberto à parte.
- **Impressão segue o padrão já estabelecido** (`print-report-header.ts`
  — cabeçalho com dados da empresa, sem mostrar filtro da tela) em vez
  do `Printer.Print` posicional por coordenada do VB6.
- **Exportar planilha via xlsx/SheetJS** (mesma biblioteca já usada no
  Borderô de Cilindros) no lugar do `CriaPlanilhaExcel` legado.
- **"Modo Didático" desde o início** (pedido explícito do usuário nesta
  mesma sessão) — o Painel de Inventário é exatamente o tipo de tela
  "complexa" que a regra em CLAUDE.md > "Padrões de UI" §4-5 exige: ícone
  único "i"/Ajuda reunindo a explicação de Abrir/Fechar/Cancelar/
  Digitar/cada relatório (efeitos não-óbvios: "Geral zera não-digitados",
  "Fechar ajusta estoque automaticamente", diferença Nível×Área×
  Descrição), tooltip em todo botão-ícone, texto de ajuda em linguagem
  de usuário final nos campos com regra de negócio.
- **Log de auditoria via `log_auditoria`** (não a tabela `Logs` legada) —
  mesmo padrão já usado em todas as outras telas migradas.

### Perguntas em aberto (bloqueantes antes de iniciar a Fase 1)

1. ~~O que exatamente é `tipo_balanco = 'C'`?~~ — **respondida
   2026-07-22, user-directed**: é o "tipo balanço **contábil**". Ainda
   assim, o texto real do combo (`.frx` binário, ilegível como texto)
   segue não confirmado — o screenshot mostra "Parcial" como valor
   padrão exibido hoje, que não bate com "Contábil"/"Geral"; possível que
   o combo mostre rótulos diferentes das letras internas (ex.: "Parcial"
   podendo ser o rótulo de exibição de `tipo_balanco='C'`, já que o
   código só reconhece "G" e "C" — sem um 3º branch, não há como o combo
   ter uma 3ª opção com efeito distinto). Tratar como 2 tipos apenas:
   Geral (zera não-digitados) e Contábil (não pré-carrega nada, só o que
   for digitado manualmente entra no fechamento).
2. ~~Este cliente usa a tabela `veiculos`?~~ — **respondida 2026-07-22,
   user-directed: SIM, entra.** Apesar de estar com 0 linhas no banco de
   teste hoje, o Painel de Inventário deve cobrir `pecas` **e**
   `veiculos` desde o início (mesmas queries UNION do legado) — não
   restringir só a `pecas`. **Novo ponto de atenção**: como não existe
   NENHUM outro módulo de veículos/concessionária migrado neste app até
   agora (Cadastro de Veículos, Venda de Veículo, etc.), o Inventário
   seria a PRIMEIRA tela a tocar essa tabela — vale confirmar com o
   usuário se um cadastro de Veículos precisa existir antes (ainda que
   básico) pra essa parte do Inventário fazer sentido, ou se a ideia é
   só ela ficar pronta pra quando/se esse módulo existir.
3. **"Registro de Inventário" deve ser portado?** Ver regra 11 — o código
   que o populava está comentado/morto no legado atual. Se não houver
   uma versão viva em outra variante de negócio, a proposta é **não
   portar** este item (fora de escopo, não regra de negócio real).
4. ~~A tabela `Movimentacao` do legado é a mesma coisa que
   `movimentacao-produtos.tsx` já grava?~~ — **respondida/confirmada ao
   vivo 2026-07-22**: SIM, é literalmente a mesma tabela `movimentacao`
   (18.773 linhas hoje) com as MESMAS colunas que
   `movimentacao_produtos_service.py` já lê/grava (`data, tipo,
   codigo_int, qtd, p_unit, num_nf, serie_nf`) — o Fechamento de
   Inventário deve reaproveitar esse service (ou pelo menos o mesmo
   padrão de insert dele) em vez de criar uma tabela de ajuste paralela.
5. ~~As tabelas `inventario`/`inventario_old`/`Inventario_Controle`/`area`
   já existem no banco real?~~ — **respondida/confirmada ao vivo
   2026-07-22** contra `GERDELL`/`BARESTELA`: todas as 4 tabelas (mais
   `veiculos`, `movimentacao`, `niveis`, `pecas`) já existem, com nomes/
   tipos de coluna batendo exatamente com o que o VB6 assume — nenhuma
   migração de schema nova é necessária pra essas tabelas. Estado atual
   de teste: `controle.situacao_balanco='F'` (nenhum balanço aberto
   agora), `tipo_balanco='G'` no último balanço; `inventario`=198 linhas,
   `inventario_old`=55, `inventario_controle`=30, `area`=2, `veiculos`=0.
6. ~~A opção "Estoque Fornecedor" em Resultado por Nível é aplicável a
   este cliente?~~ — **respondida 2026-07-22, user-directed: SIM, deve
   ser aplicada.** Ou seja, essa opção (3º rádio "Valor Usado como Preço
   Unitário" — Preço Venda / Custo Inventário / **Custo Reposição**, na
   verdade a opção real chama-se "Estoque Fornecedor" e troca a fonte da
   quantidade de `estoque_balanco+reservado_os` pra `Estoque_For` — ver
   `FrmRelInvRes.Mostra`, `vselect`/`vwhere`) entra no relatório de
   Resultado por Nível do Painel novo desde já, sem gate por
   `App.EXEName` (esse gate era só uma trava do executável legado, sem
   equivalente nesta arquitetura de menu único).

### Funções de inicialização automática — rastreadas 2026-07-22

Localizadas em `Geral\Mdl_Proc.bas` (não em `Inventario.bas`), como o
usuário indicou: `Public Sub InventarioAutomatico()` (linha ~26305) e
`Public Sub InventarioPostoAutomatico()` (linha ~26233) — chamadas a
partir da rotina de boot/abertura de dia do sistema principal (`Mdl_Proc.bas`
linhas ~6944/~7379, dentro do fluxo que já decide `Posto`/não-`Posto` e
que dispara quando o relógio do computador está à frente da
`data_movimento` de `controle`, ou seja, roda como parte do boot do dia
seguinte — o "todo dia 1º do mês" é auto-imposto pelo PRÓPRIO código,
não por um agendador externo, ver abaixo).

- **Ambas usam uma SEGUNDA conexão ADO pro MESMO banco**
  (`AbreBancoAuxADO`/`dbrevendaaux`, achei a definição em `Mdl_Proc.bas`
  linha 11596 — mesmo `Servidor`/`Banco`/credenciais de `AbreBancoADO`,
  só um `ADODB.Connection` separado). **Isso é gambiarra de concorrência
  do ADO/VB6, não arquitetura real** (mesmo princípio de "Não replicar
  truques VB6") — no backend Python cada request já abre sua própria
  conexão/cursor, então não há necessidade de simular uma "segunda
  conexão" nem um segundo par servidor/banco.
- **Idempotência por mês**: cada rotina primeiro verifica se já existe
  uma linha em `inventario_controle` pro dia 1º do mês corrente com
  `usuario_abertura=-2` (sentinela = "sistema", não um funcionário real)
  e `tipo_balanco='K'` (não-Posto) ou `'M'` (Posto) — se já existir E
  estiver com `fechamento` preenchido, sai sem fazer nada (já rodou esse
  mês). **Melhoria proposta**: trocar o sentinela mágico `-2` por uma
  coluna própria (`automatico BIT`) — mesmo princípio já usado noutras
  telas (evitar valor mágico reaproveitando uma FK que não é bem aquilo).
- **`InventarioAutomatico` (não-Posto)**: snapshot de TODO `pecas` ativo
  (`qtd+reservado+reservado_os`, sem filtrar Revenda/Consumo/Imobilizado)
  direto em `inventario_old` (NÃO em `inventario` — não abre um balanço
  "de verdade", é só arquivo histórico) — sem nenhum efeito em
  `pecas.qtd`/`movimentacao` (diferente do Fechamento manual). Exclui
  `qtd >= 1000000` (guarda de qualidade de dado, não regra de negócio) e,
  se o módulo Posto estiver ativo, exclui os `codigo_fab` hardcoded
  `'1'..'7'` (os próprios combustíveis, tratados à parte por
  `InventarioPostoAutomatico` pra não contar duas vezes).
- **`InventarioPostoAutomatico`**: snapshot do estoque de combustível
  calculado a partir de `tanque_estoque`/`tanque` (volume por tanque,
  já lido diariamente pelo módulo Posto já migrado — ver
  "Posto de Combustível" na memória de projeto) — não de `pecas.qtd`.
  Só marca o controle como fechado se TODOS os combustíveis cadastrados
  tiverem leitura (`fezcomb = qtdcomb`); senão fica em aberto e tenta de
  novo na próxima vez que rodar.
- ~~A tabela `inventario_contabil`/`DIFERENCA_ESTOQUE` (achada
  rastreando o chamador de `InventarioPostoAutomatico`) é o mesmo
  conceito de "tipo Contábil" da pergunta #1?~~ — **respondida
  2026-07-22, user-directed**: SIM, também é do tipo contábil, mas é
  **uma 3ª rotina distinta das duas acima** — disparada **diariamente**,
  no primeiro acesso ao sistema de cada dia (não mensalmente, e não
  fica dentro de `InventarioAutomatico`/`InventarioPostoAutomatico`
  apesar de estar fisicamente perto delas no `.bas`). Confirma o modelo
  de 3 mecanismos de inventário distintos e paralelos neste módulo:
  1. **Manual** (menu mostrado pelo usuário) — `inventario`/
     `inventario_old`/`inventario_controle`, tipos Geral/Contábil,
     abre→digita→fecha (com efeito real em estoque no fechamento).
  2. **Automático mensal** (`InventarioAutomatico`/
     `InventarioPostoAutomatico`) — só `inventario_old` (arquivo, zero
     efeito em estoque), tipos K/M, roda 1x por mês (auto-idempotente).
  3. **Automático diário contábil** (`inventario_contabil`/
     `inventario_contabil_os`/`DIFERENCA_ESTOQUE`) — tabelas próprias,
     roda 1x por dia. **Lido por completo 2026-07-22** — achado
     importante que muda o escopo, ver bloco abaixo.

### `inventario_contabil` — lido por completo, escopo final confirmado 2026-07-22

A rotina diária vive dentro de `Mdl_Proc.bas::MudaDataSistema` (não um
sub próprio) — o "boot do dia" chamado sempre que o sistema detecta que
`Date` (relógio) passou de `controle.Data_Movimento`. No código-fonte
lido, essa sub tinha DOIS ramos (`If Not RegControle.Posto Or Not
NFCe_Ws Then <reconciliação hardcoded por CNPJ> Else <inventario_contabil>
End If`) — **o usuário confirmou explicitamente a lógica de negócio real
pretendida, que substitui a leitura literal do código** (o código lido
tem uma condição de gate — Posto+NFC-e — que não reflete a intenção
correta, provavelmente resquício de patch/variante específica):

- **Reconciliação de estoque hardcoded por CNPJ**
  (zera `pecas.qtd/reservado/reservado_os` e reconstrói a partir de
  `movimentacao`/Orçamento/OS/Pedido de Venda, gravando antes/depois em
  `DIFERENCA_ESTOQUE`) — **descartada, fora de escopo, não portar.**
  Confirmado pelo usuário: "pode ser desconsiderada".
- **Lógica final do sistema (regra de negócio confirmada, autoritativa
  sobre a leitura do código)**:
  - **Módulo Posto ativo** → só `InventarioPostoAutomatico`
    (snapshot de combustível via `tanque_estoque`), disparado no
    **primeiro acesso ao sistema em cada MÊS**. Sem o snapshot diário
    contábil pra esse segmento.
  - **Demais segmentos (não-Posto)** → **dois** disparos:
    `InventarioAutomatico` (snapshot de `pecas`) no primeiro acesso ao
    sistema em cada **MÊS**, **e também** o snapshot `inventario_contabil`
    no primeiro acesso ao sistema em cada **DIA**.
  - Não existe combinação "Posto + contábil diário" nem "não-Posto +
    sem contábil diário" — é uma escolha binária por módulo Posto
    ativo/inativo, não pelo NFC-e como o código sugeria.
- ~~Como disparar essas rotinas automáticas nesta arquitetura nova
  (sem processo "sempre ligado")?~~ — **respondida 2026-07-22,
  user-directed: opção (a)** — um endpoint que o próprio frontend chama
  no primeiro acesso/login do dia. **Padrão de implementação proposto**
  (a confirmar quando formos pra execução): reaproveitar o mesmo
  princípio já usado por `data_movimento`/`posto_common.py` (leitura
  fresca por request, nunca cache global de processo) — o endpoint
  checa se a rotina de HOJE (diária) e a de dia-1-do-mês-corrente
  (mensal, se aplicável) já rodaram (via `inventario_controle`/data em
  `inventario_contabil`) e, se não, executa sincronamente dentro da
  própria requisição antes de responder. Não precisa de Tarefa Agendada
  do Windows nem de worker/cron separado — é sempre o primeiro request
  do dia de QUALQUER usuário que dispara, não um horário fixo.

**Levantamento do ecossistema considerado COMPLETO em 2026-07-22** — todas
as perguntas bloqueantes foram respondidas pelo usuário. Único ponto
ainda formalmente aberto, não-bloqueante: item 3 ("Registro de
Inventário" não portar, código morto no legado — proposta já feita,
aguardando só confirmação de leitura, não impede começar). Colunas/
tabelas todas confirmadas ao vivo contra `GERDELL`/`BARESTELA`. Próximo
passo: partir pra execução (backend + frontend do Painel de Gestão de
Inventário) — aguardando o usuário dar o sinal pra começar e definir por
onde (sugestão: Fase 1 = Abertura/Digitação/Fechar/Cancelar, o núcleo
manual; Fase 2 = os relatórios consolidados; Fase 3 = os 2 disparos
automáticos mensais/diário).

---

## O.S. Completa

**Status: 🟢 Fase 1 (núcleo, módulo Assistência Técnica) implementada
2026-07-30/31, UI confirmada ao vivo pelo usuário em 2026-08-01** (o clique
numa O.S. da lista abre a tela corretamente — a suspeita de cache do Metro
desatualizado, registrada abaixo, estava certa). Migração de
`FrmTraOsNew.frm` (~7000 linhas VB6) + `FrmManRet2.frm`
(Envio para Terceiros, ainda fora de escopo). Pedido original do usuário:
"implantar a Ordem de Serviço... utilize a conexão KONTACTO TESTE para essa
etapa" — Fase 1 = só o núcleo (cabeçalho completo + itens + fechar/faturar/
reabrir/cancelar + forma de pagamento + anexos + impressão/recibo),
confirmado via `AskUserQuestion`. Oficina fica pra uma 2ª etapa (mesmo
código, módulo diferente) — não iniciada.

### O que foi implementado

**Backend** (100% novo, nada duplicado — reaproveita `os_service.py`/
`os_itens_service.py` diretamente):
- `backend/services/os_completo_service.py` — cabeçalho (`get_os_completo`/
  `save_os_completo`, enriquece `os_service._get_os_sync` com os campos
  extras via JOIN em `funcionarios`/`tipo_os`/`status_os` — as 2 últimas são
  tabelas de lookup reais, confirmadas ao vivo em KONTACTO-TESTE) +
  wrappers finos `fechar_os_completo`/`faturar_os_completo`/
  `reabrir_os_completo`/`cancelar_os_completo`, cada um só chamando a
  função correspondente de `os_service.py` com `tela="OS_COMP"`.
- `backend/services/os_service.py` — `_fechar_os_sync`/`_faturar_os_sync`
  ganharam parâmetro `tela: str = "OS"` (default preserva 100% o
  comportamento da O.S. Mobile); **novas** `_reabrir_os_sync`/
  `_cancelar_os_sync` (sem precedente em nenhuma versão da O.S. até então —
  a Mobile nunca teve Reabrir/Cancelar). Reabrir só F→A, sem mexer em
  estoque (o Fechar de O.S. não movimenta estoque, só o Faturar libera a
  reserva). Cancelar A/F→C, sempre estorna a reserva dos itens não-
  cancelados (`_mover_estoque` delta negativo) — diferente do Pedido, a
  reserva da O.S. acontece na INCLUSÃO do item, não no Fechar, então
  Aberta ou Fechada sempre há reserva pra estornar. Cancelar reaproveita a
  permissão SITUACAO (não uma CANCELAR própria), mesma decisão já tomada
  pro Pedido Completo.
- `backend/routes/os_completo.py` (registrado em `server.py`) — cabeçalho +
  situação com log de auditoria `tela="OS_COMP"`; itens/descontos/desconto-
  geral/análise em rotas PARALELAS `/api/os-completo/{codigo}/...`
  (reaproveitando `os_itens_service.py` direto, só pra log de auditoria
  correto) — mesmo padrão exato de `routes/pedido_completo.py`. **Forma de
  Pagamento NÃO tem rota própria** — a tela chama
  `/api/os/{codigo}/formas-pagamento` compartilhada, mesmo precedente do
  Pedido Completo.
- `backend/models/schemas.py` — `OSCompletoSaveRequest` (estende
  `OSSaveRequest` com `referencia_os`/`tecnico_responsavel`/`posicao_os`/
  `previsao_termino`/`data_termino`/`hora_entrada`/`hora_fechamento`).
- **Achado durante a implementação, corrigido de passagem**:
  "Situação/Destino do item" (`Destino(2)` do legado — 0=Cliente paga,
  1=Garantia, 2=Interno, 3=Contrato) **nunca tinha sido implementado em
  lugar nenhum** — `OSItemSaveRequest` não tinha o campo, o INSERT gravava
  `situacao=0` como literal fixo na query, e o SELECT de listagem nem
  trazia a coluna. Corrigido em `OSItemSaveRequest`/`_add_item_sync`/
  `_update_item_sync`/`_list_itens_sync` (novo campo `situacao: int = 0`,
  testes em `test_os_itens_service.py`) — a O.S. Completa é a primeira tela
  a expor esse combobox.
- `backend/services/lookups_service.py`/`routes/lookups.py` —
  `GET /api/status-os`/`GET /api/tipo-os` novos (tabelas `status_os`/
  `tipo_os`, confirmadas ao vivo, mesmo padrão genérico
  `_list_codigo_descricao_sync` já usado por dezenas de outras tabelas
  auxiliares). A O.S. Mobile continua com a lista `STATUS_OS` hardcoded
  local (`os-form.tsx`) — troca pro lookup real não pedida pra ela ainda.
- `backend/services/os_service.py::_list_os_sync` — ganhou
  `atendente_nome` no SELECT (join `funcionarios`, `COALESCE(nome_guerra,
  nome)`) pra a nova lista da O.S. Completa poder exibir o atendente —
  não existia antes (a O.S. Mobile lista não usa esse campo).
- `backend/services/permissoes_service.py` — `ACOES_OS_COMP` (ABRIR/
  GRAVAR/WHATSAPP/ADD_ITEM/EDIT_ITEM/DEL_ITEM/DESC_ITEM/DESC_GERAL/
  VER_DESCONTOS/ANALISE/SITUACAO/FORMA_PAG/FATURAR/REABRIR/ANEXOS/
  IMPRIMIR — sem CANCELAR própria, sem DIVIDIR/ENTREGUE/TX_SERVICO/
  IMPRIMIR_ITEM/AGENDAR, que são exclusivos do Pedido). O gating por módulo
  (`OS`/`OS_COMP` desabilitadas quando Oficina E Assistência estão
  desligados) e o par de exclusividade Mobile×Completa em
  `permissoes.tsx`'s `EXCLUSIVE_PAIRS` **já existiam** de uma rodada
  anterior (achado ao investigar, não precisou de mudança).

**Frontend** (novo):
- `frontend/app/os-geral.tsx` — tela principal, web-only, mesmo esqueleto
  de `pedido-geral.tsx` (`PedidoHeader`/`ClienteSection`/`ItemList`/
  `FormaPagamentoField`/`AjudaPedidoModal`/`ScreenToast`). Cabeçalho fixo:
  Forma de Pagamento, Referência, Técnico Responsável, Tipo O.S. Modal
  "Dados Principais": Status O.S. (lookup), Atendente, Área de Atuação,
  Cliente Descreva, Serviço Executado, Observação. Bloco "Equipamento":
  busca real via `EquipamentoSearchModal` (novo), escopada por
  `cliente` (equipamento pertence ao cliente, não existe busca global —
  `GET /api/equipamentos?cliente=X&busca=termo`, endpoint já existente).
  Reabrir/Cancelar disponíveis pela primeira vez em qualquer versão da O.S.
- `frontend/app/os-lista.tsx` — lista dedicada (clone de
  `pedido-lista.tsx`), sem filtro de Vendedor (O.S. não tem vendedor no
  cabeçalho, só Atendente — vendedor é por item). `app/os.tsx` (Mobile)
  voltou a ser exclusiva de `OS.ABRIR` (removido o fallback
  `OS_COMP.ABRIR` que antes deixava a lista abrir mas o toque num item ser
  no-op) — mesma correção já feita pro Pedido em 2026-07-20.
  `transacoes.tsx`/`ModuleTiles.tsx` atualizados pra rotear
  dinamicamente por permissão (mesmo padrão do Pedido).
- **Correção de arquitetura em relação ao plano original**: o plano
  aprovado assumia que dava pra reaproveitar `pedido/ItemList.tsx`/
  `AddItemModal.tsx`/`EditItemModal.tsx`/`usePedidoItens.ts` "estendendo
  com Executor+Situação". Na prática, `usePedidoItens.ts` (911 linhas) e os
  2 modais de item carregam MUITO conceito exclusivo do Pedido (kit, m²,
  número de série, desdobramento Clínica, taxa de serviço, pedido
  totalizado) que não existe nem faz sentido pra O.S. — forçar a O.S. por
  esse caminho significaria threading `tela==="OS_COMP"` por todo esse
  código morto-pra-O.S., mais arriscado que reaproveitar. Decisão tomada
  durante a implementação (dentro do espírito do plano — "reaproveitar sem
  duplicar regra de negócio" — só a tática mudou):
  - `frontend/src/components/os/useOSItens.ts` — hook DEDICADO e bem menor
    (sem kit/m²/num_serie/clínica/taxa/pedido-totalizado), superfície
    pública compatível com o que `ItemList.tsx` realmente usa.
  - `frontend/src/components/pedido/ItemList.tsx` — generalizado
    (aditivamente, sem quebrar Pedido) pra aceitar `tela === "OS_COMP"` nos
    gates de Fechar/Faturar/Reabrir/Cancelar/Imprimir (`hasSituacaoActions`/
    `isTelaCompleta`), com rótulos "Pedido"/"O.S." dinâmicos. Dividir/
    Imprimir Item/Agendar/Tx Serviço/Pedido Totalizado continuam Pedido-only.
    Prop `it` teve o tipo estreitado de `UsePedidoItens` (tipo derivado
    gigante, só do Pedido) pra uma interface `ItemListItens` mínima —
    `usePedidoItens` já satisfaz automaticamente (é superset),
    `useOSItens` só implementa o necessário (com no-ops só pra satisfazer o
    TypeScript nos campos que nunca são de fato chamados pra O.S.).
    `GeneralDiscountModal.tsx`/`DiscountsReportModal.tsx` receberam o mesmo
    tratamento (tipos estreitados), já que também são compartilhados.
  - `frontend/src/components/os/OSItemModal.tsx` — modal ÚNICO de
    Adicionar/Editar item (mesmo fluxo de busca→confirmar já usado e
    testado na O.S. Mobile, `os-form.tsx`, só extraído + Situação/Destino
    novo), em vez dos 2 modais separados do Pedido.
  - `frontend/src/components/os/types.ts` — `OSItemRow` (`ItemRow &
    {cod_os_prod, vendedor, executor, situacao}`), `OSData`.
  - `frontend/src/components/os/OSTotaisResumo.tsx` — totais por Situação
    (Serviços+Produtos vs. Garantia/Interno/Contrato vs. combinado),
    puramente derivado dos itens já carregados, sem chamada à API.
  - `frontend/src/components/os/AnexosOSModal.tsx` — mesmo padrão de
    `AnexosPedidoModal.tsx` (grava como anexo do CLIENTE, `cod_grupo=1`),
    sub-grupo "Ordens de Serviço" `cod_sub_grupo=4` (já confirmado ao vivo
    em "Gestor de Documentos (Anexos)" acima, nunca integrado até agora).
  - `frontend/src/components/os/ReciboOSModal.tsx` — preview + impressão
    via iframe oculto (nunca o truque de CSS hide, ver "Impressão via
    iframe" acima), mais simples que o do Pedido (sem Totalizado/qtd.
    pessoas/localização/agendamento), com o detalhamento por Situação que
    o Pedido não tem.
  - `frontend/src/components/EquipamentoSearchModal.tsx` — clone do padrão
    `FornecedorSearchModal.tsx`, mas escopado por `cliente` (diferente de
    Fornecedor, que é busca global) — reflexo de `GET /api/equipamentos`
    exigir `cliente` como parâmetro obrigatório (é "Cadastro de
    Equipamentos DO CLIENTE", não uma tabela solta).

### Confirmado durante a implementação (rastreio campo-a-campo)

- Nº da O.S. é `MAX(codigo)+1`, não IDENTITY (já valia pra O.S. Mobile).
- Vendedor e Executor são por ITEM (`os_produto.vendedor`/`.executor`) —
  a O.S. Mobile (`os-form.tsx`) já tinha os 2 campos no modal de item desde
  antes desta Fase 1 (achado ao investigar — a Completa só herdou).
- Faturar sempre exige a O.S. já Fechada (`_faturar_os_sync` nunca teve o
  atalho "fecha-e-fatura junto" do Pedido Bar) — igual ao Pedido Geral,
  diferente do Pedido Bar.
- Reabrir só habilita em O.S. Fechada — o branch do legado que trataria
  reabertura de Cancelada é código morto (nunca alcançável na prática),
  não replicado (ver "Não replicar truques VB6" no CLAUDE.md).

### Fora do escopo desta Fase 1 (registrado, não bloqueante)

- ~~**Oficina (2ª etapa)**~~ — **implementado 2026-08-02**, ver seção
  própria "Oficina — Fase 2 (O.S. Completa)" logo abaixo.
- ~~**Envio para Terceiros** (`FrmManRet2.frm`, tabela `retifica`)~~ —
  **implementado 2026-08-01**, ver seção própria "Envio para Terceiros"
  logo abaixo.
- ~~**Pontuação de Técnicos** (`os_produto.Pontuacao_A/E/V`)~~ —
  **implementado 2026-08-01**, ver seção própria "Pontuação de Técnicos"
  logo abaixo.
- ~~**Tempo Gasto por Serviço** (`os_tempo`)~~ — **implementado
  2026-08-01**, ver seção própria "Tempo Gasto por Serviço" logo abaixo.
- ~~**Autorização/Expedição de Itens** (module flags
  `exige_aprovacao_itens_os`/`exige_expedicao_itens_os`)~~ —
  **implementado 2026-08-01**, ver seção própria "Autorização/Expedição de
  Itens" logo abaixo.
- ~~**Requisições vinculadas** (aba read-only da grade do legado)~~ —
  **implementado 2026-08-01**, ver seção própria "Requisições Vinculadas
  (O.S. Completa)" logo abaixo.
- ~~**Agendar item de Serviço** — o Pedido Geral já tem essa feature (módulo
  Clínica/Assistência); não trazida pra O.S. Completa nesta rodada, avaliar
  reaproveitar quando fizer sentido (não bloqueante).~~ — **implementado
  2026-08-01**, ver seção própria "Agendar item de Serviço (O.S. Completa)"
  logo abaixo.
- ~~**Doc. Origem/Revisão programada** (validação cruzada de OS/Pedido de
  origem pra Garantia/Revisão)~~ — **implementado 2026-08-02**, ver seção
  própria "Doc. Origem / Revisão Programada (O.S. Completa)" logo abaixo.
- ~~**Criar Cópia** da O.S.~~ — **implementado 2026-08-02**, ver seção
  própria "Criar Cópia (O.S. Completa)" logo abaixo.
- ~~**Alteração de Executor pós-fechamento**.~~ — **implementado
  2026-08-02**, ver seção própria "Alteração de Executor pós-fechamento
  (O.S. Completa)" logo abaixo.
- ~~**Bifurcação de faturamento Garantia×Cliente**~~ — **implementado
  2026-08-02**, ver seção própria "Bifurcação de faturamento
  Garantia×Cliente (O.S. Completa)" logo abaixo.
- ~~**Cadastro de equipamento inline** — o `EquipamentoSearchModal` oferece
  "Cadastrar novo equipamento" navegando pra `/equipamentos` (tela
  cheia), não um cadastro rápido embutido no modal.~~ — **implementado
  2026-08-02**, ver seção própria "Cadastro de Equipamento Inline (O.S.
  Completa)" logo abaixo.

### Teste ao vivo — API e UI confirmadas (2026-08-01)

**Atualização 2026-08-01**: o backend foi exercitado de ponta a ponta via
chamadas diretas à API contra KONTACTO TESTE (sem navegador — sem
ferramenta de automação disponível neste ambiente): criar O.S., buscar
cabeçalho (com enriquecimento de técnico/status/tipo), incluir item com
vendedor+executor+situação (Garantia), listar itens, definir forma de
pagamento, Fechar, Faturar (gerou Comanda), Reabrir (em O.S. separada),
Cancelar com estorno de estoque conferido antes/depois (em O.S. separada),
Descontos Concedidos, Análise de Margem, Desconto Geral, lookups `/api/
status-os`/`/api/tipo-os`, busca de equipamento por cliente, listagem de
O.S. — **tudo funcionou** depois de corrigir 1 bug real encontrado (INSERT
do cabeçalho com 1 parâmetro faltando). Dados de teste (O.S. #20498/20499/
20500) ficaram na base como Faturada/Cancelada — não há exclusão física de
O.S., mesma regra do sistema.

**UI confirmada (2026-08-01)**: o clique numa O.S. da lista abre a tela —
a causa suspeita (cache do Metro desatualizado, não recompilando os
arquivos novos da O.S. Completa) estava correta; `.metro-cache` limpo +
dev server reiniciado do zero resolveu. Anexar documento e imprimir recibo
seguem sem confirmação visual explícita (não bloqueante, mesmo componente
já validado em Pedido Bar/Geral).

**Achado adicional, corrigido junto**: `os.valor` fica desatualizado (0)
em muitos registros de O.S. Faturadas legadas (583 registros afetados em
KONTACTO TESTE — prováveis registros gravados pelo sistema VB6 legado, que
roda em paralelo). Corrigido `_list_os_sync`/`_get_os_sync` pra somar o
total direto de `os_produto` na EXIBIÇÃO (não mexe na gravação/Faturar —
ver nota abaixo).

**Risco corrigido em 2026-08-01** (era "identificado, não resolvido" até
então): `_fechar_os_sync`/`_faturar_os_sync` (`os_service.py`) liam
`os.valor` cru da tabela pra decidir o subtotal gravado em
`comanda.valor_venda` — se essa coluna estivesse desatualizada (os 2
casos identificados acima, ou qualquer O.S. gravada fora do fluxo normal
de inclusão de item deste backend), o valor faturado saía errado. Os dois
agora chamam `_recalc_os_total` (já existente em `os_itens_service.py`,
reaproveitado — não duplicado) ANTES de ler o subtotal, recalculando
`os.valor = SUM(os_produto)` na hora, tanto pro Fechar (decide a Forma de
Pagamento) quanto pro Faturar (valor gravado na Comanda). Cobertura nova
em `test_os_service.py`
(`test_fatura_recalcula_valor_ignorando_os_valor_desatualizado`) — simula
`os.valor=0`/soma real 200 e confirma que a Comanda recebe 200, não 0.
Suíte completa de testes de O.S. (151 testes) sem regressão.

---

## Envio para Terceiros

**Status: 🟢 Implementado e testado ao vivo, 2026-08-01.** Migração de
`FrmManRet.frm` ("Envio de Equipamentos para Terceiros") — rastreado no
código-fonte real em `C:\Desenv\VB6\SQLSERVER\Kontacto\frmmanret.frm`
(2381 linhas). Tela própria, standalone, web-only, sem abas (o legado
também não tem — mesma exceção "compact single-view screens" já usada em
Fornecedores/Cilindros).

### Regras de negócio confirmadas no rastreio

- Registra o envio de um equipamento do cliente para um FORNECEDOR externo
  ("Terceiro" — confirmado no JOIN `val(retifica.fornecedor) =
  fornecedor.codigo_int` usado em toda consulta do form original, não é
  texto livre) fazer conserto/manutenção, vinculado a uma O.S.
- **Nomes de coluna enganosos, mantidos por serem os nomes reais da tabela
  compartilhada com o legado**: `retifica.entrada` = data em que o
  equipamento foi ENVIADO ao terceiro (gravada ao "Envio p/ Terceiro");
  `retifica.saida` = data em que RETORNOU do terceiro (gravada ao
  "Retorno/Terceiro") — o oposto do que os nomes sugeririam isoladamente.
  Exibido na tela como "Data de Envio"/"Data de Retorno" pra não confundir
  o usuário, mas a coluna do banco continua `entrada`/`saida`.
- `cliente`/`fornecedor` são gravados como TEXTO (nvarchar) na tabela
  mesmo representando códigos numéricos — mesma tabela do legado, sem
  migração de schema (mesmo raciocínio já usado noutras reaproveitamentos
  de coluna deste projeto).
- Exclusão é HARD DELETE de verdade (`DELETE FROM retifica`) — confirmado
  no código-fonte, diferente de Pedido/O.S. (que só mudam situação); única
  entidade deste sistema com exclusão física real até agora.
- **Não replicado** (bug do código legado, não regra de negócio): o check
  de duplicidade antes de Inserir (`Procura(3, Protocolos, "")`) compara
  por `num` — sempre vazio num registro novo — em vez de por `os`/
  `numero_de_serie` como o texto do `MsgBox` ("já existe um envio para
  esta O.S.") sugere. Nunca dispara na prática no legado; não replicado
  (ver "Não replicar truques VB6" no CLAUDE.md).

### O que foi implementado

- **Backend**: `backend/services/retifica_service.py` (list/save/update/
  retorno/delete) + `backend/routes/retifica.py` (`GET/POST /api/
  retifica`, `PUT /api/retifica/{num}`, `POST /api/retifica/{num}/retorno`,
  `DELETE /api/retifica/{num}`, registrado em `server.py`) +
  `RetificaSaveRequest`/`RetificaRetornoRequest` em `schemas.py`. Permissão
  própria `RETIFICA` (ABRIR/GRAVAR/RETORNO/EXCLUIR) no menu Transações,
  gateada pelo mesmo módulo de OS/OS_COMP (Oficina OU Assistência).
  12 testes unitários em `test_retifica_service.py`.
- **Frontend**: `frontend/app/envio-terceiros.tsx` — lista (busca + filtro
  "somente em aberto") + modal de Envio/Alterar (Cliente e Terceiro via
  busca real — `ClientSearchModal`/`FornecedorSearchModal`, mesma regra
  `[GLOBAL]` de campos de identidade; Marca/Modelo via combobox de tabela
  auxiliar) + modal de Retorno (data + valor). Card novo em `transacoes.tsx`
  ("Envio para Terceiros"), gated por `RETIFICA.ABRIR`.
- **Bug real encontrado e corrigido durante o teste ao vivo**: `numero_de_
  serie` (nvarchar(20)) não era truncado antes de gravar — um valor mais
  longo que 20 caracteres quebrava com erro cru do SQL Server ("String or
  binary data would be truncated"). Corrigido com o padrão já usado no
  projeto (`_get_col_sizes`/`_trunc`), aplicado também em `cliente`/
  `fornecedor` (nvarchar(14)).
- **Testado ao vivo contra KONTACTO TESTE**: criar envio (O.S. #20499),
  listar (com filtro "somente abertos" e por busca), registrar retorno
  (grava `saida`+`valor`), alterar (incluindo o caso de truncamento acima,
  antes e depois da correção), excluir — protocolo de teste removido ao
  final (esta tabela tem exclusão física real, então a limpeza foi
  completa, diferente de O.S./Pedido).

### Fora do escopo desta rodada

- **Relatório/impressão formatada** (`Command5_Click`, subs `Imprime`/
  `Envio_Retifica2`/`Retorno_Retifica`) — não rastreado nem implementado;
  a lista em tela (com busca/filtro) cobre a consulta, mesma decisão já
  tomada pro Borderô de Cilindros (on-screen em vez do formato de
  impressão térmica do legado). Sem pedido explícito do usuário pra
  reconsiderar ainda.
- **Colunas `marinheiro` (nvarchar(40)) e `tipo_envio` (nvarchar(1))** —
  existem na tabela real (confirmado ao vivo) mas NÃO aparecem em
  `frmmanret.frm`; não modeladas aqui por falta de rastreio de uma regra
  de negócio real pra elas (podem pertencer a uma tela/variante diferente,
  não localizada). Revisitar se o usuário confirmar o propósito.
- **F2 - Busca de O.S.** do legado (`PrepProcuraOS`, join usando
  `os.CHASSI = equipamentos.numero_de_serie`) não replicado — campo O.S.
  é só um número digitado + validação no Gravar (mesmo padrão simples já
  usado em outras telas deste projeto que referenciam O.S./Pedido por
  número).
- **Auto-preenchimento de Cliente a partir da O.S.** — não implementado;
  o legado também não faz isso (Cliente é campo independente com sua
  própria busca). Poderia ser uma melhoria de UX futura, não pedida.

---

## Pontuação de Técnicos

**Status: 🟢 Implementado e testado ao vivo, 2026-08-01.** Migração do
frame "Pontuação" (`Command4_Click`) — rastreado no código-fonte real em
`C:\Desenv\VB6\SQLSERVER\Kontacto\frmtraosa.frm` (18909 linhas — a
variante mais completa das encontradas: `frmtraos.frm`/`frmtraosnova.frm`/
`frmtraos18052012.frm` também têm o form de O.S., mas `frmtraosa.frm` é a
única com o frame de Pontuação rastreado).

### Regras de negócio confirmadas no rastreio

- Nota de 0 a 999 (máscara "999" de 3 dígitos do legado) por ITEM da O.S.
  (`os_produto.Pontuacao_A/E/V`, colunas já existentes no schema),
  avaliando 3 papéis: **Executor** (rotulado "Técnico" na tela — quem
  executou o serviço, `os_produto.executor`), **Vendedor**
  (`os_produto.vendedor`) e **Atendente** (o atendente da O.S. inteira,
  `os.atendente` — mesmo valor repetido em toda linha, confirmado no
  código-fonte: a grade resolve o nome do Atendente uma vez a partir do
  combobox do cabeçalho, não por item).
- Gravação é direta por item (`UPDATE os_produto SET Pontuacao_A=...,
  Pontuacao_E=..., Pontuacao_V=... WHERE Cod_Os_Prod=...`), sem exigir a
  O.S. estar Aberta — é uma avaliação de desempenho, não uma alteração do
  pedido em si (confirmado: o botão que abre o frame não checa situação
  da O.S., só se ela existe).

### O que foi implementado

- **Backend**: `os_itens_service._list_itens_sync` passou a trazer
  `pontuacao_a`/`pontuacao_e`/`pontuacao_v` (reaproveita o endpoint de
  itens já existente, sem view nova — decisão deliberada: o legado inclui
  itens cancelados na grade de Pontuação, aqui não, já que pontuar um item
  cancelado não tem valor real); nova `save_pontuacao`/`_save_pontuacao_sync`
  (valida 0-999, item pertence à O.S.) + `PontuacaoSaveRequest` em
  `schemas.py` + rota `PUT /api/os-completo/{codigo}/itens/{cod_os_prod}/
  pontuacao` em `os_completo.py` (log de auditoria `tela="OS_COMP"`,
  `comando="PONTUACAO"`). Permissão própria `OS_COMP.PONTUACAO`. 6 testes
  unitários novos em `test_os_itens_service.py`.
- **Frontend**: `OSItemRow`/`useOSItens.ts` estendidos com os 3 campos +
  `savePontuacao`; `PontuacaoModal.tsx` novo (lista os itens da O.S. já
  carregados, 3 campos numéricos + botão Gravar por linha — mesmo padrão
  do grid+mask do legado, sem view/endpoint de listagem próprio). Botão
  "Pontuação de Técnicos" em `os-geral.tsx`, ao lado dos totais por
  Situação, gated por `OS_COMP.PONTUACAO`.
- **Testado ao vivo contra KONTACTO TESTE**: incluir item, gravar
  pontuação (Executor=90/Vendedor=80/Atendente=70), conferir persistência
  via novo GET, validação de faixa (rejeitou 1500) — tudo funcionou de
  primeira, sem bug encontrado nesta rodada. O.S. de teste (#20501)
  cancelada ao final (sem exclusão física de O.S., mesma regra já
  documentada).

### Fora do escopo desta rodada

- Não modelado: itens CANCELADOS não aparecem na lista de Pontuação aqui
  (aparecem no legado) — decisão deliberada, ver acima.
- Não implementado: nenhum relatório consolidado de pontuação por técnico/
  vendedor/atendente (ex.: "ranking" ou médias) — só o registro por item,
  igual ao escopo mínimo do frame original.

---

## Autorização/Expedição de Itens

**Status: 🟢 Implementado e testado ao vivo, 2026-08-01.** Migração da aba
"Autorização de Itens" — rastreada no código-fonte real em
`C:\Desenv\VB6\SQLSERVER\Revenda\FrmTraOsNew.frm` (20241 linhas — a variante
canônica pra esta feature: a cópia de `Kontacto\` tem os controles de UI
presentes mas `Visible=0` e **sem nenhum `Click` handler ligado**, forte
indício de que a feature foi só escafoldada e nunca ativada nessa linha de
negócio; `Revenda\` é a única cópia com a lógica de fato implementada).

### Regras de negócio confirmadas no rastreio (e com o usuário, via `AskUserQuestion`)

- **Reserva de estoque é condicional, não uma escolha binária entre "sempre
  na inclusão" e "sempre na autorização"** — confirmado diretamente pelo
  usuário depois de eu ter oferecido só essas duas opções: *"O normal é o
  sistema reservar o estoque quando lança o produto na o.s., mas quando no
  controle está habilitado pra exigir aprovação prévia, o estoque só baixa
  após ser autorizado"*. Ou seja: comportamento padrão inalterado (reserva
  na inclusão do item) **exceto** quando
  `controle_aux.exige_aprovacao_itens_os` = 1 (checkbox "Exige Autorização
  de itens O.S." em Controle do Sistema > Gerencial/Controle), caso em que
  a reserva só acontece no momento da Autorização.
- **Autorizar** é o passo que de fato move estoque (`pecas.qtd -=
  quant; reservado_os += quant`) — grava `usuario_autorizacao`/
  `data_autorizacao`/`hora_autorizacao`/`qtd_autorizada=quant` no item, cria
  1 registro em `os_autorizacao` por LOTE (a tela sempre autoriza vários
  itens marcados de uma vez) + 1 linha em `os_autorizacao_itens` por item
  (trilha de auditoria). Só permite item ainda não autorizado.
- **Quando `exige_expedicao_itens_os` também está ligada, a ordem é
  Expedição ANTES de Autorização** — confirmado no código-fonte
  (`CmdExpedicao_Click`'s validação): um item só pode ser Autorizado depois
  de já ter sido Expedido. Ordem inicialmente pareceu contraditória numa
  primeira leitura do `.frm` (reli com calma até confirmar) — Expedição é o
  registro de picking/separação física, Autorização é quem de fato libera o
  estoque contabilmente.
- **Expedição (Autorização de Expedição) NUNCA movimenta estoque** —
  confirmado no código-fonte: a linha de movimentação de estoque desse
  botão está desativada/comentada no legado. Só grava
  `usuario_expedicao`/`data_expedicao`/`hora_expedicao`. Só permite item
  ainda não autorizado e ainda não expedido.
- **Remover Autorização** desfaz tudo (limpa os 4 campos de autorização +
  `qtd_autorizada=0`, apaga a linha de `os_autorizacao_itens`, estorna o
  estoque). **Remover Autorização de Expedição** só limpa os 3 campos de
  expedição (+ reset de `qtd_autorizada=0`, no-op idêntico ao legado) — só
  permitido em item já expedido e AINDA NÃO autorizado (uma vez autorizado,
  a expedição não pode ser desfeita isoladamente; tem que remover a
  autorização primeiro).
- **Permissão por Área de Estoque**: um funcionário só pode Autorizar/
  Expedir itens cuja `pecas.area` bata com alguma área atribuída a ele em
  `funcionarios_area`. Essa tabela **já existe e já é totalmente
  gerenciável** — é o campo "Área de Estoque" já existente no cadastro de
  Funcionários (`funcionario-completo.tsx`/`funcionarios_service.py`,
  campo `areas_estoque`), confirmado diretamente pelo usuário: *"tabela
  funcionarios_area existe sim, é o campo 'area de estoque' no cadastro de
  funcionarios"* — nenhuma UI nova precisou ser criada pra gerenciar essa
  tabela, só CONSULTÁ-la ao autorizar/expedir. Usuários "sentinela" de
  sistema (`usuario_alteracao <= 0`, ex. master `-2`) bypassa essa checagem
  — mesmo espírito de "Master tem acesso total" já usado no resto do
  projeto, aqui é uma restrição de escopo de dados por funcionário comum,
  não uma permissão de tela.
- **Não replicado** (arquitetura estranha ao modelo desta migração, não uma
  regra de negócio): a segunda conexão `dbrevendaDEV` que o legado abre em
  paralelo — este backend é single-connection-per-empresa, sem equivalente.
  Também não replicado: `ImprimeExpedicao`/`CmdImpExpedicao` (impressão
  formatada) — mesma decisão já tomada noutras telas deste projeto
  (consulta em tela cobre o caso de uso, sem o formato de impressora
  térmica do legado).

### O que foi implementado

- **Backend**: dois helpers novos em `pedido_common.py`
  (`_exige_aprovacao_itens_os_ativo`/`_exige_expedicao_itens_os_ativo`, lêem
  `controle_aux.exige_aprovacao_itens_os`/`.exige_expedicao_itens_os`).
  `os_itens_service.py` ganhou: (1) reserva de estoque CONDICIONAL em
  `_add_item_sync`/`_update_item_sync`/`_delete_item_sync` (só reserva/
  ajusta/estorna quando a flag está desligada OU o item já foi autorizado
  antes — evita mexer em estoque que nunca foi de fato reservado); (2) 4
  funções novas — `_autorizar_itens_sync`/`_remover_autorizacao_sync`/
  `_expedir_itens_sync`/`_remover_expedicao_sync` — todas em LOTE (recebem
  uma lista de `cod_os_prod`, processam item a item, retornando quais foram
  processados e quais bloqueados, sem abortar o lote inteiro no primeiro
  bloqueio); (3) `_list_itens_sync` estendida com os 8 campos de
  autorização/expedição (`usuario_autorizacao`/`data_autorizacao`/
  `hora_autorizacao`/`qtd_autorizada`/`usuario_expedicao`/`data_expedicao`/
  `hora_expedicao` + nomes resolvidos). `AutorizacaoItensRequest` novo em
  `schemas.py`. 4 rotas novas em `os_completo.py`
  (`POST /api/os-completo/{codigo}/itens/autorizar`, `/remover-autorizacao`,
  `/expedir`, `/remover-expedicao`, log de auditoria `tela="OS_COMP"`,
  `comando="AUTORIZAR"`/`"EXPEDIR"`), mais as 2 flags expostas no cabeçalho
  (`os_completo_service.get_os_completo` → `exige_aprovacao_itens_os`/
  `exige_expedicao_itens_os`). Permissões novas `OS_COMP.AUTORIZAR`/
  `OS_COMP.EXPEDIR` no catálogo. 22 testes unitários novos em
  `test_os_itens_service.py` (estoque condicional nas 3 funções de item +
  as 4 funções de autorização/expedição, incluindo os casos de bloqueio por
  já-autorizado/falta-de-expedição-prévia/área-de-estoque).
- **Frontend**: `OSItemRow`/`OSData` (`types.ts`) estendidos com os campos
  novos; `useOSItens.ts` ganhou estado de seleção em lote
  (`autorizacaoSelecionados`) + as 4 ações; `AutorizacaoItensModal.tsx` novo
  (lista de itens com checkbox + badge de estado Autorizado/Expedido +
  usuário/data, e os 4 botões de ação — Autorizar/Remover Autorização
  sempre visíveis se `OS_COMP.AUTORIZAR`; Autorizar Expedição/Remover
  Expedição só quando `exige_expedicao_itens_os` E `OS_COMP.EXPEDIR`).
  Botão "Autorização de Itens" em `os-geral.tsx`, ao lado do de Pontuação de
  Técnicos, só aparece quando pelo menos uma das 2 flags de empresa está
  ligada E o usuário tem `OS_COMP.AUTORIZAR` ou `OS_COMP.EXPEDIR`.
- **Testado ao vivo contra KONTACTO TESTE** (produto `P9890`, O.S. #20497):
  liguei `exige_aprovacao_itens_os` temporariamente (valor original 0/0
  restaurado ao final), incluí item e confirmei que o estoque NÃO foi
  reservado (`qtd`/`reservado_os` inalterados); Autorizar moveu o estoque
  corretamente (-2/+2) e criou a trilha (`os_autorizacao`/
  `os_autorizacao_itens`); Remover Autorização estornou certinho. Depois
  liguei também `exige_expedicao_itens_os` e confirmei: Autorizar sem
  Expedir antes bloqueia (`bloqueados`); Expedir não mexe em estoque;
  Autorizar depois de Expedir funciona; Remover Autorização de Expedição
  bloqueia com item já autorizado, funciona depois de remover a
  autorização. Exclusão do item de teste estornou corretamente (item nunca
  autorizado) e o estoque final bateu exatamente com o valor inicial
  (73/1). Catálogo de permissões confirmado expondo `AUTORIZAR`/`EXPEDIR`
  sob `OS_COMP`. `tsc --noEmit` sem novos erros (baseline 12 preexistentes,
  não relacionados). **UI React (cliques/modal) não testada visualmente**
  — só a API, mesma ressalva já registrada pro resto da O.S. Completa nesta
  sessão (sem ferramenta de automação de navegador disponível).

### Fora do escopo desta rodada

- Nenhum relatório/consulta consolidada de itens pendentes de autorização/
  expedição entre O.S. (só o modal por-O.S., igual ao escopo do frame
  original).
- Cadastro/gestão de `funcionarios_area` não foi tocado — já existia e já
  é gerenciável via o cadastro de Funcionários, só foi CONSULTADO aqui.

---

## Tempo Gasto por Serviço

**Status: 🟢 Implementado 2026-08-01 (testes unitários; sem teste ao vivo
contra KONTACTO TESTE ainda — próxima sessão que tocar este módulo deve
validar antes de considerar realmente concluído).** Migração do frame
"Tempo Gasto" (`Command30_Click`/`Command57_Click`/`Command56_Click`) —
rastreado no código-fonte real em `C:\Desenv\VB6\SQLSERVER\Revenda\
FrmTraOsNew.frm` (20241 linhas). **`Geral\FrmTraOs.frm` NÃO tem essa
feature** (confirmado por grep, 0 ocorrências de `os_tempo`) — mesmo
precedente já registrado em "Autorização/Expedição de Itens" acima:
`Revenda\` é a cópia com a lógica de fato implementada, `Geral` não serve
de referência aqui.

### Regras de negócio confirmadas no rastreio

- Tabela `os_tempo` (colunas confirmadas no código real: `codigo` PK
  IDENTITY, `os` FK, `codigo_interno`, `funcionario`, `data`,
  `hora_inicio`, `hora_fim` opcional, `obs`) — já existia no schema, até
  agora só referenciada como guard de integridade em
  `funcionarios_service.py` (`("os_tempo", "funcionario", "", "Tempo de
  O.S.")`), nunca tinha CRUD próprio.
- Painel é uma seção dentro do próprio `FrmTraOsNew.frm` (não um form
  separado) — grid + formulário de lançamento, sem tela de
  relatório/consulta dedicada em nenhum outro `.frm`.
- **Só permite Incluir/Alterar/Excluir com a O.S. Aberta** — confirmado em
  `Command56_Click`/`Command57_Click` (`If tb("situacao") <> "A" Then
  fechaconexoes: Exit Sub`). **Consulta é permitida em qualquer situação**
  (a checagem de `Command30_Click`, que abre o painel, está comentada no
  legado).
- Combo de Serviço restrito ao que já foi incluído na O.S. (`SELECT
  DISTINCT servicos.codigo... WHERE os=<OS>`), com fallback pro catálogo
  geral de serviços quando a O.S. ainda não tem nenhum serviço lançado.
- **Tempo Gasto é sempre DERIVADO** (`hora_fim - hora_inicio`), nunca uma
  coluna própria persistida — recalculado a cada exibição no legado
  (`Diferenca()`), replicado aqui em Python (`_tempo_gasto_min`, assume
  virada de meia-noite quando `hora_fim < hora_inicio`).
- **Não replicado** (workaround VB6, não regra de negócio — ver "Não
  replicar truques VB6" no CLAUDE.md): o bloqueio de escrita no legado é
  **silencioso** (sem mensagem, só sai da sub-rotina). Aqui optamos por
  retornar uma mensagem clara ("OS 'X' não permite lançar/excluir Tempo
  Gasto — só com a OS Aberta") — a regra real (bloquear) foi mantida, só
  o silêncio da UI não foi replicado.

### O que foi implementado

- **Backend**: `backend/services/os_tempo_service.py` (novo — list/save/
  delete, exige OS Aberta pra escrita, sem checagem de permissão
  server-side — mesmo padrão já usado por TODO o resto de
  `os_itens_service.py`: ADD_ITEM/EDIT_ITEM/DEL_ITEM/PONTUACAO/AUTORIZAR/
  EXPEDIR também não checam `tem_permissao` server-side, só client-side
  via `can(...)` — não é uma omissão desta rodada, é consistência com o
  arquivo-irmão). `OSTempoSaveRequest` novo em `schemas.py`. 3 rotas novas
  em `os_completo.py` (`GET/POST /api/os-completo/{codigo}/tempo`,
  `PUT/DELETE /api/os-completo/{codigo}/tempo/{tempo_codigo}`, log de
  auditoria `tela="OS_COMP"`, `comando="TEMPO"`). Permissão nova
  `OS_COMP.TEMPO` no catálogo (`ACOES_OS_COMP`). 19 testes unitários novos
  em `test_os_tempo_service.py` (validação de campos obrigatórios, OS não
  encontrada/não aberta, criar/atualizar/excluir com sucesso e bloqueios,
  cálculo de `_tempo_gasto_min` incl. virada de meia-noite).
- **Frontend**: `frontend/src/components/os/TempoGastoModal.tsx` — modal
  autocontido (busca sua própria lista ao abrir, não depende do hook
  `useOSItens`, mesmo espírito de `AnexosOSModal.tsx`): formulário
  Serviço (combo dos serviços já na O.S., fallback pro catálogo geral via
  `GET /api/produtos-servicos?tipo=S`) + Técnico (reaproveita `funcOptions`
  já carregado em `os-geral.tsx`) + Data/Hora Inicial/Hora Final
  (`WebDateField`) + Observação, lista de lançamentos com duração
  calculada (`Xh Ymin`) e Editar/Excluir por linha — formulário e ações de
  escrita somem quando a O.S. não está Aberta, mantendo só a consulta.
  Botão "Tempo Gasto por Serviço" em `os-geral.tsx` (ícone `time-outline`,
  ao lado de Pontuação/Autorização), gated por `can("OS_COMP.TEMPO")`,
  visível independente de a O.S. já ter itens (diferente de Pontuação/
  Autorização, que só aparecem com `it.itens.length > 0` — Tempo Gasto não
  é por-item, então não faz sentido escondê-lo nesse caso). Entrada nova
  no Modo Didático (`AJUDA_OS_ITENS`).
- `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
  inalterado). Suíte de testes do backend (O.S. completa + Tempo Gasto):
  151 testes, sem regressão.

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — só testado via testes
  unitários (cursor fake) e `tsc`, igual à ressalva já registrada nas
  outras sub-features desta sessão quando não dava pra usar navegador.
  Validar criar/editar/excluir lançamento e o fallback de busca de
  serviço (O.S. sem nenhum serviço lançado ainda) antes de considerar
  encerrado.
- Nenhum relatório consolidado de tempo gasto por técnico/serviço (ex.:
  total de horas no período) — só o lançamento por O.S., igual ao escopo
  mínimo do frame original.
- `os_tempo.codigo_interno` aceita só serviços nesta implementação — o
  legado também suporta peças no JOIN de exibição (`UNION ALL PECAS`),
  mas o combo de lançamento em si só oferece serviços (`LEFT(codigo_interno,1)='S'`
  no fallback); não foi encontrado nenhum caminho no legado que de fato
  grave uma peça em `os_tempo`, então não foi replicado.

---

## Requisições Vinculadas (O.S. Completa)

**Status: 🟢 Implementado 2026-08-01 (testes unitários; sem teste ao vivo
contra KONTACTO TESTE ainda — validar antes de considerar realmente
concluído).** Migração da aba "Requisições vinculadas a O.S." (`GridReq`,
`Sub Requisicoes()`) — rastreada no código-fonte real em
`C:\Desenv\VB6\SQLSERVER\Revenda\FrmTraOsNew.frm` (2ª aba de um `SSTab1`
dentro do frame "Itens da Ordem de Serviço", ao lado de "Itens..." e
"Autorização de Itens"). **100% somente leitura no legado** — confirmado
por grep: não existe `GridReq_Click`/`GridReq_DblClick` em todo o arquivo,
e `Frame17` (o frame que contém o grid) não tem nenhum outro controle.

### Rastreio — dois mecanismos de vínculo coexistentes no legado

Achado importante durante o rastreio (evita retrabalho numa sessão
futura): o legado tem **dois mecanismos diferentes e redundantes** para
vincular uma Requisição a uma O.S., e o `GridReq` lê os dois via
`UNION ALL`:

1. **Tabela `os_requisicao`** (`os` + `requisicao`, só essas 2 colunas —
   confirmado por todo `INSERT INTO Os_Requisicao` encontrado no
   repositório). É gravada só por variantes do form de inclusão de item de
   O.S. **fora** de `Revenda\` (`Klifer\FrmOsProdutoNV2.frm`,
   `Geral\FrmOsProdutoPAFECF.frm`, `Geral\FrmOsProdutoNV.frm`/`NV2.frm`) —
   ou seja, **nenhum form que esta migração já rastreou/portou grava
   nela**. `Revenda\FrmTraOsNew.frm` só LÊ essa tabela (reserva de
   estoque, limpeza no Cancelar O.S.), nunca escreve.
2. **Colunas escalares `requisicao.tipo_mov_requisicao`/
   `codigo_requisicao`** — é o mecanismo que a tela de Requisição já
   migrada (`Geral\frmmanreq.frm`, campo "Documento vinculado" do
   cabeçalho, `Campo(0)`/`Campo(4)`) usa de fato, só que esse campo **não
   foi implementado** na migração de Requisição (registrado lá como fora
   de escopo — "Toda requisição criada aqui é avulsa" — ver seção
   "Movimentações" acima). Também é o mecanismo usado pelo
   `GeraRequisicao` (`Geral\mdl_proc.bas:18849`, requisição automática de
   produto composto) chamado por `Revenda\FrmTraOsNew.frm:8652`.
- **Consequência prática pra esta implementação**: como nenhuma tela desta
  migração grava em nenhum dos dois mecanismos ainda, esta grade hoje
  normalmente vem **vazia** em qualquer O.S. criada só pela stack nova —
  isso é esperado, não é bug. A leitura foi implementada fiel ao legado
  (`UNION ALL` das duas fontes) pra já cobrir (a) dados históricos que
  possam existir em `os_requisicao` de outras variantes/instalações e (b)
  o dia em que "Documento vinculado" for implementado na tela de
  Requisição — nenhuma mudança seria necessária nesta grade.
- **Só mostra PRODUTOS** (join com `pecas`), nunca serviços — fiel ao
  legado, que nunca junta com `servicos` nesta grade específica, mesmo a
  Requisição em si aceitando os dois tipos.
- Recarrega ao abrir/trocar de O.S. no legado (5 pontos de `Call
  Requisicoes` — `Form_Load`, `CARREGAOS`, "Nova O.S.", requisição
  automática, reabrir/gravar); replicado aqui como um `GET` sob demanda ao
  abrir o modal (não fica escutando eventos da tela).

### O que foi implementado

- **Backend**: `os_completo_service.list_requisicoes_vinculadas` (nova
  função `_list_requisicoes_vinculadas_sync`, réplica fiel do `UNION ALL`
  do `GridReq`, com total calculado em Python — mesmo padrão de
  `os_tempo_service`, sem view nova). Rota
  `GET /api/os-completo/{codigo}/requisicoes-vinculadas`. Permissão nova
  `OS_COMP.VER_REQUISICOES` ("Ver Requisições Vinculadas", mesmo padrão de
  `VER_DESCONTOS` — ação só de leitura). 4 testes unitários novos em
  `test_os_completo_service.py` (OS não encontrada, lista+soma total,
  lista vazia, wrapper async).
- **Frontend**: `frontend/src/components/os/RequisicoesVinculadasModal.tsx`
  — modal 100% somente leitura (sem formulário, sem botão de ação), busca
  a lista ao abrir, mostra requisição/data/cód. fábrica/descrição/qtd×valor
  unit./total por linha + linha de TOTAL geral. Botão "Requisições
  Vinculadas" em `os-geral.tsx` (ícone `clipboard-outline`, na mesma linha
  do botão de Tempo Gasto), gated por `can("OS_COMP.VER_REQUISICOES")`,
  visível independente de a O.S. ter itens (mesmo raciocínio do botão de
  Tempo Gasto — não é uma ação por-item). Entrada nova no Modo Didático.
- `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
  inalterado — 1 erro novo foi introduzido e corrigido na mesma rodada,
  `alignItems: "center"` sem `as const` no objeto de estilo). Suíte de
  testes do backend (O.S. completa + Requisição): 131 testes, sem
  regressão.

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — como o mecanismo de vínculo
  ainda não é gravado por nenhuma tela desta migração (ver acima), não há
  hoje um jeito de popular dados reais pra esse teste sem um INSERT manual
  direto no banco; validar quando "Documento vinculado" for implementado
  na tela de Requisição, ou com um INSERT manual de teste em
  `os_requisicao`/`requisicao.codigo_requisicao` se quiser validar antes
  disso.
- **"Documento vinculado" na tela de Requisição** (`Geral\frmmanreq.frm`,
  `Campo(0)`/`Campo(4)`, grava `requisicao.tipo_mov_requisicao`/
  `codigo_requisicao`) — continua fora de escopo, não foi implementado
  nesta rodada (só a LEITURA do lado da O.S. foi feita). Se for pedido no
  futuro: campo de texto "Tipo"+"Código" no cabeçalho da Requisição,
  validando que só aceita `Tipo="OS"` + um número de O.S. Aberta
  existente (mesma regra do legado, `Campo_LostFocus` linhas 1595-1639 de
  `frmmanreq.frm`).
- **Escrita em `os_requisicao`** (Mecanismo B, "Importar Requisição
  Fechada" de `Klifer\FrmOsProdutoNV2.frm`) — não replicado; nenhum form
  desta migração usa esse fluxo específico de importação de requisição
  fechada pra dentro de um item de O.S.

---

## Agendar item de Serviço (O.S. Completa)

**Status: 🟢 Implementado 2026-08-01 (testes unitários + `tsc` limpo; sem
teste ao vivo contra KONTACTO TESTE ainda — validar antes de considerar
realmente concluído, inclusive criar/consultar a tabela `AGENDA_OS` numa
instalação real).** Extensão do módulo Agenda (já existente pro Pedido
Geral — módulo Clínica/Assistência, ver "Transações" > "Pedido Geral —
Fase B: Clínica (Agendamento)" acima) pra também cobrir item de Serviço da
O.S. Completa, quando o módulo Assistência está ligado.

### Rastreio — dois mecanismos coexistentes, `AGENDA_PEDIDO` vs. `AGENDA_OS`

O backend do módulo Agenda (`agenda_service.py`) era, antes desta rodada,
**hard-coded** pra `pedido_venda_prod`/`AGENDA_PEDIDO` — uma nota antiga
neste arquivo (seção "Transações" > "Pedido Geral — Fase B", "Integração
com O.S. Assistência Técnica") dizia que "o backend já é genérico
(AGENDA/AGENDA_PEDIDO/AGENDA_OS)", o que se mostrou **impreciso** ao
investigar de verdade: a tabela `AGENDA` em si não tem FK fixa pra
pedido/O.S. (é genérica), mas o CÓDIGO Python só sabia falar com
`AGENDA_PEDIDO`. `AGENDA_OS(CODAGENDA, CODOS)` é a tabela ponte
equivalente do lado da O.S. (`CODOS` guarda o `os_produto.cod_os_prod` do
ITEM, mesma convenção de `AGENDA_PEDIDO.CODPEDIDO` guardar o `codauto` do
item, não o número do pedido/O.S.) — confirmada como parte real do schema
legado, mas nenhum código Python a usava ainda.

### O que foi generalizado no backend (sem duplicar a máquina de estados)

`agenda_service.py` ganhou um parâmetro `origem: str = "pedido"` (e
`tela: str = "PEDIDO_COMP"` pra permissão) em `_salvar_agendamento_sync`/
`_cancelar_agendamento_sync`/`_agendamento_atual`/
`get_agendamento_item`/`salvar_agendamento`/`cancelar_agendamento` —
**default preserva 100% do comportamento anterior** (todos os 53 testes
pré-existentes de `test_agenda_service.py` passam sem alteração de
fixture). Só os pontos que precisam saber a tabela/coluna de origem
branch por `origem`:
- Busca do item (`pedido_venda_prod`/`pedido_venda` vs. `os_produto`/`os`)
  — o resto da validação (item cancelado, é serviço, elegibilidade por
  especialidade, disponibilidade do profissional, situação protegida) é
  **100% compartilhado**, não duplicado.
- `_agendamento_atual` (bridge `AGENDA_PEDIDO`/`AGENDA_OS`).
- INSERT do vínculo ao criar (`AGENDA_PEDIDO`/`AGENDA_OS`).
- UPDATE do cache no item (`pedido_venda_prod.data_servico`/
  `.executor_agenda` vs. `os_produto.data_servico`/`.executor_agenda` —
  colunas novas em `os_produto`, ver migração abaixo).
- `_agendamento_por_codagenda` agora faz LEFT JOIN nos DOIS bridges e
  **deriva** um campo novo `origem` (`"pedido"`/`"os"`/`None` avulso) —
  usado por `_trocar_profissional_sync` (que só recebe `codagenda`, não
  sabe a origem de antemão) pra decidir qual tabela de item atualizar.
  Campos de saída antigos (`codauto`, `pedido`) continuam com o mesmo
  significado de antes (só o lado Pedido) — os novos (`codauto_os`, `os`,
  `origem`) são aditivos, nenhum consumidor existente quebra.
- **Migrações idempotentes novas** em `pedido_common.py`
  (`_ensure_agenda_os_table`/`_ensure_os_produto_agenda_cols`, mesmo
  padrão de `_ensure_agenda_forma_pag_tables`/`_ensure_qtd_pessoas_col` —
  `IF NOT EXISTS`, sem executor de migração central): criam `AGENDA_OS` se
  não existir, e `os_produto.data_servico`/`.executor_agenda` se não
  existirem. Chamadas tanto ao salvar um agendamento de O.S. quanto na
  listagem de itens da O.S. (`os_itens_service._list_itens_sync`, pro
  enriquecimento — ver abaixo), pra nunca quebrar numa instalação que
  ainda não tem essas tabelas/colunas.
- `os_itens_service._list_itens_sync` ganhou o mesmo enriquecimento com
  `item.agendamento` que o Pedido Geral já tinha
  (`pedido_completo_service._get_pedido_completo_sync`) — mesma forma
  (`codagenda`/`data`/`hora_ini`/`profissional`/`funcionario`/`situacao`),
  reaproveitando o campo `agendamento?` que já existe em `ItemRow`
  (compartilhado por Pedido e O.S. via `OSItemRow = ItemRow & {...}`).
- Rotas novas em `routes/agenda.py`: `GET/POST /api/agenda/os-item/
  {cod_os_prod}` e `POST /api/agenda/os-item/{cod_os_prod}/cancelar` —
  espelham as rotas `/agenda/item/{codauto}` já existentes, log de
  auditoria com `tela="OS_COMP"`.
- Permissão nova `OS_COMP.AGENDAR` no catálogo (`ACOES_OS_COMP`).
- 9 testes unitários novos em `test_agenda_service.py` (salvar/cancelar/
  trocar profissional pela origem "os", checagem de permissão por tela,
  módulo desligado, derivação de `origem` em `_agendamento_por_codagenda`)
  + 2 em `test_os_itens_service.py` (enriquecimento com/sem agendamento).
  Suíte completa relacionada (agenda + O.S. + Pedido Completo + permissões):
  274 testes, sem regressão.

### O que foi feito no frontend (reaproveitando o modal inteiro, não um fork)

`AgendarModal.tsx` (Situação do Atendimento, Revisão/Garantia,
Descartáveis, Hora Chegada/Saída, Anexos do agendamento, Formulários/
Layouts, Troca de Profissional com `AuthorizationSlide` — feature completa
já validada no Pedido Geral) foi **reaproveitado tal e qual**, sem
duplicar nenhuma linha de UI: seu prop `it` era tipado como
`UsePedidoItens` (o hook inteiro do Pedido); foi estreitado pra uma
interface estrutural nova, `AgendaItens`
(`frontend/src/components/pedido/agendaTypes.ts` — `conn`, `agendarItem`,
`setAgendarItem`, `profissionaisAgenda`, `profissionaisLoading`,
`agendaSaving`, `salvarAgendamento`, `cancelarAgendamento`,
`trocarProfissionalAgenda`, os únicos 9 campos que o modal de fato usa).
Mesmo princípio já usado em `ItemList.tsx`'s `ItemListItens`/
`GeneralDiscountModal`/`DiscountsReportModal` — `UsePedidoItens` já
satisfaz `AgendaItens` automaticamente (é superset, zero mudança no
Pedido), e `useOSItens.ts` (O.S. Completa) só precisou implementar esses 9
campos DE VERDADE (antes só tinha `setAgendarItem` como no-op) — as
funções são réplica adaptada das de `usePedidoItens.ts`, só apontando pra
`/api/agenda/os-item/...` em vez de `/api/agenda/item/...`.

- `ItemList.tsx`'s `canAgendar` estendido: `tela === "OS_COMP" &&
  moduleOn("Assistencia") && can("OS_COMP.AGENDAR")` (Clínica não se
  aplica à O.S. — é exclusiva do segmento Pedido). O botão "Agendar"/
  "Ver Atendimento" por item de Serviço, e o texto "· Agendado: ..." na
  descrição, já funcionam pra O.S. sem nenhuma mudança adicional em
  `ItemList.tsx` (o componente já era compartilhado).
- `os-geral.tsx`: `<AgendarModal it={it} clienteCodigo={cliente?.codigo}
  usuarioCod={usuarioCod} />` adicionado; `useOSItens` ganhou o parâmetro
  `master` (bypassa a permissão AGENDAR no backend, mesmo padrão do
  Pedido) alimentado por `isMaster` (`usePermissions()`). Entrada nova no
  Modo Didático (`AJUDA_OS_ITENS`).

### Desdobramento de item (`os_agenda_split`) — implementado 2026-08-01, mesmo dia

**Correção da decisão acima, revertida no mesmo dia por pedido explícito
do usuário** ("pode replicar. caso o técnico tenha que fazer 3
manutenções por mês com datas diferentes da mesma OS"). A hipótese
registrada acima (itens de Serviço de O.S. seriam sempre unidades únicas)
era errada pro caso real de uso — Assistência Técnica também tem
atendimentos recorrentes na mesma O.S. (manutenções periódicas), cada um
com data própria.

`os_itens_service._add_item_sync` ganhou o mesmo `clinica_split` do
Pedido Geral (renomeado `os_agenda_split` no contexto da O.S., mesma
lógica): item de Serviço + módulo Agenda ativo (`_modulo_agenda_ativo`,
CLINICA OU Assistência — reaproveitado sem mudança) grava N linhas
(`os_produto`, `quant=1` cada, literal na query — não parâmetro) em vez
de 1 linha com `quant=N`; quantidade fracionária bloqueia com mensagem
clara ("cada unidade vira um atendimento agendável"). Produto (tipo "P")
nunca desdobra — o `and` do Python nem chega a consultar
`_modulo_agenda_ativo` (short-circuit), sem query extra nesse caminho.
Reserva de estoque (`_mover_estoque`) só roda no caminho SEM desdobro —
no caminho desdobrado é sempre serviço, então seria sempre um no-op
(`_is_peca` retorna False), evitado de propósito pra não gastar N queries
à toa.

- **Resposta do backend** ganhou `cod_os_prods` (lista, todos os códigos
  criados) e `os_agenda_split` (bool) além do já existente `cod_os_prod`
  (mantido = primeiro da lista, pra não quebrar nenhum consumidor que já
  lia essa chave). `routes/os_completo.py`'s `add_item` usa
  `os_agenda_split` pra logar uma descrição diferente no log de auditoria
  ("Serviço 'X' desdobrado em N atendimento(s) agendável(is)..."), mesmo
  padrão já usado em `routes/pedido_completo.py`.
- **Frontend não precisou de nenhuma mudança** — `useOSItens.
  handleAddItem` já só olha `j?.success` e recarrega a lista
  (`loadItens()`); as N linhas aparecem naturalmente depois do reload,
  cada uma agendável via o botão "Agendar" já implementado (ver seção
  acima). Mesmo comportamento (nenhum toast especial pro caso desdobrado)
  já usado pelo Pedido Geral — não é uma lacuna, é o padrão existente.
- 4 testes unitários novos em `test_os_itens_service.py`
  (`TestAddItemAgendaSplit`): desdobra em N linhas com módulo ativo,
  bloqueia quantidade fracionária, NÃO desdobra com módulo desligado,
  produto nunca desdobra e nunca consulta `controle_configuracao`. Suíte
  completa relacionada (O.S. + Agenda + Pedido Completo + permissões):
  202 testes, sem regressão. `tsc --noEmit`: sem novos erros (nenhuma
  mudança de frontend nesta correção).

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — só testes unitários (cursor
  fake) e `tsc`, mesma ressalva já registrada nas outras sub-features
  desta sessão. Validar especialmente: `AGENDA_OS` sendo criada
  corretamente na primeira vez que alguém agenda um item de O.S. nessa
  base, o enriquecimento de `item.agendamento` na listagem não quebrando
  instalações que nunca usaram Agenda em O.S. antes, e o desdobramento em
  N linhas gerando de fato N atendimentos agendáveis independentes na UI.
- Tudo que já está fora de escopo pro módulo Agenda do Pedido Geral
  (Foto via webcam, Exportar Excel/Imprimir agenda via automação COM)
  continua fora de escopo aqui também, sem mudança.

---

## Doc. Origem / Revisão Programada (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (testes unitários + `tsc` limpo; sem
teste ao vivo contra KONTACTO TESTE ainda — validar antes de considerar
realmente concluído).** Migração de `Command2_Click` (Gravar da O.S.),
`Revenda\FrmTraOsNew.frm`, linhas 9737-9982 (validação) + 10043-10110
(consumo/regeneração de `osrevisao`) + 16107-16128/14311-14322 (habilita/
desabilita campo) + 5753-5764 (geração de datas). Item registrado há
tempos em PENDENCIAS.md sem detalhe nenhum — rastreio completo feito nesta
rodada antes de implementar.

### O que a feature realmente é (rastreio)

Duas features distintas no mesmo bloco de código, que se conectam:

1. **Doc. Origem** (`Campo(150)` + `Option9`"Pedido"/`Option10`"O.S.") —
   campo no CABEÇALHO da O.S. que aponta pra uma O.S. ou Pedido de Venda
   ANTERIOR, do qual esta O.S. é uma Garantia ou Revisão. Validado
   (cruzado) na gravação.
2. **Revisão programada** (`Campo(151)` "Revisões" + tabela `osrevisao`) —
   ao informar uma quantidade, gera N datas futuras (a cada 30 dias,
   pulando domingo) "reservadas" pra essa O.S. — não é um job/cron, é só o
   registro das datas esperadas (uma "agenda" de revisitas). Campo sempre
   habilitado, em QUALQUER O.S., independente do tipo (`Campo(151).Enabled
   = True` incondicional no legado).

Quando o cliente volta, uma nova O.S. do tipo Revisão informa a O.S.
anterior como Doc. Origem e "reivindica" a data mais antiga ainda
disponível dessa O.S. de origem.

### Regras de negócio confirmadas no rastreio

- **Dois ramos mutuamente exclusivos**, decididos por SUBSTRING (sem
  acento, maiúsculo) do texto do Tipo O.S. escolhido — não dá pra usar
  código fixo, o cadastro `tipo_os` é livre:
  - **Ramo "revisao"**: tipo contém "REVISÃO"/"REVISAO" E
    `controle_aux.ControlaRevisaoOS` ligado — só aceita **O.S.** como
    origem (Pedido fica bloqueado na tela), e exige uma data de revisão
    programada AINDA DISPONÍVEL na O.S. de origem (`osrevisao`).
  - **Ramo "garantia"**: tipo contém "GARANTIA" (ou "REVISÃO"/"REVISAO"
    quando o ramo acima não se aplicou) E
    `controle_aux.EXIGE_OS_ORIGINAL_GARANTIA` ligado — aceita **O.S. OU
    Pedido de Venda** como origem.
  - Se nenhum ramo se aplica (tipo comum, ou flags desligadas), nada é
    validado.
- **Validações cruzadas** (ambos os ramos): Doc. Origem não pode ser a
  própria O.S.; a O.S./Pedido de origem precisa existir, ser do MESMO
  CLIENTE, e estar FATURADA/FATURADO (`situacao='PG'`). Ramo Revisão
  ainda exige uma linha em `osrevisao` com `os=<origem> AND
  ISNULL(osrevisao,0)=0` (data disponível) — a menos que esta própria
  O.S. já tenha consumido uma (reedição sem trocar Doc. Origem).
- **Bypass por "senha superior"**: se a validação falha, o usuário pode
  prosseguir mesmo assim com autorização de gerente/supervisor/master —
  mesmo padrão já usado em `AgendarItemRequest.autorizado_por`/
  `AuthorizationSlide` (frontend já validou a senha via `POST /api/login`,
  o backend não reverifica, só confia no sinal não-vazio).
- **Skip de revalidação**: se a O.S. já tem `validou_garantia=1` e os
  valores atuais de Doc. Origem/Tipo batem com os já persistidos, não
  repete a validação nem pede senha de novo (reedição de outros campos da
  mesma O.S. já autorizada).
- **Consumo de data programada** (só Ramo Revisão): libera qualquer
  vínculo anterior desta O.S. (`UPDATE osrevisao SET osrevisao=0 WHERE
  osrevisao=<esta_os>`) e reivindica a data mais antiga ainda disponível
  da O.S. de origem.

### Desvio deliberado do legado — regeneração de `osrevisao`

O legado, a CADA Gravar, apaga e recria TODAS as linhas de `osrevisao`
desta O.S. a partir do combo em tela (`DELETE FROM OsRevisao WHERE
os=Campo(0)` + reinsert), **mesmo que "Revisões" não tenha mudado** — isso
inclui linhas JÁ CONSUMIDAS por outra O.S., cujo reinsert (`INSERT INTO
OsRevisao (os,data)`, só 2 colunas) **perde o vínculo de consumo**
silenciosamente. Não achei nenhuma vantagem de negócio nisso — tem cheiro
de bug/efeito colateral não intencional do "apaga tudo e recria" (ver
"Não replicar truques VB6" no CLAUDE.md), não uma regra real.

**Implementado diferente, deliberadamente**: a cada Gravar, só as linhas
AINDA DISPONÍVEIS (`ISNULL(osrevisao,0)=0`) desta O.S. são apagadas e
recriadas a partir de `qtd_revisoes`; linhas já consumidas por outra O.S.
nunca são tocadas/apagadas por este código. Preserva o histórico de
consumo mesmo que o usuário reedite "Revisões" depois.

### O que foi implementado

- **Backend** — `pedido_common.py`: `_controla_revisao_os_ativo`/
  `_exige_os_original_garantia_ativo` (leitura dos 2 flags, já existiam
  migrados em `controle_aux`/`controle-sistema.tsx`, só não eram usados
  por nenhuma lógica ainda); `_ensure_os_doc_origem_cols` (migração
  idempotente — `os.Tipo_Doc_Original`/`.VALIDOU_GARANTIA`/`.QtdRevisoes`
  novas, `OS_ORIGINAL` já existia mas ficava hardcoded em `0`);
  `_ensure_osrevisao_table` (idem, tabela `osrevisao`); `_validar_doc_origem`
  (função pura, a máquina de validação em si, reaproveitável se outra tela
  algum dia precisar — hoje só a O.S. Completa usa).
  `os_completo_service.py`: `_save_os_completo_sync` resolve o texto do
  Tipo O.S. (`SELECT descricao FROM tipo_os`, só quando `posicao_os`
  informado — sem query extra quando não), chama `_validar_doc_origem`
  ANTES do INSERT/UPDATE, grava as 4 colunas novas, e depois do
  INSERT/UPDATE faz o consumo de data (Ramo Revisão) + regeneração segura
  de `osrevisao`. `_get_os_completo_sync` enriquece com `os_original`/
  `tipo_doc_original`/`validou_garantia`/`qtd_revisoes`/
  `revisoes_programadas` (lista, com quem consumiu cada data) +
  `controla_revisao_os`/`exige_os_original_garantia` (decide o que exibir
  no frontend). `OSCompletoSaveRequest` ganhou `os_original`/
  `tipo_doc_original`/`qtd_revisoes`/`autorizado_por`. Resposta de erro de
  validação ganha `requer_autorizacao: true` pro frontend saber quando
  oferecer o `AuthorizationSlide` em vez de só mostrar a mensagem.
  32 testes unitários novos (`test_pedido_common_doc_origem.py`: 23 casos
  cobrindo cada ramo/validação/bypass/skip-revalidação, com um
  `SqlFakeCursor` por substring — mesmo padrão de
  `test_pedido_common_forma_pagamento.py`; `test_os_completo_service.py`:
  9 novos, integração save/get/regeneração de `osrevisao`). Suíte completa
  relacionada: 329 testes, sem regressão.
- **Frontend** — `os-geral.tsx`: card novo "Revisão Programada" (sempre
  visível com a O.S. já salva) com o campo "Revisões" + lista read-only
  das datas já programadas (disponível/consumida por qual O.S.); campos
  "Doc. Origem" + seletor O.S./Pedido aparecem só quando
  `mostrarDocOrigem` (mesmo critério de ramo calculado no cliente, a
  partir do Tipo O.S. escolhido + flags já carregados no `os`) — Pedido
  fica oculto quando o ramo é Revisão (só aceita O.S.). No Gravar, se a
  resposta trouxer `requer_autorizacao`, mostra confirmação
  (`useFeedback().showConfirm`) e, se aceito, abre `AuthorizationSlide`
  (componente já estabelecido no projeto, reaproveitado sem duplicar) —
  autorizado, regrava passando `autorizado_por`. `OSData`
  (`os/types.ts`) ganhou os campos novos. Entrada nova no Modo Didático.
  `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
  inalterado).

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — só testes unitários e `tsc`,
  mesma ressalva das outras sub-features desta sessão. Validar
  especialmente: criação da tabela `osrevisao`/colunas novas em `os` numa
  instalação real, o fluxo completo Revisão (gerar datas numa O.S.,
  faturar, abrir uma segunda O.S. tipo Revisão apontando pra ela, conferir
  que consome a data certa), e o fluxo de bypass por senha superior
  (`AuthorizationSlide` → `autorizado_por` → regravação).
- **"Deseja entrar com senha superior?" pro CANCELAR o Gravar** — o
  legado, ao recusar a autorização (`MsgBox ... vbNo`), cancela o Gravar
  inteiro (`Exit Sub`, mantém a tela aberta pro usuário corrigir). Aqui o
  comportamento equivalente é: o toast de confirmação fecha, nada é
  gravado, o usuário permanece na tela com os campos como estavam — mesmo
  efeito, não implementado como um "modo" separado.
- **Log de auditoria da autorização por senha** — o legado grava uma linha
  em `Logs`/`Grava_Andamento` quando o bypass é usado. Não implementado
  nesta rodada (o log de auditoria genérico da tela já registra o GRAVAR
  em si, incluindo os campos alterados — só não há uma entrada DEDICADA
  "autorizado por X" como o legado tem). Registrar se o usuário pedir
  rastreabilidade específica desse evento.

---

## Cadastro de Equipamento Inline (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (sem teste ao vivo ainda — endpoint
`POST /api/equipamentos` já existe e já é usado/testado pela tela completa
`equipamentos.tsx`, só o formulário inline em si não foi exercitado contra
KONTACTO TESTE).** Sem precedente no legado (não é migração de VB6) — pura
melhoria de UX pedida pelo usuário. Sem mudança de backend: reaproveita
100% o endpoint já existente (`equipamentos_service._save_sync`), zero
rota/schema novo.

### O que mudou

Antes, `EquipamentoSearchModal.tsx` (usado pelo bloco "Dados do
Equipamento" da O.S. Completa) tinha um botão "Cadastrar novo
equipamento" que **fechava o modal e navegava** pra `/equipamentos` (tela
cheia) quando a busca não encontrava nada — perdendo o contexto da O.S.
que estava sendo preenchida.

Agora esse botão abre um **formulário mínimo dentro do próprio modal**
(sem navegação): Número de Série + Marca + Modelo (os 3 únicos campos que
o backend realmente exige — confirmado em `equipamentos_service._save_sync`,
linhas 143-151) + Portador (opcional, incluído por ser barato e útil).
Todo o resto (Local, Data de Revisão, Valor, Situação, Tipo, Detalhes)
fica com os defaults do backend (`situacao_equipamento='A'`,
`tipo_equipamento='A'` — Avulso, o default correto pra equipamento criado
a partir de uma O.S., "Contrato" é uma ação separada de disponibilização)
— quem precisar preencher esses campos completa depois pela tela cheia
`app/equipamentos.tsx`, que continua existindo inalterada como cadastro
completo.

Marca/Modelo são combos de tabela auxiliar (`GET /api/tabelas/marcas`/
`GET /api/tabelas/modelos?cod_marca=...`, Modelo dependente da Marca
escolhida) — mesmos endpoints que `equipamentos.tsx` já usa, buscados sob
demanda só quando o formulário inline é aberto (não no boot do modal de
busca, pra não gastar uma chamada à toa em toda O.S. que nunca precisa
cadastrar equipamento novo).

Ao gravar com sucesso, monta um `EquipamentoRow` sintético localmente (com
o `codigo` retornado pelo backend + os dados já digitados/escolhidos — sem
precisar de um segundo round-trip de busca) e chama `onPick` — o
equipamento recém-criado já fica selecionado na O.S. na hora, sem sair da
tela nem re-buscar.

### Duplicidade de Número de Série — comportamento herdado, não alterado

`numero_de_serie` é único **GLOBALMENTE** (entre todos os clientes, não só
o atual) — checado só no backend
(`equipamentos_service._save_sync:170-176`), sem checagem prévia no
frontend. Se o usuário digitar um nº de série que já existe em OUTRO
cliente, a mensagem de erro do backend aparece inline no formulário
(`friendlyApiError`) — mesmo comportamento que a tela completa já tinha,
só passou a aparecer também no fluxo inline.

### Precedente novo no projeto

**Este é o primeiro lugar do projeto com um cadastro 100% inline dentro de
um modal de busca, sem navegação nenhuma** — todo outro "Cadastrar
novo X" existente (Cliente a partir de `ClientSearchModal`, tanto em
Pedido/O.S. quanto em `AtendimentoAvulsoModal`) continua navegando pra uma
tela própria (`cliente-form.tsx`). Não generalizado retroativamente pros
outros — só Equipamento foi pedido explicitamente nesta rodada. Se um caso
futuro pedir o mesmo padrão pra outra entidade, este arquivo
(`EquipamentoSearchModal.tsx`) é a referência de implementação.

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — mesma ressalva de todas as
  sub-features desta sessão de O.S. Completa.
- **Local, Data de Revisão, Valor, Tipo, Detalhes** no formulário inline —
  deliberadamente fora, ver "O que mudou" acima. Só a tela completa
  continua oferecendo esses campos.
- Nenhuma mudança de backend — `equipamentos_service.py`/
  `routes/equipamentos.py` permanecem exatamente como estavam.

---

## Criar Cópia (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (sem teste ao vivo ainda — validar
antes de considerar realmente concluído).** Migração do botão "Criar
Cópia" (`Command49_Click`, `Revenda\FrmTraOsNew.frm`, linhas 11337-11383).

### Regras de negócio confirmadas no rastreio

- **Sem restrição de Situação** — disponível em QUALQUER situação da O.S.
  original (legado não checa `situacao` em lugar nenhum, nem pra
  habilitar o botão nem dentro da rotina). Única guarda é a O.S. já estar
  salva (`Campo(0) > 0`).
- **Sem confirmação prévia** — o legado executa direto no clique (só
  mostra "OS copiada com sucesso!" DEPOIS de já ter copiado).
- **Nova O.S. nasce sempre Aberta** (`situacao='A'` hardcoded), com data/
  hora de entrada = agora (não copia a data da O.S. original), número
  novo (aqui via `MAX(codigo)+1`, o gerador já padrão desta migração — o
  legado usa `GeraCodigoOS`/`CONTROLE.numero_os`, um contador próprio sem
  equivalente aqui, mesmo espírito de "Não replicar truques VB6").
- **Itens só são copiados se o produto/serviço mestre ainda está ATIVO no
  cadastro** (`pecas.situacao='A'`/`servicos.situacao='A'`) — item cujo
  cadastro foi desativado depois da O.S. original não é trazido pra
  cópia.
- **Preço do item recalculado pelo CADASTRO ATUAL** (`pecas.p_venda`/
  `servicos.valor_hora`), não o preço congelado que estava na O.S.
  original — e **desconto/acréscimo sempre zerados** na cópia.
- Copiados tal como estavam: quantidade, vendedor, executor, `faturado`,
  custo, pontuação (Executor/Vendedor/Atendente), situação/destino do
  item, `item_cancelado`.
- **Reserva de estoque das peças copiadas** — legado sempre reserva
  (`pecas.qtd -= quant`, `reservado_os += quant`), sem checar nenhuma
  flag; esta migração aplica a MESMA condição já usada em
  `os_itens_service._add_item_sync` (só reserva se a empresa NÃO exige
  Autorização de Itens) — adaptação deliberada pra manter consistência
  com o resto da migração, não uma omissão.
- **Formas de pagamento** — o legado copia as tabelas detalhadas
  (`os_dinheiro`/`os_cheque`/etc., via `Copia_FPAG_DAV`). **Não
  implementado nesta rodada** — só o código simples `forma_pagamento` do
  cabeçalho é copiado (via cópia normal de coluna), não o detalhamento
  por múltiplas formas. Ver "Fora do escopo" abaixo.
- **NÃO copiados** (mesmo comportamento do legado, confirmado nas colunas
  ausentes do `INSERT...SELECT` original): anexos, histórico/log
  (`LOG_OS`), agendamento (`AGENDA`/`AGENDA_OS`), Doc. Origem/Revisão
  (`OS_ORIGINAL`/`Tipo_Doc_Original`/`VALIDOU_GARANTIA`/`QtdRevisoes` —
  sempre zerados/nulos na cópia, mesmo que a O.S. original os tivesse).
- **Navega pra O.S. nova depois de criar** — mesmo efeito de `CARREGAOS
  Cod_OS` no legado (a tela fica olhando a cópia, não a original).

### Colunas do cabeçalho copiadas — recorte deliberado

O `INSERT...SELECT` do legado lista ~34 colunas do cabeçalho
(`NUM_CONTROLE, CLIENTE, CLIENTE_GARANTIA, FORMA_PAGAMENTO,
FORMA_PAGAMENTO_GARANTIA, EMP_OS, MARCA, MODELO, COR, ANO, RENAVAM,
PLACA, CHASSI, MOTOR, KM, NUMERO_DE_SERIE, DESCRICAO_CLIENTE, OBS,
RESUMO, COMPLEMENTO, ATENDENTE, DATA_COMPRA, REVENDEDOR, VALOR, PRISMA,
COR_PRISMA, TECNICO_RESPONSAVEL, POSICAO_OS, TIPO, STATUS_OS,
AREA_ATUACAO`). Esta migração copia só o subconjunto que já é
usado/exposto em ALGUMA outra tela da O.S. Completa (cliente, área de
atuação, descrição do cliente, obs, resumo, status O.S., atendente,
placa, marca, modelo, km, ano, chassi, nº de série, forma de pagamento,
referência, técnico responsável, tipo O.S.) — colunas como
`CLIENTE_GARANTIA`, `FORMA_PAGAMENTO_GARANTIA`, `COR`, `MOTOR`,
`COMPLEMENTO`, `PRISMA`, `COR_PRISMA`, `REVENDEDOR`, `DATA_COMPRA`,
`NUM_CONTROLE`, `EMP_OS`, `RENAVAM` nunca foram modeladas em NENHUM outro
lugar desta migração (não lidas, não gravadas, sem campo na tela), então
copiá-las seria copiar valores que o resto do app não consegue nem
exibir. Decisão deliberada, não uma omissão por pressa — se alguma dessas
colunas for modelada no futuro (ex.: Bifurcação de faturamento
Garantia×Cliente vai precisar de `CLIENTE_GARANTIA`/
`FORMA_PAGAMENTO_GARANTIA`), revisitar esta cópia também.

### O que foi implementado

- **Backend** — `os_completo_service._criar_copia_os_sync` (+ wrapper
  async `criar_copia_os`): checa permissão, busca cabeçalho de origem,
  gera novo código, INSERT do cabeçalho (recorte de colunas acima,
  `situacao='A'` hardcoded, `OS_ORIGINAL=0` sempre), 2 INSERTs de itens
  (JOIN com `pecas`/`servicos` filtrando `situacao='A'` e recalculando
  preço), reserva de estoque condicional, `_recalc_os_total` no fim
  (itens inseridos via SQL direto, não via `_add_item_sync`, então
  `os.valor` precisa ser recalculado manualmente). Rota nova
  `POST /api/os-completo/{codigo}/copiar` (`routes/os_completo.py`,
  reaproveita `FecharRequest` como body — mesmo padrão de
  Fechar/Faturar/Reabrir/Cancelar, já tem tudo que a ação precisa). Log
  de auditoria `tela="OS_COMP"`, `comando="COPIAR"`, referência = código
  da O.S. NOVA (não da original). Permissão nova `OS_COMP.COPIAR`. 6
  testes unitários novos em `test_os_completo_service.py` (permissão,
  não encontrada, sucesso sem itens, cópia de itens pecas+serviços,
  reserva de estoque condicional, wrapper async). Suíte completa
  relacionada: 260 testes, sem regressão.
- **Frontend** — `os-geral.tsx`: botão "Criar Cópia" (ícone
  `copy-outline`) na mesma linha de Tempo Gasto/Requisições Vinculadas
  (mesmo padrão visual, sem depender de a O.S. ter itens — disponível em
  qualquer situação, igual ao legado), gated por `can("OS_COMP.COPIAR")`.
  Spinner + texto "Copiando…" enquanto processa (regra global "Feedback
  visual em processos demorados >3s" do CLAUDE.md). Ao concluir, navega
  pra O.S. nova (`router.replace`), mesmo efeito do `CARREGAOS` do
  legado. Entrada nova no Modo Didático. `tsc --noEmit`: sem novos erros
  (baseline de 12 pré-existentes inalterado).

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — mesma ressalva de todas as
  sub-features desta sessão de O.S. Completa.
- **Cópia de Formas de Pagamento detalhadas** (`Copia_FPAG_DAV`, tabelas
  `os_dinheiro`/`os_cheque`/`os_cartao`/`os_debito`/`os_duplicata`/
  `os_ticket`/`os_vale`/`os_financiado`) — não implementado, só o código
  simples do cabeçalho é copiado. Se precisar no futuro, `pedido_common.
  FORMA_PAG_SUFIXO_TIPO`/`DAV_CONFIG` já têm a estrutura de tabelas
  mapeada, só falta escrever a função de cópia em si.
- **Colunas de cabeçalho nunca modeladas nesta migração** — ver "Colunas
  do cabeçalho copiadas" acima.
- **Confirmação antes de copiar** — não implementado (o legado também não
  tem); se o usuário achar o clique único arriscado demais na prática,
  considerar um `showConfirm` no futuro.

## Alteração de Executor pós-fechamento (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (sem teste ao vivo ainda — validar
antes de considerar realmente concluído).** Migração do botão
`CmdAltExec`, branch F/PG de `CmDaltera_Click` (`Revenda\FrmTraOsNew.frm`)
— corrige o Executor (técnico) e/ou o Vendedor de um item já lançado
depois que a O.S. foi Fechada ou Faturada, sem precisar reabrir a O.S.

### Regras de negócio confirmadas no rastreio

- **Só disponível com a O.S. Fechada (`F`) ou Faturada (`PG`)** — com a
  O.S. Aberta, a correção de Vendedor/Executor já é possível pela edição
  normal do item (`OSItemModal.tsx`), que também permite mexer em preço/
  quantidade/desconto; este botão é especificamente a via restrita
  pós-fechamento, quando a edição normal do item já está bloqueada.
- **Preço/quantidade/desconto continuam bloqueados** — só
  `os_produto.vendedor`/`.executor` são alterados; nenhum outro campo do
  item é tocado nem recalculado (`_recalc_os_total` não é chamado).
- **Efeito colateral de comissão do legado NÃO foi portado** — no VB6,
  trocar o Executor/Vendedor de um item já lançado recalcula ao vivo os
  campos de comissão (`ITEM_COMISSAO_VENDEDOR`/`ITEM_COMISSAO_EXECUTOR`
  em `os_produto`, `movimentacao.item_paga_comissao`,
  `MOVIMENTACAO.VENDEDOR` via `COMANDA_OS` da O.S. faturada). **Esta
  migração não tem nenhum módulo de comissão implementado** — nenhuma
  dessas tabelas/campos existe aqui, então nada precisou (nem pôde) ser
  replicado. Se um módulo de comissão for construído no futuro, revisitar
  esta função (`_alterar_executor_sync`,
  `backend/services/os_itens_service.py`) pra adicionar o recálculo
  correspondente.
- **Propagação em massa (`propagar_demais`) — SEM equivalente no legado**,
  conveniência desta migração: quando marcada, aplica a MESMA troca a
  todos os outros itens da O.S. que tinham o valor ANTERIOR de Vendedor/
  Executor (não o valor novo) — pensado pro caso comum de uma O.S. inteira
  ter sido lançada com o técnico errado.
  - **Guarda deliberada, não presente no legado**: só propaga quando o
    valor ANTERIOR do item de origem não era vazio/nulo — evita propagar
    "de vazio pra um valor" em massa sobre itens que nunca tiveram
    executor/vendedor definido (poderia sobrescrever escolhas
    intencionalmente distintas por item).
- **Sem checagem de permissão explícita dentro do service** — segue o
  mesmo padrão já usado pelas outras ações de `os_itens_service.py`
  (a permissão é responsabilidade da camada de rota/frontend, não
  duplicada dentro do `_sync`).

### O que foi implementado

- **Backend** — `AlterarExecutorRequest` (`backend/models/schemas.py`,
  `vendedor`/`executor` opcionais — `None` = não alterar aquele campo,
  `propagar_demais` opcional). `_alterar_executor_sync` + wrapper async
  `alterar_executor` (`backend/services/os_itens_service.py`): valida
  situação da O.S. (`F`/`PG`), valida item existente, faz o `UPDATE`, e
  quando `propagar_demais` é verdadeiro, localiza e atualiza os demais
  itens que tinham o valor anterior (executor e vendedor tratados
  independentemente — só propaga o que de fato mudou). Rota nova
  `PUT /api/os-completo/{codigo}/itens/{cod_os_prod}/executor`
  (`routes/os_completo.py`), com log de auditoria
  (`tela="OS_COMP"`, `comando="ALT_EXECUTOR"`, diff de
  `vendedor`/`executor`, menciona quantos itens foram propagados na
  descrição). Permissão nova `OS_COMP.ALT_EXECUTOR`
  (`permissoes_service.py`, fim de `ACOES_OS_COMP`). 13 testes unitários
  novos em `test_os_itens_service.py`
  (`TestAlterarExecutorPosFechamento`) cobrindo: bloqueio fora de F/PG,
  item não encontrado, OS não encontrada, alteração só de executor, só de
  vendedor, dos dois juntos, propagação de executor, propagação de
  vendedor, propagação dos dois, guarda de valor anterior vazio não
  propaga, `propagar_demais=False` não propaga mesmo com outros itens
  elegíveis, nada informado retorna erro, e o wrapper async. Suíte
  focada (`test_os_itens_service.py` + `test_os_completo_service.py` +
  `test_os_service.py` + `test_permissoes_service.py`): 120 testes, sem
  regressão.
- **Frontend** — `useOSItens.ts`: `altExecutorModalOpen`/
  `altExecutorSaving`/`salvarAlterarExecutor` (chama a rota nova,
  recarrega os itens e mostra quantos foram propagados no toast).
  Componente novo `AlterarExecutorModal.tsx`
  (`frontend/src/components/os/`) — lista os itens da O.S., cada linha
  com `SelectField` (Vendedor/Executor, mesma lista `funcOptions` já
  usada em `OSItemModal.tsx`) + um `Switch` "Aplicar também aos demais
  itens..." + botão Salvar por linha (desabilitado se nada mudou).
  Botão "Alteração de Executor" em `os-geral.tsx`, mesma linha de Tempo
  Gasto/Requisições Vinculadas/Criar Cópia, gated por
  `can("OS_COMP.ALT_EXECUTOR") && (sit === "F" || sit === "PG")`. Entrada
  nova no Modo Didático. `tsc --noEmit`: sem novos erros (baseline de 12
  pré-existentes inalterado, confirmado 2026-08-02).

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — mesma ressalva de todas as
  sub-features desta sessão de O.S. Completa.
- **Recálculo de comissão** — ver "Efeito colateral de comissão do
  legado NÃO foi portado" acima; não há módulo de comissão nesta
  migração ainda.
- **Checagem de permissão dentro do service** — segue o padrão já
  estabelecido no arquivo (permissão fica na camada de rota/frontend).

## Bifurcação de faturamento Garantia×Cliente (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (sem teste ao vivo ainda — validar
antes de considerar realmente concluído).** Migração de `Command2_Click`/
`GeraComanda` (`Revenda\FrmTraOsNew.frm`, linhas ~11101-11290 e
~14637-14818) — itens da O.S. são divididos em 2 blocos por
`os_produto.situacao` (0=Cliente paga vs. 1/2/3=Garantia/Interno/
Contrato), faturados em Comandas SEPARADAS, cada uma com sua própria
forma de pagamento.

### Regras de negócio confirmadas no rastreio

- **2 blocos, 2 Comandas**: bloco "cliente" (situação=0) e bloco
  "garantia" (situação<>0) nunca viram uma Comanda combinada — mesmo
  quando os dois são faturados na mesma ação (`Check3`+`Check5` marcados
  juntos no legado), são 2 chamadas separadas a `GeraComanda` ("C" e "G"),
  2 `comanda`, 2 vínculos em `COMANDA_OS`.
- **Forma de pagamento por bloco**: bloco cliente usa `os.forma_pagamento`
  (já existente); bloco garantia usa a coluna NOVA
  `os.forma_pagamento_garantia` (migração idempotente
  `pedido_common._ensure_os_forma_pagamento_garantia_col`). Faturar o
  bloco garantia sem essa forma definida bloqueia com mensagem clara — o
  legado tem um fallback pra uma forma de pagamento "padrão de garantia"
  configurada a nível de empresa (`forma_pagamento.FORMA_PAG_GARANTIA=1`,
  aplicado automaticamente e regravado em `os.forma_pagamento_garantia`
  na primeira falta) — **não portado**, decisão deliberada (ver "Fora do
  escopo" abaixo): exige que a O.S. tenha sua PRÓPRIA forma de garantia
  definida, sem fallback de empresa.
- **Escolha obrigatória quando os 2 blocos têm valor pendente ao mesmo
  tempo**: réplica funcional da tela bloqueante `Frame5`/`Check3`/`Check5`
  do legado — `_faturar_os_sync` não fatura nada nesse caso, devolve
  `needs_choice=True` + os 2 totais, e só fatura de fato numa chamada
  SEGUINTE com `faturar_bucket` explícito ("cliente"/"garantia"/"ambos").
  Sem ambiguidade (só um bloco com valor pendente), decide sozinha, sem
  pedir escolha — mesmo comportamento dos ramos `ElseIf`/`Else` do legado.
- **Situação vira `PG` mesmo faturando só o bloco garantia** (sem nenhum
  item Cliente paga pendente) — réplica exata do ramo "só garantia" do
  legado, que também marca `PG` nesse caso.
- **Re-faturamento pós-`PG`**: uma O.S. já Faturada pode voltar a
  `_faturar_os_sync` pra faturar itens de Garantia/Interno/Contrato
  incluídos DEPOIS do primeiro faturamento (`os_produto.faturado=0`
  ainda) — o bloco cliente nunca é reconsultado nesse caso (já resolvido
  no primeiro faturamento; o legado também nunca reabre esse bloco). Sem
  itens de garantia pendentes, volta a bloquear com "OS já faturada."
  (mesma mensagem/comportamento de antes desta feature).
- **`os_produto.faturado=1` só é marcado nos itens do bloco garantia** —
  o bloco cliente não precisa dessa marcação porque, uma vez faturado, a
  O.S. inteira vira `PG` e esse bloco nunca é reconsultado de novo (coluna
  `faturado` já existia no schema, usada em outro lugar da migração —
  `produtos_niveis_service.py` — confirmando que não era preciso migração
  de coluna nova pra ela).
- **Sempre fatura pro `os.cliente`, nunca pro `cliente_garantia`** — o
  legado fatura o bloco garantia pro `os.cliente_garantia` quando
  preenchido (campo pra faturar num CNPJ de seguradora/garantidor
  diferente do cliente da O.S.); esse campo nunca foi modelado em NENHUM
  outro lugar desta migração (mesma decisão já tomada em "Criar Cópia" >
  "Colunas do cabeçalho copiadas") — replicá-lo só aqui, isolado, criaria
  um conceito sem nenhuma tela pra gerenciá-lo. Ver "Fora do escopo"
  abaixo.

### O que foi implementado

- **Backend** — `FaturarOSRequest` (`backend/models/schemas.py`, estende
  `FecharRequest` com `faturar_bucket: Optional[str]`).
  `os_service._faturar_bucket_os` (helper novo — fatura UM bloco, réplica
  de `GeraComanda`) + `_faturar_os_sync` reescrita por completo: calcula
  os 2 totais (`SUM(quant*p_venda)` agrupado por `situacao=0` vs.
  `situacao<>0 AND faturado=0`), decide o bloco automaticamente quando não
  há ambiguidade, devolve `needs_choice` quando há, valida forma de
  pagamento de garantia antes de faturar esse bloco, e trata o
  re-faturamento pós-`PG` como um ramo separado (só bloco garantia).
  `os_completo_service`: `forma_pagamento_garantia`/
  `forma_pagamento_garantia_descricao` (JOIN `forma_pagamento`) expostos
  em `_get_os_completo_sync`, gravados em `_save_os_completo_sync`
  (INSERT/UPDATE) via `OSCompletoSaveRequest.forma_pagamento_garantia`.
  Rotas `POST /api/os/{codigo}/faturar` e
  `POST /api/os-completo/{codigo}/faturar` migradas pra `FaturarOSRequest`
  (compatível com chamadas antigas — campo novo é opcional); descrição do
  log de auditoria agora menciona as 2 comandas quando aplicável
  (`_descricao_faturamento`, helper novo em cada arquivo de rota). 19
  testes em `test_os_service.py` (8 atualizados em `TestFaturarOS` + 11
  novos em `TestFaturarOSBifurcacaoGarantia`) + 2 asserts novos em
  `test_os_completo_service.py` (campo exposto/gravado). Suíte focada
  (`test_os_service.py` + `test_os_completo_service.py` +
  `test_os_itens_service.py` + `test_permissoes_service.py` +
  `test_pedido_common_doc_origem.py` + `test_agenda_service.py`): 216
  testes, sem regressão.
- **Frontend** — `os-geral.tsx`: campo novo "Forma de Pag. Garantia"
  (`SelectField compactWeb`, mesma lista `formaPagOptions` já usada pela
  Forma de Pagamento normal) ao lado do campo Forma de Pagamento, gravado
  junto no Gravar normal do cabeçalho (não é um combobox de grava-ao-
  trocar como `forma_pagamento` — é só mais um campo do formulário).
  `handleFaturar` ganhou parâmetro opcional `bucket`; ao receber
  `needs_choice` da API, abre `FaturarBucketModal.tsx` (componente novo,
  `frontend/src/components/os/`) — 3 botões (Só Cliente / Só Garantia /
  Faturar os Dois) com os 2 totais, tier de modal "confirmação"
  (`modalCardWebCompactNarrow`); escolher um bloco chama `handleFaturar`
  de novo já com `faturar_bucket` definido. Entrada nova no Modo
  Didático. `tsc --noEmit`: sem novos erros (baseline de 12
  pré-existentes inalterado, confirmado 2026-08-02).

### Fora do escopo desta rodada

- **Teste ao vivo contra KONTACTO TESTE** — mesma ressalva de todas as
  sub-features desta sessão de O.S. Completa.
- **`cliente_garantia`** (faturar o bloco garantia pra um cliente
  diferente do cliente da O.S.) — não modelado, ver "Regras de negócio
  confirmadas" acima.
- **Forma de pagamento de garantia "padrão de empresa"**
  (`forma_pagamento.FORMA_PAG_GARANTIA=1`, fallback automático do
  legado) — não implementado; cada O.S. precisa da sua própria
  `forma_pagamento_garantia` definida. Se pedido no futuro, adicionar uma
  coluna bit na tabela auxiliar `forma_pagamento` (tela
  `forma-pagamento.tsx`) + o fallback em `_faturar_os_sync`.
- **Detalhamento de forma de pagamento por parcela** (`comanda_dinheiro`/
  `comanda_duplicata`/`comanda_cheque`/etc., `GeraComanda`'s lógica de
  prazo/percentual) — nem o bloco cliente nem o bloco garantia fazem esse
  detalhamento nesta migração; mesma simplificação já usada em
  `_faturar_pedido_sync`/o `_faturar_os_sync` original (a Comanda grava um
  valor único, sem splitting por forma/prazo).
- **PAGA_COMISSAO / ITEM_COMISSAO_VENDEDOR / atendente_dav** (campos de
  comissão do legado, também presentes em `GeraComanda`) — mesma decisão
  já tomada em "Alteração de Executor pós-fechamento" acima: esta
  migração não tem módulo de comissão implementado ainda.
- **Pesquisa de satisfação** (`Pesquisa_Satisfacao_BTEN`) — não modelada
  em nenhum outro lugar desta migração, fora de escopo.

## Oficina — Fase 2 (O.S. Completa)

**Status: 🟢 Implementado 2026-08-02 (só frontend — sem teste ao vivo
ainda, ver ressalva abaixo).** Fase 1 da O.S. Completa (`os-geral.tsx`)
tinha os campos placa/marca/modelo/km/ano/chassi como state gravado, mas
SEM nenhuma UI pra editá-los — o bloco "Veículo/Equipamento" da tela
sempre forçava o fluxo de busca real do módulo Assistência
(`EquipamentoSearchModal`), que não faz sentido pra um veículo de Oficina
(carro não é uma entidade "Cadastro de Equipamentos" com número de série
buscável). Esta rodada só precisou de FRONTEND — o backend
(`OSSaveRequest`/`OSCompletoSaveRequest`, `_save_os_completo_sync`) já
aceitava e gravava todos os 6 campos desde a Fase 1, confirmado ao ler o
código antes de começar.

### Referência usada: `os-form.tsx` (O.S. Mobile) já tinha isso pronto

A O.S. Mobile já implementa a Oficina completa desde antes desta rodada —
bottom sheet "Veículo/Equipamento" com Placa (texto livre), KM (texto
livre), Marca (`SelectField` alimentado por `GET /api/tabelas/marcas
?marca_produto=false`), Modelo (`SelectField` alimentado por
`GET /api/tabelas/modelos?cod_marca=X`, desabilitado até escolher a
Marca), Ano (texto livre) e Chassi/Nº de Série (um único campo, rotulado
"Chassi" ou "Nº de Série" conforme o módulo — `os.chassi` e
`os.numero_de_serie` são colunas separadas, só uma é usada por vez). Esta
implementação não trouxe nenhum conceito novo — só portou esse mesmo
padrão (campos + tabelas auxiliares Marcas/Modelos) pra dentro da tela
web "Completa", nas mesmas 6 colunas de `os` que a Mobile já usa.

### O que foi implementado

- **`frontend/app/os-geral.tsx`**: bloco "Veículo" novo, renderizado
  quando `isOficina && !isAssist` (mesma condição que já decidia
  `equipLabel`/o mapeamento de `chassi` vs. `numero_de_serie` no payload
  de Gravar — não foi inventada agora, só reaproveitada pra decidir
  também QUAL bloco de UI aparece). Layout em 3 linhas de 2 colunas
  (Placa+KM, Marca+Modelo, Ano+Chassi), mesmos campos/ordem da O.S.
  Mobile, usando os componentes padrão da tela web (`Field`,
  `SelectField compactWeb`, `styles.input`) em vez do bottom sheet mobile
  — cabe direto no card da tela, sem precisar de modal (a Completa já é
  uma tela cheia com espaço de sobra, diferente da Mobile que precisa
  economizar espaço vertical).
  - Quando `isAssist` (Assistência, com ou sem Oficina junto) continua
    exatamente como estava — o bloco "Equipamento" com busca real
    (`EquipamentoSearchModal`), sem nenhuma mudança de comportamento.
  - Marcas carregadas no boot da tela (`GET /api/tabelas/marcas
    ?marca_produto=false`, mesmo endpoint/parâmetro da Mobile) junto com
    área de atuação/funcionários/forma de pagamento/status/tipo O.S., que
    já eram carregados ali. Modelos carregados reativamente
    (`useEffect` disparado por mudança em `marca`, mesmo padrão exato de
    `os-form.tsx`) — zero endpoint novo precisou ser criado, os dois já
    existiam (`tabelas_aux_service.py`, usados por outras telas de
    cadastro auxiliar).
  - Entrada do Modo Didático ("Equipamento" → "Equipamento / Veículo")
    atualizada pra explicar os dois módulos, já que o mesmo texto único
    de antes só descrevia o fluxo de busca (Assistência).
- **Nenhuma mudança de backend** — `OSSaveRequest`/`OSCompletoSaveRequest`
  já tinham `placa`/`marca`/`modelo`/`km`/`ano`/`chassi` desde a Fase 1;
  `_save_os_completo_sync` já grava os 6 campos (inclusive truncando
  `marca`/`modelo` pra 3 caracteres — são códigos de FK pras tabelas
  auxiliares, não texto livre, confirmado batendo com o que a Mobile já
  grava). `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
  inalterado, confirmado 2026-08-02).

### Fora do escopo desta rodada

- **Teste ao vivo contra uma empresa com módulo Oficina ligado** — esta
  sessão só teve acesso à conexão KONTACTO TESTE (módulo Assistência); a
  UI de Veículo não foi exercitada contra dados reais ainda. Validar
  antes de considerar realmente concluído.
- **Recibo (`ReciboOSModal.tsx`) não imprime dados de
  Equipamento/Veículo** — gap pré-existente da Fase 1, não introduzido
  nem corrigido nesta rodada (o recibo já não mostrava o equipamento da
  Assistência antes disso também — não é uma regressão específica de
  Oficina).
- **`os-lista.tsx`** — tela de listagem não tem nenhuma coluna/ícone
  específico de módulo, não precisou de mudança.

---

## Gestor de Projetos

**Status: 🟢 Fase 1 (núcleo) implementada 2026-08-02 — sem teste ao vivo
ainda, ver ressalva no final desta seção.** Pedido do usuário:
"rastreie os frm, regra de negócio e análise o ecossistema desse módulo.
verifique se tem um módulo específico para ele em configurações de módulo
ou usa o mesmo da assistência técnica. esse módulo tem ou deveria ter
relacionamento com produtos, serviços, prevendas e etc" — seguido de
"Gestor de Projetos vai ficar em Transações. fase 4 - Recursos extras
sugeridos que pode ser implementado ao longo das fases 1, 2 e 3.
implementar fase 1". Mencionado antes desta sessão só como item do menu
legado "Transações" (screenshot de referência de escopo futuro, ver seção
"Transações" acima) — nunca tinha sido rastreado de verdade até agora.

**Local confirmado pelo usuário**: mora em **Transações**
(`frontend/app/(tabs)/transacoes.tsx`), mesmo grupo de Pedido Geral/O.S.
Completa/Contratos — não em Cadastros nem em uma aba própria.

### Fonte VB6

- **Form principal**: `Geral\frmgespro.frm` (5005 linhas, Caption "Gestor de
  Projetos", `VB_Name = "FrmGesPro"`). Parte do projeto principal
  `Kontacto\backon.vbp` (mesmo `.vbp` de `FrmTraOsNew.frm`/`frmmanpedfor.frm`
  etc.), Module global compartilhado `mdl_proc.bas`.
  **Cuidado**: existe outro arquivo com nome parecido,
  `Geral\FrmProjetos.frm` ("Consulta Sistemas") — é uma ferramenta interna
  de controle de versão de sistemas (tabela `Sistemas`, banco Access
  próprio `Sistemas.mdb`), sem nenhuma relação com este módulo. Não usar
  como referência se este módulo for retomado.
- **Item de menu**: `Tra_gdp` ("Gestor de Projetos") em `mdirevendanv.frm`/
  `mdi_os_nova.frm`, `Tag = "FrmGesPro"`.
- **Chamado a partir de**: `frmmanreq.frm` (Requisição — o vínculo
  `ExisteDAVProjeto` já registrado como "não implementado" na seção
  "Movimentações" acima é exatamente este módulo), `FrmConPed.frm`,
  `frmconosa.frm`, `frmconorc.frm`, `FrmConCli2.frm` (o seletor de cliente
  F2 que a seção "Contatos" registrou como "nunca fornecido" — **na
  verdade existe e está em `Geral\FrmConCli2.frm`**, só não tinha sido
  localizado ainda; revisitar aquela pendência se o Gestor de Projetos ou
  outra tela que o referencie for retomado).

### Módulo de configuração: **dedicado, não reaproveita Assistência**

- Coluna própria `controle_configuracao.gestor_projetos` (BIT), confirmada
  no dump de schema (`Atualiza\estrutura_sem_cep.sql`) e na propriedade
  `Dados_Controle_Configuracao.Gestor_Projetos` (`mdl_proc.bas`) —
  totalmente separada de `Assistencia`/`Oficina`/`TSO`/`Clinica`/etc.
- **Bug real encontrado no legado, não replicar**: a linha que esconderia
  o item de menu quando o flag está desligado está COMENTADA em
  `mdl_proc.bas` (`If Not Dados_Controle_Configuracao.Gestor_Projetos Then
  ' MdiPrincipal.Tra_gdp.Visible = False End If`) — ou seja, hoje o menu
  aparece sempre, independente do flag. Se portado, o gating deve
  funcionar de verdade (mesmo padrão `moduleOn("gestor_projetos")` já
  usado nos outros módulos), não replicar esse bug.

### Ecossistema — relacionamento real com Produtos, Serviços, Pedido, O.S., Orçamento e Requisição

Este é o núcleo do módulo, não um relacionamento incidental:

- **Schema**: `Projetos` (codigo PK, data_abertura/data_inicio/
  data_prevista/data_termino, cliente FK, situacao 'A'/'F'/'C' — sem
  estado "faturado" no próprio projeto, isso vive por documento —,
  valor_projeto/valor_produtos/valor_servicos, responsavel FK
  funcionário, detalhes, logs). `projetos_documentos` (codauto PK,
  projeto FK, tipo_doc — `'PED'`/`'ORC'`/`'OSS'`/`'REQ'` —, num_doc,
  data_inclusao, incluido_por) — tabela de VÍNCULO N:1 entre documentos
  já existentes e um projeto. `itens_temp_projetos` — tabela de STAGING
  usada só durante a tela aberta (é limpa e repopulada a cada operação),
  não é histórico persistente.
- **Um documento só pode pertencer a UM projeto no sistema inteiro** — o
  legado bloqueia explicitamente ao tentar adicionar um Pedido/O.S./
  Orçamento/Requisição já vinculado a outro projeto, avisando qual
  projeto e de qual cliente.
- **Agregação automática de itens**: a tela une (`UNION ALL`)
  `pedido_venda_prod` + `orc_produto` + `os_produto` + `rec_prod` de TODOS
  os documentos vinculados ao projeto (join via `projetos_documentos`),
  separando Produtos de Serviços (join com `pecas`/`servicos`), com
  totais de custo/venda/margem — geral, por documento, e por
  produto/serviço condensado.
- **Rastro fiscal por documento vinculado**: a grade de documentos mostra
  Comanda/ECF/NFCe/NFe/NFSe de cada Pedido/O.S. vinculado (só leitura,
  reflete o que os módulos de faturamento já geraram — o Gestor de
  Projetos não emite nada).
- **"Ajustar Valores" — rebalanceamento de valor em massa através de
  VÁRIOS documentos ao mesmo tempo**: define um novo total-alvo pra
  Produtos ou Serviços do projeto; um algoritmo de rateio proporcional
  (mesma família conceitual do rateio já implementado em Contratos, mas
  aplicado através de N documentos diferentes, não um só) distribui
  desconto/acréscimo item a item, em até 3 passadas (percentual →
  fechamento sem estourar o alvo → ajuste final de R$0,01 por item pra
  fechar o centavo), até bater exatamente o valor pedido. Reescreve
  `p_venda`/`desconto`/`acrescimo`/`ajustar` de cada item
  (`orc_produto`/`os_produto`/`pedido_venda_prod`) e o total do
  cabeçalho de Orçamento/Pedido.
  - **Inconsistência real observada no legado**: esse recálculo atualiza
    o total do cabeçalho de `orcamento`/`pedido_venda`, mas **não** de
    `os` — parece lacuna do legado, não decisão consciente. Confirmar
    antes de replicar (provavelmente deveria recalcular os 3).
  - Requisição entra na agregação/totais de itens, mas **não** entra no
    motor de Ajustar Valores (não tem preço de venda ao cliente).
- **Distinção Produto×Serviço via prefixo de código** (`Left(codigo,1) =
  'S'`), não via consulta às tabelas `pecas`/`servicos` — esta migração já
  tem um jeito mais seguro e já estabelecido (`_is_peca`, consulta real
  contra `pecas`), portar usando esse padrão em vez do prefixo textual do
  legado.
- **Anexos via Gestor de Documentos genérico** — `cod_grupo=1` (Cliente),
  sub-grupo resolvido por descrição "Projetos" (find-or-create, mesmo
  padrão exato já usado por outras entidades nesta migração — ver seção
  "Gestor de Documentos (Anexos)" acima), `referencia` = código do
  projeto. Integração direta, sem invenção nova.
- **Log de auditoria embutido no próprio registro** (`projetos.logs`,
  texto único acumulando entradas "data - hora - texto - usuário",
  reescrito por completo a cada evento) — padrão pré-`log_auditoria`
  desta migração; portar usando a tabela `log_auditoria` já existente em
  vez de replicar o campo texto único.
- **Permissões são muito granulares no legado**: botões (e permissões)
  próprios pra Adicionar O.S., Adicionar Pedido, Adicionar Orçamento,
  Adicionar Requisição, Remover Documento do Projeto, Ajustar Valores,
  Visualizar Custos do Projeto (esconde colunas de custo/margem de quem
  não tem essa permissão — separado da permissão geral de acesso à tela),
  Logs do Projeto, Finalizar, Reabrir — não é só ABRIR/GRAVAR.

### Bloqueios de escopo — resolvido

- ~~**Orçamento não existe nesta migração**~~ — **resolvido 2026-08-02**,
  ver CLAUDE.md > "Regras Globais de Pré-venda" `[GLOBAL]`: "todo pedido
  aberto é um orçamento". `tipo_doc='ORC'` do legado mapeia pra Pedido de
  Venda com `situacao='A'` — não precisa de tabela/tela nova de Orçamento.
  Isso significa que o vínculo com "Orçamento" do Gestor de Projetos, na
  prática, é só mais um filtro sobre `pedido_venda` (situação Aberto),
  não um 4º tipo de documento de verdade — ver plano de fases abaixo.
- Duas telas de O.S. mais antigas referenciadas no `Documentos2_DblClick`
  do legado (`FrmTraOs`/`FrmTraOsA`/`FrmOStso`, dependendo dos flags
  Oficina/TSO) parecem ser gerações anteriores à `FrmTraOsNew.frm` (a
  fonte já usada como canônica pra O.S. Completa nesta migração) — ao
  portar o duplo-clique num documento O.S. vinculado, abrir a tela
  `os-geral.tsx` já existente, não tentar replicar essa bifurcação
  antiga de formulários.

### Plano de fases

Com a regra "todo pedido aberto é um orçamento" (ver CLAUDE.md), o
vínculo simplifica pra **3 tipos reais de documento**: PED (Pedido de
Venda, em qualquer situação — inclusive Aberto, cumprindo o papel de
orçamento), OSS (O.S.), REQ (Requisição) — sem tabela/tipo "ORC" próprio.

- ~~**Fase 1 — Núcleo**~~ — **implementado 2026-08-02**, ver "O que foi
  implementado (Fase 1)" logo abaixo.
- ~~**Fase 2 — Ajustar Valores**~~ — **implementado 2026-08-02**, ver "O
  que foi implementado (Fase 2)" logo abaixo.
- ~~**Fase 3 — Custos, Impressão e Logs**~~ — **implementado 2026-08-02**,
  ver "O que foi implementado (Fase 3)" logo abaixo.
- **Fase 4 — Recursos extras** (lista abaixo): **user-directed 2026-08-02
  — não é uma fase isolada no fim, os itens dela podem (e devem) ser
  encaixados ao longo da implementação das Fases 1/2/3** quando fizer
  sentido pro trecho sendo tocado, em vez de esperar as 3 primeiras
  fases terminarem por completo.

### O que foi implementado (Fase 1)

- **Backend**:
  - `backend/services/projetos_service.py` (novo) — `_ensure_projetos_tables`
    (migração idempotente de `projetos`/`projetos_documentos`, mesmas
    colunas do schema legado confirmado no dump), list/get/save de
    Projeto, `_documentos_vinculados_sync` (UNION Pedido/O.S./Requisição
    com situação e total sempre resolvidos AO VIVO da tabela dona, nunca
    de coluna cacheada), `_itens_agregados_sync` (agregação Produtos/
    Serviços ao vivo, sem a tabela de staging do legado — distingue
    peça×serviço via JOIN real com `pecas`/`servicos`, não pelo prefixo
    de código do legado), `_faturado_saldo` (soma dos documentos
    vinculados já `PG` vs. o resto), transições de situação (Finalizar/
    Reabrir/Cancelar, helper único `_transicao_situacao_sync`), vincular/
    desvincular documento (bloqueia documento já vinculado a outro
    projeto, valida existência do documento na tabela de origem antes de
    vincular).
  - `backend/routes/projetos.py` (novo, registrado em `server.py`) — log
    de auditoria (`tela="PROJETOS"`) em toda escrita.
  - `backend/models/schemas.py` — `ProjetosListRequest`/
    `ProjetoSaveRequest`/`ProjetoDocumentoRequest` novos; `data_abertura`
    e `data_termino` (Finalizado em) NÃO são editáveis pelo cliente —
    gravadas pelo backend via `GETDATE()`, mesmo padrão já usado em toda
    a migração (nunca confiar num campo de data de abertura/fechamento
    editável).
  - `backend/services/pedido_common.py` — `_modulo_gestor_projetos_ativo`
    (mesmo padrão de `_modulo_contratos_ativo`).
  - `backend/services/permissoes_service.py` — tela `PROJETOS` nova
    dentro do menu `TRANSACOES`, ações ABRIR/GRAVAR/ADD_PEDIDO/ADD_OS/
    ADD_REQUISICAO/REMOVER_DOC/SITUACAO/VER_CUSTOS/ANEXOS (SITUACAO cobre
    Finalizar/Reabrir/Cancelar juntos, mesmo padrão de uma permissão só
    pra todas as transições já usado em O.S.).
  - `backend/services/controle_config_service.py` — `MODULE_TELAS`
    ganhou `"gestor_projetos": ["PROJETOS"]` (desabilita a tela quando o
    módulo está desligado, tanto pra grupo quanto — diferente do bug do
    legado — de verdade).
  - 32 testes novos em `test_projetos_service.py`. Suíte focada
    (`test_projetos_service.py` + `test_permissoes_service.py` +
    `test_pedidos_service.py` + `test_os_service.py`): 155 testes, sem
    regressão.
- **Frontend**:
  - `frontend/app/projetos.tsx` (novo) — lista (mesmo padrão de
    `os-lista.tsx`): busca por cliente + chips Abertos/Finalizados/
    Cancelados/Todos, FAB "Novo" gated por `PROJETOS.GRAVAR`.
  - `frontend/app/projeto-form.tsx` (novo) — tela cheia (Full CRUD Form
    Screen Standard): Cliente via `ClienteSection`/`ClientSearchModal`
    (Campo de Identidade com busca, mesmo padrão global já estabelecido),
    Responsável/Datas/Detalhes; badge de situação + Finalizar/Reabrir/
    Cancelar; card "Documentos Vinculados" com botão "Vincular
    Pedido/O.S./Requisição" por tipo (gated por permissão própria) —
    abre um modal simples de "número do documento → Buscar → preview
    (cliente/situação/total) → Vincular", já que não existe ainda um
    componente de busca-por-nome reutilizável pra Pedido/O.S./Requisição
    (diferente de Cliente/Produto/Fornecedor); remover documento com
    confirmação; card "Itens do Projeto" com totais Produtos/Serviços/
    Geral (+ custo, gated por `PROJETOS.VER_CUSTOS`) e Faturado/Saldo a
    Faturar; Anexos via `GestorDocumentosSection` (grupo Cliente,
    sub-grupo "Projetos" resolvido dinamicamente por
    `POST /api/gestor-documentos/sub-grupos` find-or-create — não
    hardcodado, mesmo padrão já usado pelo sub-grupo "Imagens" de Produto
    Completo, já que não há acesso a um banco real pra confirmar o ID
    numérico como foi feito pro sub-grupo "Pedidos de Venda"). Modo
    Didático (ícone "i" no cabeçalho).
  - `frontend/app/(tabs)/transacoes.tsx` — card "Gestor de Projetos"
    novo, gated por `moduleOn("gestor_projetos") && can("PROJETOS.ABRIR")`.
  - `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
    inalterado, confirmado 2026-08-02).

### O que foi implementado (Fase 2)

Rastreio focado de `Command10_Click`/`Opcoes_Click`/`ResumoAcerto`/
`Reprocessados`/`Itens2`/`RecalculaDAVS`/`Descontos_Acrescimos`/
`Aplica_Desc*`/`Aplica_Acresc*` em `Geral\frmgespro.frm` — resolveu tanto
o mecanismo de "Ajustar Valores" quanto **2 gaps reais da Fase 1**
encontrados no caminho:

- **Gap 1 corrigido**: `Campo(7)/(8)/(9)` ("Valor do Projeto"/"Valor
  Produtos"/"Valor Serviços") são campos de estimativa editáveis que
  fazem parte do `Command14_Click` (Gravar) do legado, mas ficaram de
  fora da Fase 1 (gravados sempre como 0). Adicionados como "Valor
  Estimado (Produtos)"/"Valor Estimado (Serviços)" no card "Dados do
  Projeto" — `valor_projeto` continua sempre calculado no servidor como a
  soma dos dois (nunca aceito direto do cliente), mesmo comportamento do
  `Campo_LostFocus` legado.
- **Gap 2 corrigido / decisão "Situação Cancelado" da Fase 1 CONFIRMADA**:
  `Command10_Click` (Cancelar Projeto) também **desvincula todos os
  documentos** (`DELETE FROM projetos_documentos`) antes de marcar
  `situacao='C'` — a dúvida em aberto da Fase 1 (abaixo) sobre não ter
  achado esse fluxo foi resolvida ao vivo nesta passada: cancelar um
  projeto libera seus Pedidos/O.S./Requisições pra entrar em outro
  projeto no futuro, em vez de ficarem presos a um projeto cancelado.
  `_transicao_situacao_sync` corrigido.

**Simplificações deliberadas em relação ao legado** (documentadas também
no docstring de `projetos_service.py`):

- **Seleção só no nível de DOCUMENTO, não item individual**: o legado tem
  2 níveis de seleção — checkbox "Reprocessar" por documento
  (`Reprocessados`) e checkbox por item dentro do documento (`Itens2`).
  Mas a própria função `Carrega2Itens` do legado **apaga e reconstrói**
  `itens_temp_projetos` (sempre com `reprocessar=1`) toda vez que
  QUALQUER checkbox de documento muda — ou seja, desmarcar um item
  individual em `Itens2` é descartado na próxima troca de seleção de
  documento, não é um estado que sobrevive de forma confiável. Replicar
  esse segundo nível não teria efeito prático real; a migração ficou só
  com seleção por documento (lista de checkboxes na tela).
- **"Valores Já Faturados" usa a mesma definição da Fase 1** (documentos
  com `situacao='PG'`), não o rastreamento de NFe/NFSe por `comanda_nf`
  que o legado usa nesse cálculo específico do Ajustar Valores — esta
  migração não tem esse vínculo fiscal automático por comanda ainda.
- **Correção deliberada (bug real do legado)**: `RecalculaDAVS` recalcula
  o total de `pedido_venda`/`orcamento` mas esquece de recalcular o de
  `os` — a migração recalcula os 2 tipos de documento de forma
  consistente (`_recalc_os_total`, reaproveitado de `os_itens_service.py`).
- Redistribuição sempre reinicia do preço BRUTO (`p_normal`/
  `preco_unitario`) antes de aplicar o novo ajuste — mesmo comportamento
  do legado (cada passada de "Ajustar Valores" é um recálculo do zero,
  nunca empilha em cima de um ajuste anterior).

**Backend**:
- `backend/services/projetos_service.py` — `_itens_detalhados_sync`
  (query única, base compartilhada do preview e da execução — itens de
  Pedido/O.S. vinculados com preço bruto, nunca Requisição, que não tem
  preço de venda ao cliente), `_ajuste_valores_preview_sync` (estimado/
  faturado/pendente/saldo do orçamento + lista de documentos elegíveis
  com total de Produtos/Serviços cada), `_ajustar_valores_sync` (motor:
  calcula a diferença entre o total atual dos itens selecionados e
  `novo_valor`, distribui proporcionalmente como desconto/acréscimo por
  item, com o último item absorvendo a sobra de arredondamento —
  substituto mais simples, mas fiel, do laço `Aplica_Desc_Final`/
  `Aplica_Acresc_Final` de R$0,01 por vez do legado).
- `backend/models/schemas.py` — `ProjetoSaveRequest.valor_produtos/
  valor_servicos`; `ProjetoDocumentoKey`/`ProjetoAjustarValoresRequest`
  novos.
- `backend/routes/projetos.py` — `GET/POST /projetos/{codigo}/ajustar-valores`,
  log de auditoria (`comando="AJUSTAR_VALORES"`) só quando algum item foi
  de fato ajustado.
- `backend/services/permissoes_service.py` — ação `AJUSTAR_VALORES` nova
  na tela `PROJETOS`.
- 16 testes novos em `test_projetos_service.py` (48 no total). Suíte
  completa do arquivo: 48/48 passando.

**Frontend** (`frontend/app/projeto-form.tsx`):
- Card "Dados do Projeto" ganhou "Valor Estimado (Produtos)"/"(Serviços)"/
  "(Total)" (o último somente leitura, calculado no cliente).
- Botão "Ajustar Valores" no card "Itens do Projeto" (gated por
  `situacao === "A" && can("PROJETOS.AJUSTAR_VALORES")`) abre modal:
  abas Produtos/Serviços, resumo Estimado/Já Faturado/Saldo do Orçamento,
  lista de documentos elegíveis com checkbox (todos marcados por padrão),
  total atual da seleção (calculado ao vivo no cliente), campo "Novo
  Valor" (pré-preenchido com o total atual, editável) e botão "Aplicar
  Ajuste". Mensagem de sucesso com `durationMs: 5000` (CLAUDE.md > "Mensagem
  5s p/ info grande" — carrega números que o usuário precisa conferir).
  Modo Didático (`AjudaPedidoModal`) ganhou 2 itens novos: "Valor
  Estimado" e "Ajustar Valores".
- `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
  inalterado, confirmado 2026-08-02).

### O que foi implementado (Fase 3)

**Custos** — a permissão `PROJETOS.VER_CUSTOS` e o gating do total
agregado ("Custo Geral") já existiam desde a Fase 1; o que faltava era um
jeito de ver custo/margem **por item**, não só no agregado. Adicionado:

- Botão "Detalhar itens" no card "Itens do Projeto" (colapsado por
  padrão, sem ScrollView próprio — projetos costumam ter poucos itens)
  expande a lista de Produtos e Serviços um a um: descrição, quantidade,
  preço de venda unitário e total; quando `canVerCustos`, também mostra
  custo unitário e margem (`(venda-custo)/custo × 100`, "—" quando custo
  é 0). Reaproveita os arrays `itens.produtos`/`itens.servicos` que a
  Fase 1 já buscava do backend (`_itens_agregados_sync`) mas nunca
  renderizava — nenhuma chamada nova ao backend.

**Impressão** — reaproveita `printHtml.ts` + `print-report-header.ts`
(mesmo padrão já usado por Gestão de Compras/Ressuprimento, Cotação de
Compra, etc. — ver CLAUDE.md > "Padrão de Impressão de Relatórios"),
nenhum utilitário novo:

- Ícone "Imprimir" no cabeçalho (`editing` apenas — precisa do projeto já
  gravado). Monta um HTML com cabeçalho de empresa (`fetchEmpresaHeader`)
  + "Projeto nº N" como título, Cliente/Responsável/Situação/Datas/
  Detalhes/Valor Estimado, lista de Documentos Vinculados, e as mesmas
  listas de Produtos/Serviços do "Detalhar itens" (com custo/margem
  também gated por `canVerCustos` na impressão) — sem nenhum resumo de
  filtro de tela (não há filtro nesta tela de qualquer forma, é uma tela
  de registro único, não uma lista).

**Logs do Projeto** — em vez de uma tela própria (rejeitada desde o
plano original, ver "Plano de fases"), a tela de auditoria já existente
(`frontend/app/log-auditoria.tsx`) ganhou suporte a deep-link:

- `LogAuditoriaScreen` agora lê `useLocalSearchParams<{tela, referencia}>`
  e repassa pra `LogAuditoriaWebScreen` como `telaInicial`/
  `referenciaInicial`. No mount, depois do catálogo carregar, resolve o
  nó `TELA` correspondente a `telaInicial` (busca recursiva no catálogo
  já carregado) e chama `setFiltroNode`; `referenciaInicial` vira o valor
  inicial do campo "Referência". Um novo state `paramsApplied` (setado
  `true` no fim do bloco de inicialização) faz o `useEffect` de busca
  automática esperar os parâmetros da URL serem aplicados antes de
  disparar a 1ª busca (`[conn, paramsApplied]` em vez de só `[conn]`) —
  sem isso, a busca automática dispararia cedo demais, sem filtro
  nenhum, antes do catálogo (assíncrono) terminar de carregar.
- `projeto-form.tsx` ganhou ícone "Ver Logs" no cabeçalho (`editing &&
  can("LOG_AUDITORIA.ABRIR")`) navegando pra
  `/log-auditoria?tela=PROJETOS&referencia=<codigo>`.
- **Decisão deliberada**: não foi criada uma permissão `PROJETOS.LOGS`
  separada (a lista de permissões granulares do rastreio original menciona
  "Logs do Projeto" como item próprio) — a tela de destino já tem seu
  próprio gate (`LOG_AUDITORIA.ABRIR`), e ligar o botão de entrada a essa
  mesma permissão evita uma permissão redundante que não controlaria
  nenhuma capacidade a mais (quem não tem `LOG_AUDITORIA.ABRIR` já não
  consegue abrir a tela de destino de qualquer forma, com ou sem uma
  permissão `PROJETOS.LOGS` própria). Revisitar se o usuário quiser um
  controle mais fino (ex.: um grupo que pode ver custos do Projeto mas
  não deveria ver o log de auditoria do sistema inteiro).

**Frontend**: só `frontend/app/projeto-form.tsx` e
`frontend/app/log-auditoria.tsx` tocados — nenhuma mudança de backend
nesta fase (nenhum endpoint novo foi necessário; Impressão usa dados já
carregados na tela + `/api/controle/empresa` já existente, Logs reaproveita
`/api/log-auditoria` já existente). `tsc --noEmit`: sem novos erros
(baseline de 12 pré-existentes inalterado, confirmado 2026-08-02). Suíte
`test_projetos_service.py` + `test_permissoes_service.py`: 58/58 passando
(sem regressão, já que não houve mudança de backend).

### Decisões tomadas sem confirmação direta do legado (revisitar se necessário)

- ~~**Situação Cancelado**: não encontrei no rastreio o botão/fluxo exato
  que leva um Projeto a `situacao='C'` no legado~~ — **confirmado na
  passada de rastreio da Fase 2**: é `Command10_Click`, e além de marcar
  `situacao='C'` também desvincula todos os documentos — ver "O que foi
  implementado (Fase 2)" acima. Implementação já estava correta quanto ao
  "Cancelar só a partir de Aberto, com confirmação, permissão
  `SITUACAO`"; só faltava o desvínculo, já corrigido.
- **Modal "Vincular Documento" por número + Buscar**: não é o padrão
  "Campo de Identidade com busca" completo (CLAUDE.md) — é mais simples
  (busca por número exato, não por nome/busca textual), porque vincular
  um documento a um Projeto pressupõe que o usuário já sabe qual
  Pedido/O.S./Requisição quer vincular (não é uma escolha entre vários
  candidatos como Cliente/Produto). Se o usuário achar isso limitado na
  prática, considerar construir um `PedidoSearchModal`/`OSSearchModal`/
  `RequisicaoSearchModal` reutilizáveis (mesmo padrão de
  `FornecedorSearchModal`/`ProdutoSearchModal`).

### Fase 4 — Recursos extras sugeridos (além do legado)

**Implementado 2026-08-02** — os 5 itens, incluindo o que estava
reservado (confirmado via `AskUserQuestion` direto ao usuário nesta
sessão, mesmo critério já usado antes pro card de Alertas de Estoque):

- ~~**Card "Projetos" na Tela Principal**~~ — implementado após
  confirmação explícita. Novo componente
  `frontend/src/components/principal/ProjetosResumoCard.tsx` (mesmo
  padrão visual — chip 160px web, borda esquerda colorida — do
  `EstoqueAlertasCard.tsx`, mas **sem** a complexidade de cache
  compartilhado/botão "Atualizar" daquele: a consulta aqui é barata (2
  agregados sobre `projetos`/`projetos_documentos`+`pedido_venda`+`os`,
  não uma varredura de Curva ABC por todo o catálogo de produtos), então
  recarrega junto com o resto do dashboard a cada visita, sem precisar do
  mecanismo de "só 1x por sessão" que o card de estoque usa
  especificamente pra evitar repetir aquele cálculo caro. Gating:
  `isManagerFuncao` (mesmo critério) + `moduleOn("gestor_projetos")` +
  `can("PROJETOS.ABRIR")` (permissão reaproveitada, nenhuma nova). Toque
  no card navega pra `/projetos?situacao=A`. Mostrado em mobile também
  (mesmo precedente do card de Estoque — que já navega pra uma tela
  web-only, `gestao-compras-ressuprimento.tsx` — mesmo "papercut" aceito
  de tocar num card gerencial no mobile e cair num `LockedView` se a tela
  de destino for web-only; "informação gerencial" é escopo mobile
  permitido mesmo quando a tela de detalhe não é).
  - Backend: `_resumo_projetos_sync`/`resumo_projetos` em
    `projetos_service.py`, rota `GET /api/projetos-resumo`
    (`servidor`+`banco` apenas — sem paginação/filtro, é um agregado
    único). `ativo=false` (sem consultar mais nada) quando o módulo
    `gestor_projetos` está desligado — mesmo padrão de curto-circuito já
    usado nos outros gates de módulo. 2 testes novos
    (`TestResumoProjetos`).
- ~~**"Projeto parado"**~~ — implementado em `frontend/app/projetos.tsx`
  (`isProjetoParado`): projeto Aberto é destacado (borda + texto em
  vermelho, mesma cor `colors.error` já usada em outros destaques do
  sistema) quando `data_prevista` já venceu, OU quando não recebe um
  novo documento vinculado há mais de **15 dias** (limiar próprio —
  deliberadamente mais longo que o 1 dia do Painel de Pedidos, já que
  Projeto é uma entidade de ciclo de vida mais longo). Precisou de um
  campo novo na listagem, `ultimo_vinculo`
  (`MAX(projetos_documentos.data_inclusao)` por projeto, subquery
  adicionada em `_list_projetos_sync`) — sem documento vinculado ainda,
  cai para `data_abertura` como referência.
- ~~**Vínculo visível no próprio Pedido/O.S.**~~ — implementado: novo
  endpoint `GET /api/projetos-vinculo?tipo_doc=&num_doc=` (busca reversa
  documento→projeto, `_find_vinculo_sync`) chamado por
  `pedido-geral.tsx`/`os-geral.tsx` ao carregar um documento já gravado;
  quando encontra vínculo, `PedidoHeader.tsx` (novo prop
  `vinculoProjeto`) mostra um chip "Projeto #N" no cabeçalho, tocável,
  navegando pra `/projeto-form?codigo=N`. Falha da busca é silenciosa
  (chip é só um atalho de descoberta, não pode travar a tela).
- ~~**Filtro "Projeto" nos relatórios já existentes**~~ — implementado no
  **Relatório de Pedidos** (`useRelatorioPedidos.ts`/`Filtros.tsx`, campo
  numérico "Projeto (nº, opcional)") e no **Relatório de Margem/
  Descontos** (`relatorio-descontos.tsx`, campo "Projeto (nº, opcional —
  só filtra Pedidos)"). Backend: `_relatorio_pedidos_sync`/
  `_relatorio_desc_margem_sync` ganharam parâmetro `projeto` opcional —
  restringe via `pv.pedido IN (SELECT num_doc FROM projetos_documentos
  WHERE projeto=%s AND tipo_doc='PED')`, mesmo padrão de subquery já
  usado noutros filtros do sistema. **Limitação deliberada**: o filtro
  só cobre a origem Pedido — a tela de Descontos & Margem também mistura
  O.S. (`_relatorio_os_desc_margem_sync`, endpoint `/relatorios/os/
  descontos-margem`), que não foi tocado nesta rodada (fora do escopo
  explicitamente pedido: "Relatório de Pedidos, Relatório de Margem/
  Descontos" são 2 telas, não 3) — quando a origem "OS" ou "Todos" está
  selecionada, o filtro de Projeto só afeta as linhas de Pedido, as de
  O.S. continuam sem filtro. Documentado no comentário do código e no
  próprio rótulo do campo na tela.
  - **Decisão de UX**: o campo "Projeto" é um `TextInput` numérico
    simples (mesmo padrão do campo "Código (Pedido/OS)" já existente
    nessas telas), não um modal de busca por nome — mesma lógica já usada
    pra "Modal 'Vincular Documento' por número" do próprio Gestor de
    Projetos (ver "Decisões tomadas sem confirmação direta do legado"
    abaixo): filtrar por Projeto pressupõe que o usuário já sabe o
    número, não é uma escolha entre vários candidatos.
- ~~**Exportar Excel**~~ — implementado em `projeto-form.tsx`, ícone
  "Exportar Excel" no cabeçalho (`editing` apenas), reaproveita
  `exportSheetsToXlsx` (mesmo utilitário do Borderô de Cilindros — nada
  novo criado). Gera `projeto-<codigo>.xlsx` com 3 abas: "Documentos"
  (tipo/número/data/situação/total), "Produtos" e "Serviços" (código/
  descrição/qtd/preço de venda/total — custo/margem também nas 2 últimas
  colunas, só quando `canVerCustos`).

**Backend tocado**: `projetos_service.py` (`_find_vinculo_sync` +
wrapper `find_vinculo`, `ultimo_vinculo` em `_list_projetos_sync`,
`_resumo_projetos_sync`/`resumo_projetos`), `routes/projetos.py` (`GET
/projetos-vinculo`, `GET /projetos-resumo`), `relatorios_service.py`
(parâmetro `projeto` em `_relatorio_pedidos_sync`/
`_relatorio_desc_margem_sync` + wrappers), `routes/relatorios.py` (mesmo
parâmetro nas 2 rotas). 2 endpoints novos (`/projetos-vinculo`,
`/projetos-resumo`) — os outros 3 recursos reaproveitaram endpoints/
parâmetros incrementais em cima do que já existia. 14 testes novos:
`TestFindVinculo` (3) + `TestResumoProjetos` (2) +
`test_expoe_ultimo_vinculo_para_projeto_parado` (1) em
`test_projetos_service.py`, `test_relatorios_projeto_filter.py` (novo
arquivo, 4 testes) — suíte focada
(`test_projetos_service.py`+`test_relatorios_projeto_filter.py`+
`test_relatorios_dashboard.py`+`test_permissoes_service.py`): 76/76
passando. `tsc --noEmit`: sem novos erros (baseline de 12 pré-existentes
inalterado, confirmado 2026-08-02).

### Teste ao vivo — ainda não feito

As Fases 1, 2, 3 e 4 (backend + frontend) só foram validadas via testes
unitários e `tsc --noEmit` nesta sessão — **nenhuma chamada real contra
uma conexão KONTACTO TESTE (ou outra) foi feita**, nem o fluxo completo
foi exercitado num navegador. Antes de considerar o módulo realmente
concluído: criar um Projeto de teste, vincular um Pedido/O.S./Requisição
reais, conferir a agregação de itens/Faturado/Saldo, testar
Finalizar/Reabrir/Cancelar (inclusive que Cancelar realmente desvincula
os documentos), gravar os valores estimados de Produtos/Serviços, rodar
"Ajustar Valores" de ponta a ponta contra um Pedido e uma O.S. reais
(conferir que o desconto/acréscimo gravado bate com o valor-alvo e que o
total do documento é recalculado corretamente), confirmar que o módulo
`gestor_projetos` liga/desliga a tela corretamente em Configurações >
Módulos e Recursos, testar "Detalhar itens" com e sem
`PROJETOS.VER_CUSTOS` concedida, imprimir um Projeto de verdade (conferir
que o cabeçalho de empresa vem certo e que a impressão térmica/monospace
de `printHtml.ts` fica legível para um conteúdo mais denso como este, já
que esse utilitário foi pensado originalmente para cupom/comanda, não
para um relatório de página inteira), e clicar em "Ver Logs" pra
confirmar que o Log de Auditoria abre já filtrado pela tela PROJETOS e
pelo número do projeto certo. Da Fase 4: abrir um Pedido/O.S. já
vinculado a um Projeto e conferir que o chip "Projeto #N" aparece e
navega certo; deixar um Projeto Aberto sem vínculo novo por mais de 15
dias (ou com "Prev. Término" vencida) e conferir o destaque vermelho em
`projetos.tsx`; filtrar o Relatório de Pedidos e o de Descontos & Margem
por um número de Projeto real e conferir que só os Pedidos vinculados
aparecem; exportar o Excel de um Projeto com documentos/itens reais e
abrir o `.xlsx` gerado pra conferir as 3 abas; conferir que o card
"Projetos" aparece na Tela Principal só pra usuário Gerente/Supervisor/
Master com o módulo ligado, que o total de Abertos e o saldo a faturar
batem com a lista real, e que some quando não há permissão/módulo
desligado.

---

## Assistência Técnica — Atendimento de Campo

**Status: 🟡 Fundação (13/08) + Tela de Atendimento/check-in-check-out
(14/08) + Lista de Atendimento/Auxiliar/exibição de check-in-check-out
(14/08, mesma sessão) implementadas e TESTADAS AO VIVO** — múltiplos
equipamentos por OS + Motor de Layout na O.S. Completa (13/08); check-
in/check-out por geolocalização + leitura de QR Code + tela mobile enxuta
`os-atendimento.tsx` (14/08); em seguida, mesma sessão: check-in/check-out
agora exibidos na O.S. Completa (card + link "Ver no mapa"), campo opcional
"Auxiliar do técnico" (`os.auxiliar_tecnico`), e `os-lista.tsx` virou
também a "Lista de Atendimento" — funciona no mobile agora (não mais
web-only), toque na linha abre O.S. Completa ou Atendimento conforme a
plataforma, filtros de Técnico/Auxiliar, nova permissão
`OS_COMP.VER_TODAS` restringindo visibilidade por padrão a "só minhas OS
(técnico/auxiliar)", cards responsivos com pills, filtros em acordeon, e
modal de histórico de equipamento por linha. Ver `AssistenciaTecnicaCampo.md`
seções 6 e 7 pro detalhe técnico completo. O que falta — **Lista de
Atendimento por data/calendário** (a variante original do documento,
substituída por essa extensão do `os-lista.tsx` genérico — se o usuário
quiser a visão por calendário específica, é trabalho novo), sincronização
offline, fluxo completo de auxiliar (editar com credencial do titular) —
segue EM ANÁLISE, não implementar sem liberação explícita. **Teste real
de câmera/GPS em dispositivo físico ainda não feito** (só backend 100%
verificado via curl contra ARGEN-TESTE + frontend confirmado por
`tsc`/bundle limpo). Ver `AssistenciaTecnicaCampo.md` (raiz do repo) pro
documento completo de regras de negócio, e memória
`project_assistencia_tecnica_campo` pro resumo. Cliente motivador: ARGEN
Ar Condicionado (conexão de teste dedicada `ARGEN TESTE`, ver
`reference_conexoes_teste`).

### Decisões de negócio fechadas em 2026-08-13, user-directed

- **Transições de situação no mobile**: só **Fechar** liberado pro técnico
  em campo (ao concluir o atendimento). Cancelar/Faturar/Reabrir continuam
  exclusivos da retaguarda (O.S. Completa web, `OS_COMP.SITUACAO`) — ainda
  não implementado no app mobile (o app de campo em si não existe ainda,
  só a fundação de backend/O.S. Completa abaixo).
- **Orçamento recusado/sem resposta**: OS fica aguardando manualmente, sem
  prazo automático — supervisor cancela na mão quando decidir
  (`status_os` de aguardando aprovação já existe no cadastro, ver abaixo).
  Nenhum job/checagem diária necessário.
- Offline (sync/conflito) e o desenho da "tela de atendimento" mobile
  continuam deliberadamente adiados pra quando a implementação do app
  mobile realmente começar — não são lacuna esquecida.

### O que já estava implementado (achado ao retomar a sessão, não desta rodada)

- **QR Code por equipamento** — `equipamentos_service._gerar_qrcode_sync`
  + `GET /api/equipamentos/{codigo}/qrcode`, impresso a partir do Cadastro
  de Equipamento (`equipamentos.tsx`). Já existia antes desta análise.
- **`status_os`** (tabela auxiliar, cadastro CRUD já existente) já está
  populada em `ARGEN-TESTE` com os valores reais do fluxo de campo
  (confirmado ao vivo): Aguardando aprovação do Orçamento, Aguardando
  Liberação de Execução, Pendente, Em execução, Executado, Cancelado.

### Fundação implementada e testada ao vivo nesta rodada (2026-08-13)

Migração de "uma OS tem um único equipamento" (`os.numero_de_serie`,
coluna escalar) para "uma OS pode ter vários equipamentos" — ver
`AssistenciaTecnicaCampo.md` seção 5/regra 14. **Tabela nova
`os_equipamento`** (codigo, os, equipamento FK `equipamentos.codigo`,
numero_de_serie, principal, situacao, defeito_reclamado/
servico_executado/servico_a_executar/diagnostico, status_os FK
`status_os.codigo` — nível equipamento, distinto de `os.status_os` nível
OS), migração idempotente + **backfill automático** a partir de
`os.numero_de_serie` (registrada em `schema_ensure.py::_MIGRACOES`,
mesmo mecanismo integral de todas as outras migrações do projeto).
`os.numero_de_serie` não foi removida, vira campo histórico.

- **Backend**: `backend/services/os_equipamento_service.py` (CRUD:
  listar/vincular/atualizar/cancelar — soft, nunca delete físico, mesmo
  padrão de `os_produto`) + rotas em `os_completo.py`
  (`GET/POST /api/os-completo/{codigo}/equipamentos`,
  `PUT .../equipamentos/{item_codigo}`,
  `POST .../equipamentos/{item_codigo}/cancelar`, log de auditoria
  `EQUIP_ADD`/`EQUIP_CANC`). Permissões `OS_COMP.EQUIP_ADD`/
  `OS_COMP.EQUIP_CANC` (vincular/cancelar são ações exclusivas da
  retaguarda, sem equivalente mobile nesta fase). 17 testes unitários em
  `test_os_equipamento_service.py`.
- **Frontend**: `useOSEquipamentos.ts` + `OSEquipamentoCard.tsx`
  (card por equipamento: Status/Defeito Reclamado/Serviço Executado/
  Serviço a Executar/Diagnóstico + Salvar/Cancelar por linha), integrados
  em `os-geral.tsx` — vincular reaproveita `EquipamentoSearchModal` já
  existente (escopado por cliente).
- **Motor de Layout (Formulário Dinâmico) integrado à O.S.** —
  `LayoutPreenchimentoModal` já reaproveitado tal e qual (mesmo componente
  do módulo Agenda), `entidade=O.S.`, `codentidade=osId`, botão no
  cabeçalho (`PedidoHeader.onFormularios`) gated por
  `OS_COMP.FORMULARIOS`. Cobre a regra 15 (checklist do atendimento) —
  preenchimento no nível da OS inteira, como decidido no documento.

### Bug real encontrado e corrigido no teste ao vivo (2026-08-13)

**Fan-out no backfill**: `equipamentos.numero_de_serie` é documentado como
único globalmente, mas nunca foi de fato uma constraint de banco — dado
legado sujo tem duplicatas reais (confirmado ao vivo em `KONTACTO-TESTE`:
15 equipamentos com `numero_de_serie='1'`). O `LEFT JOIN equipamentos e ON
e.numero_de_serie = o.numero_de_serie` original casava com TODOS os
duplicados, multiplicando 1 OS em N linhas de backfill (OS 20494 virou 15
linhas, todas `principal=1`). Corrigido trocando o JOIN por uma subquery
correlacionada que resolve o `MIN(codigo)` entre os duplicados —
determinístico, no máximo 1 equipamento por OS no backfill, sem perder
dado (ainda cria a linha com `equipamento=NULL` se não achar nenhum
match). Teste novo cobrindo o cenário em
`test_os_equipamento_service.py::test_backfill_nao_faz_fan_out_com_numero_de_serie_duplicado`.

### Testado ao vivo (2026-08-13)

Contra `ARGEN-TESTE` (OS #294) e `KONTACTO-TESTE` (OS #20494, verificação
específica do backfill): criação da tabela + backfill, vincular
equipamento (com resolução de nome/marca/modelo via JOIN), bloqueio de
vínculo duplicado, vincular um segundo equipamento na mesma OS, atualizar
campos + status, cancelar (soft, confirmado que não usa `DELETE`),
confirmar que o backfill não corrompe mais com número de série duplicado.
Suíte completa (1822 testes) sem regressão (1 falha pré-existente e não
relacionada em `test_cnab_itau_service.py`, teste com data hardcoded).
`tsc --noEmit`: baseline de 12 erros pré-existentes inalterado, nenhum
erro novo introduzido pelas telas/componentes desta feature.

**Achado operacional, não é bug de código**: durante o teste, o processo
supervisionado do backend (porta 8081, sem `--reload`) foi encontrado com
requisições a banco travadas/represadas (nenhuma chamada tocando o banco
completava, mesmo após 90s). Reiniciado (mesmo procedimento de
`feedback_backend_supervisor_duplicado`) e voltou a responder normalmente
em segundos — causa raiz não investigada a fundo (pode ter sido conexão
travada represada de sessão anterior); se acontecer de novo, considerar
investigar timeout/pool de conexão do lado do `pymssql`.

### Fora do escopo desta rodada (não implementado)

- **Check-in/check-out por geolocalização** (regra 2) — nenhuma tabela/
  endpoint/tela criada ainda.
- **Lista de Atendimento** (tela inicial do app do técnico, regra 6/7/10)
  — não iniciada.
- **Tela de atendimento mobile** (layout completo, regra 1/9) — desenho
  adiado deliberadamente, ver decisões acima.
- **Offline** (regra 4) — adiado deliberadamente, ver decisões acima.
- **Técnico auxiliar** (regra 5/11) — não iniciado.
- **Fechar a OS a partir do mobile** (decisão desta rodada: só Fechar,
  ver acima) — ainda não implementado, não existe app/tela mobile de
  atendimento pra expor essa ação ainda.
- **Cadastro dos valores de `status_os` por equipamento** ("Não
  atendido", etc., ver seção 5 do documento) — o mecanismo (coluna FK)
  está pronto, falta só popular os valores adicionais na tabela auxiliar
  quando o cliente/negócio definir o catálogo completo.

---

## Painel de Relatórios (VB6) — Rastreio Completo por Grupo

**Status: rastreio concluído (2026-08-07), implementação NÃO iniciada.**
Motivado por um screenshot do painel `FrmRelatorios` (menu "Relatórios" do
sistema legado) — usuário pediu pra rastrear todos os relatórios por grupo
antes de expandir a tela `frontend/app/(tabs)/relatorios.tsx` (hoje só 6
cards em 3 grupos: Caixa, Margens, Pré Vendas — ver CLAUDE.md > "Card List
Ordering" > "Relatórios groups" pro padrão de grupos alfabéticos já
adotado nessa tela).

**Fonte**: `C:\Desenv\VB6\SQLSERVER\Geral\FrmRelatorios.frm` (único form
com esse nome na árvore — confirmado via busca, não há variante por linha
de negócio como em outros forms). Form MDIChild com 15 `Frame3(n)`
(grupos), cada um contendo `CommandButton`s cuja propriedade `Tag` é o
nome do form de destino (confirmado cruzando com o `Call
Exibe_Form(FormDestino, "...")` de cada `_Click` handler — em praticamente
todos os casos `Tag` bate exatamente com o form chamado no handler).

### Regras de visibilidade/gating encontradas no `Form_Load`/`SetaCores` (não são bugs — regras reais do legado)

- **Grupo "Combustíveis" (Frame3(10))** só fica visível se
  `Dados_Controle_Configuracao.Posto = True` — mesmo flag de módulo
  Posto já usado neste app (`controle_configuracao.Posto`). Por isso não
  aparece no screenshot colado pelo usuário (empresa sem módulo Posto).
- **Largura do form inteiro** varia com `Dados_Controle_Configuracao.kash`
  (módulo "KA$H", não presente/mapeado ainda nesta migração) — `Width =
  15200` (revela as colunas mais à direita: Contas a Pagar, Contas a
  Receber, Movimentação, Previsão) vs `Width = 9100` (essas colunas ficam
  fora da área visível do MDIChild). Não confundir com um `Visible=False`
  — é só recorte de viewport; o dado clicável some do alcance do mouse mas
  os controles continuam existindo.
- **Permissão por botão**: no load, lê `SELECT * FROM permissoes WHERE
  nome LIKE '%rel_%' AND (sistema=CodSistema OR sistema=CODKASH) AND
  classe=ClasseAtual` e desabilita (`.Enabled = False`) todo
  `CommandButton` cujo `Name` não aparecer nessa lista — granularidade é
  **por botão individual** (nome do controle = nome da permissão), não por
  grupo/Frame. Usuário `KONTACTO` (master) pula esse bloco inteiro
  (`Exit Sub` antes do loop) — mesmo padrão já usado nesta migração pra
  master bypassar `can()` (ver CLAUDE.md > "Master User Has Full
  Permission").
- **Caixa Analítico** (`Frm_Rel_CAT`) tem uma segunda trava, além da
  permissão: só fica habilitado se
  `Dados_Controle_Configuracao.caixa_analitico = True` (ou usuário
  master) — já replicada nesta migração (tela atual usa permissão
  `REL_CX_ANALIT.ABRIR`, mas **não** replica esse segundo flag de módulo;
  registrar como divergência a confirmar se vale a pena portar).
- **`VerificaAreaAtuacao`** é chamado antes de abrir "Fechamento de Caixa"
  (`Rel_Cai_Fca`) e "Margem de Lucro x DAV" (`Rel_Pec_MLd`) — gate de área
  de atuação do usuário logado, não rastreado em detalhe nesta rodada (fora
  do escopo do pedido, que era só o rastreio dos relatórios em si).
- **Botão morto/oculto**: `Rel_Pec_IPN` ("Itens Pendentes Nº de Série",
  Tag=`FrmNDSPend`) está declarado com `Visible = 0` fixo, fora de
  qualquer `Frame` — nunca aparece na tela, é código morto (ou recurso
  desligado deliberadamente). Não portar sem confirmação.
- **Botão sem controle correspondente**: existe um handler
  `Rel_Rec_ECO_Click` (abre `FrmEnvCob`, Envio de Cobrança) no código, mas
  **nenhum** `CommandButton Rel_Rec_ECO` está declarado no form — handler
  órfão (botão removido da tela em algum momento, handler ficou pra trás).
  Envio de Cobrança já existe nesta migração dentro do módulo Bancos (ver
  memória `project_bancos_cobranca`), então não é uma lacuna real.
- **Hardcode de CNPJ específico de cliente** (gambiarra, não regra de
  negócio — ver CLAUDE.md > "Não replicar truques VB6"): dentro do grupo
  Combustíveis, "Contagem de Abastecimentos" e "Mapa de Fechamento Diário"
  checam `SELECT cgc FROM controle` e, se `cgc = '20786044000104'`, abrem
  um form alternativo (`FrmRelComPos`/`FrmFecDia2`) em vez do padrão
  (`FrmResAba`/`FrmFecDia`) — específico de uma instalação, não portar.

### Grupos e relatórios (Caption exibido → controle VB6 → form de destino)

**Caixa**
- Apuração Vendas - DRE → `Rel_Cai_APV` → `FrmRelAPV`
- Descontos → `Rel_Cai_Des` → `FrmRelDes`
- Entrada de Caixa → `Rel_Cai_Eca` → `FrmRelEntCaixa`
- Fechamento de Caixa → `Rel_Cai_Fca` → `frmFechaCaixa` (gate `VerificaAreaAtuacao`) — ✅ já migrado (`relatorio-caixa.tsx`)
- Recebimento de Cartões → `Rel_Cai_rdc` → `FrmRelCar`
- Resumo de Venda → `Rel_Cai_Res` → `FrmRelFec`
- Saída de Caixa → `Rel_Cai_Sca` → `FrmRelSaiCaixa`
- Cartões x Vencimento → `Rel_Cai_Ved` → `FrmRelCarVen`
- Caixa Analítico → `Frm_Rel_CAT` → `FrmTotCaixa` (gate extra `caixa_analitico`) — ✅ já migrado (`relatorio-caixa-analitico.tsx`)

**Vendas**
- Itens por Funcionário → `Rel_Pec_Ivf` → `FrmRelVenFun`
- Ranking de Vendas → `rel_pec_rkv` → `FrmRkgCliPro`
- Vendas x Custo → `Rel_Pec_PVC` → `FrmRelPVC`
- Venda por Cliente → `Rel_Pec_Vci` → `FrmRelVenCli`
- Venda por Comanda → `Rel_Pec_Cvc` → `FrmRelComVen`
- Venda por Produto → `Rel_Pec_Vpr` → `FrmRelVenPro`
- Venda por Nível → `Rel_Pec_Vpn` → `FrmRelVenNiv`
- Vendas por Nota → `rel_pec_csn` → `FrmRelCSN`
- Venda por Vendedor/Executor O.S → `Rel_Pec_VGV` → `FrmRelVenNivFun` (seta `TipoRelatorio = "V"` antes de abrir)
- Venda por Região/Segmento → `Rel_Pec_VRS` → `FrmVenTot`

**Fiscal**
- Apuração Fiscal → `Rel_Nfi_AFI` → `FrmCalImp`
- Apuração Pis Cofins → `Rel_Pec_RPC` → `FrmRelPisCofins`
- Listagem Notas Fiscais → `Rel_Nfi_Nfc` → `FrmRelNF`
- Notas Recebidas → `Rel_Nfi_Rec` → `FrmRelNFRec`

**Clientes**
- Inatividade de Clientes → `Rel_Pec_CSM` → `FrmRelCliSMV`
- Listagem → `Rel_Cli_Cli` → `FrmRelClie`
- Mala Direta → `Rel_Cli_Mal` → `FrmMalDir2`

**Apuração das Comissões**
- Comissão Individual → `Rel_Com_Api` → `FrmCalcComissao`
- Comissão Geral → `Rel_Com_Apc` → `FrmRelComissao2`
- Por contas à Receber → `Rel_Com_CPF` → `FrmRelComRec`
- Comissão por Função → `Rel_Com_CCR` → `FrmRelComissao`

**Margem**
- Margem de Lucro → `Rel_Pec_MLC` → `FrmRelPecMLC` — possível equivalente já migrado: `relatorio-margem-lucro.tsx` (não confirmado campo-a-campo, só o nome/propósito batem)
- Margem de Lucro x DAV → `Rel_Pec_MLd` → `FrmResDAV` (gate `VerificaAreaAtuacao`)

**Estoque**
- Estoque → `Rel_Pec_Est` → `FrmRelPecNiv`
- Estoque por Nível → `Rel_Pec_EPN` → `FrmRelFecEst`
- Estoque Terceirizado → `Rel_Pec_Cab` → `FrmRelCAb`
- Etiqueta de Produto → `Rel_Pec_Epr` → `FrmEtqProd`
- Produtos Reservados → `Rel_Pec_Pre` → `frmRelPecRes`
- Movimentação de Itens → `Rel_Nfi_Mov` → `FrmRelMovCli`
- Movimentações por Nível → `rel_pec_mpn` → `FrmRelVenLojas`

**Compras**
- Relatório de Compra → `Rel_Pec_com` → `FrmRelEstNiv` (nome do form não bate com o rótulo — confirmado assim na fonte, não é engano de transcrição)

**Pré Venda**
- Itens do Pedido → `Rel_Pec_Ite` → `FrmItePed`
- Pedidos Pendentes → `rel_cli_pep` → `FrmRelPeP`
- Custo de O.S → `Rel_Ord_COs` → `FrmCustoOS`
- Itens Vendidos O.S. → `Rel_Pec_IOB` → `FrmRelVenOsB`
- Ordem de Serviço → `Rel_Ord_Ord` → `FrmRelOs` — possível equivalente já migrado: `relatorio-os.tsx`
- O.S. Não Faturadas → `Rel_Ord_ONf` → `frmRelOSRes`
- Resumo Atendimento → `Rel_Ord_OSS` → `FrmRelOSs`
- Resumo Mov da O.S. → `Rel_Ord_RMO` → `FrmResRos`

**Combustíveis** (grupo inteiro só visível com módulo Posto ligado — ver regras de gating acima; não aparece no screenshot)
- Contagem de Abastecimentos → `rel_cbo_aba` → `FrmResAba` (ou `FrmRelComPos` — hardcode de CNPJ, não portar)
- Encerrantes → `rel_cbo_enc` → `FrmRelEnc`
- Controle de Estoque → `rel_cbo_cec` → `FrmRelVCE`
- Livro de Movimentação - LMC → `rel_cbo_lmc` → `FrmRelLMC`
- Mapa de Fechamento Diário → `rel_cbo_mfd` → `FrmFecDia` (ou `FrmFecDia2` — hardcode de CNPJ, não portar)
- Movimentação por Bomba → `rel_cbo_mov` → `FrmRelMovBomba`
- Movimentação de Combustível → `rel_cbo_mdc` → `FrmMovCom`
- Relatório Gerencial → `rel_cbo_reg` → `FrmRelCXC`
- Venda por Cliente → `rel_cbo_vpc` → `FrmComPos`

**Movimentação**
- Cheques não compensados → `Rel_Flu_Che` → `FrmRelCnp`
- Conta corrente por Classe → `rel_flu_ccc` → `frmRelDespCat`
- Lançamentos por Classe → `Rel_Flu_Lcc` → `frmRelCat`
- Lançamentos por Centro Custo → `Rel_Flu_CCL` → `frmRelCaC`
- Lançamentos por Documento → `Rel_Flu_Lcd` → `FrmRelDoc`
- Movimentação de Contas → `Rel_Flu_Mov` → `FrmRelMov`
- Movimentação por Favorecidos → `Rel_Flu_Mvf` → `FrmRelMFav`
- Mov Favorecido Extrato → `Rel_flu_MFE` → `FrmRelMFavAM`
- Receitas x Despesas por Classe → `Rel_Flu_Rdc` → `FrmRelCla`
- Receitas x Despesas por Mês → `Rel_Flu_Rdm` → `FrmRelCla2`
- Receitas x Despesas por Favorecido → `Rel_Flu_Rdf` → `FrmRelFav`
- Saldos Atuais das Contas → `Rel_Flu_Sal` → `FrmRelSal`
- Consolidado Empresas → `Rel_Flu_CEm` → `FrmGerEmp` (aparece esmaecido no screenshot — provável botão sem permissão concedida ao usuário logado, não módulo desligado)
- Relatório Gerencial → `Rel_Flu_rge` → `FrmResFCX`

**Previsão**
- Previsões por Favorecido → `Rel_Flu_Prf` → `FrmRelPFav`
- Previsão de Lançamentos → `Rel_Flu_Pre` → `FrmRelPRL`

**Contas a Receber**
- Relatório de Cartões → `Rel_Rec_rdc` → `FrmRelCarVen` (mesmo form de destino de "Cartões x Vencimento" do grupo Caixa — reaproveitado, confirmado assim na fonte)
- Duplicatas à Receber → `Rel_Rec_Dre` → `FrmRelDRe`
- Duplicatas Recebidas → `Rel_Rec_Rec` → `FrmRelDUR`
- Impressão de Boletos → `Rel_Rec_Bol` → `FrmRelBol`
- Previsão de Recebimento → `Rel_Rec_Pre` → `FrmRelPreRD`

**Contas a Pagar**
- Duplicatas à Pagar → `Rel_Pag_Pag` → `FrmRelDPa`
- Duplicatas à Pagar por Banco → `Rel_Pag_Pgb` → `FrmRelBanP`
- Duplicatas Pagas → `Rel_Pag_Dpg` → `FrmRelDUP`
- Pagamentos por Data → `Rel_Pag_Ppg` → `FrmRelPrePD`

**Contratos**
- Listagem de Contratos → `Rel_Con_Con` → `FrmRelContrato`

### Contagem e status geral

15 grupos (14 sempre visíveis + "Combustíveis" gated por módulo Posto),
~64 relatórios ao todo (contando o botão morto `Rel_Pec_IPN`). Desses,
hoje `relatorios.tsx` cobre só 6 cards, e mesmo esses 6 **não foram
confirmados campo-a-campo** contra o form VB6 equivalente listado acima —
foram construídos a partir de necessidade própria desta migração
(Fechamento de Caixa e Caixa Analítico têm rastreio próprio documentado em
`project_fechamento_caixa`; Descontos & Margem/Margem de Lucro/Pedido de
Venda/O.S. não têm rastreio formal contra os `.frm` deste painel — usar
este documento como ponto de partida se/quando o rastreio campo-a-campo de
qualquer um desses 64 relatórios for pedido).

### Decisões do usuário (2026-08-07, via `AskUserQuestion`) — grupo Caixa

- **Prioridade/ordem**: implementar agora só os 2 relatórios simples e
  autônomos (**Entrada de Caixa**, **Saída de Caixa**) — os outros 5 ficam
  registrados aqui, com o rastreio já feito acima, aguardando retomada.
- **Escopo Comanda** (Descontos, Resumo de Venda, Cartões x Vencimento — os
  3 que no legado só enxergam vendas via `comanda`): quando forem
  retomados, **generalizar para Pedido/OS/Comanda**, no mesmo espírito do
  relatório "Descontos & Margem" já existente nesta migração (filtro
  Pedido/OS/Todos) — não replicar o escopo restrito do legado (só Comanda).
  Isso é uma mudança de arquitetura real em relação ao `.frm` original, não
  só um detalhe de UI — qualquer rastreio futuro desses 3 relatórios deve
  planejar a consulta já pensando nas 3 fontes (`pedido_venda`,
  `os_produto`, `comanda`), não só `comanda`.
- **Recebimento de Cartões**: confirmado que é um **módulo novo**, não "um
  relatório" — depende de um subsistema de conciliação de adquirente de
  cartão (`cartoes_transacoes`, `cartoes_transacoes_parcelas`,
  `cartoes_administradoras`, `bancos`, tela própria de edição de
  transação/parcela) que não existe em nenhum lugar desta migração hoje.
  Fica registrado aqui como módulo futuro — só priorizar se/quando pedido
  explicitamente, mesmo tratamento dado a outros módulos grandes
  (Bancos, Cilindros) antes de serem priorizados.

### Rastreio detalhado dos 7 relatórios pendentes (feito 2026-08-07)

**Entrada de Caixa** (`FrmRelEntCaixa.frm`, 579 linhas) — ✅ **implementado
nesta rodada** (ver abaixo). Simples: agrupa `entrada_caixa` por
`descricao`+`atendente` (nome_guerra) no período informado, soma `valor`
por grupo, mais uma linha de Total Geral. Sem filtro de tipo/forma, sem
níveis. Único detalhe do legado não replicado: a validação "data final não
pode ser maior que `DATESIST`" — nenhum outro relatório desta migração
aplica essa trava, mantido consistente com os irmãos (`relatorio-caixa.tsx`
etc. também não checam isso).

**Saída de Caixa** (`FrmRelSaiCaixa.frm`, 586 linhas) — ✅ **implementado
nesta rodada** (ver abaixo). Espelho exato do anterior, mesma estrutura,
tabela `Saida_Caixa` em vez de `entrada_Caixa`.

**Descontos** (`FrmRelDes.frm`, 478 linhas, Caption "Relatório de descontos
concedidos por venda/funcionário") — 🟢 **implementado 2026-08-07** (ver
"Fase implementada" logo abaixo do rastreio). Fonte:
`comanda` (situação='PG') + `movimentacao` (serie_nf='CM') +
`DESCONTOS_CONCEDIDOS` (tipo='COM'). Filtros: nº da comanda, período,
cliente (busca por código/CGC/nome/fantasia com autoload, mesmo padrão já
usado em outras telas), faixa de desconto % (De/Até), checkbox "exibir
também vendas sem desconto" (inverte a lógica do filtro: NOT IN vs IN na
subquery de `DESCONTOS_CONCEDIDOS`). Saída é uma árvore de 3 níveis:
Comanda (com formas de pagamento concatenadas em texto livre) → Item (com
preço bruto recalculado somando de volta os descontos) → cada desconto
concedido naquele item (percentual, valor, tipo Item/Geral, origem
Pedido/OS quando aplicável, funcionário que concedeu — `nome_guerra`).
Totaliza bruto/desconto/líquido por comanda e geral. **Decisão do usuário
acima**: generalizar pra Pedido/OS/Comanda ao implementar, não só Comanda.

### Descontos — implementado (2026-08-07)

**Achado decisivo antes de implementar**: esta migração **já tem** uma
tabela chamada exatamente `descontos_concedidos` (mesmas colunas do
legado — TIPO/CODIGO/CODIGO_PRODUTO/PERCENTUAL/VALOR/USUARIO/
TIPO_DESCONTO, ver `descontos_service.py`), mas **só é gravada pro
Pedido** (`TIPO='PED'`, em `_log_desconto_item`/
`_aplicar_desconto_geral_sync`). Confirmado por grep que **O.S.**
(`os_itens_service.py`) grava desconto só como valor direto em
`os_produto.desconto`, sem nenhuma auditoria de quem concedeu/tipo
Item-Geral — não existe nenhum `INSERT INTO descontos_concedidos` com
`TIPO='OS'` nesta migração. Por isso o relatório mostra, por item: pra
**Pedido**, tipo (Item/Geral) + quem concedeu (via JOIN em
`descontos_concedidos`); pra **O.S.**, só o valor do desconto (campos de
auditoria vêm `null`, a UI mostra "—" em vez de inventar).

**Simplificação de estrutura em relação ao legado**: no legado um item
podia ter VÁRIOS registros históricos empilhados em
`DESCONTOS_CONCEDIDOS` (append-only, dá pra ver descontos anteriores já
substituídos). Nesta migração, `_log_desconto_item`/
`_aplicar_desconto_geral_sync` usam política **delete+insert** — um item
tem NO MÁXIMO 1 linha ativa a qualquer momento (nunca 'I' e 'G' ao mesmo
tempo, desconto geral sempre sobrepõe removendo o log anterior). Por isso
a árvore de 3 níveis do legado (Documento → Item → Grants) virou 2 níveis
aqui (Documento → Item, cada item já carrega seu único desconto ativo) —
não é perda de informação, é o formato real do dado nesta migração.

**Sem filtro por situação** — mesma convenção do relatório irmão mais
próximo ("Descontos & Margem", `_relatorio_desc_margem_sync`), que também
não filtra por `situacao`.

**Implementação**:
`backend/services/relatorio_descontos_concedidos_service.py` (query com 2
branches `UNION ALL` — Pedido com JOIN em `descontos_concedidos`/
`funcionarios`, O.S. sem essa auditoria — agrupamento por documento em
Python) + rota `GET /api/relatorios/descontos-concedidos` (filtros
período, tipo Pedido/OS/Todos, cliente — nome ou fantasia, `[GLOBAL]`
busca de cliente) + permissão `REL_DESC_CONCED` + 10 testes unitários +
tela `frontend/app/relatorio-descontos-concedidos.tsx` (cards por
documento, chips de origem) + exportador PDF/Excel + card em
`relatorios.tsx` (grupo Caixa). `tsc --noEmit`: baseline de 12 mantido.
**Não testado ao vivo** ainda — quando testar, confirmar que um desconto
de item (tipo 'I') e um desconto geral (tipo 'G') aplicados num Pedido
real aparecem corretamente rotulados, e que um item de O.S. com desconto
aparece sem quebrar mesmo sem dado de auditoria.

**Resumo de Venda** (`FrmRelFec.frm`, 837 linhas, Caption interno não
explícito no form — botão "Resumo de Venda") — 🟢 **implementado
2026-08-07** (ver "Fase implementada" logo abaixo do rastreio). Fonte:
`comanda` (situação='PG') + `movimentacao` (serie_nf='CM') cruzada com
`pecas`/`servicos`/`veiculos` pra achar `nivel1..5`, agregando faturamento
(qtd×p_unit) e custo (`custo_reposicao`) por nível de produto (árvore
`niveis`, indentada por profundidade — nivel1 até nivel5). O algoritmo
VB6 usa um loop aninhado gigante pra "achar a linha do Flex que bate com
os níveis do item" — isso é puro workaround de VB6/FlexGrid (ver "Não
replicar truques VB6"), a regra real é só um `GROUP BY nivel1,nivel2,
nivel3,nivel4,nivel5` com rollup por nível, trivial em SQL moderno. Tem
também um filtro opcional por atendente (`vatendente`) via combo de
funcionários ativos. Há um bloco de "Despesas" inteiro comentado
(`'tb.Open "Select valor from Despesas..."`) — código morto/abandonado no
legado, não portar. Termina com Total Geral (faturamento) e uma segunda
seção de Saída de Caixa do mesmo período (linha 631,
`Select valor,descricao from Saida_Caixa ...`) — ou seja, este relatório
mistura "faturamento por nível" com "saídas de caixa do período" numa
única tela; avaliar ao implementar se faz sentido manter os dois juntos ou
separar, já que Saída de Caixa já vira seu próprio relatório nesta rodada.
**Decisão do usuário acima**: generalizar a base de vendas pra Pedido/OS/
Comanda, não só Comanda.

### Resumo de Venda — implementado (2026-08-07)

**Generalização real aplicada**: investigação de schema (mesma feita pro
Apuração de Vendas-DRE, ver seção acima) confirmou que `comanda`+
`movimentacao` nesta migração **não são um ledger geral de item** — só o
"envelope" de fechamento (ver `fechamento_caixa_service.py`), com a única
exceção real sendo Contratos (fora do escopo deste relatório). Por isso a
generalização "Pedido/OS/Comanda" decidida pelo usuário virou, na prática,
**Pedido/OS** (as tabelas reais de venda desta migração:
`pedido_venda_prod`/`pedido_venda`, `os_produto`/`os`) — mesmos joins já
validados no DRE (produto via `pecas.codigo_int`/`servicos.codigo`, custo
via `custo_reposicao`/`custo_hora` no Pedido e `custo_os` já pronto no
item de O.S.).

**Simplificações conscientes**:
- **Sem Veículos** — o legado cruza também com `VEICULOS`, mas nenhum
  fluxo de Pedido/O.S. já migrado referencia item tipo veículo; não
  portado sem confirmação (nem o rastreio do DRE encontrou essa
  referência em nenhum join já existente no backend).
- **Sem a seção de Saída de Caixa** que o `.frm` original anexa ao final
  — já existe como relatório próprio nesta migração
  (`relatorio-entrada-saida-caixa.tsx?tipo=S`, implementado antes deste),
  duplicar seria redundante. Essa era exatamente a dúvida registrada no
  rastreio original acima — resolvida ao implementar.
- **Árvore de nível substituída por lista plana com breadcrumb completo**
  — em vez de replicar a indentação hierárquica do `FlexGrid` (puro
  workaround de UI do legado, os valores não são somados por ancestral,
  só exibidos com indentação visual), cada combinação de nível vira uma
  linha só com o caminho completo resolvido via `buildNivelBreadcrumb`
  (mesma função/regra `[GLOBAL]` já usada em Produto Completo/Serviços) —
  mais simples de implementar e mais claro de ler que uma árvore
  recolhível, sem perder nenhuma informação (a soma por nível já era por
  combinação exata no legado, nunca um rollup pros ancestrais).
- Filtro por Vendedor replicado (opcional) — `pv.vendedor` no Pedido
  (header), `i.vendedor` na O.S. (item), mesma assimetria de schema já
  documentada no DRE.
- Venda bruta (sem descontar `desconto`), mesma convenção dos outros
  relatórios desta migração.

**Implementação**: `backend/services/relatorio_resumo_venda_service.py`
(query com 4 branches `UNION ALL` — Pedido Produto/Serviço, O.S. Produto/
Serviço — agregação por nível em Python) + rota
`GET /api/relatorios/resumo-venda` + permissão `REL_RES_VENDA` + 7 testes
unitários + tela `frontend/app/relatorio-resumo-venda.tsx` (reaproveita
`GET /api/relatorios/margem-lucro/niveis`, endpoint de lookup já
existente, pra resolver os breadcrumbs) + card em `relatorios.tsx` (grupo
Caixa). `tsc --noEmit`: baseline de 12 mantido, sem erro novo. **Não
testado ao vivo** ainda.

**Cartões x Vencimento** (`FrmRelCarVen.frm`, 808 linhas, Caption
"Relatório de Formas de Pagamento Por Vencimento") — 🔴 não implementado.
Fonte: tabelas `comanda_cartao`/`comanda_credito`-like (aliases `CC`/`CRC`
vistos nas queries, ligadas a `forma_pagamento`, com `taxa_adm`). 3 modos
de resumo alternáveis: "Por Tipo de Pagamento", "Por Forma de Pagamento",
"Cartões Por Vencimento" — mais filtros de Cheque/Cartões de Crédito/
Cartões de Débito e um botão "Exibir Comandas...". **Rastreio ainda
raso** — não foi lido campo-a-campo, só a estrutura de captions/queries;
precisa de uma leitura completa antes de implementar. **Decisão do usuário
acima**: generalizar pra Pedido/OS/Comanda.

**Recebimento de Cartões** (`FrmRelCar.frm`, 2231 linhas, Caption
"Relatório de Recebimento de Cartões") — 🔴 **módulo futuro, não um
relatório simples** (decisão do usuário acima). Fonte: `cartoes_transacoes`,
`cartoes_transacoes_parcelas`, `cartoes_administradoras`, `bancos`,
`forma_pagamento` — sistema completo de conciliação de adquirente de
cartão, com tela própria de "Alteração de Transações" (editar
data de recebimento/parcelas/bandeira/administradora de uma transação já
lançada), múltiplos resumos cruzados (por Banco, por Banco/Administradora,
por Banco/Bandeira, por Administradora, por Administradora/Bandeira, por
Bandeira), filtros Débito/Crédito/Loja/"Totalizar por data de crédito".
Nenhuma dessas tabelas existe nesta migração. Não rastreado campo-a-campo
(seria trabalho perdido antes de decidir se/quando este módulo entra em
pauta) — só a estrutura de captions/queries foi inspecionada.

**Apuração Vendas - DRE** (`FrmRelAPV.frm` — **não existe em `Geral\`**,
usado `Kontacto\FrmRelAPV.frm`, 1953 linhas, mais completo que a variante
em `consult\`; Caption "Apuração de Vendas...") — 🟢 **Fase 1 implementada
2026-08-07** (ver abaixo), Fases 2/3 pendentes.

Rastreio completo do `.frm` (campo-a-campo, `Command1_Click` = motor
principal, `executa2`/`CalculaDespesas` = sub-sistema de Despesas,
`Form_Load` = carga dos combos de filtro):

- **Filtros**: Vendedor (`Cmb(0)`, funcionários ativos + "TODOS"), Região
  (`Cmb(1)`), Segmento (`Cmb(2)`), Rota (`Cmb(3)`), Tipo Cliente (`Cmb(4)`)
  — todos opcionais, "TODOS"/"-2" tem um caso especial (registros cujo FK
  não bate com nenhuma linha da tabela auxiliar — não portado, edge case
  de dado órfão). Produto/Serviço/Veículo específico (`Campo(2)`, busca por
  código de fábrica/barras/descrição/código interno/chassi) e "Por Nível"
  (árvore de níveis) — mutuamente exclusivos (`Option1`/`Option2`), nenhum
  dos dois na Fase 1. "Incluir Vendas de Garantia" (`Check3`) filtra
  `comanda.tipo=0` quando desmarcado.
- **5 categorias de receita**, uma query `UNION ALL` por categoria,
  agrupada por mês (ou por período inteiro quando o intervalo não cobre
  mês(es) cheios — ver simplificação abaixo): Contratos, Produtos O.S.,
  Serviços O.S., Venda Produtos, Venda Serviços. Todas as 5, no legado,
  leem `comanda`+`movimentacao` (`situacao='PG'`, `serie_nf='CM'`),
  diferenciadas só por `codigo_int = Cod_Servico_Contrato` (Contratos) e
  por `c.comanda IN/NOT IN (SELECT comanda FROM comanda_os)` (O.S. vs
  venda direta).
- **Custo**: `SUM(m.QTD*custo_mov)` por categoria — coluna `custo_mov` de
  `movimentacao`, item a item.
- **Despesas** (`Command13`/`Configurar Despesas`): abre um `ListView`
  (`Classes`) com toda combinação `classe`/`sub_classe` de
  `classes`/`sub_classes` (plano de contas do Financeiro), com checkbox —
  seleção persistida em `classes_despesas` (delete-all + reinsert a cada
  abertura). `CalculaDespesas(FiltroPeriodo, Totalizar)` soma
  `movimentacoes_centro_custo` (via `movimentacoes.tipo <> 2`) restrito às
  classes marcadas (ou TODAS se nada foi desmarcado), classifica cada
  classe como Receita/Despesa pelo SINAL do total agregado (não por uma
  coluna fixa) e devolve o total de Despesas (linhas com sinal negativo,
  invertido pra positivo) do período/mês. **Reaproveita infraestrutura já
  migrada** (`movimentacoes`/`movimentacoes_centro_custo`/`classes`/
  `sub_classes` — mesmas tabelas do Financeiro > Fluxo de Caixa, ver
  `project_contas_fluxo_caixa`), não é módulo novo — só não foi portado
  na Fase 1 por ser um sub-fluxo de configuração próprio (picker de
  classes) que merece sua fase separada.
- **Colunas do grid final**: Mês/Ano (ou Período) | Contratos | Produtos
  O.S. | Serviços O.S. | Venda Produtos | Venda Serviços | Total Mês |
  Custo | Despesas | Margem Valor (`Total − Custo − Despesas`) | Margem %
  (`100 − ((Custo+Despesas)/Total×100)`).
- **"Imprime detalhado"** (`Check7`): pra cada mês, chama `Detalha` +
  `Imprime3` — não rastreado em detalhe (não lido campo-a-campo), abre uma
  segunda grade (`Grid2`/`Frame2`) com o detalhamento por produto/nível
  daquele mês. Fase 3.
- **"Preço Médio"** (`Check9`) e checkboxes de tipo de venda a incluir
  (`Check1`/`Check2`/`Check4`/`Check5`/`Check6` — Contratos/Produtos O.S./
  Venda de Produtos/Serviços O.S./Venda de Serviços) estão todos com
  `Visible=0` no form — **código morto/desligado no legado**, não geram
  nenhum filtro real em `Command1_Click` (a query sempre calcula as 5
  categorias incondicionalmente). Não portado, não é perda de regra.

### Fase 1 implementada (2026-08-07) — decisões de arquitetura

**Generalização Pedido/OS/Comanda** (decisão do usuário, mesma diretriz já
dada para Descontos/Resumo de Venda/Cartões x Vencimento acima) — mas
aplicada de forma diferente do que essas 3 vão precisar, porque a
investigação de schema mostrou que **nesta migração Pedido e O.S. já são
documentos próprios** (`pedido_venda`/`pedido_venda_prod`,
`os`/`os_produto`), não passam pelo ledger `comanda`+`movimentacao` como
no legado — `comanda` aqui é só o "envelope" de fechamento/pagamento
(`COMANDA_PED`/`comanda_os` linkam `comanda` → `pedido_venda`/`os`, ver
`fechamento_caixa_service.py`). Então a Fase 1 já lê as tabelas REAIS:
- Produtos/Serviços O.S. → `os_produto` (`codigo_interno` prefixo P/S) +
  `os` (`situacao='PG'`, período em `data_entrada`).
- Venda Produtos/Serviços → `pedido_venda_prod` (`produto` → `pecas`/
  `servicos`) + `pedido_venda` (`situacao='PG'`, período em `data`).
- **Contratos continua via `comanda`+`movimentacao`** — confirmado que
  `contratos_service.py._faturar_contratos_sync` grava EXATAMENTE nesse
  formato (`movimentacao(codigo_int=cod_servico_contrato, serie_nf='CM')`
  + `comanda`), sem equivalente em `pedido_venda`/`os` — não é o mesmo
  "workaround" das outras 3 pendências, é a tabela real usada por essa
  categoria nesta migração também.
- `situacao='PG'` (Faturado) é o código compartilhado por `pedido_venda`/
  `os`/`comanda` nesta migração (`SITUACAO_LABEL` em
  `services/constants.py`) — mesmo código que o legado já usava pra
  comanda, confirmado antes de assumir.

**Simplificações conscientes desta Fase 1** (ver docstring de
`relatorio_apuracao_vendas_service.py` pro detalhe completo):
- Sempre agrupa por mês (nunca colapsa num "Período" único) — o
  branching do legado (mês cheio vs período parcial) era só limitação de
  UI do FlexGrid, agrupar sempre por mês é estritamente mais informativo.
- "Incluir Vendas de Garantia" **não implementado** — não existe campo
  equivalente a `comanda.tipo=0` nesta migração (`pedido_venda.tipo` já
  foi reaproveitado pro tipo Mesa/Comanda/Balcão do Pedido Bar). Replicar
  exigiria juntar as 3 fontes às tabelas de forma de pagamento (mesmo
  mecanismo `FORMA_PAG_GARANTIA` que o Fechamento de Caixa já usa) — não
  feito ainda, registrado como possível Fase 1.5.
- **Despesas não implementadas** (Fase 2, ver rastreio acima) — Margem
  desta Fase 1 é só `Total − Custo`, sem dedução de despesa configurada.
- **Sem Por Nível/produto específico/Preço Médio/impressão detalhada por
  item** (Fase 3).
- Venda é **bruta** (sem descontar `desconto`) — mesma convenção já usada
  em `_relatorio_pedidos_sync`/`_relatorio_os_desc_margem_sync`.

**Implementação**: `backend/services/relatorio_apuracao_vendas_service.py`
(`_apuracao_vendas_sync`, query única com 5 branches `UNION ALL`,
agregação por mês em Python) + rota `GET /api/relatorios/apuracao-vendas`
(`routes/relatorios.py`) + permissão `REL_APUR_VENDAS` + 7 testes
unitários (`test_relatorio_apuracao_vendas_service.py`) + tela
`frontend/app/relatorio-apuracao-vendas.tsx` + card em `relatorios.tsx`
(grupo Caixa). **Não testado ao vivo** contra uma conexão real ainda —
antes de considerar a Fase 1 validada, rodar contra dados reais com
Contrato + O.S. + Pedido faturados no mesmo período e conferir que os 3
somam corretamente por mês, e que os filtros de Vendedor/Região/Segmento/
Rota/Tipo Cliente batem com o que a lista de Pedidos/O.S. já mostra pros
mesmos documentos.

### Próximos passos

- **Implementados**: Entrada de Caixa, Saída de Caixa, Apuração de Vendas
  - DRE (Fase 1), Resumo de Venda e Descontos — 5 dos 9 relatórios do
  grupo Caixa.
- **Ainda pendente**: só Cartões x Vencimento (médio porte, mesma
  generalização Pedido/OS a aplicar — usar o rastreio de schema já feito
  no DRE/Resumo de Venda/Descontos como ponto de partida, não
  re-investigar do zero) + Recebimento de Cartões (módulo futuro, fora de
  escopo até pedido explícito) + Apuração de Vendas-DRE Fases 2/3
  (Despesas configuráveis, Por Nível, Preço Médio, impressão detalhada).
- Grupo "Combustíveis" (gated por módulo Posto) e módulo "KA$H"
  (não mapeado nesta migração) — perguntas em aberto sem decisão ainda,
  não bloqueiam o trabalho acima.

## Painel de Relatórios (VB6) — Grupo Pré Venda

**Status: rastreio dos 8 relatórios feito (2026-08-07); situação multi-
select implementada; ainda faltam 4 relatórios novos, aguardando retomada.**

### Correção importante achada no meio do rastreio

Os 2 forms **"Ordem de Serviço"** (`Rel_Ord_Ord`) e **"Resumo Atendimento"**
(`Rel_Ord_OSS`) do painel apontam pra dois `CommandButton`s que chamam
identificadores VB6 quase idênticos — `FrmRelOs` (8 letras) vs `FrmRelOSs`
(9 letras, "S" maiúsculo extra) — e o **nome do ARQUIVO físico não bate
com o nome INTERNO da classe (`Attribute VB_Name`)** em nenhum dos dois,
o que gerou um rastreio errado na primeira passada:

- `Kontacto\frmrelos.frm` (arquivo, 1083 linhas) → `VB_Name = "FrmRelOSs"`
  → é na verdade o form de **"Resumo Atendimento"**, não "Ordem de
  Serviço" como uma primeira leitura sugeriria pelo nome do arquivo.
- O form real de **"Ordem de Serviço"** (`VB_Name = "FrmRelOs"`) está em
  `Revenda\FrmRelOS.frm` — não existe cópia dele em `Kontacto\`/`Geral\`,
  só referenciado via caminho relativo `..\Revenda\FrmRelOS.frm` no
  `backon.vbp` (mesmo padrão de arquivo compartilhado entre pastas de
  linha de negócio já visto em `frmRelOSRes`/`frmresros`, seção Caixa
  acima).

Isso também corrige o achado anterior de **"Resumo Atendimento" (`FrmRelOSs`)
é botão morto**: estava errado — o form existe e é robusto (1083 linhas),
só não tinha sido encontrado porque a busca original procurou por um
arquivo chamado literalmente `FrmRelOSs.frm`, que não existe (o arquivo
físico é `frmrelos.frm`, mesmo case-insensitive). **Lição pra rastreios
futuros**: sempre conferir `Attribute VB_Name` dentro do arquivo, nunca
confiar só no nome do arquivo físico — nomes de classe e nomes de arquivo
divergem no legado com mais frequência do que o esperado.

### Os 8 relatórios

**Itens do Pedido** (`Kontacto\FrmItePEd.frm`, 316 linhas) — 🟢
**implementado 2026-08-07**. Soma `qtd_pedida` por produto (`codigo_fab`) de todo Pedido
`situacao='F'` (Fechado) no período, convertido pra Unidade de Compra via
`QTD_UN_COMPRA`/`UN_COMPRA` (auxiliar de reposição/compra — "quanto
preciso comprar pra repor o que foi vendido"). Checkbox "Detalhar" expande
cada produto nos pedidos individuais que contribuíram. Só Pedido (não O.S.
— esse é o recorte do próprio legado, não uma escolha desta migração).
Situação `'F'` é uma regra real (produto "comprometido", não precisa
esperar faturamento pra entrar no cálculo de reposição) — portar como
está, mais `ISNULL(i.item_cancelado,0)=0` (schema desta migração tem essa
coluna, toda outra query já a usa; sua ausência aqui seria um bug de
correção, não fidelidade ao legado).

**Custo de O.S** (`Geral\FrmCustoOS.frm`, 736 linhas) — 🟢 **implementado
2026-08-07**. Soma `custo_os*quant` de `os_produto` (`origem<>'R'`, exclui
devoluções), situação A/F/PG, agrupável por Cliente OU por Produto/Serviço
(radio), modo Detalhado, filtro por tipo de item (`tipo_os_prod`),
período/O.S./item/cliente. Análise de custo pura, sem equivalente hoje —
`relatorio-os.tsx` mostra venda/desconto/margem por O.S., não uma
quebra de custo por cliente/produto.

**Itens Vendidos O.S./Balcão** (`Geral\FrmRelVenOsB.frm`, 770 linhas) — 🟢
**implementado 2026-08-07**. Soma quantidade/valor por produto INDIVIDUAL (não por
nível — diferente do Resumo de Venda já implementado), combinando venda
direta ("Balcão") + consumo de O.S., no legado via `comanda`+
`movimentacao`+`os_produto`/`comanda_os`. **Generalização** (mesmo
princípio já usado em DRE/Resumo de Venda/Descontos): "Balcão" nesta
migração é só Pedido (Bar ou Geral) não-vinculado a O.S. — ou seja,
`pedido_venda_prod` + `os_produto`, os mesmos dois já usados no Resumo de
Venda, só que a agregação aqui é por produto/serviço individual em vez de
por nível, e mostra quantidade (não só valor).

**Ordem de Serviço** (`Revenda\FrmRelOS.frm`, `VB_Name="FrmRelOs"`, 1391
linhas) — 🟢 **implementado 2026-08-07** (ver "Implementação" logo abaixo
dos dois rastreios). É uma tela de **busca/lookup de O.S.** (não um relatório de período
agregado como `relatorio-os.tsx`), com master-detail (Grid1 = O.S.
encontradas, Grid2 = itens da O.S. selecionada ao clicar na linha).

- **Filtro único ativo por vez** (radio `Opt(0..7)`, sem botão
  "Selecionar" — a busca dispara automaticamente ao perder o foco do
  campo, `Campo_LostFocus` → `Atualiza`): Cliente (código exato),
  Data Entrada (intervalo), Data Término (intervalo), Placa (prefixo),
  Chassi (prefixo), OS (intervalo de código), Marca (código exato),
  Modelo (código exato). Ordenação Ascendente/Descendente pela mesma
  coluna do filtro ativo.
- **Confirmado fortemente orientado a veículo** (`INNER JOIN` obrigatório
  com `marcas`/`modelos` — uma O.S. sem marca/modelo cadastrado nem
  aparece no resultado), mas **isso não bloqueia mais a implementação**:
  confirmado por grep que `os_service.py` já grava e lê `placa`, `marca`,
  `modelo`, `chassi`, `km`, `ano`, `numero_de_serie` na tabela `os` desta
  migração, e `marcas`/`modelos` já são Tabelas Auxiliares reais (ver
  "Platform Scope" > Web-only areas em CLAUDE.md). Os dados existem,
  só a tela de busca em si não foi construída ainda.
- **Grid1 (lista)**: Cliente (código-nome), OS, Veículo (marca+modelo),
  Data Entrada, Data Término, Placa, Chassi, Situação.
- **Grid2 (detalhe ao clicar numa linha)**: código+descrição do item,
  Qtd, Valor Unitário, Valor Total, **Destino** (`os_produto.situacao`
  decodificado — 0=Cliente, 1=Garantia, 2=Interno, 3=Rev. de Fábrica —
  **mesmo achado do "Custo de O.S"/"Resumo Atendimento" abaixo, agora
  confirmado numa 3ª fonte independente**: é sempre o mesmo FK pra
  `tipo_os_prod`, nunca a situação da O.S. em si).
- Botões: Imprimir, Gerar Planilha, Sair — sem período obrigatório (é
  busca pontual, não relatório fechado por data).

**Resumo Atendimento** (`Kontacto\frmrelos.frm`, `VB_Name="FrmRelOSs"`,
1083 linhas) — 🟢 **implementado 2026-08-07**. Diferente de "Ordem de
Serviço" acima — é um relatório
operacional por período, uma linha por O.S., com quebra financeira por
**destino do item** e tempo de execução.

- **Filtros**: Cliente (nome/código/CGC, com autoload de Chassi/Equip.
  associado a esse cliente), Data Término (intervalo), Tipo de O.S.
  (`tipo_os` via `os.tipo` — **nota**: o `.frm` usa `os.posicao_os`, mas
  `tabelas_aux_service.py` já confirma via `sys.foreign_keys` que o FK
  real desta migração é `os.tipo` → `tipo_os.codigo`; `posicao_os` não
  existe aqui, adaptação necessária, não é suposição — mesmo padrão de
  adaptação já usado no Custo de O.S com `os_produto.situacao`), Técnico
  (`funcionarios`, combo "TODOS"), Equipamento/Chassi (dependente do
  cliente escolhido, combo "TODOS"). Situação da O.S.: 2 checkboxes
  "Fechadas"(`F`)/"Pagas"(`PG`), combináveis (OR). 3 checkboxes de
  **destino a incluir**: "Cliente Pg." / "Interno/Contrato" / "Garantia"
  — controlam tanto se a O.S. aparece (só aparece se tiver total > 0 em
  pelo menos um destino marcado) quanto se a coluna daquele destino é
  zerada quando desmarcada.
- **Uma linha por O.S.**, colunas: Data (término), O.S., **Técnico**
  (`nome_guerra` do funcionário com o MAIOR `codigo_int` entre os
  executores dos itens daquela O.S. — `max(executor)`, regra literal do
  legado, replicável), Início/Fim (de `os_tempo.hora_inicio`/`hora_fim`,
  só quando `os.tipo=1`), T.Horas (soma de `quant` dos itens tipo
  Serviço), Serviço(s)/Peça(s) (soma de `quant*preco_unitario` por
  tipo P/S), Contrato/Garantia/Cliente Pg. (soma por destino do item —
  `os_produto.situacao` 2-ou-3 / 1 / 0), Tipo (`tipo_os.descricao`),
  Serviço Executado (`os.resumo`, quebras de linha removidas pra caber
  numa célula). Totais gerais na última linha.
- Todas as tabelas/colunas referenciadas (`os.resumo`, `os_tempo.
  hora_inicio`/`hora_fim`, `os_produto.executor`) já são reais e usadas
  nesta migração (`os_service.py`, `os_tempo_service.py`,
  `os_itens_service.py`) — confirmado por grep, nenhuma suposição.
- Botões: Imprimir, Gerar Planilha, Gerar HTML (`GeraHTML`, não
  inspecionado — provável variante de impressão, mesma informação do
  grid; não replicar como recurso separado, PDF via `expo-print` já
  cobre a necessidade de "gerar documento" desta migração).

**Pedidos Pendentes** (`Geral\FrmRelPeP.frm`) — 🟢 **resolvido sem tela
nova, 2026-08-07** (decisão do usuário). `pv.situacao NOT IN ('C','PG')`
= mesmo resultado de marcar Aberto+Fechado no relatório de Pedidos já
existente. Implementado como preset "Pendentes" (`situacao=A,F`) no chip
de situação de `relatorio-pedidos.tsx` (`Filtros.tsx`), reaproveitando o
backend já existente — `_relatorio_pedidos_sync` ganhou suporte a
`situacao` como CSV (`"A,F"` → `IN ('A','F')`), mesmo padrão de
`dias_semana` já usado em `/relatorios/caixa-analitico`. Filtro de
periodicidade de forma de pagamento do legado (`List1`/`forma_pagamento.
periodo` — Decenal/Mensal/Quinzenal/etc.) não portado — conceito
obscuro, sem uso confirmado em nenhuma outra tela desta migração.

**O.S. Não Faturadas** (`Revenda\frmRelOSRes.frm`) — 🟢 **resolvido sem
tela nova, 2026-08-07**, mesmo padrão do item acima: preset "Não
Faturadas" (`situacao=A,F`) adicionado ao dropdown de situação de
`relatorio-os.tsx`, reaproveitando `_relatorio_os_sync` (mesmo suporte a
CSV adicionado).

**Resumo Mov da O.S.** (`Focco\frmresros.frm`) — 🔴 **pulado por
enquanto** (usuário sem preferência forte, seguida a recomendação). Só
existe na linha de negócio Focco (não Kontacto/Geral), usa `TRANSFORM/
PIVOT` do Access (sintaxe não portável direto pra SQL Server, precisaria
de `PIVOT` manual) e uma regra opaca (`comanda.tipo = os_produto.
faturado`) sobre colunas (`osp.faturado`, `osp.situacao` numérico) não
confirmadas nesta migração. Registrado aqui, não investigado mais a
fundo — retomar só se pedido explicitamente.

### Implementação (2026-08-07)

- **Situação multi-select**: `test_relatorio_situacao_multi.py` (7
  testes, `_relatorio_pedidos_sync`/`_relatorio_os_sync` com `situacao`
  CSV).
- **Itens do Pedido**: `relatorio_itens_pedido_service.py` (8 testes) +
  rota `GET /api/relatorios/itens-pedido` + permissão `REL_ITENS_PED` +
  tela `relatorio-itens-pedido.tsx` (cards expansíveis por produto).
- **Custo de O.S**: `relatorio_custo_os_service.py` (7 testes) + rota
  `GET /api/relatorios/custo-os` + permissão `REL_CUSTO_OS` + tela
  `relatorio-custo-os.tsx` (toggle Cliente/Produto, filtro Tipo reaproveita
  `GET /api/tabelas/tipo-os-prod` já existente).
- **Itens Vendidos O.S./Balcão**: `relatorio_itens_vendidos_service.py`
  (6 testes) + rota `GET /api/relatorios/itens-vendidos` + permissão
  `REL_ITENS_VEND` + tela `relatorio-itens-vendidos.tsx`.
- Os 3 exportadores PDF/Excel seguem o padrão já estabelecido
  (`print-report-header.ts`). Todos os 3 cards adicionados ao grupo "Pré
  Vendas" já existente em `relatorios.tsx`.
- `tsc --noEmit`: baseline de 12 mantido. **Não testado ao vivo.**

### Implementação de Ordem de Serviço e Resumo Atendimento (2026-08-07)

- **Ordem de Serviço (busca)**: `relatorio_busca_os_service.py` (11
  testes) + rotas `GET /api/relatorios/busca-os` (lista por filtro único)
  e `GET /api/relatorios/busca-os/{os}/itens` (detalhe master-detail) +
  permissão `REL_BUSCA_OS` + tela `relatorio-busca-os.tsx` (chips de modo
  de filtro, cards expansíveis por O.S.). **Diferença consciente do
  legado**: `LEFT JOIN` com `marcas`/`modelos` em vez do `INNER JOIN`
  original — uma O.S. sem veículo cadastrado continua aparecendo (ver
  docstring do service pro raciocínio completo).
- **Resumo Atendimento**: `relatorio_resumo_atendimento_service.py` (10
  testes) + rota `GET /api/relatorios/resumo-atendimento` + permissão
  `REL_RES_ATEND` + tela `relatorio-resumo-atendimento.tsx` (chips de
  situação/destino, SelectField pra Tipo/Técnico reaproveitando lookups
  já existentes `GET /api/tabelas/tipo-os` e `GET /api/funcionarios`).
  Campo Cliente ficou como input de código simples (não usa
  ClientSearchModal) — simplificação consciente pra esta tela de
  filtro secundário, não a tela principal de cadastro/vínculo de
  cliente onde a regra `[GLOBAL]` de busca de identidade é mandatória.
- Os 2 exportadores PDF/Excel seguem o padrão já estabelecido. Cards
  adicionados ao grupo "Pré Vendas" em `relatorios.tsx`.
- `tsc --noEmit`: baseline de 12 mantido. **Não testado ao vivo** —
  atenção especial ao testar: confirmar que o `LEFT JOIN` de Ordem de
  Serviço realmente traz O.S. sem marca/modelo (não só as que têm
  veículo), e que a coluna T.Horas do Resumo Atendimento bate com os
  itens de Serviço reais de uma O.S. de teste.

### Próximos passos

Os 8 relatórios do grupo Pré Venda estão implementados. **Resumo Mov da
O.S.** (Focco) fica de fora até pedido explícito — obscuro, `TRANSFORM/
PIVOT` do Access, colunas não confirmadas nesta migração (ver rastreio
acima).

## Painel de Relatórios (VB6) — Grupo Estoque

**Status: rastreio completo dos 7 relatórios feito (2026-08-07). 4 prontos
pra implementar imediatamente, 1 bloqueado (dado nunca escrito nesta
migração), 1 muito mais rico que o esperado (motor universal de
movimentação — todo módulo já grava nele), 1 de natureza diferente
(designer de etiqueta física, não relatório de dados).**

**Produtos Reservados** (`Revenda\frmrelpecres.frm`, 374 linhas) — 🟢
**implementado 2026-08-07**. Lista `pecas` onde
`(reservado_os + reservado) <> 0` — código interno, código fabricante,
descrição, preço venda, quantidade reservada, preço total — ordenável por
Código Interno/Código Fabricante/Descrição. Sem período (é um snapshot
atual). `pecas.reservado`/`reservado_os` já são colunas reais e ativamente
usadas nesta migração (Checkout, Contratos, Inventário).

**Estoque por Nível** (`Geral\FrmRelFecEst.frm`, 603 linhas) — 🟢
**implementado 2026-08-07**. Soma `(qtd+reservado+reservado_os)` (unidades em estoque) × `custo_
reposicao` e × `p_venda`, agrupado por nível de produto (hierarquia
`niveis`) — mesmo padrão de agregação/breadcrumb já usado em "Resumo de
Venda" (Caixa), reaproveitável 1:1 (substituir a árvore do FlexGrid por
lista plana com `buildNivelBreadcrumb`). Sem período (snapshot atual).

**Estoque** (`Geral\FrmRelPecNiv.frm`, 1265 linhas) — 🟢 **implementado
2026-08-07**, complementar ao anterior. Detalhe produto-a-produto (não agregado) dentro
de UMA combinação de nível escolhida (5 combos em cascata Nível1→5):
código, descrição, `(qtd+reservado+reservado_os)`, `custo_inventario`,
`p_venda`, `area`/`prateleira`/`escaninho` (localização física —
colunas reais, já usadas em Produto Completo/Inventário), só `situacao=
'A'`. Ordenável por Código/Descrição.

**Estoque Terceirizado** (`Geral\FrmRelCAb.frm`, 696 linhas) — 🔴
**bloqueado, não implementável agora**. Inteiramente construído sobre a
tabela `consignacao` (estoque de terceiros em nosso poder / nosso estoque
em poder de terceiros, ligado a `n_fiscal`, com `qtd`/`qtd_devolvida`/
`qtd_faturada` e um botão `&Transferir` que sugere escrita, não só
leitura). Confirmado em `notas_fiscais_service.py` (docstring explícita,
linhas ~80-83): esta migração **nunca escreve** em `consignacao`/
`consignacao_baixa` — decisão consciente já tomada antes desta sessão
("muito específico e arriscado de replicar sem dados reais de
consignação pra testar"), só faz uma leitura pontual pra bloquear
cancelamento de NF já com itens devolvidos/faturados. Implementar este
relatório agora resultaria sempre em tela vazia — **fica bloqueado até o
fluxo de emissão de NF de consignação ser construído**, não antes.

**Movimentação de Itens** (`Geral\FrmRelMovCli.frm`, 1313 linhas) — 🟢
**implementado 2026-08-07**, mas **muito mais rico do que o nome sugere**:
achado importante nesta rodada — `movimentacao` é o ledger universal
desta migração também (não só do legado), escrito por **praticamente
todo módulo já migrado**: confirmado por grep de
`INSERT INTO movimentacao` em `pedidos_service.py` (`tipo='S01',
serie_nf='CM'`, ao faturar — cria uma `comanda` "envelope" na hora, exatamente
como `fechamento_caixa_service.py` já documentava), `os_service.py`,
`checkout_service.py` (4 pontos), `contratos_service.py`,
`requisicao_service.py` (`serie_nf='RQ'`), `movimentacao_produtos_service.py`
(`serie_nf='MV'`), `inventario_service.py` (`serie_nf='IV'`, tipo
`E00`/`S00` — **mesmíssimos códigos do legado**, confirmado), e
`agenda_service.py`. Tabela `tipo_mov` (codigo/descricao/atualiza_est)
também já é real e usada (`lookups_service.py`).
- **Simplificação de arquitetura consciente**: o `.frm` original
  reconstrói o ledger via 5+ branches `UNION ALL` por origem (Comanda/
  Requisição/Inventário), com lógica de exclusão via `comanda_nf` pra não
  contar duas vezes uma venda já com NF emitida — isso existia porque no
  legado `movimentacao` nem sempre é confiável sozinho pra reconstruir a
  história de uma comanda. **Nesta migração isso não é necessário**:
  como confirmado acima, todo módulo já grava fielmente em `movimentacao`
  na hora certa — um `SELECT` direto na tabela (com joins simples pra
  `pecas`/`servicos`/`tipo_mov`/`funcionarios`) já é a fonte completa e
  correta, sem precisar reconstruir nada.
- **Origem via `serie_nf`** (CM=venda faturada Pedido/OS/Contrato/
  Checkout, RQ=Requisição, IV=Inventário, MV=Movimentação de Produtos
  manual) — nota: `CM` mistura Pedido/OS/Contrato/Checkout, já que todos
  usam a mesma série; não dá pra distinguir a origem exata sem voltar em
  `COMANDA_PED`/`comanda_os`/`comanda_contrato`, não replicado nesta
  primeira versão (fica como "Venda" genérico).
- Filtros do legado a portar: período (obrigatório), produto (busca por
  código/descrição), tipo de movimentação (multi-select via `tipo_mov`),
  Entrada/Saída (`LEFT(tipo,1)`), ordenação.

**Movimentações por Nível** (`frmrelvenlojas.frm`, `Gilson Pneus\`, 1243
linhas) — 🟢 **implementado 2026-08-07**, com 2 achados de correção:
- **Caption interna do form diz "Transferência para as Filiais"**, mas o
  botão do painel chama de "Movimentações por Nível" e a query real não
  tem nada a ver com filiais/transferência entre lojas — é só soma de
  `qtd`/`qtd*p_unit` de `movimentacao` por UM tipo de movimentação
  escolhido (`tipo_mov`, situação Ativa + `atualiza_est='S'`), agrupado
  por nível de produto, num período. Caption é artefato de copiar-colar
  de outro form dentro da pasta específica de cliente ("Gilson Pneus") —
  não replicar o conceito de filial, replicar só a agregação por nível
  que a query de fato faz.
- **`PECASEQ` (produtos equivalentes/similares) não portado** — o legado
  consolida o movimento de um produto e seus equivalentes sob um único
  código antes de agrupar por nível; **simplificação consciente**: soma
  cada produto pelo seu próprio nível, sem consolidar equivalentes (a
  tabela `pecaseq` existe nesta migração — já usada em Produto Completo —
  mas essa consolidação específica não foi replicada por ora).
- Workaround de tabela temporária (`create table teste`) — puro artefato
  de VB6/Access, vira `GROUP BY` direto.

**Etiqueta de Produto** (`Geral\FrmEtqProd.frm`, 2989 linhas — o maior
form já rastreado nesta migração) — 🟢 **implementado 2026-08-07**, depois
do usuário desbloquear com detalhes reais de uso (screenshot da tela +
confirmação de que usam tanto folha laser quanto impressora térmica
Zebra). Rastreio campo-a-campo completo feito via agente de pesquisa (ver
histórico da sessão) — 3 mecanismos de impressão totalmente diferentes no
legado: `Printer` GDI puro (2 modelos "Identificação", folha laser tipo
Pimaco), uma DLL COM .NET via GDI+ (2 modelos "Gôndola", com código de
barras EAN), e comandos EPL crus escritos direto num compartilhamento de
rede fixo `\\<computador>\ZEBRA` (4 modelos térmicos Zebra GC420/TLP2844).

Decisões do usuário (`AskUserQuestion`, 2026-08-07):
- **Tabela `modelo_etiqueta` nova** (arquitetura configurável, não só
  constantes no código) — "nada impede de prepararmos pra cadastrar
  modelos específicos no futuro", semeada com os 8 modelos do legado
  (`codigo` = mesmo índice do combobox legado, `formato` = `grade_laser`/
  `gondola`/`termica`, dimensões/margens/colunas/linhas por folha).
- **Zebra (térmica) não implementada nesta rodada** — só documentada no
  Modo Didático (ícone "i") da tela nova, explicando que precisa de uma
  extensão do print-agent local já existente (`project_impressao_
  silenciosa`, testado ao vivo pra cupom/comanda) capaz de falar EPL cru
  com a impressora — extensão ainda não construída. Os 4 modelos Zebra
  aparecem no combobox (pra não precisar de migração de schema depois)
  mas o botão Imprimir bloqueia com mensagem clara se escolhidos.
- **"Excluir"/"Limpar Todos" implementados de verdade** — no legado são
  botões inertes (nenhuma `Sub` por trás, confirmado por rastreio
  completo do arquivo) — corrigido aqui, não replicado como lacuna.
- **Matriz de Grade (Cor×Tamanho) incluída** — detecção automática ao
  digitar um código com grade cadastrada (`pecas_grade`), troca o campo
  Quant por uma matriz de quantidade por combinação.
- **Bug de paginação do "Gôndola Não Fiscal"** (legado não pagina, GDI+
  desenha além da página) — não relevante, impressão via HTML/CSS no
  navegador pagina sozinha por conteúdo.

Simplificações conscientes documentadas na íntegra na docstring de
`etiqueta_produto_service.py`: subquery de cor/tamanho via `pecaseq` no
caminho "Selecionar" não portada (dado morto no legado, nunca chega a
aparecer na etiqueta impressa); "Usar descrição NFCe" só afeta o caminho
manual, replicando a assimetria real do legado; default hardcoded do
checkbox por CNPJ específico não portado (ajuste de cliente único, não
regra geral); resolução Cor×Tamanho numa única query (não no padrão
2-etapas do legado). **Nunca validado contra impressora/folha física
real** — layout CSS em cm é uma aproximação razoável dos modelos do
legado, não uma cópia pixel-a-pixel; ajuste fino de fonte/posição só é
possível comparando contra a folha impressa de verdade.

### Implementação (2026-08-07)

- **Produtos Reservados**: `relatorio_produtos_reservados_service.py`
  (6 testes) + rota `GET /api/relatorios/produtos-reservados` +
  permissão `REL_PROD_RES` + tela `relatorio-produtos-reservados.tsx`.
- **Estoque por Nível**: `relatorio_estoque_nivel_service.py` (3 testes)
  + rota `GET /api/relatorios/estoque-nivel` + permissão
  `REL_ESTOQUE_NIV` + tela `relatorio-estoque-nivel.tsx` (breadcrumb via
  `buildNivelBreadcrumb`, mesmo endpoint de lookup do Resumo de Venda).
- **Estoque**: `relatorio_estoque_service.py` (7 testes, reaproveita
  `_nivel_clause` de `margem_lucro_service.py`) + rota
  `GET /api/relatorios/estoque` + permissão `REL_ESTOQUE` + tela
  `relatorio-estoque.tsx` (seletor de nível via `NiveisModal`
  compartilhado).
- **Movimentação de Itens**: `relatorio_movimentacao_itens_service.py`
  (9 testes) + rota `GET /api/relatorios/movimentacao-itens` +
  permissão `REL_MOV_ITENS` + tela `relatorio-movimentacao-itens.tsx`
  (filtros produto/tipo/entrada-saída/origem, tipo reaproveita
  `GET /api/tabelas/tipo-mov` já existente).
- **Movimentações por Nível**: `relatorio_movimentacao_nivel_service.py`
  (5 testes) + rota `GET /api/relatorios/movimentacao-nivel` +
  permissão `REL_MOV_NIVEL` + tela `relatorio-movimentacao-nivel.tsx`.
- Novo grupo **"Estoque"** em `relatorios.tsx` (5 cards, ordem alfabética
  automática como todo grupo já existente). 5 exportadores PDF/Excel
  seguem o padrão já estabelecido.
- `tsc --noEmit`: baseline de 12 mantido. 30 testes novos, todos
  passando. **Não testado ao vivo** — atenção especial: confirmar que
  "Movimentação de Itens" realmente traz linhas de todas as origens
  (Pedido faturado, O.S. faturada, Contrato, Checkout, Requisição,
  Inventário, Movimentação de Produtos manual) contra uma conexão real
  com dados de cada tipo.

- **Etiqueta de Produto**: `etiqueta_produto_service.py` (14 testes,
  tabela nova `modelo_etiqueta` idempotente/semeada) + rotas dedicadas em
  `routes/etiqueta_produto.py` (`GET modelos`, `POST modelos/{codigo}/
  margem`, `GET nf`, `GET produto`, `GET grade`) + permissão
  `REL_ETQ_PROD` + tela `etiqueta-produto.tsx` (NF Entrada via
  `FornecedorSearchModal`, adição manual via `ProdutoSearchModal` +
  matriz de Grade, Modo Didático explicando a lacuna do Zebra) +
  `export-etiqueta-produto.ts` (grid CSS em cm, paginação por
  `linhas_por_folha` do modelo) + `src/utils/barcode.ts` (novo, usa a
  dependência `jsbarcode` — adicionada ao `package.json` nesta rodada,
  gera EAN-13/EAN-8/CODE128 conforme o tamanho do código).

### Próximos passos

Resta **Estoque Terceirizado** (bloqueado até o fluxo de emissão de NF de
consignação ser construído — não é falta de tempo, é dado que não
existe). **Etiqueta de Produto está implementada mas nunca testada contra
impressora/folha física real** — validar visualmente (alinhamento,
tamanho de fonte, código de barras legível) antes de depender dela em
produção; e retomar a impressão térmica Zebra quando o print-agent local
ganhar suporte a EPL cru (ver seção acima).

## Painel de Relatórios (VB6) — Grupo Vendas

**Status: rastreio completo dos 10 relatórios feito (2026-08-07). 5
implementados, 3 pulados por sobreposição (pendente resposta da equipe
VB6), 1 adiado por ser área fiscal sensível, 1 (Ranking) implementado sem
sua sub-feature de cruzamento com Compras.**

**Achado de localização, antes do rastreio em si**: só 3 dos 10 forms
vivem em `Geral\` — os outros 5 vêm de `Kontacto\`/`Guerengases\` (cada
`.vbp`, inclusive o `backon.vbp` do próprio Kontacto, aponta pra eles
nesses locais; não existem em `Geral\` de forma alguma, não é uma falha
de busca). Duas armadilhas nome-de-arquivo/`VB_Name` reais encontradas:
`Geral\FrmRelComVenCup.frm` **não** é "Venda por Comanda" (é outro
relatório, não rastreado) — o real é `Geral\frmrelcomven.frm` (minúsculo,
só achado via grep case-insensitive); `Geral\FrmRelVenNiv2.frm` tem
`VB_Name = FrmRelVenNiv` (cópia abandonada, mesmo nome interno do form
#5) — **não** é "Venda por Vendedor/Executor O.S", que é de fato
`Kontacto\frmrelvennivfun.frm` (`VB_Name FrmRelVenNivFun`).

**Confirmação da diretriz de generalização já usada no grupo Caixa**
(Apuração de Vendas-DRE/Resumo de Venda/Descontos/Itens Vendidos, todos
2026-08-07): nesta migração `comanda`+`movimentacao` **não** é o ledger
geral de venda — é só o "envelope" de fechamento (ver
`fechamento_caixa_service.py`), exceto Contratos (exceção já confirmada,
arquitetura própria). Todo relatório do legado que lê `comanda`+
`movimentacao` com `serie_nf='CM'` foi generalizado pra ler
`pedido_venda_prod`/`pedido_venda` (situação `'PG'`) UNION `os_produto`/
`os` (situação `'PG'`) diretamente — mesmo padrão/mesmas colunas de custo
já validadas (`custo_reposicao` produto, `custo_hora` serviço no Pedido,
`custo_os` já pronto no item de O.S.). Aplicada a todos os 5 relatórios
implementados abaixo, sem exceção.

**Inconsistências reais do legado, resolvidas por decisão desta migração
(não do legado)**:
- **`situacao`**: a maioria dos 10 forms usa `comanda.situacao='PG'`
  (só pago), mas o form #7 (Venda por Vendedor/Executor) usa
  `c.situacao<>'C'` (qualquer não-cancelado) no modo Vendedor — outlier
  mesmo dentro do próprio legado. Decisão: manter `'PG'`/situação
  faturada em todos os 5 implementados, consistente com **todo** outro
  relatório já construído nesta migração (Apuração/Resumo/Descontos/Itens
  Vendidos/Itens do Pedido) — não replicar o outlier.
- **`veiculos`**: aparece em 4 dos 8 forms rastreados pelo agente (mais os
  2 já traçados por mim). Decisão: **sem Veículos** em nenhum dos 5
  implementados — mesma simplificação consciente já documentada em
  `relatorio_resumo_venda_service.py` (`pedido_venda_prod`/`os_produto`
  nesta migração só referenciam `pecas`/`servicos`, sem evidência de item
  tipo veículo nesses fluxos).
- **Custo básis**: form #1 usava `movimentacao.custo_mov` (custo no
  momento da venda), form #5 usava `pecas.custo_reposicao` (custo atual).
  Como nenhum dos dois foi implementado (ver "pulados" abaixo), não
  precisou de decisão nesta rodada — fica registrado pra quando/se
  "Vendas x Custo"/"Venda por Nível" forem retomados.

### Implementados (2026-08-07)

**Itens por Funcionário** (`Geral\FrmRelVenFun.frm`, 866 linhas) — toggle
Vendedores (Pedido, agrupado por `nome_guerra` via `pedido_venda_prod.
vendedor`/`pedido_venda.vendedor`, header sobrepõe item quando vazio,
mesma regra já usada em Descontos) / Executores (O.S., agrupado por
`os_produto.executor`) — filtros período (obrigatório) + funcionário
(opcional) + "considerar serviços" (inclui/exclui a união com
`servicos`). Sem filtro de código de fabricante do legado (marginal,
já coberto indiretamente pela busca de produto de outros relatórios).

**Ranking de Vendas** (`Geral\FrmRkgCliPro.frm`, 1787 linhas) — Top-N por
Cliente, Produto ou Vendedor, ordenável por Quantidade ou Valor, filtro
"Nº de Registros" (cap), período, vendedor, considerar serviços. **Não
portada a sub-feature "Compras"** (cruzamento com `n_fiscal_itens` de
entrada pra mostrar histórico de compra ao lado de cada produto no
ranking) — decisão consciente: é uma feature de compras enxertada dentro
de uma tela de vendas, sem pedido explícito do usuário pra portar, e our
Gestão de Compras já tem seus próprios relatórios de ressuprimento/curva
ABC que cobrem essa necessidade de outro ângulo.

**Venda por Cliente/Produto** (`Geral\FrmRelVenCli.frm` 738L +
`Geral\FrmRelVenPro.frm` 902L, unificados por decisão do usuário) — uma
tela só, toggle Cliente↔Produto (mesma consulta, `GROUP BY`/`ORDER BY`
invertido), com busca opcional de produto específico (código
fábrica/barras/descrição/código interno, mesmo fallback do legado) só
disponível no modo Produto. Lista itemizada com quebra/subtotal por
cliente (ou por produto) e total geral, período obrigatório.

**Venda por Vendedor × Nível** (`Kontacto\frmrelvennivfun.frm`, 1357
linhas) — mesmo toggle Vendedor(Pedido)/Executor(O.S.) do "Itens por
Funcionário" acima, mas agregado por **nível de produto** em vez de por
funcionário isoladamente (venda/custo/margem por nível, dentro de UM
funcionário ou geral) — reaproveita `buildNivelBreadcrumb`. Filtro de
funcionário único (sem "TODOS + quebra por funcionário" do legado — só
"todos os funcionários juntos" ou "um funcionário específico", simplifi-
cação consciente pra não empilhar 2 dimensões de agrupamento na mesma
tela).

**Venda por Região/Segmento** (`Guerengases\FrmVenTot.frm`, 847 linhas)
— generalização do "query builder dinâmico" do legado (4 dimensões
opcionais: Região/Segmento/Rota/Vendedor, cada uma podendo ser
"não filtrar"/"todos"/valor específico, com `SELECT`/`GROUP BY`
montados em string no próprio VB6) pra uma agregação fixa: sempre agrega
por todas as 4 dimensões de uma vez (`cliente.regiao`/`.segmento`/
`.rota`, `pedido_venda.vendedor`/`os_produto.executor`), retorna a lista
completa, e o FRONTEND decide quais colunas mostrar/agrupar visualmente
conforme os filtros marcados — evita replicar a montagem de SQL dinâmico
(puro workaround de VB6, ver "Não replicar truques VB6" no CLAUDE.md; a
regra real é só "group by configurável", não a técnica de concatenar
string de SQL). "SEM REGIÃO"/"SEM SEGMENTO"/"SEM ROTA"/"SEM VENDEDOR"
como label de fallback, igual ao legado.

### Pulados — pendente resposta da equipe VB6 (2026-08-07)

Por decisão explícita do usuário ("pular os 3 até ter resposta da
equipe vb 6"), os 3 relatórios abaixo **não foram implementados nesta
rodada** — aguardando confirmação de que a sobreposição com relatórios
já existentes é aceitável (ou se há alguma diferença de regra de negócio
real que eu não capturei no rastreio):

- **Vendas x Custo** (`Kontacto\FrmRelPVC.frm`, 1261 linhas) — venda ×
  custo × lucro % por nível de produto, com filtro adicional de
  documento (Fichas/Orçamento/O.S./Pedidos via `comanda_ped`/
  `comanda_orc`/`comanda_os`/`comanda_ficha`) que **nem teria como ser
  replicado fielmente** — `comanda_orc`/`comanda_ficha`/`os_ficha` não
  são gravados por nenhum service desta migração (grep confirmado,
  zero ocorrências fora de `comanda_ped`/`comanda_os` que já existem
  como link tables do Fechamento de Caixa). Sobreposição: **Resumo de
  Venda** (Caixa) já entrega venda/custo/margem por nível a partir de
  Pedido+O.S. — só falta o detalhamento produto-a-produto dentro de
  cada nível (o legado mostra, Resumo de Venda hoje só mostra o nível
  agregado).
- **Venda por Nível** (`Geral\FrmRelVenNiv.frm`, 1307 linhas) — mesmíssima
  forma (venda/custo/margem por nível, com detalhamento produto-a-produto
  dentro do nível) sem o filtro de documento do anterior. Mesma
  sobreposição com Resumo de Venda.
- **Itens Vendidos por Comanda** (`Geral\frmrelcomven.frm`, 804 linhas) —
  auditoria/conferência item-a-item por número de comanda + vendedor
  (inclusive uma faixa "vendedor=0/Ninguém", achado que parece truque de
  VB6 — `comanda.situacao` reaproveitado como alias `Nome_Guerra` pra
  esses casos — não uma regra de negócio real). Como `comanda` não é mais
  a unidade conceitual de venda nesta migração (é só o envelope de
  fechamento), o equivalente mais próximo seria "item a item por
  Pedido/O.S." — que **Itens do Pedido** e **Itens Vendidos O.S./Balcão**
  (grupo Pré Venda) já cobrem em nível agregado por produto, só sem a
  quebra por número de documento individual.

**Se a resposta da equipe VB6 confirmar que algum dos 3 tem valor real
além do que já existe**, retomar aqui — o rastreio SQL completo de cada
um já está registrado acima (via o agente de pesquisa desta sessão),
não precisa ser refeito do zero.

### Adiado — área fiscal sensível

**Vendas por Nota** (`Kontacto\FrmRelCSN.frm`, 688 linhas) — o mais
estruturalmente diferente do grupo: não soma vendas, **confronta** o
total vendido por nível contra o quanto já foi emitido em documento
fiscal (NFC-e via `comanda_nfce`/`comanda_nfce_detalhe`, NF-e via
`n_fiscal`/`n_fiscal_itens`/`comanda_nf` com `SITUACAO_NFE=1`, NF-e de
Serviço via a mesma trinca com série de serviço), mostrando o gap
"Outros" (vendido mas sem nota emitida). Todas as tabelas dependência
existem nesta migração (confirmado por grep), mas:
- É o único relatório do grupo cuja regra de negócio central é
  inteiramente sobre emissão fiscal — cai sob a seção 12 do CLAUDE.md
  ("Telas Fiscais — Fonte VB6 em Evolução Contínua"), que pede cautela
  extra e reconfirmação antes de portar regra fiscal, mesmo sendo um
  relatório só de leitura.
- Teria que decidir também de que fonte vem o "Venda" total pra
  confrontar — repetir a mesma generalização Pedido/O.S. já usada nos
  outros 5 (provavelmente correto), mas ainda não confirmado.
- Por decisão explícita do usuário (`AskUserQuestion`, "Deixar por
  último/pendente"), fica registrado aqui com o rastreio SQL completo
  (5 passos: base de venda por nível, NFS-e, NF-e, NFC-e, rollup
  hierárquico em 2 tabelas temporárias) já feito — implementar depois,
  isoladamente, não junto com o resto do grupo.

### Implementação (2026-08-07)

- **Itens por Funcionário**: `relatorio_itens_funcionario_service.py`
  (8 testes) + rota `GET /api/relatorios/itens-funcionario` + permissão
  `REL_ITENS_FUNC` + tela `relatorio-itens-funcionario.tsx` (toggle
  Vendedor/Executor, filtro funcionário opcional, considerar serviços).
- **Ranking de Vendas**: `relatorio_ranking_vendas_service.py` (8 testes)
  + rota `GET /api/relatorios/ranking-vendas` + permissão `REL_RANKING`
  + tela `relatorio-ranking-vendas.tsx` (Cliente/Produto/Vendedor,
  ordenar por Qtd/Valor, Nº de Registros, filtro vendedor/fabricante).
- **Venda por Cliente/Produto**: `relatorio_venda_cliente_produto_service.py`
  (6 testes) + rota `GET /api/relatorios/venda-cliente-produto` +
  permissão `REL_VEN_CLIPRO` + tela
  `relatorio-venda-cliente-produto.tsx` (toggle de agrupamento client-side,
  busca de produto via `ProdutoSearchModal` reaproveitado, `tipo=all`).
- **Venda por Vendedor × Nível**: `relatorio_venda_nivel_funcionario_service.py`
  (7 testes) + rota `GET /api/relatorios/venda-nivel-funcionario` +
  permissão `REL_VEN_NIVFUN` + tela
  `relatorio-venda-nivel-funcionario.tsx` (mesmo breadcrumb de nível do
  Resumo de Venda).
- **Venda por Região/Segmento**: `relatorio_venda_regiao_service.py`
  (6 testes) + rota `GET /api/relatorios/venda-regiao` + permissão
  `REL_VEN_REGIAO` + tela `relatorio-venda-regiao.tsx` (chips de dimensão
  multi-seleção, reagrupamento no backend conforme `dimensoes` CSV).
- 5 exportadores PDF/Excel novos (`export-itens-funcionario.ts`,
  `export-ranking-vendas.ts`, `export-venda-cliente-produto.ts`,
  `export-venda-nivel-funcionario.ts`, `export-venda-regiao.ts`), seguem
  o padrão já estabelecido (`print-report-header.ts`/`export-xlsx.ts`).
  Novo grupo **"Vendas"** populado em `relatorios.tsx` (5 cards, ordem
  alfabética automática).
- `tsc --noEmit`: baseline de 12 mantido (nenhum erro novo). Backend:
  1674 passed / 67 failed (baseline pré-existente inalterado) — 35 testes
  novos, todos passando. **Não testado ao vivo contra dados reais.**

### Próximos passos

1. Aguardar resposta da equipe VB6 sobre os 3 relatórios pulados (Vendas
   x Custo, Venda por Nível, Itens Vendidos por Comanda) antes de decidir
   se algum deles precisa mesmo assim de uma tela própria.
2. Retomar **Vendas por Nota** (fiscal, `Kontacto\FrmRelCSN.frm`)
   isoladamente — rastreio SQL completo já registrado acima, falta só a
   decisão de arquitetura (fonte do "Venda" a confrontar) e a implementação
   em si, com a cautela de área fiscal já descrita.
3. Validar os 5 relatórios implementados contra uma conexão real (nenhum
   foi testado ao vivo ainda) — atenção especial pro Ranking de Vendas
   (2 UNIONs por modo) e Venda por Região/Segmento (reagrupamento em
   Python, cardinalidade pequena mas nunca exercitada contra dado real).

## Painel de Relatórios (VB6) — Grupo Clientes

**Status: rastreio completo dos 3 relatórios feito (2026-08-07), os 3
implementados — mas o de "Mala Direta" saiu **bem diferente** do legado
por decisão explícita do usuário, ver abaixo.**

### Rastreio

- **Inatividade de Clientes** (`Geral\FrmRelCliSMV.frm`, 1065 linhas) —
  detecção de clientes sem compra num período, com 3 "ciclos" de
  frequência de recompra (janelas configuráveis em dias, contadas a
  partir de uma data-base por cliente ou global), campo "Acima de" que
  na prática é um PISO DE DATA (não um valor — nome enganoso do legado,
  replicado como está por fidelidade ao rótulo mas com comportamento
  correto), e 2 sub-checks de faturamento de Contrato.
- **Listagem de Clientes** (`Geral\FrmRelClie.frm`, 692 linhas) — 6 modos
  de filtro (Código/CPF-CNPJ/Nome/Data Cadastro/Data Nascimento/Tipo) +
  PF/PJ por tamanho de `cgc_cpf`. Achado: o "Tipo" do legado é
  `cliente.tipo`, uma coluna que **não existe nesta migração** —
  generalizado pra `cliente.cliente_forn` (a FK real de tipo_cliente, já
  usada em todo o resto do sistema).
- **Mala Direta** (`Geral\FrmMalDir2.FRM`, 2741 linhas) — no legado,
  imprime etiqueta de endereço em folha Pimaco (mesmo mecanismo GDI de
  `FrmEtqProd.frm`, 4 formatos fixos + um modo "Personalizado" de texto
  livre repetido), com 4 modos de seleção de destinatário (Clientes —
  Todos/Aniversário/Data Cadastro/Tipo —, Clientes que Compraram,
  Fornecedores, Clientes e Fornecedores).

### Decisões do usuário (2026-08-07, várias rodadas de `AskUserQuestion` +
mensagens diretas) — **mudança de arquitetura real, não só de UI**

1. **Mala Direta perdeu a impressão de etiqueta por completo** — "retire
   envio por etiqueta e me surpreenda com o envio por email e whatsapp".
   Não imprime mais nada; seleciona destinatário (Clientes: Todos/
   Aniversário dia-mês/Data Cadastro/Tipo Cliente; + Fornecedores; ambos
   juntos) e dispara envio em massa. Fora do escopo desta rodada:
   "Clientes que Compraram" (cruzamento com Pedido+O.S., mais complexo)
   e "Etiqueta Personalizada" (não faz mais sentido sem impressão).
2. **Novo recurso reutilizável `envio_massa_service.py`** (backend) +
   `EnvioMassaModal.tsx` (frontend) — pedido explícito do usuário: "esse
   recurso de envio vai ser introduzido em consulta de clientes entre
   outros" e "use metodologia atuais de envio". **Não reinventa nada** —
   reaproveita exatamente a infraestrutura já existente e testada:
   - **WhatsApp**: `services/whatsapp/service.py`, `document_type='CLI'`
     — o mesmo motor já usado pela tela de Telemarketing pra mensagem
     avulsa a um cliente (histórico, retry, config/provider já prontos).
     Escopo: só Cliente (o motor `CLI` só resolve contra a tabela
     `cliente`, confirmado em `whatsapp/repository.py` — não dá pra
     mandar WhatsApp pra Fornecedor sem estender esse motor, não feito
     aqui).
   - **E-mail**: `services/email_cobranca_service.py` (`enviar_email`) —
     SMTP puro já usado no envio de cobrança
     (`Controle do Sistema > aba Outros > Configuração de Emails`).
     Funciona pra Cliente E Fornecedor (ambos têm `e_mail` próprio).
   - `envio_massa_service.py` só faz o LOOP pelos destinatários + um
     render simples de `{nome}` na mensagem/assunto/corpo — não tenta
     reconstruir a partir do template de documento do WhatsApp (pensado
     pra Pedido/OS, com `{itens}`/`{total}`, que não fazem sentido numa
     campanha de marketing).
   - Rotas: `POST /api/envio-massa/whatsapp` e `/email`, ambas com log de
     auditoria (`tela=ENVIO_MASSA`). **Este recurso ainda NÃO foi
     conectado a nenhuma tela de Consulta de Clientes** (só Mala Direta e
     Inatividade de Clientes, que já existiam nesta rodada) — o
     componente `EnvioMassaModal` já está pronto pra isso (só precisa de
     `{codigo, nome, email?, tem_telefone?}[]`), fica como próximo passo
     natural quando pedido.
3. **Inatividade de Clientes ganhou ação "Enviar WhatsApp em massa"**
   sobre os clientes encontrados (reengajamento), reaproveitando o mesmo
   `EnvioMassaModal` — usuário confirmou explicitamente.
4. **Decisão própria desta migração, sem precedente no legado**: todo
   modo de seleção da Mala Direta (Clientes e Fornecedores) exige
   `situacao = 'A'` — envio de verdade (ao contrário de imprimir uma
   etiqueta que pode simplesmente não ser usada) não deveria alcançar
   cadastro inativo/cancelado por padrão. Reavaliar se pedido o
   contrário.

### Achados técnicos confirmados durante a implementação

- `contratos.situacao` usa 'A'/'F' (Aberto/Finalizado) nesta migração —
  diferente do texto livre do legado (`Left(SituacaoContrato.Text,1)`).
- **Divergência real de série confirmada**: o legado filtra
  `receber.serie='CM'` pro sub-check "último faturamento de contrato
  pago", mas `_faturar_contratos_sync` desta migração grava com
  `serie='CO'` — usado o valor real desta migração, não o do legado.
- `Receber`/`Duplicata_Receber`/`Duplicata_Rec_Venc`/`Duplicata_Rec_Nf`
  (incl. `duplicata_rec_venc.data_pag`) e `comanda_contrato` — todos
  confirmados reais e já usados pelo módulo Contratos/CNAB.
- "Ciclos" de frequência de recompra ficaram fiéis ao legado — só contam
  `pedido_venda` (não O.S.), mesmo antes desta migração generalizar o
  resto do relatório.

### Implementação (2026-08-07)

- **`envio_massa_service.py`** (5 testes) + `routes/envio_massa.py`
  (`POST /api/envio-massa/whatsapp`, `/email`).
- **Listagem de Clientes**: `relatorio_listagem_clientes_service.py`
  (10 testes) + rotas em `routes/relatorio_clientes.py` + permissão
  `REL_LIST_CLI` + tela `relatorio-listagem-clientes.tsx` +
  `export-listagem-clientes.ts` (PDF busca contato/endereço por cliente
  sob demanda, fiel à diferença real Imprimir vs. Gerar Planilha do
  legado).
- **Inatividade de Clientes**: `relatorio_inatividade_clientes_service.py`
  (10 testes) + permissão `REL_INAT_CLI` + tela
  `relatorio-inatividade-clientes.tsx` (com botão "Enviar WhatsApp") +
  `export-inatividade-clientes.ts`.
- **Mala Direta**: `mala_direta_service.py` (7 testes) + permissão
  `MALA_DIRETA` + tela `mala-direta.tsx` (sem exportador de impressão —
  não imprime mais nada).
- **`EnvioMassaModal.tsx`** (novo componente reutilizável,
  `frontend/src/components/`) — canal WhatsApp/E-mail, template com
  `{nome}`, resultado por destinatário.
- Novo grupo **"Clientes"** em `relatorios.tsx` (3 cards, ordem
  alfabética automática).
- `tsc --noEmit`: baseline de 12 mantido. Backend: 1720 passed / 67
  failed (baseline pré-existente inalterado) — 32 testes novos, todos
  passando. **Não testado ao vivo** — atenção especial: nenhum envio de
  WhatsApp/e-mail de verdade foi disparado ainda (só testado com mocks
  nos testes unitários); confirmar credenciais/configuração antes de
  usar em produção.

### Próximos passos

1. Conectar `EnvioMassaModal` numa tela de Consulta/Cadastro de Clientes
   (pedido explícito do usuário, ainda não feito — só precisa passar
   `destinatarios: [{codigo, nome, email?, tem_telefone?}]`, componente já
   pronto).
2. Testar envio real de WhatsApp e e-mail em massa contra uma conexão de
   teste antes de liberar pra produção.
3. Se pedido no futuro: "Clientes que Compraram" (Mala Direta) e a
   integração de "Grade" nos filtros — nenhum dos dois foi rastreado a
   fundo nesta rodada por estarem fora do escopo aprovado.

## KPDV — Migração da Tela de Vendas (Checkout) para C#/.NET/WPF

**Status: análise de viabilidade feita (2026-08-08), nenhuma linha de
código C# escrita ainda.** Pedido do usuário: migrar a "tela de vendas"
pra um app desktop nativo separado, nome **KPDV (Kontacto PDV)**, em
C# + .NET + WPF — motivado por acesso mais fácil a periféricos (balança,
impressora térmica, etc.) do que a stack atual permite.

### Escopo — qual tela é "a tela de vendas"

Confirmado: é o **Checkout** (`frontend/app/checkout.tsx`, migração de
`Geral\FrmPafOFF.frm` — "Emissão de Cupom Fiscal", o PDV/venda direta de
balcão do legado, ver [[project_checkout]]). Não é Pedido Bar/Pedido
Geral/O.S. (pré-venda) — é especificamente a tela de venda imediata,
onde faz sentido pensar em balança/impressora térmica no ato da venda.

### Confirmações de arquitetura (usuário, 2026-08-08)

- **Backend**: KPDV consome a mesma API Python (FastAPI) já em
  desenvolvimento neste projeto — confirma a premissa já usada na análise
  de viabilidade, nenhuma mudança de backend necessária.
- **Busca de Produtos/Serviços — SEM modal, inline no campo.** Diferente
  do padrão já estabelecido no frontend web (`ProdutoSearchModal`/
  `ClientSearchModal` — digitar + Enter abre um modal de seleção quando
  há 0 ou 2+ resultados, ver regra `[GLOBAL]` "Campos de identidade
  precisam de mecanismo de busca" em CLAUDE.md), o KPDV usa um padrão
  **typeahead/autocomplete ancorado no próprio campo** — resultado
  aparece direto abaixo do campo de busca enquanto digita, navegável por
  teclado (↑/↓/Enter/Esc), sem nunca abrir uma janela/diálogo separada.
  Motivação explícita: velocidade — é o fluxo mais crítico da tela (a
  cada item vendido), um modal quebraria o ritmo do operador de caixa.
  Em WPF, o equivalente é um `Popup`/`ListBox` não-modal ancorado sob o
  `TextBox` (mesma árvore visual, sem `Window` nova) — WPF-UI não tem um
  `AutoSuggestBox` pronto no momento desta análise, mas o padrão é
  simples de montar com `Popup` + `ListBox` + navegação de teclado
  manual.
  - **Mockup interativo desta busca já publicado** (Artifact HTML/CSS,
    ver "Mockup visual" na memória do projeto) — campo "Pesquisar por
    código, descrição ou GTIN" filtra a lista de produtos ao digitar,
    mostra um painel flutuante ancorado sob o campo (não modal), com
    navegação por teclado e "Enter" adicionando o item direto à venda —
    é a referência de interação, não só de aparência.
  - Esta regra é específica do KPDV — não estende automaticamente pro
    resto do frontend web (que continua usando o padrão modal já
    validado em produção lá).
- **O screenshot "ShopPdv" usado como referência inicial era só um
  exemplo de inspiração**, não uma especificação a seguir literalmente —
  confirmado pelo usuário. O mockup publicado (ver memória) reflete a
  interpretação/adaptação pra marca Kontacto, não uma cópia pixel-a-pixel
  do exemplo.

### Login e permissões (usuário, 2026-08-08)

- **Tela de login do KPDV**: ao abrir, solicita **conexão** (servidor/
  banco — mesmo conceito já usado no frontend web, `listConnections()`/
  tela de Conexões, hoje uma lista local por instalação) + **usuário** +
  **senha**. Usa o mesmo `POST /api/login` já existente — `LoginResponse`
  já devolve `usuario`/`funcionario` (inclui `classe`, usado a seguir pra
  resolver permissões), nenhuma mudança de backend necessária.
- **Toda administração de permissão continua sendo feita pelo frontend
  React** — o KPDV **não terá tela própria de gestão de permissões**.
  Quem concede/revoga o que cada grupo pode fazer no KPDV é a tela
  Permissões já existente (`frontend/app/permissoes.tsx` +
  `GET/POST /api/permissoes*`). O KPDV só **consome** essas permissões
  (mesmo fluxo já usado no React: login → `classe` do usuário →
  `GET /api/permissoes?classe=X` → gate de UI equivalente ao `can()` do
  hook `usePermissions()`), nunca as edita.
  - **O catálogo de permissões já tem a tela certa pra isso**: a tela
    `CHECKOUT` já existe no catálogo (`permissoes_service.py`,
    `ACOES_CHECKOUT` — `ABRIR`/`ADD_ITEM`/`DEL_ITEM`/`DESC_ITEM`/
    `DESC_GERAL`/`FECHAR`/`CANCELAR`) porque o Checkout web já usa essas
    mesmas ações. Como o KPDV assume literalmente a mesma tela/regra de
    negócio, a expectativa é que ele reaproveite a MESMA chave `CHECKOUT`
    no catálogo — não uma tela nova — a menos que surja uma ação
    genuinamente exclusiva do KPDV (ex.: algo ligado só a periférico)
    que precise de um `BOTAO` próprio.
- **O Checkout deixará de existir no frontend React** — confirmado pelo
  usuário: "não existirá mais a tela de vendas no frontend React". É uma
  substituição completa, não convivência (resolve o ponto em aberto #3
  já registrado na análise de viabilidade). **Reconfirmado explicitamente
  2026-08-10** ("KPDV não convive com checkout web. Só existirá o KPDV."),
  em resposta direta à pergunta ainda listada como "em aberto" na seção
  acima — a lista de pontos em aberto não tinha sido atualizada quando
  esta decisão foi tomada originalmente, causando essa reabertura
  aparente; já corrigido lá. **Isto é uma decisão de
  destino, não uma instrução pra remover o código agora** — `checkout.tsx`
  e toda a árvore de componentes ligada (`FecharVendaModal.tsx`,
  `DavPendentesModal.tsx`, `ConfiguracaoImpressaoModal.tsx`,
  `DemonstrativoCupomFiscal.tsx`, `AbastecimentoModal.tsx`,
  `AgendamentoModal.tsx`) continuam sendo a ÚNICA tela de venda em
  produção até o KPDV existir de verdade e atingir paridade de
  funcionalidade — remover agora deixaria o negócio sem PDV nenhum. A
  remoção do Checkout web fica registrada aqui como passo FUTURO,
  condicionado ao KPDV estar pronto pra substituir, não antes.
  - **Implicação prática pra daqui pra frente**: novo trabalho de venda de
    balcão (regra de negócio nova, ajuste de fluxo) deve mirar o KPDV
    primeiro — o Checkout web só recebe manutenção mínima/correção de bug
    enquanto continuar sendo a única coisa em produção, não deve ganhar
    funcionalidade nova a partir de agora, pra não duplicar esforço numa
    tela com prazo de vida definido.

### Remoção do Checkout web (2026-08-10) — EXECUTADA

Pedido explícito do usuário: "elimine o checkout web do projeto." Removido:

- `frontend/app/checkout.tsx` (a tela em si).
- `frontend/src/components/checkout/` inteiro — `AbastecimentoModal.tsx`,
  `AgendamentoModal.tsx`, `ConfiguracaoImpressaoModal.tsx`,
  `DavPendentesModal.tsx`, `DemonstrativoCupomFiscal.tsx`,
  `FecharVendaModal.tsx` — confirmado por grep que **nenhum outro arquivo
  do frontend importava nada desse diretório** (exclusivo de
  `checkout.tsx`, seguro remover a árvore inteira).
- Tile "Checkout" removido de `frontend/app/(tabs)/transacoes.tsx`
  (apontava pra rota `/checkout`, que deixou de existir).

**Deliberadamente NÃO removido** (é "Checkout **web**", não "Checkout" —
o backend é infraestrutura COMPARTILHADA que o KPDV consome pra valer):
- `backend/services/checkout_service.py` + `backend/routes/checkout.py` +
  `backend/tests/unit/test_checkout_service.py` — o KPDV fala com esses
  MESMOS endpoints (`/api/checkout/*`); removê-los quebraria o KPDV por
  completo.
- Permissão `CHECKOUT` no catálogo (`permissoes_service.py`) — decisão já
  registrada acima ("Login e permissões"): o KPDV reaproveita literalmente
  a mesma chave/ações, não ganha uma tela nova no catálogo.
- `frontend/src/utils/reciboTexto.ts` — utilitário genérico, desenhado
  desde o início pra ser reaproveitável por qualquer tela ("não só
  Checkout"), sem acoplamento exclusivo à tela removida.
- Referências a `tipo === "CHECKOUT"` em `useDashboard.ts`/
  `PedidosTable.tsx` (Tela Principal) — isso é sobre DADOS históricos de
  vendas (`comanda.tipo`), não sobre a tela; o KPDV continua gravando
  vendas com esse mesmo tipo, então o dashboard precisa continuar sabendo
  exibi-las.
- `print-agent/` e a fila `impressao_fila`/`impressao_service.py` — infra
  compartilhada, não exclusiva do Checkout web, fora do pedido explícito.

**Verificação**: `tsc --noEmit` → mesmos 12 erros de baseline
pré-existentes, nenhum novo, nenhum erro de import quebrado (confirma que
a remoção não deixou nada pendurado). Arquivos removidos via `rm` (não
`git rm`/commit) — reversível com `git checkout HEAD -- <caminho>` se
precisar, nenhum commit foi feito nesta sessão.

### Ícone de conexão — restrito aos "3 Magníficos" (usuário, 2026-08-08)

KPDV terá um **ícone de conexão** (acessa/altera a configuração de
servidor+banco do terminal) visível só pros **"3 Magníficos"** — mesmo
apelido e mesmo critério já usado no Checkout web pro ícone "engrenagem"
de configuração de impressão (ver [[project_checkout]]): **Gerente ou
Supervisor por função (`funcionarios.cod_funcao` 01/02) OU usuário
Master**. Critério exato já implementado em
`frontend/src/permissions/index.tsx` (`isManagerFuncao = isMaster ||
codFuncao === 1 || codFuncao === 2`, `isMaster = usuario.master===true
OU usuario.usuario.toUpperCase()==='KONTACTO'`) — **nenhum endpoint
novo necessário**, tanto `usuario.master`/`usuario.usuario` quanto
`funcionario.cod_funcao` já vêm prontos no `LoginResponse` do
`POST /api/login`, então o KPDV replica a mesma conta booleana em C# a
partir do que a própria tela de login já recebeu.

Motivação implícita (mesmo raciocínio do ícone de impressão): trocar
servidor/banco por engano ou por má-fé (operador de caixa comum) é um
risco real — venda podendo ir pro banco errado — então só quem já tem
autoridade operacional (gerência) deve poder mexer nisso; é uma trava de
função, não uma permissão granular do catálogo.

### Achado do rastreio: balança NÃO existe no legado

Busca exaustiva em `FrmPafOFF.frm` e na árvore `Geral\` inteira por
qualquer integração de balança/porta serial (`MSComm`, `RS232`) —
**nenhuma ocorrência real** (os únicos matches de "balanc*" eram
"balanço" contábil/inventário, falso positivo). **Balança é
funcionalidade nova, sem regra de negócio legada pra replicar** — precisa
de definição de requisitos própria (modelo/protocolo) antes de
implementar, não é rastreio de VB6.

Impressão no legado é via `Printer` (GDI/driver do Windows, mesmo
mecanismo já visto em `FrmEtqProd.frm`/`FrmMalDir2.FRM`), não ESC/POS
cru. TEF existe (`USA_TEF`, `TEF_Hora`, `TEF_ValorPago`, `TEF_Transacao`,
`TEF_NumeroCupom`) mas a chamada externa (DLL tipo `CliSiTef.dll`) não
foi rastreada a fundo nesta rodada — TEF real já estava adiado no
Checkout web também (ver [[project_checkout]]).

### Por que WPF resolve o problema de verdade (não é só "mais uma tentativa de desktop")

Este projeto já tentou desktop nativo uma vez — `react-native-windows`,
ver "Platform Scope" em CLAUDE.md — e **pausou especificamente por causa
de acesso a periférico**: o motivador original (enumeração automática de
impressoras) acabou não precisando de RNW, e o resultado prático foi
construir um workaround via HTTP (o **print-agent**, ver
[[project_impressao_silenciosa]]) — um processo Python separado rodando
na máquina cliente, fazendo *polling* numa fila (`impressao_fila`) porque
o navegador não tem acesso à porta USB local. Funciona, mas é indireto:
2 processos, fila, latência de polling.

**C#/.NET/WPF resolve isso nativamente, sem indireção**:

| Periférico | Stack atual (web/RNW) | WPF nativo |
|---|---|---|
| Impressora térmica (USB local) | Fila + agente Python fazendo polling + `win32print` RAW | `System.Drawing.Printing`/P-Invoke direto no spooler, OU bibliotecas ESC/POS maduras (ex. `ESC POS .NET`) — **sem fila, sem 2º processo, imprime síncrono no fechar da venda** |
| Balança (serial/COM) | Inviável — Web Serial API tem suporte limitado, nunca tentada; RNW exigiria native module próprio (mesmo tipo de trabalho que já pausou o RNW) | `System.IO.Ports.SerialPort` — acesso trivial e nativo, um dos usos mais documentados da classe |
| Leitor de código de barras | Já funciona (HID keyboard-wedge, Enter-driven) | Idêntico — não é diferencial, mas não regride |
| Gaveta de dinheiro | Depende da impressora (pulso ESC/POS) | Resolvido junto com a impressora |
| TEF | Adiado (Checkout web nunca implementou) | P/Invoke pra DLL nativa (`CliSiTef.dll`/PayGo) é natural em C#; em RN exigiria native module Windows |

### O que se aproveita do que já foi construído

- **Backend inteiro, sem mudança nenhuma.** A API HTTP já é agnóstica de
  frontend (mesmo raciocínio já documentado no CLAUDE.md pro RNW —
  "talking to the same Python HTTP API — no backend changes needed").
  `checkout_service.py` inteiro — formas de pagamento múltiplas, Vale de
  Devolução, Cartão Presente, checagem de Taxa NFCe, importar Pedido/O.S.
  como DAV, Abastecimento/Agenda — já rastreado, testado (67 testes) e
  100% reaproveitável.
- **`/api/login`** já existe e serve pro KPDV autenticar sem mudança —
  CORS (`allow_origins=["*"]`) nem é relevante aqui, é um conceito só de
  navegador; um `HttpClient` nativo do .NET não é afetado por CORS de
  jeito nenhum.
- **UX já validada com o usuário** (não código, mas especificação viva):
  campo Código como único foco + Enter inclui direto, destaque do item
  recém-lançado, grade Descrição/Qtd/Unit./Total, rodapé de totais — todo
  esse desenho de interação (`checkout.tsx`/`DemonstrativoCupomFiscal.tsx`)
  já foi discutido e ajustado com o usuário, reduz bastante retrabalho de
  UX mesmo que o código TypeScript em si não sirva pra WPF.
- **print-agent continua sendo a solução certa pras OUTRAS telas** que
  não têm plano de virar desktop nativo (Pedido Bar, Pedido Geral, O.S.)
  — migrar o Checkout pro KPDV não invalida esse trabalho, só o torna
  desnecessário especificamente pra esta tela.

### Pontos em aberto (decisões do usuário, não técnicas)

~~1. **Modelo/protocolo de balança** a suportar~~ — **RESOLVIDO
   2026-08-10**: Toledo, modo compatível. Implementado best-effort (ver
   "Balança Toledo + Pré-Pesagem" abaixo) — ainda precisa de validação
   contra hardware físico real, mas a decisão de qual protocolo perseguir
   está tomada.
2. **TEF entra no escopo do KPDV desde já** ou fica adiado como já estava
   no Checkout web? — ainda em aberto.
~~3. **KPDV convive com o Checkout web** ou **substitui por completo**?~~ —
   **RESOLVIDO 2026-08-08** (registrado abaixo em "Login e permissões",
   só não tinha sido refletido aqui), **reconfirmado explicitamente pelo
   usuário em 2026-08-10** ("KPDV não convive com checkout web. Só
   existirá o KPDV.") **e EXECUTADO no mesmo dia** — usuário pediu
   explicitamente pra eliminar o Checkout web do projeto, não é mais só
   decisão de destino. Ver "Remoção do Checkout web" logo abaixo.
4. **Distribuição/atualização** do KPDV nas lojas — **infraestrutura de
   auto-update IMPLEMENTADA 2026-08-10** (ver "Distribuição — Velopack"
   abaixo). Das 2 sub-decisões, 1 já **RESOLVIDA no mesmo dia**:
   ~~(a) framework-dependent vs. self-contained~~ → **self-contained**
   (script já ajustado, virou o padrão). Continua aberta: (b) ONDE a fonte
   de atualização física vai morar (pasta de rede entre as lojas? servidor
   HTTP central?) — o painel "Atualização" do KPDV já aceita qualquer um
   dos dois formatos, só falta a decisão de infraestrutura em si.

### Recomendação

Tecnicamente viável, e resolve de forma definitiva e nativa exatamente os
2 problemas que motivaram a pausa do react-native-windows. Nenhuma mudança
de backend necessária. O trabalho real é: (a) reconstruir a UI em XAML
consumindo os mesmos endpoints REST já existentes e testados, (b)
implementar 2 módulos de periférico em C# (impressão ESC/POS direta,
leitura serial de balança), (c) decidir os 4 pontos em aberto acima com o
usuário antes de começar a implementação.

### Direção visual — "aparência bastante atual" (pedido do usuário, mesmo dia)

WPF puro (sem biblioteca extra) tem os controles padrão do .NET Framework
clássico — cinza, chrome datado, nada "atual". Pra atingir a aparência
pedida sem trocar de framework (o usuário pediu WPF, não WinUI3/UWP),
a rota é uma **biblioteca de estilos Fluent para WPF por cima do WPF
padrão**:

- **Recomendação: [WPF-UI](https://github.com/lepoco/wpfui)** (`lepoco/wpfui`,
  ativamente mantida) — aplica o Fluent Design real do Windows 11 (cantos
  arredondados, fundo Mica/acrylic na janela, `NavigationView`, ícones
  Fluent, snackbar/toast, tema claro/escuro/automático do sistema) em
  cima do WPF puro — não é WinUI3, continua sendo WPF, só com o visual
  atualizado.
  - Alternativas consideradas: **ModernWpfUI** (mesma ideia, menos
    ativa), **MaterialDesignInXamlToolkit** (visual Material/Android, não
    "nativo Windows"), **HandyControl** (rico em controles tipo
    dashboard, bom pra telas densas de dados), **MahApps.Metro** (visual
    "Metro" da era Windows 8, hoje já datado comparado ao Fluent do
    Windows 11).
- **Continuidade de marca com o resto do sistema (web/mobile)**: reaproveitar
  a paleta já definida em `frontend/src/theme/colors.ts` em vez do azul
  padrão do Fluent — `brandPrimary #0B2A5B` (navy) como cor de destaque,
  `surface #F4F6FB`/`surfaceSecondary #FFFFFF` como fundos, `radius.md
  12px` pros cantos de card, `spacing` (4/8/12/16/24/32) como escala de
  espaçamento. O KPDV deve parecer parte da mesma família visual do
  Kontacto, não um app à parte.
- **Contexto de PDV**: botões grandes/tocáveis (mesmo em desktop, o
  operador de caixa costuma usar mouse/touch rápido, não precisão fina),
  alto contraste pro ambiente de loja, tipografia Segoe UI Variable
  (fonte padrão do Windows 11, incluída pelo WPF-UI).
- Tema claro/escuro/automático do sistema já vem de graça com WPF-UI —
  vale oferecer, mesmo que o padrão operacional de PDV normalmente seja
  tema claro.

Ainda não decidido nem prototipado — fica registrado como direção pra
quando a implementação começar.

### Considerações técnicas WPF (checklist do usuário, mesmo dia)

Pontos que precisam de decisão de arquitetura ANTES de começar a
implementação (nenhum decidido ainda, só mapeados):

- **Renderização de fontes**: `TextOptions.TextFormattingMode` —
  `Display` (pixel-snapped, mais nítido a 100% de escala) vs `Ideal`
  (correto em telas com DPI fracionário/escalado, mais consistente entre
  terminais de loja diferentes). Terminal de PDV varia muito de hardware
  — tender pra `Ideal` + `TextRenderingMode=ClearType`, mas validar contra
  os monitores reais das lojas antes de fixar.
- **XAML**: padrão MVVM (View em XAML "burro", lógica em ViewModel,
  nunca code-behind com regra de negócio) — mesma separação de
  responsabilidade já praticada no React (`checkout.tsx` = orquestração,
  `DemonstrativoCupomFiscal.tsx` = apresentação). UserControl por seção
  da tela, espelhando a modularização já validada no frontend web.
- **Recursos dinâmicos**: `DynamicResource` só onde precisa mudar em
  runtime (troca de tema claro/escuro do WPF-UI) — tem custo de lookup a
  cada acesso. `StaticResource` (resolvido uma vez, mais rápido) pra tudo
  que não muda em runtime (tamanhos fixos, brushes não-temáticos).
- **Entrada de dados**: a UX inteira do Checkout web já é construída em
  cima de "campo Código é o único foco necessário, Enter inclui o item
  direto, foco volta sozinho" (ver [[project_checkout]]) — replicar via
  `PreviewKeyDown`/`InputBindings` pro Enter (inclusive o Enter automático
  de leitor de código de barras HID) + gestão explícita de foco
  (`FocusManager`), não widgets de captura genéricos.
- **Cache**: tabelas de apoio (funcionários, formas de pagamento, produto
  buscado) devem ser cacheadas em memória no processo do KPDV, buscadas
  uma vez e reaproveitadas — mesmo padrão já usado no frontend web (listas
  carregadas uma vez no mount, não a cada tecla). `BitmapCache`/`CacheMode`
  só se algum visual pesado (ícone/gradiente) causar lag perceptível em
  grade rolável — não otimizar isso de antemão sem medir.
- **Arrays**: lista de itens da venda deve ser `ObservableCollection<T>`
  (notifica a UI sozinha em Add/Remove), não `List<T>` — evita
  implementar `INotifyCollectionChanged` na mão.
- **Diálogos**: `Window.ShowDialog()` clássico (modal, bloqueia a janela
  pai) só pra confirmação que realmente precisa bloquear (ex.: código do
  Cartão Presente/Vale de Devolução). Pra aviso não-bloqueante (equivalente
  ao `ScreenToast`/`useFeedback` do web — ver "Mensagens de sistema" em
  CLAUDE.md), usar Snackbar/InfoBar do WPF-UI, não uma segunda `Window` —
  mesmo princípio já `[GLOBAL]` no resto do sistema: mensagem de sistema
  nunca trava a tela sem necessidade real.
- **Automação da interface**: todo controle relevante ganha
  `AutomationProperties.AutomationId` (equivalente direto do `testID` já
  usado em toda tela React deste projeto) — viabiliza teste automatizado
  futuro (WinAppDriver/FlaUI) e acessibilidade (leitor de tela), mesma
  disciplina já seguida no resto do sistema, não uma prática nova.
- **Conversões de pixel/DPI**: WPF trabalha em pixels independentes de
  dispositivo (1 DIP = 1/96"), mas terminal de loja varia de escala
  (100/125/150/200%, comum em hardware touch de PDV) — manifest precisa
  declarar **Per-Monitor V2 DPI awareness** (crítico se o KPDV rodar com
  monitor do operador + monitor voltado pro cliente, cada um podendo ter
  DPI diferente), e todo layout deve ser medido em DIP, nunca pixel de
  tela cru — testar os botões grandes/tocáveis em mais de uma escala
  antes de fixar tamanho.

### Versão do .NET e requisitos não-funcionais (decisão do usuário, mesmo dia)

**Target: .NET 10 (LTS), não .NET 11.** Decisão explícita do usuário:
".NET 11 ainda está em Preview [na época deste registro] — ficar no .NET
10 LTS" — segue o padrão real de release do .NET (versões pares =
LTS/3 anos de suporte, ímpares = STS/18 meses; .NET 11 só vira estável em
novembro, ~1 ano depois do .NET 10). TFM do projeto:
`net10.0-windows` (WPF sempre precisa do sufixo `-windows`, não existe
`net10.0` puro pra WPF). **Verificar na hora de implementar** se WPF-UI
(biblioteca recomendada acima) já publica build compatível com .NET 10
antes de fixar a versão do pacote — não assumido/confirmado ainda, só
verificável quando o projeto for criado de fato.

**"Leve, responsiva e estável"** — 3 requisitos não-funcionais explícitos
do usuário, com implicação técnica direta:

- **Leve**: mínimo de dependências além do essencial (WPF-UI +
  `HttpClient`, sem framework de DI pesado se não for necessário — o
  `Microsoft.Extensions.DependencyInjection` já é leve e idiomático o
  bastante se precisar). Decisão de deployment framework-dependent
  (runtime .NET 10 pré-instalado na loja) vs. self-contained (maior,
  mas não depende de nada instalado) fica pro momento de decidir
  distribuição (ver ponto 4 já registrado acima) — self-contained tende
  a contradizer "leve" em tamanho de instalador, mas é mais robusto pra
  loja sem runtime já presente; avaliar então.
- **Responsiva**: nunca bloquear a UI thread — toda chamada ao backend
  via `async`/`await` real (nunca `.Result`/`.Wait()` síncrono em cima de
  `Task`, armadilha clássica de deadlock em WPF), debounce em busca de
  produto "ao digitar" (mesmo princípio já usado no frontend web —
  350ms de debounce nas buscas de cliente/produto/fornecedor), UI nunca
  "trava" esperando rede — precisa de indicador de carregando (mesmo
  princípio `[GLOBAL]` "Feedback visual em processos demorados" já
  aplicado no resto do sistema).
- **Estável**: tratamento robusto de falha de rede (a loja pode ter rede
  instável, backend pode estar temporariamente fora) — política de
  retry (`Polly` é a biblioteca padrão de mercado pra isso em .NET, leve
  o bastante pra não contradizer o requisito anterior), handler global
  de exceção não tratada (`Application.DispatcherUnhandledException`)
  pra nunca deixar o app fechar sozinho no meio de uma venda, e cuidado
  especial pra uma venda nunca ficar "presa" num estado intermediário se
  a rede cair no meio do fechamento.

Nenhuma dessas decisões foi implementada ainda — ficam registradas como
requisito orientador pra quando o projeto KPDV for criado de fato.

### Implementação — 1ª fase (2026-08-08)

**Status: projeto WPF real criado, compila e roda.** Solução em
`C:\Desenv\KPDV\` (fora do repositório APPIAREACT — projeto irmão,
consome a mesma API, não faz parte deste monorepo). `dotnet build`:
**0 erros, 0 avisos**. Processo testado (`Start-Process` +
`Get-Process`): abre e fica de pé com o título "KPDV — Kontacto PDV" —
confirma que DI, tema Fluent, `App.xaml`/`Brand.xaml` e a `LoginView`
inicial carregam sem exceção. **Não testado visualmente** (tentativa de
screenshot pegou a janela errada por engano — descartada, não repetida;
ver nota de segurança abaixo) nem testado com login real de ponta a
ponta (precisa de usuário/senha reais, que não estão disponíveis nesta
sessão) — só a conectividade/contrato dos endpoints foi verificada
contra o backend rodando (`curl`/leitura direta do código-fonte antes de
implementar, não suposição).

**Achado que corrige a análise anterior**: o pacote NuGet `WPF-UI`
4.3.0 (`lepoco/wpfui`) **já publica build oficial pra `net10.0-
windows7.0`** — confirmado inspecionando o pacote instalado
(`lib/net10.0-windows7.0/Wpf.Ui.dll`). A ressalva "verificar na hora de
implementar" registrada na análise de viabilidade está resolvida:
compatível, sem downgrade de target framework necessário. Também
corrige outra suposição anterior: **o WPF-UI 4.3.0 já tem um
`AutoSuggestBox` nativo** (`Wpf.Ui.Controls.AutoSuggestBox`, API estilo
WinUI — `TextChanged`/`SuggestionChosen`/`OriginalItemsSource`) — não
precisou montar `Popup`+`ListBox` na mão como a análise original previa;
o controle pronto já entrega exatamente o comportamento pedido (busca
inline, sem modal, ancorada no campo).

**Estrutura do projeto** (`src/KPDV/`):
- `Models/` — DTOs espelhando 1:1 os contratos reais do backend
  (`LoginModels.cs`, `PermissoesModels.cs`, `ProdutoModels.cs`,
  `CheckoutModels.cs`, `Conexao.cs`) — cada campo conferido contra o
  código-fonte Python antes de escrever o C# (`auth_service.py`,
  `permissoes_service.py`, `produtos_service.py`,
  `checkout_service.py`/`models/schemas.py`), não suposto. JSON usa
  `JsonNamingPolicy.SnakeCaseLower` global (`ApiClient`) em vez de
  `[JsonPropertyName]` por campo — `codigo_int`↔`CodigoInt` etc. convertido
  automaticamente.
- `Services/` — `ApiClient` (HTTP genérico, `BaseUrl` dinâmico por conexão,
  erros de rede viram `ApiConnectionException` com mensagem amigável —
  requisito "estável"), `AuthService`, `SessionService` (`IsMaster`/
  `IsManagerFuncao` — réplica exata de `frontend/src/permissions/
  index.tsx`), `PermissoesService` (`Can(key)` — réplica exata do `can()`
  React, master bypassa, senão checa chave exata ou `TELA.ABRIR`),
  `ConexaoStore` (persistência local em `%AppData%\KPDV\connections.json`),
  `ProdutoService` (busca fuzzy pro painel inline,
  `GET /produtos-servicos`), `CheckoutService` (abrir venda, resolver
  produto exato, incluir item, obter venda — `GET/POST /checkout/*`).
- `ViewModels/` — `LoginViewModel`, `VendaViewModel`, `ItemVendaLinha` —
  `CommunityToolkit.Mvvm` (`ObservableObject`/`[ObservableProperty]`/
  `[RelayCommand]`, requisito "leve": sem boilerplate de
  `INotifyPropertyChanged` manual).
- `Views/` — `LoginView.xaml` (Conexão + Usuário + Senha, formulário de
  "nova conexão" inline quando não há nenhuma salva), `VendaView.xaml`
  (busca inline via `ui:AutoSuggestBox` + grade de itens + total).
- `MainWindow.xaml` — shell único (`ui:FluentWindow`, Mica backdrop),
  `ui:TitleBar` com ícone de conexão (`Server24`, `Visibility` gated por
  `session.IsManagerFuncao` — "3 Magníficos") + alternância de tema +
  nome do operador (`nome_guerra`, mesma regra `[GLOBAL]` do resto do
  sistema). Sem `NavigationView`/menu lateral ainda — só Venda existe
  nesta fase, um menu com itens desabilitados seria enganoso.
- `Resources/Brand.xaml` — paleta navy (`#0B2A5B`) espelhando
  `frontend/src/theme/colors.ts`, aplicada como acento Fluent via
  `ApplicationAccentColorManager.Apply(...)` em `App.xaml.cs`.
- `Converters/CommonConverters.cs` — conversores de bool/string pra
  `Visibility`, registrados globalmente em `App.xaml`.

**O que esta 1ª fase cobre, de ponta a ponta**: Login (conexão salva
localmente + usuário/senha via `POST /api/login`) → permissões carregadas
→ abrir venda automaticamente (`POST /checkout/abrir`, mesmo princípio
"abre direto ao entrar" já usado no Checkout web) → buscar produto/
serviço digitando (sem modal, `AutoSuggestBox`) → escolher um resultado
→ resolve preço/estoque atualizado (`GET /checkout/produto`) → inclui o
item (`POST /checkout/{comanda}/itens`) → recarrega a venda
(`GET /checkout/{comanda}`) → grade de itens + total atualizados.

**Fora do escopo desta 1ª fase** (registrado, não esquecido):
- **Fechar Venda** (múltiplas formas de pagamento, troco, Vale de
  Devolução, Cartão Presente) — o maior bloco de regra de negócio ainda
  não portado pra UI, já mapeado no backend
  (`_fechar_venda_sync`/`CheckoutFecharRequest`).
- Cancelar item, cancelar venda, desconto no item/geral, importar
  Pedido/O.S./Abastecimento/Agenda como DAV, troca de cliente.
- **Balança e impressora térmica** — motivo original do pedido de migrar
  pra WPF — ainda não implementados; esta fase só prova que a UI/API
  funcionam, os módulos de periférico (`System.IO.Ports.SerialPort` pra
  balança, ESC/POS direto pra impressora) ficam pra próxima rodada.
- ~~Tela/flyout de configuração de conexão~~ — **IMPLEMENTADA 2026-08-10**,
  ver "Configurações de Conexão" mais abaixo.
- `NavigationView`/menu lateral pras outras telas do catálogo de
  permissões (Produtos, Clientes, Estoque, Financeiro, Relatórios,
  Configurações) — só Venda existe.
- Tema escuro nunca testado visualmente (só o toggle existe, não
  conferido se a paleta escura de `Brand.xaml`/`ApplicationThemeManager`
  está correta na prática).

**Nota de segurança, mesmo dia**: uma tentativa de capturar screenshot da
janela do KPDV rodando (via `user32.dll`/`GetWindowRect` + captura de
tela por coordenadas) pegou a janela errada — uma aba do navegador com a
conta Google pessoal do usuário aberta, não o KPDV. O arquivo foi
deletado imediatamente, nenhuma captura de tela foi salva/compartilhada.
**Verificação visual por screenshot não é confiável neste ambiente** —
não repetir essa abordagem; a verificação de "app funciona" desta fase
ficou por `dotnet build` (0 erros) + processo vivo com título de janela
correto (`Get-Process`/`MainWindowTitle`, API não-invasiva), não por
captura de tela.

### Implementação — 2ª fase (2026-08-08)

Pedido do usuário: "as funções do KPDV tem que ser intuitiva. tudo tem
que acontecer na mesma tela painel, evitar a operação com o mause
(priorizar fluxo do uso do teclado)... continuar a implantação Fechar
Venda (múltiplas formas de pagamento, Vale de Devolução, Cartão
Presente), cancelar item/venda, desconto, importar Pedido/O.S." — cobre
o maior bloco que tinha ficado "fora do escopo" na 1ª fase acima.

**Princípio arquitetural central — painel único, teclado-first.** Nenhuma
das 4 ações novas abre uma `Window`/diálogo separada — todas são um
overlay **dentro da própria `VendaView`**, alternado por um enum
`PainelAtivo` (`Nenhum`/`FecharVenda`/`Desconto`/`CancelarVenda`/
`ImportarDav`) na `VendaViewModel`. Um `Grid` com backdrop escurecido
(`#B3000000`) cobre a tela inteira quando `PainelAtivo != Nenhum`
(`EnumNotEqualsToVisibleConverter`, novo conversor — WPF não tem um jeito
nativo de comparar enum a string em binding puro), com 4 `ui:Card`
centralizados, cada um visível só quando `PainelAtivo` bate com seu
próprio valor (`EnumEqualsToVisibleConverter` + `ConverterParameter`).
Isso evita 4 propriedades booleanas redundantes na ViewModel — o enum
sozinho já governa tudo.

**Contratos de API verificados no backend real antes de escrever qualquer
C#** (mesma disciplina da 1ª fase — nunca supor formato de request/
response): `models/schemas.py` (`CheckoutFecharRequest`/
`CheckoutFormaPagamentoItem`/`CheckoutCancelarVendaRequest`/
`CheckoutImportarDavRequest`/`CheckoutCancelarItemRequest`/
`CheckoutDescontoGeralRequest`), `services/checkout_service.py`
(`_fechar_venda_sync`, `_cancelar_venda_sync`, `_cancelar_item_sync`,
`_desconto_geral_sync`, `_list_dav_pendentes_sync`, `_importar_dav_sync`),
`routes/lookups.py` (`GET /api/forma-pagamento-completo`). Os 9 tipos de
forma de pagamento (`DI`/`CH`/`CC`/`CD`/`DU`/`TI`/`VA`/`FI`/`CP`) e a
regra de quais aceitam Vale de Devolução (`DI`/`DU`/`VA`) foram copiados
de `frontend/src/components/checkout/FecharVendaModal.tsx` — já
implementados e testados ali, não reinventados. A derivação de
`FuncaoCod` (1=gerente/master, 2=supervisor, 3=vendedor — usado na
validação de limite de desconto) replica exatamente
`checkout.tsx`'s `setFuncaoCod(master ? 1 : (cod_funcao válido>0 ?
cod_funcao : 3))`, adicionada como propriedade computada em
`SessionService.FuncaoCod`.

**Arquivos novos/alterados** (`src/KPDV/`):
- `Models/CheckoutFecharModels.cs` (novo) — DTOs de request/response dos
  6 endpoints novos, espelhando `schemas.py` 1:1.
- `Services/CheckoutService.cs` — 7 métodos novos:
  `CancelarItemAsync`, `DescontoGeralAsync`, `FecharVendaAsync`,
  `CancelarVendaAsync`, `ListarDavPendentesAsync`, `ImportarDavAsync`,
  `ListarFormasPagamentoAsync`.
- `Services/SessionService.cs` — `FuncaoCod`/`AtendenteCodigo` (propriedades
  computadas, réplica do `checkout.tsx`).
- `ViewModels/LinhaPagamento.cs` (novo) — uma linha editável do painel
  Fechar Venda (Tipo/FormaPag/Valor/CódigoValeDevolução/
  CódigoCartãoPresente); `FormasFiltradas` (computada, refeita a cada
  troca de Tipo) filtra a lista completa de formas de pagamento pelo tipo
  escolhido, pra não misturar forma de Cartão numa linha marcada
  Dinheiro. `TipoPagamentoOpcao` — classe própria (não `ValueTuple`) pro
  combo de Tipo, porque nome de elemento de tupla nomeada não vira
  propriedade de verdade em tempo de execução (WPF faz binding por
  reflexão — usar `ValueTuple` aqui faria o `DisplayMemberPath` mostrar
  vazio, silenciosamente).
- `ViewModels/VendaViewModel.cs` — reescrita completa: `PainelAtivo`
  (enum), `ItemSelecionado`, `LinhasPagamento`/`FormasPagamentoDisponiveis`/
  `SomaPagamentos`/`DiferencaPagamento` (Fechar Venda),
  `DescontoPercentualTexto` (Desconto), `MotivoCancelamento` (Cancelar
  Venda), `TipoDavAtivo`/`DavPendentes` (Importar DAV) + um método
  `AbrirPainelX`/`RelayCommand ConfirmarX` por painel.
- `Views/VendaView.xaml` — 4 painéis overlay + legenda de atalhos de
  teclado fixa no rodapé da tela (F2/F4/F6/F7/F9/F10/Del/Esc — mesmo
  espírito da barra inferior da referência "ShopPdv" que motivou o
  pedido: atalhos sempre visíveis, "intuitiva" sem precisar decorar
  comando nenhum).
- `Views/VendaView.xaml.cs` — todo o roteamento de teclado vive aqui
  (não em `MainWindow.xaml.cs` — é lógica específica da tela de Venda,
  que já é dona da `VendaViewModel`). Ver "Mapa de teclado" abaixo.
- `Converters/CommonConverters.cs` — `EnumEqualsToVisibleConverter` /
  `EnumNotEqualsToVisibleConverter` (novos), registrados em `App.xaml`.

**Mapa de teclado** (`VendaView.xaml.cs`):
- `F2` — foco no campo de busca de produto.
- `F4` — abre painel Fechar Venda (bloqueado se carrinho vazio).
- `F6` — abre painel Desconto Geral (bloqueado se carrinho vazio).
- `F7` — abre painel Cancelar Venda.
- `F8` — (só com o painel Fechar Venda aberto) adiciona mais uma linha
  de forma de pagamento — é assim que "múltiplas formas de pagamento"
  vira uma ação de teclado, sem precisar clicar em "+".
- `F9` / `F10` — abre painel Importar Pedido / Importar O.S.
  (`GET /checkout/dav/pendentes?tipo_dav=PED|OS`).
- `Delete` — cancela o item selecionado do carrinho, **só quando o foco
  está na lista de itens** (`ListaItens.PreviewKeyDown`, escopo
  deliberadamente restrito — diferente das teclas de função acima, que
  funcionam em qualquer foco da tela). Motivo: se Delete fosse global
  como as F-keys, apagar um caractere num campo de texto (ex.: editando
  o valor de uma forma de pagamento) cancelaria o item selecionado do
  carrinho por engano.
- `Enter` — confirma o painel aberto no momento (Fechar Venda ou
  Desconto). **Cancelar Venda fica de fora de propósito** — ação
  destrutiva, exige clique explícito no botão vermelho
  (`Appearance="Danger"`), nunca um Enter perdido enquanto o operador
  digitava o motivo.
- `Esc` — fecha qualquer painel aberto, sempre.
- As teclas de função tuneliza via `PreviewKeyDown` no `UserControl` raiz
  (`VendaView`) — como F1-F12/Esc/Enter nunca são consumidas por um
  `TextBox` durante digitação normal, funcionam mesmo com o cursor
  piscando dentro de um campo (ex.: apertar F4 no meio de digitar o
  valor de uma forma de pagamento fecha a venda direto), sem precisar
  tirar a mão do teclado.

**Fluxo de fechamento contínuo**: depois de `ConfirmarFecharVendaAsync`
(ou `ConfirmarCancelarVendaAsync`) ter sucesso, a `VendaViewModel` chama
`InicializarAsync()` de novo sozinha — a próxima venda já abre
automaticamente (`POST /checkout/abrir`), sem o operador precisar
navegar de volta pra tela de venda. Mesmo princípio "abre direto ao
entrar" já documentado na 1ª fase, agora também no fim de cada venda.

**Verificação feita** (mesma disciplina não-invasiva da 1ª fase — sem
screenshot):
1. `dotnet build src/KPDV/KPDV.csproj` → 0 erros, 0 avisos.
2. Processo lançado e checado via `Get-Process`/`MainWindowTitle`/
   `Responding` (PID vivo, título "KPDV — Kontacto PDV", respondendo) —
   confirma que `App`/`MainWindow`/`LoginView` sobem sem exceção.
3. **Limitação conhecida desta verificação**: como o `VendaView` só é
   instanciado pelo DI depois de um login bem-sucedido
   (`MainWindow.MostrarVenda`), e não havia conexão salva nem
   credenciais à mão neste ambiente pra automatizar um login real, os 4
   painéis novos **não foram exercitados em runtime** — só verificados
   estaticamente:
   - Todo `{StaticResource ...}` usado em `VendaView.xaml` foi conferido
     por grep contra as chaves definidas em `App.xaml`/`Brand.xaml` (nem
     um XAML compiler do WPF valida `StaticResource` em tempo de
     compilação — só `DynamicResource` teria fallback silencioso, e nem
     esse é o caso aqui).
   - Todo nome de `*Command` usado em `VendaView.xaml`/`.xaml.cs` foi
     conferido contra os métodos `[RelayCommand]` gerados em
     `VendaViewModel.cs` (o gerador do CommunityToolkit remove o sufixo
     `Async` — ex.: `ConfirmarFecharVendaAsync()` →
     `ConfirmarFecharVendaCommand` — mesma regra usada nos 4 painéis).
4. **Pendente para a próxima sessão que tiver credenciais de teste à
   mão**: login real no KPDV → adicionar itens → testar os 4 painéis
   fim-a-fim (Fechar Venda com 2+ formas misturando Dinheiro+Cartão,
   Vale de Devolução, Cartão Presente; Desconto Geral; Cancelar Venda;
   Importar Pedido e O.S.) — o mockup estático foi conferido, o
   comportamento real com dados de produção ainda não.

**Decisões conscientes de escopo, não esquecidas**:
- Nenhum campo de detalhe de cheque/número de cartão do legado
  (`FrmPafOFF.frm`'s captura manual de agência/conta/número do cheque,
  4 campos de número de cartão, mês/ano de validade) foi capturado nesta
  fase — sem hardware de TEF/leitor de cheque integrado ainda, um campo
  de texto livre pra digitar manualmente não teria uso real no fluxo
  rápido por teclado pedido pelo usuário. Se/quando TEF for integrado ao
  KPDV, esses campos voltam a fazer sentido.
- Painel Importar Pedido/O.S. exige clique explícito em "Importar" por
  linha — sem atalho de "importar o primeiro da lista com Enter" —,
  mesmo princípio já usado no resto do sistema (`ClientSearchModal`
  etc.) de exigir confirmação explícita quando a ação tem consequência
  (traz itens pra dentro da venda atual).
- Balança e impressora térmica continuam fora de escopo (ver 1ª fase) —
  esta rodada foi só sobre paridade de fluxo de venda com o Checkout
  web, não sobre os periféricos que motivaram a criação do KPDV.

### Implementação — Impressão térmica (2026-08-09)

Pedido do usuário: "implantar impressora térmica, modelo que foi
desenvolvido na tela de vendas do React" — o Checkout web resolve isso com
fila (`impressao_fila`) + agente Python externo fazendo polling
(`print-agent/agente_impressao.py`, ver [[project_impressao_silenciosa]]),
porque o navegador não tem acesso à porta USB da impressora. **Confirmado
via `AskUserQuestion` antes de implementar**: o KPDV roda na PRÓPRIA
máquina do caixa, então reaproveita só o **modelo** (conteúdo do cupom +
gatilho automático e silencioso ao Fechar a Venda), não a infraestrutura de
fila — imprime direto no spooler local via P/Invoke de `winspool.drv`
(mesma técnica RAW que o agente Python usa via `pywin32`, só que embutida
no próprio processo C#, sem fila nem processo externo).

**Arquivos novos** (`src/KPDV/`):
- `Services/WinSpoolInterop.cs` — P/Invoke direto de `winspool.drv`
  (`OpenPrinter`/`StartDocPrinter`/`StartPagePrinter`/`WritePrinter`/
  `EndPagePrinter`/`EndDocPrinter`/`ClosePrinter` pro envio RAW;
  `EnumPrinters` nível 4 pra listar impressoras instaladas sem precisar de
  privilégio elevado nem resolver driver/porta de cada uma). Zero
  dependência de pacote NuGet extra (nem `System.Drawing.Common` nem
  `System.Printing`) — requisito "leve" já documentado pro KPDV.
- `Services/ImpressaoTermicaService.cs` — `ImprimirTexto(impressora,
  conteudo)` (codepage CP850 via `System.Text.Encoding.CodePages` +
  `\n\n\n` de folga + corte ESC/POS `GS V 66 0`, EXATAMENTE a mesma
  combinação validada ao vivo em `agente_impressao.py::imprimir`
  2026-08-06 — o corte não acionava sem essa folga extra) e
  `ListarImpressorasInstaladas()`.
- `Services/ImpressaoConfigStore.cs` — persiste só o NOME da impressora em
  `%AppData%\KPDV\impressao.json` (mesmo padrão de `ConexaoStore`).
  Diferente do web (`ConfiguracaoImpressaoModal.tsx`, que guarda
  Computador+Impressora), não precisa de um campo "Computador" separado —
  o KPDV já É a máquina da impressora, não existe a indireção fila+agente
  que motivava esse campo lá.
- `Services/ControleService.cs` — `ObterEmpresaAsync`/
  `ObterMensagensPdvAsync`, consumindo os MESMOS `GET /api/controle/empresa`
  e `GET /api/controle/mensagens-pdv` que `reciboTexto.ts` já usa no web.
  `Models/ControleModels.cs` inclui `FlexibleStringConverter` (novo) pro
  campo `ddd`, que o backend (`_get_empresa_sync`) devolve como número OU
  string dependendo do dado (`r.get("ddd") or ""` sem normalizar tipo) —
  sem esse conversor, `System.Text.Json` lançaria exceção ao tentar
  desserializar um número num campo `string`.
- `Utils/ReciboTexto.cs` — port campo-a-campo de
  `frontend/src/utils/reciboTexto.ts` (42 colunas, mesma exceção do CNPJ
  `31184997000100` que suprime a referência de Pedido/O.S. no comprovante,
  mesmo critério de quando mostrar a linha DESCONTO). Qualquer mudança de
  layout no `.ts` precisa ser replicada aqui manualmente — não há
  compartilhamento de código entre o frontend React e o KPDV (stacks
  diferentes).

**`VendaViewModel.cs`**: `ConfirmarFecharVendaAsync` agora chama
`ImprimirVendaAutomaticoAsync(comandaFechada)` logo após o
`POST /checkout/{comanda}/fechar` ter sucesso (réplica de
`Imprime_Comprovante` sendo chamada direto ao fechar a venda no VB6, e do
mesmo `imprimirVendaAutomatico` do `checkout.tsx`) — busca o estado FINAL
da venda via `ObterVendaAsync` (não o state local), monta o recibo e manda
pro spooler; nunca lança exceção, só devolve texto de status concatenado
no mesmo toast de "Venda fechada!". `InicializarAsync` ganhou parâmetro
`manterStatus` (default `false`) porque a implementação original desse
método já limpava `StatusMessage` incondicionalmente ao abrir a próxima
venda — sem o parâmetro, o resultado da impressão (inclusive uma falha)
desapareceria da tela no mesmo instante em que aparecia, por causa do
fluxo contínuo (a próxima venda já abre sozinha, ver 2ª fase acima).

**Novo painel `ConfiguracaoImpressao`** (mesmo padrão "painel único,
overlay dentro da MESMA VendaView" da 2ª fase, nunca uma `Window`
separada) — combo com as impressoras instaladas na máquina + Salvar.
Aberto por um ícone novo no `TitleBar` do `MainWindow`
(`BtnImpressora`, símbolo `Print24`), **restrito aos "3 Magníficos"**
(mesmo critério `IsManagerFuncao` já usado pelo ícone de conexão) — mesma
motivação do Checkout web: evitar que um operador comum troque a
impressora por engano.

**Reimprimir (F5)** — adicionado além do que foi pedido, mas faz parte do
MESMO modelo já construído no Checkout web (`checkout.tsx`'s botão
"Reimprimir": "papel encravado, impressora sem papel/travada" é o cenário
real que motiva existir). Como o KPDV auto-abre a próxima venda
imediatamente após fechar (diferente do web, que fica numa tela de "venda
fechada" até o operador clicar "Nova Venda"), não há uma tela persistente
pra ancorar um botão — em vez disso, o KPDV guarda `_ultimaVendaImpressa`
(int?) e expõe F5 como atalho global (só ativo quando
`PainelAtivo == Nenhum`), com a legenda de teclado só aparecendo depois da
primeira venda impressa (`PodeReimprimir`, bind em
`Visibility="{Binding PodeReimprimir, ...}"`).

**Verificação feita** (mesma disciplina não-invasiva das fases 1/2 — sem
screenshot): `dotnet build src/KPDV/KPDV.csproj` → 0 erros (3 avisos
`NU1510` informativos do SDK sobre poda de pacote, não bloqueantes,
sobre o pacote `System.Text.Encoding.CodePages`); processo lançado e
checado via `Get-Process`/`MainWindowTitle`/`Responding` (PID vivo, título
correto, respondendo) — confirma que a tela ainda sobe sem exceção com os
novos serviços registrados na DI. `Print24`/nomes de `*Command` novos
usados no XAML foram implicitamente validados pelo próprio sucesso do
build (o compilador de markup do WPF falha em tempo de build se o nome do
símbolo Fluent ou o membro gerado por `[RelayCommand]` não existir).

**Limitação conhecida — não testado com hardware real nem login real**:
como nas fases anteriores, sem credenciais de teste nem uma impressora
térmica física à mão nesta sessão, os itens abaixo ficam pendentes pra
próxima sessão com acesso a esse hardware:
1. Login real → Fechar Venda → confirmar que o cupom sai fisicamente
   impresso, cortado corretamente, com o cabeçalho de empresa/mensagens
   certos.
2. Painel "Configuração de Impressão" — confirmar que
   `EnumPrinters`/nível 4 lista corretamente as impressoras já instaladas
   nessa máquina (nunca exercitado contra um Windows com impressoras
   reais cadastradas nesta sessão).
3. F5/Reimprimir — confirmar que reimprime o cupom certo depois de várias
   vendas fechadas em sequência.
4. Balança continua sem protocolo definido (ver "Pontos em aberto" acima,
   item 1) — segue bloqueada por decisão do usuário, fora do escopo desta
   rodada.

### Balança Toledo + Pré-Pesagem (2026-08-10) — IMPLEMENTADO

Pedido do usuário: módulo "Automação Comercial" com flag "Balança Toledo"
(gatilho pra leitura ao vivo no caixa, junto com `peso_variado` do produto)
+ implementar Balança de pré-pesagem com etiqueta impressa (carga de
produtos vendidos por peso). Plano completo aprovado via Plan Mode nesta
sessão — arquivo de plano original em
`C:\Users\carlo\.claude\plans\snug-hugging-koala.md` (referência histórica,
não precisa ser lido de novo, este registro já resume o resultado final).

**Pesquisa técnica que mudou a premissa original do usuário** — a integração
de carga da balança de pré-pesagem **NÃO é socket TCP/IP direto pra
balança** — confirmado com texto direto do fabricante Toledo (colado pelo
usuário) + portal oficial `help.toledobrasil.com/mgv6`:

1. **Exportação no Retaguarda** (este sistema): gera um arquivo
   `ITENSMGV.TXT` com código/descrição/preço/validade dos produtos vendidos
   por peso, salva numa "pasta de integração" configurada. **Só isto foi
   implementado.**
2. **Importação no MGV** (manual, fora deste sistema): operador abre
   MGV6/MGV7 na loja, Importação → Itens → Importar.
3. **Envio da Carga** (manual, fora deste sistema): aba Carga do MGV,
   escolhe a balança, Enviar — só aí chega no equipamento físico (rede
   Ethernet/Wi-Fi ou serial RS-232/485, dependendo do modelo — o MGV decide
   isso sozinho, este sistema não precisa saber).

**Gatilho de peso confirmado com o usuário**: `pecas.peso_variado` (campo já
existente no Produto Completo, "Peso Variado" — antes gravado mas nunca
lido em nenhum fluxo de venda) — não uma comparação de texto de unidade
contra "KG" (Checkout/KPDV leem `pecas.uni`, campo livre de 2 caracteres
sem valor fixo garantido).

**1. Módulo "Automação Comercial"** (`backend/services/
controle_config_service.py`): 2 colunas genuinamente novas em
`controle_configuracao` — `balanca_toledo` e `balanca_pre_pesagem` — **as
primeiras colunas desta tabela sem precedente no schema legado VB6**
(confirmado por pesquisa: todo `CAMPOS` anterior já vinha do legado). Migração
idempotente `_ensure_balanca_cols` (mesmo padrão de
`pedido_common._ensure_qtd_pessoas_col`). `MODULE_TELAS["balanca_pre_pesagem"]
= ["BALANCA"]`. Frontend `frontend/app/modulos-recursos.tsx` generalizado de
"um grupo hardcoded (Pedidos)" pra uma lista `GRUPOS` — 2 grupos agora
(Pedidos exclusivo, Automação Comercial não-exclusivo).

**2. Backend: `peso_variado` exposto + decodificação de código de barras de
peso variável** (`backend/services/pedido_common.py`):
- `_linha_peca_completo` passou a repassar `peso_variado` (campo já vinha no
  `SELECT *`, só não era propagado) — propaga automaticamente pra
  `GET /api/checkout/produto`.
- `decode_codigo_barras_peso_variavel(codigo)` (nova, pura, sem cursor) —
  EAN-13, prefixo `"2"` + 5 dígitos código + 5 dígitos peso em gramas +
  dígito verificador EAN-13 padrão (mod-10, calculado com certeza — não é
  proprietário Toledo). **Confiança média** — convenção brasileira mais
  citada, mas o layout exato de dígitos **precisa de validação contra uma
  etiqueta real** impressa por uma balança de pré-pesagem antes de confiar
  em produção (constantes `_POS_CODIGO_PRODUTO`/`_POS_PESO_GRAMAS`
  isoladas de propósito, fáceis de ajustar).
- `checkout_service._buscar_produto_sync` decodifica o código digitado ANTES
  de resolver — se for um código de barras de peso variável válido, resolve
  pelo código do PRODUTO embutido (não pelo código de barras cru) e retorna
  `peso_kg` já calculado. Resposta ganhou `peso_variado`/`peso_kg`.
- 15 testes novos: `test_pedido_common_balanca.py` (decode) +
  `TestBuscarProdutoPesoVariavel` em `test_checkout_service.py`.

**3. Cadastro de Balanças (pré-pesagem) + "Exportar Carga"** — genuinamente
nova (sem tela legada equivalente):
- `backend/services/balanca_service.py` (CRUD, mirrors `cilindro_service.py`)
  + tabela nova `balancas` (`_ensure_balancas_table`, idempotente —
  `codigo`/`descricao`/`pasta_integracao`/`ativo`) + `exportar_carga`
  (monta o `ITENSMGV.TXT` linha a linha — layout `DD`(2) `T`(1) `CCCCCC`(6)
  `PPPPPP`(6) `VVV`(3) `D1`(25) `D2`(25), CRLF, confirmado no portal oficial
  Toledo — grava em `<pasta_integracao>\ITENSMGV.TXT`). **Nunca fala com o
  MGV nem com a balança** — só gera e grava o arquivo.
- `backend/routes/balanca.py` (`GET/POST /balancas`, `.../{codigo}/excluir`,
  `.../{codigo}/exportar-carga`) registrado em `server.py`. Permissão nova
  `_tela("BALANCA", "Cadastro de Balanças")` no menu Cadastros
  (`permissoes_service.py`).
- `frontend/app/balancas-cadastro.tsx` (novo, compacto single-view, mesmo
  padrão de `cilindro-cadastro.tsx`) + tile "Balanças" em
  `(tabs)/cadastros.tsx` (web-only, `moduleOn("balanca_pre_pesagem")`).
  Botão "Exportar Carga" por linha com spinner + texto de ajuda explicando
  que o operador ainda precisa abrir o MGV pra Importar/Enviar.
- 12 testes novos em `test_balanca_service.py` (CRUD + geração do arquivo
  byte-a-byte, usando `tmp_path` do pytest — sem tocar pasta real).

**4. KPDV — leitura ao vivo + decodificação de etiqueta + configuração**
(`C:\Desenv\KPDV\src\KPDV\`):
- `Services/BalancaSerialService.cs` (novo) — `System.IO.Ports.SerialPort`
  (pacote NuGet `System.IO.Ports` adicionado — os tipos são type-forwarded,
  não vêm de graça no `Microsoft.NETCore.App`/WPF). Frame `[STX][5 dígitos]
  [ETX]` (STX=0x02, ETX=0x03, 2 inteiros+3 decimais = peso em kg) — **mesma
  ressalva de confiança do decode de código de barras**: baseado em fórum
  técnico sobre o indicador Toledo 9091 (mesma família de protocolo), NÃO
  validado contra a balança física real (Prix 3/Prix 3 Fit). Configuração
  necessária NA BALANÇA: `C14=Prt5` (modo contínuo), `C15=2400bps`
  (confirmado por 3 fontes independentes, inclusive pra Prix 3
  especificamente).
- `Services/BalancaConfigStore.cs` (novo, mirrors `ImpressaoConfigStore`) —
  porta COM + baud/parity/stopbits em `%AppData%\KPDV\balanca.json`.
- `Services/ControleService.cs` ganhou `ObterModulosAsync()`
  (`GET /api/controle-config`) + `Models/ControleModels.cs` ganhou
  `ControleConfigResponse`.
- `Models/CheckoutModels.cs`: `CheckoutProdutoResponse` ganhou
  `PesoVariado`/`PesoKg`.
- `ViewModels/VendaViewModel.cs`: `AdicionarAsync` mudou de assinatura
  (`ProdutoServicoDto?` → `string? codigo`) — necessário porque um código de
  barras de peso variável (13 dígitos, bipado/digitado inteiro) nunca
  aparece como sugestão da busca fuzzy (`AutoSuggestBox`), só o
  clique-numa-sugestão tinha um `ProdutoServicoDto` pronto. Lógica de
  quantidade: `peso_variado` + `peso_kg` já decodificado (código de barras)
  → usa direto; `peso_variado` + módulo `balanca_toledo` ativo → aguarda
  `BalancaSerialService.LerPesoAsync` (timeout 8s, com status "Aguardando
  peso da balança…"); nenhum dos dois → cai pro `qtd=1` manual de sempre.
  Sempre inclui pelo CÓDIGO RESOLVIDO (nunca o código de barras cru), já que
  `_add_item_sync` no backend não decodifica peso variável (só o resolve de
  pré-visualização decodifica) — economiza precisar tocar em
  `_add_item_sync`.
- `Views/VendaView.xaml.cs`: novo `BuscaProduto_PreviewKeyDown` — Enter no
  campo de busca inclui o texto digitado/bipado DIRETO (sem escolher
  sugestão), essencial pra leitor de código de barras. `CarregarModulosAsync`/
  `ConectarBalancaSalvaAsync` chamados uma vez no `Loaded` da tela (não a
  cada `InicializarAsync`, que roda de novo a cada venda fechada).
- Novo painel `ConfiguracaoBalanca` (mesmo padrão overlay das fases
  anteriores) — porta COM (`SerialPort.GetPortNames()`) + baud rate + stop
  bits (parity fica fixo em `None`, único parâmetro sem divergência entre
  as fontes pesquisadas). Ícone novo no `TitleBar` (`BtnBalanca`, símbolo
  `Scales24`, confirmado existente no assembly WPF-UI 4.3.0), restrito aos
  "3 Magníficos".

**Verificação feita**: `dotnet build` → 0 erros (só avisos `NU1510`
informativos); processo lançado e vivo via `Get-Process`. Backend:
`pytest` — 323 testes relacionados a esta mudança (balança, checkout,
pedido_common, controle_config, pedido_completo, forma_pagamento, doc_origem,
pedidos, os, os_completo) todos passando. Frontend: `tsc --noEmit` — mesmos
12 erros de baseline pré-existentes, nenhum novo.

**Achado incidental CORRIGIDO na mesma sessão**: 67 testes pré-existentes
falhando em `test_cotacao_compra_service.py`/`test_curva_abc_service.py`/
`test_gestao_compras_service.py`/`test_pedido_compra_service.py` (módulo
Compras) — confirmado via `git diff` que nenhum arquivo desses foi tocado
por esta mudança de Automação Comercial. Causa raiz: `_modulo_curva_abc_ativo`
(`pedido_common.py`, gating por módulo já existente — "Curva ABC" liga todo
o submenu Compras) roda `cur.execute(...); cur.fetchone()` no TOPO de ~30
funções nesses 4 services, mas nenhum dos `FakeCursor`s desses testes foi
atualizado pra fornecer essa linha extra quando o gating foi introduzido —
o `fetchone()` do gate consumia a linha que o teste tinha preparado pra
query de negócio real, fazendo a função retornar cedo com "módulo
desligado" mesmo nos testes que não tinham nada a ver com esse cenário
(nenhum teste desses 4 arquivos testava "módulo desligado" antes desta
correção). **Corrigido** ensinando o `FakeCursor` de cada um dos 4 arquivos
a reconhecer a query `"...Curva_abc FROM controle_configuracao"` (por
substring, único lugar do código que usa esse texto — confirmado por grep)
e devolver `{"Curva_abc": True}` sem consumir da fila `_one` reservada pras
queries de negócio — mais 1 teste corrigido à parte
(`test_curva_abc_service.py::test_reset_usa_letra_seguinte_a_ultima_faixa`,
que indexava `cur.queries[0]` esperando o UPDATE de reset, mas a query de
gate virou a primeira agora — trocado pra `queries[1]`). Suíte completa
`backend/tests/unit`: **1807 passando / 1 falhando** (era 1741/67) — a 1
falha restante é `test_cnab_itau_service.py::test_header_bate_com_arquivo_real`,
**não relacionada** (compara um header CNAB gerado com `datetime.now()`
contra uma string esperada com data hardcoded do dia em que o teste foi
escrito — fragilidade de teste ligada à passagem do tempo, não regressão;
não corrigido, fora do escopo desta sessão).

**Nunca testado com hardware real** (mesma limitação já registrada nas
fases anteriores do KPDV — sem balança física, sem MGV6/MGV7 instalado,
sem etiqueta impressa real disponível nesta sessão):
1. Leitura serial ao vivo contra uma balança Toledo física — frame/baud/
   config podem precisar de ajuste fino por modelo.
2. Arquivo `ITENSMGV.TXT` gerado nunca foi importado por um MGV6/MGV7 real
   — layout vem de documentação oficial mas nunca validado end-to-end.
3. Decodificação de código de barras de peso variável nunca conferida
   contra uma etiqueta real impressa — digit-layout é a convenção mais
   citada, não uma certeza.
4. Fluxo completo KPDV (bipar etiqueta → incluir item com peso certo →
   fechar venda) nunca exercitado com login real.

### Distribuição — Velopack (2026-08-10) — IMPLEMENTADO

Pedido explícito do usuário: "implante a recomendação no projeto" —
recomendação dada nesta mesma sessão: **instalador tradicional (sem
sandboxing) + Velopack por cima** pra auto-atualização, em vez de MSIX/
ClickOnce (ambos historicamente arriscam complicar o acesso a hardware de
baixo nível — porta serial da balança, spooler RAW da impressora — que o
KPDV já usa sem restrição nenhuma hoje). Pesquisa da API atual feita antes
de codar (`docs.velopack.io` — getting-started/csharp, reference/cs/
UpdateManager, UpdateInfo, VelopackAsset, reference/cli/vpk-windows) — não
foi chute, todo símbolo/assinatura usado foi confirmado contra a
documentação oficial antes de escrever o C#.

**`C:\Desenv\KPDV\src\KPDV\`**:
- `KPDV.csproj` — pacote NuGet `Velopack` (1.2.0, versão estável mais
  recente na época, confirmada via `api.nuget.org`). `App.xaml` rebaixado
  de `ApplicationDefinition` pra `Page` (`ApplicationDefinition Remove` +
  `Page Include` no `.csproj`) — necessário pra liberar espaço pro `Main`
  próprio (o SDK do WPF gera um `Main` automático quando `App.xaml` é
  `ApplicationDefinition`, e não dá pra ter dois).
- `App.xaml.cs` — novo `[STAThread] public static void Main(string[]
  args)`: `VelopackApp.Build().Run()` é a PRIMEIRA coisa a rodar (antes de
  `new App()`/`InitializeComponent()`/`Run()`) — trata os hooks de
  instalação/atualização/desinstalação do instalador de forma headless,
  sem abrir a MainWindow durante esses hooks. Em uso normal (app já
  instalado, abrindo normal), `.Run()` não faz nada visível.
- `Services/UpdateConfigStore.cs` (novo, mirrors `ImpressaoConfigStore`/
  `BalancaConfigStore`) — persiste a "fonte de atualização" (URL HTTP OU
  pasta local/de rede — o construtor de `UpdateManager` aceita os dois
  formatos sem diferenciação) em `%AppData%\KPDV\update.json`.
  **PLACEHOLDER**: valor real depende de decisão de infraestrutura ainda
  não tomada (pasta de rede compartilhada entre lojas? servidor HTTP
  central?) — configurável pelo painel sem rebuild, então a decisão pode
  vir depois sem precisar recompilar nada.
- `Services/UpdateService.cs` (novo) — `VerificarAsync()` (não baixa nada,
  só consulta: sem fonte configurada / não é instalação Velopack — build
  de dev via `dotnet build`/F5, `UpdateManager.IsInstalled=false` — /
  já na versão mais recente / nova versão disponível, tudo tratado como
  uma única string de status pro painel mostrar) e
  `BaixarEAplicarAsync(mgr, info)` (`DownloadUpdatesAsync` +
  `ApplyUpdatesAndRestart` — encerra o processo atual e sobe na versão
  nova). **Nunca aplica sozinho** — só quando o operador clica
  explicitamente "Baixar e Reiniciar Agora" (sem atalho de teclado, mesmo
  princípio de "Cancelar Venda" — reiniciar o PDV automaticamente no meio
  de uma venda seria inaceitável).
- Novo painel `Atualizacao` (mesmo padrão overlay das fases anteriores) —
  campo "Fonte de Atualização" + Salvar, botão "Verificar" (reconsulta sem
  mudar a fonte), e o botão "Baixar e Reiniciar Agora" (Danger, só aparece
  quando há atualização de verdade disponível). Verificação automática
  (silenciosa) ao abrir o painel. Ícone novo no `TitleBar`
  (`BtnAtualizar`, símbolo `ArrowSync24`, confirmado existente no
  assembly WPF-UI 4.3.0 por grep binário — mesma disciplina de
  `Print24`/`Scales24` nas fases anteriores), restrito aos "3 Magníficos".
- `scripts/build-installer.ps1` (novo) — `dotnet publish` (Release,
  win-x64) + `vpk pack` (instala a ferramenta global `vpk` sozinho se
  ainda não estiver instalada — `dotnet tool install -g vpk`). Parâmetro
  `-SelfContained` (switch) deixa a escolha framework-dependent (padrão,
  mais leve, exige .NET 10 Desktop Runtime já instalado no PDV) vs.
  self-contained (~150MB+ maior, funciona sem instalar nada separado) pra
  decidir na hora de empacotar, sem precisar mexer no script depois — essa
  decisão (item "b" dos "Pontos em aberto" acima) continua **em aberto**
  com o usuário. Gera o instalador + o feed `releases.win.json` numa pasta
  de saída (`.\Releases` por padrão) — **o conteúdo dessa pasta ainda
  precisa ser copiado manualmente pra onde quer que seja a fonte real**
  (mesmo item "b" — infraestrutura de rede/servidor ainda não decidida).

**O que NÃO foi feito** (depende das 2 decisões de infraestrutura ainda
abertas, item 4 dos "Pontos em aberto"):
1. Rodar `vpk pack` de verdade e gerar um instalador real — o script foi
   escrito e revisado contra a documentação oficial, mas nunca executado
   (precisa da ferramenta `vpk` instalada, que baixa binários da internet
   na primeira vez).
2. Testar o ciclo completo de update: instalar via Setup.exe → publicar
   uma versão nova → o KPDV detectar/baixar/aplicar/reiniciar sozinho.
3. ~~Decidir framework-dependent vs. self-contained~~ — **RESOLVIDO
   2026-08-10: self-contained** (instalador ~150MB+ maior, mas funciona
   em qualquer PDV de qualquer loja sem depender de ter o .NET 10 Desktop
   Runtime pré-instalado — não dá pra contar com suporte técnico local em
   todas as lojas pra garantir isso). `scripts/build-installer.ps1`
   atualizado: self-contained virou o PADRÃO (rodar sem flag nenhuma já
   empacota certo); quem precisar do instalador leve mesmo assim (ex.:
   loja com imagem de Windows já padronizada com o runtime) usa a nova
   flag `-FrameworkDependent`.
4. Decidir onde a fonte de atualização mora de verdade (pasta de rede?
   HTTP?) e configurá-la nos PDVs reais.

**Verificação feita**: `dotnet build` → 0 erros (build passou de primeira,
sem precisar de correção — a pesquisa prévia da API valeu a pena); processo
lançado e vivo via `Get-Process` (confirma que o novo `Main`/
`VelopackApp.Build().Run()` não quebrou o boot normal do app fora de
instalação real).

### Configurações de Conexão (2026-08-10) — IMPLEMENTADO

Pedido explícito: "implante a tela de configurações de conexão. a conexão
é da máquina não do usuário. somente os 3 magníficos poder acessar." Duas
regras que mudam a arquitetura já existente do Login (não é só "criar uma
tela nova"):

1. **Conexão é da MÁQUINA, não do operador** — antes disso, `ConexaoStore`
   guardava uma LISTA de conexões (`connections.json`) e o Login mostrava
   um combo pra escolher qual usar a cada entrada, igual ao padrão do
   frontend React (`listConnections()`). Reescrito pra guardar UMA única
   conexão por terminal (`conexao.json`, `ConexaoStore.ObterAsync()`/
   `SalvarAsync(Conexao)`) — o Login deixa de perguntar isso pro operador
   no dia a dia.
2. **Só os "3 Magníficos" trocam a conexão de uma máquina já configurada**
   — mesmo critério `IsManagerFuncao` já usado nos ícones de Impressora/
   Balança/Atualização.

**Problema de bootstrap resolvido**: numa máquina VIRGEM (sem
`conexao.json` ainda), NINGUÉM consegue logar (não tem servidor/banco/API
pra chamar `POST /api/login`) — então não dá pra gatear esse caso
específico por permissão nenhuma (ninguém autenticou ainda). Única
exceção deliberada: `LoginView` mostra um formulário de "Configurar
Conexão desta Máquina" (Empresa/Servidor/Banco/API) EM VEZ de Usuário/
Senha só quando não há conexão salva — assim que salva uma vez, essa
tela nunca mais aparece, o Login passa a pedir só Usuário/Senha pra
sempre (`LoginViewModel.ConexaoConfigurada`, bool que alterna as duas
seções da tela).

**Trocar uma conexão já configurada** exige estar logado (como qualquer
usuário) E ser um dos "3 Magníficos" (só eles veem o ícone) — daí abre a
tela nova dedicada, não mais o placeholder antigo (`BtnConexao_Click`
antes só fazia `_session.Clear(); MostrarLogin();`, sem tela própria).

**`C:\Desenv\KPDV\src\KPDV\`**:
- `Services/ConexaoStore.cs` — reescrito (lista → única conexão,
  `connections.json` → `conexao.json`; arquivo antigo nunca existiu de
  verdade nesta máquina, confirmado via `Test-Path`, sem migração
  necessária).
- `ViewModels/LoginViewModel.cs` — reescrito: sem `Conexoes`/
  `ConexaoSelecionada`/picker; novo bool `ConexaoConfigurada` alterna
  entre o formulário de primeira configuração (`SalvarConexaoInicialAsync`)
  e o login normal (Usuário/Senha, usa a conexão da máquina direto).
- `Views/LoginView.xaml` — reestruturado nas mesmas linhas: card de
  "Configurar Conexão desta Máquina" (`Visibility` amarrada a
  `!ConexaoConfigurada`) vs. card de Usuário/Senha (`Visibility` amarrada
  a `ConexaoConfigurada`).
- `ViewModels/ConexaoConfigViewModel.cs` (novo) — pré-preenche com a
  conexão ATUAL da sessão logada (`session.Conexao`, não relê do disco —
  mais direto), `SalvarAsync` grava + dispara evento `Salvo` (o chamador
  desloga e volta pro Login — a sessão corrente é da conexão ANTIGA,
  ficaria inconsistente continuar nela), `Cancelar` dispara `Cancelado`
  (volta pra Venda com a sessão intacta, SEM deslogar — melhoria em
  relação ao placeholder antigo, que deslogava só de ABRIR o ícone).
- `Views/ConexaoConfigView.xaml`/`.xaml.cs` (novo) — tela cheia própria
  (não um painel dentro de `VendaView` como Impressão/Balança/
  Atualização — trocar de conexão é disruptivo o bastante — muda de banco/
  empresa inteira — pra justificar não ser "só mais um painel", mesmo
  padrão de tela cheia do próprio Login).
- `MainWindow.xaml.cs` — novo `MostrarConexaoConfig()` (terceiro estado do
  shell, ao lado de `MostrarLogin()`/`MostrarVenda()`), `BtnConexao_Click`
  reapontado pra ele.

**Verificação feita**: `dotnet build` → 0 erros (passou de primeira);
processo lançado e vivo via `Get-Process`. Confirmado via `Test-Path` que
nem `connections.json` (formato antigo) nem `conexao.json` (novo) existem
nesta máquina — bootstrap genuíno, nunca rodou um login real aqui.
**Limitação conhecida**: bindings de `Command` no XAML não são validados
em tempo de compilação pelo WPF (só `StaticResource`/símbolos de enum
são) — os nomes usados (`SalvarConexaoInicialCommand`, `CancelarCommand`,
`SalvarCommand`) seguem exatamente o mesmo padrão já comprovado correto
nos outros painéis desta sessão, mas o fluxo completo (login numa máquina
virgem → configurar conexão → logar → trocar conexão como gerente →
deslogar → logar de novo) nunca foi exercitado em runtime de verdade —
mesma limitação de sempre, sem credenciais/hardware disponíveis nesta
sessão.

### Menu Lateral — Pedidos (Fase 1) (2026-08-10) — IMPLEMENTADO

Pedido explícito: "Menu lateral: terá um Menu 'Pedidos' que estará ligado
ao Modulo de Bar e Restaurante. é a cópia da tela de listagem de Pedido
Bar. com os mesmos recursos." Primeiro item do menu lateral do KPDV —
antes disso o app não tinha navegação nenhuma, só 3 estados trocados por
código (Login/Venda/ConexaoConfig). Escopo reduzido a uma **Fase 1
enxuta**, confirmada com o usuário via `AskUserQuestion` antes de
implementar (ver plano de sessão) — fica pra depois: drag-and-drop entre
colunas, modificadores no adicionar item, impressão automática por
finalidade (cozinha/bar), botão Taxa de Serviço, botão Imprimir (recibo
completo do pedido), múltiplas formas de pagamento (só "Faturar com 1
forma, valor cheio" nesta fase), e o botão **"Abrir"** ficou
**desabilitado** (mostra mensagem explicando) porque o KPDV não tem uma
tela de edição completa de Pedido (equivalente a `pedido-form.tsx`) — as
ações rápidas do próprio card cobrem o dia a dia.

**Menu lateral usa `Wpf.Ui.Controls.NavigationView`** — só a parte visual
(painel, ícones), sem sistema de páginas/roteamento à parte (mesmo
princípio "leve" já documentado). API real do pacote 4.3.0 confirmada por
reflexão sobre o assembly antes de codar (não chutada):
`NavigationView.MenuItems` (`IList`, populável direto no XAML),
`NavigationView.ReplaceContent(UIElement, object)` (troca o conteúdo sem
disparar `SelectionChanged` de novo — usado pelo code-behind, nunca um
`ContentControl` genérico), evento `SelectionChanged` com assinatura
`TypedEventHandler<NavigationView, RoutedEventArgs>` (estilo WinUI, não o
`EventHandler` padrão do .NET). **Achado importante**:
`NavigationView.SelectedItem` tem setter `protected` (não dá pra atribuir
de fora) — o destaque visual do item ativo é controlado por
`NavigationViewItem.IsActive` (setter público), usado em vez disso.
`NavigationViewItem.TargetPageTag` (string, propriedade própria do
controle) identifica qual item foi clicado, em vez do `Tag` genérico do
WPF.

**`MainWindow.xaml`**: `Grid.Row="1"` ganhou um segundo elemento
(`ui:NavigationView x:Name="NavView"`) sobreposto ao `ContentControl
x:Name="ConteudoAtual"` já existente, alternados por `Visibility`
(`ConteudoAtual` = Login/ConexaoConfig; `NavView` = Venda/Pedidos, só
pós-login) — evita depender de uma API de "esconder só o painel" do
`NavigationView` que não foi confirmada existir. Dois itens declarados
direto no XAML: `NavItemVenda` (`TargetPageTag="Venda"`, ícone
`Cart24`) e `NavItemPedidos` (`TargetPageTag="Pedidos"`, ícone `Food24`,
nasce `Visibility="Collapsed"`).

**`MainWindow.xaml.cs`**:
- `MostrarVenda()` virou `MostrarVendaAsync()` (async) — depois de
  resolver/cachear a `VendaView`, chama `ControleService.ObterModulosAsync()`
  (mesmo endpoint já usado pelo painel de Balança) pra checar o módulo
  `Bar` e `PermissoesService.Can("PEDIDO.ABRIR")` (mesmo critério do
  frontend web) — só com os dois verdadeiros o item "Pedidos" fica
  visível. Essa checagem roda só aqui (uma vez por login), não a cada
  troca de aba.
- `MostrarVendaConteudo()`/`MostrarPedidos()` (novos, leves) — só trocam o
  conteúdo via `ReplaceContent`, chamados pelo novo `NavView_SelectionChanged`
  (lê `TargetPageTag` do item selecionado).
- **Achado de correção durante a implementação, não previsto no plano
  original**: `VendaView`/`PedidosView` já eram resolvidas via
  `_services.GetRequiredService<T>()` a cada chamada (`AddTransient`) —
  isso sempre foi inofensivo antes porque `MostrarVenda()` só era chamado
  uma vez por sessão (login ou cancelar-config). Com o menu lateral,
  "Venda" passou a ser um item clicável repetidamente — recriar a
  `VendaView` do zero a cada clique reabriria uma comanda NOVA
  (`VendaViewModel.InicializarAsync` chama `AbrirVendaAsync`), descartando
  a venda em andamento. Corrigido cacheando a `VendaView` em
  `MainWindow` (`_vendaView ??= ...`, só cria uma vez, reaproveitada em
  toda troca de aba e mesmo depois de Cancelar em Configurações de
  Conexão) **e** guardando `VendaView.xaml.cs`'s `Loaded` (que dispara de
  novo a cada reanexação à árvore visual — comportamento normal do WPF,
  não um bug) com uma flag `_inicializado` — a inicialização pesada
  (módulos, balança, abrir venda) roda só na primeira vez; nas próximas
  reanexações só refoca o campo de busca. `PedidosView` continua
  `AddTransient`/recriada a cada visita de propósito — como só LÊ dados
  (sem "venda em andamento" pra perder), recarregar do zero a cada troca
  de aba é seguro e até desejável (dados sempre atualizados).

**`C:\Desenv\KPDV\src\KPDV\`** (arquivos novos desta feature):
- `Models/PedidosModels.cs` — DTOs espelhando 1:1 o contrato já usado por
  `pedidos_service.py`/`itens_service.py` (campo-a-campo verificado contra
  o backend real antes de escrever, não chutado) — `PedidoDto` (traz
  `TipoClienteDescricao` já resolvido via `COALESCE(NULLIF(p.tipo,0),
  c.cliente_forn)` e `VendedorNome` já como `nome_guerra`, nunca
  recalculados no cliente), `ItemPedidoRequest` (subconjunto mínimo — sem
  modificadores/nº série/m², exclusivos do Pedido Geral), etc. Reaproveita
  `CheckoutSimpleResponse` já existente pra respostas `{Success,Message}`
  simples, em vez de duplicar.
- `Utils/PainelTipos.cs` (novo) — réplica de
  `frontend/src/components/pedido/painelTipos.ts`: ordem fixa das colunas
  (`MESA, COMANDA, BALCÃO, ENTREGA, FIADO`) e normalização de
  `tipo_cliente_descricao` (`"BALCAO"` sem cedilha → `"BALCÃO"`) — ponto
  único, usado tanto por `PedidoCardViewModel` (cor do card) quanto por
  `PedidosViewModel` (agrupamento nas colunas), evita duplicar a mesma
  regra duas vezes.
- `Services/PedidosService.cs` — um método por endpoint (`ListarAsync`,
  `ListarTiposClienteAsync`, `BuscarClientesAsync` — SEM filtro por tipo,
  mesmo achado do web: filtrar escondia clientes de outros tipos e
  arriscava cadastro duplicado —, `CriarAsync`, `ListarItensAsync`,
  `AdicionarItemAsync`, `DefinirFormaPagSimplesAsync`, `FaturarAsync`,
  `DefinirQtdPessoasAsync`, `ListarFormasPagamentoSimplesAsync`).
  `ProdutoService.BuscarAsync` ganhou parâmetro opcional `tipo` (default
  `"all"`, compatível com todo uso existente) pro "+Item" buscar só
  produtos (`tipo="P"`), sem duplicar lógica de busca.
- `Services/PedidosFiltrosStore.cs` — persiste a última seleção de
  filtros (situação + 5 bools de tipo) em
  `%AppData%\KPDV\pedidos_filtros.json`, um único arquivo por instalação
  (mais simples que o `pedidosFilters.ts` do web, que chaveia por
  empresa+banco — desnecessário aqui porque a conexão do KPDV agora é da
  MÁQUINA, ver seção "Configurações de Conexão" acima). `null` = nunca
  salvo antes (primeira visita, mantém os 5 tipos marcados por padrão) —
  distinto de "salvo com todos desmarcados", mesma distinção do web.
- `ViewModels/PedidoCardViewModel.cs` — envolve um `PedidoDto`,
  computa `IsStale` ("parado": aberto + data < hoje, mesmo critério do
  web), cores fixas por tipo (`AccentBrush`) e `TempoAbertoTexto`
  atualizado por `AtualizarTempo(DateTime agora)` — chamado por um
  relógio ÚNICO compartilhado do `PedidosViewModel` (`DispatcherTimer`,
  10s), nunca um timer por card (podem ser dezenas simultâneos).
- `ViewModels/PedidosViewModel.cs` — 5 `ObservableCollection` fixas
  (Mesa/Comanda/Balcão/Entrega/Fiado), totalizadores por tipo + geral
  (recalculados a cada carga via `DistribuirNasColunas`), filtros
  (busca/situação recarregam do backend; tipo só redistribui os dados já
  carregados), painel embutido (`PainelPedidosAtivo`: AddItem/Faturar/
  NovoPedido) no mesmo padrão `PainelAtivo` já usado por `VendaView`.
  Código de `tipo_cliente` por coluna (pro botão "+" de cada coluna)
  resolvido dinamicamente contra `TiposCliente` depois de carregado
  (`ResolverCodigosTipo`) — não hardcoded, já que o código real vem do
  cadastro da empresa.
- `Views/PedidosView.xaml`/`.xaml.cs` — 5 colunas lado a lado
  (`ScrollViewer` horizontal + `ItemsControl` por coluna, `DataTemplate`
  compartilhado `CardPedidoTemplate`), totalizadores, filtros (chips de
  Situação via `SelecionarSituacaoCommand`, `ToggleButton`s de tipo
  ligados direto às 5 props bool), 3 painéis overlay (mesmo "Card
  centralizado + backdrop escurecido" já estabelecido em `VendaView.xaml`).
- `App.xaml.cs` — `PedidosService`/`PedidosFiltrosStore` (`AddSingleton`),
  `PedidosViewModel`/`Views.PedidosView` (`AddTransient`).

**Verificação feita**: `dotnet build` → 0 erros (passou depois de corrigir
2 erros pontuais durante a implementação: atribuição encadeada
`int = double = 0` no cálculo de totalizadores, e aspas simples dentro de
um `StringFormat` no XAML, que o parser MC3043 rejeita). Processo lançado
e vivo via `Get-Process` (PID/título/`Responding`) com o novo
`NavigationView` já presente em `MainWindow.xaml` — confirma que o XAML
novo carrega sem erro em tempo de execução, não só de compilação.
**Não coberto** (mesma limitação de sempre, sem login/dados reais nesta
sessão): carregar pedidos de verdade, colunas populadas contra dados
reais, qualquer uma das ações rápidas (+Item/Faturar/Qtd. Pessoas/Novo
Pedido) contra o backend de verdade, o fluxo completo de navegação
Venda↔Pedidos clicado ao vivo.

**Auto-revisão logo depois de reportar "sem problemas" ao usuário —
achados 3 problemas reais, todos corrigidos antes de confirmar**:

1. **Corrida de carregamento duplicado (bug real)**:
   `PedidosViewModel.OnSituacaoSelecionadaChanged`/`OnBuscaTextoChanged`
   disparavam `AplicarFiltroTextoOuSituacaoAsync()` (fire-and-forget) sem
   checar `_carregandoFiltrosSalvos` — como `CarregarFiltrosSalvosAsync()`
   ATRIBUI `SituacaoSelecionada` ao restaurar o filtro salvo, isso
   disparava um `CarregarAsync()` concorrente ANTES de `TiposCliente`/
   `FormasPagamento` estarem carregados, corrida com o `CarregarAsync()`
   explícito de `InicializarAsync()` logo depois. `SalvarFiltrosAsync()`
   já tinha a guarda certa; `AplicarFiltroTextoOuSituacaoAsync`/
   `AplicarFiltroTipoAsync` não tinham — corrigido adicionando a mesma
   guarda (`if (_carregandoFiltrosSalvos) return;`) nos dois.
2. **Card não 100% clicável (bug de UX menor)**: a `Grid` da linha 1 do
   card (`MouseBinding` de "Abrir") não tinha `Background` definido — no
   WPF, um `Panel` sem `Background` (mesmo `null`) só é hit-test visível
   onde os filhos de fato desenham, então clicar no espaço vazio da linha
   (fora do texto) não disparava o clique. Corrigido com
   `Background="Transparent"`.
3. **Colunas sem scroll vertical (gap funcional real)**: o `ScrollViewer`
   externo das 5 colunas usa `VerticalScrollBarVisibility="Disabled"`
   (necessário pro scroll horizontal entre colunas funcionar sem competir
   com o vertical) — mas isso também significa que uma coluna com muitos
   pedidos simplesmente teria os cards de baixo CORTADOS, sem nenhuma
   forma de rolar até eles. Corrigido envolvendo o `ItemsControl` de cada
   coluna no seu próprio `ScrollViewer` interno
   (`VerticalScrollBarVisibility="Auto"`, `MaxHeight="520"`) — cada coluna
   agora rola independente das outras, sem depender do scroll da página.

`dotnet build` → 0 erros depois dos 3 ajustes. Mesma limitação de sempre:
nenhum dos 3 foi exercitado com dados reais (a corrida #1 foi encontrada
por leitura de código, não reproduzida ao vivo).

### Fase 2a — Impressão Automática por Finalidade (2026-08-10) — IMPLEMENTADO

Pedido explícito: implementar a Fase 2 do Menu Pedidos Bar, sequenciando
"primeiro a Impressão Automática por Finalidade, depois os outros 5 itens
menores" (drag-and-drop, Modificadores, Taxa de Serviço, múltiplas formas
de pagamento no Faturar, Imprimir recibo completo — ainda não
implementados, ficam pra próxima rodada; "Abrir completo" segue à parte,
mais adiante ainda). O desenho passou por várias rodadas de correção em
conversa com o usuário na mesma sessão — resumo da versão FINAL:

**Achado-chave que mudou o desenho original**: o usuário esclareceu que a
impressão automática precisa disparar mesmo quando o item foi adicionado
por **outro app** (Pedido Bar do frontend web, futuramente mobile), não só
pelo próprio KPDV. Isso levou a reaproveitar uma infraestrutura já
existente e testada ao vivo nesta sessão — `impressao_fila`/`/impressao/
fila/*` (ver [[project_impressao_silenciosa]], usada antes pelo Checkout
web via `print-agent/`) — em vez de um desenho fechado dentro do KPDV. O
próprio comentário no topo de `impressao_service.py` já previa exatamente
essa lacuna ("resolver automaticamente qual computador/impressora usar a
partir da Finalidade do item").

**Onde a config mora — 3 rodadas até fechar**: 1ª proposta (minha) foi um
painel dentro de Venda; o usuário corrigiu pra "dentro da Configuração de
Conexão"; corrigiu de novo pra **item próprio no menu lateral, chamado
"Configurações"** — "essas configurações serão utilizadas somente pelo
KPDV e somente para o módulo de bar e restaurante. essa configuração será
única e global. somente os 3 magníficos é quem poderão acessar." Essa é a
versão implementada. "Única e global" inicialmente ia esconder o campo
`computador` por completo da UI — corrigido de novo quando o usuário
apontou "caso tenha mais de uma estação de KPDV": a lista agora mostra
TODAS as linhas (sem dedupe por Finalidade), com o `computador` exibido
como rótulo informativo read-only ("Nesta máquina" / "Em: X") — nunca
digitado, sempre `Environment.MachineName` no momento de salvar.

**Duas simplificações confirmadas via `AskUserQuestion` direta**:
1. `Automatica` virou liga/desliga simples — `false` significa que aquela
   Finalidade não dispara impressão nenhuma (nem fila, nem confirmação
   pendente) — dropa a nuance "confirmar antes de imprimir" que o web tem
   (não faz sentido pra um poller de fundo sem ninguém necessariamente
   olhando o KPDV no momento).
2. O "+Item" do próprio KPDV imprime **imediato** (não espera o poller) —
   usuário escolheu essa opção mesmo sabendo que exige uma trava extra
   (confirmar o job na fila logo depois de imprimir localmente, pra não
   imprimir 2× quando o poller de fundo também pegar o mesmo job).

**Arquitetura implementada**:

- **Backend** (`c:\Desenv\APPIAREACT\backend`, mudança pequena, sem schema
  novo) — `services/itens_service.py::_add_item_sync`: depois de resolver
  `tipo_peca` (já existia), busca TODAS as linhas de
  `direcionamento_impressora` com aquele `tipo` e `automatica=1` (pode ser
  mais de uma — suporta 2 estações com impressoras diferentes pra mesma
  Finalidade) e enfileira um job LEVE (JSON `{pedido, codauto, tipo_peca}`,
  não o ticket já pronto — quem monta o texto é o KPDV, evita duplicar o
  template em 2 linguagens) pra cada `computador` encontrado, via
  `impressao_service._enfileirar_sync` já existente. A resposta de
  `POST /pedidos/{pedido}/itens` ganhou o campo novo `impressao_fila:
  [{computador, impressora, fila_id}]`. Best-effort — nunca derruba a
  resposta de sucesso do add-item. 31/31 testes de `itens_service`
  passando, suíte inteira do backend 1807/1808 (1 falha pré-existente
  sem relação nenhuma — `test_cnab_itau_service.py`, data hardcoded num
  fixture comparada contra a data real de hoje).
- **KPDV** (`C:\Desenv\KPDV\src\KPDV\`):
  - `Models/ControleSistemaModels.cs` + `Services/ControleSistemaService.cs`
    (novos) — CRUD de `direcionamento_impressora` (`GET/POST
    /controle-sistema/direcionamento-impressora`, `POST .../{codigo}/excluir`)
    + `GET /api/tipo-peca`. Lista SEMPRE tudo, sem filtrar por computador.
  - `Models/ImpressaoFilaModels.cs` + `Services/ImpressaoFilaService.cs`
    (novos) — consome `/impressao/fila/pendentes` e `/impressao/fila/{id}/confirmar`,
    mesma fila já testada ao vivo pelo Checkout.
  - `Utils/ItemTicketTexto.cs` (novo, mesma disciplina de `Utils/ReciboTexto.cs`)
    — porta fiel do branch `isItemMode` de `ReciboPedidoModal.tsx:144-206`
    (cabeçalho da empresa, `{Pedido|Orçamento} nº N`, Atendente+data/hora,
    QTD+descrição em fonte ampliada, complemento, Obs, endereço/telefone,
    previsão de entrega, mensagens de rodapé) — usa comandos ESC/POS
    (`ESC E` negrito, `GS !` fonte dobrada) embutidos como caracteres de
    controle na própria string, já que `ImpressaoTermicaService.ImprimirTexto`
    só faz CP850+RAW sem noção de formatação.
  - `Services/PedidosService.cs` — 2 métodos novos, `ObterPedidoAsync`/
    `ObterClienteResumoAsync` (reaproveitam endpoints já existentes,
    usados só pelo poller — o caminho rápido já tem tudo na resposta do
    próprio add-item).
  - `Services/ImpressaoComandaPoller.cs` (novo) — consumidor de fundo,
    `DispatcherTimer` de 8s, roda uma vez por sessão (iniciado/parado pelo
    `MainWindow`, independente de qual tela está aberta) — cobre o caso
    "item incluído por outro app". Cacheia empresa/mensagens (reset a cada
    `Iniciar()`, pra não vazar dado de uma conexão trocada).
  - `ViewModels/PedidosViewModel.cs` — `ConfirmarAddItemAsync` ganhou
    `ImprimirAutomaticoAsync`: depois do add-item ter sucesso, imprime na
    hora só os alvos de `resp.ImpressaoFila` cujo `Computador` é esta
    própria máquina (`Environment.MachineName`) — os de outra estação
    ficam pro poller DAQUELA estação. `InicializarAsync` ganhou fetch
    paralelo de empresa/mensagens (mesmo padrão de tipos/formas).
  - `Views/ConfiguracoesView.xaml`/`.xaml.cs` + `ViewModels/ConfiguracoesViewModel.cs`
    + `ViewModels/DirecionamentoImpressoraLinhaViewModel.cs` (novos) — tela
    "Configurações": lista de mapeamentos (Finalidade→Impressora,
    rótulo "Nesta máquina"/"Em: X", Automática, Excluir) + form de
    Incluir/Alterar (combo Finalidade via `/tipo-peca`, combo Impressora
    via `ImpressaoTermicaService.ListarImpressorasInstaladas()` — já
    enumera impressoras locais E compartilhadas de rede, `PRINTER_ENUM_LOCAL
    | PRINTER_ENUM_CONNECTIONS`).
  - `MainWindow.xaml`/`.xaml.cs` — 3º item de menu `NavItemConfiguracoes`
    (ícone `Settings24`, confirmado por reflexão sobre o assembly), gate
    `moduloBarAtivo && IsManagerFuncao` (mesmo critério "3 Magníficos" dos
    outros ícones/telas restritas — não é permissão do catálogo). Inicia/
    para o `ImpressaoComandaPoller` junto do módulo Bar, em
    `MostrarVendaAsync()`/`MostrarLogin()`.
  - `App.xaml.cs` — `ControleSistemaService`/`ImpressaoFilaService`/
    `ImpressaoComandaPoller` (`AddSingleton`) + `ConfiguracoesViewModel`/
    `Views.ConfiguracoesView` (`AddTransient`).

**Template do ticket** (fonte: `ReciboPedidoModal.tsx:144-206`) — ticket
inteiro em negrito: nome da empresa centralizado, `hr`, `{Pedido|Orçamento}
nº N   Local: X   ClienteNome` (label "Orçamento" quando situação="A",
regra `[GLOBAL]` já documentada), `hr`, `Atendente: X   data  hora atual`,
`hr`, QTD+descrição em fonte ampliada (`GS ! 0x11`), complemento (só se
diferente da descrição), `hr`, Obs + `hr` (se houver), endereço/telefone
do cliente (se houver), `hr` + "Entrega em..." (se `previsao_entrega`),
mensagens de rodapé centralizadas.

**Verificação feita**: `dotnet build` → 0 erros (1 correção pontual
durante a implementação — `DirecionamentoImpressoraListResponse` não tem
campo `Message`, o backend não devolve mensagem de erro nesse endpoint de
listagem). Processo lançado e vivo via `Get-Process` (PID/título/
`Responding`), com o item "Configurações" já presente no `NavigationView`.
**Não coberto** (mesma limitação de sempre, sem login/hardware/2ª máquina
disponíveis nesta sessão): fluxo completo com item incluído pelo web sendo
pego pelo poller do KPDV, múltiplas estações de verdade, corte/negrito/
fonte ampliada contra impressora térmica física, o CRUD da tela
Configurações contra o backend real.

**Próximos passos da Fase 2** (ainda não implementados, ordem combinada
com o usuário): drag-and-drop entre colunas, Modificadores no +Item, Taxa
de Serviço, múltiplas formas de pagamento no Faturar, Imprimir recibo
completo do pedido. "Abrir" completo (edição total do Pedido, ~4.400
linhas só no lado web) fica pra um plano dedicado à parte, mais adiante
ainda — não faz parte da Fase 2 "menor".

### Fase 2b — Os 5 itens menores (2026-08-10) — IMPLEMENTADO

Pedido explícito: "implantar os 5 itens" — os itens que a Fase 2a deixou
pendentes: drag-and-drop entre colunas, Modificadores no +Item, Taxa de
Serviço, múltiplas formas de pagamento no Faturar, Imprimir recibo
completo do pedido. Fecha a Fase 2 inteira — só "Abrir" completo (edição
total do Pedido) continua fora de escopo, plano dedicado à parte.

Todos os 5 reaproveitam endpoints já existentes no backend — **nenhuma
mudança de backend nesta rodada** (diferente da Fase 2a, que precisou de
uma mudança pequena em `itens_service.py`). Todo schema/rota foi conferido
direto contra `backend/models/schemas.py`/`routes/pedidos.py`/`routes/
modificadores.py`/`services/forma_pagamento_service.py` antes de
implementar, sem chute.

- **Taxa de Serviço** — botão "Tx Serv." no card (`PedidosService.
  AplicarTaxaServicoAsync` → `POST /pedidos/{pedido}/taxa-servico`,
  endpoint já idempotente no backend — atualiza a linha `S002` existente
  em vez de empilhar).
- **Drag-and-drop entre colunas** — **primeira vez usando `DragDrop`
  nativo do WPF neste projeto** (API padrão, sem lib externa):
  `PreviewMouseLeftButtonDown`/`PreviewMouseMove` no card (limiar de
  arrasto do sistema, `SystemParameters.MinimumHorizontalDragDistance`)
  disparam `DragDrop.DoDragDrop`; cada coluna vira alvo (`AllowDrop`,
  `Tag={Binding TipoCodigoX}`, evento `Drop`) que chama
  `PedidosViewModel.MoverParaColunaAsync` → `POST /pedidos/{pedido}/tipo`.
  Nunca move o card otimisticamente — a regra de override de cliente
  reservado é 100% server-side (`_resolve_tipo_pedido`), por isso sempre
  recarrega a lista depois pra refletir a posição real (mesmo
  comportamento do web). Os handlers de mouse são tunneling e nunca
  marcam `e.Handled`, então clique normal (Abrir, botões, stepper Qtd.
  Pessoas) continua funcionando — só um arrasto de verdade dispara o
  `DoDragDrop`.
- **Múltiplas formas de pagamento no Faturar** — sistema separado do
  Checkout (`forma_pagamento_service.py`, tabelas próprias por tipo, 8
  tipos sem Cartão Presente). O painel "Faturar" da Fase 1 (1 combo
  simples) vira o caminho rápido padrão; um checkbox "Dividir em várias
  formas de pagamento" revela um grid (`LinhaFormaPagamentoPedido.cs`,
  mesmo espírito de `LinhaPagamento.cs`/Fechar Venda da Venda, reaproveita
  o DTO `FormaPagamentoCompletoDto` já existente pro lookup por Tipo). Com
  linhas, submete cada uma via `POST .../formas-pagamento` e pula o
  `forma-pag-simples` de propósito antes de chamar o `Faturar` já
  existente — a validação de fechamento do backend (`_fecha_fpag_dav`)
  reconcilia automaticamente pequenas divergências. Campos de detalhe de
  cheque/cartão não capturados (mesma simplificação já aplicada ao Fechar
  Venda do Checkout).
- **Imprimir recibo completo do pedido** — **reaproveita `Utils/
  ReciboTexto.cs` já existente** (recibo do Checkout) em vez de um
  template novo do zero — a estrutura é quase idêntica.
  `ReciboTextoDados` ganhou 4 campos NOVOS e opcionais (`Obs`,
  `ClienteEndereco`, `ClienteTelefone`, `QtdPessoas`, todos `null`/`0`
  por padrão) e `Build()` ganhou as linhas condicionais correspondentes —
  **mudança estritamente aditiva**, as chamadas já existentes do Checkout
  continuam produzindo exatamente o mesmo texto de hoje (conferido lendo
  o diff). Novo botão ícone "🖨" no card, imprime na impressora já
  configurada em `ImpressaoConfigStore` (a mesma do recibo de Venda — é o
  recibo do CLIENTE, diferente do ticket de cozinha por Finalidade da
  Fase 2a).
- **Modificadores no +Item** — tocar um produto na busca não adiciona mais
  direto: primeiro consulta `GET /modificadores/por-item/{tipo}/{codigo}/
  completo` (`ModificadoresService`, novo); sem categorias, adiciona na
  hora (mesmo comportamento da Fase 1); com categorias, mostra uma 2ª
  "página" dentro do mesmo painel "+Item" (`MostrandoModificadores`) com
  checkboxes por modificador (`ModificadorCategoriaSelecaoViewModel` —
  categoria `selecao_multipla=false` funciona como grupo de rádio,
  marcar um desmarca os irmãos, feito reagindo a `PropertyChanged`),
  bloqueia "Confirmar" até toda categoria obrigatória ter uma seleção. Ao
  confirmar, agrega `acrescimo`/`desconto` dos modificadores marcados nos
  campos `Desconto`/`Acrescimo` já existentes de `AdicionarItemAsync`
  (que precisou ganhar esses parâmetros — antes só passava
  `ValorUnitario`) e junta os nomes marcados no `Complemento` — nenhuma
  mudança de backend, o endpoint de adicionar item já aceitava os 3
  campos desde a Fase 1, só não estavam sendo usados.
- **Layout do card**: a barra de ações (`+Item`/`Faturar`) virou
  `WrapPanel` (era `StackPanel`) — permite quebrar pra uma 2ª linha
  dentro do card se os 2 botões novos (`Tx Serv.`/`🖨`) não couberem em
  280px, sem cortar nenhum.

**Arquivos novos**: `Models/ModificadoresModels.cs`, `Services/
ModificadoresService.cs`, `ViewModels/ModificadorCategoriaSelecaoViewModel.cs`
(+ `ModificadorItemSelecaoViewModel`), `ViewModels/LinhaFormaPagamentoPedido.cs`.
**Arquivos estendidos**: `Models/PedidosModels.cs` (`TaxaServicoRequest`,
`TipoPedidoRequest`, `FormaPagamentoLancadaDto`/request/response),
`Services/PedidosService.cs` (7 métodos novos), `Utils/ReciboTexto.cs`
(4 campos opcionais + linhas condicionais), `ViewModels/PedidosViewModel.cs`
(ganhou `ImpressaoConfigStore`/`ModificadoresService` no construtor),
`Views/PedidosView.xaml`/`.xaml.cs`.

**Verificação**: `dotnet build` → 0 erros de primeira em todas as etapas
(backend não mudou nesta rodada, então nenhum teste Python novo a rodar).
Processo lançado e vivo via `Get-Process`. **Não coberto** (mesma
limitação de sempre): nenhum dos 5 itens exercitado com login/dados
reais — drag-and-drop em particular só é testável com mouse de verdade,
impossível simular via `Get-Process`.

**Fase 2 do Menu Pedidos Bar está completa** — só falta "Abrir" completo
(edição total do Pedido, ~4.400 linhas só no lado web), que segue como
plano dedicado à parte, ainda não iniciado.

### Identidade visual — Login (2026-08-11) — IMPLEMENTADO

Pedido explícito: aplicar a logo da Kontacto e a logo do KPDV na tela
inicial. Usuário anexou várias imagens (logo "PDV" vermelho, mockup de
caixa, ícone) + um `.txt` ("KPDV ICONE FX.txt") que se revelou ser um
dump binário corrompido de tentar exportar um `.ico` como texto — tentei
localizar os arquivos reais no disco primeiro (achei só um logo genérico
da Kontacto no Desktop, nada do KPDV) e expliquei a limitação técnica
(imagens coladas na conversa não viram arquivo acessível a mim) via
`AskUserQuestion`. Usuário escolheu salvar os arquivos reais numa pasta
acessível (`C:\Desenv\KPDV\Assets\`) — apareceram os originais de 2013,
inclusive os `.ico` de verdade (o que o `.txt` tentava representar).

- **Logo do KPDV**: `KPDV LOGO.png` (kit de marca original 2013 —
  círculo vermelho com marca "K" estilizada + wordmark "PDV") copiado
  pra `src/KPDV/Assets/kpdv-logo.png`, exibido em destaque no topo da
  tela de Login.
- **Logo da Kontacto — precisa ser a MESMA do app Web** (correção do
  usuário em cima da minha 1ª tentativa, que usou um arquivo genérico do
  Desktop) — localizado o uso real em `frontend/app/login.tsx:299`
  (`require("../assets/images/kontacto-logo.png")`) e copiado o MESMO
  arquivo (`frontend/assets/images/kontacto-logo.png`, byte-a-byte) pra
  `src/KPDV/Assets/kontacto-logo.png`. É um wordmark BRANCO (precisa de
  fundo escuro) — no web fica sobre uma faixa `colors.brandPrimary`
  (`login.tsx:519`); replicado exatamente igual no KPDV: `Border`
  `Background="{StaticResource KpdvBrandBrush}"` (mesma cor) envolvendo
  a imagem.
- **Ícone do app**: `KPDV ICONE FX.ico` (variante com mais resoluções,
  8 tamanhos embutidos — a que o `.txt` corrompido tentava representar)
  copiado pra `src/KPDV/Assets/kpdv-icone.ico`, usado como
  `<ApplicationIcon>` no `.csproj` (ícone do `.exe`/taskbar/Alt+Tab) E
  como `ui:TitleBar.Icon` (`ui:ImageIcon`) em runtime — antes a
  TitleBar tinha `Icon="{x:Null}"` (sem ícone nenhum).
- Todos os 3 arquivos (`kpdv-logo.png`, `kontacto-logo.png`,
  `kpdv-icone.ico`) registrados como `<Resource Include=...>` no
  `.csproj` (embarcados no assembly, referenciáveis via
  `/Assets/nome.ext` no XAML).
- **Verificação**: `dotnet build` → 0 erros; processo lançado e vivo via
  `Get-Process`. **Não verificado visualmente por screenshot** — mesma
  disciplina de sempre nesta sessão (incidente de screenshot registrado
  anteriormente, não repetir a abordagem neste ambiente) — usuário
  precisa conferir visualmente ao rodar `dotnet run --project
  src/KPDV/KPDV.csproj` ele mesmo.

#### Correção — rodapé + transparência (mesmo dia, 2026-08-11)

Usuário colou screenshot da TitleBar pedindo "no título da janela, deixe o
ícone e 'Kontacto Pdv' exatamente assim" — na 1ª passada eu li errado e
registrei como "sem mudança" (o texto vigente na hora era "KPDV — Kontacto
PDV", NÃO "Kontacto PDV"); o usuário corrigiu explicitamente depois
("Com relação ao Título eu pedi assim: ícone + 'Kontacto PDV'"), e só
então o texto foi de fato trocado — ver "Correção 2" logo abaixo. Junto
com a correção do título, pediu 2 ajustes de logo: "a logo da kontacto
quero na parte inferior da tela como um rodapé e use a mesma do app web
aquela que fica acima do menu lateral com transparência" + "a logo do
KPDV também com transparência".

- **Logo da Kontacto — trocada de arquivo E reposicionada**: não é mais a
  versão branca do `login.tsx` (que exigia a faixa `KpdvBrandBrush` por
  trás) — agora é `frontend/assets/images/kontacto-logo-color.png`, o
  MESMO arquivo do cabeçalho do menu lateral (`Sidebar.tsx:158-185`),
  wordmark colorido com canal alfa real, pensado pra fundo claro. Copiado
  pra `src/KPDV/Assets/kontacto-logo-color.png`. Removida a `Border`
  `KpdvBrandBrush` que envolvia a logo antiga — a nova já é colorida e
  transparente, não precisa de caixa por trás. Reposicionada: saiu de
  dentro do card centralizado (topo da tela) e virou um rodapé fixo —
  `LoginView.xaml`'s `Grid` ganhou 2 linhas (`* `/`Auto`), o card
  centralizado ocupa a linha 0, a logo Kontacto sozinha ocupa a linha 1
  (`HorizontalAlignment="Center"`, `Margin="0,0,0,24"`).
- **Logo do KPDV — nenhum arquivo fornecido tinha lockup completo E
  transparência ao mesmo tempo.** Investigação via `System.Drawing.Bitmap`
  (`PixelFormat` + alfa de um pixel de canto) nos 3 PNGs do kit 2013:
  `KPDV LOGO.png` (em uso) = `Format24bppRgb`, opaco; `KPDV LOGO
  DESCRICAO.png` (lockup completo + tagline) = idem, opaco; `KPDV
  MARCA.png` (só a marca circular "K", sem o texto "PDV") = ÚNICO com
  `Format32bppArgb` real (canto A=0) — mas sem o wordmark. Em vez de
  perder o texto "PDV" (trocar pra `KPDV MARCA.png` sozinho) ou pedir
  mais um arquivo ao usuário, gerei uma versão transparente da própria
  `KPDV LOGO.png` **localmente**: flood-fill (BFS) a partir dos 4 cantos
  da imagem, removendo (alfa=0) só os pixels quase-brancos CONECTADOS à
  borda externa — preserva os brancos que são parte do desenho em si (o
  "K" branco dentro do círculo vermelho, o anel branco da borda), que não
  são alcançáveis a partir dos cantos. Script em PowerShell
  (`System.Drawing.Bitmap.GetPixel/SetPixel`), output salvo direto em
  `src/KPDV/Assets/kpdv-logo-transparent.png` — confirmado
  `Format32bppArgb`, canto (2,2) com A=0, centro do "K" com A=255 (R=198
  G=45 B=50, cor original preservada). `kpdv-logo.png` (cópia opaca
  original) continua no repo como histórico/fonte, não é mais referenciada
  em nenhum XAML.
- `.csproj`: `ItemGroup` de identidade visual atualizado —
  `kontacto-logo-color.png` e `kpdv-logo-transparent.png` adicionados
  (`kontacto-logo.png`/`kpdv-logo.png` continuam registrados, só não são
  mais usados por nenhuma tela).
- **Verificação**: `dotnet build` → 0 erros; processo lançado,
  `Responding=True`, encerrado limpo via `Stop-Process`. Mesma disciplina —
  **não verificado por screenshot**; usuário deve conferir visualmente
  rodando o app.

#### Correção 2 — texto do título estava errado (mesmo dia, 2026-08-11)

Eu tinha registrado o texto do título como já correto ("KPDV — Kontacto
PDV") na 1ª rodada — leitura errada da própria instrução do usuário.
Usuário corrigiu diretamente: pediu ícone + **"Kontacto PDV"**, sem o
prefixo "KPDV — ". Corrigido nos 3 pontos que carregavam o texto antigo em
`MainWindow.xaml`: `ui:FluentWindow`'s `Title` (título nativo da janela),
`ui:TitleBar`'s `Title`, e o `TextBlock` dentro de `ui:TitleBar.Header`
(o texto visível de fato) — todos trocados de `"KPDV — Kontacto PDV"` pra
`"Kontacto PDV"`. Confirmado por grep que não havia outra ocorrência do
texto antigo em nenhum outro arquivo `.xaml`/`.cs` do projeto (só nos
binários `bin`/`obj`, que ficam desatualizados até o próximo build).

- **Verificação**: `dotnet build` → 0 erros; processo lançado e `Get-Process`
  confirmou `MainWindowTitle = 'Kontacto PDV'` (texto exato, sem "KPDV — "),
  `Responding=True`, encerrado limpo.

#### Correção 3 — cor do texto do título (mesmo dia, 2026-08-11)

Pedido: "koloque a cor da fonte do título na cor da logo da kontacto Azul
marine eu acho". O `TextBlock` do `ui:TitleBar.Header` (`MainWindow.xaml`)
não tinha `Foreground` explícito (herdava a cor padrão do tema). Aplicado
`Foreground="{StaticResource KpdvBrandBrush}"` — já é literalmente o azul
marinho da marca (`#0B2A5B`, `Resources/Brand.xaml`), mesmo tom usado em
toda parte do app (preços, valores em destaque, título das telas de
Pedidos/Venda) e o mesmo `colors.brandPrimary` do site — não precisou
adivinhar/criar cor nova. `dotnet build` → 0 erros; processo vivo
confirmado.

#### Correção 4 — campos de Usuário/Senha ilegíveis (mesmo dia, 2026-08-11)

Reportado: "os campos usuário e senha não estão visíveis. branco sobre
branco parece. na conexão está do mesmo jeto. a caixa do text box precisa
está delineada para o usuário, assim como botão". Causa provável: o
`ui:TextBox`/`ui:PasswordBox`/`ui:Button` do WPF-UI usam um visual Fluent
"underline" por padrão (sem caixa completa) e resolvem cor de
fundo/texto/borda por `DynamicResource`/triggers internos ligados ao
`Appearance` — sem contraste garantido sobre o `KpdvSurfaceBrush` (fundo
claro custom da marca) nem borda visível o bastante pro usuário perceber
o campo.

- **Corrigido com valores LOCAIS explícitos** (não um `Style`/`Setter`) —
  valor local tem prioridade máxima em WPF, acima de qualquer trigger de
  `Style`/`ControlTemplate` interno do WPF-UI, então é a forma garantida
  de funcionar independente do que o `Appearance="Primary"/"Secondary"`
  decidir por baixo dos panos. Todo `ui:TextBox`/`ui:PasswordBox` de
  `LoginView.xaml` e `ConexaoConfigView.xaml` ganhou
  `Background="{StaticResource KpdvSurfaceSecondaryBrush}"` (branco),
  `Foreground="{StaticResource KpdvInkBrush}"` (tinta escura #0B1B33),
  `BorderBrush="{StaticResource KpdvBorderBrush}"` (#D7DEEC) +
  `BorderThickness="1"` — caixa clara e delineada, texto legível. Todo
  `ui:Button`: Primary (Entrar/Salvar) ganhou
  `Background="{StaticResource KpdvBrandBrush}"` (navy) +
  `Foreground="{StaticResource KpdvOnBrandBrush}"` (branco) +
  `BorderBrush="{StaticResource KpdvBrandBrush}"`; Secondary (Cancelar)
  ganhou fundo branco + texto escuro + a mesma borda cinza-azulada —
  ambos com `BorderThickness="1"` pra ficarem visivelmente delineados.
- **Escopo**: só `LoginView.xaml`/`ConexaoConfigView.xaml` (as 2 telas
  reportadas com o problema) — `VendaView.xaml`/`PedidosView.xaml`/
  `ConfiguracoesView.xaml` não foram tocadas (nunca reportado problema
  ali, e essas telas só são alcançadas pós-login, ainda não exercitadas
  ao vivo nesta sessão — se o mesmo problema aparecer lá, aplicar o
  mesmo tratamento quando reportado).
- **Verificação**: `dotnet build` → 0 erros (1 processo de teste anterior
  preso travando a cópia do `.exe`, encerrado antes do rebuild); processo
  lançado, título `Kontacto PDV`, `Responding=True`, encerrado limpo.
  **Sem screenshot**, mesma disciplina — contraste/legibilidade final
  precisam ser conferidos visualmente pelo usuário.
- **Confirmado ao vivo pelo usuário, mesmo dia** — colou screenshot da
  tela de Login já com os campos legíveis/delineados, título navy e o
  rodapé/logo corretos (ver Correções 1-3 acima) — nenhum ajuste adicional
  pedido nesse retorno.

#### Correção 5 — cantos arredondados em todos os campos/botões do projeto (mesmo dia, 2026-08-11)

Pedido: "caixa de texto e botões arredondado em todas as janelas desse
projeto, é possível?". Investigação (lendo o template REAL de `Button`/
`TextBox`/`PasswordBox` na fonte oficial do WPF-UI, tag `4.3.0` do
`lepoco/wpfui` no GitHub — a mesma versão instalada, via `gh api`) achou
que os 3 controles resolvem o próprio `CornerRadius` a partir de uma
**única chave compartilhada**: `Setter Property="Border.CornerRadius"
Value="{DynamicResource ControlCornerRadius}"` — valor padrão da lib,
`4,4,4,4` (`src/Wpf.Ui/Resources/Variables.xaml`), sutil demais pra o
usuário notar.

- **Corrigido num único ponto**: `<CornerRadius x:Key="ControlCornerRadius">6,6,6,6</CornerRadius>`
  adicionado em `Resources/Brand.xaml` — mesmo raio `radius.sm` já usado em
  campos/botões no app Web (`frontend/src/theme/colors.ts`). Como
  `Brand.xaml` já é mesclado DEPOIS do tema base do WPF-UI em `App.xaml`
  (`MergedDictionaries`: `Wpf.Ui.xaml` primeiro, `Brand.xaml` depois — regra
  do WPF é "o último da lista vence" quando duas dictionaries do mesmo
  nível definem a mesma chave), essa redefinição vale automaticamente pra
  TODO `Button`/`TextBox`/`PasswordBox` de QUALQUER tela do projeto — não
  precisou tocar em nenhuma tela individualmente.
- **Verificação**: `dotnet build` → 0 erros (um valor malformado de
  `CornerRadius` teria quebrado o parse XAML na hora); processo lançado e
  vivo. Tentativa de verificação mais profunda (instanciar os controles
  reais fora do `.exe`, ver valor resolvido em runtime) esbarrou numa
  limitação de resolução de `pack://` URI fora de um host de app de
  verdade — não chegou a comprometer a confiança na correção, já que o
  `.exe` real segue compilando/subindo normalmente. Confirmado ao vivo
  pelo usuário no mesmo retorno da Correção 4 (screenshot mostrando cantos
  arredondados nos campos/botão).

### Trocar conexão direto na tela de Login (2026-08-11) — IMPLEMENTADO

Pedido: "na tela de login, tem que informar qual a conexão está sendo
usada para se conectar. precisamos alterar essa conexão da tela de login
caso seja necessário. com usuário e senha de um dos magníficos". Antes
disso, a única forma de trocar a conexão de uma máquina já configurada era
logar primeiro e usar o ícone de conexão no `TitleBar` (`ConexaoConfigView`,
ver seção "Configurações de Conexão" acima) — inconveniente quando a
conexão está tão errada que ninguém consegue nem logar pra chegar lá.

- **Conexão em uso sempre visível**: novo bloco no topo do formulário de
  Usuário/Senha (`LoginViewModel.ConexaoResumo`, `"{Empresa} — {Servidor} /
  {Banco}"`) — texto pequeno, mudo, com um botão "Trocar" ao lado.
- **3 sub-estados novos na tela de Login** (`enum TrocaConexaoEstado`:
  `Fechado`/`Autorizando`/`Editando`, mesmo padrão de enum +
  `EnumEqualsToVisibleConverter` já usado pelos painéis inline da
  `VendaView`, aplicado aqui pela 1ª vez fora da Venda):
  1. **Fechado** — formulário normal de Usuário/Senha (como já era),
     mais o bloco "Conexão em uso" acima.
  2. **Autorizando** — pede Usuário/Senha de um "3 Magnífico" (Gerente/
     Supervisor/Master), **validados contra a conexão ATUAL** (a que será
     eventualmente trocada) via uma chamada normal a `POST /api/login`
     — mas **nunca chama `SessionService.SetLogin`**, é só uma verificação
     de credencial (`LoginViewModel.VerificarAutorizacaoAsync`), não
     estabelece sessão nenhuma. Critério "3 Magnífico" checado via novo
     método estático `SessionService.EhManagerFuncao(UsuarioInfo?,
     FuncionarioInfo?)` — extraído da lógica de instância já existente
     (`IsManagerFuncao`) pra não duplicar o critério nem precisar mutar o
     `SessionService` singleton só pra checar uma credencial que não é a
     do operador.
  3. **Editando** — autorizado, mostra o MESMO formulário de Empresa/
     Servidor/Banco/API já usado pelo ícone de conexão pós-login —
     **reaproveita `ConexaoConfigViewModel` por inteiro** (não duplica
     campos/lógica de salvar): `LoginViewModel` recebe um
     `ConexaoConfigViewModel` próprio via DI (já era `AddTransient`, sem
     mudança de registro), e o `StackPanel` desse estado troca seu
     `DataContext` pra `{Binding ConexaoConfig}`. `ConexaoConfigViewModel.
     Inicializar()` ganhou um overload `Inicializar(Conexao? atual)` — o
     original lia `SessionService.Conexao` (só existe pós-login), o novo
     aceita a conexão explícita (a `ConexaoAtual` da tela de Login, ainda
     sem sessão nenhuma).
- **Evento `Salvo` do `ConexaoConfigViewModel` tratado de forma diferente
  aqui do que no fluxo pós-login**: no ícone de conexão pós-login, Salvar
  desloga e recarrega a `MainWindow` inteira (a sessão antiga fica
  inconsistente com a conexão nova). Na tela de Login não existe sessão
  pra deslogar — `LoginViewModel` assina o mesmo evento e só relê a
  conexão do disco (`OnConexaoTrocadaAsync`), volta pro estado `Fechado`
  já com `ConexaoResumo` refletindo a conexão nova, campos de Usuário/
  Senha limpos. Evento `Cancelado` simplesmente volta pro estado
  `Fechado` (mesmo padrão do botão Cancelar já existente nesse VM).
- **Verificação**: `dotnet build` → 0 erros de primeira; processo lançado,
  título `Kontacto PDV`, `Responding=True` — a tela abriu normalmente numa
  máquina já configurada (mostrando Usuário/Senha, não o formulário de
  primeira config), confirmando que `InicializarAsync` e o binding dos 3
  novos estados carregaram sem erro de XAML/binding.

#### Correção — botão "Verificar" sem nenhum retorno visível (mesmo dia, 2026-08-11)

Usuário testou ao vivo pela 1ª vez (screenshot mostrando o painel
"Autorização necessária" preenchido com `KONTACTO`/`$KONT2011`) e
reportou: "clico em verificar e não tem nenhuma ação ou mensagem".

Investigação (sem conseguir reproduzir o silêncio nem confirmar a causa
exata — documentado honestamente, não um "achei e corrigi" de verdade):

- **Conexão da máquina de teste**: `conexao.json` aponta pra
  `Empresa=BAIXO BRISA, Servidor=MINIMACHINE, Banco=BD_BAIXOBRISA,
  Api=http://192.168.18.50:8081/` — um servidor de cliente real, não o
  backend local desta sessão. Testado direto via `curl` contra
  `POST http://192.168.18.50:8081/api/login` com as mesmas credenciais:
  respondeu em **0.03s** com `success:true, master:true` — a rede/
  credencial/backend estão OK, não é problema de conectividade nem de
  timeout.
- **Revisão de código não achou bug óbvio** no fluxo (`VerificarAutorizacaoAsync`,
  `PodeVerificarAutorizacao`, notificação de `CanExecute` nos
  `On*Changed` parciais — mesmo padrão já usado e comprovado em
  `EntrarAsync`/`PodeLogar`).
- **Tentativa de reproduzir headless** (projeto console descartável em
  `tools/DiagLogin`, instanciando `LoginViewModel` via DI real e chamando
  `VerificarAutorizacaoCommand.ExecuteAsync` direto, sem UI) travou —
  mas por uma limitação do PRÓPRIO harness (um `System.Windows.Application`
  sem `Application.Run()` rodando não tem message pump pra processar
  `Dispatcher.Invoke` vindo de uma continuação `.ConfigureAwait(false)`
  que retomou numa thread do pool — no app real isso não é problema
  porque `Application.Run()` já está bombeando mensagens o tempo todo).
  Não prova nem descarta o bug real; só não serviu como reprodução válida.
  Projeto removido depois (`tools/DiagLogin`, nunca fez parte do app).
- **Hipótese mais provável, não confirmada**: alguma exceção não prevista
  (ou uma resposta com `message` vazio) fazendo a `Task` do comando
  falhar sem nada visível — `AsyncRelayCommand` por padrão RELANÇA a
  exceção (não swallow silencioso, ao contrário do que se imaginaria à
  primeira vista — confirmado lendo `AsyncRelayCommand.cs` na fonte
  oficial do CommunityToolkit.Mvvm, tag `v8.4.0`), então um crash puro
  seria mais provável que um silêncio total — mas sem log nenhum no KPDV
  até agora, não dava pra confirmar se algo chegou a lançar.

**Corrigido de forma defensiva** (não é a causa raiz confirmada, é
blindagem pra garantir que isso nunca mais aconteça sem deixar rastro,
seja qual for a causa real):

- **Novo `Services/AppLog.cs`** — log mínimo em arquivo
  (`%AppData%\KPDV\logs\kpdv-AAAAMMDD.log`, mesmo espírito do log diário
  já usado em `start-backend.ps1`/`start-frontend.ps1`), sem
  níveis/rotação, só `AppLog.Error(contexto, exception)`. Primeira peça
  de logging do KPDV — não existia nenhuma antes.
- **`catch (Exception ex)` adicionado** em `VerificarAutorizacaoAsync` E
  `EntrarAsync` (parceiro do mesmo risco, mesmo já em produção) — além do
  `catch (ApiConnectionException)` já existente, grava no `AppLog` e
  mostra uma mensagem amigável genérica em vez de deixar a `Task` falhar
  sem eco nenhum.
- **`response.Message` vazio/nulo agora cai num fallback** ("Usuário ou
  senha inválidos.") em vez de deixar a caixa de erro sem texto nenhum
  (que ficaria invisível — `StringToVisibleConverter` colapsa string
  vazia).
- **Feedback visual de "processando" adicionado** (`EntrarButtonText`/
  `VerificarButtonText`, vira "Entrando..."/"Verificando..." durante a
  chamada) — gap real contra a regra `[GLOBAL]` já existente no projeto
  ("Feedback visual em processos demorados (>3s)", CLAUDE.md) que a tela
  de Login nunca tinha aplicado (só desabilitava o botão, sem indicar
  visualmente que algo estava em andamento) — mesmo que não seja A causa
  raiz, era um gap real encontrado durante a investigação.
- **Verificação**: `dotnet build` → 0 erros; processo vivo confirmado.
  **Causa raiz não confirmada** — próxima vez que isso acontecer (com o
  log já em produção), checar `%AppData%\KPDV\logs\kpdv-*.log` antes de
  investigar de novo do zero.

#### Correção — causa raiz CONFIRMADA (mesmo dia, 2026-08-11)

Usuário testou de novo (rodando via **Visual Studio 2026 em modo Debug**,
achado importante em si — nenhum teste anterior desta sessão tinha um
depurador anexado) e desta vez colou o print da exceção real capturada
pelo VS: `System.InvalidOperationException: 'O thread de chamada não pode
acessar este objeto porque ele pertence a um thread diferente.'` em
`KPDV.ViewModels.LoginViewModel.OnAutorizandoChanged(bool value)`. Essa
evidência concreta (não mais suposição) permitiu achar e confirmar 3 bugs
reais, todos verificados contra o comportamento documentado/fonte oficial
do WPF-UI antes de corrigir — nenhum chute:

1. **Causa raiz de "clico e não acontece nada"**: `finally { Autorizando =
   false; }` (`VerificarAutorizacaoAsync`) e `finally { IsBusy = false; }`
   (`EntrarAsync`) eram os ÚNICOS pontos de mutação de estado que NÃO
   passavam por `App.Current.Dispatcher.Invoke(...)` — como o método
   retoma numa thread do pool depois do `.ConfigureAwait(false)`, esse
   `finally` roda fora da UI thread. Mudar `Autorizando`/`IsBusy` dispara
   `OnAutorizandoChanged`/`OnIsBusyChanged` → `NotifyCanExecuteChanged()`
   → WPF tenta atualizar o `IsEnabled` do botão vinculado DIRETO na thread
   errada → exceção. Como isso acontece DENTRO do próprio `finally`, fica
   fora do alcance de qualquer `catch` do `try` acima — por isso a
   blindagem da rodada anterior (catch-all) não pegava. Corrigido
   envolvendo as 2 atribuições em `App.Current.Dispatcher.Invoke(() =>
   ... = false)`, igual a todas as outras mutações de estado no mesmo
   método.
2. **Senha nunca chegava no ViewModel**: `Wpf.Ui.Controls.PasswordBox.
   PasswordProperty` é registrado com `PropertyMetadata` simples, SEM
   `FrameworkPropertyMetadataOptions.BindsTwoWayByDefault` (confirmado
   lendo `PasswordBox.cs` na fonte oficial, tag `4.3.0` do `lepoco/wpfui`)
   — diferente de `TextBox.Text`, que tem esse flag. Sem `Mode=TwoWay`
   explícito, `Password="{Binding X, UpdateSourceTrigger=PropertyChanged}"`
   vira OneWay (só ViewModel→tela) — a senha digitada nunca era
   propagada pro `AutorizacaoSenha`/`Senha` do ViewModel, então
   `PodeVerificarAutorizacao()`/`PodeLogar()` ficavam sempre `false`
   (campo "vazio" do ponto de vista do C#) e o clique nunca disparava o
   comando. **Afeta os dois campos de senha do app** (login normal E
   autorização) — corrigido com `Mode=TwoWay` explícito nos 2
   `ui:PasswordBox` de `LoginView.xaml`.
3. **Senha digitada permanecendo visível ao reabrir o painel** (reportado
   pelo usuário como risco de segurança, "isso não pode acontecer"):
   mesmo com o binding corrigido, o `PasswordBox` do WPF-UI tem uma lógica
   interna (`HandleRevealedModeUpdate`) que "briga" contra um reset vindo
   de fora enquanto o modo "revelar" (👁) está ligado — comparando
   `Password` com `Text` e resincronizando pro `Text` antigo. Corrigido em
   `LoginView.xaml.cs`: novo handler `ViewModel_PropertyChanged`,
   assinado no construtor, que reseta os 2 `PasswordBox` DIRETO (`Text`,
   `Password`, e `IsPasswordRevealed` via `SetValue` já que o setter
   público é privado) sempre que `TrocaConexaoEstado`/`ConexaoConfigurada`
   mudam — bypassa por completo a lógica de binding/revelar que causa o
   problema.
4. **Botão "Verificar" sumindo ao passar o mouse** (reportado pelo
   usuário): cor de fundo/borda no hover e no clique são propriedades
   PRÓPRIAS do `Wpf.Ui.Controls.Button` — `MouseOverBackground`,
   `MouseOverBorderBrush`, `PressedBackground`, `PressedForeground` —
   separadas de `Background`/`Foreground`/`BorderBrush` (confirmado lendo
   `Button.xaml` na mesma fonte oficial). Como eu só tinha fixado os 3
   primeiros como valor local, o hover caía de volta na cor padrão da lib
   (clara) enquanto o texto branco continuava fixo — texto branco sobre
   fundo claro, "sumindo". Corrigido adicionando as 4 propriedades como
   valor local em **todos os 9 botões customizados** desta rodada
   (`LoginView.xaml` e `ConexaoConfigView.xaml`, não só o "Verificar") —
   botões navy usam `KpdvBrandHoverBrush` (já existia em `Brand.xaml`,
   pensado exatamente pra isso, só não estava em uso) pro hover/pressed;
   botões brancos usam `KpdvSurfaceSunkenBrush`/`KpdvBrandTintBrush`.
- **Verificação**: `dotnet build` → 0 erros de C# (só falha esperada de
  cópia do `.exe`, travado pela própria sessão de Debug do usuário no
  VS2026 — não encerrada, não é processo meu). Aguardando o usuário parar
  o debug (Shift+F5) e testar de novo (F5) pra confirmar os 4 pontos.

#### Login funcionou — 1ª vez na história do projeto — e destravou o próximo bug (mesmo dia, 2026-08-11)

Com os 4 pontos acima corrigidos, o usuário conseguiu logar de verdade
pela primeira vez nesta sessão (conexão BARESTELA, usuário master) — e
isso, por sua vez, expôs o PRÓXIMO trecho de código nunca antes
exercitado com login real: `MainWindow.MostrarVendaAsync()` (chamado
automaticamente após `LoginSucceeded`). Novo crash, também capturado com
print da exceção real do VS2026: `System.NullReferenceException:
'Object reference not set to an instance of an object.'` dentro do
próprio `Wpf.Ui.dll`, na linha `NavView.ReplaceContent(_vendaView,
null);`.

- **Causa**: `MainWindow.xaml.cs::MostrarVendaAsync()` fazia
  `NavView.Visibility = Visibility.Visible;` e, na LINHA SEGUINTE,
  síncrona, chamava `NavView.ReplaceContent(...)`. Confirmado lendo a
  fonte oficial do WPF-UI (`NavigationView.Navigation.cs`, tag `4.3.0`):
  `ReplaceContent` → `UpdateContent` → `NavigationViewContentPresenter.
  Navigate(content)` — `NavigationViewContentPresenter` é uma PEÇA DE
  TEMPLATE (`OnApplyTemplate`), que só existe depois de um passe de
  layout do WPF. Marcar `Visibility = Visible` num elemento antes
  Collapsed NÃO aplica o template na hora — isso só acontece
  assincronamente no próximo passe de layout. Chamar `ReplaceContent` na
  linha seguinte corre na frente desse passe, e a peça interna ainda é
  `null` nesse instante → `NullReferenceException` dentro do próprio
  `Wpf.Ui.dll`.
- **Corrigido**: `NavView.UpdateLayout()` adicionado entre as duas linhas
  — força o passe de layout (inclusive aplicação do template) a
  acontecer AGORA, de forma síncrona, garantindo que
  `NavigationViewContentPresenter` já existe antes do `ReplaceContent`.
  Único ponto afetado no arquivo — os outros 3 usos de `ReplaceContent`
  (`MostrarVendaConteudo`/`MostrarPedidos`/`MostrarConfiguracoesConteudo`)
  rodam a partir de `NavView_SelectionChanged`, ou seja, com o `NavView`
  já visível havia tempo (usuário clicando dentro do menu já aberto) —
  sem a mesma corrida, não precisaram de ajuste.
- **Contexto**: este é código da Fase 1 do Menu Lateral (2026-08-10, ver
  seção própria de PENDENCIAS.md > "KPDV"), não desta rodada — só nunca
  tinha sido testado com um login de verdade até agora (mesma limitação
  "nunca testado com login real" registrada em TODAS as fases anteriores
  do projeto). Primeiro bug de um caminho de código que provavelmente
  tem outros ainda não descobertos, mais adiante no fluxo pós-login
  (Venda, Pedidos, Configurações) — nenhum desses foi exercitado ainda.
- **Verificação**: `dotnet build` → 0 erros de C# (mesma sessão de Debug
  do usuário travando a cópia do `.exe`, não é erro de código).

#### Mais 2 achados no mesmo teste — mensagem de erro crua + painéis "invisíveis" (mesmo dia, 2026-08-11)

Com o crash do `NavView` corrigido, o usuário chegou até a tela de Venda de
verdade e bateu em mais 2 problemas reais, ambos no mesmo teste:

**1) Erro cru vazando na tela de Venda** — "abrir venda" falhou contra
GERDELL/BARESTELA com o texto cru do driver direto na tela: `Erro ao abrir
venda: (20047, b'DB-Lib error message 20003, severity 6:\nAdaptive Server
connection timed out\nDB-Lib error message 20047, severity 9:\nDBPROCESS is
dead or not enabled\n')`. Investigação: `GERDELL` é a PRÓPRIA máquina de
teste (`$env:COMPUTERNAME` confirma) e o SQL Server está mesmo escutando
normalmente em `1433` (confirmado via `Get-NetTCPConnection` filtrado pelo
processo `sqlservr` — uma checagem inicial sem esse filtro deu falso
negativo) — não é problema de porta/rede, foi uma conexão que caiu NO MEIO
da query (exatamente o cenário que CLAUDE.md > "Mensagens de Erro" já
previa como fora do escopo da correção original: "erros de query já
executando com conexão aberta... continuam podendo vazar texto técnico...
fica pra quando aparecer um caso concreto" — este é esse caso).
- **Corrigido em `backend/db/connection.py`**: novo `is_connection_error(e)`
  (mesma lista de padrões de `friendly_db_error`, mais os padrões de
  conexão que caem NO MEIO de uma query — `"dbprocess is dead"`,
  `"server connection lost"`, `"connection is closed"`, `"read from the
  server failed"`, `"not connected to any mssql server"`) +
  `friendly_db_error` ganhou um novo `if` pra esses padrões ("A conexão
  com o banco de dados caiu no meio da operação..."). `is_connection_error`
  existe pra decidir SE aplica a tradução amigável — nunca confundir um
  erro de negócio genuíno (chave duplicada, violação de constraint) com
  um erro de conexão.
- **Aplicado em `backend/services/checkout_service.py::_abrir_venda_sync`**
  (o caso concretamente reportado) — o `except` que envolve a query
  (depois da conexão já aberta) agora usa `friendly_db_error(e) if
  is_connection_error(e) else f"Erro ao abrir venda: {e}"`. **Escopo
  deliberadamente contido**: este mesmo arquivo tem ~19 outros `except`
  no mesmo formato (`_get_venda_sync`, `_buscar_produto_sync`,
  `_add_item_sync`, `_importar_dav_sync`, `_fechar_venda_sync`,
  `_cancelar_venda_sync`, etc.) que têm a MESMA lacuna latente — não
  corrigidos nesta rodada (só o caso concreto reportado), mas registrados
  aqui como pendência conhecida pra quando/se aparecer outro caso
  concreto num desses, seguindo o mesmo princípio de não-retroatividade
  já usado em outras regras deste projeto.
- **Verificação**: `python -c "import services.checkout_service"` → sem
  erro; `pytest tests/unit/test_checkout_service.py` → 63/63 passando;
  backend reiniciado (supervisor `start-backend.ps1`) com a correção em
  produção nesta máquina.

**2) Painéis "Configuração de Impressão"/"Configuração de Balança"
praticamente invisíveis** — texto flutuando sobre o fundo escurecido, sem
nenhum cartão/superfície visível por trás. Causa: NENHUM dos `ui:Card`
usados como painel overlay (backdrop escurecido `#B3000000` + card
centralizado) em `VendaView.xaml`/`PedidosView.xaml` tinha `Background`
explícito — o `ui:Card` do WPF-UI resolve isso por `DynamicResource`, e
nesta configuração de tema (Light forçado + backdrop Mica) o resultado
prático é quase transparente sobre o overlay escuro, deixando só o texto
visível e sem contraste real. Reportado só pros 2 painéis de Impressão/
Balança, mas o MESMO padrão (`ui:Card` sem Background, dentro do backdrop
escurecido) se repete em TODOS os painéis dessas 2 telas — corrigido de
forma sistemática, não só nos 2 relatados:
- **`VendaView.xaml`**: os 7 painéis (Fechar Venda, Desconto, Cancelar
  Venda, Importar DAV, Configuração de Impressão, Configuração de
  Balança, Atualização) ganharam
  `Background="{StaticResource KpdvSurfaceSecondaryBrush}"` (branco —
  mesmo brush já validado ao vivo nos cards de Login/Configurações de
  Conexão).
- **`PedidosView.xaml`**: os 3 painéis overlay (+Item, Faturar, Novo
  Pedido) ganharam o mesmo tratamento. As 5 colunas de tipo (Mesa/
  Comanda/Balcão/Entrega/Fiado, `Width="280"`) e o card de resumo no topo
  NÃO foram tocados — não são overlay sobre backdrop escuro, ficam sobre
  o fundo claro normal da página, risco bem menor e não reportado.
- **`ConfiguracoesView.xaml`**: card único da tela também NÃO foi tocado
  pelo mesmo motivo (fica sobre fundo claro normal, não um backdrop
  escurecido) — não reportado como quebrado.
- **Verificação**: `dotnet build` → 0 erros de XAML/C# (mesma sessão de
  Debug do usuário travando só a cópia do `.exe`).

#### Achado real e não relacionado — incompatibilidade de versão TDS bloqueava a conexão "Baixo Brisa Real" (mesmo dia, 2026-08-11)

Aproveitando o teste, o usuário conectou direto no SQL Server do
`DESKTOP-TDK482U` ("Baixo Brisa Real", pendência antiga registrada em
`project_login_baixo_brisa_sa_password.md` como suspeita de senha `sa`
divergente) via SSMS/VS com `sa`/`Cmslrav@155` — **conectou com sucesso**,
provando que a hipótese antiga (senha errada) estava incorreta: essa é
literalmente a MESMA senha já configurada como padrão do backend
(`SQL_LOCAL_PASSWORD`, `db/connection.py`), sem nenhuma variável de
ambiente sobrescrevendo (confirmado via `[Environment]::
GetEnvironmentVariable` nos 3 escopos). Rede também não era o problema —
`Test-NetConnection` já tinha confirmado a porta 1433 acessível.

Testado com `pymssql.connect` direto (mesmo método usado por
`_open_conn`), variando só `tds_version`:
- `DESKTOP-TDK482U` (SQL Server 2014 SP1, build **12.0.2000**) — falha com
  `(20002) Adaptive Server connection failed` em TDS 7.1/7.2/7.3/7.4 (o
  padrão do backend era 7.4); **conecta instantaneamente em TDS 7.0**.
- `GERDELL` (SQL Server 2014 SP2, build **12.0.5000** — build mais nova/
  mais atualizada) — conecta em QUALQUER versão testada, 7.0 a 7.4.

**Causa raiz real**: incompatibilidade de negociação de protocolo TDS
entre o FreeTDS/pymssql do backend e uma versão de SQL Server 2014 menos
atualizada — não é rede, não é senha, nunca foi. TDS é retrocompatível
(servidor mais novo aceita protocolo mais antigo sem problema), então a
versão mais baixa é a escolha mais ampla.

**Corrigido em `backend/db/connection.py`** — pedido explícito do
usuário ("TEM QUE PREVER ISSO", repetido 2x): não só baixar o padrão
(`SQL_TDS_VERSION` de `"7.4"` pra `"7.0"`), mas também um **retry em
cascata** (`_TDS_VERSION_FALLBACKS = ("7.0","7.1","7.2","7.3","7.4")`) —
`_open_conn` tenta a versão configurada primeiro; se falhar
especificamente com o padrão de negociação de protocolo
(`_e_falha_negociacao_tds`, checa só `"adaptive server connection
failed"`/`"net-lib error"` — nunca acionado por senha errada/host fora
do ar/timeout, onde trocar a versão não ajudaria e só atrasaria o erro
real), tenta as outras versões em sequência antes de desistir. Isso
protege QUALQUER instalação de cliente futura com uma versão de SQL
Server ainda não vista, sem precisar de uma nova rodada de investigação
manual — a motivação explícita do pedido do usuário.
- **Verificação em 3 camadas**: `pytest tests/unit/test_db_connection.py`
  → 8/8; `pytest tests/unit` (suíte inteira) → 1807/1808 (a 1 falha é a
  mesma pré-existente e sem relação, data hardcoded em teste de CNAB
  Itaú); backend reiniciado em produção nesta máquina; **teste end-to-end
  real via `POST /api/login`** contra `DESKTOP-TDK482U`/`BD_BAIXOBRISA`
  com usuário `KONTACTO` → `success:true, master:true` — confirmado
  funcionando de ponta a ponta, não só no teste isolado do driver.

#### Mais um achado real no mesmo teste — `codigo_int` como número em vez de string quebrava o login de usuário comum (mesmo dia, 2026-08-11)

Com a conexão já corrigida (TDS 7.0), o usuário testou login de verdade
com um usuário COMUM (não master) — `carlos`, senha real fornecida pelo
próprio usuário pra viabilizar o teste — e bateu em outro erro real,
diferente do de conexão: `"O servidor retornou uma resposta em formato
inesperado."` (mensagem do KPDV, `ApiClient.HandleAsync`'s
`catch (JsonException)`).

**Causa raiz**: `funcionarios.codigo_int` é coluna `INT` no SQL Server —
confirmado com uma consulta somente-leitura direta contra
`BD_BAIXOBRISA` (`SELECT codigo_int, ... FROM funcionarios WHERE
nome_guerra = 'carlos'` → `codigo_int: 2` tipo `int`). O backend
(`auth_service._enrich_funcionario`) devolvia esse valor sem conversão,
saindo como NÚMERO no JSON (`"codigo_int": 2`). O modelo C# do KPDV
(`Models/LoginModels.cs::FuncionarioInfo.CodigoInt`) é `string?`
(deliberado — mesmo motivo já documentado pra `CodFuncao`: precisa
acomodar o valor sintético do usuário master). `System.Text.Json` não
converte número→string automaticamente por padrão — a desserialização
inteira falhava, e como isso acontece DEPOIS de um HTTP 200 válido (JSON
malformado em relação ao TIPO esperado, não erro HTTP), a mensagem
genérica de "formato inesperado" era a única pista.

**Por que só apareceu agora**: o login master (`KONTACTO`, testado antes
e funcionando) usa `_build_master_session` — uma sessão SINTÉTICA que
nem inclui `codigo_int` no dict retornado, então nunca exercitou esse
campo. Só um login de usuário REAL (com uma linha de verdade em
`funcionarios`) expõe o bug — mais um caso do padrão já repetido nesta
sessão: "nunca testado com login real" escondendo bugs em cascata,
revelados um de cada vez conforme o teste avança mais fundo no fluxo.

- **Corrigido em `backend/services/auth_service.py::_enrich_funcionario`**:
  `out["codigo_int"] = str(out["codigo_int"])` quando presente e não-nulo,
  antes de qualquer outro processamento.
- **Verificação**: `pytest tests/unit` → 1807/1808 (mesma falha
  pré-existente sem relação); backend reiniciado; **teste end-to-end real**
  via `POST /api/login` com `carlos`/senha real contra `DESKTOP-TDK482U`/
  `BD_BAIXOBRISA` → `success:true`, `"codigo_int":"2"` (string, confirmado
  no JSON de resposta) — corrigido de ponta a ponta.
- **Escopo**: só `codigo_int` tinha esse tipo de mismatch — os outros
  campos de `FuncionarioInfo`/`UsuarioInfo` (nome_guerra, nome, cod_funcao,
  situacao, administrador, classe) já batiam com os tipos SQL reais
  (todos string/int corretamente alinhados, conferido linha a linha contra
  os dados reais de "carlos"). Não há outro campo com a mesma lacuna
  neste endpoint.

#### Regressão do próprio fix de TDS — datas viravam `str` crua, quebrando `.isoformat()` (mesmo dia, 2026-08-11, achado ao vivo no app web/Pedido Bar contra "Baixo Brisa Real")

O fix de cascata TDS acima (baixar `SQL_TDS_VERSION` padrão pra `"7.0"` e
tentar `_TDS_VERSION_FALLBACKS` em ordem CRESCENTE, `("7.0","7.1",...
"7.4")`) resolveu a conexão mas introduziu uma regressão **sistêmica**:
como TDS 7.0 é a versão mais permissiva, ela passou a negociar com
sucesso pra praticamente QUALQUER servidor (não só `DESKTOP-TDK482U`) —
inclusive servidores que suportam versões mais novas, como `GERDELL`.
TDS 7.0 é anterior ao tipo `DATE` do protocolo (introduzido só a partir de
TDS 7.3/SQL Server 2008): negociando em 7.0, o FreeTDS/pymssql não
reconhece colunas `DATE` como tipo temporal e devolve `str` cru em vez de
`datetime.date` — todo `campo.isoformat()` direto (sem checar o tipo)
quebra com `'str' object has no attribute 'isoformat'`. Reproduzido ao
vivo no app web, tela Pedido Bar (`app/pedidos.tsx`), contra
`DESKTOP-TDK482U`/`BD_BAIXOBRISA` ("Baixo Brisa Real").

**Escala do problema**: `grep -rn "\.isoformat()"` no backend inteiro
encontrou **114 ocorrências em 53 arquivos** — o padrão
`campo.isoformat() if campo else None` (sem checar tipo) está espalhado
por praticamente todo service que formata data pra JSON.

**Corrigido em 2 camadas**:
1. **Causa raiz** (`backend/db/connection.py`): `_TDS_VERSION_FALLBACKS`
   invertido pra ordem DECRESCENTE (`("7.4","7.3","7.2","7.1","7.0")`) e
   `SQL_TDS_VERSION` padrão voltou pra `"7.4"` — tenta a versão mais
   moderna (melhor fidelidade de tipo) primeiro, só degradando quando a
   negociação genuinamente falha. Resolve pra qualquer servidor que
   suporte uma versão ≥ 7.3 (ex.: `GERDELL`) — volta a ter tipagem `DATE`
   correta.
2. **Defesa** (não resolvida só pela camada 1): `DESKTOP-TDK482U`
   especificamente só nego TDS 7.0 (SQL Server 2014 SP1 build 12.0.2000
   — ver achado original acima), então mesmo com a ordem corrigida, ele
   AINDA devolve `str` crua pra colunas `DATE` — é uma limitação real do
   driver/servidor, não resolvível por ordem de tentativa. Criado helper
   `iso(value)` em `db/connection.py` (tolera `str` OU
   `date`/`datetime`, mesmo padrão defensivo que `_to_json_safe` já usava
   internamente) e aplicado nos 5 pontos de
   `services/pedidos_service.py` (`_list_pedidos_sync`,
   `_get_pedido_sync`) — a tela que quebrou ao vivo.
- **Verificação**: `pytest tests/unit` → 1807/1808 (mesma falha
  pré-existente sem relação, CNAB Itaú data hardcoded); backend
  reiniciado; teste end-to-end real via `POST /api/pedidos` contra
  `DESKTOP-TDK482U`/`BD_BAIXOBRISA` → 22 pedidos reais retornados com
  datas corretas (antes: `success:false`, erro de isoformat).
- **Pendência real, NÃO resolvida nesta rodada**: os outros ~109
  ocorrências de `.isoformat()` cru em ~51 arquivos continuam vulneráveis
  ao mesmo bug pra qualquer servidor cliente que só negocie TDS < 7.3
  (mesma classe de SQL Server antigo/desatualizado que `DESKTOP-TDK482U`
  representa) — a causa raiz (camada 1) já cobre a maioria dos casos, mas
  não windows como este. Trocar `campo.isoformat() if campo else None`
  por `iso(campo)` (importar de `db.connection`) em cada arquivo quando
  ele for tocado por outro motivo, em vez de uma varredura retroativa
  agora — mesmo princípio de não-retroatividade automática já usado nas
  regras `[GLOBAL]` do CLAUDE.md.

#### Mais um achado real no mesmo teste — Login do KPDV usava `pymssql.connect` direto, sem a cascata TDS (mesmo dia, 2026-08-11)

Com o backend corrigido (camada 1 acima), o usuário testou o LOGIN do
KPDV contra `DESKTOP-TDK482U`/`BD_BAIXOBRISA` e bateu em
"Não foi possível conectar ao servidor de banco de dados" — a MESMA
falha de negociação TDS que a cascata deveria evitar. Causa: a tela de
Login (`auth_service._sql_login_sync`) sempre abriu sua PRÓPRIA conexão
via `pymssql.connect(..., tds_version=SQL_TDS_VERSION)` direto — nunca
passou por `_open_conn` (roda ANTES de qualquer sessão existir, então não
tinha motivo histórico pra reaproveitar aquele helper) — então nunca
ganhou a cascata de fallback quando ela foi criada só dentro de
`_open_conn`.

**Corrigido** extraindo a lógica de cascata de `_open_conn` pra um novo
helper `_connect_with_tds_fallback(server, user, password, banco,
timeout)` em `db/connection.py` (levanta a exceção crua, sem traduzir —
quem chama decide) — `_open_conn` e `auth_service._sql_login_sync` agora
os dois chamam esse mesmo helper, cada um com seu próprio
tratamento de erro em cima (o de `auth_service` preserva `attempted`/
`error_step`/`error_line` pro payload de diagnóstico que já existia).
- **Verificação**: `pytest tests/unit` → 1807/1808 (mesma falha
  pré-existente); backend reiniciado; teste end-to-end real via
  `POST /api/login` com senha intencionalmente errada contra
  `DESKTOP-TDK482U`/`BD_BAIXOBRISA` → `"Usuário ou senha inválidos."`
  (rejeição de CREDENCIAL, não mais falha de CONEXÃO) — confirma que a
  conexão em si abre com sucesso agora.

#### Mais um achado real — painel Pedido Bar escondia pedidos abertos há mais de 1 dia, exceto Fiado (mesmo dia, 2026-08-11)

Comparando lado a lado com o legado VB6 (tela "Pedidos Abertos",
`FrmManPedBar.frm`) contra os mesmos dados reais de `BD_BAIXOBRISA`: o
VB6 mostrava 6 pedidos abertos (4 Comanda + 2 Mesa, total R$845,50,
alguns abertos desde janeiro/maio) — o painel web (`app/pedidos.tsx`)
mostrava só 3 pedidos Fiado antigos (R$190,00), com Mesa/Comanda/Balcão/
Entrega todos zerados.

**Causa raiz**: `pedidos.tsx` sempre envia `data_ini`/`data_fim` = hoje
por padrão (não é um filtro opcional, é o `useState` inicial da tela) —
e o backend (`_list_pedidos_sync`) já tinha uma exceção pra isso, mas só
pra pedidos tipo **FIADO** ainda Abertos (implementada 2026-07-18,
pensada especificamente pro caso "fiado pode ficar aberto por semanas").
Mesa/Comanda/Balcão/Entrega abertos há mais de 1 dia NÃO tinham a mesma
exceção — eram filtrados pra fora da lista assim que a data de abertura
deixava de ser "hoje", mesmo com o pedido genuinamente ainda aberto. Isso
contrariava o próprio comportamento já documentado do painel (CLAUDE.md
> "Painel de Pedidos": "pedido aberto há mais de um dia... nunca é
filtrado por data, só reordenado/destacado em vermelho") e divergia do
legado (a tela "Pedidos Abertos" do VB6 não filtra por data de abertura
nenhuma, só por Data de Entrega — campo separado).

**Corrigido** em `services/pedidos_service.py::_list_pedidos_sync` —
generalizada a exceção de "`situacao = 'A'` E tipo FIADO" pra só
"`situacao = 'A'`", cobrindo qualquer tipo de pedido aberto, não só
Fiado. `tests/unit/test_pedidos_service.py::
test_data_ini_e_fim_tem_excecao_pra_qualquer_pedido_aberto` (renomeado,
antes `..._pra_fiado_aberto`) atualizado pra cobrir a cláusula nova.
- **Verificação**: `pytest tests/unit` → 1807/1808 (mesma falha
  pré-existente); backend reiniciado; teste end-to-end real via
  `POST /api/pedidos` com `data_ini=data_fim="2026-08-11"` (exatamente o
  que a tela envia por padrão) contra `DESKTOP-TDK482U`/`BD_BAIXOBRISA` →
  22 pedidos retornados (antes: só os Fiado apareciam), incluindo os 6
  Mesa/Comanda que batem exatamente com a lista do VB6.
- **Escopo**: não muda o filtro pra situações Fechado/Faturado/
  Cancelado/Todos — só pedidos com `situacao = 'A'` (Aberto) ganham a
  exceção, mantendo o filtro de data útil pra restringir histórico
  grande nas outras situações.

#### Fiado deixa de ser fallback do tipo do cliente; cores do card por coluna; bug real de drag-and-drop (mesmo dia, 2026-08-11)

Três achados na mesma sessão de teste ao vivo contra "Baixo Brisa Real",
depois que o painel passou a bater com o VB6 (achado acima):

1. **Fiado não pode ser inferido só pelo tipo do CLIENTE**: pedidos
   antigos sem "Tipo" próprio gravado (campo só existe no app web/KPDV,
   nunca existiu no VB6) caíam na coluna Fiado só porque o CLIENTE tem
   `cliente_forn = Fiado` — categorização administrativa do cliente, não
   prova que aquele pedido específico é uma venda fiado. Corrigido com
   `TIPO_EFETIVO_PEDIDO_SQL` (novo, `services/pedido_common.py`): cai pro
   tipo do cliente normalmente (Mesa/Comanda/Balcão/Entrega), EXCETO pra
   Fiado, onde o fallback é recusado — só conta como Fiado se
   `pedido_venda.tipo` foi gravado explicitamente assim (ex.: por
   arrasto manual, ver item 3). Aplicado em `pedidos_service.py`
   (`_list_pedidos_sync`, `_get_pedido_sync`) e
   `pedido_completo_service.py`. Web e KPDV herdam automaticamente (só
   leem `tipo_cliente_descricao` já resolvido pelo backend, nenhum
   recalcula por conta própria).
2. **Cor do card sempre da COLUNA, nunca sobrescrita por "parado"**:
   antes, um pedido aberto há mais de 1 dia (`isStale`/`IsStale`) virava
   vermelho sólido (border+texto), mascarando a cor real do tipo (Mesa
   azul, Comanda verde, etc.) — dava a impressão errada de que "parado =
   Fiado". Pedido explícito do usuário: "quero que o tema de cor dos
   cards da coluna Mesa tenha a cor da coluna. propague para as demais
   colunas". Removida a sobrescrita em `PainelPedidoCard.tsx` (web,
   prop `stale` removida do componente — não influencia mais nada) e
   `PedidoCardViewModel.cs` (KPDV, `BrushStale` removido) — `accentColor`/
   `AccentBrush` e `textColor`/`TextoBrush` usam só `TIPO_COLOR`/
   `CorPorTipo` agora. A REORDENAÇÃO de pedidos parados pro fim da coluna
   (`isStale`/`IsStale` usado só pra `sort`/`OrderBy`) não mudou — só a
   cor deixou de depender disso. Vai de mãos dadas com o novo fluxo
   manual: "no app da web e do KPDV, nós arrastaremos o card para fiado
   manualmente" (pedido explícito do usuário) — em vez de o sistema
   inferir Fiado automaticamente (item 1), o operador decide arrastando.
3. **Bug real achado ao vivo: drag-and-drop no WEB nunca disparava**
   (Fase 2b/2026-07-30 nunca tinha sido testada com um navegador real —
   só validada por leitura de código). Causa: `DraggablePedidoCard`
   (`PainelDragDrop.tsx`) seta `draggable="true"` no elemento WRAPPER,
   que usa `display:"contents"` (necessário pro layout do grid de
   cards). Elemento com `display:contents` não gera caixa própria no
   navegador, e a HTML5 Drag and Drop API exige uma caixa real pra
   servir de fonte do arrasto — `draggable="true"` no wrapper
   simplesmente não tinha efeito nenhum, sem erro visível. Corrigido
   movendo o atributo `draggable` + os listeners `dragstart`/`dragend`
   pro CARD real (`node.firstElementChild`, já usado só pra estilo
   antes) em vez do wrapper. `DroppableColuna` não tinha o mesmo problema
   (não usa `display:contents`, listeners continuam no próprio nó). KPDV
   não tem esse bug — usa `DragDrop.DoDragDrop` nativo do WPF, sem
   equivalente a `display:contents`.
- **Verificação**: `pytest tests/unit` → 1807/1808 (mesma falha
  pré-existente); backend reiniciado; teste end-to-end real via
  `POST /api/pedidos` contra `DESKTOP-TDK482U`/`BD_BAIXOBRISA` → Fiado
  não lista mais os 3 pedidos sem tipo próprio (achado 1); `dotnet build`
  KPDV → 0 erros, app relançado (achado 2 no KPDV); achado 2 no web e
  achado 3 dependem de teste manual no navegador/app (não coberto por
  este agente — usuário deve confirmar ao vivo).

#### Menu lateral do KPDV parou de responder a cliques após o submenu "Configurações" (mesmo dia, 2026-08-11) — CORRIGIDO

Regressão crítica reportada logo após o submenu "Configurações" ser
adicionado (ver seção "Contraste global de ComboBox/TextBox + submenu
'Configurações'" abaixo) — confirmado via `AskUserQuestion`: o app NÃO
trava (resto da janela responde normalmente), mas **nenhum** item do
menu lateral reage a clique — nem os NOVOS (Impressora/Balança/Conexão/
Atualização) nem os já existentes e intocados (Venda/Pedidos). Também
reportado junto: "menu duplicado" (não investigado a fundo — não há
duplicação real no XAML, só 1 `<ui:NavigationView>`; pode ser um efeito
colateral visual do mesmo estado quebrado, a confirmar depois do fix
abaixo).

**Causa raiz**: `Wpf.Ui.Controls.NavigationViewItem.OnClick()` (lido
diretamente do código-fonte da versão instalada, 4.3.0, via `gh api`
contra `lepoco/wpfui`) só chama `NavigationView.OnNavigationViewItemClick`
(que dispara o evento `SelectionChanged`) quando a propriedade
`TargetPageType` (um `System.Type`, usado pro sistema de navegação por
PÁGINA/cache do WPF-UI) está definida:
```csharp
if (TargetPageType is not null) navigationView.OnNavigationViewItemClick(this);
```
Este projeto **nunca** usou `TargetPageType` — só `TargetPageTag`
(string), roteado manualmente no code-behind (`NavView_SelectionChanged`)
sem o sistema de páginas do WPF-UI. Ou seja, pela leitura do código-fonte,
`SelectionChanged` nunca deveria ter disparado neste projeto, nem antes
do submenu — mas Venda/Pedidos funcionavam antes, então algum mecanismo
interno não documentado do WPF-UI estava fazendo a seleção funcionar de
outra forma, e a adição do submenu aninhado
(`NavItemConfiguracoes.MenuItems`) evidentemente perturbou esse estado
interno o bastante pra quebrar a seleção pra TODO o menu, não só os itens
novos.

**Decisão**: em vez de continuar depurando um mecanismo interno não
documentado de uma lib de terceiros, trocado por um caminho robusto e
óbvio — `NavigationViewItem` herda `System.Windows.Controls.Primitives.
ButtonBase`, cujo evento `Click` SEMPRE dispara (`base.OnClick()` é
chamado incondicionalmente no fim do `OnClick()` override, independente
de `TargetPageType`). Adicionado `Click="NavItem_Click"` em CADA item
folha do menu (Venda, Pedidos, Impressão por Finalidade, Impressora,
Balança, Conexão, Atualização — não no item pai "Configurações", que só
expande/colapsa) + handler compartilhado `NavItem_Click` em
`MainWindow.xaml.cs`, que delega pro mesmo switch de roteamento (extraído
pra `NavigateByTag(string? tag)`, reaproveitado tanto por `NavItem_Click`
quanto por `NavView_SelectionChanged` — mantido como rede de segurança
idempotente, não removido, caso o mecanismo antigo volte a funcionar em
paralelo).
- **Verificação**: `dotnet build` → 0 erros; app relançado
  (`Get-Process` → `Responding: True`). **Não testado ao vivo por este
  agente** (clique de mouse real não é simulável pelas ferramentas
  disponíveis) — usuário deve confirmar que todos os itens do menu voltam
  a funcionar, e se o "menu duplicado" reportado junto também some.
- **Confirmado funcionando** pelo usuário logo em seguida (conseguiu
  navegar até "Impressão por Finalidade" e reportar outro bug ali —
  prova de que o clique passou a funcionar).

#### `ConfiguracoesViewModel`'s combobox "Finalidade" — 3 achados na mesma investigação (mesmo dia, 2026-08-11)

1. **Erro real descoberto ao adicionar diagnóstico**: o código silenciava
   `tipos.Success == false` sem nunca mostrar mensagem de erro (diferente
   do tratamento já existente pra `mapeamentos`), deixando o combobox
   "Finalidade" vazio sem nenhuma pista. Corrigido — `TipoPecaListResponse`
   ganhou campo `Message`, e `InicializarAsync` agora chama
   `SetStatusOnUi(tipos.Message ?? "Falha ao carregar finalidades.", true)`
   quando falha. Com isso, o usuário viu o erro real pela primeira vez:
   **"O servidor retornou uma resposta em formato inesperado."**
   (`JsonException` capturada em `ApiClient.HandleAsync`) — confirma que
   é uma falha de DESSERIALIZAÇÃO intermitente, não um bug de estilo/
   ComboBox (teoria descartada no caminho — `Wpf.Ui.Controls` NÃO tem uma
   classe `ComboBox` própria, `ui:ComboBox` nem existe na v4.3.0; toda
   ComboBox do app é a vanilla do WPF, retemplada globalmente por um
   `Style` implícito do tema do WPF-UI).
2. **Causa raiz suspeita**: usuário relatou "falha às vezes, principalmente
   quando vem de um menu para outro" — bate com o próprio
   `NavView_SelectionChanged` mantido como "rede de segurança" junto do
   novo `Click` (ver achado anterior) — se os dois dispararem juntos pro
   mesmo clique, `NavigateByTag` roda 2x, criando 2 instâncias de
   `ConfiguracoesView`/`ViewModel` quase simultâneas, cada uma disparando
   sua PRÓPRIA leva de chamadas HTTP concorrentes — explicação plausível
   pra uma falha intermitente de parsing JSON sob concorrência. Removido
   por completo `SelectionChanged` (não só mantido como redundância) —
   `Click` é a ÚNICA fonte de navegação agora. **Não confirmado
   definitivamente como a causa raiz** (não há como reproduzir/instrumentar
   a condição de corrida por este agente) — se o erro intermitente
   persistir mesmo assim, investigar outra causa (ex.: timeout do backend
   sob carga, resposta truncada por outro motivo).
3. **Pedido explícito do usuário, mesma rodada**: "coloque o menu
   impressora e impressora por finalidade na mesma tela. Não precisa de
   uma tela para cada configuração" — `ConfiguracaoImpressaoViewModel`/
   `View` (tela separada "Impressora", configuração LOCAL desta estação
   pro cupom da Venda) removidos por completo e mesclados dentro de
   `ConfiguracoesViewModel`/`ConfiguracoesView` (antes só "Impressão por
   Finalidade", mapeamento GLOBAL via API) — 2 cards na mesma tela agora:
   "Impressora desta Estação" (topo) + "Impressão por Finalidade"
   (embaixo, como já era). Reaproveitada a mesma `ImpressorasDisponiveis`
   (fonte de dados idêntica nos dois casos — `_impressao.
   ListarImpressorasInstaladas()`), com uma propriedade separada
   `ImpressoraEstacaoSelecionada` (pra não colidir com
   `ImpressoraSelecionada`, já usada pelo "Novo mapeamento"). Item de menu
   "Impressora" removido; "Impressão por Finalidade" renomeado só "Impressão"
   e não depende mais de `moduloBarAtivo` (a seção de impressora da
   estação é útil em qualquer segmento, não só Bar).
- **Verificação**: `dotnet build` → 0 erros (3 rodadas: diagnóstico,
  merge das telas, remoção do SelectionChanged); app relançado. Teste ao
  vivo da causa raiz nº2 (condição de corrida) e do combobox Finalidade
  em si ficam pendentes de confirmação do usuário — não reproduzíveis
  pelas ferramentas deste agente.

#### Redesign da tela de Venda (Checkout) — layout em 2 colunas (mesmo dia, 2026-08-11)

Usuário pediu ajuda de design a um Claude Chat separado ("gera uma tela em
XAML... me surpreenda com design moderno"), colou o `VendaView.xaml`
atual como referência, e trouxe o XAML gerado de volta pra cá pra aplicar
— explicitamente pedindo pra **não perder a versão atual, caso precise
reverter**.

- **Backup criado antes de qualquer mudança**:
  `Views/_backup_venda_2026-08-11/VendaView.xaml.bak` +
  `VendaView.xaml.cs.bak` (cópia fiel da versão anterior). Pra reverter:
  copiar esses 2 arquivos de volta pra `Views/VendaView.xaml`/`.xaml.cs`
  (o `.xaml.cs` não foi alterado nesta rodada, mas o backup existe por
  precaução) e `dotnet build`.
- **Layout novo**: 2 colunas na área central — esquerda = busca de item +
  "Ações Rápidas" (cards com botões Fechar Venda/Desconto/Cancelar/
  Importar Pedido/Importar O.S./Reimprimir, cada um com o badge da tecla
  de função, substituindo a antiga legenda de atalhos em texto no
  rodapé); direita = lista de itens da venda (cards com sombra, cantos
  arredondados) + barra de total fixa embaixo. Painéis modais (Fechar
  Venda/Desconto/Cancelar/Importar) e toda a lógica de atalhos de teclado
  (F2/F4-F10/Esc/Enter/Delete) preservados 100% sem mudança — só a área
  visível por trás deles foi redesenhada.
- **XAML gerado pelo Claude Chat NÃO foi colado direto** — validado
  campo a campo contra `VendaViewModel.cs`/`VendaView.xaml.cs` reais
  antes de aplicar (o próprio XAML colado já vinha com um aviso
  explícito sobre isso). Achados reais da validação:
  1. `AbrirPainelFecharVendaCommand`/`AbrirPainelDescontoCommand`/
     `AbrirPainelCancelarVendaCommand`/`AbrirPainelImportarDavCommand`
     **não existiam** — eram métodos públicos comuns chamados direto
     pelo code-behind (atalhos de teclado), nunca `[RelayCommand]`.
     Adicionados ao `VendaViewModel.cs`: `[RelayCommand]` direto em
     `AbrirPainelDesconto()`/`AbrirPainelCancelarVenda()`/
     `AbrirPainelImportarDavAsync(string)` (parâmetros batem exatamente
     com o que o XAML novo espera); `AbrirPainelFecharVendaAsync(string
     tipoInicial = "DI")` ganhou um WRAPPER parameterless
     (`AbrirPainelFecharVenda()`) em vez de receber o atributo direto —
     um `[RelayCommand]` num método com parâmetro só-com-default geraria
     um comando de 1 argumento que, sem `CommandParameter` no botão,
     executaria com `null` em vez do default "DI". Em todos os 4 casos,
     o método público original foi mantido intacto — os atalhos de
     teclado (F4/F6/F7/F9/F10) continuam chamando-o direto, sem
     depender do novo `[RelayCommand]`.
  2. Todo o resto (bindings de `ItemVendaLinha`, `LinhaPagamento`,
     `ui:AutoSuggestBox`/`OriginalItemsSource`, os 16
     brushes/conversores `StaticResource`) já existia e batia
     exatamente — nenhuma outra mudança necessária. `ui:AutoSuggestBox`
     em particular já era usado assim na tela original, confirmado por
     comparação direta com o backup antes de aceitar como válido (mesmo
     princípio de cautela que descobriu, na mesma sessão, que
     `ui:ComboBox` NÃO existe no WPF-UI 4.3.0 — nunca assumir que um
     nome de controle/propriedade gerado por IA está certo sem checar
     contra o código real ou a fonte da lib).
- **Verificação**: `dotnet build` → 0 erros; app relançado. **Não
  testado visualmente por este agente** (não há como renderizar/
  screenshotar uma janela WPF pelas ferramentas disponíveis) — usuário
  deve conferir o resultado visual e testar o fluxo completo (buscar
  item, fechar venda, desconto, cancelar, importar, reimprimir) antes de
  considerar concluído.

#### 2ª rodada do redesign — revertido e refeito espelhando o Checkout web de verdade (mesmo dia, 2026-08-11)

Usuário pediu reverter a 1ª tentativa ("preciso da tela o mais parecido
com a tela de venda do app web. as duas versões atuais está muito longe
do que preciso"). Revertido via backup
(`Views/_backup_venda_2026-08-11/*.bak`).

- **Fonte de referência real**: `frontend/app/checkout.tsx` +
  `DemonstrativoCupomFiscal.tsx` foram DELETADOS do working tree em
  2026-08-10 (substituídos pelo KPDV, ver [[project_checkout]]), mas
  ainda existem no último commit (`3fa72b3`) — recuperados via
  `git show HEAD:caminho` pra servir de referência visual real, não uma
  lembrança aproximada.
- **Achado real ao comparar**: o Checkout web tem busca/vínculo de
  Cliente na venda — o KPDV não tem essa funcionalidade implementada
  (nem endpoint chamado nem lógica no `CheckoutService`/
  `VendaViewModel`). Perguntado ao usuário via `AskUserQuestion` — decisão:
  **só o layout agora**, seção Cliente fixa em "Clientes Diversos" (sem
  busca), funcionalidade de vincular cliente fica pra rodada futura.
- **Correção do usuário no meio da implementação**: a 1ª versão desta
  2ª rodada replicava a estrutura LITERAL do `checkout.tsx` antigo (card
  Atendente/Cliente cheio, 2 colunas Busca+Demonstrativo, DEPOIS uma
  faixa cheia de caixas de total, DEPOIS uma faixa cheia de botões de
  ação) — usuário corrigiu: "o layout do web possui duas colunas na tela
  central: os campos + funções e a outra à direita com a lista de
  itens." Refeito: os botões de ação (Importar Pedido/O.S., Desconto
  Geral, Fechar Venda, Reimprimir, Cancelar Venda) SAÍRAM da faixa cheia
  embaixo e entraram dentro da COLUNA ESQUERDA, empilhados abaixo do
  campo de busca — a coluna direita fica só com o Demonstrativo (lista
  de itens + total), como pedido.
- **Dados novos expostos** (o DTO da API já trazia, só não estava
  mapeado pra exibição): `ItemVendaLinha` ganhou `PrecoBruto`/
  `DescontoUnit`/`AcrescimoUnit`/`OrigemDav`; `VendaViewModel` ganhou
  `AtendenteNome` (nome_guerra, regra `[GLOBAL]` de sempre), `UltimoItem`
  (destaque grande no Demonstrativo, réplica de `ultimoItem` do web),
  `TotalBruto`/`TotalDescontosItens`/`TotalAcrescimosItens` (as 4 caixas
  de total, réplica de `totalBruto`/`totalDescontos`/`totalAcrescimos`
  do web) — todos recalculados/notificados dentro de
  `RecarregarVendaAsync`. Novo comando `CancelarItemAsync(ItemVendaLinha?
  item)` — cancelar item pelo ÍCONE na própria linha da grade (réplica do
  "✕" por linha do `DemonstrativoCupomFiscal.tsx`), complementar ao
  atalho de teclado Delete-sobre-linha-selecionada já existente (não
  substituído).
- **3 conversores novos** (não existiam): `NullToVisibleConverter`/
  `NullToCollapsedConverter` (destaque do último item vs. estado vazio)
  e `ZeroToCollapsedConverter` (só mostra "desc. RX/un." quando o item
  genuinamente tem desconto unitário) — adicionados em
  `Converters/CommonConverters.cs` + registrados em `App.xaml`, mesmo
  padrão dos conversores já existentes.
- **Bug de sintaxe achado e corrigido no caminho**: comentários XML com
  `----` (múltiplos hífens seguidos, usados como separador visual em 3
  lugares) quebram a compilação (`XML comment cannot contain '--'`) —
  regra do XML, não do WPF-UI. Trocados por texto sem hífens duplos.
- **Verificação**: `dotnet build` → 0 erros (2 rodadas: erro de sintaxe
  XML corrigido, depois build limpo); app relançado. Mesma ressalva de
  sempre — **não testado visualmente por este agente**.

#### 3ª rodada — usuário testou ao vivo e pediu mais 8 ajustes de uma vez (mesmo dia, 2026-08-11)

Lista completa do que foi pedido e implementado nesta rodada:

1. **Lista de itens fixa com scrollbar** — `ListaItens` trocou `MaxHeight`
   por `Height="280"` (não encolhe com 0 itens) +
   `ScrollViewer.VerticalScrollBarVisibility="Visible"` (sempre visível,
   não "Auto").
2. **Atendente removido do corpo** — já mostrava em `TxtOperador` na
   barra de título (`MainWindow.xaml`); o card "Atendente" do corpo era
   redundante, removido.
3. **"Venda + comanda" centralizado na barra de título** — novo
   `TxtTituloBarra` (renomeado do TextBlock estático "Kontacto PDV" que
   já existia no `TitleBar.Header`) atualizado via código
   (`MainWindow.xaml.cs::AtualizarTituloVenda()`, chamado ao mostrar a
   tela de Venda E assinado a `VendaViewModel.PropertyChanged` uma única
   vez pra acompanhar `Comanda` ao vivo — ex.: depois de Fechar Venda, a
   próxima venda abre sozinha com número novo). Outras telas (Pedidos/
   Configurações/Conexão) resetam pra "Kontacto PDV". **Ressalva
   honesta**: `TitleBar.Header` do WPF-UI fica logo após o ícone, não
   necessariamente centralizado matematicamente na largura total da
   janela — usei `HorizontalAlignment="Center"` mas não há como
   confirmar visualmente sem o usuário testar.
4. **Campo Cliente virou busca de verdade** (não mais só layout) —
   usuário reverteu a decisão anterior ("só layout agora"). Implementado:
   `CheckoutService.BuscarClientesAsync`/`DefinirClienteAsync` (novo,
   `PUT /checkout/{comanda}/cliente`, mesmo endpoint do web) +
   `VendaViewModel.BuscarClienteAsync`/`DefinirClienteCommand` (mesmo
   padrão de busca inline via `ui:AutoSuggestBox` já usado pro Produto,
   sem modal) + handlers novos em `VendaView.xaml.cs`
   (`BuscaCliente_TextChanged`/`SuggestionChosen`/`PreviewKeyDown`).
   Enter com busca resolvendo pra exatamente 1 cliente vincula direto
   (regra [GLOBAL] "Padrão de Campo Cliente" do CLAUDE.md).
5. **Campo Qtd ao lado do Produto/Serviço** — `VendaViewModel.QtdTexto`
   (novo, default "1", resetado após cada inclusão), lido dentro de
   `AdicionarAsync` (só quando o produto NÃO é vendido por peso — peso da
   balança/etiqueta sempre prevalece, comportamento já existente
   preservado).
6. **Busca sem modal, com Enter, tanto Produto quanto Cliente** — Produto
   já funcionava assim; Cliente ganhou o mesmo padrão (achado 4 acima).
7. **Botões de Ações em grade estilo VB6** — antes empilhados numa coluna
   só (6 linhas); agora `UniformGrid Columns="2"` (3 linhas pros 6
   botões), cada botão com tecla de função grande em cima + rótulo
   embaixo, centralizado (`VbAcaoButtonStyle` novo) — réplica do estilo
   da legenda de atalhos do VB6 que o usuário anexou como referência.
8. **Mensagens de status: 3s, centralizadas** — antes um banner fixo no
   canto superior direito, sem auto-esconder. Agora: `VendaViewModel.
   SetStatus` inicia um timer (`ClearStatusAfterDelayAsync`, cancela o
   anterior a cada mensagem nova) que limpa `StatusMessage` sozinho
   depois de 3000ms; `VendaView.xaml` trocou o banner de canto por um
   `Border` centralizado na tela inteira (fora da área de rolagem),
   verde quando `StatusIsError=False`, vermelho quando `True`.

**Bug real achado e corrigido no caminho** (não pedido pelo usuário,
achado comparando o screenshot dele com o código): o box de "destaque do
último item" aparecia como um "x" solto mesmo com a venda vazia — os 3
usos de `NullToVisibleConverter`/`NullToCollapsedConverter` (destaque,
vazio, botão cancelar por linha) estavam com os dois conversores
TROCADOS entre si (nome dos conversores é sobre o que a lógica FAZ, não
sobre quando aparecem — confusão na hora de aplicar). `UltimoItem=null`
fazia o box de destaque aparecer (errado) em vez do box "vazio"; como
`UltimoItem` é null, só o texto ESTÁTICO " x " (separador entre Qtd e
PUnit) renderizava, o resto ficava em branco — daí o "x" solto no
screenshot. Corrigido invertendo os 3 usos pro converter certo.
- **Verificação**: `dotnet build` → 0 erros (2 rodadas: build inicial
  limpo, depois fix do bug do "x" + rebuild limpo); app relançado. Mesma
  ressalva de sempre — **não testado visualmente por este agente**,
  inclusive a centralização exata do título na barra (item 3 acima) fica
  sujeita a confirmação visual do usuário.

#### 4ª rodada — usuário confirmou o layout ao vivo (screenshot real, "Venda #17851" batendo certinho) e pediu mais 2 ajustes (mesmo dia, 2026-08-11)

1. **Enter com busca PARCIAL (descrição ou código) traz a lista, não
   tenta incluir direto** — antes, digitar "picanha" (não é um código
   válido) e Enter caía direto em "Produto não encontrado" porque
   `AdicionarAsync` sempre tentava resolver o texto como CÓDIGO EXATO
   primeiro. Corrigido nos dois campos (mesma regra pros dois, pedido
   explícito do usuário — "mesma regra para o cliente"):
   - Novo `VendaViewModel.ProdutoExisteAsync(codigo)` — só CHECA se
     resolve como código exato, sem incluir nada.
   - `BuscaProduto_PreviewKeyDown` (code-behind) reescrito: tenta
     `ProdutoExisteAsync` primeiro (caminho rápido, bipe de leitor de
     código de barras) → se falhar, dispara `BuscarAsync(texto,
     imediato:true)` (novo parâmetro `imediato`, pula o debounce de
     350ms) → 1 resultado inclui direto, 0 ou 2+ deixam o dropdown do
     `AutoSuggestBox` aberto pro usuário escolher.
   - O campo Cliente já tinha essa exata lógica desde a 3ª rodada — não
     precisou de mudança, só confirma que "mesma regra" já estava valendo.
2. **Botões de Ações menores e arredondados** — `VbAcaoButtonStyle`:
   `Height` 64→48, `Margin` 4→3, `CornerRadius="16"` novo (propriedade
   própria do `ui:Button`, maior que o `ControlCornerRadius` global de
   6px do app), fonte da tecla de função 16→13, fonte do rótulo 11→10.
- **Verificação**: `dotnet build` → 0 erros; app relançado. Mesma
  ressalva de sempre — **não testado visualmente por este agente**.

#### 5ª rodada — busca ainda não funcionava de fato (root cause achada na fonte do WPF-UI) + 3 ajustes de layout (mesmo dia, 2026-08-11)

Usuário reportou que a busca continuava não funcionando nos dois campos
mesmo depois da 4ª rodada, e pediu 3 ajustes de layout: agrupar
Cliente+Produto num card só, aumentar a lista de itens, diminuir a
largura dos botões de ação (repetindo o pedido da 4ª rodada — o resultado
anterior não pareceu suficientemente estreito).

1. **Causa raiz real da busca nunca ter funcionado**: lida direto da fonte
   do `AutoSuggestBox` do WPF-UI 4.3.0 (`gh api
   repos/lepoco/wpfui/contents/...?ref=4.3.0`). O controle filtra
   `OriginalItemsSource` sozinho, a cada `TextChanged`, via
   `DefaultFiltering(text)` → `GetStringFromObj(item)` — que usa
   `DisplayMemberPath` se ele estiver setado, senão cai pra
   `item.ToString()`. Nem `BuscaProduto` nem `BuscaCliente` tinham
   `DisplayMemberPath`, e os DTOs (`ProdutoBuscaDto`/`ClienteBuscaDto`)
   não sobrescrevem `ToString()` — o filtro interno SEMPRE devolvia vazio,
   não importa o que a busca assíncrona já tivesse colocado na coleção.
   Agravante: `OriginalItemsSourceProperty` não tem
   `PropertyChangedCallback` nenhum — mesmo com `DisplayMemberPath`
   correto, uma busca assíncrona/debounced que termina DEPOIS do
   `TextChanged` não reabre/atualiza o dropdown sozinha.
   - **Fix (2 camadas)**: (a) `DisplayMemberPath="Nome"` em `BuscaCliente`
     e `DisplayMemberPath="Descricao"` em `BuscaProduto` — corrige o
     filtro interno do controle; (b) mais importante, `VendaView.xaml.cs`
     — todo handler que dispara uma busca (`BuscaProduto_TextChanged`,
     `BuscaProduto_PreviewKeyDown`, `BuscaCliente_TextChanged`,
     `BuscaCliente_PreviewKeyDown`) agora, depois do `await` da busca,
     empurra o resultado explicitamente via
     `sender.SetCurrentValue(AutoSuggestBox.ItemsSourceProperty, resultados)`
     + `sender.SetCurrentValue(AutoSuggestBox.IsSuggestionListOpenProperty,
     resultados.Count > 0)` — contorna o mecanismo interno quebrado/
     defasado em vez de depender dele.
2. **Cliente + Produto/Serviço agrupados num único card** — antes eram 2
   `ui:Card` separados (um "CLIENTE" acima da grade de 2 colunas, outro
   "BIPAR OU DIGITAR PRODUTO/SERVIÇO" já dentro da coluna esquerda);
   viraram um só card na coluna esquerda, com um separador (`Border`
   1px) entre a seção Cliente e a seção Produto/Qtd.
3. **Lista de itens aumentada** — `Height` do `ListView` 280→460.
4. **Botões de Ação com largura fixa e mais arredondados** —
   `VbAcaoButtonStyle` ganhou `Width="112"` (antes esticava pra caber na
   célula da `UniformGrid`) e `CornerRadius` 16→22; o contêiner trocou de
   `UniformGrid Columns="2"` (força esticar) pra `WrapPanel` (respeita a
   largura fixa do botão e quebra linha sozinho).
- **Verificação**: `dotnet build src/KPDV/KPDV.csproj` → 0 erros (precisou
  encerrar o processo KPDV rodando antes — arquivo `.dll` travado); app
  relançado (PID 17240, título "Kontacto PDV", `Responding=True`). Mesma
  ressalva de sempre — **não testado visualmente/ao vivo por este agente**
  (nem teclado real nem mouse). O usuário mencionou "em anexo imagem de
  como quero a tela" numa mensagem, mas nenhuma imagem chegou de fato
  neste agente — se a busca ou o layout ainda não baterem com o que o
  usuário tinha em mente, pode ser necessário reenviar essa imagem.

#### 6ª rodada — crash real ao logar (`XamlParseException`), causado pelo fix da 5ª rodada (mesmo dia, 2026-08-11)

Usuário testou ao vivo (Visual Studio, F5) e o app quebrou com
`System.Windows.Markup.XamlParseException`: "A propriedade definida
'System.Windows.Controls.ItemsControl.ItemTemplate' iniciou uma exceção"
— confirma que a 5ª rodada nunca tinha sido de fato exercitada contra a
tela renderizando (só build+`Get-Process` liveness, que não chega a
montar `VendaView`).

- **Causa raiz**: `ItemsControl` (classe-base de `ui:AutoSuggestBox`) do
  WPF **não permite setar `DisplayMemberPath` e `ItemTemplate` ao mesmo
  tempo** no mesmo controle — lança `InvalidOperationException` em
  runtime assim que o controle tenta aplicar o template, que o parser XAML
  embrulha em `XamlParseException`. A 5ª rodada tinha acabado de adicionar
  `DisplayMemberPath="Nome"`/`"Descricao"` exatamente nos 2
  `AutoSuggestBox` que JÁ tinham `ItemTemplate` custom (grid com
  Código/Nome/Tipo) — conflito direto, nunca compilado+executado antes de
  reportar como pronto.
- **Fix**: removido `DisplayMemberPath` dos 2 `AutoSuggestBox`
  (`VendaView.xaml`) — o `ItemTemplate` visual fica intacto. Em vez disso,
  `ProdutoServicoDto`/`ClienteBuscaDto` (`Models/ProdutoModels.cs`/
  `Models/PedidosModels.cs`) ganharam `override string ToString()`
  (retornando `Descricao`/`Nome`) — é isso que o filtro interno do
  `AutoSuggestBox` (`DefaultFiltering`→`GetStringFromObj`) usa quando
  `DisplayMemberPath` não está setado, sem conflitar com `ItemTemplate`.
  O resto do fix da 5ª rodada (push explícito de `ItemsSource`/
  `IsSuggestionListOpen` via `SetCurrentValue` no code-behind) continua
  válido e inalterado.
- **Regra pra qualquer `AutoSuggestBox` futuro neste projeto**: se o
  controle tem `ItemTemplate` custom, NUNCA setar `DisplayMemberPath`
  junto — usar `override ToString()` no DTO em vez disso.
- **Verificação**: `dotnet build` → 0 erros; processo encerrado e
  relançado (PID 23224, "Kontacto PDV", `Responding=True`) — mas isso
  ainda não prova que a tela abre sem crash (o crash anterior só
  acontecia ao NAVEGAR pra Venda/logar, não no boot do processo). Login
  real + navegação até a tela de Venda continuam sem confirmação deste
  agente — só o usuário pode validar isso de fato.

#### 7ª rodada — usuário testou de verdade (login + digitação real) e achou 2 problemas novos: lista de sugestões "vazando" por trás da tela + crash real ao digitar (mesmo dia, 2026-08-11)

Confirma que a 6ª rodada resolveu o crash de NAVEGAR pra Venda, mas
digitar no campo Cliente ("carlos") e no campo Produto ("picanha")
revelou 2 problemas novos, um visual e um crash real (`InvalidOperationException`
capturado ao vivo pelo Visual Studio, call stack até `Main`).

1. **Lista de sugestões "vazando" — texto da tela por trás aparecendo
   através do popup**: causa raiz é a MESMA já documentada em
   `Resources/Brand.xaml` pro `ComboBox` (`ComboBoxDropDownBackground`) —
   `FlyoutBackground` (usado pelo `Border` do popup de sugestões do
   `AutoSuggestBox`) resolve pra `AcrylicBackgroundFillColorDefault`, uma
   cor TRANSLÚCIDA pensada pra um desfoque Mica real que o WPF-UI não
   aplica em `Popup`s (issue #93 do próprio repositório, já citada no
   comentário do ComboBox). Sem desfoque, a translucidez vira "vidro" e
   deixa o conteúdo por trás (Ações, hint text, etc.) transparecendo.
   **Fix**: `Brand.xaml` ganhou `FlyoutBackground`/`FlyoutBorderBrush`
   sólidos (mesma técnica já usada pro ComboBox/TextBox nesta sessão) —
   corrige TODO popup/flyout do app de uma vez (não só os 2 campos desta
   tela), incluindo qualquer um futuro.
2. **Crash real ao digitar**: `System.InvalidOperationException: 'A
   propriedade 'Background' não aponta para um DependencyObject no
   caminho '(0).(1)'.'`, não tratado, derrubando o processo inteiro
   (stack desenrolado até `Main`). Causa raiz lida direto na fonte do
   WPF-UI 4.3.0 (`Controls/AutoSuggestBox/AutoSuggestBox.xaml`,
   `DefaultAutoSuggestBoxItemContainerStyle`): a lib anima
   `(Border.Background).(SolidColorBrush.Opacity)` via `Storyboard` no
   `MouseEnter`/`MouseLeave` de cada item de sugestão. O `ItemsPanel` do
   popup é uma `VirtualizingStackPanel` com `VirtualizationMode="Recycling"`,
   e `BuscarAsync`/`BuscarClienteAsync` fazem `Clear()`+`Add()` na
   coleção a CADA tecla digitada — se o mouse estiver sobre um item
   quando a coleção é trocada, o container é RECICLADO no meio da
   animação (Background fica `null` momentaneamente), e o `Storyboard`
   tenta resolver `(Border.Background)` como `SolidColorBrush` — acha
   `null`, e o WPF derruba o app (esse `Storyboard` é código da PRÓPRIA
   lib WPF-UI, nunca foi escrito por este projeto).
   - **Fix**: novo `SuggestionItemStyle` em `VendaView.xaml` — cópia do
     `DefaultAutoSuggestBoxItemContainerStyle` original, mas com o
     `MultiTrigger`+`Storyboard` de fade TROCADO por `Trigger`+`Setter`
     estático (`IsMouseOver`/`IsSelected` → muda `Background`
     instantaneamente, sem `Storyboard`, sem precisar resolver
     `PropertyPath` nenhum) — elimina a corrida por completo. Aplicado via
     `ItemContainerStyle="{StaticResource SuggestionItemStyle}"` nos 2
     `AutoSuggestBox` (Cliente e Produto).
   - `Brand.xaml` também ganhou `ListViewItemBackgroundPointerOver` sólido
     (cor de hover usada pelo novo Style), por consistência com o resto
     da paleta.
3. **Bug lateral achado na mesma revisão** (não reportado pelo usuário,
   mas visível nos prints — botões F4/F6/F9 renderizando lisos/cinzas,
   sem o visual pill/gradiente do WPF-UI): `VbAcaoButtonStyle` não tinha
   `BasedOn` — `Style="{StaticResource VbAcaoButtonStyle}"` substitui por
   completo o style implícito do WPF-UI (`DefaultUiButtonStyle`,
   registrado sem `x:Key` em `Button.xaml`), perdendo o Template/triggers
   que dão cor a `Appearance="Primary/Secondary/Danger"`. Corrigido com
   `BasedOn="{StaticResource {x:Type ui:Button}}"`.
- **Regra geral pra qualquer Style customizado de `ui:*` neste projeto**:
  sempre usar `BasedOn="{StaticResource {x:Type ui:TipoDoControle}}"` ao
  criar um `Style x:Key="..."` pra um controle WPF-UI — senão o visual
  padrão da lib (cores por `Appearance`, hover, etc.) é perdido por
  completo, não só "não personalizado".
- **Verificação**: `dotnet build` → 0 erros (precisou matar o processo
  KPDV rodando via PID, `Get-Process -Name KPDV` não encontra porque o
  processo real é `dotnet.exe` hospedando o `.dll`, não `KPDV.exe`);
  relançado (PID 32868, "Kontacto PDV", `Responding=True`). Mesma
  ressalva de sempre — **não testado ao vivo por este agente** (nem
  teclado real nem mouse) — só o usuário pode confirmar se o crash
  realmente parou de acontecer e se o popup ficou sólido.

#### 8ª rodada — usuário testou login+digitação de verdade: popup "vazio" sobrando, item duplicado + deadlock, crash de thread no Enter da forma de pagamento, totais somem, botões sem relevo (mesmo dia, 2026-08-11)

A 7ª rodada resolveu o crash de MOUSE OVER e a transparência do popup — mas
o teste real revelou mais 3 bugs novos (2 reais/graves) e 2 pedidos de
ajuste visual.

1. **Campo vazio sobrando abaixo de Cliente/Produto depois de
   selecionar**: causa raiz lida na própria fonte do `AutoSuggestBox.cs`
   (não suposição) — no clique do mouse, `SelectedItem` já é setado no
   MouseDown, então quando `PreviewMouseLeftButtonUp` roda e vê
   `SelectedItem != null`, ele **retorna sem fechar o popup**; quem
   fecha é `SelectionChanged` → `OnSelectedChanged`, que só chama
   `OnSuggestionChosen` (dispara o evento, atualiza o texto) e **nunca
   fecha o popup**. Resultado: o popup fica ABERTO com o `ItemsSource`
   antigo (a mesma coleção que o code-behind empurrou manualmente) — a
   faixa vazia era esse popup ainda aberto. **Fix**:
   `BuscaProduto_SuggestionChosen`/`BuscaCliente_SuggestionChosen`
   (`VendaView.xaml.cs`) agora fecham explicitamente
   (`IsSuggestionListOpen=false`) e limpam `ItemsSource=null` **antes**
   de processar a seleção (não depois), eliminando o estado antigo por
   completo.
2. **Item duplicado na lista + erro de deadlock do SQL Server ao
   adicionar produto**: mesma causa raiz do item 1 — como o popup ficava
   aberto com a seleção antiga ainda "viva" (`_selectedItem` interno da
   lib), qualquer interação seguinte na lista podia redisparar
   `SuggestionChosen` pro MESMO produto, mandando uma 2ª chamada de
   `POST /pedidos/.../itens` quase simultânea à 1ª — 2 transações
   concorrentes na mesma comanda é exatamente o padrão de um deadlock
   real do SQL Server (`Transaction ... was deadlocked on lock
   resources`), e explica as 2 linhas do mesmo item na grade. **Mesmo
   fix do item 1** resolve os dois de uma vez (fechar+limpar antes de
   processar elimina a chance de redisparo).
3. **Crash real (`NotSupportedException`) ao dar Enter na forma de
   pagamento**: "'Este tipo de CollectionView não oferece suporte às
   alterações feitas a SourceCollection a partir de um thread diferente
   do thread Dispatcher.'" — causa raiz bem mais profunda, achada lendo
   o próprio `VendaViewModel.cs`: **praticamente todo `await` do arquivo
   usava `.ConfigureAwait(false)`** (35 ocorrências). Isso faz a
   continuação depois do `await` retomar numa thread do POOL, não na
   thread da UI — e como `ConfirmarFecharVendaAsync` (Fechar Venda/
   confirmar pagamento) termina chamando `InicializarAsync(manterStatus:
   true)` (abre a próxima venda), e `InicializarAsync` faz `Itens.Clear()`
   **antes do seu próprio primeiro `await`**, essa linha acabava rodando
   na thread do pool (herdada de um `ConfigureAwait(false)` anterior na
   cadeia) — WPF derruba o app na hora, porque `Itens` é a
   `ObservableCollection` vinculada ao `ListView` da tela.
   - **Achado mais grave**: esse MESMO padrão (`ConfigureAwait(false)`
     em todo `await` de ViewModel) está espalhado em **7 dos 13
     ViewModels do projeto** (`AtualizacaoViewModel`,
     `ConexaoConfigViewModel`, `ConfiguracaoBalancaViewModel`,
     `ConfiguracoesViewModel`, `LoginViewModel`, `PedidosViewModel`,
     `VendaViewModel` — 101 ocorrências no total). Um comentário já
     existente em `LoginViewModel.cs` (achado ao revisar) confirma que
     esse MESMO bug já tinha acontecido antes ali e foi "resolvido" só
     com `App.Current.Dispatcher.Invoke(...)` no `finally` — um
     band-aid pontual, não a causa raiz.
   - **Fix real, não band-aid**: removido `.ConfigureAwait(false)` dos 7
     arquivos (101 ocorrências) — em WPF, um método `async` chamado a
     partir de um `[RelayCommand]`/evento de UI já captura o
     `DispatcherSynchronizationContext` da thread da UI ao iniciar;
     **não** usar `ConfigureAwait(false)` (o padrão, sem chamar o
     método) garante que toda continuação depois de um `await` volta
     pra essa mesma thread — é o padrão correto e idiomático pra WPF
     (`ConfigureAwait(false)` é pensado pra código de biblioteca/
     servidor que não tem SynchronizationContext, não pra ViewModel que
     mexe em coleção/propriedade vinculada à UI). Os `App.Current.
     Dispatcher.Invoke(...)` já espalhados pelo código (inclusive os
     que já existiam antes desta correção) continuam funcionando
     normalmente — viram só redundantes/inofensivos onde já estavam
     certos, não foram removidos (fora de escopo, sem necessidade).
4. **Totais somem da tela** ("colocar os totais na mesma caixa dos
   botões de ações... a tela não pode esconder nenhum campo ou botão"):
   os 4 boxes de total (Bruto/Descontos/Acréscimos/A Pagar) ficavam numa
   faixa própria, largura cheia, ABAIXO das 2 colunas inteiras — em
   janela mais baixa, essa faixa ficava fora da área visível. Movidos
   pra DENTRO do mesmo card "AÇÕES" (coluna esquerda, sempre perto do
   topo), em grade 2x2 (não mais 1x4, a coluna é mais estreita que a
   tela toda).
5. **Botões de ação em 3D**: `VbAcaoButtonStyle` ganhou `DropShadowEffect`
   (sombra mais forte que a dos cards — "flutuando" sobre o card) +
   `Trigger IsPressed` que reduz a sombra e desloca o botão 1.5px pra
   baixo (`TranslateTransform`), simulando o botão "afundando" no clique
   — WPF não tem relevo nativo, essa é a aproximação padrão pra efeito
   3D em botões flat.
- **Verificação**: `dotnet build` → 0 erros; app relançado (PID 34168,
  "Kontacto PDV", `Responding=True`). Mesma ressalva de sempre — **não
  testado ao vivo por este agente**; o crash de thread em particular só
  foi confirmado por análise de código (leitura de fonte + grep), não
  reproduzido/re-testado por este agente antes do fix.
- **Pendência pra próxima sessão**: os OUTROS 6 ViewModels com o mesmo
  padrão (`AtualizacaoViewModel`/`ConexaoConfigViewModel`/
  `ConfiguracaoBalancaViewModel`/`ConfiguracoesViewModel`/
  `LoginViewModel`/`PedidosViewModel`) já tiveram o `.ConfigureAwait(false)`
  removido nesta rodada (fix aplicado, não é só o Venda) — mas as telas
  Pedidos/Configurações/Atualização/Conexão/Balança **não foram
  re-testadas ao vivo** depois da mudança; se alguma dessas telas nunca
  teve o bug se manifestar antes, é porque o caminho de código
  específico nunca tocou UI depois do `await` — a remoção é segura de
  qualquer forma (nunca piora, só remove um risco latente).

#### 9ª rodada — botões "invisíveis" (mesma causa raiz do ComboBox/Flyout), menu Configurações recolhido não fazia nada, e informação da venda anterior sobrando na tela (mesmo dia, 2026-08-11)

1. **Botões Primary/Secondary "invisíveis" (só texto, sem fundo/pill
   visível) — só o Danger (F7, vermelho) aparecia certo**: MESMA causa
   raiz já corrigida 2x nesta sessão pro ComboBox/Flyout — confirmado
   lendo `Resources/Theme/Light.xaml`: `ButtonBackground` (Secondary)
   resolve pra `ControlFillColorDefault` = `#B3FFFFFF` (branco 70%
   translúcido, pensado pra Mica real) — sobre um `ui:Card` sólido isso
   vira quase invisível; `Danger` já usa uma cor SÓLIDA da paleta
   estática (`PaletteRedColor`), por isso era o único visível. Fix:
   `Brand.xaml` ganhou `ButtonBackground`/`ButtonForeground` (Secondary,
   tons de superfície/borda da marca) e `AccentButtonBackground`/
   `AccentButtonForeground` (Primary, azul da marca) sólidos — corrige
   TODO botão do app de uma vez, não só os 5 da tela de Venda.
2. **Ícone "Configurações" recolhido não fazia nada**: lido na fonte do
   `NavigationViewItem.OnClick()` — o expand/collapse do submenu só roda
   `if (HasMenuItems && navigationView.IsPaneOpen)`; com o menu lateral
   recolhido (só ícones, `IsPaneOpen=false`), essa condição nunca bate, e
   como o item pai também não tem `TargetPageType`, o clique não tinha
   NENHUM efeito. Fix: novo `NavItemConfiguracoes_Click`
   (`MainWindow.xaml.cs`) — só age quando o painel está FECHADO: abre o
   painel (`IsPaneOpen=true`) + expande o item (`IsExpanded=true`); com o
   painel já aberto, não faz nada extra (deixa o comportamento nativo da
   lib cuidar, evita alternar `IsExpanded` duas vezes pro mesmo clique).
3. **Informação da venda anterior (cliente + produto digitado + totais)
   sobrando na tela depois de Faturar**: 2 causas reais, ambas
   corrigidas:
   - `TotalBruto`/`TotalDescontosItens`/`TotalAcrescimosItens`
     (`VendaViewModel.cs`) são getters computados a partir de `Itens`,
     **sem** `[ObservableProperty]` — só notificam quando alguém chama
     `OnPropertyChanged` explicitamente (já acontecia em
     `RecarregarVendaAsync`, mas faltava em `InicializarAsync`). Sem
     isso, a tela seguia mostrando os totais da venda ANTERIOR mesmo com
     `Itens.Clear()` já tendo rodado. Adicionados os 3
     `OnPropertyChanged` que faltavam em `InicializarAsync`.
   - `BuscaProduto.Text`/`BuscaCliente.Text` (o texto literal digitado/
     bipado no `AutoSuggestBox`) são estado puramente LOCAL do controle
     — não têm `Text="{Binding ...}"`, só eram limpos manualmente nos
     handlers de seleção/Enter, NUNCA ao iniciar uma venda nova.
     `InicializarAsync` já resetava `ClienteNome`/`QtdTexto` (propriedades
     do ViewModel), mas nada limpava o texto ainda visível na caixa.
     Fix: `VendaView.xaml.cs` (construtor) assina `PropertyChanged` do
     ViewModel — sempre que `Comanda` muda (nova venda iniciada), limpa
     `BuscaProduto.Text`/`BuscaCliente.Text` via `SetCurrentValue`
     (mesmo padrão de assinatura única já usado em `MainWindow.xaml.cs`
     pro título "Venda #N").
   - **"Vender pra Clientes Diversos se ninguém for selecionado" já
     funciona, sem precisar de mudança**: confirmado lendo
     `backend/services/checkout_service.py::_abrir_venda_sync` — TODA
     comanda já nasce com `cliente = req.cliente or _cliente_diversos(cur)`
     no INSERT, antes mesmo do usuário poder escolher alguém. O que
     parecia "cliente errado" era só o sintoma acima (nome antigo
     sobrando na tela), não uma venda de fato vinculada ao cliente
     errado no banco.
- **Verificação**: `dotnet build` → 0 erros (precisou encerrar um
  `KPDV.exe` rodando via sessão de debug do Visual Studio pra liberar o
  arquivo); app relançado (PID 30744, "Kontacto PDV", `Responding=True`).
  Mesma ressalva de sempre — **não testado ao vivo por este agente**.

#### 10ª rodada — largura da lista, `Total` não resetava, foco no produto, totais separados dos botões, TROCO da última venda (mesmo dia, 2026-08-11)

1. **Lista de itens mais larga**: coluna direita (Demonstrativo) da grade
   de 2 colunas — proporção `1.2*`→`1.8*`, `MinWidth` 380→420.
2. **`Total` não zerava ao voltar do faturamento**: a 9ª rodada já tinha
   corrigido `TotalBruto`/`TotalDescontosItens`/`TotalAcrescimosItens`
   (getters computados, faltava `OnPropertyChanged`), mas `Total` em si é
   um `[ObservableProperty]` SETADO de fora (por
   `RecarregarVendaAsync`/`ConfirmarFecharVendaAsync`) — `InicializarAsync`
   nunca fazia `Total = 0`, então a barra "TOTAL A PAGAR" (tanto a caixa
   pequena quanto a grande, embaixo da lista) seguia mostrando o valor da
   venda ANTERIOR. Adicionado `Total = 0;` em `InicializarAsync`.
3. **Foco no campo Produto após selecionar Cliente** (pedido repetido —
   não tinha sido implementado numa rodada anterior por causa da
   sequência de bugs mais urgentes que vieram no meio): `BuscaCliente.
   Focus()`/`Keyboard.Focus(BuscaProduto)` adicionados em
   `BuscaCliente_SuggestionChosen` (clique numa sugestão) e em
   `BuscaCliente_PreviewKeyDown` (Enter com 1 resultado único).
4. **Totais separados dos botões de Ação**: voltaram a ser um `ui:Card`
   PRÓPRIO (título "TOTAIS"), não mais dentro do mesmo card "AÇÕES" — fica
   logo abaixo dele, mesma coluna esquerda.
5. **"Total a Pagar" vira "Troco" quando a venda está vazia**: a barra
   grande embaixo da lista de itens (Demonstrativo) alterna entre 2
   estados mutuamente exclusivos via `Itens.Count`: com itens lançados,
   mostra "TOTAL A PAGAR"/`Total` (info essencial durante a venda, mesmo
   de sempre); com a venda vazia (tela recém-aberta/entre vendas), mostra
   "TROCO (última venda)"/`UltimoTroco` — novo `[ObservableProperty]`,
   setado em `ConfirmarFecharVendaAsync` a partir de `resp.Troco` (o
   backend já devolvia esse valor, `CheckoutFecharResponse.Troco` — só
   nunca tinha sido persistido além do toast de "Venda fechada! Troco:
   R$X"). Igual `_ultimaVendaImpressa`/`PodeReimprimir`, **não** é
   resetado em `InicializarAsync` — é informação sobre a venda ANTERIOR.
   Implementado com 2 `Grid`s sobrepostos dentro do mesmo `Border`, cada
   um com `Visibility` num dos 2 novos converters genéricos
   `ZeroToCollapsedConverter`/`ZeroToVisibleConverter`
   (`Converters/CommonConverters.cs` — o primeiro já existia, generalizado
   de `double` pra qualquer `IConvertible` numérico, incluindo o `int` de
   `Itens.Count`; o segundo é o inverso, novo).
- **Verificação**: `dotnet build` → 0 erros; app relançado (PID 29708,
  "Kontacto PDV", `Responding=True`). Mesma ressalva de sempre — **não
  testado ao vivo por este agente**.

#### 11ª rodada — MESMO crash de `Background`/`DependencyObject` voltou, em outro controle (mesmo dia, 2026-08-11)

Usuário reportou o mesmíssimo `InvalidOperationException` ("A propriedade
'Background' não aponta para um DependencyObject no caminho '(0).(1)'")
de novo, mesmo depois do fix da 6ª rodada (que corrigiu especificamente o
`AutoSuggestBox`). Investigação (`gh api search/code` no repositório do
WPF-UI) confirmou que o MESMO padrão de bug — `Storyboard` animando
`(Elemento.Background).(SolidColorBrush.Opacity)` no MouseEnter/Leave,
vulnerável a `Background` ficar `null` quando o elemento é reciclado por
virtualização — existe em **7 controles diferentes** da lib, não só o
AutoSuggestBox: `ToolBar`, `TreeViewItem`, `TabControl`, `ScrollBar`,
`NavigationLeftFluent` (esse último anima `BorderBrush`, não `Background`
— não bate com a mensagem exata, descartado), `DynamicScrollBar`.
Candidato mais forte pro caso desta vez: `ScrollBar`'s
`UiScrollBarLineButton` (botõezinhos de seta topo/base) — `ListaItens`
(tela de Venda) usa `ScrollViewer.VerticalScrollBarVisibility="Visible"`
(barra SEMPRE visível, sempre alcançável pelo mouse), e a animação em
questão é sobre `ScrollBarButtonBackground` = `SubtleFillColorTransparent`
(`#00FFFFFF`) — ou seja, mesmo funcionando perfeitamente, o efeito visual
é **sempre transparente→transparente, zero diferença visível**.

- **1ª tentativa (revertida)**: sobrescrever `x:Key="UiScrollBarLineButton"`
  em `Brand.xaml` com uma versão sem a animação. **Não funciona** — WPF
  resolve `StaticResource` DENTRO de `ScrollBar.xaml` (onde
  `UiVerticalScrollBar`/`UiHorizontalScrollBar` referenciam esse Style)
  usando o escopo de dicionário do PRÓPRIO arquivo da lib no momento em
  que ele é compilado/carregado — nunca "o último a vencer" do merge do
  app inteiro (isso só vale pra Styles IMPLÍCITOS, sem `x:Key`, que usam
  resolução em runtime pela árvore de recursos). Corrigir de verdade
  exigiria reimplementar o `ControlTemplate` inteiro do `ScrollBar`
  (track+thumb+botões, ~380 linhas) só pra remover uma animação que já
  não tem efeito visual nenhum — custo desproporcional ao benefício.
- **Fix real, robusto e escalável**: novo `DispatcherUnhandledException`
  handler em `App.xaml.cs::OnStartup` — captura especificamente
  `InvalidOperationException` cuja mensagem contém "DependencyObject"
  (o padrão exato desta classe de bug, em qualquer um dos 7 controles
  candidatos, presentes ou futuros), loga via `AppLog.Error` (nunca
  desaparece sem rastro) e marca `Handled = true` — impede o crash total
  do app por uma falha comprovadamente cosmética de terceiros, sem abafar
  NENHUMA outra exceção (qualquer coisa que não bata nesse padrão bem
  específico continua derrubando o app normalmente, como deveria).
- **Por que essa é a defesa certa** (não é só "esconder o problema"):
  como o mesmo padrão de bug já apareceu 2x em controles DIFERENTES da
  lib nesta sessão, e existem outros 5 candidatos ainda não exercitados
  ao vivo, remendar um controle de cada vez conforme aparece é reativo e
  incompleto por definição — a defesa em profundidade (nunca deixar ESSE
  padrão específico crashar o processo inteiro) cobre os 7 candidatos
  conhecidos E qualquer outro igual que apareça no futuro, sem precisar
  reidentificar a causa raiz a cada vez.
- **Verificação**: `dotnet build` → 0 erros (precisou matar 2 processos —
  um provável resquício de sessão de debug do Visual Studio, PID 22752, e
  o `dotnet.exe` da 10ª rodada, PID 29708); app relançado (PID 32944,
  "Kontacto PDV", `Responding=True`). **Não testado ao vivo por este
  agente** — usuário precisa confirmar que hover/interação repetida na
  barra de rolagem/outros controles não derruba mais o app (mesmo que o
  handler pegue a exceção, vale confirmar que não sobra nenhum efeito
  colateral visual estranho do catch).

### Enter no campo Senha executa a ação — regra `[GLOBAL]` (2026-08-11)

Pedido explícito do usuário, marcado "[Regras Globais]": "ao teclar enter
no campo senha de qualquer tela de autorização, como a tela de login,
executar o login da mesma." Vale pra **toda tela de autorização/login do
KPDV**, não só a atual — hoje são os 2 campos de senha que existem no app
(`LoginView.xaml`: Senha do login normal + Senha do painel de Autorização
de troca de conexão), mas qualquer campo de senha NOVO em telas futuras
(ex.: se o app ganhar uma tela própria de troca de senha, PIN de operador,
etc.) deve seguir o mesmo padrão desde o início.

- **Implementado** via `KeyDown` no `ui:PasswordBox` (code-behind,
  `LoginView.xaml.cs` — `SenhaBox_KeyDown`/`AutorizacaoSenhaBox_KeyDown`),
  checando `e.Key == Key.Enter` e chamando o `Command` correspondente
  diretamente (`EntrarCommand`/`VerificarAutorizacaoCommand`) — **não**
  simula um clique de botão, chama o `ICommand` de verdade, respeitando o
  próprio `CanExecute` (Enter com campo vazio ou já processando não faz
  nada, mesma proteção que o botão já tinha).
- **Verificação**: `dotnet build` → 0 erros (build limpo, sem bloqueio de
  arquivo desta vez); processo lançado e vivo (`Kontacto PDV`,
  `Responding=True`). **Nunca testado ao vivo via teclado de verdade**
  (só a compilação/liveness foram confirmadas) — usuário deve confirmar
  na próxima sessão de uso.

## Persistência de schema INTEGRAL (não pontual) — `backend/services/schema_ensure.py` (2026-08-11) — IMPLEMENTADO

Correção arquitetural pedida pelo usuário logo após a regra `[GLOBAL]`
"Cada app precisa se auto-atualizar no banco" (ver CLAUDE.md, mesma
seção, já corrigida com o texto integral abaixo): "a persistência não
pode ser de forma pontual. tem que ser integral."

- **Levantamento**: 24 helpers `_ensure_*` já existiam, espalhados por 15
  services diferentes (`balanca_service`, `checkout_service`,
  `controle_config_service`, `cotacao_compra_service`,
  `etiqueta_produto_service`, `gestao_compras_service`,
  `impressao_service`, `inventario_service` (2), `log_auditoria_service`,
  `modificadores_service`, `pedido_common` (8), `produto_completo_service`
  (2), `projetos_service`, `tabelas_aux_service`) — cada um só rodava
  quando o service específico que o chamava era exercitado. 23 são
  migração de SCHEMA (DDL); 1 (`contratos_service._ensure_forma_pag_
  contrato_sync`) é bootstrap de LINHA de dado de negócio, categoria
  diferente, deliberadamente excluído do registro central.
- **Novo `backend/services/schema_ensure.py`**: importa os 23 helpers de
  schema (2 tinham nome colidente — `_ensure_tables` em
  `cotacao_compra_service` e `modificadores_service` — importados com
  alias), registrados em `_MIGRACOES`. `ensure_all_schema(cur, servidor,
  banco)` roda TODOS de uma vez, cada um em try/except isolado (uma falha
  não bloqueia as outras — achado real durante a implementação: sem
  isolamento, uma migração quebrada travava as ~15 seguintes na lista,
  exatamente o oposto de "integral"), com cache em memória por processo
  (`_SCHEMA_JA_GARANTIDO`, chave `(servidor, banco)` normalizados) pra não
  repetir ~23 checagens `EXISTS` em toda requisição.
- **Wired em `backend/db/connection.py::_open_conn`** (o único ponto de
  abertura de conexão de todo o backend — mesmo argumento já usado pra
  `friendly_db_error`) via novo `_ensure_schema_integral(conn, servidor,
  banco)`, chamado logo após conectar, antes de devolver a conexão.
  **Import tardio** (dentro da função, não no topo do arquivo) — evita
  ciclo, já que `schema_ensure` importa de vários services que por sua
  vez importam `_open_conn` no topo dos arquivos deles. Falha aqui NUNCA
  derruba a conexão em si, só loga (`logging.getLogger`) — os `_ensure_*`
  originais continuam existindo nos pontos de uso de origem como rede de
  segurança adicional.
- **Bug real achado ao testar ao vivo** (não hipotético — testado contra
  GERDELL/BARESTELA de verdade antes de considerar pronto): o cursor
  aberto em `_ensure_schema_integral` precisa ser `conn.cursor(as_dict=
  True)` — os 23 `_ensure_*` foram todos escritos assumindo esse formato
  (mesmo padrão do resto do backend), e um cursor padrão (tuplas) quebrava
  com `AttributeError: 'tuple' object has no attribute 'get'` na primeira
  migração que fazia `.get(...)` no resultado.
- **Verificação em múltiplas camadas**: `pytest tests/unit` → 1807/1808
  (mesma falha pré-existente sem relação); teste ao vivo direto contra
  GERDELL/BARESTELA confirmando (a) 1ª conexão roda as 23 migrações sem
  erro (~0.8s) e (b) 2ª conexão pula tudo via cache (~0.01s); backend
  reiniciado em produção; **login real via `POST /api/login`** contra
  GERDELL/BARESTELA (master) confirmado funcionando com o mecanismo ativo.
- **CLAUDE.md atualizado** (seção "Cada app precisa se auto-atualizar no
  banco") — regra pra migração de schema NOVA daqui pra frente: escrever
  o `_ensure_*` de sempre **e também registrar em
  `schema_ensure.py::_MIGRACOES`** — é esse 2º passo que mantém a
  cobertura integral, não pontual.

## Pendência de Schema BD (2026-08-11) — cobertura gradual, por menu

Pedido explícito do usuário: "guarde em pendência, separe por menu todas
as entidades para cobrirmos de todas as telas gradativamente todos os
schema. para futuramente tenhamos todas as tabelas persistidas... Vamos
dar o nome da Pendência de Schema BD." Objetivo: usar esta lista (levantada
direto de `backend/routes/` — 68 módulos — e cruzada com os menus reais do
frontend, `frontend/app/(tabs)/*.tsx`) como checklist pra, sessão a
sessão, revisar cada entidade e confirmar se ela precisa de um `_ensure_*`
registrado em `schema_ensure.py::_MIGRACOES` (ver seção acima) — não é
pra ser feito tudo de uma vez, é o mapa completo pra cobertura ir
crescendo aos poucos até cobrir 100% do sistema.

**Legenda**: ✅ já tem `_ensure_*` registrado em `schema_ensure.py` |
⬜ ainda não revisado — próximo a fazer, gradualmente.

### Cadastros
- ⬜ Clientes (`clientes_service.py`)
- ⬜ Cliente Rápido (mesma entidade acima, tela simplificada)
- ⬜ Produtos (`produtos_service.py`)
- ✅ Produto Completo (`produto_completo_service.py` — `_ensure_promocao_periodo_cols`, `_ensure_web_dias_semana_table`)
- ⬜ Produtos Compostos (`produtos_compostos.py`)
- ⬜ Produtos Níveis (`produtos_niveis.py`)
- ⬜ Fornecedores (`fornecedores_service.py`)
- ⬜ Serviços (`servicos_service.py`)
- ⬜ Veículos (`veiculos_service.py`)
- ⬜ Funcionários (`funcionarios_service.py`)
- ⬜ Contatos (`contatos_service.py`)
- ⬜ Telemarketing (`telemarketing_service.py`)
- ⬜ Equipamentos (`equipamentos_service.py`)
- ⬜ Notas Fiscais (`notas_fiscais_service.py`)
- ⬜ Entrada/Saída de Caixa (`entrada_saida_caixa_service.py`)
- ✅ Balanças (`balanca_service.py` — `_ensure_balancas_table`)
- ⬜ Tabelas Auxiliares (`tabelas_aux_service.py` — parcial, ver Configurações abaixo)
- ⬜ Etiqueta de Produto (`etiqueta_produto_service.py` — parcial: `_ensure_modelo_etiqueta_table` já cobre a tabela de modelos, mas revisar o resto do service)
- ⬜ Modificadores (`modificadores_service.py` — parcial: `_ensure_tables` já cobre as 3 tabelas base, revisar o resto)

### Transações
- ⬜ Pedido de Venda / Pedido Bar / Pedido Geral (`pedidos_service.py`, `pedido_completo_service.py` — parcial: vários `_ensure_*` de `pedido_common.py` já cobrem colunas específicas — `hora_inclusao_item`, `qtd_pessoas`, `os_doc_origem`, `os_forma_pagamento_garantia`, `agenda_forma_pag`, `osrevisao`, `agenda_os`, `os_produto_agenda` — mas revisar se há mais colunas não cobertas)
- ⬜ O.S. Completa (`os_service.py`, `os_completo.py`)
- ⬜ Envio para Terceiros (`envio_massa.py`)
- ⬜ Gestor de Devolução (`devolucao_service.py`)
- ⬜ Movimentações (`movimentacao_produtos.py`)
- ⬜ Inventário (`inventario_service.py` — parcial: `_ensure_usuario_digitacao_col`, `_ensure_automatico_col` já cobrem, revisar resto)
- ✅ Gestão de Compras (`gestao_compras_service.py` — `_ensure_alertas_estoque_cache_table`; `cotacao_compra_service.py` — `_ensure_tables`; `curva_abc.py`/`pedido_compra.py`/`requisicao.py` do mesmo menu — revisar)
- ⬜ Gestor de Comandas (`comanda_service.py` — o arquivo que estava aberto no IDE quando este pedido foi feito)
- ⬜ Agenda (`agenda_service.py` — parcial via `pedido_common._ensure_agenda_os_table`/`_ensure_agenda_forma_pag_tables`, revisar o resto)
- ✅ Gestor de Projetos (`projetos_service.py` — `_ensure_projetos_tables`)
- ⬜ Contratos (`contratos_service.py` — `_ensure_forma_pag_contrato_sync` existe mas é bootstrap de DADO, não schema; revisar se há colunas/tabelas novas sem `_ensure_*` de schema)

### Financeiro
- ⬜ Contas a Pagar / Contas a Receber (`financeiro.py`)
- ⬜ Fluxo de Caixa (`contas.py`)
- ⬜ Cobranças (`bancos.py`, `geracao_boletos.py`, `conta_func.py`)

### Posto de Combustível
- ⬜ Bombas (`bomba.py`)
- ⬜ Mov. Encerrantes (`mov_encerrante.py`)
- ⬜ Aferições/Despesas (`afericao_abastecimento.py`)
- ⬜ Fechamento/Reabertura de Turno (`fechamento_turno.py`, `reabertura_turno.py`)
- ⬜ Metas Combustível (`combustivel_meta.py`)
- ⬜ Combustíveis (`combustivel.py`)
- ⬜ Estoque/Custo Combustível (`estoque_combustivel.py`, `custo_combustivel.py`)
- ⬜ Ilhas (`ilha.py`)
- ⬜ Tanques/Tanque Estoque/Tanque NF (`tanque.py`, `tanque_estoque.py`, `tanque_nf.py`)
- ⬜ Borderô (`bordero.py`)
- ⬜ Retífica (`retifica.py`)
- ⬜ Viagem (`viagem.py`)

### Cilindros
- ⬜ Cadastro de Cilindros / Viagens / Borderô de Cilindros (`cilindro.py`)

### Configurações
- ⬜ Tabelas Auxiliares (`tabelas_aux_service.py` — parcial: `_ensure_nfse_indop_sync` já cobre, revisar o resto — é um service GRANDE, várias tabelas auxiliares diferentes)
- ✅ Módulos e Recursos / Balança (`controle_config_service.py` — `_ensure_balanca_cols`)
- ⬜ Permissões (`permissoes_service.py`)
- ⬜ Controle do Sistema (`controle_sistema.py`, `controle.py`)
- ⬜ Usuários (`usuarios_service.py`)

### Relatórios (prioridade mais baixa — telas majoritariamente LEITURA, menor risco de schema drift, mas revisar se algum tem tabela de cache/config própria)
- ⬜ `relatorios_service.py`, `margem_lucro.py`, `descontos.py`, `relatorio_clientes.py`, `curva_abc.py` (relatório) — nenhum `_ensure_*` conhecido hoje; confirmar se genuinamente não introduzem schema novo antes de marcar como "não precisa".

### Cross-cutting (não é 1 menu específico, é infraestrutura compartilhada)
- ✅ Log de Auditoria (`log_auditoria_service.py` — `_ensure_log_auditoria_table`)
- ✅ Impressão (`impressao_service.py` — `_ensure_impressao_fila_table`)
- ⬜ Gestor de Documentos (`gestor_documentos.py`)
- ⬜ WhatsApp (`whatsapp/`)
- ⬜ Checkout/Comanda (`checkout_service.py` — parcial: `_ensure_cartao_presente_resgate_table` já cobre, revisar resto — inclui as 8 tabelas de detalhe de forma de pagamento documentadas em `checkout_service.py`'s docstring)
- ⬜ `layout.py`, `lookups.py`, `misc.py`, `auth.py` — provavelmente não introduzem schema próprio (só leem/orquestram), confirmar e marcar quando revisado.

**Como usar esta lista numa sessão futura**: escolher um menu (ou uma
entidade específica pedida pelo usuário), ler o service correspondente
procurando por `ALTER TABLE`/colunas novas sem `IF NOT EXISTS` guard
existente, escrever o `_ensure_*` que faltar, registrar em
`schema_ensure.py::_MIGRACOES`, marcar ✅ aqui. Não precisa seguir a ordem
listada — qualquer entidade tocada por outro motivo já serve de gatilho
pra revisar de passagem (mesmo princípio de não-retroatividade forçada já
usado noutras regras `[GLOBAL]` deste projeto).

## Contraste global de ComboBox/TextBox + submenu "Configurações" (2026-08-11) — IMPLEMENTADO

Continuação da sessão de testes ao vivo — usuário reportou 2 problemas
visuais adicionais e pediu 1 reorganização de navegação, todos na tela
de Venda/Configurações do KPDV.

### 1) ComboBox — dropdown "vidro" (list overlapping)

Reportado nos painéis de Configuração de Impressão E Balança: a lista
suspensa do `ComboBox` aparecia translúcida, com o conteúdo por trás
(botões "Voltar"/"Salvar") transparecendo através do texto dos itens.

**Causa raiz confirmada lendo a fonte oficial do WPF-UI**
(`Resources/Theme/Light.xaml`, tag 4.3.0): `ComboBoxDropDownBackground`
usa `AcrylicBackgroundFillColorDefault` — uma cor translúcida pensada
pra um desfoque real (Acrylic) atrás do popup, que o WPF-UI **não
aplica em popups** (limitação conhecida do próprio projeto, issue #93:
"these controls exist outside the main window, so the mica effect does
not apply to them"). Sem o desfoque, sobra só a cor translúcida — vira
vidro.

**Corrigido em `Resources/Brand.xaml`** (mesma técnica já usada pra
`ControlCornerRadius`): `ComboBoxBackground`/`ComboBoxForeground`/
`ComboBoxDropDownBackground` redefinidos com cores SÓLIDAS
(`KpdvSurfaceSecondaryColor`/`KpdvInkColor`). Resource compartilhado —
corrige todo `ComboBox` do app de uma vez, presente e futuro.

### 2) "Mesma padronização de campos" na tela de Venda

Investigação achou que este é o MESMO problema de base do Login
original ("branco sobre branco"), não um problema por tela — lendo a
mesma fonte oficial: `TextControlBackground` (usado por `TextBox`,
`AutoSuggestBox`, `NumberBox`, `PasswordBox`, `RichSuggestBox` — mesmo
grupo de brushes, confirmado no próprio comentário da lib) resolve pra
`ControlFillColorDefault = #B3FFFFFF` (branco 70% translúcido) e
`TextControlForeground` pra `TextFillColorPrimary = #E4000000` (preto
~89% translúcido) — a borda (`TextControlElevationBorderBrush`) usa
`ControlStrokeColorDefault = #0F000000`, ~6% de opacidade, quase
invisível. Todos pensados pra compor sobre um fundo com desfoque Mica
de verdade, não sobre um `Card`/tela de cor sólida como as deste app.

**Corrigido em `Resources/Brand.xaml`**: `TextControlBackground`/
`TextControlForeground`/`TextControlElevationBorderBrush` redefinidos
com cores sólidas — corrige `TextBox`/`AutoSuggestBox`/`PasswordBox`/
`NumberBox` do app inteiro de uma vez (inclusive o campo de busca da
tela de Venda, "Pesquisar por código, descrição ou GTIN"), sem precisar
repetir `Background`/`Foreground` local em cada campo — mesmo princípio
"integral, não pontual" já aplicado ao schema do backend nesta sessão.

### 3) Submenu "Configurações" no menu lateral

Pedido explícito do usuário: "Todas as configurações de Impressora,
balança, conexões, atualizar e etc, deverão ficar em um submenu do menu
configurações no menu lateral." Antes, Impressora/Balança/Atualização
eram painéis overlay dentro da tela de Venda (abertos por ícones soltos
no `TitleBar`); Conexão era uma troca de tela cheia (`ConteudoAtual`),
também acionada por ícone no `TitleBar`.

**Refactor implementado**:
- **3 novos pares View+ViewModel**, extraídos de `VendaViewModel`
  (que ficava sobrecarregado com estado de 3 painéis de configuração
  não relacionados ao fluxo de venda em si):
  `ConfiguracaoImpressaoView`/`ConfiguracaoImpressaoViewModel`,
  `ConfiguracaoBalancaView`/`ConfiguracaoBalancaViewModel`,
  `AtualizacaoView`/`AtualizacaoViewModel` — cada um tela própria
  (não mais painel overlay), registrados `AddTransient` no DI
  (mesmo padrão de Pedidos/Configurações — recarrega do zero a cada
  visita, seguro porque são só telas de configuração, sem "trabalho em
  andamento" a preservar).
- **`VendaViewModel` limpo**: removidas as ~150 linhas de estado/lógica
  dos 3 painéis (`ImpressorasDisponiveis`, `PortasComDisponiveis`,
  `BaudRateTexto`, `FonteAtualizacaoTexto`, etc., e os métodos
  `AbrirPainelConfiguracaoImpressaoAsync`/`SalvarConfiguracaoBalancaAsync`/
  `AplicarAtualizacaoAsync` e afins) — **cuidado tomado**: os SERVIÇOS
  ainda usados pela Venda de verdade (`ImpressaoTermicaService`/
  `ImpressaoConfigStore` pra imprimir o cupom ao Fechar Venda,
  `BalancaSerialService`/`BalancaConfigStore` pra ler peso ao vivo)
  continuam injetados em `VendaViewModel` — só a UI de CONFIGURAR foi
  extraída, a lógica de USAR continua lá. `UpdateService`/
  `UpdateConfigStore` foram removidos do construtor de `VendaViewModel`
  por completo — não eram usados por mais nada ali.
- **`PainelAtivo` enum**: removidos os 3 valores `ConfiguracaoImpressao`/
  `ConfiguracaoBalanca`/`Atualizacao` (só sobram os 4 painéis que
  continuam sendo overlay de verdade dentro da Venda: Fechar Venda,
  Desconto, Cancelar Venda, Importar DAV).
- **`MainWindow.xaml`**: os 4 ícones do `TitleBar` (Conexão/Impressora/
  Balança/Atualizar) removidos. `NavItemConfiguracoes` virou um item PAI
  com submenu (`NavigationViewItem.MenuItems`, suporte nativo do
  WPF-UI) com 5 filhos: "Impressão por Finalidade" (o que já existia,
  `ConfiguracoesView`), "Impressora", "Balança", "Conexão",
  "Atualização".
- **Achado importante durante o refactor** (evitou uma regressão real):
  o item pai `NavItemConfiguracoes` antes só ficava visível com
  `moduloBarAtivo && IsManagerFuncao` — mas só "Impressão por
  Finalidade" é de fato específico do módulo Bar; Impressora/Balança/
  Conexão/Atualização são configuração de MÁQUINA, sempre relevantes
  pros "3 Magníficos" independente de segmento. Corrigido: o PAI agora
  depende só de `IsManagerFuncao`; só o filho "Impressão por
  Finalidade" (`NavItemImpressaoFinalidade`) tem seu próprio
  `Visibility` extra gated por `moduloBarAtivo`. Sem essa correção, uma
  instalação sem o módulo Bar perderia acesso a Impressora/Balança/
  Conexão/Atualização inteiramente — bug que nunca existia antes desta
  rodada (os ícones do TitleBar só dependiam de `IsManagerFuncao`).
- **"Conexão" continua com tratamento especial**: diferente dos outros
  4 itens (que trocam conteúdo via `NavView.ReplaceContent`, mantendo o
  menu lateral visível), "Conexão" continua trocando `ConteudoAtual`
  inteiro e escondendo o `NavView` — trocar a conexão da máquina é
  disruptivo demais (muda banco/empresa inteira) pra continuar
  mostrando o menu lateral normal. Mesmo comportamento de antes, só
  acionado pelo item do submenu em vez do ícone antigo.
- **Verificação**: `dotnet build` → 0 erros de primeira (raro nesta
  sessão, bom sinal pra um refactor deste tamanho); processo lançado,
  título `Kontacto PDV`, `Responding=True`; varredura por referências
  soltas aos membros removidos (`BtnConexao`, `AbrirPainelConfiguracao*`,
  etc.) em todo o código-fonte → nenhuma encontrada (só um artefato de
  build intermediário em `obj/`, que se regenera sozinho). **Nunca
  exercitado ao vivo** (clicar em cada item do novo submenu, confirmar
  que Impressora/Balança/Atualização realmente abrem e salvam, confirmar
  que a Venda continua imprimindo/lendo peso normalmente) — usuário
  precisa confirmar navegando de verdade.

## Tela Principal — Painel "Movimento de Hoje" (2026-08-11) — IMPLEMENTADO

Pedido explícito do usuário: "o painel não está atualizando a venda de
checkout. acumule na lista as venda de checkout, pedidos e OS com acordion
para cada um. expandido abrir a venda ou pré venda." Motivado pela mesma
sessão de testes ao vivo do KPDV — vendas fechadas no KPDV (app desktop
separado, sem canal de push/websocket pra este painel web) só apareciam no
painel depois do usuário sair e voltar pra tela (`useFocusEffect`).

- **Auto-atualização** (`frontend/src/components/principal/useDashboard.ts`):
  novo `useEffect` com `setInterval(() => loadDashboard(session,
  situacaoFiltro), 30000)`, limpo no cleanup — refresca "Movimento de Hoje"
  (e os totais) a cada 30s enquanto a sessão está ativa, sem depender de
  focus/navegação. Projeto não tem infraestrutura de socket/push — poll
  simples é a solução consistente com o resto do app.
- **Agrupamento em acordion** (`frontend/src/components/principal/
  PedidosTable.tsx`): a lista, antes uma única tabela plana com badge de
  tipo (CHECKOUT/PED/OS) por linha, virou 3 seções recolhíveis — Checkout,
  Pedidos, O.S. (ordem fixa pedida pelo usuário, não a ordem de chegada da
  API) — cada uma com cabeçalho `"Tipo (N) · R$ subtotal"`, reaproveitando
  `frontend/src/components/pedido/AccordionSection.tsx` (já existente,
  usado em outras telas de Pedido — não duplicado). Grupo sem nenhum item
  não renderiza sua seção (mesmo princípio de "Relatórios groups" no
  CLAUDE.md). Todas as seções nascem expandidas
  (`defaultExpanded`) — nada fica escondido por padrão, só recolhível sob
  demanda. Clique numa linha continua abrindo a venda/pré-venda exatamente
  como antes (`openItem` inalterado — Checkout → `/alterar-comanda`,
  O.S. → `/os-form`, Pedido → `/pedido-form` ou `/pedido-geral` conforme
  permissão).
- **Verificação**: `npx tsc --noEmit` → 0 erros novos nos 2 arquivos
  tocados (erros pré-existentes no projeto, em arquivos não relacionados,
  continuam os mesmos de antes). **Não testado ao vivo** (abrir a Tela
  Principal, conferir que os 3 grupos renderizam e recolhem/expandem
  corretamente, e que uma venda nova do KPDV aparece sozinha em até 30s)
  — usuário precisa confirmar navegando de verdade.
