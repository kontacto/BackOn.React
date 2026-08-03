// Totais da O.S. por Situação/Destino do item (réplica do bloco de totais
// do legado `FrmTraOsNew.frm`: soma "Serviços+Produtos" — só itens
// situação=0, Cliente paga — separado de "Garantia/Interno/Contrato"
// — situação 1/2/3 —, mais o total combinado). Puramente derivado dos
// itens já carregados (sem chamada à API), mesmo princípio de
// `pedidoTotalizadoGrupos` em usePedidoItens.ts.
import { useMemo } from "react";
import { StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { OSItemRow } from "./types";

type Props = { itens: OSItemRow[] };

export default function OSTotaisResumo({ itens }: Props) {
  const { cliente, garantiaEtc, total } = useMemo(() => {
    let cliente = 0;
    let garantiaEtc = 0;
    for (const it of itens) {
      const linha = (it.qtd || 0) * (it.valor_unitario || 0);
      if ((it.situacao ?? 0) === 0) cliente += linha;
      else garantiaEtc += linha;
    }
    return { cliente, garantiaEtc, total: cliente + garantiaEtc };
  }, [itens]);

  if (itens.length === 0) return null;

  return (
    <View style={styles.row}>
      <View style={styles.box}>
        <Text style={styles.label}>Serviços + Produtos</Text>
        <Text style={styles.value}>{formatBRL(cliente)}</Text>
      </View>
      {garantiaEtc > 0 ? (
        <View style={styles.box}>
          <Text style={styles.label}>Garantia / Interno / Contrato</Text>
          <Text style={[styles.value, { color: colors.warning }]}>{formatBRL(garantiaEtc)}</Text>
        </View>
      ) : null}
      <View style={[styles.box, styles.boxTotal]}>
        <Text style={styles.label}>Total (À Pagar + Garantia)</Text>
        <Text style={[styles.value, styles.valueTotal]}>{formatBRL(total)}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  box: {
    flex: 1, minWidth: 160, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  boxTotal: { backgroundColor: colors.brandTertiary, borderColor: colors.brandPrimary },
  label: { fontSize: 10, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4, marginBottom: 2 },
  value: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  valueTotal: { color: colors.brandPrimary },
});
