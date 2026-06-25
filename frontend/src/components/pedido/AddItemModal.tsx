// Modal "Adicionar Item": busca de produto/serviço + formulário de confirmação.
import {
  ActivityIndicator, Modal, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum, calcDescUnit } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";
import { ProdutoServico } from "./types";
import { UsePedidoItens } from "./usePedidoItens";

type Props = {
  it: UsePedidoItens;
  onOpenProdutos: () => void;
};

export default function AddItemModal({ it, onOpenProdutos }: Props) {
  const { selProd } = it;
  const { can } = usePermissions();
  const canDesc = can("PEDIDO.DESC_ITEM");
  return (
    <Modal visible={it.addOpen} transparent animationType="slide" onRequestClose={() => it.setAddOpen(false)}>
      <Pressable style={styles.modalBg} onPress={() => it.setAddOpen(false)}>
        <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{selProd ? "Confirmar Item" : "Adicionar Item"}</Text>
            <Pressable onPress={() => it.setAddOpen(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {!selProd ? (
            <>
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={it.prodTerm}
                  onChangeText={it.setProdTerm}
                  placeholder="Buscar produto ou serviço…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  autoFocus
                  testID="pedido-form-prod-search"
                />
              </View>
              {it.prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 360 }} keyboardShouldPersistTaps="handled">
                {it.prodResults.map((p: ProdutoServico) => (
                  <Pressable
                    key={`${p.tipo}-${p.codigo}`}
                    onPress={() => it.pickProduto(p)}
                    style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`pedido-form-prod-${p.codigo}`}
                  >
                    <View style={[styles.itemTipo, p.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                      <Ionicons name={p.tipo === "P" ? "cube" : "construct"} size={16} color={p.tipo === "P" ? colors.brandPrimary : colors.warning} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.resultNome} numberOfLines={1}>{p.descricao}</Text>
                      <Text style={styles.resultSub} numberOfLines={1}>
                        #{p.codigo}{p.cod_fab ? ` · ${p.cod_fab}` : ""}
                      </Text>
                    </View>
                    <Text style={styles.itemTotal}>{formatBRL(p.valor)}</Text>
                  </Pressable>
                ))}
                {!it.prodLoading && it.prodResults.length === 0 ? (
                  <Text style={styles.emptyText}>Nenhum produto/serviço encontrado.</Text>
                ) : null}
              </ScrollView>
              <Pressable
                onPress={onOpenProdutos}
                style={({ pressed }) => [styles.fullListBtn, pressed && { opacity: 0.8 }]}
                testID="pedido-form-open-produtos"
              >
                <Ionicons name="grid-outline" size={16} color={colors.brandPrimary} />
                <Text style={styles.fullListText}>Abrir lista completa de produtos</Text>
              </Pressable>
            </>
          ) : (
            <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: spacing.sm }}>
                <View style={styles.selProdBox}>
                  <Text style={styles.itemDesc} numberOfLines={2}>{selProd.descricao}</Text>
                  <Text style={styles.resultSub}>#{selProd.codigo}{selProd.cod_fab ? ` · ${selProd.cod_fab}` : ""}</Text>
                </View>
                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Quantidade</Text>
                    <View style={styles.qtdInputRow}>
                      <TextInput
                        value={it.addQtd}
                        onChangeText={it.setAddQtd}
                        keyboardType="decimal-pad"
                        style={[styles.input, { flex: 1 }]}
                        testID="pedido-form-add-qtd"
                      />
                      <TouchableOpacity
                        onPress={() => it.setAddQtd(fmtNum(parseNum(it.addQtd) + 1))}
                        activeOpacity={0.7}
                        style={styles.plusBtn}
                        testID="pedido-form-add-qtd-plus"
                      >
                        <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor unitário</Text>
                    <TextInput
                      value={it.addValor}
                      onChangeText={it.setAddValor}
                      keyboardType="decimal-pad"
                      style={styles.input}
                      testID="pedido-form-add-valor"
                    />
                  </View>
                </View>
                <View style={styles.qtdRow}>
                  {canDesc ? (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. %</Text>
                    <TextInput
                      value={it.addDescPct}
                      onChangeText={(v) => { it.setAddDescPct(v); if (parseNum(v) > 0) it.setAddDescRs(""); }}
                      editable={parseNum(it.addDescRs) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, parseNum(it.addDescRs) > 0 && styles.inputDisabled]}
                      testID="pedido-form-add-descpct"
                    />
                  </View>
                  ) : null}
                  {canDesc ? (
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                    <TextInput
                      value={it.addDescRs}
                      onChangeText={(v) => { it.setAddDescRs(v); if (parseNum(v) > 0) it.setAddDescPct(""); }}
                      editable={parseNum(it.addDescPct) <= 0}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={[styles.input, parseNum(it.addDescPct) > 0 && styles.inputDisabled]}
                      testID="pedido-form-add-descrs"
                    />
                  </View>
                  ) : null}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Acrésc. R$ (unit.)</Text>
                    <TextInput
                      value={it.addAcr}
                      onChangeText={it.setAddAcr}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="pedido-form-add-acr"
                    />
                  </View>
                </View>
                <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                <TextInput
                  value={it.addCompl}
                  onChangeText={it.setAddCompl}
                  placeholder="Descrição complementar"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-form-add-compl"
                />
                {(() => {
                  const pNormal = parseNum(it.addValor);
                  const dUnit = calcDescUnit(pNormal, it.addDescPct, it.addDescRs);
                  const acr = parseNum(it.addAcr);
                  const pVenda = pNormal - dUnit + acr;
                  const qtd = parseNum(it.addQtd);
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
                  <Pressable
                    onPress={() => it.setSelProd(null)}
                    style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}
                  >
                    <Text style={styles.secondaryBtnText}>Voltar</Text>
                  </Pressable>
                  <Pressable
                    onPress={it.handleAddItem}
                    disabled={it.addSaving}
                    style={({ pressed }) => [styles.primaryBtn, (pressed || it.addSaving) && { opacity: 0.8 }]}
                    testID="pedido-form-add-confirm"
                  >
                    {it.addSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Adicionar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
