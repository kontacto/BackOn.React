// Monta um recibo em TEXTO PURO (sem HTML/CSS) — formato usado pela fila de
// impressão silenciosa (POST /api/impressao/fila), consumida pelo agente
// local (print-agent/agente_impressao.py) que manda os bytes crus pro
// spooler do Windows via win32print (RAW, sem diálogo). No Checkout, este
// texto é montado automaticamente ao Fechar a Venda (sem botão manual de
// impressão nem preview em HTML — assim como no legado FrmPafOFF.frm) —
// reaproveitável por qualquer tela futura que precise do mesmo formato.
import { formatBRL, formatDateBR, fmtNum } from "@/src/utils/format";

const LARGURA = 42; // colunas — bobina térmica 80mm em fonte condensada

function centralizar(t: string): string {
  const s = t.slice(0, LARGURA);
  const pad = Math.max(0, Math.floor((LARGURA - s.length) / 2));
  return " ".repeat(pad) + s;
}

function linhaDupla(a: string, b: string): string {
  const espaco = Math.max(1, LARGURA - a.length - b.length);
  return a + " ".repeat(espaco) + b;
}

const HR = "-".repeat(LARGURA);

function temDocumentoValido(cgc: string | null | undefined): boolean {
  const v = (cgc || "").replace(/\D/g, "");
  return v.length > 0 && !/^0+$/.test(v);
}

export type ReciboTextoEmpresa = {
  fantasia?: string | null; rz_social?: string | null; uf?: string | null;
  endereco?: string; numero?: number | null; complemento?: string; bairro?: string; cidade?: string;
  cep?: string; ddd?: string | number; telefone?: string; celular?: string; cgc?: string; inscr_est?: string;
} | null;

export type ReciboTextoItem = { descricao: string; qtd: number; p_unit: number; preco_bruto: number; total: number };
export type ReciboTextoFormaPag = { descricao: string; forma_pag: string; valor: number };

export type ReciboTextoDados = {
  titulo: string; // ex.: "COMANDA Nº 123" — deixa a função reaproveitável por outras telas
  itens: ReciboTextoItem[];
  valorTotal: number;
  formasPagamento: ReciboTextoFormaPag[];
  troco: number;
  clienteNome: string;
  clienteCgcCpf: string;
  atendenteNome: string;
  data: string | null;
  mensagens: string[];
};

export function buildReciboTexto(empresa: ReciboTextoEmpresa, d: ReciboTextoDados): string {
  const linhas: string[] = [];
  const endereco = empresa
    ? [empresa.endereco, empresa.numero ? String(empresa.numero) : null, empresa.complemento].filter(Boolean).join(" ")
    : "";
  const cidade = empresa ? [empresa.bairro, empresa.cidade, empresa.uf].filter(Boolean).join(" - ") : "";

  if (empresa?.fantasia || empresa?.rz_social) {
    linhas.push(centralizar((empresa.fantasia || empresa.rz_social || "").toUpperCase()));
  }
  if (endereco) linhas.push(centralizar(endereco));
  if (cidade) linhas.push(centralizar(`${cidade}${empresa?.cep ? ` CEP: ${empresa.cep}` : ""}`));
  if (empresa?.telefone) {
    linhas.push(centralizar(`Tel: (${empresa.ddd}) ${empresa.telefone}${empresa.celular ? ` / ${empresa.celular}` : ""}`));
  }
  if (empresa?.cgc) linhas.push(centralizar(`CNPJ: ${empresa.cgc}${empresa.inscr_est ? ` IE: ${empresa.inscr_est}` : ""}`));
  linhas.push(HR);
  linhas.push(d.titulo);
  linhas.push(HR);

  d.itens.forEach((it) => {
    linhas.push(it.descricao);
    linhas.push(linhaDupla(`${fmtNum(it.qtd)} x ${formatBRL(it.p_unit)}`, formatBRL(it.total)));
  });
  linhas.push(HR);

  // Mesmo critério de ReciboCheckoutModal.tsx: subtotal bruto = soma de
  // qtd*preco_bruto (preço de lista, antes do desconto); a linha DESCONTO
  // só aparece quando isso diverge do total já com desconto aplicado.
  const subtotalBruto = d.itens.reduce((s, r) => s + r.qtd * r.preco_bruto, 0);
  const descontoTotal = subtotalBruto - d.valorTotal;
  if (subtotalBruto > 0 && descontoTotal > 0.005) {
    linhas.push(linhaDupla("SUB-TOTAL", formatBRL(subtotalBruto)));
    linhas.push(linhaDupla("DESCONTO", formatBRL(descontoTotal)));
  }
  linhas.push(linhaDupla("TOTAL", formatBRL(d.valorTotal)));
  linhas.push(HR);

  linhas.push("FORMA DE PAGAMENTO");
  if (d.formasPagamento.length > 0) {
    d.formasPagamento.forEach((f) => linhas.push(linhaDupla(f.descricao || f.forma_pag, formatBRL(f.valor))));
    if (d.troco > 0.004) linhas.push(linhaDupla("TROCO", formatBRL(d.troco)));
  } else {
    linhas.push("(ainda não definida)");
  }
  linhas.push(HR);

  if (temDocumentoValido(d.clienteCgcCpf)) linhas.push(`Doc: ${d.clienteCgcCpf}`);
  linhas.push(d.clienteNome || "CLIENTES DIVERSOS");
  linhas.push(HR);

  linhas.push(`Atendente: ${d.atendenteNome}`);
  if (d.data) linhas.push(formatDateBR(d.data));

  if (d.mensagens.length > 0) {
    linhas.push(HR);
    d.mensagens.forEach((m) => linhas.push(centralizar(m)));
  }

  // Margem final — o corte de papel fica a cargo da impressora (ESC/POS de
  // corte automático) ou do operador; não emitimos comando de corte cru
  // aqui, mesma decisão já tomada em enviar_rede (backend).
  return linhas.join("\n") + "\n\n\n";
}
