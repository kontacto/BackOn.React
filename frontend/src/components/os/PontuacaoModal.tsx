// Pontuação de Técnicos — migração do frame "Pontuação" (Command4_Click,
// frmtraosa.frm): nota de 0 a 999 pro Executor ("Técnico" na tela),
// Vendedor e Atendente de cada item da O.S. O Atendente é sempre o mesmo
// (o da O.S. inteira, não por item) — mostrado uma vez no topo, mas
// gravado por item (mesma redundância do legado, `os_produto.Pontuacao_A`
// repetido em toda linha).
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import { OSItemRow } from "./types";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  itens: OSItemRow[];
  atendenteNome: string;
  saving: boolean;
  onSave: (codOsProd: number, valores: { pontuacao_e?: number | null; pontuacao_v?: number | null; pontuacao_a?: number | null }) => void;
};

function clampPontos(v: string): number | null {
  const n = parseInt(v.replace(/\D/g, ""), 10);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(999, n));
}

function PontuacaoRow({ item, saving, onSave }: { item: OSItemRow; saving: boolean; onSave: Props["onSave"] }) {
  const [e, setE] = useState(item.pontuacao_e != null ? String(item.pontuacao_e) : "");
  const [v, setV] = useState(item.pontuacao_v != null ? String(item.pontuacao_v) : "");
  const [a, setA] = useState(item.pontuacao_a != null ? String(item.pontuacao_a) : "");

  useEffect(() => {
    setE(item.pontuacao_e != null ? String(item.pontuacao_e) : "");
    setV(item.pontuacao_v != null ? String(item.pontuacao_v) : "");
    setA(item.pontuacao_a != null ? String(item.pontuacao_a) : "");
  }, [item.pontuacao_e, item.pontuacao_v, item.pontuacao_a]);

  return (
    <View style={rs.row}>
      <Text style={rs.desc} numberOfLines={2}>{item.descricao}</Text>
      <View style={rs.fieldsRow}>
        <View style={rs.field}>
          <Text style={rs.label}>Técnico: {item.executor_nome || "—"}</Text>
          <TextInput value={e} onChangeText={setE} keyboardType="number-pad" maxLength={3} style={rs.input} testID={`pontuacao-e-${item.cod_os_prod}`} />
        </View>
        <View style={rs.field}>
          <Text style={rs.label}>Vendedor: {item.vendedor_nome || "—"}</Text>
          <TextInput value={v} onChangeText={setV} keyboardType="number-pad" maxLength={3} style={rs.input} testID={`pontuacao-v-${item.cod_os_prod}`} />
        </View>
        <View style={rs.field}>
          <Text style={rs.label}>Atendente</Text>
          <TextInput value={a} onChangeText={setA} keyboardType="number-pad" maxLength={3} style={rs.input} testID={`pontuacao-a-${item.cod_os_prod}`} />
        </View>
        <Pressable
          onPress={() => onSave(item.cod_os_prod, { pontuacao_e: clampPontos(e), pontuacao_v: clampPontos(v), pontuacao_a: clampPontos(a) })}
          disabled={saving}
          style={[rs.saveBtn, saving && { opacity: 0.6 }]}
          testID={`pontuacao-salvar-${item.cod_os_prod}`}
        >
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Ionicons name="checkmark" size={16} color={colors.onBrandPrimary} />}
        </Pressable>
      </View>
    </View>
  );
}

export default function PontuacaoModal({ visible, onClose, itens, atendenteNome, saving, onSave }: Props) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Pontuação de Técnicos</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              Avalie de 0 a 999 o desempenho do Técnico e do Vendedor de cada item, e do Atendente ({atendenteNome || "—"}) da O.S.
            </Text>
          </View>
          <ScrollView style={{ maxHeight: 480 }} keyboardShouldPersistTaps="handled">
            {itens.map((item) => (
              <PontuacaoRow key={item.cod_os_prod} item={item} saving={saving} onSave={onSave} />
            ))}
            {itens.length === 0 ? <Text style={styles.emptyText}>Nenhum item para pontuar.</Text> : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  row: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border } as const,
  desc: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface, marginBottom: 6 },
  fieldsRow: { flexDirection: "row" as const, gap: spacing.sm, alignItems: "flex-end" as const },
  field: { flex: 1, minWidth: 0 },
  label: { fontSize: 10, color: colors.muted, marginBottom: 4 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 6,
    paddingHorizontal: 8, paddingVertical: 8, fontSize: 13, color: colors.onSurface, textAlign: "center" as const,
  },
  saveBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: 6, width: 36, height: 36,
    alignItems: "center" as const, justifyContent: "center" as const,
  },
};
