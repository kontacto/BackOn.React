// Util de chamadas HTTP à API Back-On, reutilizado pelas telas.
// Centraliza a montagem da URL base e do querystring servidor/banco.
import { Connection } from "./storage/connections";

// Forma mínima aceita por todas as funções abaixo — `Connection` (o objeto
// completo salvo em storage) satisfaz isso estruturalmente, mas telas com
// seu próprio `Conn` reduzido (ex.: `useProdutoCompletoForm.ts`'s
// `{ servidor, banco, api }`) também servem, sem precisar de cast.
export type ConnLike = { servidor: string; banco: string; api: string };

export function apiBase(conn: ConnLike): string {
  return conn.api.replace(/\/+$/, "");
}

type QSValue = string | number | boolean | null | undefined;

// Monta querystring incluindo servidor/banco da conexão + parâmetros extras.
export function connQS(conn: ConnLike, extra?: Record<string, QSValue>): string {
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
export async function apiGet(conn: ConnLike, path: string, params?: Record<string, QSValue>): Promise<any> {
  const url = `${apiBase(conn)}${path}?${connQS(conn, params)}`;
  const r = await fetch(url);
  return r.json();
}

// POST/PUT/DELETE com corpo JSON → json. servidor/banco devem ir no body pelo chamador.
// `timeoutMs` é opcional — sem ele, comportamento idêntico a sempre (sem
// timeout, mesmo padrão de todo o resto do app). Passar um valor só nas
// telas onde travar pra sempre já foi um problema real (ex.: Efetivar
// Previsão travando "processando" indefinidamente contra um banco real
// com lock — achado do usuário 2026-08-31, PENDENCIAS.md > "Painel
// Financeiro"). Não virou padrão global de propósito — uma chamada
// legitimamente demorada (emissão de NFe, relatório grande) não deve
// ganhar um timeout que não pediu.
export async function apiSend(
  conn: ConnLike,
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body: Record<string, unknown>,
  timeoutMs?: number,
): Promise<any> {
  const controller = timeoutMs ? new AbortController() : undefined;
  const timer = timeoutMs ? setTimeout(() => controller!.abort(), timeoutMs) : undefined;
  try {
    const r = await fetch(`${apiBase(conn)}${path}`, {
      method,
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...body }),
      signal: controller?.signal,
    });
    return await r.json();
  } finally {
    if (timer) clearTimeout(timer);
  }
}

// DELETE via querystring (servidor/banco). Sem corpo.
export async function apiDelete(conn: ConnLike, path: string, params?: Record<string, QSValue>): Promise<any> {
  const url = `${apiBase(conn)}${path}?${connQS(conn, params)}`;
  const r = await fetch(url, { method: "DELETE" });
  return r.json();
}

// [GLOBAL] Mensagens de Erro — Linguagem Não-Técnica (ver CLAUDE.md).
// Quando um payload não bate com o schema esperado pelo backend, o FastAPI
// devolve um 422 com `detail: [{loc, msg, type}, ...]` — `msg` é sempre em
// inglês e cheio de jargão de validação ("Input should be a valid string"),
// sem dizer ao usuário final QUAL campo da tela está errado nem como
// corrigir. Usar esta função em vez do padrão antigo
// `j.detail.map(d => d.msg).join("; ")` (ainda encontrado em telas mais
// antigas — trocar quando a tela for tocada por outro motivo, não é gatilho
// de varredura retroativa sozinho).
const _VALIDATION_TYPE_MESSAGES: Record<string, string> = {
  string_type: "valor com tipo inválido para este campo",
  int_type: "precisa ser um número inteiro",
  int_parsing: "precisa ser um número inteiro",
  float_type: "precisa ser um número",
  float_parsing: "precisa ser um número",
  bool_type: "precisa ser Sim ou Não",
  bool_parsing: "precisa ser Sim ou Não",
  missing: "é obrigatório",
  value_error: "está com um valor inválido",
  string_too_short: "está muito curto",
  string_too_long: "está muito longo",
  greater_than: "precisa ser maior que o mínimo permitido",
  less_than: "precisa ser menor que o máximo permitido",
};

function _campoFromLoc(loc: unknown): string {
  if (!Array.isArray(loc)) return "campo";
  const partes = loc.filter((p) => typeof p === "string" && !["body", "dados", "query", "path"].includes(p));
  return partes.length ? String(partes[partes.length - 1]) : "campo";
}

// Traduz a resposta de erro de uma chamada `apiGet`/`apiSend`/`apiDelete`
// (ou `fetch` cru) numa frase curta e não-técnica pra mostrar ao usuário
// final, sempre apontando o campo/causa quando possível. Prioridades:
// 1) `message` — já é a mensagem de negócio pensada pra tela (services do
//    backend já escrevem essas em português, ver `friendly_db_error` no
//    backend pro mesmo princípio aplicado a erro de conexão);
// 2) `detail[]` — payload cru de validação do FastAPI/Pydantic, traduzido
//    campo a campo;
// 3) `fallback`.
export function friendlyApiError(j: any, fallback = "Não foi possível concluir a ação. Tente novamente."): string {
  if (j?.message) return j.message;
  if (Array.isArray(j?.detail) && j.detail.length > 0) {
    const linhas = j.detail.map((d: any) => {
      const campo = _campoFromLoc(d?.loc);
      const causa = _VALIDATION_TYPE_MESSAGES[d?.type] || "está com um valor inválido";
      return `Campo "${campo}": ${causa}.`;
    });
    return linhas.join(" ");
  }
  return fallback;
}

// [GLOBAL] Mensagens de Erro — Linguagem Não-Técnica, estendida 2026-07-24
// pro caso que `friendlyApiError` acima não cobre: quando o próprio
// `fetch()` lança (nunca chega a ter resposta HTTP pra virar `j`) — sem
// servidor no ar, sem rede, CORS bloqueando, timeout. O texto da exceção
// nesse caso é sempre em inglês e varia por engine ("Failed to fetch" no
// Chrome, "NetworkError when attempting to fetch resource" no Firefox,
// "Load failed" no Safari, "Network request failed" no React Native) —
// nenhum desses diz algo útil pro usuário final. Usar esta função no
// `catch` de qualquer chamada à API, no lugar do padrão antigo
// `` `Erro: ${e instanceof Error ? e.message : String(e)}` `` (ainda
// encontrado em telas mais antigas — trocar quando a tela for tocada por
// outro motivo, não é gatilho de varredura retroativa sozinho).
export function friendlyCatchError(e: unknown, fallback = "Não foi possível completar a ação. Tente novamente."): string {
  // `fetch()` sempre rejeita com TypeError quando falha antes de obter
  // resposta HTTP (qualquer engine/plataforma) — status 4xx/5xx não caem
  // aqui, eles retornam uma resposta normal pro `.json()` ler.
  if (e instanceof TypeError) {
    return "Falha de conexão com o servidor. Verifique sua internet/rede e tente novamente.";
  }
  // `AbortController` (só quando `apiSend` recebeu `timeoutMs`) — distinto
  // de falha de rede: o pedido chegou a sair, só não voltou a tempo.
  if (e instanceof Error && e.name === "AbortError") {
    return "O servidor demorou demais para responder. Pode haver um bloqueio no banco de dados — tente novamente em instantes; se persistir, avise o suporte.";
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}
