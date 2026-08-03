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
  const isWeb = Platform.OS === "web";
  if (!showTotais && !showMargem) return null;
  return (
    <>
      {showTotais ? (
        <>
          <Text style={[styles.sectionTitle, isWeb && styles.sectionTitleWeb]}>Totais de Hoje</Text>
          {/* Formatação reduzida — as 4 informações em uma única linha,
              não mais 2 linhas de 2 (pedido explícito do usuário,
              2026-07-20: "coloque em uma única linha"). Cards mais
              estreitos/compactos (padding e fonte menores) pra caber os 4
              juntos sem quebrar. */}
          <View style={[styles.totalsRow, isWeb && styles.totalsRowWeb]} testID="principal-totals">
            <View style={[styles.totalCard, isWeb && styles.totalCardWebCompact, { borderLeftColor: colors.brandPrimary }]}>
              <Text style={[styles.totalLabel, isWeb && styles.totalLabelWebCompact]}>Pedidos</Text>
              <Text style={[styles.totalValue, isWeb && styles.totalValueWebCompact]} testID="totals-pedidos">{dashLoading ? "…" : totais.pedidos}</Text>
            </View>
            <View style={[styles.totalCard, isWeb && styles.totalCardWebCompact, { borderLeftColor: colors.brandSecondary || colors.brandPrimary }]}>
              <Text style={[styles.totalLabel, isWeb && styles.totalLabelWebCompact]}>OS</Text>
              <Text style={[styles.totalValue, isWeb && styles.totalValueWebCompact]} testID="totals-os">{dashLoading ? "…" : (totais.os ?? 0)}</Text>
            </View>
            <View style={[styles.totalCard, isWeb && styles.totalCardWebCompact, { borderLeftColor: colors.success }]}>
              <Text style={[styles.totalLabel, isWeb && styles.totalLabelWebCompact]}>Produtos</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }, isWeb && styles.totalValueWebCompact]} testID="totals-produtos">{dashLoading ? "…" : formatBRL(totais.produtos)}</Text>
            </View>
            <View style={[styles.totalCard, isWeb && styles.totalCardWebCompact, { borderLeftColor: colors.warning }]}>
              <Text style={[styles.totalLabel, isWeb && styles.totalLabelWebCompact]}>Serviços</Text>
              <Text style={[styles.totalValue, { fontSize: 16 }, isWeb && styles.totalValueWebCompact]} testID="totals-servicos">{dashLoading ? "…" : formatBRL(totais.servicos)}</Text>
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
