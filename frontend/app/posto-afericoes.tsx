// Posto de Combustível > Aferições/Despesas — migração de
// `FrmBaiABc2.frm` ("Baixa de Abastecimentos...", pasta VB6 Posto).
//
// Achado importante (ver backend/services/afericao_abastecimento_service.py):
// nenhuma tela migrada até agora cria linhas em `abastecimento` — em
// produção elas vêm do polling do concentrador Wayne Fusion (Fase 2,
// fora de escopo). Esta tela funciona normalmente, só que a lista de
// "Abastecimentos Pendentes" fica vazia até essa automação existir.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Abastecimento = {
  num: number; ponto: number | null; posicao: number | null; combustivel_descricao: string;
  valor: number; volume: number; preco_un: number; data: string; hora: string; turno: number | null;
  valor_despesa: number; obs_afericao: string;
};

function fmt(v: number) { return v.toLocaleString("pt-BR", { minimumFractionDigits: 2 }); }
function todayIso() { return new Date().toISOString().slice(0, 10); }

export default function PostoAfericoesScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Aferições/Despesas está disponível apenas no web." testID="posto-afericoes-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-afericoes-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [pendentes, setPendentes] = useState<Abastecimento[]>([]);
  const [afericoes, setAfericoes] = useState<Abastecimento[]>([]);
  const [selecionados, setSelecionados] = useState<number[]>([]);
  const [lancarDespesa, setLancarDespesa] = useState(false);
  const [motivo, setMotivo] = useState("");
  const [dataIni, setDataIni] = useState(todayIso());
  const [dataFim, setDataFim] = useState(todayIso());
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 500); };

  const loadPendentes = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/abastecimentos/pendentes?${qs}`);
      const j = await r.json();
      setPendentes(j?.success ? j.items || [] : []);
      if (!j?.success && j?.message) showToast(j.message);
    } catch { setPendentes([]); } finally { setLoading(false); }
  }, []);

  const loadAfericoes = useCallback(async (c: Conn, ini: string, fim: string) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&data_ini=${ini}&data_fim=${fim}`;
      const r = await fetch(`${base}/api/posto/abastecimentos/afericoes?${qs}`);
      const j = await r.json();
      setAfericoes(j?.success ? j.items || [] : []);
    } catch { setAfericoes([]); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      loadPendentes(cc);
      loadAfericoes(cc, todayIso(), todayIso());
    })();
  }, [router, loadPendentes, loadAfericoes]);

  useEffect(() => {
    if (conn) loadAfericoes(conn, dataIni, dataFim);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dataIni, dataFim, conn]);

  const toggleSelecao = (num: number) => {
    setSelecionados((prev) => {
      if (prev.includes(num)) return prev.filter((n) => n !== num);
      if (prev.length >= 10) { showToast("Só é permitido selecionar até 10 abastecimentos por vez."); return prev; }
      return [...prev, num];
    });
  };

  const aferirSelecionados = async () => {
    if (!conn) return;
    if (selecionados.length === 0) { showToast("Selecione ao menos um abastecimento."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/abastecimentos/aferir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, nums: selecionados, lancar_despesa: lancarDespesa, motivo }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Aferido." : "Falha ao aferir."));
      if (j?.success) {
        setSelecionados([]); setMotivo(""); setLancarDespesa(false);
        loadPendentes(conn); loadAfericoes(conn, dataIni, dataFim);
      }
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const reverter = async (a: Abastecimento) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/abastecimentos/${a.num}/reverter`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Revertido." : "Falha ao reverter."));
      if (j?.success) { loadPendentes(conn); loadAfericoes(conn, dataIni, dataFim); }
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canAferir = can("POSTO_AFERICAO.GRAVAR") || isMaster;
  const canReverter = can("POSTO_AFERICAO.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-afericoes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Aferições/Despesas</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Abastecimentos Pendentes ({selecionados.length}/10 selecionados)</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && pendentes.length === 0 ? (
              <Text style={styles.empty}>Nenhum abastecimento pendente de baixa.</Text>
            ) : null}
            {pendentes.map((a) => {
              const sel = selecionados.includes(a.num);
              return (
                <Pressable key={a.num} onPress={() => toggleSelecao(a.num)} style={[styles.row, sel && styles.rowSelected]} testID={`posto-afericoes-pendente-${a.num}`}>
                  <Ionicons name={sel ? "checkbox" : "square-outline"} size={20} color={sel ? colors.brandPrimary : colors.muted} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowTitle}>#{a.num} · Bico {a.ponto}/{a.posicao} · {a.combustivel_descricao}</Text>
                    <Text style={styles.rowSub}>{a.data} {a.hora} · Volume: {fmt(a.volume)} · Valor: {fmt(a.valor)}</Text>
                  </View>
                </Pressable>
              );
            })}

            {canAferir && pendentes.length > 0 ? (
              <>
                <View style={styles.checkRow}>
                  <Pressable onPress={() => setLancarDespesa((v) => !v)} style={styles.checkTouch} testID="posto-afericoes-despesa-check">
                    <Ionicons name={lancarDespesa ? "checkbox" : "square-outline"} size={20} color={lancarDespesa ? colors.brandPrimary : colors.muted} />
                    <Text style={styles.checkLabel}>Lançar como Despesa</Text>
                  </Pressable>
                </View>
                <Text style={styles.label}>Observação</Text>
                <TextInput value={motivo} onChangeText={setMotivo} placeholder="Opcional" placeholderTextColor={colors.muted} style={styles.input} testID="posto-afericoes-motivo" />
                <Pressable onPress={aferirSelecionados} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-afericoes-aferir">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Aferir Selecionados</Text>}
                </Pressable>
              </>
            ) : null}
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Aferições Lançadas</Text>
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>De</Text>
                <WebDateField value={dataIni} onChange={(v) => setDataIni(v || todayIso())} type="date" testID="posto-afericoes-data-ini" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={dataFim} onChange={(v) => setDataFim(v || todayIso())} type="date" testID="posto-afericoes-data-fim" />
              </View>
            </View>
            {afericoes.length === 0 ? <Text style={styles.empty}>Nenhuma aferição neste período.</Text> : null}
            {afericoes.map((a) => (
              <View key={a.num} style={styles.row} testID={`posto-afericoes-lancada-${a.num}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>#{a.num} · Bico {a.ponto}/{a.posicao} · {a.combustivel_descricao}</Text>
                  <Text style={styles.rowSub}>
                    {a.data} {a.hora} · Volume: {fmt(a.volume)}{a.valor_despesa > 0 ? ` · Despesa: ${fmt(a.valor_despesa)}` : ""}
                    {a.obs_afericao ? ` · ${a.obs_afericao}` : ""}
                  </Text>
                </View>
                {canReverter ? (
                  <Pressable onPress={() => reverter(a)} hitSlop={8} testID={`posto-afericoes-reverter-${a.num}`}>
                    <Ionicons name="arrow-undo-outline" size={20} color={colors.error} />
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
  rowSelected: { borderColor: colors.brandPrimary, borderWidth: 2 },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 16 },
  checkRow: { marginTop: spacing.md },
  checkTouch: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  checkLabel: { fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
