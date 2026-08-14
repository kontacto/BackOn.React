// Descontos (Concedidos) — migração de FrmRelDes.frm (Painel de
// Relatórios > Caixa). Documento (Pedido/OS) → itens com desconto, tipo
// Item/Geral e quem concedeu (só disponível pra Pedido nesta migração —
// ver PENDENCIAS.md > "Painel de Relatórios (VB6)" > "Descontos").
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
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
import { exportDescontosConcedidosPdf, DescontosConcedidosPayload } from "@/src/utils/export-descontos-concedidos";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Tipo = "todos" | "pedido" | "os";

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

export default function RelatorioDescontosConcedidosScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [tipo, setTipo] = useState<Tipo>("todos");
  const [clienteFiltro, setClienteFiltro] = useState("");

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<DescontosConcedidosPayload | null>(null);
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
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/descontos-concedidos?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (tipo !== "todos") url += `&tipo=${tipo}`;
      if (clienteFiltro.trim()) url += `&cliente_nome=${encodeURIComponent(clienteFiltro.trim())}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Descontos Concedidos",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          documentos: j.documentos || [],
          totais: j.totais || { bruto: 0, desconto: 0, liquido: 0, desconto_pct: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, tipo, clienteFiltro, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportDescontosConcedidosPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("descontos-concedidos", [
      {
        name: "Descontos Concedidos",
        rows: resultado.documentos.flatMap((d) =>
          d.itens.map((i) => ({
            Documento: `${d.tipo === "PEDIDO" ? "Pedido" : "O.S."} #${d.numero}`,
            Data: d.data, Cliente: d.cliente_nome, Vendedor: d.vendedor_nome,
            Item: i.descricao, Qtd: i.qtd, Bruto: i.valor_bruto, "%": i.percentual,
            Desconto: i.valor_desconto, Líquido: i.valor_liquido,
            Tipo: i.tipo_desconto_label || "—", "Concedido por": i.concedido_por || "—",
          }))
        ),
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-descontos-concedidos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="reldc-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Descontos Concedidos</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Origem</Text>
            <View style={styles.chipRow}>
              {([
                { key: "todos" as const, label: "Todos" },
                { key: "pedido" as const, label: "Pedidos" },
                { key: "os" as const, label: "O.S." },
              ]).map((o) => {
                const sel = tipo === o.key;
                return (
                  <Pressable
                    key={o.key}
                    onPress={() => setTipo(o.key)}
                    style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.8 }]}
                    testID={`reldc-tipo-${o.key}`}
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
                    testID="reldc-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="reldc-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="reldc-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="reldc-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="reldc-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Cliente (nome contém — opcional)</Text>
            <TextInput
              value={clienteFiltro}
              onChangeText={setClienteFiltro}
              placeholder="Ex.: João, Mercado…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="reldc-cliente"
            />

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="reldc-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="reldc-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="reldc-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <>
              <View style={styles.totaisRow}>
                <View style={styles.totCard}>
                  <Text style={styles.totLabel}>Bruto</Text>
                  <Text style={styles.totValue}>{formatBRL(resultado.totais.bruto)}</Text>
                </View>
                <View style={styles.totCard}>
                  <Text style={styles.totLabel}>Desconto</Text>
                  <Text style={[styles.totValue, styles.totValueRed]}>
                    {formatBRL(resultado.totais.desconto)} ({formatPct(resultado.totais.desconto_pct)})
                  </Text>
                </View>
                <View style={styles.totCard}>
                  <Text style={styles.totLabel}>Líquido</Text>
                  <Text style={styles.totValue}>{formatBRL(resultado.totais.liquido)}</Text>
                </View>
              </View>

              {resultado.documentos.length === 0 ? (
                <Text style={styles.empty}>Nenhum desconto concedido no período.</Text>
              ) : resultado.documentos.map((d) => (
                <View key={`${d.tipo}-${d.numero}`} style={styles.card}>
                  <View style={styles.docHead}>
                    <Text style={styles.docTitle}>
                      {d.tipo === "PEDIDO" ? "Pedido" : "O.S."} #{d.numero} — {d.cliente_nome}
                    </Text>
                    <Text style={styles.docSub}>
                      {brDate(d.data)} · Vendedor: {d.vendedor_nome} · Bruto {formatBRL(d.total_bruto)} · Desconto {formatBRL(d.total_desconto)} · Líquido {formatBRL(d.total_liquido)}
                    </Text>
                  </View>
                  {d.itens.map((i, idx) => (
                    <View key={idx} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemDesc} numberOfLines={1}>{i.descricao}</Text>
                        <Text style={styles.itemMeta}>
                          Qtd {i.qtd} · {formatPct(i.percentual)}
                          {i.tipo_desconto_label ? ` · ${i.tipo_desconto_label}` : ""}
                          {i.concedido_por ? ` · por ${i.concedido_por}` : ""}
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={styles.itemDescontoValue}>-{formatBRL(i.valor_desconto)}</Text>
                        <Text style={styles.itemLiquidoValue}>{formatBRL(i.valor_liquido)}</Text>
                      </View>
                    </View>
                  ))}
                </View>
              ))}
            </>
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
  input: {
    height: 40, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
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
  totaisRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  totCard: {
    flexGrow: 1, minWidth: 140, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  totLabel: { fontSize: 10, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  totValue: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  totValueRed: { color: "#c0392b" },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  docHead: { marginBottom: spacing.sm },
  docTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  docSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  itemRow: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, paddingVertical: 6,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  itemDesc: { fontSize: 12, color: colors.onSurface, fontWeight: "500" },
  itemMeta: { fontSize: 11, color: colors.muted, marginTop: 2 },
  itemDescontoValue: { fontSize: 12, fontWeight: "700", color: "#c0392b" },
  itemLiquidoValue: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
