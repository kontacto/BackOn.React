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
type Modelo = { codigo: string; cod_marca: string; descricao: string };
type Marca = { codigo: string; descricao: string };

export default function ModelosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Modelos está disponível apenas no web."
        testID="modelos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [marcas, setMarcas] = useState<Marca[]>([]);
  const [filtroMarca, setFiltroMarca] = useState<string | number | null>(null);
  const [items, setItems] = useState<Modelo[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<string | null>(null);
  const [codMarca, setCodMarca] = useState<string | number | null>(null);
  const [descricao, setDescricao] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const loadModelos = useCallback(async (c: Conn, marca: string | number | null) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      let url = `${base}/api/tabelas/modelos?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      if (marca) url += `&cod_marca=${encodeURIComponent(String(marca))}`;
      const r = await fetch(url);
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
      try {
        const base = cc.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/tabelas/marcas?servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`);
        const j = await r.json();
        setMarcas(j?.success ? j.items || [] : []);
      } catch { /* */ }
      loadModelos(cc, null);
    })();
  }, [router, loadModelos]);

  const marcaLabel = (cod: string) => marcas.find((m) => m.codigo === cod)?.descricao || cod;

  const openNew = () => { setEditCod(null); setCodMarca(filtroMarca); setDescricao(""); setFormOpen(true); };
  const openEdit = (m: Modelo) => { setEditCod(m.codigo); setCodMarca(m.cod_marca); setDescricao(m.descricao); setFormOpen(true); };

  const save = async () => {
    if (!conn) return;
    if (!codMarca) { showToast("Selecione a marca."); return; }
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/modelos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCod, cod_marca: String(codMarca), descricao: descricao.trim() }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Modelo gravado."); setFormOpen(false); loadModelos(conn, filtroMarca); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (m: Modelo) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/modelos/${encodeURIComponent(m.codigo)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) loadModelos(conn, filtroMarca);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("MODELOS.GRAVAR") || isMaster;
  const canDel = can("MODELOS.EXCLUIR") || isMaster;
  const marcaOpts = marcas.map((m) => ({ value: m.codigo, label: m.descricao }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="modelos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Modelos</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={isWeb ? styles.webShell : undefined}>
        <View style={styles.filterBox}>
          <Text style={styles.label}>Filtrar por marca</Text>
          <SelectField value={filtroMarca} onChange={(v) => { setFiltroMarca(v); if (conn) loadModelos(conn, v); }} options={marcaOpts} placeholder="Todas as marcas" modalTitle="Marca" allowClear testID="modelos-filtro-marca" />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum modelo.</Text> : null}
          {items.map((m) => (
            <View key={m.codigo} style={styles.row} testID={`modelo-${m.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(m)}>
                <Text style={styles.rowTitle}>{m.codigo} · {m.descricao}</Text>
                <Text style={styles.rowSub}>Marca: {marcaLabel(m.cod_marca)}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(m)} hitSlop={8} testID={`modelo-del-${m.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="modelos-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editCod ? `Modelo ${editCod}` : "Novo modelo"}</Text>
            <Text style={styles.label}>Marca *</Text>
            <SelectField value={codMarca} onChange={setCodMarca} options={marcaOpts} placeholder="Selecione a marca" modalTitle="Marca" testID="modelo-marca" />
            <Text style={styles.label}>Descrição</Text>
            <TextInput value={descricao} onChangeText={setDescricao} placeholder="Ex.: UNO MILLE" placeholderTextColor={colors.muted} style={styles.input} autoCapitalize="characters" testID="modelo-descricao" />
            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="modelo-salvar">
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
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
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
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
    gap: spacing.sm,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
