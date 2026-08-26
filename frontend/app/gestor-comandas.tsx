// Gestor de Comandas — migração de `FrmConCupom.frm` ("Consulta de
// Vendas"). Relatório/consulta somente leitura sobre `comanda` — a tabela
// que representa toda venda finalizada no sistema (Pedido Bar/Geral, O.S.
// faturada, Faturar Contratos). Ver CLAUDE.md e
// `backend/services/comanda_service.py` pro racional completo.
//
// Cada linha tem um botão dedicado "Alterar" que abre `alterar-comanda.tsx`
// (Fase 2) — só esse botão abre a tela de alteração, pedido explícito do
// usuário (2026-07-21): "a tela alterar comanda só será chamada pelo
// gestor de comandas, através de um botão em cada registro da lista dela".
// Quando a comanda tiver Pedido/O.S. vinculado, um botão extra abre a
// Pré-Venda de origem — mesmo padrão já usado em telas de relatório
// (`relatorio-descontos.tsx`/`PedidosTable.tsx`): `/os-form?os=` ou
// `/pedido-form?pedido=`.
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import WebDateField from "@/src/components/WebDateField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { useClienteSearchModal } from "@/src/hooks/useClienteSearchModal";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { printHtml, printFullHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { buildDanfceHtml, buildDanfseHtml, buildDanfeHtml } from "@/src/utils/danfeFacsimile";
import { friendlyApiError } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";
import { comandasFiltrosKey, loadComandasFiltros, saveComandasFiltros } from "@/src/utils/storage/comandasFilters";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function brDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

type ComandaItem = {
  comanda: number;
  data: string | null;
  valor: number;
  situacao: string;
  situacao_label: string;
  cliente: number | null;
  cliente_nome: string;
  num_pdv: number | null;
  num_cupom: number | null;
  num_nfce: number | null;
  num_nf: number | null;
  pedido_vinculado: number | null;
  os_vinculada: number | null;
  atendente_nome: string;
};

type ResumoFormaPag = { tipo: string; label: string; valor: number };
type Resumo = {
  total_geral: number; total_ecf: number; total_nfce: number; total_nf: number; total_sem_documento: number;
  total_sem_pagamento: number; por_forma_pagamento: ResumoFormaPag[];
};

const RESUMO_VAZIO: Resumo = {
  total_geral: 0, total_ecf: 0, total_nfce: 0, total_nf: 0, total_sem_documento: 0,
  total_sem_pagamento: 0, por_forma_pagamento: [],
};

// Modo Didático (CLAUDE.md, regras 4-5) — ícone único "i" no cabeçalho,
// reunindo a explicação de cada ação/coluna da tela em linguagem de
// usuário final. Pedido explícito do usuário, 2026-07-21.
const GESTOR_COMANDAS_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Buscar e Filtrar",
    texto: "Toque para abrir os filtros de busca (período, comanda, cliente, cupom, NFCe, NF, valor). O período sempre nasce na data de hoje; os demais filtros ficam salvos para a próxima vez que você abrir esta tela.",
    icon: { lib: "ion", name: "filter-outline" },
  },
  {
    titulo: "Totais",
    texto: "Soma o valor de todas as comandas encontradas, separado por tipo de documento fiscal (ECF, NFCe, Nota Fiscal) e por comandas sem nenhum documento vinculado.",
    icon: { lib: "ion", name: "calculator-outline" },
  },
  {
    titulo: "Alterar (ícone de lápis)",
    texto: "Abre a tela de Alterar Comanda, onde é possível corrigir atendente/vendedor/cliente, trocar forma de pagamento, gerenciar números de série ou cancelar a venda.",
    icon: { lib: "ion", name: "create-outline" },
  },
  {
    titulo: "Pré-Venda",
    texto: "Quando a comanda veio de um Pedido ou O.S. faturado, toque no número da Pré-Venda (ou no ícone ao lado) para abrir a tela original de onde a venda saiu.",
    icon: { lib: "ion", name: "receipt-outline" },
  },
  {
    titulo: "Reimprimir (ícone de impressora)",
    texto: "Reimprime os dados já registrados do documento fiscal vinculado (Nota Fiscal, NFCe ou Cupom). Não é uma via oficial idêntica ao documento original — apenas os dados armazenados no sistema.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Excel",
    texto: "Exporta a lista de comandas encontrada para uma planilha.",
    icon: { lib: "ion", name: "download-outline" },
  },
  {
    titulo: "Imprimir (cabeçalho)",
    texto: "Imprime o relatório completo da consulta atual, com o cabeçalho da empresa — sem mostrar os filtros escolhidos na tela.",
    icon: { lib: "ion", name: "print-outline" },
  },
];

export default function GestorComandasScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gestor de Comandas está disponível apenas no web." testID="gestor-comandas-web-only" />;
  }

  const canAbrir = can("COMANDA.ABRIR") || isMaster;
  const canImprimir = can("COMANDA.IMPRIMIR") || isMaster;
  const canExportar = can("COMANDA.EXPORTAR") || isMaster;
  const canAlterar = can("ALTERAR_COMANDA.ABRIR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(false);

  const [dataIni, setDataIni] = useState<string | null>(todayIso());
  const [dataFim, setDataFim] = useState<string | null>(todayIso());
  const [comandaNum, setComandaNum] = useState("");
  const [clienteTermo, setClienteTermo] = useState("");
  const clienteSearch = useClienteSearchModal(conn);
  const [cupom, setCupom] = useState("");
  const [nfce, setNfce] = useState("");
  const [nf, setNf] = useState("");
  const [valorDe, setValorDe] = useState("");
  const [valorAte, setValorAte] = useState("");
  const [comNota, setComNota] = useState(true);
  const [semNota, setSemNota] = useState(true);
  const [ordenarPor, setOrdenarPor] = useState<"venda" | "cliente">("venda");

  const [itens, setItens] = useState<ComandaItem[]>([]);
  const [resumo, setResumo] = useState<Resumo>(RESUMO_VAZIO);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);

  const filtrosRestauradosRef = useRef(false);
  const storageKeyRef = useRef<string | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      // Restaura a última seleção de filtros salva (empresa+banco) — exceto
      // o período, que sempre nasce em "hoje" (pedido explícito do usuário,
      // mesmo padrão de pedidosFilters.ts).
      if (!filtrosRestauradosRef.current) {
        filtrosRestauradosRef.current = true;
        const key = comandasFiltrosKey(c.empresa, c.banco);
        storageKeyRef.current = key;
        const saved = await loadComandasFiltros(key);
        if (saved) {
          setComNota(saved.comNota);
          setSemNota(saved.semNota);
          setOrdenarPor(saved.ordenarPor || "venda");
        }
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  // Grava a última seleção de filtros — só depois da restauração inicial,
  // senão os valores padrão sobrescreveriam o que estava salvo.
  useEffect(() => {
    if (!filtrosRestauradosRef.current || !storageKeyRef.current) return;
    saveComandasFiltros(storageKeyRef.current, { comNota, semNota, ordenarPor });
  }, [comNota, semNota, ordenarPor]);

  const int_ = (s: string): number | undefined => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || undefined : undefined);
  const float_ = (s: string): number | undefined => {
    const n = parseFloat(s.replace(",", "."));
    return Number.isFinite(n) ? n : undefined;
  };

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor,
        banco: conn.banco,
        data_ini: dataIni || undefined,
        data_fim: dataFim || undefined,
        comanda: int_(comandaNum),
        cliente: clienteTermo.trim() || undefined,
        cupom: int_(cupom),
        nfce: int_(nfce),
        nf: int_(nf),
        valor_de: float_(valorDe),
        valor_ate: float_(valorAte),
        com_nota: comNota,
        sem_nota: semNota,
        ordenar_por: ordenarPor,
      };
      const r = await fetch(`${base}/api/comandas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        setItens(j.items || []);
        // Mescla com o vazio (não só `j.resumo || RESUMO_VAZIO`) — protege
        // contra um backend ainda rodando código antigo (sem reiniciar),
        // que devolveria um `resumo` sem os campos novos
        // (`por_forma_pagamento`/`total_sem_pagamento`) e quebraria o
        // `.length`/`.map` na tela.
        setResumo({ ...RESUMO_VAZIO, ...(j.resumo || {}) });
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível consultar as comandas."));
        setItens([]);
        setResumo(RESUMO_VAZIO);
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, comandaNum, clienteTermo, cupom, nfce, nf, valorDe, valorAte, comNota, semNota, ordenarPor, fb]);

  useEffect(() => {
    if (conn) buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const exportarExcel = () => {
    if (!itens.length) { fb.showWarning("Consulte antes de exportar."); return; }
    exportSheetsToXlsx("gestor-comandas", [
      {
        name: "Comandas",
        rows: itens.map((it) => ({
          Comanda: it.comanda, Data: brDate(it.data), Cliente: it.cliente_nome, Valor: it.valor,
          Situação: it.situacao_label, Pdv: it.num_pdv, Cupom: it.num_cupom, NFCe: it.num_nfce, NF: it.num_nf,
          Pedido: it.pedido_vinculado, OS: it.os_vinculada, Atendente: it.atendente_nome,
        })),
      },
    ]);
  };

  const imprimir = async () => {
    if (!conn || !itens.length) { fb.showWarning("Consulte antes de imprimir."); return; }
    const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
    const linhas = itens.map((it) => `
      <tr>
        <td>${it.comanda}</td>
        <td>${escHtml(brDate(it.data))}</td>
        <td>${escHtml(it.cliente_nome)}</td>
        <td style="text-align:right">${formatBRL(it.valor)}</td>
        <td>${escHtml(it.situacao_label)}</td>
        <td>${it.num_cupom ?? ""}</td>
        <td>${it.num_nfce ?? ""}</td>
        <td>${it.num_nf ?? ""}</td>
        <td>${escHtml(it.atendente_nome)}</td>
      </tr>`).join("");
    const html = `
      ${buildReportHeaderHtml(empresa, "Gestor de Comandas")}
      <p style="font-size:12px;color:#555">Período: ${brDate(dataIni)} a ${brDate(dataFim)}</p>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:1px solid #999">
          <th align="left">Comanda</th><th align="left">Data</th><th align="left">Cliente</th>
          <th align="right">Valor</th><th align="left">Situação</th><th align="left">Cupom</th>
          <th align="left">NFCe</th><th align="left">NF</th><th align="left">Atendente</th>
        </tr></thead>
        <tbody>${linhas}</tbody>
      </table>
      <p style="font-size:12px;margin-top:12px">
        Total Geral: ${formatBRL(resumo.total_geral)} · ECF: ${formatBRL(resumo.total_ecf)} ·
        NFCe: ${formatBRL(resumo.total_nfce)} · NF: ${formatBRL(resumo.total_nf)} ·
        Sem Documento: ${formatBRL(resumo.total_sem_documento)} ·
        Sem Pagamento Lançado: ${formatBRL(resumo.total_sem_pagamento)}
      </p>
      ${resumo.por_forma_pagamento.length > 0 ? `<p style="font-size:12px">Por Forma de Pagamento: ${resumo.por_forma_pagamento.map((fp) => `${escHtml(fp.label)}: ${formatBRL(fp.valor)}`).join(" · ")}</p>` : ""}
      <style>${REPORT_HEADER_CSS}</style>`;
    printHtml(html, "Gestor de Comandas");
  };

  // Reimpressão do documento fiscal vinculado à comanda — migração do
  // atalho `[F2] - Reimprimir Não-fiscal ou NFCe` do legado. Pra NFC-e/
  // NFS-e, monta um fac-símile visual (DANFCe/DANFSe) — pedido explícito
  // do usuário 2026-07-21, com exemplo real de DANFSe colado — em vez da
  // lista crua de campos usada antes. NF genérica/Cupom ECF continuam sem
  // fac-símile (nenhum layout de referência disponível ainda).
  const reimprimirDocFiscal = async (it: ComandaItem) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/comandas/${it.comanda}/doc-fiscal?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showWarning(friendlyApiError(j, "Nenhum documento fiscal vinculado a esta comanda.")); return; }
      if (j.tipo === "NFCE") {
        const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
        printHtml(buildDanfceHtml(empresa, it.comanda, j.detalhe), "DANFCe");
        return;
      }
      if (j.tipo === "NFSE") {
        printHtml(buildDanfseHtml(j.chave_acesso, j.numero_dps, j.serie_dps, j.data_emissao, j.valor, j.detalhe), "DANFSe");
        return;
      }
      if (j.tipo === "NF" && j.detalhe) {
        const empresaNf = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
        printFullHtml(buildDanfeHtml(empresaNf, j.detalhe, j.modelo_danfe));
        return;
      }
      const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
      const tituloDoc = j.tipo === "NF" ? "Nota Fiscal" : "Cupom Fiscal";
      const linhas: string[] = [];
      if (j.tipo === "NF") {
        linhas.push(`Número: ${j.numero ?? ""}`, `Série: ${escHtml(String(j.serie ?? ""))}`, `Situação: ${escHtml(j.situacao || "")}`,
          `Protocolo SEFAZ: ${escHtml(j.protocolo || "")}`, `Chave de Acesso: ${escHtml(j.chave_acesso || "")}`);
      } else {
        linhas.push(`PDV: ${j.num_pdv ?? ""}`, `Número do Cupom: ${j.numero ?? ""}`, `COO: ${escHtml(j.coo || "")}`, `Situação: ${escHtml(j.situacao || "")}`);
      }
      const html = `
        ${buildReportHeaderHtml(empresa, `Reimpressão — ${tituloDoc} (Comanda ${it.comanda})`)}
        <p style="font-size:12px;color:#555">Esta reimpressão reproduz os dados já armazenados no sistema — não é uma via fac-símile do documento oficial.</p>
        <div style="font-size:13px;line-height:1.8">${linhas.map((l) => `<div>${l}</div>`).join("")}</div>
        <style>${REPORT_HEADER_CSS}</style>`;
      printHtml(html, `Reimpressão — ${tituloDoc}`);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  // Navegação pra Pré-Venda vinculada — acionada tanto pelo ícone quanto
  // por um toque direto na referência dentro da linha (a coluna Comanda
  // não tem mais esse toque duplo — só o ícone "Alterar", pedido explícito
  // do usuário 2026-07-21: "retire o link que o leva a tela de alterar
  // comanda, essa tarefa já está no botão").
  const abrirPreVenda = (it: ComandaItem) => {
    if (it.pedido_vinculado) {
      router.push({ pathname: "/pedido-form", params: { pedido: String(it.pedido_vinculado) } } as never);
    } else if (it.os_vinculada) {
      router.push({ pathname: "/os-form", params: { os: String(it.os_vinculada) } } as never);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Gestor de Comandas." testID="gestor-comandas-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="gestor-comandas-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Gestor de Comandas</Text>
        <View style={styles.headerActions}>
          <IconButtonWithTooltip
            icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
            size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="gestor-comandas-ajuda"
          />
          {canImprimir ? (
            <IconButtonWithTooltip
              icon="print-outline" label="Imprimir relatório" onPress={imprimir}
              size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="gestor-comandas-imprimir"
            />
          ) : null}
          {canExportar ? (
            <Pressable onPress={exportarExcel} style={styles.saveBtn} hitSlop={8} testID="gestor-comandas-exportar">
              <Ionicons name="download-outline" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Excel</Text>
            </Pressable>
          ) : null}
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <AccordionSection title="Buscar e Filtrar" testID="gestor-comandas-filtros">
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Data de</Text>
                <WebDateField
                  value={dataIni}
                  onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                  testID="gestor-comandas-data-ini"
                  onSubmitEditing={() => {
                    document.querySelector<HTMLInputElement>('[data-testid="gestor-comandas-data-fim"]')?.focus();
                  }}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Data até</Text>
                <WebDateField value={dataFim} onChange={setDataFim} testID="gestor-comandas-data-fim" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Comanda</Text>
                <TextInput value={comandaNum} onChangeText={(v) => setComandaNum(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-comandas-comanda" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Cliente (código, CGC/CPF ou nome)</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <TextInput
                    value={clienteTermo} onChangeText={setClienteTermo}
                    style={[styles.input, { flex: 1, minWidth: 0 }]} testID="gestor-comandas-cliente"
                  />
                  <IconButtonWithTooltip
                    icon="search-outline" label="Buscar Cliente" onPress={clienteSearch.openModal}
                    size={20} color={colors.brandPrimary} testID="gestor-comandas-cliente-buscar"
                  />
                </View>
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Cupom</Text>
                <TextInput value={cupom} onChangeText={(v) => setCupom(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-comandas-cupom" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>NFCe</Text>
                <TextInput value={nfce} onChangeText={(v) => setNfce(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-comandas-nfce" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>NF</Text>
                <TextInput value={nf} onChangeText={(v) => setNf(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-comandas-nf" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Valor de</Text>
                <TextInput value={valorDe} onChangeText={setValorDe} style={styles.input} keyboardType="decimal-pad" testID="gestor-comandas-valor-de" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Valor até</Text>
                <TextInput value={valorAte} onChangeText={setValorAte} style={styles.input} keyboardType="decimal-pad" testID="gestor-comandas-valor-ate" />
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Pressable onPress={() => setComNota((v) => !v)} style={styles.checkRow} testID="gestor-comandas-com-nota">
                  <Ionicons name={comNota ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Com Nota/NFCe</Text>
                </Pressable>
              </View>
              <View style={styles.colNarrow}>
                <Pressable onPress={() => setSemNota((v) => !v)} style={styles.checkRow} testID="gestor-comandas-sem-nota">
                  <Ionicons name={semNota ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Sem Nota/NFCe</Text>
                </Pressable>
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Ordenar por</Text>
                <View style={styles.pillRow}>
                  <Pressable onPress={() => setOrdenarPor("venda")} style={[styles.pillBtn, ordenarPor === "venda" && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, ordenarPor === "venda" && styles.pillBtnTextSel]}>Venda</Text>
                  </Pressable>
                  <Pressable onPress={() => setOrdenarPor("cliente")} style={[styles.pillBtn, ordenarPor === "cliente" && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, ordenarPor === "cliente" && styles.pillBtnTextSel]}>Cliente</Text>
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.modalActionsRow}>
              <Pressable onPress={buscar} disabled={loading} style={styles.primaryBtn} testID="gestor-comandas-buscar">
                {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Consultar</Text>}
              </Pressable>
            </View>
            </AccordionSection>
          </View>

          <View style={styles.totaisCard} testID="gestor-comandas-totais">
            <Text style={styles.totaisTitle}>Totais ({itens.length} comanda{itens.length === 1 ? "" : "s"})</Text>
            <View style={styles.totaisGrid}>
              <View style={styles.totItem}><Text style={styles.totLbl}>Total Geral</Text><Text style={styles.totVal}>{formatBRL(resumo.total_geral)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>ECF</Text><Text style={styles.totVal}>{formatBRL(resumo.total_ecf)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>NFCe</Text><Text style={styles.totVal}>{formatBRL(resumo.total_nfce)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>NF</Text><Text style={styles.totVal}>{formatBRL(resumo.total_nf)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>Sem Documento</Text><Text style={styles.totVal}>{formatBRL(resumo.total_sem_documento)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>Sem Pagamento Lançado</Text><Text style={[styles.totVal, resumo.total_sem_pagamento > 0 && { color: colors.error }]}>{formatBRL(resumo.total_sem_pagamento)}</Text></View>
            </View>
            {resumo.por_forma_pagamento.length > 0 ? (
              <>
                <Text style={[styles.totaisTitle, { fontSize: 12, marginTop: spacing.sm }]}>Por Forma de Pagamento</Text>
                <View style={styles.totaisGrid}>
                  {resumo.por_forma_pagamento.map((fp) => (
                    <View key={fp.tipo} style={styles.totItem}><Text style={styles.totLbl}>{fp.label}</Text><Text style={styles.totVal}>{formatBRL(fp.valor)}</Text></View>
                  ))}
                </View>
              </>
            ) : null}
          </View>

          <View style={styles.card}>
            {loading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : itens.length === 0 ? (
              <Text style={styles.hint}>Nenhuma comanda encontrada para os filtros selecionados.</Text>
            ) : (
              itens.map((it, idx) => (
                // zIndex decrescente por linha — sem isso, o tooltip de um
                // ícone perto do fim de uma linha escapa (`top:"100%"`) por
                // trás da PRÓXIMA linha da lista (elevar só o wrapper do
                // próprio ícone, já feito em `IconButtonWithTooltip`, só
                // resolve o ícone vizinho na MESMA linha). Ver CLAUDE.md >
                // "Modo Didático" > regra de tooltip sempre por cima.
                <View key={it.comanda} style={[styles.itemRow, { zIndex: itens.length - idx }]} testID={`gestor-comandas-item-${it.comanda}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>
                      CMD #{it.comanda}
                      {" · "}{brDate(it.data)} · {it.cliente_nome} · <Text style={{ fontWeight: "700" }}>{formatBRL(it.valor)}</Text>
                    </Text>
                    <Text style={styles.hint}>
                      {it.situacao_label}
                      {it.num_cupom ? ` · Cupom ${it.num_cupom}` : ""}
                      {it.num_nfce ? ` · NFCe ${it.num_nfce}` : ""}
                      {it.num_nf ? ` · NF ${it.num_nf}` : ""}
                      {it.atendente_nome ? ` · Atendente ${it.atendente_nome}` : ""}
                      {it.pedido_vinculado || it.os_vinculada ? (
                        <Text> · Pré-Venda: <Text
                          onPress={() => abrirPreVenda(it)}
                          style={styles.colComandaLink}
                          testID={`gestor-comandas-col-prevenda-${it.comanda}`}
                        >
                          {it.pedido_vinculado ? `Pedido #${it.pedido_vinculado}` : `O.S. #${it.os_vinculada}`}
                        </Text></Text>
                      ) : null}
                    </Text>
                  </View>
                  <View style={styles.itemActions}>
                    {canImprimir && (it.num_cupom || it.num_nfce || it.num_nf) ? (
                      <IconButtonWithTooltip
                        icon="print-outline" label="Reimprimir documento fiscal" onPress={() => reimprimirDocFiscal(it)}
                        style={styles.itemActionBtn} testID={`gestor-comandas-reimprimir-${it.comanda}`}
                      />
                    ) : null}
                    {it.pedido_vinculado ? (
                      <IconButtonWithTooltip
                        icon="receipt-outline" label="Abrir Pedido de origem"
                        onPress={() => router.push({ pathname: "/pedido-form", params: { pedido: String(it.pedido_vinculado) } } as never)}
                        style={styles.itemActionBtn} testID={`gestor-comandas-abrir-pedido-${it.comanda}`}
                      />
                    ) : null}
                    {it.os_vinculada ? (
                      <IconButtonWithTooltip
                        icon="construct-outline" label="Abrir O.S. de origem"
                        onPress={() => router.push({ pathname: "/os-form", params: { os: String(it.os_vinculada) } } as never)}
                        style={styles.itemActionBtn} testID={`gestor-comandas-abrir-os-${it.comanda}`}
                      />
                    ) : null}
                    {canAlterar ? (
                      <IconButtonWithTooltip
                        icon="create-outline" label="Alterar comanda"
                        onPress={() => router.push({ pathname: "/alterar-comanda", params: { comanda: String(it.comanda) } } as never)}
                        style={styles.itemActionBtn} testID={`gestor-comandas-alterar-${it.comanda}`}
                      />
                    ) : null}
                  </View>
                </View>
              ))
            )}
          </View>
        </View>
      </ScrollView>

      <AjudaPedidoModal
        visible={ajudaVisivel}
        onClose={() => setAjudaVisivel(false)}
        titulo="Gestor de Comandas"
        itens={GESTOR_COMANDAS_AJUDA_ITENS}
      />

      <ClientSearchModal
        visible={clienteSearch.open}
        onClose={clienteSearch.closeModal}
        term={clienteSearch.term}
        setTerm={clienteSearch.setTerm}
        loading={clienteSearch.loading}
        results={clienteSearch.results}
        onPick={(c) => { setClienteTermo(c.nome); clienteSearch.closeModal(); }}
        onCreate={clienteSearch.closeModal}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  // zIndex alto — cabeçalho sempre por cima do conteúdo rolável (mesmo
  // achado de `alterar-comanda.tsx`, ver comentário lá).
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm, zIndex: 100 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 170 },
  colTiny: { width: 100 },

  checkRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 11 },
  checkLabel: { fontSize: 13, color: colors.onSurface },

  pillRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },

  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  totaisCard: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, paddingVertical: spacing.md },
  totaisTitle: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginBottom: spacing.sm },
  totaisGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  totItem: { minWidth: 130 },
  totLbl: { fontSize: 11, color: colors.muted },
  totVal: { fontSize: 15, fontWeight: "700", color: colors.onSurface },

  itemRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowText: { fontSize: 13, color: colors.onSurface },
  itemActions: { flexDirection: "row", alignItems: "center", gap: 4 },
  itemActionBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },
  colComandaLink: { color: colors.brandPrimary, fontWeight: "700", textDecorationLine: "underline" },
});
