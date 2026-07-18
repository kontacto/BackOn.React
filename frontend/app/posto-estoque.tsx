// Posto de Combustível > Estoque Combustível — migração de
// `frmmanest.frm` ("Manutenção de Estoque...", pasta VB6 Posto). Chave
// natural composta (combustivel, data, turno) — upsert, mesmo padrão de
// Metas Combustível. Excluir usa a MESMA chave completa (o legado
// original excluía por combustivel+data só, apagando todos os turnos do
// dia por engano — corrigido aqui, ver estoque_combustivel_service.py).
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
type Combustivel = { codigo: number; descricao: string };
type EstoqueItem = {
  combustivel: number; combustivel_descricao: string; data: string; turno_estoque: number;
  venda: number; venda2: number; estoque: number;
};

function todayIso() { return new Date().toISOString().slice(0, 10); }
function fmt(v: number) { return v.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }); }
function parseNum(s: string): number { const n = parseFloat(s.replace(/\./g, "").replace(",", ".")); return isNaN(n) ? 0 : n; }

export default function PostoEstoqueScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Estoque Combustível está disponível apenas no web." testID="posto-estoque-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-estoque-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [combustiveis, setCombustiveis] = useState<Combustivel[]>([]);
  const [itens, setItens] = useState<EstoqueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [combustivel, setCombustivel] = useState<number | null>(null);
  const [data, setData] = useState(todayIso());
  const [turno, setTurno] = useState("");
  const [venda, setVenda] = useState("");
  const [venda2, setVenda2] = useState("");

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

  const loadItens = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/estoque-combustivel?${qs}`);
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
      loadItens(cc);
    })();
  }, [router, loadCombustiveis, loadItens]);

  const limpar = () => { setCombustivel(null); setTurno(""); setVenda(""); setVenda2(""); };

  const abrirEdicao = (it: EstoqueItem) => {
    setCombustivel(it.combustivel); setData(it.data); setTurno(String(it.turno_estoque));
    setVenda(fmt(it.venda)); setVenda2(it.venda2 ? fmt(it.venda2) : "");
  };

  const gravar = async () => {
    if (!conn) return;
    if (combustivel == null) { showToast("Selecione o combustível."); return; }
    if (!data) { showToast("Selecione a data."); return; }
    const tn = parseInt(turno, 10);
    if (!turno.trim() || isNaN(tn)) { showToast("Informe o turno."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/estoque-combustivel`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          combustivel, data, turno: tn, venda: parseNum(venda), venda2: venda2 ? parseNum(venda2) : 0,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Estoque gravado."); limpar(); loadItens(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (it: EstoqueItem) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/estoque-combustivel/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, combustivel: it.combustivel, data: it.data, turno: it.turno_estoque }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha ao excluir."));
      if (j?.success) loadItens(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const combustivelOptions: SelectOption[] = combustiveis.map((c) => ({ value: c.codigo, label: `${c.codigo} · ${c.descricao}` }));
  const canSave = can("POSTO_ESTOQUE.GRAVAR") || isMaster;
  const canDel = can("POSTO_ESTOQUE.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-estoque-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Estoque Combustível</Text>
        {canSave ? (
          <Pressable onPress={gravar} disabled={saving} style={styles.saveBtn} testID="posto-estoque-gravar">
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
            <Text style={styles.label}>Combustível *</Text>
            <SelectField value={combustivel} onChange={(v) => setCombustivel(v == null ? null : Number(v))} options={combustivelOptions} placeholder="Selecione…" compactWeb searchable testID="posto-estoque-combustivel" />
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Data *</Text>
                <WebDateField value={data} onChange={(v) => setData(v || todayIso())} type="date" testID="posto-estoque-data" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Turno *</Text>
                <TextInput value={turno} onChangeText={(v) => setTurno(v.replace(/[^0-9]/g, "").slice(0, 1))} placeholder="1" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-estoque-turno" />
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Preço Venda</Text>
                <TextInput value={venda} onChangeText={(v) => setVenda(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-estoque-venda" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Segundo Preço</Text>
                <TextInput value={venda2} onChangeText={(v) => setVenda2(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-estoque-venda2" />
              </View>
            </View>
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Registros de Estoque</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && itens.length === 0 ? <Text style={styles.empty}>Nenhum registro de estoque.</Text> : null}
            {itens.map((it) => (
              <View key={`${it.combustivel}-${it.data}-${it.turno_estoque}`} style={styles.row} testID={`posto-estoque-row-${it.combustivel}-${it.data}-${it.turno_estoque}`}>
                <Pressable style={{ flex: 1 }} onPress={() => canSave && abrirEdicao(it)}>
                  <Text style={styles.rowTitle}>{it.combustivel_descricao || `Combustível #${it.combustivel}`} · {it.data} · Turno {it.turno_estoque}</Text>
                  <Text style={styles.rowSub}>Venda: {fmt(it.venda)}{it.venda2 ? ` · 2º: ${fmt(it.venda2)}` : ""}</Text>
                </Pressable>
                {canDel ? (
                  <Pressable onPress={() => excluir(it)} hitSlop={8} testID={`posto-estoque-del-${it.combustivel}-${it.data}-${it.turno_estoque}`}>
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
  colNarrow: { width: 90 },
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
