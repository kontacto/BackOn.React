// Persiste a última configuração de opções da tela Curva ABC e Estoques
// (app/curva-abc.tsx) por empresa+banco — pedido explícito do usuário,
// 2026-07-20 ("salve as configurações de opções setadas, inclusive faixas
// para um próximo processamento"). Mesmo padrão de pedidosFilters.ts/
// mlFilters.ts.
//
// Datas (De/Até) e o preset de período NÃO são persistidos — mesmo
// princípio já usado em pedidosFilters.ts (datas sempre voltam ao default
// da tela, nunca ficam "presas" numa seleção antiga); só as opções de
// configuração propriamente ditas (tipo de classificação, nível, faixas,
// grau de atendimento, o que atualizar).
import AsyncStorage from "./asyncStorageCompat";

const PREFIX = "curva_abc_config::";

export type Faixa = { curva: string; percentual: string };

export type CurvaAbcSavedConfig = {
  g1Tipo: "financeira" | "quantidade";
  g1NivelCodigo: string | null;
  g1NivelLabel: string | null;
  faixas: Faixa[];
  grauAtendimento: string;
  r1NivelCodigo: string | null;
  r1NivelLabel: string | null;
  atualizarMinimo: boolean;
  atualizarRessuprimento: boolean;
  atualizarMaximo: boolean;
  atualizarConsumo: boolean;
};

export function curvaAbcConfigKey(empresa?: string | null, banco?: string | null): string {
  return `${PREFIX}${empresa || "_"}__${banco || "_"}`;
}

export async function saveCurvaAbcConfig(key: string, data: CurvaAbcSavedConfig): Promise<void> {
  try {
    await AsyncStorage.setItem(key, JSON.stringify(data));
  } catch {
    // ignora falha de persistência
  }
}

export async function loadCurvaAbcConfig(key: string): Promise<CurvaAbcSavedConfig | null> {
  try {
    const raw = await AsyncStorage.getItem(key);
    return raw ? (JSON.parse(raw) as CurvaAbcSavedConfig) : null;
  } catch {
    return null;
  }
}
