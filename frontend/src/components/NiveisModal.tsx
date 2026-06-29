// Modal de seleção de Nível (árvore de níveis de produto) para o relatório de Margem.
import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { apiGet } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

export type NivelNode = {
  cod_nivel: number | string;
  codigo: string;
  profundidade: number;
  descricao: string;
};

type Props = {
  visible: boolean;
  conn: Connection | null;
  onClose: () => void;
  onPick: (codigo: string, label: string) => void;
};

export default function NiveisModal({ visible, conn, onClose, onPick }: Props) {
  const [loading, setLoading] = useState(false);
  const [niveis, setNiveis] = useState<NivelNode[]>([]);
  const [term, setTerm] = useState("");
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    if (!visible || !conn) return;
    setLoading(true);
    setErro(null);
    (async () => {
      try {
        const j = await apiGet(conn, "/api/relatorios/margem-lucro/niveis");
        if (j?.success) setNiveis(j.niveis || []);
        else setErro(j?.message || "Falha ao carregar níveis.");
      } catch (e) {
        setErro(e instanceof Error ? e.message : "Falha ao carregar níveis.");
      } finally {
        setLoading(false);
      }
    })();
  }, [visible, conn]);

  const filtrados = useMemo(() => {
    const t = term.trim().toLowerCase();
    if (!t) return niveis;
    return niveis.filter(
      (n) => n.codigo.toLowerCase().includes(t) || (n.descricao || "").toLowerCase().includes(t)
    );
  }, [niveis, term]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.bg} onPress={onClose}>
        <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Selecionar Nível</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          <View style={styles.searchWrap}>
            <Ionicons name="search" size={16} color={colors.muted} />
            <TextInput
              value={term}
              onChangeText={setTerm}
              placeholder="Buscar por código ou descrição…"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              testID="ml-niveis-search"
            />
          </View>

          <Pressable
            onPress={() => onPick("", "Todos os níveis")}
            style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
            testID="ml-nivel-todos"
          >
            <Text style={styles.rowTodos}>Todos os níveis</Text>
          </Pressable>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
          {erro ? <Text style={styles.erro}>{erro}</Text> : null}

          <ScrollView style={{ maxHeight: 420 }}>
            {filtrados.map((n) => (
              <Pressable
                key={`${n.cod_nivel}-${n.codigo}`}
                onPress={() => onPick(n.codigo, `${n.codigo} · ${n.descricao}`)}
                style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`ml-nivel-${n.codigo}`}
              >
                <View style={{ paddingLeft: Math.max(0, (n.profundidade - 1)) * spacing.md, flex: 1 }}>
                  <Text style={styles.rowDesc} numberOfLines={1}>{n.descricao || "—"}</Text>
                  <Text style={styles.rowCod}>{n.codigo}</Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
            {!loading && !erro && filtrados.length === 0 ? (
              <Text style={styles.vazio}>Nenhum nível encontrado.</Text>
            ) : null}
          </ScrollView>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  card: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
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
  rowTodos: { fontSize: 14, fontWeight: "700", color: colors.brandPrimary },
  rowDesc: { fontSize: 14, color: colors.onSurface },
  rowCod: { fontSize: 11, color: colors.muted, marginTop: 2 },
  erro: { color: colors.danger, fontSize: 13, marginVertical: spacing.sm },
  vazio: { color: colors.muted, fontSize: 13, padding: spacing.md, textAlign: "center" },
});
