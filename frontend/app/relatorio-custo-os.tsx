// Custo de O.S — migração de FrmCustoOS.frm (Painel de Relatórios > Pré
// Venda). Custo (custo_os*quant) agrupado por Cliente ou por Produto/
// Serviço no período, filtro opcional por Tipo (destino do item —
// Cliente/Garantia/Interno/Revisão de Fábrica, tabela tipo_os_prod).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportCustoOsPdf, CustoOsPayload } from "@/src/utils/export-custo-os";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Agrupamento = "cliente" | "produto";

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

export default function RelatorioCustoOsScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [agrupamento, setAgrupamento] = useState<Agrupamento>("cliente");
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipo, setTipo] = useState<string | number | null>(null);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<CustoOsPayload | null>(null);
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
        const r = await fetch(`${base}/api/tabelas/tipo-os-prod?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setTipoOpts((j.items || []).map((t: { codigo: number; descricao: string }) => ({
            value: t.codigo, label: t.descricao,
          })));
        }
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
      let url = `${base}/api/relatorios/custo-os?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}&agrupar_por=${agrupamento}`;
      if (tipo !== null && tipo !== undefined) url += `&tipo=${encodeURIComponent(String(tipo))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Custo de O.S",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          agrupamento,
          itens: j.itens || [],
          total: j.total || 0,
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, agrupamento, tipo, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportCustoOsPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    const colLabel = agrupamento === "produto" ? "Produto/Serviço" : "Cliente";
    exportSheetsToXlsx("custo-de-os", [
      {
        name: "Custo de O.S",
        rows: [
          ...resultado.itens.map((i) => ({ [colLabel]: i.label, "Qtd.": i.qtd, Custo: i.custo })),
          { [colLabel]: "TOTAL", Custo: resultado.total },
        ],
      },
    ]);
  }, [resultado, agrupamento]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-custo-os-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relcos-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Custo de O.S</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Agrupar por</Text>
            <View style={styles.chipRow}>
              {([
                { key: "cliente" as const, label: "Cliente" },
                { key: "produto" as const, label: "Produto/Serviço" },
              ]).map((o) => {
                const sel = agrupamento === o.key;
                return (
                  <Pressable
                    key={o.key}
                    onPress={() => setAgrupamento(o.key)}
                    style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.8 }]}
                    testID={`relcos-agrupar-${o.key}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{o.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Inicial</Text>
                {isWeb ? (
                  <WebDateField
                    value={dataIni}
                    onChange={(v) => {
                      setDataIni(v || null);
                      if (v) setDataFim(v);
                    }}
                    icon="calendar-outline"
                    testID="relcos-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relcos-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relcos-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relcos-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relcos-data-fim" />
                )}
              </View>
            </View>

            <View style={{ maxWidth: 320 }}>
              <Text style={styles.fieldLabel}>Tipo (destino do item — opcional)</Text>
              <SelectField
                value={tipo} onChange={setTipo} options={tipoOpts}
                placeholder="Todos" modalTitle="Selecione o tipo" allowClear compactWeb testID="relcos-tipo"
              />
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relcos-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relcos-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relcos-planilha">
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
                <Text style={[styles.th, { flex: 2 }]}>{agrupamento === "produto" ? "Produto/Serviço" : "Cliente"}</Text>
                <Text style={[styles.th, styles.thNum]}>Qtd.</Text>
                <Text style={[styles.th, styles.thNum]}>Custo</Text>
              </View>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : resultado.itens.map((i, idx) => (
                <View key={idx} style={styles.row}>
                  <Text style={[styles.rowLabel, { flex: 2 }]} numberOfLines={2}>{i.label}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{i.qtd}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.custo)}</Text>
                </View>
              ))}
              <View style={styles.rowTotal}>
                <Text style={[styles.rowTotalLabel, { flex: 2 }]}>TOTAL</Text>
                <View style={styles.thNum} />
                <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.total)}</Text>
              </View>
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
  dateRow: { flexDirection: "row", gap: spacing.sm },
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
