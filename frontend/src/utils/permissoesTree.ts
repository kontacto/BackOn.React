// Árvore do catálogo de permissões (Menu > Tela > Botão) — extraído de
// permissoes.tsx para reaproveitar em log-auditoria.tsx (seleção única de
// Tela/Ação como filtro) sem duplicar a árvore pela terceira vez.
export type CatNode = {
  tipo: "MENU" | "TELA" | "BOTAO";
  tela: string;
  comando: string;
  nome: string;
  children: CatNode[];
};

// chave única de um nó (tipo|tela|comando)
export const keyOf = (n: { tipo: string; tela: string; comando: string }) =>
  `${n.tipo}|${n.tela}|${n.comando || ""}`;

// percorre a árvore e devolve todas as chaves descendentes (inclui o próprio nó)
export function collectKeys(node: CatNode, acc: string[] = []): string[] {
  acc.push(keyOf(node));
  node.children.forEach((c) => collectKeys(c, acc));
  return acc;
}

// mapa chave -> nó
export function flatten(nodes: CatNode[], map: Record<string, CatNode> = {}): Record<string, CatNode> {
  nodes.forEach((n) => {
    map[keyOf(n)] = n;
    flatten(n.children, map);
  });
  return map;
}
