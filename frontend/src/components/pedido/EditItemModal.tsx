// Modal "Editar Item": ajusta qtd, valor, desconto, acréscimo e complemento; permite excluir.
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum, calcDescUnit } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";
import { UsePedidoItens } from "./usePedidoItens";

const isWeb = Platform.OS === "web";

export default function EditItemModal({ it, tela = "PEDIDO" }: { it: UsePedidoItens; tela?: string }) {
  const { editItem } = it;
  const { can } = usePermissions();
  const canDesc = can(`${tela}.DESC_ITEM`);
  const canSave = can(`${tela}.EDIT_ITEM`);
  const canDelete = can(`${tela}.DEL_ITEM`);
  return (
    <Modal visible={!!editItem} transparent animationType="slide" onRequestClose={() => it.setEditItem(null)}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => it.setEditItem(null)}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Editar Item</Text>
            <Pressable onPress={() => it.setEditItem(null)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          {editItem ? (
            <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: spacing.sm }}>
                <View style={styles.selProdBox}>
                  <Text style={styles.itemDesc} numberOfLines={2}>{editItem.descricao || editItem.produto}</Text>
                  <Text style={styles.resultSub}>#{editItem.produto}{editItem.cod_fab ? ` · ${editItem.cod_fab}` : ""}</Text>
                </View>
                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Quantidade</Text>
                    <View style={styles.qtdInputRow}>
                      <TextInput value={it.editQtd} onChangeText={it.setEditQtd} keyboardType="decimal-pad" style={[styles.input, { flex: 1, minWidth: 0 }]} testID="pedido-form-edit-qtd" />
                      <TouchableOpacity
                        onPress={() => it.setEditQtd(fmtNum(parseNum(it.editQtd) + 1))}
                        activeOpacity={0.7}
                        style={styles.plusBtn}
                        testID="pedido-form-edit-qtd-plus"
                      >
                        <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor unitário</Text>
                    <TextInput value={it.editValor} onChangeText={it.setEditValor} keyboardType="decimal-pad" style={styles.input} testID="pedido-form-edit-valor" />
                  </View>
                </View>
                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. %</Text>
                    <TextInput
                      value={it.editDescPct}
                      onChangeText={(v) => { it.setEditDescPct(v); if (parseNum(v) > 0) it.setEditDescRs(""); }}
                      editable={canDesc && parseNum(it.editDescRs) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, (!canDesc || parseNum(it.editDescRs) > 0) && styles.inputDisabled]}
                      testID="pedido-form-edit-descpct"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                    <TextInput
                      value={it.editDescRs}
                      onChangeText={(v) => { it.setEditDescRs(v); if (parseNum(v) > 0) it.setEditDescPct(""); }}
                      editable={canDesc && parseNum(it.editDescPct) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, (!canDesc || parseNum(it.editDescPct) > 0) && styles.inputDisabled]}
                      testID="pedido-form-edit-descrs"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Acrésc. R$ (unit.)</Text>
                    <TextInput
                      value={it.editAcr}
                      onChangeText={it.setEditAcr}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="pedido-form-edit-acr"
                    />
                  </View>
                </View>
                <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                <TextInput value={it.editCompl} onChangeText={it.setEditCompl} placeholder="Descrição complementar" placeholderTextColor={colors.muted} style={styles.input} testID="pedido-form-edit-compl" />
                {(() => {
                  const pNormal = parseNum(it.editValor);
                  const dUnit = calcDescUnit(pNormal, it.editDescPct, it.editDescRs);
                  const acr = parseNum(it.editAcr);
                  const pVenda = pNormal - dUnit + acr;
                  const qtd = parseNum(it.editQtd);
                  return (
                    <View style={styles.liquidoBox}>
                      <View style={styles.liquidoRow}>
                        <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                        <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                      </View>
                      {dUnit > 0 ? (
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Desconto total ({fmtNum(qtd)}×)</Text>
                          <Text style={[styles.liquidoVal, { color: colors.error }]}>- {formatBRL(dUnit * qtd)}</Text>
                        </View>
                      ) : null}
                      <View style={styles.previewRow}>
                        <Text style={styles.subtotalLabel}>Total do item</Text>
                        <Text style={styles.subtotalValue}>{formatBRL(qtd * pVenda)}</Text>
                      </View>
                    </View>
                  );
                })()}
                <View style={styles.modalBtns}>
                  {canDelete ? (
                    <Pressable
                      onPress={() => it.handleDeleteItem(editItem)}
                      disabled={it.editSaving}
                      style={({ pressed }) => [styles.deleteBtn, (pressed || it.editSaving) && { opacity: 0.8 }]}
                      testID="pedido-form-edit-delete"
                    >
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  ) : null}
                  {canSave ? (
                    <Pressable
                      onPress={it.handleUpdateItem}
                      disabled={it.editSaving}
                      style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, (pressed || it.editSaving) && { opacity: 0.8 }]}
                      testID="pedido-form-edit-save"
                    >
                      {it.editSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Salvar</Text>}
                    </Pressable>
                  ) : (
                    <Pressable
                      onPress={() => it.setEditItem(null)}
                      style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, pressed && { opacity: 0.8 }]}
                      testID="pedido-form-edit-close"
                    >
                      <Text style={styles.primaryBtnText}>Fechar</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            </ScrollView>
          ) : null}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
