// Ordem de Serviço (busca) — migração de FrmRelOS.frm (Painel de
// Relatórios > Pré Venda). Tela de busca/lookup de O.S. por um único
// critério por vez (não é relatório de período) — master-detail: lista
// de O.S. encontradas → itens da O.S. selecionada.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportBuscaOsPdf, BuscaOsPayload, BuscaOsItem } from "@/src/utils/export-busca-os";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Filtro = "cliente" | "data_entrada" | "data_termino" | "placa" | "chassi" | "os" | "marca" | "modelo";
type ItemOs = { codigo: string; descricao: string; qtd: number; valor_unitario: number; valor_total: number; destino: string };

const FILTROS: { key: Filtro; label: string; range: boolean }[] = [
  { key: "cliente", label: "Cliente", range: false },
  { key: "data_entrada", label: "Data Entrada", range: true },
  { key: "data_termino", label: "Data Término", range: true },
  { key: "placa", label: "Placa", range: false },
  { key: "chassi", label: "Chassi", range: false },
  { key: "os", label: "OS", range: true },
  { key: "marca", label: "Marca", range: false },
  { key: "modelo", label: "Modelo", range: false },
];

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function brDate(iso: string | null): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : "—";
}

export default function RelatorioBuscaOsScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [filtro, setFiltro] = useState<Filtro>("cliente");
  const [valor1, setValor1] = useState("");
  const [valor2, setValor2] = useState("");
  const [ordem, setOrdem] = useState<"asc" | "desc">("asc");

  const [loading, setLoading] = useState(false);
  const [itens, setItens] = useState<BuscaOsItem[]>([]);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);
  const [expandidoOs, setExpandidoOs] = useState<number | null>(null);
  const [itensExpandido, setItensExpandido] = useState<ItemOs[]>([]);
  const [loadingDetalhe, setLoadingDetalhe] = useState(false);

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

  const filtroInfo = FILTROS.find((f) => f.key === filtro)!;

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!valor1.trim()) { feedback.showWarning("Informe o valor do filtro."); return; }
    setLoading(true);
    setExpandidoOs(null);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/busca-os?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&filtro=${filtro}&valor1=${encodeURIComponent(valor1.trim())}&ordem=${ordem}`;
      if (filtroInfo.range && valor2.trim()) url += `&valor2=${encodeURIComponent(valor2.trim())}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha na busca."); setItens([]); }
      else setItens(j.itens || []);
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, filtro, valor1, valor2, ordem, filtroInfo, feedback]);

  const toggleExpand = useCallback(async (os: number) => {
    if (!conn) return;
    if (expandidoOs === os) { setExpandidoOs(null); return; }
    setExpandidoOs(os);
    setLoadingDetalhe(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/relatorios/busca-os/${os}/itens?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`);
      const j = await r.json();
      setItensExpandido(j?.success ? (j.itens || []) : []);
    } catch {
      setItensExpandido([]);
    } finally {
      setLoadingDetalhe(false);
    }
  }, [conn, expandidoOs]);

  const payload = useCallback((): BuscaOsPayload => ({
    titulo: "Ordem de Serviço",
    criterio: `${filtroInfo.label}: ${valor1}${filtroInfo.range && valor2 ? ` a ${valor2}` : ""}`,
    itens,
    empresa,
  }), [filtroInfo, valor1, valor2, itens, empresa]);

  const imprimir = useCallback(async () => {
    try {
      await exportBuscaOsPdf(payload());
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [payload, feedback]);

  const gerarPlanilha = useCallback(() => {
    exportSheetsToXlsx("ordem-de-servico-busca", [
      {
        name: "Ordem de Serviço",
        rows: itens.map((i) => ({
          Cliente: i.cliente_nome, OS: i.os, Veículo: i.veiculo,
          Entrada: i.data_entrada, Término: i.data_termino, Placa: i.placa, Chassi: i.chassi, Situação: i.situacao,
        })),
      },
    ]);
  }, [itens]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-busca-os-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relbos-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Ordem de Serviço</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Buscar por</Text>
            <View style={styles.chipRow}>
              {FILTROS.map((f) => {
                const sel = filtro === f.key;
                return (
                  <Pressable
                    key={f.key}
                    onPress={() => { setFiltro(f.key); setValor1(""); setValor2(""); }}
                    style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.8 }]}
                    testID={`relbos-filtro-${f.key}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{f.label}</Text>
                  </Pressable>
                );
              })}
            </View>

            <View style={styles.valueRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>{filtroInfo.range ? `${filtroInfo.label} (de)` : filtroInfo.label}</Text>
                <TextInput
                  value={valor1}
                  onChangeText={setValor1}
                  placeholder={filtro === "data_entrada" || filtro === "data_termino" ? "AAAA-MM-DD" : ""}
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="relbos-valor1"
                />
              </View>
              {filtroInfo.range ? (
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>{filtroInfo.label} (até)</Text>
                  <TextInput
                    value={valor2}
                    onChangeText={setValor2}
                    placeholder={filtro === "data_entrada" || filtro === "data_termino" ? "AAAA-MM-DD" : ""}
                    placeholderTextColor={colors.muted}
                    style={styles.input}
                    testID="relbos-valor2"
                  />
                </View>
              ) : null}
            </View>

            <Text style={styles.fieldLabel}>Ordenação</Text>
            <View style={styles.chipRow}>
              <Pressable
                onPress={() => setOrdem("asc")}
                style={[styles.chip, ordem === "asc" && styles.chipSel]}
                testID="relbos-ordem-asc"
              >
                <Text style={[styles.chipText, ordem === "asc" && styles.chipTextSel]}>Ascendente</Text>
              </Pressable>
              <Pressable
                onPress={() => setOrdem("desc")}
                style={[styles.chip, ordem === "desc" && styles.chipSel]}
                testID="relbos-ordem-desc"
              >
                <Text style={[styles.chipText, ordem === "desc" && styles.chipTextSel]}>Descendente</Text>
              </Pressable>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relbos-selecionar"
              >
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Buscar</Text>
                  </>
                )}
              </Pressable>

              {itens.length > 0 ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relbos-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relbos-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {itens.length === 0 && !loading ? (
            <Text style={styles.empty}>Informe um critério e clique em Buscar.</Text>
          ) : (
            <View style={styles.card}>
              {itens.map((i) => {
                const aberto = expandidoOs === i.os;
                return (
                  <View key={i.os} style={styles.itemBlock}>
                    <Pressable onPress={() => toggleExpand(i.os)} style={styles.itemRow} testID={`relbos-os-${i.os}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemTitle}>OS #{i.os} — {i.cliente_nome}</Text>
                        <Text style={styles.itemMeta}>
                          {i.veiculo} · Placa {i.placa || "—"} · Entrada {brDate(i.data_entrada)} · Término {brDate(i.data_termino)} · {i.situacao}
                        </Text>
                      </View>
                      <Ionicons name={aberto ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
                    </Pressable>
                    {aberto ? (
                      loadingDetalhe ? (
                        <ActivityIndicator size="small" color={colors.brandPrimary} style={{ marginVertical: spacing.sm }} />
                      ) : (
                        <View style={styles.detalheBlock}>
                          {itensExpandido.length === 0 ? (
                            <Text style={styles.detalheVazio}>Sem itens.</Text>
                          ) : itensExpandido.map((it, idx) => (
                            <View key={idx} style={styles.detalheRow}>
                              <View style={{ flex: 1 }}>
                                <Text style={styles.detalheText}>{it.codigo} — {it.descricao}</Text>
                                <Text style={styles.detalheMeta}>Qtd {it.qtd} · {formatBRL(it.valor_unitario)} · {it.destino}</Text>
                              </View>
                              <Text style={styles.detalheValor}>{formatBRL(it.valor_total)}</Text>
                            </View>
                          ))}
                        </View>
                      )
                    ) : null}
                  </View>
                );
              })}
            </View>
          )}
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
  valueRow: { flexDirection: "row", gap: spacing.sm },
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
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  itemBlock: { borderBottomWidth: 1, borderBottomColor: colors.border },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8 },
  itemTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  itemMeta: { fontSize: 11, color: colors.muted, marginTop: 2 },
  detalheBlock: { paddingLeft: spacing.md, paddingBottom: spacing.sm, gap: 6 },
  detalheRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  detalheText: { fontSize: 12, color: colors.onSurface },
  detalheMeta: { fontSize: 10, color: colors.muted, marginTop: 1 },
  detalheValor: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  detalheVazio: { fontSize: 11, color: colors.muted, fontStyle: "italic" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
