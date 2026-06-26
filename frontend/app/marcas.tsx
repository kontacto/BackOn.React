import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import { usePermissions } from "@/src/permissions";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type Conn = { servidor: string; banco: string; api: string };
type Marca = { codigo: string; descricao: string; marca_produto: boolean };

const FIPE_TIPOS: SelectOption[] = [
  { value: "carros", label: "Carros" },
  { value: "motos", label: "Motos" },
  { value: "caminhoes", label: "Caminhões" },
];

export default function MarcasScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const [conn, setConn] = useState<Conn | null>(null);
  const [userFuncao, setUserFuncao] = useState<number | null>(null);
  const [items, setItems] = useState<Marca[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  // form modal
  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [marcaProduto, setMarcaProduto] = useState(false);
  const [saving, setSaving] = useState(false);

  // FIPE modal
  const [fipeOpen, setFipeOpen] = useState(false);
  const [fipeTipo, setFipeTipo] = useState<string | number | null>("carros");
  const [fipeMarcas, setFipeMarcas] = useState<{ id: string; nome: string }[]>([]);
  const [fipeMarca, setFipeMarca] = useState<string | number | null>(null);
  const [fipeLoading, setFipeLoading] = useState(false);
  const [importing, setImporting] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/marcas?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const fnc = (s as { funcionario?: { funcao?: number | string } })?.funcionario?.funcao;
      setUserFuncao(fnc != null ? parseInt(String(fnc), 10) : null);
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc); load(cc);
    })();
  }, [router, load]);

  const openNew = () => { setEditCod(null); setDescricao(""); setMarcaProduto(false); setFormOpen(true); };
  const openEdit = (m: Marca) => { setEditCod(m.codigo); setDescricao(m.descricao); setMarcaProduto(m.marca_produto); setFormOpen(true); };

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/marcas`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, codigo: editCod, descricao: descricao.trim(), marca_produto: marcaProduto }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Marca gravada."); setFormOpen(false); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (m: Marca) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/marcas/${encodeURIComponent(m.codigo)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // FIPE
  const openFipe = async () => {
    setFipeOpen(true); setFipeMarca(null); setFipeMarcas([]);
    await loadFipeMarcas("carros");
  };
  const loadFipeMarcas = async (tipo: string) => {
    if (!conn) return;
    setFipeLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/fipe/marcas?tipo=${tipo}`);
      const j = await r.json();
      setFipeMarcas(j?.success ? j.items || [] : []);
    } catch { setFipeMarcas([]); } finally { setFipeLoading(false); }
  };
  const importFipe = async () => {
    if (!conn || !fipeMarca) { showToast("Selecione a marca FIPE."); return; }
    const sel = fipeMarcas.find((m) => m.id === String(fipeMarca));
    setImporting(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/marcas/importar-fipe`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, tipo: String(fipeTipo), fipe_marca_id: String(fipeMarca), descricao: sel?.nome || "" }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Importado." : "Falha."));
      if (j?.success) { setFipeOpen(false); load(conn); }
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setImporting(false); }
  };

  const canSave = can("MARCAS.GRAVAR") || isMaster;
  const canDel = can("MARCAS.EXCLUIR") || isMaster;
  // Importar da FIPE: KONTACTO (master) ou funcionários função 1/2.
  const canFipe = isMaster || userFuncao === 1 || userFuncao === 2;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="marcas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Marcas</Text>
        {canFipe ? (
          <Pressable onPress={openFipe} hitSlop={12} style={styles.back} testID="marcas-fipe-btn">
            <Ionicons name="cloud-download-outline" size={22} color={colors.onBrandPrimary} />
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
        {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma marca cadastrada.</Text> : null}
        {items.map((m) => (
          <View key={m.codigo} style={styles.row} testID={`marca-${m.codigo}`}>
            <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(m)}>
              <Text style={styles.rowTitle}>{m.codigo} · {m.descricao}</Text>
              <Text style={styles.rowSub}>{m.marca_produto ? "Produto" : "Veículo (O.S.)"}</Text>
            </Pressable>
            {canDel ? (
              <Pressable onPress={() => remove(m)} hitSlop={8} testID={`marca-del-${m.codigo}`}>
                <Ionicons name="trash-outline" size={20} color={colors.error} />
              </Pressable>
            ) : null}
          </View>
        ))}
      </ScrollView>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="marcas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      {/* Form */}
      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editCod ? `Marca ${editCod}` : "Nova marca"}</Text>
            <Text style={styles.label}>Descrição</Text>
            <TextInput value={descricao} onChangeText={setDescricao} placeholder="Ex.: FIAT" placeholderTextColor={colors.muted} style={styles.input} autoCapitalize="characters" testID="marca-descricao" />
            <View style={styles.switchRow}>
              <Text style={styles.label}>Marca referente a produtos</Text>
              <Switch value={marcaProduto} onValueChange={setMarcaProduto} testID="marca-produto-switch" />
            </View>
            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="marca-salvar">
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      {/* FIPE */}
      <Modal visible={fipeOpen} transparent animationType="slide" onRequestClose={() => setFipeOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFipeOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Importar da FIPE</Text>
            <Text style={styles.label}>Tipo</Text>
            <SelectField value={fipeTipo} onChange={(v) => { setFipeTipo(v); setFipeMarca(null); loadFipeMarcas(String(v)); }} options={FIPE_TIPOS} placeholder="Tipo" searchable={false} testID="fipe-tipo" />
            <Text style={styles.label}>Marca (FIPE)</Text>
            {fipeLoading ? <ActivityIndicator color={colors.brandPrimary} /> : (
              <SelectField value={fipeMarca} onChange={setFipeMarca} options={fipeMarcas.map((m) => ({ value: m.id, label: m.nome }))} placeholder="Selecione a marca" modalTitle="Marca FIPE" testID="fipe-marca" />
            )}
            <Text style={styles.hint}>Importa a marca (como veículo) e todos os modelos dela.</Text>
            <Pressable onPress={importFipe} disabled={importing} style={[styles.primaryBtn, importing && { opacity: 0.6 }]} testID="fipe-importar">
              {importing ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Importar modelos</Text>}
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
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
