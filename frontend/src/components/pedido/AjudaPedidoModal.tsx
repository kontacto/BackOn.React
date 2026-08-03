// Modal único de Ajuda — reúne, num só lugar, a explicação de cada botão/
// campo da tela em linguagem de usuário final (garçom/caixa/gerente), em
// vez de espalhar um tooltip por botão. Aberto pelo ícone "i" no cabeçalho
// (`PedidoHeader.onHelp`). Pedido explícito do usuário, 2026-07-20 — ver
// CLAUDE.md > "Modo Didático" (regra 4).
//
// Componente e conteúdo (`titulo`/`itens`) são parametrizáveis — compartilhado
// entre Pedido Bar (`pedido-form.tsx`, usa o default `PEDIDO_BAR_AJUDA_ITENS`
// abaixo) e Pedido Geral/Completo (`pedido-geral.tsx`, monta sua própria
// lista reaproveitando/filtrando a do Bar) em vez de duplicar o componente
// inteiro por tela — pedido explícito do usuário, 2026-07-20 ("tente usar
// as mesmas funções para não replicar o mesmo código entre telas").
import { Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as ps } from "./styles";

const isWeb = Platform.OS === "web";

export type HelpIcon =
  | { lib: "ion"; name: React.ComponentProps<typeof Ionicons>["name"] }
  | { lib: "mci"; name: React.ComponentProps<typeof MaterialCommunityIcons>["name"] };

export type HelpItem = {
  titulo: string;
  texto: string;
  icon: HelpIcon;
  cor?: string;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  // Título do modal ("Ajuda — {titulo}") e lista de itens explicados —
  // default é o conteúdo do Pedido Bar (`PEDIDO_BAR_AJUDA_ITENS`).
  titulo?: string;
  itens?: HelpItem[];
};

export const PEDIDO_BAR_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Gravar",
    texto: "Salva o vendedor, cliente, forma de pagamento e demais dados do cabeçalho do pedido. Precisa ser feito antes de incluir itens num pedido novo.",
    icon: { lib: "ion", name: "checkmark" },
  },
  {
    titulo: "Adicionar",
    texto: "Inclui um novo produto ou serviço na lista de itens do pedido.",
    icon: { lib: "ion", name: "add" },
    cor: colors.onBrandPrimary,
  },
  {
    titulo: "Tx Serviço",
    texto: "Inclui (ou atualiza) automaticamente a taxa de serviço de 10% sobre o valor do pedido. Clicar de novo só atualiza o valor, não duplica a linha.",
    icon: { lib: "mci", name: "room-service" },
  },
  {
    titulo: "Distribuir",
    texto: "Divide o pedido em dois ou mais, movendo itens (ou parte de um item) para um pedido novo — útil para separar a conta de uma mesa entre pessoas diferentes.",
    icon: { lib: "ion", name: "git-branch-outline" },
  },
  {
    titulo: "Fechar Pedido",
    texto: "Trava a lista de itens e dá baixa no estoque dos produtos vendidos. Depois de fechado, o pedido ainda pode ser reaberto se precisar corrigir algo.",
    icon: { lib: "ion", name: "lock-closed-outline" },
    cor: colors.success,
  },
  {
    titulo: "Faturar Pedido",
    texto: "Conclui a venda: gera a comanda de recebimento e marca o pedido como Faturado. Se o pedido ainda não foi fechado, o sistema fecha e fatura de uma vez só. Depois de faturado, não é mais possível reabrir ou cancelar.",
    icon: { lib: "ion", name: "cash-outline" },
    cor: colors.brandPrimary,
  },
  {
    titulo: "Reabrir",
    texto: "Volta um pedido Fechado para Aberto, desfazendo a baixa de estoque — use quando precisar corrigir itens depois de ter fechado por engano.",
    icon: { lib: "ion", name: "lock-open-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Cancelar",
    texto: "Cancela o pedido (Aberto ou Fechado). Se já estava Fechado, desfaz a baixa de estoque. Ação definitiva, não pode ser desfeita.",
    icon: { lib: "ion", name: "close-circle-outline" },
    cor: colors.error,
  },
  {
    titulo: "Anexo",
    texto: "Anexa fotos ou documentos relacionados a este pedido (ex.: foto de um comprovante), guardados junto ao cadastro do cliente.",
    icon: { lib: "ion", name: "attach-outline" },
  },
  {
    titulo: "Imprimir",
    texto: "Mostra uma prévia do recibo do pedido inteiro, pronta para imprimir.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Imprimir Item (em cada linha)",
    texto: "Imprime só aquele item, num ticket reduzido — útil para mandar um pedido específico direto para a cozinha ou o bar.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Etiqueta vermelha (nos itens)",
    texto: "Indica que aquele item recebeu desconto. Passe o mouse ou toque para ver o valor descontado.",
    icon: { lib: "ion", name: "pricetag" },
    cor: colors.error,
  },
  {
    titulo: "Descontos",
    texto: "Mostra o total de desconto já concedido em itens deste pedido, com o detalhe de cada um.",
    icon: { lib: "ion", name: "pricetag" },
    cor: colors.error,
  },
  {
    titulo: "Margem",
    texto: "Abre o relatório de margem e descontos deste pedido — quanto foi vendido, com que desconto e qual a margem restante.",
    icon: { lib: "ion", name: "bar-chart-outline" },
  },
  {
    titulo: "Desconto geral",
    texto: "Aplica um desconto sobre o total do pedido (não item por item).",
    icon: { lib: "ion", name: "cash-outline" },
  },
  {
    titulo: "Pedido Totalizado",
    texto: "Mostra a lista de itens agrupada por produto — útil para conferir rapidamente quantas unidades de cada produto foram pedidas ao todo.",
    icon: { lib: "ion", name: "receipt-outline" },
  },
  {
    titulo: "Pedido Entregue",
    texto: "Marca que este pedido já foi entregue ao cliente. Grava assim que marcado, sem precisar clicar em Gravar.",
    icon: { lib: "ion", name: "checkbox" },
  },
  {
    titulo: "Campo Tipo",
    texto: "Define se este é um pedido de Mesa, Comanda, Balcão ou Entrega. Para clientes que já são uma mesa/comanda física do estabelecimento, esse valor é sempre o tipo do próprio cliente e não pode ser alterado aqui.",
    icon: { lib: "ion", name: "grid-outline" },
  },
  {
    titulo: "Campo Referência",
    texto: "Campo livre para anotar um número ou observação de identificação do pedido. Quando o pedido vem de uma divisão de conta (Distribuir), mostra o número do pedido de origem e fica travado.",
    icon: { lib: "ion", name: "bookmark-outline" },
  },
];

export default function AjudaPedidoModal({ visible, onClose, titulo = "Pedido Bar", itens = PEDIDO_BAR_AJUDA_ITENS }: Props) {
  if (!visible) return null;
  return (
    <View
      style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: "rgba(0,0,0,0.45)",
        alignItems: "center", justifyContent: isWeb ? "center" : "flex-end",
        paddingHorizontal: isWeb ? spacing.xl : 0,
        zIndex: 1000,
      }}
    >
      <Pressable
        style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
        onPress={onClose}
      />
      <View
        style={[
          ps.modalCard,
          isWeb && ps.modalCardWebCompact,
          { maxHeight: "82%" },
        ]}
      >
        <View style={ps.modalHeader}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="information-circle-outline" size={20} color={colors.brandPrimary} />
            <Text style={ps.modalTitle}>Ajuda — {titulo}</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={8} testID="ajuda-pedido-fechar">
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>
        <Text style={{ fontSize: 13, color: colors.muted, marginBottom: spacing.md }}>
          O que cada botão e campo desta tela faz:
        </Text>
        <ScrollView style={{ maxHeight: 480 }}>
          <View style={{ gap: spacing.md }}>
            {itens.map((item) => (
              <View
                key={item.titulo}
                style={{
                  flexDirection: "row", gap: spacing.sm,
                  paddingBottom: spacing.md,
                  borderBottomWidth: 1, borderBottomColor: colors.border,
                }}
              >
                <View
                  style={{
                    width: 30, height: 30, borderRadius: radius.pill,
                    alignItems: "center", justifyContent: "center", flexShrink: 0,
                    backgroundColor: colors.brandTertiary,
                  }}
                >
                  {item.icon.lib === "mci" ? (
                    <MaterialCommunityIcons name={item.icon.name} size={16} color={item.cor || colors.brandPrimary} />
                  ) : (
                    <Ionicons name={item.icon.name} size={16} color={item.cor || colors.brandPrimary} />
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, marginBottom: 2 }}>
                    {item.titulo}
                  </Text>
                  <Text style={{ fontSize: 13, color: colors.muted, lineHeight: 18 }}>
                    {item.texto}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}
