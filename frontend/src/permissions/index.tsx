// Contexto global de permissões (sistema=50).
// Carrega as permissões do GRUPO (classe) do usuário logado e expõe `can(key)`.
// Regras:
//   • Usuário master (KONTACTO) → acesso total (can() sempre true).
//   • Modo ESTRITO: sem registro na tabela = bloqueado.
//   • key no formato "TELA.COMANDO" (ex.: "CLIENTE.GRAVAR") ou "TELA" (abrir tela).
import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";

type PermState = {
  loading: boolean;
  isMaster: boolean;
  keys: Set<string>;
  classe: number | null;
};

type PermContextValue = PermState & {
  can: (key: string) => boolean;
  reload: () => Promise<void>;
};

const PermissionsContext = createContext<PermContextValue | null>(null);

function normKey(tela: string, comando: string): string {
  const t = (tela || "").trim().toUpperCase();
  const c = (comando || "").trim().toUpperCase();
  return c ? `${t}.${c}` : t;
}

export function PermissionsProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<PermState>({
    loading: true,
    isMaster: false,
    keys: new Set(),
    classe: null,
  });

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    const session = await getSession();
    if (!session) {
      setState({ loading: false, isMaster: false, keys: new Set(), classe: null });
      return;
    }
    const usuario = (session.usuario ?? {}) as Record<string, unknown>;
    const isMaster =
      usuario?.master === true ||
      String(usuario?.usuario ?? "").toUpperCase() === "KONTACTO";
    const classeRaw = usuario?.classe;
    const classe =
      classeRaw === undefined || classeRaw === null || classeRaw === ""
        ? null
        : Number(classeRaw);

    if (isMaster) {
      setState({ loading: false, isMaster: true, keys: new Set(), classe });
      return;
    }
    if (classe === null || Number.isNaN(classe)) {
      // Sem classe identificada → modo estrito: nada liberado.
      setState({ loading: false, isMaster: false, keys: new Set(), classe: null });
      return;
    }
    try {
      const conns = await listConnections();
      const conn = conns.find((c) => c.empresa === session.empresa);
      if (!conn) {
        setState({ loading: false, isMaster: false, keys: new Set(), classe });
        return;
      }
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(
        conn.banco
      )}&classe=${classe}`;
      const r = await fetch(`${base}/api/permissoes?${qs}`).then((x) => x.json());
      const keys = new Set<string>();
      if (r?.success && Array.isArray(r.items)) {
        (r.items as { tela: string; comando: string }[]).forEach((i) =>
          keys.add(normKey(i.tela, i.comando))
        );
      }
      setState({ loading: false, isMaster: false, keys, classe });
    } catch {
      // Falha de rede → modo estrito (mantém bloqueado), evita liberar por engano.
      setState({ loading: false, isMaster: false, keys: new Set(), classe });
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const can = useCallback(
    (key: string) => {
      if (state.isMaster) return true;
      const k = (key || "").trim().toUpperCase();
      if (!k) return false;
      if (state.keys.has(k)) return true;
      // "CLIENTE" sem comando → considera permitido se houver "CLIENTE.ABRIR".
      if (!k.includes(".") && state.keys.has(`${k}.ABRIR`)) return true;
      return false;
    },
    [state.isMaster, state.keys]
  );

  const value = useMemo<PermContextValue>(
    () => ({ ...state, can, reload }),
    [state, can, reload]
  );

  return <PermissionsContext.Provider value={value}>{children}</PermissionsContext.Provider>;
}

export function usePermissions(): PermContextValue {
  const ctx = useContext(PermissionsContext);
  if (!ctx) {
    // Fallback seguro caso usado fora do provider (não deve acontecer).
    return {
      loading: false,
      isMaster: false,
      keys: new Set(),
      classe: null,
      can: () => false,
      reload: async () => {},
    };
  }
  return ctx;
}
