// Constantes compartilhadas do "Painel de Pedidos" (Mesa/Comanda/Balcão/
// Entrega) — usadas tanto pela lista (app/pedidos.tsx) quanto pelo card
// rico (PainelPedidoCard.tsx). Um único lugar pra ordem/ícone/cor de cada
// tipo, pra não divergir entre os dois arquivos. Pedido explícito do
// usuário, 2026-07-17.

export function normalizaDescricao(s: string): string {
  return (s || "").trim().toUpperCase();
}

// Chave de agrupamento — "BALCAO" (sem cedilha, como pode vir cadastrado)
// cai junto com "BALCÃO" na mesma coluna/total.
export function tipoClienteKey(descricao: string): string {
  const n = normalizaDescricao(descricao);
  return n === "BALCAO" ? "BALCÃO" : n;
}

// Ordem fixa das colunas no painel — independe da ordem de seleção do
// filtro ou da ordem devolvida por /api/tipo-cliente. FIADO adicionado no
// fim, pedido explícito do usuário, 2026-07-18.
export const ORDEM_COLUNAS_TIPO = ["MESA", "COMANDA", "BALCÃO", "ENTREGA", "FIADO"];

// Ícone por tipo, um em cada card do painel.
export const TIPO_ICON: Record<string, { name: string; lib: "mci" | "ion" }> = {
  MESA: { name: "table-furniture", lib: "mci" },
  "BALCÃO": { name: "storefront-outline", lib: "ion" },
  COMANDA: { name: "receipt-outline", lib: "ion" },
  ENTREGA: { name: "bicycle-outline", lib: "ion" },
  FIADO: { name: "book-outline", lib: "ion" },
};

// Cor por tipo — título de cada coluna do painel.
export const TIPO_COLOR: Record<string, string> = {
  MESA: "#0B2A5B",
  "BALCÃO": "#C27A29",
  COMANDA: "#1F7A4D",
  ENTREGA: "#6B3FA0",
  FIADO: "#A31621",
};
