import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type GrupoUsuario = {
  codigo: number;
  descricao: string;
  exige_tipo_cliente: boolean;
  exige_canal_aquisicao_cliente: boolean;
  visualiza_pedido_aberto: boolean;
  visualiza_pedido_fechado: boolean;
  visualiza_pedido_cancelado: boolean;
  visualiza_pedido_faturado: boolean;
};

// Cadastro/Tabelas Auxiliares > Grupo de Usuário (tabela `classes_usuarios`).
// Legado: FrmCadCla. Os 4 campos "Visualiza Pedidos..." são exibidos de forma
// positiva na tela, mas gravados invertidos no banco (NAO_VISUALIZA_PEDIDO_*) —
// confirmado no código-fonte legado: marcado -> grava 0 (libera), desmarcado ->
// grava 1 (bloqueia). O backend já faz essa inversão; aqui só lidamos com o
// campo positivo (visualiza_pedido_*).
export default function GrupoUsuarioScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Grupo de Usuário está disponível apenas no web."
        testID="grupo-usuario-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<GrupoUsuario[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [descricao, setDescricao] = useState("");
  const [exigeTipoCliente, setExigeTipoCliente] = useState(false);
  const [exigeCanalAquisicao, setExigeCanalAquisicao] = useState(false);
  const [visualizaAberto, setVisualizaAberto] = useState(false);
  const [visualizaFechado, setVisualizaFechado] = useState(false);
  const [visualizaCancelado, setVisualizaCancelado] = useState(false);
  const [visualizaFaturado, setVisualizaFaturado] = useState(false);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/grupos-usuario?${qs}`);
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

  const openNew = () => {
    setEditCod(null); setDescricao("");
    setExigeTipoCliente(false); setExigeCanalAquisicao(false);
    setVisualizaAberto(false); setVisualizaFechado(false); setVisualizaCancelado(false); setVisualizaFaturado(false);
    setFormOpen(true);
  };
  const openEdit = (g: GrupoUsuario) => {
    setEditCod(g.codigo); setDescricao(g.descricao);
    setExigeTipoCliente(g.exige_tipo_cliente); setExigeCanalAquisicao(g.exige_canal_aquisicao_cliente);
    setVisualizaAberto(g.visualiza_pedido_aberto); setVisualizaFechado(g.visualiza_pedido_fechado);
    setVisualizaCancelado(g.visualiza_pedido_cancelado); setVisualizaFaturado(g.visualiza_pedido_faturado);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição do grupo."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/grupos-usuario`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCod, descricao: descricao.trim(),
          exige_tipo_cliente: exigeTipoCliente,
          exige_canal_aquisicao_cliente: exigeCanalAquisicao,
          visualiza_pedido_aberto: visualizaAberto,
          visualiza_pedido_fechado: visualizaFechado,
          visualiza_pedido_cancelado: visualizaCancelado,
          visualiza_pedido_faturado: visualizaFaturado,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Grupo gravado."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (g: GrupoUsuario) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/grupos-usuario/${g.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("GRUPO_USUARIO.GRAVAR") || isMaster;
  const canDel = can("GRUPO_USUARIO.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="grupo-usuario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Grupo de Usuário</Text>
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
            testID="grupo-usuario-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum grupo cadastrado.</Text> : null}
          {items.map((g) => (
            <View key={g.codigo} style={styles.row} testID={`grupo-usuario-${g.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(g)}>
                <Text style={styles.rowTitle}>{g.codigo} · {g.descricao}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(g)} hitSlop={8} testID={`grupo-usuario-del-${g.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="grupo-usuario-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod ? `Grupo ${editCod}` : "Novo grupo"}</Text>

              <Text style={styles.label}>Descrição do Grupo *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: VENDEDOR"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={15}
                autoCapitalize="characters"
                testID="grupo-usuario-descricao"
              />

              <View style={styles.switchRow}>
                <Text style={styles.label}>Exige Tipo Do Cliente no cadastro</Text>
                <Switch value={exigeTipoCliente} onValueChange={setExigeTipoCliente} testID="grupo-usuario-exige-tipo-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Exige Canal de Aquisição do Cliente no cadastro</Text>
                <Switch value={exigeCanalAquisicao} onValueChange={setExigeCanalAquisicao} testID="grupo-usuario-exige-canal-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Visualiza Pedidos Abertos</Text>
                <Switch value={visualizaAberto} onValueChange={setVisualizaAberto} testID="grupo-usuario-visualiza-aberto-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Visualiza Pedidos Fechados</Text>
                <Switch value={visualizaFechado} onValueChange={setVisualizaFechado} testID="grupo-usuario-visualiza-fechado-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Visualiza Pedidos Faturados</Text>
                <Switch value={visualizaFaturado} onValueChange={setVisualizaFaturado} testID="grupo-usuario-visualiza-faturado-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Visualiza Pedidos Cancelados</Text>
                <Switch value={visualizaCancelado} onValueChange={setVisualizaCancelado} testID="grupo-usuario-visualiza-cancelado-switch" />
              </View>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="grupo-usuario-salvar">
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
  webShell: { width: "100%", maxWidth: 560, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
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
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4, flex: 1, marginRight: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
