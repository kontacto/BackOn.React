// Posto de Combustível > Tanque/Nota Fiscal — migração de
// `frmmantnf.frm` ("Tanque / Nota Fiscal", pasta VB6 Posto). Vínculo
// entre uma Nota Fiscal já cadastrada (Notas Fiscais) e o tanque que
// recebeu a quantidade. Chave natural composta (nota, tanque) — upsert.
//
// Simplificação: o legado permite localizar a Nota Fiscal por código OU
// por fornecedor+série+número — aqui só o campo Código é exposto (busca
// mais direta); o backend (`GET /posto/tanque-nf/find`) já aceita os
// dois caminhos, caso essa tela precise do segundo modo de busca depois.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
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
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type TanqueOpt = { tanque: number; combustivel_descricao: string };
type Nota = { codigo: number; fornecedor: number; num_nf: number; serie_nf: string };
type Item = { tanque: number; nota: number; qtd: number; combustivel_descricao: string };

export default function PostoTanqueNfScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Tanque/Nota Fiscal está disponível apenas no web." testID="posto-tanque-nf-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-tanque-nf-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [tanques, setTanques] = useState<TanqueOpt[]>([]);
  const [codigoNf, setCodigoNf] = useState("");
  const [nota, setNota] = useState<Nota | null>(null);
  const [itens, setItens] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [tanque, setTanque] = useState<number | null>(null);
  const [qtd, setQtd] = useState("");

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const ensureConn = useCallback(async () => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (!c) return null;
    const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
    setConn(cc);
    return cc;
  }, [conn, router]);

  useEffect(() => { ensureConn(); }, [ensureConn]);

  const loadItens = async (c: Conn, notaCod: number) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&nota=${notaCod}`;
      const r = await fetch(`${base}/api/posto/tanque-nf?${qs}`);
      const j = await r.json();
      setItens(j?.success ? j.items || [] : []);
      setTotal(j?.total || 0);
    } catch { setItens([]); setTotal(0); } finally { setLoading(false); }
  };

  const buscarNota = async () => {
    const c = await ensureConn();
    if (!c) return;
    const cod = parseInt(codigoNf, 10);
    if (!codigoNf.trim() || isNaN(cod)) { showToast("Informe o código da Nota Fiscal."); return; }
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&codigo=${cod}`;
      const [rn, rt] = await Promise.all([
        fetch(`${base}/api/posto/tanque-nf/find?${qs}`),
        fetch(`${base}/api/posto/tanques?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`),
      ]);
      const jn = await rn.json();
      const jt = await rt.json();
      setTanques(jt?.success ? jt.items || [] : []);
      if (!jn?.success) { showToast(jn?.message || "Nota Fiscal não encontrada."); setNota(null); setItens([]); setTotal(0); return; }
      setNota(jn.item);
      await loadItens(c, jn.item.codigo);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setLoading(false); }
  };

  const gravar = async () => {
    if (!conn || !nota) return;
    if (tanque == null) { showToast("Selecione o tanque."); return; }
    const q = parseInt(qtd, 10);
    if (!qtd.trim() || isNaN(q) || q <= 0) { showToast("Informe a quantidade."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanque-nf`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, nota: nota.codigo, tanque, qtd: q }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Gravado."); setTanque(null); setQtd(""); loadItens(conn, nota.codigo); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (it: Item) => {
    if (!conn || !nota) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/tanque-nf/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, nota: it.nota, tanque: it.tanque }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha ao excluir."));
      if (j?.success) loadItens(conn, nota.codigo);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const tanqueOptions: SelectOption[] = tanques.map((t) => ({ value: t.tanque, label: `Tanque ${t.tanque} (${t.combustivel_descricao})` }));
  const canSave = can("POSTO_TQ_NF.GRAVAR") || isMaster;
  const canDel = can("POSTO_TQ_NF.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-tanque-nf-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Tanque/Nota Fiscal</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Buscar Nota Fiscal</Text>
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Código da N.F. *</Text>
                <TextInput value={codigoNf} onChangeText={(v) => setCodigoNf(v.replace(/[^0-9]/g, ""))} placeholder="Código" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-tanque-nf-codigo" />
              </View>
              <Pressable onPress={buscarNota} style={styles.searchBtn} testID="posto-tanque-nf-buscar">
                <Ionicons name="search-outline" size={18} color="#fff" />
              </Pressable>
            </View>
            {nota ? (
              <Text style={styles.notaInfo}>NF {nota.num_nf} série {nota.serie_nf} · Fornecedor #{nota.fornecedor}</Text>
            ) : null}
          </View>

          {nota ? (
            <>
              <View style={[styles.card, isWeb && styles.cardWeb]}>
                <Text style={styles.sectionTitle}>Vincular Tanque</Text>
                <Text style={styles.label}>Tanque *</Text>
                <SelectField value={tanque} onChange={(v) => setTanque(v == null ? null : Number(v))} options={tanqueOptions} placeholder="Selecione…" compactWeb searchable testID="posto-tanque-nf-tanque" />
                <Text style={styles.label}>Quantidade *</Text>
                <TextInput value={qtd} onChangeText={(v) => setQtd(v.replace(/[^0-9]/g, ""))} placeholder="Litros" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-tanque-nf-qtd" />
                {canSave ? (
                  <Pressable onPress={gravar} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-tanque-nf-gravar">
                    {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                  </Pressable>
                ) : null}
              </View>

              <View style={[styles.card, isWeb && styles.cardWeb]}>
                <Text style={styles.sectionTitle}>Movimentações desta Nota (Total: {total})</Text>
                {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
                {!loading && itens.length === 0 ? <Text style={styles.empty}>Nenhum tanque vinculado a esta nota.</Text> : null}
                {itens.map((it) => (
                  <View key={it.tanque} style={styles.row} testID={`posto-tanque-nf-row-${it.tanque}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowTitle}>Tanque {it.tanque}</Text>
                      <Text style={styles.rowSub}>{it.combustivel_descricao} · Qtd: {it.qtd}</Text>
                    </View>
                    {canDel ? (
                      <Pressable onPress={() => excluir(it)} hitSlop={8} testID={`posto-tanque-nf-del-${it.tanque}`}>
                        <Ionicons name="trash-outline" size={20} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>
                ))}
              </View>
            </>
          ) : null}
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
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.md, gap: spacing.sm },
  cardWeb: {},
  sectionTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  colFlex: { flex: 1 },
  searchBtn: { width: 44, height: 44, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  notaInfo: { fontSize: 13, color: colors.onSurface, marginTop: spacing.sm, fontWeight: "600" },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginTop: spacing.sm,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 16 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
