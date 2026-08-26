import { useEffect, useState } from "react";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";

// Badge do Sidebar (item "Configurações") quando há uma atualização já
// baixada e pronta pra aplicar em Serviço do Sistema > Atualização — ver
// PENDENCIAS.md > "Serviço do Sistema — Atualização". Visível pra
// QUALQUER usuário logado (avisa a equipe, mesmo que só o master consiga
// agir) — sem gate de master aqui, o gate fica na tela em si.
const POLL_MS = 120_000; // 2 min — leve, só {pendente: bool}, não a config inteira

export function useAtualizacaoPendente(): boolean {
  const [pendente, setPendente] = useState(false);

  useEffect(() => {
    let cancelado = false;

    const verificar = async () => {
      try {
        const s = await getSession();
        if (!s) return;
        const c = (await listConnections()).find((x) => x.empresa === s.empresa);
        if (!c) return;
        const j = await apiGet({ servidor: c.servidor, banco: c.banco, api: c.api }, "/api/servico-sistema/atualizacao/status");
        if (!cancelado && j?.success) setPendente(!!j.pendente);
      } catch {
        // silencioso — badge é só um aviso, nunca deve gerar erro visível
      }
    };

    void verificar();
    const t = setInterval(verificar, POLL_MS);
    return () => { cancelado = true; clearInterval(t); };
  }, []);

  return pendente;
}
