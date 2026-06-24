// Filtro de situação do pedido (chips).
import { Pressable, Text, View } from "react-native";
import { styles } from "./styles";

const SITUACOES: { value: string; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];

type Props = { value: string; onChange: (v: string) => void };

export default function SituacaoFilter({ value, onChange }: Props) {
  return (
    <View style={styles.sitFilterRow} testID="principal-situacao-filter">
      {SITUACOES.map((s) => {
        const sel = value === s.value;
        return (
          <Pressable
            key={s.value || "all"}
            onPress={() => onChange(s.value)}
            style={[styles.sitChip, sel && styles.sitChipSel]}
            testID={`principal-sit-${s.value || "todos"}`}
          >
            <Text style={[styles.sitChipText, sel && styles.sitChipTextSel]}>{s.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}
