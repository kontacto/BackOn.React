import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

// Hub de Fluxo de Caixa (Financeiro) — mesmo padrão do hub Tabelas Auxiliares:
// lista de tiles que abrem sub-telas. Primeiro item: Plano de Contas
// (classes/sub_classes). Espaço para futuras telas de fluxo de caixa em si.
export default function FluxoCaixaScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Fluxo de Caixa está disponível apenas no web."
        testID="fluxo-caixa-web-only"
      />
    );
  }

  const tiles = [
    { key: "plano-contas", label: "Plano de Contas", hint: "Classes e subclasses de receitas e despesas", icon: "git-branch-outline" as const, route: "/plano-contas", visible: can("PLANO_CONTAS.ABRIR") },
    { key: "centro-custo", label: "Centro de Custo", hint: "Centros de custo e vínculo com o plano de contas", icon: "layers-outline" as const, route: "/centro-custo", visible: can("CENTRO_CUSTO.ABRIR") },
  ].filter((t) => t.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="fluxo-caixa-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Fluxo de Caixa</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.sectionCardWeb}>
            {tiles.map((t) => (
              <Pressable
                key={t.key}
                onPress={() => router.push(t.route as never)}
                style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
                testID={`fluxo-caixa-${t.key}`}
              >
                <Ionicons name={t.icon} size={24} color={colors.brandPrimary} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{t.label}</Text>
                  <Text style={styles.cardHint}>{t.hint}</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.muted} />
              </Pressable>
            ))}
            {tiles.length === 0 ? <Text style={styles.empty}>Sem permissão para estas telas.</Text> : null}
          </View>
        </View>
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
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  sectionCardWeb: {
    ...WEB_FILTER_CARD,
    maxWidth: 560,
    padding: spacing.md,
    gap: spacing.sm,
  },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.sm },
  cardTitle: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
});
