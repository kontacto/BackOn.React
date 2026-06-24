// Util de chamadas HTTP à API Back-On, reutilizado pelas telas.
// Centraliza a montagem da URL base e do querystring servidor/banco.
import { Connection } from "./storage/connections";

export function apiBase(conn: Connection): string {
  return conn.api.replace(/\/+$/, "");
}

type QSValue = string | number | boolean | null | undefined;

// Monta querystring incluindo servidor/banco da conexão + parâmetros extras.
export function connQS(conn: Connection, extra?: Record<string, QSValue>): string {
  const parts = [
    `servidor=${encodeURIComponent(conn.servidor)}`,
    `banco=${encodeURIComponent(conn.banco)}`,
  ];
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v === undefined || v === null) continue;
      parts.push(`${k}=${encodeURIComponent(String(v))}`);
    }
  }
  return parts.join("&");
}

// GET → json. `path` começa com "/api/...". `params` são adicionados ao querystring.
export async function apiGet(conn: Connection, path: string, params?: Record<string, QSValue>): Promise<any> {
  const url = `${apiBase(conn)}${path}?${connQS(conn, params)}`;
  const r = await fetch(url);
  return r.json();
}

// POST/PUT/DELETE com corpo JSON → json. servidor/banco devem ir no body pelo chamador.
export async function apiSend(
  conn: Connection,
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body: Record<string, unknown>,
): Promise<any> {
  const r = await fetch(`${apiBase(conn)}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...body }),
  });
  return r.json();
}

// DELETE via querystring (servidor/banco). Sem corpo.
export async function apiDelete(conn: Connection, path: string, params?: Record<string, QSValue>): Promise<any> {
  const url = `${apiBase(conn)}${path}?${connQS(conn, params)}`;
  const r = await fetch(url, { method: "DELETE" });
  return r.json();
}
