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
};

export type ItemRow = {
  codauto: number; produto: string; tipo: "P" | "S" | "?";
  descricao: string; complemento: string; cod_fab: string; unidade: string;
  qtd: number; p_normal: number; valor_unitario: number; desconto: number; acrescimo: number; total: number;
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
