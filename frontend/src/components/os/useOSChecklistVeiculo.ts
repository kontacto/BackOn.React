// Hook do Checklist de Entrada de Veículo (`os_checklist_veiculo`, via
// `/api/os-completo/{codigo}/checklist-veiculo...`) — O.S. Oficina, pedido
// explícito do usuário 2026-08-26, sem precedente no legado. Cada marcação
// é um toque no diagrama do veículo (ver ChecklistVeiculoDiagrama.tsx),
// não uma pergunta fixa Sim/Não/Reparar. Mesmo formato de
// useOSEquipamentos.ts — sem handleUpdate (sem PUT/editar aqui: errou a
// marcação, cancela e marca de novo).
import { useCallback, useEffect, useState } from "react";
import { Platform } from "react-native";

import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { OSChecklistVeiculoRow } from "./types";
import { ToastTone } from "@/src/components/pedido/types";

type Params = {
  conn: Connection | null;
  editing: boolean;
  osId: number | null;
  usuarioCod: number;
  classe: number | null;
  showToast: (m: string, t?: ToastTone) => void;
};

const BASE_PATH = "/api/os-completo";

export type ChecklistConclusao = {
  concluido: boolean;
  semAvaria: boolean;
  concluidoPor: string;
  concluidoData: string | null;
  concluidoHora: string;
};

const CONCLUSAO_VAZIA: ChecklistConclusao = {
  concluido: false, semAvaria: false, concluidoPor: "", concluidoData: null, concluidoHora: "",
};

export function useOSChecklistVeiculo({ conn, editing, osId, usuarioCod, classe, showToast }: Params) {
  const [checklist, setChecklist] = useState<OSChecklistVeiculoRow[]>([]);
  const [checklistLoading, setChecklistLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [cancelingCodigo, setCancelingCodigo] = useState<number | null>(null);
  const [concluindo, setConcluindo] = useState(false);
  const [conclusao, setConclusao] = useState<ChecklistConclusao>(CONCLUSAO_VAZIA);

  const loadChecklist = useCallback(async () => {
    if (!conn || !editing || !osId) return;
    setChecklistLoading(true);
    try {
      const j = await apiGet(conn, `${BASE_PATH}/${osId}/checklist-veiculo`);
      if (j?.success) {
        setChecklist(j.items || []);
        setConclusao({
          concluido: !!j.concluido, semAvaria: !!j.sem_avaria,
          concluidoPor: j.concluido_por || "", concluidoData: j.concluido_data || null,
          concluidoHora: j.concluido_hora || "",
        });
      }
    } catch {
      // silencioso — mesma cautela já usada em useOSEquipamentos
    } finally {
      setChecklistLoading(false);
    }
  }, [conn, editing, osId]);

  useEffect(() => { loadChecklist(); }, [loadChecklist]);

  const handleAdd = async (tipoAvaria: string, posX: number, posY: number, descricao: string) => {
    if (!conn || !osId) return;
    setAdding(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/checklist-veiculo`, "POST", {
        tipo_avaria: tipoAvaria, pos_x: posX, pos_y: posY, descricao,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao marcar avaria."), "error"); return; }
      showToast("Marcação incluída no checklist.", "success");
      loadChecklist();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao marcar avaria."), "error");
    } finally {
      setAdding(false);
    }
  };

  const handleCancelar = async (itemCodigo: number) => {
    if (!conn || !osId) return;
    setCancelingCodigo(itemCodigo);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/checklist-veiculo/${itemCodigo}/cancelar`, "POST", {
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao cancelar marcação."), "error"); return; }
      showToast("Marcação cancelada.", "success");
      loadChecklist();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao cancelar marcação."), "error");
    } finally {
      setCancelingCodigo(null);
    }
  };

  const handleConcluir = async () => {
    if (!conn || !osId) return;
    setConcluindo(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/checklist-veiculo/concluir`, "POST", {
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao concluir o checklist."), "error"); return; }
      showToast(
        j.sem_avaria ? "Checklist concluído — nenhuma avaria encontrada." : "Checklist concluído.",
        "success",
      );
      loadChecklist();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao concluir o checklist."), "error");
    } finally {
      setConcluindo(false);
    }
  };

  return {
    checklist, checklistLoading, loadChecklist,
    adding, handleAdd,
    cancelingCodigo, handleCancelar,
    conclusao, concluindo, handleConcluir,
  };
}

export type UseOSChecklistVeiculo = ReturnType<typeof useOSChecklistVeiculo>;
