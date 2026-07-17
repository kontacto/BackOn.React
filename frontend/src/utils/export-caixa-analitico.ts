// Impressão do Caixa Analítico — mesmo padrão de export-fechamento-caixa.ts
// (expo-print, cabeçalho de empresa compartilhado, sem o filtro da tela no
// PDF). Aqui o conteúdo é uma única grade larga (uma linha por período +
// TOTAIS), réplica da ListView de `FrmTotCaixa.frm`.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type CaixaAnaliticoLinha = {
  label: string;
  total_caixa: number;
  total_recebidos: number;
  total_entradas: number;
  total_saidas: number;
  dinheiro: number;
  cheque: number;
  credito: number;
  debito: number;
  vale: number;
  ticket: number;
  duplicata: number;
  financiado: number;
};

export type CaixaAnaliticoPayload = {
  periodo: string;
  agrupamentoLabel: string;
  empresa?: EmpresaHeader | null;
  linhas: CaixaAnaliticoLinha[];
  totais: CaixaAnaliticoLinha;
};

type NumCol = Exclude<keyof CaixaAnaliticoLinha, "label">;
const COLS: { key: NumCol; label: string }[] = [
  { key: "total_caixa", label: "Total Caixa" },
  { key: "total_recebidos", label: "Total Recebidos" },
  { key: "total_entradas", label: "Total Entradas" },
  { key: "total_saidas", label: "Total Saídas" },
  { key: "dinheiro", label: "Dinheiro" },
  { key: "cheque", label: "Cheque" },
  { key: "credito", label: "Crédito" },
  { key: "debito", label: "Débito" },
  { key: "vale", label: "Vale" },
  { key: "ticket", label: "Ticket" },
  { key: "duplicata", label: "Duplicata" },
  { key: "financiado", label: "Financiado" },
];

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: CaixaAnaliticoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.linhas
    .map(
      (l) => `<tr>
        <td>${esc(l.label)}</td>
        ${COLS.map((c) => `<td class="num">${brl(l[c.key])}</td>`).join("")}
      </tr>`
    )
    .join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 11px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 12px; text-align: center; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 4px 5px; border-bottom: 1px solid #eee; font-size: 10px; white-space: nowrap; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    tr.total td { font-weight: 700; border-top: 2px solid #333; }
    .footnote { margin-top: 16px; font-size: 10px; color: #888; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, `Caixa Analítico — ${esc(p.agrupamentoLabel)}`)}
    <div class="meta">${esc(p.periodo)}</div>
    <table>
      <thead><tr><th>Data</th>${COLS.map((c) => `<th class="num">${c.label}</th>`).join("")}</tr></thead>
      <tbody>
        ${linhas || `<tr><td colspan="${COLS.length + 1}">Nenhum lançamento no período.</td></tr>`}
        <tr class="total"><td>TOTAIS</td>${COLS.map((c) => `<td class="num">${brl(p.totais[c.key])}</td>`).join("")}</tr>
      </tbody>
    </table>
    <div class="footnote">Gerado em ${esc(geradoEm)}</div>
  </body></html>`;
}

export async function exportCaixaAnaliticoPdf(payload: CaixaAnaliticoPayload): Promise<void> {
  const html = buildHtml(payload);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, {
      mimeType: "application/pdf",
      dialogTitle: "Caixa Analítico",
      UTI: "com.adobe.pdf",
    });
  } else {
    await Print.printAsync({ uri });
  }
}
