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

export default function CadastrosScreen() {
  const router = useRouter();
  const { can, moduleOn, isMaster } = usePermissions();

  const entries = useMemo<Entry[]>(
    () => [
      {
        key: "clientes",
        label: "Clientes",
        hint: "Cadastro e consulta de clientes",
        icon: "people-outline",
        route: "/clientes",
        visible: can("CLIENTE.ABRIR"),
      },
      {
        key: "clientes-rapido",
        label: "Cliente Rápido",
        hint: "Listagem de clientes com cadastro rápido",
        icon: "flash-outline",
        route: "/clientes?modo=rapido",
        visible: can("CLIENTE.ABRIR"),
      },
      {
        key: "produtos",
        label: "Produtos",
        hint: "Catálogo de produtos",
        icon: "cube-outline",
        route: "/produtos?tipo=P",
        visible: can("PRODUTO.ABRIR"),
      },
      {
        key: "fornecedores",
        label: "Fornecedores",
        hint: "Cadastro e manutenção de fornecedores",
        icon: "briefcase-outline",
        route: "/fornecedores",
        visible: Platform.OS === "web" && can("FORNECEDOR.ABRIR"),
      },
      {
        key: "servicos",
        label: "Serviços",
        hint: "Cadastro e manutenção de serviços",
        icon: "construct-outline",
        route: "/servicos",
        visible: Platform.OS === "web" && can("SERVICO.ABRIR") && moduleOn("servicos"),
      },
      {
        key: "veiculos",
        label: "Veículos",
        hint: "Cadastro de veículos da frota",
        icon: "car-outline",
        route: "/veiculos",
        // Liberada pelas flags de módulo "Cilindro" OU "Emite MDF-e"
        // (Configurações > Módulos e Recursos) OU pelo usuário master —
        // pedido explícito do usuário, diferente do padrão "servicos" (que
        // não abre exceção pro master).
        visible: Platform.OS === "web" && can("VEICULOS.ABRIR") && (moduleOn("Cilindro") || moduleOn("emite_mdfe") || isMaster),
      },
      {
        key: "funcionarios",
        label: "Funcionários",
        hint: "Cadastro de funcionários",
        icon: "id-card-outline",
        route: "/funcionarios",
        visible: Platform.OS === "web" && can("FUNCIONARIOS.ABRIR"),
      },
      {
        key: "contatos",
        label: "Contatos",
        hint: "Registro de contatos/leads, com previsão de retorno",
        icon: "call-outline",
        route: "/contatos",
        visible: Platform.OS === "web" && can("CONTATOS.ABRIR"),
      },
      {
        key: "telemarketing",
        label: "Telemarketing",
        hint: "Gestor de comunicação com o cliente (histórico, agendamento)",
        icon: "headset-outline",
        route: "/telemarketing",
        visible: Platform.OS === "web" && can("TELEMARKETING.ABRIR"),
      },
      {
        key: "equipamentos",
        label: "Equipamentos",
        hint: "Equipamentos vinculados a clientes, avulsos ou em contrato",
        icon: "construct-outline",
        route: "/equipamentos",
        visible: Platform.OS === "web" && can("EQUIPAMENTOS.ABRIR"),
      },
      {
        key: "notas-fiscais",
        label: "Notas Fiscais",
        hint: "Manutenção de Notas Fiscais (Fase 1 — sem emissão fiscal)",
        icon: "receipt-outline",
        route: "/notas-fiscais",
        visible: Platform.OS === "web" && can("NOTAS_FISCAIS.ABRIR"),
      },
      {
        key: "entrada-saida-caixa",
        label: "Entrada/Saída de Caixa",
        hint: "Sangrias, suprimentos e demais lançamentos do caixa operacional",
        icon: "swap-vertical-outline",
        route: "/entrada-saida-caixa",
        // Caixa OPERACIONAL da loja (recebe as vendas do dia) — não é o caixa
        // financeiro (Financeiro > Fluxo de Caixa). Pedido explícito do
        // usuário pra ficar em Cadastros, não em Financeiro.
        visible: Platform.OS === "web" && can("MOV_CAIXA.ABRIR"),
      },
      {
        key: "tabelas-aux",
        label: "Tabelas Auxiliares",
        hint: "Marcas e Modelos",
        icon: "list-outline",
        route: "/tabelas-auxiliares",
        visible: Platform.OS === "web" && (can("MARCAS.ABRIR") || can("MODELOS.ABRIR") || can("AREA.ABRIR") || can("AREA_ATUACAO.ABRIR")),
      },
    ],
    [can, moduleOn, isMaster]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="cadastros-screen">
      <View style={styles.header}>
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Cadastros</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          {visible.length === 0 ? (
            <View style={[styles.emptyCard, Platform.OS === "web" && styles.emptyCardWeb]}>
              <Ionicons name="albums-outline" size={28} color={colors.brandPrimary} />
              <Text style={styles.empty}>Nenhum cadastro liberado para o seu grupo.</Text>
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
                testID={`cadastros-${e.key}`}
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
