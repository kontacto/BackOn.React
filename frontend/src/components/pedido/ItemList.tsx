// Seção "Itens do Pedido": lista de itens + botões de desconto geral/concedidos + subtotal.
import { ActivityIndicator, Pressable, Text, TouchableOpacity, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";
import { ItemRow } from "./types";
import { UsePedidoItens } from "./usePedidoItens";

type Props = {
  editing: boolean;
  isAberto: boolean;
  it: UsePedidoItens;
};

export default function ItemList({ editing, isAberto, it }: Props) {
  const { itens, subtotal, itensLoading, descTotalItens, geralAtual } = it;
  const { can } = usePermissions();
  const canEditItem = can("PEDIDO.EDIT_ITEM") || can("PEDIDO.DEL_ITEM") || can("PEDIDO.DESC_ITEM");

  return (
    <>
      <View style={styles.itensHeader}>
        <Text style={styles.sectionTitle}>
          Itens do Pedido {itens.length ? `(${itens.length})` : ""}
        </Text>
        {editing && isAberto && can("PEDIDO.ADD_ITEM") ? (
          <Pressable
            onPress={it.openAddModal}
            style={({ pressed }) => [styles.addItemBtn, pressed && { opacity: 0.8 }]}
            testID="pedido-form-add-item"
          >
            <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.addItemBtnText}>Adicionar</Text>
          </Pressable>
        ) : null}
      </View>

      {!editing ? (
        <View style={styles.itensHint}>
          <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
          <Text style={styles.itensHintText}>Grave o pedido para adicionar itens.</Text>
        </View>
      ) : itensLoading && itens.length === 0 ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
      ) : itens.length === 0 ? (
        <View style={styles.itensHint}>
          <Ionicons name="cube-outline" size={18} color={colors.muted} />
          <Text style={styles.itensHintText}>Nenhum item adicionado.</Text>
        </View>
      ) : (
        <View style={{ gap: 8 }}>
          {itens.map((item: ItemRow) => (
            <Pressable
              key={item.codauto}
              onPress={canEditItem ? () => it.openEditModal(item) : undefined}
              disabled={!canEditItem}
              style={({ pressed }) => [styles.itemRow, pressed && canEditItem && { opacity: 0.8 }]}
              testID={`pedido-form-item-${item.codauto}`}
            >
              <View style={[styles.itemTipo, item.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                <Ionicons
                  name={item.tipo === "P" ? "cube" : "construct"}
                  size={16}
                  color={item.tipo === "P" ? colors.brandPrimary : colors.warning}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.itemDesc} numberOfLines={1}>{item.descricao || item.produto}</Text>
                {item.complemento ? (
                  <Text style={styles.itemCompl} numberOfLines={1}>{item.complemento}</Text>
                ) : null}
                <Text style={styles.itemSub}>
                  {item.cod_fab ? `${item.cod_fab} · ` : ""}{item.qtd.toLocaleString("pt-BR")} {item.unidade} × {formatBRL(item.valor_unitario)}
                </Text>
              </View>
              <Text style={styles.itemTotal}>{formatBRL(item.total)}</Text>
            </Pressable>
          ))}

          {isAberto && can("PEDIDO.DESC_GERAL") ? (
            <TouchableOpacity
              onPress={it.openGeralModal}
              activeOpacity={0.8}
              style={styles.geralBtn}
              testID="pedido-form-desconto-geral-btn"
            >
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Ionicons name="cash-outline" size={16} color={colors.brandPrimary} />
                <Text style={styles.geralBtnLabel}>
                  Desconto geral{geralAtual > 0 ? ` (${formatBRL(geralAtual)})` : ""}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}

          {descTotalItens > 0 && can("PEDIDO.VER_DESCONTOS") ? (
            <TouchableOpacity
              onPress={it.openDescontos}
              activeOpacity={0.8}
              style={styles.descBtn}
              testID="pedido-form-descontos-btn"
            >
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                <Ionicons name="pricetag" size={15} color={colors.error} />
                <Text style={styles.descBtnLabel}>Descontos concedidos</Text>
              </View>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                <Text style={styles.descBtnValue}>- {formatBRL(descTotalItens)}</Text>
                <Ionicons name="chevron-forward" size={16} color={colors.error} />
              </View>
            </TouchableOpacity>
          ) : null}

          <View style={styles.subtotalRow}>
            <Text style={styles.subtotalLabel}>Subtotal</Text>
            <Text style={styles.subtotalValue}>{formatBRL(subtotal)}</Text>
          </View>
        </View>
      )}
    </>
  );
}
