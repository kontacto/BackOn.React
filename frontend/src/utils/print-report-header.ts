// Cabeçalho padrão de impressão de relatório — [GLOBAL] 2026-07-16, pedido
// explícito do usuário: toda impressão de relatório deve trazer os dados
// da empresa (Controle) no topo, com o NOME DO RELATÓRIO logo abaixo — não
// o filtro selecionado na tela (período/vendedor/atendente/etc.), que fica
// só na tela mesmo. Compartilhado entre export-report.ts,
// export-fechamento-caixa.ts e qualquer export de relatório futuro — não
// duplicar esta busca/HTML por tela.
export type EmpresaHeader = {
  fantasia?: string | null;
  rz_social?: string | null;
  uf?: string | null;
  endereco?: string;
  numero?: number | null;
  complemento?: string;
  bairro?: string;
  cidade?: string;
  cep?: string;
  ddd?: string | number;
  telefone?: string;
  celular?: string;
  cgc?: string;
  inscr_est?: string;
};

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** Busca os dados da empresa em Controle — mesma rota já usada pelo recibo
 * do Pedido Bar (`ReciboPedidoModal.tsx`). Falha silenciosamente (retorna
 * null) — a ausência do cabeçalho de empresa não pode impedir a impressão
 * do relatório em si. */
export async function fetchEmpresaHeader(apiBase: string, servidor: string, banco: string): Promise<EmpresaHeader | null> {
  try {
    const base = apiBase.replace(/\/+$/, "");
    const r = await fetch(`${base}/api/controle/empresa?servidor=${encodeURIComponent(servidor)}&banco=${encodeURIComponent(banco)}`);
    const j = await r.json();
    return j?.success ? j : null;
  } catch {
    return null;
  }
}

export const REPORT_HEADER_CSS = `
  .rel-empresa { text-align: center; margin-bottom: 10px; }
  .rel-empresa-nome { font-weight: 700; font-size: 14px; color: #1a1a2e; }
  .rel-empresa-linha { font-size: 11px; color: #555; margin-top: 1px; }
  .rel-titulo { font-size: 17px; margin: 8px 0 2px; color: #1f3a93; text-align: center; }
`;

/** Monta o bloco de cabeçalho (empresa + nome do relatório logo abaixo) —
 * sem nenhum resumo de filtro da tela (período/vendedor/atendente/etc.),
 * por pedido explícito do usuário. */
export function buildReportHeaderHtml(empresa: EmpresaHeader | null, tituloRelatorio: string): string {
  const nome = (empresa?.fantasia || empresa?.rz_social || "").toUpperCase();
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.complemento].filter(Boolean).join(" ")
    : "";
  const cidade = empresa ? [empresa.bairro, empresa.cidade, empresa.uf].filter(Boolean).join(" - ") : "";
  return `
    <div class="rel-empresa">
      ${nome ? `<div class="rel-empresa-nome">${esc(nome)}</div>` : ""}
      ${endereco ? `<div class="rel-empresa-linha">${esc(endereco)}</div>` : ""}
      ${cidade ? `<div class="rel-empresa-linha">${esc(cidade)}${empresa?.cep ? ` CEP: ${esc(empresa.cep)}` : ""}</div>` : ""}
      ${empresa?.telefone ? `<div class="rel-empresa-linha">Tel: (${esc(String(empresa.ddd || ""))}) ${esc(empresa.telefone)}${empresa.celular ? ` / ${esc(empresa.celular)}` : ""}</div>` : ""}
      ${empresa?.cgc ? `<div class="rel-empresa-linha">CNPJ: ${esc(empresa.cgc)}${empresa.inscr_est ? ` IE: ${esc(empresa.inscr_est)}` : ""}</div>` : ""}
    </div>
    <h1 class="rel-titulo">${esc(tituloRelatorio)}</h1>
  `;
}
