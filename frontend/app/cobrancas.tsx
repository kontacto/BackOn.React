// Hub "Cobranças" (2026-07-23, user-directed) — aberto pelo Card
// "Cobranças" em app/(tabs)/financeiro.tsx. Reúne as telas do módulo
// financeiro de cobrança (Bancos hoje; Fase 2 — CNAB/API — e futuras
// telas de cobrança entram aqui também). Mesmo padrão de
// app/contratos.tsx/app/movimentacoes.tsx.
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

export default function CobrancasScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cobranças está disponível apenas no web."
        testID="cobrancas-web-only"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "bancos",
        label: "Bancos",
        hint: "Cadastro de bancos para cobrança (boleto/CNAB/API)",
        icon: "business-outline",
        route: "/bancos",
        visible: can("BANCOS.ABRIR"),
      },
      {
        key: "geracao-boletos",
        label: "Geração de Boletos",
        hint: "Gera remessa/planilha de títulos e importa o retorno do banco (2 abas)",
        icon: "document-text-outline",
        route: "/geracao-boletos",
        visible: can("GERACAO_BOLETOS.ABRIR") || can("RETORNO_BANC.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="cobrancas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Cobranças</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="business-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhuma tela liberada para o seu grupo neste módulo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`cobrancas-${e.key}`}
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
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerSpacer: { width: 40 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
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
