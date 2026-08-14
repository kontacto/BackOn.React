// Ícone de informação com tooltip no hover (web) — pra texto de ajuda LONGO
// que não cabe como frase full-width sob um campo/seção sem "usar quase
// metade da tela" (achado ao vivo, Revisão Programada em os-geral.tsx,
// 2026-08-13, user-directed: "USA TOOLTIP PARA ESSES CASOS"). Ver CLAUDE.md
// > "Padrões de UI" > seção 5 — regra já previa esse padrão pra texto longo,
// só não tinha componente pronto ainda.
//
// Diferente de `IconButtonWithTooltip` (rótulo curto, `numberOfLines={1}`,
// pensado pra nome de ação de botão-ícone): aqui o texto pode ter várias
// frases e quebra em múltiplas linhas dentro de uma largura fixa.
import { useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors, radius, spacing } from "@/src/theme/colors";

const isWeb = Platform.OS === "web";

type Props = {
  text: string;
  size?: number;
  maxWidth?: number;
  align?: "left" | "right";
  testID?: string;
};

export default function InfoTooltip({ text, size = 16, maxWidth = 280, align = "left", testID }: Props) {
  const [hover, setHover] = useState(false);
  return (
    // Mesmo cuidado de zIndex/stacking já documentado em
    // IconButtonWithTooltip — o wrapper (não só a tooltip) precisa subir de
    // zIndex durante o hover, senão um irmão posterior no DOM pinta por cima.
    <View style={{ position: "relative", zIndex: hover ? 1000 : 1 }}>
      <Pressable
        onHoverIn={isWeb ? () => setHover(true) : undefined}
        onHoverOut={isWeb ? () => setHover(false) : undefined}
        onPress={!isWeb ? () => setHover((v) => !v) : undefined}
        hitSlop={8}
        testID={testID}
      >
        <Ionicons name="information-circle-outline" size={size} color={colors.muted} />
      </Pressable>
      {hover ? (
        <View
          style={{
            position: "absolute", top: "100%", [align]: 0, marginTop: 4,
            backgroundColor: "#1a1a1a", borderRadius: radius.sm,
            paddingHorizontal: spacing.sm, paddingVertical: spacing.xs,
            width: maxWidth, zIndex: 1000,
          }}
          pointerEvents="none"
        >
          <Text style={{ color: "#fff", fontSize: 11, lineHeight: 15 }}>{text}</Text>
        </View>
      ) : null}
    </View>
  );
}
