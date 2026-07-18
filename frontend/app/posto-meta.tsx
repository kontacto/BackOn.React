// Posto de Combustível > Metas Combustível — migração de `frmcadmet.frm`
// ("Metas dos Combustíveis", pasta VB6 Posto). Chave natural composta
// (grupo, ano, mes) — sem PK própria, upsert por essa combinação, fiel
// ao legado (Gravar decide Incluir/Alterar sozinho, sem trava de campos
// ao editar). NÃO confundir com FrmCadMeta.frm (nome parecido, mesma
// pasta) — aquele é um rascunho abandonado que grava na tabela Bomba,
// nunca chega a tocar combustivel_meta (ver PENDENCIAS.md).
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
type Grupo = { codigo: number; descricao: string };
type Meta = { grupo: number; grupo_descricao: string; ano: number; mes: number; meta: number };

const MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function fmtMeta(v: number) {
  return v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function parseMeta(s: string): number {
  const n = parseFloat(s.replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export default function PostoMetaScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Metas Combustível está disponível apenas no web." testID="posto-meta-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-meta-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [grupos, setGrupos] = useState<Grupo[]>([]);
  const [metas, setMetas] = useState<Meta[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [grupo, setGrupo] = useState<number | null>(null);
  const [ano, setAno] = useState("");
  const [mes, setMes] = useState<number | null>(null);
  const [metaStr, setMetaStr] = useState("");
  const [editando, setEditando] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const [rg, rm] = await Promise.all([
        fetch(`${base}/api/posto/combustivel-meta/grupos?${qs}`),
        fetch(`${base}/api/posto/combustivel-meta?${qs}`),
      ]);
      const jg = await rg.json();
      const jm = await rm.json();
      setGrupos(jg?.success ? jg.items || [] : []);
      setMetas(jm?.success ? jm.items || [] : []);
      if (!jg?.success && jg?.message) showToast(jg.message);
      else if (!jm?.success && jm?.message) showToast(jm.message);
    } catch {
      setGrupos([]); setMetas([]);
    } finally {
      setLoading(false);
    }
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

  const limpar = () => {
    setGrupo(null); setAno(""); setMes(null); setMetaStr(""); setEditando(false);
  };

  const abrirEdicao = (m: Meta) => {
    setGrupo(m.grupo); setAno(String(m.ano)); setMes(m.mes); setMetaStr(fmtMeta(m.meta)); setEditando(true);
  };

  const gravar = async () => {
    if (!conn) return;
    if (grupo == null) { showToast("Selecione o grupo de combustível."); return; }
    const anoNum = parseInt(ano, 10);
    if (!ano.trim() || isNaN(anoNum) || anoNum < 2000 || anoNum > 2100) { showToast("Informe um ano válido."); return; }
    if (mes == null) { showToast("Selecione o mês."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/combustivel-meta`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          grupo, ano: anoNum, mes, meta: parseMeta(metaStr),
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Meta gravada."); limpar(); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (m: Meta) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/combustivel-meta/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, grupo: m.grupo, ano: m.ano, mes: m.mes }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha ao excluir."));
      if (j?.success) { if (editando && grupo === m.grupo && parseInt(ano, 10) === m.ano && mes === m.mes) limpar(); load(conn); }
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const grupoOptions: SelectOption[] = grupos.map((g) => ({ value: g.codigo, label: g.descricao }));
  const mesOptions: SelectOption[] = MESES.map((label, i) => ({ value: i + 1, label }));

  const canSave = can("POSTO_META.GRAVAR") || isMaster;
  const canDel = can("POSTO_META.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-meta-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Metas Combustível</Text>
        {canSave ? (
          <Pressable onPress={gravar} disabled={saving} style={styles.saveBtn} testID="posto-meta-gravar">
            {saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>{editando ? "Editar Meta" : "Nova Meta"}</Text>
            <Text style={styles.label}>Grupo de Combustível *</Text>
            <SelectField
              value={grupo}
              onChange={(v) => setGrupo(v == null ? null : Number(v))}
              options={grupoOptions}
              placeholder="Selecione o grupo…"
              compactWeb
              testID="posto-meta-grupo"
            />
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Ano *</Text>
                <TextInput
                  value={ano}
                  onChangeText={(v) => setAno(v.replace(/[^0-9]/g, "").slice(0, 4))}
                  placeholder="2026"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  keyboardType="number-pad"
                  maxLength={4}
                  testID="posto-meta-ano"
                />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Mês *</Text>
                <SelectField
                  value={mes}
                  onChange={(v) => setMes(v == null ? null : Number(v))}
                  options={mesOptions}
                  placeholder="Selecione…"
                  compactWeb
                  testID="posto-meta-mes"
                />
              </View>
            </View>
            <Text style={styles.label}>Meta</Text>
            <TextInput
              value={metaStr}
              onChangeText={(v) => setMetaStr(v.replace(/[^0-9.,]/g, ""))}
              placeholder="0,00"
              placeholderTextColor={colors.muted}
              style={styles.input}
              keyboardType="decimal-pad"
              testID="posto-meta-valor"
            />
            {editando ? (
              <Pressable onPress={limpar} style={styles.ghostBtn} testID="posto-meta-novo">
                <Text style={styles.ghostBtnText}>Cancelar edição / Nova meta</Text>
              </Pressable>
            ) : null}
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Metas Cadastradas</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && metas.length === 0 ? <Text style={styles.empty}>Nenhuma meta cadastrada.</Text> : null}
            {metas.map((m) => (
              <View key={`${m.grupo}-${m.ano}-${m.mes}`} style={styles.row} testID={`posto-meta-row-${m.grupo}-${m.ano}-${m.mes}`}>
                <Pressable style={{ flex: 1 }} onPress={() => canSave && abrirEdicao(m)}>
                  <Text style={styles.rowTitle}>{m.grupo_descricao} · {MESES[m.mes - 1]}/{m.ano}</Text>
                  <Text style={styles.rowSub}>Meta: {fmtMeta(m.meta)}</Text>
                </Pressable>
                {canDel ? (
                  <Pressable onPress={() => excluir(m)} hitSlop={8} testID={`posto-meta-del-${m.grupo}-${m.ano}-${m.mes}`}>
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
  colNarrow: { width: 110 },
  colFlex: { flex: 1 },
  ghostBtn: { alignSelf: "flex-start", marginTop: spacing.sm },
  ghostBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
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
