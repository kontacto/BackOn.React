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
  isManagerFuncao: boolean;
  keys: Set<string>;
  classe: number | null;
  disabledTelas: Set<string>;
  modules: Record<string, boolean>;
};

// Mapa: módulo (coluna controle_configuracao) -> telas controladas.
// Manter alinhado com backend services/controle_config_service.MODULE_TELAS.
const MODULE_TELAS: Record<string, string[]> = {
  Pedido_venda: ["PEDIDO"],
  Clientes: ["CLIENTE"],
};

type PermContextValue = PermState & {
  can: (key: string) => boolean;
  moduleOn: (name: string) => boolean;
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
    isManagerFuncao: false,
    keys: new Set(),
    classe: null,
    disabledTelas: new Set(),
    modules: {},
  });

  const reload = useCallback(async () => {
    setState((s) => ({ ...s, loading: true }));
    const session = await getSession();
    if (!session) {
      setState({ loading: false, isMaster: false, isManagerFuncao: false, keys: new Set(), classe: null, disabledTelas: new Set(), modules: {} });
      return;
    }
    const usuario = (session.usuario ?? {}) as Record<string, unknown>;
    const isMaster =
      usuario?.master === true ||
      String(usuario?.usuario ?? "").toUpperCase() === "KONTACTO";
    // Gerente por função: cod_funcao 01/02 (ou master). Controla "ver todos os vendedores".
    const funcionario = (session.funcionario ?? {}) as Record<string, unknown>;
    const codFuncao = parseInt(String(funcionario?.cod_funcao ?? ""), 10);
    const isManagerFuncao = isMaster || codFuncao === 1 || codFuncao === 2;
    const classeRaw = usuario?.classe;
    const classe =
      classeRaw === undefined || classeRaw === null || classeRaw === ""
        ? null
        : Number(classeRaw);

    const conns = await listConnections();
    const conn = conns.find((c) => c.empresa === session.empresa);
    const keys = new Set<string>();
    const disabledTelas = new Set<string>();
    const modules: Record<string, boolean> = {};

    if (conn) {
      const base = conn.api.replace(/\/+$/, "");
      const cq = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      // 1) Módulos ligados/desligados (controle_configuracao) — sobrepõe tudo.
      try {
        const cfg = await fetch(`${base}/api/controle-config?${cq}`).then((x) => x.json());
        if (cfg?.success && cfg.valores) {
          Object.assign(modules, cfg.valores);
          Object.entries(MODULE_TELAS).forEach(([mod, telas]) => {
            if (!cfg.valores[mod]) telas.forEach((t) => disabledTelas.add(t.toUpperCase()));
          });
        }
      } catch {
        // sem flags → não desliga nada
      }
      // 2) Permissões do grupo (apenas não-master com classe válida).
      if (!isMaster && classe !== null && !Number.isNaN(classe)) {
        try {
          const r = await fetch(`${base}/api/permissoes?${cq}&classe=${classe}`).then((x) => x.json());
          if (r?.success && Array.isArray(r.items)) {
            (r.items as { tela: string; comando: string }[]).forEach((i) =>
              keys.add(normKey(i.tela, i.comando))
            );
          }
        } catch {
          // falha → modo estrito (mantém bloqueado)
        }
      }
    }

    setState({ loading: false, isMaster, isManagerFuncao, keys, classe, disabledTelas, modules });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const can = useCallback(
    (key: string) => {
      const k = (key || "").trim().toUpperCase();
      if (!k) return false;
      // Módulo desligado (controle_configuracao) sobrepõe tudo, inclusive master.
      const tela = k.split(".")[0];
      if (state.disabledTelas.has(tela)) return false;
      if (state.isMaster) return true;
      if (state.keys.has(k)) return true;
      // "CLIENTE" sem comando → considera permitido se houver "CLIENTE.ABRIR".
      if (!k.includes(".") && state.keys.has(`${k}.ABRIR`)) return true;
      return false;
    },
    [state.isMaster, state.keys, state.disabledTelas]
  );

  const moduleOn = useCallback(
    (name: string) => state.modules[name] === true,
    [state.modules]
  );

  const value = useMemo<PermContextValue>(
    () => ({ ...state, can, moduleOn, reload }),
    [state, can, moduleOn, reload]
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
      isManagerFuncao: false,
      keys: new Set(),
      classe: null,
      disabledTelas: new Set(),
      modules: {},
      can: () => false,
      moduleOn: () => false,
      reload: async () => {},
    };
  }
  return ctx;
}
