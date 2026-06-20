import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
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
import { colors, radius, spacing } from "@/src/theme/colors";

type Pedido = {
  pedido: number;
  data: string | null;
  validade: string | null;
  situacao: string;
  situacao_label: string;
  total: number;
  cliente: number | null;
  cliente_nome: string;
  vendedor: number | null;
  vendedor_nome: string;
  hora_aberto: string;
};

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
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

export default function PedidosScreen() {
  const router = useRouter();
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("");
  const [items, setItems] = useState<Pedido[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      setConn(cs.find((x) => x.empresa === s?.empresa) || null);
    })();
  }, []);

  const load = useCallback(
    async (term: string, sit: string, pg: number, append: boolean) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      setError(null);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/pedidos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: conn.servidor, banco: conn.banco,
            search: term, situacao: sit, page: pg, size: 20,
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
      load(search, situacao, 1, false);
    }, 350);
    return () => clearTimeout(t);
  }, [search, situacao, conn, load]);

  useFocusEffect(useCallback(() => {
    if (conn) load(search, situacao, 1, false);
  }, [conn, search, situacao, load]));

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, situacao, next, true);
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="pedidos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]} hitSlop={12}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Pedidos ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por cliente, CPF, telefone ou nº do pedido…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="pedidos-search-input"
        />
      </View>

      <View style={styles.chipsRow}>
        {SITUACOES.map((s) => {
          const sel = situacao === s.value;
          return (
            <Pressable
              key={s.value || "all"}
              onPress={() => setSituacao(s.value)}
              style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.7 }]}
              testID={`pedidos-chip-${s.value || "all"}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>{s.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {error ? <Text style={styles.errorText} testID="pedidos-error">{error}</Text> : null}

      <FlatList
        data={items}
        keyExtractor={(p) => String(p.pedido)}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 100 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum pedido.</Text> : null}
        ListFooterComponent={loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => router.push({ pathname: "/pedido-form", params: { pedido: String(item.pedido) } })}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }]}
            testID={`pedido-${item.pedido}`}
          >
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Text style={styles.cardTitle}>#{item.pedido}</Text>
                <View style={[styles.sitTag, { backgroundColor: (SIT_COLOR[item.situacao] || colors.muted) + "22" }]}>
                  <Text style={[styles.sitTagText, { color: SIT_COLOR[item.situacao] || colors.muted }]}>{item.situacao_label}</Text>
                </View>
              </View>
              <Text style={styles.cardCliente} numberOfLines={1}>{item.cliente_nome || "(sem cliente)"}</Text>
              <Text style={styles.cardMeta}>
                {formatDate(item.data)} · {item.vendedor_nome || "—"}
              </Text>
            </View>
            <Text style={styles.cardValor}>{formatBRL(item.total)}</Text>
          </Pressable>
        )}
      />

      <Pressable
        onPress={() => router.push("/pedido-form")}
        style={({ pressed }) => [styles.fab, pressed && { opacity: 0.85 }]}
        hitSlop={8}
        testID="pedidos-fab-new"
      >
        <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
      </Pressable>
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
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  chipsRow: {
    flexDirection: "row", flexWrap: "wrap", gap: 8,
    paddingHorizontal: spacing.lg, marginTop: spacing.md, marginBottom: spacing.sm,
  },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, height: 36, justifyContent: "center", flexShrink: 0,
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  errorText: { color: colors.error, fontSize: 13, marginHorizontal: spacing.lg, marginBottom: spacing.sm },
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
