// Modal de busca de Veículo (por placa ou descrição) — reaproveitável por
// qualquer tela que referencie um veículo por código (ex.: MDF-e). Mesmo
// padrão de `FornecedorSearchModal.tsx` — ver CLAUDE.md > "[Regras
// Globais]" (campo de identidade precisa de mecanismo de busca).
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { colors, radius, spacing } from "@/src/theme/colors";

const isCompactWeb = Platform.OS === "web";

export type VeiculoRow = {
  codigo: number;
  placa: string;
  descricao?: string | null;
  marca_desc?: string | null;
  modelo_desc?: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  term: string;
  setTerm: (v: string) => void;
  loading: boolean;
  results: VeiculoRow[];
  onPick: (v: VeiculoRow) => void;
};

export default function VeiculoSearchModal({ visible, onClose, term, setTerm, loading, results, onPick }: Props) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Buscar Veículo</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <View style={styles.searchWrap}>
            <Ionicons name="search" size={16} color={colors.muted} />
            <TextInput
              value={term}
              onChangeText={setTerm}
              placeholder="Placa ou descrição…"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              autoFocus
              testID="veiculo-search-input"
              autoComplete="off"
              autoCorrect={false}
              textContentType="none"
              importantForAutofill="no"
            />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          <ScrollView style={{ maxHeight: 380 }}>
            {results.map((v) => (
              <Pressable
                key={v.codigo}
                onPress={() => onPick(v)}
                style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`veiculo-search-result-${v.codigo}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowNome} numberOfLines={1}>{v.placa}</Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {[v.descricao, v.marca_desc, v.modelo_desc].filter(Boolean).join(" · ")}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
            {!loading && term.trim().length >= 2 && results.length === 0 ? (
              <Text style={styles.vazio}>Nenhum veículo encontrado.</Text>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  bgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  card: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  cardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center", maxHeight: "80%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  row: {
    flexDirection: "row", alignItems: "center", paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: colors.border, gap: spacing.sm,
  },
  rowNome: { fontSize: 14, color: colors.onSurface, fontWeight: "600" },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  vazio: { color: colors.muted, fontSize: 13, padding: spacing.md, textAlign: "center" },
});
