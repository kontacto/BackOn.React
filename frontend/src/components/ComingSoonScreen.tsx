// Placeholder para telas do módulo Financeiro ainda não implementadas
// (Contas a Pagar/Receber, Fluxo de Caixa) — sem backend/rota real ainda.
import { Image, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";

export default function ComingSoonScreen({
  title,
  icon,
  message = "Esta área está em desenvolvimento e será liberada em breve.",
  testID,
}: {
  title: string;
  icon: keyof typeof Ionicons.glyphMap;
  message?: string;
  testID?: string;
}) {
  const router = useRouter();

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID={testID}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>{title}</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.center}>
        <View style={styles.iconWrap}>
          <Ionicons name={icon} size={40} color={colors.brandPrimary} />
        </View>
        <Text style={styles.title}>Em desenvolvimento</Text>
        <Text style={styles.msg}>{message}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    paddingHorizontal: spacing.xl,
  },
  iconWrap: {
    width: 72,
    height: 72,
    borderRadius: radius.lg,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  msg: { fontSize: 14, color: colors.muted, textAlign: "center", lineHeight: 20, maxWidth: Platform.OS === "web" ? 420 : undefined },
});
