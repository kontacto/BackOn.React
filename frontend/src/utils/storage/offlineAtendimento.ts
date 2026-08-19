// Cache local + fila de sincronização da tela de Atendimento de Campo
// (Assistência Técnica — ver AssistenciaTecnicaCampo.md, "Sincronização
// Offline"). Mesmo padrão de storage já usado no projeto (funções simples
// sobre AsyncStorage, chave `@back_on/...`, sem ORM — ver `pedidosFilters.ts`)
// — decisão explícita do usuário, 2026-08-14: nenhuma dependência de banco
// local nova (`expo-sqlite` etc.), a fila cabe tranquilamente num JSON.
//
// Dois mecanismos distintos, não confundir:
//  - CACHE (por OS): dados pra abrir uma OS já vista antes SEM internet
//    (pré-carregados por `os-lista.tsx` quando a lista é vista online).
//  - FILA (compartilhada): mutações que tentaram gravar e falharam por
//    rede — ficam pendentes até uma sincronização bem-sucedida ou um
//    conflito (ver `versaoAtendimento`/`versao_esperada`).
import AsyncStorage from "./asyncStorageCompat";

const CACHE_PREFIX = "@back_on/atendimento_cache::";
const CACHE_INDEX_KEY = "@back_on/atendimento_cache_index";
const FILA_KEY = "@back_on/atendimento_fila";

export type OSCacheBundle = {
  // Formato solto de propósito (não importa o tipo de os-atendimento.tsx
  // aqui, pra não criar dependência circular tela↔storage) — o
  // consumidor já sabe o formato real.
  os: Record<string, unknown>;
  equipamentos: { codigo: number; equipamento: number | null; numero_de_serie: string; [k: string]: unknown }[];
  historico: Record<string, unknown>[];
  statusOsOptions: { value: number; label: string }[];
  versaoAtendimento: string | null;
  cachedAt: string;
};

export type MutacaoTipo = "checkin" | "checkout" | "fechar" | "equipamento" | "formulario";

export type MutacaoPendente = {
  id: string;
  tipo: MutacaoTipo;
  osId: number;
  itemCodigo?: number; // só usado por tipo "equipamento"
  payload: Record<string, unknown>;
  criadaEm: string;
  tentativas: number;
  // Conflito de versão (bloqueia, exige "Recarregar dados atuais" — ver
  // os-atendimento.tsx). Distinto de `erro` abaixo: aqui o app não sabe
  // resolver sozinho, precisa que o técnico recarregue os dados.
  conflito?: string;
  // Falha de regra de negócio genuína (não é rede, não é conflito de
  // versão) — a mutação NÃO bloqueia o resto da fila (ver `syncFilaOS`),
  // fica marcada aqui pro técnico revisar e descartar manualmente (achado
  // de revisão Gauntlet retroativa, 2026-08-14 — sem isto, uma falha
  // permanente travava a fila inteira daquela OS pra sempre).
  erro?: string;
};

// Retenção do cache local (Leandro/LGPD, mesma revisão) — dado de cliente
// e coordenadas de GPS não deve ficar gravado indefinidamente no aparelho
// do técnico. Só purga bundle SEM fila pendente daquela OS (uma mutação
// ainda não sincronizada continua precisando do `versaoAtendimento`
// cacheado pra checagem de conflito).
const CACHE_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 dias

function novoId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

// ---------------- cache por OS ----------------

export async function cacheOsParaOffline(codigo: number, bundle: Omit<OSCacheBundle, "cachedAt">): Promise<void> {
  try {
    const completo: OSCacheBundle = { ...bundle, cachedAt: new Date().toISOString() };
    await AsyncStorage.setItem(`${CACHE_PREFIX}${codigo}`, JSON.stringify(completo));
    const raw = await AsyncStorage.getItem(CACHE_INDEX_KEY);
    const indice: number[] = raw ? JSON.parse(raw) : [];
    if (!indice.includes(codigo)) {
      indice.push(codigo);
      await AsyncStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(indice));
    }
  } catch {
    // cache é conveniência, nunca deve quebrar o fluxo principal
  }
}

export async function getOsCacheada(codigo: number): Promise<OSCacheBundle | null> {
  try {
    const raw = await AsyncStorage.getItem(`${CACHE_PREFIX}${codigo}`);
    return raw ? (JSON.parse(raw) as OSCacheBundle) : null;
  } catch {
    return null;
  }
}

// Usado pra resolver QR Code/nº de série offline (busca em todo o cache,
// não só numa OS já aberta) — ver os-atendimento.tsx `resolveSerie`.
export async function listarTodasCacheadas(): Promise<{ codigo: number; bundle: OSCacheBundle }[]> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_INDEX_KEY);
    const indice: number[] = raw ? JSON.parse(raw) : [];
    const resultados: { codigo: number; bundle: OSCacheBundle }[] = [];
    for (const codigo of indice) {
      const bundle = await getOsCacheada(codigo);
      if (bundle) resultados.push({ codigo, bundle });
    }
    return resultados;
  } catch {
    return [];
  }
}

// ---------------- fila de mutações pendentes ----------------

async function lerFila(): Promise<MutacaoPendente[]> {
  try {
    const raw = await AsyncStorage.getItem(FILA_KEY);
    return raw ? (JSON.parse(raw) as MutacaoPendente[]) : [];
  } catch {
    return [];
  }
}

async function gravarFila(fila: MutacaoPendente[]): Promise<void> {
  try {
    await AsyncStorage.setItem(FILA_KEY, JSON.stringify(fila));
  } catch {
    // se não conseguir persistir a fila, a mutação fica só na memória
    // desta sessão — melhor que travar a tela
  }
}

export async function enfileirarMutacao(
  m: Pick<MutacaoPendente, "tipo" | "osId" | "payload" | "itemCodigo">,
): Promise<MutacaoPendente> {
  const fila = await lerFila();
  const nova: MutacaoPendente = { ...m, id: novoId(), criadaEm: new Date().toISOString(), tentativas: 0 };
  fila.push(nova);
  await gravarFila(fila);
  return nova;
}

export async function listarFilaPendente(osId?: number): Promise<MutacaoPendente[]> {
  const fila = await lerFila();
  return osId != null ? fila.filter((m) => m.osId === osId) : fila;
}

export async function removerDaFila(id: string): Promise<void> {
  const fila = await lerFila();
  await gravarFila(fila.filter((m) => m.id !== id));
}

export async function marcarConflito(id: string, mensagem: string): Promise<void> {
  const fila = await lerFila();
  await gravarFila(fila.map((m) => (m.id === id ? { ...m, conflito: mensagem } : m)));
}

export async function incrementarTentativa(id: string): Promise<void> {
  const fila = await lerFila();
  await gravarFila(fila.map((m) => (m.id === id ? { ...m, tentativas: m.tentativas + 1 } : m)));
}

// Falha de regra de negócio genuína (ver comentário do campo `erro` acima)
// — distinto de `marcarConflito`, nunca dispara o banner bloqueante.
export async function marcarErro(id: string, mensagem: string): Promise<void> {
  const fila = await lerFila();
  await gravarFila(fila.map((m) => (m.id === id ? { ...m, erro: mensagem } : m)));
}

// ---------------- retenção do cache (LGPD) ----------------

// Apaga bundles cacheados há mais de 7 dias que já não têm nenhuma
// mutação pendente pra aquela OS — chamado por os-lista.tsx sempre que a
// tela carrega com conexão. Best-effort/silencioso: nunca deve interromper
// o carregamento da lista.
export async function purgarCacheExpirado(): Promise<void> {
  try {
    const raw = await AsyncStorage.getItem(CACHE_INDEX_KEY);
    const indice: number[] = raw ? JSON.parse(raw) : [];
    if (indice.length === 0) return;
    const fila = await lerFila();
    const osComFilaPendente = new Set(fila.map((m) => m.osId));
    const agora = Date.now();
    const restante: number[] = [];
    for (const codigo of indice) {
      const bundle = await getOsCacheada(codigo);
      const expirado = !bundle || (agora - new Date(bundle.cachedAt).getTime()) > CACHE_TTL_MS;
      if (bundle && expirado && !osComFilaPendente.has(codigo)) {
        await AsyncStorage.removeItem(`${CACHE_PREFIX}${codigo}`);
      } else if (bundle) {
        restante.push(codigo);
      }
    }
    if (restante.length !== indice.length) {
      await AsyncStorage.setItem(CACHE_INDEX_KEY, JSON.stringify(restante));
    }
  } catch {
    // limpeza é conveniência, nunca deve quebrar o fluxo principal
  }
}
