// Bifurcação de faturamento Garantia×Cliente — quando a O.S. tem itens
// Cliente paga (situação=0) E Garantia/Interno/Contrato (situação<>0)
// pendentes ao mesmo tempo, o backend não fatura nada sozinho
// (`needs_choice=True`, ver `os_service._faturar_os_sync`) — este modal é
// a pergunta ao usuário, réplica funcional da tela bloqueante `Frame5`/
// `Check3`/`Check5` do legado (`FrmTraOsNew.frm`), sem os checkboxes: 3
// botões diretos (Só Cliente / Só Garantia / Faturar os Dois).
import { ActivityIndicator, Modal, Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";
import { styles } from "@/src/components/pedido/styles";

const isWeb = Platform.OS === "web";

type Bucket = "cliente" | "garantia" | "ambos";

type Props = {
  visible: boolean;
  onClose: () => void;
  totalCliente: number;
  totalGarantia: number;
  saving: boolean;
  onEscolher: (bucket: Bucket) => void;
};

export default function FaturarBucketModal({ visible, onClose, totalCliente, totalGarantia, saving, onEscolher }: Props) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>O que faturar agora?</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <View style={styles.itensHint}>
            <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
            <Text style={styles.itensHintText}>
              Esta O.S. tem itens de Cliente paga e itens de Garantia/Interno/Contrato pendentes de
              faturamento — cada bloco gera sua própria Comanda, com sua própria forma de pagamento.
            </Text>
          </View>
          <View style={{ gap: spacing.sm }}>
            <Pressable
              onPress={() => onEscolher("cliente")}
              disabled={saving}
              style={[rs.opcao, saving && { opacity: 0.6 }]}
              testID="faturar-bucket-cliente"
            >
              <Text style={rs.opcaoTitulo}>Só Cliente paga</Text>
              <Text style={rs.opcaoValor}>{formatBRL(totalCliente)}</Text>
            </Pressable>
            <Pressable
              onPress={() => onEscolher("garantia")}
              disabled={saving}
              style={[rs.opcao, saving && { opacity: 0.6 }]}
              testID="faturar-bucket-garantia"
            >
              <Text style={rs.opcaoTitulo}>Só Garantia/Interno/Contrato</Text>
              <Text style={rs.opcaoValor}>{formatBRL(totalGarantia)}</Text>
            </Pressable>
            <Pressable
              onPress={() => onEscolher("ambos")}
              disabled={saving}
              style={[rs.opcao, rs.opcaoDestaque, saving && { opacity: 0.6 }]}
              testID="faturar-bucket-ambos"
            >
              {saving ? (
                <ActivityIndicator color={colors.onBrandPrimary} size="small" />
              ) : (
                <>
                  <Text style={[rs.opcaoTitulo, { color: colors.onBrandPrimary }]}>Faturar os Dois</Text>
                  <Text style={[rs.opcaoValor, { color: colors.onBrandPrimary }]}>
                    {formatBRL(totalCliente + totalGarantia)}
                  </Text>
                </>
              )}
            </Pressable>
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const rs = {
  opcao: {
    flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "space-between" as const,
    borderWidth: 1, borderColor: colors.border, borderRadius: 8,
    paddingVertical: 12, paddingHorizontal: 14,
  },
  opcaoDestaque: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  opcaoTitulo: { fontSize: 13, fontWeight: "600" as const, color: colors.onSurface },
  opcaoValor: { fontSize: 13, fontWeight: "700" as const, color: colors.onSurface },
};
