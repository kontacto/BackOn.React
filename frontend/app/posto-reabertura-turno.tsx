// Posto de Combustível > Reabertura de Turno — migração de
// `FrmReaTurno.frm` (pasta VB6 Posto). Desfaz o fechamento mais recente.
// Ver backend/services/reabertura_turno_service.py pro porquê da
// reatribuição de turno de abastecimento/mov_bomba do legado não ser
// replicada aqui (simplificação real, não lacuna).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Preview = {
  data_movimento: string; turno_atual: number;
  turno_a_reabrir: number; data_a_reabrir: string; cruza_dia: boolean; existe_fechamento: boolean;
};

export default function PostoReaberturaTurnoScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Reabertura de Turno está disponível apenas no web." testID="posto-reabertura-turno-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-reabertura-turno-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 3000); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/reabertura-turno/preview?${qs}`);
      const j = await r.json();
      if (j?.success) setPreview(j);
      else { setPreview(null); if (j?.message) showToast(j.message); }
    } catch { setPreview(null); } finally { setLoading(false); }
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

  const reabrir = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/reabertura-turno/reabrir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Turno reaberto." : "Falha ao reabrir."));
      setConfirmando(false);
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const canReabrir = can("POSTO_REA_TURNO.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-reabertura-turno-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Reabertura de Turno</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
            {!loading && preview ? (
              <>
                <Text style={styles.label}>Situação Atual</Text>
                <Text style={styles.value}>Turno {preview.turno_atual} · {preview.data_movimento}</Text>

                {preview.existe_fechamento ? (
                  <>
                    <Text style={styles.label}>Será reaberto</Text>
                    <Text style={styles.value}>Turno {preview.turno_a_reabrir} de {preview.data_a_reabrir}</Text>
                    {preview.cruza_dia ? (
                      <View style={styles.warnBox}>
                        <Ionicons name="warning-outline" size={18} color={colors.error} />
                        <Text style={styles.warnText}>Isso desfaz o fechamento do dia — a data de movimento volta para {preview.data_a_reabrir}.</Text>
                      </View>
                    ) : null}

                    {canReabrir && !confirmando ? (
                      <Pressable onPress={() => setConfirmando(true)} style={styles.primaryBtn} testID="posto-reabertura-turno-pedir">
                        <Text style={styles.primaryBtnText}>Reabrir Turno {preview.turno_a_reabrir}</Text>
                      </Pressable>
                    ) : null}
                    {canReabrir && confirmando ? (
                      <View style={styles.confirmRow}>
                        <Pressable onPress={() => setConfirmando(false)} style={styles.secondaryBtn} testID="posto-reabertura-turno-cancelar">
                          <Text style={styles.secondaryBtnText}>Cancelar</Text>
                        </Pressable>
                        <Pressable onPress={reabrir} disabled={saving} style={[styles.dangerBtn, saving && { opacity: 0.6 }]} testID="posto-reabertura-turno-confirmar">
                          {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Confirmar Reabertura</Text>}
                        </Pressable>
                      </View>
                    ) : null}
                  </>
                ) : (
                  <Text style={styles.hint}>Nenhum fechamento encontrado para reabrir.</Text>
                )}
              </>
            ) : null}
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
  card: { ...WEB_FILTER_CARD, gap: spacing.sm },
  cardWeb: {},
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm },
  value: { fontSize: 20, fontWeight: "700", color: colors.onSurface },
  hint: { fontSize: 13, color: colors.muted, marginTop: spacing.sm },
  warnBox: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md, padding: spacing.md, borderRadius: radius.md, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.error },
  warnText: { flex: 1, fontSize: 13, color: colors.error },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  confirmRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg },
  secondaryBtn: { flex: 1, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "700", fontSize: 15 },
  dangerBtn: { flex: 1, backgroundColor: colors.error, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center" },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
