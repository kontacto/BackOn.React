// Movimentação de Itens — migração de FrmRelMovCli.frm (Painel de
// Relatórios > Estoque). Ledger universal (Vendas/Requisição/
// Inventário/Manual) no período — ver PENDENCIAS.md > "Painel de
// Relatórios (VB6)" > "Estoque" pro achado completo (movimentacao já é
// escrito por praticamente todo módulo desta migração).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
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
import { exportMovimentacaoItensPdf, MovimentacaoItensPayload } from "@/src/utils/export-movimentacao-itens";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

const ORIGENS = [
  { key: "CM", label: "Venda" },
  { key: "RQ", label: "Requisição" },
  { key: "IV", label: "Inventário" },
  { key: "MV", label: "Manual" },
];

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

export default function RelatorioMovimentacaoItensScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [produto, setProduto] = useState("");
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipo, setTipo] = useState<string | number | null>(null);
  const [entradaSaida, setEntradaSaida] = useState<"" | "E" | "S">("");
  const [origens, setOrigens] = useState<string[]>([]);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<MovimentacaoItensPayload | null>(null);
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
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  const toggleOrigem = (key: string) => {
    setOrigens((prev) => (prev.includes(key) ? prev.filter((o) => o !== key) : [...prev, key]));
  };

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/movimentacao-itens?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (produto.trim()) url += `&produto=${encodeURIComponent(produto.trim())}`;
      if (tipo !== null) url += `&tipo=${encodeURIComponent(String(tipo))}`;
      if (entradaSaida) url += `&entrada_saida=${entradaSaida}`;
      if (origens.length) url += `&origem=${origens.join(",")}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Movimentação de Itens",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
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
  }, [conn, dataIni, dataFim, produto, tipo, entradaSaida, origens, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportMovimentacaoItensPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("movimentacao-de-itens", [
      {
        name: "Movimentação de Itens",
        rows: [
          ...resultado.itens.map((i) => ({
            Data: i.data, Tipo: i.tipo_desc, Origem: i.origem_label, Produto: i.produto_descricao,
            Qtd: i.qtd, "Vlr. Unit": i.p_unit, Valor: i.valor, "NF/Doc": i.num_nf, Responsável: i.vendedor_nome,
          })),
          { Data: "TOTAL", Qtd: resultado.totais.qtd, Valor: resultado.totais.valor },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-movimentacao-itens-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relmi-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Movimentação de Itens</Text>
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
                    onChange={(v) => {
                      setDataIni(v || null);
                      if (v) setDataFim(v);
                    }}
                    icon="calendar-outline"
                    testID="relmi-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relmi-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relmi-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relmi-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relmi-data-fim" />
                )}
              </View>
            </View>

            <View style={styles.filterGrid}>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Produto (código exato, opcional)</Text>
                <TextInput value={produto} onChangeText={setProduto} placeholderTextColor={colors.muted} style={styles.input} testID="relmi-produto" />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Tipo (opcional)</Text>
                <SelectField value={tipo} onChange={setTipo} options={tipoOpts} placeholder="Todos" modalTitle="Selecione o tipo" allowClear compactWeb testID="relmi-tipo" />
              </View>
            </View>

            <Text style={styles.fieldLabel}>Entrada/Saída</Text>
            <View style={styles.chipRow}>
              {([{ k: "" as const, l: "Todos" }, { k: "E" as const, l: "Entradas" }, { k: "S" as const, l: "Saídas" }]).map((o) => (
                <Pressable key={o.k || "all"} onPress={() => setEntradaSaida(o.k)} style={[styles.chip, entradaSaida === o.k && styles.chipSel]} testID={`relmi-es-${o.k || "todos"}`}>
                  <Text style={[styles.chipText, entradaSaida === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Origem (opcional, múltipla escolha)</Text>
            <View style={styles.chipRow}>
              {ORIGENS.map((o) => {
                const sel = origens.includes(o.key);
                return (
                  <Pressable key={o.key} onPress={() => toggleOrigem(o.key)} style={[styles.chip, sel && styles.chipSel]} testID={`relmi-origem-${o.key}`}>
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
                testID="relmi-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relmi-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relmi-planilha">
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
                <Text style={styles.empty}>Nenhuma movimentação no período.</Text>
              ) : resultado.itens.map((i, idx) => (
                <View key={idx} style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowLabel} numberOfLines={1}>{i.produto_descricao}</Text>
                    <Text style={styles.rowMeta}>
                      {brDate(i.data)} · {i.tipo_desc} · {i.origem_label}{i.num_nf ? ` · Doc #${i.num_nf}` : ""} · {i.vendedor_nome}
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
  filterGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  filterCol: { flexGrow: 1, flexBasis: 180, minWidth: 160 },
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
  rowMeta: { fontSize: 10, color: colors.muted, marginTop: 2 },
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
