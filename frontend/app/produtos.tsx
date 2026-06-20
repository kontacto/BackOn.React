import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type Tipo = "all" | "P" | "S";
type Item = {
  tipo: "P" | "S";
  codigo: string;
  descricao: string;
  valor: number;
  estoque: number | null;
};

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function ProdutosScreen() {
  const router = useRouter();
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  const [tipo, setTipo] = useState<Tipo>("all");
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
    })();
  }, []);

  const load = useCallback(
    async (term: string, pg: number, tp: Tipo, append: boolean) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      setError(null);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const url =
          `${base}/api/produtos-servicos` +
          `?servidor=${encodeURIComponent(conn.servidor)}` +
          `&banco=${encodeURIComponent(conn.banco)}` +
          `&search=${encodeURIComponent(term)}` +
          `&page=${pg}&size=40&tipo=${tp}`;
        const r = await fetch(url, { signal: ac.signal });
        const j = await r.json();
        if (!j?.success) {
          setError(j?.message || "Falha ao consultar.");
          if (!append) setItems([]);
        } else {
          const fetched: Item[] = j.items || [];
          setItems((prev) => (append ? [...prev, ...fetched] : fetched));
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

  // Recarrega quando muda search / tipo (debounce 300ms na busca)
  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => {
      setPage(1);
      load(search, 1, tipo, false);
    }, 300);
    return () => clearTimeout(t);
  }, [search, tipo, conn, load]);

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, next, tipo, true);
  };

  // Tipo da rota da foto — codigo é string (nvarchar). URL-encode pra segurança.
  const fotoUrl = useCallback(
    (item: Item): string | null => {
      if (!conn) return null;
      if (item.tipo === "S") return null;
      return `${conn.api.replace(/\/+$/, "")}/api/produtos/foto/${encodeURIComponent(item.codigo)}`;
    },
    [conn]
  );

  const counts = useMemo(() => {
    const p = items.filter((i) => i.tipo === "P").length;
    const s = items.filter((i) => i.tipo === "S").length;
    return { p, s };
  }, [items]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="produtos-screen">
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Produtos & Serviços ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por código ou descrição…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="produtos-search-input"
        />
      </View>

      {/* Chips de tipo — chrome sticky, scroll horizontal NÃO necessário (só 3 chips) */}
      <View style={styles.chips}>
        {([
          { key: "all" as const, label: "Tudo", count: counts.p + counts.s },
          { key: "P" as const, label: "Produtos", count: counts.p },
          { key: "S" as const, label: "Serviços", count: counts.s },
        ]).map((c) => {
          const sel = tipo === c.key;
          return (
            <Pressable
              key={c.key}
              onPress={() => setTipo(c.key)}
              style={({ pressed }) => [
                styles.chip,
                sel && styles.chipSel,
                pressed && { opacity: 0.7 },
              ]}
              testID={`produtos-chip-${c.key}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {error ? (
        <Text style={styles.errorText} testID="produtos-error">
          {error}
        </Text>
      ) : null}

      <FlatList
        data={items}
        keyExtractor={(i) => `${i.tipo}-${i.codigo}`}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.empty}>Nenhum item encontrado.</Text>
          ) : null
        }
        ListFooterComponent={
          loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : null
        }
        renderItem={({ item }) => (
          <View
            style={styles.card}
            testID={`item-${item.tipo}-${item.codigo}`}
          >
            {item.tipo === "P" ? (
              <ProdutoFoto url={fotoUrl(item)} />
            ) : (
              <View style={[styles.thumb, styles.thumbServico]}>
                <Ionicons name="construct-outline" size={26} color={colors.brandPrimary} />
              </View>
            )}

            <View style={{ flex: 1 }}>
              <View style={styles.cardTitleRow}>
                <Text style={styles.cardTitle} numberOfLines={2}>
                  {item.descricao || "—"}
                </Text>
                <View
                  style={[
                    styles.tipoTag,
                    item.tipo === "P" ? styles.tagProd : styles.tagServ,
                  ]}
                >
                  <Text style={[styles.tipoTagText, item.tipo === "P" ? { color: colors.brandPrimary } : { color: colors.warning }]}>
                    {item.tipo === "P" ? "PRODUTO" : "SERVIÇO"}
                  </Text>
                </View>
              </View>
              <Text style={styles.cardSub}>
                Código: <Text style={styles.cardSubBold}>#{item.codigo}</Text>
              </Text>
              <View style={styles.cardFooter}>
                <Text style={styles.cardValor}>{formatBRL(item.valor)}</Text>
                {item.tipo === "P" ? (
                  <Text
                    style={[
                      styles.estoque,
                      (item.estoque ?? 0) <= 0 && { color: colors.error },
                    ]}
                  >
                    Estoque: {item.estoque ?? 0}
                  </Text>
                ) : (
                  <Text style={styles.estoque}>por hora</Text>
                )}
              </View>
            </View>
          </View>
        )}
      />
    </SafeAreaView>
  );
}

// Foto do produto com fallback (placeholder com ícone quando o endpoint retorna 204).
function ProdutoFoto({ url }: { url: string | null }) {
  const [erro, setErro] = useState(false);
  useEffect(() => {
    setErro(false);
  }, [url]);
  if (!url || erro) {
    return (
      <View style={[styles.thumb, styles.thumbProduto]}>
        <Ionicons name="cube-outline" size={26} color={colors.brandPrimary} />
      </View>
    );
  }
  return (
    <Image
      source={{ uri: url }}
      style={styles.thumb}
      onError={() => setErro(true)}
      resizeMode="cover"
    />
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  backBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  headerTitle: {
    flex: 1, color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  chips: {
    flexDirection: "row", gap: 8,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md, marginBottom: spacing.sm,
    height: 56, alignItems: "center",
  },
  chip: {
    flexShrink: 0,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    height: 36, justifyContent: "center",
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  errorText: {
    color: colors.error, fontSize: 13, marginHorizontal: spacing.lg, marginBottom: spacing.sm,
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  thumb: {
    width: 64, height: 64, borderRadius: radius.sm,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  thumbProduto: { backgroundColor: colors.brandTertiary },
  thumbServico: { backgroundColor: "#fff4e0" },
  cardTitleRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm },
  cardTitle: { flex: 1, fontSize: 14, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardSubBold: { color: colors.onSurface, fontWeight: "500" },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  cardValor: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  estoque: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  tipoTag: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 4, alignSelf: "flex-start",
  },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  tipoTagText: { fontSize: 10, fontWeight: "600", letterSpacing: 0.4 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40 },
});
