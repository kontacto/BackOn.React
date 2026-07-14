import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { usePermissions } from "@/src/permissions";

type ReportTile = {
  label: string;
  desc: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: "/relatorio-descontos" | "/relatorio-pedidos" | "/relatorio-os" | "/relatorio-margem-lucro" | null;
  perm: string | null;
};

// Relatórios do grupo "Vendas".
const VENDAS_REPORTS: ReportTile[] = [
  {
    label: "Margem de Lucro",
    desc: "Faturamento e margem consolidados (multiempresa): Pedidos, O.S. e Comandas, por Empresa → DAV → Itens.",
    icon: "trending-up-outline",
    route: "/relatorio-margem-lucro",
    perm: null,
  },
  {
    label: "Relatório de Pedidos",
    desc: "Pedidos por período/vendedor/situação. Expanda para ver descontos e margem.",
    icon: "documents-outline",
    route: "/relatorio-pedidos",
    perm: "REL_PEDIDOS.ABRIR",
  },
  {
    label: "Descontos & Margens",
    desc: "Consolidado por vendedor: vendas, descontos, custo e margem. Filtre por Pedido, OS ou Todos.",
    icon: "trending-down-outline",
    route: "/relatorio-descontos",
    perm: "REL_DESCONTOS.ABRIR",
  },
  {
    label: "Relatório de OS",
    desc: "Ordens de Serviço por período/vendedor/situação, com totais e margem.",
    icon: "construct-outline",
    route: "/relatorio-os",
    perm: "REL_OS.ABRIR",
  },
];

export default function RelatoriosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const vendas = VENDAS_REPORTS
    .filter((r) => !r.perm || can(r.perm))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="relatorios-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Relatórios</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          <View style={Platform.OS === "web" ? styles.webShell : undefined}>
            {vendas.length === 0 ? (
              <View style={[styles.emptyCard, Platform.OS === "web" && styles.emptyCardWeb]}>
                <Ionicons name="bar-chart-outline" size={28} color={colors.brandPrimary} />
                <Text style={styles.sectionSub}>Nenhum relatório liberado para o seu grupo.</Text>
              </View>
            ) : (
              <>
                <Text style={styles.sectionTitle}>Vendas</Text>
                <View style={Platform.OS === "web" ? styles.gridWeb : undefined}>
                  {vendas.map((r) => (
                    <Pressable
                      key={r.label}
                      onPress={() => r.route && router.push(r.route)}
                      disabled={!r.route}
                      style={({ pressed }) => [
                        styles.card,
                        Platform.OS === "web" && styles.cardWeb,
                        pressed && r.route && { opacity: 0.85 },
                        !r.route && { opacity: 0.6 },
                      ]}
                      testID={`relatorio-${r.label}`}
                    >
                      <View style={styles.cardIcon}>
                        <Ionicons name={r.icon} size={22} color={colors.brandPrimary} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.cardLabel}>{r.label}</Text>
                        <Text style={styles.cardDesc}>{r.desc}</Text>
                      </View>
                      {r.route ? <Ionicons name="chevron-forward" size={20} color={colors.muted} /> : null}
                    </Pressable>
                  ))}
                </View>
              </>
            )}
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
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 64, height: 18 },
  headerLogoSpacer: { width: 64, height: 18 },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 18, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: { alignItems: "center", paddingHorizontal: spacing.xl, paddingVertical: spacing.xl },
  webFrame: { width: "100%", maxWidth: 1240 },
  webShell: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
  },
  sectionTitle: {
    fontSize: 12, fontWeight: "700", color: colors.muted,
    textTransform: "uppercase", letterSpacing: 0.6, marginBottom: spacing.xs,
  },
  sectionSub: { fontSize: 13, color: colors.muted, marginBottom: spacing.sm },
  emptyCard: {
    alignItems: "center",
    justifyContent: "center",
    gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
    marginTop: spacing.md,
  },
  emptyCardWeb: {
    minHeight: 220,
  },
  gridWeb: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
    alignItems: "stretch",
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  cardWeb: {
    flexBasis: "48%",
    minHeight: 98,
    paddingVertical: spacing.lg,
  },
  cardIcon: {
    width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  cardLabel: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardDesc: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
