import { useMemo } from "react";
import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";

type Entry = {
  key: string;
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  visible: boolean;
};

// Aba Financeiro — web-only (ver CLAUDE.md > Platform Scope), mesmo tratamento já
// dado a Tabelas Auxiliares e Cadastro completo de cliente: some da navegação
// mobile (href: null em (tabs)/_layout.tsx) e é bloqueada por guard se acessada
// direto por rota.
export default function FinanceiroScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Financeiro está disponível apenas no web."
        testID="financeiro-web-only"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "contas-pagar",
        label: "Contas a Pagar",
        hint: "Duplicatas e vencimentos a pagar",
        icon: "arrow-up-circle-outline",
        route: "/contas-pagar",
        visible: can("CONTAS_PAGAR.ABRIR"),
      },
      {
        key: "contas-receber",
        label: "Contas a Receber",
        hint: "Duplicatas e vencimentos a receber",
        icon: "arrow-down-circle-outline",
        route: "/contas-receber",
        visible: can("CONTAS_RECEBER.ABRIR"),
      },
      {
        key: "fluxo-caixa",
        label: "Fluxo de Caixa",
        hint: "Movimentação e previsão de caixa",
        icon: "swap-vertical-outline",
        route: "/fluxo-caixa",
        // FLUXO_CAIXA é um MENU (guarda o Plano de Contas dentro), não uma TELA —
        // menus não têm ação "Abrir Tela" própria, então a visibilidade do tile
        // segue a permissão das telas filhas (mesmo padrão do tile "Tabelas
        // Auxiliares" em cadastros.tsx).
        visible: can("PLANO_CONTAS.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="financeiro-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Financeiro</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="cash-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhum item financeiro liberado para o seu grupo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`financeiro-${e.key}`}
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
          </View>
        </View>
      </ScrollView>
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
  headerLogo: { width: 64, height: 18 },
  headerLogoSpacer: { width: 64, height: 18 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 18, fontWeight: "600", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: { alignItems: "center", paddingHorizontal: spacing.xl, paddingVertical: spacing.xl },
  webFrame: { width: "100%", maxWidth: 1240 },
  gridWeb: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  emptyCard: {
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    padding: spacing.xl,
    marginTop: spacing.xl,
    borderRadius: radius.lg,
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
  },
  emptyCardWeb: {
    minHeight: 220,
  },
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
  cardWeb: {
    flexBasis: "48%",
    minHeight: 96,
    paddingVertical: spacing.xl,
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
