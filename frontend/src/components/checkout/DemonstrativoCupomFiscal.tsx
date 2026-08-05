// "Demonstrativo do Cupom Fiscal" — painel principal da venda em andamento.
// Sintetiza 3 referências visuais que o usuário trouxe: o painel direito de
// `FrmPafOFF.frm` (legado, "Demonstrativo do Cupom Fiscal" — itens
// aparecendo em tempo real, cancelar clicando na lista), o destaque grande
// do último item lançado de um PDV moderno (SysPDV), e a grade de colunas
// claras (Descrição/Qtd/Unitário/Total) de um terceiro exemplo de PDV.
// Resultado: nem cupom monoespaçado nem grade fria de planilha — um painel
// moderno com destaque grande + grade legível.
//
// Não é o cupom final impresso — isso é responsabilidade de
// `reciboTexto.ts`/`imprimirVendaAutomatico` (checkout.tsx), disparado
// automaticamente ao Fechar Venda.
import { ScrollView, StyleSheet, Text, View } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, fmtNum } from "@/src/utils/format";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";

type Item = {
  id_mov: number;
  descricao: string;
  qtd: number;
  p_unit: number;
  total: number;
  desconto_unit: number;
  origemDav: string | null;
};

type Props = {
  comanda: number;
  itens: Item[];
  valorVenda: number;
  podeCancelar: boolean;
  onCancelarItem: (id_mov: number) => void;
};

export default function DemonstrativoCupomFiscal({ comanda, itens, valorVenda, podeCancelar, onCancelarItem }: Props) {
  const ultimoItem = itens.length > 0 ? itens[itens.length - 1] : null;

  return (
    <View style={s.card}>
      <View style={s.header}>
        <Text style={s.title}>Demonstrativo do Cupom Fiscal</Text>
        <Text style={s.comanda}>Comanda Nº {comanda}</Text>
      </View>

      {ultimoItem ? (
        <View style={s.destaque}>
          <Text style={s.destaqueDescricao} numberOfLines={1}>{ultimoItem.descricao}</Text>
          <View style={s.row}>
            <Text style={s.destaqueQtd}>{fmtNum(ultimoItem.qtd)} x {formatBRL(ultimoItem.p_unit)}</Text>
            <Text style={s.destaqueTotal}>{formatBRL(ultimoItem.total)}</Text>
          </View>
        </View>
      ) : (
        <View style={s.destaqueVazio}>
          <Text style={s.hint}>Nenhum item lançado ainda — o próximo item aparece aqui em destaque.</Text>
        </View>
      )}

      <View style={s.gridHeader}>
        <Text style={[s.gridHeaderText, { flex: 2 }]}>Descrição</Text>
        <Text style={[s.gridHeaderText, s.gridColQtd]}>Qtd</Text>
        <Text style={[s.gridHeaderText, s.gridColValor]}>Unit.</Text>
        <Text style={[s.gridHeaderText, s.gridColValor]}>Total</Text>
        <View style={{ width: 28 }} />
      </View>
      <ScrollView style={s.gridBody}>
        {itens.length === 0 ? (
          <Text style={[s.hint, { padding: spacing.md }]}>Nenhum item lançado ainda.</Text>
        ) : (
          itens.map((it, idx) => (
            <View key={it.id_mov} style={[s.gridRow, idx % 2 === 1 && s.gridRowAlt]}>
              <View style={{ flex: 2 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Text style={s.gridCell} numberOfLines={1}>{it.descricao}</Text>
                  {it.origemDav ? (
                    <View style={s.badge}>
                      <Text style={s.badgeText}>{it.origemDav === "P" ? "Pedido" : "O.S."}</Text>
                    </View>
                  ) : null}
                </View>
                {it.desconto_unit > 0 ? (
                  <Text style={s.gridCellHint}>desc. {formatBRL(it.desconto_unit)}/un.</Text>
                ) : null}
              </View>
              <Text style={[s.gridCell, s.gridColQtd]}>{fmtNum(it.qtd)}</Text>
              <Text style={[s.gridCell, s.gridColValor]}>{formatBRL(it.p_unit)}</Text>
              <Text style={[s.gridCell, s.gridColValor, { fontWeight: "700" }]}>{formatBRL(it.total)}</Text>
              <View style={{ width: 28, alignItems: "center" }}>
                {podeCancelar && !it.origemDav ? (
                  <IconButtonWithTooltip
                    icon="close-circle-outline"
                    label="Cancelar item"
                    size={18}
                    color={colors.error}
                    onPress={() => onCancelarItem(it.id_mov)}
                    testID={`checkout-demonstrativo-cancel-${it.id_mov}`}
                  />
                ) : null}
              </View>
            </View>
          ))
        )}
      </ScrollView>

      <View style={s.totalBox}>
        <Text style={s.totalLabel}>TOTAL A PAGAR</Text>
        <Text style={s.totalValor}>{formatBRL(valorVenda)}</Text>
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  card: {
    flex: 1, minWidth: 340, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm,
  },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  title: { fontSize: 12, fontWeight: "700", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  comanda: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },

  destaque: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, gap: 4 },
  destaqueVazio: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.lg, alignItems: "center" },
  destaqueDescricao: { fontSize: 20, fontWeight: "800", color: colors.brandPrimary },
  destaqueQtd: { fontSize: 14, color: colors.onSurface },
  destaqueTotal: { fontSize: 22, fontWeight: "800", color: colors.brandPrimary },

  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },

  gridHeader: { flexDirection: "row", gap: 6, paddingHorizontal: 4, paddingTop: 4 },
  gridHeaderText: { fontSize: 11, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  gridColQtd: { width: 48, textAlign: "right" },
  gridColValor: { width: 76, textAlign: "right" },
  gridBody: { maxHeight: 260, borderTopWidth: 1, borderTopColor: colors.border },
  gridRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 4, paddingVertical: 8 },
  gridRowAlt: { backgroundColor: colors.surfaceSecondary },
  gridCell: { fontSize: 13, color: colors.onSurface },
  gridCellHint: { fontSize: 10, color: colors.muted },

  hint: { fontSize: 12, color: colors.muted, fontStyle: "italic", textAlign: "center" },

  badge: { backgroundColor: colors.brandTertiary, borderRadius: radius.pill, paddingHorizontal: 6, paddingVertical: 1 },
  badgeText: { fontSize: 9, fontWeight: "700", color: colors.brandPrimary },

  totalBox: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
  },
  totalLabel: { fontSize: 13, fontWeight: "700", color: colors.onBrandPrimary },
  totalValor: { fontSize: 20, fontWeight: "800", color: colors.onBrandPrimary },
});
