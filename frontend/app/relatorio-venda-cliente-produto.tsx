// Venda por Cliente/Produto — unificação de Geral\FrmRelVenCli.frm +
// Geral\FrmRelVenPro.frm (Painel de Relatórios > Vendas), a pedido do
// usuário (AskUserQuestion, 2026-08-07): uma tela só com toggle de
// agrupamento Cliente↔Produto em vez de 2 telas quase idênticas.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import ProdutoSearchModal, { ProdutoRow } from "@/src/components/ProdutoSearchModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportVendaClienteProdutoPdf, VendaClienteProdutoPayload, VendaClienteProdutoRow } from "@/src/utils/export-venda-cliente-produto";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function firstDayOfMonthISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : (iso || "—");
}

type Grupo = { chave: string; label: string; itens: VendaClienteProdutoRow[]; qtd: number; valor: number };

export default function RelatorioVendaClienteProdutoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [agruparPor, setAgruparPor] = useState<"cliente" | "produto">("cliente");
  const [produto, setProduto] = useState<ProdutoRow | null>(null);

  const [prodOpen, setProdOpen] = useState(false);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoRow[]>([]);
  const [prodLoading, setProdLoading] = useState(false);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<VendaClienteProdutoPayload | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  useEffect(() => {
    if (!prodOpen || !conn) return;
    const t = prodTerm.trim();
    if (t.length < 2) { setProdResults([]); return; }
    setProdLoading(true);
    const timer = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(t)}&tipo=all&page=1&size=30`;
        const r = await fetch(`${base}/api/produtos-servicos?${qs}`);
        const j = await r.json();
        setProdResults(j?.success ? (j.items || []) : []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 350);
    return () => clearTimeout(timer);
  }, [prodOpen, prodTerm, conn]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/venda-cliente-produto?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (produto) url += `&produto=${encodeURIComponent(produto.codigo)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Venda por Cliente/Produto",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          agruparPor,
          itens: j.itens || [],
          totais: j.totais || { qtd: 0, valor: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, produto, agruparPor, empresa, feedback]);

  const grupos: Grupo[] = useMemo(() => {
    if (!resultado) return [];
    const porChave = new Map<string, Grupo>();
    for (const item of resultado.itens) {
      const chave = agruparPor === "cliente" ? String(item.cliente_codigo ?? "") : item.item_codigo;
      const label = agruparPor === "cliente" ? item.cliente_nome : item.item_descricao;
      let g = porChave.get(chave);
      if (!g) { g = { chave, label, itens: [], qtd: 0, valor: 0 }; porChave.set(chave, g); }
      g.itens.push(item);
      g.qtd += item.qtd;
      g.valor += item.valor;
    }
    return Array.from(porChave.values()).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
  }, [resultado, agruparPor]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportVendaClienteProdutoPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("venda-por-cliente-produto", [
      {
        name: "Venda por Cliente-Produto",
        rows: [
          ...resultado.itens.map((i) => ({
            Data: i.data, Documento: `${i.doc_tipo} #${i.doc_numero ?? ""}`, Cliente: i.cliente_nome,
            "Produto/Serviço": i.item_descricao, Qtd: i.qtd, Valor: i.valor,
          })),
          { Data: "TOTAL", Qtd: resultado.totais.qtd, Valor: resultado.totais.valor },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-venda-cliente-produto-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relvcp-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Venda por Cliente/Produto</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Inicial</Text>
                {isWeb ? (
                  <WebDateField
                    value={dataIni}
                    onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                    icon="calendar-outline" testID="relvcp-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relvcp-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relvcp-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relvcp-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relvcp-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Agrupar por</Text>
            <View style={styles.chipRow}>
              {([{ k: "cliente" as const, l: "Cliente" }, { k: "produto" as const, l: "Produto/Serviço" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setAgruparPor(o.k)} style={[styles.chip, agruparPor === o.k && styles.chipSel]} testID={`relvcp-agrupar-${o.k}`}>
                  <Text style={[styles.chipText, agruparPor === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Produto específico (opcional)</Text>
            <Pressable onPress={() => setProdOpen(true)} style={styles.searchField} testID="relvcp-produto-abrir">
              <Ionicons name="search" size={15} color={colors.muted} />
              <Text style={styles.searchFieldText} numberOfLines={1}>
                {produto ? `${produto.codigo} — ${produto.descricao}` : "Todos os produtos/serviços"}
              </Text>
              {produto ? (
                <Pressable onPress={() => setProduto(null)} hitSlop={8} testID="relvcp-produto-limpar">
                  <Ionicons name="close-circle" size={16} color={colors.muted} />
                </Pressable>
              ) : null}
            </Pressable>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relvcp-selecionar"
              >
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>

              {resultado ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relvcp-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relvcp-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              {grupos.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : grupos.map((g) => (
                <View key={g.chave} style={styles.grupo}>
                  <View style={styles.grupoHeader}>
                    <Text style={styles.grupoLabel} numberOfLines={1}>{g.label}</Text>
                    <Text style={styles.grupoValor}>{formatBRL(g.valor)} · Qtd {g.qtd}</Text>
                  </View>
                  {g.itens.map((it, idx) => (
                    <View key={idx} style={styles.row}>
                      <Text style={styles.rowLabel} numberOfLines={1}>
                        {agruparPor === "cliente" ? it.item_descricao : it.cliente_nome}
                      </Text>
                      <Text style={styles.rowMeta}>{brDate(it.data)} · {it.doc_tipo} #{it.doc_numero ?? "—"}</Text>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.rowValue}>{formatBRL(it.valor)}</Text>
                        <Text style={styles.rowValueSecondary}>Qtd {it.qtd}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              ))}
              {grupos.length > 0 ? (
                <View style={styles.rowTotal}>
                  <Text style={styles.rowTotalLabel}>TOTAL GERAL</Text>
                  <Text style={styles.rowTotalValue}>{formatBRL(resultado.totais.valor)} · Qtd {resultado.totais.qtd}</Text>
                </View>
              ) : null}
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Informe o período e clique em Selecionar.</Text>
          ) : null}
        </View>
      </ScrollView>

      <ProdutoSearchModal
        visible={prodOpen} onClose={() => setProdOpen(false)}
        term={prodTerm} setTerm={setProdTerm} loading={prodLoading} results={prodResults}
        onPick={(p) => { setProduto(p); setProdOpen(false); }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 16, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  searchField: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, height: 40,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.md,
    backgroundColor: colors.surface,
  },
  searchFieldText: { flex: 1, fontSize: 13, color: colors.onSurface },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  actionBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  actionBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  grupo: { marginBottom: spacing.sm },
  grupoHeader: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: colors.brandPrimary,
  },
  grupoLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface, flex: 1 },
  grupoValor: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface, flex: 1 },
  rowMeta: { fontSize: 10, color: colors.muted, width: 110 },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowValueSecondary: { fontSize: 10, color: colors.muted, marginTop: 2 },
  rowTotal: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 8, marginTop: 4,
    borderTopWidth: 2, borderTopColor: colors.brandPrimary,
  },
  rowTotalLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
