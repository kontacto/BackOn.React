import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, Text, View } from "react-native";
import { Platform } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/principal/styles";
import { useDashboard } from "@/src/components/principal/useDashboard";
import WelcomeHero from "@/src/components/principal/WelcomeHero";
import ModuleTiles from "@/src/components/principal/ModuleTiles";
import SituacaoFilter from "@/src/components/principal/SituacaoFilter";
import TotalsCards from "@/src/components/principal/TotalsCards";
import PedidosTable from "@/src/components/principal/PedidosTable";
import EstoqueAlertasCard, { hasAlertasEstoque } from "@/src/components/principal/EstoqueAlertasCard";
import ProjetosResumoCard from "@/src/components/principal/ProjetosResumoCard";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";

// "Modo Didático" (CLAUDE.md) — ícone único de Ajuda no cabeçalho, reunindo
// a explicação de cada seção da Tela Principal em linguagem de usuário
// final. Reaproveita o mesmo `AjudaPedidoModal` já usado no Pedido Bar/
// Geral (componente genérico, não é específico de Pedido) em vez de criar
// um modal novo do zero. Pedido explícito do usuário, 2026-07-20.
const PRINCIPAL_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Totais de Hoje",
    texto: "Quantidade de Pedidos e Ordens de Serviço abertos hoje, mais o valor vendido em produtos e serviços no dia.",
    icon: { lib: "ion", name: "bar-chart-outline" },
  },
  {
    titulo: "Margem média do dia",
    texto: "Diferença entre o valor vendido e o custo de reposição dos produtos — mostra quanto sobrou de lucro bruto no dia, descontados os descontos concedidos.",
    icon: { lib: "ion", name: "trending-up" },
  },
  {
    titulo: "Alerta — Estoque Zerado ou Negativo",
    texto: "Produtos sem nenhuma unidade disponível — risco real de não conseguir vender por falta de estoque. Toque no card pra ver a lista.",
    icon: { lib: "ion", name: "alert-circle" },
    cor: colors.error,
  },
  {
    titulo: "Alerta — Estoque Mínimo",
    texto: "Produtos que já caíram abaixo da quantidade mínima cadastrada — comprar com urgência.",
    icon: { lib: "ion", name: "warning" },
    cor: colors.error,
  },
  {
    titulo: "Alerta — Ressuprimento",
    texto: "Produtos no momento certo de iniciar a compra, antes que faltem de vez.",
    icon: { lib: "ion", name: "trending-down" },
    cor: colors.warning,
  },
  {
    titulo: "Atualizar (alertas de estoque)",
    texto: "Os números do card são compartilhados por todo mundo com acesso gerencial — não são recalculados a cada visita, pra não deixar o sistema lento. Toque em \"Atualizar\", ao lado do título, pra recalcular de verdade; o resultado (e o horário mostrado no botão) passa a valer pra todos os outros usuários também, até a próxima atualização. Mesmo desatualizado, o alerta continua valendo: se apareceu, é porque em algum momento aquele produto realmente ficou baixo — vale a pena conferir.",
    icon: { lib: "ion", name: "refresh-outline" },
  },
  {
    titulo: "Por que atualizar a Curva ABC periodicamente",
    texto: "A Curva ABC recalcula, com base nas vendas recentes, o estoque mínimo, o ponto de ressuprimento e o consumo médio de cada produto. Sem gerar essa atualização a cada poucos meses, os alertas acima passam a usar números antigos — podem ficar quietos quando na verdade falta produto, ou pedir compra de itens que já não vendem como antes. Atualize em Transações > Gestão de Compras > Curva ABC e Estoques.",
    icon: { lib: "ion", name: "refresh-outline" },
  },
  {
    titulo: "Módulos",
    texto: "Atalhos pras principais áreas do sistema — toque em um card pra abrir aquele módulo.",
    icon: { lib: "ion", name: "grid-outline" },
  },
];

export default function PrincipalScreen() {
  const d = useDashboard();
  const isWeb = Platform.OS === "web";
  const [ajudaOpen, setAjudaOpen] = useState(false);

  if (d.loading || !d.session) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="principal-screen">
      <View style={styles.header}>
        <View style={styles.headerLeft} />
        <View style={styles.headerCenter}>
          <Text style={[styles.headerSub, isWeb && styles.headerSubWeb]} numberOfLines={1}>
            {d.fantasia || d.session.empresa}
          </Text>
        </View>
        <View style={[styles.headerRight, { width: 190, flexDirection: "row", alignItems: "center", justifyContent: "flex-end", gap: 8 }]}>
        <Pressable
          onPress={() => setAjudaOpen(true)}
          hitSlop={12}
          testID="principal-ajuda-button"
        >
          <Ionicons name="information-circle-outline" size={20} color={colors.onBrandPrimary} />
        </Pressable>
        <Pressable
          onPress={d.handleLogout}
          style={({ pressed }) => [styles.logoutBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="principal-logout-button"
        >
          <Ionicons name="log-out-outline" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.logoutLabel}>Sair</Text>
        </Pressable>
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          {Platform.OS === "web" ? (
            <>
              <WelcomeHero
                empresa={d.session.empresa}
                logo={d.session.logo}
                displayName={d.displayName}
                nomeGuerra={d.nomeGuerra}
                classe={d.classe}
              />

              {/* Alertas de Estoque ao lado dos tiles de módulo (pedido
                  explícito do usuário, 2026-07-20: "colocar o card ao lado
                  do card de Pedidos") — os tiles ficam compactos (160px
                  cada) e sobra bastante largura na mesma linha. "Tela
                  Principal" e "Alertas de Estoque" viram os títulos de cada
                  coluna, lado a lado na mesma linha (pedido explícito do
                  usuário: "coloque a label de estoque na mesma linha do
                  label tela principal") — cada um é o primeiro filho da sua
                  própria coluna, com o mesmo marginTop/marginBottom, então
                  alinham exatamente na mesma altura. */}
              <View style={{ flexDirection: "row", gap: spacing.md, width: "100%", maxWidth: 920, alignSelf: "center", alignItems: "flex-start" }}>
                <View style={{ flexShrink: 0 }}>
                  <Text style={[styles.sectionTitle, { marginTop: 0, marginBottom: spacing.xs }]}>Pré-Vendas</Text>
                  <ModuleTiles compact />
                </View>
                {hasAlertasEstoque(d.alertasEstoque) ? (
                  <EstoqueAlertasCard
                    resumo={d.alertasEstoque}
                    compact
                    atualizadoEm={d.alertasAtualizadoEm}
                    carregando={d.alertasCarregando}
                    onAtualizar={d.podeAtualizarAlertasEstoque ? d.reloadAlertasEstoque : undefined}
                  />
                ) : null}
                {d.resumoProjetos?.ativo ? (
                  <View style={{ flexShrink: 0 }}>
                    <Text style={[styles.sectionTitle, { marginTop: 0, marginBottom: spacing.xs }]}>Projetos</Text>
                    <ProjetosResumoCard resumo={d.resumoProjetos} />
                  </View>
                ) : null}
              </View>

              <SituacaoFilter value={d.situacaoFiltro} onChange={d.handleSituacao} />

              <TotalsCards
                totais={d.totais}
                dashLoading={d.dashLoading}
                showTotais={d.showTotais}
                showMargem={d.showMargem}
                showDescontos={d.showDescontos}
              />

              <PedidosTable
                movimento={d.movimento}
                dashLoading={d.dashLoading}
                totalMovimento={d.totalMovimento}
                situacaoFiltro={d.situacaoFiltro}
              />
            </>
          ) : (
            <>
              <WelcomeHero
                empresa={d.session.empresa}
                logo={d.session.logo}
                displayName={d.displayName}
                nomeGuerra={d.nomeGuerra}
                classe={d.classe}
              />

              <Text style={styles.sectionTitle}>Pré-Vendas</Text>

              <ModuleTiles />

              <EstoqueAlertasCard
                resumo={d.alertasEstoque}
                atualizadoEm={d.alertasAtualizadoEm}
                carregando={d.alertasCarregando}
                onAtualizar={d.podeAtualizarAlertasEstoque ? d.reloadAlertasEstoque : undefined}
              />

              <ProjetosResumoCard resumo={d.resumoProjetos} />

              <SituacaoFilter value={d.situacaoFiltro} onChange={d.handleSituacao} />

              <TotalsCards
                totais={d.totais}
                dashLoading={d.dashLoading}
                showTotais={d.showTotais}
                showMargem={d.showMargem}
                showDescontos={d.showDescontos}
              />

              <PedidosTable
                movimento={d.movimento}
                dashLoading={d.dashLoading}
                totalMovimento={d.totalMovimento}
                situacaoFiltro={d.situacaoFiltro}
              />
            </>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal
        visible={ajudaOpen}
        onClose={() => setAjudaOpen(false)}
        titulo="Tela Principal"
        itens={PRINCIPAL_AJUDA_ITENS}
      />
    </SafeAreaView>
  );
}
