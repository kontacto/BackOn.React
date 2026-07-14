import { useCallback, useState } from "react";
import { Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { Session, clearSession, getSession } from "@/src/utils/storage/session";
import { colors, radius, spacing } from "@/src/theme/colors";
import { secureStorageService } from "@/src/services/SecureStorageService";
import { connId } from "@/src/services/types";
import { usePermissions } from "@/src/permissions";

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
  const isWeb = Platform.OS === "web";
  const { can, isMaster } = usePermissions();
  const [session, setSession] = useState<Session | null>(null);
  const [hasBio, setHasBio] = useState(false);

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const s = await getSession();
        setSession(s);
        if (s?.empresa && s?.database) {
          setHasBio(await secureStorageService.hasCredentials(connId(s.empresa, s.database)));
        } else {
          setHasBio(false);
        }
      })();
    }, [])
  );

  const handleDisableBio = () => {
    Alert.alert(
      "Desativar biometria",
      "Deseja remover o login por biometria deste dispositivo?",
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Desativar",
          style: "destructive",
          onPress: async () => {
            if (session?.empresa && session?.database) {
              await secureStorageService.deleteCredentials(
                connId(session.empresa, session.database)
              );
            }
            setHasBio(false);
          },
        },
      ]
    );
  };

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
        <Image source={require("../../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Configurações</Text>
        <View style={styles.headerLogoSpacer} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, Platform.OS === "web" && styles.scrollWeb]}>
        <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
          <View style={Platform.OS === "web" ? styles.webShell : undefined}>
          {/* Perfil */}
          <View style={[styles.profile, Platform.OS === "web" && styles.profileWeb]} testID="config-profile">
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

          <View style={Platform.OS === "web" ? styles.gridWeb : undefined}>
            <View style={Platform.OS === "web" ? styles.columnWeb : undefined}>
              <Text style={styles.sectionTitle}>Geral</Text>
              <View style={[styles.group, Platform.OS === "web" && styles.groupWeb]}>
                <Item
                  icon="server-outline"
                  label="Conexões"
                  hint="Gerenciar empresas e bancos"
                  onPress={() => router.push("/connections")}
                  testID="config-conexoes"
                />
                {isWeb && (can("CTRL_SISTEMA.ABRIR") || isMaster) ? (
                  <Item
                    icon="options-outline"
                    label="Controle do Sistema"
                    hint="Configurações gerais da empresa (fiscal, financeiro, movimentação)"
                    onPress={() => router.push("/controle-sistema")}
                    testID="config-controle-sistema"
                  />
                ) : null}
              </View>

              {hasBio ? (
                <>
                  <Text style={styles.sectionTitle}>Segurança</Text>
                  <View style={[styles.group, Platform.OS === "web" && styles.groupWeb]}>
                    <Item
                      icon="finger-print-outline"
                      label="Desativar Login por Biometria"
                      hint="Remover digital/Face ID deste dispositivo"
                      onPress={handleDisableBio}
                      testID="config-disable-biometria"
                    />
                  </View>
                </>
              ) : null}
            </View>

            {canManagePermissoes ? (
              <View style={Platform.OS === "web" ? styles.columnWeb : undefined}>
                {isWeb && isKontacto ? (
                  <>
                    <Text style={styles.sectionTitle}>Administração</Text>
                    <View style={[styles.group, Platform.OS === "web" && styles.groupWeb]}>
                      <Item
                        icon="cube-outline"
                        label="Módulos e Recursos"
                        hint="Liberar módulos do sistema para a empresa"
                        onPress={() => router.push("/modulos-recursos")}
                        testID="config-modulos"
                      />
                      <Item
                        icon="logo-whatsapp"
                        label="WhatsApp"
                        hint="Configurar envio de Pedidos e OS por WhatsApp"
                        onPress={() => router.push("/whatsapp-config")}
                        testID="config-whatsapp"
                      />
                    </View>
                  </>
                ) : null}

                <Text style={styles.sectionTitle}>Conta</Text>
                <View style={[styles.group, Platform.OS === "web" && styles.groupWeb]}>
                  {isWeb ? (
                    <Item
                      icon="document-text-outline"
                      label="Log de Auditoria"
                      hint="Histórico de alterações do sistema"
                      onPress={() => router.push("/log-auditoria")}
                      testID="config-log-auditoria"
                    />
                  ) : null}
                  {isWeb ? (
                    <Item
                      icon="person-circle-outline"
                      label="Perfil do Usuário"
                      hint="Cadastro e manutenção de usuários"
                      onPress={() => router.push("/perfil-usuario")}
                      testID="config-perfil-usuario"
                    />
                  ) : null}
                  {isWeb ? (
                    <Item
                      icon="shield-checkmark-outline"
                      label="Permissões"
                      hint="Definir acessos por grupo de usuário"
                      onPress={() => router.push("/permissoes")}
                      testID="config-permissoes"
                    />
                  ) : null}
                  <Item
                    icon="log-out-outline"
                    label="Sair"
                    hint="Encerrar a sessão atual"
                    onPress={handleLogout}
                    danger
                    testID="config-logout"
                  />
                </View>
              </View>
            ) : (
              <View style={Platform.OS === "web" ? styles.columnWeb : undefined}>
                <Text style={styles.sectionTitle}>Conta</Text>
                <View style={[styles.group, Platform.OS === "web" && styles.groupWeb]}>
                  <Item
                    icon="log-out-outline"
                    label="Sair"
                    hint="Encerrar a sessão atual"
                    onPress={handleLogout}
                    danger
                    testID="config-logout"
                  />
                </View>
              </View>
            )}
          </View>

          <Text style={styles.version}>Back-On · v1.0</Text>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  headerLogo: { width: 72, height: 20 },
  headerLogoSpacer: { width: 72, height: 20 },
  headerTitle: { flex: 1, textAlign: "center", color: colors.onBrandPrimary, fontSize: 17, fontWeight: "600" },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  scrollWeb: { alignItems: "center", paddingHorizontal: spacing.xl, paddingVertical: spacing.xl },
  webFrame: { width: "100%", maxWidth: 1240 },
  webShell: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    padding: spacing.xl,
  },
  profile: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  profileWeb: { borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md },
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
  groupWeb: { borderWidth: 1, borderColor: colors.border, boxShadow: "0 4px 14px rgba(0,0,0,0.06)" },
  gridWeb: { flexDirection: "row", gap: spacing.xl, alignItems: "flex-start" },
  columnWeb: { flex: 1, minWidth: 0 },
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
