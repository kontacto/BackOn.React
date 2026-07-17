// Fechamento de Caixa (Comandas) — migrado de frmFechaCaixa.frm.
//
// Correção de arquitetura importante em relação ao legado (ver docstring
// de backend/services/fechamento_caixa_service.py): o form original lê
// comanda_dinheiro/comanda_cheque/etc. Este app grava a forma de
// pagamento em pedido_venda_dinheiro/pedido_venda_cheque/etc. (feature
// "Forma de Pagamento" já migrada) — o backend agrega essas tabelas via
// COMANDA_PED/comanda_os, não as tabelas comanda_*.
//
// Simplificações conscientes: sem "Empresas" (Filial/multi-banco — este
// app usa uma conexão por vez), sem "Impressora não fiscal" (um único
// layout de impressão agora), sem Troco/Gorjeta/Vale Devolução (nenhuma
// tela migrada grava essas tabelas ainda). Ver PENDENCIAS.md > "Fechamento
// de Caixa" pro detalhe completo.
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
import { exportFechamentoCaixaPdf, FechamentoCaixaPayload } from "@/src/utils/export-fechamento-caixa";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import SimpleBarChart, { BarChartDatum } from "@/src/components/SimpleBarChart";
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
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : (iso || "—");
}

export default function RelatorioCaixaScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [atendenteOpts, setAtendenteOpts] = useState<SelectOption[]>([]);
  const [atendente, setAtendente] = useState<string | number | null>(null);
  const [areaOpts, setAreaOpts] = useState<SelectOption[]>([]);
  const [area, setArea] = useState<string | number | null>(null);
  const [filtrarAtendenteDav, setFiltrarAtendenteDav] = useState(false);
  const [exibirGarantias, setExibirGarantias] = useState(false);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<FechamentoCaixaPayload | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);
  const [chartModo, setChartModo] = useState<"forma" | "tipo">("forma");

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
        setAtendenteOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
          value: String(f.codigo), label: (f.nome || "").trim() || `#${f.codigo}`,
        })));
      } catch {
        // sem lista
      }
      try {
        const r = await fetch(`${base}/api/area-atuacao?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setAreaOpts((j.items || []).map((a: { codigo: number; descricao: string }) => ({
            value: a.codigo, label: a.descricao,
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
      let url = `${base}/api/relatorios/caixa?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}` +
        `&filtrar_atendente_dav=${filtrarAtendenteDav ? "true" : "false"}` +
        `&exibir_garantias=${exibirGarantias ? "true" : "false"}`;
      if (atendente) url += `&atendente=${encodeURIComponent(String(atendente))}`;
      if (area) url += `&area=${encodeURIComponent(String(area))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          periodo: dataIni === dataFim ? `Dia ${brDate(dataIni)}` : `${brDate(dataIni)} a ${brDate(dataFim)}`,
          empresa,
          formas_pagamento: j.formas_pagamento || [],
          subtotal_formas_pagamento: j.subtotal_formas_pagamento || 0,
          entradas: j.entradas || [],
          total_entradas: j.total_entradas || 0,
          saidas: j.saidas || [],
          total_saidas: j.total_saidas || 0,
          despesas_com_comprovante: j.despesas_com_comprovante || 0,
          despesas_sem_comprovante: j.despesas_sem_comprovante || 0,
          total_caixa: j.total_caixa || 0,
          resumo_tipo: j.resumo_tipo || [],
          total_recebimentos: j.total_recebimentos || 0,
          pedidos_sem_forma_pagamento: j.pedidos_sem_forma_pagamento || [],
          total_sem_forma_pagamento: j.total_sem_forma_pagamento || 0,
        });
      }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, atendente, area, filtrarAtendenteDav, exibirGarantias, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportFechamentoCaixaPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("fechamento-de-caixa", [
      {
        name: "Entradas e Saídas",
        rows: [
          ...resultado.formas_pagamento.map((f) => ({
            "Forma de Pagamento": (f.nao_totaliza_caixa ? "(*) " : "") + f.descricao, Valor: f.valor,
          })),
          { "Forma de Pagamento": "SUB TOTAL", Valor: resultado.subtotal_formas_pagamento },
          ...resultado.entradas.map((e) => ({ "Forma de Pagamento": `Entrada de Caixa: ${e.descricao}`, Valor: e.valor })),
          ...resultado.saidas.map((s) => ({ "Forma de Pagamento": `Saída de Caixa: ${s.descricao}`, Valor: s.valor })),
          { "Forma de Pagamento": "Despesas com comprovante", Valor: resultado.despesas_com_comprovante },
          { "Forma de Pagamento": "Despesas sem comprovante", Valor: resultado.despesas_sem_comprovante },
          { "Forma de Pagamento": "TOTAL CAIXA", Valor: resultado.total_caixa },
        ],
      },
      {
        name: "Resumo por Tipo",
        rows: [
          ...resultado.resumo_tipo.map((r) => ({ Tipo: `${r.tipo} ${r.label}`, Valor: r.valor, "%": r.percentual })),
          { Tipo: "T O T A L", Valor: resultado.total_recebimentos, "%": 100 },
        ],
      },
      ...(resultado.pedidos_sem_forma_pagamento.length > 0
        ? [{
            name: "Sem Forma de Pagamento",
            rows: [
              ...resultado.pedidos_sem_forma_pagamento.map((s) => ({ Pedido: s.pedido, Valor: s.valor })),
              { Pedido: "Total", Valor: resultado.total_sem_forma_pagamento },
            ],
          }]
        : []),
    ]);
  }, [resultado]);

  const chartData: BarChartDatum[] = useMemo(() => {
    if (!resultado) return [];
    if (chartModo === "forma") {
      return resultado.formas_pagamento.map((f) => ({
        label: (f.nao_totaliza_caixa ? "(*) " : "") + f.descricao, value: f.valor,
      }));
    }
    return resultado.resumo_tipo.map((r) => ({ label: `${r.tipo} ${r.label}`, value: r.valor }));
  }, [resultado, chartModo]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-caixa-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relcx-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Fechamento de Caixa</Text>
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
                    testID="relcx-data-ini"
                    onSubmitEditing={() => {
                      if (dataIni) setDataFim(dataIni);
                      document.querySelector<HTMLInputElement>('[data-testid="relcx-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relcx-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relcx-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relcx-data-fim" />
                )}
              </View>
            </View>
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Atendente (opcional)</Text>
                <SelectField
                  value={atendente}
                  onChange={setAtendente}
                  options={atendenteOpts}
                  placeholder="Todos"
                  modalTitle="Selecione o atendente"
                  allowClear
                  testID="relcx-atendente"
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Área de Atuação (opcional)</Text>
                <SelectField
                  value={area}
                  onChange={setArea}
                  options={areaOpts}
                  placeholder="Todas"
                  modalTitle="Selecione a área de atuação"
                  allowClear
                  testID="relcx-area"
                />
              </View>
            </View>
            <View style={styles.checkGroupRow}>
              <TouchableOpacity
                onPress={() => setFiltrarAtendenteDav((v) => !v)}
                style={styles.checkRow}
                testID="relcx-filtrar-atendente-dav"
              >
                <Ionicons name={filtrarAtendenteDav ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Filtrar pelo atendente da comanda</Text>
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => setExibirGarantias((v) => !v)}
                style={styles.checkRow}
                testID="relcx-exibir-garantias"
              >
                <Ionicons name={exibirGarantias ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Exibir Garantias</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relcx-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relcx-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relcx-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado && resultado.pedidos_sem_forma_pagamento.length > 0 ? (
            <View style={styles.warningCard} testID="relcx-alerta-sem-forma">
              <View style={styles.warningHeaderRow}>
                <Ionicons name="warning-outline" size={18} color={colors.warning} />
                <Text style={styles.warningTitle}>
                  Faturados sem forma de pagamento lançada (não entram no Total Caixa)
                </Text>
              </View>
              {resultado.pedidos_sem_forma_pagamento.map((s) => (
                <View key={s.pedido} style={styles.row}>
                  <Text style={styles.rowLabel}>Pedido #{s.pedido}</Text>
                  <Text style={styles.rowValue}>{formatBRL(s.valor)}</Text>
                </View>
              ))}
              <View style={styles.rowTotal}>
                <Text style={styles.rowTotalLabel}>Total</Text>
                <Text style={styles.rowTotalValue}>{formatBRL(resultado.total_sem_forma_pagamento)}</Text>
              </View>
            </View>
          ) : null}

          {resultado ? (
            <View style={styles.resultsGrid}>
              <View style={styles.card}>
                <Text style={styles.cardTitle}>Entradas e Saídas</Text>
                {resultado.formas_pagamento.map((f) => (
                  <View key={f.descricao} style={styles.row}>
                    <Text style={styles.rowLabel} numberOfLines={1}>
                      {f.nao_totaliza_caixa ? "(*) " : ""}{f.descricao}
                    </Text>
                    <Text style={styles.rowValue}>{formatBRL(f.valor)}</Text>
                  </View>
                ))}
                <View style={styles.rowTotal}>
                  <Text style={styles.rowTotalLabel}>SUB TOTAL</Text>
                  <Text style={styles.rowTotalValue}>{formatBRL(resultado.subtotal_formas_pagamento)}</Text>
                </View>
                {resultado.entradas.map((e) => (
                  <View key={`e-${e.descricao}`} style={styles.row}>
                    <Text style={styles.rowLabel} numberOfLines={1}>Entrada de Caixa: {e.descricao}</Text>
                    <Text style={styles.rowValue}>{formatBRL(e.valor)}</Text>
                  </View>
                ))}
                {resultado.total_entradas ? (
                  <View style={styles.rowTotal}>
                    <Text style={styles.rowTotalLabel}>Total de Entradas</Text>
                    <Text style={styles.rowTotalValue}>{formatBRL(resultado.total_entradas)}</Text>
                  </View>
                ) : null}
                {resultado.despesas_com_comprovante ? (
                  <View style={styles.row}>
                    <Text style={styles.rowLabel}>Despesas com comprovante</Text>
                    <Text style={styles.rowValue}>{formatBRL(resultado.despesas_com_comprovante)}</Text>
                  </View>
                ) : null}
                {resultado.despesas_sem_comprovante ? (
                  <View style={styles.row}>
                    <Text style={styles.rowLabel}>Despesas sem comprovante</Text>
                    <Text style={styles.rowValue}>{formatBRL(resultado.despesas_sem_comprovante)}</Text>
                  </View>
                ) : null}
                {resultado.saidas.map((s) => (
                  <View key={`s-${s.descricao}`} style={styles.row}>
                    <Text style={styles.rowLabel} numberOfLines={1}>Saída de Caixa: {s.descricao}</Text>
                    <Text style={styles.rowValue}>{formatBRL(s.valor)}</Text>
                  </View>
                ))}
                {resultado.total_saidas ? (
                  <View style={styles.rowTotal}>
                    <Text style={styles.rowTotalLabel}>Total de Saídas</Text>
                    <Text style={styles.rowTotalValue}>{formatBRL(resultado.total_saidas)}</Text>
                  </View>
                ) : null}
                <View style={[styles.rowTotal, styles.rowGrandTotal]}>
                  <Text style={styles.rowTotalLabel}>TOTAL CAIXA</Text>
                  <Text style={styles.rowTotalValue}>{formatBRL(resultado.total_caixa)}</Text>
                </View>
                {resultado.formas_pagamento.some((f) => f.nao_totaliza_caixa) ? (
                  <Text style={styles.footnote}>
                    (*) As formas de pagamento com este símbolo foram configuradas pra não somarem no total do caixa.
                  </Text>
                ) : null}
              </View>

              <View style={styles.card}>
                <Text style={styles.cardTitle}>Resumo</Text>
                {resultado.resumo_tipo.map((r) => (
                  <View key={r.tipo} style={styles.row}>
                    <Text style={styles.rowLabel} numberOfLines={1}>{r.tipo} {r.label}</Text>
                    <Text style={styles.rowValue}>{formatBRL(r.valor)}</Text>
                    <Text style={styles.rowPct}>{r.percentual.toFixed(2).replace(".", ",")}%</Text>
                  </View>
                ))}
                <View style={styles.rowTotal}>
                  <Text style={styles.rowTotalLabel}>T O T A L</Text>
                  <Text style={styles.rowTotalValue}>{formatBRL(resultado.total_recebimentos)}</Text>
                </View>
              </View>
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Informe o período e clique em Selecionar.</Text>
          ) : null}

          {resultado ? (
            <View style={styles.card}>
              <View style={styles.chartHeaderRow}>
                <Text style={styles.cardTitle}>Gráfico</Text>
                <View style={styles.chartToggle}>
                  <TouchableOpacity
                    onPress={() => setChartModo("forma")}
                    style={[styles.chartToggleBtn, chartModo === "forma" && styles.chartToggleBtnActive]}
                    testID="relcx-chart-forma"
                  >
                    <Text style={[styles.chartToggleText, chartModo === "forma" && styles.chartToggleTextActive]}>
                      Forma de Pagamento
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => setChartModo("tipo")}
                    style={[styles.chartToggleBtn, chartModo === "tipo" && styles.chartToggleBtnActive]}
                    testID="relcx-chart-tipo"
                  >
                    <Text style={[styles.chartToggleText, chartModo === "tipo" && styles.chartToggleTextActive]}>
                      Tipo de Pagamento
                    </Text>
                  </TouchableOpacity>
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
  resultsGrid: { flexDirection: Platform.OS === "web" ? "row" : "column", flexWrap: "wrap", gap: spacing.md },
  warningCard: {
    backgroundColor: "#fff8e1", borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.warning, padding: spacing.md, marginBottom: spacing.md,
  },
  warningHeaderRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm },
  warningTitle: { flex: 1, fontSize: 12, fontWeight: "700", color: "#8a6100" },
  card: {
    flex: Platform.OS === "web" ? 1 : undefined,
    minWidth: 280,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  cardTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.sm, textTransform: "uppercase", letterSpacing: 0.4 },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 4, gap: spacing.sm },
  rowLabel: { flex: 1, fontSize: 12, color: colors.onSurface },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowPct: { fontSize: 11, color: colors.muted, width: 56, textAlign: "right" },
  rowTotal: {
    flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, marginTop: 4,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  rowGrandTotal: { borderTopWidth: 2, borderTopColor: colors.brandPrimary, marginTop: spacing.xs },
  rowTotalLabel: { fontSize: 12, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  footnote: { fontSize: 10, color: colors.muted, marginTop: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
  chartHeaderRow: {
    flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between",
    gap: spacing.sm, marginBottom: spacing.md,
  },
  chartToggle: { flexDirection: "row", gap: 6 },
  chartToggleBtn: {
    height: 30, paddingHorizontal: spacing.md, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center",
  },
  chartToggleBtnActive: { backgroundColor: colors.brandPrimary },
  chartToggleText: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  chartToggleTextActive: { color: colors.onBrandPrimary },
});
