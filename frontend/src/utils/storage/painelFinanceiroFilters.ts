// Persiste a última seleção de filtros do Painel Financeiro (app/
// painel-financeiro.tsx — abas Painel de Movimentações e Previsões) por
// empresa+banco — pedido explícito do usuário, 2026-08-31 ("gravar filtro
// para próximo acesso"). Mesmo padrão de src/utils/storage/pedidosFilters.ts.
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "painel_financeiro_filtros::";

export type PainelFinanceiroSavedFilters = {
  contaFiltro: number | null;
  periodo: string;
  mesRef: string;
  partirDeHoje: boolean;
  desconsiderarPendencias: boolean;
  prevContaFiltro: number | null;
  tipoFiltro: number | null;
  filtroData: string;
  prevMesRef: string;
  relContaFiltro: number | null;
};

export function painelFinanceiroFiltrosKey(empresa?: string | null, banco?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}`;
}

export async function savePainelFinanceiroFiltros(key: string, data: PainelFinanceiroSavedFilters): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadPainelFinanceiroFiltros(key: string): Promise<PainelFinanceiroSavedFilters | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as PainelFinanceiroSavedFilters) : null;
  } catch {
    return null;
  }
}
