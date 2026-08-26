// Hub "Contratos" (2026-07-19, user-directed) — aberto pelo Card
// "Contratos" em app/(tabs)/transacoes.tsx. Fase A da migração de
// FrmManTPC/FrmManRea/FrmManInd/FrmConPDI/FrmManContra.frm. Faturar
// Contratos (2026-07-20) e Envio de Cobrança (2026-08-25) já implementados
// — ver PENDENCIAS.md > "Contratos". Mesmo padrão de app/movimentacoes.tsx.
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

export default function ContratosScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contratos está disponível apenas no web."
        testID="contratos-web-only"
      />
    );
  }

  if (!moduleOn("contratos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Contratos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="contratos-module-off"
      />
    );
  }

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "contrato",
        label: "Contratos",
        hint: "Cadastro de contratos, itens, centro de custo e reajuste",
        icon: "document-text-outline",
        route: "/contrato-lista",
        visible: can("CONTRATO.ABRIR"),
      },
      {
        key: "faturar",
        label: "Faturar Contratos",
        hint: "Selecionar contratos do período, faturar e gerar Recibo",
        icon: "cash-outline",
        route: "/contrato-faturar",
        visible: can("FATURAR_CONTR.ABRIR"),
      },
      {
        key: "envio-cobranca",
        label: "Envio de Cobrança",
        hint: "Enviar e-mail de cobrança das mensalidades já faturadas",
        icon: "mail-outline",
        route: "/contrato-envio-cobranca",
        visible: can("ENVIO_COBRANCA.ABRIR"),
      },
      {
        key: "produtos-disponiveis",
        label: "Produtos Disponíveis",
        hint: "Produtos/equipamentos/serviços liberados para uso em contrato",
        icon: "cube-outline",
        route: "/contrato-produtos-disponiveis",
        visible: can("CONTR_PROD_DISP.ABRIR"),
      },
      {
        key: "tipo-contrato",
        label: "Tipo de Contrato",
        hint: "Tabela auxiliar de tipos de contrato",
        icon: "pricetag-outline",
        route: "/contrato-tipo",
        visible: can("TIPO_CONTRATO.ABRIR"),
      },
      {
        key: "tipo-reajuste",
        label: "Tipo de Reajuste",
        hint: "Periodicidade do reajuste (mensal, anual, ...)",
        icon: "calendar-outline",
        route: "/contrato-tipo-reajuste",
        visible: can("TIPO_REAJUSTE.ABRIR"),
      },
      {
        key: "indice-reajuste",
        label: "Índices de Reajuste",
        hint: "IGPM, IPCA e demais índices usados no reajuste",
        icon: "trending-up-outline",
        route: "/contrato-indice-reajuste",
        visible: can("INDICE_REAJUSTE.ABRIR"),
      },
    ],
    [can]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="contratos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Contratos</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webFrame}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, styles.emptyCardWeb]}>
              <Ionicons name="document-text-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhuma tela liberada para o seu grupo neste módulo.</Text>
            </View>
          ) : null}
          <View style={styles.gridWeb}>
            {visible.map((e) => (
              <Pressable
                key={e.key}
                onPress={() => router.push(e.route as never)}
                style={({ pressed }) => [styles.card, styles.cardWeb, pressed && { opacity: 0.85 }]}
                testID={`contratos-${e.key}`}
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
