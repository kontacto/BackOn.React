import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { Connection, listConnections } from "@/src/utils/storage/connections";
import { setSession } from "@/src/utils/storage/session";
import { usePermissions } from "@/src/permissions";
import { colors, radius, spacing } from "@/src/theme/colors";
import BiometricButton from "@/src/components/BiometricButton";
import EnableBiometricModal from "@/src/components/EnableBiometricModal";
import { useBiometricLogin } from "@/src/hooks/useBiometricLogin";

const GENERIC_AUTH_ERROR = "Usuário ou senha inválidos.";

function normalizeApiUrl(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

const LOGIN_CARD_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 10px 24px rgba(11, 27, 51, 0.08)" }
    : {
        shadowColor: "#0B1B33",
        shadowOpacity: 0.08,
        shadowRadius: 24,
        shadowOffset: { width: 0, height: 10 },
        elevation: 2,
      };

type LoginResult = {
  success: boolean;
  message: string;
  empresa?: string;
  server?: string;
  database?: string;
  usuario?: Record<string, unknown> | null;
  funcionario?: Record<string, unknown> | null;
  error_step?: string | null;
  error_line?: string | null;
  error_code_line?: string | null;
  error_query?: string | null;
  attempted?: {
    empresa?: string;
    server?: string;
    database?: string;
    sql_user?: string;
    login_user?: string;
    login_timeout?: number;
  } | null;
};

function isMasterKontactoUser(user: Record<string, unknown> | null | undefined): boolean {
  if (!user) return false;
  if (user.master === true) return true;
  return String(user.usuario ?? "").trim().toUpperCase() === "KONTACTO";
}

export default function LoginScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const { reload: reloadPermissions } = usePermissions();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selected, setSelected] = useState<Connection | null>(null);
  const [usuario, setUsuario] = useState("");
  const [senha, setSenha] = useState("");
  const [showPicker, setShowPicker] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorDetails, setErrorDetails] = useState<LoginResult | null>(null);
  const [showEnable, setShowEnable] = useState(false);
  const [enabling, setEnabling] = useState(false);
  const pendingCredsRef = useRef<{ usuario: string; senha: string } | null>(null);

  const {
    canBiometricLogin,
    shouldOfferEnable,
    loginWithBiometrics,
    enableBiometrics,
    disableBiometrics,
  } = useBiometricLogin(selected);

  // Centraliza a persistência da sessão (reaproveitada pelo login por senha e por biometria).
  const applySession = useCallback(
    async (data: LoginResult, conn: Connection) => {
      await setSession({
        empresa: data.empresa || conn.empresa,
        server: data.server || conn.servidor,
        database: data.database || conn.banco,
        logo: conn.logo || "",
        usuario: data.usuario ?? null,
        funcionario: data.funcionario ?? null,
        loggedAt: new Date().toISOString(),
      });
      await reloadPermissions();
    },
    [reloadPermissions]
  );

  const reload = useCallback(async () => {
    const items = await listConnections();
    setConnections(items);
    if (items.length === 0) {
      router.replace("/connections?initial=1");
      return;
    }
    setSelected((prev) => {
      if (prev) {
        const stillExists = items.find((c) => c.id === prev.id);
        if (stillExists) return stillExists;
      }
      return items[0];
    });
  }, [router]);

  useFocusEffect(
    useCallback(() => {
      reload();
    }, [reload])
  );

  useEffect(() => {
    setError(null);
    setErrorDetails(null);
  }, [selected, usuario, senha]);

  const handleSubmit = async () => {
    if (submitting) return;
    setError(null);
    setErrorDetails(null);
    if (!selected) {
      setError("Selecione uma empresa.");
      return;
    }
    if (!selected.banco || !selected.banco.trim()) {
      setError("A conexão selecionada não tem 'Banco' definido. Edite a conexão.");
      return;
    }
    if (!usuario.trim()) {
      setError("Informe o usuário.");
      return;
    }
    if (!senha) {
      setError("Informe a senha.");
      return;
    }
    setSubmitting(true);
    try {
      // Usa a URL da API CONFIGURADA NA CONEXÃO SELECIONADA (não mais EXPO_PUBLIC_BACKEND_URL)
      if (!selected.api || !selected.api.trim()) {
        setError("A conexão selecionada não tem URL da API definida. Edite a conexão.");
        return;
      }
      const apiUrl = normalizeApiUrl(selected.api);
      // Timeout defensivo: evita o botão ficar "processando" para sempre quando a
      // URL da API está inacessível (ex.: conexão salva com URL antiga após um fork).
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 30000);
      let resp: Response;
      try {
        resp = await fetch(`${apiUrl}/api/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            empresa: selected.empresa,
            servidor: selected.servidor,
            banco: selected.banco,
            usuario: usuario.trim(),
            senha,
          }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timer);
      }
      const data = (await resp.json()) as LoginResult & { detail?: string };
      if (!resp.ok) {
        setError(data.detail || GENERIC_AUTH_ERROR);
        return;
      }
      if (data.success) {
        await applySession(data, selected);
        if (isMasterKontactoUser(data.usuario)) {
          // Regra de segurança: conta master (KONTACTO) não pode persistir senha no dispositivo.
          await disableBiometrics();
          pendingCredsRef.current = null;
          setSenha("");
          router.replace("/principal");
        } else if (shouldOfferEnable) {
          // Oferece ativar a biometria para os próximos logins neste dispositivo.
          pendingCredsRef.current = { usuario: usuario.trim(), senha };
          setShowEnable(true);
        } else {
          setSenha("");
          router.replace("/principal");
        }
      } else {
        setErrorDetails(data);
        if (data.message === GENERIC_AUTH_ERROR) {
          setError(GENERIC_AUTH_ERROR);
        } else if (
          data.message &&
          (data.message.startsWith("Erro") || data.message.startsWith("Falha"))
        ) {
          setError(data.message);
        } else {
          setError(GENERIC_AUTH_ERROR);
        }
      }
    } catch (e: unknown) {
      const isAbort = e instanceof Error && e.name === "AbortError";
      if (isAbort) {
        setError(
          `Tempo esgotado ao contatar o servidor (${selected.api}). ` +
            "Verifique a URL da API em Conexões e sua conexão com a internet."
        );
      } else {
        const msg = e instanceof Error ? e.message : "Falha de rede";
        setError(
          `Não foi possível contatar o servidor (${msg}). ` +
            `Confira a URL da API da conexão: ${selected.api}`
        );
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleBiometricLogin = async () => {
    if (!selected) return;
    setError(null);
    setErrorDetails(null);
    setSubmitting(true);
    try {
      const res = await loginWithBiometrics();
      if (res.ok && res.data) {
        await applySession(res.data as LoginResult, selected);
        setSenha("");
        router.replace("/principal");
      } else if (res.message) {
        setError(res.message);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const finishAndGo = () => {
    setShowEnable(false);
    pendingCredsRef.current = null;
    setSenha("");
    router.replace("/principal");
  };

  const handleEnableAccept = async () => {
    const creds = pendingCredsRef.current;
    if (!creds) {
      finishAndGo();
      return;
    }
    setEnabling(true);
    try {
      await enableBiometrics(creds);
    } finally {
      setEnabling(false);
      finishAndGo();
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="login-screen">
      <View style={styles.header}>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.brand}>Back-On</Text>
        <Pressable
          onPress={() => router.push("/connections")}
          style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
          hitSlop={12}
          testID="login-open-connections-button"
        >
          <Ionicons name="server-outline" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.iconBtnLabel}>Conexões</Text>
        </Pressable>
      </View>

      <KeyboardAvoidingView
        behavior={Platform.OS === "ios" ? "padding" : undefined}
        style={{ flex: 1 }}
      >
        <ScrollView
          contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}
          keyboardShouldPersistTaps="handled"
        >
          <View
            style={[styles.webCard, LOGIN_CARD_SHADOW_STYLE]}
          >
            <Text style={styles.title}>Bem-vindo</Text>
            <Text style={styles.subtitle}>
              Selecione a empresa e informe suas credenciais para conectar ao banco.
            </Text>

            <View style={styles.field}>
              <Text style={styles.label}>Empresa</Text>
              <Pressable
                onPress={() => setShowPicker(true)}
                style={({ pressed }) => [styles.input, styles.inputRow, pressed && styles.pressed]}
                testID="login-empresa-picker"
              >
                <Text
                  style={[styles.inputText, !selected && { color: colors.muted }]}
                  numberOfLines={1}
                >
                  {selected ? selected.empresa : "Selecione uma empresa"}
                </Text>
                <Ionicons name="chevron-down" size={18} color={colors.onSurfaceTertiary} />
              </Pressable>
              {selected ? (
                <View style={styles.metaRow}>
                  <View style={styles.metaItem}>
                    <Ionicons name="server-outline" size={12} color={colors.muted} />
                    <Text style={styles.metaText} numberOfLines={1} testID="login-empresa-servidor">
                      {selected.servidor}
                    </Text>
                  </View>
                  <View style={styles.metaItem}>
                    <Ionicons name="cube-outline" size={12} color={colors.muted} />
                    <Text style={styles.metaText} numberOfLines={1} testID="login-empresa-banco">
                      {selected.banco || "Banco não definido"}
                    </Text>
                  </View>
                  <View style={styles.metaItem}>
                    <Ionicons name="cloud-outline" size={12} color={colors.muted} />
                    <Text style={styles.metaText} numberOfLines={1} testID="login-empresa-api">
                      {selected.api || "API não definida"}
                    </Text>
                  </View>
                </View>
              ) : null}
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Usuário</Text>
              <TextInput
                value={usuario}
                onChangeText={setUsuario}
                placeholder="Digite seu usuário"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
                testID="login-usuario-input"
              />
            </View>

            <View style={styles.field}>
              <Text style={styles.label}>Senha</Text>
              <TextInput
                value={senha}
                onChangeText={setSenha}
                placeholder="Digite sua senha"
                placeholderTextColor={colors.muted}
                secureTextEntry
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
                testID="login-senha-input"
                returnKeyType="go"
                onSubmitEditing={handleSubmit}
              />
            </View>

            {error ? (
              <View style={[styles.banner, styles.bannerError]} testID="login-error">
                <Ionicons name="alert-circle" size={16} color={colors.error} />
                <View style={{ flex: 1 }}>
                  <Text style={[styles.bannerText, { color: colors.error, fontWeight: "500" }]}>
                    {error}
                  </Text>
                  {errorDetails?.attempted ? (
                    <View style={styles.errorMeta} testID="login-error-attempted">
                      <Text style={styles.errorMetaTitle}>Conexão tentada</Text>
                      <Text style={styles.errorMetaLine}>
                        Empresa: {errorDetails.attempted.empresa}
                      </Text>
                      <Text style={styles.errorMetaLine}>
                        Servidor: {errorDetails.attempted.server}
                      </Text>
                      <Text style={styles.errorMetaLine}>
                        Banco: {errorDetails.attempted.database}
                      </Text>
                      <Text style={styles.errorMetaLine}>
                        Usuário SQL: {errorDetails.attempted.sql_user}
                      </Text>
                      <Text style={styles.errorMetaLine}>
                        Usuário login: {errorDetails.attempted.login_user}
                      </Text>
                      {errorDetails.attempted.login_timeout ? (
                        <Text style={styles.errorMetaLine}>
                          Timeout: {errorDetails.attempted.login_timeout}s
                        </Text>
                      ) : null}
                    </View>
                  ) : null}
                  {errorDetails?.error_step || errorDetails?.error_line ? (
                    <View style={styles.errorMeta} testID="login-error-origin">
                      <Text style={styles.errorMetaTitle}>Origem do erro</Text>
                      {errorDetails.error_step ? (
                        <Text style={styles.errorMetaLine}>
                          Etapa: {errorDetails.error_step}
                        </Text>
                      ) : null}
                      {errorDetails.error_line ? (
                        <Text style={styles.errorMetaLine}>
                          Linha: {errorDetails.error_line}
                        </Text>
                      ) : null}
                      {errorDetails.error_code_line ? (
                        <Text style={styles.errorMetaCode}>
                          {errorDetails.error_code_line}
                        </Text>
                      ) : null}
                      {errorDetails.error_query ? (
                        <>
                          <Text style={[styles.errorMetaLine, { marginTop: 4 }]}>Query:</Text>
                          <Text style={styles.errorMetaCode}>
                            {errorDetails.error_query}
                          </Text>
                        </>
                      ) : null}
                    </View>
                  ) : null}
                </View>
              </View>
            ) : null}
          </View>
        </ScrollView>

        <View style={[styles.footer, isWeb && styles.footerWeb]}>
          <View style={isWeb ? styles.footerInner : undefined}>
            <Pressable
              onPress={handleSubmit}
              disabled={submitting}
              style={({ pressed }) => [
                styles.primaryBtn,
                (pressed || submitting) && styles.primaryBtnPressed,
              ]}
              testID="login-submit-button"
            >
              {submitting ? (
                <ActivityIndicator color={colors.onBrandPrimary} />
              ) : (
                <Text style={styles.primaryBtnText}>Entrar</Text>
              )}
            </Pressable>
            {canBiometricLogin ? (
              <BiometricButton onPress={handleBiometricLogin} busy={submitting} />
            ) : null}
          </View>
        </View>
      </KeyboardAvoidingView>

      <Modal
        visible={showPicker}
        transparent
        animationType="slide"
        onRequestClose={() => setShowPicker(false)}
      >
        <Pressable
          style={[styles.backdrop, isWeb && styles.backdropWebCompact]}
          onPress={() => setShowPicker(false)}
        >
          <Pressable
            style={[styles.sheet, isWeb && styles.sheetWebCompact]}
            onPress={(e) => e.stopPropagation()}
            testID="login-empresa-sheet"
          >
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>Selecione a empresa</Text>
            <ScrollView style={{ maxHeight: 360 }}>
              {connections.map((c) => {
                const isSel = selected?.id === c.id;
                return (
                  <Pressable
                    key={c.id}
                    onPress={() => {
                      setSelected(c);
                      setShowPicker(false);
                    }}
                    style={({ pressed }) => [
                      styles.sheetItem,
                      isSel && styles.sheetItemSelected,
                      pressed && styles.pressed,
                    ]}
                    testID={`login-empresa-option-${c.id}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.sheetItemTitle}>{c.empresa}</Text>
                      <Text style={styles.sheetItemSub}>
                        {c.servidor} · {c.banco || "sem banco"}
                      </Text>
                    </View>
                    {isSel ? (
                      <Ionicons name="checkmark" size={20} color={colors.brandPrimary} />
                    ) : null}
                  </Pressable>
                );
              })}
            </ScrollView>
            <Pressable
              onPress={() => {
                setShowPicker(false);
                router.push("/connections");
              }}
              style={({ pressed }) => [styles.sheetCta, pressed && styles.pressed]}
              testID="login-manage-connections-button"
            >
              <Ionicons name="settings-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.sheetCtaText}>Gerenciar conexões</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      <EnableBiometricModal
        visible={showEnable}
        busy={enabling}
        onAccept={handleEnableAccept}
        onDecline={finishAndGo}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    backgroundColor: colors.brandPrimary,
  },
  brand: {
    fontSize: 20,
    fontWeight: "500",
    color: colors.onBrandPrimary,
    letterSpacing: -0.3,
  },
  iconBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: "rgba(255,255,255,0.25)",
  },
  iconBtnLabel: { fontSize: 13, color: colors.onBrandPrimary, fontWeight: "500" },
  pressed: { opacity: 0.7 },
  scroll: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xxxl,
  },
  scrollWeb: {
    alignItems: "center",
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xl,
  },
  webCard: {
    width: "100%",
    maxWidth: 760,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: {
    fontSize: 28,
    fontWeight: "500",
    color: colors.onSurface,
    letterSpacing: -0.5,
  },
  subtitle: {
    marginTop: spacing.sm,
    fontSize: 14,
    color: colors.onSurfaceTertiary,
    lineHeight: 20,
  },
  field: { marginTop: spacing.xl },
  label: {
    fontSize: 13,
    fontWeight: "500",
    color: colors.onSurfaceTertiary,
    marginBottom: spacing.sm,
  },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontSize: 15,
    color: colors.onSurface,
    minHeight: 48,
  },
  inputRow: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  inputText: { fontSize: 15, color: colors.onSurface, flex: 1, paddingRight: spacing.sm },
  metaRow: {
    marginTop: 8,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  metaItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  metaText: { fontSize: 12, color: colors.muted, maxWidth: 200 },
  banner: {
    marginTop: spacing.lg,
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  bannerError: { backgroundColor: "#FBECEC", borderColor: "#F1C9C9" },
  bannerSuccess: { backgroundColor: "#E7F5EE", borderColor: "#BFE0CE" },
  bannerText: { fontSize: 13, flex: 1, lineHeight: 18 },
  bannerSub: { fontSize: 12, color: colors.onSurfaceTertiary, marginTop: 2 },
  errorMeta: {
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: "#E5B5B5",
    gap: 2,
  },
  errorMetaTitle: {
    fontSize: 11,
    fontWeight: "600",
    color: colors.error,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginBottom: 2,
  },
  errorMetaLine: { fontSize: 12, color: colors.onSurfaceTertiary, lineHeight: 16 },
  errorMetaCode: {
    fontSize: 11,
    color: colors.onSurface,
    backgroundColor: "rgba(0,0,0,0.05)",
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: 4,
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }),
    marginTop: 2,
  },
  footer: {
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  footerWeb: {
    paddingHorizontal: spacing.xl,
    paddingTop: 0,
    paddingBottom: spacing.xl,
    backgroundColor: "transparent",
    borderTopWidth: 0,
    alignItems: "center",
  },
  footerInner: {
    width: "100%",
    maxWidth: 760,
    gap: spacing.sm,
  },
  primaryBtn: {
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
  },
  primaryBtnPressed: { opacity: 0.85 },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 15 },
  // "Modal/Selector Standard (Web)" — mobile: bottom sheet full-width, só
  // cantos de cima arredondados; web: card centralizado, maxWidth 560,
  // todos os cantos + borda ("redução forte"). Ver CLAUDE.md > "Padrões de
  // UI — Modais, Mensagens e Formulários (Web)".
  backdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  backdropWebCompact: { justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  sheet: {
    width: "100%",
    backgroundColor: colors.surfaceSecondary,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  sheetWebCompact: {
    maxWidth: 560,
    alignSelf: "center",
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  sheetHandle: {
    alignSelf: "center",
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginBottom: spacing.md,
  },
  sheetTitle: {
    fontSize: 16,
    fontWeight: "500",
    color: colors.onSurface,
    marginBottom: spacing.md,
  },
  sheetItem: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
    backgroundColor: colors.surfaceSecondary,
  },
  sheetItemSelected: {
    borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  sheetItemTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  sheetItemSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sheetCta: {
    marginTop: spacing.md,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
  },
  sheetCtaText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 14 },
});
