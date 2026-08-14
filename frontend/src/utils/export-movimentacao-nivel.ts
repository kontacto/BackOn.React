// Movimentações por Nível — migração de frmrelvenlojas.frm (Painel de
// Relatórios > Estoque). Soma qtd/valor por nível, pra um tipo de
// movimentação escolhido, no período.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type MovimentacaoNivelItem = { codigo: string; label: string; qtd: number; valor: number };
export type MovimentacaoNivelPayload = {
  titulo: string; periodo: string; tipoLabel: string; itens: MovimentacaoNivelItem[];
  totais: { qtd: number; valor: number }; empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: MovimentacaoNivelPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map((i) => `<tr><td>${esc(i.label)}</td><td class="num">${i.qtd}</td><td class="num">${brl(i.valor)}</td></tr>`)
    .join("");
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 12px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; font-size: 11px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    tfoot td { font-weight: 700; border-top: 2px solid #1f3a93; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${esc(p.tipoLabel)} · ${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Nível</th><th class="num">Qtd</th><th class="num">Valor</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="3">Nenhuma movimentação no período.</td></tr>'}</tbody>
      <tfoot><tr><td>TOTAL</td><td class="num">${p.totais.qtd}</td><td class="num">${brl(p.totais.valor)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportMovimentacaoNivelPdf(payload: MovimentacaoNivelPayload): Promise<void> {
  const html = buildHtml(payload);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: payload.titulo, UTI: "com.adobe.pdf" });
  } else {
    await Print.printAsync({ uri });
  }
}
