// Venda por Região/Segmento — migração de Guerengases\FrmVenTot.frm
// (Painel de Relatórios > Vendas). Agrupamento configurável por até 4
// dimensões (Região/Segmento/Rota/Vendedor) — colunas dinâmicas conforme
// o que o usuário marcou.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export const DIM_LABEL: Record<string, string> = {
  regiao: "Região", segmento: "Segmento", rota: "Rota", vendedor: "Vendedor",
};

export type VendaRegiaoRow = { [dim: string]: string | number | undefined; qtd: number; valor: number };
export type VendaRegiaoPayload = {
  titulo: string; periodo: string; dimensoes: string[];
  itens: VendaRegiaoRow[]; totais: { qtd: number; valor: number }; empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: VendaRegiaoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const dims = p.dimensoes.length ? p.dimensoes : [];
  const headerCols = dims.length
    ? dims.map((d) => `<th>${esc(DIM_LABEL[d] || d)}</th>`).join("")
    : `<th>Total Geral</th>`;
  const linhas = p.itens
    .map((i) => {
      const cols = dims.length
        ? dims.map((d) => `<td>${esc(String(i[d] ?? ""))}</td>`).join("")
        : `<td>Total Geral</td>`;
      return `<tr>${cols}<td class="num">${i.qtd}</td><td class="num">${brl(i.valor)}</td></tr>`;
    })
    .join("");
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 11px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; font-size: 10px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    tfoot td { font-weight: 700; border-top: 2px solid #1f3a93; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr>${headerCols}<th class="num">Qtd</th><th class="num">Valor</th></tr></thead>
      <tbody>${linhas || `<tr><td colspan="${dims.length + 2 || 3}">Nenhum registro no período.</td></tr>`}</tbody>
      <tfoot><tr><td colspan="${dims.length || 1}">TOTAL</td><td class="num">${p.totais.qtd}</td><td class="num">${brl(p.totais.valor)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportVendaRegiaoPdf(payload: VendaRegiaoPayload): Promise<void> {
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
