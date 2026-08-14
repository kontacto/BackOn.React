// Produtos Reservados — migração de frmrelpecres.frm (Painel de
// Relatórios > Estoque). Snapshot atual (sem período) de produtos com
// reserva ativa (reservado + reservado_os).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportProdutosReservadosPdf, ProdutosReservadosPayload } from "@/src/utils/export-produtos-reservados";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Ordenacao = "codigo_int" | "codigo_fab" | "descricao";

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function RelatorioProdutosReservadosScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [ordenacao, setOrdenacao] = useState<Ordenacao>("codigo_int");
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ProdutosReservadosPayload | null>(null);
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

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/relatorios/produtos-reservados?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&ordenar_por=${ordenacao}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else setResultado({ titulo: "Produtos Reservados", itens: j.itens || [], total: j.total || 0, empresa });
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, ordenacao, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportProdutosReservadosPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("produtos-reservados", [
      {
        name: "Produtos Reservados",
        rows: [
          ...resultado.itens.map((i) => ({
            "Cód. Interno": i.codigo_int, "Cód. Fabricante": i.codigo_fab, Descrição: i.descricao,
            "Preço Venda": i.p_venda, Qtd: i.reserva, "Preço Total": i.preco_total,
          })),
          { "Cód. Interno": "TOTAL", "Preço Total": resultado.total },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-produtos-reservados-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relpr-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Produtos Reservados</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Ordenar por</Text>
            <View style={styles.chipRow}>
              {([
                { key: "codigo_int" as const, label: "Código Interno" },
                { key: "codigo_fab" as const, label: "Código Fabricante" },
                { key: "descricao" as const, label: "Descrição" },
              ]).map((o) => {
                const sel = ordenacao === o.key;
                return (
                  <Pressable
                    key={o.key}
                    onPress={() => setOrdenacao(o.key)}
                    style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.8 }]}
                    testID={`relpr-ord-${o.key}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{o.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relpr-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relpr-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relpr-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              <View style={styles.tableHeaderRow}>
                <Text style={[styles.th, { flex: 2 }]}>Produto</Text>
                <Text style={[styles.th, styles.thNum]}>Preço</Text>
                <Text style={[styles.th, styles.thNumSm]}>Qtd</Text>
                <Text style={[styles.th, styles.thNum]}>Total</Text>
              </View>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum produto reservado.</Text>
              ) : resultado.itens.map((i) => (
                <View key={i.codigo_int} style={styles.row}>
                  <View style={{ flex: 2 }}>
                    <Text style={styles.rowLabel} numberOfLines={1}>{i.descricao}</Text>
                    <Text style={styles.rowCodigo}>{i.codigo_int} · {i.codigo_fab}</Text>
                  </View>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.p_venda)}</Text>
                  <Text style={[styles.rowValue, styles.thNumSm]}>{i.reserva}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.preco_total)}</Text>
                </View>
              ))}
              <View style={styles.rowTotal}>
                <Text style={[styles.rowTotalLabel, { flex: 2 }]}>TOTAL</Text>
                <View style={styles.thNum} />
                <View style={styles.thNumSm} />
                <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.total)}</Text>
              </View>
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Clique em Selecionar.</Text>
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
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
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
  tableHeaderRow: { flexDirection: "row", paddingBottom: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.border },
  th: { fontSize: 11, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  thNum: { width: 100, textAlign: "right" },
  thNumSm: { width: 50, textAlign: "right" },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowCodigo: { fontSize: 10, color: colors.muted, marginTop: 2 },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowTotal: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8, marginTop: 4,
    borderTopWidth: 2, borderTopColor: colors.brandPrimary,
  },
  rowTotalLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, textAlign: "right" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
