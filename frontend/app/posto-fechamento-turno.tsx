// Posto de Combustível > Fechamento de Turno — migração de
// `FrmFecTurno.frm` (pasta VB6 Posto). Fecha o turno corrente
// (`controle.turno_movimento`); ao fechar o último turno do dia, também
// avança `controle.data_movimento` pro dia seguinte. Ver
// backend/services/fechamento_turno_service.py pro que foi
// deliberadamente simplificado (sem captura automática de encerrante via
// hardware Wayne Fusion — Fase 2; sem impressão de relatório; sem a
// checagem hardcoded de CNPJ que liberava fechar com pendências).
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
type Status = {
  data_movimento: string; turno_atual: number; qtd_turnos: number;
  ultimo_turno_do_dia: boolean; abastecimentos_pendentes: boolean; hora_minima: string | null;
};

export default function PostoFechamentoTurnoScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Fechamento de Turno está disponível apenas no web." testID="posto-fechamento-turno-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-fechamento-turno-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 1000); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/posto/fechamento-turno/status?${qs}`);
      const j = await r.json();
      if (j?.success) setStatus(j);
      else { setStatus(null); if (j?.message) showToast(j.message); }
    } catch { setStatus(null); } finally { setLoading(false); }
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

  const fechar = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/fechamento-turno/fechar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Turno fechado." : "Falha ao fechar."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const canClose = can("POSTO_FEC_TURNO.GRAVAR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-fechamento-turno-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Fechamento de Turno</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
            {!loading && status ? (
              <>
                <Text style={styles.label}>Data de Movimento</Text>
                <Text style={styles.value}>{status.data_movimento}</Text>
                <Text style={styles.label}>Turno Atual</Text>
                <Text style={styles.value}>{status.turno_atual} de {status.qtd_turnos}{status.ultimo_turno_do_dia ? " (último do dia)" : ""}</Text>
                {status.hora_minima ? (
                  <Text style={styles.hint}>Horário mínimo para fechar este turno: {status.hora_minima}</Text>
                ) : null}
                {status.abastecimentos_pendentes ? (
                  <View style={styles.warnBox}>
                    <Ionicons name="warning-outline" size={18} color={colors.error} />
                    <Text style={styles.warnText}>Há abastecimentos pendentes de baixa neste turno — baixe-os em Aferições/Despesas antes de fechar.</Text>
                  </View>
                ) : null}
                {canClose ? (
                  <Pressable onPress={fechar} disabled={saving || status.abastecimentos_pendentes} style={[styles.primaryBtn, (saving || status.abastecimentos_pendentes) && { opacity: 0.5 }]} testID="posto-fechamento-turno-fechar">
                    {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Fechar Turno {status.turno_atual}{status.ultimo_turno_do_dia ? " (encerra o dia)" : ""}</Text>}
                  </Pressable>
                ) : null}
              </>
            ) : null}
            {!loading && !status ? <Text style={styles.hint}>Não foi possível carregar o status do turno.</Text> : null}
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
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
