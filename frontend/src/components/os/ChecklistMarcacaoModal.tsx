// Modal de classificação de uma marcação recém-feita no diagrama do
// Checklist de Entrada de Veículo (ChecklistVeiculoDiagrama.tsx) — pedido
// explícito do usuário 2026-08-26. Tier "confirmação pontual sobre um
// único registro" (360–480px, CLAUDE.md "Padrões de UI — Modais"), mesmo
// padrão de EditItemModal.tsx.
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "@/src/components/pedido/styles";
import SelectField from "@/src/components/SelectField";
import { TIPO_AVARIA_OPTIONS } from "./types";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  onConfirmar: (tipoAvaria: string, descricao: string) => void;
  saving: boolean;
};

export default function ChecklistMarcacaoModal({ visible, onClose, onConfirmar, saving }: Props) {
  const [tipo, setTipo] = useState<string>("AMASSADO");
  const [descricao, setDescricao] = useState("");

  useEffect(() => {
    if (visible) { setTipo("AMASSADO"); setDescricao(""); }
  }, [visible]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Marcar Avaria</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <Text style={styles.fieldLabel}>Tipo de Avaria</Text>
          <SelectField
            value={tipo}
            onChange={(v) => setTipo(String(v ?? "AMASSADO"))}
            options={TIPO_AVARIA_OPTIONS}
            compactWeb
            testID="checklist-marcacao-tipo"
          />
          <Text style={[styles.fieldLabel, { marginTop: 8 }]}>Descrição (opcional)</Text>
          <TextInput
            value={descricao}
            onChangeText={setDescricao}
            placeholder="Ex.: porta dianteira esquerda"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="checklist-marcacao-descricao"
          />

          <View style={[styles.modalBtns, { marginTop: 12 }]}>
            <Pressable onPress={onClose} disabled={saving} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}>
              <Text style={styles.secondaryBtnText}>Cancelar</Text>
            </Pressable>
            <Pressable
              onPress={() => onConfirmar(tipo, descricao)}
              disabled={saving}
              style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, (pressed || saving) && { opacity: 0.8 }]}
              testID="checklist-marcacao-confirmar"
            >
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Marcar</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
