// Autorização/Expedição de Itens — migração da aba "Autorização de Itens"
// (`FrmTraOsNew.frm`, Revenda). Lista os itens da O.S. com checkbox de
// seleção em lote + 4 ações: Autorizar (reserva o estoque de verdade, só
// quando a empresa exige Autorização — ver `os.exige_aprovacao_itens_os`),
// Remover Autorização (estorna), Autorização de Expedição (registro de
// picking, não mexe em estoque) e Remover Autorização de Expedição.
//
// Modo Didático: cada botão já é auto-explicativo pelo rótulo + badge de
// estado do item (Autorizado/Expedido/usuário/data) — sem ícone solto sem
// texto, então não precisa de tooltip individual (ver CLAUDE.md > "Padrões
// de UI" > seção 4, regra só se aplica a botões SÓ-ícone).
import { Modal, Platform, Pressable, ScrollView, Text, View, ActivityIndicator } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import { OSItemRow } from "./types";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  itens: OSItemRow[];
  selecionados: number[];
  onToggle: (codOsProd: number) => void;
  saving: boolean;
  exigeAprovacao: boolean;
  exigeExpedicao: boolean;
  canAutorizar: boolean;
  canExpedir: boolean;
  onAutorizar: () => void;
  onRemoverAutorizacao: () => void;
  onExpedir: () => void;
  onRemoverExpedicao: () => void;
};

function ItemRowView({ item, checked, onToggle }: { item: OSItemRow; checked: boolean; onToggle: () => void }) {
  const autorizado = !!item.data_autorizacao;
  const expedido = !!item.data_expedicao;
  return (
    <Pressable style={rs.row} onPress={onToggle} testID={`autorizacao-item-${item.cod_os_prod}`}>
      <Ionicons
        name={checked ? "checkbox" : "square-outline"}
        size={20}
        color={checked ? colors.brandPrimary : colors.muted}
      />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={rs.desc} numberOfLines={1}>{item.descricao}</Text>
        <View style={rs.badgesRow}>
          <View style={[rs.badge, autorizado ? rs.badgeOn : rs.badgeOff]}>
            <Text style={[rs.badgeText, autorizado && rs.badgeTextOn]}>
              {autorizado ? `Autorizado · ${item.usuario_autorizacao_nome || "—"}` : "Não autorizado"}
            </Text>
          </View>
          <View style={[rs.badge, expedido ? rs.badgeOn : rs.badgeOff]}>
            <Text style={[rs.badgeText, expedido && rs.badgeTextOn]}>
              {expedido ? `Expedido · ${item.usuario_expedicao_nome || "—"}` : "Não expedido"}
            </Text>
          </View>
        </View>
      </View>
    </Pressable>
  );
}

export default function AutorizacaoItensModal({
  visible, onClose, itens, selecionados, onToggle, saving,
  exigeAprovacao, exigeExpedicao, canAutorizar, canExpedir,
  onAutorizar, onRemoverAutorizacao, onExpedir, onRemoverExpedicao,
}: Props) {
  const temSelecao = selecionados.length > 0;
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Autorização de Itens</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              {exigeAprovacao
                ? "Marque os itens e toque em Autorizar para liberar a saída do estoque."
                : "Autorização opcional — o estoque já foi reservado na inclusão do item."}
              {exigeExpedicao ? " Itens precisam ser expedidos (separados fisicamente) antes de serem autorizados." : ""}
            </Text>
          </View>
          <ScrollView style={{ maxHeight: 380 }}>
            {itens.map((item) => (
              <ItemRowView
                key={item.cod_os_prod}
                item={item}
                checked={selecionados.includes(item.cod_os_prod)}
                onToggle={() => onToggle(item.cod_os_prod)}
              />
            ))}
            {itens.length === 0 ? <Text style={styles.emptyText}>Nenhum item na O.S.</Text> : null}
          </ScrollView>
          <View style={rs.actions}>
            {canAutorizar ? (
              <>
                <Pressable
                  onPress={onAutorizar}
                  disabled={saving || !temSelecao}
                  style={[rs.actionBtn, rs.actionBtnPrimary, (saving || !temSelecao) && rs.actionBtnDisabled]}
                  testID="autorizacao-btn-autorizar"
                >
                  {saving ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : <Ionicons name="lock-open-outline" size={16} color={colors.onBrandPrimary} />}
                  <Text style={rs.actionBtnTextPrimary}>Autorizar</Text>
                </Pressable>
                <Pressable
                  onPress={onRemoverAutorizacao}
                  disabled={saving || !temSelecao}
                  style={[rs.actionBtn, (saving || !temSelecao) && rs.actionBtnDisabled]}
                  testID="autorizacao-btn-remover-autorizacao"
                >
                  <Ionicons name="lock-closed-outline" size={16} color={colors.onSurface} />
                  <Text style={rs.actionBtnText}>Remover Autorização</Text>
                </Pressable>
              </>
            ) : null}
            {canExpedir && exigeExpedicao ? (
              <>
                <Pressable
                  onPress={onExpedir}
                  disabled={saving || !temSelecao}
                  style={[rs.actionBtn, (saving || !temSelecao) && rs.actionBtnDisabled]}
                  testID="autorizacao-btn-expedir"
                >
                  <Ionicons name="cube-outline" size={16} color={colors.onSurface} />
                  <Text style={rs.actionBtnText}>Autorizar Expedição</Text>
                </Pressable>
                <Pressable
                  onPress={onRemoverExpedicao}
                  disabled={saving || !temSelecao}
                  style={[rs.actionBtn, (saving || !temSelecao) && rs.actionBtnDisabled]}
                  testID="autorizacao-btn-remover-expedicao"
                >
                  <Ionicons name="arrow-undo-outline" size={16} color={colors.onSurface} />
                  <Text style={rs.actionBtnText}>Remover Expedição</Text>
                </Pressable>
              </>
            ) : null}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  row: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  desc: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface },
  badgesRow: { flexDirection: "row" as const, gap: 6, marginTop: 4, flexWrap: "wrap" as const },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  badgeOff: { backgroundColor: colors.surfaceTertiary },
  badgeOn: { backgroundColor: colors.success + "22" },
  badgeText: { fontSize: 10, color: colors.muted },
  badgeTextOn: { color: colors.success, fontWeight: "600" as const },
  actions: {
    flexDirection: "row" as const, flexWrap: "wrap" as const, gap: spacing.sm,
    marginTop: spacing.md, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border,
  },
  actionBtn: {
    flexDirection: "row" as const, alignItems: "center" as const, gap: 6,
    paddingHorizontal: spacing.sm, paddingVertical: 8, borderRadius: 8,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  actionBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  actionBtnDisabled: { opacity: 0.5 },
  actionBtnText: { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface },
  actionBtnTextPrimary: { fontSize: 12, fontWeight: "600" as const, color: colors.onBrandPrimary },
};
