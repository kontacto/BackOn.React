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
import { buildBarcodeSvg } from "./barcode";

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
  qr_code_png_base64?: string;
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
      ${detalhe.tp_amb === "2" ? `<div class="box" style="background:#b91c1c;color:#fff;text-align:center;font-weight:700;padding:6px">AMBIENTE DE HOMOLOGAÇÃO — SEM VALOR FISCAL</div>` : ""}
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
        ${buildBarcodeSvg(detalhe.chave_acesso || "", 32)}
        ${detalhe.qr_code_url ? `
        <div class="grid" style="margin-top:6px;align-items:center">
          ${detalhe.qr_code_png_base64
            ? `<div class="cell" style="flex:0 0 90px"><img src="data:image/png;base64,${detalhe.qr_code_png_base64}" style="width:90px;height:90px" /></div>`
            : ""}
          <div class="cell">
            <div class="cell-label">Consulte pela Chave de Acesso em</div>
            <div class="cell-value" style="word-break:break-all">${esc(detalhe.qr_code_url)}</div>
          </div>
        </div>` : ""}
      </div>
    </div>
  `;
}

export type DamdfeDetalhe = {
  num_mdfe?: number | null;
  serie?: string | null;
  chave_acesso?: string | null;
  protocolo_sefaz?: string | null;
  dhemi?: string | null;
  situacao?: string | null;
  veiculo_placa?: string | null;
  motorista_nome?: string | null;
  ufini?: string | null;
  uffim?: string | null;
  percurso?: string | null;
  tp_amb?: string | null;
  url_qrcode?: string | null;
  notas?: { num_nf: number; serie_nf: string; valor_total: number }[];
};

const SITUACAO_MDFE_LABEL: Record<string, string> = {
  A: "Sem MDF-e", N: "Não Transmitido", T: "Transmitido", E: "Encerrado", C: "Cancelado",
};

/** DAMDFE — Documento Auxiliar do MDF-e. No legado (`FrmTraMDF.frm`) é
 * impresso via GDI (`Printer.Print`, coordenadas manuais) — mesmo
 * precedente já usado pra DANFE/DANFCe/DANFSe: fac-símile HTML, não
 * réplica pixel a pixel do desenho GDI. Montado a partir dos dados já
 * carregados na própria tela (`mdfe.tsx`), sem reanalisar o XML no
 * frontend — mesmo princípio de simplicidade já usado pelo DANFSe. */
export function buildDamdfeHtml(empresa: EmpresaHeader | null, detalhe: DamdfeDetalhe | null): string {
  if (!detalhe) {
    return `<div class="doc"><style>${DOC_CSS}</style><p>Não foi possível ler os dados deste MDF-e.</p></div>`;
  }
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.bairro].filter(Boolean).join(", ")
    : "";
  const notasHtml = (detalhe.notas || [])
    .map((n) => `<tr><td>${esc(n.num_nf)}</td><td>${esc(n.serie_nf)}</td><td class="right">R$ ${fmtBRL(n.valor_total)}</td></tr>`)
    .join("");
  const situacaoLabel = detalhe.situacao ? SITUACAO_MDFE_LABEL[detalhe.situacao] || detalhe.situacao : "";
  return `
    <div class="doc">
      <style>${DOC_CSS}</style>
      ${detalhe.tp_amb === "2" ? `<div class="box" style="background:#b91c1c;color:#fff;text-align:center;font-weight:700;padding:6px">AMBIENTE DE HOMOLOGAÇÃO — SEM VALOR FISCAL</div>` : ""}
      <div class="header-title">${esc((empresa?.fantasia || empresa?.rz_social || "").toUpperCase())}</div>
      <div class="header-sub">
        ${endereco ? esc(endereco) : ""}${empresa?.cidade ? ` · ${esc(empresa.cidade)}/${esc(empresa.uf)}` : ""}
      </div>
      <div class="header-title" style="font-size:12px">DAMDFE — Documento Auxiliar do Manifesto Eletrônico de Documentos Fiscais</div>
      <div class="header-sub">Situação: ${esc(situacaoLabel)}</div>

      <div class="box">
        <div class="grid">
          <div class="cell"><div class="cell-label">MDF-e Nº</div><div class="cell-value">${esc(detalhe.num_mdfe)}</div></div>
          <div class="cell"><div class="cell-label">SÉRIE</div><div class="cell-value">${esc(detalhe.serie)}</div></div>
          <div class="cell"><div class="cell-label">EMISSÃO</div><div class="cell-value">${fmtDataHora(detalhe.dhemi)}</div></div>
          <div class="cell"><div class="cell-label">PROTOCOLO SEFAZ</div><div class="cell-value">${esc(detalhe.protocolo_sefaz)}</div></div>
        </div>
        <div class="grid" style="margin-top:4px">
          <div class="cell"><div class="cell-label">VEÍCULO</div><div class="cell-value">${esc(detalhe.veiculo_placa)}</div></div>
          <div class="cell"><div class="cell-label">MOTORISTA</div><div class="cell-value">${esc(detalhe.motorista_nome)}</div></div>
          <div class="cell"><div class="cell-label">UF INÍCIO / FIM</div><div class="cell-value">${esc(detalhe.ufini)} → ${esc(detalhe.uffim)}${detalhe.percurso ? ` (percurso: ${esc(detalhe.percurso)})` : ""}</div></div>
        </div>
      </div>

      <div class="section-title">Documentos Fiscais Vinculados</div>
      <table class="itens">
        <thead><tr><th>Nº NF</th><th>Série</th><th>Valor</th></tr></thead>
        <tbody>${notasHtml || `<tr><td colspan="3">Nenhuma nota vinculada.</td></tr>`}</tbody>
      </table>

      <div class="box" style="margin-top:8px">
        <div class="cell-label">Chave de Acesso</div>
        <div class="cell-value" style="font-family:monospace">${esc(fmtChave(detalhe.chave_acesso))}</div>
        ${buildBarcodeSvg(detalhe.chave_acesso || "", 32)}
        ${detalhe.url_qrcode ? `
        <div class="cell" style="margin-top:6px">
          <div class="cell-label">Consulte pela Chave de Acesso em</div>
          <div class="cell-value" style="word-break:break-all">${esc(detalhe.url_qrcode)}</div>
        </div>` : ""}
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

// DANFE (NF-e modelo 55, Retrato/Paisagem) — 2026-08-20, ver PENDENCIAS.md
// > "DANFE NF-e (modelo 55)". Diferente de `buildDanfceHtml`/
// `buildDanfseHtml` acima (que devolvem um FRAGMENTO `<div class="doc">`,
// embrulhado pelo chamador via `printHtml`), esta função devolve um
// DOCUMENTO HTML COMPLETO (`<!doctype html>...`) — precisa de controle
// próprio de `@page` pra alternar Retrato/Paisagem (`controle_aux.
// modelo_danfe`), o que o wrapper padrão de `printHtml` não permite (só
// aceita largura de bobina térmica). O chamador deve usar `printFullHtml`
// (não `printHtml`) com o resultado desta função — mesmo padrão já usado
// por `equipamentos.tsx` (impressão de QR Code com página própria).
//
// Estrutura segue a disposição pública conhecida do DANFE (MOC Anexo I/
// II, Confaz/SEFAZ) — não foi validada campo-a-campo contra o manual
// oficial nesta rodada (fetch ao portal oficial bloqueou por redirect
// loop). Campos de cálculo de imposto detalhado que o XML montado por
// este backend ainda não carrega (bases/alíquotas de ICMS/IPI por item)
// mostram "-", mesmo precedente já usado no bloco IBS/CBS de
// `buildDanfseHtml` acima. Transportador/Volumes foi implementado
// 2026-08-22 (ver `parse_nfe_xml_para_exibicao`/`_montar_transp_completo_
// nfe_xml` no backend) — mostra "-" só quando a NF-e de fato não tem
// esse bloco (ex.: NF-e Agrupada, que ainda não captura essa informação
// na tela, ao contrário de NF-e Avulsa).
export type DanfeItem = {
  codigo: string; descricao: string; ncm?: string; cfop?: string; unidade?: string;
  qtd: number; valor_unitario: number; valor_total: number;
};

export type DanfeDetalhe = {
  chave_acesso?: string;
  protocolo_sefaz?: string;
  dh_recbto?: string;
  tp_amb?: string;
  serie?: string;
  numero?: string;
  dh_emi?: string;
  natureza_operacao?: string;
  tp_nf?: string; // "0" Entrada / "1" Saída
  tp_emis?: string;
  dh_cont?: string | null;
  x_just?: string | null;
  emit_cnpj?: string;
  emit_nome?: string;
  dest_doc?: string;
  dest_nome?: string;
  dest_ie?: string;
  dest_endereco?: string;
  dest_numero?: string;
  dest_bairro?: string;
  dest_cidade?: string;
  dest_uf?: string;
  dest_cep?: string;
  itens?: DanfeItem[];
  valor_total?: number;
  ibs_cbs_totais?: { base?: string; valor_ibs?: string; valor_cbs?: string } | null;
  situacao?: string;
  // Transportador/Veículo/Volumes — achado 2026-08-22 (varredura de
  // simplificações pendentes): antes o XML nunca carregava esse bloco,
  // então não havia o que mostrar aqui. `mod_frete` segue o código real
  // do XML (0=Emitente/CIF, 1=Destinatário/FOB, 2=Terceiros,
  // 3=Próprio Remetente, 4=Próprio Destinatário, 9=Sem transporte).
  mod_frete?: string;
  transportador?: { cgc_cpf?: string; nome?: string; ie?: string; uf?: string } | null;
  veiculo?: { placa?: string; uf?: string } | null;
  volumes?: { qtd?: string; especie?: string; marca?: string; numero?: string; peso_liquido?: string; peso_bruto?: string } | null;
};

const MOD_FRETE_LABEL: Record<string, string> = {
  "0": "0 - Emitente (CIF)", "1": "1 - Destinatário (FOB)", "2": "2 - Terceiros",
  "3": "3 - Próprio Remetente", "4": "4 - Próprio Destinatário", "9": "9 - Sem Transporte",
};

const DANFE_CSS = `
  * { box-sizing: border-box; }
  body { font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #111; margin: 0; padding: 10mm; }
  .danfe-box { border: 1px solid #333; padding: 6px 8px; margin-bottom: 6px; }
  .danfe-grid { display: flex; flex-wrap: wrap; gap: 0; }
  .danfe-cell { flex: 1; min-width: 140px; padding: 2px 8px 2px 0; }
  .danfe-cell-label { font-size: 9px; color: #555; }
  .danfe-cell-value { font-size: 11px; }
  .danfe-section-title { background: #eee; font-weight: 700; padding: 3px 6px; border: 1px solid #333; border-bottom: none; }
  .danfe-title { text-align: center; font-weight: 700; font-size: 14px; }
  .danfe-sub { text-align: center; font-size: 10px; color: #555; }
  .danfe-itens td, .danfe-itens th { border: 1px solid #999; padding: 3px 6px; font-size: 10px; }
  .danfe-itens th { background: #f0f0f0; text-align: left; }
  .danfe-right { text-align: right; }
  .danfe-total-box { border: 1px solid #333; padding: 6px 8px; margin-top: 6px; font-weight: 700; }
  .danfe-homolog { text-align: center; background: #b91c1c; color: #fff; font-weight: 700; padding: 6px; margin-bottom: 6px; letter-spacing: 0.5px; }
  .danfe-header-row { display: flex; gap: 8px; margin-bottom: 6px; }
  .danfe-header-row .danfe-box { flex: 1; margin-bottom: 0; }
`;

export function buildDanfeHtml(
  empresa: EmpresaHeader | null, detalhe: DanfeDetalhe | null, modeloDanfe: string | number | null | undefined,
): string {
  const paisagem = String(modeloDanfe ?? "0") === "1";
  if (!detalhe) {
    return `<!doctype html><html><head><meta charset="utf-8"><title>DANFE</title><style>${DANFE_CSS}</style></head>` +
      `<body><p>Não foi possível ler os dados desta Nota Fiscal.</p></body></html>`;
  }
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.bairro].filter(Boolean).join(", ")
    : "";
  const destEndereco = [detalhe.dest_endereco, detalhe.dest_numero, detalhe.dest_bairro].filter(Boolean).join(", ");
  const itensHtml = (detalhe.itens || [])
    .map(
      (it) => `<tr>
        <td>${esc(it.codigo)}</td><td>${esc(it.descricao)}</td>
        <td>${esc(it.ncm)}</td><td>${esc(it.cfop)}</td><td>${esc(it.unidade)}</td>
        <td class="danfe-right">${it.qtd}</td><td class="danfe-right">${fmtBRL(it.valor_unitario)}</td>
        <td class="danfe-right">${fmtBRL(it.valor_total)}</td>
      </tr>`
    )
    .join("");
  const contingencia = detalhe.tp_emis && detalhe.tp_emis !== "1"
    ? `<div class="danfe-homolog" style="background:#92400e">EMITIDA EM CONTINGÊNCIA — ${esc(detalhe.x_just || "pendente de autorização")}</div>`
    : "";

  return `
    <!doctype html>
    <html>
    <head>
      <meta charset="utf-8">
      <title>DANFE ${esc(detalhe.numero)}/${esc(detalhe.serie)}</title>
      <style>
        @page { size: A4 ${paisagem ? "landscape" : "portrait"}; margin: 10mm; }
        ${DANFE_CSS}
      </style>
    </head>
    <body>
      ${detalhe.tp_amb === "2" ? `<div class="danfe-homolog">AMBIENTE DE HOMOLOGAÇÃO — SEM VALOR FISCAL</div>` : ""}
      ${contingencia}

      <div class="danfe-title">DANFE — Documento Auxiliar da Nota Fiscal Eletrônica</div>
      <div class="danfe-sub">${detalhe.tp_nf === "0" ? "0 - ENTRADA" : "1 - SAÍDA"} — Nº ${esc(detalhe.numero)} — Série ${esc(detalhe.serie)}</div>

      <div class="danfe-header-row" style="margin-top:6px">
        <div class="danfe-box">
          <div class="danfe-cell-label">EMITENTE</div>
          <div class="danfe-cell-value" style="font-weight:700">${esc((empresa?.fantasia || empresa?.rz_social || detalhe.emit_nome || "").toUpperCase())}</div>
          <div class="danfe-cell-label" style="margin-top:2px">${esc(endereco)}${empresa?.cidade ? ` — ${esc(empresa.cidade)}/${esc(empresa.uf)}` : ""}</div>
          <div class="danfe-cell-label">CNPJ: ${esc(detalhe.emit_cnpj)}${empresa?.inscr_est ? ` · IE: ${esc(empresa.inscr_est)}` : ""}</div>
        </div>
        <div class="danfe-box">
          <div class="danfe-cell-label">CHAVE DE ACESSO</div>
          <div class="danfe-cell-value" style="font-family:monospace">${esc(fmtChave(detalhe.chave_acesso))}</div>
          ${buildBarcodeSvg(detalhe.chave_acesso || "", 32)}
          <div class="danfe-cell-label" style="margin-top:2px">Consulte a autenticidade no portal da NF-e</div>
          <div class="danfe-cell-label">Protocolo de autorização: ${esc(detalhe.protocolo_sefaz)} — ${fmtDataHora(detalhe.dh_recbto)}</div>
        </div>
      </div>

      <div class="danfe-box">
        <div class="danfe-cell-label">NATUREZA DA OPERAÇÃO</div>
        <div class="danfe-cell-value">${esc(detalhe.natureza_operacao)}</div>
      </div>

      <div class="danfe-section-title">DESTINATÁRIO/REMETENTE</div>
      <div class="danfe-box">
        <div class="danfe-grid">
          <div class="danfe-cell" style="flex:2"><div class="danfe-cell-label">Nome/Razão Social</div><div class="danfe-cell-value">${esc(detalhe.dest_nome)}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">CNPJ/CPF</div><div class="danfe-cell-value">${esc(detalhe.dest_doc)}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Data de Emissão</div><div class="danfe-cell-value">${fmtDataHora(detalhe.dh_emi)}</div></div>
        </div>
        <div class="danfe-grid">
          <div class="danfe-cell" style="flex:2"><div class="danfe-cell-label">Endereço</div><div class="danfe-cell-value">${esc(destEndereco)}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Município/UF</div><div class="danfe-cell-value">${esc(detalhe.dest_cidade)}/${esc(detalhe.dest_uf)}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">CEP</div><div class="danfe-cell-value">${esc(detalhe.dest_cep)}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Inscrição Estadual</div><div class="danfe-cell-value">${esc(detalhe.dest_ie) || "-"}</div></div>
        </div>
      </div>

      <div class="danfe-section-title">CÁLCULO DO IMPOSTO</div>
      <div class="danfe-box">
        <div class="danfe-grid">
          <div class="danfe-cell"><div class="danfe-cell-label">Base de Cálculo ICMS</div><div class="danfe-cell-value">-</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Valor do ICMS</div><div class="danfe-cell-value">-</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Valor do IPI</div><div class="danfe-cell-value">-</div></div>
          <div class="danfe-cell danfe-right"><div class="danfe-cell-label">VALOR TOTAL DA NOTA</div><div class="danfe-cell-value" style="font-weight:700">R$ ${fmtBRL(detalhe.valor_total)}</div></div>
        </div>
        ${detalhe.ibs_cbs_totais ? `
        <div class="danfe-grid" style="margin-top:4px">
          <div class="danfe-cell"><div class="danfe-cell-label">Base de Cálculo IBS/CBS</div><div class="danfe-cell-value">R$ ${fmtBRL(Number(detalhe.ibs_cbs_totais.base || 0))}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Valor Total do IBS</div><div class="danfe-cell-value">R$ ${fmtBRL(Number(detalhe.ibs_cbs_totais.valor_ibs || 0))}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Valor Total da CBS</div><div class="danfe-cell-value">R$ ${fmtBRL(Number(detalhe.ibs_cbs_totais.valor_cbs || 0))}</div></div>
        </div>` : ""}
      </div>

      <div class="danfe-section-title">TRANSPORTADOR/VOLUMES TRANSPORTADOS</div>
      <div class="danfe-box">
        <div class="danfe-grid">
          <div class="danfe-cell" style="flex:2"><div class="danfe-cell-label">Nome/Razão Social</div><div class="danfe-cell-value">${esc(detalhe.transportador?.nome) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">CNPJ/CPF</div><div class="danfe-cell-value">${esc(detalhe.transportador?.cgc_cpf) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Inscrição Estadual</div><div class="danfe-cell-value">${esc(detalhe.transportador?.ie) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Frete por Conta</div><div class="danfe-cell-value">${esc(MOD_FRETE_LABEL[detalhe.mod_frete || "9"] || "-")}</div></div>
        </div>
        <div class="danfe-grid" style="margin-top:4px">
          <div class="danfe-cell"><div class="danfe-cell-label">Placa</div><div class="danfe-cell-value">${esc(detalhe.veiculo?.placa) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">UF</div><div class="danfe-cell-value">${esc(detalhe.veiculo?.uf) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Qtd. Volumes</div><div class="danfe-cell-value">${esc(detalhe.volumes?.qtd) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Espécie</div><div class="danfe-cell-value">${esc(detalhe.volumes?.especie) || "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Peso Bruto</div><div class="danfe-cell-value">${detalhe.volumes?.peso_bruto ? `${detalhe.volumes.peso_bruto} kg` : "-"}</div></div>
          <div class="danfe-cell"><div class="danfe-cell-label">Peso Líquido</div><div class="danfe-cell-value">${detalhe.volumes?.peso_liquido ? `${detalhe.volumes.peso_liquido} kg` : "-"}</div></div>
        </div>
      </div>

      <div class="danfe-section-title">DADOS DOS PRODUTOS/SERVIÇOS</div>
      <table class="danfe-itens">
        <thead><tr><th>Código</th><th>Descrição</th><th>NCM</th><th>CFOP</th><th>Un.</th><th>Qtd.</th><th>Vl. Unit.</th><th>Vl. Total</th></tr></thead>
        <tbody>${itensHtml || `<tr><td colspan="8">Nenhum item.</td></tr>`}</tbody>
      </table>

      <div class="danfe-section-title" style="margin-top:6px">DADOS ADICIONAIS</div>
      <div class="danfe-box">
        <div class="danfe-cell-value">${esc(detalhe.natureza_operacao)}${detalhe.x_just ? ` — ${esc(detalhe.x_just)}` : ""}</div>
      </div>
    </body>
    </html>
  `;
}
