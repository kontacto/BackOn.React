// Painel de Cilindros — dashboard do módulo, mesmo padrão estrutural de
// app/(tabs)/posto-combustivel.tsx. Módulo de segmento (indústria/locação
// de gás), gated por controle_configuracao.Cilindro (coluna que já
// existia antes desta migração). Legado: FrmManCil.frm — ver
// PENDENCIAS.md > "Cilindros" pro relatório de rastreio completo e o
// plano faseado (Fase 1: Cadastro/Consulta — esta rodada. Fase 2:
// Clientes x Cilindro + Cilindro/Nº Série. Fase 3: Borderô de
// Cilindros — consulta em tela + exportação, sem impressão formatada).
//
// Só o card de Cadastro/Consulta é exibido por ora — os outros 3 entram
// conforme as fases seguintes forem implementadas (não linkar card pra
// tela que ainda não existe).
import { useMemo } from "react";
import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";

type Entry = {
  key: string;
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: string;
  visible: boolean;
};

export default function CilindrosScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "cadastro",
        label: "Cadastro de Cilindros",
        hint: "Cadastro e consulta de cilindros (capacidade, pressão, padrão)",
        icon: "flame-outline",
        route: "/cilindro-cadastro",
        visible: can("CILINDRO.ABRIR"),
      },
      {
        key: "viagens",
        label: "Viagens",
        hint: "Saída/retorno de cilindros — itens, fechamento e estoque",
        icon: "bus-outline",
        route: "/viagem-cadastro",
        visible: can("VIAGEM.ABRIR"),
      },
      {
        key: "bordero",
        label: "Borderô de Cilindros",
        hint: "Consulta de saídas/retornos por cliente + exportação Excel",
        icon: "document-text-outline",
        route: "/bordero-cilindros",
        visible: can("BORDERO_CIL.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="cilindros-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Painel de Cilindros</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, Platform.OS === "web" && styles.emptyCardWeb]}>
              <Ionicons name="flame-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>
                Nenhuma tela liberada para o seu grupo neste módulo.{"\n"}Fale com o
                administrador em Configurações {">"} Permissões.
              </Text>
            </View>
          ) : null}
          <View style={Platform.OS === "web" ? styles.gridWeb : undefined}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [
                  styles.card,
                  Platform.OS === "web" && styles.cardWeb,
                  pressed && { opacity: 0.85 },
                ]}
                testID={`cilindros-${e.key}`}
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
