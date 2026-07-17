// Painel Posto de Combustível — dashboard do módulo, mesmo padrão
// estrutural de app/(tabs)/cadastros.tsx (lista de `entries` filtrada por
// permissão via `can`, cada uma vira um card clicável). Ordenação: os
// cards Combustível/Bomba/Ilha/Tanque ficam agrupados nessa ordem fixa
// (pedido explícito do usuário, 2026-07-14) — os demais continuam em
// ordem alfabética por label, como o resto do app ("Card List Ordering"
// no CLAUDE.md). Ver a montagem de `visible` mais abaixo.
//
// As 13 telas abaixo vêm da pasta VB6 legada "Posto"
// (C:\Desenv\VB6\...\SQLSERVER\Posto), que TEM telas exclusivas do
// segmento (correção 2026-07-13 — um levantamento anterior, registrado
// em PENDENCIAS.md, tinha concluído o contrário por engano). Todas as 13
// já foram migradas (ver PENDENCIAS.md pro detalhe de cada uma — Mov.
// Encerrantes/Fechamento/Reabertura de Turno/Aferições dependiam de
// modelar "DATESIST"/"turno aberto agora" como leitura simples e fresca
// de `controle.data_movimento`/`controle.turno_movimento`, nunca como
// global — ver CLAUDE.md > "Porting VB6 global state").
// O catálogo de permissões (`POSTO_*` em permissoes_service.py) tem a
// entrada de cada uma, então o gating por card já funciona.
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

export default function PostoCombustivelScreen() {
  const router = useRouter();
  const { can } = usePermissions();

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "bombas",
        label: "Bombas",
        hint: "Cadastro de bombas (ilha, ponto, posição, tanque, combustível)",
        icon: "water-outline",
        route: "/posto-bombas",
        visible: can("POSTO_BOMBA.ABRIR"),
      },
      {
        key: "mov-encerrantes",
        label: "Mov. Encerrantes",
        hint: "Movimentação de bombas e encerrantes por turno",
        icon: "swap-vertical-outline",
        route: "/posto-mov-encerrantes",
        visible: can("POSTO_ENCERR.ABRIR"),
      },
      {
        key: "afericoes",
        label: "Aferições/Despesas",
        hint: "Baixa de abastecimentos, aferições e despesas",
        icon: "clipboard-outline",
        route: "/posto-afericoes",
        visible: can("POSTO_AFERICAO.ABRIR"),
      },
      {
        key: "fechamento-turno",
        label: "Fechamento Turno",
        hint: "Fechamento do turno de movimento do posto",
        icon: "lock-closed-outline",
        route: "/posto-fechamento-turno",
        visible: can("POSTO_FEC_TURNO.ABRIR"),
      },
      {
        key: "reabertura-turno",
        label: "Reabertura Turno",
        hint: "Reabertura do turno de movimento do posto",
        icon: "lock-open-outline",
        route: "/posto-reabertura-turno",
        visible: can("POSTO_REA_TURNO.ABRIR"),
      },
      {
        key: "metas",
        label: "Metas Combustível",
        hint: "Metas de venda por grupo de combustível/mês/ano",
        icon: "trending-up-outline",
        route: "/posto-meta",
        visible: can("POSTO_META.ABRIR"),
      },
      {
        key: "combustiveis",
        label: "Combustíveis",
        hint: "Cadastro de combustíveis (preço, estoque)",
        icon: "flask-outline",
        route: "/posto-combustiveis",
        visible: can("POSTO_COMBUST.ABRIR"),
      },
      {
        key: "estoque",
        label: "Estoque Combustível",
        hint: "Estoque de combustível por data/turno",
        icon: "cube-outline",
        route: "/posto-estoque",
        visible: can("POSTO_ESTOQUE.ABRIR"),
      },
      {
        key: "custo",
        label: "Custo Combustível",
        hint: "Histórico de entrada/saída/custo do combustível",
        icon: "cash-outline",
        route: "/posto-custo",
        visible: can("POSTO_CUSTO.ABRIR"),
      },
      {
        key: "ilhas",
        label: "Ilhas",
        hint: "Vínculo de funcionário, ilha, turno e data",
        icon: "location-outline",
        route: "/posto-ilhas",
        visible: can("POSTO_ILHA.ABRIR"),
      },
      {
        key: "tanques",
        label: "Tanques",
        hint: "Cadastro de tanques (capacidade, combustível)",
        icon: "layers-outline",
        route: "/posto-tanques",
        visible: can("POSTO_TANQUE.ABRIR"),
      },
      {
        key: "tanque-estoque",
        label: "Tanque/Estoque",
        hint: "Movimentação de estoque por tanque",
        icon: "swap-horizontal-outline",
        route: "/posto-tanque-estoque",
        visible: can("POSTO_TQ_EST.ABRIR"),
      },
      {
        key: "tanque-nf",
        label: "Tanque/Nota Fiscal",
        hint: "Vínculo entre tanque e nota fiscal de compra de combustível",
        icon: "receipt-outline",
        route: "/posto-tanque-nf",
        visible: can("POSTO_TQ_NF.ABRIR"),
      },
    ],
    [can]
  );

  // Combustível/Bomba/Ilha/Tanque ficam agrupados nesta ordem fixa, por
  // pedido explícito do usuário (2026-07-14) — única exceção à ordenação
  // alfabética deste painel (ver CLAUDE.md > "Card List Ordering").
  const GRUPO_ORDEM = ["combustiveis", "bombas", "ilhas", "tanques"];
  const grupo = GRUPO_ORDEM.map((k) => entries.find((e) => e.key === k))
    .filter((e): e is Entry => !!e && e.visible);
  const resto = entries
    .filter((e) => e.visible && !GRUPO_ORDEM.includes(e.key))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));
  const visible = [...grupo, ...resto];

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="posto-combustivel-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Painel Posto de Combustível</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, Platform.OS === "web" && styles.emptyCardWeb]}>
              <Ionicons name="water-outline" size={28} color={colors.brandPrimary} />
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
                testID={`posto-combustivel-${e.key}`}
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
