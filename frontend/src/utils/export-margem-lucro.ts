import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";

export type MLItem = {
  codigo: string; descricao: string; qtd: number; custo_unit: number;
  preco_bruto: number; desconto: number; acrescimo: number; preco_liquido: number;
  total_venda: number; total_custo: number; lucro: number; margem_pct: number;
};
export type MLDav = {
  tipo: string; codigo: number; data: string; cliente: string;
  total_venda: number; total_custo: number; lucro: number; margem_pct: number;
  itens: MLItem[];
};
export type MLEmpresa = {
  empresa: string; servidor: string; banco: string; success: boolean; message?: string;
  total_venda?: number; total_custo?: number; lucro?: number; margem_pct?: number;
  qtd_davs?: number; davs?: MLDav[]; truncated?: boolean; davs_exibidos?: number;
};
export type MLConsolidado = {
  total_venda: number; total_custo: number; lucro: number; margem_pct: number;
  qtd_davs: number; qtd_empresas: number;
};
export type MLPayload = {
  titulo: string; periodo?: string;
  consolidado: MLConsolidado; empresas: MLEmpresa[];
};

function brl(v?: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function brDate(iso: string): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : iso || "";
}
function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function buildHtml(p: MLPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const c = p.consolidado;

  const empresasHtml = p.empresas
    .map((e) => {
      if (!e.success) {
        return `<div class="empresa"><div class="empresa-head"><span class="empresa-nome">${esc(e.empresa)}</span>
          <span class="erro">Falha: ${esc(e.message || "erro")}</span></div></div>`;
      }
      const davsHtml = (e.davs || [])
        .map((d) => {
          const itens = d.itens
            .map(
              (it) => `<tr>
                <td>${esc(it.codigo)}</td><td>${esc(it.descricao)}</td>
                <td class="num">${it.qtd}</td>
                <td class="num">${brl(it.preco_liquido)}</td>
                <td class="num">${brl(it.total_venda)}</td>
                <td class="num">${brl(it.total_custo)}</td>
                <td class="num">${brl(it.lucro)}</td>
                <td class="num">${it.margem_pct}%</td></tr>`
            )
            .join("");
          return `<div class="dav">
            <div class="dav-head">${d.tipo} #${d.codigo} · ${brDate(d.data)} · ${esc(d.cliente || "—")}
              <span class="dav-sub">Venda ${brl(d.total_venda)} · Custo ${brl(d.total_custo)} · Lucro ${brl(d.lucro)} (${d.margem_pct}%)</span>
            </div>
            <table><thead><tr>
              <th>Código</th><th>Descrição</th><th class="num">Qtd</th><th class="num">Líq.</th>
              <th class="num">Venda</th><th class="num">Custo</th><th class="num">Lucro</th><th class="num">%</th>
            </tr></thead><tbody>${itens}</tbody></table>
          </div>`;
        })
        .join("");
      return `<div class="empresa">
        <div class="empresa-head"><span class="empresa-nome">${esc(e.empresa)}</span>
          <span class="empresa-sub">${e.qtd_davs || 0} DAV(s) · Venda ${brl(e.total_venda)} · Custo ${brl(e.total_custo)} · Lucro ${brl(e.lucro)} (${e.margem_pct}%)</span>
        </div>${davsHtml || "<p class='vazio'>Nenhum registro.</p>"}</div>`;
    })
    .join("");

  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 12px; }
    h1 { font-size: 18px; margin: 0 0 4px; color: #1f3a93; }
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; }
    .totais { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 20px; }
    .tot { border: 1px solid #ddd; border-radius: 6px; padding: 8px 12px; min-width: 120px; }
    .tot .lbl { font-size: 10px; text-transform: uppercase; color: #888; letter-spacing: .4px; }
    .tot .val { font-size: 14px; font-weight: 700; margin-top: 2px; }
    .empresa { margin-bottom: 22px; }
    .empresa-head { background: #1f3a93; color: #fff; border-radius: 6px; padding: 8px 10px; margin-bottom: 8px; }
    .empresa-nome { font-weight: 700; font-size: 13px; }
    .empresa-sub { display: block; font-size: 10px; opacity: .85; margin-top: 2px; }
    .dav { margin: 0 0 12px 8px; }
    .dav-head { background: #eef1fb; border-radius: 5px; padding: 6px 8px; font-weight: 600; font-size: 12px; color: #1f3a93; }
    .dav-sub { display: block; font-weight: 400; font-size: 10px; color: #666; margin-top: 2px; }
    table { width: 100%; border-collapse: collapse; margin-top: 4px; }
    th, td { text-align: left; padding: 4px 6px; border-bottom: 1px solid #eee; font-size: 10px; }
    th { background: #f7f8fc; color: #555; }
    .num { text-align: right; }
    .erro { color: #c0392b; font-size: 11px; }
    .vazio { color: #999; font-size: 11px; margin: 4px 0 0 8px; }
  </style></head><body>
    <h1>${esc(p.titulo)}</h1>
    <div class="meta">${p.periodo ? esc(p.periodo) + " · " : ""}${c.qtd_empresas} empresa(s) · Gerado em ${esc(geradoEm)}</div>
    <div class="totais">
      <div class="tot"><div class="lbl">DAVs</div><div class="val">${c.qtd_davs}</div></div>
      <div class="tot"><div class="lbl">Total Vendas</div><div class="val">${brl(c.total_venda)}</div></div>
      <div class="tot"><div class="lbl">Total Custos</div><div class="val">${brl(c.total_custo)}</div></div>
      <div class="tot"><div class="lbl">Lucro</div><div class="val">${brl(c.lucro)}</div></div>
      <div class="tot"><div class="lbl">Margem %</div><div class="val">${c.margem_pct}%</div></div>
    </div>
    ${empresasHtml || "<p>Nenhum dado no período.</p>"}
  </body></html>`;
}

/** Gera PDF do relatório de Margem de Lucro e abre o compartilhamento (nativo) ou
 *  o diálogo de impressão/salvar-PDF (web). */
export async function exportMargemLucroPdf(payload: MLPayload): Promise<void> {
  const html = buildHtml(payload);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  if (await Sharing.isAvailableAsync()) {
    await Sharing.shareAsync(uri, {
      mimeType: "application/pdf",
      dialogTitle: payload.titulo,
      UTI: "com.adobe.pdf",
    });
  } else {
    await Print.printAsync({ uri });
  }
}
