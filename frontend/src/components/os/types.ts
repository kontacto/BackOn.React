// Tipos da O.S. Completa — reaproveita `ItemRow` do Pedido pra poder
// reusar `ItemList.tsx` sem alterações (ver `ItemList.tsx`'s `ItemListItens`
// pra o porquê disso ser seguro), estendido com os campos que só existem
// em `os_produto` (chave própria `cod_os_prod`, vendedor+executor POR ITEM
// — diferente do Pedido, que tem um vendedor só no cabeçalho — e Situação/
// Destino do item).
import { ItemRow } from "@/src/components/pedido/types";

export type OSItemRow = ItemRow & {
  cod_os_prod: number;
  vendedor: number | null;
  vendedor_nome: string;
  executor: number | null;
  executor_nome: string;
  // Situação/Destino do item (os_produto.situacao, réplica de `Destino(2)`
  // do legado `FrmTraOsNew.frm`) — 0=Cliente paga, 1=Garantia, 2=Interno,
  // 3=Contrato. Decide em qual bloco de totais (ver OSTotaisResumo.tsx) o
  // item entra.
  situacao: number;
  // Pontuação de Técnicos (os_produto.Pontuacao_A/E/V, réplica do frame
  // "Pontuação" em `frmtraosa.frm`) — nota 0-999 do Executor ("Técnico" na
  // tela)/Vendedor/Atendente daquele item. `null` = ainda não pontuado.
  pontuacao_e: number | null;
  pontuacao_v: number | null;
  pontuacao_a: number | null;
  // Autorização/Expedição de Itens (os_produto.usuario_autorizacao/
  // data_autorizacao/.../usuario_expedicao/data_expedicao, réplica da aba
  // "Autorização de Itens" em `FrmTraOsNew.frm`, Revenda). `data_*` nulo =
  // ainda não autorizado/expedido — é o que decide o estado do item nos
  // botões de ação (ver `AutorizacaoItensModal.tsx`).
  usuario_autorizacao: number | null;
  usuario_autorizacao_nome: string;
  data_autorizacao: string | null;
  hora_autorizacao: string;
  qtd_autorizada: number;
  usuario_expedicao: number | null;
  usuario_expedicao_nome: string;
  data_expedicao: string | null;
  hora_expedicao: string;
};

export const OS_SITUACAO_ITEM_OPTIONS: { value: number; label: string }[] = [
  { value: 0, label: "Cliente paga" },
  { value: 1, label: "Garantia" },
  { value: 2, label: "Interno" },
  { value: 3, label: "Contrato" },
];

export function osSituacaoItemLabel(v: number): string {
  return OS_SITUACAO_ITEM_OPTIONS.find((o) => o.value === v)?.label || "Cliente paga";
}

export type OSData = {
  codigo: number; cliente: number | null; cliente_nome: string; cliente_cgc: string;
  data: string | null; hora: string; situacao: string; situacao_label: string; total: number;
  area_atuacao: number | null; area_descricao: string; descricao_cliente: string; obs: string;
  resumo: string; status_os: number | null; atendente: number | null; atendente_nome: string;
  placa: string; marca: string; modelo: string; km: number | null; ano: string;
  chassi: string; numero_de_serie: string;
  forma_pagamento: string; forma_pagamento_descricao: string;
  // Campos extras da O.S. Completa (os_completo_service.get_os_completo).
  referencia_os: string;
  tecnico_responsavel: number | null; tecnico_responsavel_nome: string;
  posicao_os: number | null; tipo_os_descricao: string;
  previsao_termino: string | null; data_termino: string | null;
  hora_entrada: string; hora_fechamento: string;
  status_os_descricao: string;
  // Flags de empresa que decidem se a Autorização de Itens é exigida antes
  // de reservar estoque, e se a Expedição é exigida antes da Autorização
  // (Controle do Sistema > "Exige Autorização de itens O.S."/"Exige
  // Expedição Itens O.S." — controle_aux.exige_aprovacao_itens_os/
  // exige_expedicao_itens_os).
  exige_aprovacao_itens_os: boolean;
  exige_expedicao_itens_os: boolean;
  // Doc. Origem / Revisão Programada (migração de `Campo(150)`/`Campo(151)`/
  // `Option9`/`Option10` em `FrmTraOsNew.frm`) — validação cruzada de OS/
  // Pedido de origem pra O.S. do tipo Garantia/Revisão. Flags decidem se os
  // campos aparecem habilitados pro Tipo O.S. atual (controle_aux.
  // ControlaRevisaoOS/EXIGE_OS_ORIGINAL_GARANTIA); `os_original`/
  // `tipo_doc_original` são os valores já gravados (preenchem o formulário
  // ao reabrir a O.S.); `revisoes_programadas` são as datas futuras geradas
  // por ESTA O.S. via `qtd_revisoes` (disponíveis ou já consumidas por
  // outra O.S. de Revisão).
  controla_revisao_os: boolean;
  exige_os_original_garantia: boolean;
  os_original: number | null;
  tipo_doc_original: "O" | "P" | null;
  validou_garantia: boolean;
  qtd_revisoes: number | null;
  revisoes_programadas: { sequencia: number; data: string; consumida_por: number | null }[];
  // Bifurcação de faturamento Garantia×Cliente (`GeraComanda`, branch "G",
  // `FrmTraOsNew.frm`) — forma de pagamento usada só pra faturar o bloco de
  // itens Garantia/Interno/Contrato (situação<>0), em Comanda separada do
  // bloco Cliente paga (que usa `forma_pagamento` normal).
  forma_pagamento_garantia: string;
  forma_pagamento_garantia_descricao: string;
};
