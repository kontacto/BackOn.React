// Itens Vendidos O.S./Balcão — migração de FrmRelVenOsB.frm (Painel de
// Relatórios > Pré Venda). Quantidade/valor por produto individual
// (Pedido "Balcão" + consumo de O.S.) no período.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ItemVendido = { codigo: string; descricao: string; qtd: number; valor: number };
export type ItensVendidosPayload = {
  titulo: string; periodo: string; itens: ItemVendido[]; total_valor: number; empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: ItensVendidosPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map((i) => `<tr><td>${esc(i.codigo)}</td><td>${esc(i.descricao)}</td><td class="num">${i.qtd}</td><td class="num">${brl(i.valor)}</td></tr>`)
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
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Código</th><th>Descrição</th><th class="num">Qtd.</th><th class="num">Valor</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="4">Nenhum registro no período.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="3">TOTAL</td><td class="num">${brl(p.total_valor)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportItensVendidosPdf(payload: ItensVendidosPayload): Promise<void> {
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
