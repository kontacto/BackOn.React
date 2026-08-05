// Persiste a configuração local de Impressão Silenciosa (computador +
// impressora desta estação) por empresa+banco — mesmo padrão de
// pedidosFilters.ts/mlFilters.ts. Usada pelo Checkout (e futuras telas) pra
// decidir se o botão "Imprimir" deve enfileirar direto pro agente local
// (print-agent/) em vez de abrir o preview + diálogo do navegador.
//
// É local por navegador/estação de propósito: não existe hoje nenhum jeito
// confiável do browser saber seu próprio hostname — ver PENDENCIAS.md >
// "Impressão Silenciosa — Fila + Agente Local" pro contexto completo dessa
// decisão.
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "impressao_silenciosa::";

export type ImpressaoSilenciosaConfig = {
  computador: string;
  impressora: string;
};

export function impressaoSilenciosaKey(empresa?: string | null, banco?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}`;
}

export async function saveImpressaoSilenciosaConfig(key: string, data: ImpressaoSilenciosaConfig): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadImpressaoSilenciosaConfig(key: string): Promise<ImpressaoSilenciosaConfig | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as ImpressaoSilenciosaConfig) : null;
  } catch {
    return null;
  }
}

export async function clearImpressaoSilenciosaConfig(key: string): Promise<void> {
  try {
    await AsyncStorage.removeItem(key);
  } catch {
    // ignora falha de persistência
  }
}
