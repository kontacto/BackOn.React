// Orientação de resolução pra logo (empresa/banco) — 2026-08-26, pedido
// explícito do usuário: "orientar a resolução da imagem da logo. Essa
// imagem será utilizada em todos os relatórios e cupom fiscal e não
// fiscal do sistema".
//
// A logo é sempre desenhada em ESCALA REDUZIDA (nunca ampliada) nos
// consumidores já existentes — O.S. Completa (A4, até ~28×20mm) e Boleto
// (até ~45×7mm) — então o que importa é um MÍNIMO de nitidez a 300dpi
// (resolução de impressão), não um máximo. A 300dpi, a maior área de uso
// hoje (O.S. A4) pede ~330×236px pra sair nítida; a orientação abaixo dá
// uma folga confortável pra cobrir também os futuros usos (cupom fiscal/
// não fiscal, outros relatórios) sem pedir uma imagem gigante demais pra
// gravar direto no banco (VARBINARY — decisão já tomada, não Azure Blob).
export const LOGO_LARGURA_MINIMA = 400;
export const LOGO_ALTURA_MINIMA = 200;
export const LOGO_TAMANHO_MAXIMO_BYTES = 1024 * 1024; // 1 MB

export const LOGO_ORIENTACAO_TEXTO =
  "Formato PNG (fundo transparente) ou JPG. Resolução mínima recomendada: " +
  `${LOGO_LARGURA_MINIMA}×${LOGO_ALTURA_MINIMA} pixels (nítida em impressão A4/boleto — ` +
  "a imagem é sempre reduzida, nunca ampliada). Arquivo até 1 MB.";

/** Lê as dimensões reais de um arquivo de imagem antes do upload — só
 * pra orientar o usuário (aviso, não bloqueio); nunca lança, devolve
 * `null` se não conseguir ler (arquivo corrompido/formato inesperado). */
export function lerResolucaoImagem(arquivo: File): Promise<{ largura: number; altura: number } | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(arquivo);
    const img = new window.Image();
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({ largura: img.naturalWidth, altura: img.naturalHeight });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(null);
    };
    img.src = url;
  });
}
