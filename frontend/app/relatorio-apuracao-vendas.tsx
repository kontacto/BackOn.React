// Apuração de Vendas - DRE — migração de FrmRelAPV.frm (Painel de
// Relatórios > Caixa). Fase 1: grid mensal (Contratos, Produtos O.S.,
// Serviços O.S., Venda Produtos, Venda Serviços, Total, Custo, Margem),
// filtros Vendedor/Região/Segmento/Rota/Tipo Cliente. Ver PENDENCIAS.md >
// "Painel de Relatórios (VB6)" > "Apuração Vendas - DRE" pro que ainda
// falta (Despesas, Por Nível, Preço Médio, impressão detalhada — Fases
// 2/3) e pras simplificações conscientes desta fase (sem "Incluir Vendas
// de Garantia", agrupamento sempre mensal).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportApuracaoVendasPdf, ApuracaoVendasPayload, mesAnoLabel } from "@/src/utils/export-apuracao-vendas";
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

export default function RelatorioApuracaoVendasScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [regiaoOpts, setRegiaoOpts] = useState<SelectOption[]>([]);
  const [regiao, setRegiao] = useState<string | number | null>(null);
  const [segmentoOpts, setSegmentoOpts] = useState<SelectOption[]>([]);
  const [segmento, setSegmento] = useState<string | number | null>(null);
  const [rotaOpts, setRotaOpts] = useState<SelectOption[]>([]);
  const [rota, setRota] = useState<string | number | null>(null);
  const [tipoClienteOpts, setTipoClienteOpts] = useState<SelectOption[]>([]);
  const [tipoCliente, setTipoCliente] = useState<string | number | null>(null);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ApuracaoVendasPayload | null>(null);
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
      const loadOpts = async (path: string, setOpts: (o: SelectOption[]) => void) => {
        try {
          const r = await fetch(`${base}/api/${path}?${qs}`);
          const j = await r.json();
          if (j?.success) {
            setOpts((j.items || []).map((it: { codigo: string | number; descricao: string }) => ({
              value: it.codigo, label: it.descricao,
            })));
          }
        } catch {
          // sem lista
        }
      };
      await Promise.all([
        loadOpts("regioes", setRegiaoOpts),
        loadOpts("segmentos", setSegmentoOpts),
        loadOpts("rotas", setRotaOpts),
        loadOpts("tipo-cliente", setTipoClienteOpts),
      ]);
      try {
        const r = await fetch(`${base}/api/funcionarios?${qs}`);
        const j = await r.json();
        const arr = Array.isArray(j) ? j : j?.items || [];
        setVendedorOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
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
      let url = `${base}/api/relatorios/apuracao-vendas?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (vendedor) url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      if (regiao) url += `&regiao=${encodeURIComponent(String(regiao))}`;
      if (segmento) url += `&segmento=${encodeURIComponent(String(segmento))}`;
      if (rota) url += `&rota=${encodeURIComponent(String(rota))}`;
      if (tipoCliente) url += `&tipo_cliente=${encodeURIComponent(String(tipoCliente))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Apuração de Vendas - DRE",
          periodo: `${brDate(dataIni)} a ${brDate(dataFim)}`,
          meses: j.meses || [],
          totais: j.totais || { total: 0, custo: 0, margem: 0, margem_pct: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, regiao, segmento, rota, tipoCliente, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportApuracaoVendasPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("apuracao-de-vendas-dre", [
      {
        name: "Apuração de Vendas",
        rows: [
          ...resultado.meses.map((m) => ({
            "Mês/Ano": mesAnoLabel(m.ano, m.mes),
            Contratos: m.contratos, "Produtos O.S.": m.produtos_os, "Serviços O.S.": m.servicos_os,
            "Venda Produtos": m.venda_produtos, "Venda Serviços": m.venda_servicos,
            Total: m.total, Custo: m.custo, Margem: m.margem, "Margem %": m.margem_pct,
          })),
          {
            "Mês/Ano": "TOTAL GERAL", Total: resultado.totais.total, Custo: resultado.totais.custo,
            Margem: resultado.totais.margem, "Margem %": resultado.totais.margem_pct,
          },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-apuracao-vendas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relapv-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Apuração de Vendas - DRE</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
          <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="relapv-filtros">
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
                    testID="relapv-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relapv-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relapv-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relapv-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relapv-data-fim" />
                )}
              </View>
            </View>

            <View style={styles.filterGrid}>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Vendedor</Text>
                <SelectField
                  value={vendedor} onChange={setVendedor} options={vendedorOpts}
                  placeholder="Todos" modalTitle="Selecione o vendedor" allowClear compactWeb testID="relapv-vendedor"
                />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Região</Text>
                <SelectField
                  value={regiao} onChange={setRegiao} options={regiaoOpts}
                  placeholder="Todas" modalTitle="Selecione a região" allowClear compactWeb testID="relapv-regiao"
                />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Segmento</Text>
                <SelectField
                  value={segmento} onChange={setSegmento} options={segmentoOpts}
                  placeholder="Todos" modalTitle="Selecione o segmento" allowClear compactWeb testID="relapv-segmento"
                />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Rota</Text>
                <SelectField
                  value={rota} onChange={setRota} options={rotaOpts}
                  placeholder="Todas" modalTitle="Selecione a rota" allowClear compactWeb testID="relapv-rota"
                />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Tipo Cliente</Text>
                <SelectField
                  value={tipoCliente} onChange={setTipoCliente} options={tipoClienteOpts}
                  placeholder="Todos" modalTitle="Selecione o tipo de cliente" allowClear compactWeb testID="relapv-tipo-cliente"
                />
              </View>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relapv-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relapv-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relapv-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </AccordionSection>
          </View>

          {resultado ? (
            <View style={styles.card}>
              <ScrollView horizontal showsHorizontalScrollIndicator={isWeb}>
                <View>
                  <View style={styles.tableHeaderRow}>
                    <Text style={[styles.th, styles.colMes]}>Mês/Ano</Text>
                    <Text style={[styles.th, styles.colNum]}>Contratos</Text>
                    <Text style={[styles.th, styles.colNum]}>Produtos O.S.</Text>
                    <Text style={[styles.th, styles.colNum]}>Serviços O.S.</Text>
                    <Text style={[styles.th, styles.colNum]}>Venda Produtos</Text>
                    <Text style={[styles.th, styles.colNum]}>Venda Serviços</Text>
                    <Text style={[styles.th, styles.colNum]}>Total</Text>
                    <Text style={[styles.th, styles.colNum]}>Custo</Text>
                    <Text style={[styles.th, styles.colNum]}>Margem</Text>
                    <Text style={[styles.th, styles.colNum]}>Margem %</Text>
                  </View>
                  {resultado.meses.length === 0 ? (
                    <Text style={styles.empty}>Nenhum registro no período.</Text>
                  ) : resultado.meses.map((m) => (
                    <View key={`${m.ano}-${m.mes}`} style={styles.row}>
                      <Text style={[styles.rowLabel, styles.colMes]}>{mesAnoLabel(m.ano, m.mes)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.contratos)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.produtos_os)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.servicos_os)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.venda_produtos)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.venda_servicos)}</Text>
                      <Text style={[styles.rowValue, styles.colNum, styles.bold]}>{formatBRL(m.total)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatBRL(m.custo)}</Text>
                      <Text style={[styles.rowValue, styles.colNum, styles.bold]}>{formatBRL(m.margem)}</Text>
                      <Text style={[styles.rowValue, styles.colNum]}>{formatPct(m.margem_pct)}</Text>
                    </View>
                  ))}
                  <View style={styles.rowTotal}>
                    <Text style={[styles.rowTotalLabel, styles.colMes]}>TOTAL GERAL</Text>
                    <View style={{ width: 5 * 110 }} />
                    <Text style={[styles.rowTotalValue, styles.colNum]}>{formatBRL(resultado.totais.total)}</Text>
                    <Text style={[styles.rowTotalValue, styles.colNum]}>{formatBRL(resultado.totais.custo)}</Text>
                    <Text style={[styles.rowTotalValue, styles.colNum]}>{formatBRL(resultado.totais.margem)}</Text>
                    <Text style={[styles.rowTotalValue, styles.colNum]}>{formatPct(resultado.totais.margem_pct)}</Text>
                  </View>
                </View>
              </ScrollView>
              <Text style={styles.footnote}>
                Margem = Total − Custo (sem despesas configuradas — recurso ainda não implementado).
              </Text>
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
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  filterGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 },
  filterCol: { flexGrow: 1, flexBasis: 160, minWidth: 140 },
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
  th: { fontSize: 10, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.3 },
  colMes: { width: 110 },
  colNum: { width: 110, textAlign: "right" },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowValue: { fontSize: 12, color: colors.onSurface },
  bold: { fontWeight: "700" },
  rowTotal: {
    flexDirection: "row", alignItems: "center", paddingVertical: 8, marginTop: 4,
    borderTopWidth: 2, borderTopColor: colors.brandPrimary,
  },
  rowTotalLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, textAlign: "right" },
  footnote: { fontSize: 10, color: colors.muted, marginTop: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
