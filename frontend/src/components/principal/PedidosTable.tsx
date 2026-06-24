// Tabela de pedidos do dia + erro de dashboard + linha de total.
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { styles } from "./styles";
import { DashboardPedido } from "./useDashboard";

type Props = {
  pedidos: DashboardPedido[];
  dashLoading: boolean;
  dashError: string | null;
  totalPedidos: number;
};

export default function PedidosTable({ pedidos, dashLoading, dashError, totalPedidos }: Props) {
  const router = useRouter();
  return (
    <>
      <View style={styles.pedidosHeader}>
        <Text style={styles.sectionTitle}>Pedidos de Hoje</Text>
        {dashLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>

      {dashError ? (
        <View style={styles.errorBox} testID="principal-dash-error">
          <Ionicons name="alert-circle-outline" size={16} color={colors.error} />
          <Text style={styles.errorText}>{dashError}</Text>
        </View>
      ) : null}

      <View style={styles.pedidosCard} testID="principal-pedidos-list">
        <View style={styles.pedidosHead}>
          <Text style={[styles.pedidoCell, { flex: 0.7 }]}>Pedido</Text>
          <Text style={[styles.pedidoCell, { flex: 2 }]}>Cliente</Text>
          <Text style={[styles.pedidoCell, { flex: 1.2, textAlign: "right" }]}>Valor</Text>
        </View>
        {pedidos.length === 0 && !dashLoading ? (
          <Text style={styles.empty}>Nenhum pedido hoje.</Text>
        ) : (
          pedidos.map((p) => (
            <Pressable
              key={p.pedido}
              onPress={() => router.push({ pathname: "/pedido-form", params: { pedido: String(p.pedido) } })}
              style={({ pressed }) => [styles.pedidoRow, pressed && { backgroundColor: colors.brandTertiary }]}
              testID={`pedido-${p.pedido}`}
            >
              <Text style={[styles.pedidoCellValue, { flex: 0.7 }]}>#{p.pedido}</Text>
              <Text style={[styles.pedidoCellValue, { flex: 2 }]} numberOfLines={1}>{p.cliente || "—"}</Text>
              <Text style={[styles.pedidoCellValue, { flex: 1.2, textAlign: "right", fontWeight: "500" }]}>{formatBRL(p.valor)}</Text>
            </Pressable>
          ))
        )}
        {pedidos.length > 0 ? (
          <View style={styles.pedidoTotalRow} testID="principal-pedidos-total">
            <Text style={[styles.pedidoTotalLabel, { flex: 2.7 }]}>Total ({pedidos.length})</Text>
            <Text style={[styles.pedidoTotalValue, { flex: 1.2, textAlign: "right" }]}>{formatBRL(totalPedidos)}</Text>
          </View>
        ) : null}
      </View>
    </>
  );
}
