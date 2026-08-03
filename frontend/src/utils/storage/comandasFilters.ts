// Persiste a última seleção de filtros do Gestor de Comandas
// (app/gestor-comandas.tsx) por empresa+banco — mesmo padrão de
// pedidosFilters.ts/mlFilters.ts. Período (data de/até) NUNCA é
// restaurado — sempre nasce em "hoje", pedido explícito do usuário
// (mesma regra já usada em pedidosFilters.ts).
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "comandas_filtros::";

export type ComandasSavedFilters = {
  comNota: boolean;
  semNota: boolean;
  ordenarPor: "venda" | "cliente";
};

export function comandasFiltrosKey(empresa?: string | null, banco?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}`;
}

export async function saveComandasFiltros(key: string, data: ComandasSavedFilters): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadComandasFiltros(key: string): Promise<ComandasSavedFilters | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as ComandasSavedFilters) : null;
  } catch {
    return null;
  }
}
