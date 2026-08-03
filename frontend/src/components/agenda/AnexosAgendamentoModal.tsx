// Anexos do Agendamento (Gestor de Documentos) — mesmo padrão de
// AnexosPedidoModal.tsx: Agenda não é entidade principal do Gestor de
// Documentos, é gravada como anexo do CLIENTE (`cod_grupo=1`), sub-grupo
// "Agendamentos" (`cod_sub_grupo=16` — valor do código-fonte VB6, escolhido
// pelo usuário 2026-07-28; PENDENTE confirmar contra conexão de teste real,
// ver PENDENCIAS.md) + `referencia` = código do agendamento (codagenda).
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AppModal } from "@/src/components/AppModal";
import { Ionicons } from "@/src/components/Ionicons";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import { colors, radius, spacing } from "@/src/theme/colors";
import { Connection } from "@/src/utils/storage/connections";

export const GESTOR_DOC_SUBGRUPO_AGENDAMENTO = 16;

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  codagenda: number;
  clienteCodigo: number;
};

export default function AnexosAgendamentoModal({ visible, onClose, conn, codagenda, clienteCodigo }: Props) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Anexos do Agendamento nº {codagenda}</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          {conn ? (
            <ScrollView style={{ maxHeight: 560 }}>
              <GestorDocumentosSection
                api={conn.api}
                servidor={conn.servidor}
                banco={conn.banco}
                codGrupo={GESTOR_DOC_GRUPO_CLIENTE}
                codigoEntidade={clienteCodigo}
                codSubGrupo={GESTOR_DOC_SUBGRUPO_AGENDAMENTO}
                referencia={codagenda}
              />
            </ScrollView>
          ) : null}
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  bg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "center", alignItems: "center", padding: spacing.xl,
  },
  card: {
    width: "100%", maxWidth: 920, maxHeight: "88%",
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
});
