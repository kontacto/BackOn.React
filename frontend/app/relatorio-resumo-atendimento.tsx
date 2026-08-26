// Resumo Atendimento — migração de frmrelos.frm/FrmRelOSs (Painel de
// Relatórios > Pré Venda). Uma linha por O.S. no período: técnico,
// horas, quebra Serviço/Peça e quebra por destino (Cliente Pg./
// Interno-Contrato/Garantia). Ver PENDENCIAS.md > "Painel de Relatórios
// (VB6)" > "Pré Venda" pro rastreio completo (inclusive a adaptação
// os.posicao_os → os.tipo).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { useClienteSearchModal } from "@/src/hooks/useClienteSearchModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportResumoAtendimentoPdf, ResumoAtendimentoPayload } from "@/src/utils/export-resumo-atendimento";
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

export default function RelatorioResumoAtendimentoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [fechadas, setFechadas] = useState(true);
  const [pagas, setPagas] = useState(true);
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipo, setTipo] = useState<string | number | null>(null);
  const [tecnicoOpts, setTecnicoOpts] = useState<SelectOption[]>([]);
  const [tecnico, setTecnico] = useState<string | number | null>(null);
  const [clienteCodigo, setClienteCodigo] = useState("");
  const clienteSearch = useClienteSearchModal(conn);
  const [chassi, setChassi] = useState("");
  const [incluirClientePg, setIncluirClientePg] = useState(true);
  const [incluirContrato, setIncluirContrato] = useState(true);
  const [incluirGarantia, setIncluirGarantia] = useState(true);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<ResumoAtendimentoPayload | null>(null);
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
        const r = await fetch(`${base}/api/tabelas/tipo-os?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setTipoOpts((j.items || []).map((t: { codigo: number; descricao: string }) => ({ value: t.codigo, label: t.descricao })));
        }
      } catch {
        // sem lista
      }
      try {
        const r = await fetch(`${base}/api/funcionarios?${qs}`);
        const j = await r.json();
        const arr = Array.isArray(j) ? j : j?.items || [];
        setTecnicoOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
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
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/resumo-atendimento?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      if (dataIni && dataFim) url += `&data_ini=${dataIni}&data_fim=${dataFim}`;
      const sits = [fechadas ? "F" : null, pagas ? "PG" : null].filter(Boolean);
      if (sits.length) url += `&situacao=${sits.join(",")}`;
      if (tipo !== null) url += `&tipo=${encodeURIComponent(String(tipo))}`;
      if (tecnico !== null) url += `&tecnico=${encodeURIComponent(String(tecnico))}`;
      if (clienteCodigo.trim()) url += `&cliente=${encodeURIComponent(clienteCodigo.trim())}`;
      if (chassi.trim()) url += `&chassi=${encodeURIComponent(chassi.trim())}`;
      url += `&incluir_cliente_pg=${incluirClientePg}&incluir_contrato=${incluirContrato}&incluir_garantia=${incluirGarantia}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else {
        setResultado({
          titulo: "Resumo Atendimento",
          periodo: dataIni && dataFim ? `${brDate(dataIni)} a ${brDate(dataFim)}` : "Todo o período",
          itens: j.itens || [],
          totais: j.totais || { horas: 0, servicos: 0, pecas: 0, contrato: 0, garantia: 0, cliente_pg: 0 },
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, fechadas, pagas, tipo, tecnico, clienteCodigo, chassi, incluirClientePg, incluirContrato, incluirGarantia, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportResumoAtendimentoPdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("resumo-atendimento", [
      {
        name: "Resumo Atendimento",
        rows: [
          ...resultado.itens.map((i) => ({
            Data: i.data_termino, OS: i.os, Técnico: i.tecnico_nome, Início: i.hora_inicio, Fim: i.hora_fim,
            "T.Horas": i.tot_horas, "Serviço(s)": i.tot_servicos, "Peça(s)": i.tot_pecas,
            Contrato: i.tot_contrato, Garantia: i.tot_garantia, "Cliente Pg.": i.tot_cliente_pg,
            Tipo: i.tipo_desc, "Serviço Executado": i.resumo,
          })),
          {
            Data: "TOTAIS", "T.Horas": resultado.totais.horas, "Serviço(s)": resultado.totais.servicos,
            "Peça(s)": resultado.totais.pecas, Contrato: resultado.totais.contrato,
            Garantia: resultado.totais.garantia, "Cliente Pg.": resultado.totais.cliente_pg,
          },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-resumo-atendimento-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relra-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Resumo Atendimento</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
          <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="relra-filtros">
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Término (de)</Text>
                {isWeb ? (
                  <WebDateField
                    value={dataIni}
                    onChange={(v) => {
                      setDataIni(v || null);
                      if (v) setDataFim(v);
                    }}
                    icon="calendar-outline"
                    testID="relra-data-ini"
                    onSubmitEditing={() => {
                      document.querySelector<HTMLInputElement>('[data-testid="relra-data-fim"]')?.focus();
                    }}
                  />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} testID="relra-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Término (até)</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} icon="calendar-outline" testID="relra-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} testID="relra-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Situação da O.S.</Text>
            <View style={styles.chipRow}>
              <Pressable onPress={() => setFechadas((v) => !v)} style={[styles.chip, fechadas && styles.chipSel]} testID="relra-sit-fechadas">
                <Text style={[styles.chipText, fechadas && styles.chipTextSel]}>Fechadas</Text>
              </Pressable>
              <Pressable onPress={() => setPagas((v) => !v)} style={[styles.chip, pagas && styles.chipSel]} testID="relra-sit-pagas">
                <Text style={[styles.chipText, pagas && styles.chipTextSel]}>Pagas</Text>
              </Pressable>
            </View>

            <View style={styles.filterGrid}>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Tipo (opcional)</Text>
                <SelectField value={tipo} onChange={setTipo} options={tipoOpts} placeholder="Todos" modalTitle="Selecione o tipo" allowClear compactWeb testID="relra-tipo" />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Técnico (opcional)</Text>
                <SelectField value={tecnico} onChange={setTecnico} options={tecnicoOpts} placeholder="Todos" modalTitle="Selecione o técnico" allowClear compactWeb testID="relra-tecnico" />
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Cliente (código, opcional)</Text>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                  <TextInput
                    value={clienteCodigo}
                    onChangeText={setClienteCodigo}
                    keyboardType="number-pad"
                    placeholder="Código"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, { flex: 1, minWidth: 0 }]}
                    testID="relra-cliente"
                  />
                  <IconButtonWithTooltip
                    icon="search-outline" label="Buscar Cliente" onPress={clienteSearch.openModal}
                    size={20} color={colors.brandPrimary} testID="relra-cliente-buscar"
                  />
                </View>
              </View>
              <View style={styles.filterCol}>
                <Text style={styles.fieldLabel}>Chassi/Equip. (opcional)</Text>
                <TextInput
                  value={chassi}
                  onChangeText={setChassi}
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="relra-chassi"
                />
              </View>
            </View>

            <Text style={styles.fieldLabel}>Incluir por destino</Text>
            <View style={styles.chipRow}>
              <Pressable onPress={() => setIncluirClientePg((v) => !v)} style={[styles.chip, incluirClientePg && styles.chipSel]} testID="relra-inc-cliente">
                <Text style={[styles.chipText, incluirClientePg && styles.chipTextSel]}>Cliente Pg.</Text>
              </Pressable>
              <Pressable onPress={() => setIncluirContrato((v) => !v)} style={[styles.chip, incluirContrato && styles.chipSel]} testID="relra-inc-contrato">
                <Text style={[styles.chipText, incluirContrato && styles.chipTextSel]}>Interno/Contrato</Text>
              </Pressable>
              <Pressable onPress={() => setIncluirGarantia((v) => !v)} style={[styles.chip, incluirGarantia && styles.chipSel]} testID="relra-inc-garantia">
                <Text style={[styles.chipText, incluirGarantia && styles.chipTextSel]}>Garantia</Text>
              </Pressable>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relra-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relra-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relra-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </AccordionSection>
          </View>

          {resultado ? (
            resultado.itens.length === 0 ? (
              <Text style={styles.empty}>Nenhum registro no período.</Text>
            ) : (
              <View style={styles.card}>
                {resultado.itens.map((i) => (
                  <View key={i.os} style={styles.osRow}>
                    <View style={styles.osHead}>
                      <Text style={styles.osTitle}>OS #{i.os} — {brDate(i.data_termino)}</Text>
                      <Text style={styles.osTipo}>{i.tipo_desc}</Text>
                    </View>
                    <Text style={styles.osMeta}>
                      Técnico: {i.tecnico_nome} · {i.hora_inicio || "—"} - {i.hora_fim || "—"} · {i.tot_horas}h
                    </Text>
                    {i.resumo ? <Text style={styles.osResumo} numberOfLines={2}>{i.resumo}</Text> : null}
                    <View style={styles.osValoresRow}>
                      <View style={styles.osValorCol}>
                        <Text style={styles.osValorLabel}>Serviço(s)</Text>
                        <Text style={styles.osValorValue}>{formatBRL(i.tot_servicos)}</Text>
                      </View>
                      <View style={styles.osValorCol}>
                        <Text style={styles.osValorLabel}>Peça(s)</Text>
                        <Text style={styles.osValorValue}>{formatBRL(i.tot_pecas)}</Text>
                      </View>
                      <View style={styles.osValorCol}>
                        <Text style={styles.osValorLabel}>Contrato</Text>
                        <Text style={styles.osValorValue}>{formatBRL(i.tot_contrato)}</Text>
                      </View>
                      <View style={styles.osValorCol}>
                        <Text style={styles.osValorLabel}>Garantia</Text>
                        <Text style={styles.osValorValue}>{formatBRL(i.tot_garantia)}</Text>
                      </View>
                      <View style={styles.osValorCol}>
                        <Text style={styles.osValorLabel}>Cliente Pg.</Text>
                        <Text style={[styles.osValorValue, styles.osValorDestaque]}>{formatBRL(i.tot_cliente_pg)}</Text>
                      </View>
                    </View>
                  </View>
                ))}
                <View style={styles.totaisRow}>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>T.Horas</Text>
                    <Text style={styles.totalValue}>{resultado.totais.horas}</Text>
                  </View>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>Serviço(s)</Text>
                    <Text style={styles.totalValue}>{formatBRL(resultado.totais.servicos)}</Text>
                  </View>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>Peça(s)</Text>
                    <Text style={styles.totalValue}>{formatBRL(resultado.totais.pecas)}</Text>
                  </View>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>Contrato</Text>
                    <Text style={styles.totalValue}>{formatBRL(resultado.totais.contrato)}</Text>
                  </View>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>Garantia</Text>
                    <Text style={styles.totalValue}>{formatBRL(resultado.totais.garantia)}</Text>
                  </View>
                  <View style={styles.osValorCol}>
                    <Text style={styles.osValorLabel}>Cliente Pg.</Text>
                    <Text style={styles.totalValue}>{formatBRL(resultado.totais.cliente_pg)}</Text>
                  </View>
                </View>
              </View>
            )
          ) : !loading ? (
            <Text style={styles.empty}>Defina os filtros e clique em Selecionar.</Text>
          ) : null}
        </View>
      </ScrollView>
      <ClientSearchModal
        visible={clienteSearch.open}
        onClose={clienteSearch.closeModal}
        term={clienteSearch.term}
        setTerm={clienteSearch.setTerm}
        loading={clienteSearch.loading}
        results={clienteSearch.results}
        onPick={(c) => { setClienteCodigo(String(c.codigo)); clienteSearch.closeModal(); }}
        onCreate={clienteSearch.closeModal}
      />
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
  filterGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  filterCol: { flexGrow: 1, flexBasis: 160, minWidth: 140 },
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
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: spacing.sm,
  },
  osRow: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: spacing.sm },
  osHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  osTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  osTipo: { fontSize: 11, color: colors.muted },
  osMeta: { fontSize: 11, color: colors.muted, marginTop: 2 },
  osResumo: { fontSize: 11, color: colors.onSurface, marginTop: 4 },
  osValoresRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: spacing.sm },
  osValorCol: { minWidth: 80 },
  osValorLabel: { fontSize: 9, color: colors.muted, textTransform: "uppercase" },
  osValorValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  osValorDestaque: { color: colors.brandPrimary, fontWeight: "700" },
  totaisRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, paddingTop: spacing.sm, borderTopWidth: 2, borderTopColor: colors.brandPrimary },
  totalValue: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
