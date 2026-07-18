// Posto de Combustível > Combustíveis — migração de `FRMMANCOM.FRM`
// ("Cadastro de Combustível", pasta VB6 Posto). Ver
// backend/services/combustivel_service.py para a lista completa de
// campos deliberadamente fora de escopo (Estoque oculto, Custo dead code
// no legado, Grupo nunca lido/gravado por essa tela, cascata pra
// pecas/estoque e push de preço pro hardware Wayne Fusion).
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
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Combustivel = { codigo: number; descricao: string; venda: number; venda2: number };

function fmt(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 3 });
}
function parseNum(s: string): number {
  const n = parseFloat(s.replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export default function PostoCombustiveisScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Combustíveis está disponível apenas no web." testID="posto-combustiveis-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-combustiveis-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Combustivel[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [venda, setVenda] = useState("");
  const [venda2, setVenda2] = useState("");
  const [codigoAutomacao, setCodigoAutomacao] = useState("");
  const [indImport, setIndImport] = useState("");
  const [ufOrig, setUfOrig] = useState("");
  const [pOrig, setPOrig] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/combustiveis?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
      if (!j?.success && j?.message) showToast(j.message);
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
      load(cc);
    })();
  }, [router, load]);

  const openNew = () => {
    setEditCod(null); setCodigo(""); setDescricao(""); setVenda(""); setVenda2("");
    setCodigoAutomacao(""); setIndImport(""); setUfOrig(""); setPOrig("");
    setFormOpen(true);
  };

  const openEdit = async (c: Combustivel) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/posto/combustiveis/${c.codigo}?${qs}`);
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao carregar."); return; }
      const it = j.item;
      setEditCod(it.codigo);
      setCodigo(String(it.codigo));
      setDescricao(it.descricao);
      setVenda(fmt(it.venda));
      setVenda2(it.venda2 ? fmt(it.venda2) : "");
      setCodigoAutomacao(it.codigo_automacao != null ? String(it.codigo_automacao) : "");
      setIndImport(it.indImport || "");
      setUfOrig(it.cUFOrig || "");
      setPOrig(it.pOrig ? fmt(it.pOrig) : "");
      setFormOpen(true);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const save = async () => {
    if (!conn) return;
    const cod = parseInt(codigo, 10);
    if (!codigo.trim() || isNaN(cod) || cod < 0 || cod > 255) { showToast("Código deve estar entre 0 e 255."); return; }
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    if (!venda.trim()) { showToast("Informe o preço de venda."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/combustiveis`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: cod,
          dados: {
            descricao: descricao.trim(), venda: parseNum(venda), venda2: venda2 ? parseNum(venda2) : 0,
            codigo_automacao: codigoAutomacao.trim() ? parseInt(codigoAutomacao, 10) : null,
            indImport: indImport.trim() || null, cUFOrig: ufOrig.trim() || null,
            pOrig: pOrig ? parseNum(pOrig) : 0,
          },
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Combustível gravado."); setFormOpen(false); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (c: Combustivel) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/combustiveis/${c.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("POSTO_COMBUST.GRAVAR") || isMaster;
  const canDel = can("POSTO_COMBUST.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-combustiveis-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Combustíveis</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum combustível cadastrado.</Text> : null}
          {items.map((c) => (
            <View key={c.codigo} style={styles.row} testID={`posto-combustiveis-${c.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(c)}>
                <Text style={styles.rowTitle}>{c.codigo} · {c.descricao}</Text>
                <Text style={styles.rowSub}>Venda: {fmt(c.venda)}{c.venda2 ? ` · 2º Preço: ${fmt(c.venda2)}` : ""}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(c)} hitSlop={8} testID={`posto-combustiveis-del-${c.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="posto-combustiveis-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <Text style={styles.modalTitle}>{editCod != null ? `Combustível ${editCod}` : "Novo Combustível"}</Text>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código *</Text>
                  <TextInput
                    value={codigo}
                    onChangeText={(v) => setCodigo(v.replace(/[^0-9]/g, "").slice(0, 3))}
                    placeholder="0-255"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, editCod != null && styles.inputDisabled]}
                    editable={editCod == null}
                    keyboardType="number-pad"
                    testID="posto-combustiveis-codigo"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Descrição *</Text>
                  <TextInput
                    value={descricao}
                    onChangeText={setDescricao}
                    placeholder="Ex.: Gasolina Comum"
                    placeholderTextColor={colors.muted}
                    style={styles.input}
                    maxLength={40}
                    testID="posto-combustiveis-descricao"
                  />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Preço Venda *</Text>
                  <TextInput value={venda} onChangeText={(v) => setVenda(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-combustiveis-venda" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Segundo Preço</Text>
                  <TextInput value={venda2} onChangeText={(v) => setVenda2(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-combustiveis-venda2" />
                </View>
              </View>

              <Text style={styles.label}>Código Automação</Text>
              <TextInput value={codigoAutomacao} onChangeText={(v) => setCodigoAutomacao(v.replace(/[^0-9]/g, ""))} placeholder="Opcional" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-combustiveis-cod-automacao" />

              <Text style={styles.sectionTitle}>Tributação Monofásica NFe/NFCe</Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Indicador Importação</Text>
                  <TextInput value={indImport} onChangeText={(v) => setIndImport(v.replace(/[^01]/g, "").slice(0, 1))} placeholder="0/1" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-combustiveis-ind-import" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>UF Origem</Text>
                  <TextInput value={ufOrig} onChangeText={(v) => setUfOrig(v.toUpperCase().replace(/[^A-Z]/g, "").slice(0, 2))} placeholder="RJ" placeholderTextColor={colors.muted} style={styles.input} autoCapitalize="characters" testID="posto-combustiveis-uf-orig" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>% Originário</Text>
                  <TextInput value={pOrig} onChangeText={(v) => setPOrig(v.replace(/[^0-9.,]/g, ""))} placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-combustiveis-p-orig" />
                </View>
              </View>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-combustiveis-salvar">
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
    maxHeight: "85%",
    gap: spacing.sm,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginTop: spacing.md },
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
