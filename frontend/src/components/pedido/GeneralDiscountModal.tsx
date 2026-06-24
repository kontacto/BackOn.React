// Modal "Desconto Geral": informa valor em R$, distribui proporcionalmente entre itens.
import {
  ActivityIndicator, Modal, Pressable, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum } from "@/src/utils/format";
import { styles } from "./styles";
import { UsePedidoItens } from "./usePedidoItens";

export default function GeneralDiscountModal({ it }: { it: UsePedidoItens }) {
  return (
    <Modal visible={it.geralModalOpen} transparent animationType="slide" onRequestClose={() => it.setGeralModalOpen(false)}>
      <Pressable style={styles.modalBg} onPress={() => it.setGeralModalOpen(false)}>
        <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Desconto Geral</Text>
            <Pressable onPress={() => it.setGeralModalOpen(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={{ gap: spacing.sm }}>
            <View style={styles.itensHint}>
              <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
              <Text style={styles.itensHintText}>
                Informe o valor do desconto em R$ — será distribuído proporcionalmente entre os itens e substitui descontos por item. Limite da sua função: {fmtNum(it.geralLimite)}%.
              </Text>
            </View>
            <Text style={styles.fieldLabel}>Valor do desconto (R$)</Text>
            <TextInput
              value={it.geralValor}
              onChangeText={it.setGeralValor}
              keyboardType="decimal-pad"
              placeholder="0,00"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="pedido-form-geral-valor"
            />
            {parseNum(it.geralValor) > 0 && it.baseGeral > 0 ? (
              <Text style={styles.geralEquiv}>
                Equivale a {((parseNum(it.geralValor) / it.baseGeral) * 100).toFixed(1)}% do total dos itens ({formatBRL(it.baseGeral)}).
              </Text>
            ) : null}
            <View style={styles.modalBtns}>
              {it.geralAtual > 0 ? (
                <TouchableOpacity
                  onPress={() => it.submitGeral(0)}
                  disabled={it.geralSaving}
                  activeOpacity={0.8}
                  style={styles.deleteBtnWide}
                  testID="pedido-form-geral-remove"
                >
                  <Text style={styles.deleteBtnWideText}>Remover</Text>
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity
                onPress={it.handleApplyGeral}
                disabled={it.geralSaving}
                activeOpacity={0.8}
                style={[styles.primaryBtn, { flex: 1 }]}
                testID="pedido-form-geral-apply"
              >
                {it.geralSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Aplicar</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
