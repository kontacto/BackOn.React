// Dias da semana (0=Domingo..6=Sábado) em que um profissional atende —
// janela de 7 dias a partir de hoje é suficiente pra cobrir o padrão
// semanal (Ausência pontual não muda esse padrão, só marca slots como
// "ausente" dentro de um dia que "atende"). Reaproveita o mesmo
// `GET /agenda/grade` já usado pela grade/lista de horários — sem endpoint
// novo. Compartilhado por `AgendarModal.tsx` (Pedido Geral) e
// `app/agenda.tsx` (tela Agenda) — extraído pra não duplicar a mesma busca
// nos dois lugares (2026-07-28, user-directed: "só exibir data/horário em
// que o funcionário atende").
import { useEffect, useState } from "react";
import { apiGet } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";

export function useDiasAtende(conn: Connection | null, funcionario: number | null): Set<number> | null {
  const [diasAtende, setDiasAtende] = useState<Set<number> | null>(null);

  useEffect(() => {
    if (!conn || !funcionario) {
      setDiasAtende(null);
      return;
    }
    let ativo = true;
    (async () => {
      const hoje = new Date();
      const ini = hoje.toISOString().slice(0, 10);
      const fimDate = new Date(hoje);
      fimDate.setDate(fimDate.getDate() + 6);
      const fim = fimDate.toISOString().slice(0, 10);
      const j = await apiGet(conn, "/api/agenda/grade", { funcionario, data_ini: ini, data_fim: fim });
      if (!ativo) return;
      if (j?.success && Array.isArray(j.dias)) {
        const set = new Set<number>();
        j.dias.forEach((d: { data: string; atende: boolean }) => {
          if (d.atende) set.add(new Date(`${d.data}T00:00:00`).getDay());
        });
        setDiasAtende(set);
      } else {
        setDiasAtende(null);
      }
    })();
    return () => {
      ativo = false;
    };
  }, [funcionario, conn]);

  return diasAtende;
}
