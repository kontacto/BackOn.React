import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { Session, clearSession, getSession } from "@/src/utils/storage/session";
import { colors, radius, spacing } from "@/src/theme/colors";

function pickFirst(obj: Record<string, unknown> | null | undefined, keys: string[]): string | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") {
      return String(v);
    }
  }
  return null;
}

function formatValue(v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? "Sim" : "Não";
  return String(v);
}

function entries(obj: Record<string, unknown> | null | undefined): [string, unknown][] {
  if (!obj) return [];
  // Esconder: senha (segurança), campos enriquecidos auxiliares (já mostrados no resumo),
  // e DDD separados (mostrados junto do telefone como 'celular'/'telefone')
  const hidden = new Set([
    "senha",
    "administrador_label",
    "classe_label",
    "situacao_label",
    "ddd_prof",
    "ddd_cel_prof",
  ]);
  return Object.entries(obj).filter(([k]) => !hidden.has(k.toLowerCase()));
}

export default function PrincipalScreen() {
  const router = useRouter();
  const [session, setSessionState] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [showAllUsuario, setShowAllUsuario] = useState(false);
  const [showAllFuncionario, setShowAllFuncionario] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const s = await getSession();
    if (!s) {
      router.replace("/login");
      return;
    }
    setSessionState(s);
    setLoading(false);
  }, [router]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  useEffect(() => {
    load();
  }, [load]);

  const handleLogout = async () => {
    await clearSession();
    router.replace("/login");
  };

  const displayName = useMemo(() => {
    if (!session) return "";
    const funcName = pickFirst(session.funcionario, [
      "nome",
      "nome_guerra",
      "nome_completo",
      "apelido",
    ]);
    const usrName = pickFirst(session.usuario, ["nome", "usuario"]);
    return funcName || usrName || "";
  }, [session]);

  const cargo = useMemo(
    () =>
      pickFirst(session?.funcionario, [
        "cod_funcao",
        "codcargo",
        "cargo",
        "funcao",
        "setor",
      ]) || null,
    [session]
  );

  const nomeGuerra = useMemo(
    () => pickFirst(session?.funcionario, ["nome_guerra"]) || null,
    [session]
  );

  const situacao = useMemo(
    () =>
      pickFirst(session?.funcionario, ["situacao_label", "situacao"]) || null,
    [session]
  );

  const celular = useMemo(
    () => pickFirst(session?.funcionario, ["celular", "tel_cel_prof"]) || null,
    [session]
  );

  const email = useMemo(
    () => pickFirst(session?.funcionario, ["email"]) || null,
    [session]
  );

  const empresaCodigo = useMemo(
    () => pickFirst(session?.funcionario, ["empresa"]) || null,
    [session]
  );

  const classe = useMemo(
    () => pickFirst(session?.usuario, ["classe_label", "classe"]) || null,
    [session]
  );

  const isAdmin = useMemo(
    () => pickFirst(session?.usuario, ["administrador_label"]) === "Sim",
    [session]
  );

  if (loading || !session) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  const usuarioEntries = entries(session.usuario);
  const funcionarioEntries = entries(session.funcionario);
  const usuarioShown = showAllUsuario ? usuarioEntries : usuarioEntries.slice(0, 6);
  const funcionarioShown = showAllFuncionario
    ? funcionarioEntries
    : funcionarioEntries.slice(0, 6);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="principal-screen">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Back-On</Text>
          <Text style={styles.headerSub} numberOfLines={1}>
            {session.empresa}
          </Text>
        </View>
        <Pressable
          onPress={handleLogout}
          style={({ pressed }) => [styles.logoutBtn, pressed && styles.pressed]}
          hitSlop={12}
          testID="principal-logout-button"
        >
          <Ionicons name="log-out-outline" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.logoutLabel}>Sair</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.hero} testID="principal-welcome">
          {session.logo ? (
            <Image
              source={{ uri: session.logo }}
              style={styles.avatar}
              resizeMode="cover"
              testID="principal-logo"
            />
          ) : (
            <View style={styles.avatar}>
              <Ionicons name="person" size={28} color={colors.onBrandPrimary} />
            </View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={styles.welcome}>Bem-vindo,</Text>
            <Text style={styles.heroName} numberOfLines={1}>
              {displayName || "Usuário"}
            </Text>
            {nomeGuerra && nomeGuerra !== displayName ? (
              <Text style={styles.heroSub}>@{nomeGuerra}</Text>
            ) : null}
            {classe ? (
              <Text style={styles.heroSub}>Grupo do Sistema: {classe}</Text>
            ) : cargo ? (
              <Text style={styles.heroSub}>Função: {cargo}</Text>
            ) : null}
          </View>
        </View>

        {/* Resumo (campos principais do banco BackOn) */}
        <View style={styles.summary} testID="principal-summary">
          {situacao ? (
            <View style={styles.summaryRow}>
              <Ionicons name="checkmark-circle-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.summaryLabel}>Situação</Text>
              <Text style={styles.summaryValue}>{situacao}</Text>
            </View>
          ) : null}
          {classe ? (
            <View style={styles.summaryRow}>
              <Ionicons name="ribbon-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.summaryLabel}>Classe</Text>
              <Text style={styles.summaryValue}>{classe}</Text>
            </View>
          ) : null}
          {isAdmin ? (
            <View style={styles.summaryRow}>
              <Ionicons name="shield-checkmark-outline" size={14} color={colors.success} />
              <Text style={styles.summaryLabel}>Acesso</Text>
              <Text style={[styles.summaryValue, { color: colors.success }]}>Administrador</Text>
            </View>
          ) : null}
          {empresaCodigo ? (
            <View style={styles.summaryRow}>
              <Ionicons name="business-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.summaryLabel}>Empresa</Text>
              <Text style={styles.summaryValue}>#{empresaCodigo}</Text>
            </View>
          ) : null}
          {email ? (
            <View style={styles.summaryRow}>
              <Ionicons name="mail-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.summaryLabel}>E-mail</Text>
              <Text style={styles.summaryValue} numberOfLines={1}>{email}</Text>
            </View>
          ) : null}
          {celular ? (
            <View style={styles.summaryRow}>
              <Ionicons name="call-outline" size={14} color={colors.brandPrimary} />
              <Text style={styles.summaryLabel}>Celular</Text>
              <Text style={styles.summaryValue}>{celular}</Text>
            </View>
          ) : null}
        </View>

        <View style={styles.connRow}>
          <View style={styles.connItem}>
            <Ionicons name="server-outline" size={14} color={colors.muted} />
            <Text style={styles.connText} numberOfLines={1}>
              {session.server}
            </Text>
          </View>
          <View style={styles.connItem}>
            <Ionicons name="cube-outline" size={14} color={colors.muted} />
            <Text style={styles.connText} numberOfLines={1}>
              {session.database}
            </Text>
          </View>
        </View>

        <Text style={styles.sectionTitle}>Tela Principal</Text>
        <Text style={styles.sectionSub}>
          Painel de controle. Os módulos do sistema serão exibidos abaixo.
        </Text>

        <View style={styles.tilesGrid}>
          {[
            { label: "Clientes", icon: "people-outline" as const, route: "/clientes" as const },
            { label: "Pedidos", icon: "swap-horizontal-outline" as const, route: null },
            { label: "Relatórios", icon: "bar-chart-outline" as const, route: null },
            { label: "Configurações", icon: "settings-outline" as const, route: null },
          ].map((t) => (
            <Pressable
              key={t.label}
              onPress={() => t.route && router.push(t.route)}
              disabled={!t.route}
              style={({ pressed }) => [styles.tile, pressed && t.route && { opacity: 0.8 }]}
              testID={`principal-tile-${t.label.toLowerCase()}`}
            >
              <View style={styles.tileIcon}>
                <Ionicons name={t.icon} size={22} color={colors.brandPrimary} />
              </View>
              <Text style={styles.tileLabel}>{t.label}</Text>
              <Text style={styles.tileHint}>{t.route ? "Abrir" : "Em breve"}</Text>
            </Pressable>
          ))}
        </View>

        <View style={styles.card} testID="principal-usuario-card">
          <View style={styles.cardHeader}>
            <Ionicons name="id-card-outline" size={18} color={colors.brandPrimary} />
            <Text style={styles.cardTitle}>Usuário (usuarioObj)</Text>
          </View>
          {usuarioEntries.length === 0 ? (
            <Text style={styles.emptyHint}>Sem dados.</Text>
          ) : (
            <>
              {usuarioShown.map(([k, v]) => (
                <View key={k} style={styles.kvRow}>
                  <Text style={styles.kvKey}>{k}</Text>
                  <Text style={styles.kvValue} numberOfLines={2}>
                    {formatValue(v)}
                  </Text>
                </View>
              ))}
              {usuarioEntries.length > 6 ? (
                <Pressable
                  onPress={() => setShowAllUsuario((v) => !v)}
                  style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}
                  testID="principal-usuario-toggle"
                >
                  <Text style={styles.toggleText}>
                    {showAllUsuario ? "Mostrar menos" : `Mostrar mais (${usuarioEntries.length - 6})`}
                  </Text>
                </Pressable>
              ) : null}
            </>
          )}
        </View>

        <View style={styles.card} testID="principal-funcionario-card">
          <View style={styles.cardHeader}>
            <Ionicons name="briefcase-outline" size={18} color={colors.brandPrimary} />
            <Text style={styles.cardTitle}>Funcionário (funcionarioObj)</Text>
          </View>
          {funcionarioEntries.length === 0 ? (
            <Text style={styles.emptyHint}>
              Nenhum funcionário vinculado a este usuário (funcionarios.nome_guerra = {""}
              {(session.usuario?.usuario as string) || "?"}).
            </Text>
          ) : (
            <>
              {funcionarioShown.map(([k, v]) => (
                <View key={k} style={styles.kvRow}>
                  <Text style={styles.kvKey}>{k}</Text>
                  <Text style={styles.kvValue} numberOfLines={2}>
                    {formatValue(v)}
                  </Text>
                </View>
              ))}
              {funcionarioEntries.length > 6 ? (
                <Pressable
                  onPress={() => setShowAllFuncionario((v) => !v)}
                  style={({ pressed }) => [styles.toggle, pressed && styles.pressed]}
                  testID="principal-funcionario-toggle"
                >
                  <Text style={styles.toggleText}>
                    {showAllFuncionario
                      ? "Mostrar menos"
                      : `Mostrar mais (${funcionarioEntries.length - 6})`}
                  </Text>
                </Pressable>
              ) : null}
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.md,
    backgroundColor: colors.brandPrimary,
    gap: spacing.md,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: "500",
    color: colors.onBrandPrimary,
    letterSpacing: -0.3,
  },
  headerSub: {
    fontSize: 12,
    color: "rgba(255,255,255,0.75)",
    marginTop: 2,
  },
  logoutBtn: {
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
  logoutLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  pressed: { opacity: 0.7 },
  scroll: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
    paddingBottom: spacing.xxl,
  },
  hero: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  avatar: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  welcome: { fontSize: 13, color: colors.muted },
  heroName: {
    fontSize: 22,
    fontWeight: "500",
    color: colors.onSurface,
    letterSpacing: -0.3,
  },
  heroSub: { marginTop: 2, fontSize: 13, color: colors.onSurfaceTertiary },
  summary: {
    marginTop: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  summaryRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingVertical: 8,
    gap: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.divider,
  },
  summaryLabel: {
    fontSize: 12,
    color: colors.muted,
    width: 80,
  },
  summaryValue: {
    flex: 1,
    fontSize: 13,
    color: colors.onSurface,
    fontWeight: "500",
    textAlign: "right",
  },
  connRow: {
    marginTop: spacing.md,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.lg,
    paddingHorizontal: spacing.sm,
  },
  connItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  connText: { fontSize: 12, color: colors.muted, maxWidth: 250 },
  sectionTitle: {
    marginTop: spacing.xl,
    fontSize: 18,
    fontWeight: "500",
    color: colors.onSurface,
  },
  sectionSub: {
    marginTop: 4,
    fontSize: 13,
    color: colors.onSurfaceTertiary,
  },
  tilesGrid: {
    marginTop: spacing.md,
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.md,
  },
  tile: {
    flexBasis: "47%",
    flexGrow: 1,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  tileIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: spacing.sm,
  },
  tileLabel: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  tileHint: { fontSize: 11, color: colors.muted, marginTop: 2 },
  card: {
    marginTop: spacing.xl,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  cardTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  emptyHint: { fontSize: 13, color: colors.muted, lineHeight: 18 },
  kvRow: {
    flexDirection: "row",
    paddingVertical: 8,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: colors.divider,
  },
  kvKey: { width: 130, fontSize: 12, color: colors.muted, paddingRight: spacing.sm },
  kvValue: { flex: 1, fontSize: 13, color: colors.onSurface },
  toggle: {
    marginTop: spacing.md,
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
  },
  toggleText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "500" },
});
