// Modal único de item da O.S. Completa (busca → confirmar/editar), mesmo
// fluxo já usado e testado na O.S. Mobile (`app/os-form.tsx`'s modal
// inline) — só extraído pra componente próprio + Situação/Destino (não
// existia na Mobile) + estilos web-compact de `pedido/styles.ts` (mesma
// linguagem visual do Pedido Bar/Geral). Um modal só pros dois fluxos
// (Adicionar/Editar), igual ao original — não dois componentes separados,
// pra não duplicar o formulário inteiro por uma diferença pequena (o botão
// Excluir e o pré-preenchimento).
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum, calcDescUnit } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { styles } from "@/src/components/pedido/styles";
import { OS_SITUACAO_ITEM_OPTIONS } from "./types";
import { UseOSItens } from "./useOSItens";

const isWeb = Platform.OS === "web";

type Props = {
  it: UseOSItens;
  funcOptions: SelectOption[];
  tela?: string;
};

export default function OSItemModal({ it, funcOptions, tela = "OS_COMP" }: Props) {
  const { can } = usePermissions();
  const canDesc = can(`${tela}.DESC_ITEM`);
  const canSave = it.editItem ? can(`${tela}.EDIT_ITEM`) : can(`${tela}.ADD_ITEM`);
  const canDelete = can(`${tela}.DEL_ITEM`);

  const visible = it.addOpen || !!it.editItem;
  const editing = !!it.editItem;
  const onClose = () => { it.setAddOpen(false); it.setEditItem(null); };

  const qtd = editing ? it.editQtd : it.addQtd;
  const setQtd = editing ? it.setEditQtd : it.setAddQtd;
  const valor = editing ? it.editValor : it.addValor;
  const setValor = editing ? it.setEditValor : it.setAddValor;
  const descPct = editing ? it.editDescPct : it.addDescPct;
  const setDescPct = editing ? it.setEditDescPct : it.setAddDescPct;
  const descRs = editing ? it.editDescRs : it.addDescRs;
  const setDescRs = editing ? it.setEditDescRs : it.setAddDescRs;
  const acr = editing ? it.editAcr : it.addAcr;
  const setAcr = editing ? it.setEditAcr : it.setAddAcr;
  const compl = editing ? it.editCompl : it.addCompl;
  const setCompl = editing ? it.setEditCompl : it.setAddCompl;
  const vendedor = editing ? it.editVendedor : it.addVendedor;
  const setVendedor = editing ? it.setEditVendedor : it.setAddVendedor;
  const executor = editing ? it.editExecutor : it.addExecutor;
  const setExecutor = editing ? it.setEditExecutor : it.setAddExecutor;
  const situacao = editing ? it.editSituacao : it.addSituacao;
  const setSituacao = editing ? it.setEditSituacao : it.setAddSituacao;
  const saving = editing ? it.editSaving : it.addSaving;

  const desc = editing
    ? { descricao: it.editItem!.descricao, codigo: it.editItem!.produto, cod_fab: it.editItem!.cod_fab }
    : it.selProd
      ? { descricao: it.selProd.descricao, codigo: it.selProd.codigo, cod_fab: it.selProd.cod_fab || "" }
      : null;

  const showForm = editing || !!it.selProd;

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{editing ? "Editar Item" : it.selProd ? "Confirmar Item" : "Adicionar Item"}</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {!showForm ? (
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
                  testID="os-item-search"
                />
              </View>
              {it.prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 380 }} keyboardShouldPersistTaps="handled">
                {it.prodResults.map((p) => (
                  <Pressable
                    key={`${p.tipo}-${p.codigo}`}
                    onPress={() => it.pickProduto(p)}
                    style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`os-item-prod-${p.codigo}`}
                  >
                    <View style={[styles.itemTipo, p.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                      <Ionicons name={p.tipo === "P" ? "cube" : "construct"} size={16} color={p.tipo === "P" ? colors.brandPrimary : colors.warning} />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemDesc} numberOfLines={1}>{p.descricao}</Text>
                      <Text style={styles.itemSub} numberOfLines={1}>#{p.codigo}{p.cod_fab ? ` · ${p.cod_fab}` : ""}</Text>
                    </View>
                    <Text style={styles.itemTotal}>{formatBRL(p.valor)}</Text>
                  </Pressable>
                ))}
                {!it.prodLoading && it.prodTerm.trim().length >= 2 && it.prodResults.length === 0 ? (
                  <Text style={styles.resultSub}>Nenhum produto/serviço encontrado.</Text>
                ) : null}
              </ScrollView>
            </>
          ) : (
            <ScrollView style={{ maxHeight: 560 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: 8 }}>
                <View style={styles.selProdBox}>
                  <Text style={styles.itemDesc} numberOfLines={2}>{desc?.descricao}</Text>
                  <Text style={styles.itemSub}>#{desc?.codigo ?? ""}{desc?.cod_fab ? ` · ${desc.cod_fab}` : ""}</Text>
                </View>

                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Quantidade</Text>
                    <View style={styles.qtdInputRow}>
                      <TextInput value={qtd} onChangeText={setQtd} keyboardType="decimal-pad" style={[styles.input, { flex: 1 }]} testID="os-item-qtd" />
                      <TouchableOpacity onPress={() => setQtd(fmtNum(parseNum(qtd) + 1))} activeOpacity={0.7} style={styles.plusBtn}>
                        <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor unitário</Text>
                    <TextInput value={valor} onChangeText={setValor} keyboardType="decimal-pad" style={styles.input} testID="os-item-valor" />
                  </View>
                </View>

                <View style={styles.qtdRow}>
                  {canDesc ? (
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. %</Text>
                      <TextInput
                        value={descPct}
                        onChangeText={(v) => { setDescPct(v); if (parseNum(v) > 0) setDescRs(""); }}
                        editable={parseNum(descRs) <= 0}
                        keyboardType="decimal-pad" placeholder="0" placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(descRs) > 0 && styles.inputDisabled]}
                        testID="os-item-descpct"
                      />
                    </View>
                  ) : null}
                  {canDesc ? (
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                      <TextInput
                        value={descRs}
                        onChangeText={(v) => { setDescRs(v); if (parseNum(v) > 0) setDescPct(""); }}
                        editable={parseNum(descPct) <= 0}
                        keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(descPct) > 0 && styles.inputDisabled]}
                        testID="os-item-descrs"
                      />
                    </View>
                  ) : null}
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Acrésc. R$</Text>
                    <TextInput value={acr} onChangeText={setAcr} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="os-item-acr" />
                  </View>
                </View>

                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Vendedor</Text>
                    <SelectField
                      value={vendedor}
                      onChange={(v) => setVendedor(v == null ? null : Number(v))}
                      options={funcOptions}
                      placeholder="Vendedor"
                      modalTitle="Selecionar Vendedor"
                      allowClear
                      compactWeb
                      testID="os-item-vendedor"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Executor</Text>
                    <SelectField
                      value={executor}
                      onChange={(v) => setExecutor(v == null ? null : Number(v))}
                      options={funcOptions}
                      placeholder="Executor"
                      modalTitle="Selecionar Executor"
                      allowClear
                      compactWeb
                      testID="os-item-executor"
                    />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>Situação / Destino</Text>
                <SelectField
                  value={situacao}
                  onChange={(v) => setSituacao(v == null ? 0 : Number(v))}
                  options={OS_SITUACAO_ITEM_OPTIONS}
                  placeholder="Cliente paga"
                  modalTitle="Situação do Item"
                  searchable={false}
                  compactWeb
                  testID="os-item-situacao"
                />

                <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                <TextInput value={compl} onChangeText={setCompl} placeholder="Descrição complementar" placeholderTextColor={colors.muted} style={styles.input} testID="os-item-compl" />

                {(() => {
                  const pNormal = parseNum(valor);
                  const dUnit = calcDescUnit(pNormal, descPct, descRs);
                  const acrN = parseNum(acr);
                  const pVenda = pNormal - dUnit + acrN;
                  const qtdN = parseNum(qtd);
                  return (
                    <View style={styles.liquidoBox}>
                      <View style={styles.liquidoRow}>
                        <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                        <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                      </View>
                      {dUnit > 0 ? (
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Desconto total ({fmtNum(qtdN)}×)</Text>
                          <Text style={[styles.liquidoVal, { color: colors.error }]}>- {formatBRL(dUnit * qtdN)}</Text>
                        </View>
                      ) : null}
                      <View style={styles.previewRow}>
                        <Text style={styles.subtotalLabel}>Total do item</Text>
                        <Text style={styles.subtotalValue}>{formatBRL(qtdN * pVenda)}</Text>
                      </View>
                    </View>
                  );
                })()}

                <View style={styles.modalBtns}>
                  {editing ? (
                    canDelete ? (
                      <Pressable
                        onPress={it.handleDeleteItem}
                        disabled={saving}
                        style={({ pressed }) => [styles.deleteBtn, (pressed || saving) && { opacity: 0.8 }]}
                        testID="os-item-delete"
                      >
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : null
                  ) : (
                    <Pressable onPress={() => it.setSelProd(null)} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}>
                      <Text style={styles.secondaryBtnText}>Voltar</Text>
                    </Pressable>
                  )}
                  {canSave ? (
                    <Pressable
                      onPress={editing ? it.handleUpdateItem : it.handleAddItem}
                      disabled={saving}
                      style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, (pressed || saving) && { opacity: 0.8 }]}
                      testID="os-item-confirm"
                    >
                      {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>{editing ? "Salvar" : "Adicionar"}</Text>}
                    </Pressable>
                  ) : (
                    <Pressable onPress={onClose} style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, pressed && { opacity: 0.8 }]}>
                      <Text style={styles.primaryBtnText}>Fechar</Text>
                    </Pressable>
                  )}
                </View>
              </View>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
