// Impressão do Fechamento de Caixa — mesmo padrão já usado por
// export-report.ts/export-margem-lucro.ts: monta um HTML e imprime via
// expo-print (`Print.printAsync`), que já resolve web (diálogo de
// impressão do navegador) e mobile (compartilhar/salvar PDF) — não usa o
// truque de CSS "esconde tudo/mostra #id" que se mostrou frágil na
// impressão do Pedido (ver feedback_print_via_iframe_not_css_hide).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type FormaPagamentoLinha = { descricao: string; tipo: string; nao_totaliza_caixa: boolean; valor: number };
export type EntradaSaidaLinha = { descricao: string; valor: number };
export type ResumoTipoLinha = { tipo: string; label: string; valor: number; percentual: number };
export type PedidoSemFormaLinha = { pedido: number; valor: number };

export type FechamentoCaixaPayload = {
  periodo: string;
  // Dados da empresa (Controle) pro cabeçalho — [GLOBAL], sem filtro da
  // tela no PDF (ver print-report-header.ts). Substituiu o campo `filtros`
  // (resumo de Atendente/Área) que existia aqui antes.
  empresa?: EmpresaHeader | null;
  formas_pagamento: FormaPagamentoLinha[];
  subtotal_formas_pagamento: number;
  entradas: EntradaSaidaLinha[];
  total_entradas: number;
  saidas: EntradaSaidaLinha[];
  total_saidas: number;
  despesas_com_comprovante: number;
  despesas_sem_comprovante: number;
  total_caixa: number;
  resumo_tipo: ResumoTipoLinha[];
  total_recebimentos: number;
  // Pedidos faturados (com comanda) no período sem nenhuma forma de
  // pagamento lançada nas tabelas detalhadas — gap real de dados (não
  // entram no TOTAL CAIXA, mas contam no total "Faturado" da Tela
  // Principal via pedido_venda.total). Achado 2026-07-16, ver
  // fechamento_caixa_service.py.
  pedidos_sem_forma_pagamento: PedidoSemFormaLinha[];
  total_sem_forma_pagamento: number;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: FechamentoCaixaPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");

  const linhasFormas = p.formas_pagamento
    .map(
      (f) => `<tr>
        <td>${f.nao_totaliza_caixa ? "(*) " : ""}${esc(f.descricao)}</td>
        <td class="num">${brl(f.valor)}</td>
      </tr>`
    )
    .join("");

  const linhasEntradas = p.entradas
    .map((e) => `<tr><td>Entrada de Caixa: ${esc(e.descricao)}</td><td class="num">${brl(e.valor)}</td></tr>`)
    .join("");
  const linhasSaidas = p.saidas
    .map((s) => `<tr><td>Saída de Caixa: ${esc(s.descricao)}</td><td class="num">${brl(s.valor)}</td></tr>`)
    .join("");

  const linhasSemForma = p.pedidos_sem_forma_pagamento
    .map((s) => `<tr><td>Pedido #${s.pedido}</td><td class="num">${brl(s.valor)}</td></tr>`)
    .join("");

  const linhasResumo = p.resumo_tipo
    .map(
      (r) => `<tr>
        <td>${esc(r.tipo)} ${esc(r.label)}</td>
        <td class="num">${brl(r.valor)}</td>
        <td class="num">${r.percentual.toFixed(2).replace(".", ",")}%</td>
      </tr>`
    )
    .join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 12px; }
    ${REPORT_HEADER_CSS}
    h2 { font-size: 14px; margin: 18px 0 6px; color: #1f3a93; }
    .meta { color: #777; font-size: 11px; margin-bottom: 4px; text-align: center; }
    table { width: 100%; border-collapse: collapse; margin-top: 4px; }
    th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; font-size: 11px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    tr.total td { font-weight: 700; border-top: 2px solid #333; }
    .footnote { margin-top: 16px; font-size: 10px; color: #888; }
    .alerta { margin-top: 14px; padding: 8px 10px; border: 1px solid #e0a800; background: #fff8e1; border-radius: 6px; }
    .alerta-titulo { font-weight: 700; font-size: 11px; color: #8a6100; margin-bottom: 4px; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, "Fechamento de Caixa")}
    <div class="meta">${esc(p.periodo)}</div>

    <h2>Entradas e Saídas</h2>
    <table>
      <thead><tr><th>Forma de Pagamento</th><th class="num">Valor</th></tr></thead>
      <tbody>
        ${linhasFormas}
        <tr class="total"><td>SUB TOTAL</td><td class="num">${brl(p.subtotal_formas_pagamento)}</td></tr>
        ${linhasEntradas}
        ${p.total_entradas ? `<tr class="total"><td>Total de Entradas</td><td class="num">${brl(p.total_entradas)}</td></tr>` : ""}
        ${p.despesas_com_comprovante ? `<tr><td>Despesas com comprovante</td><td class="num">${brl(p.despesas_com_comprovante)}</td></tr>` : ""}
        ${p.despesas_sem_comprovante ? `<tr><td>Despesas sem comprovante</td><td class="num">${brl(p.despesas_sem_comprovante)}</td></tr>` : ""}
        ${linhasSaidas}
        ${p.total_saidas ? `<tr class="total"><td>Total de Saídas</td><td class="num">${brl(p.total_saidas)}</td></tr>` : ""}
        <tr class="total"><td>TOTAL CAIXA</td><td class="num">${brl(p.total_caixa)}</td></tr>
      </tbody>
    </table>

    ${p.pedidos_sem_forma_pagamento.length > 0 ? `
    <div class="alerta">
      <div class="alerta-titulo">⚠ Faturados sem forma de pagamento lançada (não entram no Total Caixa acima)</div>
      <table>
        <tbody>
          ${linhasSemForma}
          <tr class="total"><td>Total</td><td class="num">${brl(p.total_sem_forma_pagamento)}</td></tr>
        </tbody>
      </table>
    </div>` : ""}

    <h2>Resumo por Forma de Pagamento</h2>
    <table>
      <thead><tr><th>Tipo</th><th class="num">Valor</th><th class="num">%</th></tr></thead>
      <tbody>
        ${linhasResumo}
        <tr class="total"><td>T O T A L</td><td class="num">${brl(p.total_recebimentos)}</td><td></td></tr>
      </tbody>
    </table>

    <div class="footnote">
      (*) As formas de pagamento com este símbolo foram configuradas pra não somarem no total do caixa.<br/>
      Gerado em ${esc(geradoEm)}
    </div>
  </body></html>`;
}

export async function exportFechamentoCaixaPdf(payload: FechamentoCaixaPayload): Promise<void> {
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
      dialogTitle: "Fechamento de Caixa",
      UTI: "com.adobe.pdf",
    });
  } else {
    await Print.printAsync({ uri });
  }
}
