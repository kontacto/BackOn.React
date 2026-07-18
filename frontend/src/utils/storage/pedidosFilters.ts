// Persiste a última seleção de filtros da lista de Pedidos (app/pedidos.tsx)
// por empresa+banco — pedido explícito do usuário, 2026-07-17. Mesmo padrão
// de src/utils/storage/mlFilters.ts (relatório de Margem de Lucro).
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "pedidos_filtros::";

export type PedidosSavedFilters = {
  situacao: string;
  vendedor: string | number | null;
  dataIni: string | null;
  dataFim: string | null;
  tiposClienteSel: number[];
  dataEntrega: string | null;
  ordenarPor: string | null;
};

export function pedidosFiltrosKey(empresa?: string | null, banco?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}`;
}

export async function savePedidosFiltros(key: string, data: PedidosSavedFilters): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadPedidosFiltros(key: string): Promise<PedidosSavedFilters | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as PedidosSavedFilters) : null;
  } catch {
    return null;
  }
}
