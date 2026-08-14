// Produtos Reservados — migração de frmrelpecres.frm (Painel de
// Relatórios > Estoque). Snapshot atual, sem período.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ProdutoReservadoItem = {
  codigo_int: string; codigo_fab: string; descricao: string;
  p_venda: number; reserva: number; preco_total: number;
};
export type ProdutosReservadosPayload = {
  titulo: string; itens: ProdutoReservadoItem[]; total: number; empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: ProdutosReservadosPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (i) => `
        <tr>
          <td>${esc(i.codigo_int)}</td>
          <td>${esc(i.codigo_fab)}</td>
          <td>${esc(i.descricao)}</td>
          <td class="num">${brl(i.p_venda)}</td>
          <td class="num">${i.reserva}</td>
          <td class="num">${brl(i.preco_total)}</td>
        </tr>`
    )
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
    <div class="meta">Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Cód. Interno</th><th>Cód. Fabricante</th><th>Descrição</th><th class="num">Preço Venda</th><th class="num">Qtd</th><th class="num">Preço Total</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="6">Nenhum produto reservado.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="5">TOTAL</td><td class="num">${brl(p.total)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportProdutosReservadosPdf(payload: ProdutosReservadosPayload): Promise<void> {
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
