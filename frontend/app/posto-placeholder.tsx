// Placeholder genérico pros cards do Painel Posto de Combustível ainda não
// migrados (ver PENDENCIAS.md > "Posto de Combustível" — 13 telas do
// legado VB6, pasta Posto, planejadas mas não implementadas ainda). Cada
// card do painel aponta pra cá com seu próprio título via querystring
// até a tela real ser construída, uma de cada vez.
import { Image, Platform, Pressable, Text, View, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

export default function PostoPlaceholderScreen() {
  const router = useRouter();
  const { titulo } = useLocalSearchParams<{ titulo?: string }>();
  const label = titulo || "Posto de Combustível";

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="posto-placeholder-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>{label}</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={[styles.center, Platform.OS === "web" && styles.centerWeb]}>
        <View style={styles.card}>
          <Ionicons name="construct-outline" size={40} color={colors.brandPrimary} />
          <Text style={styles.title}>Tela em construção</Text>
          <Text style={styles.msg}>
            "{label}" ainda não foi migrada do sistema legado. Acompanhe o progresso em PENDENCIAS.md.
          </Text>
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  centerWeb: WEB_SCROLL_CENTER,
  card: {
    alignItems: "center",
    gap: spacing.sm,
    padding: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    maxWidth: 420,
  },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  msg: { fontSize: 14, color: colors.muted, textAlign: "center", lineHeight: 20 },
});
