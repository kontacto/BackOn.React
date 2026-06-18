import AsyncStorage from "@react-native-async-storage/async-storage";

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
