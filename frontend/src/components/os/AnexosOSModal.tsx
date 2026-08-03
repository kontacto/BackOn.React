// Anexos da O.S. (Gestor de Documentos) — mesmo padrão de
// `pedido/AnexosPedidoModal.tsx`: não é entidade principal do Gestor de
// Documentos, grava como anexo do CLIENTE (`cod_grupo=1`), sub-grupo
// "Ordens de Serviço" (`cod_sub_grupo=4`, confirmado ao vivo em GERDELL/
// BARESTELA, ver PENDENCIAS.md > "Gestor de Documentos") + `referencia` =
// número da O.S.
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AppModal } from "@/src/components/AppModal";
import { Ionicons } from "@/src/components/Ionicons";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import { colors, radius, spacing } from "@/src/theme/colors";
import { Connection } from "@/src/utils/storage/connections";

export const GESTOR_DOC_SUBGRUPO_OS = 4;

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  os: number;
  clienteCodigo: number;
};

export default function AnexosOSModal({ visible, onClose, conn, os, clienteCodigo }: Props) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Anexos da O.S. nº {os}</Text>
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
                codSubGrupo={GESTOR_DOC_SUBGRUPO_OS}
                referencia={os}
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
