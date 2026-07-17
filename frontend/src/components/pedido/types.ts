// Tipos compartilhados das telas de pedido.

export type ClienteRow = { codigo: number; nome: string; cgc_cpf: string; telefone: string };

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
