// Cartão de um pedido no relatório, com cabeçalho clicável e detalhe (margem + descontos).
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR } from "@/src/utils/format";
import { styles, SIT_COLOR } from "./styles";
import { PedidoItem, Analise } from "./useRelatorioPedidos";

type Props = {
  pedido: PedidoItem;
  open: boolean;
  analise?: Analise;
  onToggle: (pedido: number) => void;
};

export default function PedidoCard({ pedido: p, open, analise: an, onToggle }: Props) {
  const sitColor = SIT_COLOR[p.situacao] || colors.muted;
  return (
    <View style={styles.card} testID={`relpedidos-row-${p.pedido}`}>
      <Pressable
        onPress={() => onToggle(p.pedido)}
        style={({ pressed }) => [styles.cardHead, pressed && { backgroundColor: colors.brandTertiary }]}
      >
        <View style={{ flex: 1 }}>
          <View style={styles.cardTopRow}>
            <Text style={styles.cardPedido}>#{p.pedido}</Text>
            <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
              <Text style={[styles.sitTagText, { color: sitColor }]}>{p.situacao_label}</Text>
            </View>
          </View>
          <Text style={styles.cardCliente} numberOfLines={1}>{p.cliente}</Text>
          <Text style={styles.cardMeta} numberOfLines={1}>{formatDateBR(p.data)} · {p.vendedor_nome}</Text>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Text style={styles.cardTotal}>{formatBRL(p.total)}</Text>
          <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
        </View>
      </Pressable>

      {open ? (
        <View style={styles.expand} testID={`relpedidos-expand-${p.pedido}`}>
          {an?.loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} />
          ) : an?.error ? (
            <Text style={styles.errorText}>Falha ao carregar análise: {an.error}</Text>
          ) : (
            <>
              <Text style={styles.expandTitle}>Margem</Text>
              {an?.margem ? (
                <View style={styles.margemGrid}>
                  <View style={styles.mItem}><Text style={styles.mLabel}>Venda</Text><Text style={styles.mVal}>{formatBRL(an.margem.venda)}</Text></View>
                  <View style={styles.mItem}><Text style={styles.mLabel}>Desconto</Text><Text style={[styles.mVal, { color: colors.error }]}>{formatBRL(an.margem.desconto)}</Text></View>
                  <View style={styles.mItem}><Text style={styles.mLabel}>Custo</Text><Text style={styles.mVal}>{formatBRL(an.margem.custo)}</Text></View>
                  <View style={styles.mItem}><Text style={styles.mLabel}>Margem</Text><Text style={[styles.mVal, { color: colors.success }]}>{formatBRL(an.margem.margem)} ({(an.margem.margem_pct || 0).toFixed(2).replace(".", ",")}%)</Text></View>
                </View>
              ) : (
                <Text style={styles.muted}>Sem dados de margem.</Text>
              )}

              <Text style={[styles.expandTitle, { marginTop: spacing.md }]}>Descontos concedidos</Text>
              {an?.descontos && an.descontos.length > 0 ? (
                an.descontos.map((d) => (
                  <View key={d.cod} style={styles.descRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.descDesc} numberOfLines={1}>{d.descricao || "—"}</Text>
                      <Text style={styles.descMeta}>{d.tipo_label} · {(d.percentual || 0).toFixed(2).replace(".", ",")}% · qtd {d.qtd}</Text>
                    </View>
                    <Text style={[styles.descVal, { color: colors.error }]}>- {formatBRL(d.valor_total)}</Text>
                  </View>
                ))
              ) : (
                <Text style={styles.muted}>Nenhum desconto concedido.</Text>
              )}
            </>
          )}
        </View>
      ) : null}
    </View>
  );
}
