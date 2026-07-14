// Cartões de totais do dia (pedidos/produtos/serviços) + margem média.
import { Platform, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

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
          <Text style={[styles.sectionTitle, Platform.OS === "web" && styles.sectionTitleWeb]}>Totais de Hoje</Text>
          <View style={[styles.totalsRow, Platform.OS === "web" && styles.totalsRowWeb]} testID="principal-totals">
            <View style={[styles.totalCard, Platform.OS === "web" && styles.totalCardWeb, { borderLeftColor: colors.brandPrimary }]}>
              <Text style={styles.totalLabel}>Pedidos</Text>
              <Text style={styles.totalValue} testID="totals-pedidos">{dashLoading ? "…" : totais.pedidos}</Text>
            </View>
            <View style={[styles.totalCard, Platform.OS === "web" && styles.totalCardWeb, { borderLeftColor: colors.brandSecondary || colors.brandPrimary }]}>
              <Text style={styles.totalLabel}>OS</Text>
              <Text style={styles.totalValue} testID="totals-os">{dashLoading ? "…" : (totais.os ?? 0)}</Text>
            </View>
          </View>
          <View style={[styles.totalsRow, { marginTop: 8 }, Platform.OS === "web" && styles.totalsRowWeb]}>
            <View style={[styles.totalCard, Platform.OS === "web" && styles.totalCardWeb, { borderLeftColor: colors.success }]}>
              <Text style={styles.totalLabel}>Produtos</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-produtos">{dashLoading ? "…" : formatBRL(totais.produtos)}</Text>
            </View>
            <View style={[styles.totalCard, Platform.OS === "web" && styles.totalCardWeb, { borderLeftColor: colors.warning }]}>
              <Text style={styles.totalLabel}>Serviços</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-servicos">{dashLoading ? "…" : formatBRL(totais.servicos)}</Text>
            </View>
          </View>
        </>
      ) : null}

      {showMargem ? (
        <View style={[styles.margemCard, Platform.OS === "web" && styles.margemCardWeb]} testID="principal-margem">
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
