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

// "H" (Homologação, equipe) | "P" (Produção, clientes) — ver
// CLAUDE.md > "Padrões de UI" > seção 13 pro desenho completo. Aplicar a
// atualização pendente em Homologação só é possível por esta tela
// (botão "Aplicar agora" abaixo); em Produção só pelo botão "Atualizar
// Sistema" do Sidebar — cada canal tem exatamente 1 caminho de aplicar.
export type Canal = "H" | "P";

export type ServicoSistemaAtualizacaoForm = {
  manifest_url: string;
  pasta_backend: string;
  pasta_frontend: string;
  intervalo_minutos: string;
  canal: Canal;
  cel_suporte: string;
  commit_atual: string | null;
  commit_anterior: string | null;
  commit_pendente: string | null;
  pendente_desde: string | null;
  ultima_verificacao: string | null;
  ultimo_erro: string | null;
  // Manutenção automática de índices (2026-08-28) — ver
  // backend/services/manutencao_indices_service.py. `dias_semana`
  // guarda a mesma convenção 0=domingo..6=sábado já usada em
  // "Dias da Semana (Web Convidado)".
  manutencao_indices_ativo: boolean;
  manutencao_indices_dias_semana: string;
  manutencao_indices_hora: string;
  manutencao_indices_ultima_execucao: string | null;
  manutencao_indices_ultimo_resultado: string | null;
  // Extensão 2026-08-31 (Áureo, análise DBA de RJPNEUS-TESTE) — ver
  // docstring de manutencao_indices_service.py pro racional completo.
  manutencao_indices_orcamento_minutos: string;
  checkdb_ativo: boolean;
  checkdb_dias_semana: string;
  checkdb_hora: string;
  checkdb_ultima_execucao: string | null;
  checkdb_ultimo_resultado: string | null;
  espaco_pct_usado: number | null;
  espaco_verificado_em: string | null;
};

export type IndiceNaoUsado = { tabela: string; indice: string; paginas: number };

const FORM_VAZIO: ServicoSistemaAtualizacaoForm = {
  manifest_url: "",
  pasta_backend: "",
  pasta_frontend: "",
  intervalo_minutos: "30",
  canal: "H",
  cel_suporte: "",
  commit_atual: null,
  commit_anterior: null,
  commit_pendente: null,
  pendente_desde: null,
  ultima_verificacao: null,
  ultimo_erro: null,
  manutencao_indices_ativo: true,
  manutencao_indices_dias_semana: "0,1,2,3,4,5,6",
  manutencao_indices_hora: "03:00",
  manutencao_indices_ultima_execucao: null,
  manutencao_indices_ultimo_resultado: null,
  manutencao_indices_orcamento_minutos: "120",
  checkdb_ativo: true,
  checkdb_dias_semana: "0",
  checkdb_hora: "04:00",
  checkdb_ultima_execucao: null,
  checkdb_ultimo_resultado: null,
  espaco_pct_usado: null,
  espaco_verificado_em: null,
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
  const [rodandoManutencao, setRodandoManutencao] = useState(false);
  const [carregandoNaoUsados, setCarregandoNaoUsados] = useState(false);
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
        canal: d.canal === "P" ? "P" : "H",
        cel_suporte: d.cel_suporte || "",
        commit_atual: d.commit_atual ?? null,
        commit_anterior: d.commit_anterior ?? null,
        commit_pendente: d.commit_pendente ?? null,
        pendente_desde: d.pendente_desde ?? null,
        ultima_verificacao: d.ultima_verificacao ?? null,
        ultimo_erro: d.ultimo_erro ?? null,
        manutencao_indices_ativo: d.manutencao_indices_ativo !== false,
        manutencao_indices_dias_semana: d.manutencao_indices_dias_semana || "0,1,2,3,4,5,6",
        manutencao_indices_hora: d.manutencao_indices_hora || "03:00",
        manutencao_indices_ultima_execucao: d.manutencao_indices_ultima_execucao ?? null,
        manutencao_indices_ultimo_resultado: d.manutencao_indices_ultimo_resultado ?? null,
        manutencao_indices_orcamento_minutos: String(d.manutencao_indices_orcamento_minutos ?? 120),
        checkdb_ativo: d.checkdb_ativo !== false,
        checkdb_dias_semana: d.checkdb_dias_semana || "0",
        checkdb_hora: d.checkdb_hora || "04:00",
        checkdb_ultima_execucao: d.checkdb_ultima_execucao ?? null,
        checkdb_ultimo_resultado: d.checkdb_ultimo_resultado ?? null,
        espaco_pct_usado: d.espaco_pct_usado ?? null,
        espaco_verificado_em: d.espaco_verificado_em ?? null,
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
          canal: form.canal,
          cel_suporte: form.cel_suporte.trim(),
          manutencao_indices_ativo: form.manutencao_indices_ativo,
          manutencao_indices_dias_semana: form.manutencao_indices_dias_semana,
          manutencao_indices_hora: form.manutencao_indices_hora,
          manutencao_indices_orcamento_minutos: parseInt(form.manutencao_indices_orcamento_minutos, 10) || 120,
          checkdb_ativo: form.checkdb_ativo,
          checkdb_dias_semana: form.checkdb_dias_semana,
          checkdb_hora: form.checkdb_hora,
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

  // Item 5 — botão "Rodar agora" (bypassa a janela agendada). REBUILD
  // pode ser demorado num banco fragmentado — feedback visual obrigatório
  // (CLAUDE.md > "Padrões de UI" > seção 6), mesmo padrão de spinner+
  // gerúndio já usado em `verificarAgora`/`aplicar`.
  const rodarManutencaoAgora = async (): Promise<boolean> => {
    if (!conn) return false;
    setRodandoManutencao(true);
    try {
      const j = await apiSend(conn, "/api/manutencao-indices/rodar-agora", "POST", { ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, j?.resumo || "Falha ao rodar a manutenção.")); return false; }
      fb.showSuccess(j.resumo || "Manutenção concluída.", undefined, 5000);
      await loadDados(conn);
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao rodar a manutenção."));
      return false;
    } finally {
      setRodandoManutencao(false);
    }
  };

  // Item 4 — relatório de índices nunca usados (revisão manual, nunca
  // dropa nada sozinho). Devolve a lista pro chamador decidir onde
  // mostrar (modal), em vez de guardar estado próprio aqui — mesmo
  // padrão de `carregarLogs` em `useBackupSistemaForm.ts`.
  const buscarIndicesNaoUsados = async (): Promise<IndiceNaoUsado[]> => {
    if (!conn) return [];
    setCarregandoNaoUsados(true);
    try {
      const j = await apiGet(conn, "/api/manutencao-indices/nao-usados");
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao buscar índices não utilizados.")); return []; }
      return (j.indices || []) as IndiceNaoUsado[];
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao buscar índices não utilizados."));
      return [];
    } finally {
      setCarregandoNaoUsados(false);
    }
  };

  return {
    conn, loadingInit, saving, aplicando, revertendo, verificando, rodandoManutencao, carregandoNaoUsados,
    form, setField, save, aplicar, reverter, verificarAgora, rodarManutencaoAgora, buscarIndicesNaoUsados,
  };
}
