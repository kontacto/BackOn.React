import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL } from "@/src/theme/webLayout";
import { CatNode, keyOf, collectKeys, flatten } from "@/src/utils/permissoesTree";

const SAVE_BTN_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 4px 8px rgba(0, 0, 0, 0.2)" }
    : {
        shadowColor: "#000",
        shadowOpacity: 0.2,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 4 },
        elevation: 6,
      };

// ---------------- Tipos ----------------
type Classe = { codigo: number; classe: string };

// [GLOBAL] Pedido/O.S. Mobile (pré-venda rápida) e Pedido/O.S. Completo são
// mutuamente exclusivos: marcar um desmarca o outro (tela + ações) por
// completo. Ver CLAUDE.md > "Transações Screens Strategy". A Tela Principal
// (ModuleTiles.tsx) usa qual dos dois está marcado pra decidir pra onde os
// cards de Pedido/O.S. apontam.
const EXCLUSIVE_PAIRS: [string, string][] = [
  ["PEDIDO", "PEDIDO_COMP"],
  ["OS", "OS_COMP"],
];

function clearTela(next: Set<string>, flatMap: Record<string, CatNode>, tela: string) {
  const node = flatMap[keyOf({ tipo: "TELA", tela, comando: "" })];
  if (node) collectKeys(node).forEach((k) => next.delete(k));
}

// `node` é o nó que o usuário efetivamente clicou (TELA ou BOTAO) — usado
// pra saber a DIREÇÃO do toggle (qual lado do par foi ligado agora, pra
// desligar só o outro). Quando o toggle não veio de um clique num nó do
// par (ex.: marcar o menu Transações inteiro, ou "Marcar todas as
// permissões"), não há sinal de direção — nesse caso, se os dois lados
// acabarem ligados ao mesmo tempo, mantém a versão Mobile (já funcional)
// e desliga a Completa (ainda placeholder).
function applyPedidoOsExclusivity(
  node: CatNode | null,
  next: Set<string>,
  flatMap: Record<string, CatNode>
) {
  if (node) {
    const pair = EXCLUSIVE_PAIRS.find(([a, b]) => node.tela === a || node.tela === b);
    if (pair) {
      const [mobile, completo] = pair;
      clearTela(next, flatMap, node.tela === mobile ? completo : mobile);
      return;
    }
  }
  for (const [mobile, completo] of EXCLUSIVE_PAIRS) {
    const mobileNode = flatMap[keyOf({ tipo: "TELA", tela: mobile, comando: "" })];
    const completoNode = flatMap[keyOf({ tipo: "TELA", tela: completo, comando: "" })];
    if (!mobileNode || !completoNode) continue;
    const mobileOn = collectKeys(mobileNode).some((k) => next.has(k));
    const completoOn = collectKeys(completoNode).some((k) => next.has(k));
    if (mobileOn && completoOn) clearTela(next, flatMap, completo);
  }
}

export default function PermissoesScreen() {
  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="A gestão de grupos e permissões está disponível apenas no web."
        testID="permissoes-web-only"
      />
    );
  }

  const router = useRouter();
  const { reload: reloadPermissions } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const [conn, setConn] = useState<Connection | null>(null);
  const [catalogo, setCatalogo] = useState<CatNode[]>([]);
  const [classes, setClasses] = useState<Classe[]>([]);
  const [classe, setClasse] = useState<Classe | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
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
    const next = allOn ? new Set<string>() : new Set(allKeys);
    if (!allOn) applyPedidoOsExclusivity(null, next, flatMap);
    setSelected(next);
  };

  // Carrega catálogo + classes ao abrir
  const boot = useCallback(async () => {
    setLoading(true);
    const session = await getSession();
    if (!session) {
      // Sessão já foi encerrada (ex.: logout disparado enquanto esta tela
      // ainda estava montada em segundo plano) — não é erro de conexão,
      // só não há mais sessão pra carregar. Mesmo padrão de funcionarios.tsx.
      router.replace("/login");
      setLoading(false);
      return;
    }
    const conns = await listConnections();
    const c = conns.find((x) => x.empresa === session.empresa) ?? null;
    setConn(c);
    if (!c) {
      fb.showError("Conexão não encontrada.");
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
      else fb.showError(clsR?.message || "Erro ao carregar classes.");
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [fb]);

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
          fb.showError(r?.message || "Erro ao carregar permissões.");
        }
      } catch (e) {
        fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setLoading(false);
      }
    },
    [conn, fb]
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
    if (!allOn) applyPedidoOsExclusivity(node, next, flatMap);
    setSelected(next);
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
          usuario_alteracao: auditCtx.usuario_alteracao,
          plataforma: auditCtx.plataforma,
          itens,
        }),
      }).then((x) => x.json());
      if (r?.success) fb.showSuccess(r.message || "Permissões salvas.");
      else fb.showError(r?.message || "Erro ao salvar.");
      if (r?.success) await reloadPermissions();
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
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
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Permissões</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={Platform.OS === "web" ? styles.webScrollWrap : undefined}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          <View style={Platform.OS === "web" ? styles.webShell : undefined}>
            {/* Combobox de classe */}
            <View style={styles.pickerWrap}>
              <Text style={styles.pickerLabel}>Grupo (classe)</Text>
              <Pressable
                style={[styles.pickerBtn, Platform.OS === "web" && styles.pickerBtnWeb]}
                onPress={() => setPickerOpen(true)}
                testID="perm-classe-picker"
              >
                <Text style={[styles.pickerValue, !classe && { color: colors.muted }]}>
                  {classe ? classe.classe : "Selecione um grupo…"}
                </Text>
                <Ionicons name="chevron-down" size={18} color={colors.muted} />
              </Pressable>
            </View>


            <View style={Platform.OS === "web" ? styles.webBody : undefined}>
              {loading ? (
                <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} />
              ) : !classe ? (
                <View style={[styles.placeholder, Platform.OS === "web" && styles.placeholderWeb]}>
                  <Ionicons name="lock-closed-outline" size={40} color={colors.muted} />
                  <Text style={styles.placeholderText}>
                    Selecione um grupo para configurar as permissões.
                  </Text>
                </View>
              ) : (
                <FlatList
                  style={Platform.OS === "web" ? styles.treeListWeb : undefined}
                  data={catalogo}
                  keyExtractor={(n) => keyOf(n)}
                  renderItem={({ item }) => renderNode(item, 0)}
                  ListHeaderComponent={
                    <Pressable
                      onPress={toggleAll}
                      style={[styles.selectAllRow, Platform.OS === "web" && styles.selectAllRowWeb]}
                      testID="perm-select-all"
                    >
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
                  contentContainerStyle={
                    Platform.OS === "web"
                      ? styles.listContentWeb
                      : { paddingVertical: spacing.sm, paddingBottom: 110 }
                  }
                />
              )}
            </View>

            {/* Botão salvar */}
            {classe && !loading ? (
              <Pressable
                onPress={handleSave}
                disabled={saving}
                style={({ pressed }) => [
                  styles.saveBtn,
                  Platform.OS === "web" && styles.saveBtnWeb,
                  SAVE_BTN_SHADOW_STYLE,
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
          </View>
        </View>
      </View>

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
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  pickerWrap: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, gap: 6 },
  webScrollWrap: { flex: 1, alignItems: "center" },
  webFrame: {
    ...WEB_CONTENT_SHELL,
    flex: 1,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.xl,
  },
  webShell: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingBottom: spacing.md,
    overflow: "hidden",
    boxShadow: "0 10px 28px rgba(0, 0, 0, 0.06)",
  },
  webBody: {
    flex: 1,
    minHeight: 0,
  },
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
  pickerBtnWeb: { backgroundColor: colors.surfaceSecondary },
  pickerValue: { fontSize: 15, color: colors.onSurface, fontWeight: "500" },
  placeholder: { alignItems: "center", justifyContent: "center", marginTop: 60, gap: 12, paddingHorizontal: spacing.xl },
  placeholderWeb: {
    marginTop: spacing.lg,
    minHeight: 280,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
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
  selectAllRowWeb: {
    marginHorizontal: spacing.md,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderRadius: radius.md,
    borderWidth: 1,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    backgroundColor: colors.surface,
    boxShadow: "0 4px 14px rgba(0, 0, 0, 0.05)",
  },
  selectAllLabel: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  listContentWeb: { paddingVertical: spacing.sm, paddingBottom: 120 },
  treeListWeb: { flex: 1, minHeight: 0 },
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
  },
  saveBtnWeb: {
    position: "relative",
    left: undefined,
    right: undefined,
    bottom: undefined,
    width: "100%",
    maxWidth: 360,
    alignSelf: "center",
    marginTop: spacing.md,
    marginBottom: spacing.md,
  },
  saveLabel: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "600" },
  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  modalCard: {
    width: "100%",
    maxWidth: Platform.OS === "web" ? 380 : undefined,
    alignSelf: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.lg,
    gap: 4,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  modalItem: { flexDirection: "row", alignItems: "center", gap: 12, paddingVertical: 12 },
  modalItemText: { fontSize: 15, color: colors.onSurface },
});
