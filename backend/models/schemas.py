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
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    classe: Optional[int] = None             # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


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
    sequencia: int


class FormaPagamentoDeleteRequest(BaseModel):
    servidor: str
    banco: str
    tipo_dav: str = "PED"
    tela: Optional[str] = None
    tipo: str
    sequencia: int
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
    obs: Optional[str] = ""
    area_atuacao: Optional[int] = None  # area_atuacao.area (FK)
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    classe: Optional[int] = None             # grupo do usuário — só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria


class FecharRequest(BaseModel):
    """Fechar (situação = 'F') um Pedido ou O.S. Reutilizado por ambos."""
    servidor: str
    banco: str
    classe: Optional[int] = None    # grupo do usuário (para validar permissão SITUACAO; também usado no log de auditoria)
    master: Optional[bool] = False  # KONTACTO/master ignora checagem de permissão
    usuario_alteracao: Optional[int] = None  # só pro log de auditoria
    plataforma: Optional[str] = None         # "web"/"android"/"ios" — só pro log de auditoria



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
