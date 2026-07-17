// Aba "Transações" — nova área web-only pras versões COMPLETAS de Pedido
// e O.S. (distintas das versões rápidas de pré-venda usadas no mobile,
// `pedido-form.tsx`/`os-form.tsx`, que continuam inalteradas). Ver
// CLAUDE.md > "Transações Screens Strategy" pro racional completo.
//
// Mesmo padrão estrutural de app/(tabs)/cadastros.tsx: lista de `entries`
// filtrada por permissão via `can`, cada uma vira um card clicável.
// As telas de lista (`/pedidos`, `/os`) servem tanto a versão Mobile
// quanto a Completa — os cards abaixo apontam pra elas também; só o
// clique num item específico da lista ainda não abre nada pra quem só
// tem a permissão Completo, até a tela de edição completa existir de
// verdade (ver pedidos.tsx/os.tsx — decisão do usuário 2026-07-13).
import { useMemo } from "react";
import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Entry = {
  key: string;
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  visible: boolean;
};

export default function TransacoesScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Transações está disponível apenas no web."
        testID="transacoes-web-only"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "pedido-completo",
        label: "Pedido Completo",
        hint: "Versão completa do Pedido de Venda (back-office, web)",
        icon: "receipt-outline",
        route: "/pedidos",
        visible: can("PEDIDO_COMP.ABRIR"),
      },
      {
        key: "pedido-bar",
        label: "Pedido Bar",
        hint: "Pedido Bar e Restaurante",
        icon: "restaurant-outline",
        route: "/pedidos",
        visible: can("PEDIDO.ABRIR"),
      },
      {
        key: "os-completa",
        label: "O.S. Completa",
        hint: "Versão completa da Ordem de Serviço (back-office, web)",
        icon: "construct-outline",
        route: "/os",
        visible: can("OS_COMP.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="transacoes-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Transações</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="swap-horizontal-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhuma tela liberada para o seu grupo neste módulo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`transacoes-${e.key}`}
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
  safe: { flex: 1, backgroundColor: colors.background },
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
  scrollWeb: WEB_SCROLL_CENTER,
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
  emptyCardWeb: { minHeight: 220 },
  empty: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 8 },
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
  cardWeb: { flexBasis: "48%", minHeight: 96, paddingVertical: spacing.xl },
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
