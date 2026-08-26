// Modal de busca de Município (por nome) — reaproveitável por qualquer
// tela que referencie um município por código IBGE (hoje: MDF-e >
// Encerramento, `GET /api/mdfe/municipios`). Mesmo padrão de
// `VeiculoSearchModal.tsx`/`FornecedorSearchModal.tsx` — ver CLAUDE.md >
// "[Regras Globais]" (campo de identidade precisa de mecanismo de busca).
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { colors, radius, spacing } from "@/src/theme/colors";

const isCompactWeb = Platform.OS === "web";

export type MunicipioRow = {
  codigo: number;
  descricao: string;
  uf?: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  term: string;
  setTerm: (v: string) => void;
  loading: boolean;
  results: MunicipioRow[];
  onPick: (m: MunicipioRow) => void;
};

export default function MunicipioSearchModal({ visible, onClose, term, setTerm, loading, results, onPick }: Props) {
  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Buscar Município</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <View style={styles.searchWrap}>
            <Ionicons name="search" size={16} color={colors.muted} />
            <TextInput
              value={term}
              onChangeText={setTerm}
              placeholder="Nome do município…"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              autoFocus
              testID="municipio-search-input"
              autoComplete="off"
              autoCorrect={false}
              textContentType="none"
              importantForAutofill="no"
            />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          <ScrollView style={{ maxHeight: 380 }}>
            {results.map((m) => (
              <Pressable
                key={m.codigo}
                onPress={() => onPick(m)}
                style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`municipio-search-result-${m.codigo}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowNome} numberOfLines={1}>{m.descricao}</Text>
                  {m.uf ? <Text style={styles.rowSub} numberOfLines={1}>{m.uf}</Text> : null}
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
            {!loading && term.trim().length >= 2 && results.length === 0 ? (
              <Text style={styles.vazio}>Nenhum município encontrado.</Text>
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
