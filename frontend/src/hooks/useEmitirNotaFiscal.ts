// Hook compartilhado de emissão fiscal (NFC-e/NFS-e) por comanda —
// extraído de `app/alterar-comanda.tsx` (`emitirNfce`/`emitirNfse`, único
// lugar do app que já tinha essa lógica) como parte do ecossistema fiscal
// (Web + KPDV), pedido explícito do usuário via WhatsApp da equipe VB6:
// "essa tela [Gerar Nfe Comanda, legado] tem que ser reaproveitada para
// essas outras telas, viável refatoramento" — no legado é uma tela única
// compartilhada por Faturar Pedido/Faturar O.S./Tela de Vendas; aqui vira
// um hook único, reaproveitado por Pedido Bar, Pedido Geral, O.S. Mobile,
// O.S. Completa, e retrofitado no próprio `alterar-comanda.tsx`. Nunca
// duplicar esta lógica por tela.
//
// Emissão aqui é sempre MANUAL (o usuário decide clicar) — confirmado
// diretamente pelo usuário: Pedido/O.S. faturar nunca emitem nota
// sozinhos, diferente da Tela de Vendas/KPDV (que tem um caminho
// condicional de emissão automática, replicado só no KPDV, não aqui).
import { useCallback, useEffect, useState } from "react";

import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import type { Connection } from "@/src/utils/storage/connections";
import { friendlyCatchError } from "@/src/utils/api";
import { showApoioFiscalError } from "@/src/utils/apoioFiscal";
import type { ApoioFiscalInfo } from "@/src/components/ApoioFiscalBackOnModal";

export type DocFiscal = {
  tipo: string;
  numero: number | string | null;
  situacao: string | null;
  protocolo: string | null;
  chave_acesso?: string | null;
};

type SessionLike = { usuarioCodigo?: number | null; classe?: number | null };

export function useEmitirNotaFiscal(params: {
  conn: Connection | null;
  session: SessionLike | null;
  comanda: number | null;
  isMaster: boolean;
}) {
  const { conn, session, comanda, isMaster } = params;
  const fb = useFeedback();
  const [docFiscal, setDocFiscal] = useState<DocFiscal | null>(null);
  const [loadingDocFiscal, setLoadingDocFiscal] = useState(false);
  const [emitindoNfce, setEmitindoNfce] = useState(false);
  const [emitindoNfse, setEmitindoNfse] = useState(false);
  const [apoioFiscalInfo, setApoioFiscalInfo] = useState<ApoioFiscalInfo | null>(null);

  const recarregar = useCallback(async () => {
    if (!conn || !comanda) { setDocFiscal(null); return; }
    setLoadingDocFiscal(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/comandas/${comanda}/doc-fiscal?${qs}`);
      const j = await r.json().catch(() => null);
      setDocFiscal(j?.success ? j : null);
    } catch {
      setDocFiscal(null);
    } finally {
      setLoadingDocFiscal(false);
    }
  }, [conn, comanda]);

  useEffect(() => { recarregar(); }, [recarregar]);

  // Emitir NFC-e real junto ao SEFAZ — Fase 1 do pacote de emissão fiscal
  // (ver `backend/services/nfe_emissao_service.py`). Ação irreversível (uma
  // vez autorizada, só é desfeita por Cancelar Comanda) — erro fica 5s na
  // tela (pode ter detalhe importante do SEFAZ pra conferir).
  const emitirNfce = useCallback(async () => {
    if (!conn || !comanda || !session) return null;
    setEmitindoNfce(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comanda}/emitir-nfce`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "NFC-e emitida."); await recarregar(); }
      else {
        const info = showApoioFiscalError(fb, j, "Não foi possível emitir a NFC-e.", 5000);
        if (info) setApoioFiscalInfo(info);
      }
      return j;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Não foi possível emitir a NFC-e."));
      return null;
    } finally {
      setEmitindoNfce(false);
    }
  }, [conn, comanda, session, isMaster, fb, recarregar]);

  // Emitir NFS-e real via DPS Nacional/Sefin Nacional — Fase 3 do pacote de
  // emissão fiscal (ver `backend/services/nfse_emissao_service.py`). Mesma
  // lógica de confirmação/erro de `emitirNfce`, documento diferente
  // (serviço, não produto) — a mesma comanda pode gerar os dois.
  const emitirNfse = useCallback(async () => {
    if (!conn || !comanda || !session) return null;
    setEmitindoNfse(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        usuario_alteracao: session.usuarioCodigo, classe: session.classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(`${base}/api/comandas/${comanda}/emitir-nfse`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "NFS-e emitida."); await recarregar(); }
      else {
        const info = showApoioFiscalError(fb, j, "Não foi possível emitir a NFS-e.", 5000);
        if (info) setApoioFiscalInfo(info);
      }
      return j;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Não foi possível emitir a NFS-e."));
      return null;
    } finally {
      setEmitindoNfse(false);
    }
  }, [conn, comanda, session, isMaster, fb, recarregar]);

  return {
    docFiscal, loadingDocFiscal, emitindoNfce, emitindoNfse, emitirNfce, emitirNfse, recarregar,
    apoioFiscalInfo, fecharApoioFiscal: () => setApoioFiscalInfo(null),
  };
}
