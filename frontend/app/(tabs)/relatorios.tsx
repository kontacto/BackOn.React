import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

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
        <Text style={styles.headerTitle}>Relatórios</Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {vendas.length === 0 ? (
          <Text style={styles.sectionSub}>Nenhum relatório liberado para o seu grupo.</Text>
        ) : (
          <>
            <Text style={styles.sectionTitle}>Vendas</Text>
            {vendas.map((r) => (
              <Pressable
                key={r.label}
                onPress={() => r.route && router.push(r.route)}
                disabled={!r.route}
                style={({ pressed }) => [styles.card, pressed && r.route && { opacity: 0.85 }, !r.route && { opacity: 0.6 }]}
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
          </>
        )}
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
  headerTitle: { flex: 1, textAlign: "center", fontSize: 18, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md },
  sectionTitle: {
    fontSize: 12, fontWeight: "700", color: colors.muted,
    textTransform: "uppercase", letterSpacing: 0.6, marginBottom: spacing.xs,
  },
  sectionSub: { fontSize: 13, color: colors.muted, marginBottom: spacing.sm },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  cardIcon: {
    width: 44, height: 44, borderRadius: radius.md, backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  cardLabel: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardDesc: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
