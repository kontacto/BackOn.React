// Posto de Combustível > Tanques — migração de `frmmantan.frm`
// ("Manutenção de Tanques...", pasta VB6 Posto). Upsert por `tanque`
// (PK própria) — igual ao `Command3_Click` original (Inclui se não
// existe, Altera se já existe).
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type TanqueItem = { tanque: number; capacidade: number; combustivel: number | null; combustivel_descricao: string };
type Combustivel = { codigo: number; descricao: string };

export default function PostoTanquesScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Tanques está disponível apenas no web." testID="posto-tanques-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-tanques-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<TanqueItem[]>([]);
  const [combustiveis, setCombustiveis] = useState<Combustivel[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editTanque, setEditTanque] = useState<number | null>(null);
  const [tanque, setTanque] = useState("");
  const [capacidade, setCapacidade] = useState("");
  const [combustivel, setCombustivel] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const [rt, rc] = await Promise.all([
        fetch(`${base}/api/posto/tanques?${qs}`),
        fetch(`${base}/api/posto/combustiveis?${qs}`),
      ]);
      const jt = await rt.json();
      const jc = await rc.json();
      setItems(jt?.success ? jt.items || [] : []);
      setCombustiveis(jc?.success ? jc.items || [] : []);
      if (!jt?.success && jt?.message) showToast(jt.message);
    } catch { setItems([]); setCombustiveis([]); } finally { setLoading(false); }
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
    })();
  }, [router, load]);

  const openNew = () => { setEditTanque(null); setTanque(""); setCapacidade(""); setCombustivel(null); setFormOpen(true); };
  const openEdit = (it: TanqueItem) => {
    setEditTanque(it.tanque); setTanque(String(it.tanque)); setCapacidade(String(it.capacidade)); setCombustivel(it.combustivel);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    const tq = parseInt(tanque, 10);
    if (!tanque.trim() || isNaN(tq)) { showToast("Informe o código do tanque."); return; }
    const cap = parseInt(capacidade, 10);
    if (!capacidade.trim() || isNaN(cap)) { showToast("Informe a capacidade."); return; }
    if (combustivel == null) { showToast("Selecione o combustível."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanques`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tanque: tq, capacidade: cap, combustivel }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Tanque gravado."); setFormOpen(false); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (it: TanqueItem) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanques/${it.tanque}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const combustivelOptions: SelectOption[] = combustiveis.map((c) => ({ value: c.codigo, label: `${c.codigo} · ${c.descricao}` }));
  const canSave = can("POSTO_TANQUE.GRAVAR") || isMaster;
  const canDel = can("POSTO_TANQUE.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-tanques-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tanques</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum tanque cadastrado.</Text> : null}
          {items.map((it) => (
            <View key={it.tanque} style={styles.row} testID={`posto-tanques-${it.tanque}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <Text style={styles.rowTitle}>Tanque {it.tanque}</Text>
                <Text style={styles.rowSub}>{it.combustivel_descricao || `Combustível #${it.combustivel}`} · Capacidade: {it.capacidade}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`posto-tanques-del-${it.tanque}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="posto-tanques-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editTanque != null ? `Tanque ${editTanque}` : "Novo Tanque"}</Text>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Código *</Text>
                <TextInput
                  value={tanque}
                  onChangeText={(v) => setTanque(v.replace(/[^0-9]/g, "").slice(0, 3))}
                  placeholder="0-255"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, editTanque != null && styles.inputDisabled]}
                  editable={editTanque == null}
                  keyboardType="number-pad"
                  testID="posto-tanques-codigo"
                />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Capacidade *</Text>
                <TextInput value={capacidade} onChangeText={(v) => setCapacidade(v.replace(/[^0-9]/g, ""))} placeholder="Litros" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-tanques-capacidade" />
              </View>
            </View>
            <Text style={styles.label}>Combustível *</Text>
            <SelectField value={combustivel} onChange={(v) => setCombustivel(v == null ? null : Number(v))} options={combustivelOptions} placeholder="Selecione…" compactWeb searchable testID="posto-tanques-combustivel" />

            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-tanques-salvar">
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
            </Pressable>
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
  webShell: { width: "100%", maxWidth: 560, alignSelf: "center", flex: 1 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
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
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
    gap: spacing.sm,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  colNarrow: { width: 90 },
  colFlex: { flex: 1 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
