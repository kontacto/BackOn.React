// Caixa Analítico — migrado de FrmTotCaixa.frm. Quebra os recebimentos
// (via pedido_venda_*/os_*, mesma correção de arquitetura do Fechamento de
// Caixa — ver backend/services/caixa_analitico_service.py) + entradas/
// saídas por período (dia, dia da semana, semana, mês, trimestre,
// semestre, ano), com uma linha de TOTAIS.
//
// Mesma formatação de campos/botões da tela de Fechamento de Caixa
// (relatorio-caixa.tsx) — pedido explícito do usuário: WebDateField com
// Enter copiando pra Data Final, checkboxes lado a lado, botão Selecionar
// + Imprimir/Gerar Planilha do mesmo tamanho, resultado em cards com o
// mesmo `WEB_FILTER_CARD`.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TouchableOpacity, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportCaixaAnaliticoPdf, CaixaAnaliticoLinha, CaixaAnaliticoPayload } from "@/src/utils/export-caixa-analitico";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import SimpleBarChart, { BarChartDatum } from "@/src/components/SimpleBarChart";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

const AGRUPAMENTO_OPTS: SelectOption[] = [
  { value: "diario", label: "Diário" },
  { value: "dia_semana", label: "Dia da Semana" },
  { value: "semanal", label: "Semanal" },
  { value: "mensal", label: "Mensal" },
  { value: "trimestral", label: "Trimestral" },
  { value: "semestral", label: "Semestral" },
  { value: "anual", label: "Anual" },
];
const DIAS_SEMANA = ["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"];

type NumCol = Exclude<keyof CaixaAnaliticoLinha, "label">;
const COLS: { key: NumCol; label: string }[] = [
  { key: "total_caixa", label: "Total Caixa" },
  { key: "total_recebidos", label: "Total Recebidos" },
  { key: "total_entradas", label: "Total Entradas" },
  { key: "total_saidas", label: "Total Saídas" },
  { key: "dinheiro", label: "Dinheiro" },
  { key: "cheque", label: "Cheque" },
  { key: "credito", label: "Crédito" },
  { key: "debito", label: "Débito" },
  { key: "vale", label: "Vale" },
  { key: "ticket", label: "Ticket" },
  { key: "duplicata", label: "Duplicata" },
  { key: "financiado", label: "Financiado" },
];
const CHART_METRICAS: { key: NumCol; label: string }[] = [
  { key: "total_caixa", label: "Total Caixa" },
  { key: "total_recebidos", label: "Recebidos" },
  { key: "total_entradas", label: "Entradas" },
  { key: "total_saidas", label: "Saídas" },
];

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : (iso || "—");
}
function emptyLinha(): CaixaAnaliticoLinha {
  return {
    label: "TOTAIS", total_caixa: 0, total_recebidos: 0, total_entradas: 0, total_saidas: 0,
    dinheiro: 0, cheque: 0, credito: 0, debito: 0, vale: 0, ticket: 0, duplicata: 0, financiado: 0,
  };
}

export default function RelatorioCaixaAnaliticoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [agrupamento, setAgrupamento] = useState<string | number | null>("diario");
  const [diasSemana, setDiasSemana] = useState<boolean[]>([true, true, true, true, true, true, true]);

  const [loading, setLoading] = useState(false);
  const [linhas, setLinhas] = useState<CaixaAnaliticoLinha[]>([]);
  const [totais, setTotais] = useState<CaixaAnaliticoLinha | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);
  const [chartMetrica, setChartMetrica] = useState<NumCol>("total_caixa");

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

  const toggleDia = useCallback((idx: number) => {
    setDiasSemana((prev) => prev.map((v, i) => (i === idx ? !v : v)));
  }, []);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const diasQs = diasSemana.map((v, i) => (v ? i : null)).filter((v) => v !== null).join(",");
      const url = `${base}/api/relatorios/caixa-analitico?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}` +
        `&agrupamento=${agrupamento}&dias_semana=${encodeURIComponent(diasQs)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setLinhas([]); setTotais(null); }
      else {
        setLinhas(j.linhas || []);
        setTotais(j.totais || emptyLinha());
      }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, agrupamento, diasSemana, feedback]);

  const agrupamentoLabel = useMemo(
    () => AGRUPAMENTO_OPTS.find((o) => o.value === agrupamento)?.label || "",
    [agrupamento]
  );
  const periodo = dataIni === dataFim ? `Dia ${brDate(dataIni)}` : `${brDate(dataIni)} a ${brDate(dataFim)}`;

  const imprimir = useCallback(async () => {
    if (!totais) return;
    const payload: CaixaAnaliticoPayload = { periodo, agrupamentoLabel, empresa, linhas, totais };
    try {
      await exportCaixaAnaliticoPdf(payload);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [totais, periodo, agrupamentoLabel, empresa, linhas, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!totais) return;
    exportSheetsToXlsx("caixa-analitico", [
      {
        name: "Caixa Analítico",
        rows: [
          ...linhas.map((l) => ({
            Data: l.label,
            "Total Caixa": l.total_caixa, "Total Recebidos": l.total_recebidos,
            "Total Entradas": l.total_entradas, "Total Saídas": l.total_saidas,
            Dinheiro: l.dinheiro, Cheque: l.cheque, Crédito: l.credito, Débito: l.debito,
            Vale: l.vale, Ticket: l.ticket, Duplicata: l.duplicata, Financiado: l.financiado,
          })),
          {
            Data: "TOTAIS",
            "Total Caixa": totais.total_caixa, "Total Recebidos": totais.total_recebidos,
            "Total Entradas": totais.total_entradas, "Total Saídas": totais.total_saidas,
            Dinheiro: totais.dinheiro, Cheque: totais.cheque, Crédito: totais.credito, Débito: totais.debito,
            Vale: totais.vale, Ticket: totais.ticket, Duplicata: totais.duplicata, Financiado: totais.financiado,
          },
        ],
      },
    ]);
  }, [linhas, totais]);

  const chartData: BarChartDatum[] = useMemo(
    () => linhas.map((l) => ({ label: l.label, value: l[chartMetrica] as number })),
    [linhas, chartMetrica]
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relcxa-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relcxa-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Caixa Analítico</Text>
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
                    onChange={(v) => setDataIni(v || null)}
                    icon="calendar-outline"
                    testID="relcxa-data-ini"
                    onSubmitEditing={() => {
                      if (dataIni) setDataFim(dataIni);
                      document.querySelector<HTMLInputElement>('[data-testid="relcxa-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relcxa-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relcxa-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relcxa-data-fim" />
                )}
              </View>
            </View>

            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Agrupamento</Text>
                <SelectField
                  value={agrupamento}
                  onChange={setAgrupamento}
                  options={AGRUPAMENTO_OPTS}
                  modalTitle="Selecione o agrupamento"
                  testID="relcxa-agrupamento"
                />
              </View>
            </View>

            {agrupamento === "diario" ? (
              <View style={styles.checkGroupRow}>
                {DIAS_SEMANA.map((label, idx) => (
                  <TouchableOpacity
                    key={label}
                    onPress={() => toggleDia(idx)}
                    style={styles.checkRow}
                    testID={`relcxa-dia-${idx}`}
                  >
                    <Ionicons name={diasSemana[idx] ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.checkLabel}>{label}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            ) : null}

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relcxa-selecionar"
              >
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>

              {totais ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relcxa-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relcxa-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {totais ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>{agrupamentoLabel} · {periodo}</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={isWeb}>
                <View>
                  <View style={styles.gridHeaderRow}>
                    <Text style={[styles.gridCell, styles.gridHeadText, styles.gridLabelCol]}>Data</Text>
                    {COLS.map((c) => (
                      <Text key={c.key} style={[styles.gridCell, styles.gridHeadText, styles.gridNumCol]}>{c.label}</Text>
                    ))}
                  </View>
                  {linhas.length === 0 ? (
                    <Text style={styles.empty}>Nenhum lançamento no período.</Text>
                  ) : (
                    linhas.map((l, idx) => (
                      <View key={`${l.label}-${idx}`} style={styles.gridRow}>
                        <Text style={[styles.gridCell, styles.gridLabelCol]} numberOfLines={1}>{l.label}</Text>
                        {COLS.map((c) => (
                          <Text key={c.key} style={[styles.gridCell, styles.gridNumCol, styles.gridNumText]}>
                            {formatBRL(l[c.key] as number)}
                          </Text>
                        ))}
                      </View>
                    ))
                  )}
                  <View style={styles.gridTotalRow}>
                    <Text style={[styles.gridCell, styles.gridLabelCol, styles.gridTotalText]}>TOTAIS</Text>
                    {COLS.map((c) => (
                      <Text key={c.key} style={[styles.gridCell, styles.gridNumCol, styles.gridTotalText]}>
                        {formatBRL(totais[c.key] as number)}
                      </Text>
                    ))}
                  </View>
                </View>
              </ScrollView>
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Informe o período e clique em Selecionar.</Text>
          ) : null}

          {totais && linhas.length > 0 ? (
            <View style={styles.card}>
              <View style={styles.chartHeaderRow}>
                <Text style={styles.cardTitle}>Gráfico</Text>
                <View style={styles.chartToggle}>
                  {CHART_METRICAS.map((m) => (
                    <TouchableOpacity
                      key={m.key}
                      onPress={() => setChartMetrica(m.key)}
                      style={[styles.chartToggleBtn, chartMetrica === m.key && styles.chartToggleBtnActive]}
                      testID={`relcxa-chart-${m.key}`}
                    >
                      <Text style={[styles.chartToggleText, chartMetrica === m.key && styles.chartToggleTextActive]}>
                        {m.label}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
              <SimpleBarChart data={chartData} formatValue={formatBRL} emptyMessage="Sem lançamentos no período." />
            </View>
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
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  checkGroupRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg, marginTop: 4 },
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
  cardTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.sm, textTransform: "uppercase", letterSpacing: 0.4 },
  gridHeaderRow: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: 6 },
  gridRow: { flexDirection: "row", paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridTotalRow: { flexDirection: "row", paddingVertical: 6, marginTop: 2, borderTopWidth: 2, borderTopColor: colors.brandPrimary },
  gridCell: { fontSize: 11, color: colors.onSurface, paddingHorizontal: 6 },
  gridHeadText: { fontWeight: "700", color: colors.muted, textTransform: "uppercase", fontSize: 10 },
  gridLabelCol: { width: 130 },
  gridNumCol: { width: 100, textAlign: "right" },
  gridNumText: { fontWeight: "500" },
  gridTotalText: { fontWeight: "700", color: colors.brandPrimary },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24, marginBottom: 12 },
  chartHeaderRow: {
    flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between",
    gap: spacing.sm, marginBottom: spacing.md,
  },
  chartToggle: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chartToggleBtn: {
    height: 30, paddingHorizontal: spacing.md, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center",
  },
  chartToggleBtnActive: { backgroundColor: colors.brandPrimary },
  chartToggleText: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  chartToggleTextActive: { color: colors.onBrandPrimary },
});
