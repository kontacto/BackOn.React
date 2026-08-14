// Apuração de Vendas - DRE — migração de FrmRelAPV.frm (Painel de
// Relatórios > Caixa). Fase 1: grid mensal com as 5 categorias + Total +
// Custo + Margem (sem Despesas — ver PENDENCIAS.md > "Painel de
// Relatórios (VB6)" > "Apuração Vendas - DRE").
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ApuracaoVendasMes = {
  ano: number;
  mes: number;
  contratos: number;
  produtos_os: number;
  servicos_os: number;
  venda_produtos: number;
  venda_servicos: number;
  total: number;
  custo: number;
  margem: number;
  margem_pct: number;
};

export type ApuracaoVendasPayload = {
  titulo: string;
  periodo: string;
  meses: ApuracaoVendasMes[];
  totais: { total: number; custo: number; margem: number; margem_pct: number };
  empresa?: EmpresaHeader | null;
};

const MESES_NOME = [
  "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

export function mesAnoLabel(ano: number, mes: number): string {
  return `${MESES_NOME[mes] || mes}/${ano}`;
}

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function pct(v: number): string {
  return `${(v || 0).toFixed(2).replace(".", ",")}%`;
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: ApuracaoVendasPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const linhas = p.meses
    .map(
      (m) => `
        <tr>
          <td>${esc(mesAnoLabel(m.ano, m.mes))}</td>
          <td class="num">${brl(m.contratos)}</td>
          <td class="num">${brl(m.produtos_os)}</td>
          <td class="num">${brl(m.servicos_os)}</td>
          <td class="num">${brl(m.venda_produtos)}</td>
          <td class="num">${brl(m.venda_servicos)}</td>
          <td class="num">${brl(m.total)}</td>
          <td class="num">${brl(m.custo)}</td>
          <td class="num">${brl(m.margem)}</td>
          <td class="num">${pct(m.margem_pct)}</td>
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
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <table>
      <thead>
        <tr>
          <th>Mês/Ano</th><th class="num">Contratos</th><th class="num">Produtos O.S.</th>
          <th class="num">Serviços O.S.</th><th class="num">Venda Produtos</th>
          <th class="num">Venda Serviços</th><th class="num">Total</th><th class="num">Custo</th>
          <th class="num">Margem</th><th class="num">Margem %</th>
        </tr>
      </thead>
      <tbody>${linhas || '<tr><td colspan="10">Nenhum registro no período.</td></tr>'}</tbody>
      <tfoot>
        <tr>
          <td colspan="6">TOTAL GERAL</td>
          <td class="num">${brl(p.totais.total)}</td>
          <td class="num">${brl(p.totais.custo)}</td>
          <td class="num">${brl(p.totais.margem)}</td>
          <td class="num">${pct(p.totais.margem_pct)}</td>
        </tr>
      </tfoot>
    </table>
    <p style="font-size:10px;color:#888;margin-top:12px;">
      Margem = Total − Custo (sem dedução de despesas configuradas — ver Fase 2).
    </p>
  </body></html>`;
}

export async function exportApuracaoVendasPdf(payload: ApuracaoVendasPayload): Promise<void> {
  const html = buildHtml(payload);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, {
      mimeType: "application/pdf",
      dialogTitle: payload.titulo,
      UTI: "com.adobe.pdf",
    });
  } else {
    await Print.printAsync({ uri });
  }
}
