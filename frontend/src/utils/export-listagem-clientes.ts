// Listagem de Clientes — migração de Geral\FrmRelClie.frm (Painel de
// Relatórios > Clientes). O PDF mostra contato+endereço por cliente (dado
// que a tela/Excel não mostram) — precisa buscar o detalhe por cliente
// antes de montar o HTML (ver detalheFetcher).
import { Platform } from "react-native";
import * as Print from "expo-print";
import * as Sharing from "expo-sharing";
import { buildReportHeaderHtml, EmpresaHeader, REPORT_HEADER_CSS } from "./print-report-header";

export type ClienteListagemRow = {
  codigo: number; cgc_cpf: string; nome: string; e_mail: string;
  data_cad: string | null; data_nasc: string | null; tipo: number | null; situacao: string;
};
export type DetalheClienteContato = { telefones: string[]; enderecos: string[] };

function esc(s: string): string {
  return (s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function buildHtml(
  titulo: string, periodo: string, clientes: ClienteListagemRow[], empresa: EmpresaHeader | null,
  detalheFetcher: (codigo: number) => Promise<DetalheClienteContato>,
): Promise<string> {
  const geradoEm = new Date().toLocaleString("pt-BR");
  const blocos = await Promise.all(
    clientes.map(async (c) => {
      const det = await detalheFetcher(c.codigo);
      const contato = [c.e_mail, ...det.telefones].filter(Boolean).join(" / ");
      return `
        <div class="bloco">
          <div class="linha1">
            <span class="nome">${esc(c.nome)}</span>
            <span class="cgc">${esc(c.cgc_cpf)}</span>
          </div>
          <div class="meta">Código ${c.codigo} · Cadastro ${esc(c.data_cad || "—")} · Situação ${esc(c.situacao)}</div>
          ${contato ? `<div class="meta">Contato(s): ${esc(contato)}</div>` : ""}
          ${det.enderecos.map((e) => `<div class="meta">${esc(e)}</div>`).join("")}
        </div>`;
    })
  );
  return `<!DOCTYPE html><html><head><meta charset="utf-8" />
  <style>
    * { box-sizing: border-box; }
    body { font-family: -apple-system, Helvetica, Arial, sans-serif; color: #1a1a2e; padding: 24px; font-size: 11px; }
    ${REPORT_HEADER_CSS}
    .meta_top { color: #777; font-size: 11px; margin-bottom: 16px; text-align: center; }
    .bloco { padding: 8px 0; border-bottom: 1px solid #eee; }
    .linha1 { display: flex; justify-content: space-between; font-weight: 700; font-size: 12px; }
    .meta { color: #555; font-size: 10px; margin-top: 2px; }
  </style></head><body>
    ${buildReportHeaderHtml(empresa, titulo)}
    <div class="meta_top">${esc(periodo)} · Gerado em ${esc(geradoEm)}</div>
    ${blocos.join("") || "<p>Nenhum cliente encontrado.</p>"}
  </body></html>`;
}

export async function exportListagemClientesPdf(
  titulo: string, periodo: string, clientes: ClienteListagemRow[], empresa: EmpresaHeader | null,
  detalheFetcher: (codigo: number) => Promise<DetalheClienteContato>,
): Promise<void> {
  const html = await buildHtml(titulo, periodo, clientes, empresa, detalheFetcher);
  if (Platform.OS === "web") {
    await Print.printAsync({ html });
    return;
  }
  const { uri } = await Print.printToFileAsync({ html });
  const canShare = await Sharing.isAvailableAsync();
  if (canShare) {
    await Sharing.shareAsync(uri, { mimeType: "application/pdf", dialogTitle: titulo, UTI: "com.adobe.pdf" });
  } else {
    await Print.printAsync({ uri });
  }
}
