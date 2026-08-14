// Movimentação de Itens — migração de FrmRelMovCli.frm (Painel de
// Relatórios > Estoque). Ledger universal (Vendas/Requisição/
// Inventário/Manual) no período.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type MovimentacaoItemRow = {
  data: string | null; tipo: string; tipo_desc: string; codigo_int: string; produto_descricao: string;
  qtd: number; p_unit: number; valor: number; num_nf: number | null; origem: string; origem_label: string;
  vendedor_nome: string;
};
export type MovimentacaoItensPayload = {
  titulo: string; periodo: string; itens: MovimentacaoItemRow[];
  totais: { qtd: number; valor: number }; empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : "—";
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: MovimentacaoItensPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (i) => `
        <tr>
          <td>${brDate(i.data)}</td>
          <td>${esc(i.tipo_desc)}</td>
          <td>${esc(i.origem_label)}</td>
          <td>${esc(i.produto_descricao)}</td>
          <td class="num">${i.qtd}</td>
          <td class="num">${brl(i.p_unit)}</td>
          <td class="num">${brl(i.valor)}</td>
          <td>${i.num_nf ?? "—"}</td>
          <td>${esc(i.vendedor_nome)}</td>
        </tr>`
    )
    .join("");
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 10px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 4px 5px; border-bottom: 1px solid #eee; font-size: 9px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    tfoot td { font-weight: 700; border-top: 2px solid #1f3a93; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead>
        <tr><th>Data</th><th>Tipo</th><th>Origem</th><th>Produto</th><th class="num">Qtd</th><th class="num">Vlr. Unit</th><th class="num">Valor</th><th>NF/Doc</th><th>Responsável</th></tr>
      </thead>
      <tbody>${linhas || '<tr><td colspan="9">Nenhuma movimentação no período.</td></tr>'}</tbody>
      <tfoot><tr><td colspan="4">TOTAL</td><td class="num">${p.totais.qtd}</td><td></td><td class="num">${brl(p.totais.valor)}</td><td colspan="2"></td></tr></tfoot>
    </table>
  </body></html>`;
}

export async function exportMovimentacaoItensPdf(payload: MovimentacaoItensPayload): Promise<void> {
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
