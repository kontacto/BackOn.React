import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";
import { printFullHtml } from "./printHtml";

// Impressão do preenchimento de um Formulário Dinâmico (Motor de Layout) —
// [GLOBAL] pedido explícito do usuário, 2026-08-12: sempre A4, com
// cabeçalho da empresa + título do relatório.
//
// **Correção 2026-08-12, achado ao vivo**: no web, `Print.printAsync({html})`
// (expo-print) NÃO renderiza o HTML passado — ele dispara o print nativo do
// NAVEGADOR sobre a ABA ATUAL (a tela por trás do modal), então o PDF saía
// sem o cabeçalho de empresa (o documento gerado por `buildHtml()` nunca
// chegou a ser desenhado) e com a barra de rolagem interna do próprio modal
// visível/cortada no preview de impressão, em vez do relatório A4 completo.
// Mesma causa raiz já documentada no projeto pra `printHtml.ts` (ver
// comentário no topo daquele arquivo) — por isso o web agora usa
// `printFullHtml()` (iframe oculto com o documento completo já pronto,
// mesma técnica, só sem reembrulhar num segundo `<html>`) em vez de
// `expo-print` nesta plataforma. Nativo (iOS/Android) continua em
// `Print.printToFileAsync`, onde expo-print de fato roda nativamente.

export type CampoImpressao = {
  campo1: string;
  tipo_descricao: string;
  unidade_medida: string;
  conteudo: string;
  campo_agrupado: boolean;
};

export type LayoutPreenchimentoPayload = {
  titulo: string;
  empresa?: EmpresaHeader | null;
  // Dados de identidade resolvidos a partir da entidade vinculada (Cliente,
  // Técnico, Data do atendimento, etc.) — pedido explícito do usuário:
  // "trazer da entidade se existir", não digitado no formulário.
  dadosExtras?: { label: string; valor: string }[];
  campos: CampoImpressao[];
};

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function ehSimNao(tipoDescricao: string): boolean {
  const t = (tipoDescricao || "").trim().toLowerCase();
  return t.includes("sim") && (t.includes("não") || t.includes("nao"));
}

function celulaHtml(c: CampoImpressao): string {
  const valor = ehSimNao(c.tipo_descricao) ? (c.conteudo || "—") : (c.conteudo || "—");
  return `
    <div class="campo">
      <div class="campo-label">${esc(c.campo1)}${c.unidade_medida ? ` (${esc(c.unidade_medida)})` : ""}</div>
      <div class="campo-valor">${esc(valor)}</div>
    </div>`;
}

// Agrupa campos consecutivos (campo_agrupado=true no primeiro) em linhas de
// até 2 colunas — mesma lógica de agrupamento usada na tela de
// preenchimento, preservando a posição/disposição do documento original.
function montarLinhasHtml(campos: CampoImpressao[]): string {
  const linhas: string[] = [];
  let i = 0;
  while (i < campos.length) {
    const atual = campos[i];
    const proximo = campos[i + 1];
    if (atual.campo_agrupado && proximo) {
      linhas.push(`<div class="linha linha2">${celulaHtml(atual)}${celulaHtml(proximo)}</div>`);
      i += 2;
    } else {
      linhas.push(`<div class="linha">${celulaHtml(atual)}</div>`);
      i += 1;
    }
  }
  return linhas.join("");
}

function buildHtml(p: LayoutPreenchimentoPayload): string {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const extras = (p.dadosExtras || []).filter((d) => (d.valor || "").trim());
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    @page { size: A4; margin: 16mm; }
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; font-size: 12px; }
    ${REPORT_HEADER_CSS}
    .meta { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    .extras { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 18px; padding: 10px 12px; background: #f7f8fc; border-radius: 6px; }
    .extra { min-width: 160px; }
    .extra .lbl { font-size: 10px; text-transform: uppercase; color: #888; letter-spacing: .4px; }
    .extra .val { font-size: 12px; font-weight: 600; margin-top: 1px; }
    .linha { display: flex; gap: 12px; margin-bottom: 8px; }
    .linha2 .campo { flex: 1; min-width: 0; }
    .campo { border: 1px solid #e2e2ea; border-radius: 6px; padding: 6px 10px; flex: 1; }
    .campo-label { font-size: 10px; color: #666; margin-bottom: 2px; }
    .campo-valor { font-size: 12px; font-weight: 600; word-break: break-word; }
  </style></head><body>
    ${buildReportHeaderHtml(p.empresa || null, p.titulo)}
    <div class="meta">Gerado em ${esc(geradoEm)}</div>
    ${extras.length > 0 ? `<div class="extras">${extras.map((d) => `<div class="extra"><div class="lbl">${esc(d.label)}</div><div class="val">${esc(d.valor)}</div></div>`).join("")}</div>` : ""}
    ${montarLinhasHtml(p.campos)}
  </body></html>`;
}

/** Gera um PDF do preenchimento (A4) e abre a folha de compartilhamento
 * (nativo) ou o diálogo de impressão/salvar-PDF (web). Lança erro em caso
 * de falha. */
export async function exportLayoutPreenchimentoPdf(payload: LayoutPreenchimentoPayload): Promise<void> {
  const html = buildHtml(payload);
  if (Platform.OS === "web") {
    printFullHtml(html);
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
