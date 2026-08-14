// Inatividade de Clientes — migração de Geral\FrmRelCliSMV.frm (Painel de
// Relatórios > Clientes). PDF mais enxuto que a tela (só Cliente + Última
// Compra, fiel ao legado — Imprimir é mais magro que Gerar Planilha lá
// também).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ClienteInativoRow = {
  codigo: number; nome: string; situacao: string; ultima_compra: string | null;
  ciclos: { qtd_pedidos: number; dias_medio: number | null }[];
  ultimo_faturamento_contrato?: string | null; ultimo_faturamento_contrato_pago?: string | null;
  telefones: string[];
};

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(periodo: string, clientes: ClienteInativoRow[], empresa: EmpresaHeader | null): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = clientes
    .map((c) => `<tr><td>${esc(c.nome)}</td><td>${esc(c.ultima_compra || "—")}</td></tr>`)
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
  </style></head><body>
    ${buildReportHeaderHtml(empresa, "Relatório de Inatividade de Clientes")}
    <div class="meta">${esc(periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Cliente</th><th>Última Compra</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="2">Nenhum cliente inativo no período.</td></tr>'}</tbody>
    </table>
  </body></html>`;
}

export async function exportInatividadeClientesPdf(periodo: string, clientes: ClienteInativoRow[], empresa: EmpresaHeader | null): Promise<void> {
  const html = buildHtml(periodo, clientes, empresa);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Inatividade de Clientes", UTI: "com.adobe.pdf" });
  } else {
    await Print.printAsync({ uri });
  }
}
