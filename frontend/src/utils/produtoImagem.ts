// Fotos de Produto — sistema novo, isolado do Gestor de Documentos (que
// continua servindo DOCUMENTO de produto). Ver backend/services/
// produto_imagem_service.py para o desenho completo.
//
// Toda leitura passa pela rota do backend (nunca URL direta do driver de
// storage) — mesma decisão já usada pelo Gestor de Documentos.

export type ConnLike = { servidor: string; banco: string; api: string };
export type ProdutoImagemVariante = "thumb" | "medium" | "web" | "original";

export function produtoImagemUrl(conn: ConnLike, codigo: number, variante: ProdutoImagemVariante = "thumb"): string {
  const base = conn.api.replace(/\/+$/, "");
  const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&variante=${variante}`;
  return `${base}/api/produto-imagem/${codigo}/arquivo?${qs}`;
}
