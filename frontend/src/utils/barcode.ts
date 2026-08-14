// Gera o SVG de um código de barras como string, pra embutir direto no HTML
// de impressão de etiquetas (não dá pra usar um componente React aqui — o
// HTML de impressão é montado como string pura, ver export-etiqueta-produto.ts).
// Web-only (usa document/XMLSerializer) — todo chamador já roda dentro do
// fluxo de impressão, que só existe no web (ver etiqueta-produto.tsx).
//
// Tenta EAN-13/EAN-8 quando o código tem 13/8 dígitos (formato real de
// código de barras de produto de varejo), caindo pra CODE128 (aceita
// qualquer alfanumérico, sem dígito verificador) quando o código não é um
// EAN válido — JsBarcode lança exceção em checksum inválido, por isso o
// try/catch em cascata.
import JsBarcode from "jsbarcode";

export function buildBarcodeSvg(codigo: string, heightPx = 50): string {
  if (typeof document === "undefined") return "";
  const valor = (codigo || "").trim();
  if (!valor) return "";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const digitos = valor.replace(/\D/g, "");
  const tentativas: string[] = [];
  if (digitos.length === 13) tentativas.push("EAN13");
  if (digitos.length === 8) tentativas.push("EAN8");
  tentativas.push("CODE128");

  for (const formato of tentativas) {
    try {
      JsBarcode(svg, valor, {
        format: formato, width: 2, height: heightPx, displayValue: true, fontSize: 12, margin: 0,
      });
      return new XMLSerializer().serializeToString(svg);
    } catch {
      // formato incompatível com o valor — tenta o próximo
    }
  }
  return "";
}
