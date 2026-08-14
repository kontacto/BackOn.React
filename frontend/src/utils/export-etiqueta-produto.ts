// Impressão de Etiquetas de Produto — migração de Geral\FrmEtqProd.frm
// (Painel de Relatórios > Estoque). Ao contrário dos outros exportadores
// deste projeto (tabela de relatório), aqui o HTML monta um LAYOUT FÍSICO
// de etiquetas — grid CSS em cm, paginado por `linhas_por_folha` do modelo
// escolhido (tabela `modelo_etiqueta`, ver backend). Cada linha marcada
// ("Imp") vira N etiquetas individuais (N = Quant), mesma expansão
// "1 etiqueta por unidade" que TODO sub de impressão do legado replicava
// (ver docstring de `etiqueta_produto_service.py`).
//
// "Nº Etiquetas a Saltar": no legado é matemática imperativa de posição —
// aqui vira simplesmente N `<div>` vazios inseridos ANTES do conteúdo real
// no grid CSS, que empurram o resto pra frente automaticamente (CSS Grid
// já faz o "avança célula a célula, quebra linha, quebra página" sozinho).
//
// Modelos "gôndola" (fiscal/não fiscal) imprimem um código de barras real
// (ver src/utils/barcode.ts) — os modelos "Identificação" (grade_laser)
// não têm código de barras, só texto (fiel ao legado, confirmado no
// rastreio: nenhum dos dois desenha barcode).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildBarcodeSvg } from "./barcode";

export type ModeloEtiqueta = {
  codigo: number;
  nome: string;
  formato: "grade_laser" | "gondola" | "termica";
  especificacao: string | null;
  colunas: number;
  linhas_por_folha: number | null;
  largura_cm: number | null;
  altura_cm: number | null;
  margem_lateral_cm: number | null;
  margem_superior_cm: number | null;
  tem_barcode: boolean | number;
};

export type EtiquetaItem = {
  codigo_int: string;
  codigo_fab: string;
  descricao: string;
  codigo_bar: string;
  quant: number;
  p_venda: number;
};

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
function brl(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function expandirInstancias(itens: EtiquetaItem[]): EtiquetaItem[] {
  const out: EtiquetaItem[] = [];
  for (const it of itens) {
    const n = Math.max(1, Math.round(it.quant) || 1);
    for (let i = 0; i < n; i++) out.push(it);
  }
  return out;
}

function buildCelulaLaser(it: EtiquetaItem): string {
  return `
    <div class="etq etq-laser">
      <div class="etq-cod">${esc(it.codigo_fab || it.codigo_int)}</div>
      <div class="etq-desc">${esc(it.descricao)}</div>
      <div class="etq-preco">${esc(brl(it.p_venda))}</div>
    </div>`;
}

function buildCelulaGondola(it: EtiquetaItem): string {
  const svg = buildBarcodeSvg(it.codigo_bar, 45);
  return `
    <div class="etq etq-gondola">
      <div class="etq-g-desc">${esc(it.descricao)}</div>
      <div class="etq-g-cod">${esc(it.codigo_int)}</div>
      <div class="etq-g-preco">${esc(brl(it.p_venda))}</div>
      <div class="etq-g-barcode">${svg}</div>
    </div>`;
}

export async function imprimirEtiquetas(
  modelo: ModeloEtiqueta, itens: EtiquetaItem[], saltar: number,
): Promise<void> {
  if (modelo.formato === "termica") {
    throw new Error(
      "Impressão térmica (Zebra) ainda não disponível nesta migração — veja o ícone de Ajuda (i) no cabeçalho pra entender o que falta."
    );
  }
  const instancias = expandirInstancias(itens);
  const colunas = modelo.colunas || 1;
  const linhasPorFolha = modelo.linhas_por_folha || 9999;
  const capacidadeFolha = colunas * linhasPorFolha;
  const larguraCm = modelo.largura_cm || 5;
  const alturaCm = modelo.altura_cm || 2;
  const margemLateral = modelo.margem_lateral_cm || 0;
  const margemSuperior = modelo.margem_superior_cm || 0;
  const isLaser = modelo.formato === "grade_laser";

  const vazio = `<div class="etq etq-vazia"></div>`;
  const skipCount = Math.max(0, Math.round(saltar) || 0);
  const celulas = [
    ...Array.from({ length: skipCount }, () => vazio),
    ...instancias.map((it) => (isLaser ? buildCelulaLaser(it) : buildCelulaGondola(it))),
  ];

  const folhas: string[] = [];
  for (let i = 0; i < celulas.length; i += capacidadeFolha) {
    folhas.push(celulas.slice(i, i + capacidadeFolha).join(""));
  }
  if (folhas.length === 0) folhas.push("");

  const folhasHtml = folhas
    .map(
      (conteudo, idx) => `
      <div class="folha" style="grid-template-columns: repeat(${colunas}, ${larguraCm}cm); padding-top: ${margemSuperior}cm; padding-left: ${margemLateral}cm;">
        ${conteudo}
      </div>
      ${idx < folhas.length - 1 ? '<div style="page-break-after: always;"></div>' : ""}`
    )
    .join("");

  const html = `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    @page { size: A4; margin: 0.5cm; }
    * { box-sizing: border-box; }
    body { font-family: Arial, Helvetica, sans-serif; margin: 0; }
    .folha { display: grid; grid-auto-rows: ${alturaCm}cm; }
    .etq { overflow: hidden; padding: 2px 4px; display: flex; flex-direction: column; justify-content: center; }
    .etq-vazia { visibility: hidden; }
    .etq-laser .etq-cod { font-size: 7px; font-weight: 700; }
    .etq-laser .etq-desc { font-size: 7px; line-height: 1.1; max-height: 2.2em; overflow: hidden; }
    .etq-laser .etq-preco { font-size: 9px; font-weight: 700; text-align: right; }
    .etq-gondola { border: 1px dashed #ccc; align-items: center; text-align: center; gap: 2px; }
    .etq-g-desc { font-size: 12px; font-weight: 700; max-height: 2.4em; overflow: hidden; }
    .etq-g-cod { font-size: 8px; color: #555; }
    .etq-g-preco { font-size: 16px; font-weight: 800; }
    .etq-g-barcode svg { width: 90%; height: auto; }
  </style></head><body>${folhasHtml}</body></html>`;

  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: "Etiquetas de Produto", UTI: "com.adobe.pdf" });
  } else {
    await Print.printAsync({ uri });
  }
}
