// Tipos compartilhados das telas de pedido.

export type ClienteRow = {
  codigo: number; nome: string; cgc_cpf: string; telefone: string;
  // Tipo do cliente (Mesa/Comanda/Balcão/Entrega/...) — só vem preenchido
  // pela busca do Painel de Pedidos (`GET /api/clientes/find/search`);
  // omitido em construções locais de ClienteRow que não vêm dessa busca.
  tipo_cliente_descricao?: string;
  // Código numérico do tipo do cliente (cliente.cliente_forn, FK
  // tipo_cliente.codigo) — mesma busca acima; usado pra pré-preencher o
  // combobox "Tipo" do Pedido (cadastro) ao carregar um cliente, pedido
  // explícito do usuário, 2026-07-17. `null`/ausente = cliente sem tipo.
  tipo_cliente_codigo?: number | null;
};

export type ClienteResumo = {
  codigo: number; nome: string; cgc_cpf: string; e_mail: string;
  telefone: string; endereco: string;
};

export type AreaAtuacao = { codigo: number; descricao: string };

export type Funcionario = { codigo: number; nome: string; nome_guerra: string; cod_funcao: string };

export type PedidoData = {
  pedido: number; cliente: number | null; cliente_nome: string; cliente_cgc: string;
  data: string | null; validade: string | null;
  vendedor: number | null; vendedor_nome: string;
  hora_aberto: string; obs: string; situacao: string; situacao_label: string; total: number;
  area_atuacao: number | null; area_descricao: string;
  // Entrega (pedido_venda.previsao_entrega/hora_entrega/pedido_entregue) —
  // "Entrega ... às ..." + checkbox "Pedido Entregue" do Pedido Bar.
  previsao_entrega: string | null; hora_entrega: string; pedido_entregue: boolean;
  // Forma de pagamento — combobox simples (1 forma) do cabeçalho.
  forma_pag: string; forma_pag_descricao: string;
  // Localização (mesa/balcão) — pedido_venda.LOCALIZACAO, exibida no recibo.
  localizacao_descricao: string;
  // Qtd. de pessoas na mesa/comanda/balcão (Painel de Pedidos) — usada só
  // pra dividir o valor total na impressão da conta. null = não informado.
  qtd_pessoas: number | null;
  // Combobox "Tipo" do Pedido Bar (pedido_venda.tipo, FK tipo_cliente.codigo)
  // — tipo do PEDIDO, separado do tipo do CLIENTE (cliente.cliente_forn).
  // null = sem tipo próprio, a listagem cai pro tipo do cliente.
  // `tipo_descricao` já vem resolvido (pedido ou, na falta, cliente).
  // Pedido explícito do usuário, 2026-07-18.
  tipo: number | null; tipo_descricao: string;
  // Campo livre "Referência" — reaproveita pedido_venda.num_ped_cliente (já
  // existente na tabela, já exposto no Pedido Completo como "Nº Pedido do
  // Cliente"); no Pedido Bar também guarda o nº do pedido original ao
  // Dividir Pedido (pedido explícito do usuário, 2026-07-17).
  referencia: string;
  // Outros pedidos da MESMA divisão (mesma mesa) — calculado pela raiz (o
  // pedido original), não importa se este aqui é a raiz ou um filho, então
  // a lista fica igual em qualquer um dos pedidos da divisão. Mostrados na
  // tela pra permitir abrir/faturar cada um sem perder a referência da
  // mesa até o fechamento total de todos eles (pedido explícito do
  // usuário, 2026-07-17).
  pedidos_relacionados: { pedido: number; situacao: string; situacao_label: string; total: number }[];
};

export type ItemRow = {
  codauto: number; produto: string; tipo: "P" | "S" | "?";
  descricao: string; complemento: string; cod_fab: string; unidade: string;
  qtd: number; p_normal: number; valor_unitario: number; desconto: number; acrescimo: number; total: number;
  // Data/hora de inclusão do item no pedido (pedido_venda_prod.data_inclusao_item/
  // hora_inclusao_item) — ISO "yyyy-mm-dd" e "HH:MM:SS", "" se ainda não gravado.
  data_inclusao: string | null; hora_inclusao: string;
  // Finalidade do produto (pecas.tipo_peca -> tipo_peca.descricao;
  // "" pra serviço ou produto sem Finalidade definida) — rótulo no ticket
  // de impressão de item (ReciboPedidoModal em modo item).
  finalidade_descricao: string;
};

// Dados mínimos pro ticket de impressão de um item só (ReciboPedidoModal
// em modo item) — ItemRow satisfaz esse shape (superset), usado tanto pelo
// botão manual "Imprimir" de cada linha quanto pelo disparo automático por
// Finalidade (que só tem o item recém-incluído, não o ItemRow completo).
export type ItemPrintData = {
  codauto: number; produto: string; tipo: "P" | "S" | "?";
  descricao: string; complemento: string; cod_fab: string; unidade: string; qtd: number;
  finalidade_descricao: string;
};

export type ProdutoServico = {
  tipo: "P" | "S"; codigo: string; descricao: string; valor: number;
  estoque: number | null; cod_fab?: string; unidade?: string;
};

export type DescontoRow = {
  cod: number; tipo_desconto: string; tipo_label: string; descricao: string;
  percentual: number; valor_unitario: number; qtd: number; valor_total: number; usuario: number;
};

export type ToastTone = "info" | "error" | "success";
