// Anexos do Pedido (Gestor de Documentos) — botão "Anexo" entre "Faturar
// Pedido" e "Imprimir" na toolbar do Pedido Bar (pedido explícito do
// usuário, 2026-07-16). Mesmo padrão arquitetural já usado por Cliente/
// Serviços/Fornecedores/Produto Completo (ver GestorDocumentosSection.tsx),
// mas Pedido não é uma entidade principal do Gestor de Documentos — é
// gravado como anexo do CLIENTE (`cod_grupo=1`), filtrado por sub-grupo
// "Pedidos de Venda" (`cod_sub_grupo=2`, confirmado ao vivo em GERDELL/
// BARESTELA, ver PENDENCIAS.md > "Gestor de Documentos") + `referencia` =
// número do pedido. Mesmo raciocínio documentado em
// GestorDocumentosSection.tsx (props `codSubGrupo`/`referencia`).
//
// Largura maior que o tier "seleção/busca" padrão (560px, "Modal/Selector
// Standard" em CLAUDE.md) porque o componente embutido tem lista + painel
// de preview lado a lado (mesma ressalva já registrada em CLAUDE.md > "Full
// CRUD Form Screen Standard" sobre a aba Anexos precisar de mais largura) —
// ainda centralizado/com raio completo/borda, só a largura diverge do
// tier padrão.
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { AppModal } from "@/src/components/AppModal";
import { Ionicons } from "@/src/components/Ionicons";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import { colors, radius, spacing } from "@/src/theme/colors";
import { Connection } from "@/src/utils/storage/connections";

// Sub-grupo "Pedidos de Venda" dentro do grupo Clientes — schema
// `gestor_docs_sub_grupos`, conferido ao vivo (ver PENDENCIAS.md).
export const GESTOR_DOC_SUBGRUPO_PEDIDO = 2;

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  pedido: number;
  clienteCodigo: number;
};

export default function AnexosPedidoModal({ visible, onClose, conn, pedido, clienteCodigo }: Props) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Anexos do Pedido nº {pedido}</Text>
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
                codSubGrupo={GESTOR_DOC_SUBGRUPO_PEDIDO}
                referencia={pedido}
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
