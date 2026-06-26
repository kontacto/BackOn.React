import { useMemo } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";

type Entry = {
  key: string;
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  visible: boolean;
};

export default function CadastrosScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "clientes",
        label: "Clientes",
        hint: "Cadastro e consulta de clientes",
        icon: "people-outline",
        route: "/clientes",
        visible: can("CLIENTE.ABRIR"),
      },
      {
        key: "produtos",
        label: "Produtos",
        hint: "Catálogo de produtos",
        icon: "cube-outline",
        route: "/produtos?tipo=P",
        visible: can("PRODUTO.ABRIR"),
      },
      {
        key: "servicos",
        label: "Serviços",
        hint: "Catálogo de serviços",
        icon: "construct-outline",
        route: "/produtos?tipo=S",
        visible: can("PRODUTO.ABRIR") && moduleOn("servicos"),
      },
      {
        key: "tabelas-aux",
        label: "Tabelas Auxiliares",
        hint: "Marcas e Modelos",
        icon: "list-outline",
        route: "/tabelas-auxiliares",
        visible: can("MARCAS.ABRIR") || can("MODELOS.ABRIR"),
      },
    ],
    [can, moduleOn]
  );

  const visible = entries.filter((e) => e.visible);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="cadastros-screen">
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Cadastros</Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {visible.length === 0 ? (
          <Text style={styles.empty}>Nenhum cadastro liberado para o seu grupo.</Text>
        ) : null}
        {visible.map((e) => (
          <Pressable
            key={e.key}
            onPress={() => router.push(e.route as never)}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
            testID={`cadastros-${e.key}`}
          >
            <View style={styles.cardIcon}>
              <Ionicons name={e.icon} size={24} color={colors.brandPrimary} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.cardLabel}>{e.label}</Text>
              <Text style={styles.cardHint}>{e.hint}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.muted} />
          </Pressable>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  headerTitle: { color: colors.onBrandPrimary, fontSize: 18, fontWeight: "600", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  empty: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 40 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  cardIcon: {
    width: 48,
    height: 48,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  cardLabel: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 13, color: colors.muted, marginTop: 2 },
});
