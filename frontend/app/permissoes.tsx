import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";

// ---------------- Tipos ----------------
type CatNode = {
  tipo: "MENU" | "TELA" | "BOTAO";
  tela: string;
  comando: string;
  nome: string;
  children: CatNode[];
};
type Classe = { codigo: number; classe: string };

// chave única de um nó (tipo|tela|comando)
const keyOf = (n: { tipo: string; tela: string; comando: string }) =>
  `${n.tipo}|${n.tela}|${n.comando || ""}`;

// percorre a árvore e devolve todas as chaves descendentes (inclui o próprio nó)
function collectKeys(node: CatNode, acc: string[] = []): string[] {
  acc.push(keyOf(node));
  node.children.forEach((c) => collectKeys(c, acc));
  return acc;
}

// mapa chave -> nó (para reconstruir os itens ao salvar)
function flatten(nodes: CatNode[], map: Record<string, CatNode> = {}): Record<string, CatNode> {
  nodes.forEach((n) => {
    map[keyOf(n)] = n;
    flatten(n.children, map);
  });
  return map;
}

export default function PermissoesScreen() {
  const router = useRouter();
  const { reload: reloadPermissions } = usePermissions();
  const [conn, setConn] = useState<Connection | null>(null);
  const [catalogo, setCatalogo] = useState<CatNode[]>([]);
  const [classes, setClasses] = useState<Classe[]>([]);
  const [classe, setClasse] = useState<Classe | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);

  const flatMap = useMemo(() => flatten(catalogo), [catalogo]);

  // Todas as chaves do catálogo (para o checkbox pai "Marcar tudo")
  const allKeys = useMemo(() => catalogo.flatMap((n) => collectKeys(n)), [catalogo]);
  const allState: boolean | "partial" = useMemo(() => {
    if (allKeys.length === 0) return false;
    const sel = allKeys.filter((k) => selected.has(k)).length;
    if (sel === 0) return false;
    if (sel === allKeys.length) return true;
    return "partial";
  }, [allKeys, selected]);

  const toggleAll = () => {
    const allOn = allKeys.length > 0 && allKeys.every((k) => selected.has(k));
    setSelected(allOn ? new Set() : new Set(allKeys));
    setFeedback(null);
  };

  // Carrega catálogo + classes ao abrir
  const boot = useCallback(async () => {
    setLoading(true);
    setError(null);
    const session = await getSession();
    const conns = await listConnections();
    const c = conns.find((x) => x.empresa === session?.empresa) ?? null;
    setConn(c);
    if (!c) {
      setError("Conexão não encontrada.");
      setLoading(false);
      return;
    }
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [catR, clsR] = await Promise.all([
        fetch(`${base}/api/permissoes/catalogo?${qs}`).then((r) => r.json()),
        fetch(`${base}/api/permissoes/classes?${qs}`).then((r) => r.json()),
      ]);
      if (catR?.catalogo) {
        setCatalogo(catR.catalogo);
        // expande os menus por padrão
        setExpanded(new Set((catR.catalogo as CatNode[]).map((m) => keyOf(m))));
      }
      if (clsR?.success) setClasses(clsR.items);
      else setError(clsR?.message || "Erro ao carregar classes.");
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      boot();
    }, [boot])
  );

  // Carrega permissões da classe selecionada
  const loadClasse = useCallback(
    async (cl: Classe) => {
      if (!conn) return;
      setClasse(cl);
      setFeedback(null);
      setError(null);
      setLoading(true);
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(
        conn.banco
      )}&classe=${cl.codigo}`;
      try {
        const r = await fetch(`${base}/api/permissoes?${qs}`).then((x) => x.json());
        if (r?.success) {
          const s = new Set<string>(
            (r.items as { tipo: string; tela: string; comando: string }[]).map((i) => keyOf(i))
          );
          setSelected(s);
        } else {
          setError(r?.message || "Erro ao carregar permissões.");
        }
      } catch (e) {
        setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setLoading(false);
      }
    },
    [conn]
  );

  // estado de um nó: true (todos descendentes), false (nenhum), "partial"
  const nodeState = (node: CatNode): boolean | "partial" => {
    const keys = collectKeys(node);
    const sel = keys.filter((k) => selected.has(k)).length;
    if (sel === 0) return false;
    if (sel === keys.length) return true;
    return "partial";
  };

  const toggleNode = (node: CatNode) => {
    const keys = collectKeys(node);
    const next = new Set(selected);
    const allOn = keys.every((k) => next.has(k));
    if (allOn) keys.forEach((k) => next.delete(k));
    else keys.forEach((k) => next.add(k));
    setSelected(next);
    setFeedback(null);
  };

  const toggleExpand = (k: string) => {
    const next = new Set(expanded);
    if (next.has(k)) next.delete(k);
    else next.add(k);
    setExpanded(next);
  };

  const handleSave = async () => {
    if (!conn || !classe) return;
    setSaving(true);
    setError(null);
    setFeedback(null);
    const itens = Array.from(selected)
      .map((k) => flatMap[k])
      .filter(Boolean)
      .map((n) => ({
        tipo: n.tipo,
        tela: n.tela,
        comando: n.comando || "",
        nome: n.nome,
        formulario: n.tela,
      }));
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/permissoes/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor,
          banco: conn.banco,
          classe: classe.codigo,
          itens,
        }),
      }).then((x) => x.json());
      if (r?.success) setFeedback(r.message || "Permissões salvas.");
      else setError(r?.message || "Erro ao salvar.");
      if (r?.success) await reloadPermissions();
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  // ---------------- Render de um nó (recursivo) ----------------
  const renderNode = (node: CatNode, depth: number) => {
    const k = keyOf(node);
    const st = nodeState(node);
    const hasChildren = node.children.length > 0;
    const isOpen = expanded.has(k);
    const icon =
      st === true ? "checkbox" : st === "partial" ? "remove-circle" : "square-outline";
    const iconColor =
      st === true ? colors.brandPrimary : st === "partial" ? colors.warning : colors.muted;

    return (
      <View key={k}>
        <View style={[styles.row, { paddingLeft: spacing.md + depth * 22 }]}>
          {hasChildren ? (
            <Pressable onPress={() => toggleExpand(k)} hitSlop={{ top: 12, bottom: 12, left: 14, right: 14 }} style={styles.caret}>
              <Ionicons
                name={isOpen ? "chevron-down" : "chevron-forward"}
                size={16}
                color={colors.muted}
              />
            </Pressable>
          ) : (
            <View style={styles.caret} />
          )}
          <Pressable
            onPress={() => toggleNode(node)}
            style={styles.checkArea}
            testID={`perm-${k}`}
          >
            <Ionicons name={icon as any} size={22} color={iconColor} />
            <Text
              style={[
                styles.rowLabel,
                node.tipo === "MENU" && styles.menuLabel,
                node.tipo === "TELA" && styles.telaLabel,
              ]}
            >
              {node.nome}
            </Text>
          </Pressable>
        </View>
        {hasChildren && isOpen ? node.children.map((c) => renderNode(c, depth + 1)) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="permissoes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Permissões</Text>
        <View style={{ width: 40 }} />
      </View>

      {/* Combobox de classe */}
      <View style={styles.pickerWrap}>
        <Text style={styles.pickerLabel}>Grupo (classe)</Text>
        <Pressable
          style={styles.pickerBtn}
          onPress={() => setPickerOpen(true)}
          testID="perm-classe-picker"
        >
          <Text style={[styles.pickerValue, !classe && { color: colors.muted }]}>
            {classe ? classe.classe : "Selecione um grupo…"}
          </Text>
          <Ionicons name="chevron-down" size={18} color={colors.muted} />
        </Pressable>
      </View>

      {error ? <Text style={styles.errorText}>{error}</Text> : null}
      {feedback ? <Text style={styles.feedbackText}>{feedback}</Text> : null}

      {loading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} />
      ) : !classe ? (
        <View style={styles.placeholder}>
          <Ionicons name="lock-closed-outline" size={40} color={colors.muted} />
          <Text style={styles.placeholderText}>
            Selecione um grupo para configurar as permissões.
          </Text>
        </View>
      ) : (
        <FlatList
          data={catalogo}
          keyExtractor={(n) => keyOf(n)}
          renderItem={({ item }) => renderNode(item, 0)}
          ListHeaderComponent={
            <Pressable onPress={toggleAll} style={styles.selectAllRow} testID="perm-select-all">
              <Ionicons
                name={
                  (allState === true
                    ? "checkbox"
                    : allState === "partial"
                    ? "remove-circle"
                    : "square-outline") as any
                }
                size={22}
                color={
                  allState === true
                    ? colors.brandPrimary
                    : allState === "partial"
                    ? colors.warning
                    : colors.muted
                }
              />
              <Text style={styles.selectAllLabel}>Marcar todas as permissões</Text>
            </Pressable>
          }
          contentContainerStyle={{ paddingVertical: spacing.sm, paddingBottom: 110 }}
        />
      )}

      {/* Botão salvar */}
      {classe && !loading ? (
        <Pressable
          onPress={handleSave}
          disabled={saving}
          style={({ pressed }) => [
            styles.saveBtn,
            (pressed || saving) && { opacity: 0.8 },
          ]}
          testID="perm-save"
        >
          {saving ? (
            <ActivityIndicator color={colors.onBrandPrimary} />
          ) : (
            <>
              <Ionicons name="save-outline" size={18} color={colors.onBrandPrimary} />
              <Text style={styles.saveLabel}>Salvar permissões</Text>
            </>
          )}
        </Pressable>
      ) : null}

      {/* Modal do combobox */}
      <Modal visible={pickerOpen} transparent animationType="fade" onRequestClose={() => setPickerOpen(false)}>
        <Pressable style={styles.modalBackdrop} onPress={() => setPickerOpen(false)}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Selecione o grupo</Text>
            {classes.map((cl) => (
              <Pressable
                key={cl.codigo}
                style={styles.modalItem}
                onPress={() => {
                  setPickerOpen(false);
                  loadClasse(cl);
                }}
                testID={`perm-classe-${cl.codigo}`}
              >
                <Ionicons
                  name={classe?.codigo === cl.codigo ? "radio-button-on" : "radio-button-off"}
                  size={20}
                  color={colors.brandPrimary}
                />
                <Text style={styles.modalItemText}>{cl.classe}</Text>
              </Pressable>
            ))}
          </View>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.sm,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: {
    flex: 1,
    textAlign: "center",
    color: colors.onBrandPrimary,
    fontSize: 17,
    fontWeight: "600",
  },
  pickerWrap: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: 6 },
  pickerLabel: {
    fontSize: 12,
    fontWeight: "600",
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  pickerBtn: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 12,
  },
  pickerValue: { fontSize: 15, color: colors.onSurface, fontWeight: "500" },
  errorText: { marginHorizontal: spacing.lg, marginTop: spacing.sm, color: colors.error, fontSize: 13 },
  feedbackText: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    color: colors.success,
    fontSize: 13,
    fontWeight: "500",
  },
  placeholder: { alignItems: "center", justifyContent: "center", marginTop: 60, gap: 12, paddingHorizontal: spacing.xl },
  placeholderText: { color: colors.muted, fontSize: 14, textAlign: "center" },
  selectAllRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
    paddingVertical: 12,
    paddingHorizontal: spacing.md,
    marginBottom: 4,
    backgroundColor: colors.surfaceSecondary ?? "#f3f5f9",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
  },
  selectAllLabel: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  row: { flexDirection: "row", alignItems: "center", paddingRight: spacing.md, minHeight: 44 },
  caret: { width: 22, alignItems: "center", justifyContent: "center" },
  checkArea: { flex: 1, flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 6 },
  rowLabel: { fontSize: 15, color: colors.onSurface, flex: 1 },
  menuLabel: { fontWeight: "700", color: colors.brandPrimary },
  telaLabel: { fontWeight: "600" },
  saveBtn: {
    position: "absolute",
    left: spacing.lg,
    right: spacing.lg,
    bottom: spacing.lg,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    paddingVertical: 14,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 8,
    shadowOffset: { width: 0, height: 4 },
    elevation: 6,
  },
  saveLabel: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "600" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: 4 },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  modalItem: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  modalItemText: { fontSize: 15, color: colors.onSurface },
});
