import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";

export default function TabelasAuxiliaresScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  const tiles = [
    { key: "marcas", label: "Marcas", hint: "Marcas de veículos e produtos", icon: "pricetag-outline" as const, route: "/marcas", visible: can("MARCAS.ABRIR") },
    { key: "modelos", label: "Modelos", hint: "Modelos por marca", icon: "car-outline" as const, route: "/modelos", visible: can("MODELOS.ABRIR") },
  ].filter((t) => t.visible);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="tabelas-aux-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Tabelas Auxiliares</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={styles.scroll}>
        {tiles.map((t) => (
          <Pressable
            key={t.key}
            onPress={() => router.push(t.route)}
            style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
            testID={`tabaux-${t.key}`}
          >
            <Ionicons name={t.icon} size={24} color={colors.brandPrimary} />
            <View style={{ flex: 1 }}>
              <Text style={styles.cardTitle}>{t.label}</Text>
              <Text style={styles.cardHint}>{t.hint}</Text>
            </View>
            <Ionicons name="chevron-forward" size={20} color={colors.muted} />
          </Pressable>
        ))}
        {tiles.length === 0 ? <Text style={styles.empty}>Sem permissão para estas tabelas.</Text> : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  cardTitle: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
});
