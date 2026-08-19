// Aba "Transações" — nova área web-only pras versões COMPLETAS/GERAIS de
// Pedido e O.S. (distintas das versões rápidas de pré-venda usadas no
// mobile, `pedido-form.tsx`/`os-form.tsx`, que continuam inalteradas). Ver
// CLAUDE.md > "Transações Screens Strategy" pro racional completo.
//
// Mesmo padrão estrutural de app/(tabs)/cadastros.tsx: lista de `entries`
// filtrada por permissão via `can`, cada uma vira um card clicável.
//
// **Atualizado 2026-07-20, user-directed**: "Pedido Completo" foi renomeado
// "Pedido Geral" e ganhou lista PRÓPRIA (`pedido-lista.tsx`) — não abre
// mais em `/pedidos` (que agora é exclusiva do Pedido Bar). `pedido-lista.tsx`
// é desenhada pra ser compartilhada por futuras versões de Pedido também
// (qualquer uma que não seja do segmento Bar), não só o Pedido Geral.
//
// **Atualizado 2026-07-31**: "O.S. Completa" ganhou a mesma separação —
// tela própria `os-geral.tsx` + lista própria `os-lista.tsx` (Fase 1,
// núcleo — ver PENDENCIAS.md > "O.S. Completa"). `os.tsx` volta a ser
// exclusiva da O.S. Mobile, mesmo padrão já aplicado ao Pedido.
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

export default function TransacoesScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();

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
        key: "pedido-geral",
        label: "Pedido de Venda",
        hint: "Versão completa do Pedido de Venda (back-office, web)",
        icon: "receipt-outline",
        route: "/pedido-lista",
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
        route: "/os-lista",
        visible: can("OS_COMP.ABRIR"),
      },
      {
        key: "envio-terceiros",
        label: "Envio para Terceiros",
        hint: "Envio e retorno de equipamentos enviados para conserto externo",
        icon: "swap-vertical-outline",
        route: "/envio-terceiros",
        visible: can("RETIFICA.ABRIR"),
      },
      {
        key: "devolucao",
        label: "Gestor de Devolução",
        hint: "Devolução de itens de vendas pagas, com emissão de Vale de Devolução",
        icon: "return-down-back-outline",
        route: "/devolucao",
        // Módulo "Devolução" (controle_configuracao.devolucao) — mesmo
        // racional de `moduleOn` explícito já usado por outros cards deste
        // menu (Curva_abc, contratos, gestor_projetos).
        visible: moduleOn("devolucao") && can("DEVOLUCAO.ABRIR"),
      },
      {
        key: "movimentacoes",
        label: "Movimentações",
        hint: "Movimentação de Produtos e Requisição",
        icon: "swap-horizontal-outline",
        route: "/movimentacoes",
        visible: can("MOV_PRODUTOS.ABRIR") || can("REQUISICAO.ABRIR"),
      },
      {
        key: "inventario",
        label: "Inventário",
        hint: "Abertura, Digitação de Estoque, Fechamento e Cancelamento de balanço",
        icon: "cube-outline",
        route: "/inventario",
        visible: can("INVENTARIO.ABRIR"),
      },
      {
        key: "gestao-compras",
        label: "Gestão de Compras",
        hint: "Pedido de Compra, Curva ABC e Estoques, Ressuprimento",
        icon: "cart-outline",
        route: "/gestao-compras",
        // Módulo "Curva ABC" (controle_configuracao.Curva_abc) gateia todo
        // o submenu Compra — pedido explícito do usuário, 2026-07-19.
        // `moduleOn` explícito (não só `can`) porque master bypassa
        // `disabledTelas` dentro de `can()`, mas módulo vale igual pra
        // todo mundo (ver "Master Has Full Permission" no CLAUDE.md).
        visible: moduleOn("Curva_abc") && (can("PEDIDO_COMPRA.ABRIR") || can("CURVA_ABC.ABRIR") || can("GESTAO_COMPRAS.ABRIR")),
      },
      {
        key: "gestor-comandas",
        label: "Gestor de Comandas",
        hint: "Consulta de vendas finalizadas (comandas) e alteração/cancelamento",
        icon: "list-outline",
        route: "/gestor-comandas",
        visible: can("COMANDA.ABRIR"),
      },
      {
        key: "gestor-nfce",
        label: "Gestor NFCe",
        hint: "Consulta situação no SEFAZ, cancela, inutiliza numeração e valida contingência de NFC-e",
        icon: "receipt-outline",
        route: "/gestor-nfce",
        visible: can("GESTOR_NFCE.ABRIR"),
      },
      {
        key: "agenda",
        label: "Agenda",
        hint: "Grade semanal de atendimentos por profissional (módulo Clínica ou Assistência)",
        icon: "calendar-outline",
        route: "/agenda",
        // Módulo "Clínica" (controle_configuracao.CLINICA) OU "Assistência"
        // (controle_configuracao.Assistencia) — os dois habilitam a MESMA
        // tela/fluxo de Agenda, user-directed 2026-07-28 ("é só chamar a
        // tela"). Mesmo racional de `moduleOn` explícito acima.
        visible: (moduleOn("CLINICA") || moduleOn("Assistencia")) && can("AGENDA.ABRIR"),
      },
      {
        key: "projetos",
        label: "Gestor de Projetos",
        hint: "Vincula Pedidos, O.S. e Requisições a um projeto do cliente",
        icon: "briefcase-outline",
        route: "/projetos",
        // Módulo "gestor_projetos" (controle_configuracao.gestor_projetos)
        // — coluna própria, não reaproveita Assistência/Oficina. Ver
        // PENDENCIAS.md > "Gestor de Projetos".
        visible: moduleOn("gestor_projetos") && can("PROJETOS.ABRIR"),
      },
      {
        key: "contratos",
        label: "Contratos",
        hint: "Cadastro de contratos, itens, produtos disponíveis e tabelas auxiliares",
        icon: "document-text-outline",
        route: "/contratos",
        // Módulo "Contratos" (controle_configuracao.contratos) — pedido
        // explícito do usuário, 2026-07-19. Mesmo racional de `moduleOn`
        // explícito acima.
        visible:
          moduleOn("contratos") &&
          (can("CONTRATO.ABRIR") ||
            can("CONTR_PROD_DISP.ABRIR") ||
            can("TIPO_CONTRATO.ABRIR") ||
            can("TIPO_REAJUSTE.ABRIR") ||
            can("INDICE_REAJUSTE.ABRIR")),
      },
    ],
    [can, moduleOn]
  );

  const visible = entries.filter((e) => e.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="transacoes-screen">
      <View style={styles.header}>
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
