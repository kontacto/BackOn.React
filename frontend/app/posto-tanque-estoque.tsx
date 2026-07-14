// Posto de Combustível > Tanque/Estoque — migração de `frmmantes.frm`
// ("Manutenção de Tanques / Estoque...", pasta VB6 Posto). Chave natural
// composta (tanque, data) — upsert, mesmo padrão de Estoque Combustível.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type TanqueOpt = { tanque: number; combustivel_descricao: string };
type Item = { tanque: number; data: string; estoque: number; capacidade: number; combustivel_descricao: string };

function todayIso() { return new Date().toISOString().slice(0, 10); }

export default function PostoTanqueEstoqueScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Tanque/Estoque está disponível apenas no web." testID="posto-tanque-estoque-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-tanque-estoque-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [tanques, setTanques] = useState<TanqueOpt[]>([]);
  const [itens, setItens] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [tanque, setTanque] = useState<number | null>(null);
  const [data, setData] = useState(todayIso());
  const [estoque, setEstoque] = useState("");

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const loadTanques = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/tanques?${qs}`);
      const j = await r.json();
      setTanques(j?.success ? j.items || [] : []);
    } catch { setTanques([]); }
  }, []);

  const loadItens = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/tanque-estoque?${qs}`);
      const j = await r.json();
      setItens(j?.success ? j.items || [] : []);
      if (!j?.success && j?.message) showToast(j.message);
    } catch { setItens([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      loadTanques(cc);
      loadItens(cc);
    })();
  }, [router, loadTanques, loadItens]);

  const limpar = () => { setTanque(null); setEstoque(""); };

  const abrirEdicao = (it: Item) => { setTanque(it.tanque); setData(it.data); setEstoque(String(it.estoque)); };

  const gravar = async () => {
    if (!conn) return;
    if (tanque == null) { showToast("Selecione o tanque."); return; }
    if (!data) { showToast("Selecione a data."); return; }
    const est = parseInt(estoque, 10);
    if (!estoque.trim() || isNaN(est)) { showToast("Informe o estoque."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanque-estoque`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tanque, data, estoque: est }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Gravado."); limpar(); loadItens(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (it: Item) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanque-estoque/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tanque: it.tanque, data: it.data }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha ao excluir."));
      if (j?.success) loadItens(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const tanqueOptions: SelectOption[] = tanques.map((t) => ({ value: t.tanque, label: `Tanque ${t.tanque} (${t.combustivel_descricao})` }));
  const canSave = can("POSTO_TQ_EST.GRAVAR") || isMaster;
  const canDel = can("POSTO_TQ_EST.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-tanque-estoque-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tanque/Estoque</Text>
        {canSave ? (
          <Pressable onPress={gravar} disabled={saving} style={styles.saveBtn} testID="posto-tanque-estoque-gravar">
            {saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Lançamento de Estoque</Text>
            <Text style={styles.label}>Tanque *</Text>
            <SelectField value={tanque} onChange={(v) => setTanque(v == null ? null : Number(v))} options={tanqueOptions} placeholder="Selecione…" compactWeb searchable testID="posto-tanque-estoque-tanque" />
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Data *</Text>
                <WebDateField value={data} onChange={(v) => setData(v || todayIso())} type="date" testID="posto-tanque-estoque-data" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Estoque (litros) *</Text>
                <TextInput value={estoque} onChangeText={(v) => setEstoque(v.replace(/[^0-9]/g, ""))} placeholder="0" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-tanque-estoque-valor" />
              </View>
            </View>
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Registros</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && itens.length === 0 ? <Text style={styles.empty}>Nenhum registro de estoque.</Text> : null}
            {itens.map((it) => (
              <View key={`${it.tanque}-${it.data}`} style={styles.row} testID={`posto-tanque-estoque-row-${it.tanque}-${it.data}`}>
                <Pressable style={{ flex: 1 }} onPress={() => canSave && abrirEdicao(it)}>
                  <Text style={styles.rowTitle}>Tanque {it.tanque} · {it.data}</Text>
                  <Text style={styles.rowSub}>{it.combustivel_descricao} · Estoque: {it.estoque} / {it.capacidade}</Text>
                </Pressable>
                {canDel ? (
                  <Pressable onPress={() => excluir(it)} hitSlop={8} testID={`posto-tanque-estoque-del-${it.tanque}-${it.data}`}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            ))}
          </View>
        </View>
      </ScrollView>

      {toast ? <View style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  saveBtn: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.2)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.md, gap: spacing.sm },
  cardWeb: {},
  sectionTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  colFlex: { flex: 1 },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginTop: spacing.sm,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 16 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
