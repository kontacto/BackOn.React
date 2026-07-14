// Bloco de filtros do Relatório de Pedidos (período, vendedor, situação, botão).
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];

type Props = {
  dataIni: string | null; setDataIni: (v: string | null) => void;
  dataFim: string | null; setDataFim: (v: string | null) => void;
  vendedorOpts: SelectOption[]; vendedor: string | number | null; setVendedor: (v: string | number | null) => void;
  situacao: string; setSituacao: (v: string) => void;
  loading: boolean; onBuscar: () => void;
};

export default function Filtros(p: Props) {
  return (
    <View style={styles.filters}>
      <View style={styles.dateRow}>
        <View style={{ flex: 1 }}>
          <DateField label="De" value={p.dataIni} onChange={p.setDataIni} testID="relpedidos-di" />
        </View>
        <View style={{ flex: 1 }}>
          <DateField label="Até" value={p.dataFim} onChange={p.setDataFim} testID="relpedidos-df" />
        </View>
      </View>

      <Text style={styles.fieldLabel}>Vendedor (opcional)</Text>
      <SelectField
        value={p.vendedor}
        onChange={p.setVendedor}
        options={p.vendedorOpts}
        placeholder="Todos os vendedores"
        modalTitle="Selecione o vendedor"
        allowClear
        testID="relpedidos-vendedor"
      />

      <Text style={styles.fieldLabel}>Situação</Text>
      <View style={styles.sitRow}>
        {SITUACOES.map((s) => {
          const sel = p.situacao === s.value;
          return (
            <Pressable
              key={s.value || "all"}
              onPress={() => p.setSituacao(s.value)}
              style={[styles.chip, sel && styles.chipSel]}
              testID={`relpedidos-sit-${s.value || "todos"}`}
            >
              <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        onPress={p.onBuscar}
        disabled={p.loading}
        style={({ pressed }) => [styles.btn, (pressed || p.loading) && { opacity: 0.7 }]}
        testID="relpedidos-buscar"
      >
        {p.loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
          <>
            <Ionicons name="search" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.btnText}>Gerar relatório</Text>
          </>
        )}
      </Pressable>
    </View>
  );
}
