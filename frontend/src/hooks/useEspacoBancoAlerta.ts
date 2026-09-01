import { useEffect, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";

// Item "Espaço do Banco" do grupo "Pendências do Sistema" (Sidebar) — ver
// CLAUDE.md > "Padrões de UI" > seção 10, e o precedente
// `useTransferenciaCaixaPendenteCount.ts` (mesmo padrão de polling).
// Achado real que motivou (Áureo, análise DBA de RJPNEUS-TESTE,
// 2026-08-31): SQL Server Express tem teto rígido de 10GB de dados por
// banco — passar do limite trava novos lançamentos. `GET /api/
// manutencao-indices/espaco` só calcula/alerta quando a instância é
// Express (`EngineEdition = 4`); outras edições não têm esse teto.
const POLL_MS = 120_000; // 2 min, mesmo intervalo dos demais itens do grupo
const LIMIAR_ALERTA_PCT = 80;

export function useEspacoBancoAlerta(): { visivel: boolean; pct: number } {
  const [pct, setPct] = useState(0);

  useEffect(() => {
    let cancelado = false;

    const verificar = async () => {
      try {
        const s = await getSession();
        if (!s) return;
        const c = (await listConnections()).find((x) => x.empresa === s.empresa);
        if (!c) return;
        const j = await apiGet({ servidor: c.servidor, banco: c.banco, api: c.api }, "/api/manutencao-indices/espaco");
        if (!cancelado && j?.success && j.express && typeof j.pct_usado === "number") {
          setPct(j.pct_usado);
        }
      } catch {
        // silencioso — item some/fica com valor antigo, nunca gera erro visível
      }
    };

    void verificar();
    const t = setInterval(verificar, POLL_MS);
    return () => { cancelado = true; clearInterval(t); };
  }, []);

  return { visivel: pct >= LIMIAR_ALERTA_PCT, pct };
}
