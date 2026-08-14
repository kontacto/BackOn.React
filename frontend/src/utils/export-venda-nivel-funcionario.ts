// Venda por Vendedor × Nível — migração de Kontacto\frmrelvennivfun.frm
// (Painel de Relatórios > Vendas). Venda/custo/margem por nível, dentro
// de um vendedor/executor (ou todos agregados).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type VendaNivelFuncionarioRow = { codigo: string; label: string; venda: number; custo: number; margem: number; margem_pct: number };
export type VendaNivelFuncionarioPayload = {
  titulo: string; periodo: string; modo: "vendedor" | "executor"; funcNome: string;
  niveis: VendaNivelFuncionarioRow[]; totais: { venda: number; custo: number; margem: number; margem_pct: number };
  empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function pct(v: number): string {
  return `${(v || 0).toFixed(2).replace(".", ",")}%`;
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: VendaNivelFuncionarioPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.niveis
    .map(
      (n) => `
        <tr>
          <td>${esc(n.label)}</td>
          <td class="num">${brl(n.venda)}</td>
          <td class="num">${brl(n.custo)}</td>
          <td class="num">${brl(n.margem)}</td>
          <td class="num">${pct(n.margem_pct)}</td>
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
    <div class="meta">${esc(p.periodo)} · ${esc(p.funcNome || "Todos")} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Nível</th><th class="num">Venda</th><th class="num">Custo</th><th class="num">Margem</th><th class="num">Margem %</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="5">Nenhum registro no período.</td></tr>'}</tbody>
      <tfoot><tr><td>TOTAL</td><td class="num">${brl(p.totais.venda)}</td><td class="num">${brl(p.totais.custo)}</td><td class="num">${brl(p.totais.margem)}</td><td class="num">${pct(p.totais.margem_pct)}</td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportVendaNivelFuncionarioPdf(payload: VendaNivelFuncionarioPayload): Promise<void> {
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
