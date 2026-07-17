// Tabela de movimento do dia (Pedidos + OS) + erro de dashboard + linha de total.
import { ActivityIndicator, Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { SIT_COLOR } from "@/src/components/relatorio/styles";
import { styles } from "./styles";
import { MovimentoItem } from "./useDashboard";

type Props = {
  movimento: MovimentoItem[];
  dashLoading: boolean;
  dashError: string | null;
  totalMovimento: number;
  // Filtro de situação ativo na tela ("" = Todos). Selo de situação por
  // linha só aparece com "Todos" — com um filtro específico já selecionado
  // (ex. só "Faturado"), todas as linhas teriam o mesmo selo, redundante.
  situacaoFiltro: string;
};

export default function PedidosTable({ movimento, dashLoading, dashError, totalMovimento, situacaoFiltro }: Props) {
  const mostrarSituacao = !situacaoFiltro;
  const router = useRouter();
  const openItem = (m: MovimentoItem) => {
    if (m.tipo === "OS") router.push({ pathname: "/os-form", params: { codigo: String(m.doc) } });
    else router.push({ pathname: "/pedido-form", params: { pedido: String(m.doc) } });
  };
  return (
    <>
      <View style={[styles.pedidosHeader, Platform.OS === "web" && styles.pedidosHeaderWeb]}>
        <Text style={[styles.sectionTitle, Platform.OS === "web" && styles.sectionTitleWeb]}>Movimento de Hoje</Text>
        {dashLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>

      {dashError ? (
        <View style={[styles.errorBox, Platform.OS === "web" && styles.errorBoxWeb]} testID="principal-dash-error">
          <Ionicons name="alert-circle-outline" size={16} color={colors.error} />
          <Text style={styles.errorText}>{dashError}</Text>
        </View>
      ) : null}

      <View style={[styles.pedidosCard, Platform.OS === "web" && styles.pedidosCardWeb]} testID="principal-pedidos-list">
        <View style={styles.pedidosHead}>
          <Text style={[styles.pedidoCell, { flex: 1.1 }]}>Documento</Text>
          <Text style={[styles.pedidoCell, Platform.OS === "web" && { flex: 2.1 }]}>Cliente</Text>
          <Text style={[styles.pedidoCell, { flex: 1.5 }]}>Vendedor</Text>
          <Text style={[styles.pedidoCell, { flex: 1.2, textAlign: "right" }]}>Valor</Text>
        </View>
        {movimento.length === 0 && !dashLoading ? (
          <Text style={styles.empty}>Nenhum movimento hoje.</Text>
        ) : (
          movimento.map((m) => (
            <Pressable
              key={`${m.tipo}-${m.doc}`}
              onPress={() => openItem(m)}
              style={({ pressed }) => [styles.pedidoRow, pressed && { backgroundColor: colors.brandTertiary }]}
              testID={`mov-${m.tipo}-${m.doc}`}
            >
              <View style={[{ flexDirection: "row", alignItems: "center", gap: 6, flex: 1.1 }]}>
                <View
                  style={{
                    backgroundColor: m.tipo === "OS" ? "#E8F0FE" : colors.brandTertiary,
                    borderRadius: 4,
                    paddingHorizontal: 5,
                    paddingVertical: 1,
                  }}
                >
                  <Text style={{ fontSize: 10, fontWeight: "700", color: m.tipo === "OS" ? "#2563EB" : colors.brandPrimary }}>
                    {m.tipo}
                  </Text>
                </View>
                <Text style={styles.pedidoCellValue}>#{m.doc}</Text>
              </View>
              <View style={[{ flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 6 }, Platform.OS === "web" && { flex: 2.1 }]}>
                <Text style={styles.pedidoCellValue} numberOfLines={1}>{m.cliente || "—"}</Text>
                {mostrarSituacao && m.situacaoLabel ? (
                  <View
                    style={{
                      backgroundColor: (SIT_COLOR[m.situacao] || colors.muted) + "22",
                      borderRadius: 4, paddingHorizontal: 5, paddingVertical: 1,
                    }}
                    testID={`mov-situacao-${m.tipo}-${m.doc}`}
                  >
                    <Text style={{ fontSize: 10, fontWeight: "700", color: SIT_COLOR[m.situacao] || colors.muted }}>
                      {m.situacaoLabel}
                    </Text>
                  </View>
                ) : null}
              </View>
              <Text style={[styles.pedidoCellValue, { flex: 1.5 }]} numberOfLines={1}>{m.vendedor || "—"}</Text>
              <Text style={[styles.pedidoCellValue, { flex: 1.2, textAlign: "right", fontWeight: "500" }]}>{formatBRL(m.valor)}</Text>
            </Pressable>
          ))
        )}
        {movimento.length > 0 ? (
          <View style={styles.pedidoTotalRow} testID="principal-pedidos-total">
            <Text style={[styles.pedidoTotalLabel, { flex: 4.7 }]}>Total ({movimento.length})</Text>
            <Text style={[styles.pedidoTotalValue, { flex: 1.2, textAlign: "right" }]}>{formatBRL(totalMovimento)}</Text>
          </View>
        ) : null}
      </View>
    </>
  );
}
