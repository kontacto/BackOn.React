// Fac-símile visual de documento fiscal (DANFCe/DANFSe) pra reimpressão a
// partir do Gestor de Comandas / Alterar Comandas — pedido explícito do
// usuário 2026-07-21 ("tem que trazer o documento fiscal", com exemplo real
// de DANFSe v2.0 colado). Substitui a reimpressão anterior (lista crua de
// campos texto) — ver `gestor-comandas.tsx`/`alterar-comanda.tsx`.
//
// DANFCe: monta a partir do XML da NFC-e já assinado e gravado em
// `comanda_nfce.xml` na emissão (`nfe_emissao_service.parse_nfce_xml_para_
// exibicao`, backend) — é o XML que o próprio sistema montou, dados reais.
// DANFSe: como a emissão de NFS-e nunca foi validada contra o ADN real
// (`nfse_emissao_service.py`), o emitente/tomador/serviço são resolvidos de
// novo no backend (mesmas fontes da emissão), não lidos de um XML de
// resposta confiável — layout segue o exemplo oficial "DANFSe v2.0" colado
// pelo usuário, mas os campos de TRIBUTAÇÃO IBS/CBS ficam em branco: o
// cálculo real (`CalculaIBSCBS`, `Geral\mdl_proc.bas`) é uma rotina extensa
// da Reforma Tributária ainda não portada — ver PENDENCIAS.md.
import { EmpresaHeader } from "./print-report-header";

function esc(s: string | number | null | undefined): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function fmtBRL(v: number | null | undefined): string {
  return (v ?? 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

const DOC_CSS = `
  .doc { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; }
  .doc table { border-collapse: collapse; width: 100%; }
  .doc .box { border: 1px solid #333; padding: 6px 8px; margin-bottom: 6px; }
  .doc .grid { display: flex; flex-wrap: wrap; gap: 0; }
  .doc .cell { flex: 1; min-width: 140px; padding: 2px 8px 2px 0; }
  .doc .cell-label { font-size: 9px; color: #555; }
  .doc .cell-value { font-size: 11px; }
  .doc .section-title { background: #eee; font-weight: 700; padding: 3px 6px; border: 1px solid #333; border-bottom: none; }
  .doc .header-title { text-align: center; font-weight: 700; font-size: 13px; margin-bottom: 2px; }
  .doc .header-sub { text-align: center; font-size: 10px; color: #555; margin-bottom: 8px; }
  .doc .itens td, .doc .itens th { border: 1px solid #999; padding: 3px 6px; font-size: 10px; }
  .doc .itens th { background: #f0f0f0; text-align: left; }
  .doc .right { text-align: right; }
  .doc .total-box { border: 1px solid #333; padding: 6px 8px; margin-top: 6px; font-weight: 700; }
`;

export type DanfceDetalhe = {
  chave_acesso?: string;
  tp_amb?: string;
  serie?: string;
  numero?: string;
  dh_emi?: string;
  emit_cnpj?: string;
  emit_nome?: string;
  dest_doc?: string;
  itens?: { codigo: string; descricao: string; qtd: number; valor_unitario: number; valor_total: number }[];
  valor_total?: number;
  forma_pagamento?: string;
  valor_pago?: number;
  qr_code_url?: string;
};

export function buildDanfceHtml(empresa: EmpresaHeader | null, comanda: number, detalhe: DanfceDetalhe | null): string {
  if (!detalhe) {
    return `<div class="doc"><style>${DOC_CSS}</style><p>Não foi possível ler os dados da NFC-e desta comanda.</p></div>`;
  }
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.bairro].filter(Boolean).join(", ")
    : "";
  const itensHtml = (detalhe.itens || [])
    .map(
      (it) => `<tr>
        <td>${esc(it.codigo)}</td><td>${esc(it.descricao)}</td>
        <td class="right">${it.qtd}</td><td class="right">${fmtBRL(it.valor_unitario)}</td>
        <td class="right">${fmtBRL(it.valor_total)}</td>
      </tr>`
    )
    .join("");
  return `
    <div class="doc">
      <style>${DOC_CSS}</style>
      <div class="header-title">${esc((empresa?.fantasia || empresa?.rz_social || detalhe.emit_nome || "").toUpperCase())}</div>
      <div class="header-sub">
        ${esc(detalhe.emit_cnpj)}${endereco ? ` · ${esc(endereco)}` : ""}${empresa?.cidade ? ` · ${esc(empresa.cidade)}/${esc(empresa.uf)}` : ""}
      </div>
      <div class="header-title" style="font-size:12px">DANFCE — Documento Auxiliar da Nota Fiscal de Consumidor Eletrônica</div>
      <div class="header-sub">Não permite aproveitamento de crédito de ICMS — Comanda #${comanda}</div>

      <table class="itens">
        <thead><tr><th>Código</th><th>Descrição</th><th>Qtd.</th><th>Vl. Unit.</th><th>Vl. Total</th></tr></thead>
        <tbody>${itensHtml || `<tr><td colspan="5">Nenhum item.</td></tr>`}</tbody>
      </table>

      <div class="total-box">
        <div class="grid">
          <div class="cell"><div class="cell-label">FORMA DE PAGAMENTO</div><div class="cell-value">${esc(detalhe.forma_pagamento)}</div></div>
          <div class="cell right"><div class="cell-label">VALOR TOTAL</div><div class="cell-value">R$ ${fmtBRL(detalhe.valor_total)}</div></div>
        </div>
      </div>

      <div class="box" style="margin-top:8px">
        <div class="cell-label">NFC-e nº ${esc(detalhe.numero)} série ${esc(detalhe.serie)} — emitida em ${fmtDataHora(detalhe.dh_emi)}</div>
        <div class="cell-label" style="margin-top:4px">Chave de Acesso</div>
        <div class="cell-value" style="font-family:monospace">${esc(fmtChave(detalhe.chave_acesso))}</div>
        ${detalhe.qr_code_url ? `<div class="cell-label" style="margin-top:4px">Consulte pela Chave de Acesso em</div><div class="cell-value" style="word-break:break-all">${esc(detalhe.qr_code_url)}</div>` : ""}
      </div>
    </div>
  `;
}

export type DanfseDetalhe = {
  emit_cnpj?: string; emit_nome?: string; emit_endereco?: string; emit_cidade?: string; emit_uf?: string;
  emit_cep?: string; emit_telefone?: string; emit_inscr_municipal?: string;
  toma_doc?: string; toma_nome?: string;
  servicos?: { descricao: string; cod_lista_servico: string }[];
};

/** Bloco "TRIBUTAÇÃO IBS/CBS" — campos fixos "-", **confirmado direto na
 * fonte real** (`Geral\Mdl_Imp_XML.bas::DanfeNFSE`, achado 2026-07-21): a
 * rotina de impressão oficial LÊ as variáveis do XML (CST, cClassTrib,
 * pIBSUF, pIBSMun, vIBSUF, vIBSMun, vIBSTot, pCBS, pAliqEfetCBS, vCBS
 * etc.) mas NUNCA as imprime — todo `Printer.Print` dessa seção manda o
 * literal "-", independente do valor lido. Ou seja: mesmo o sistema
 * legado oficial, na fase de teste 2026 da Reforma Tributária, mostra "-"
 * aqui — não é omissão minha, é o comportamento real confirmado na
 * fonte. Reverte a versão "simulada" anterior (pedido do usuário antes
 * dessa fonte ter sido encontrada) — ver PENDENCIAS.md. */
function buildIbsCbsHtml(): string {
  const t = '<div class="cell-value">-</div>';
  return `
    <div class="section-title">TRIBUTAÇÃO IBS/CBS (Reforma Tributária)</div>
    <div class="box">
      <div class="grid">
        <div class="cell"><div class="cell-label">CST/cClassTrib</div>${t}</div>
        <div class="cell"><div class="cell-label">Indicador de Operação / Local de incidência</div>${t}</div>
        <div class="cell"><div class="cell-label">Base Cálculo Após exclusões/reduções</div>${t}</div>
      </div>
      <div class="grid">
        <div class="cell"><div class="cell-label">Alíquota Municipal IBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Valor Municipal IBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Alíquota Estadual IBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Valor Estadual IBS</div>${t}</div>
      </div>
      <div class="grid">
        <div class="cell"><div class="cell-label">Valor Total IBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Alíquota CBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Alíquota Efetiva CBS</div>${t}</div>
        <div class="cell"><div class="cell-label">Valor Total CBS</div>${t}</div>
      </div>
    </div>
  `;
}

export function buildDanfseHtml(
  chaveAcesso: string, numeroDps: string | number | null, serieDps: string | null, dataEmissao: string | null,
  valorTotal: number, detalhe: DanfseDetalhe | null,
): string {
  const d = detalhe || {};
  const servicosHtml = (d.servicos || [])
    .map((s) => `${esc(s.descricao)}${s.cod_lista_servico ? ` (${esc(s.cod_lista_servico)})` : ""}`)
    .join("; ") || "—";
  return `
    <div class="doc">
      <style>${DOC_CSS}</style>
      <div class="header-title">DANFSe v2.0 — Documento Auxiliar da NFS-e</div>
      <div class="header-sub">${esc(d.emit_cidade)}${d.emit_uf ? ` / ${esc(d.emit_uf)}` : ""}</div>

      <div class="box">
        <div class="cell-label">Chave de Acesso da NFS-e</div>
        <div class="cell-value" style="font-family:monospace">${esc(fmtChave(chaveAcesso))}</div>
        <div class="grid" style="margin-top:6px">
          <div class="cell"><div class="cell-label">Número da DPS</div><div class="cell-value">${esc(numeroDps)}</div></div>
          <div class="cell"><div class="cell-label">Série da DPS</div><div class="cell-value">${esc(serieDps)}</div></div>
          <div class="cell"><div class="cell-label">Data e Hora de emissão</div><div class="cell-value">${fmtDataHora(dataEmissao)}</div></div>
        </div>
      </div>

      <div class="section-title">EMITENTE DO SERVIÇO</div>
      <div class="box">
        <div class="grid">
          <div class="cell"><div class="cell-label">CNPJ/CPF</div><div class="cell-value">${esc(d.emit_cnpj)}</div></div>
          <div class="cell"><div class="cell-label">Inscrição Municipal</div><div class="cell-value">${esc(d.emit_inscr_municipal)}</div></div>
          <div class="cell"><div class="cell-label">Telefone</div><div class="cell-value">${esc(d.emit_telefone)}</div></div>
        </div>
        <div class="grid">
          <div class="cell" style="flex:2"><div class="cell-label">Nome/Nome Empresarial</div><div class="cell-value">${esc(d.emit_nome)}</div></div>
          <div class="cell"><div class="cell-label">Município</div><div class="cell-value">${esc(d.emit_cidade)}/${esc(d.emit_uf)}</div></div>
        </div>
        <div class="grid">
          <div class="cell" style="flex:2"><div class="cell-label">Endereço</div><div class="cell-value">${esc(d.emit_endereco)}</div></div>
          <div class="cell"><div class="cell-label">CEP</div><div class="cell-value">${esc(d.emit_cep)}</div></div>
        </div>
      </div>

      <div class="section-title">TOMADOR DO SERVIÇO</div>
      <div class="box">
        <div class="grid">
          <div class="cell"><div class="cell-label">CNPJ/CPF</div><div class="cell-value">${esc(d.toma_doc) || "—"}</div></div>
          <div class="cell" style="flex:2"><div class="cell-label">Nome/Nome Empresarial</div><div class="cell-value">${esc(d.toma_nome) || "Consumidor não identificado"}</div></div>
        </div>
      </div>

      <div class="section-title">SERVIÇO PRESTADO</div>
      <div class="box">
        <div class="cell-label">Descrição do Serviço</div>
        <div class="cell-value">${servicosHtml}</div>
      </div>

      ${buildIbsCbsHtml()}

      <div class="total-box">
        <div class="grid">
          <div class="cell right" style="flex:1"><div class="cell-label">VALOR TOTAL DA NFS-e</div><div class="cell-value">R$ ${fmtBRL(valorTotal)}</div></div>
        </div>
      </div>
    </div>
  `;
}
