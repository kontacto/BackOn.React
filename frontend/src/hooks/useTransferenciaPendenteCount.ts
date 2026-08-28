import { useEffect, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";

// Item "Transferência Pendente" do grupo "Pendências do Sistema"
// (Sidebar) — ver CLAUDE.md > "Padrões de UI" > seção 10. Mesmo padrão de
// `useAtualizacaoPendente.ts` (polling leve, resolve conn do jeito mais
// simples possível porque o Sidebar é montado fora de contexto de tela).
// Reaproveita o MESMO endpoint que a tela `/transferencia-contas` já usa
// pra listar (`GET /transferencia-contas/pendentes`) — nenhuma rota nova
// foi criada só pra este contador.
const POLL_MS = 120_000; // 2 min, mesmo intervalo do badge de atualização

export function useTransferenciaPendenteCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelado = false;

    const verificar = async () => {
      try {
        const s = await getSession();
        if (!s) return;
        const c = (await listConnections()).find((x) => x.empresa === s.empresa);
        if (!c) return;
        const j = await apiGet({ servidor: c.servidor, banco: c.banco, api: c.api }, "/api/transferencia-contas/pendentes");
        if (!cancelado && j?.success) setCount((j.items || []).length);
      } catch {
        // silencioso — item some/fica com contagem antiga, nunca gera erro visível
      }
    };

    void verificar();
    const t = setInterval(verificar, POLL_MS);
    return () => { cancelado = true; clearInterval(t); };
  }, []);

  return count;
}
