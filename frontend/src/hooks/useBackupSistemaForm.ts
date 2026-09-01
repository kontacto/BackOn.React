import { useCallback, useEffect, useState } from "react";

import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import type { Conn } from "@/src/hooks/useServicoSistemaForm";

// Serviço do Sistema > "Backup Programado" — config + execução manual +
// consulta de log (backend/services/backup_sistema_service.py). Tabela
// PRÓPRIA (`backup_sistema_config`/`backup_sistema_log`), separada de
// `servico_sistema_atualizacao` — aquela já acumula Atualização +
// Manutenção de Índices, virar um "balde" único demais passou a valer
// separar (decisão registrada no service, 2026-08-28).

export type Destino = "LOCAL" | "BLOB";

export type BackupConfigForm = {
  ativo: boolean;
  dias_semana: string;
  hora_inicio: string;
  intervalo_horas: string;
  destino: Destino;
  pasta_local: string;
  blob_container: string;
  retencao_dias: string;
  ultima_execucao: string | null;
  ultimo_resultado: string | null;
};

const FORM_VAZIO: BackupConfigForm = {
  ativo: false,
  dias_semana: "0,1,2,3,4,5,6",
  hora_inicio: "02:00",
  intervalo_horas: "24",
  destino: "LOCAL",
  pasta_local: "",
  blob_container: "backups-sql",
  retencao_dias: "30",
  ultima_execucao: null,
  ultimo_resultado: null,
};

export type BackupLogItem = {
  codigo: number;
  data_hora: string;
  sucesso: boolean;
  destino: string;
  caminho_ou_url: string | null;
  tamanho_mb: number | null;
  duracao_segundos: number | null;
  mensagem: string | null;
};

export function useBackupSistemaForm(conn: Conn | null) {
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [loadingInit, setLoadingInit] = useState(true);
  const [saving, setSaving] = useState(false);
  const [executando, setExecutando] = useState(false);
  const [form, setForm] = useState<BackupConfigForm>(FORM_VAZIO);

  const setField = useCallback(<K extends keyof BackupConfigForm>(k: K, v: BackupConfigForm[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
  }, []);

  const loadDados = useCallback(async (c: Conn) => {
    const j = await apiGet(c, "/api/backup-sistema/config");
    if (j?.success && j.dados) {
      const d = j.dados;
      setForm({
        ativo: !!d.ativo,
        dias_semana: d.dias_semana || "0,1,2,3,4,5,6",
        hora_inicio: d.hora_inicio || "02:00",
        intervalo_horas: String(d.intervalo_horas ?? 24),
        destino: d.destino === "BLOB" ? "BLOB" : "LOCAL",
        pasta_local: d.pasta_local || "",
        blob_container: d.blob_container || "backups-sql",
        retencao_dias: String(d.retencao_dias ?? 30),
        ultima_execucao: d.ultima_execucao ?? null,
        ultimo_resultado: d.ultimo_resultado ?? null,
      });
    }
  }, []);

  useEffect(() => {
    if (!conn) { setLoadingInit(false); return; }
    (async () => {
      await loadDados(conn);
      setLoadingInit(false);
    })();
  }, [conn, loadDados]);

  const save = async (): Promise<boolean> => {
    if (!conn) return false;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/backup-sistema/config", "POST", {
        ...auditCtx,
        dados: {
          ativo: form.ativo,
          dias_semana: form.dias_semana,
          hora_inicio: form.hora_inicio,
          intervalo_horas: parseInt(form.intervalo_horas, 10) || 24,
          destino: form.destino,
          pasta_local: form.pasta_local.trim(),
          blob_container: form.blob_container.trim(),
          retencao_dias: parseInt(form.retencao_dias, 10) || 30,
        },
      });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao gravar a configuração de backup.")); return false; }
      fb.showSuccess("Configuração de Backup gravada.");
      await loadDados(conn);
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar a configuração de backup."));
      return false;
    } finally {
      setSaving(false);
    }
  };

  const executarAgora = async (): Promise<boolean> => {
    if (!conn) return false;
    setExecutando(true);
    try {
      const j = await apiSend(conn, "/api/backup-sistema/executar-agora", "POST", { ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao executar o backup.")); return false; }
      fb.showSuccess(j.message || "Backup concluído.", undefined, 5000);
      await loadDados(conn);
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao executar o backup."));
      return false;
    } finally {
      setExecutando(false);
    }
  };

  const carregarLogs = async (): Promise<BackupLogItem[]> => {
    if (!conn) return [];
    const j = await apiGet(conn, "/api/backup-sistema/logs?limite=50");
    if (!j?.success) {
      fb.showError(friendlyApiError(j, "Falha ao carregar o histórico de backup."));
      return [];
    }
    return (j.itens || []) as BackupLogItem[];
  };

  return { loadingInit, saving, executando, form, setField, save, executarAgora, carregarLogs };
}
