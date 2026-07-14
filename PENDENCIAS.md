# Pendências de Migração

Formato e processo definidos em `promptPendencias.md` (seção 10 — "Gestão de
pendências entre telas"). Ao retomar uma tela listada aqui, ler a seção
inteira antes de continuar — não reanalisar do zero.

---

## Transações

**Status: 🟡 scaffolding pronto, telas reais bloqueadas** (2026-07-13)

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
- Rótulos renomeados no catálogo: `PEDIDO` agora exibe "Pedidos Mobile" (era
  "Pedidos") e `OS` exibe "OS Mobile" (era "Ordem de Serviço") — só troca de
  label, mesma chave/comportamento.
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

### O que falta (bloqueado)

- **Rastrear a fonte VB6 completa de Pedido e O.S.** campo-a-campo (mesmo
  processo de "Legacy VB6 Source Reference" do CLAUDE.md) antes de
  implementar "Pedido Completo"/"O.S. Completa" de verdade — ainda não
  feito. Sem isso não dá pra saber quais campos/abas essas telas completas
  precisam além do que já existe no formulário rápido.
- Nenhuma ação customizada (`ACOES_*`) definida ainda para PEDIDO_COMP/
  OS_COMP — hoje usam `ACOES_PADRAO` (ABRIR/GRAVAR) só pra existir no
  catálogo; a lista real de ações (ex: itens, descontos, análise de
  margem, situação — como já existe em ACOES_PEDIDO/ACOES_OS) precisa ser
  definida quando as telas reais forem desenhadas.
- O menu de referência do VB6 (Produtos, Compra, Contrato, Notas Fiscais,
  Gestor de Devolução, Gestor de Projetos, Vendas, Recibos) tem bem mais
  itens que só Pedido/O.S. — fora de escopo por enquanto, usuário só pediu
  Pedido/O.S. completos nesta rodada.

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

**Status**: 🔴 bloqueada — aguardando resposta do analista/usuário sobre 2 perguntas.

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
  `cliente-completo.tsx` (aba Anexos) e `servicos.tsx` (aba Anexos).
- Painel de preview (`<img>`/`<iframe>` conforme extensão), campos
  Referência (bloqueado quando a prop é passada de fora) e Validade.

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

Depois de resposta às duas perguntas: (1) ajustar/confirmar
`_GRUPOS_CODIGO_TEXTO` em `gestor_documentos_service.py`; (2) se
`sub_referencia` for um campo real, mapear em `GestorDocumentosSection`
(nova prop) e no schema; (3) atualizar a memória de projeto
`project_gestor_documentos.md` com a resposta; (4) só então prosseguir
para wire-up de novas telas chamadoras (Pedido de Venda, O.S., etc. — ainda
não integradas ao Gestor de Documentos nesta sessão).
