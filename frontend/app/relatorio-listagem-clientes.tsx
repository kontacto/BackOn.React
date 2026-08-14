// Listagem de Clientes — migração de Geral\FrmRelClie.frm (Painel de
// Relatórios > Clientes). 6 modos de filtro + PF/PJ. "Tipo" generalizado
// pra cliente.cliente_forn (tipo_cliente real) — ver docstring do
// service pro raciocínio completo.
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
import { exportListagemClientesPdf, ClienteListagemRow } from "@/src/utils/export-listagem-clientes";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Modo = "codigo" | "cgc" | "nome" | "data_cadastro" | "data_nasc" | "tipo";

const MODOS: { k: Modo; l: string }[] = [
  { k: "nome", l: "Nome/Razão Social" }, { k: "codigo", l: "Código Interno" }, { k: "cgc", l: "CPF/CNPJ" },
  { k: "data_cadastro", l: "Data de Cadastro" }, { k: "data_nasc", l: "Data de Nascimento" }, { k: "tipo", l: "Tipo Cliente" },
];

export default function RelatorioListagemClientesScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);

  const [modo, setModo] = useState<Modo>("nome");
  const [termo, setTermo] = useState("");
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [pessoaFisica, setPessoaFisica] = useState(true);
  const [pessoaJuridica, setPessoaJuridica] = useState(true);
  const [ordem, setOrdem] = useState<"asc" | "desc">("asc");

  const [loading, setLoading] = useState(false);
  const [clientes, setClientes] = useState<ClienteListagemRow[]>([]);

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
        const r = await fetch(`${base}/api/tabelas/tipo-cliente?${qs}`);
        const j = await r.json();
        if (j?.success) setTipoOpts((j.items || []).map((t: { codigo: number; descricao: string }) => ({ value: t.codigo, label: t.descricao })));
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
      let url = `${base}/api/relatorios/listagem-clientes?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&modo=${modo}&pessoa_fisica=${pessoaFisica}&pessoa_juridica=${pessoaJuridica}&ordem=${ordem}`;
      if (termo.trim()) url += `&termo=${encodeURIComponent(termo.trim())}`;
      if (dataIni) url += `&data_ini=${dataIni}`;
      if (dataFim) url += `&data_fim=${dataFim}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao buscar."); return; }
      setClientes(j.clientes || []);
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, modo, termo, dataIni, dataFim, pessoaFisica, pessoaJuridica, ordem, feedback]);

  const imprimir = useCallback(async () => {
    if (!conn) return;
    try {
      await exportListagemClientesPdf("Listagem de Clientes", `${clientes.length} cliente(s)`, clientes, empresa, async (codigo) => {
        const base = conn.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/relatorios/listagem-clientes/${codigo}/detalhe?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`);
        const j = await r.json();
        return { telefones: j.telefones || [], enderecos: j.enderecos || [] };
      });
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [conn, clientes, empresa, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (clientes.length === 0) return;
    exportSheetsToXlsx("listagem-de-clientes", [
      {
        name: "Clientes",
        rows: clientes.map((c) => ({
          "Código Int": c.codigo, "CNPJ/CPF": c.cgc_cpf, Nome: c.nome, "Data Cad.": c.data_cad,
          "Data Nasc.": c.data_nasc, Situação: c.situacao,
        })),
      },
    ]);
  }, [clientes]);

  const modoAtual = MODOS.find((m) => m.k === modo)!;
  const isDataMode = modo === "data_cadastro" || modo === "data_nasc";

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-listagem-clientes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="rellc-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Listagem de Clientes</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Filtrar por</Text>
            <View style={styles.chipRow}>
              {MODOS.map((m) => (
                <Pressable key={m.k} onPress={() => setModo(m.k)} style={[styles.chip, modo === m.k && styles.chipSel]} testID={`rellc-modo-${m.k}`}>
                  <Text style={[styles.chipText, modo === m.k && styles.chipTextSel]}>{m.l}</Text>
                </Pressable>
              ))}
            </View>

            {isDataMode ? (
              <View style={styles.dateRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>De</Text>
                  {isWeb ? (
                    <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="rellc-data-ini" />
                  ) : (
                    <DateField value={dataIni} onChange={setDataIni} testID="rellc-data-ini" />
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Até</Text>
                  {isWeb ? (
                    <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="rellc-data-fim" />
                  ) : (
                    <DateField value={dataFim} onChange={setDataFim} testID="rellc-data-fim" />
                  )}
                </View>
              </View>
            ) : modo === "tipo" ? (
              <View style={{ maxWidth: 320 }}>
                <Text style={styles.fieldLabel}>Tipo Cliente</Text>
                <SelectField value={termo} onChange={(v) => setTermo(String(v))} options={tipoOpts} placeholder="Selecione" compactWeb testID="rellc-tipo" />
              </View>
            ) : (
              <View style={{ maxWidth: 320 }}>
                <Text style={styles.fieldLabel}>{modoAtual.l}</Text>
                <TextInput value={termo} onChangeText={setTermo} style={styles.input} testID="rellc-termo" />
              </View>
            )}

            <View style={styles.chipRow}>
              <Pressable onPress={() => setPessoaFisica((v) => !v)} style={styles.checkRow} testID="rellc-pf">
                <Ionicons name={pessoaFisica ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Pessoa Física</Text>
              </Pressable>
              <Pressable onPress={() => setPessoaJuridica((v) => !v)} style={styles.checkRow} testID="rellc-pj">
                <Ionicons name={pessoaJuridica ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Pessoa Jurídica</Text>
              </Pressable>
              <Pressable onPress={() => setOrdem(ordem === "asc" ? "desc" : "asc")} style={styles.checkRow} testID="rellc-ordem">
                <Ionicons name={ordem === "asc" ? "arrow-down-outline" : "arrow-up-outline"} size={16} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>{ordem === "asc" ? "A → Z" : "Z → A"}</Text>
              </Pressable>
            </View>

            <View style={styles.actionsRow}>
              <Pressable onPress={buscar} disabled={loading} style={[styles.searchBtn, loading && { opacity: 0.85 }]} testID="rellc-selecionar">
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>
              {clientes.length > 0 ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="rellc-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="rellc-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          <View style={styles.card}>
            {clientes.length === 0 ? (
              <Text style={styles.empty}>{loading ? "Buscando..." : "Nenhum cliente encontrado."}</Text>
            ) : clientes.map((c) => (
              <View key={c.codigo} style={styles.row}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowLabel} numberOfLines={1}>{c.nome}</Text>
                  <Text style={styles.rowMeta}>{c.cgc_cpf} · Cód {c.codigo} · {c.situacao}</Text>
                </View>
                <Text style={styles.rowDate}>{c.data_cad || "—"}</Text>
              </View>
            ))}
          </View>
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
  filters: { gap: spacing.sm, marginBottom: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  dateRow: { flexDirection: "row", gap: spacing.sm },
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
  input: {
    height: 40, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
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
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 8, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowMeta: { fontSize: 10, color: colors.muted, marginTop: 2 },
  rowDate: { fontSize: 11, color: colors.muted },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginVertical: 12 },
});
