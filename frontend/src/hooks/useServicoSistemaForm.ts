import { useCallback, useEffect, useState } from "react";
import { useRouter } from "expo-router";

import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";

// Serviço do Sistema > aba "Atualização" — config + status da atualização
// automática desta instalação (backend/services/servico_sistema_service.py).
// Tabela nova e pequena (6-8 campos) — sem o aparato de arrays TEXT_FIELDS/
// NUM_FIELDS genérico que `useControleSistemaForm.ts` usa (esse existe lá só
// por causa de dezenas de colunas legadas em `controle`/`controle_aux`; aqui
// não compensa, o form é tipado direto).

export type Conn = { servidor: string; banco: string; api: string };

export type ServicoSistemaAtualizacaoForm = {
  manifest_url: string;
  pasta_backend: string;
  pasta_frontend: string;
  intervalo_minutos: string;
  commit_atual: string | null;
  commit_anterior: string | null;
  commit_pendente: string | null;
  pendente_desde: string | null;
  ultima_verificacao: string | null;
  ultimo_erro: string | null;
};

const FORM_VAZIO: ServicoSistemaAtualizacaoForm = {
  manifest_url: "",
  pasta_backend: "",
  pasta_frontend: "",
  intervalo_minutos: "30",
  commit_atual: null,
  commit_anterior: null,
  commit_pendente: null,
  pendente_desde: null,
  ultima_verificacao: null,
  ultimo_erro: null,
};

export function useServicoSistemaForm() {
  const router = useRouter();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const [aplicando, setAplicando] = useState(false);
  const [revertendo, setRevertendo] = useState(false);
  const [verificando, setVerificando] = useState(false);
  const [form, setForm] = useState<ServicoSistemaAtualizacaoForm>(FORM_VAZIO);

  const setField = useCallback(<K extends keyof ServicoSistemaAtualizacaoForm>(k: K, v: ServicoSistemaAtualizacaoForm[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
  }, []);

  const loadDados = useCallback(async (c: Conn) => {
    const j = await apiGet(c, "/api/servico-sistema/atualizacao");
    if (j?.success && j.dados) {
      const d = j.dados;
      setForm({
        manifest_url: d.manifest_url || "",
        pasta_backend: d.pasta_backend || "",
        pasta_frontend: d.pasta_frontend || "",
        intervalo_minutos: String(d.intervalo_minutos ?? 30),
        commit_atual: d.commit_atual ?? null,
        commit_anterior: d.commit_anterior ?? null,
        commit_pendente: d.commit_pendente ?? null,
        pendente_desde: d.pendente_desde ?? null,
        ultima_verificacao: d.ultima_verificacao ?? null,
        ultimo_erro: d.ultimo_erro ?? null,
      });
    }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) { setLoadingInit(false); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      await loadDados(cc);
      setLoadingInit(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, loadDados]);

  const save = async (): Promise<boolean> => {
    if (!conn) return false;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/servico-sistema/atualizacao", "POST", {
        ...auditCtx,
        dados: {
          manifest_url: form.manifest_url.trim(),
          pasta_backend: form.pasta_backend.trim(),
          pasta_frontend: form.pasta_frontend.trim(),
          intervalo_minutos: parseInt(form.intervalo_minutos, 10) || 30,
        },
      });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao gravar a configuração.")); return false; }
      fb.showSuccess("Configuração de Atualização gravada.");
      await loadDados(conn);
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar a configuração."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const aplicar = async (): Promise<boolean> => {
    if (!conn) return false;
    setAplicando(true);
    try {
      const j = await apiSend(conn, "/api/servico-sistema/atualizacao/aplicar", "POST", { ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao aplicar a atualização.")); return false; }
      fb.showSuccess(
        "Atualização iniciada — o sistema vai reiniciar em instantes. Esta página vai perder a conexão por alguns segundos; atualize (F5) depois.",
        undefined, 5000,
      );
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao aplicar a atualização."));
      return false;
    } finally {
      setAplicando(false);
    }
  };

  const reverter = async (): Promise<boolean> => {
    if (!conn) return false;
    setRevertendo(true);
    try {
      const j = await apiSend(conn, "/api/servico-sistema/atualizacao/reverter", "POST", { ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao reverter a atualização.")); return false; }
      fb.showSuccess(
        "Reversão iniciada — o sistema vai reiniciar em instantes. Esta página vai perder a conexão por alguns segundos; atualize (F5) depois.",
        undefined, 5000,
      );
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao reverter a atualização."));
      return false;
    } finally {
      setRevertendo(false);
    }
  };

  const verificarAgora = async (): Promise<boolean> => {
    if (!conn) return false;
    setVerificando(true);
    try {
      const j = await apiSend(conn, "/api/servico-sistema/atualizacao/verificar-agora", "POST", { ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao verificar atualização.")); return false; }
      fb.showSuccess(j.message || "Verificação concluída.", undefined, 5000);
      await loadDados(conn);
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao verificar atualização."));
      return false;
    } finally {
      setVerificando(false);
    }
  };

  return { conn, loadingInit, saving, aplicando, revertendo, verificando, form, setField, save, aplicar, reverter, verificarAgora };
}
