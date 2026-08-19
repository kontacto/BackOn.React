// Abertura do Dia — Configurações > Geral. Migração de "Gerencial >
// Abertura do Dia" (Ger_Abr_Click, MdiPrincipal) + Revenda\frmAbreDia.frm.
// Avança controle.Data_Movimento (com validações + confirmação se for
// retroceder) e grava log de auditoria. A reconciliação de estoque que o
// legado fazia junto disso está CONFIRMADA em desuso pela equipe VB6
// (2026-08-16) — deliberadamente não portada. Ver PENDENCIAS.md > "MDI
// Principal (VB6)".
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import LockedView from "@/src/components/LockedView";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

function brDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function AberturaDiaScreen() {
  const router = useRouter();
  const fb = useFeedback();
  const auditCtx = useAuditContext();
  const { can, isMaster } = usePermissions();

  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(true);
  const [dataMovimento, setDataMovimento] = useState<string | null>(null);
  const [controlaAberturaDia, setControlaAberturaDia] = useState(false);
  const [disponivel, setDisponivel] = useState(true);
  const [novaData, setNovaData] = useState<string | null>(todayISO());
  const [saving, setSaving] = useState(false);

  const carregar = useCallback(async (c: Connection) => {
    setLoading(true);
    try {
      const j = await apiGet(c, "/api/abertura-dia/status");
      if (j?.success) {
        setDataMovimento(j.data_movimento || null);
        setControlaAberturaDia(!!j.controla_abertura_dia);
        setDisponivel(j.disponivel !== false);
        setNovaData(j.data_movimento || todayISO());
      } else {
        fb.showError(friendlyApiError(j, "Falha ao carregar."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [fb]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { fb.showError("Conexão não encontrada."); return; }
      setConn(c);
      await carregar(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const gravar = useCallback(async (confirmaRetrocesso: boolean) => {
    if (!conn || !novaData) return;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/abertura-dia/abrir", "POST", {
        nova_data: novaData,
        usuario_alteracao: auditCtx.usuario_alteracao,
        classe: auditCtx.classe,
        master: isMaster,
        plataforma: auditCtx.plataforma,
        confirma_retrocesso: confirmaRetrocesso,
      });
      if (j?.success) {
        fb.showSuccess(`Data de Movimento atualizada para ${brDate(j.data_movimento)}.`);
        setDataMovimento(j.data_movimento);
      } else if (j?.requer_confirmacao) {
        fb.showConfirm(j.message, () => gravar(true));
      } else {
        fb.showError(friendlyApiError(j, "Falha ao abrir o dia."));
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setSaving(false);
    }
  }, [conn, novaData, auditCtx, isMaster, fb]);

  if (!isWeb) {
    return <LockedView message="Abertura do Dia está disponível apenas no aplicativo web." />;
  }
  if (!loading && !can("ABERTURA_DIA.ABRIR") && !isMaster) {
    return <LockedView message="Você não tem permissão para acessar esta tela." />;
  }
  if (!loading && !disponivel) {
    return <LockedView message="Abertura do Dia ainda está em teste — disponível só para a Kontacto por enquanto." />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="abertura-dia-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerBtn} testID="abdia-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Abertura do Dia</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          {loading ? (
            <ActivityIndicator style={{ marginTop: 40 }} color={colors.brandPrimary} />
          ) : (
            <View style={[styles.card, isWeb && styles.cardWeb]}>
              <Text style={styles.hint}>
                Controla a Data de Movimento do sistema — a data usada como referência em relatórios e
                fechamentos. {controlaAberturaDia
                  ? "Esta empresa usa abertura MANUAL — a data só avança quando alguém grava aqui."
                  : "Esta empresa usa abertura AUTOMÁTICA — a data já avança sozinha ao criar um novo Pedido/O.S.; use esta tela só se precisar corrigir manualmente."}
              </Text>

              <View style={styles.row}>
                <Text style={styles.label}>Data de Movimento Atual</Text>
                <Text style={styles.valorAtual}>{brDate(dataMovimento)}</Text>
              </View>

              <Text style={styles.label}>Nova Data</Text>
              {isWeb ? (
                <WebDateField value={novaData} onChange={setNovaData} max={todayISO()} testID="abdia-nova-data" />
              ) : (
                <DateField value={novaData} onChange={setNovaData} allowClear={false} testID="abdia-nova-data" />
              )}

              <Pressable
                onPress={() => gravar(false)}
                disabled={saving || !novaData}
                style={({ pressed }) => [styles.btnGravar, (pressed || saving || !novaData) && { opacity: 0.85 }]}
                testID="abdia-gravar"
              >
                {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="calendar-outline" size={16} color={colors.onBrandPrimary} />
                    <Text style={styles.btnGravarText}>Abrir Dia</Text>
                  </>
                )}
              </Pressable>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  headerBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 16, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.lg, gap: spacing.sm,
  },
  cardWeb: WEB_FILTER_CARD,
  hint: { fontSize: 12, color: colors.muted, lineHeight: 18, marginBottom: spacing.sm },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  valorAtual: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  btnGravar: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 44, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, marginTop: spacing.md,
  },
  btnGravarText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
});
