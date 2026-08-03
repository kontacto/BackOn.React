import AsyncStorage from "./asyncStorageCompat";

const SESSION_KEY = "@back_on/session";

export type Session = {
  empresa: string;
  server: string;
  database: string;
  logo: string;
  usuario: Record<string, unknown> | null;
  funcionario: Record<string, unknown> | null;
  loggedAt: string;
};

export async function getSession(): Promise<Session | null> {
  const raw = await AsyncStorage.getItem(SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Session;
  } catch {
    return null;
  }
}

export async function setSession(s: Session): Promise<void> {
  await AsyncStorage.setItem(SESSION_KEY, JSON.stringify(s));
}

export async function clearSession(): Promise<void> {
  await AsyncStorage.removeItem(SESSION_KEY);
}

// Último login bem-sucedido (conexão + usuário) — sobrevive ao logout de
// propósito (diferente de `session`, que `clearSession()` apaga por
// completo) pra pré-preencher a tela de Login na próxima vez que o app
// abrir. Pedido explícito do usuário, 2026-07-20 ("ao sair do sistema, tem
// que trazer as informações do último login, conexão e usuário").
const LAST_LOGIN_KEY = "@back_on/last_login";

export type LastLogin = { connectionId: string; usuario: string };

export async function getLastLogin(): Promise<LastLogin | null> {
  const raw = await AsyncStorage.getItem(LAST_LOGIN_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as LastLogin;
  } catch {
    return null;
  }
}

export async function setLastLogin(v: LastLogin): Promise<void> {
  await AsyncStorage.setItem(LAST_LOGIN_KEY, JSON.stringify(v));
}

const SIT_FILTER_KEY = "@back_on/dashboard_situacao";

export async function getSituacaoFiltro(): Promise<string> {
  try {
    return (await AsyncStorage.getItem(SIT_FILTER_KEY)) ?? "";
  } catch {
    return "";
  }
}

export async function setSituacaoFiltro(value: string): Promise<void> {
  try {
    await AsyncStorage.setItem(SIT_FILTER_KEY, value);
  } catch {
    // ignora falha de persistência
  }
}
