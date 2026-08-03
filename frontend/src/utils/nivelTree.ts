// Árvore de Nível (Grupo Mercadológico, tabela `niveis`) — path materializado por
// concatenação de nivel1..nivel5 (não por parent_id). Extraído de
// grupo-mercadologico.tsx para reaproveitar em produtos-niveis.tsx sem duplicar.
export type NivelFlat = {
  cod_nivel: number;
  nivel1: string; nivel2: string; nivel3: string; nivel4: string; nivel5: string;
  descricao: string;
  custo: number | null;
  classe_entrada: number | null;
  sub_classe_entrada: number | null;
  classe_saida: number | null;
  sub_classe_saida: number | null;
};

export type NivelNode = NivelFlat & { depth: number; path: string; children: NivelNode[] };

export const segments = (n: Pick<NivelFlat, "nivel1" | "nivel2" | "nivel3" | "nivel4" | "nivel5">) =>
  [n.nivel1, n.nivel2, n.nivel3, n.nivel4, n.nivel5].filter((s) => s);

// [GLOBAL] Todo nível exibido (cadastros e filtros de relatório que usam
// essa tabela auxiliar) deve mostrar o caminho completo — a descrição de
// cada nó ancestral, do topo até o nó escolhido, juntada por "\" — mesmo
// formato do `NIVEIS.SelectedItem.FullPath` do legado VB6 (ex.:
// "Kontacto\Produto\Microcomputadores"), nunca só a descrição do nó-folha.
// Usa o mesmo esquema de segmentos fixos de 3 caracteres por nível já usado
// pelo backend (`_nivel_clause`, `margem_lucro_service.py`) — cada
// ancestral já existe como sua própria linha na lista `niveis`, então basta
// resolver o prefixo do código em cada profundidade.
export function buildNivelBreadcrumb(lista: { codigo: string; descricao: string }[], codigo: string): string {
  if (!codigo) return "";
  const porCodigo = new Map(lista.map((n) => [n.codigo, n.descricao]));
  const partes: string[] = [];
  for (let i = 3; i <= codigo.length; i += 3) {
    const prefixo = codigo.slice(0, i);
    partes.push(porCodigo.get(prefixo) ?? prefixo);
  }
  return partes.join("\\");
}

export function buildTree(flat: NivelFlat[]): NivelNode[] {
  const nodes: NivelNode[] = flat.map((f) => {
    const segs = segments(f);
    return { ...f, depth: segs.length, path: segs.join("/"), children: [] };
  });
  const byPath = new Map(nodes.map((n) => [n.path, n]));
  const roots: NivelNode[] = [];
  for (const n of nodes) {
    if (n.depth <= 1) { roots.push(n); continue; }
    const parentPath = segments(n).slice(0, n.depth - 1).join("/");
    const parent = byPath.get(parentPath);
    if (parent) parent.children.push(n); else roots.push(n);
  }
  const sortRec = (list: NivelNode[]) => {
    list.sort((a, b) => a.descricao.localeCompare(b.descricao, "pt-BR"));
    list.forEach((n) => sortRec(n.children));
  };
  sortRec(roots);
  return roots;
}
