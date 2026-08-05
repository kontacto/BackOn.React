// Modal "Configurar Impressão" do Checkout — define o Computador+Impressora
// desta estação, salvos localmente no navegador (não no banco — ver
// src/utils/storage/impressaoSilenciosa.ts). Quando preenchido, o botão
// "Imprimir" da tela passa a enfileirar direto pro agente local
// (POST /api/impressao/fila) em vez de abrir o preview + diálogo do
// navegador — ver PENDENCIAS.md > "Impressão Silenciosa — Fila + Agente
// Local" pro desenho completo.
import { useEffect, useState } from "react";
import { Modal, Platform, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";
import { ImpressaoSilenciosaConfig } from "@/src/utils/storage/impressaoSilenciosa";

const isWeb = Platform.OS === "web";

type Props = {
  visible: boolean;
  onClose: () => void;
  config: ImpressaoSilenciosaConfig | null;
  onSave: (config: ImpressaoSilenciosaConfig) => void;
  onClear: () => void;
};

export default function ConfiguracaoImpressaoModal({ visible, onClose, config, onSave, onClear }: Props) {
  const [computador, setComputador] = useState("");
  const [impressora, setImpressora] = useState("");

  useEffect(() => {
    if (!visible) return;
    setComputador(config?.computador || "");
    setImpressora(config?.impressora || "");
  }, [visible, config]);

  if (!visible) return null;

  const podeSalvar = computador.trim().length > 0 && impressora.trim().length > 0;

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={ps.modalHeader}>
            <Text style={ps.modalTitle}>Configurar Impressão</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <Text style={{ fontSize: 13, color: colors.muted, marginBottom: spacing.md }}>
            Preenchendo os dois campos abaixo, o botão "Imprimir" passa a mandar o cupom direto pra impressora desta
            estação, sem abrir diálogo nenhum — precisa do Agente de Impressão instalado e configurado nesta máquina
            (print-agent). Deixando em branco, "Imprimir" continua abrindo a prévia com o diálogo de impressão do
            navegador, como sempre foi.
          </Text>

          <View style={{ gap: spacing.sm }}>
            <View>
              <Text style={ps.fieldLabel}>Nome do Computador</Text>
              <TextInput
                value={computador}
                onChangeText={setComputador}
                placeholder='ex.: "computador" do config.json do agente'
                placeholderTextColor={colors.muted}
                style={inputStyle()}
                testID="config-impressao-computador"
              />
            </View>
            <View>
              <Text style={ps.fieldLabel}>Nome da Impressora</Text>
              <TextInput
                value={impressora}
                onChangeText={setImpressora}
                placeholder="Nome exato dela no Windows"
                placeholderTextColor={colors.muted}
                style={inputStyle()}
                testID="config-impressao-impressora"
              />
            </View>
          </View>

          <View style={ps.modalBtns}>
            {config ? (
              <Pressable
                onPress={() => { onClear(); onClose(); }}
                style={[ps.secondaryBtn, { borderColor: colors.error }]}
                testID="config-impressao-remover"
              >
                <Text style={[ps.secondaryBtnText, { color: colors.error }]}>Remover</Text>
              </Pressable>
            ) : (
              <Pressable onPress={onClose} style={ps.secondaryBtn} testID="config-impressao-cancelar">
                <Text style={ps.secondaryBtnText}>Cancelar</Text>
              </Pressable>
            )}
            <Pressable
              onPress={() => { onSave({ computador: computador.trim(), impressora: impressora.trim() }); onClose(); }}
              disabled={!podeSalvar}
              style={[ps.primaryBtn, !podeSalvar && { opacity: 0.5 }]}
              testID="config-impressao-salvar"
            >
              <Text style={ps.primaryBtnText}>Salvar</Text>
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

function inputStyle() {
  return {
    borderWidth: 1, borderColor: colors.border, borderRadius: 8,
    paddingHorizontal: spacing.sm, paddingVertical: 10, color: colors.onSurface,
    marginTop: 4,
  } as const;
}
