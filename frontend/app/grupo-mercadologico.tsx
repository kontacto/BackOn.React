import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField from "@/src/components/SelectField";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { buildTree, NivelFlat, NivelNode } from "@/src/utils/nivelTree";

type Conn = { servidor: string; banco: string; api: string };
type LookupItem = { codigo: number | string; descricao: string };

// Cadastro/Tabelas Auxiliares > Grupo Mercadológico (tabela `niveis`). Legado:
// FRMMANNIVNEW ("Definição de Níveis"). Árvore de até 5 níveis para classificar
// produtos/serviços — cada nó é uma linha própria em `niveis` (path materializado
// por nivel1..nivel5, não por parent_id). Montamos a árvore no cliente a partir
// da lista plana que o backend devolve.
export default function GrupoMercadologicoScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Grupo Mercadológico está disponível apenas no web."
        testID="grupo-mercadologico-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [flat, setFlat] = useState<NivelFlat[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const [centrosCusto, setCentrosCusto] = useState<LookupItem[]>([]);
  const [classes, setClasses] = useState<LookupItem[]>([]);
  const [subClasses, setSubClasses] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [parentCod, setParentCod] = useState<number | null>(null);
  const [parentLabel, setParentLabel] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [custo, setCusto] = useState<string | null>(null);
  const [classeEntrada, setClasseEntrada] = useState<string | null>(null);
  const [subClasseEntrada, setSubClasseEntrada] = useState<string | null>(null);
  const [classeSaida, setClasseSaida] = useState<string | null>(null);
  const [subClasseSaida, setSubClasseSaida] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/grupos-mercadologicos?${qs}`);
      const j = await r.json();
      setFlat(j?.success ? j.items || [] : []);
    } catch { setFlat([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const fetchLookup = async (path: string, setter: (items: LookupItem[]) => void) => {
      try {
        const r = await fetch(`${base}/api/${path}?${qs}`);
        const j = await r.json();
        if (j?.success && Array.isArray(j.items)) setter(j.items);
      } catch { /* silencioso — lookup opcional */ }
    };
    await Promise.all([
      fetchLookup("centro-custo", setCentrosCusto),
      fetchLookup("classes", setClasses),
      fetchLookup("sub-classes", setSubClasses),
    ]);
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc);
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  const tree = useMemo(() => buildTree(flat), [flat]);

  const term = search.trim().toLowerCase();
  const matchesSearch = (n: NivelNode): boolean =>
    n.descricao.toLowerCase().includes(term) || n.children.some(matchesSearch);
  const visibleTree = term ? tree.filter(matchesSearch) : tree;

  useEffect(() => {
    if (!term) return;
    setExpanded((prev) => {
      const next = new Set(prev);
      const walk = (nodes: NivelNode[]) => {
        for (const n of nodes) {
          if (matchesSearch(n)) next.add(n.cod_nivel);
          walk(n.children);
        }
      };
      walk(tree);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [term]);

  const toggleExpand = (cod: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cod)) next.delete(cod); else next.add(cod);
      return next;
    });
  };

  const clearForm = () => {
    setDescricao(""); setCusto(null);
    setClasseEntrada(null); setSubClasseEntrada(null); setClasseSaida(null); setSubClasseSaida(null);
  };

  const openNewRoot = () => {
    setEditCod(null); setParentCod(null); setParentLabel(null); clearForm(); setFormOpen(true);
  };
  const openNewChild = (parent: NivelNode) => {
    setEditCod(null); setParentCod(parent.cod_nivel); setParentLabel(parent.descricao); clearForm(); setFormOpen(true);
  };
  const openEdit = (n: NivelNode) => {
    setEditCod(n.cod_nivel); setParentCod(null); setParentLabel(null);
    setDescricao(n.descricao); setCusto(n.custo != null ? String(n.custo) : null);
    setClasseEntrada(n.classe_entrada != null ? String(n.classe_entrada) : null);
    setSubClasseEntrada(n.sub_classe_entrada != null ? String(n.sub_classe_entrada) : null);
    setClasseSaida(n.classe_saida != null ? String(n.classe_saida) : null);
    setSubClasseSaida(n.sub_classe_saida != null ? String(n.sub_classe_saida) : null);
    setFormOpen(true);
  };

  const centrosOpts = centrosCusto.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));
  const classesOpts = classes.map((i) => ({ value: i.codigo, label: i.descricao }));
  const subClassesOpts = subClasses.map((i) => ({ value: i.codigo, label: i.descricao }));

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/grupos-mercadologicos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          cod_nivel: editCod, parent_cod_nivel: parentCod, descricao: descricao.trim(),
          custo: custo ? parseInt(custo, 10) : null,
          classe_entrada: classeEntrada ? parseInt(classeEntrada, 10) : null,
          sub_classe_entrada: subClasseEntrada ? parseInt(subClasseEntrada, 10) : null,
          classe_saida: classeSaida ? parseInt(classeSaida, 10) : null,
          sub_classe_saida: subClasseSaida ? parseInt(subClasseSaida, 10) : null,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        showToast(j.message || "Grupo gravado.");
        setFormOpen(false);
        if (parentCod) setExpanded((prev) => new Set(prev).add(parentCod));
        load(conn);
      } else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (n: NivelNode) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/grupos-mercadologicos/${n.cod_nivel}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("GRUPO_MERCAD.GRAVAR") || isMaster;
  const canDel = can("GRUPO_MERCAD.EXCLUIR") || isMaster;

  const renderNode = (n: NivelNode) => {
    const isOpen = expanded.has(n.cod_nivel);
    const hasChildren = n.children.length > 0;
    return (
      <View key={n.cod_nivel} style={{ marginLeft: (n.depth - 1) * spacing.lg }}>
        <View style={styles.row} testID={`nivel-${n.cod_nivel}`}>
          <Pressable onPress={() => hasChildren && toggleExpand(n.cod_nivel)} hitSlop={8} style={{ opacity: hasChildren ? 1 : 0.25 }}>
            <Ionicons name={isOpen ? "chevron-down" : "chevron-forward"} size={16} color={colors.muted} />
          </Pressable>
          <Ionicons name={hasChildren ? "folder-outline" : "pricetag-outline"} size={16} color={colors.brandPrimary} />
          <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(n)}>
            <Text style={styles.rowTitle}>{n.descricao}</Text>
          </Pressable>
          {canSave && n.depth < 5 ? (
            <Pressable onPress={() => openNewChild(n)} hitSlop={8} testID={`nivel-add-${n.cod_nivel}`}>
              <Ionicons name="add-circle-outline" size={19} color={colors.brandPrimary} />
            </Pressable>
          ) : null}
          {canDel ? (
            <Pressable onPress={() => remove(n)} hitSlop={8} testID={`nivel-del-${n.cod_nivel}`}>
              <Ionicons name="trash-outline" size={18} color={colors.error} />
            </Pressable>
          ) : null}
        </View>
        {isOpen ? n.children.map(renderNode) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="grupo-mercadologico-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Grupo Mercadológico</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="grupo-mercadologico-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && visibleTree.length === 0 ? <Text style={styles.empty}>Nenhum grupo cadastrado.</Text> : null}
          {visibleTree.map(renderNode)}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNewRoot} style={styles.fab} testID="grupo-mercadologico-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>
                {editCod ? `Grupo ${editCod}` : parentLabel ? `Novo subnível em "${parentLabel}"` : "Novo nível raiz"}
              </Text>

              <Text style={styles.label}>Descrição *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: Automação"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={35}
                autoCapitalize="characters"
                testID="grupo-mercadologico-descricao"
              />

              <Text style={styles.label}>Centro Custo</Text>
              <SelectField value={custo} onChange={(v) => setCusto(v == null ? null : String(v))} options={centrosOpts} placeholder="Selecione…" allowClear compactWeb testID="grupo-mercadologico-custo" modalTitle="Centro Custo" />

              <Text style={styles.sectionTitle}>Definições para o Fluxo de Caixa</Text>

              <Text style={styles.label}>Classe (Compra/Entrada)</Text>
              <SelectField value={classeEntrada} onChange={(v) => setClasseEntrada(v == null ? null : String(v))} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="grupo-mercadologico-classe-entrada" modalTitle="Classe (Entrada)" />

              <Text style={styles.label}>Sub-Classe (Compra/Entrada)</Text>
              <SelectField value={subClasseEntrada} onChange={(v) => setSubClasseEntrada(v == null ? null : String(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb testID="grupo-mercadologico-subclasse-entrada" modalTitle="Sub-Classe (Entrada)" />

              <Text style={styles.label}>Classe (Venda/Saída)</Text>
              <SelectField value={classeSaida} onChange={(v) => setClasseSaida(v == null ? null : String(v))} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="grupo-mercadologico-classe-saida" modalTitle="Classe (Saída)" />

              <Text style={styles.label}>Sub-Classe (Venda/Saída)</Text>
              <SelectField value={subClasseSaida} onChange={(v) => setSubClasseSaida(v == null ? null : String(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb testID="grupo-mercadologico-subclasse-saida" modalTitle="Sub-Classe (Saída)" />

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="grupo-mercadologico-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? <View style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 1800, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.xs, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.xxl, marginBottom: spacing.sm,
  },
  rowTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 560 : undefined,
    maxHeight: "85%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: 4, textTransform: "uppercase" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
