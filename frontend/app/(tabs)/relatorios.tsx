import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { usePermissions } from "@/src/permissions";

type ReportTile = {
  label: string;
  desc: string;
  icon: keyof typeof Ionicons.glyphMap;
  route: "/relatorio-descontos" | "/relatorio-pedidos" | "/relatorio-os" | "/relatorio-margem-lucro" | "/relatorio-caixa" | "/relatorio-caixa-analitico" | "/relatorio-entrada-saida-caixa" | "/relatorio-apuracao-vendas" | "/relatorio-resumo-venda" | "/relatorio-descontos-concedidos" | "/relatorio-itens-pedido" | "/relatorio-custo-os" | "/relatorio-itens-vendidos" | "/relatorio-busca-os" | "/relatorio-resumo-atendimento" | "/relatorio-produtos-reservados" | "/relatorio-estoque-nivel" | "/relatorio-estoque" | "/relatorio-movimentacao-itens" | "/relatorio-movimentacao-nivel" | "/relatorio-itens-funcionario" | "/relatorio-ranking-vendas" | "/relatorio-venda-cliente-produto" | "/relatorio-venda-nivel-funcionario" | "/relatorio-venda-regiao" | "/etiqueta-produto" | "/relatorio-listagem-clientes" | "/relatorio-inatividade-clientes" | "/mala-direta" | null;
  params?: Record<string, string>;
  perm: string | null;
};

// Cards de relatório agrupados por assunto — 2026-07-16, pedido explícito
// do usuário `[GLOBAL]`. Cada grupo é só um array de cards; a ORDEM
// alfabética (dos grupos entre si e dos cards dentro de cada grupo) é
// sempre calculada em runtime (ver `groups` no componente), nunca
// hardcoded aqui — um card/grupo novo adicionado a qualquer um destes
// arrays cai automaticamente na posição alfabética certa, sem precisar
// reordenar nada manualmente. Grupo sem nenhum card ainda (ex.: "Caixa")
// simplesmente não aparece na tela até ganhar o primeiro card.
const CAIXA_REPORTS: ReportTile[] = [
  {
    label: "Fechamento de Caixa",
    desc: "Recebimentos por forma de pagamento + entradas/saídas de caixa no período, por atendente e área de atuação.",
    icon: "cash-outline",
    route: "/relatorio-caixa",
    perm: "REL_CAIXA.ABRIR",
  },
  {
    label: "Caixa Analítico",
    desc: "Total de caixa, recebimentos e formas de pagamento quebrados por período — dia, semana, mês, trimestre, semestre ou ano.",
    icon: "bar-chart-outline",
    route: "/relatorio-caixa-analitico",
    perm: "REL_CX_ANALIT.ABRIR",
  },
  {
    label: "Entrada de Caixa",
    desc: "Lançamentos de entrada de caixa do período, agrupados por descrição e atendente.",
    icon: "arrow-down-circle-outline",
    route: "/relatorio-entrada-saida-caixa",
    params: { tipo: "E" },
    perm: "REL_ENT_CAIXA.ABRIR",
  },
  {
    label: "Saída de Caixa",
    desc: "Lançamentos de saída de caixa do período, agrupados por descrição e atendente.",
    icon: "arrow-up-circle-outline",
    route: "/relatorio-entrada-saida-caixa",
    params: { tipo: "S" },
    perm: "REL_SAI_CAIXA.ABRIR",
  },
  {
    label: "Apuração de Vendas - DRE",
    desc: "Faturamento mensal por categoria (Contratos, O.S., Vendas) com custo e margem. Fase 1 — sem despesas configuradas ainda.",
    icon: "stats-chart-outline",
    route: "/relatorio-apuracao-vendas",
    perm: "REL_APUR_VENDAS.ABRIR",
  },
  {
    label: "Resumo de Venda",
    desc: "Faturamento, custo e margem agregados por nível de produto no período, com o caminho completo da classificação.",
    icon: "layers-outline",
    route: "/relatorio-resumo-venda",
    perm: "REL_RES_VENDA.ABRIR",
  },
  {
    label: "Descontos Concedidos",
    desc: "Descontos concedidos por Pedido/O.S., item a item, com percentual e quem concedeu (Pedido).",
    icon: "pricetag-outline",
    route: "/relatorio-descontos-concedidos",
    perm: "REL_DESC_CONCED.ABRIR",
  },
];

const MARGENS_REPORTS: ReportTile[] = [
  {
    label: "Descontos & Margens",
    desc: "Consolidado por vendedor: vendas, descontos, custo e margem. Filtre por Pedido, OS ou Todos.",
    icon: "trending-down-outline",
    route: "/relatorio-descontos",
    perm: "REL_DESCONTOS.ABRIR",
  },
  {
    label: "Margem de Lucro",
    desc: "Faturamento e margem consolidados (multiempresa): Pedidos, O.S. e Comandas, por Empresa → DAV → Itens.",
    icon: "trending-up-outline",
    route: "/relatorio-margem-lucro",
    perm: null,
  },
];

const PRE_VENDAS_REPORTS: ReportTile[] = [
  {
    label: "Ordem de Serviço",
    desc: "Ordens de Serviço por período/vendedor/situação, com totais e margem.",
    icon: "construct-outline",
    route: "/relatorio-os",
    perm: "REL_OS.ABRIR",
  },
  {
    label: "Pedido de Venda",
    desc: "Pedidos por período/vendedor/situação. Expanda para ver descontos e margem.",
    icon: "documents-outline",
    route: "/relatorio-pedidos",
    perm: "REL_PEDIDOS.ABRIR",
  },
  {
    label: "Itens do Pedido",
    desc: "Quantidade vendida por produto (Pedido Fechado) no período, em Unidade de Compra — auxiliar de reposição.",
    icon: "cube-outline",
    route: "/relatorio-itens-pedido",
    perm: "REL_ITENS_PED.ABRIR",
  },
  {
    label: "Custo de O.S",
    desc: "Custo de itens de O.S. agrupado por Cliente ou Produto/Serviço no período.",
    icon: "calculator-outline",
    route: "/relatorio-custo-os",
    perm: "REL_CUSTO_OS.ABRIR",
  },
  {
    label: "Itens Vendidos O.S./Balcão",
    desc: "Quantidade e valor por produto individual (Pedido \"Balcão\" + consumo de O.S.) no período.",
    icon: "list-outline",
    route: "/relatorio-itens-vendidos",
    perm: "REL_ITENS_VEND.ABRIR",
  },
  {
    label: "Ordem de Serviço (Busca)",
    desc: "Busca de O.S. por Cliente, Data, Placa, Chassi, OS, Marca ou Modelo, com detalhe dos itens.",
    icon: "search-outline",
    route: "/relatorio-busca-os",
    perm: "REL_BUSCA_OS.ABRIR",
  },
  {
    label: "Resumo Atendimento",
    desc: "Uma linha por O.S. no período: técnico, horas trabalhadas e quebra por destino (Cliente Pg./Contrato/Garantia).",
    icon: "person-outline",
    route: "/relatorio-resumo-atendimento",
    perm: "REL_RES_ATEND.ABRIR",
  },
];

const VENDAS_REPORTS: ReportTile[] = [
  {
    label: "Itens por Funcionário",
    desc: "Quantidade e valor vendido no período, agrupado por Vendedor (Pedido) ou Executor (O.S.).",
    icon: "people-outline",
    route: "/relatorio-itens-funcionario",
    perm: "REL_ITENS_FUNC.ABRIR",
  },
  {
    label: "Ranking de Vendas",
    desc: "Top N por Cliente, Produto/Serviço ou Vendedor no período, ordenável por quantidade ou valor.",
    icon: "podium-outline",
    route: "/relatorio-ranking-vendas",
    perm: "REL_RANKING.ABRIR",
  },
  {
    label: "Venda por Cliente/Produto",
    desc: "Lista itemizada de vendas (Pedido + O.S.) no período, agrupável por Cliente ou por Produto/Serviço.",
    icon: "swap-horizontal-outline",
    route: "/relatorio-venda-cliente-produto",
    perm: "REL_VEN_CLIPRO.ABRIR",
  },
  {
    label: "Venda por Vendedor × Nível",
    desc: "Venda, custo e margem por nível de produto, dentro de um Vendedor ou Executor (ou todos agregados).",
    icon: "layers-outline",
    route: "/relatorio-venda-nivel-funcionario",
    perm: "REL_VEN_NIVFUN.ABRIR",
  },
  {
    label: "Venda por Região/Segmento",
    desc: "Venda agrupada por até 4 dimensões do cliente: Região, Segmento, Rota e Vendedor.",
    icon: "map-outline",
    route: "/relatorio-venda-regiao",
    perm: "REL_VEN_REGIAO.ABRIR",
  },
];

const ESTOQUE_REPORTS: ReportTile[] = [
  {
    label: "Produtos Reservados",
    desc: "Produtos com reserva ativa (Pedido/O.S.) — snapshot atual, sem período.",
    icon: "lock-closed-outline",
    route: "/relatorio-produtos-reservados",
    perm: "REL_PROD_RES.ABRIR",
  },
  {
    label: "Estoque por Nível",
    desc: "Unidades em estoque e valor a custo/venda, agrupado por nível de produto — snapshot atual.",
    icon: "layers-outline",
    route: "/relatorio-estoque-nivel",
    perm: "REL_ESTOQUE_NIV.ABRIR",
  },
  {
    label: "Estoque",
    desc: "Detalhe produto-a-produto (quantidade, custo, localização física) dentro de um nível escolhido.",
    icon: "cube-outline",
    route: "/relatorio-estoque",
    perm: "REL_ESTOQUE.ABRIR",
  },
  {
    label: "Movimentação de Itens",
    desc: "Ledger de movimentações de estoque no período — vendas, requisições, inventário e lançamentos manuais.",
    icon: "swap-vertical-outline",
    route: "/relatorio-movimentacao-itens",
    perm: "REL_MOV_ITENS.ABRIR",
  },
  {
    label: "Movimentações por Nível",
    desc: "Quantidade e valor movimentados por nível de produto, para um tipo de movimentação escolhido, no período.",
    icon: "git-branch-outline",
    route: "/relatorio-movimentacao-nivel",
    perm: "REL_MOV_NIVEL.ABRIR",
  },
  {
    label: "Etiqueta de Produto",
    desc: "Imprime etiquetas de estoque a partir de uma NF de entrada ou de produtos avulsos, em vários modelos de folha.",
    icon: "pricetags-outline",
    route: "/etiqueta-produto",
    perm: "REL_ETQ_PROD.ABRIR",
  },
];

const CLIENTES_REPORTS: ReportTile[] = [
  {
    label: "Listagem de Clientes",
    desc: "Busca clientes por código, CPF/CNPJ, nome, data de cadastro/nascimento ou tipo, com filtro Pessoa Física/Jurídica.",
    icon: "people-outline",
    route: "/relatorio-listagem-clientes",
    perm: "REL_LIST_CLI.ABRIR",
  },
  {
    label: "Inatividade de Clientes",
    desc: "Clientes sem compra no período, com ciclos de frequência, sub-checks de contrato e ação de reengajamento por WhatsApp.",
    icon: "alert-circle-outline",
    route: "/relatorio-inatividade-clientes",
    perm: "REL_INAT_CLI.ABRIR",
  },
  {
    label: "Mala Direta",
    desc: "Seleciona clientes (Todos/Aniversário/Cadastro/Tipo) e/ou fornecedores e envia mensagem em massa por WhatsApp ou E-mail.",
    icon: "megaphone-outline",
    route: "/mala-direta",
    perm: "MALA_DIRETA.ABRIR",
  },
];

const REPORT_GROUPS: { nome: string; cards: ReportTile[] }[] = [
  { nome: "Caixa", cards: CAIXA_REPORTS },
  { nome: "Clientes", cards: CLIENTES_REPORTS },
  { nome: "Estoque", cards: ESTOQUE_REPORTS },
  { nome: "Margens", cards: MARGENS_REPORTS },
  { nome: "Pré Vendas", cards: PRE_VENDAS_REPORTS },
  { nome: "Vendas", cards: VENDAS_REPORTS },
];

export default function RelatoriosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  // [Global] sempre em ordem alfabética — grupos entre si e cards dentro
  // de cada grupo, recalculado aqui em vez de fixado nos arrays acima, pra
  // qualquer adição futura já nascer na posição certa.
  const groups = REPORT_GROUPS
    .map((g) => ({
      nome: g.nome,
      cards: g.cards
        .filter((r) => !r.perm || can(r.perm))
        .sort((a, b) => a.label.localeCompare(b.label, "pt-BR")),
    }))
    .filter((g) => g.cards.length > 0)
    .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="relatorios-screen">
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Relatórios</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          <View style={Platform.OS === "web" ? styles.webShell : undefined}>
            {groups.length === 0 ? (
              <View style={[styles.emptyCard, Platform.OS === "web" && styles.emptyCardWeb]}>
                <Ionicons name="bar-chart-outline" size={28} color={colors.brandPrimary} />
                <Text style={styles.sectionSub}>Nenhum relatório liberado para o seu grupo.</Text>
              </View>
            ) : (
              groups.map((g, gi) => (
                <View key={g.nome} style={gi > 0 ? styles.groupSpacing : undefined}>
                  <Text style={styles.sectionTitle}>{g.nome}</Text>
                  <View style={Platform.OS === "web" ? styles.gridWeb : undefined}>
                    {g.cards.map((r) => (
                      <Pressable
                        key={r.label}
                        onPress={() => r.route && router.push((r.params ? { pathname: r.route, params: r.params } : r.route) as any)}
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
                </View>
              ))
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
  groupSpacing: { marginTop: spacing.lg },
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
