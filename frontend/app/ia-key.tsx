// IA Key — Configurações > Administração, master-only. Cadastra a chave de
// API da Anthropic (Claude) usada pelo Motor de Formulário Dinâmico
// ("Importar Formulário" — ver layout-cadastro.tsx). Gravada em
// `controle.ANTHROPIC_API_KEY` (backend/services/ia_config_service.py) — a
// chave nunca volta em texto puro pra tela, só um indicador "configurada"
// + os últimos 4 caracteres. Pedido explícito do usuário, 2026-08-12.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";

import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

const AJUDA_ITENS = [
  {
    icon: "key-outline" as const,
    titulo: "Chave de API da Anthropic",
    texto:
      "Chave usada pelo botão \"Importar Formulário\" (Cadastro de Layout) para ler um PDF/foto de checklist pronto e propor os campos automaticamente. Sem essa chave, o botão fica indisponível — o resto do sistema funciona normalmente.",
  },
  {
    icon: "shield-checkmark-outline" as const,
    titulo: "A chave não é exibida de volta",
    texto:
      "Depois de gravada, a tela só mostra que existe uma chave configurada (e os 4 últimos caracteres) — o valor completo nunca volta para o navegador, por segurança.",
  },
  {
    icon: "globe-outline" as const,
    titulo: "Onde conseguir a chave",
    texto:
      "Acesse console.anthropic.com e crie uma conta (ou faça login, se já tiver uma). No menu lateral, vá em \"API Keys\" (ou \"Get API keys\" na tela inicial). Clique em \"Create Key\", dê um nome (ex.: \"Nome da Empresa\").",
  },
];

export default function IaKeyScreen() {
  const router = useRouter();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  const [checkingAcesso, setCheckingAcesso] = useState(true);
  const [isKontacto, setIsKontacto] = useState(false);
  const [conn, setConn] = useState<Connection | null>(null);

  const [loading, setLoading] = useState(false);
  const [configurada, setConfigurada] = useState(false);
  const [ultimosDigitos, setUltimosDigitos] = useState<string | null>(null);
  const [novaChave, setNovaChave] = useState("");
  const [saving, setSaving] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const usuarioObj = (s.usuario ?? {}) as Record<string, unknown>;
      const master = usuarioObj?.master === true || String(usuarioObj?.usuario ?? "").toUpperCase() === "KONTACTO";
      setIsKontacto(master);
      setCheckingAcesso(false);
      if (master) {
        const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
        setConn(c);
      }
    })();
  }, [router]);

  const carregar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/ia-config");
      if (j?.success) {
        setConfigurada(!!j.configurada);
        setUltimosDigitos(j.final || null);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao consultar a chave."));
    } finally {
      setLoading(false);
    }
  }, [conn, fb]);

  useEffect(() => { carregar(); }, [carregar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="IA Key está disponível apenas no web." testID="ia-key-web-only" />;
  }
  if (checkingAcesso) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.xl }} />
      </SafeAreaView>
    );
  }
  if (!isKontacto) {
    return <LockedView title="Acesso restrito" message="IA Key é acessível somente pelo usuário master." testID="ia-key-sem-permissao" />;
  }

  const salvar = async () => {
    if (!conn) return;
    if (!novaChave.trim()) { fb.showWarning("Digite a nova chave antes de gravar."); return; }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/ia-config", "POST", { api_key: novaChave.trim(), ...auditCtx });
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao gravar a chave.")); return; }
      fb.showSuccess("Chave gravada.");
      setNovaChave("");
      await carregar();
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar a chave."));
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="ia-key-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12} testID="ia-key-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>IA Key</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} testID="ia-key-ajuda" />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Chave de API da Anthropic</Text>
            <Text style={styles.hint}>
              Usada pelo botão "Importar Formulário" no Cadastro de Layout (Configurações), pra ler um PDF/foto de checklist pronto e propor os campos automaticamente.
            </Text>

            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.sm }} /> : (
              <View style={styles.statusRow}>
                <Ionicons name={configurada ? "checkmark-circle" : "close-circle-outline"} size={18} color={configurada ? colors.success : colors.muted} />
                <Text style={styles.statusText}>
                  {configurada ? `Chave configurada (termina em ${ultimosDigitos ?? "····"})` : "Nenhuma chave configurada ainda"}
                </Text>
              </View>
            )}

            <Text style={[styles.fieldLabel, { marginTop: spacing.md }]}>{configurada ? "Substituir por uma nova chave" : "Nova chave"}</Text>
            <TextInput
              value={novaChave}
              onChangeText={setNovaChave}
              style={styles.input}
              placeholder="sk-ant-..."
              placeholderTextColor={colors.muted}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              testID="ia-key-input"
            />

            <Pressable onPress={salvar} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.7 }]} testID="ia-key-salvar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
            </Pressable>
          </View>
        </View>
      </ScrollView>

      <AppModal visible={ajudaOpen} transparent animationType="slide" onRequestClose={() => setAjudaOpen(false)}>
        <Pressable style={mstyles.bg} onPress={() => setAjudaOpen(false)}>
          <Pressable style={mstyles.card} onPress={(e) => e.stopPropagation()}>
            <View style={mstyles.mheader}>
              <Text style={mstyles.mtitle}>Ajuda — IA Key</Text>
              <Pressable onPress={() => setAjudaOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {AJUDA_ITENS.map((it) => (
              <View key={it.titulo} style={mstyles.ajudaItem}>
                <Ionicons name={it.icon} size={18} color={colors.brandPrimary} />
                <View style={{ flex: 1 }}>
                  <Text style={mstyles.ajudaTitulo}>{it.titulo}</Text>
                  <Text style={mstyles.ajudaTexto}>{it.texto}</Text>
                </View>
              </View>
            ))}
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md,
    paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: spacing.md, maxWidth: 480, alignSelf: "center", width: "100%",
  },
  sectionTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  statusRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs, marginTop: spacing.md },
  statusText: { fontSize: 13, color: colors.onSurface },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  primaryBtn: { marginTop: spacing.md, paddingVertical: 12, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 14 },
});

const mstyles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", padding: spacing.xl },
  card: {
    width: "100%", maxWidth: 560, backgroundColor: colors.surface, padding: spacing.lg,
    borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
  },
  mheader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  mtitle: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  ajudaItem: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  ajudaTitulo: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  ajudaTexto: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
