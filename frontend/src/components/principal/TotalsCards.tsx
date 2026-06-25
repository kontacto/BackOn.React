// Cartões de totais do dia (pedidos/produtos/serviços) + margem média.
import { Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { styles } from "./styles";
import { DashboardTotals } from "./useDashboard";

type Props = {
  totais: DashboardTotals;
  dashLoading: boolean;
  showTotais?: boolean;
  showMargem?: boolean;
  showDescontos?: boolean;
};

export default function TotalsCards({
  totais,
  dashLoading,
  showTotais = true,
  showMargem = true,
  showDescontos = true,
}: Props) {
  if (!showTotais && !showMargem) return null;
  return (
    <>
      {showTotais ? (
        <>
          <Text style={styles.sectionTitle}>Totais de Hoje</Text>
          <View style={styles.totalsRow} testID="principal-totals">
            <View style={[styles.totalCard, { borderLeftColor: colors.brandPrimary }]}>
              <Text style={styles.totalLabel}>Pedidos</Text>
              <Text style={styles.totalValue} testID="totals-pedidos">{dashLoading ? "…" : totais.pedidos}</Text>
            </View>
            <View style={[styles.totalCard, { borderLeftColor: colors.success }]}>
              <Text style={styles.totalLabel}>Produtos</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-produtos">{dashLoading ? "…" : formatBRL(totais.produtos)}</Text>
            </View>
            <View style={[styles.totalCard, { borderLeftColor: colors.warning }]}>
              <Text style={styles.totalLabel}>Serviços</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-servicos">{dashLoading ? "…" : formatBRL(totais.servicos)}</Text>
            </View>
          </View>
        </>
      ) : null}

      {showMargem ? (
        <View style={styles.margemCard} testID="principal-margem">
          <View style={styles.margemIcon}>
            <Ionicons name="trending-up" size={20} color={colors.onBrandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.margemLabel}>Margem média do dia</Text>
            <Text style={styles.margemHint}>Venda líquida − custo de reposição</Text>
            {showDescontos ? (
              <Text style={styles.margemDesc} testID="totals-descontos">
                Descontos concedidos: {dashLoading ? "…" : formatBRL(totais.descontos)}
              </Text>
            ) : null}
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.margemValue} testID="totals-margem">{dashLoading ? "…" : formatBRL(totais.margem)}</Text>
            <Text style={styles.margemPct} testID="totals-margem-pct">
              {dashLoading ? "" : `${(totais.margem_pct || 0).toFixed(2).replace(".", ",")}%`}
            </Text>
          </View>
        </View>
      ) : null}
    </>
  );
}
