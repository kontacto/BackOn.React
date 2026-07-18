import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
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
type SubClasse = { codigo: number; classe: number; descricao: string; tipo: string; ativa: boolean };
type Classe = { codigo: number; descricao: string; tipo: string; sub_classes: SubClasse[] };

const TIPO_OPTIONS = [
  { value: "R", label: "Receita" },
  { value: "D", label: "Despesa" },
];

const tipoLabel = (t: string) => (t === "R" ? "Receita" : "Despesa");

// Financeiro > Fluxo de Caixa > Plano de Contas — árvore Classes/SubClasses
// (tabelas `classes`/`sub_classes`, classes.codigo = sub_classes.classe,
// sub_classes.tipo = 'D' despesa / 'R' receita). Modelo VB6 de origem: FrmManCla.
export default function PlanoContasScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Plano de Contas está disponível apenas no web."
        testID="plano-contas-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Classe[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const [formOpen, setFormOpen] = useState(false);
  const [formKind, setFormKind] = useState<"classe" | "subclasse">("classe");
  const [editCod, setEditCod] = useState<number | null>(null);
  const [descricao, setDescricao] = useState("");
  const [tipo, setTipo] = useState<string | null>("D");
  const [classePai, setClassePai] = useState<number | null>(null);
  const [ativa, setAtiva] = useState(true);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/financeiro/plano-contas?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
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
    })();
  }, [router, load]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const toggleExpand = (cod: number) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cod)) next.delete(cod); else next.add(cod);
      return next;
    });
  };

  const openNewClasse = () => {
    setFormKind("classe"); setEditCod(null); setDescricao(""); setTipo("D"); setFormOpen(true);
  };
  const openEditClasse = (c: Classe) => {
    setFormKind("classe"); setEditCod(c.codigo); setDescricao(c.descricao); setTipo(c.tipo); setFormOpen(true);
  };
  const openNewSubClasse = (c: Classe) => {
    setFormKind("subclasse"); setEditCod(null); setDescricao(""); setTipo(c.tipo); setClassePai(c.codigo); setAtiva(true); setFormOpen(true);
  };
  const openEditSubClasse = (c: Classe, sc: SubClasse) => {
    setFormKind("subclasse"); setEditCod(sc.codigo); setDescricao(sc.descricao); setTipo(sc.tipo); setClassePai(c.codigo); setAtiva(sc.ativa); setFormOpen(true);
  };

  const classeOpts = items.map((c) => ({ value: c.codigo, label: c.descricao }));

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      if (formKind === "classe") {
        const r = await fetch(`${base}/api/financeiro/plano-contas/classe`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCod, descricao: descricao.trim(), tipo }),
        });
        const j = await r.json();
        if (j?.success) { showToast(j.message || "Classe gravada."); setFormOpen(false); load(conn, search); }
        else showToast(j?.message || "Falha ao gravar.");
      } else {
        if (!classePai) { showToast("Selecione a classe."); setSaving(false); return; }
        const r = await fetch(`${base}/api/financeiro/plano-contas/subclasse`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCod, classe: classePai, descricao: descricao.trim(), tipo, ativa }),
        });
        const j = await r.json();
        if (j?.success) {
          showToast(j.message || "SubClasse gravada."); setFormOpen(false);
          setExpanded((prev) => new Set(prev).add(classePai));
          load(conn, search);
        } else showToast(j?.message || "Falha ao gravar.");
      }
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const removeClasse = async (c: Classe) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/financeiro/plano-contas/classe/${c.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const removeSubClasse = async (sc: SubClasse) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/financeiro/plano-contas/subclasse/${sc.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("PLANO_CONTAS.GRAVAR") || isMaster;
  const canDel = can("PLANO_CONTAS.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="plano-contas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Plano de Contas</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por classe ou subclasse…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="plano-contas-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma classe cadastrada.</Text> : null}
          {items.map((c) => {
            const isOpen = expanded.has(c.codigo);
            return (
              <View key={c.codigo} style={styles.group}>
                <View style={styles.row} testID={`classe-${c.codigo}`}>
                  <Pressable onPress={() => toggleExpand(c.codigo)} hitSlop={8}>
                    <Ionicons name={isOpen ? "chevron-down" : "chevron-forward"} size={18} color={colors.muted} />
                  </Pressable>
                  <Pressable style={{ flex: 1 }} onPress={() => canSave && openEditClasse(c)}>
                    <Text style={styles.rowTitle}>{c.descricao}</Text>
                    <Text style={styles.rowSub}>{tipoLabel(c.tipo)} · {c.sub_classes.length} subclasse(s)</Text>
                  </Pressable>
                  {canSave ? (
                    <Pressable onPress={() => openNewSubClasse(c)} hitSlop={8} testID={`classe-add-sub-${c.codigo}`}>
                      <Ionicons name="add-circle-outline" size={20} color={colors.brandPrimary} />
                    </Pressable>
                  ) : null}
                  {canDel ? (
                    <Pressable onPress={() => removeClasse(c)} hitSlop={8} testID={`classe-del-${c.codigo}`}>
                      <Ionicons name="trash-outline" size={20} color={colors.error} />
                    </Pressable>
                  ) : null}
                </View>
                {isOpen ? c.sub_classes.map((sc) => (
                  <View key={sc.codigo} style={styles.subRow} testID={`subclasse-${sc.codigo}`}>
                    <Pressable style={{ flex: 1 }} onPress={() => canSave && openEditSubClasse(c, sc)}>
                      <Text style={styles.subRowTitle}>{sc.descricao}</Text>
                      <Text style={styles.rowSub}>{tipoLabel(sc.tipo)}{sc.ativa ? "" : " · Inativa"}</Text>
                    </Pressable>
                    {canDel ? (
                      <Pressable onPress={() => removeSubClasse(sc)} hitSlop={8} testID={`subclasse-del-${sc.codigo}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>
                )) : null}
                {isOpen && c.sub_classes.length === 0 ? <Text style={styles.emptySub}>Nenhuma subclasse.</Text> : null}
              </View>
            );
          })}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNewClasse} style={styles.fab} testID="plano-contas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>
                {formKind === "classe"
                  ? (editCod ? `Classe ${editCod}` : "Nova classe")
                  : (editCod ? `SubClasse ${editCod}` : "Nova subclasse")}
              </Text>

              {formKind === "subclasse" ? (
                <>
                  <Text style={styles.label}>Classe *</Text>
                  <SelectField
                    value={classePai}
                    onChange={(v) => setClassePai(v == null ? null : Number(v))}
                    options={classeOpts}
                    placeholder="Selecione…"
                    compactWeb
                    testID="subclasse-classe"
                    modalTitle="Classe"
                  />
                </>
              ) : null}

              <Text style={styles.label}>Descrição *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: Aluguel"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={50}
                autoCapitalize="characters"
                testID="plano-contas-descricao"
              />

              <Text style={styles.label}>Tipo *</Text>
              <SelectField value={tipo} onChange={(v) => setTipo(v == null ? null : String(v))} options={TIPO_OPTIONS} placeholder="Selecione…" compactWeb testID="plano-contas-tipo" modalTitle="Tipo" />

              {formKind === "subclasse" ? (
                <View style={styles.switchRow}>
                  <Text style={styles.label}>Ativa</Text>
                  <Switch value={ativa} onValueChange={setAtiva} testID="subclasse-ativa-switch" />
                </View>
              ) : null}

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="plano-contas-salvar">
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
  group: { gap: spacing.xs, alignSelf: "stretch", width: "100%" },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  subRow: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.md, marginLeft: spacing.xl,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  subRowTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  emptySub: { fontSize: 12, color: colors.muted, marginLeft: spacing.xl + spacing.md, fontStyle: "italic" },
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
    maxWidth: Platform.OS === "web" ? 480 : undefined,
    maxHeight: "85%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
