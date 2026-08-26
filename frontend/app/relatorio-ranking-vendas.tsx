// Ranking de Vendas — migração de Geral\FrmRkgCliPro.frm (Painel de
// Relatórios > Vendas). Top-N por Cliente, Produto ou Vendedor. Sub-
// feature "Compras" do legado não portada (ver PENDENCIAS.md > "Painel
// de Relatórios (VB6)" > "Grupo Vendas").
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportRankingVendasPdf, RankingVendasPayload } from "@/src/utils/export-ranking-vendas";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type RankingPor = "cliente" | "produto" | "vendedor";

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

export default function RelatorioRankingVendasScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [rankingPor, setRankingPor] = useState<RankingPor>("produto");
  const [ordenarPor, setOrdenarPor] = useState<"qtd" | "valor">("valor");
  const [topN, setTopN] = useState("10");
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [considerarServicos, setConsiderarServicos] = useState(true);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<RankingVendasPayload | null>(null);
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
      const base = cc.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
      try {
        const r = await fetch(`${base}/api/funcionarios?${qs}`);
        const j = await r.json();
        const arr = Array.isArray(j) ? j : j?.items || [];
        setVendedorOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
          value: String(f.codigo), label: (f.nome || "").trim() || `#${f.codigo}`,
        })));
      } catch {
        // sem lista
      }
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/ranking-vendas?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}` +
        `&ranking_por=${rankingPor}&ordenar_por=${ordenarPor}&top_n=${Number(topN) || 10}` +
        `&considerar_servicos=${considerarServicos ? "true" : "false"}`;
      if (vendedor && rankingPor !== "vendedor") url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Ranking de Vendas",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          rankingPor, ordenarPor,
          itens: j.itens || [],
          totais: j.totais || { qtd: 0, valor: 0, registros: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, rankingPor, ordenarPor, topN, vendedor, considerarServicos, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportRankingVendasPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("ranking-de-vendas", [
      {
        name: "Ranking de Vendas",
        rows: resultado.itens.map((i) => ({ Posição: i.posicao, Nome: i.nome, Qtd: i.qtd, Valor: i.valor })),
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-ranking-vendas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relrk-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Ranking de Vendas</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
          <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="relrk-filtros">
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Inicial</Text>
                {isWeb ? (
                  <WebDateField
                    value={dataIni}
                    onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                    icon="calendar-outline" testID="relrk-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relrk-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relrk-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relrk-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relrk-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Ranking por</Text>
            <View style={styles.chipRow}>
              {([{ k: "produto" as const, l: "Produto/Serviço" }, { k: "cliente" as const, l: "Cliente" }, { k: "vendedor" as const, l: "Vendedor" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setRankingPor(o.k)} style={[styles.chip, rankingPor === o.k && styles.chipSel]} testID={`relrk-por-${o.k}`}>
                  <Text style={[styles.chipText, rankingPor === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Ordenar por</Text>
            <View style={styles.chipRow}>
              {([{ k: "valor" as const, l: "Valor" }, { k: "qtd" as const, l: "Quantidade" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setOrdenarPor(o.k)} style={[styles.chip, ordenarPor === o.k && styles.chipSel]} testID={`relrk-ord-${o.k}`}>
                  <Text style={[styles.chipText, ordenarPor === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.filterGrid}>
              <View style={{ width: 110 }}>
                <Text style={styles.fieldLabel}>Nº de Registros</Text>
                <TextInput value={topN} onChangeText={setTopN} keyboardType="numeric" style={styles.input} testID="relrk-topn" />
              </View>
              {rankingPor !== "vendedor" ? (
                <View style={{ flexGrow: 1, minWidth: 200 }}>
                  <Text style={styles.fieldLabel}>Vendedor (opcional, filtra o ranking)</Text>
                  <SelectField
                    value={vendedor} onChange={setVendedor} options={vendedorOpts}
                    placeholder="Todos" modalTitle="Selecione o vendedor" allowClear compactWeb testID="relrk-vendedor"
                  />
                </View>
              ) : null}
            </View>

            <Pressable onPress={() => setConsiderarServicos((v) => !v)} style={styles.checkRow} testID="relrk-considerar-servicos">
              <Ionicons name={considerarServicos ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Considerar serviços</Text>
            </Pressable>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relrk-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relrk-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relrk-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </AccordionSection>
          </View>

          {resultado ? (
            <View style={styles.card}>
              <Text style={styles.subMeta}>Top {resultado.itens.length} de {resultado.totais.registros} registros</Text>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : resultado.itens.map((i) => (
                <View key={`${i.posicao}-${i.codigo}`} style={styles.row}>
                  <Text style={styles.posicao}>{i.posicao}º</Text>
                  <Text style={styles.rowLabel} numberOfLines={1}>{i.nome}</Text>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.rowValue}>{formatBRL(i.valor)}</Text>
                    <Text style={styles.rowValueSecondary}>Qtd {i.qtd}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Informe o período e clique em Selecionar.</Text>
          ) : null}
        </View>
      </ScrollView>
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
  filterGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, alignItems: "flex-end" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    height: 40, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
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
  subMeta: { fontSize: 11, color: colors.muted, marginBottom: 6 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  posicao: { width: 28, fontSize: 12, fontWeight: "700", color: colors.brandPrimary },
  rowLabel: { fontSize: 12, color: colors.onSurface, flex: 1 },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowValueSecondary: { fontSize: 10, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
