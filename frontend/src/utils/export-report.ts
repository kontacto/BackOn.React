import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

type PedidoRow = {
  pedido: number;
  data: string;
  cliente: string;
  venda: number;
  desconto: number;
  custo: number;
  margem: number;
  margem_pct: number;
};
type VendedorGroup = {
  vendedor: string;
  vendedor_nome: string;
  pedidos: PedidoRow[];
  sub_venda: number;
  sub_desconto: number;
  sub_custo: number;
  sub_margem: number;
  sub_margem_pct: number;
};
type Totais = {
  venda: number;
  desconto: number;
  custo: number;
  margem: number;
  margem_pct: number;
  qtd_pedidos: number;
};

export type ReportPayload = {
  titulo: string;
  periodo?: string;
  totais: Totais;
  vendedores: VendedorGroup[];
  // Dados da empresa (Controle) pro cabeçalho de impressão — [GLOBAL],
  // ver print-report-header.ts. Sem filtro da tela no PDF, só empresa +
  // nome do relatório.
  empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function brDate(iso: string): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : iso || "";
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: ReportPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const t = p.totais;

  const grupos = p.vendedores
    .map((g) => {
      const linhas = g.pedidos
        .map(
          (pe) => `
            <tr>
              <td>#${pe.pedido}</td>
              <td>${brDate(pe.data)}</td>
              <td>${esc(pe.cliente || "—")}</td>
              <td class="num">${brl(pe.venda)}</td>
              <td class="num red">${brl(pe.desconto)}</td>
              <td class="num">${brl(pe.custo)}</td>
              <td class="num">${brl(pe.margem)}</td>
              <td class="num">${pe.margem_pct}%</td>
            </tr>`
        )
        .join("");
      return `
        <div class="grupo">
          <div class="grupo-head">
            <span class="grupo-nome">${esc(g.vendedor_nome)}</span>
            <span class="grupo-sub">${g.pedidos.length} pedido(s) · Venda ${brl(g.sub_venda)} · Desc ${brl(
        g.sub_desconto
      )} · Margem ${brl(g.sub_margem)} (${g.sub_margem_pct}%)</span>
          </div>
          <table>
            <thead>
              <tr>
                <th>Pedido</th><th>Data</th><th>Cliente</th>
                <th class="num">Venda</th><th class="num">Desconto</th>
                <th class="num">Custo</th><th class="num">Margem</th><th class="num">%</th>
              </tr>
            </thead>
            <tbody>${linhas}</tbody>
          </table>
        </div>`;
    })
    .join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 12px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    .totais { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
    .tot { border: 1px solid #ddd; border-radius: 6px; padding: 8px 12px; min-width: 110px; }
    .tot .lbl { font-size: 10px; text-transform: uppercase; color: #888; letter-spacing: .4px; }
    .tot .val { font-size: 14px; font-weight: 700; margin-top: 2px; }
    .grupo { margin-bottom: 18px; }
    .grupo-head { background: #eef1fb; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; }
    .grupo-nome { font-weight: 700; font-size: 13px; color: #1f3a93; }
    .grupo-sub { display: block; font-size: 10px; color: #666; margin-top: 2px; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 5px 6px; border-bottom: 1px solid #eee; font-size: 11px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    .red { color: #c0392b; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">${p.periodo ? esc(p.periodo) + " · " : ""}Gerado em ${esc(geradoEm)}</div>
    <div class="totais">
      <div class="tot"><div class="lbl">Pedidos</div><div class="val">${t.qtd_pedidos}</div></div>
      <div class="tot"><div class="lbl">Vendas</div><div class="val">${brl(t.venda)}</div></div>
      <div class="tot"><div class="lbl">Descontos</div><div class="val red">${brl(t.desconto)}</div></div>
      <div class="tot"><div class="lbl">Custo</div><div class="val">${brl(t.custo)}</div></div>
      <div class="tot"><div class="lbl">Margem</div><div class="val">${brl(t.margem)} (${t.margem_pct}%)</div></div>
    </div>
    ${grupos || "<p>Nenhum pedido no período.</p>"}
  </body></html>`;
}

/** Gera um PDF do relatório e abre a folha de compartilhamento (nativo) ou o
 *  diálogo de impressão/salvar-PDF (web). Lança erro em caso de falha. */
export async function exportReportPdf(payload: ReportPayload): Promise<void> {
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
