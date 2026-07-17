// Exportação Excel genérica — introduzida para o Borderô de Cilindros
// (frontend/app/bordero-cilindros.tsx), primeira tela do projeto a exigir
// .xlsx real em vez do padrão de PDF já usado pelos relatórios existentes
// (ver `export-report.ts`/`export-margem-lucro.ts`, que geram HTML e usam
// expo-print/expo-sharing). O usuário confirmou explicitamente, via
// pergunta direta, que o Borderô deve exportar Excel de verdade — não
// impressão formatada — daí a biblioteca nova (`xlsx`/SheetJS) em vez de
// reaproveitar o caminho de PDF.
//
// Web-only: `XLSX.writeFile` no navegador já dispara o download do
// arquivo (cria um Blob + clique simulado em `<a download>`), sem precisar
// de expo-sharing — suficiente porque o módulo Cilindros inteiro já é
// web-only (ver "Platform Scope" no CLAUDE.md).
import * as XLSX from "xlsx";

export type XlsxSheet = {
  name: string;
  rows: Record<string, unknown>[];
};

export function exportSheetsToXlsx(filename: string, sheets: XlsxSheet[]) {
  const wb = XLSX.utils.book_new();
  for (const sheet of sheets) {
    const ws = XLSX.utils.json_to_sheet(sheet.rows);
    // Nome de aba do Excel tem limite de 31 caracteres.
    XLSX.utils.book_append_sheet(wb, ws, sheet.name.slice(0, 31));
  }
  XLSX.writeFile(wb, filename.endsWith(".xlsx") ? filename : `${filename}.xlsx`);
}
