// Lista de O.S. da O.S. Completa — mesma relação de `pedido-lista.tsx` com
// `pedido-geral.tsx`: a O.S. Mobile continua com sua própria tela
// (`app/os.tsx`), esta é exclusiva da O.S. Completa. Reaproveita o mesmo
// endpoint `POST /api/os` (já suporta busca/situação/período) que `os.tsx`
// usa — sem os filtros/visual de painel por colunas do módulo Bar (aquilo
// é específico do Pedido, não existe equivalente pra O.S.). Sem filtro de
// Vendedor — diferente do Pedido, a O.S. não tem vendedor no cabeçalho (é
// por item, ver `os_produto.vendedor`), só Atendente.
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;
type OSRow = {
  codigo: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente_nome: string; atendente_nome: string;
};

const SITUACOES = [
  { value: "", label: "Todas" },
  { value: "A", label: "Aberta" },
  { value: "F", label: "Fechada" },
  { value: "PG", label: "Faturada" },
  { value: "C", label: "Cancelada" },
];

export default function OSListaScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const feedback = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Esta lista de O.S. está disponível apenas no web." testID="os-lista-web-only" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [items, setItems] = useState<OSRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      setLoadingConn(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (c: Conn, term: string, sit: string, di: string | null, df: string | null, pg: number, append: boolean) => {
    if (aborter.current) aborter.current.abort();
    const ac = new AbortController();
    aborter.current = ac;
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/os`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: c.servidor, banco: c.banco,
          search: term, situacao: sit,
          data_ini: di, data_fim: df, page: pg, size: 20,
        }),
        signal: ac.signal,
      });
      const j = await r.json();
      if (!j?.success) {
        feedback.showError(j?.message || "Falha na consulta.");
        if (!append) setItems([]);
      } else {
        setItems((prev) => (append ? [...prev, ...j.items] : j.items));
        setTotal(j.total || 0);
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError") {
        feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    } finally {
      if (aborter.current === ac) setLoading(false);
    }
  }, [feedback]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => { setPage(1); load(conn, search, situacao, dataIni, dataFim, 1, false); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, search, situacao, dataIni, dataFim]);

  const loadMore = () => {
    if (!conn || loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(conn, search, situacao, dataIni, dataFim, next, true);
  };

  const abrirOS = (item: OSRow) => {
    router.push({ pathname: "/os-geral", params: { os: String(item.codigo) } } as never);
  };

  const canGravar = can("OS_COMP.GRAVAR");

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="os-lista-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="os-lista-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>O.S. ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.shellOuter}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={search}
                onChangeText={setSearch}
                placeholder="Buscar por cliente ou nº da O.S.…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="os-lista-search"
              />
            </View>
            <View style={styles.chipsRow}>
              {SITUACOES.map((s) => {
                const sel = situacao === s.value;
                return (
                  <Pressable
                    key={s.value || "all"}
                    onPress={() => setSituacao(s.value)}
                    style={[styles.chip, sel && styles.chipSel]}
                    testID={`os-lista-chip-${s.value || "all"}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>De</Text>
                <WebDateField
                  value={dataIni}
                  onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                  testID="os-lista-data-ini"
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="os-lista-data-fim" />
              </View>
            </View>
          </View>

          {loading && items.length === 0 ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          <FlatList
            data={items}
            keyExtractor={(i) => String(i.codigo)}
            contentContainerStyle={styles.listContent}
            onEndReached={loadMore}
            onEndReachedThreshold={0.4}
            ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhuma O.S. encontrada.</Text> : null}
            renderItem={({ item }) => (
              <Pressable onPress={() => abrirOS(item)} style={styles.row} testID={`os-lista-${item.codigo}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>#{item.codigo} · {item.cliente_nome || "(sem cliente)"}</Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {item.data ? formatDateBR(item.data) : "—"} · {item.atendente_nome || "—"} · {item.situacao_label}
                  </Text>
                </View>
                <Text style={styles.rowValor}>{formatBRL(item.total)}</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            )}
          />
        </View>
      </View>

      {canGravar ? (
        <Pressable onPress={() => router.push("/os-geral" as never)} style={styles.fab} testID="os-lista-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  shellOuter: { flex: 1, alignItems: "center" },
  shell: { ...WEB_CONTENT_SHELL, flex: 1 },
  scrollWeb: WEB_SCROLL_CENTER,
  filterCard: { ...WEB_FILTER_CARD, marginTop: spacing.md, marginBottom: spacing.sm, gap: spacing.sm },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  colNarrow: { width: 160 },
  label: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: 100, gap: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, minHeight: 72,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
});
