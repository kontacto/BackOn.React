// Venda por Vendedor × Nível — migração de Kontacto\frmrelvennivfun.frm
// (Painel de Relatórios > Vendas). Toggle Vendedor(Pedido)/Executor(O.S.),
// venda/custo/margem por nível de produto.
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
import { buildNivelBreadcrumb } from "@/src/utils/nivelTree";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportVendaNivelFuncionarioPdf, VendaNivelFuncionarioPayload } from "@/src/utils/export-venda-nivel-funcionario";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function formatPct(v: number): string {
  return `${(v || 0).toFixed(2).replace(".", ",")}%`;
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

export default function RelatorioVendaNivelFuncionarioScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [modo, setModo] = useState<"vendedor" | "executor">("vendedor");
  const [funcOpts, setFuncOpts] = useState<SelectOption[]>([]);
  const [funcionario, setFuncionario] = useState<string | number | null>(null);
  const [niveisLista, setNiveisLista] = useState<{ codigo: string; descricao: string }[]>([]);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<VendaNivelFuncionarioPayload | null>(null);
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
      try {
        const r = await fetch(`${base}/api/relatorios/margem-lucro/niveis?${qs}`);
        const j = await r.json();
        if (j?.success) setNiveisLista(j.niveis || []);
      } catch {
        // sem lista — breadcrumb cai pro código cru
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
      let url = `${base}/api/relatorios/venda-nivel-funcionario?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}&modo=${modo}`;
      if (funcionario) url += `&funcionario=${encodeURIComponent(String(funcionario))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        const niveis = (j.niveis || []).map((n: { codigo: string; venda: number; custo: number; margem: number; margem_pct: number }) => ({
          ...n,
          label: n.codigo ? buildNivelBreadcrumb(niveisLista, n.codigo) || n.codigo : "Sem Classificação",
        }));
        niveis.sort((a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label, "pt-BR"));
        setResultado({
          titulo: "Venda por Vendedor × Nível",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          modo,
          funcNome: j.func_nome || "Todos",
          niveis,
          totais: j.totais || { venda: 0, custo: 0, margem: 0, margem_pct: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, modo, funcionario, niveisLista, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportVendaNivelFuncionarioPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("venda-por-vendedor-nivel", [
      {
        name: "Venda por Vendedor x Nível",
        rows: [
          ...resultado.niveis.map((n) => ({
            Nível: n.label, Venda: n.venda, Custo: n.custo, Margem: n.margem, "Margem %": n.margem_pct,
          })),
          {
            Nível: "TOTAL", Venda: resultado.totais.venda, Custo: resultado.totais.custo,
            Margem: resultado.totais.margem, "Margem %": resultado.totais.margem_pct,
          },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-venda-nivel-funcionario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relvnf-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Venda por Vendedor × Nível</Text>
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
                    icon="calendar-outline" testID="relvnf-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relvnf-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relvnf-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relvnf-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relvnf-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Modo</Text>
            <View style={styles.chipRow}>
              {([{ k: "vendedor" as const, l: "Vendedores (Pedido)" }, { k: "executor" as const, l: "Executores (O.S.)" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setModo(o.k)} style={[styles.chip, modo === o.k && styles.chipSel]} testID={`relvnf-modo-${o.k}`}>
                  <Text style={[styles.chipText, modo === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <View style={{ maxWidth: 320 }}>
              <Text style={styles.fieldLabel}>Funcionário (opcional, senão soma todos)</Text>
              <SelectField
                value={funcionario} onChange={setFuncionario} options={funcOpts}
                placeholder="Todos" modalTitle="Selecione o funcionário" allowClear compactWeb testID="relvnf-funcionario"
              />
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relvnf-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relvnf-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relvnf-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              <Text style={styles.subMeta}>{resultado.funcNome}</Text>
              <View style={styles.tableHeaderRow}>
                <Text style={[styles.th, { flex: 2 }]}>Nível</Text>
                <Text style={[styles.th, styles.thNum]}>Venda</Text>
                <Text style={[styles.th, styles.thNum]}>Custo</Text>
                <Text style={[styles.th, styles.thNum]}>Margem</Text>
                <Text style={[styles.th, styles.thNumSm]}>Margem %</Text>
              </View>
              {resultado.niveis.length === 0 ? (
                <Text style={styles.empty}>Nenhum registro no período.</Text>
              ) : resultado.niveis.map((n, idx) => (
                <View key={`${n.codigo}-${idx}`} style={styles.row}>
                  <Text style={[styles.rowLabel, { flex: 2 }]} numberOfLines={2}>{n.label}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(n.venda)}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(n.custo)}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(n.margem)}</Text>
                  <Text style={[styles.rowValue, styles.thNumSm]}>{formatPct(n.margem_pct)}</Text>
                </View>
              ))}
              {resultado.niveis.length > 0 ? (
                <View style={styles.rowTotal}>
                  <Text style={[styles.rowTotalLabel, { flex: 2 }]}>TOTAL</Text>
                  <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.venda)}</Text>
                  <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.custo)}</Text>
                  <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.margem)}</Text>
                  <Text style={[styles.rowTotalValue, styles.thNumSm]}>{formatPct(resultado.totais.margem_pct)}</Text>
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
  subMeta: { fontSize: 12, color: colors.muted, marginBottom: 8, fontWeight: "600" },
  tableHeaderRow: { flexDirection: "row", paddingBottom: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.border },
  th: { fontSize: 11, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  thNum: { width: 100, textAlign: "right" },
  thNumSm: { width: 70, textAlign: "right" },
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
