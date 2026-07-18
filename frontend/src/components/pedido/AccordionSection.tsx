// Seção recolhível genérica (título + chevron) — mesmo padrão visual já usado
// em bordero-cilindros.tsx ("Resumo por Status"), extraído aqui porque agora
// é usado em 2 telas de Pedido (rápido e completo) pro bloco "Dados
// Principais" (Vendedor, Área de Atuação, Data/Validade, Observação, etc.).
import { useState } from "react";
import { Pressable, StyleProp, Text, View, ViewStyle } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

type Props = {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  testID?: string;
  // Estilo do `View` mais externo — por padrão o cabeçalho (`itensHeader`)
  // já força `width: "100%"`/`alignSelf: "stretch"`, então passar aqui
  // `alignSelf: "flex-start"` + uma `width` calculada é o jeito de encolher
  // o acordeon inteiro (cabeçalho incluso) pro tamanho do conteúdo em vez
  // de ocupar a tela toda — usado em `app/pedidos.tsx`.
  style?: StyleProp<ViewStyle>;
};

export default function AccordionSection({ title, defaultExpanded = false, children, testID, style }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <View style={style}>
      <Pressable
        onPress={() => setExpanded((v) => !v)}
        style={styles.itensHeader}
        testID={testID ? `${testID}-toggle` : undefined}
      >
        <Text style={[styles.sectionTitle, { marginTop: 0, marginBottom: 0 }]}>{title}</Text>
        <Ionicons name={expanded ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
      </Pressable>
      {expanded ? children : null}
    </View>
  );
}
