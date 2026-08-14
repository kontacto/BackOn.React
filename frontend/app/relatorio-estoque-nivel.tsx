// Estoque por Nível — migração de FrmRelFecEst.frm (Painel de
// Relatórios > Estoque). Unidades em estoque + valor a custo/venda,
// agrupado por nível (breadcrumb completo, [GLOBAL]). Snapshot atual.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { buildNivelBreadcrumb } from "@/src/utils/nivelTree";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportEstoqueNivelPdf, EstoqueNivelPayload } from "@/src/utils/export-estoque-nivel";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function RelatorioEstoqueNivelScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [niveisLista, setNiveisLista] = useState<{ codigo: string; descricao: string }[]>([]);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<EstoqueNivelPayload | null>(null);
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
      try {
        const r = await fetch(`${base}/api/relatorios/margem-lucro/niveis?servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`);
        const j = await r.json();
        if (j?.success) setNiveisLista(j.niveis || []);
      } catch {
        // sem lista
      }
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/relatorios/estoque-nivel?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        const itens = (j.itens || []).map((n: { codigo: string; unidades: number; valor_custo: number; valor_venda: number }) => ({
          ...n,
          label: n.codigo ? buildNivelBreadcrumb(niveisLista, n.codigo) || n.codigo : "Sem Classificação",
        }));
        itens.sort((a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label, "pt-BR"));
        setResultado({ titulo: "Estoque por Nível", itens, totais: j.totais || { unidades: 0, valor_custo: 0, valor_venda: 0 }, empresa });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, niveisLista, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportEstoqueNivelPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("estoque-por-nivel", [
      {
        name: "Estoque por Nível",
        rows: [
          ...resultado.itens.map((i) => ({ Nível: i.label, Unidades: i.unidades, "Valor Custo": i.valor_custo, "Valor Venda": i.valor_venda })),
          { Nível: "TOTAL", Unidades: resultado.totais.unidades, "Valor Custo": resultado.totais.valor_custo, "Valor Venda": resultado.totais.valor_venda },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-estoque-nivel-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relen-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Estoque por Nível</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.helperText}>Snapshot do estoque atual, sem filtro de período.</Text>
            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relen-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relen-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relen-planilha">
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
                <Text style={[styles.th, { flex: 2 }]}>Nível</Text>
                <Text style={[styles.th, styles.thNum]}>Unidades</Text>
                <Text style={[styles.th, styles.thNum]}>Valor Custo</Text>
                <Text style={[styles.th, styles.thNum]}>Valor Venda</Text>
              </View>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Sem estoque.</Text>
              ) : resultado.itens.map((i, idx) => (
                <View key={`${i.codigo}-${idx}`} style={styles.row}>
                  <Text style={[styles.rowLabel, { flex: 2 }]} numberOfLines={2}>{i.label}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{i.unidades}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.valor_custo)}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.valor_venda)}</Text>
                </View>
              ))}
              <View style={styles.rowTotal}>
                <Text style={[styles.rowTotalLabel, { flex: 2 }]}>TOTAL</Text>
                <Text style={[styles.rowTotalValue, styles.thNum]}>{resultado.totais.unidades}</Text>
                <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.valor_custo)}</Text>
                <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.valor_venda)}</Text>
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
  helperText: { fontSize: 12, color: colors.muted },
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
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowTotal: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8, marginTop: 4,
    borderTopWidth: 2, borderTopColor: colors.brandPrimary,
  },
  rowTotalLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, textAlign: "right" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
