// Hub "Gestão de Compras" (2026-07-18, user-directed) — aberto pelo Card
// "Gestão de Compras" em Transações. Mesmo submenu "Transações > Compra"
// do MDI legado: Pedido de Compra, Curva ABC e Estoques, Gestão de
// Compras. Prioridade confirmada pelo usuário: Gestão de Compras
// (Ressuprimento) e Curva ABC e Estoques têm tela real; Pedido de Compra
// fica placeholder — ver PENDENCIAS.md > "Gestão de Compras".
import { useMemo } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
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

export default function GestaoComprasScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Gestão de Compras está disponível apenas no web."
        testID="gestao-compras-web-only"
      />
    );
  }

  if (!moduleOn("Curva_abc")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Curva ABC/Compras está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="gestao-compras-module-off"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "gestao-compras-ressuprimento",
        label: "Gestão de Compras",
        hint: "Relatório de ressuprimento — o que precisa comprar, por curva ABC e posição de estoque",
        icon: "bar-chart-outline",
        route: "/gestao-compras-ressuprimento",
        visible: can("GESTAO_COMPRAS.ABRIR"),
      },
      {
        key: "curva-abc",
        label: "Curva ABC e Estoques",
        hint: "Classifica seus produtos por importância de venda e recalcula mínimo/máximo de estoque",
        icon: "analytics-outline",
        route: "/curva-abc",
        visible: can("CURVA_ABC.ABRIR"),
      },
      {
        key: "pedido-compra",
        label: "Pedido de Compra",
        hint: "Emissão de pedido formal ao fornecedor",
        icon: "document-text-outline",
        route: "/pedido-compra",
        visible: can("PEDIDO_COMPRA.ABRIR"),
      },
      {
        key: "cotacao-compra",
        label: "Cotação de Compra",
        hint: "Compare preços de fornecedores por produto e marque o vencedor",
        icon: "swap-vertical-outline",
        route: "/cotacao-compra",
        visible: can("COTACAO_COMPRA.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="gestao-compras-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Gestão de Compras</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="cart-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhuma tela liberada para o seu grupo neste módulo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`gestao-compras-${e.key}`}
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
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webFrame: { width: "100%", maxWidth: 1240 },
  gridWeb: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  emptyCard: {
    alignItems: "center", justifyContent: "center", gap: spacing.sm,
    padding: spacing.xl, marginTop: spacing.xl, borderRadius: radius.lg,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  emptyCardWeb: { minHeight: 220 },
  empty: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 8 },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.lg,
  },
  cardWeb: { flexBasis: "31%", minHeight: 96, paddingVertical: spacing.xl },
  cardIcon: {
    width: 48, height: 48, borderRadius: radius.md, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  cardLabel: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
