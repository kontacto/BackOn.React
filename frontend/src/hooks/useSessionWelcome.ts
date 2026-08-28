import { useEffect, useState } from "react";

import { getSession } from "@/src/utils/storage/session";

export type SessionWelcome = {
  empresa: string;
  logo: string | null;
  displayName: string;
  nomeGuerra: string | null;
  classe: string | null;
};

function pickFirst(obj: unknown, keys: string[]): string | null {
  if (!obj || typeof obj !== "object") return null;
  const rec = obj as Record<string, unknown>;
  for (const k of keys) {
    const v = rec[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v);
  }
  return null;
}

// Card "Bem-vindo" (empresa/avatar/nome/grupo) reaproveitado no final do
// Sidebar — pedido explícito do usuário, 2026-08-28 ("exibir esse card na
// parte inferior da tela na barra de menu lateral"). Mesma derivação já
// usada por `useDashboard.ts` na Tela Principal (`displayName`/
// `nomeGuerra`/`classe`), replicada aqui de forma enxuta porque o
// Sidebar é montado uma vez no layout raiz — não faz sentido puxar o
// hook de dashboard inteiro (muito mais estado do que este card precisa)
// só por essas 5 linhas de derivação.
const POLL_MS = 120_000;

export function useSessionWelcome(): SessionWelcome | null {
  const [info, setInfo] = useState<SessionWelcome | null>(null);

  useEffect(() => {
    let cancelado = false;

    const carregar = async () => {
      const s = await getSession();
      if (cancelado) return;
      if (!s) { setInfo(null); return; }
      const displayName = pickFirst(s.funcionario, ["nome", "nome_guerra", "nome_completo", "apelido"])
        || pickFirst(s.usuario, ["nome", "usuario"]) || "Usuário";
      const nomeGuerra = pickFirst(s.funcionario, ["nome_guerra"]);
      const classe = pickFirst(s.usuario, ["classe_descricao", "classe_label", "classe"]);
      setInfo({ empresa: s.empresa || "", logo: s.logo || null, displayName, nomeGuerra, classe });
    };

    void carregar();
    const t = setInterval(carregar, POLL_MS);
    return () => { cancelado = true; clearInterval(t); };
  }, []);

  return info;
}
