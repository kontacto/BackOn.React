// Descontos (Concedidos) — migração de FrmRelDes.frm (Painel de
// Relatórios > Caixa). Documento (Pedido/OS) → itens com desconto, tipo
// Item/Geral e quem concedeu (só disponível pra Pedido — ver
// PENDENCIAS.md > "Painel de Relatórios (VB6)" > "Descontos").
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type DescontoItem = {
  descricao: string;
  qtd: number;
  valor_bruto: number;
  percentual: number;
  valor_desconto: number;
  valor_liquido: number;
  tipo_desconto_label: string | null;
  concedido_por: string | null;
};

export type DescontoDocumento = {
  tipo: "PEDIDO" | "OS";
  numero: number;
  data: string | null;
  cliente_nome: string;
  vendedor_nome: string;
  itens: DescontoItem[];
  total_bruto: number;
  total_desconto: number;
  total_liquido: number;
};

export type DescontosConcedidosPayload = {
  titulo: string;
  periodo: string;
  documentos: DescontoDocumento[];
  totais: { bruto: number; desconto: number; liquido: number; desconto_pct: number };
  empresa?: EmpresaHeader | null;
};

function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function pct(v: number): string {
  return `${(v || 0).toFixed(2).replace(".", ",")}%`;
}
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : (iso || "—");
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: DescontosConcedidosPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const docs = p.documentos
    .map((d) => {
      const linhas = d.itens
        .map(
          (i) => `
            <tr>
              <td>${esc(i.descricao)}</td>
              <td class="num">${i.qtd}</td>
              <td class="num">${brl(i.valor_bruto)}</td>
              <td class="num">${pct(i.percentual)}</td>
              <td class="num red">${brl(i.valor_desconto)}</td>
              <td class="num">${brl(i.valor_liquido)}</td>
              <td>${esc(i.tipo_desconto_label || "—")}</td>
              <td>${esc(i.concedido_por || "—")}</td>
            </tr>`
        )
        .join("");
      return `
        <div class="grupo">
          <div class="grupo-head">
            <span class="grupo-nome">${d.tipo === "PEDIDO" ? "Pedido" : "O.S."} #${d.numero} — ${esc(d.cliente_nome)}</span>
            <span class="grupo-sub">${brDate(d.data)} · Vendedor: ${esc(d.vendedor_nome)} · Bruto ${brl(d.total_bruto)} · Desconto ${brl(d.total_desconto)} · Líquido ${brl(d.total_liquido)}</span>
          </div>
          <table>
            <thead>
              <tr><th>Item</th><th class="num">Qtd</th><th class="num">Bruto</th><th class="num">%</th><th class="num">Desconto</th><th class="num">Líquido</th><th>Tipo</th><th>Concedido por</th></tr>
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
    <div class="meta">${esc(p.periodo)} · Gerado em ${esc(geradoEm)}</div>
    <div class="totais">
      <div class="tot"><div class="lbl">Bruto</div><div class="val">${brl(p.totais.bruto)}</div></div>
      <div class="tot"><div class="lbl">Desconto</div><div class="val red">${brl(p.totais.desconto)} (${pct(p.totais.desconto_pct)})</div></div>
      <div class="tot"><div class="lbl">Líquido</div><div class="val">${brl(p.totais.liquido)}</div></div>
    </div>
    ${docs || "<p>Nenhum desconto concedido no período.</p>"}
  </body></html>`;
}

export async function exportDescontosConcedidosPdf(payload: DescontosConcedidosPayload): Promise<void> {
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
