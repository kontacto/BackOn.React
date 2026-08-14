// Venda por Região/Segmento — migração de Guerengases\FrmVenTot.frm
// (Painel de Relatórios > Vendas). Agrupamento configurável por até 4
// dimensões (Região/Segmento/Rota/Vendedor) — sem o query-builder
// dinâmico do legado (ver docstring do service).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportVendaRegiaoPdf, VendaRegiaoPayload, DIM_LABEL } from "@/src/utils/export-venda-regiao";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
const DIMS = ["regiao", "segmento", "rota", "vendedor"] as const;

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

export default function RelatorioVendaRegiaoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [dimensoes, setDimensoes] = useState<string[]>(["regiao"]);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<VendaRegiaoPayload | null>(null);
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

  const toggleDim = (d: string) => {
    setDimensoes((prev) => (prev.includes(d) ? prev.filter((x) => x !== d) : [...prev, d]));
  };

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/relatorios/venda-regiao?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}&dimensoes=${dimensoes.join(",")}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Venda por Região/Segmento",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          dimensoes: j.dimensoes || [],
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
  }, [conn, dataIni, dataFim, dimensoes, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportVendaRegiaoPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("venda-por-regiao-segmento", [
      {
        name: "Venda por Região/Segmento",
        rows: resultado.itens.map((i) => {
          const row: Record<string, string | number> = {};
          for (const d of resultado.dimensoes) row[DIM_LABEL[d] || d] = String(i[d] ?? "");
          row.Qtd = i.qtd; row.Valor = i.valor;
          return row;
        }),
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-venda-regiao-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relvr-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Venda por Região/Segmento</Text>
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
                    icon="calendar-outline" testID="relvr-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relvr-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relvr-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relvr-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relvr-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Agrupar por (múltipla escolha, ordem fixa)</Text>
            <View style={styles.chipRow}>
              {DIMS.map((d) => {
                const sel = dimensoes.includes(d);
                return (
                  <Pressable key={d} onPress={() => toggleDim(d)} style={[styles.chip, sel && styles.chipSel]} testID={`relvr-dim-${d}`}>
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{DIM_LABEL[d]}</Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relvr-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relvr-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relvr-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : resultado.itens.map((i, idx) => (
                <View key={idx} style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowLabel} numberOfLines={1}>
                      {resultado.dimensoes.length
                        ? resultado.dimensoes.map((d) => String(i[d] ?? "")).join(" · ")
                        : "Total Geral"}
                    </Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.rowValue}>{formatBRL(i.valor)}</Text>
                    <Text style={styles.rowValueSecondary}>Qtd {i.qtd}</Text>
                  </View>
                </View>
              ))}
              {resultado.itens.length > 0 ? (
                <View style={styles.rowTotal}>
                  <Text style={styles.rowTotalLabel}>TOTAL</Text>
                  <Text style={styles.rowTotalValue}>{formatBRL(resultado.totais.valor)} · Qtd {resultado.totais.qtd}</Text>
                </View>
              ) : null}
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
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
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
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
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
