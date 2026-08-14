// Movimentações por Nível — migração de frmrelvenlojas.frm (Painel de
// Relatórios > Estoque). Soma qtd/valor por nível, pra um tipo de
// movimentação escolhido, no período. Ver PENDENCIAS.md > "Painel de
// Relatórios (VB6)" > "Estoque" — caption interna do form legado
// ("Transferência para as Filiais") é artefato de copiar-colar, não
// reflete a query real.
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
import { exportMovimentacaoNivelPdf, MovimentacaoNivelPayload } from "@/src/utils/export-movimentacao-nivel";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

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
function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function RelatorioMovimentacaoNivelScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [niveisLista, setNiveisLista] = useState<{ codigo: string; descricao: string }[]>([]);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipo, setTipo] = useState<string | number | null>(null);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<MovimentacaoNivelPayload | null>(null);
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
        const r = await fetch(`${base}/api/tabelas/tipo-mov?servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`);
        const j = await r.json();
        if (j?.success) {
          setTipoOpts((j.items || []).map((t: { codigo: string; descricao: string }) => ({ value: t.codigo, label: `${t.codigo} — ${t.descricao}` })));
        }
      } catch {
        // sem lista
      }
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
    if (!tipo) { feedback.showWarning("Selecione o tipo de movimentação."); return; }
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/relatorios/movimentacao-nivel?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&tipo=${encodeURIComponent(String(tipo))}&data_ini=${dataIni}&data_fim=${dataFim}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        const itens = (j.itens || []).map((n: { codigo: string; qtd: number; valor: number }) => ({
          ...n,
          label: n.codigo ? buildNivelBreadcrumb(niveisLista, n.codigo) || n.codigo : "Sem Classificação",
        }));
        itens.sort((a: { label: string }, b: { label: string }) => a.label.localeCompare(b.label, "pt-BR"));
        const tipoOpt = tipoOpts.find((o) => String(o.value) === String(tipo));
        setResultado({
          titulo: "Movimentações por Nível",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          tipoLabel: tipoOpt?.label || String(tipo),
          itens,
          totais: j.totais || { qtd: 0, valor: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, tipo, dataIni, dataFim, niveisLista, tipoOpts, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportMovimentacaoNivelPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("movimentacoes-por-nivel", [
      {
        name: "Movimentações por Nível",
        rows: [
          ...resultado.itens.map((i) => ({ Nível: i.label, Qtd: i.qtd, Valor: i.valor })),
          { Nível: "TOTAL", Qtd: resultado.totais.qtd, Valor: resultado.totais.valor },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-movimentacao-nivel-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relmn-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Movimentações por Nível</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Tipo de Movimentação</Text>
            <SelectField value={tipo} onChange={setTipo} options={tipoOpts} placeholder="Selecione…" modalTitle="Selecione o tipo" compactWeb testID="relmn-tipo" />

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
                    testID="relmn-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relmn-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relmn-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relmn-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relmn-data-fim" />
                )}
              </View>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relmn-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relmn-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relmn-planilha">
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
                <Text style={[styles.th, styles.thNum]}>Qtd</Text>
                <Text style={[styles.th, styles.thNum]}>Valor</Text>
              </View>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhuma movimentação no período.</Text>
              ) : resultado.itens.map((i, idx) => (
                <View key={`${i.codigo}-${idx}`} style={styles.row}>
                  <Text style={[styles.rowLabel, { flex: 2 }]} numberOfLines={2}>{i.label}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{i.qtd}</Text>
                  <Text style={[styles.rowValue, styles.thNum]}>{formatBRL(i.valor)}</Text>
                </View>
              ))}
              <View style={styles.rowTotal}>
                <Text style={[styles.rowTotalLabel, { flex: 2 }]}>TOTAL</Text>
                <Text style={[styles.rowTotalValue, styles.thNum]}>{resultado.totais.qtd}</Text>
                <Text style={[styles.rowTotalValue, styles.thNum]}>{formatBRL(resultado.totais.valor)}</Text>
              </View>
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Selecione o tipo e o período, e clique em Selecionar.</Text>
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
  headerTitle: { flex: 1, textAlign: "center", fontSize: 15, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
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
