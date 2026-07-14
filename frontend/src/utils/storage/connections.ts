import AsyncStorage from "./asyncStorageCompat";

const CONNECTIONS_KEY = "@back_on/connections";

export type Connection = {
  id: string;
  empresa: string;
  servidor: string;
  banco: string;
  api: string;
  logo: string;
  imagensUrl: string;
  permitirBiometria: boolean;
  createdAt: string;
};

function uid(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`;
}

export async function listConnections(): Promise<Connection[]> {
  const raw = await AsyncStorage.getItem(CONNECTIONS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Backward-compatible: conexões antigas não tinham 'api'
    return parsed.map((c: Connection) => ({
      id: c.id,
      empresa: c.empresa ?? "",
      servidor: c.servidor ?? "",
      banco: c.banco ?? "",
      api: c.api ?? "",
      logo: c.logo ?? "",
      imagensUrl: c.imagensUrl ?? "",
      permitirBiometria: c.permitirBiometria ?? false,
      createdAt: c.createdAt ?? new Date().toISOString(),
    }));
  } catch {
    return [];
  }
}

export async function saveAll(items: Connection[]): Promise<void> {
  await AsyncStorage.setItem(CONNECTIONS_KEY, JSON.stringify(items));
}

export async function addConnection(input: {
  empresa: string;
  servidor: string;
  banco: string;
  api: string;
  logo: string;
  imagensUrl?: string;
  permitirBiometria?: boolean;
}): Promise<Connection> {
  const items = await listConnections();
  const conn: Connection = {
    id: uid(),
    empresa: input.empresa.trim(),
    servidor: input.servidor.trim(),
    banco: input.banco.trim(),
    api: input.api.trim(),
    logo: input.logo.trim(),
    imagensUrl: (input.imagensUrl ?? "").trim(),
    permitirBiometria: !!input.permitirBiometria,
    createdAt: new Date().toISOString(),
  };
  items.push(conn);
  await saveAll(items);
  return conn;
}

export async function updateConnection(
  id: string,
  input: { empresa: string; servidor: string; banco: string; api: string; logo: string; imagensUrl?: string; permitirBiometria?: boolean }
): Promise<Connection | null> {
  const items = await listConnections();
  const idx = items.findIndex((c) => c.id === id);
  if (idx === -1) return null;
  items[idx] = {
    ...items[idx],
    empresa: input.empresa.trim(),
    servidor: input.servidor.trim(),
    banco: input.banco.trim(),
    api: input.api.trim(),
    logo: input.logo.trim(),
    imagensUrl: (input.imagensUrl ?? "").trim(),
    permitirBiometria: !!input.permitirBiometria,
  };
  await saveAll(items);
  return items[idx];
}

export async function deleteConnection(id: string): Promise<void> {
  const items = await listConnections();
  const next = items.filter((c) => c.id !== id);
  await saveAll(next);
}

export async function hasConnections(): Promise<boolean> {
  const items = await listConnections();
  return items.length > 0;
}
