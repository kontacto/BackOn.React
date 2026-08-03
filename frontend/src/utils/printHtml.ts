// Impressão via iframe oculto — bem mais confiável do que o truque de CSS
// "esconde tudo com body *, mostra só #id" (ver ReciboPedidoModal.tsx):
// aquele truque depende de nenhum ancestral (Modal/ScrollView/Pressable)
// ter overflow/posicionamento que corte o conteúdo, e na prática a
// impressão saía em branco (reportado pelo usuário 2026-07-16 — preview
// do navegador só com o cabeçalho/rodapé nativos do Chrome, nada do
// recibo). Um iframe tem seu PRÓPRIO documento, isolado do resto da
// página — nada pra esconder, nada pra vazar.
// `paperWidthMm`: só pra impressão em bobina térmica (cupom/comanda) — sem
// isso, o navegador imprime na página padrão dele (A4/Letter), sem noção
// nenhuma da largura real do rolo, o que faz o conteúdo sair desproporcional
// (achado ao vivo 2026-07-23, comparando cupom impresso de verdade). Passar
// a largura real (mm) injeta `@page{size:...}` + trava a largura do `body`
// nesse valor, então o navegador já "sabe" o tamanho certo do papel. Deixar
// de fora (chamada padrão) mantém o comportamento de sempre — página normal
// — pros outros usos deste utilitário (relatórios, DANFCe, cotação, etc.),
// que não são impressão térmica.
export function printHtml(bodyHtml: string, title = "", paperWidthMm?: number) {
  if (typeof document === "undefined") return;
  const iframe = document.createElement("iframe");
  iframe.style.position = "fixed";
  iframe.style.right = "0";
  iframe.style.bottom = "0";
  iframe.style.width = "0";
  iframe.style.height = "0";
  iframe.style.border = "0";
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument;
  if (!doc) {
    document.body.removeChild(iframe);
    return;
  }
  const paperCss = paperWidthMm
    ? `@page { size: ${paperWidthMm}mm auto; margin: 0; } html, body { width: ${paperWidthMm}mm; }`
    : "";
  doc.open();
  doc.write(
    `<!doctype html><html><head><meta charset="utf-8"><title>${title}</title>` +
      `<style>
        * { box-sizing: border-box; }
        ${paperCss}
        body { font-family: "Courier New", Courier, monospace; font-size: 12px; color: #111; margin: 0; padding: 12px; }
        .center { text-align: center; }
        .bold { font-weight: 700; }
        .big { font-size: 15px; font-weight: 700; }
        .huge { font-size: 26px; font-weight: 800; line-height: 1.15; }
        .huge2 { font-size: 20px; font-weight: 800; line-height: 1.15; }
        .row { display: flex; justify-content: space-between; gap: 8px; }
        .row span:first-child { flex: 1; min-width: 0; word-break: break-word; }
        .row span:last-child { flex-shrink: 0; white-space: nowrap; }
        .row3 { display: flex; justify-content: space-between; gap: 8px; }
        .row3 span:nth-child(1) { flex: 1; min-width: 0; word-break: break-word; }
        .row3 span:nth-child(2) { flex-shrink: 0; white-space: nowrap; }
        .row3 span:nth-child(3) { flex-shrink: 0; white-space: nowrap; text-align: right; min-width: 64px; }
        .hr { border-bottom: 1px solid #999; margin: 6px 0; }
        .mb { margin-bottom: 4px; }
      </style></head><body>${bodyHtml}</body></html>`
  );
  doc.close();

  const cleanup = () => {
    if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
  };
  const win = iframe.contentWindow;
  if (win) {
    win.addEventListener("afterprint", cleanup);
    win.focus();
    win.print();
  }
  // Segurança: se `afterprint` não disparar (alguns navegadores/fluxos de
  // "Salvar como PDF"), remove de qualquer forma depois de um tempo — não
  // corta a impressão em andamento, só evita acumular iframes órfãos.
  setTimeout(cleanup, 120000);
}

export function escHtml(s: string | number | null | undefined): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
