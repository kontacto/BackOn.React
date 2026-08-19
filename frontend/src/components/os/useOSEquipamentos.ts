// Hook de equipamentos vinculados a uma O.S. Completa (`os_equipamento`,
// via `/api/os-completo/{codigo}/equipamentos...`) — Assistência Técnica,
// Fase 1 (ver AssistenciaTecnicaCampo.md seção 5, regra 14: "uma OS pode
// ter vários equipamentos"). Substitui o campo único "Dados do
// Equipamento" (antigo `numeroSerie`/`equipamentoSel` em `os-geral.tsx`)
// por uma lista — cada linha com seu próprio Defeito Reclamado/Serviço
// Executado/Serviço a Executar/Diagnóstico/Status (reaproveita `status_os`)
// e ação de Cancelar (soft, item-level).
//
// Vincular um equipamento novo continua usando `EquipamentoSearchModal`
// já existente em `os-geral.tsx` (busca/cadastro rápido reaproveitados tal
// como estão) — este hook só expõe `handleAdd` pra receber o `EquipamentoRow`
// escolhido e persistir o vínculo.
import { useCallback, useEffect, useState } from "react";
import { Platform } from "react-native";

import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { EquipamentoRow } from "@/src/components/EquipamentoSearchModal";
import { OSEquipamentoRow } from "./types";
import { ToastTone } from "@/src/components/pedido/types";

type Params = {
  conn: Connection | null;
  editing: boolean;
  osId: number | null;
  usuarioCod: number;
  classe: number | null;
  showToast: (m: string, t?: ToastTone) => void;
  // Rastreabilidade do fluxo "auxiliar edita em nome do técnico" (regra
  // 11, AssistenciaTecnicaCampo.md) — só usado por `os-atendimento.tsx`;
  // `os-geral.tsx` nunca passa isto (fica `undefined`, sem efeito).
  viaAuxiliar?: number | null;
  // Sincronização Offline (Atendimento de Campo) — opcional, só passado por
  // os-atendimento.tsx. Quando a gravação falha por rede (offline), em vez
  // do erro genérico o hook já atualiza `equipamentos` localmente (estado
  // otimista) e chama isto pro chamador enfileirar a mutação. Sem esta
  // prop (`os-geral.tsx`, retaguarda web sempre online), comportamento
  // 100% inalterado.
  onOfflineFallback?: (itemCodigo: number, draft: OSEquipamentoDraft) => void;
};

const BASE_PATH = "/api/os-completo";

export type OSEquipamentoDraft = {
  defeito_reclamado: string;
  servico_executado: string;
  servico_a_executar: string;
  diagnostico: string;
  status_os: number | null;
};

export function useOSEquipamentos({ conn, editing, osId, usuarioCod, classe, showToast, viaAuxiliar, onOfflineFallback }: Params) {
  const [equipamentos, setEquipamentos] = useState<OSEquipamentoRow[]>([]);
  const [equipamentosLoading, setEquipamentosLoading] = useState(false);
  const [adding, setAdding] = useState(false);
  const [savingCodigo, setSavingCodigo] = useState<number | null>(null);
  const [cancelingCodigo, setCancelingCodigo] = useState<number | null>(null);

  const loadEquipamentos = useCallback(async () => {
    if (!conn || !editing || !osId) return;
    setEquipamentosLoading(true);
    try {
      const j = await apiGet(conn, `${BASE_PATH}/${osId}/equipamentos`);
      if (j?.success) setEquipamentos(j.items || []);
    } catch {
      // silencioso — mesma cautela já usada em loadItens
    } finally {
      setEquipamentosLoading(false);
    }
  }, [conn, editing, osId]);

  useEffect(() => { loadEquipamentos(); }, [loadEquipamentos]);

  const handleAdd = async (e: EquipamentoRow) => {
    if (!conn || !osId) return;
    setAdding(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/equipamentos`, "POST", {
        equipamento: e.codigo, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao vincular equipamento."), "error"); return; }
      showToast("Equipamento vinculado.", "success");
      loadEquipamentos();
    } catch (e2) {
      showToast(friendlyCatchError(e2, "Falha ao vincular equipamento."), "error");
    } finally {
      setAdding(false);
    }
  };

  const handleUpdate = async (itemCodigo: number, draft: OSEquipamentoDraft) => {
    if (!conn || !osId) return;
    setSavingCodigo(itemCodigo);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/equipamentos/${itemCodigo}`, "PUT", {
        ...draft, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS, via_auxiliar: viaAuxiliar ?? undefined,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao gravar equipamento."), "error"); return; }
      showToast("Equipamento atualizado.", "success");
      loadEquipamentos();
    } catch (e) {
      if (e instanceof TypeError && onOfflineFallback) {
        // Estado otimista — a tela continua utilizável offline sem esperar
        // sincronizar (decisão do usuário, ver AssistenciaTecnicaCampo.md
        // "Sincronização Offline"); status_os_descricao não é reresolvido
        // aqui (fica com o texto antigo até a próxima sincronização), gap
        // cosmético conhecido e aceito.
        setEquipamentos((prev) => prev.map((it) => (it.codigo === itemCodigo ? { ...it, ...draft } : it)));
        onOfflineFallback(itemCodigo, draft);
        return;
      }
      showToast(friendlyCatchError(e, "Falha ao gravar equipamento."), "error");
    } finally {
      setSavingCodigo(null);
    }
  };

  const handleCancelar = async (itemCodigo: number) => {
    if (!conn || !osId) return;
    setCancelingCodigo(itemCodigo);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/equipamentos/${itemCodigo}/cancelar`, "POST", {
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao cancelar equipamento."), "error"); return; }
      showToast("Equipamento cancelado.", "success");
      loadEquipamentos();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao cancelar equipamento."), "error");
    } finally {
      setCancelingCodigo(null);
    }
  };

  return {
    equipamentos, equipamentosLoading, loadEquipamentos,
    adding, handleAdd,
    savingCodigo, handleUpdate,
    cancelingCodigo, handleCancelar,
  };
}

export type UseOSEquipamentos = ReturnType<typeof useOSEquipamentos>;
