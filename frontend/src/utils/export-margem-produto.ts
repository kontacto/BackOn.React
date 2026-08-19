// Margem de Lucro (por produto) — migração de Gilson Pneus\FrmRelPecMLC.frm
// (Painel de Relatórios > Margem). Ver relatorio-margem-produto.tsx.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type MargemProdutoRow = {
  codigo: string | number | null; descricao: string; custo: number; venda: number; margem_pct: number | null;
};
export type MargemProdutoPayload = {
  titulo: string; codigoLabel: string; nivelLabel: string;
  itens: MargemProdutoRow[];
  totalCusto: number; totalVenda: number; margemTotalPct: number | null;
  empresa?: EmpresaHeader | null;
};

function moeda(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function pct(v: number | null): string {
  return v === null || v === undefined ? "—" : `${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: MargemProdutoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (it) => `
        <tr>
          <td>${esc(String(it.codigo ?? ""))}</td>
          <td>${esc(it.descricao)}</td>
          <td class="num">${moeda(it.custo)}</td>
          <td class="num">${moeda(it.venda)}</td>
          <td class="num">${pct(it.margem_pct)}</td>
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
    <div class="meta">Nível: ${esc(p.nivelLabel || "Todos")} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>${esc(p.codigoLabel)}</th><th>Descrição</th><th class="num">Preço Custo</th><th class="num">Preço Venda</th><th class="num">Margem</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="5">Nenhum produto encontrado.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="2">TOTAL GERAL</td><td class="num">${moeda(p.totalCusto)}</td><td class="num">${moeda(p.totalVenda)}</td><td class="num">${pct(p.margemTotalPct)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportMargemProdutoPdf(payload: MargemProdutoPayload): Promise<void> {
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
