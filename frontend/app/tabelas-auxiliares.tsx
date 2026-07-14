import { Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

export default function TabelasAuxiliaresScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Tabelas Auxiliares está disponível apenas no web."
        testID="tabelas-aux-web-only"
      />
    );
  }

  const tiles = [
    { key: "area", label: "Área", hint: "Áreas de estoque (Loja/Depósito)", icon: "business-outline" as const, route: "/area", visible: can("AREA.ABRIR") },
    { key: "area-atuacao", label: "Área de Atuação", hint: "Classificação de Pedidos e O.S.", icon: "git-network-outline" as const, route: "/area-atuacao", visible: can("AREA_ATUACAO.ABRIR") },
    { key: "marcas", label: "Marcas", hint: "Marcas de veículos e produtos", icon: "pricetag-outline" as const, route: "/marcas", visible: can("MARCAS.ABRIR") },
    { key: "modelos", label: "Modelos", hint: "Modelos por marca", icon: "car-outline" as const, route: "/modelos", visible: can("MODELOS.ABRIR") },
    { key: "forma-pagamento", label: "Forma de Pagamento", hint: "Formas de pagamento e condições de recebimento", icon: "card-outline" as const, route: "/forma-pagamento", visible: can("FORMA_PAGAMENTO.ABRIR") },
    { key: "grupo-usuario", label: "Grupo de Usuário", hint: "Grupos/funções de usuário e permissões de cadastro", icon: "people-circle-outline" as const, route: "/grupo-usuario", visible: can("GRUPO_USUARIO.ABRIR") },
    { key: "grupo-mercadologico", label: "Grupo Mercadológico", hint: "Árvore de níveis para classificar produtos e serviços", icon: "git-commit-outline" as const, route: "/grupo-mercadologico", visible: can("GRUPO_MERCAD.ABRIR") },
    { key: "cfop", label: "Código Fiscal de Operações", hint: "CFOP e vínculos de importação de NF-e por XML", icon: "swap-horizontal-outline" as const, route: "/cfop", visible: can("CFOP.ABRIR") },
    { key: "cfop-pis-cofins", label: "Cfop x Pis/Cofins", hint: "Tributação de PIS/COFINS por CFOP e grupo", icon: "calculator-outline" as const, route: "/cfop-pis-cofins", visible: can("CFOP_PISCOF.ABRIR") },
    { key: "cores", label: "Cores", hint: "Cores de veículos e produtos", icon: "color-palette-outline" as const, route: "/cores", visible: can("CORES.ABRIR") },
    { key: "icms", label: "Icms", hint: "Situações tributárias de ICMS (CST/CSOSN)", icon: "receipt-outline" as const, route: "/icms", visible: can("ICMS.ABRIR") },
    { key: "origem", label: "Origem", hint: "Origem da mercadoria (padrão NFe)", icon: "earth-outline" as const, route: "/origem", visible: can("ORIGEM.ABRIR") },
    { key: "regioes", label: "Regiões", hint: "Regiões geográficas de atendimento", icon: "map-outline" as const, route: "/regioes", visible: can("REGIOES.ABRIR") },
    { key: "rotas", label: "Rotas", hint: "Rotas de entrega/atendimento por região", icon: "navigate-outline" as const, route: "/rotas", visible: can("ROTAS.ABRIR") },
    { key: "segmentos", label: "Segmentos", hint: "Segmentos de mercado do cliente", icon: "layers-outline" as const, route: "/segmentos", visible: can("SEGMENTOS.ABRIR") },
    { key: "situacao", label: "Situação", hint: "Situações genéricas usadas em diversos cadastros", icon: "checkmark-circle-outline" as const, route: "/situacao", visible: can("SITUACAO.ABRIR") },
    { key: "tamanho", label: "Tamanhos", hint: "Tamanhos/grades de produtos", icon: "resize-outline" as const, route: "/tamanho", visible: can("TAMANHO.ABRIR") },
    { key: "taxas", label: "Taxas", hint: "Alíquotas de ICMS/PIS/COFINS/IBS/CBS por UF, CFOP e movimentação (NFe/NFSe e NFCe)", icon: "calculator-outline" as const, route: "/taxas", visible: can("TAXAS.ABRIR") || can("TAXAS_NFCE.ABRIR") },
    { key: "grupo-pis-cofins", label: "Grupo PIS/COFINS", hint: "Agrupamento de produtos/serviços para PIS e COFINS", icon: "document-text-outline" as const, route: "/grupo-pis-cofins", visible: can("GRUPO_PISCOF.ABRIR") },
    { key: "tipo-cliente", label: "Tipo Clientes/Fornecedores", hint: "Classificação do cliente (usado no Cadastro Completo)", icon: "person-outline" as const, route: "/tipo-cliente", visible: can("TIPO_CLIENTE.ABRIR") },
    { key: "tipo-doc", label: "Tipo de Documento", hint: "Tipos de documento fiscal/administrativo", icon: "document-outline" as const, route: "/tipo-doc", visible: can("TIPO_DOC.ABRIR") },
    { key: "status-os", label: "Status de O.S.", hint: "Status de andamento da Ordem de Serviço", icon: "flag-outline" as const, route: "/status-os", visible: can("STATUS_OS.ABRIR") },
    { key: "funcoes", label: "Funções", hint: "Funções de funcionários e suas permissões", icon: "briefcase-outline" as const, route: "/funcoes", visible: can("FUNCOES.ABRIR") },
    { key: "mensagens", label: "Mensagens", hint: "Textos padronizados para observação de nota fiscal/orçamento", icon: "chatbox-ellipses-outline" as const, route: "/mensagens", visible: can("MENSAGENS.ABRIR") },
    { key: "mensagens-pdv", label: "Mensagens PDV", hint: "Mensagens promocionais impressas no Cupom Fiscal", icon: "receipt-outline" as const, route: "/mensagens-pdv", visible: can("MENSAGENS_PDV.ABRIR") },
    { key: "num-serie", label: "Números de Série", hint: "Controle de série por produto (disponibilidade e detalhes)", icon: "barcode-outline" as const, route: "/num-serie", visible: can("NUM_SERIE.ABRIR") },
    { key: "tipo-mov", label: "Tipo de Movimentação", hint: "Tipos de entrada/saída de estoque e suas regras fiscais/contábeis", icon: "swap-vertical-outline" as const, route: "/tipo-mov", visible: can("TIPO_MOV.ABRIR") },
    { key: "tipo-mov-mensagens", label: "Tipo Mov x Mensagem", hint: "Mensagens vinculadas a cada Tipo de Movimentação", icon: "link-outline" as const, route: "/tipo-mov-mensagens", visible: can("TIPO_MOV_MSG.ABRIR") },
    { key: "tipo-os", label: "Tipo de Pré-Venda", hint: "Classificação usada em Pedidos e O.S.", icon: "pricetags-outline" as const, route: "/tipo-os", visible: can("TIPO_OS.ABRIR") },
    { key: "executor-padrao", label: "Executor Padrão OS", hint: "Executor sugerido por nível de produto/serviço", icon: "person-outline" as const, route: "/executor-padrao", visible: can("EXECUTOR_PADRAO.ABRIR") },
    { key: "tipo-peca", label: "Tipo de Produto", hint: "Classificação de produtos (revenda, consumo, imobilizado)", icon: "cube-outline" as const, route: "/tipo-peca", visible: can("TIPO_PECA.ABRIR") },
    { key: "tipo-os-prod", label: "Tipo Destino Itens OS", hint: "Destino dos itens de O.S. (Cliente, Garantia, Interno)", icon: "swap-horizontal-outline" as const, route: "/tipo-os-prod", visible: can("TIPO_OS_PROD.ABRIR") },
    { key: "tipo-servico", label: "Tipo de Serviço", hint: "Classificação de serviços (próprio, terceiro)", icon: "construct-outline" as const, route: "/tipo-servico", visible: can("TIPO_SERVICO.ABRIR") },
    { key: "tributacao", label: "Tributação", hint: "Códigos CST/CSOSN de ICMS", icon: "document-text-outline" as const, route: "/tributacao", visible: can("TRIBUTACAO.ABRIR") },
    { key: "unidade-medida", label: "Unidade de Medida", hint: "Unidades de medida de produtos (CX, DZ, MT etc.)", icon: "cube-outline" as const, route: "/unidade-medida", visible: can("UNID.ABRIR") },
  ].filter((t) => t.visible).sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="tabelas-aux-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tabelas Auxiliares</Text>
        <View style={{ width: 40 }} />
      </View>
      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.sectionCard, isWeb && styles.sectionCardWeb]}>
            {tiles.map((t) => (
              <Pressable
                key={t.key}
                onPress={() => router.push(t.route)}
                style={({ pressed }) => [styles.card, pressed && { opacity: 0.85 }]}
                testID={`tabaux-${t.key}`}
              >
                <Ionicons name={t.icon} size={24} color={colors.brandPrimary} />
                <View style={{ flex: 1 }}>
                  <Text style={styles.cardTitle}>{t.label}</Text>
                  <Text style={styles.cardHint}>{t.hint}</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.muted} />
              </Pressable>
            ))}
            {tiles.length === 0 ? <Text style={styles.empty}>Sem permissão para estas tabelas.</Text> : null}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  sectionCard: { gap: spacing.sm },
  sectionCardWeb: {
    ...WEB_FILTER_CARD,
    maxWidth: 560,
    padding: spacing.md,
  },
  card: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.sm },
  cardTitle: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  cardHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
});
