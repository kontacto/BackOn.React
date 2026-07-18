// Posto de Combustível > Custo Combustível — migração de `frmmancus.frm`
// ("Custo Combustível", pasta VB6 Posto). Fiel ao legado: **só
// leitura + alteração**, sem Incluir/Excluir (o `.frm` original só tem
// botão "Altera" + navegação Anterior/Próximo/Primeiro/Último — a
// criação de linhas em Custo_Combustivel é feita por outro
// processo/tela, ver custo_combustivel_service.py).
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
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Combustivel = { codigo: number; descricao: string };
type CustoItem = { cod_cus: number; combustivel: number; data: string; seq: number; entrada: number; saida: number; custo: number };

function fmt(v: number) { return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 3 }); }
function parseNum(s: string): number { const n = parseFloat(s.replace(/\./g, "").replace(",", ".")); return isNaN(n) ? 0 : n; }

export default function PostoCustoScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Custo Combustível está disponível apenas no web." testID="posto-custo-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-custo-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [combustiveis, setCombustiveis] = useState<Combustivel[]>([]);
  const [combustivel, setCombustivel] = useState<number | null>(null);
  const [itens, setItens] = useState<CustoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<CustoItem | null>(null);
  const [data, setData] = useState("");
  const [entrada, setEntrada] = useState("");
  const [saida, setSaida] = useState("");
  const [custo, setCusto] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const loadCombustiveis = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/combustiveis?${qs}`);
      const j = await r.json();
      setCombustiveis(j?.success ? j.items || [] : []);
    } catch { setCombustiveis([]); }
  }, []);

  const loadItens = useCallback(async (c: Conn, comb: number) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&combustivel=${comb}`;
      const r = await fetch(`${base}/api/posto/custo-combustivel?${qs}`);
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
      loadCombustiveis(cc);
    })();
  }, [router, loadCombustiveis]);

  useEffect(() => {
    if (conn && combustivel != null) loadItens(conn, combustivel);
    else setItens([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [combustivel, conn]);

  const openEdit = (it: CustoItem) => {
    setEditItem(it); setData(it.data); setEntrada(fmt(it.entrada)); setSaida(fmt(it.saida)); setCusto(fmt(it.custo));
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn || !editItem) return;
    if (!data) { showToast("Informe a data."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/custo-combustivel/${editItem.cod_cus}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          data, entrada: parseNum(entrada), saida: parseNum(saida), custo: parseNum(custo),
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Custo atualizado."); setFormOpen(false); if (combustivel != null) loadItens(conn, combustivel); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const combustivelOptions: SelectOption[] = combustiveis.map((c) => ({ value: c.codigo, label: `${c.codigo} · ${c.descricao}` }));
  const canSave = can("POSTO_CUSTO.GRAVAR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-custo-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Custo Combustível</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <Text style={styles.label}>Combustível</Text>
          <SelectField value={combustivel} onChange={(v) => setCombustivel(v == null ? null : Number(v))} options={combustivelOptions} placeholder="Selecione um combustível…" compactWeb searchable testID="posto-custo-combustivel" />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && combustivel != null && itens.length === 0 ? <Text style={styles.empty}>Nenhum registro de custo para este combustível.</Text> : null}
          {!loading && combustivel == null ? <Text style={styles.empty}>Selecione um combustível para ver o histórico de custo.</Text> : null}
          {itens.map((it) => (
            <Pressable key={it.cod_cus} style={styles.row} onPress={() => canSave && openEdit(it)} testID={`posto-custo-${it.cod_cus}`}>
              <Text style={styles.rowTitle}>{it.data} · Seq {it.seq}</Text>
              <Text style={styles.rowSub}>Entrada: {fmt(it.entrada)} · Saída: {fmt(it.saida)} · Custo: {fmt(it.custo)}</Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Custo #{editItem?.cod_cus}</Text>
            <Text style={styles.label}>Data *</Text>
            <WebDateField value={data} onChange={(v) => setData(v || "")} type="date" testID="posto-custo-data" />
            <Text style={styles.label}>Entrada</Text>
            <TextInput value={entrada} onChangeText={(v) => setEntrada(v.replace(/[^0-9.,]/g, ""))} placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-custo-entrada" />
            <Text style={styles.label}>Saída</Text>
            <TextInput value={saida} onChangeText={(v) => setSaida(v.replace(/[^0-9.,]/g, ""))} placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-custo-saida" />
            <Text style={styles.label}>Custo</Text>
            <TextInput value={custo} onChangeText={(v) => setCusto(v.replace(/[^0-9.,]/g, ""))} placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-custo-custo" />

            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-custo-salvar">
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
  row: {
    alignSelf: "stretch", width: "100%", gap: 4,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
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
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
