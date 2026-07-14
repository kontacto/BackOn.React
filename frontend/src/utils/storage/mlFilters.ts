// Persiste as seleções do relatório de Margem de Lucro por usuário + conexão.
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "ml_filtros::";

export type MLSavedFilters = {
  selIds: string[];
  dataIni: string;
  dataFim: string;
  incluirPedidos: boolean;
  incluirOS: boolean;
  incluirComandas: boolean;
  retProdutos: boolean;
  retServicos: boolean;
  sitAbertos: boolean;
  sitFechados: boolean;
  sitFaturados: boolean;
  opOperacional: boolean;
  opGarantias: boolean;
  opVendaDireta: boolean;
  opOsNaoCobrados: boolean;
  area: number;
  nivel: string;
  nivelLabel: string;
  codCliente: number | null;
  clienteNome: string;
};

export function mlKey(empresa?: string | null, banco?: string | null, usuario?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}__${usuario || "_"}`;
}

export async function saveMLFilters(key: string, data: MLSavedFilters): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadMLFilters(key: string): Promise<MLSavedFilters | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as MLSavedFilters) : null;
  } catch {
    return null;
  }
}
