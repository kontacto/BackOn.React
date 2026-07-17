// Seção recolhível genérica (título + chevron) — mesmo padrão visual já usado
// em bordero-cilindros.tsx ("Resumo por Status"), extraído aqui porque agora
// é usado em 2 telas de Pedido (rápido e completo) pro bloco "Dados
// Principais" (Vendedor, Área de Atuação, Data/Validade, Observação, etc.).
import { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

type Props = {
  title: string;
  defaultExpanded?: boolean;
  children: React.ReactNode;
  testID?: string;
};

export default function AccordionSection({ title, defaultExpanded = false, children, testID }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  return (
    <View>
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
