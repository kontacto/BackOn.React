# Módulo: Assistência Técnica — Atendimento de Campo (Mobile)

Status: fundação de retaguarda implementada 2026-08-13 (múltiplos
equipamentos por OS + Motor de Layout na O.S. Completa) **e a "tela de
atendimento" (check-in/check-out por geolocalização + QR Code)
implementada e testada ao vivo 2026-08-14** — ver seção "Tela de
Atendimento — Implementação (2026-08-14)" mais abaixo. O que ainda falta —
Lista de Atendimento (tela nova, calendário), offline, técnico auxiliar —
continua EM ANÁLISE, não implementar sem nova liberação explícita.

## 1. Visão geral

Extensão do módulo **Assistência Técnica** (já existe no sistema como
O.S. Completa, `moduleOn("Assistencia")` — ver PENDENCIAS.md > "O.S.
Completa") para cobrir o **atendimento remoto do técnico de campo via
celular**, substituindo o processo manual atual do cliente que motivou
este pedido.

## 2. Contexto de uso (cliente real, processo atual)

Cliente: **ARGEN Ar Condicionado** (Rua Caviana, 427 - Taquara -
Jacarepaguá - Rio de Janeiro - RJ). Hoje o atendimento é feito com um
**talão de OS em papel** (numeração sequencial, ex.: "15451/1", 1ª via
cliente / 2ª via empresa) — o técnico preenche à mão em campo e só leva o
talão preenchido para a empresa **semanalmente**, quando então vira OS no
sistema. O cliente quer que o técnico registre a OS **em tempo real, via
celular**, no momento do atendimento.

### 2.1 Referência visual — talão de OS atual (papel)

Campos do talão físico, usados como referência de quais dados a OS digital
precisa cobrir no mínimo:

- Cabeçalho: nº da OS (formato `NNNNN/N`), data.
- Cliente, Endereço, Contato, Telefone.
- Defeito Reclamado.
- Serviço Executado (bloco de texto livre, várias linhas).
- Serviço a Executar (bloco de texto livre separado — usado quando o
  atendimento não resolve de primeira, ver fluxo abaixo).
- Data do Atendimento, Hora de Entrada, Hora de Saída.
- Nome do Técnico, Visto do Técnico, Assinatura do Cliente.

### 2.2 Fluxo resumido (diagrama fornecido pelo cliente)

1. Cliente solicita atendimento.
2. Supervisor interno registra a solicitação.
3. Supervisor identifica a equipe mais próxima/disponível.
4. Supervisor agenda o atendimento.
5. Técnico recebe a OS (no celular).
6. Técnico realiza o atendimento.
7. Técnico registra equipamento, modelo, identificação, defeito, serviço e
   diagnóstico.
8. **Problema solucionado?**
   - **Sim** → Técnico registra conclusão → Cliente assina (no
     celular) → OS encerrada.
   - **Não** → Técnico registra serviço a executar → Supervisor recebe a
     pendência → Supervisor envia orçamento → **Cliente aprova?**
     - **Não** → OS permanece aguardando retorno ou é encerrada/cancelada
       conforme procedimento (regra exata de quando cancelar automático
       vs. manter aguardando ainda não detalhada — ver "Pontos em aberto").
     - **Sim** → Supervisor agenda o novo serviço → Técnico realiza o
       serviço → Técnico registra execução → Cliente assina → OS
       encerrada.

Este fluxo é equivalente, em espírito, ao ciclo Aberto → Fechado/Faturado
já usado no resto do sistema para Pedido/O.S. (ver "Regras Globais de
Pré-venda" no CLAUDE.md — "todo pedido aberto é um orçamento") — o "envia
orçamento"/"cliente aprova" aqui é o mesmo tipo de ponto de decisão, só
que aplicado ao ciclo de uma O.S. de assistência técnica, com uma etapa
de aprovação do cliente no meio.

## 3. Regras de negócio (ditadas pelo cliente)

1. **QR Code por equipamento.** O sistema gera um QR Code vinculado ao
   **número de série do equipamento do cliente**. Ao chegar no local do
   atendimento, o técnico aponta a câmera do celular para o QR Code
   (provavelmente fixado no próprio equipamento) e isso **carrega a OS já
   Aberta pela retaguarda** (a OS/o vínculo equipamento↔OS precisa já
   existir, criado pelo back office — ver regra 14 abaixo, "o equipamento
   precisa ser previamente adicionado pela OS Completa") junto com o
   **histórico do equipamento** (atendimentos/OS anteriores daquele
   número de série). **Correção 2026-08-12, user-directed**: a QR Code não
   é o único caminho de entrada — o mesmo carregamento também pode ser
   disparado **de dentro da tela de atendimento** (ver regra 2), sem
   precisar ler o código de novo.
2. **Monitoramento por geolocalização (check-in/check-out).** Os técnicos
   são monitorados por geolocalização ao dar check-in e check-out em cada
   atendimento — precisa ser possível saber **data, hora e local** de cada
   check-in/check-out, se possível visualizado **num mapa, por técnico**.
   **Detalhado 2026-08-12, user-directed**: existe uma **"tela de
   atendimento"** (a tela mobile que o técnico usa durante a visita —
   ver também regra 1 e o ponto "O.S. Completa" resolvido abaixo) que
   reúne, além do check-in/check-out em si: **data e hora da marcação do
   atendimento** (quando o atendimento foi agendado, não só quando foi
   executado) e o **status do atendimento** (ver regra 9 abaixo — conceito
   distinto do status da própria OS).
3. **Fotos sempre via sistema, nunca no celular do técnico.** As fotos que
   o técnico tira durante o atendimento precisam ir direto para o sistema,
   vinculadas à OS, através do **Gestor de Documentos** (mesmo componente
   de anexos já usado no resto do sistema — ver "Gestor de Documentos" no
   CLAUDE.md) — não podem ocupar espaço de armazenamento no celular do
   técnico.
4. **Atendimento offline.** O técnico precisa conseguir realizar todo o
   atendimento (preencher OS, tirar fotos, etc.) **sem conexão com a
   internet**. Quando a conexão for reestabelecida, os dados são
   sincronizados com o banco da empresa.
5. **Técnico auxiliar.** O técnico pode trabalhar acompanhado de um
   auxiliar. Se o celular do técnico titular ficar sem bateria, o
   auxiliar pode preencher a OS **em nome do técnico**, mediante
   autorização dele.
6. **Tela "Lista de Atendimento".** Tela nova, no app do técnico, que
   lista em sequência os atendimentos que ele fará numa data — com um
   **calendário para escolher a data** no mesmo estilo do módulo Agenda
   já existente no sistema (ver "Pedido Geral — Fase B: Clínica
   (Agendamento)" no CLAUDE.md/PENDENCIAS.md), selecionando a data
   filtra a lista para os atendimentos daquele dia.
7. **Toque num atendimento da lista → abre a OS.** Tocar em um item da
   Lista de Atendimento leva direto para a tela da OS correspondente.
8. **QR Code → abre a OS (caminho alternativo ao toque na lista).** Ler o
   QR Code gerado pelo sistema (regra 1) também leva direto para a mesma
   OS — os dois caminhos (tocar na lista ou ler o QR Code) chegam no
   mesmo destino.
9. **Quem muda o status é o técnico.** Quem altera o status é o **técnico**
   (a partir das ações que ele registra no app — concluir atendimento,
   registrar serviço a executar, etc. — ver fluxo da seção 2.2), não uma
   ação direta do cliente. **Correção 2026-08-12, user-directed — são DOIS
   status distintos, não um só:**
   - **Status da própria OS** (`os.situacao`) — continua sendo o mesmo já
     usado hoje: **A**=Aberto, **F**=Fechado, **PG**=Faturado,
     **C**=Cancelado (`SITUACAO_LABEL` em `backend/services/constants.py`)
     — sem mudança aqui, confirmado.
   - **Status do ATENDIMENTO** (a visita/etapa em si — ex.: Aprovação,
     Concluído, Adiado, Orçamento, Atendendo, Aguardando Peças) — o
     usuário pediu pra verificar se já existe um cadastro pra isso.
     **Investigado nesta sessão: já existe, pronto pra reaproveitar.** A
     tabela `status_os` (codigo smallint + descricao) já é um cadastro
     CRUD completo (Tabelas Auxiliares, `tabelas_aux_service.py`
     `list/save/delete_status_os`), já ligada à coluna `os.status_os`
     (distinta de `os.situacao`), e **já está integrada de ponta a ponta**
     em O.S. Completa hoje: `frontend/app/os-geral.tsx` já tem o
     `SelectField` de Status O.S. (`statusOs`/`statusOsList`, populado via
     `GET /api/tabelas/status-os`) e o backend já lê/grava
     (`os_service.py`, coluna `status_os`). **Não existe hoje é só o
     cadastro dos VALORES certos** — os itens citados pelo usuário
     (Aprovação, Concluído, Adiado, Orçamento, Atendendo, Aguardando
     Peças) não estão pré-cadastrados em nenhuma instalação; é só uma
     questão de o cliente popular essa tabela auxiliar já existente com
     os valores que fazem sentido pro fluxo de campo — nenhuma tabela,
     coluna ou tela nova é necessária pra isso. `SITUACOES_ATENDIMENTO`
     (`agenda_service.py`) é uma lista fixa em código, DIFERENTE — cobre
     status de presença/agendamento (Confirmado, Ausente, etc.), não o
     andamento técnico da OS — não é o mesmo conceito, não confundir.

   **Quem pode alterar cada um, detalhado 2026-08-12, user-directed:**
   - As **transições de `situacao`** — Fechar, Cancelar, Faturar, Reabrir
     — continuam sendo feitas pela **O.S. Completa**, controladas por
     **permissão** (mesmo modelo já existente hoje — `OS_COMP.*` no
     catálogo de permissões, botões de ação em `os-geral.tsx`/
     `ItemList.tsx`). **Se o app mobile/campo também vai ter acesso a
     essas mesmas ações ainda não foi decidido** — fica como ponto em
     aberto, não assumir nem "sim" nem "não" até confirmação.
   - **O mobile PODE alterar o `status_os`** ("Status da OS", o campo do
     atendimento — Aprovação/Concluído/Adiado/Orçamento/Atendendo/
     Aguardando Peças etc.) — essa é a ação natural do técnico durante a
     visita, confirmada explicitamente. Ou seja: mudar o **andamento do
     atendimento** é livre pro técnico em campo (sujeito à permissão
     normal de gravar na OS); mudar a **situação formal da OS**
     (Fechar/Cancelar/Faturar/Reabrir) é ação de retaguarda, com o acesso
     mobile ainda pendente de decisão.
   - **Detalhado 2026-08-12, user-directed — "Cancelar" também existe no
     nível do EQUIPAMENTO, não só no nível da OS inteira.** Com a OS
     suportando múltiplos equipamentos (regra 14), cancelar um
     equipamento específico dentro da OS é tratado como uma ação de
     situação própria daquele equipamento — equivalente ao "Cancelar" que
     a OS já tem hoje, só que aplicado a um item/equipamento em vez da OS
     toda (permite cancelar o atendimento de UM equipamento problemático
     sem cancelar a OS inteira, que pode ter outros equipamentos ainda em
     andamento). Ainda não especificado: se essa ação também é
     exclusiva da O.S. Completa (mesmo padrão do "vincular equipamento"
     abaixo) ou se o mobile pode cancelar um equipamento específico
     durante o atendimento — fica registrado como detalhe a confirmar
     quando a "tela de atendimento" for desenhada.
10. **Lista de Atendimento é a tela inicial do app do técnico.** Ao entrar
    na "Ordem de Serviço" (o app/módulo do técnico), ele é direcionado
    direto para a Lista de Atendimento (regra 6) — que fica dentro da sua
    Agenda (a mesma agenda de onde vem a lista de atendimentos do dia
    selecionado no calendário).
11. **Auxiliar tem usuário e senha próprios, mas alterar a OS exige a
    credencial do técnico.** Ao abrir a OS, é preciso informar quem será
    o auxiliar daquele técnico. O auxiliar tem **login/senha próprios**
    no sistema (usuário normal, cadastro já existente hoje — ver
    `usuarios_service.py`, a novidade é só o vínculo "auxiliar de qual
    técnico" numa OS específica) e pode **visualizar** a Lista de
    Atendimento com sua própria conta — mas para **fazer alterações na
    OS** (preencher/editar em nome do técnico, cenário da regra 5 —
    celular do técnico sem bateria), precisa entrar com a
    **credencial do técnico titular**, não com a própria.
12. ~~OS relacionada — outro equipamento no mesmo atendimento vira nova OS
    com código de referência para a original.~~ **SUPERADA (regra 14
    abaixo) — não será feito assim.** O técnico **não vai abrir uma nova
    OS** para atender outro equipamento na mesma visita — em vez disso, a
    própria OS passa a suportar múltiplos equipamentos (ver regra 14).
    Mantido riscado aqui só como histórico da decisão anterior, não
    seguir esta regra.
13. **Criar OS exige permissão.** O técnico só pode criar uma OS nova se
    tiver a permissão correspondente — reforça o modelo de permissões já
    existente no resto do sistema (catálogo `CATALOGO` em
    `permissoes_service.py`, ex.: `OS.GRAVAR`/`OS_COMP.GRAVAR`), sem
    exceção especial para o app de campo.
14. **Mudança grande de modelo: uma OS pode ter mais de um equipamento no
    mesmo atendimento.** Diferente de tudo que existe hoje no sistema
    (uma O.S. de Assistência tem hoje um único `os.numero_de_serie`), a
    OS de atendimento de campo passa a suportar **múltiplos
    equipamentos** dentro da mesma OS — é assim, e não com OS
    separadas/relacionadas (regra 12, revogada), que o cenário "achei
    outro equipamento com problema na mesma visita" é resolvido.
    **Adicionar um equipamento novo à OS exige permissão própria**,
    configurável (nova ação/`BOTAO` no catálogo de permissões, mesmo
    padrão de "Botão de tela secundária precisa permissão" no CLAUDE.md)
    — nem todo usuário com acesso à OS pode necessariamente incluir mais
    equipamentos nela.

    **Referência visual (screenshot do sistema concorrente AUVO,
    `app.auvo.com.br`, tela "Cadastrar nova tarefa" → aba
    "Equipamentos")**: na criação da OS, uma lista de seleção múltipla
    (checkbox por linha) com os equipamentos já associados ao
    cliente/colaborador/equipe selecionado — colunas Nome, Identificador,
    Associado a, Garantia até; campo de busca por nome/identificador +
    filtro por Associação/Especificações. É o padrão de UI de referência
    para "escolher quais equipamentos do cliente sofrerão manutenção
    nesta OS" (regra 14) — lista de seleção múltipla sobre a base de
    equipamentos já cadastrados do cliente, não um campo avulso por
    equipamento. Mais próximo do já existente `EquipamentoSearchModal`
    (O.S. Completa hoje) estendido para **seleção múltipla**, do que de
    um componente novo do zero.
15. **Checklist do atendimento reaproveita o Motor de Formulário Dinâmico
    já existente ("Motor de Layout").** Referência: documento
    `OS_CLIMATIZACAO_MODELO_DEMO.pdf` (relatório de visita de um
    concorrente — AUVO Tecnologia — fornecido como modelo do que o
    checklist da OS de campo precisa cobrir), mostrando 3 blocos de
    perguntas dinâmicas na mesma visita ("Instalação - Ar Condicionado",
    12 perguntas; "PASSOS RECOMENDADOS PARA REALIZAÇÃO DO PMOC 1", 10
    passos; "Pintura residencial", 4 perguntas), cada bloco com perguntas
    numeradas emparelhadas (2 por linha) e respostas curtas (Sim/Não,
    texto livre, número/medida).
    **Este sistema já tem esse motor implementado** (não para O.S. ainda,
    mas o modelo já serve) — `backend/services/layout_service.py` +
    `routes/layout.py`, tabelas `layout`/`layout_campos`/
    `layout_tipo_campo`/`layout_entidade`/`layout_preenchido`. O cadastro
    do template (`frontend/app/layout-cadastro.tsx`) já suporta a
    entidade **O.S.** como uma das entidades marcáveis (coluna `os` em
    `layout`), campos emparelhados (`campo1`/`campo2`, igual ao layout do
    PDF), tipo de campo via lookup, e **campo calculado com fórmula entre
    2 campos** (`calculado`/`calc_campo1`/`calc_campo2`/`operador` já
    existem no schema — respondendo a pergunta "não lembro se
    implementamos fórmulas": sim, o campo existe, mas a **resolução ao
    vivo do cálculo ainda não foi implementada**, hoje aparece desabilitado
    com aviso, ver PENDENCIAS.md > "Motor de Layout"). O preenchimento em
    tela (`LayoutPreenchimentoModal.tsx`, padrão Possíveis/Preenchidos) já
    está integrado no módulo Agenda — **mas ainda não na tela O.S.
    Completa** (`os-geral.tsx`), que é exatamente a peça que falta para
    cobrir este checklist. Como uma OS pode ter vários checklists
    aplicáveis na mesma visita (ex.: os 3 blocos do PDF), o modelo já
    suporta isso nativamente — cada bloco é um Layout próprio, e
    `layout_entidade` já permite múltiplos preenchimentos por instância de
    entidade.

    **Atualizado — acesso ao cadastro do template já implementado
    (2026-08-12).** O cadastro do Layout (o template, quem define as
    perguntas) passou a ficar em **Configurações**, rotulado
    **"Formulário Dinâmico"** (não em Tabelas Auxiliares, onde estava sem
    nenhum ponto de acesso até então) — tile novo em
    `frontend/app/(tabs)/configuracoes.tsx`, seção "Geral", gated por
    `can("LAYOUT.ABRIR")`, web-only. Nome exibido também atualizado no
    cabeçalho da própria tela (`layout-cadastro.tsx`) e no rótulo da
    permissão no catálogo (`permissoes_service.py`) — de "Cadastro de
    Layout" para "Formulário Dinâmico" em todo lugar visível ao usuário
    (a permissão em si continua com a chave interna `LAYOUT`, sem
    renomear). **Isso é só o cadastro do template — a tela de
    preenchimento em si (`LayoutPreenchimentoModal.tsx`) continua sem
    integração com O.S., que é o que falta pra fechar o checklist do
    atendimento de campo.**

    **Confirmado: o preenchimento acontece no momento do atendimento, e
    fica vinculado a ele.** O técnico preenche o(s) Formulário(s)
    Dinâmico(s) aplicável(is) **durante a visita** (não é algo preenchido
    depois, na retaguarda) — e o preenchimento fica **vinculado ao
    atendimento** (a OS/visita específica), reaproveitando o mesmo
    mecanismo `layout_entidade` (`entidade=O.S.`, `codentidade=código da
    OS`) já usado para as outras entidades.

## 4. Pontos em aberto (não bloqueiam a análise, mas precisam de resposta
   antes da implementação)

Itens já resolvidos ficam riscados, com a resolução ao lado — mantidos
aqui (não apagados) pra preservar o histórico da decisão.

- ~~Regra 1/8 (QR Code): confirmado que é **gerado pelo sistema** (regra 8).
  Ainda falta confirmar onde ele fica **fisicamente**~~ — **RESOLVIDO
  2026-08-12, user-directed**: a impressão do QR Code é feita **a partir
  do Cadastro de Equipamento** (`equipamentos.tsx`/`equipamentos_service.py`),
  junto com a identificação do equipamento — não é uma tela/fluxo
  separado, é uma ação do cadastro já existente.
- ~~Como este fluxo se encaixa na tela **O.S. Completa** já existente —
  é uma extensão dela pro mobile, ou uma tela mobile nova e mais
  enxuta?~~ — **RESOLVIDO 2026-08-12, user-directed**: **estende a O.S.
  Completa** (`os-geral.tsx`), não vira um app/tela separado — a novidade
  é a **"tela de atendimento"**: os recursos de atendimento em campo
  (check-in/check-out, status do atendimento, QR Code, checklist) ficam
  dentro da própria O.S. Completa, com as informações necessárias
  organizadas pro uso do técnico no mobile. Ainda não desenhado em
  detalhe (layout exato dessa "tela de atendimento" dentro de
  `os-geral.tsx`) — só a decisão de "estende, não separa" está fechada
  (ver "genuinamente em aberto" abaixo).
- Regra 14 (múltiplos equipamentos por OS) — pontos de arquitetura,
  **todos resolvidos nesta rodada (2026-08-12, user-directed)**:
  - ~~`os.numero_de_serie`... decidir se continua existindo~~ —
    **RESOLVIDO, ver seção 5**: a coluna continua existindo, intocada,
    virando o "equipamento principal" histórico; uma tabela filha nova é
    populada automaticamente por backfill a partir dela, sem perda de
    dado e sem script manual. Ver também seção 5.1 (por que a tabela
    filha continua sendo necessária mesmo reaproveitando essa coluna).
  - ~~Defeito/Serviço/Diagnóstico — por equipamento ou no cabeçalho da
    OS?~~ — **RESOLVIDO: por equipamento.** Cada equipamento da OS tem
    seu próprio Defeito Reclamado / Serviço Executado / Serviço a
    Executar / Diagnóstico — não fica mais compartilhado no cabeçalho da
    OS pra atendimentos com múltiplos equipamentos.
  - ~~QR Code: ler o QR de um 2º equipamento com OS já aberta —
    adiciona o equipamento à OS?~~ — **RESOLVIDO, com uma restrição
    importante**: ler o QR de um equipamento **abre a informação daquele
    equipamento DENTRO da OS já aberta, pronta pra ser preenchida** — mas
    o **equipamento precisa já ter sido adicionado à OS previamente, via
    O.S. Completa** (retaguarda/back office). Ou seja: o técnico em campo
    **não** adiciona um equipamento novo à OS só por ler um QR Code não
    vinculado — a associação equipamento↔OS é responsabilidade da
    retaguarda (O.S. Completa), o QR em campo só **carrega** o que já foi
    associado. Consistente com a regra 1 revisada acima ("carrega a OS
    Aberta pela retaguarda").
    ~~O que acontece se o técnico ler um QR Code de um equipamento que
    NÃO foi previamente adicionado à OS?~~ — **RESOLVIDO 2026-08-12,
    user-directed**: o técnico **recebe uma mensagem** informando que
    precisa vincular o equipamento à OS. **Reforçado no mesmo dia: vincular
    equipamento à OS é ação EXCLUSIVA da O.S. Completa** — não é uma
    questão de permissão que poderia liberar isso no mobile no futuro
    (diferente da dúvida em aberto sobre Fechar/Cancelar/Faturar/Reabrir
    acima), é uma restrição de onde a ação mora: só existe na O.S.
    Completa, ponto final. A mensagem que o técnico recebe em campo é
    puramente informativa/de bloqueio — nunca abre um caminho alternativo
    de vincular pelo mobile.
  - ~~Faturamento/orçamento — por equipamento ou único pra OS inteira?~~
    — **RESOLVIDO: faturamento é por OS** (fluxo único pra OS inteira,
    independente de quantos equipamentos ela tiver dentro).
- ~~Regra 15 (checklist/Motor de Layout): por equipamento ou pra OS como
  um todo?~~ — **RESOLVIDO 2026-08-12, user-directed: pra OS como um
  todo**, não por equipamento — `layout_entidade` continua vinculado a
  `codentidade = código da OS` sem precisar de uma granularidade nova por
  equipamento; quantos checklists forem aplicáveis (Possíveis), todos são
  preenchidos no nível da OS inteira, do jeito que o mecanismo já
  funciona hoje pras outras entidades.

- ~~Regra 9: se o app mobile/campo terá acesso às transições de `situacao`
  da OS (Fechar/Cancelar/Faturar/Reabrir, hoje só na O.S. Completa por
  permissão)~~ — **RESOLVIDO 2026-08-13, user-directed: parcial, só
  Fechar.** O técnico PODE **Fechar** a OS em campo, ao concluir o
  atendimento — é a transição natural do fluxo "Problema solucionado? Sim
  → OS encerrada" (seção 2.2). **Cancelar/Faturar/Reabrir continuam
  exclusivos da retaguarda** (O.S. Completa web, `OS_COMP.SITUACAO`) — não
  ficam disponíveis no app do técnico. Quando a implementação chegar
  nesse ponto: reaproveitar `_fechar_os_sync` já existente (mesmo backend
  que a O.S. Completa web já chama), só expor a ação no app mobile
  controlada pela mesma permissão de sempre — sem motor de regra novo.
- ~~Regra 8/"Não" do fluxo — o que acontece com a OS quando o cliente
  recusa ou não responde o orçamento enviado~~ — **RESOLVIDO 2026-08-13,
  user-directed: aguarda manual, sem prazo automático.** A OS fica no
  `status_os` de aguardando aprovação (valor a cadastrar na tabela
  auxiliar, junto com os demais valores da regra 9 acima —
  Aprovação/Concluído/Adiado/Orçamento/Atendendo/Aguardando Peças)
  **indefinidamente**, até um supervisor decidir manualmente cancelar
  (usando o "Cancelar" que a OS já tem hoje, sem botão dedicado novo) ou
  seguir o atendimento. **Nenhum job/cron/checagem automática de prazo é
  necessário** — mais simples que o mecanismo de disparo diário já usado
  no Inventário (que não se aplica aqui, decisão consciente de não
  replicar esse padrão pra este caso).
- **Confirmado 2026-08-13, user-directed: os 2 pontos abaixo continuam
  deliberadamente em aberto**, adiados para quando a implementação
  chegar na fase mobile (não é uma lacuna esquecida, é escolha explícita
  de não decidir agora):
  - Regra 4 (offline): estratégia de sincronização/resolução de conflito
    (ex.: dois técnicos/auxiliares editando a mesma OS off-line) — este
    projeto não tem nenhum módulo offline-first hoje, será a primeira
    vez. Decidir só quando a implementação do app mobile realmente
    começar, não antes.
  - Desenho exato da "tela de atendimento" dentro de O.S. Completa
    (layout, quais campos ficam visíveis quando, navegação a partir da
    Lista de Atendimento) — fica para uma sessão dedicada de
    wireframe/UX mais adiante, não decidido nesta rodada.

## 5. Estratégia de migração — múltiplos equipamentos por OS sem perda de dado

Pedido explícito do usuário: a regra 14 (uma OS pode ter vários
equipamentos) precisa ser implementada nos bancos de cada cliente **sem
perder dado** e **de forma transparente** — o cliente não pode perceber
nem precisar fazer nada manual. Isso é exatamente o caso que a regra
`[GLOBAL]` já existente neste projeto foi criada para cobrir — ver
CLAUDE.md > "Cada app precisa se auto-atualizar no banco, de forma
INTEGRAL — nunca script de migração manual". A estratégia abaixo é só a
aplicação dessa regra já estabelecida a este caso específico, não um
mecanismo novo.

1. **Tabela nova, não substituição destrutiva.** Uma tabela filha nova
   (ex.: `os_equipamento`, no mesmo formato de item que `os_produto` já
   usa) passa a guardar N equipamentos por OS. A coluna atual
   `os.numero_de_serie` **não é removida** — continua existindo, intocada
   — mesmo princípio de preservação de coluna já usado deliberadamente no
   módulo Cilindro (CLAUDE.md > "Pedido de Cilindro" — "decisão consciente
   de manter... não recriar colunas, não sugerir esse refatoramento de
   schema de novo").
2. **Backfill automático, idempotente e set-based**, dentro do mesmo
   `_ensure_*` que cria a tabela nova (registrado em
   `schema_ensure.py::_MIGRACOES`, aplicado por `ensure_all_schema` na
   primeira conexão de cada `servidor`+`banco`, mesmo mecanismo que já
   aplica as 23+ migrações de schema existentes hoje):
   ```sql
   INSERT INTO os_equipamento (os, numero_de_serie, principal)
   SELECT o.codigo, o.numero_de_serie, 1
   FROM os o
   WHERE o.numero_de_serie IS NOT NULL AND o.numero_de_serie <> ''
     AND NOT EXISTS (SELECT 1 FROM os_equipamento oe WHERE oe.os = o.codigo)
   ```
   O `NOT EXISTS` faz o backfill **idempotente** — roda de novo em toda
   conexão sem duplicar linha, e nunca sobrescreve um equipamento que já
   tenha sido adicionado manualmente depois da primeira execução. É isso
   que garante "transparente, sem perda de dado": nenhum script manual,
   nenhuma janela de manutenção, o próprio primeiro request contra o
   banco do cliente já popula a tabela nova a partir do que já existia.
3. **Todo código novo lê/grava só na tabela nova** — `os.numero_de_serie`
   vira campo histórico (o "equipamento principal" pré-migração), sem
   nenhuma tela nova escrevendo nele. Antes de considerar a migração
   concluída, auditar se algum relatório/tela já existente lê esse campo
   diretamente e decidir, caso a caso, se precisa passar a ler da tabela
   nova (com fallback pro campo antigo) ou se pode continuar como está.
4. **Falha isolada por migração** — mesma garantia já existente em
   `ensure_all_schema`: se este `_ensure_*` falhar num banco específico
   (nome de coluna conflitante, por exemplo), as outras migrações do
   sistema continuam aplicando normalmente; o erro é logado, nunca
   bloqueia a conexão em si.

**Fora do escopo desta estratégia** (ver "Pontos em aberto" acima): o
formato exato da tabela nova ainda não está totalmente decidido — esta
seção resolve só o "como migrar sem perder dado", não o desenho final da
tabela. Já confirmado até agora que `os_equipamento` precisa de, no
mínimo: Defeito/Serviço/Diagnóstico por equipamento (já resolvido acima),
uma ação de **cancelar** própria por equipamento (não só a `situacao` da
OS inteira — ver regra 9), e um campo de **status do equipamento**
— **valor confirmado 2026-08-12, user-directed: "Não atendido"** (esse
equipamento especificamente não foi atendido nesta visita). Esse status é
**um conceito à parte do `status_os`** ("Status do Atendimento" —
Aprovação/Concluído/Adiado/etc., que é da OS como um todo, ver regra 9)
em termos de SIGNIFICADO — mas **RESOLVIDO 2026-08-12, user-directed:
reaproveita a MESMA tabela `status_os`** como cadastro (não cria uma
tabela/enum nova) — "Não atendido" vira só mais um `codigo`/`descricao`
cadastrado ali, só que referenciado a partir de `os_equipamento` (por
equipamento) em vez de a partir de `os` (pela OS toda). `os_equipamento`
precisa então de sua própria coluna FK pra `status_os.codigo`, distinta
da coluna `os.status_os` que já existe hoje pro nível da OS — os dois
níveis (OS e equipamento) apontam pra linhas da mesma tabela de cadastro,
só em colunas/lugares diferentes. Catálogo completo de valores além de
"Não atendido" ainda não fechado (ex.: precisa também de um "Atendido"?
"Pendente"?) — mas isso já não trava mais o desenho da tabela, é só
questão de cadastro (mesmo caso já resolvido pra `status_os` no nível da
OS, ver regra 9). Quando o desenho final de `os_equipamento` for
fechado, o `INSERT` de backfill acima precisa ser ajustado pra preencher
também as colunas novas que existirem (hoje o SQL acima assume só
`os`/`numero_de_serie`/`principal` como exemplo mínimo).

**"Não atendido" cadastrado em `ARGEN-TESTE`, 2026-08-14** — via
`POST /api/tabelas/status-os` (mesmo endpoint CRUD já existente,
`tabelas_aux_service.save_status_os`), `codigo=7` (próximo livre — os 6
já existentes eram os do nível OS: 1 Aguardando aprovação do Orçamento, 2
Aguardando Liberação de Execução, 3 Pendente, 4 Em execução, 5 Executado,
6 Cancelado). Só o cadastro do VALOR — nenhuma coluna nova em
`os_equipamento` foi criada nesta rodada (a FK própria pra esse status,
citada acima, continua não implementada; é peça de código, não de dado).

### 5.1 Por que a tabela filha continua necessária (analisado 2026-08-12)

Pergunta levantada pelo usuário: dá pra evitar criar `os_equipamento` e só
reaproveitar `os.numero_de_serie` pra popular os números de série dos
equipamentos? **Não, pelo motivo abaixo — mas parte da ideia já está
correta e já é o que a seção 5 propõe.**

- **`os.numero_de_serie` hoje é uma coluna ESCALAR** (`VARCHAR(20)`, ver
  `os_service.py::_trunc(req.numero_de_serie, sizes, "numero_de_serie",
  20)`) — guarda exatamente **um** valor por linha de `os`, e é um soft-FK
  por **texto** pro `equipamentos.numero_de_serie` (que é único
  GLOBALMENTE entre clientes, ver `equipamentos_service.py`). A regra 14
  inteira existe porque uma OS precisa referenciar **N** equipamentos, não
  1 — e uma coluna escalar não guarda N valores sem virar uma lista
  separada por vírgula (ou JSON) dentro do campo, o que quebraria:
  - **Integridade**: não dá pra ter um soft-FK de texto válido apontando
    pra vários `equipamentos.numero_de_serie` ao mesmo tempo dentro de uma
    única string sem parsing manual em toda consulta.
  - **Histórico por equipamento** (regra 1 — "abre a OS já carregada com
    o histórico do equipamento"): responder "quais OS já atenderam este
    número de série" via `LIKE '%123%'` numa lista concatenada é lento,
    frágil (falso-positivo se um serial for substring de outro) e não tem
    precedente em nenhum lugar deste sistema.
  - **Consistência com o resto do projeto**: toda vez que este sistema já
    precisou de "1 registro-pai tem N itens-filho" (Pedido→itens via
    `pedido_venda_prod`, O.S.→itens via `os_produto`, Cliente→telefones via
    `cliente_tel`, Cliente→endereços via `cliente_end`), a solução sempre
    foi uma tabela filha de verdade, nunca uma coluna escalar com lista
    embutida — não há motivo pra abrir exceção aqui.
  - Os próprios "Pontos em aberto" da regra 14 (Defeito/Serviço/Diagnóstico
    por equipamento? check-in/out por equipamento? faturamento por
    equipamento? checklist do Motor de Layout por equipamento?) só fazem
    sentido de responder "sim" se cada equipamento da OS for uma **linha**
    própria com seu próprio código — o que uma coluna escalar não
    oferece de jeito nenhum.
- **O que da ideia do usuário JÁ está certo, e já é exatamente o que a
  seção 5 propõe**: `os.numero_de_serie` continua sendo usado — não como
  mecanismo de armazenamento contínuo, mas exatamente como a **fonte do
  backfill** (passo 2 acima) — é dali que vem o valor que popula
  automaticamente a primeira linha (`principal=1`) da tabela nova pra toda
  OS já existente, sem nenhum script manual. Ou seja: a coluna não morre
  nem fica ociosa — ela é literalmente o dado de origem que "povoa os
  números de série dos equipamentos" na tabela nova, só que isso acontece
  **uma vez, no backfill**, não como leitura/escrita contínua depois disso
  (ponto 3 da seção 5: código novo lê/grava só na tabela nova daqui pra
  frente).
- **Decisão de desenho ainda em aberto, vale registrar aqui**: o exemplo
  de `os_equipamento` na seção 5 replica o mesmo soft-FK por **texto**
  (`numero_de_serie`) que `os.numero_de_serie` já usa hoje — mantém o
  padrão já validado no restante do sistema (cascata de rename em
  `equipamentos_service.py`), mas um FK de verdade por
  `equipamentos.codigo` (inteiro, chave primária) seria mais correto
  architeturalmente. Não decidido ainda — fica junto dos outros pontos em
  aberto da regra 14 quando a implementação for liberada.

## 6. Tela de Atendimento — Implementação (2026-08-14)

**Status: 🟢 implementada e testada ao vivo em ARGEN-TESTE** (backend
100% verificado via chamada direta aos endpoints; frontend confirmado só
por `tsc --noEmit` limpo + bundle Metro sem erro — **sem teste real de
câmera/GPS/dispositivo físico nesta sessão**, mesma limitação de ambiente
já registrada em outras rodadas deste projeto).

Duas decisões de arquitetura confirmadas com o usuário antes de
implementar (sessão de wireframe/UX que a seção 4 já previa):

1. **Tela mobile enxuta e separada**, não abrir a O.S. Completa
   (`os-geral.tsx`, web-only) pro mobile — mesmo padrão rápido/completo já
   usado em Cliente e Pedido/O.S.
2. **Um único par de check-in/check-out por OS** (não um conceito de
   "visita" repetível) — mais simples, sem tabela nova.

### Backend

- **8 colunas novas em `os`** (não uma tabela nova):
  `checkin_em`/`checkin_lat`/`checkin_lng`/`checkin_usuario`,
  `checkout_em`/`checkout_lat`/`checkout_lng`/`checkout_usuario` — todas
  `NULL`. Migração `_ensure_os_checkin_cols` (`os_service.py`), registrada
  em `schema_ensure.py::_MIGRACOES` (regra `[GLOBAL]` de persistência
  integral).
- `_get_os_sync` estendida com os 8 campos — como
  `os_completo_service._get_os_completo_sync` chama essa função como base,
  a O.S. Completa web também passou a expor esses campos (read-only),
  **de graça**, sem precisar tocar em `os_completo_service.py`.
- `_checkin_os_sync`/`_checkout_os_sync` (`os_service.py`) — validam OS
  aberta, bloqueiam check-in/check-out duplicado, checkout exige check-in
  prévio. `POST /api/os/{codigo}/checkin`/`.../checkout`
  (`OSCheckinRequest`: `latitude`/`longitude` + campos de auditoria).
- `POST /api/os/{codigo}/fechar-atendimento` — reaproveita
  `_fechar_os_sync` já existente (mesma função que `OS`/`OS_COMP` chamam),
  só com `tela="OS_ATENDIMENTO"` pra checar a permissão certa.
- `GET /api/os/resolver-por-equipamento?numero_de_serie=` — resolve o nº
  de série lido do QR Code pra uma O.S. Aberta já vinculada a ele
  (`os_equipamento_service.resolver_os_aberta_por_serie`). **Bug real
  encontrado e corrigido no teste ao vivo**: resolver por um único
  `equipamentos.codigo` (`TOP 1` pelo nº de série) escolhia a linha errada
  quando havia duplicatas (mesmo problema de dado sujo já documentado no
  backfill de `_ensure_os_equipamento_table` — `numero_de_serie='1'`
  repetido em várias linhas de `equipamentos` no ARGEN-TESTE) — corrigido
  casando `equipamentos`→`os_equipamento`→`os` pelo **texto** do nº de
  série nos 3, não por um `equipamento.codigo` resolvido antes.
- `GET /api/equipamentos/{codigo}/historico-os` — histórico de OS já
  atendidas naquele equipamento (regra 1).
- **Gotcha de ordem de rota, achado ao vivo**: `GET /os/resolver-por-
  equipamento` registrada DEPOIS de `GET /os/{codigo}` fazia
  "resolver-por-equipamento" ser capturado pelo path param `{codigo}`
  (int) e nunca alcançar a rota certa — 422 de "not a valid integer" em
  vez de resolver. Corrigido movendo a rota nova pra ANTES de
  `GET /os/{codigo}` no arquivo (mesmo alerta já registrado em memória
  "Checar colisão de rota antes de criar").
- **Permissões**: nova tela `OS_ATENDIMENTO` ("Atendimento Campo") no
  catálogo, ações `ABRIR`/`CHECKIN`/`CHECKOUT`/`REGISTRAR`/`SITUACAO` (o
  nome `SITUACAO` é obrigatório, não cosmético — `_fechar_os_sync` já
  checa `tem_permissao(cur, classe, tela, "SITUACAO")` hardcoded).
  Gateada por `Assistencia` (não Oficina) tanto no backend
  (`disabled_telas`) quanto no frontend (`src/permissions/index.tsx`,
  mesmo espelhamento client-side já usado pra `OS`/`OS_COMP`).
- 12 testes unitários novos (`test_os_checkin.py`) + suíte completa
  (1838 testes) rodada — só a falha pré-existente e sem relação de
  sempre (CNAB Itaú, data hardcoded).

### Frontend

- **`frontend/app/os-atendimento.tsx`** (novo, lean, sem tabs) — 2
  estados: **scanner** (sem `?os=` na URL — `CameraView` do `expo-camera`
  com leitura de QR + busca manual por nº de série como fallback) e
  **atendimento** (com `?os=&serie=` — dados da OS, histórico do
  equipamento, Check-in, cards de equipamento, Formulário Dinâmico,
  Fechar O.S., Check-out).
- **Reaproveitados tal como estão, sem nenhuma alteração**:
  `useOSEquipamentos.ts`/`OSEquipamentoCard.tsx` (mesmos endpoints
  `/api/os-completo/{os}/equipamentos...` — confirmado sem checagem de
  permissão no backend, então funcionam pro técnico em campo mesmo sem
  permissão `OS_COMP.*`) e `LayoutPreenchimentoModal.tsx` (Motor de
  Layout, entidade O.S., mesmo componente já usado em `os-geral.tsx`).
- **Novas dependências**: `expo-camera` + `expo-location` (`npx expo
  install`), strings de permissão em `app.json` (iOS `infoPlist` +
  Android `permissions` + plugins `expo-camera`/`expo-location`).
- **"Modo Didático"** aplicado (ícone "i" no cabeçalho, `AjudaPedidoModal`
  reaproveitado com lista própria de itens).
- Entrada: tile "Atendimento de Campo" em `ModuleTiles.tsx` (Tela
  Principal), rota `/os-atendimento`.

### Fora do escopo desta rodada (fica pra depois, não é lacuna esquecida)

- **Lista de Atendimento** (tela separada, calendário) — não construída.
- **Sincronização offline** — doc já marcava como "decidir só quando a
  implementação mobile realmente começar".
- **Técnico auxiliar** (regra 5) — não implementado, mobile sempre pede a
  credencial de quem está logado.
- **"Data/hora da marcação do atendimento"** (regra 2) — investigado se
  dava pra reaproveitar `AGENDA_OS`, mas essa tabela liga a **item de
  serviço** (`os_produto.cod_os_prod`), não à OS inteira — conceito
  diferente, não mapeado.
- **Teste real de câmera/GPS/dispositivo físico** — nunca exercitado
  nesta sessão (sem hardware/emulador com câmera disponível); antes de
  considerar esta feature pronta pra produção, testar em dispositivo real
  com o cliente ARGEN.

## 7. Extensões pedidas na sequência (2026-08-14, mesmo dia)

Logo depois da entrega da seção 6, o usuário pediu 3 extensões — todas
**implementadas e testadas ao vivo** contra ARGEN-TESTE (OS #294):

1. **Check-in/check-out (horário + localização) exibidos na O.S.
   Completa** — antes só existiam no banco/API. Novo card em `os-
   geral.tsx` logo após "Equipamentos", com data/hora + link "Ver no
   mapa" (`Linking.openURL`, URL de busca do Google Maps — sem
   precedente no projeto, construído direto). `os-atendimento.tsx`
   (mobile) ganhou a mesma confirmação de check-in que o check-out já
   tinha.
2. **Auxiliar do técnico** (regra 11, campo opcional — só o cadastro,
   sem o fluxo "auxiliar edita com a credencial do titular") — nova
   coluna `os.auxiliar_tecnico INT NULL` (migração
   `_ensure_os_auxiliar_tecnico_col`, `os_completo_service.py`,
   registrada em `schema_ensure.py`), mesmo padrão soft-FK de
   `tecnico_responsavel`. Campo novo em `os-geral.tsx` (`SelectField`,
   ao lado de "Técnico Responsável").
3. **Lista de Atendimento acessível no web e no mobile** — decisão
   confirmada com o usuário: **estender `os-lista.tsx`** (já existia,
   antes web-only) em vez de criar tela nova. Mudanças:
   - Trava `Platform.OS !== "web"` → `LockedView` virou
     `!(can("OS_COMP.ABRIR") || can("OS_ATENDIMENTO.ABRIR"))`.
   - Toque na linha abre `os-geral.tsx` (web) ou `os-atendimento.tsx`
     (mobile), decidido por `Platform.OS`.
   - **Nova permissão `OS_COMP.VER_TODAS`** ("Ver todas as O.S.") —
     quem não tem, só vê O.S. onde é técnico responsável OU auxiliar
     (restrição aplicada no backend, `_list_os_sync`, opt-in: só ativa
     quando o chamador manda `classe`+`usuario_codigo`, então
     `os.tsx`/`os-form.tsx` continuam sem restrição nenhuma). Testado
     ao vivo: usuário-técnico da OS 294 (código 20) via 49 O.S. via
     restrição; um código inexistente via 0; master vê tudo.
   - Novos filtros Técnico/Auxiliar (dropdowns).
   - `_list_os_sync` ganhou campos por item: `tecnico_nome`,
     `auxiliar_nome`, `checkin_em`, `checkout_em`, `proxima_agenda`
     (agregado `MIN(AGENDA.data)` via `AGENDA_OS`→`os_produto` — só
     leitura, não muda o modelo de agendamento por item já decidido).
   - Card de linha redesenhado com "pills" em `flexWrap` (responsivo —
     quebra em tela estreita em vez de estourar horizontalmente).
   - Filtros agora dentro de um `AccordionSection` ("Buscar e
     Filtrar", `defaultExpanded`) — pedido explícito do usuário, "para
     economizar espaço" (mesmo componente já usado no Painel de
     Pedidos).
   - Ícone por linha abre um modal leve listando os equipamentos da OS
     + histórico sob demanda — reaproveita só endpoints já existentes
     (`GET /api/os-completo/{codigo}/equipamentos` +
     `GET /api/equipamentos/{codigo}/historico-os`), nenhum endpoint
     novo.
   - FAB "Novo" continua só no web (criar OS é ação de retaguarda).

**Testes**: 12 novos em `test_os_lista.py` (filtros + restrição de
visibilidade) + 6 novos em `test_os_completo_service.py` (auxiliar_tecnico
get/save/migração) — suíte inteira (1850 testes) sem regressão (só a
falha pré-existente de CNAB Itaú). `tsc --noEmit`: baseline de 12 erros
preservado em toda a rodada.

**Não testado nesta rodada**: câmera/GPS reais (mesma limitação da seção
6); a permissão `OS_COMP.VER_TODAS` só foi testada na variante SEM a
permissão ao vivo (a variante COM já está coberta por teste unitário,
`test_com_ver_todas_nao_restringe`) — não achei necessário conceder essa
permissão de verdade pra um classe de teste só pra confirmar algo que já
é lógica SQL pura já coberta.

### Indicador de "atendimento parado" (2026-08-14, mesmo dia — análise Gauntlet)

Encontrado numa análise estruturada da entrega acima (papel "Carlos" do
Protocolo Gauntlet — ver `feedback_gauntlet_multiagent_protocol` na
memória): a lista mostrava check-in/check-out, mas não sinalizava um
técnico em campo há tempo demais sem finalizar. Implementado em
`os-lista.tsx`:

- Relógio único compartilhado (`nowMs`, tick 10s, mesmo padrão de
  `app/pedidos.tsx` — nunca 1 `setInterval` por linha).
- Pill de check-in fica vermelha ("Em campo há Xh") quando há check-in
  sem check-out há mais de `CHECKIN_STALE_MS` (2h, constante ajustável).
- **Diferença deliberada do precedente em `pedidos.tsx`**: o Painel de
  Pedidos removeu o vermelho sólido de "parado" em 2026-08-11 porque
  sobrescrevia a cor da coluna (Mesa/Comanda/etc.) — aqui não existe
  esse conflito (a lista de O.S. não tem cor por coluna/tipo), então o
  destaque vermelho na pill foi mantido sem o mesmo problema. Só sinal
  visual — não reordena a lista (diferente do Painel de Pedidos, que
  também empurra pedidos parados pro fim da coluna).
- Testado ao vivo (checkin sem checkout na OS #293, ARGEN-TESTE) — o
  caminho não-parado (checkin recente) confirmado renderizando
  corretamente; o caminho "parado" (>2h) é aritmética de data direta, não
  testado esperando 2h de verdade, mas mesma lógica já validada no
  Painel de Pedidos.

### Ferramenta de conformidade LGPD — remover coordenadas de GPS (2026-08-14, mesmo dia)

Item 2 da análise Gauntlet (papel Leandro) — **não é uma política de
retenção automática** (isso continua em aberto, decisão de negócio real
que não foi tomada, não presumida). É uma **ferramenta manual** que dá ao
sistema a capacidade de atender um pedido de exclusão de dado de
geolocalização (LGPD), sem precisar decidir de antemão prazo/retenção.

- **Backend**: `POST /api/os/{codigo}/limpar-localizacao`
  (`os_service._limpar_localizacao_sync`) — zera `checkin_lat`/
  `checkin_lng`/`checkout_lat`/`checkout_lng`, **mantém os horários**
  (`checkin_em`/`checkout_em`/`*_usuario` intactos — o "quando e quem" é
  registro de auditoria da OS, diferente do "onde exatamente", que é o
  dado pessoal sensível). Ação irreversível, disparada manualmente,
  **nunca por job agendado**.
- **Permissão própria** `OS_COMP.LIMPAR_GEO` ("Remover localização de
  check-in/check-out (LGPD)") — não amarrada a `GRAVAR`, checada no
  backend (reforço, não só frontend, mesmo princípio de `_fechar_os_sync`).
  Log de auditoria (`comando="LIMPAR_GEO"`).
- **Frontend**: botão "Remover coordenadas de GPS (LGPD)" no card de
  Check-in/Check-out da O.S. Completa (`os-geral.tsx`), só aparece quando
  há de fato lat/lng gravado e o usuário tem a permissão; confirmação via
  `useFeedback().showConfirm` (`destructive: true`) explicando a
  consequência antes de agir.
- 4 testes novos (`test_os_checkin.py::TestLimparLocalizacao` — não
  encontrada, sem permissão bloqueia, com permissão limpa, master
  bypassa). Testado ao vivo contra ARGEN-TESTE (OS #294): bloqueio sem
  permissão confirmado, limpeza via master confirmada (lat/lng viraram
  `null`, horários preservados).
- **Não resolvido, de propósito**: a política de retenção em si (por
  quanto tempo guardar, se deve haver expurgo automático) continua sendo
  uma decisão de negócio real, não inventada nesta rodada — esta
  ferramenta só torna possível cumprir uma solicitação pontual de
  exclusão, não decide uma regra geral.

### Índices — risco de performance do item 3 (2026-08-14, mesmo dia)

Item 3 da análise Gauntlet (papel Thomé). Diagnóstico ao vivo contra
ARGEN-TESTE (`sys.indexes`/`sys.index_columns`) confirmou: `os_produto.os`,
`AGENDA_OS.CODOS`/`CODAGENDA` e `os.tecnico_responsavel` (todas colunas
legadas) **já tinham índice** — a subquery de `proxima_agenda` não era o
problema real. O problema real, achado no mesmo diagnóstico: **3 colunas
criadas por este projeto (não legado) nunca tiveram índice** —
`os.auxiliar_tecnico` (criada nesta sessão) e `os_equipamento.os`/
`os_equipamento.equipamento` (tabela criada na sessão de 13/08, nunca
indexada desde então) — todas usadas em `WHERE`/`JOIN` toda vez que a
O.S. Completa, a tela de Atendimento, ou a Lista de Atendimento carregam.

- **3 índices novos**, cada um na mesma migração que já é dona da
  coluna/tabela (não uma função separada):
  - `IX_os_auxiliar_tecnico` — em `_ensure_os_auxiliar_tecnico_col`
    (`os_completo_service.py`), junto com a criação da própria coluna.
  - `IX_os_equipamento_os` / `IX_os_equipamento_equipamento` — em
    `_ensure_os_equipamento_table` (`os_equipamento_service.py`), depois
    do `CREATE TABLE`/backfill.
- Mesmo padrão `IF NOT EXISTS` idempotente já usado em toda migração de
  coluna/tabela do projeto, só trocando `sys.columns`/`sys.tables` por
  `sys.indexes`.
- **Confirmado ao vivo**: diagnóstico rodado ANTES (achou as 3 colunas
  sem índice) e DEPOIS de reiniciar o backend contra ARGEN-TESTE (as 3
  aparecem criadas, `IX_os_auxiliar_tecnico`/`IX_os_equipamento_os`/
  `IX_os_equipamento_equipamento`).
- Testes de migração existentes (`test_cria_tabela_e_faz_backfill`,
  `TestEnsureAuxiliarTecnicoCol`) atualizados pra cobrir as novas
  queries. Suíte inteira sem regressão.
