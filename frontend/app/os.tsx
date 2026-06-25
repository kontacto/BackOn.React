import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import DateField from "@/src/components/DateField";

type OS = {
  codigo: number;
  cliente: number | null;
  cliente_nome: string;
  data: string | null;
  hora: string;
  situacao: string;
  situacao_label: string;
  total: number;
};

const SITUACOES = [
  { value: "", label: "Todas" },
  { value: "A", label: "Aberta" },
  { value: "F", label: "Fechada" },
  { value: "PG", label: "Faturada" },
  { value: "C", label: "Cancelada" },
];

const SIT_COLOR: Record<string, string> = {
  A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935",
};

function formatBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

export default function OSScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("");
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [items, setItems] = useState<OS[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
    })();
  }, []);

  const load = useCallback(
    async (
      term: string, sit: string, di: string | null, df: string | null,
      pg: number, append: boolean,
    ) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      setError(null);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/os`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: conn.servidor, banco: conn.banco,
            search: term, situacao: sit,
            data_ini: di, data_fim: df,
            page: pg, size: 20,
          }),
          signal: ac.signal,
        });
        const j = await r.json();
        if (!j?.success) {
          setError(j?.message || "Falha na consulta.");
          if (!append) setItems([]);
        } else {
          setItems((prev) => (append ? [...prev, ...j.items] : j.items));
          setTotal(j.total || 0);
        }
      } catch (e: unknown) {
        if ((e as { name?: string })?.name !== "AbortError") {
          setError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        }
      } finally {
        if (aborter.current === ac) {
          setLoading(false);
          aborter.current = null;
        }
      }
    },
    [conn]
  );

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => {
      setPage(1);
      load(search, situacao, dataIni, dataFim, 1, false);
    }, 350);
    return () => clearTimeout(t);
  }, [search, situacao, dataIni, dataFim, conn, load]);

  useFocusEffect(useCallback(() => {
    if (conn) load(search, situacao, dataIni, dataFim, 1, false);
  }, [conn, search, situacao, dataIni, dataFim, load]));

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, situacao, dataIni, dataFim, next, true);
  };

  const clearDateFilters = () => {
    setDataIni(null);
    setDataFim(null);
  };

  const hasDateFilter = !!(dataIni || dataFim);

  const listHeader = (
    <View style={styles.headerBlock}>
      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por cliente, CPF/CNPJ ou nº da OS…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="os-search-input"
        />
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.chipsScroll}
        contentContainerStyle={styles.chipsRow}
        keyboardShouldPersistTaps="handled"
      >
        {SITUACOES.map((s) => {
          const sel = situacao === s.value;
          return (
            <Pressable
              key={s.value || "all"}
              onPress={() => setSituacao(s.value)}
              style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.7 }]}
              testID={`os-chip-${s.value || "all"}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>{s.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      {showFilters ? (
        <View style={styles.filterCard} testID="os-filter-card">
          <View style={styles.filterHeader}>
            <Text style={styles.filterTitle}>Filtrar por data</Text>
            {hasDateFilter ? (
              <Pressable
                onPress={clearDateFilters}
                style={({ pressed }) => [styles.clearBtn, pressed && { opacity: 0.7 }]}
                testID="os-clear-dates"
                hitSlop={6}
              >
                <Ionicons name="close-circle-outline" size={14} color={colors.brandPrimary} />
                <Text style={styles.clearBtnText}>Limpar</Text>
              </Pressable>
            ) : null}
          </View>
          <View style={styles.filterRow}>
            <DateField
              label="De"
              value={dataIni}
              onChange={setDataIni}
              testID="os-data-ini"
              maximumDate={dataFim ? new Date(dataFim) : undefined}
            />
            <DateField
              label="Até"
              value={dataFim}
              onChange={setDataFim}
              testID="os-data-fim"
              minimumDate={dataIni ? new Date(dataIni) : undefined}
            />
          </View>
        </View>
      ) : null}

      {error ? <Text style={styles.errorText} testID="os-error">{error}</Text> : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="os-screen">
      {!can("OS.ABRIR") ? (
        <LockedView testID="os-locked" />
      ) : (
      <>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="os-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Ordem de Serviço ({total})</Text>
        <Pressable
          onPress={() => setShowFilters((v) => !v)}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="os-toggle-filters"
        >
          <Ionicons
            name={showFilters ? "options" : "options-outline"}
            size={22}
            color={colors.onBrandPrimary}
          />
          {hasDateFilter ? <View style={styles.filterDot} /> : null}
        </Pressable>
      </View>

      <FlatList
        data={items}
        style={styles.list}
        keyExtractor={(o) => String(o.codigo)}
        keyboardShouldPersistTaps="handled"
        ListHeaderComponent={listHeader}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 100, paddingTop: spacing.sm }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhuma OS.</Text> : null}
        ListFooterComponent={loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => router.push({ pathname: "/os-form", params: { os: String(item.codigo) } })}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }]}
            testID={`os-${item.codigo}`}
          >
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Text style={styles.cardTitle}>OS #{item.codigo}</Text>
                <View style={[styles.sitTag, { backgroundColor: (SIT_COLOR[item.situacao] || colors.muted) + "22" }]}>
                  <Text style={[styles.sitTagText, { color: SIT_COLOR[item.situacao] || colors.muted }]}>{item.situacao_label}</Text>
                </View>
              </View>
              <Text style={styles.cardCliente} numberOfLines={1}>{item.cliente_nome || "(sem cliente)"}</Text>
              <Text style={styles.cardMeta}>{formatDate(item.data)}{item.hora ? ` · ${item.hora}` : ""}</Text>
            </View>
            <Text style={styles.cardValor}>{formatBRL(item.total)}</Text>
          </Pressable>
        )}
      />

      {can("OS.GRAVAR") ? (
        <Pressable
          onPress={() => router.push("/os-form")}
          style={({ pressed }) => [styles.fab, pressed && { opacity: 0.85 }]}
          hitSlop={8}
          testID="os-fab-new"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}
      </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  filterDot: {
    position: "absolute", top: 8, right: 8,
    width: 8, height: 8, borderRadius: 4, backgroundColor: "#ff5252",
  },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  headerBlock: { marginBottom: spacing.xs },
  chipsRow: { gap: 8, paddingVertical: spacing.md },
  chipsScroll: { flexGrow: 0, flexShrink: 0 },
  list: { flex: 1 },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, height: 36, justifyContent: "center", flexShrink: 0,
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  filterCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  filterHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  filterTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  clearBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  clearBtnText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "500" },
  filterRow: { flexDirection: "row", gap: 8 },
  errorText: { color: colors.error, fontSize: 13, marginBottom: spacing.sm },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  cardTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  cardCliente: { fontSize: 14, color: colors.onSurface, marginTop: 4 },
  cardMeta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardValor: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  sitTagText: { fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  fab: {
    position: "absolute", right: spacing.lg, bottom: spacing.xl,
    width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000", shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40 },
});
