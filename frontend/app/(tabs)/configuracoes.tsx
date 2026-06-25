import { useCallback, useState } from "react";
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { Session, clearSession, getSession } from "@/src/utils/storage/session";
import { colors, radius, spacing } from "@/src/theme/colors";

function pickFirst(obj: Record<string, unknown> | undefined | null, keys: string[]): string | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") return String(v);
  }
  return null;
}

export default function ConfiguracoesScreen() {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);

  useFocusEffect(
    useCallback(() => {
      (async () => setSession(await getSession()))();
    }, [])
  );

  const displayName =
    pickFirst(session?.funcionario, ["nome", "nome_guerra"]) ||
    String((session?.usuario as Record<string, unknown> | null)?.usuario ?? "") ||
    "Usuário";

  // Acesso ao módulo de Permissões: usuário master (KONTACTO) ou funcionário com
  // cod_funcao 01/02 (sócio/gerente).
  const usuarioObj = (session?.usuario ?? {}) as Record<string, unknown>;
  const isKontacto =
    usuarioObj?.master === true ||
    String(usuarioObj?.usuario ?? "").toUpperCase() === "KONTACTO";
  const canManagePermissoes = (() => {
    if (isKontacto) return true;
    const cf = parseInt(
      String((session?.funcionario as Record<string, unknown> | null)?.cod_funcao ?? ""),
      10
    );
    return cf === 1 || cf === 2;
  })();

  const handleLogout = async () => {
    await clearSession();
    router.replace("/login");
  };

  const Item = ({
    icon,
    label,
    hint,
    onPress,
    danger,
    testID,
  }: {
    icon: keyof typeof Ionicons.glyphMap;
    label: string;
    hint?: string;
    onPress: () => void;
    danger?: boolean;
    testID?: string;
  }) => (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [styles.item, pressed && { backgroundColor: colors.brandTertiary }]}
      testID={testID}
    >
      <View style={[styles.itemIcon, danger && { backgroundColor: "#FDE7E7" }]}>
        <Ionicons name={icon} size={20} color={danger ? colors.error : colors.brandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={[styles.itemLabel, danger && { color: colors.error }]}>{label}</Text>
        {hint ? <Text style={styles.itemHint}>{hint}</Text> : null}
      </View>
      <Ionicons name="chevron-forward" size={18} color={colors.muted} />
    </Pressable>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="configuracoes-screen">
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Configurações</Text>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Perfil */}
        <View style={styles.profile} testID="config-profile">
          {session?.logo ? (
            <Image source={{ uri: session.logo }} style={styles.avatar} resizeMode="cover" />
          ) : (
            <View style={styles.avatar}>
              <Ionicons name="person" size={28} color={colors.onBrandPrimary} />
            </View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={styles.profileName} numberOfLines={1}>
              {displayName}
            </Text>
            {session?.empresa ? (
              <Text style={styles.profileSub} numberOfLines={1}>
                {session.empresa}
              </Text>
            ) : null}
          </View>
        </View>

        <Text style={styles.sectionTitle}>Geral</Text>
        <View style={styles.group}>
          <Item
            icon="server-outline"
            label="Conexões"
            hint="Gerenciar empresas e bancos"
            onPress={() => router.push("/connections")}
            testID="config-conexoes"
          />
        </View>

        {canManagePermissoes ? (
          <>
            <Text style={styles.sectionTitle}>Administração</Text>
            <View style={styles.group}>
              <Item
                icon="shield-checkmark-outline"
                label="Permissões"
                hint="Definir acessos por grupo de usuário"
                onPress={() => router.push("/permissoes")}
                testID="config-permissoes"
              />
              {isKontacto ? (
                <Item
                  icon="cube-outline"
                  label="Módulos e Recursos"
                  hint="Liberar módulos do sistema para a empresa"
                  onPress={() => router.push("/modulos-recursos")}
                  testID="config-modulos"
                />
              ) : null}
            </View>
          </>
        ) : null}

        <Text style={styles.sectionTitle}>Conta</Text>
        <View style={styles.group}>
          <Item
            icon="log-out-outline"
            label="Sair"
            hint="Encerrar a sessão atual"
            onPress={handleLogout}
            danger
            testID="config-logout"
          />
        </View>

        <Text style={styles.version}>Back-On · v1.0</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    alignItems: "center",
  },
  headerTitle: { color: colors.onBrandPrimary, fontSize: 17, fontWeight: "600" },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  profile: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    backgroundColor: colors.brandPrimary,
    alignItems: "center",
    justifyContent: "center",
  },
  profileName: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  profileSub: { fontSize: 13, color: colors.muted, marginTop: 2 },
  sectionTitle: {
    fontSize: 12,
    fontWeight: "600",
    color: colors.muted,
    textTransform: "uppercase",
    letterSpacing: 0.4,
    marginTop: spacing.md,
    marginBottom: spacing.xs,
  },
  group: { backgroundColor: colors.surface, borderRadius: radius.md, overflow: "hidden" },
  item: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  itemIcon: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: colors.brandTertiary,
    alignItems: "center",
    justifyContent: "center",
  },
  itemLabel: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  itemHint: { fontSize: 12, color: colors.muted, marginTop: 1 },
  version: { textAlign: "center", color: colors.muted, fontSize: 12, marginTop: spacing.lg },
});
