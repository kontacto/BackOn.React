// Ordem de Serviço (busca) — migração de FrmRelOS.frm (Painel de
// Relatórios > Pré Venda). Lista de O.S. encontradas pelo filtro ativo.
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type BuscaOsItem = {
  cliente_codigo: number; cliente_nome: string; os: number; veiculo: string;
  data_entrada: string | null; data_termino: string | null; placa: string; chassi: string; situacao: string;
};
export type BuscaOsPayload = {
  titulo: string; criterio: string; itens: BuscaOsItem[]; empresa?: EmpresaHeader | null;
};

function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : "—";
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: BuscaOsPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (i) => `
        <tr>
          <td>${esc(i.cliente_nome)}</td>
          <td>${i.os}</td>
          <td>${esc(i.veiculo)}</td>
          <td>${brDate(i.data_entrada)}</td>
          <td>${brDate(i.data_termino)}</td>
          <td>${esc(i.placa)}</td>
          <td>${esc(i.chassi)}</td>
          <td>${esc(i.situacao)}</td>
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
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${esc(p.criterio)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead><tr><th>Cliente</th><th>OS</th><th>Veículo</th><th>Entrada</th><th>Término</th><th>Placa</th><th>Chassi</th><th>Sit.</th></tr></thead>
      <tbody>${linhas || '<tr><td colspan="8">Nenhum registro encontrado.</td></tr>'}</tbody>
    </table>
  </body></html>`;
}

export async function exportBuscaOsPdf(payload: BuscaOsPayload): Promise<void> {
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
