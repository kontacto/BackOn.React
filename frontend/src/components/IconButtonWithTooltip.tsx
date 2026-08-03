// Botão de ícone com tooltip no hover (web) — extraído de
// `pedido/PedidoHeader.tsx`'s `HeaderIconButton` local pra ser reaproveitado
// por qualquer tela, não só as de Pedido. Regra `[GLOBAL]` reforçada
// 2026-07-21, user-directed: "incluir no modo didático, os tooltip em
// todos os botões do tipo ícones" — todo botão-ícone (sem rótulo de texto
// ao lado) ganha esse tooltip, além do ícone único de Ajuda/modal
// consolidado (as duas coisas coexistem, não uma substitui a outra).
import { useState } from "react";
import { GestureResponderEvent, Platform, Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors } from "@/src/theme/colors";

const isWeb = Platform.OS === "web";

type Props = {
  icon: React.ComponentProps<typeof Ionicons>["name"];
  label: string;
  // Recebe o evento (não só `() => void`) pra quem precisa de
  // `e.stopPropagation()` — caso de um ícone aninhado dentro de outro
  // elemento também clicável (ex.: ícone de linha dentro da linha inteira
  // do item, que também abre o item ao tocar). Callers que não precisam do
  // evento continuam funcionando normalmente, sem mudança.
  onPress: (e: GestureResponderEvent) => void;
  size?: number;
  color?: string;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  tooltipAlign?: "left" | "right";
  testID?: string;
  // Bolinha de sinalização no canto (ex.: "existe pelo menos 1 fornecedor
  // vinculado") — puramente visual, não intercepta toque.
  badge?: boolean;
  badgeColor?: string;
};

export default function IconButtonWithTooltip({
  icon, label, onPress, size = 18, color = colors.brandPrimary, disabled, style, tooltipAlign = "right", testID,
  badge = false, badgeColor = colors.success,
}: Props) {
  const [hover, setHover] = useState(false);
  // Limpa o hover no clique, antes de disparar a ação — sem isso, uma ação
  // que abre um diálogo nativo do navegador (ex.: imprimir/`window.print()`)
  // pode interromper o processamento de eventos e nunca disparar o
  // `onHoverOut` desse ícone quando o diálogo fecha; o tooltip fica "preso"
  // visível, e some somado ao de outro ícone que o mouse passou a
  // sobrepor depois — achado ao vivo 2026-07-21 (2 tooltips juntos após
  // clicar em "Reimprimir documento fiscal").
  const handlePress = (e: GestureResponderEvent) => {
    setHover(false);
    onPress(e);
  };
  return (
    // `zIndex` só reordena entre IRMÃOS do MESMO pai — um `zIndex` alto só
    // na tooltip (filha) não escapa por cima de um botão-ícone vizinho,
    // porque esse vizinho é irmão deste `View` (o pai da tooltip), não da
    // tooltip em si. Sem elevar o próprio wrapper durante o hover, o botão
    // seguinte na linha (posterior no DOM) pinta por cima da tooltip
    // mesmo com `zIndex: 20` nela — achado ao vivo 2026-07-21 (tooltip
    // "Abrir O.S." aparecendo atrás do ícone seguinte no Gestor de
    // Comandas/Alterar Comandas). Ver CLAUDE.md > "Modo Didático" > regra
    // de tooltip sempre por cima.
    // `flexShrink: 0` — sem isso, um ícone dentro de um pai `flexDirection:
    // "row"` com espaço apertado (ex.: ao lado de um `Text` de largura
    // fixa) pode ser espremido pelo flexbox web, e a tooltip (filha
    // posicionada dentro desse wrapper encolhido) herda a largura mínima
    // resultante — o texto quebra em várias linhas estreitas em vez de
    // uma única linha ao lado do ícone. Achado ao vivo 2026-07-28
    // (tooltip "Adicionar encaixe" na Agenda, ícone ao lado de um `Text`
    // "08:00" de largura fixa).
    <View style={{ position: "relative", zIndex: hover ? 1000 : 1, flexShrink: 0 }}>
      <Pressable
        onPress={handlePress}
        disabled={disabled}
        onHoverIn={isWeb ? () => setHover(true) : undefined}
        onHoverOut={isWeb ? () => setHover(false) : undefined}
        style={style}
        hitSlop={8}
        testID={testID}
      >
        <Ionicons name={icon} size={size} color={color} />
        {badge ? (
          <View
            pointerEvents="none"
            style={{
              position: "absolute", top: -2, right: -2, width: 8, height: 8, borderRadius: 4,
              backgroundColor: badgeColor, borderWidth: 1, borderColor: colors.surface,
            }}
          />
        ) : null}
      </Pressable>
      {hover ? (
        <View
          style={{
            position: "absolute", top: "100%", [tooltipAlign]: 0, marginTop: 4,
            backgroundColor: "#1a1a1a", borderRadius: 6,
            paddingHorizontal: 8, paddingVertical: 4, zIndex: 1000,
          }}
          pointerEvents="none"
        >
          <Text style={{ color: "#fff", fontSize: 11, fontWeight: "600" }} numberOfLines={1}>{label}</Text>
        </View>
      ) : null}
    </View>
  );
}
