// Resumo Atendimento — migração de frmrelos.frm/FrmRelOSs (Painel de
// Relatórios > Pré Venda). Uma linha por O.S. no período, técnico, horas
// e quebra por destino (Cliente Pg./Contrato/Garantia).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ResumoAtendimentoItem = {
  os: number; data_termino: string | null; tecnico_nome: string;
  hora_inicio: string | null; hora_fim: string | null;
  tot_horas: number; tot_servicos: number; tot_pecas: number;
  tot_contrato: number; tot_garantia: number; tot_cliente_pg: number;
  tipo_desc: string; resumo: string;
};
export type ResumoAtendimentoTotais = {
  horas: number; servicos: number; pecas: number; contrato: number; garantia: number; cliente_pg: number;
};
export type ResumoAtendimentoPayload = {
  titulo: string; periodo: string; itens: ResumoAtendimentoItem[];
  totais: ResumoAtendimentoTotais; empresa?: EmpresaHeader | null;
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

function buildHtml(p: ResumoAtendimentoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.itens
    .map(
      (i) => `
        <tr>
          <td>${brDate(i.data_termino)}</td>
          <td>${i.os}</td>
          <td>${esc(i.tecnico_nome)}</td>
          <td>${esc(i.hora_inicio || "—")}</td>
          <td>${esc(i.hora_fim || "—")}</td>
          <td class="num">${i.tot_horas}</td>
          <td class="num">${brl(i.tot_servicos)}</td>
          <td class="num">${brl(i.tot_pecas)}</td>
          <td class="num">${brl(i.tot_contrato)}</td>
          <td class="num">${brl(i.tot_garantia)}</td>
          <td class="num">${brl(i.tot_cliente_pg)}</td>
          <td>${esc(i.tipo_desc)}</td>
          <td>${esc(i.resumo)}</td>
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
        <tr>
          <th>Data</th><th>O.S.</th><th>Técnico</th><th>Início</th><th>Fim</th>
          <th class="num">T.Horas</th><th class="num">Serviço(s)</th><th class="num">Peça(s)</th>
          <th class="num">Contrato</th><th class="num">Garantia</th><th class="num">Cliente Pg.</th>
          <th>Tipo</th><th>Serviço Executado</th>
        </tr>
      </thead>
      <tbody>${linhas || '<tr><td colspan="13">Nenhum registro no período.</td></tr>'}</tbody>
      <tfoot>
        <tr>
          <td colspan="5">TOTAIS</td>
          <td class="num">${p.totais.horas}</td>
          <td class="num">${brl(p.totais.servicos)}</td>
          <td class="num">${brl(p.totais.pecas)}</td>
          <td class="num">${brl(p.totais.contrato)}</td>
          <td class="num">${brl(p.totais.garantia)}</td>
          <td class="num">${brl(p.totais.cliente_pg)}</td>
          <td colspan="2"></td>
        </tr>
      </tfoot>
    </table>
  </body></html>`;
}

export async function exportResumoAtendimentoPdf(payload: ResumoAtendimentoPayload): Promise<void> {
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
