import { useCallback, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

// Cadastro/Tabelas Auxiliares > Mensagens PDV (tabela `mensagenspdv`, registro
// único — legado FrmManMsgPDV). Só 3 linhas de mensagem promocional para o
// Cupom Fiscal (linha4/linha5 existem na tabela mas ficavam escondidas na
// tela legada e nunca eram editadas — não expostas aqui).
export default function MensagensPdvScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Mensagens PDV está disponível apenas no web."
        testID="mensagens-pdv-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [linha1, setLinha1] = useState("");
  const [linha2, setLinha2] = useState("");
  const [linha3, setLinha3] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const canSave = can("MENSAGENS_PDV.GRAVAR") || isMaster;

  const boot = useCallback(async () => {
    setLoading(true);
    const session = await getSession();
    if (!session) {
      router.replace("/login");
      setLoading(false);
      return;
    }
    const conns = await listConnections();
    const c = conns.find((x) => x.empresa === session.empresa) ?? null;
    setConn(c);
    if (!c) {
      fb.showError("Conexão não encontrada.");
      setLoading(false);
      return;
    }
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/mensagens-pdv?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setLinha1(j.linha1 || "");
        setLinha2(j.linha2 || "");
        setLinha3(j.linha3 || "");
      } else {
        fb.showError(j?.message || "Erro ao carregar mensagens.");
      }
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [fb]);

  useFocusEffect(
    useCallback(() => {
      boot();
    }, [boot])
  );

  const handleSave = async () => {
    if (!conn) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/mensagens-pdv`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, linha1, linha2, linha3 }),
      });
      const j = await r.json();
      if (j?.success) fb.showSuccess(j.message || "Mensagens gravadas.");
      else fb.showError(j?.message || "Erro ao gravar.");
    } catch (e) {
      fb.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="mensagens-pdv-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Mensagens PDV</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} />
          ) : (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Mensagens promocionais para o Cupom Fiscal</Text>

              <Text style={styles.label}>Linha 1</Text>
              <TextInput
                value={linha1}
                onChangeText={setLinha1}
                editable={canSave}
                maxLength={48}
                placeholder="Ex.: Volte sempre!"
                placeholderTextColor={colors.muted}
                style={styles.input}
                testID="mensagens-pdv-linha1"
              />

              <Text style={styles.label}>Linha 2</Text>
              <TextInput
                value={linha2}
                onChangeText={setLinha2}
                editable={canSave}
                maxLength={48}
                placeholderTextColor={colors.muted}
                style={styles.input}
                testID="mensagens-pdv-linha2"
              />

              <Text style={styles.label}>Linha 3</Text>
              <TextInput
                value={linha3}
                onChangeText={setLinha3}
                editable={canSave}
                maxLength={48}
                placeholderTextColor={colors.muted}
                style={styles.input}
                testID="mensagens-pdv-linha3"
              />

              {canSave ? (
                <Pressable
                  onPress={handleSave}
                  disabled={saving}
                  style={[styles.primaryBtn, saving && { opacity: 0.6 }]}
                  testID="mensagens-pdv-salvar"
                >
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: {
    ...WEB_FILTER_CARD,
    maxWidth: 480,
    gap: spacing.sm,
  },
  cardTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
