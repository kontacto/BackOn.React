// Apoio Fiscal BackOn — ponto único de decisão entre "mostrar a tradução
// didática da rejeição fiscal" (quando o backend anexou `apoio_fiscal` na
// resposta, ver services/apoio_fiscal_service.py) e o erro genérico de
// sempre (`friendlyApiError`). Uso típico numa tela de emissão/
// cancelamento fiscal:
//
//   const info = showApoioFiscalError(fb, j, "Falha ao emitir a nota.");
//   if (info) setApoioFiscalInfo(info); // abre <ApoioFiscalBackOnModal>
//
// Não abre o modal sozinho — devolve os dados pra tela decidir (mesmo
// padrão de state local já usado pelos outros modais deste projeto), já
// que `useFeedback()` só sabe mostrar toast/confirmação simples, não um
// modal com conteúdo custom.
import type { FeedbackApi } from "@/src/components/feedback/FeedbackProvider";
import { friendlyApiError } from "@/src/utils/api";
import type { ApoioFiscalInfo } from "@/src/components/ApoioFiscalBackOnModal";

export function showApoioFiscalError(fb: FeedbackApi, j: any, fallback: string, durationMs?: number): ApoioFiscalInfo | null {
  const af = j?.apoio_fiscal;
  if (af && typeof af === "object" && af.titulo) {
    return {
      titulo: af.titulo,
      explicacao_curta: af.explicacao_curta || "",
      explicacao_detalhada: af.explicacao_detalhada || "",
      acao_usuario: af.acao_usuario ?? null,
      notificado_suporte: af.notificado_suporte,
    };
  }
  fb.showError(friendlyApiError(j, fallback), undefined, durationMs);
  return null;
}
