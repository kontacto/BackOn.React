// Motor de sincronização da fila offline do Atendimento de Campo — extraído
// de os-atendimento.tsx (2026-08-14, achado de revisão Gauntlet retroativa)
// pra ser reaproveitável também por os-lista.tsx: antes, só a OS ABERTA NA
// TELA tinha sua fila sincronizada — um técnico que visita várias OS's
// offline e só volta a ter conexão horas depois (ex.: de volta à base) não
// sincronizava nada até reabrir manualmente cada uma. Ver
// AssistenciaTecnicaCampo.md seção 8.
//
// Sem estado de componente — cada chamada é independente; quem chama
// decide o que fazer com o resultado (UI rica com banner de conflito em
// os-atendimento.tsx, best-effort silencioso em os-lista.tsx).
import { apiGet, apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import {
  listarFilaPendente, removerDaFila, marcarConflito, marcarErro, incrementarTentativa,
  getOsCacheada, MutacaoPendente,
} from "@/src/utils/storage/offlineAtendimento";

export type SyncResultado = {
  algumSucesso: boolean;
  conflito: { id: string; message: string } | null;
};

async function enviarMutacao(
  conn: Connection, osId: number, m: MutacaoPendente, versaoAtual: string | null,
): Promise<{ success?: boolean; conflito?: boolean; message?: string; [k: string]: unknown } | null> {
  if (m.tipo === "formulario") {
    return apiSend(conn, "/api/layout/preencher", "POST", m.payload);
  }
  const payloadComVersao = { ...m.payload, versao_esperada: versaoAtual };
  if (m.tipo === "checkin") return apiSend(conn, `/api/os/${osId}/checkin`, "POST", payloadComVersao);
  if (m.tipo === "checkout") return apiSend(conn, `/api/os/${osId}/checkout`, "POST", payloadComVersao);
  if (m.tipo === "fechar") return apiSend(conn, `/api/os/${osId}/fechar-atendimento`, "POST", payloadComVersao);
  if (m.tipo === "equipamento") return apiSend(conn, `/api/os-completo/${osId}/equipamentos/${m.itemCodigo}`, "PUT", payloadComVersao);
  return null;
}

// Reenvia a fila pendente de UMA OS, na ordem em que foi enfileirada,
// sempre com `versao_esperada` (concorrência otimista — bloqueia e nunca
// sobrescreve, decisão de negócio já fechada). Regras do laço:
//  - conflito de versão → marca, PARA o processamento (estado incerto a
//    partir daí, exige o técnico recarregar os dados — decisão de negócio).
//  - falha de rede (ainda offline) → incrementa tentativa, PARA (tenta de
//    novo no próximo ciclo).
//  - falha de regra de negócio genuína (nem conflito, nem rede) → marca
//    erro e CONTINUA com o resto da fila (não bloqueia mutações de outros
//    tipos/itens só porque uma falhou por um motivo que só aquela mutação
//    tem — achado de revisão Gauntlet: bloquear tudo perdia trabalho válido
//    atrás de um item preso).
export async function syncFilaOS(conn: Connection, osId: number, versaoInicial: string | null): Promise<SyncResultado> {
  const pendentes = await listarFilaPendente(osId);
  if (pendentes.length === 0) return { algumSucesso: false, conflito: null };
  let versaoAtual = versaoInicial;
  let algumSucesso = false;
  let conflito: { id: string; message: string } | null = null;
  for (const m of pendentes) {
    try {
      const resp = await enviarMutacao(conn, osId, m, versaoAtual);
      if (resp?.conflito) {
        const msg = (resp.message as string) || "Esta OS mudou enquanto você estava offline.";
        await marcarConflito(m.id, msg);
        if (!conflito) conflito = { id: m.id, message: msg };
        break;
      }
      if (!resp?.success) {
        await marcarErro(m.id, (resp?.message as string) || "Falha ao sincronizar este item.");
        await incrementarTentativa(m.id);
        continue;
      }
      await removerDaFila(m.id);
      algumSucesso = true;
      // checkin/checkout/fechar bumpam a MESMA coluna que a checagem de
      // equipamento também usa — busca a versão fresca antes do próximo
      // item, senão a própria sincronização gera um "falso conflito"
      // contra si mesma.
      const fresh = await apiGet(conn, `/api/os-completo/${osId}`);
      if (fresh?.success && fresh.os) versaoAtual = fresh.os.versao_atendimento ?? versaoAtual;
    } catch (e) {
      if (e instanceof TypeError) { await incrementarTentativa(m.id); break; } // ainda offline
      await marcarErro(m.id, "Falha inesperada ao sincronizar.");
      await incrementarTentativa(m.id);
    }
  }
  return { algumSucesso, conflito };
}

// Varre TODA a fila do dispositivo (todas as OS's visitadas offline, não
// só a que está aberta na tela) e tenta sincronizar cada uma — chamado por
// os-lista.tsx assim que a lista carrega com conexão. Best-effort e
// silencioso: um conflito marcado aqui não tem UI própria nesta tela, só
// reaparece (com o banner bloqueante correto) quando o técnico reabrir
// aquela OS específica em os-atendimento.tsx.
export async function syncTodasFilasPendentes(conn: Connection): Promise<void> {
  try {
    const todas = await listarFilaPendente();
    const osIds = Array.from(new Set(todas.map((m) => m.osId)));
    for (const osId of osIds) {
      const cache = await getOsCacheada(osId);
      await syncFilaOS(conn, osId, cache?.versaoAtendimento ?? null);
    }
  } catch {
    // best-effort — nunca deve quebrar o carregamento da lista
  }
}
