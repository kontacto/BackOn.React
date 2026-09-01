import { useEffect, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";

// Item "Transferência p/Fluxo de Caixa Pendente" do grupo "Pendências do
// Sistema" (Sidebar) — ver CLAUDE.md > "Padrões de UI" > seção 10, e o
// precedente `useTransferenciaPendenteCount.ts` (irmão desta, pra
// Transferência p/Contas Pagar/Receber). Usa o endpoint dedicado
// `GET /transferencia-caixa/tem-pendencia` (COUNT direto, não a listagem
// completa) — a listagem desta tela tem filtro/checkbox rico e pode
// devolver muitas linhas, contar direto no banco é mais barato pra um
// polling de sidebar.
const POLL_MS = 120_000; // 2 min, mesmo intervalo dos demais itens do grupo

export function useTransferenciaCaixaPendenteCount(): number {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelado = false;

    const verificar = async () => {
      try {
        const s = await getSession();
        if (!s) return;
        const c = (await listConnections()).find((x) => x.empresa === s.empresa);
        if (!c) return;
        const j = await apiGet({ servidor: c.servidor, banco: c.banco, api: c.api }, "/api/transferencia-caixa/tem-pendencia");
        if (!cancelado && j?.success) setCount(j.pendentes || 0);
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
