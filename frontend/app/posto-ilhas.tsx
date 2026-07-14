// Posto de Combustível > Ilhas — migração de `frmmanilha.frm` ("Manutenção
// de Ilhas", pasta VB6 Posto). Chave natural composta (data, ilha, turno) —
// fiel ao legado: só Incluir/Excluir, sem Alterar (pra trocar o funcionário
// de uma combinação já existente, exclui e inclui de novo).
//
// Seletor "Ilha" lista o número de agrupamento físico (`bomba.ilha`),
// mesma query do `.frm` original — ver nota em ilha_service.py sobre as
// FKs desabilitadas nesta área do schema (não são regras vigentes).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
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
type Opcoes = {
  ilhas: number[];
  turnos: number[];
  funcionarios: { codigo: number; nome: string }[];
};
type ItemIlha = { ilha: number; turno: number; funcionario: number | null; funcionario_nome: string };

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function PostoIlhasScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Ilhas está disponível apenas no web." testID="posto-ilhas-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-ilhas-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [opcoes, setOpcoes] = useState<Opcoes>({ ilhas: [], turnos: [], funcionarios: [] });
  const [data, setData] = useState(todayIso());
  const [itens, setItens] = useState<ItemIlha[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [ilha, setIlha] = useState<number | null>(null);
  const [turno, setTurno] = useState<number | null>(null);
  const [funcionario, setFuncionario] = useState<number | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const loadOpcoes = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/ilhas/opcoes?${qs}`);
      const j = await r.json();
      if (j?.success) setOpcoes({ ilhas: j.ilhas || [], turnos: j.turnos || [], funcionarios: j.funcionarios || [] });
      else if (j?.message) showToast(j.message);
    } catch { /* ignore */ }
  }, []);

  const loadItens = useCallback(async (c: Conn, d: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&data=${encodeURIComponent(d)}`;
      const r = await fetch(`${base}/api/posto/ilhas?${qs}`);
      const j = await r.json();
      setItens(j?.success ? j.items || [] : []);
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
      loadOpcoes(cc);
      loadItens(cc, todayIso());
    })();
  }, [router, loadOpcoes, loadItens]);

  useEffect(() => {
    if (conn) loadItens(conn, data);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, conn]);

  const limpar = () => { setIlha(null); setTurno(null); setFuncionario(null); };

  const incluir = async () => {
    if (!conn) return;
    if (!data) { showToast("Selecione a data."); return; }
    if (ilha == null) { showToast("Selecione a ilha."); return; }
    if (turno == null) { showToast("Selecione o turno."); return; }
    if (funcionario == null) { showToast("Selecione o funcionário."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/ilhas`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, data, ilha, turno, funcionario }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Ilha cadastrada."); limpar(); loadItens(conn, data); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (item: ItemIlha) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/ilhas/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, data, ilha: item.ilha, turno: item.turno }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha ao excluir."));
      if (j?.success) loadItens(conn, data);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const ilhaOptions: SelectOption[] = opcoes.ilhas.map((n) => ({ value: n, label: `Ilha ${n}` }));
  const turnoOptions: SelectOption[] = opcoes.turnos.map((t) => ({ value: t, label: `Turno ${t}` }));
  const funcOptions: SelectOption[] = opcoes.funcionarios.map((f) => ({ value: f.codigo, label: f.nome }));

  const canSave = can("POSTO_ILHA.GRAVAR") || isMaster;
  const canDel = can("POSTO_ILHA.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-ilhas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Ilhas</Text>
        {canSave ? (
          <Pressable onPress={incluir} disabled={saving} style={styles.saveBtn} testID="posto-ilhas-gravar">
            {saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveLabel}>Incluir</Text>}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Nova Atribuição</Text>
            <Text style={styles.label}>Data *</Text>
            <WebDateField value={data} onChange={(v) => setData(v || todayIso())} type="date" testID="posto-ilhas-data" />
            <Text style={styles.label}>Ilha (Bomba) *</Text>
            <SelectField value={ilha} onChange={(v) => setIlha(v == null ? null : Number(v))} options={ilhaOptions} placeholder="Selecione a ilha…" compactWeb testID="posto-ilhas-ilha" />
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Turno *</Text>
                <SelectField value={turno} onChange={(v) => setTurno(v == null ? null : Number(v))} options={turnoOptions} placeholder="…" compactWeb testID="posto-ilhas-turno" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Funcionário *</Text>
                <SelectField value={funcionario} onChange={(v) => setFuncionario(v == null ? null : Number(v))} options={funcOptions} placeholder="Selecione…" compactWeb searchable testID="posto-ilhas-funcionario" />
              </View>
            </View>
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Ilhas Atribuídas em {data}</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && itens.length === 0 ? <Text style={styles.empty}>Nenhuma atribuição nesta data.</Text> : null}
            {itens.map((it) => (
              <View key={`${it.ilha}-${it.turno}`} style={styles.row} testID={`posto-ilhas-row-${it.ilha}-${it.turno}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle}>Ilha {it.ilha} · Turno {it.turno}</Text>
                  <Text style={styles.rowSub}>{it.funcionario_nome || `Funcionário #${it.funcionario}`}</Text>
                </View>
                {canDel ? (
                  <Pressable onPress={() => excluir(it)} hitSlop={8} testID={`posto-ilhas-del-${it.ilha}-${it.turno}`}>
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
  rowFields: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start" },
  colNarrow: { width: 110 },
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
