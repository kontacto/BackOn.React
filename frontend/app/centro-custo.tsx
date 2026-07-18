import { useCallback, useEffect, useState } from "react";
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

type Conn = { servidor: string; banco: string; api: string };
type LookupItem = { codigo: number | string; descricao: string };
type CentroCusto = {
  codigo: number;
  descricao: string;
  classe_entrada: number | null;
  sub_classe_entrada: number | null;
  classe_saida: number | null;
  sub_classe_saida: number | null;
};

// Financeiro > Fluxo de Caixa > Centro de Custo (tabela `centro_custo`).
// Diferente de Plano de Contas, `codigo` aqui é digitado pelo usuário (não é
// IDENTITY) — mesmo padrão do legado FrmManCeC. Fica travado depois de criado.
export default function CentroCustoScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Centro de Custo está disponível apenas no web."
        testID="centro-custo-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<CentroCusto[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [classes, setClasses] = useState<LookupItem[]>([]);
  const [subClasses, setSubClasses] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [classeEntrada, setClasseEntrada] = useState<string | null>(null);
  const [subClasseEntrada, setSubClasseEntrada] = useState<string | null>(null);
  const [classeSaida, setClasseSaida] = useState<string | null>(null);
  const [subClasseSaida, setSubClasseSaida] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/financeiro/centro-custo?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
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
      load(cc, "");
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const classeLabel = (cod: number | null) => (cod == null ? "-" : classes.find((c) => String(c.codigo) === String(cod))?.descricao || String(cod));
  const subClasseLabel = (cod: number | null) => (cod == null ? "-" : subClasses.find((c) => String(c.codigo) === String(cod))?.descricao || String(cod));

  const nextCodigoSuggestion = () => {
    const max = items.reduce((m, it) => Math.max(m, it.codigo), 0);
    return String(max + 1);
  };

  const openNew = () => {
    setEditCod(null); setCodigo(nextCodigoSuggestion()); setDescricao("");
    setClasseEntrada(null); setSubClasseEntrada(null); setClasseSaida(null); setSubClasseSaida(null);
    setFormOpen(true);
  };
  const openEdit = (c: CentroCusto) => {
    setEditCod(c.codigo); setCodigo(String(c.codigo)); setDescricao(c.descricao);
    setClasseEntrada(c.classe_entrada != null ? String(c.classe_entrada) : null);
    setSubClasseEntrada(c.sub_classe_entrada != null ? String(c.sub_classe_entrada) : null);
    setClasseSaida(c.classe_saida != null ? String(c.classe_saida) : null);
    setSubClasseSaida(c.sub_classe_saida != null ? String(c.sub_classe_saida) : null);
    setFormOpen(true);
  };

  const classesOpts = classes.map((i) => ({ value: i.codigo, label: i.descricao }));
  const subClassesOpts = subClasses.map((i) => ({ value: i.codigo, label: i.descricao }));

  const save = async () => {
    if (!conn) return;
    const codNum = parseInt(codigo, 10);
    if (!codigo.trim() || !Number.isFinite(codNum) || codNum <= 0) { showToast("Informe um código válido."); return; }
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/financeiro/centro-custo`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: codNum, descricao: descricao.trim(),
          classe_entrada: classeEntrada ? parseInt(classeEntrada, 10) : null,
          sub_classe_entrada: subClasseEntrada ? parseInt(subClasseEntrada, 10) : null,
          classe_saida: classeSaida ? parseInt(classeSaida, 10) : null,
          sub_classe_saida: subClasseSaida ? parseInt(subClasseSaida, 10) : null,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Centro de custo gravado."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (c: CentroCusto) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/financeiro/centro-custo/${c.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("CENTRO_CUSTO.GRAVAR") || isMaster;
  const canDel = can("CENTRO_CUSTO.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="centro-custo-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Centro de Custo</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por código ou descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="centro-custo-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum centro de custo cadastrado.</Text> : null}
          {items.map((c) => (
            <View key={c.codigo} style={styles.row} testID={`centro-custo-${c.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(c)}>
                <Text style={styles.rowTitle}>{c.codigo} · {c.descricao}</Text>
                <Text style={styles.rowSub}>Entrada: {classeLabel(c.classe_entrada)} / {subClasseLabel(c.sub_classe_entrada)}</Text>
                <Text style={styles.rowSub}>Saída: {classeLabel(c.classe_saida)} / {subClasseLabel(c.sub_classe_saida)}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(c)} hitSlop={8} testID={`centro-custo-del-${c.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="centro-custo-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod ? `Centro de Custo ${editCod}` : "Novo centro de custo"}</Text>

              <Text style={styles.label}>Código *</Text>
              <TextInput
                value={codigo}
                onChangeText={(v) => setCodigo(v.replace(/[^0-9]/g, ""))}
                keyboardType="number-pad"
                style={[styles.input, editCod != null && styles.inputDisabled]}
                editable={editCod == null}
                testID="centro-custo-codigo"
              />

              <Text style={styles.label}>Descrição *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: Produtos"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={30}
                autoCapitalize="characters"
                testID="centro-custo-descricao"
              />

              <Text style={styles.sectionTitle}>Definições para o Fluxo de Caixa</Text>

              <Text style={styles.label}>Classe (Compra/Entrada)</Text>
              <SelectField value={classeEntrada} onChange={(v) => setClasseEntrada(v == null ? null : String(v))} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="centro-custo-classe-entrada" modalTitle="Classe (Entrada)" />

              <Text style={styles.label}>Sub-Classe (Compra/Entrada)</Text>
              <SelectField value={subClasseEntrada} onChange={(v) => setSubClasseEntrada(v == null ? null : String(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb testID="centro-custo-subclasse-entrada" modalTitle="Sub-Classe (Entrada)" />

              <Text style={styles.label}>Classe (Venda/Saída)</Text>
              <SelectField value={classeSaida} onChange={(v) => setClasseSaida(v == null ? null : String(v))} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="centro-custo-classe-saida" modalTitle="Classe (Saída)" />

              <Text style={styles.label}>Sub-Classe (Venda/Saída)</Text>
              <SelectField value={subClasseSaida} onChange={(v) => setSubClasseSaida(v == null ? null : String(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb testID="centro-custo-subclasse-saida" modalTitle="Sub-Classe (Saída)" />

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="centro-custo-salvar">
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
  webShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
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
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
