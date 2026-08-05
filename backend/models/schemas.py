"""Modelos Pydantic (request/response) de toda a API Back-On."""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


class StatusCheck(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    client_name: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class StatusCheckCreate(BaseModel):
    client_name: str


class LoginRequest(BaseModel):
    empresa: str
    servidor: str
    banco: str
    usuario: str
    senha: str
    timeout: Optional[int] = 8


class LoginResponse(BaseModel):
    success: bool
    message: str
    empresa: Optional[str] = None
    server: Optional[str] = None
    database: Optional[str] = None
    usuario: Optional[dict] = None
    funcionario: Optional[dict] = None
    # Diagnóstico de erro
    error_step: Optional[str] = None          # connect | query_usuarios | query_funcionarios
    error_line: Optional[str] = None          # arquivo:linha
    error_code_line: Optional[str] = None     # trecho de código que falhou
    error_query: Optional[str] = None         # SQL executado (parâmetros omitidos)
    attempted: Optional[dict] = None          # dados da conexão tentada


class ClientesRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    page: int = 1
    size: int = 20


class PedidosListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    situacao: Optional[str] = ""  # vazio = todos
    vendedor: Optional[str] = None  # None/"all" = todos; número = filtra por vendedor
    data_ini: Optional[str] = None  # ISO YYYY-MM-DD
    data_fim: Optional[str] = None  # ISO YYYY-MM-DD
    page: int = 1
    size: int = 20
    # Filtros do painel "Pedidos Abertos" do Pedido Bar (FrmManPedBar.frm)
    # — tela old-VB6 filtra pelo tipo do CLIENTE (cliente.cliente_forn),
    # não por um tipo de pedido: os "tipos" Mesa/Balcão/Entrega/Comanda são
    # linhas específicas em `tipo_cliente` (descricao='MESA'/'BALCÃO'/
    # 'ENTREGA'/'COMANDA'), data-driven (só existem se cadastradas).
    tipos_cliente: Optional[List[int]] = None  # códigos de tipo_cliente pra filtrar
    data_entrega: Optional[str] = None  # ISO YYYY-MM-DD — previsao_entrega <= data_entrega
    ordenar_por: Optional[str] = None  # "abertura" | "tipo" | "cliente"


class PedidoSaveRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int                       # cliente.codigo
    vendedor: int                      # funcionarios.codigo_int
    validade: Optional[str] = None     # ISO date YYYY-MM-DD
    obs: Optional[str] = ""
    area_atuacao: Optional[int] = None  # area_atuacao.area (FK)
    previsao_entrega: Optional[str] = None  # ISO date YYYY-MM-DD (pedido_venda.previsao_entrega)
    hora_entrega: Optional[str] = None      # HH:MM ou HH:MM:SS (pedido_venda.hora_entrega)
    forma_pag: Optional[str] = None    # forma_pagamento.codigo — combobox simples (1 forma só)
    # Combobox "Tipo" do Pedido Bar (pedido_venda.tipo, FK tipo_cliente.codigo)
    # — tipo do PEDIDO, separado do tipo do CLIENTE (cliente.cliente_forn):
    # um cliente Entrega pode virar um pedido lançado como Comanda na lista,
    # sem mudar o tipo do cliente. Cliente reservado Mesa/Comanda/Balcão
    # sempre sobrescreve esse valor com o próprio tipo dele no backend (ver
    # `_save_pedido_sync`) — este campo aqui é só o que foi pedido/
    # selecionado na tela, não o valor final gravado. None = sem tipo
    # próprio, a listagem cai pro tipo do cliente. Pedido explícito do
    # usuário, 2026-07-18.
    tipo: Optional[int] = None
    # Campo livre "Referência" — reaproveita pedido_venda.num_ped_cliente (já
    # existente na tabela, já exposto no Pedido Completo como "Nº Pedido do
    # Cliente"), agora também no Pedido Bar. Usado tanto como referência livre
    # do cliente quanto, ao Dividir Pedido, para registrar o nº do pedido que
    # originou a divisão nos pedidos filhos (pedido explícito do usuário,
    # 2026-07-17 — ver `_dividir_pedido_sync`).
    referencia: Optional[str] = None
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    classe: Optional[int] = None             # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


class DividirPedidoItem(BaseModel):
    codauto: int    # pedido_venda_prod.codauto do item no pedido ORIGINAL
    qtd: float      # quantidade movida pra este grupo (pode ser fracionária —
                     # é assim que se divide o VALOR de 1 unidade indivisível
                     # entre várias pessoas, ex. 1 pizza / 4 = qtd 0.25 cada)


class DividirPedidoGrupo(BaseModel):
    """Um grupo vira um pedido NOVO. O que não for atribuído a nenhum grupo
    continua no pedido original — não precisa ser listado explicitamente."""
    itens: list[DividirPedidoItem]


class DividirPedidoRequest(BaseModel):
    servidor: str
    banco: str
    grupos: list[DividirPedidoGrupo]
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class FormaPagamentoAddRequest(BaseModel):
    """Lança uma forma de pagamento (modal "Forma de Pagamento", FrmForPag.frm
    — tela genérica reaproveitada por Pedido Bar, Pedido Completo e O.S. no
    legado, mesmo `Type_FormaPagPedOS`) — um dos 8 tipos
    (`forma_pagamento.tipo`), cada um com um subconjunto de campos extras
    (os demais ficam None/ignorados)."""
    servidor: str
    banco: str
    tipo_dav: str = "PED"  # PED (Pedido Bar/Completo) ou OS
    tela: Optional[str] = None  # tela da permissão (PEDIDO/PEDIDO_COMP/OS) — Pedido Bar e Completo
    # compartilham as mesmas tabelas (tipo_dav="PED"), mas têm permissões
    # próprias; default fica a cargo do service (_TELA_POR_DAV) se omitido.
    tipo: str            # DI/CH/CC/CD/DU/TI/VA/FI
    forma_pag: str        # forma_pagamento.codigo
    valor: float
    vencimento: Optional[str] = None  # ISO date — CH/CC/CD/VA "Bom Para", DU/FI "Vencimento"
    # Cheque
    cod_banco: Optional[int] = None
    agencia: Optional[int] = None
    conta: Optional[str] = None
    numero_ch: Optional[int] = None
    nome_cheque: Optional[str] = None
    telefone: Optional[str] = None
    # Cartão crédito/débito
    num_cartao1: Optional[int] = None
    num_cartao2: Optional[int] = None
    num_cartao3: Optional[int] = None
    num_cartao4: Optional[int] = None
    mes_validade: Optional[int] = None
    ano_validade: Optional[int] = None
    parcelas: Optional[int] = None
    cod_administradora: Optional[int] = None
    cod_parcelador: Optional[str] = None
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    master: Optional[bool] = False
    plataforma: Optional[str] = None


class FormaPagamentoUpdateRequest(FormaPagamentoAddRequest):
    # Opcional (não `int` puro) de propósito: o frontend nunca manda
    # `sequencia` no corpo (só no path da URL, `PUT .../{sequencia}`) — a
    # rota sempre sobrescreve `req.sequencia` a partir do path logo depois
    # de validar o body (`routes/pedidos.py`/`routes/os.py`). Se este campo
    # fosse obrigatório, o FastAPI rejeitava a requisição com 422 ANTES da
    # rota rodar (o body nunca tem `sequencia`), e a sobrescrita nunca
    # chegava a acontecer — bug real encontrado 2026-07-17 (usuário
    # reportou "não exclui pagamento"; alterar tinha o mesmo problema,
    # só não relatado ainda).
    sequencia: Optional[int] = None


class FormaPagamentoDeleteRequest(BaseModel):
    servidor: str
    banco: str
    tipo_dav: str = "PED"
    tela: Optional[str] = None
    tipo: str
    # Mesmo motivo do comentário em FormaPagamentoUpdateRequest.sequencia
    # acima — opcional de propósito, sempre sobrescrito pela rota a partir
    # do path da URL.
    sequencia: Optional[int] = None
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    master: Optional[bool] = False
    plataforma: Optional[str] = None


class PedidoEntregueRequest(BaseModel):
    """Checkbox 'Pedido Entregue' do Pedido Bar (FrmManPedBar.frm,
    Check88_Click) — grava direto, fora do fluxo normal de Gravar."""
    servidor: str
    banco: str
    entregue: bool
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class QtdPessoasRequest(BaseModel):
    """Painel de Pedidos (Mesa/Comanda/Balcão) — quantidade de pessoas
    sentadas na mesa/comanda/balcão, usada só pra dividir o valor total na
    impressão da conta (ver `ReciboPedidoModal`). Grava direto ao editar no
    card, fora do fluxo normal de Gravar — mesmo padrão de
    `FormaPagSimplesRequest`/`PedidoEntregueRequest` abaixo. Campo novo, sem
    precedente no legado. Pedido explícito do usuário, 2026-07-17."""
    servidor: str
    banco: str
    qtd_pessoas: Optional[int] = None  # None/0 = "não informado"
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class TipoPedidoRequest(BaseModel):
    """Painel de Pedidos — troca do "Tipo" do pedido (Mesa/Comanda/Balcão/
    Entrega/Fiado, FK `tipo_cliente.codigo`) direto da listagem, arrastando
    o card entre colunas (`app/pedidos.tsx`, `tipo` = código da coluna de
    destino). Grava direto, fora do fluxo normal de Gravar — mesmo padrão de
    `QtdPessoasRequest`/`FormaPagSimplesRequest` acima. Passa pela mesma
    regra de override de cliente reservado já usada no combobox "Tipo" da
    tela cheia (`pedido_common._resolve_tipo_pedido`) — ver
    `pedidos_service._set_tipo_pedido_sync`. Pedido explícito do usuário,
    2026-07-30."""
    servidor: str
    banco: str
    tipo: int
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class FormaPagSimplesRequest(BaseModel):
    """Combobox simples 'Forma de Pagamento' do cabeçalho (não o modal de
    múltiplas formas) — grava direto ao trocar a seleção, fora do fluxo
    normal de Gravar. Sem isso, escolher a forma aqui só ficava em estado
    local até o usuário clicar em Gravar; clicar direto em Faturar/Fechar
    antes disso via `pedido_venda.forma_pag`/`os.forma_pagamento` ainda
    vazio, e a validação de forma de pagamento bloqueava mesmo com uma
    forma "selecionada" na tela (bug reportado pelo usuário 2026-07-16).
    Reutilizado por Pedido (Bar e Completo, mesma tabela pedido_venda) e
    O.S. — mesmo padrão de `FecharRequest`."""
    servidor: str
    banco: str
    forma_pag: str = ""
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class ItemSaveRequest(BaseModel):
    servidor: str
    banco: str
    produto: Optional[str] = None          # obrigatório no create
    qtd: float = 1
    valor_unitario: Optional[float] = None  # se None, usa preço padrão do produto
    complemento: Optional[str] = ""
    desconto: Optional[float] = 0          # desconto UNITÁRIO em R$
    desconto_pct: Optional[float] = 0      # % informado (0 se foi em R$) — só para o log
    acrescimo: Optional[float] = 0         # acréscimo UNITÁRIO em R$
    usuario_codigo: Optional[int] = -2     # -2 = KONTACTO (master) — também usado como ator no log de auditoria
    funcao: Optional[int] = None           # 1=gerente,2=supervisor,3=vendedor (p/ validar limite)
    classe: Optional[int] = None           # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None       # "web"/"android"/"ios" — só pro log de auditoria
    # Número de série (pecas_num_serie.codigo) — só usado pelo Pedido Geral
    # (PEDIDO_COMP), quando o produto tem `controla_num_serie=1`. Ignorado
    # pelo fluxo rápido do Bar (itens_service.py nunca lê este campo — ver
    # PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: número de série").
    cod_num_serie: Optional[int] = None
    # Metro Quadrado (m²/ml/m³) — só usado pelo Pedido Geral (PEDIDO_COMP)
    # quando `pecas.uni` do produto é M2/ML/M3 e o módulo Metro Quadrado
    # está ativo. `tipo_preco_m2` é o índice (0-5) escolhido em
    # `pedido_common.TIPOS_PRECO_M2`. Ignorados pelo fluxo do Bar. Ver
    # PENDENCIAS.md > "Transações" > "Pedido Geral — Metro Quadrado".
    tipo_preco_m2: Optional[int] = None
    comprimento: Optional[float] = None
    largura: Optional[float] = None
    comprimento_chapa: Optional[float] = None
    largura_chapa: Optional[float] = None


class TaxaServicoRequest(BaseModel):
    """Botão 'Incluir Tx Serviço' do Pedido Bar (FrmManPedBar.frm, Command50_Click)
    — inclui (ou atualiza, se já existir) uma linha de 10% do subtotal atual
    como serviço 'S002'. Idempotente: não empilha uma nova linha a cada
    clique (decisão explícita do usuário, 2026-07-15 — diferente do legado)."""
    servidor: str
    banco: str
    usuario_codigo: Optional[int] = -2
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class OSListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""
    situacao: Optional[str] = ""  # vazio = todas
    data_ini: Optional[str] = None  # ISO YYYY-MM-DD
    data_fim: Optional[str] = None  # ISO YYYY-MM-DD
    page: int = 1
    size: int = 20


class OSSaveRequest(BaseModel):
    servidor: str
    banco: str
    cliente: int                          # cliente.codigo
    area_atuacao: Optional[int] = None    # area_atuacao.area (FK)
    descricao_cliente: Optional[str] = ""  # "Cliente Descreva" (os.descricao_cliente)
    obs: Optional[str] = ""                # os.obs
    resumo: Optional[str] = ""             # "Serviço Executado" (os.resumo)
    status_os: Optional[int] = None        # índice do combobox (os.status_os)
    atendente: Optional[int] = None        # funcionarios.codigo_int (os.atendente)
    situacao: Optional[str] = None         # A/F/PG/C (os.situacao); None no create = 'A'
    # Veículo / Equipamento
    placa: Optional[str] = ""              # os.placa
    marca: Optional[str] = ""              # os.marca
    modelo: Optional[str] = ""             # os.modelo
    km: Optional[int] = None               # os.km
    ano: Optional[str] = ""                # os.ano
    chassi: Optional[str] = ""             # os.chassi (Oficina)
    numero_de_serie: Optional[str] = ""    # os.numero_de_serie (Assistência)
    forma_pagamento: Optional[str] = None  # forma_pagamento.codigo — combobox simples (1 forma só)
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    classe: Optional[int] = None             # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


class OSCompletoSaveRequest(OSSaveRequest):
    """Cabeçalho da O.S. Completa (`FrmTraOsNew.frm`) — estende
    `OSSaveRequest` com os campos que só existem na tela completa (a O.S.
    Mobile continua gravando só o subconjunto de `OSSaveRequest`). Todas as
    colunas abaixo já existem em `os` (confirmado ao vivo contra
    KONTACTO-TESTE, 2026-07-31) — nenhuma migração de schema necessária."""
    referencia_os: Optional[str] = ""          # os.REFERENCIA_OS
    tecnico_responsavel: Optional[int] = None  # funcionarios.codigo_int (os.tecnico_responsavel)
    posicao_os: Optional[int] = None           # Tipo O.S. — lookup tipo_os.codigo (os.posicao_os)
    previsao_termino: Optional[str] = None     # yyyy-mm-dd (os.previsao_termino)
    data_termino: Optional[str] = None         # yyyy-mm-dd (os.data_termino)
    hora_entrada: Optional[str] = ""           # hh:mm (os.hora_entrada)
    hora_fechamento: Optional[str] = ""        # hh:mm (os.hora_fechamento)
    # Doc. Origem / Revisão programada (migração de `Campo(150)`/`Campo(151)`/
    # `Option9`/`Option10` em `FrmTraOsNew.frm`) — validação cruzada de OS/
    # Pedido de origem pra O.S. do tipo Garantia/Revisão, ver
    # `os_completo_service._validar_doc_origem`. Colunas NOVAS em `os`
    # (`Tipo_Doc_Original`/`VALIDOU_GARANTIA`/`QtdRevisoes` — `OS_ORIGINAL`
    # já existia), migração idempotente em `pedido_common.
    # _ensure_os_doc_origem_cols`.
    os_original: Optional[int] = None          # os.OS_ORIGINAL — código da O.S. ou Pedido de origem
    tipo_doc_original: Optional[str] = None    # "O" (O.S.) ou "P" (Pedido) — os.Tipo_Doc_Original
    qtd_revisoes: Optional[int] = None         # os.QtdRevisoes — gera N datas de revisão programada
    # "Deseja entrar com senha superior para autorização?" (bypass de
    # gerente/supervisor/master quando a validação cruzada falha) — mesmo
    # padrão de `AgendarItemRequest.autorizado_por`/`AuthorizationSlide`,
    # não reverifica senha no backend, só registra quem autorizou no log.
    autorizado_por: Optional[str] = None
    # Bifurcação de faturamento Garantia×Cliente (`GeraComanda`, branch "G",
    # `FrmTraOsNew.frm`) — forma de pagamento usada SÓ pra faturar o bloco
    # de itens Garantia/Interno/Contrato (`os_produto.situacao<>0`), em
    # comanda separada do bloco Cliente paga (que continua usando
    # `forma_pagamento` normal). Coluna nova `os.forma_pagamento_garantia`,
    # migração idempotente em `pedido_common._ensure_os_forma_pagamento_garantia_col`.
    forma_pagamento_garantia: Optional[str] = None


class OSItemSaveRequest(BaseModel):
    servidor: str
    banco: str
    produto: Optional[str] = None          # obrigatório no create (pecas.codigo_int / servicos.codigo)
    qtd: float = 1
    valor_unitario: Optional[float] = None  # se None, usa preço padrão do produto
    complemento: Optional[str] = ""
    desconto: Optional[float] = 0          # desconto UNITÁRIO em R$
    desconto_pct: Optional[float] = 0      # % informado (só p/ log)
    acrescimo: Optional[float] = 0         # acréscimo UNITÁRIO em R$
    vendedor: Optional[int] = None         # funcionarios.codigo_int — POR ITEM
    executor: Optional[int] = None         # funcionarios.codigo_int — POR ITEM
    # Situação/Destino do item (os_produto.situacao) — réplica de `Destino(2)`
    # no legado (`FrmTraOsNew.frm`): 0=Cliente paga, 1=Garantia, 2=Interno,
    # 3=Contrato. Só a O.S. Completa expõe esse combobox na tela; a O.S.
    # Mobile sempre grava 0 (default) — mesmo padrão de "campo novo,
    # default preserva o comportamento anterior" já usado noutros lugares
    # deste arquivo. Consumido hoje só como dado de cabeçalho/exibição —
    # a bifurcação de faturamento por Situação (Cliente x Garantia/Interno/
    # Contrato) fica fora da Fase 1, ver PENDENCIAS.md > "O.S. Completa".
    situacao: Optional[int] = 0
    usuario_codigo: Optional[int] = -2     # também usado como ator no log de auditoria
    funcao: Optional[int] = None
    classe: Optional[int] = None           # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None       # "web"/"android"/"ios" — só pro log de auditoria


class DescontoGeralRequest(BaseModel):
    servidor: str
    banco: str
    valor: float = 0               # valor TOTAL do desconto geral em R$ (0 = remover)
    usuario_codigo: Optional[int] = -2  # também usado como ator no log de auditoria
    funcao: Optional[int] = 1       # 1=gerente, 2=supervisor, 3=vendedor
    classe: Optional[int] = None    # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None  # "web"/"android"/"ios" — só pro log de auditoria


class PedidoCompletoSaveRequest(BaseModel):
    """Cabeçalho do Pedido Completo (web) — mesma tabela `pedido_venda` do
    Pedido rápido (`PedidoSaveRequest`), mas com o conjunto de campos real
    do `frmmanpedfor.frm` (Frame2), maior que o do fluxo rápido mobile."""
    servidor: str
    banco: str
    cliente: int                       # cliente.codigo
    vendedor: int                      # funcionarios.codigo_int
    forma_pag: Optional[str] = ""      # forma_pagamento.codigo (nvarchar(3))
    validade: Optional[str] = None     # ISO date YYYY-MM-DD
    previsao_entrega: Optional[str] = None  # ISO date YYYY-MM-DD
    local_entrega: Optional[str] = ""
    infoentrega: Optional[str] = ""
    num_ped_cliente: Optional[str] = ""     # "nº do pedido do cliente" (referência externa)
    # Reaproveita `num_ped_cliente` também para o rastreio do pedido-pai ao
    # Dividir (mesmo campo/coluna, mesma regra do Pedido Bar — ver
    # `_dividir_pedido_sync`). Um pedido FILHO de uma divisão trava esse
    # campo na tela; o pedido ORIGINAL continua livre pra guardar o próprio
    # nº de referência do cliente. Pedido explícito do usuário, 2026-07-20.
    obs: Optional[str] = ""
    area_atuacao: Optional[int] = None  # area_atuacao.area (FK)
    hora_entrega: Optional[str] = None      # HH:MM ou HH:MM:SS (pedido_venda.hora_entrega)
    # Combobox "Tipo" do Pedido Bar (pedido_venda.tipo, FK tipo_cliente.codigo)
    # — trazido ao Pedido Geral/Completo 2026-07-20 (pedido explícito do
    # usuário), mesma regra/resolução do Bar (`_resolve_tipo_pedido` em
    # `pedido_common.py`, inclusive a exceção de cliente reservado Mesa/
    # Comanda/Balcão que sempre sobrescreve).
    tipo: Optional[int] = None
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    classe: Optional[int] = None             # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


class AgendarItemRequest(BaseModel):
    """Agendar/reagendar um atendimento (módulo Clínica — `FrmAtende.frm`/
    `FrmMarAge2.frm`). Ampliado pra cobrir tanto um item de Serviço do Pedido
    Geral (`codauto` informado — cliente/serviço vêm do próprio pedido)
    quanto um agendamento AVULSO criado direto da grade (`codauto` None —
    `cliente`/`servico` obrigatórios). Ver PENDENCIAS.md > "Transações" >
    "Pedido Geral — Fase B: Clínica (Agendamento)"."""
    servidor: str
    banco: str
    funcionario: int
    data: str      # yyyy-mm-dd
    hora_ini: str   # HH:MM
    # Avulso (sem item de Pedido) — obrigatórios quando não há codauto.
    # `codagenda` identifica o agendamento avulso ao REAGENDAR/editar (criado
    # direto da grade, sem AGENDA_PEDIDO) — None numa criação nova.
    codagenda: Optional[int] = None
    cliente: Optional[int] = None
    servico: Optional[str] = None
    valor: Optional[float] = None  # só avulso; do item de Pedido vem de p_venda
    # Campos do atendimento em si (13 estados — ver FrmAtende.frm Form_Load).
    situacao_atendimento: Optional[str] = None  # default "Confirmado" na criação
    revisao: Optional[bool] = False  # "Revisão"(Clínica)/"Garantia"(Assistência) — zera o valor
    descartavel_valor: Optional[float] = None
    descartavel_obs: Optional[str] = None
    hora_chegada: Optional[str] = None
    hora_saida: Optional[str] = None
    # Confirmação de gerente/supervisor/master (AuthorizationSlide, frontend)
    # — obrigatória pra editar atendimento já "Atendido"/"Desistência".
    autorizado_por: Optional[str] = None
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class TrocarProfissionalRequest(BaseModel):
    servidor: str
    banco: str
    novo_funcionario: int
    autorizado_por: str  # nome_guerra/usuário de quem autorizou (AuthorizationSlide)
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class FaturarAgendaAvulsoRequest(BaseModel):
    servidor: str
    banco: str
    forma_pag: str
    classe: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    plataforma: Optional[str] = None


class FecharRequest(BaseModel):
    """Fechar (situação = 'F') um Pedido ou O.S. Reutilizado por ambos."""
    servidor: str
    banco: str
    classe: Optional[int] = None    # grupo do usuário (para validar permissão SITUACAO; também usado no log de auditoria)
    master: Optional[bool] = False  # KONTACTO/master ignora checagem de permissão
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


class FaturarOSRequest(FecharRequest):
    """Faturar uma O.S. — estende `FecharRequest` com a escolha de bloco
    quando a O.S. tem itens Cliente paga (situação=0) E Garantia/Interno/
    Contrato (situação<>0) pendentes ao mesmo tempo (ver
    `os_service._faturar_os_sync`). `None`/omitido = decide sozinho quando
    não há ambiguidade (só um dos 2 blocos tem valor pendente); com os 2
    blocos pendentes E nenhum valor aqui, o backend responde
    `needs_choice=True` em vez de faturar, pedindo pra tela perguntar ao
    usuário — mesmo efeito da tela de escolha bloqueante do legado
    (`Frame5`/`Check3`/`Check5`, `Command2_Click`)."""
    faturar_bucket: Optional[str] = None  # "cliente" | "garantia" | "ambos"


class TelefoneInput(BaseModel):
    ddd: Optional[str] = ""
    tel: Optional[str] = ""
    descricao: Optional[str] = ""


class EnderecoInput(BaseModel):
    tipo: int = 0  # 0=Comercial, 1=Cobrança, 2=Entrega
    cep: Optional[str] = ""
    endereco: Optional[str] = ""
    numero: Optional[int] = None
    complemento: Optional[str] = ""
    bairro: Optional[str] = ""
    cidade: Optional[str] = ""
    uf: Optional[str] = ""


class ContatoInput(BaseModel):
    """Pessoa de contato do cliente (tabela `cliente_contato`) — entidade
    separada dos telefones do cliente (`cliente_tel`, aba Dados Principais)."""
    contato: Optional[str] = ""
    setor: Optional[str] = ""
    cargo: Optional[str] = ""
    ddd: Optional[str] = ""
    telefone: Optional[str] = ""
    ddd_fax: Optional[str] = ""
    fax: Optional[str] = ""
    ddd_celular: Optional[str] = ""
    celular: Optional[str] = ""
    e_mail: Optional[str] = ""
    sexo: Optional[str] = ""


class ClienteSaveRequest(BaseModel):
    servidor: str
    banco: str
    cgc_cpf: Optional[str] = ""
    nome: str
    e_mail: Optional[str] = ""
    inscre: Optional[str] = ""
    tipo: Optional[str] = ""           # FK string para tipo_cliente.codigo
    aceita_email: bool = False
    vendedor: Optional[int] = None     # funcionarios.codigo_int do usuário logado
    usuario_cadastro: Optional[int] = None
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None       # grupo do usuário — só contexto pro log de auditoria
    plataforma: Optional[str] = None   # "web"/"android"/"ios" — só pro log de auditoria

    # ---- Dados Principais (legado Frame9) ----
    nome_fantasia: Optional[str] = ""
    sexo: Optional[str] = ""              # CPF apenas
    data_nasc: Optional[str] = None       # ISO YYYY-MM-DD; CPF=data nasc, CNPJ=data abertura
    inscr_mun: Optional[str] = ""         # CNPJ apenas (distinto de inscre/Insc. Estadual)
    site: Optional[str] = ""
    historico: Optional[str] = ""
    situacao: Optional[str] = "A"         # 'A' Ativo / 'I' Inativo
    status: Optional[str] = ""            # FK situacao.codigo (STATUS_CLIENTE)
    inativo_em: Optional[str] = None      # ISO YYYY-MM-DD (DB column DATA_ENCERRAMENTO_CLIENTE)

    # ---- Dados Secundários (legado Frame11) ----
    contato: Optional[str] = ""                        # nome do contato principal (texto único)
    limite_credito: Optional[float] = None
    desconto: Optional[float] = None                    # desconto global do cliente
    regime_tributario: Optional[int] = None             # crt
    credita_icms: bool = False                          # legenda legada "Não Contribuinte"
    consumidor_final: bool = False
    tributa_iss_fora_municipio: bool = False
    fatura_para: bool = False                           # checkbox "Fatura Para"
    cliente_principal: Optional[int] = None             # FK cliente.codigo (DB column `faturar`)
    prazo_faturamento: Optional[int] = None
    indpres: Optional[str] = ""                         # indicador de presença (NFC-e/NFe)
    canal_aquisicao_cliente: Optional[int] = None
    dia_contato: Optional[int] = None                   # FK dia_semana
    dia_entrega: Optional[int] = None                   # FK dia_semana.dia
    forma_pagamento: Optional[str] = ""                 # FK forma_pagamento.codigo (DB column forma_pag, nvarchar(3))
    segmento: Optional[str] = ""                        # FK segmentos.codigo (nvarchar(3))
    rota: Optional[int] = None
    regiao: Optional[int] = None
    email_cobranca: Optional[str] = ""
    email_nfe: Optional[str] = ""
    centro_custo_cliente: Optional[int] = None
    conta_transf_caixa: Optional[int] = None
    cobra_tarifa_bancaria: bool = False
    tipo_cobranca_tarifa: Optional[str] = ""            # 'B' Boleto / 'N' NFe (coluna nvarchar(1))
    valor_frete: Optional[float] = None
    classe_caixa: Optional[int] = None
    sub_classe_caixa: Optional[int] = None


class ClienteCreateRequest(ClienteSaveRequest):
    enderecos: List[EnderecoInput] = Field(default_factory=list)
    telefones: List[TelefoneInput] = Field(default_factory=list)
    contatos: List[ContatoInput] = Field(default_factory=list)


# ---------------- Envio de Equipamentos para Terceiros (retifica) ----------------
# Migração de `FrmManRet.frm` ("Envio de Equipamentos para Terceiros") —
# tabela `retifica` já existente no schema (compartilhada com o legado VB6).
# `cliente`/`fornecedor` são gravados como texto (nvarchar) na tabela mesmo
# representando códigos numéricos (`cliente.codigo`/`fornecedor.codigo_int`)
# — mantido assim de propósito, mesma tabela do legado, sem migração de
# schema. Ver PENDENCIAS.md > "Envio para Terceiros" pro rastreio completo.
class RetificaSaveRequest(BaseModel):
    servidor: str
    banco: str
    os: int                                # FK os.codigo
    marca: Optional[str] = ""              # FK marcas.codigo (3 chars)
    modelo: Optional[str] = ""             # FK modelos.codigo (3 chars)
    cliente: int                           # cliente.codigo
    fornecedor: int                        # fornecedor.codigo_int — "Terceiro"
    numero_de_serie: str
    entrada: str                           # ISO date — data de ENVIO ao terceiro
    valor: Optional[float] = 0
    obs: Optional[str] = ""
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class RetificaRetornoRequest(BaseModel):
    """Marca o retorno do equipamento (Command3_Click, "Retorno/Terceiro")
    — grava `saida` (data de RETORNO, nome de coluna legado) e permite
    reajustar o valor cobrado pelo terceiro."""
    servidor: str
    banco: str
    saida: str                             # ISO date — data de RETORNO do terceiro
    valor: Optional[float] = None
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class PontuacaoSaveRequest(BaseModel):
    """Pontuação de Técnicos por item da O.S. (migração do frame
    "Pontuação"/Command4_Click em `frmtraosa.frm`) — nota de 0 a 999
    (mesma máscara "999" de 3 dígitos do legado) pro Executor ("Técnico"
    na tela), Vendedor e Atendente daquele item. `os_produto.Pontuacao_A/
    E/V`, já existentes no schema."""
    servidor: str
    banco: str
    pontuacao_e: Optional[int] = None      # Executor ("Técnico" na tela)
    pontuacao_v: Optional[int] = None      # Vendedor
    pontuacao_a: Optional[int] = None      # Atendente (da O.S., mesmo valor em todo item)
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class AlterarExecutorRequest(BaseModel):
    """Alteração de Executor/Vendedor pós-fechamento (migração do botão
    `CmdAltExec`/branch F-PG de `CmDaltera_Click`, `FrmTraOsNew.frm`) —
    corrige o técnico executor (e o vendedor) de um item já lançado depois
    que a O.S. foi Fechada ou Faturada, sem reabrir a O.S. Preço/
    quantidade/desconto continuam bloqueados nessa situação (isso usa a
    edição normal do item, exclusiva de O.S. Aberta). Campos de comissão
    do legado (`ITEM_COMISSAO_VENDEDOR/EXECUTOR`, `movimentacao.
    item_paga_comissao`, `MOVIMENTACAO.VENDEDOR` via `COMANDA_OS`) não têm
    equivalente aqui — esta migração ainda não tem nenhum módulo de
    comissão implementado, ver PENDENCIAS.md > "O.S. Completa" >
    "Alteração de Executor pós-fechamento"."""
    servidor: str
    banco: str
    vendedor: Optional[int] = None   # None = não alterar
    executor: Optional[int] = None   # None = não alterar
    # Propaga a troca pros demais itens da MESMA O.S. que tinham o MESMO
    # executor/vendedor anterior — mesmo comportamento do legado (lá eram
    # 2 perguntas separadas, "Deseja Alterar os demais executores?"/
    # "...vendedores?"; aqui é uma única flag pros dois, simplificação de
    # UX — o frontend confirma com o usuário antes de mandar True).
    propagar_demais: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class AutorizacaoItensRequest(BaseModel):
    """Autorização/Expedição de Itens (migração da aba "Autorização de
    Itens" em `FrmTraOsNew.frm`) — usado pelas 4 ações (Autorizar/Remover
    Autorização/Autorização de Expedição/Remover Autorização de Expedição),
    sempre em lote (o legado permite marcar vários itens de uma vez via
    checkbox na lista)."""
    servidor: str
    banco: str
    cod_os_prod: List[int]
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class OSTempoSaveRequest(BaseModel):
    """Tempo Gasto por Serviço (migração do frame "Tempo Gasto",
    Command30_Click, em Revenda\\FrmTraOsNew.frm — a única cópia com essa
    feature de fato implementada, ver PENDENCIAS.md > "Tempo Gasto por
    Serviço"). Lançamento de início/fim de atendimento por serviço +
    técnico, tabela `os_tempo` (já existente no schema — referenciada em
    `funcionarios_service.py` como guard de integridade, nunca tinha CRUD
    próprio até agora). Tempo gasto (minutos) é sempre DERIVADO
    (hora_fim - hora_inicio), nunca persistido — mesmo comportamento do
    legado, que recalcula na hora em vez de gravar uma coluna própria."""
    servidor: str
    banco: str
    codigo_interno: str              # servicos.codigo do serviço atendido
    funcionario: Optional[int] = None  # funcionarios.codigo_int — Técnico
    data: str                       # yyyy-mm-dd
    hora_inicio: str                # HH:MM
    hora_fim: Optional[str] = None  # HH:MM — opcional
    obs: Optional[str] = ""
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class ProjetosListRequest(BaseModel):
    servidor: str
    banco: str
    search: Optional[str] = ""       # nome/fantasia do cliente
    situacao: Optional[str] = ""     # "A" | "F" | "C" | "" (todas)
    responsavel: Optional[int] = None
    page: int = 1
    size: int = 20


class ProjetoSaveRequest(BaseModel):
    """Cabeçalho de Projeto (migração de `frmgespro.frm` — Gestor de
    Projetos, Fase 1, 2026-08-02). `data_abertura` NÃO faz parte deste
    request — é gravada pelo backend via `GETDATE()` na criação, mesmo
    padrão de `hora_entrada` em O.S./`data_entrada` em Pedido (não confiar
    num campo de data de abertura editável pelo cliente). Mesma decisão
    pra `data_termino` ("Finalizado em" no legado) — gravada pelo backend
    quando o projeto é Finalizado (`_finalizar_projeto_sync`), não editável
    aqui."""
    servidor: str
    banco: str
    cliente: int                          # cliente.codigo
    responsavel: Optional[int] = None     # funcionarios.codigo_int
    data_inicio: Optional[str] = None     # yyyy-mm-dd
    data_prevista: Optional[str] = None   # yyyy-mm-dd
    detalhes: Optional[str] = ""
    # Valores ESTIMADOS do projeto (`Campo(7)/(8)/(9)` do legado,
    # `Command14_Click` — achado só ao rastrear a Fase 2 "Ajustar Valores",
    # que lê esses campos como a base de comparação "estimado vs. já
    # coberto por documento" — não fazia parte do Gravar da Fase 1 por
    # engano). `valor_projeto` é sempre a soma, gravado pelo backend (não
    # aceito do cliente) — mesmo comportamento de `Campo(7) = Campo(8) +
    # Campo(9)` no `Campo_LostFocus` do legado.
    valor_produtos: Optional[float] = 0
    valor_servicos: Optional[float] = 0
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class ProjetoDocumentoRequest(BaseModel):
    """Vincular/desvincular um documento (Pedido/O.S./Requisição) a um
    Projeto — migração de `AdicionaDocumento`/`Documentos2_KeyDown` (F4)
    em `frmgespro.frm`. Sem `tipo_doc='ORC'` — ver CLAUDE.md > "Regras
    Globais de Pré-venda": um Pedido com `situacao='A'` já cumpre o papel
    de Orçamento, não é um tipo de documento à parte."""
    servidor: str
    banco: str
    tipo_doc: str   # "PED" | "OSS" | "REQ"
    num_doc: int
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class ProjetoDocumentoKey(BaseModel):
    tipo_doc: str   # "PED" | "OSS" (nunca "REQ" — sem preço de venda ao cliente)
    num_doc: int


class CheckoutAbrirRequest(BaseModel):
    """Abre uma venda direta nova (Checkout — migração de FrmPafOFF.frm,
    "Emissão de Cupom Fiscal"/PDV). Diferente do legado (que só cria a linha
    em `comanda` na inclusão do 1º item, `Vende_Item`/"gera comanda no
    primeiro item"), esta migração cria o cabeçalho `comanda` (situacao='A')
    já na abertura da tela — mesmo padrão já usado por Pedido/O.S.
    (`POST /pedidos/create`), mais adequado a uma API stateless/SPA do que
    depender de "isso é o 1º item?" implícito no fluxo."""
    servidor: str
    banco: str
    atendente: int  # funcionarios.codigo_int logado
    cliente: Optional[int] = None  # None = "Clientes Diversos" (mesmo fallback do legado)
    area_atuacao: Optional[int] = 0
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    master: Optional[bool] = False
    plataforma: Optional[str] = None


class CheckoutClienteRequest(BaseModel):
    servidor: str
    banco: str
    cliente: Optional[int] = None  # None = volta pra "Clientes Diversos"
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutItemRequest(BaseModel):
    """Adicionar item ao Checkout — réplica simplificada de `Vende_Item`
    (busca produto/serviço por código interno/fábrica/barras, aplica
    promoção/preço por quantidade, grava `movimentacao` tipo S01/CM).
    Desconto/acréscimo do item podem vir já neste mesmo request (o legado
    faz em 2 passos — inclui o item, depois abre `FrmDescItem` — aqui é 1
    só, mais direto pra uma tela web)."""
    servidor: str
    banco: str
    codigo: str          # código digitado (interno, fábrica, barras ou serviço)
    qtd: float = 1
    vendedor: Optional[int] = None
    funcao: Optional[int] = None  # 1=gerente,2=supervisor,3=vendedor (p/ validar limite de desconto do item)
    desconto_percentual: Optional[float] = 0
    acrescimo_percentual: Optional[float] = 0
    # Bypass de limite de desconto (senha de gerente/supervisor — mesmo
    # padrão de AuthorizationSlide já usado em outras telas do projeto):
    # código do funcionário que autorizou, quando o desconto pedido excede
    # o limite do próprio vendedor.
    autorizado_por: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutCancelarItemRequest(BaseModel):
    servidor: str
    banco: str
    autorizado_por: Optional[int] = None  # senha superior — cancelamento de item também exige (mesmo padrão do legado)
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutDescontoGeralRequest(BaseModel):
    """Desconto Geral da Venda (`FrmDescGeral`/`ProcessaDescontoGeral`) —
    redistribui percentualmente entre os itens não cancelados."""
    servidor: str
    banco: str
    desconto_percentual: float = 0
    funcao: Optional[int] = None  # 1=gerente,2=supervisor,3=vendedor (p/ validar limite geral, controle.desconto_pdv_*)
    autorizado_por: Optional[int] = None
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutFormaPagamentoItem(BaseModel):
    tipo: str        # DI/CH/CC/CD/DU/TI/VA/FI
    forma_pag: str   # forma_pagamento.codigo
    valor: float
    vencimento: Optional[str] = None
    # Cheque
    cod_banco: Optional[int] = None
    agencia: Optional[int] = None
    conta: Optional[str] = None
    numero_ch: Optional[int] = None
    nome_cheque: Optional[str] = None
    telefone: Optional[str] = None
    # Cartão crédito/débito
    num_cartao1: Optional[int] = None
    num_cartao2: Optional[int] = None
    num_cartao3: Optional[int] = None
    num_cartao4: Optional[int] = None
    mes_validade: Optional[int] = None
    ano_validade: Optional[int] = None
    parcelas: Optional[int] = None
    cod_administradora: Optional[int] = None
    cod_parcelador: Optional[str] = None  # "L" Loja | "A" Administradora


class CheckoutFecharRequest(BaseModel):
    """Fechamento da venda (`Command4_Click`/`FinalizaVenda`) — 1+ formas de
    pagamento, gravadas fielmente nas tabelas legadas `comanda_dinheiro`/
    `comanda_cheque`/`comanda_cartao`/`comanda_debito`/`comanda_duplicata`/
    `comanda_ticket`/`comanda_vale`/`comanda_financiado` (decisão explícita
    do usuário — ver PENDENCIAS.md > "Checkout")."""
    servidor: str
    banco: str
    formas: List[CheckoutFormaPagamentoItem]
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutCancelarVendaRequest(BaseModel):
    servidor: str
    banco: str
    motivo: Optional[str] = ""
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class CheckoutImportarDavRequest(BaseModel):
    """Importar Pedido/O.S. como DAV pro Checkout (`Insere_Dav`, FrmPafOFF.frm
    — F4/F8; F7/Orçamento colapsa em "PED" nesta migração, ver CLAUDE.md >
    "Regras Globais de Pré-venda"). `documento` já precisa estar Fechado
    (situação 'F') — mesma exigência do legado, sem atalho de fechar
    automaticamente."""
    servidor: str
    banco: str
    tipo_dav: str  # "PED" | "OS"
    documento: int
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None


class ProjetoAjustarValoresRequest(BaseModel):
    """"Ajustar Valores" (Fase 2, migração de `Reprocessa`/`RecalculaDAVS`/
    `Descontos_Acrescimos` em `frmgespro.frm`) — define um novo total-alvo
    pra Produtos OU Serviços do projeto; o backend redistribui
    desconto/acréscimo proporcionalmente entre os itens dos documentos
    SELECIONADOS (`documentos`) pra bater esse valor. `documentos` é a
    lista de Pedido/O.S. que participam desta passada — no legado, todo
    documento elegível (situação Aberta/Fechada, não Requisição) nasce
    pré-marcado, mas o usuário pode desmarcar algum antes de confirmar;
    aqui o frontend manda a lista final já filtrada, sem meio-termo
    "desmarcar item individual dentro de um documento" — ver PENDENCIAS.md
    > "Gestor de Projetos" > "Fase 2" pro porquê dessa simplificação."""
    servidor: str
    banco: str
    tipo: str  # "P" (Produtos) | "S" (Serviços)
    novo_valor: float
    documentos: List[ProjetoDocumentoKey]
    master: Optional[bool] = False
    usuario_alteracao: Optional[int] = None
    classe: Optional[int] = None
    plataforma: Optional[str] = None
