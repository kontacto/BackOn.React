# Módulo: Web Convidado

Status: EM ANÁLISE (não implementar até liberação explícita)

## 1. Visão geral

Tela de consulta de listagem de produtos para clientes avulsos, não
cadastrados no sistema — acesso via QR Code, estilo "Olá Click".

**Correção importante (2026-07-30, regra 20, seção 3)**: "cardápio" é só
o rótulo/apresentação quando o módulo **Bar** está ativo na empresa — sem
Bar ativo, é uma apresentação genérica "Listagem de Produtos Web" (mesmos
dados, sem a linguagem/estilo de restaurante). O termo "cardápio" usado
no resto deste documento (herdado da referência visual original, um
bar/restaurante) deve ser lido como "cardápio OU listagem genérica,
dependendo do módulo Bar" — não reescrito em massa neste arquivo, mas a
regra 20 é quem manda em caso de conflito de leitura.

**Referência visual (screenshot fornecido em 2026-07-11)**: cardápio
digital de terceiro ("BAIXO BRISA BISTRÔ") — abas de categoria no topo
(Destaques, Pratos Executivos, Petiscos, Pratos Típicos, Pratos Grelhados,
Frutos do Mar, Caldos, Sobremesas, Drinks, Bebidas, Cervejas, Doses),
cards de produto com foto + nome + descrição + preço, agrupados por seção
na página (título da seção = categoria). Registrado aqui como referência
de estilo/organização visual — **confirmado (2026-07-11): os elementos de
e-commerce dessa referência** (ícone de carrinho, "Pedido mínimo R$
30,00", tempo de entrega) **são escopo futuro do módulo**, não da fase
atual — só o layout de abas de categoria + cards de produto é referência
válida pra agora.

## 2. Contexto de uso

O cliente entra em um estabelecimento (bar/restaurante) que usa o sistema,
recebe um QR Code (impresso na mesa, no cardápio físico ou entregue pelo
atendente) e, ao escanear, acessa uma versão web do cardápio sem precisar
de cadastro/login tradicional.

## 3. Regras de negócio

1. O acesso a essa tela é liberado através da mesma tela de
   conexão/login que já existe hoje no sistema, mas com uma flag "Web
   Convidado".
2. ~~Essa flag só fica disponível/liberada quando o módulo de bar estiver
   marcado/ativo na configuração do estabelecimento.~~ **SUPERADA
   (2026-07-11) — ver regra 17.** A liberação não depende mais do módulo
   de Bar especificamente.
3. Os produtos exibidos no cardápio devem estar organizados por grupo
   mercadológico (ex: Pratos, Petiscos, Caldos, Bebidas alcoólicas,
   Bebidas sem álcool, entre outros a definir).
4. Campos do produto exibidos no cardápio: `pecas.codigo_int` (oculto,
   não exibido ao cliente — uso interno), `pecas.descricao`,
   `pecas.aplicação`, `pecas.p_venda` (preço) e foto do produto.
   ⚠️ `pecas.aplicação` ainda não foi confirmado contra o schema real do
   banco — nome de campo citado pelo usuário, precisa ser validado ao
   vivo (INFORMATION_SCHEMA) antes da implementação, seguindo o processo
   já padrão do projeto (CLAUDE.md > "Legacy VB6 Source Reference") — não
   verificado agora porque estamos em fase de análise, sem tocar em
   código/schema.
5. Acesso via QR Code é resolvido inteiramente pelo backend a partir de
   uma conexão especial: só pode existir **uma** conexão marcada como
   "Web Convidado" dentro da tela de Conexões existente. Essa conexão é
   de uso exclusivo do backend (o cliente avulso nunca escolhe/vê uma
   tela de conexão) — quando o QR Code é lido, o endereço acessado já
   lista os produtos agrupados por grupo mercadológico diretamente; o
   backend usa essa conexão fixa para saber em qual servidor/banco
   buscar os dados.
   **Confirmado (2026-07-11): isso implica que cada estabelecimento
   físico precisa da sua própria instalação/deploy do backend** — não há
   um backend compartilhado escolhendo entre múltiplas conexões
   "Web Convidado" de empresas diferentes.
6. Somente produtos com a flag `pecas.Produto_web = true` são exibidos na
   listagem via QR Code — produtos sem essa flag marcada não aparecem no
   cardápio de convidado, mesmo que estejam ativos/disponíveis nas
   demais telas do sistema.
7. Expiração de sessão: a sessão do "Web Convidado" fica ativa enquanto
   houver atividade, expirando somente por inatividade prolongada — limite
   definido em **2 horas** sem atividade.
8. **A princípio não haverá pedido feito pelo cliente convidado.** O
   recurso é somente para visualização da lista de produtos (consulta de
   cardápio). O pedido em si continua sendo feito pelo vendedor (fluxo já
   existente de Pedido de Venda), presumivelmente a partir do que o
   cliente escolheu/comunicou ao ver o cardápio — o Web Convidado não
   cria nem envia pedido nenhum ao sistema nesta fase.
9. **Apresentação dos campos: sem rótulo, só o conteúdo.** Nenhum campo
   exibido no cardápio mostra o nome/label do campo (ex: não aparece
   "Descrição:" nem "Preço:") — só o valor em si, formatado
   visualmente (ex: nome do produto em destaque/negrito, texto da
   aplicação em cor mais discreta, preço em formato monetário, foto ao
   lado). Confirmado pelo screenshot de referência anexado em 2026-07-11
   (card "BOLINHO DE FEIJOADA UND." — título em negrito, descrição em
   texto secundário, preço "R$ 7,00" solto, foto ao lado — mesmo padrão
   visual do "BAIXO BRISA BISTRÔ" já registrado na seção 1).
10. **Estrutura geral da tela (de cima para baixo)**, conforme novo
    screenshot de referência (2026-07-11):
    1. Cabeçalho com 3 imagens coladas lado a lado (banner/faixa de
       fotos). **As três imagens do topo são cadastradas/carregadas no
       próprio cadastro da conexão "Web Convidado"** (upload feito na
       tela de Conexões, associado a essa conexão específica).
    2. Logo do estabelecimento + nome fantasia, logo abaixo do banner.
       **Essas informações (logo e nome fantasia) vêm da tabela
       `controle`** (tabela de configuração do estabelecimento já
       existente no sistema — mesma família de `controle_aux` já usada
       por outras configurações do ERP, ex: `path_gestor_documentos`).
       Nome exato da(s) coluna(s) em `controle` a confirmar contra o
       schema quando a implementação for liberada.
    3. Grupos de produtos (abas de categoria).
    4. Produtos do grupo selecionado, logo abaixo das abas.
    (O screenshot de referência também mostra "Aberto"/status, tempo de
    entrega, pedido mínimo, botão "Informação" e ícones de
    WhatsApp/Instagram/Facebook no cabeçalho — mantendo o que já foi
    decidido antes: esses elementos de e-commerce/contato são escopo
    futuro, não fazem parte da regra 10 nesta fase; a regra 10 cobre só a
    estrutura confirmada — banner, logo+nome fantasia, grupos, produtos.)
11. **A tela deverá ser moderna e intuitiva** — diretriz geral de
    UX/visual pra guiar decisões de design na fase de implementação
    (sem detalhamento técnico ainda).
12. **Layout responsivo**, tanto para computador quanto para smartphone.
13. **Sincronização entre rolagem e aba de grupo selecionada**: ao rolar
    a lista de produtos, a aba do grupo mercadológico ativa (destacada)
    muda automaticamente para acompanhar a seção visível na tela, seguindo
    a sequência de grupos exibida — mesmo comportamento visto no
    screenshot de referência BAIXO BRISA BISTRÔ (rolar de "Destaques" pra
    "Pratos Executivos" destaca a aba correspondente sem precisar clicar
    nela).
    **Comportamento inverso — CONFIRMADO (2026-07-11), diferente do
    BAIXO BRISA BISTRÔ**: clicar numa aba de grupo **filtra a lista pra
    mostrar só os produtos daquele grupo** — não é "rolar até a seção"
    dentro de uma lista contínua com todos os grupos.
    **Mecânica da rolagem contínua entre grupos — CONFIRMADO
    (2026-07-11)**: ao chegar no final da lista de produtos de um grupo,
    se o cliente continuar rolando, a lista passa a mostrar os produtos
    do **próximo** grupo (na sequência de exibição definida) **sem
    remover/esconder os itens do grupo anterior que já estavam
    carregados/visíveis** — comportamento tipo rolagem contínua
    (infinite scroll), até completar a lista do grupo subsequente
    também. Isso confirma que a rolagem SIM acontece dentro de uma lista
    contínua com todos os grupos empilhados em sequência (reforça a 1ª
    metade desta regra) — o ponto de atenção anterior (possível conflito
    com "clicar numa aba filtra a lista pro grupo clicado") **segue não
    totalmente resolvido**: ainda não está claro se o clique-filtra é um
    modo à parte (ex: sai da rolagem contínua e entra numa visão só
    daquele grupo) que depois oferece um caminho de volta pra rolagem
    contínua, ou se as duas descrições precisam ser conciliadas de outra
    forma. Não assumindo — ver seção 6.
    **CONFIRMADO (2026-07-11)**: sim, ao clicar numa aba o cliente sai da
    rolagem contínua entre grupos e entra num modo mostrando só aquele
    grupo. Ainda não confirmado: existe algum caminho de volta pra visão
    com todos os grupos (rolagem contínua), ou uma vez filtrado só se
    navega clicando em outra aba? Ver seção 6.
    **CONFIRMADO (2026-07-11) — fecha o ponto de atenção acima**: as abas
    de grupo **ficam sempre visíveis** (não somem/travam no modo
    filtrado), e a navegação acontece por **rolagem OU clique**, os dois
    sempre disponíveis. A listagem **sempre inicia pelo primeiro grupo da
    sequência** definida (não por uma aba "Destaques"/highlights como no
    BAIXO BRISA BISTRÔ).
14. **Arquitetura completa de configuração de Grupo Mercadológico pro Web
    Convidado — detalhada em 2026-07-11 a partir de screenshot da tela
    REAL já existente** (árvore de Grupo Mercadológico, raiz
    "RESTAURANTE" com nós filho tipo pasta/tag — mesma tela por trás de
    `GET/POST /api/tabelas/grupos-mercadologicos`, já usada também pelo
    seletor `NiveisModal`/Classificação Mercadológica de Produtos e
    Serviços):
    - **Flag "Web"** — cada grupo, na listagem em árvore já existente,
      ganha uma flag chamada **"Web"** (rótulo de UI). **Todo grupo com
      essa flag marcada `true` é exibido no Web Convidado.** Nome da
      coluna no banco já definido antes: **`grupo_web`**.
    - **Botão novo no canto superior direito da mesma tela de listagem**:
      ao clicar, exibe (filtra) só os grupos que têm a flag Web = true.
    - **Nova tela: "Grupos da Web Convidado"** — é o que abre ao clicar
      nesse botão. É aqui que a **sequência de exibição é configurada,
      por arrastar-e-soltar**, entre os grupos já marcados com a flag
      Web. Isso resolve a dúvida antiga sobre "tela nova x tela já
      existente": é **as duas coisas** — a flag "Web" fica na tela já
      existente (Grupo Mercadológico), mas a ordenação por
      arrastar-e-soltar acontece numa tela nova dedicada ("Grupos da Web
      Convidado"), acessada a partir da primeira.
    - **Nova tabela a criar: `gruposweb`** — armazena os grupos que serão
      exibidos, na sequência configurada na tela "Grupos da Web
      Convidado".
    **Relação entre a flag e a tabela — CONFIRMADO (2026-07-11)**:
    `niveis.grupo_web` é quem decide de verdade SE o grupo aparece (fonte
    da verdade de visibilidade); `gruposweb` é **só a tabela de
    sequência**, sincronizada automaticamente — marcar a flag `true`
    adiciona o grupo na tabela `gruposweb` (presumivelmente ao final da
    sequência atual), desmarcar remove. `gruposweb` nunca é editada
    diretamente fora dessa sincronização automática, exceto pela própria
    reordenação por arrastar-e-soltar (que só reordena os grupos já
    presentes, não adiciona/remove nenhum).
    **Colunas de `gruposweb` DEFINIDAS (2026-07-11)**: código do grupo +
    sequência (nomes de rótulo, mapeamento exato pra nome de coluna SQL
    fica pra fase de implementação).
    **Nível da árvore — FECHADA (2026-07-30)**: "código do grupo" em
    `gruposweb` sempre se refere ao **último nível** (nó folha) da árvore
    de Grupo Mercadológico — nunca um nó intermediário/pasta de nível
    superior. Ou seja, cada aba do Web Convidado corresponde a uma
    categoria "final" da árvore, não a um agrupamento de nível mais alto
    que ainda teria subcategorias por baixo.
15. **Geração automática de QR Code na tela de Conexões.** Quando a
    conexão "Web Convidado" for criada, o sistema deve gerar o QR Code
    correspondente **na mesma tela** (Conexões), sem passo manual
    separado. Esse QR Code pode ser **capturado (print/screenshot) ou
    exportado pra um arquivo** sempre que for necessário — ou seja,
    precisa ficar disponível/visível de forma persistente na tela da
    conexão (não só no momento da criação), e com alguma ação explícita
    de exportar (baixar como imagem/arquivo).
16. **[GLOBAL] O carregamento (upload) das imagens dos produtos será
    feito pelo Cadastro de Produtos — uma tela que ainda será construída
    em breve, fora deste módulo.** O Web Convidado **não terá mecanismo
    próprio de upload de foto** — ele só consome/exibe a foto que já
    estiver disponível pra aquele produto (reaproveitando
    `GET /api/produtos/foto/{codigo}`, já decidido na regra sobre foto
    acima). Isso cria uma **dependência entre módulos**: hoje o sistema
    ainda não tem NENHUMA tela de upload de foto de produto (confirmado
    em CLAUDE.md — infraestrutura de leitura já existe, mas não de
    escrita/upload) — então, na prática, o Web Convidado só vai
    conseguir mostrar fotos de produtos depois que o Cadastro de Produtos
    (com upload) for implementado, ainda que os dois módulos sejam
    trabalhos separados.
17. **Nova flag "Convidado Web" na tela de Módulos do Sistema —
    SUPERSEDE a regra 2.** A liberação do recurso "Web Convidado" deixa
    de depender do módulo de Bar estar marcado — passa a ter sua própria
    flag dedicada, **"Convidado Web"**, na configuração de módulos do
    sistema (mesmo mecanismo já usado por outras flags de módulo do
    projeto, ex.: `moduleOn("Cilindro")`, `moduleOn("emite_mdfe")`,
    `moduleOn("servicos")`). Isso libera o recurso pra **qualquer tipo de
    cliente/estabelecimento**, não só quem usa o módulo Bar. **Nome do
    campo: `convidado_web`.** O usuário reforçou explicitamente que esse
    campo **precisa ser persistido** (coluna real no banco, não
    calculado/derivado) — mesmo padrão de persistência já exigido pra
    `grupo_web`/`gruposweb`.
    **Motivo do escopo global — CONFIRMADO (2026-07-30)**: "esse é um
    módulo global. Não só do bar. Pois futuramente terá checkout." —
    o módulo não é pensado como uma feature exclusiva do segmento
    Bar/restaurante; é um catálogo/vitrine genérico que **qualquer**
    segmento de negócio pode usar, e a justificativa explícita é que o
    checkout (carrinho/compra, já citado como escopo futuro na seção 6)
    vai se aplicar a esse universo mais amplo, não só a comanda de
    bar/mesa. Reforça — não substitui — a regra 17 original.
    **Tabela de persistência — resposta do usuário (2026-07-30)**: "Por
    enquanto somente exibição" — o usuário não fechou o nome exato da
    tabela; o contexto da resposta é que essa é uma decisão de baixo risco
    pra adiar, já que hoje o módulo inteiro é só leitura/exibição (ver
    regra 18) — mesmo padrão de outras dúvidas técnicas já adiadas pra
    fase de implementação nesta doc (ex.: `cod_grupo`/`cod_sub_grupo` do
    Gestor de Documentos).
    **Mecanismo de liberação (crivo) — CONFIRMADO (2026-07-30)**: "O
    crivo é feito via configurações de módulos. Lá teremos Web Convidado.
    Essa flag habilitada, é liberado esse recurso para o cliente." —
    fecha a parte de ARQUITETURA da dúvida: `convidado_web` é mais um
    item na tela **Módulos e Recursos** já existente (mesma lista de
    `moduleOn("Cilindro")`/`moduleOn("servicos")`/etc. citada acima — no
    código atual, essas flags moram em `controle_configuracao`, mas isso
    ainda não foi confirmado literalmente pelo usuário pra esse campo
    específico), com um item "Web Convidado" na listagem de módulos que,
    marcado, libera o recurso pro cliente. **Só o nome exato da
    tabela/coluna no schema segue em aberto** (detalhe de implementação,
    ver seção 6) — a arquitetura do crivo (tela + flag booleana, mesmo
    padrão dos outros módulos) está fechada.
18. **[GLOBAL, NOVO] Web Convidado é somente-leitura — toda configuração é
    feita no app principal (ERP), nunca no próprio Web Convidado —
    CONFIRMADO (2026-07-30).** Respondendo à dúvida sobre o formato de
    `gestor_documentos.referencia_texto`, o usuário esclareceu: "Configuração
    é toda feita no app. Web convidado somente exibição." Isso não é só
    sobre essa coluna específica — é um princípio geral de arquitetura do
    módulo inteiro: `grupo_web`/`gruposweb` (regra 14), a foto/`referencia_texto`
    do produto no Gestor de Documentos, e (por ora) `convidado_web` — tudo
    isso é escrito/gerenciado pelas telas já existentes do ERP principal;
    o Web Convidado nunca grava nada nessas tabelas, só lê o que já foi
    configurado. Reforça a regra 8 (não há pedido feito pelo convidado) —
    agora generalizado pra "nenhuma escrita de nenhum tipo", não só
    ausência de pedido. Isso também implica que o Web Convidado, quando
    implementado, não precisa entender/validar o FORMATO de
    `referencia_texto` (ex.: se é `P`+`codigo_int` ou outra convenção) —
    só precisa ler o valor já gravado pelo Gestor de Documentos e usá-lo
    como veio, sem nenhuma lógica própria de geração/parsing.
19. **[NOVO] O preço exibido deve considerar os recursos de configuração
    de preço já existentes no Cadastro de Produtos — CONFIRMADO
    (2026-07-30)**: "os recursos de configuração de preço, também deve
    ser contemplado na visualização do Web Convidado." Ou seja, o
    cardápio não pode simplesmente mostrar `pecas.p_venda` cru — precisa
    levar em conta as regras de precificação que já existem no sistema:
    **Preço por Quantidade** (`pecas_preco_qtd`) e **Variações de Preços/
    Promoção** (`pecas_promocao`, incluindo o período opcional dias da
    semana/data/hora já implementado — ver CLAUDE.md > "Produto
    Completo").
    **Sem carrinho — CONFIRMADO (2026-07-30)**: "O preço exibido... levará
    em conta as configurações de Preço por Quantidade/Promoção. Não
    haverá na primeira etapa carrinho de compra. Somente exibição." —
    ou seja, como o cliente não escolhe quantidade nesta fase, não existe
    "quantidade selecionada" pra escalonar o Preço por Quantidade contra
    — o preço mostrado é resolvido sem depender de uma quantidade
    escolhida pelo cliente (presumivelmente a faixa de menor quantidade/
    qtd=1, já que é o preço-base do produto, mas o mecanismo exato de
    qual faixa mostrar quando há mais de uma cadastrada **ainda não foi
    detalhado literalmente** — fica pra fase de implementação, sem
    assumir). Promoção (dia/data/hora) já não depende de quantidade
    escolhida pelo cliente do mesmo jeito, então essa parte é direta:
    aplica quando o momento do acesso cai dentro do período configurado.
    **Produto m² (Metro Quadrado) — RESPONDIDO, exclusão por produto, não
    por empresa (2026-07-30)**: "produto m² precisa de um especialista
    para compor o preço final. Mas não impede dos outros produtos dessa
    empresa entrar na exibição do Web Convidado." Fecha a dúvida: produto
    m² fica de fora da precificação automática do cardápio (não tem preço
    "pronto" sem dimensão informada por um humano) — mas isso NÃO exclui
    a empresa inteira do módulo, só aquele(s) produto(s) específico(s).
    **Aparição na listagem — FECHADA (2026-07-30)**: "todos os Produtos
    Web aparecem na listagem." Ou seja, produto m² com `Produto_web=true`
    aparece normalmente no cardápio (mesmo critério de qualquer outro
    produto, regra 6) — a exclusão da regra acima é só do cálculo de
    área/preço final, nunca da listagem em si.
    **Preço exibido pra produto m² — FECHADA (2026-07-30)**: "aparece o
    preço de venda" — ou seja, `pecas.p_venda` (o preço-base cadastrado,
    o mesmo lido pra qualquer produto normal), sem calcular nenhuma área.
    Não há mais nenhuma exceção especial pra m² na exibição: o produto
    aparece na listagem (regra acima) com o preço de venda cadastrado
    (esta regra) — trata-se do mesmo campo já definido na regra 4
    (`p_venda`), sem lógica adicional. **Justificativa do usuário**: "pois
    a descrição do produto já vai informar que é m2" — não precisa de
    nenhum indicador/badge visual extra (tipo "por m²") no cardápio, já
    que a própria descrição cadastrada do produto (regra 4) já deixa isso
    claro pro cliente. Fecha por completo a regra 19 — nenhuma dúvida
    residual sobre precificação m² no Web Convidado.
20. **[NOVO] "Cardápio" só é o rótulo/apresentação quando o módulo Bar
    está ativo — CORREÇÃO IMPORTANTE (2026-07-30)**: o usuário corrigiu um
    texto de ajuda do app (Modo Didático, Cadastro de Produtos) que dizia
    "aparecer no cardápio do Web Convidado" — errado, porque presume Bar
    sempre ativo. **Regra real**: "A listagem de produtos Web, só é
    cardápio se o módulo bar estiver ativo, caso contrário é uma listagem
    de Produtos Web." Ou seja, a apresentação do Web Convidado tem DOIS
    modos, decididos pelo módulo Bar (`controle_configuracao.Bar`, já
    existente e independente da flag `convidado_web` — reforça a regra 17,
    "módulo global, não só do bar"):
    - **Bar ativo**: apresentação estilo "cardápio" (a referência visual
      BAIXO BRISA BISTRÔ da seção 1 — abas de categoria, cards com foto/
      nome/descrição/preço, linguagem de restaurante/bar).
    - **Bar inativo**: apresentação genérica "Listagem de Produtos Web" —
      mesmos dados (produtos, grupos, preço), mas sem a apresentação/
      linguagem de cardápio de restaurante (empresas de outros ramos —
      ex.: loja, oficina — também podem ativar `convidado_web` sem serem
      um bar/restaurante, coerente com o motivo do escopo global já
      registrado na regra 17: futuro checkout pra qualquer segmento).
    **Correção já aplicada no app**: o texto de ajuda (Modo Didático) do
    Cadastro de Produtos foi corrigido pra "'Produto Web' libera este
    produto para aparecer na listagem Web para convidados" — texto
    genérico, sem presumir "cardápio". **Esta regra 20 é só o registro de
    negócio pra fase de implementação do Web Convidado em si** — nenhuma
    tela nova foi construída agora, só o texto de ajuda do Cadastro de
    Produtos (que já existe) foi ajustado pra não prometer algo que só é
    verdade condicionalmente.

## 4. Grupos mercadológicos / dados envolvidos

Exemplos de grupos mercadológicos citados:
- Pratos
- Petiscos
- Caldos
- Bebidas alcoólicas
- Bebidas sem álcool
- (lista em aberto — outros grupos podem ser adicionados dinamicamente
  pelo banco)

**Configuração por grupo mercadológico** (ver regra 14 na seção 3):
flag `niveis.grupo_web` (rótulo de UI "Web", marca se o grupo aparece no
Web Convidado) + nova tabela `gruposweb` (grupos + sequência de exibição,
configurada por arrastar-e-soltar na tela nova "Grupos da Web Convidado").
Ambos ainda precisam ser criados no banco.

**Dados do produto exibidos** (ver regra 4 na seção 3): `codigo_int`
(oculto), `descricao`, `aplicação` (⚠️ nome a confirmar contra o schema),
`p_venda`, foto. Filtro adicional (regra 6): só entram na lista produtos
com `pecas.Produto_web = true`.

**Foto do produto — DECISÃO FECHADA (revisada 2026-07-11)**: as fotos dos
produtos passam a ser gravadas **no mesmo path/mecanismo já usado pelo
Gestor de Documentos** (`controle_aux.path_gestor_documentos`, local ou
Azure Blob, configurado por banco/conexão) — **substitui** a decisão
anterior de reaproveitar `FOTOS_PRODUTOS_DIR` (variável de ambiente
fixa/global), que fica superada. Confirma a recomendação que havia sido
registrada em avaliação na rodada 22.
**"Todas as regras serão passadas pela forma como o gestor trabalha"**
(instrução literal do usuário, 2026-07-11): não é só o path que muda —
**todo o mecanismo de armazenamento das fotos de produto passa a seguir o
funcionamento do Gestor de Documentos** (dual local/Azure Blob conforme a
configuração da conexão, mesma lógica de resolução de caminho já usada
por `GestorDocumentosSection`/`controle_aux`), não só o campo de path
isolado. **Upload da foto continua sendo responsabilidade do futuro
Cadastro de Produtos (regra 16)** — o Web Convidado só consome/exibe,
nunca faz upload — mas agora tanto o upload (Cadastro de Produtos) quanto
a leitura (`GET /api/produtos/foto/{codigo}` ou equivalente, e o consumo
pelo Web Convidado) precisam apontar pro mesmo mecanismo do Gestor de
Documentos.

**CONFIRMADO (2026-07-11) — fecha a dúvida de arquitetura acima**: a
imagem do produto **não é um mecanismo à parte** — ela é gravada como um
registro normal, direto na própria tabela `gestor_documentos` (mesmo
fluxo de qualquer outro anexo gerenciado pelo Gestor de Documentos), não
um path solto fora do Gestor. Confirmado por print de uma linha real já
gravada na tabela:

| codigo | cod_grupo | cod_sub_grupo | path | descricao | path_origem | adicionado_por | data | hora | referencia_texto | referencia_codigo | referencia | computador(?) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3521 | 4 | 11 | H:\SQLSERVER\Docu... | IMAGEM | C:\Users\leandro.KONTA... | KONTACTO | 2026-07-11 | 15:10:05 | P10324 | 0 | 0 | DESE...(?) |

⚠️ Nomes de coluna confirmados visualmente pelo print (`codigo`,
`cod_grupo`, `cod_sub_grupo`, `path`, `descricao`, `path_origem`,
`adicionado_por`, `data`, `hora`, `referencia_texto`, `referencia_codigo`,
`referencia`) — a última coluna do print aparece cortada
("comput...", presumivelmente `computador`), não conferida por completo.
Ainda não confirmado/assumido: quais `cod_grupo`/`cod_sub_grupo`
exatos são reservados pra "Produto - Imagem" dentro do catálogo já
existente de grupos do Gestor de Documentos (`GESTOR_DOC_GRUPO_*`), e o
formato/significado exato de `referencia_texto` (no exemplo aparece
`P10324` — hipótese não confirmada: prefixo `P` + `codigo_int` do
produto, usado pra depois buscar a foto daquele produto especificamente)
— ver seção 6.

**Segundo mecanismo — "Produto de Grade" (2026-07-11, REVISADO)**: o
usuário esclareceu inicialmente que existe um fluxo separado pra imagem
de "produto de grade" (produto com variações/matriz — ex.: tamanho/cor),
com tela dedicada, usando Azure Blob — mas **detalhou/corrigiu em
seguida (mesmo dia) que NÃO é um destino/mecanismo totalmente à parte**:
quando é "grade", a imagem adicionada **vai pra mesma pasta de imagens
do sistema que qualquer outra** (mesmo `path` local, mesma estrutura de
pastas já documentada acima) — a única diferença é que **também** faz
upload pro Blob e grava a **URL resultante numa coluna própria da
própria tabela `gestor_documentos`**, chamada **`PATH_NUVEM`** (existência
confirmada por print de uma consulta real: coluna aparece com valor
`NULL` em todas as linhas de exemplo já vistas, porque nenhuma delas
passou pelo fluxo de upload pro Blob). Ou seja: **um único
registro/mecanismo** (`gestor_documentos`), com um campo opcional
(`PATH_NUVEM`) que só é preenchido quando o item passa pelo upload pro
Blob — não dois sistemas de armazenamento paralelos. **As funções desse
fluxo (upload pro Blob) estão numa DLL VB.NET** (mesma camada de negócio
já referenciada em CLAUDE.md > "Legacy VB6 Source Reference" —
`C:\Desenv\VB6\vb.net\APICamadas\BackOn`) — não rastreado agora (fase de
análise, sem tocar em código/schema).
✅ **Isso resolve parte da dúvida anterior**: o Web Convidado não precisa
de um fluxo "diferente" pro consumo via URL — ele consulta a mesma tabela
`gestor_documentos` e usa `PATH_NUVEM` quando disponível (URL pronta pra
uso direto no site) ou cai pro `path` local caso contrário. **Ainda em
aberto** (ver seção 6): pra fotos de produto aparecerem no Web Convidado
com URL utilizável, o upload pro Blob (preenchimento de `PATH_NUVEM`)
precisa acontecer **sempre** que uma foto de produto é adicionada (não só
quando é "produto de grade"), ou o Web Convidado vai ter que lidar com
casos em que só existe `path` local (sem URL pública)? Isso depende de
como o futuro Cadastro de Produtos vai implementar o upload — não
assumido agora.

**Convenção de nome de arquivo — SEM RESTRIÇÃO (2026-07-11)**: o usuário
esclareceu que o nome do arquivo gravado (`código - descrição`, visto nos
exemplos de `path`) é só a convenção que o sistema legado usa hoje, **não
é uma regra de negócio obrigatória** — o que realmente importa é o valor
gravado na coluna `path`, não o nome do arquivo em si. Ou seja, a futura
implementação pode nomear o arquivo como for mais conveniente
tecnicamente, desde que grave o `path` (e `PATH_NUVEM`, quando aplicável)
corretamente na tabela.

**Estrutura de `path`/`path_origem` no Gestor de Documentos — detalhada
por print (2026-07-11)**: o usuário mostrou várias linhas reais de
`gestor_documentos` confirmando a convenção geral (vale pra qualquer
anexo do Gestor, não só foto de produto):
- `path_origem` = caminho original do arquivo na máquina de quem
  adicionou (ex.: `C:\Users\leandro.KONTACTO\Downloads\WhatsApp Image
  ....jpg`, `C:\Users\leandro.KONTACTO\Desktop\IDENTIDDADE.jpg`) — só
  informativo/auditoria, não é de onde o arquivo é servido depois.
- `path` (destino real, de onde o arquivo é servido) segue o padrão
  `<raiz>\<Grupo>\<SubGrupo/contexto>\<referência> - <nome do arquivo>`,
  onde `<raiz>` é a base configurada (`H:\SQLSERVER\Documentos` no
  exemplo, presumivelmente = `controle_aux.path_gestor_documentos`).
  Exemplos confirmados: `Produtos\Imagens\P10324 - WhatsApp Image...`,
  `Favorecidos\Movimentações\28289 - WhatsApp Image...`,
  `Clientes\Pedidos de Venda\6451 - WhatsApp Image...`,
  `Clientes\Contratos\6451 - WhatsApp Image...`,
  `Clientes\Contratos\6470 - IDENTIDDADE...`,
  `Clientes\Ordens de Serviço\6517 - IDENTIDDADE...`,
  `Clientes\Contratos\6517 - teste_boleto.pdf`. **Reforça (não fecha
  ainda) a dúvida sobre `cod_grupo=4`/`cod_sub_grupo=11`** registrada na
  rodada 25: a pasta de destino da linha de exemplo era
  `Produtos\Imagens`, batendo com a hipótese de que
  `cod_grupo`=Produtos/`cod_sub_grupo`=Imagens — ainda não confirmado
  formalmente contra o catálogo `GESTOR_DOC_GRUPO_*`.
- **A rotina que adiciona o arquivo cria a pasta de destino
  automaticamente, caso ela ainda não exista** — não é preciso
  pré-criar a estrutura de pastas manualmente.

**Árvore de pastas confirmada por print (2026-07-11)** — o usuário
mostrou a árvore real já criada em disco pela própria função de
adicionar arquivo (reforça o ponto acima: essa estrutura inteira é
gerada automaticamente, não montada manualmente):

```
Documentos
├── Clientes
│   ├── Contratos
│   ├── Ordens de Serviço
│   └── Pedidos de Venda
├── Favorecidos
│   └── Movimentações
└── Produtos
    └── Imagens
```

Isso **confirma a nível de negócio** (ainda não a nível de código/schema)
que `Produtos\Imagens` é a pasta de destino usada pra foto de produto —
condizente com o exemplo `cod_grupo=4`/`cod_sub_grupo=11` das rodadas
25/27. Falta só confirmar, na fase de implementação, os valores exatos
desses códigos contra o catálogo `GESTOR_DOC_GRUPO_*` no código.

## 5. Integração com o sistema existente

- Reaproveita a tela de conexão atual do ERP (não é uma tela de login
  nova/paralela) — mas não como uma opção que o cliente avulso escolhe;
  ver abaixo.
- ~~Depende da configuração do módulo de bar estar ativa no
  estabelecimento para a flag "Web Convidado" aparecer/funcionar.~~
  **SUPERADA (2026-07-11) — ver regra 17.** A liberação passa a depender
  de uma flag de módulo própria e independente, **"Convidado Web"**
  (campo persistido `convidado_web`), disponível pra qualquer
  cliente/estabelecimento, não só quem usa o módulo Bar.
- **Mecanismo de resolução via QR Code (detalhado 2026-07-11)**: existe
  no máximo **uma** conexão, dentro da tela de Conexões já existente,
  marcada com a flag "Web Convidado". Essa conexão é de uso exclusivo do
  **backend** — não é uma opção selecionável pelo cliente avulso. O QR
  Code aponta direto para o endereço que já lista os produtos por grupo
  mercadológico; o backend, ao receber essa chamada de convidado, usa a
  conexão marcada como "Web Convidado" pra saber automaticamente em qual
  servidor/banco buscar os dados — o cliente nunca vê/interage com a tela
  de conexão.
- **Confirmado**: cada estabelecimento físico precisa da própria
  instalação/deploy do backend — a regra "só 1 conexão Web Convidado" é
  por instalação, não há backend compartilhado entre estabelecimentos
  diferentes pra esse módulo.
- **Geração de QR Code (regra 15, seção 3)**: ao criar a conexão "Web
  Convidado" na tela de Conexões, o sistema gera automaticamente o QR
  Code correspondente, exibido na própria tela — disponível pra captura
  (print) ou exportação em arquivo sempre que necessário, não só no
  momento da criação.

## 6. Dúvidas em aberto

- ~~Nível hierárquico ao qual `grupo_web`/`gruposweb` se aplica~~ —
  **FECHADA (2026-07-30)**: sempre o último nível (nó folha) da árvore de
  Grupo Mercadológico. Ver regra 14, seção 3.
- Confirmar o nome exato do campo `aplicação` no banco (`pecas.aplicação`
  foi citado, mas ainda não conferido ao vivo) — e confirmar também
  `pecas.Produto_web` (nome/tipo exatos da flag da regra 6) e a(s)
  coluna(s) exata(s) de logo/nome fantasia em `controle` (regra 10.2).
- ~~Em qual tabela exatamente o novo campo `convidado_web` (regra 17) vai
  ser persistido~~ — **arquitetura FECHADA (2026-07-30)**: mais um item
  booleano na tela **Módulos e Recursos** já existente, mesmo padrão de
  `Cilindro`/`emite_mdfe`/`servicos` — "o crivo é feito via configurações
  de módulos... essa flag habilitada, libera o recurso pro cliente" (ver
  regra 17, seção 3). **Só resta o detalhe técnico**: o nome exato da
  tabela/coluna no schema (presunção é `controle_configuracao`, mesma
  tabela das outras flags de módulo já citadas, mas isso ainda não foi
  confirmado literalmente pelo usuário nem contra o schema real) — fica
  pra fase de implementação, não bloqueia mais a análise de negócio.
- **Confirmar `cod_grupo`/`cod_sub_grupo` reservados pra "Produto -
  Imagem" no Gestor de Documentos** — negócio já confirma
  `cod_grupo=4`/`cod_sub_grupo=11` = Produtos/Imagens (reforçado por
  print com destaque em 2026-07-11), falta só bater esses números contra
  o catálogo `GESTOR_DOC_GRUPO_*` no código na fase de implementação
  (detalhe técnico, não bloqueia mais a análise de negócio).
- ~~Confirmar formato/significado de `gestor_documentos.referencia_texto`~~
  — **FECHADA na prática (2026-07-30)**: não é o Web Convidado que gera
  ou precisa interpretar esse valor — "Configuração é toda feita no app.
  Web convidado somente exibição." (ver regra 18, seção 3). O módulo só
  lê o que o Gestor de Documentos já gravou, sem lógica própria de
  parsing/geração — o formato exato (`P`+`codigo_int` ou outra convenção)
  vira um detalhe interno do Gestor de Documentos, irrelevante pra esta
  implementação. Ainda não confirmado, mas também não bloqueia mais nada
  aqui: o nome completo da última coluna do print que aparece cortada
  ("comput...", presumivelmente `computador`).
- **[GLOBAL] Preenchimento de `PATH_NUVEM` (upload pro Blob) pra foto de
  produto — ADIADA (2026-07-11)**: já esclarecido que não existe um
  "fluxo grade" separado — é a mesma tabela/registro, só com `PATH_NUVEM`
  preenchido quando passa por upload pro Blob. Se o upload vai acontecer
  **sempre** que uma foto de produto for cadastrada (garantindo URL
  disponível pro Web Convidado) ou só em certos casos — **o usuário
  decidiu explicitamente adiar essa decisão pro momento em que a tela de
  Cadastro de Produtos for implementada** ("veremos no momento da tela de
  produtos"), não é uma dúvida a resolver na fase de análise do Web
  Convidado. Marcada como [GLOBAL] porque a resposta, quando vier, também
  vai valer pra qualquer outro consumidor de foto de produto, não só o
  Web Convidado. Também segue em aberto (sem urgência): o que é
  exatamente "produto de grade" neste sistema (aplica a produtos de
  bar/restaurante, ou é conceito de outro ramo, ex.: confecção/varejo com
  tamanho/cor)?
- Carrinho/pedido mínimo/tempo de entrega são escopo futuro — **agora
  com nome confirmado: "checkout" (2026-07-30, regra 17)** — mas o
  mecanismo exato segue em aberto: quando esse futuro chegar, isso vai
  significar que o convidado passa a fazer pedido de verdade (criando um
  Pedido de Venda no sistema) ou é algum outro tipo de interação (ex: só
  enviar a lista pro WhatsApp do estabelecimento)? Não precisa responder
  agora — registrando a pergunta pra quando a fase futura for discutida.
  Vale notar que checkout, por definição, é uma escrita de dados — quando
  essa fase chegar, o princípio "somente-leitura" da regra 18 deixa de
  valer pra essa parte específica do fluxo (não pro resto do módulo).
- ~~Como exibir o preço considerando Preço por Quantidade/Promoção~~ —
  **RESPONDIDA em espírito (2026-07-30)**: sem carrinho, não há
  quantidade escolhida pra escalonar (ver regra 19). **Detalhe técnico
  ainda em aberto** (não bloqueia mais a análise de negócio): qual faixa
  de `pecas_preco_qtd` exibir quando o produto tem mais de uma cadastrada
  — a de menor quantidade (qtd=1, o preço-base), ou outra lógica? Fica
  pra fase de implementação. Promoção com restrição de dia/hora segue
  direta: aplica quando o momento do acesso cai dentro da janela
  configurada (recalculado a cada carregamento da página) — isso não foi
  contestado pelo usuário.
- ~~Produto m² entra na regra 19?~~ — **FECHADA POR COMPLETO (2026-07-30)**:
  aparece normalmente na listagem (mesmo critério de qualquer produto
  Web) e exibe `pecas.p_venda` (preço-base cadastrado), sem calcular
  nenhuma área nem precisar de indicador visual extra — a descrição do
  produto já deixa claro que é m². Nenhuma dúvida residual.

## 7. Decisões já confirmadas

- O acesso é via QR Code, sem cadastro do cliente.
- ~~A liberação da flag "Web Convidado" depende do módulo de bar estar
  marcado.~~ **SUPERADA (2026-07-11)**.
- **Nova flag de módulo "Convidado Web" — DECISÃO FECHADA (regra 17,
  seção 3)**: liberação do recurso passa a ser controlada por uma flag
  própria e independente na tela de Módulos do Sistema (mesmo mecanismo
  já usado por `Cilindro`/`emite_mdfe`/`servicos`), disponível pra
  qualquer cliente/estabelecimento — não fica mais exclusiva do módulo
  Bar. Campo **`convidado_web`**, obrigatoriamente persistido (coluna
  real no banco).
- Reaproveita a tela de conexão existente (não cria fluxo de
  autenticação novo) — mas o cliente avulso nunca vê essa tela; é usada
  internamente pelo backend via uma conexão fixa marcada "Web Convidado"
  (só pode existir uma).
- Cardápio exibe, por produto: descrição, aplicação, preço (`p_venda`) e
  foto — código interno (`codigo_int`) fica oculto do cliente.
- Por enquanto (fase inicial), a tela mostra somente produtos — sem
  dados do estabelecimento (endereço, horário, formas de pagamento) —
  outros recursos ficam para fases futuras do projeto.
- Só produtos com `pecas.Produto_web = true` aparecem no cardápio de
  convidado.
- Cada estabelecimento físico precisa da própria instalação/deploy do
  backend (decorrência da regra "só 1 conexão Web Convidado" por
  instalação).
- **Foto do produto — DECISÃO FECHADA, revisada 2026-07-11**: gravada no
  mesmo path/mecanismo já usado pelo Gestor de Documentos
  (`controle_aux.path_gestor_documentos`, local ou Azure Blob, por
  banco/conexão) — substitui a decisão anterior de usar
  `FOTOS_PRODUTOS_DIR` (fixo/global). Por instrução explícita do usuário,
  todo o mecanismo de armazenamento (não só o path) passa a seguir o
  funcionamento do Gestor de Documentos.
- **Mecanismo confirmado por print real (2026-07-11)**: a foto do produto
  não é um caso especial — vira um registro comum direto na tabela
  `gestor_documentos` (mesmo fluxo de qualquer anexo do Gestor), colunas
  confirmadas visualmente: `codigo`, `cod_grupo`, `cod_sub_grupo`, `path`,
  `descricao`, `path_origem`, `adicionado_por`, `data`, `hora`,
  `referencia_texto`, `referencia_codigo`, `referencia`. Exemplo real:
  `cod_grupo=4`, `cod_sub_grupo=11`, `descricao=IMAGEM`,
  `referencia_texto=P10324`. Detalhes exatos (quais `cod_grupo`/
  `cod_sub_grupo` são reservados pra produto, formato de
  `referencia_texto`) ainda em aberto — ver seção 6.
- Carrinho, pedido mínimo e tempo de entrega (vistos na referência visual
  BAIXO BRISA BISTRÔ) são escopo futuro do módulo — fora da fase atual,
  que é só consulta de cardápio.
- Identificador de mesa/comanda vinculado ao QR Code também é escopo
  futuro — a fase atual do QR Code é genérica por estabelecimento, sem
  vínculo com mesa específica.
- Expiração de acesso — DECISÃO FECHADA (regra 7, seção 3): sessão fica
  ativa enquanto houver atividade, expira por inatividade prolongada de
  **2 horas**.
- Não há pedido feito pelo cliente convidado (regra 8, seção 3) — o
  recurso é só visualização da lista de produtos; o pedido continua
  sendo feito pelo vendedor, via fluxo já existente.
- Apresentação sem rótulo de campo (regra 9, seção 3) — só o conteúdo
  formatado é exibido (nome em destaque, descrição secundária, preço,
  foto), nunca o nome do campo.
- Estrutura geral da tela — DECISÃO FECHADA (regra 10, seção 3): banner
  de 3 imagens (upload no cadastro da conexão "Web Convidado") → logo +
  nome fantasia (vindos da tabela `controle`) → grupos de produtos →
  produtos do grupo selecionado.
- Diretriz geral de design: tela moderna e intuitiva (regra 11, seção 3).
- Layout responsivo, computador e smartphone (regra 12, seção 3).
- Rolagem da lista sincroniza a aba de grupo ativa (regra 13, seção 3).
- Rolagem entre grupos é contínua (infinite scroll): ao terminar a lista
  de um grupo, rolar mais avança pro próximo grupo sem remover os itens
  do grupo anterior já carregados (regra 13, seção 3).
- Clicar numa aba de grupo filtra a lista pra mostrar só os produtos
  daquele grupo (regra 13, seção 3) — não é "rolar até a seção", e sai
  da rolagem contínua entre grupos.
- Abas de grupo ficam sempre visíveis (nunca somem/travam); navegação é
  por rolagem OU clique, os dois sempre disponíveis; a listagem sempre
  começa pelo primeiro grupo da sequência (regra 13, seção 3).
- Arquitetura de configuração de Grupo Mercadológico pro Web Convidado —
  DECISÃO FECHADA (regra 14, seção 3): flag "Web" (`niveis.grupo_web`) na
  tela já existente de Grupo Mercadológico decide se o grupo aparece
  (fonte da verdade de visibilidade); botão novo no canto superior
  direito dessa mesma tela filtra só os grupos com Web=true; esse botão
  abre uma tela NOVA ("Grupos da Web Convidado") onde a sequência é
  configurada por arrastar-e-soltar; nova tabela `gruposweb` é só a
  sequência, sincronizada automaticamente com a flag (marcar adiciona,
  desmarcar remove) — nunca editada diretamente fora disso, exceto pela
  própria reordenação. Colunas de `gruposweb`: código do grupo +
  sequência.
- QR Code é gerado automaticamente na tela de Conexões ao criar a conexão
  "Web Convidado", disponível pra captura/exportação sempre que necessário
  (regra 15, seção 3).
- **[GLOBAL] Upload de foto de produto é escopo do futuro Cadastro de
  Produtos, não do Web Convidado** (regra 16, seção 3) — o Web Convidado
  só exibe fotos já existentes. **Dependência entre módulos**: sem o
  Cadastro de Produtos (upload) implementado, não há como colocar fotos
  novas no sistema hoje — nenhum dos dois módulos resolve isso sozinho.
- **Módulo é global, não exclusivo de Bar — DECISÃO REFORÇADA (regra 17,
  2026-07-30)**: motivo explícito é o futuro checkout, que vai se aplicar
  a qualquer segmento de negócio, não só comanda de bar/mesa.
- **Mecanismo do crivo de liberação — DECISÃO FECHADA (regra 17,
  2026-07-30)**: `convidado_web` é um item booleano na tela **Módulos e
  Recursos** já existente, mesmo padrão de todo outro módulo do sistema
  (`Cilindro`/`emite_mdfe`/`servicos`/etc.) — flag marcada libera o
  recurso "Web Convidado" pro cliente. Só o nome exato da tabela/coluna
  no schema segue em aberto (detalhe de implementação).
- **[GLOBAL, NOVO] Web Convidado é somente-leitura — DECISÃO FECHADA
  (regra 18, seção 3)**: toda configuração (`grupo_web`/`gruposweb`, foto
  de produto/`referencia_texto`, e por ora `convidado_web`) é feita
  inteiramente pelas telas já existentes do ERP principal; o módulo nunca
  escreve nessas tabelas, só lê o que já está configurado. Isso permanece
  válido até a fase de checkout (futura), quando parte do fluxo passa a
  envolver escrita.
- **Nível da árvore de Grupo Mercadológico pra `gruposweb` — DECISÃO
  FECHADA (2026-07-30)**: sempre o último nível (nó folha), nunca um nó
  intermediário. Ver regra 14, seção 3.
- **Formato de `gestor_documentos.referencia_texto` — não é mais uma
  dúvida bloqueante (2026-07-30)**: decorrência direta da regra 18 —
  o Web Convidado só lê o valor já gravado, sem precisar gerar/entender
  esse formato.
- **Preço exibido considera Preço por Quantidade/Promoção, sem carrinho —
  DECISÃO FECHADA em espírito (regra 19, 2026-07-30)**: como não há
  quantidade escolhida pelo cliente (fase atual é só vitrine), a
  precificação escalonada não depende de input do cliente. Detalhe de
  qual faixa exibir quando há mais de uma cadastrada fica pra
  implementação.
- **Produto m² fica fora da precificação automática do cardápio, mas não
  exclui a empresa/outros produtos — DECISÃO FECHADA (regra 19,
  2026-07-30)**: "produto m² precisa de um especialista para compor o
  preço final" — exclusão é por produto, não por estabelecimento.
- **Todos os Produtos Web aparecem na listagem — DECISÃO FECHADA (regra
  19, 2026-07-30)**: inclusive produto m² (que fica de fora só do preço
  calculado automaticamente, não da listagem) — a exclusão da regra
  acima nunca é "some do cardápio", só "não tem preço pronto".
- **Preço exibido pra produto m² é `pecas.p_venda` cru, sem indicador
  visual extra — DECISÃO FECHADA, regra 19 encerrada por completo
  (2026-07-30)**: "aparece o preço de venda... pois a descrição do
  produto já vai informar que é m2" — mesmo campo/exibição de qualquer
  produto normal, a descrição cadastrada já comunica o contexto m² pro
  cliente, sem precisar de tratamento visual especial.

## Histórico de atualizações

- 2026-07-11 — Criação do arquivo. Registradas visão geral, contexto de
  uso, regras de negócio 1-3, grupos mercadológicos de exemplo,
  integração com o sistema existente e decisões confirmadas (conforme
  prompt inicial do usuário). Levantadas 7 dúvidas em aberto para
  próximas rodadas de análise.
- 2026-07-11 (rodada 2) — Usuário respondeu 3 das 7 dúvidas: campos do
  produto exibidos (regra 4), mecanismo de resolução via QR Code + regra
  "só 1 conexão Web Convidado" de uso exclusivo do backend (regra 5), e
  escopo inicial só-produtos sem dados do estabelecimento. Registrada
  referência visual (screenshot BAIXO BRISA BISTRÔ). Registrada avaliação
  técnica (não decisão fechada) sobre armazenamento de foto, a pedido do
  usuário — recomendação de reaproveitar `FOTOS_PRODUTOS_DIR`/
  `GET /api/produtos/foto` já existentes. 3 dúvidas antigas fechadas,
  4 novas dúvidas registradas (implicação de "1 conexão só" pra
  múltiplos estabelecimentos, nome real do campo `aplicação`, fechamento
  da decisão de foto, escopo dos elementos de e-commerce da referência
  visual).
- 2026-07-11 (rodada 3) — Usuário fechou 4 pontos: nova regra 6
  (`pecas.Produto_web = true` filtra o que aparece no cardápio);
  confirmado que cada estabelecimento precisa da própria instalação de
  backend; decisão de foto FECHADA (reaproveitar infra de Produtos,
  sem mecanismo novo); confirmado que carrinho/pedido mínimo/tempo de
  entrega são escopo futuro, não da fase atual. Restam em aberto:
  identificador de mesa/comanda no QR Code, expiração do acesso, e
  confirmação dos nomes reais dos campos `aplicação`/`Produto_web` contra
  o schema (fica pra quando a implementação for liberada).
- 2026-07-11 (rodada 4) — Confirmado: identificador de mesa/comanda
  vinculado ao QR Code também é escopo futuro — a fase atual usa QR Code
  genérico por estabelecimento, sem vínculo com mesa específica. Restam
  em aberto: expiração do acesso, e confirmação dos nomes reais dos
  campos `aplicação`/`Produto_web` contra o schema.
- 2026-07-11 (rodada 5) — Expiração de acesso: intenção de negócio
  fechada — "sessão ativa enquanto o cliente estiver no estabelecimento".
  Mecanismo técnico exato (timeout por inatividade vs. limite máximo)
  registrado como dúvida pra fase de implementação, já que é decisão
  técnica e não de negócio. Restam em aberto: mecanismo técnico de
  expiração, e confirmação dos nomes reais dos campos
  `aplicação`/`Produto_web` contra o schema.
- 2026-07-11 (rodada 6) — Expiração de acesso FECHADA (regra 7): sessão
  ativa enquanto houver atividade, expira por inatividade prolongada de
  2 horas. Resta em aberto só a confirmação dos nomes reais dos campos
  `aplicação`/`Produto_web` contra o schema (fica pra fase de
  implementação).
- 2026-07-11 (rodada 7) — Nova regra 8: a princípio não há pedido feito
  pelo cliente convidado — o recurso é só visualização da lista de
  produtos; o pedido continua sendo feito pelo vendedor. Resta em aberto
  só a confirmação dos nomes reais dos campos `aplicação`/`Produto_web`
  contra o schema.
- 2026-07-11 (rodada 8) — Nova regra 9, a partir de novo screenshot de
  referência (card "BOLINHO DE FEIJOADA UND."): apresentação dos campos
  sem rótulo/nome do campo, só o conteúdo formatado visualmente. Resta em
  aberto só a confirmação dos nomes reais dos campos
  `aplicação`/`Produto_web` contra o schema.
- 2026-07-11 (rodada 9) — A partir de screenshot completo do BAIXO BRISA
  BISTRÔ (cabeçalho inteiro): nova regra 10 (estrutura geral da tela —
  banner de 3 imagens → logo+nome fantasia → grupos → produtos),
  confirmado em seguida que o banner é upload no cadastro da conexão
  "Web Convidado" e que logo/nome fantasia vêm da tabela `controle`.
  Também registradas regra 11 (tela moderna e intuitiva) e regra 12
  (layout responsivo, computador e smartphone). Resta em aberto só a
  confirmação dos nomes reais dos campos `aplicação`/`Produto_web`/
  colunas de `controle` contra o schema (fica pra fase de
  implementação).
- 2026-07-11 (rodada 10) — Nova regra 13: rolar a lista de produtos
  sincroniza a aba de grupo ativa, seguindo a sequência exibida (mesmo
  comportamento do BAIXO BRISA BISTRÔ). Registrada dúvida sobre o
  comportamento inverso (clicar numa aba rola até a seção, ou filtra a
  lista?) — assumido rolagem por ora, não confirmado.
- 2026-07-11 (rodada 11) — Nova regra 14: Cadastro de Grupo Mercadológico
  vai precisar de sequência de exibição + flag de habilitação pro Web
  Convidado, no mesmo espírito da flag de Produto (regra 6) — mas,
  diferente dos campos de Produto (só precisam confirmação de nome),
  esses dois campos de Grupo **ainda não existem no banco** e vão
  precisar ser criados. Tabela alvo provável: `niveis`.
- 2026-07-11 (rodada 12) — Confirmado (regra 13, 2ª metade): clicar numa
  aba de grupo filtra a lista pro grupo clicado, não rola até a seção.
  Registrado ponto de atenção não resolvido: possível conflito entre essa
  resposta e a 1ª metade da regra 13 (rolagem sincroniza aba ativa,
  presumindo lista contínua com vários grupos) — fica como pergunta
  aberta pra próxima rodada, sem assumir a reconciliação.
- 2026-07-11 (rodada 13) — Nome do campo de habilitação de Grupo
  Mercadológico pro Web Convidado definido: `grupo_web` (regra 14). Nome
  do campo de sequência de exibição ainda não definido.
- 2026-07-11 (rodada 14) — Confirmada a mecânica de rolagem contínua
  entre grupos (regra 13): ao terminar a lista de um grupo, rolar mais
  avança pro próximo grupo sem remover os itens já carregados do grupo
  anterior (infinite scroll). Isso reforça a 1ª metade da regra 13, mas
  o ponto de atenção sobre "clicar numa aba filtra a lista" segue em
  aberto — refinada a pergunta na seção 6 (como o modo filtrado por
  clique se relaciona com a rolagem contínua, e se há caminho de volta).
- 2026-07-11 (rodada 15) — Duas respostas: (1) mecanismo de ordenação de
  Grupo Mercadológico (regra 14) confirmado como arrastar-e-soltar, local
  exato (tela nova x já existente) deixado em aberto pelo próprio
  usuário; (2) confirmado que clicar numa aba SAI da rolagem contínua e
  entra num modo só daquele grupo (regra 13) — resta só confirmar se há
  caminho de volta pra visão com todos os grupos.
- 2026-07-11 (rodada 16) — FECHADA a dúvida sobre caminho de volta
  (regra 13): abas de grupo ficam sempre visíveis, navegação por rolagem
  OU clique sempre disponíveis, listagem sempre começa pelo primeiro
  grupo da sequência. Restam em aberto: local do arrastar-e-soltar (tela
  nova x já existente), nome do campo de sequência de exibição, e
  confirmação dos nomes reais dos campos `aplicação`/`Produto_web`/
  colunas de `controle` contra o schema.
- 2026-07-11 (rodada 17) — Nova regra 15: ao criar a conexão "Web
  Convidado" na tela de Conexões, o sistema gera o QR Code
  automaticamente na mesma tela, disponível pra captura/exportação em
  arquivo sempre que necessário.
- 2026-07-11 (rodada 18) — Regra 14 detalhada por completo a partir de
  screenshot da tela REAL de Grupo Mercadológico (árvore, já existente no
  sistema): flag "Web" (`niveis.grupo_web`) na própria árvore decide
  visibilidade; botão novo no canto superior direito filtra só grupos
  Web=true; esse botão abre tela NOVA "Grupos da Web Convidado" onde a
  sequência é configurada por arrastar-e-soltar; nova tabela `gruposweb`
  guarda grupos + sequência — resolve a dúvida antiga "tela nova x já
  existente" (resposta: as duas coisas, cada parte numa tela). Registrada
  dúvida nova, não assumida: como a flag `grupo_web` e a tabela
  `gruposweb` se relacionam exatamente (a flag decide sozinha e a tabela
  só guarda ordem, ou a tabela é quem decide de verdade)?
- 2026-07-11 (rodada 19) — FECHADA a dúvida da relação flag x tabela
  (regra 14): `grupo_web` é a fonte da verdade de visibilidade;
  `gruposweb` é só a sequência, sincronizada automaticamente (marcar
  adiciona, desmarcar remove). Restam em aberto: nomes exatos das colunas
  de `gruposweb`, nome do campo de sequência de exibição, e confirmação
  dos nomes reais de `aplicação`/`Produto_web`/colunas de `controle`
  contra o schema.
- 2026-07-11 (rodada 20) — Nova regra 16 [GLOBAL]: upload de foto de
  produto é escopo do futuro Cadastro de Produtos, não do Web Convidado
  — o módulo só consome/exibe fotos já existentes. Registrada dependência
  entre módulos (sem o Cadastro de Produtos com upload, não há como
  adicionar fotos novas hoje).
- 2026-07-11 (rodada 21) — Colunas de `gruposweb` definidas: código do
  grupo + sequência. Levantada dúvida nova: a que nível da árvore
  hierárquica de Grupo Mercadológico esse "código do grupo" se refere
  (qualquer nó em qualquer profundidade, ou só um nível específico)?
- 2026-07-11 (rodada 22) — Usuário perguntou diretamente sobre local de
  armazenamento das imagens de produto (por conexão x mesmo mecanismo do
  Gestor de Documentos). Registrada avaliação/recomendação (reaproveitar
  Gestor de Documentos/`controle_aux`, evitar terceiro mecanismo de
  storage), sinalizando que isso implica revisar a decisão anterior sobre
  `FOTOS_PRODUTOS_DIR` — aguardando confirmação do usuário antes de
  fechar.
- 2026-07-11 (rodada 23) — Nova regra 17: criação de flag de módulo
  própria e independente **"Convidado Web"** (campo persistido
  `convidado_web`) na tela de Módulos do Sistema, liberando o recurso pra
  qualquer cliente/estabelecimento — **SUPERSEDE a regra 2** (não depende
  mais do módulo Bar). Seções 5 e 7 atualizadas (bullets antigos riscados
  e marcados SUPERADA, nova decisão fechada registrada). Nova dúvida:
  confirmar em qual tabela exata `convidado_web` será persistido.
- 2026-07-11 (rodada 24) — FECHADA a dúvida sobre local de armazenamento
  das fotos de produto (pendente desde a rodada 22): as fotos passam a
  ser gravadas no mesmo path/mecanismo do Gestor de Documentos
  (`controle_aux.path_gestor_documentos`), substituindo a decisão
  anterior de usar `FOTOS_PRODUTOS_DIR`. Por instrução explícita do
  usuário ("todas as regras serão passadas pela forma como o gestor
  trabalha"), todo o mecanismo de armazenamento — não só o path — passa a
  seguir o funcionamento do Gestor de Documentos, afetando tanto o futuro
  upload (Cadastro de Produtos, regra 16) quanto a leitura/consumo pelo
  Web Convidado. Seção 4, 6 e 7 atualizadas; dúvida de local removida da
  seção 6 (resolvida).
- 2026-07-11 (rodada 25) — Usuário trouxe print de uma linha real da
  tabela `gestor_documentos` (imagem de produto já gravada por lá).
  CONFIRMADO: a foto do produto não usa mecanismo à parte, é um registro
  comum direto no Gestor de Documentos, mesmo fluxo de qualquer anexo.
  Colunas confirmadas visualmente. Registradas 2 dúvidas novas na seção
  6: quais `cod_grupo`/`cod_sub_grupo` são reservados pra "Produto -
  Imagem", e o formato exato de `referencia_texto` (exemplo `P10324`,
  hipótese não confirmada de prefixo `P` + `codigo_int`).
- 2026-07-11 (rodada 26) — Usuário detalhou um SEGUNDO mecanismo de
  imagem no Gestor de Documentos: fluxo de "produto de grade" (produto
  com variações/matriz), com tela dedicada, usa Azure Blob
  especificamente porque o consumo via site precisa de URL (diferente do
  fluxo "normal" registrado na rodada 25, que só grava direto em
  `gestor_documentos`). Funções desse fluxo vivem numa DLL VB.NET
  (`APICamadas\BackOn`, mesma referência já usada em CLAUDE.md > "Legacy
  VB6 Source Reference") — não rastreado agora, fase de análise. Nova
  dúvida registrada (seção 6): já que o Web Convidado também é um
  consumo tipo site (precisa de URL), ele deve seguir o fluxo de "produto
  de grade" (Blob+URL) mesmo pra produtos que não são de grade, ou existe
  outra forma de obter URL a partir do registro "normal"? E o que
  "produto de grade" significa exatamente neste sistema (aplica a
  produtos de bar/restaurante)?
- 2026-07-11 (rodada 27) — Usuário trouxe print com várias linhas reais
  de `gestor_documentos`, confirmando a convenção geral de
  `path`/`path_origem`: `path_origem` é só o caminho original na máquina
  de quem adicionou (auditoria); `path` (destino real) segue o padrão
  `<raiz>\<Grupo>\<SubGrupo>\<referência> - <arquivo>` — reforça (sem
  fechar de vez) a hipótese de `cod_grupo=4`/`cod_sub_grupo=11` =
  Produtos/Imagens, já que o exemplo de foto de produto caiu exatamente
  em `Produtos\Imagens`. Também confirmado: a rotina de adicionar arquivo
  cria a pasta de destino automaticamente se ela não existir.
- 2026-07-11 (rodada 28) — Usuário trouxe print da árvore de pastas real
  em disco (Documentos > Clientes/Favorecidos/Produtos, com seus
  subgrupos), confirmando visualmente que toda essa estrutura é gerada
  automaticamente pela função de adicionar arquivo (reforça a rodada 27).
  Confirma a nível de negócio que `Produtos\Imagens` é o destino padrão
  de foto de produto — falta só confirmar os códigos numéricos exatos
  (`cod_grupo`/`cod_sub_grupo`) contra `GESTOR_DOC_GRUPO_*` na fase de
  implementação.
- 2026-07-11 (rodada 29) — Usuário corrigiu/detalhou o "segundo mecanismo
  (produto de grade)" da rodada 26: NÃO é um destino separado — é o
  MESMO registro/pasta de qualquer imagem, só que quando é "grade"
  também faz upload pro Blob e grava a URL numa coluna própria de
  `gestor_documentos`, **`PATH_NUVEM`** (existência confirmada por print,
  aparece `NULL` nas linhas de exemplo que não passaram por upload).
  Resolve boa parte da dúvida da rodada 26: Web Convidado consulta a
  mesma tabela e usa `PATH_NUVEM` quando disponível, senão cai pro `path`
  local. Também esclarecido: o nome do arquivo gravado (`código -
  descrição`) é só convenção do sistema legado, não regra obrigatória —
  o que importa é o valor da coluna `path`. Dúvida refinada (seção 6):
  o upload pro Blob vai acontecer sempre que uma foto de produto for
  cadastrada, ou só em certos casos? Print também reforçou (com destaque
  visual) `cod_grupo=4`/`cod_sub_grupo=11` = Produtos/Imagens.
- 2026-07-11 (rodada 30) — [GLOBAL] Usuário decidiu explicitamente adiar
  a dúvida sobre quando `PATH_NUVEM` é preenchido (upload pro Blob
  sempre x só em certos casos) pro momento em que a tela de Cadastro de
  Produtos for implementada ("veremos no momento da tela de produtos") —
  não é mais uma dúvida ativa da fase de análise do Web Convidado, só
  fica registrada como pendência pra quando aquela tela for construída.
- 2026-07-30 (rodada 31) — Usuário respondeu 4 pontos de uma vez: (1)
  reforçou que o módulo é GLOBAL, não exclusivo de Bar, porque
  futuramente terá checkout (regra 17 ampliada); (2) tabela de
  `convidado_web` — não fechou o nome, respondeu "por enquanto somente
  exibição" (mantido em aberto, seção 6, com o novo contexto); (3)
  FECHADA a dúvida do nível da árvore de Grupo Mercadológico pra
  `gruposweb` — sempre o último nível (nó folha), nunca intermediário
  (regra 14); (4) esclarecido que o formato de
  `gestor_documentos.referencia_texto` não é uma preocupação do Web
  Convidado — "configuração é toda feita no app, Web Convidado somente
  exibição" — generalizado como nova regra 18 [GLOBAL]: o módulo inteiro
  é somente-leitura, toda escrita/configuração acontece no ERP principal,
  até a fase futura de checkout.
- 2026-07-30 (rodada 32) — Usuário detalhou o mecanismo do crivo de
  liberação (dúvida deixada em aberto na rodada 31): "O crivo é feito via
  configurações de módulos. Lá teremos Web Convidado. Essa flag
  habilitado, é liberado esse recurso para o cliente." FECHA a
  arquitetura da regra 17 — `convidado_web` é mais um item booleano na
  tela Módulos e Recursos já existente, mesmo padrão de todo outro módulo
  do sistema. Resta só o nome exato da tabela/coluna no schema (detalhe
  de implementação, não bloqueia mais a análise de negócio).
- 2026-07-30 (rodada 33) — Nova regra 19: o preço exibido no cardápio
  precisa considerar os recursos de configuração de preço já existentes
  no Cadastro de Produtos (Preço por Quantidade, Variações de Preços/
  Promoção), não só `p_venda` cru. Registradas 2 dúvidas novas (seção 6):
  como exibir preço escalonado por quantidade sem carrinho, e se produto
  m² (Metro Quadrado) entra nessa regra dado que seu preço depende de
  dimensão só informada na hora da venda. Nesta mesma rodada, o usuário
  também autorizou implementar desde já (fora da fase de análise) um
  recurso adjacente no Cadastro de Produtos: modal "Dias da Semana"
  (tabela nova `Web_DiasSemana`) — ver CLAUDE.md > "Produto Completo" pro
  registro da implementação em si (fora do escopo desta doc, que é só
  análise de negócio do módulo Web Convidado como um todo).
- 2026-07-30 (rodada 34) — Usuário respondeu as 2 dúvidas da rodada 33:
  (1) preço escalonado sem carrinho — confirmado que a precificação
  (Preço por Quantidade/Promoção) é considerada mesmo sem o cliente
  escolher quantidade (fase 1 é só exibição, sem carrinho); detalhe de
  qual faixa exibir quando há mais de uma cadastrada fica pra
  implementação; (2) produto m² — FECHADA: fica de fora da precificação
  automática ("precisa de um especialista para compor o preço final"),
  mas isso é uma exclusão POR PRODUTO, não exclui a empresa nem os outros
  produtos do Web Convidado. Resta só o detalhe de UI de como o produto
  m² aparece (ou não) na listagem — ver seção 6.
- 2026-07-30 (rodada 35) — FECHADA a última parte da dúvida do produto
  m²: "todos os Produtos Web aparecem na listagem" — inclusive m², que só
  fica de fora do preço calculado automaticamente, nunca da listagem em
  si. Resta só o detalhe visual (implementação): o que aparece no lugar
  do preço nesse caso.
- 2026-07-30 (rodada 36) — FECHA por completo a regra 19: "aparece o
  preço de venda" pra produto m² (mesmo `pecas.p_venda` de qualquer
  produto normal, sem calcular área), e "pois a descrição do produto já
  vai informar que é m2" — não precisa de indicador visual extra, a
  descrição cadastrada já comunica isso. Nenhuma dúvida residual sobre
  precificação m² no Web Convidado.
- 2026-07-30 (rodada 37) — Nova regra 20: "cardápio" só é o rótulo/
  apresentação do Web Convidado quando o módulo Bar está ativo — sem Bar,
  é uma "Listagem de Produtos Web" genérica (mesmos dados, sem estilo de
  restaurante). Motivado por uma correção do usuário a um texto de ajuda
  do app (Cadastro de Produtos) que presumia "cardápio" incondicional —
  texto já corrigido pra "listagem Web para convidados", genérico. Seção
  1 (Visão Geral) atualizada com nota de leitura.
