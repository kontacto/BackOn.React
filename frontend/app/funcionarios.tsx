import { useCallback, useState } from "react";
import { ActivityIndicator, FlatList, Image, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type FuncionarioItem = {
  codigo: number;
  nome_guerra: string;
  nome: string;
  situacao: string;
  funcao_descricao: string;
};

// Cadastro > Funcionários (tabela `funcionarios` + sub-tabelas). Legado:
// FrmManPro ("Manutenção de Funcionários"). Lista simples aqui; o cadastro
// completo (abas Comissões/Dados/Horários/Ausências/Especialidades) fica em
// `funcionario-completo.tsx`, mesmo padrão de Cliente (lista enxuta +
// editor completo em tela própria).
export default function FuncionariosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Funcionários está disponível apenas no web."
        testID="funcionarios-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [items, setItems] = useState<FuncionarioItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (c: Connection, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/funcionarios-cadastro?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const session = await getSession();
        if (!session) {
          router.replace("/login");
          return;
        }
        const conns = await listConnections();
        const c = conns.find((x) => x.empresa === session.empresa) ?? null;
        setConn(c);
        if (!c) {
          fb.showError("Conexão não encontrada.");
          return;
        }
        load(c, search);
      })();
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [load])
  );

  const onSearchChange = (v: string) => {
    setSearch(v);
    if (conn) load(conn, v);
  };

  const canGravar = can("FUNCIONARIOS.GRAVAR");

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="funcionarios-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn} testID="funcionarios-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Funcionários</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={[styles.filterBox, styles.filterBoxWeb]}>
          <Ionicons name="search" size={16} color={colors.muted} />
          <TextInput
            value={search}
            onChangeText={onSearchChange}
            placeholder="Buscar por codinome ou nome…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            testID="funcionarios-search"
          />
        </View>

        <FlatList
          style={styles.listWeb}
          contentContainerStyle={[styles.listContent, styles.listContentWeb]}
          data={items}
          keyExtractor={(i) => String(i.codigo)}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum funcionário cadastrado.</Text> : null}
          ListFooterComponent={loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => router.push({ pathname: "/funcionario-completo", params: { codigo: String(item.codigo) } })}
              style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }]}
              testID={`funcionario-${item.codigo}`}
            >
              <View style={styles.cardIcon}>
                <Ionicons name="person-outline" size={20} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle} numberOfLines={1}>{item.nome_guerra} · {item.nome}</Text>
                <Text style={styles.cardSub} numberOfLines={1}>
                  {item.funcao_descricao || "Sem função"} {item.situacao && item.situacao !== "A" ? `· ${item.situacao}` : ""}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={20} color={colors.muted} />
            </Pressable>
          )}
        />
      </View>

      {canGravar ? (
        <Pressable
          onPress={() => router.push({ pathname: "/funcionario-completo" })}
          style={({ pressed }) => [styles.fab, pressed && { opacity: 0.85 }]}
          hitSlop={8}
          testID="funcionarios-fab-new"
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
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  webShell: { flex: 1, alignItems: "center", width: "100%" },
  filterBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    marginTop: spacing.md, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  filterBoxWeb: { width: "100%", maxWidth: 620 },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface, minHeight: 36 },
  listWeb: { width: "100%", maxWidth: 620, alignSelf: "center" },
  listContent: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, paddingBottom: 100 },
  listContentWeb: { width: "100%", maxWidth: 620, alignSelf: "center" },
  empty: { textAlign: "center", color: colors.muted, marginTop: 40 },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
  },
  cardIcon: { width: 40, height: 40, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandTertiary },
  cardTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  fab: {
    position: "absolute", right: spacing.lg, bottom: spacing.xl, width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4,
  },
});
