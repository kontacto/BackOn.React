// Inatividade de Clientes — migração de Geral\FrmRelCliSMV.frm (Painel de
// Relatórios > Clientes). Generalizado pra Pedido/O.S. (não Comanda) —
// ver docstring do service pro raciocínio completo (ciclos, sub-checks de
// Contrato, "Acima de" como piso de data). Ganhou ação de reengajamento
// via EnvioMassaModal (WhatsApp), reaproveitando o mesmo mecanismo da
// Mala Direta (pedido do usuário, 2026-08-07).
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import EnvioMassaModal from "@/src/components/EnvioMassaModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportInatividadeClientesPdf, ClienteInativoRow } from "@/src/utils/export-inatividade-clientes";
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

export default function RelatorioInatividadeClientesScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);

  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipoCliente, setTipoCliente] = useState<string | number | null>(null);
  const [situacaoCadastro, setSituacaoCadastro] = useState<"todos" | "ativo" | "inativo">("ativo");
  const [situacaoContrato, setSituacaoContrato] = useState<"todos" | "A" | "F">("todos");
  const [patrimonio, setPatrimonio] = useState<"todos" | "com" | "sem">("todos");
  const [modoBase, setModoBase] = useState<"ultima_compra" | "especificar">("ultima_compra");
  const [dataBase, setDataBase] = useState<string | null>(null);
  const [fator1, setFator1] = useState("360");
  const [fator2, setFator2] = useState("180");
  const [fator3, setFator3] = useState("90");
  const [ultimaCompraDesde, setUltimaCompraDesde] = useState<string | null>(null);
  const [exibirContratoFat, setExibirContratoFat] = useState(false);
  const [exibirContratoPago, setExibirContratoPago] = useState(false);

  const [loading, setLoading] = useState(false);
  const [clientes, setClientes] = useState<ClienteInativoRow[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [envioOpen, setEnvioOpen] = useState(false);

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
        setVendedorOpts(arr.map((f: { codigo: string | number; nome: string }) => ({ value: String(f.codigo), label: (f.nome || "").trim() })));
      } catch { /* sem lista */ }
      try {
        const r = await fetch(`${base}/api/tabelas/tipo-cliente?${qs}`);
        const j = await r.json();
        if (j?.success) setTipoOpts((j.items || []).map((t: { codigo: number; descricao: string }) => ({ value: t.codigo, label: t.descricao })));
      } catch { /* sem lista */ }
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/inatividade-clientes?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}` +
        `&situacao_cadastro=${situacaoCadastro}&situacao_contrato=${situacaoContrato}&patrimonio=${patrimonio}` +
        `&modo_base=${modoBase}&fator1=${fator1}&fator2=${fator2}&fator3=${fator3}` +
        `&exibir_contrato_faturamento=${exibirContratoFat}&exibir_contrato_pago=${exibirContratoPago}`;
      if (vendedor) url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      if (tipoCliente) url += `&tipo_cliente=${encodeURIComponent(String(tipoCliente))}`;
      if (modoBase === "especificar" && dataBase) url += `&data_base=${dataBase}`;
      if (ultimaCompraDesde) url += `&ultima_compra_desde=${ultimaCompraDesde}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); return; }
      setClientes(j.clientes || []);
      setSelecionados(new Set((j.clientes || []).map((c: ClienteInativoRow) => c.codigo)));
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, tipoCliente, situacaoCadastro, situacaoContrato, patrimonio,
      modoBase, dataBase, fator1, fator2, fator3, ultimaCompraDesde, exibirContratoFat, exibirContratoPago, feedback]);

  const toggleSel = (codigo: number) => {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };

  const destinatariosEnvio = useMemo(
    () => clientes.filter((c) => selecionados.has(c.codigo)).map((c) => ({ codigo: c.codigo, nome: c.nome })),
    [clientes, selecionados]
  );

  const imprimir = useCallback(async () => {
    try {
      await exportInatividadeClientesPdf(`${brDate(dataIni)} a ${brDate(dataFim)}`, clientes, empresa);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [clientes, dataIni, dataFim, empresa, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (clientes.length === 0) return;
    exportSheetsToXlsx("inatividade-de-clientes", [
      {
        name: "Inatividade de Clientes",
        rows: clientes.map((c) => ({
          Cliente: c.nome, "Última Compra": c.ultima_compra,
          "Ciclo 1 (pedidos)": c.ciclos[0]?.qtd_pedidos, "Ciclo 2 (pedidos)": c.ciclos[1]?.qtd_pedidos, "Ciclo 3 (pedidos)": c.ciclos[2]?.qtd_pedidos,
          "Últ. Fat. Contrato": c.ultimo_faturamento_contrato, "Últ. Fat. Contrato Pago": c.ultimo_faturamento_contrato_pago,
          Telefone: c.telefones.join(" / "),
        })),
      },
    ]);
  }, [clientes]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-inatividade-clientes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relic-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Inatividade de Clientes</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.sectionTitle}>Período sem compra</Text>
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Inicial</Text>
                {isWeb ? (
                  <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="relic-data-ini" />
                ) : (
                  <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relic-data-ini" />
                )}
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Final</Text>
                {isWeb ? (
                  <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="relic-data-fim" />
                ) : (
                  <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relic-data-fim" />
                )}
              </View>
            </View>

            <Text style={styles.fieldLabel}>Situação Cadastro</Text>
            <View style={styles.chipRow}>
              {(["ativo", "inativo", "todos"] as const).map((v) => (
                <Pressable key={v} onPress={() => setSituacaoCadastro(v)} style={[styles.chip, situacaoCadastro === v && styles.chipSel]} testID={`relic-sitcad-${v}`}>
                  <Text style={[styles.chipText, situacaoCadastro === v && styles.chipTextSel]}>{v === "ativo" ? "Ativos" : v === "inativo" ? "Inativos" : "Todos"}</Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.rowFields}>
              <View style={{ flexGrow: 1, minWidth: 180 }}>
                <Text style={styles.fieldLabel}>Vendedor (opcional)</Text>
                <SelectField value={vendedor} onChange={setVendedor} options={vendedorOpts} placeholder="Todos" compactWeb allowClear testID="relic-vendedor" />
              </View>
              <View style={{ flexGrow: 1, minWidth: 180 }}>
                <Text style={styles.fieldLabel}>Tipo Cliente (opcional)</Text>
                <SelectField value={tipoCliente} onChange={setTipoCliente} options={tipoOpts} placeholder="Todos" compactWeb allowClear testID="relic-tipo" />
              </View>
            </View>

            <Text style={styles.fieldLabel}>Situação do Contrato</Text>
            <View style={styles.chipRow}>
              {([{ k: "todos" as const, l: "Todos" }, { k: "A" as const, l: "Aberto" }, { k: "F" as const, l: "Finalizado" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setSituacaoContrato(o.k)} style={[styles.chip, situacaoContrato === o.k && styles.chipSel]} testID={`relic-sitcon-${o.k}`}>
                  <Text style={[styles.chipText, situacaoContrato === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Patrimônio (produto/equipamento sob contrato ativo)</Text>
            <View style={styles.chipRow}>
              {([{ k: "todos" as const, l: "Todos" }, { k: "com" as const, l: "Com patrimônio" }, { k: "sem" as const, l: "Sem patrimônio" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setPatrimonio(o.k)} style={[styles.chip, patrimonio === o.k && styles.chipSel]} testID={`relic-patrim-${o.k}`}>
                  <Text style={[styles.chipText, patrimonio === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={styles.sectionTitle}>Apuração dos Ciclos</Text>
            <View style={styles.chipRow}>
              {([{ k: "ultima_compra" as const, l: "Última Compra do Cliente" }, { k: "especificar" as const, l: "Especificar Data Base" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setModoBase(o.k)} style={[styles.chip, modoBase === o.k && styles.chipSel]} testID={`relic-modobase-${o.k}`}>
                  <Text style={[styles.chipText, modoBase === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>
            {modoBase === "especificar" ? (
              <View style={{ maxWidth: 200 }}>
                <Text style={styles.fieldLabel}>Data Base</Text>
                {isWeb ? <WebDateField value={dataBase} onChange={setDataBase} testID="relic-database" /> : <DateField value={dataBase} onChange={setDataBase} testID="relic-database" />}
              </View>
            ) : null}
            <View style={styles.rowFields}>
              <View style={{ width: 100 }}>
                <Text style={styles.fieldLabel}>1ª (dias)</Text>
                <TextInput value={fator1} onChangeText={setFator1} keyboardType="numeric" style={styles.input} testID="relic-fator1" />
              </View>
              <View style={{ width: 100 }}>
                <Text style={styles.fieldLabel}>2ª (dias)</Text>
                <TextInput value={fator2} onChangeText={setFator2} keyboardType="numeric" style={styles.input} testID="relic-fator2" />
              </View>
              <View style={{ width: 100 }}>
                <Text style={styles.fieldLabel}>3ª (dias)</Text>
                <TextInput value={fator3} onChangeText={setFator3} keyboardType="numeric" style={styles.input} testID="relic-fator3" />
              </View>
            </View>

            <View style={{ maxWidth: 220 }}>
              <Text style={styles.fieldLabel}>Só clientes com última compra a partir de (opcional)</Text>
              {isWeb ? <WebDateField value={ultimaCompraDesde} onChange={setUltimaCompraDesde} testID="relic-ultima-desde" /> : <DateField value={ultimaCompraDesde} onChange={setUltimaCompraDesde} testID="relic-ultima-desde" />}
            </View>

            <Pressable onPress={() => setExibirContratoFat((v) => !v)} style={styles.checkRow} testID="relic-check-fat">
              <Ionicons name={exibirContratoFat ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Exibir data do último faturamento de contrato</Text>
            </Pressable>
            <Pressable onPress={() => setExibirContratoPago((v) => !v)} style={styles.checkRow} testID="relic-check-pago">
              <Ionicons name={exibirContratoPago ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Exibir último faturamento de contrato pago</Text>
            </Pressable>

            <View style={styles.actionsRow}>
              <Pressable onPress={buscar} disabled={loading} style={[styles.searchBtn, loading && { opacity: 0.85 }]} testID="relic-selecionar">
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>
              {clientes.length > 0 ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relic-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relic-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                  <Pressable onPress={() => setEnvioOpen(true)} disabled={destinatariosEnvio.length === 0} style={[styles.waBtn, destinatariosEnvio.length === 0 && { opacity: 0.5 }]} testID="relic-enviar-whatsapp">
                    <Ionicons name="logo-whatsapp" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Enviar WhatsApp ({destinatariosEnvio.length})</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          <View style={styles.card}>
            {clientes.length === 0 ? (
              <Text style={styles.empty}>{loading ? "Buscando..." : "Informe os filtros e clique em Selecionar."}</Text>
            ) : clientes.map((c) => (
              <View key={c.codigo} style={styles.row}>
                <Pressable onPress={() => toggleSel(c.codigo)} hitSlop={8} testID={`relic-sel-${c.codigo}`}>
                  <Ionicons name={selecionados.has(c.codigo) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                </Pressable>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>{c.nome}</Text>
                  <Text style={styles.rowMeta}>
                    Última compra: {c.ultima_compra ? brDate(c.ultima_compra) : "nunca"}
                    {c.telefones.length ? ` · ${c.telefones[0]}` : ""}
                  </Text>
                  {c.ciclos.some((ci) => ci.qtd_pedidos > 0) ? (
                    <Text style={styles.rowMeta}>
                      Ciclos: {c.ciclos.map((ci, i) => `${ci.qtd_pedidos} ped.${ci.dias_medio ? ` (${ci.dias_medio}d)` : ""}`).join(" · ")}
                    </Text>
                  ) : null}
                </View>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      <EnvioMassaModal
        visible={envioOpen} onClose={() => setEnvioOpen(false)} conn={conn}
        destinatarios={destinatariosEnvio} canalWhatsapp canalEmail={false}
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
  filters: { gap: spacing.sm, marginBottom: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginTop: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  dateRow: { flexDirection: "row", gap: spacing.sm },
  rowFields: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
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
  checkRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  checkLabel: { fontSize: 12, color: colors.onSurface },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  waBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: "#25D366",
  },
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
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 8, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowMeta: { fontSize: 10, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginVertical: 12 },
});
