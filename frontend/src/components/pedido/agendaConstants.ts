// 13 estados de "Situação do Atendimento" — réplica exata da lista fixa do
// backend (`agenda_service.SITUACOES_ATENDIMENTO`, `FrmAtende.frm`/
// `FrmMarAge2.frm`'s `Form_Load`). Mantida em sincronia manualmente — sem
// endpoint de lookup, é texto livre fixo dos dois lados.
export const SITUACOES_ATENDIMENTO = [
  "Aguardando", "Em Atendimento", "Atendido", "Desistência", "Não Confirmado",
  "Confirmado", "Avaliação", "Avaliado", "Chamando", "Ausente", "Medicar",
  "Medicado", "Encaminhar", "Encaminhado",
];

// Rótulo por dia da semana (índice = `Date.getDay()`, 0=Domingo) — usado em
// toda tela de Agenda pra explicar/validar em quais dias um profissional
// atende (ver `useDiasAtende`, `AgendarModal.tsx`, `app/agenda.tsx`).
export const DIA_SEMANA_LABEL = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];
