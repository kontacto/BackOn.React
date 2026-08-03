// Modal único de Ajuda do Painel de Inventário — mesmo padrão já usado em
// Pedido Bar/Geral (`AjudaPedidoModal.tsx`): um ícone "i" no cabeçalho abre
// um modal reunindo a explicação de cada botão/campo em linguagem de
// usuário final, em vez de espalhar tooltip por botão (ver CLAUDE.md >
// "Modo Didático"). Componente próprio (não reaproveita AjudaPedidoModal)
// porque Inventário não é do domínio Pedido — mesmo formato, conteúdo
// independente.
import { Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";

const isWeb = Platform.OS === "web";

export type AjudaInventarioItem = {
  titulo: string; texto: string; icon: React.ComponentProps<typeof Ionicons>["name"]; cor?: string;
};

const ITENS_PAINEL: AjudaInventarioItem[] = [
  {
    titulo: "Abrir Inventário",
    texto:
      "Inicia um novo balanço de estoque, num dos 3 tipos: Geral pré-carrega automaticamente todo o estoque atual — qualquer item que não for digitado de novo é ajustado a zero no Fechamento. Parcial (padrão) não pré-carrega nada — só entram os itens que você realmente digitar, o resto do catálogo não é tocado nem no Fechamento. Contábil também pré-carrega tudo (assumindo o saldo do sistema como já conferido), mas nunca altera o estoque de verdade — é só um registro informativo.",
    icon: "lock-open-outline",
  },
  {
    titulo: "Digitação de Estoque",
    texto:
      "Tela para contar os produtos fisicamente: busque o produto pelo código (interno, de fábrica ou de barras) ou pelo chassi (veículos), informe a quantidade contada e grave. Só fica disponível com um balanço aberto.",
    icon: "create-outline",
  },
  {
    titulo: "Fechar Inventário",
    texto:
      "Encerra o balanço. Em balanços do tipo Geral, TODO o catálogo é conferido — item cuja contagem for diferente do estoque do sistema (inclusive um item nunca digitado, que conta como \"contagem zero\") tem o estoque ajustado automaticamente, com o lançamento registrado no histórico de movimentações. No tipo Parcial, só os itens que você digitou entram nesse ajuste — o resto do catálogo fica intocado. Balanços do tipo Contábil não alteram o estoque em nenhum dos dois casos.",
    icon: "checkmark-done-outline",
    cor: colors.success,
  },
  {
    titulo: "Cancelar Inventário",
    texto:
      "Descarta o balanço aberto e tudo o que já foi contado nele, sem nenhum efeito no estoque. Use quando o balanço foi aberto por engano ou precisa recomeçar do zero.",
    icon: "close-circle-outline",
    cor: colors.error,
  },
];

export default function AjudaInventarioModal({
  visible, onClose, titulo = "Ajuda — Inventário", itens = ITENS_PAINEL,
}: {
  visible: boolean; onClose: () => void; titulo?: string; itens?: AjudaInventarioItem[];
}) {
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
      <Pressable style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }} onPress={onClose} />
      <View
        style={{
          width: "100%",
          maxWidth: isWeb ? 560 : undefined,
          maxHeight: "82%",
          backgroundColor: colors.surface,
          borderRadius: radius.lg,
          borderWidth: isWeb ? 1 : 0,
          borderColor: colors.border,
          padding: spacing.lg,
        }}
      >
        <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
            <Ionicons name="information-circle-outline" size={20} color={colors.brandPrimary} />
            <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{titulo}</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={8} testID="ajuda-inventario-fechar">
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>
        <Text style={{ fontSize: 13, color: colors.muted, marginBottom: spacing.md }}>
          O que cada ação desta tela faz:
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
                  <Ionicons name={item.icon} size={16} color={item.cor || colors.brandPrimary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, marginBottom: 2 }}>
                    {item.titulo}
                  </Text>
                  <Text style={{ fontSize: 13, color: colors.muted, lineHeight: 18 }}>{item.texto}</Text>
                </View>
              </View>
            ))}
          </View>
        </ScrollView>
      </View>
    </View>
  );
}
