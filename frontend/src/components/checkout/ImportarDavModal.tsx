// Modal "Importar Pedido/O.S." do Checkout — réplica de `Insere_Dav`
// (FrmPafOFF.frm, F4/F8). "Orçamento" (F7 no legado) não é um caso à parte
// nesta migração — um Orçamento já é só um Pedido em situação Aberto (ver
// CLAUDE.md > "Regras Globais de Pré-venda"), então só existem os tipos
// Pedido/O.S. aqui.
import { useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";

const isWeb = Platform.OS === "web";

const TIPOS_DAV: SelectOption[] = [
  { value: "PED", label: "Pedido de Venda" },
  { value: "OS", label: "Ordem de Serviço" },
];

type Props = {
  visible: boolean;
  onClose: () => void;
  onConfirm: (tipoDav: string, documento: number) => Promise<{ success: boolean; message?: string }>;
};

export default function ImportarDavModal({ visible, onClose, onConfirm }: Props) {
  const [tipoDav, setTipoDav] = useState<string>("PED");
  const [numero, setNumero] = useState("");
  const [saving, setSaving] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  const confirmar = async () => {
    const documento = parseInt(numero, 10);
    if (!Number.isFinite(documento) || documento <= 0) {
      setErro("Informe um número válido.");
      return;
    }
    setErro(null);
    setSaving(true);
    try {
      const r = await onConfirm(tipoDav, documento);
      if (r.success) {
        setNumero("");
      } else {
        setErro(r.message || "Não foi possível importar o documento.");
      }
    } finally {
      setSaving(false);
    }
  };

  if (!visible) return null;
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={ps.modalHeader}>
            <Text style={ps.modalTitle}>Importar Pedido/O.S.</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <Text style={{ fontSize: 13, color: colors.muted, marginBottom: spacing.md }}>
            Traz os itens de um Pedido de Venda ou O.S. já Fechado pra esta venda — o documento de origem é marcado
            como Faturado.
          </Text>

          <View style={{ gap: spacing.sm }}>
            <SelectField
              label="Tipo de Documento"
              value={tipoDav}
              onChange={(v) => setTipoDav(String(v))}
              options={TIPOS_DAV}
              compactWeb
              searchable={false}
              testID="importar-dav-tipo"
            />
            <TextInput
              value={numero}
              onChangeText={setNumero}
              keyboardType="numeric"
              placeholder="Número do documento"
              placeholderTextColor={colors.muted}
              style={{
                borderWidth: 1, borderColor: colors.border, borderRadius: 8,
                paddingHorizontal: spacing.sm, paddingVertical: 10, color: colors.onSurface,
              }}
              testID="importar-dav-numero"
            />
          </View>

          {erro ? <Text style={{ color: colors.error, fontSize: 13, marginTop: spacing.sm }}>{erro}</Text> : null}

          <View style={ps.modalBtns}>
            <Pressable onPress={onClose} style={ps.secondaryBtn} testID="importar-dav-cancelar">
              <Text style={ps.secondaryBtnText}>Voltar</Text>
            </Pressable>
            <Pressable onPress={confirmar} disabled={saving} style={[ps.primaryBtn, saving && { opacity: 0.7 }]} testID="importar-dav-confirmar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={ps.primaryBtnText}>Importar</Text>}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}
