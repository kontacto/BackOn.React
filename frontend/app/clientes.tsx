import { useCallback, useEffect, useState } from "react";
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
import { listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";

type Cliente = {
  codigo: number;
  nome: string;
  cgc_cpf?: string;
  telefone?: string;
  e_mail?: string;
  tipo_descricao?: string;
  situacao?: string;
};

export default function ClientesScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const canNovoCliente = can("CLIENTE.GRAVAR");
  const canNovoPedido = can("PEDIDO.GRAVAR");
  const [items, setItems] = useState<Cliente[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (q: string, p: number, append: boolean) => {
    setLoading(true);
    setError(null);
    const session = await getSession();
    const conns = await listConnections();
    const conn = conns.find((c) => c.empresa === session?.empresa);
    if (!conn) {
      setError("Conexão não encontrada.");
      setLoading(false);
      return;
    }
    try {
      const resp = await fetch(`${conn.api.replace(/\/+$/, "")}/api/clientes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor,
          banco: conn.banco,
          search: q,
          page: p,
          size: 20,
        }),
      });
      const data = await resp.json();
      if (!data.success) {
        setError(data.message || "Erro ao carregar");
      } else {
        setItems((prev) => (append ? [...prev, ...data.items] : data.items));
        setTotal(data.total);
      }
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1);
      load(search, 1, false);
    }, 400);
    return () => clearTimeout(t);
  }, [search, load]);

  // Recarrega a lista ao voltar para a tela (ex.: depois de criar/editar cliente),
  // mantendo o filtro de busca atual. Aplica reload em background sem mexer no
  // estado de search/page para não perder o contexto.
  useFocusEffect(
    useCallback(() => {
      load(search, 1, false);
      setPage(1);
    }, [load, search])
  );

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, next, true);
  };

  if (!can("CLIENTE.ABRIR")) {
    return <LockedView testID="clientes-locked" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="clientes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn} testID="clientes-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Clientes ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por nome, CPF/CNPJ ou telefone…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="clientes-search-input"
        />
      </View>

      {error ? (
        <Text style={styles.errorText} testID="clientes-error">{error}</Text>
      ) : null}

      <FlatList
        data={items}
        keyExtractor={(c) => String(c.codigo)}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 100 }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.empty}>Nenhum cliente encontrado.</Text>
          ) : null
        }
        ListFooterComponent={
          loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : null
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() =>
              router.push({
                pathname: "/cliente-form",
                params: { codigo: String(item.codigo) },
              })
            }
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }]}
            testID={`cliente-${item.codigo}`}
          >
            <View style={styles.cardIcon}>
              <Ionicons name="person-outline" size={20} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle} numberOfLines={1}>{item.nome}</Text>
              <Text style={styles.cardSub} numberOfLines={1}>
                {item.telefone || "Sem telefone"}
                {item.cgc_cpf ? ` · ${item.cgc_cpf}` : ""}
              </Text>
              {item.tipo_descricao ? (
                <Text style={styles.cardSub} numberOfLines={1}>Tipo: {item.tipo_descricao}</Text>
              ) : null}
            </View>
            {canNovoPedido ? (
              <Pressable
                onPress={(e) => {
                  e.stopPropagation();
                  router.push({
                    pathname: "/pedido-form",
                    params: { cliente: String(item.codigo), cliente_nome: item.nome },
                  });
                }}
                style={({ pressed }) => [styles.novoPedidoBtn, pressed && { opacity: 0.7 }]}
                hitSlop={6}
                testID={`cliente-${item.codigo}-novo-pedido`}
              >
                <Ionicons name="add-circle" size={28} color={colors.brandPrimary} />
                <Text style={styles.novoPedidoLabel}>Pedido</Text>
              </Pressable>
            ) : null}
          </Pressable>
        )}
      />

      {canNovoCliente ? (
        <Pressable
          onPress={() => router.push("/cliente-form")}
          style={({ pressed }) => [styles.fab, pressed && { opacity: 0.85, transform: [{ scale: 0.96 }] }]}
          hitSlop={8}
          testID="clientes-fab-new"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  backBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  headerTitle: {
    flex: 1, textAlign: "center", color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    marginHorizontal: spacing.lg, marginVertical: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  searchInput: {
    flex: 1, fontSize: 14, color: colors.onSurface, minHeight: 36,
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
  },
  cardIcon: {
    width: 40, height: 40, borderRadius: radius.md,
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.brandTertiary,
  },
  cardTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  errorText: {
    marginHorizontal: spacing.lg, marginBottom: spacing.sm,
    color: colors.error, fontSize: 13,
  },
  empty: {
    textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40,
  },
  fab: {
    position: "absolute",
    right: spacing.lg,
    bottom: spacing.xl,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
    shadowColor: "#000",
    shadowOpacity: 0.25, shadowRadius: 8, shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  novoPedidoBtn: {
    padding: 4,
    marginLeft: 4,
    alignItems: "center",
  },
  novoPedidoLabel: {
    fontSize: 10,
    color: colors.brandPrimary,
    fontWeight: "600",
    marginTop: -2,
  },
});
