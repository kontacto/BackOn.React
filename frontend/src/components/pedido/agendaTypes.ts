// Superfície mínima que `AgendarModal.tsx` precisa do hook de itens (Pedido
// OU O.S.) — extraída pra permitir reaproveitar o MESMO modal (Anexos,
// Layouts, Troca de Profissional, Garantia — tudo incluso) sem duplicar
// ~440 linhas de UI, mesmo princípio já usado em `ItemList.tsx`'s
// `ItemListItens`/`GeneralDiscountModal`/`DiscountsReportModal`. Tanto
// `UsePedidoItens` (retorno de `usePedidoItens.ts`) quanto `UseOSItens`
// (retorno de `os/useOSItens.ts`) satisfazem este tipo automaticamente —
// são supersets, nenhuma mudança precisou ser feita nos dois hooks além de
// implementar estes campos de verdade (o de O.S. era só um no-op antes).
import { Connection } from "@/src/utils/storage/connections";
import { ItemRow } from "./types";

export type AgendaSalvarPayload = {
  funcionario: number;
  data: string;
  hora_ini: string;
  situacao_atendimento?: string;
  revisao?: boolean;
  descartavel_valor?: number | null;
  descartavel_obs?: string;
  hora_chegada?: string | null;
  hora_saida?: string | null;
  autorizado_por?: string;
};

export type AgendaItens = {
  conn: Connection | null;
  agendarItem: ItemRow | null;
  setAgendarItem: (item: ItemRow | null) => void;
  profissionaisAgenda: { codigo: number; nome_guerra: string }[];
  profissionaisLoading: boolean;
  agendaSaving: boolean;
  salvarAgendamento: (payload: AgendaSalvarPayload) => unknown;
  cancelarAgendamento: () => unknown;
  trocarProfissionalAgenda: (novoFuncionario: number, autorizadoPor: string) => Promise<boolean>;
};
