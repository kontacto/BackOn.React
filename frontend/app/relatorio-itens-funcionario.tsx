// Itens por Funcionário — migração de Geral\FrmRelVenFun.frm (Painel de
// Relatórios > Vendas). Toggle Vendedores (Pedido, agrupado por
// pedido_venda.vendedor) / Executores (O.S., agrupado por
// os_produto.executor) — ver PENDENCIAS.md > "Painel de Relatórios
// (VB6)" > "Grupo Vendas" pro rastreio completo.
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
import { exportItensFuncionarioPdf, ItensFuncionarioPayload } from "@/src/utils/export-itens-funcionario";
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

export default function RelatorioItensFuncionarioScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [modo, setModo] = useState<"vendedor" | "executor">("vendedor");
  const [funcOpts, setFuncOpts] = useState<SelectOption[]>([]);
  const [funcionario, setFuncionario] = useState<string | number | null>(null);
  const [considerarServicos, setConsiderarServicos] = useState(true);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ItensFuncionarioPayload | null>(null);
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
        setFuncOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
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
      let url = `${base}/api/relatorios/itens-funcionario?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}&modo=${modo}` +
        `&considerar_servicos=${considerarServicos ? "true" : "false"}`;
      if (funcionario) url += `&funcionario=${encodeURIComponent(String(funcionario))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Itens por Funcionário",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          modo,
          funcionarios: j.funcionarios || [],
          totais: j.totais || { qtd: 0, valor: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, modo, funcionario, considerarServicos, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportItensFuncionarioPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("itens-por-funcionario", [
      {
        name: "Itens por Funcionário",
        rows: [
          ...resultado.funcionarios.map((f) => ({ Funcionário: f.nome, Qtd: f.qtd, Valor: f.valor })),
          { Funcionário: "TOTAL", Qtd: resultado.totais.qtd, Valor: resultado.totais.valor },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-itens-funcionario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relif-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Itens por Funcionário</Text>
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
                    icon="calendar-outline" testID="relif-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relif-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relif-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relif-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relif-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Modo</Text>
            <View style={styles.chipRow}>
              {([{ k: "vendedor" as const, l: "Vendedores (Pedido)" }, { k: "executor" as const, l: "Executores (O.S.)" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setModo(o.k)} style={[styles.chip, modo === o.k && styles.chipSel]} testID={`relif-modo-${o.k}`}>
                  <Text style={[styles.chipText, modo === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <View style={{ maxWidth: 320 }}>
              <Text style={styles.fieldLabel}>Funcionário (opcional)</Text>
              <SelectField
                value={funcionario} onChange={setFuncionario} options={funcOpts}
                placeholder="Todos" modalTitle="Selecione o funcionário" allowClear compactWeb testID="relif-funcionario"
              />
            </View>

            <Pressable onPress={() => setConsiderarServicos((v) => !v)} style={styles.checkRow} testID="relif-considerar-servicos">
              <Ionicons name={considerarServicos ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Considerar serviços</Text>
            </Pressable>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relif-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relif-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relif-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              {resultado.funcionarios.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : resultado.funcionarios.map((f, idx) => (
                <View key={`${f.codigo}-${idx}`} style={styles.row}>
                  <Text style={styles.rowLabel} numberOfLines={1}>{f.nome}</Text>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.rowValue}>{formatBRL(f.valor)}</Text>
                    <Text style={styles.rowValueSecondary}>Qtd {f.qtd}</Text>
                  </View>
                </View>
              ))}
              {resultado.funcionarios.length > 0 ? (
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
  row: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface, flex: 1 },
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
