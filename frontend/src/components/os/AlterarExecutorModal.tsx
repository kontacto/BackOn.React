// Alteração de Executor/Vendedor pós-fechamento — migração do botão
// `CmdAltExec` (branch F/PG de `CmDaltera_Click`, `FrmTraOsNew.frm`): corrige
// o técnico Executor (e o Vendedor) de um item já lançado depois que a O.S.
// foi Fechada ou Faturada, sem precisar reabrir a O.S. — preço/quantidade/
// desconto continuam bloqueados nessa situação (isso é a edição normal do
// item, exclusiva de O.S. Aberta). "Propagar" (sem equivalente no legado,
// conveniência desta migração) troca o mesmo valor anterior em todos os
// demais itens da O.S. que ainda tinham o executor/vendedor antigo.
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Switch, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { OSItemRow } from "./types";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  itens: OSItemRow[];
  funcOptions: SelectOption[];
  saving: boolean;
  onSave: (codOsProd: number, valores: { vendedor?: number | null; executor?: number | null }, propagarDemais: boolean) => void;
};

function AlterarExecutorRow({
  item, funcOptions, saving, onSave,
}: { item: OSItemRow; funcOptions: SelectOption[]; saving: boolean; onSave: Props["onSave"] }) {
  const [vendedor, setVendedor] = useState<number | null>(item.vendedor ?? null);
  const [executor, setExecutor] = useState<number | null>(item.executor ?? null);
  const [propagar, setPropagar] = useState(false);

  useEffect(() => {
    setVendedor(item.vendedor ?? null);
    setExecutor(item.executor ?? null);
  }, [item.vendedor, item.executor]);

  const mudou = vendedor !== (item.vendedor ?? null) || executor !== (item.executor ?? null);

  return (
    <View style={rs.row}>
      <Text style={rs.desc} numberOfLines={2}>{item.descricao}</Text>
      <View style={rs.fieldsRow}>
        <View style={{ flex: 1 }}>
          <Text style={rs.label}>Vendedor</Text>
          <SelectField
            value={vendedor}
            onChange={(v) => setVendedor(v == null ? null : Number(v))}
            options={funcOptions}
            placeholder="Vendedor"
            modalTitle="Selecionar Vendedor"
            allowClear
            compactWeb
            testID={`altexec-vendedor-${item.cod_os_prod}`}
          />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={rs.label}>Executor</Text>
          <SelectField
            value={executor}
            onChange={(v) => setExecutor(v == null ? null : Number(v))}
            options={funcOptions}
            placeholder="Executor"
            modalTitle="Selecionar Executor"
            allowClear
            compactWeb
            testID={`altexec-executor-${item.cod_os_prod}`}
          />
        </View>
      </View>
      <View style={rs.propagarRow}>
        <Switch value={propagar} onValueChange={setPropagar} testID={`altexec-propagar-${item.cod_os_prod}`} />
        <Text style={rs.propagarText}>Aplicar também aos demais itens que tinham o mesmo Vendedor/Executor</Text>
      </View>
      <Pressable
        onPress={() => onSave(item.cod_os_prod, { vendedor, executor }, propagar)}
        disabled={saving || !mudou}
        style={[rs.saveBtn, (saving || !mudou) && { opacity: 0.5 }]}
        testID={`altexec-salvar-${item.cod_os_prod}`}
      >
        {saving ? (
          <ActivityIndicator color={colors.onBrandPrimary} size="small" />
        ) : (
          <>
            <Ionicons name="checkmark" size={16} color={colors.onBrandPrimary} />
            <Text style={rs.saveBtnText}>Salvar</Text>
          </>
        )}
      </Pressable>
    </View>
  );
}

export default function AlterarExecutorModal({ visible, onClose, itens, funcOptions, saving, onSave }: Props) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Alteração de Executor/Vendedor</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              A O.S. já está Fechada/Faturada — preço, quantidade e desconto não podem mais mudar, mas
              é possível corrigir aqui qual técnico (Executor) e/ou Vendedor ficou responsável por cada item.
            </Text>
          </View>
          <ScrollView style={{ maxHeight: 480 }} keyboardShouldPersistTaps="handled">
            {itens.map((item) => (
              <AlterarExecutorRow key={item.cod_os_prod} item={item} funcOptions={funcOptions} saving={saving} onSave={onSave} />
            ))}
            {itens.length === 0 ? <Text style={styles.emptyText}>Nenhum item nesta O.S.</Text> : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  row: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 6 } as const,
  desc: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface },
  fieldsRow: { flexDirection: "row" as const, gap: spacing.sm },
  label: { fontSize: 10, color: colors.muted, marginBottom: 4 },
  propagarRow: { flexDirection: "row" as const, alignItems: "center" as const, gap: 8 },
  propagarText: { fontSize: 11, color: colors.muted, flex: 1 },
  saveBtn: {
    flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: 6, paddingVertical: 8, alignSelf: "flex-start" as const, paddingHorizontal: 14,
  },
  saveBtnText: { color: colors.onBrandPrimary, fontSize: 12, fontWeight: "600" as const },
};
