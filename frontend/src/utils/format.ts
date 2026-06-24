// Helpers de formatação e parse numérico (pt-BR) usados nas telas de pedido.

export function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export function parseNum(s: string): number {
  const n = parseFloat(String(s).replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}

export function fmtNum(n: number): string {
  return String(Math.round((n + Number.EPSILON) * 1000) / 1000).replace(".", ",");
}

// Formata valores monetários (descontos, acréscimos, totais) sempre com 2 casas decimais.
export function fmtMoney2(n: number): string {
  return (Math.round((n + Number.EPSILON) * 100) / 100).toFixed(2).replace(".", ",");
}

// Desconto unitário em R$: se % preenchido usa p_normal*%/100, senão usa o valor em R$.
export function calcDescUnit(pNormal: number, pctStr: string, rsStr: string): number {
  const pct = parseNum(pctStr);
  if (pct > 0) return round2((pNormal * pct) / 100);
  return parseNum(rsStr);
}

export function formatDateBR(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

export function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
