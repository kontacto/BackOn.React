// Cartões de totais do período no Relatório de Pedidos.
import { Text, View } from "react-native";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { styles } from "./styles";
import { RelTotais } from "./useRelatorioPedidos";

export default function TotaisBox({ totais }: { totais: RelTotais }) {
  return (
    <View style={styles.totaisBox} testID="relpedidos-totais">
      <Text style={styles.totaisTitle}>Totais do período</Text>
      <View style={styles.totaisRow}>
        <View style={[styles.tCard, { borderLeftColor: colors.brandPrimary }]}>
          <Text style={styles.tLabel}>Pedidos</Text>
          <Text style={styles.tValue} testID="relpedidos-tot-pedidos">{totais.qtd_pedidos}</Text>
        </View>
        <View style={[styles.tCard, { borderLeftColor: colors.brandSecondary || "#5a7bd8" }]}>
          <Text style={styles.tLabel}>Total Prod/Serv</Text>
          <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-total">
            {formatBRL((totais.produtos || 0) + (totais.servicos || 0))}
          </Text>
        </View>
        <View style={[styles.tCard, { borderLeftColor: colors.success }]}>
          <Text style={styles.tLabel}>Margem média</Text>
          <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-margem">{formatBRL(totais.margem)}</Text>
          <Text style={styles.tSub}>{(totais.margem_pct || 0).toFixed(2).replace(".", ",")}%</Text>
        </View>
      </View>
      <View style={styles.totaisRow}>
        <View style={[styles.tCard, { borderLeftColor: colors.error }]}>
          <Text style={styles.tLabel}>Descontos</Text>
          <Text style={[styles.tValue, { fontSize: 14, color: colors.error }]} testID="relpedidos-tot-descontos">{formatBRL(totais.desconto)}</Text>
        </View>
        <View style={[styles.tCard, { borderLeftColor: "#1e88e5" }]}>
          <Text style={styles.tLabel}>Produtos</Text>
          <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-produtos">{formatBRL(totais.produtos)}</Text>
        </View>
        <View style={[styles.tCard, { borderLeftColor: colors.warning }]}>
          <Text style={styles.tLabel}>Serviços</Text>
          <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-servicos">{formatBRL(totais.servicos)}</Text>
        </View>
      </View>
    </View>
  );
}
