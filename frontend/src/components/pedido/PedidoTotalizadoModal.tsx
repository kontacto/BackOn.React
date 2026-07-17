// Modal "Pedido Totalizado" (FrmManPedBar.frm, botão/F9 "Pedido Totalizado")
// — não é só uma lista de produtos, é o TOTAL de cada produto: agrupa por
// produto (soma quantidade e valor, mesmo com preço unitário variando entre
// inclusões) numa única linha, em vez da lista crua com uma linha por
// inclusão.
import { Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { formatBRL, fmtNum } from "@/src/utils/format";
import { styles } from "./styles";
import { UsePedidoItens } from "./usePedidoItens";

const isWeb = Platform.OS === "web";

export default function PedidoTotalizadoModal({ it }: { it: UsePedidoItens }) {
  return (
    <Modal
      visible={it.pedidoTotalizadoOpen}
      transparent
      animationType="slide"
      onRequestClose={() => it.setPedidoTotalizadoOpen(false)}
    >
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => it.setPedidoTotalizadoOpen(false)}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Pedido Totalizado</Text>
            <Pressable onPress={() => it.setPedidoTotalizadoOpen(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          {it.pedidoTotalizadoGrupos.length === 0 ? (
            <Text style={styles.emptyText}>Nenhum item no pedido.</Text>
          ) : (
            <ScrollView style={{ maxHeight: 420 }}>
              {it.pedidoTotalizadoGrupos.map((g) => (
                <View key={g.produto} style={styles.descRow} testID={`pedido-totalizado-row-${g.produto}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemDesc} numberOfLines={1}>{g.descricao}</Text>
                    <Text style={styles.itemSub}>
                      {g.cod_fab ? `${g.cod_fab} · ` : ""}{fmtNum(g.qtd)}× (média {formatBRL(g.qtd ? g.valorTotal / g.qtd : 0)})
                    </Text>
                  </View>
                  <Text style={styles.itemTotal}>{formatBRL(g.valorTotal)}</Text>
                </View>
              ))}
              <View style={styles.subtotalRow}>
                <Text style={styles.subtotalLabel}>Total geral</Text>
                <Text style={styles.subtotalValue}>{formatBRL(it.pedidoTotalizadoTotal)}</Text>
              </View>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
