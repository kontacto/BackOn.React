// Itens do Pedido — migração de FrmItePEd.frm (Painel de Relatórios >
// Pré Venda). Auxiliar de reposição/compra: quantidade vendida por
// produto (Pedido Fechado) no período.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ItemPedidoPedido = { pedido: number; cliente_nome: string; qtd_pedida: number };
export type ItemPedido = {
  codigo_fab: string; descricao: string; unidade_compra: string;
  fator: number; qtd_total: number; qtd_compra: number; pedidos: ItemPedidoPedido[];
};
export type ItensPedidoPayload = {
  titulo: string; periodo: string; itens: ItemPedido[]; empresa?: EmpresaHeader | null;
};

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: ItensPedidoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (i) => `
        <tr>
          <td>${esc(i.codigo_fab)}</td>
          <td>${esc(i.descricao)}</td>
          <td>${esc(i.unidade_compra)}</td>
          <td class="num">${i.fator}</td>
          <td class="num">${i.qtd_total}</td>
          <td class="num">${i.qtd_compra}</td>
        </tr>`
    )
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
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Código</th><th>Descrição</th><th>Uni.</th><th class="num">Fator</th><th class="num">Total Qtd.</th><th class="num">Total Geral</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="6">Nenhum registro no período.</td></tr>'}</tbody>
    </table>
  </body></html>`;
}

export async function exportItensPedidoPdf(payload: ItensPedidoPayload): Promise<void> {
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
