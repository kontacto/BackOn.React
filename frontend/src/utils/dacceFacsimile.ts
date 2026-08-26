// Fac-símile de impressão da Carta de Correção Eletrônica (CC-e) — não
// existe leiaute obrigatório de "DACCe" (documento auxiliar) como existe
// pro DANFE — confirmado via pesquisa ao planejar esta feature
// (2026-08-22): a impressão da CC-e não é legalmente exigida, é só
// conveniência operacional. Por isso este documento é deliberadamente
// simples (1 página), sem tentar reproduzir um leiaute "oficial" que não
// existe — segue a mesma linguagem visual do DANFE (`danfeFacsimile.ts`)
// só pra manter consistência de estilo entre os documentos fiscais desta
// migração.
import { EmpresaHeader } from "./print-report-header";

function esc(s: string | number | null | undefined): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtChave(chave: string | null | undefined): string {
  if (!chave) return "";
  return (chave.match(/.{1,4}/g) || []).join(" ");
}

function fmtDataHora(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString("pt-BR");
}

const DACCE_CSS = `
  body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #111; margin: 0; }
  .dacce-title { text-align: center; font-weight: 700; font-size: 15px; margin-bottom: 2px; }
  .dacce-sub { text-align: center; font-size: 11px; color: #555; margin-bottom: 12px; }
  .dacce-box { border: 1px solid #333; padding: 8px 10px; margin-bottom: 10px; }
  .dacce-cell-label { font-size: 9px; color: #555; text-transform: uppercase; }
  .dacce-cell-value { font-size: 12px; margin-top: 1px; }
  .dacce-texto { white-space: pre-wrap; font-size: 12px; line-height: 1.5; }
  .dacce-aviso { font-size: 9px; color: #555; line-height: 1.4; margin-top: 4px; }
`;

export type DacceDetalhe = {
  n_seq_evento?: number;
  motivo?: string;
  protocolo?: string;
  data_registro?: string;
  chave_acesso?: string;
  x_cond_uso?: string;
};

export function buildDacceHtml(empresa: EmpresaHeader | null, detalhe: DacceDetalhe | null): string {
  if (!detalhe) {
    return `<!doctype html><html><head><meta charset="utf-8"><title>Carta de Correção</title><style>${DACCE_CSS}</style></head>` +
      `<body><p>Não foi possível ler os dados desta Carta de Correção.</p></body></html>`;
  }
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.bairro].filter(Boolean).join(", ")
    : "";
  return `
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>Carta de Correção Nº ${esc(detalhe.n_seq_evento)}</title>
      <style>
        @page { size: A4 portrait; margin: 15mm; }
        ${DACCE_CSS}
      </style>
    </head>
    <body>
      <div class="dacce-title">CARTA DE CORREÇÃO ELETRÔNICA</div>
      <div class="dacce-sub">Nº ${esc(String(detalhe.n_seq_evento).padStart(2, "0"))} — documento sem valor fiscal, só de apoio operacional</div>

      <div class="dacce-box">
        <div class="dacce-cell-label">EMITENTE</div>
        <div class="dacce-cell-value" style="font-weight:700">${esc((empresa?.fantasia || empresa?.rz_social || "").toUpperCase())}</div>
        <div class="dacce-cell-label" style="margin-top:4px">${esc(endereco)}${empresa?.cidade ? ` — ${esc(empresa.cidade)}/${esc(empresa.uf)}` : ""}</div>
        <div class="dacce-cell-label">CNPJ: ${esc(empresa?.cgc)}${empresa?.inscr_est ? ` · IE: ${esc(empresa.inscr_est)}` : ""}</div>
      </div>

      <div class="dacce-box">
        <div class="dacce-cell-label">CHAVE DE ACESSO DA NF-e CORRIGIDA</div>
        <div class="dacce-cell-value" style="font-family:monospace">${esc(fmtChave(detalhe.chave_acesso))}</div>
        <div class="dacce-cell-label" style="margin-top:6px">Protocolo de registro: ${esc(detalhe.protocolo)} — ${fmtDataHora(detalhe.data_registro)}</div>
      </div>

      <div class="dacce-box">
        <div class="dacce-cell-label">TEXTO DA CORREÇÃO</div>
        <div class="dacce-texto">${esc(detalhe.motivo)}</div>
      </div>

      <div class="dacce-aviso">${esc(detalhe.x_cond_uso)}</div>
    </body>
    </html>
  `;
}
