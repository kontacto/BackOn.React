// Gráfico de barras vertical simples — sem lib de gráfico nova (nenhum
// relatório do app usava gráfico até agora), só Views com altura
// proporcional ao valor. Cross-platform (web + mobile) de graça, já que
// não depende de SVG/Canvas nenhum. Rolagem horizontal quando há muitas
// categorias (evita esmagar as barras/rótulos).
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";

export type BarChartDatum = { label: string; value: number; color?: string };

type Props = {
  data: BarChartDatum[];
  formatValue?: (v: number) => string;
  emptyMessage?: string;
  // Altura da área de barras (o valor máximo do conjunto ocupa essa altura).
  height?: number;
};

const COLUMN_WIDTH = 88;

export default function SimpleBarChart({ data, formatValue = (v) => String(v), emptyMessage = "Sem dados.", height = 160 }: Props) {
  const max = Math.max(1, ...data.map((d) => Math.abs(d.value)));

  if (data.length === 0) {
    return <Text style={styles.empty}>{emptyMessage}</Text>;
  }

  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.scrollContent}>
      {data.map((d) => {
        const barHeight = Math.max(4, (Math.abs(d.value) / max) * height);
        return (
          <View key={d.label} style={styles.column}>
            <Text style={styles.value} numberOfLines={1}>{formatValue(d.value)}</Text>
            <View style={[styles.track, { height }]}>
              <View style={[styles.bar, { height: barHeight, backgroundColor: d.color || colors.brandPrimary }]} />
            </View>
            <Text style={styles.label} numberOfLines={2}>{d.label}</Text>
          </View>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollContent: { flexDirection: "row", alignItems: "flex-end", gap: spacing.lg, paddingHorizontal: spacing.xs, paddingBottom: spacing.xs },
  column: { width: COLUMN_WIDTH, alignItems: "center" },
  value: { fontSize: 11, fontWeight: "600", color: colors.onSurface, marginBottom: 4 },
  track: {
    width: 36, borderRadius: radius.sm, backgroundColor: colors.surfaceTertiary,
    justifyContent: "flex-end", overflow: "hidden",
  },
  bar: { width: "100%", borderRadius: radius.sm },
  label: { fontSize: 10, color: colors.onSurface, textAlign: "center", marginTop: 6 },
  empty: { fontSize: 12, color: colors.muted, textAlign: "center", paddingVertical: spacing.md },
});
