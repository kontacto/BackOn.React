// Modal "Descontos Concedidos": lista os descontos do pedido com total.
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { formatBRL, fmtNum } from "@/src/utils/format";
import { styles } from "./styles";
import { DescontoRow } from "./types";
import { UsePedidoItens } from "./usePedidoItens";

const isWeb = Platform.OS === "web";

export default function DiscountsReportModal({ it }: { it: UsePedidoItens }) {
  return (
    <Modal visible={it.descModalOpen} transparent animationType="slide" onRequestClose={() => it.setDescModalOpen(false)}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => it.setDescModalOpen(false)}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Descontos Concedidos</Text>
            <Pressable onPress={() => it.setDescModalOpen(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          {it.descLoading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
          ) : it.descItems.length === 0 ? (
            <Text style={styles.emptyText}>Nenhum desconto registrado.</Text>
          ) : (
            <ScrollView style={{ maxHeight: 420 }}>
              {it.descItems.map((d: DescontoRow) => (
                <View key={d.cod} style={styles.descRow} testID={`pedido-form-desc-${d.cod}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemDesc} numberOfLines={1}>{d.descricao}</Text>
                    <Text style={styles.itemSub}>
                      {d.tipo_label}{d.percentual > 0 ? ` · ${fmtNum(d.percentual)}%` : ""}
                      {d.qtd > 0 ? ` · ${fmtNum(d.qtd)}× ${formatBRL(d.valor_unitario)}` : ""}
                      {` · usuário ${d.usuario}`}
                    </Text>
                  </View>
                  <Text style={[styles.itemTotal, { color: colors.error }]}>- {formatBRL(d.valor_total)}</Text>
                </View>
              ))}
              <View style={styles.subtotalRow}>
                <Text style={styles.subtotalLabel}>Total de descontos</Text>
                <Text style={[styles.subtotalValue, { color: colors.error }]}>- {formatBRL(it.descTotalApi)}</Text>
              </View>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
