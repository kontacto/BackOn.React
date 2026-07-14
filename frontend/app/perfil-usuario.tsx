import { useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { Connection, listConnections } from "@/src/utils/storage/connections";
import { getSession } from "@/src/utils/storage/session";
import { apiGet, apiSend } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Classe = { codigo: number; classe: string };
type UsuarioListItem = { usuario: string; nome_funcionario: string };

export default function PerfilUsuarioScreen() {
  const router = useRouter();
  const fb = useFeedback();
  const { isManagerFuncao, can } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponivel somente na versao web"
        message="Perfil do Usuario esta disponivel apenas no web."
        testID="perfil-usuario-web-only"
      />
    );
  }

  // Regra de negócio: consultar/editar o perfil de OUTROS usuários (e trocar o
  // grupo de qualquer um, inclusive o próprio) é restrito a Gerente/Supervisor
  // (funcionarios.cod_funcao 01/02), master, ou quem tiver a permissão
  // PERFIL_USUARIO.GRAVAR liberada. Fora isso, a tela carrega travada no
  // próprio usuário logado — que ainda assim pode trocar a própria senha
  // livremente, só não o grupo.
  const canManageOthers = isManagerFuncao || can("PERFIL_USUARIO.GRAVAR");

  const [conn, setConn] = useState<Connection | null>(null);
  const [classes, setClasses] = useState<Classe[]>([]);
  const [usuariosList, setUsuariosList] = useState<UsuarioListItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [usuario, setUsuario] = useState("");
  const [meuLogin, setMeuLogin] = useState("");
  const [nomeFuncionario, setNomeFuncionario] = useState("");
  const [classe, setClasse] = useState<number | null>(null);
  const [administrador, setAdministrador] = useState(false);
  const [exists, setExists] = useState(false);

  const [senhaAtual, setSenhaAtual] = useState("");
  const [novaSenha, setNovaSenha] = useState("");
  const [confirmacaoSenha, setConfirmacaoSenha] = useState("");

  const classeOptions: SelectOption[] = useMemo(
    () => classes.map((c) => ({ value: c.codigo, label: c.classe })),
    [classes]
  );

  const usuarioOptions: SelectOption[] = useMemo(
    () =>
      usuariosList.map((u) => ({
        value: u.usuario,
        label: u.nome_funcionario ? `${u.usuario} - ${u.nome_funcionario}` : u.usuario,
      })),
    [usuariosList]
  );

  const resetPasswords = () => {
    setSenhaAtual("");
    setNovaSenha("");
    setConfirmacaoSenha("");
  };

  // Regra de negócio (2026-07-07): a senha atual só é exigida no
  // autoatendimento (usuário trocando a própria senha). Gerente/Supervisor
  // (funcionarios.cod_funcao 01/02) ou master trocando a senha de OUTRO
  // usuário não precisa informar a senha atual — o servidor faz a mesma
  // checagem de forma independente (nunca confia só nisto vindo do cliente).
  const dispensaSenhaAtual = isManagerFuncao && usuario.trim().toUpperCase() !== meuLogin;

  const fetchPerfil = useCallback(
    async (c: Connection, usu: string) => {
      setLoading(true);
      try {
        const j = await apiGet(c, "/api/usuarios/perfil", { usuario: usu });
        if (!j?.success) {
          fb.showError(j?.message || "Falha ao consultar usuario.");
          return;
        }

        const funcNome = String(j?.funcionario?.nome || "").trim();
        setNomeFuncionario(funcNome);

        const userObj = j?.usuario || null;
        if (j?.exists && userObj) {
          setExists(true);
          setClasse(typeof userObj.classe === "number" ? userObj.classe : Number(userObj.classe || 0));
          setAdministrador(Boolean(userObj.administrador));
        } else {
          setExists(false);
          setClasse(null);
          setAdministrador(false);
        }
        resetPasswords();

        if (!funcNome) {
          fb.showWarning("Funcionario nao cadastrado para este usuario.");
        }
      } catch (e) {
        fb.showError(`Falha ao consultar usuario: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setLoading(false);
      }
    },
    [fb]
  );

  const boot = useCallback(async () => {
    setLoading(true);
    try {
      const session = await getSession();
      if (!session) {
        router.replace("/login");
        return;
      }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === session.empresa) ?? null;
      setConn(c);
      if (!c) {
        fb.showError("Conexao nao encontrada.");
        return;
      }

      const cls = await apiGet(c, "/api/permissoes/classes");
      if (cls?.success) setClasses(cls.items || []);
      else fb.showError(cls?.message || "Falha ao carregar grupos de usuario.");

      const login = String(
        (session.usuario as Record<string, unknown> | null)?.usuario ?? ""
      ).toUpperCase();
      setMeuLogin(login);

      if (canManageOthers) {
        const lst = await apiGet(c, "/api/usuarios/perfil/lista");
        if (lst?.success) setUsuariosList(lst.items || []);
        else fb.showError(lst?.message || "Falha ao carregar lista de usuarios.");
      } else if (login) {
        // Regra de negócio: sem permissão de gerenciar outros, a tela já carrega
        // travada no próprio usuário logado — sem busca, sem escolher outro.
        setUsuario(login);
        await fetchPerfil(c, login);
      }
    } catch (e) {
      fb.showError(`Falha ao carregar tela: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [fb, router, canManageOthers, fetchPerfil]);

  useFocusEffect(
    useCallback(() => {
      boot();
    }, [boot])
  );

  const consultar = async () => {
    if (!conn) return;
    const usu = usuario.trim().toUpperCase();
    setUsuario(usu);
    if (!usu) {
      fb.showWarning("Informe o usuario.");
      return;
    }
    await fetchPerfil(conn, usu);
  };

  const selecionarUsuario = async (usu: string) => {
    if (!conn) return;
    setUsuario(usu);
    await fetchPerfil(conn, usu);
  };

  const incluir = async () => {
    if (!conn) return;
    const usu = usuario.trim().toUpperCase();
    if (!usu) {
      fb.showWarning("Informe o usuario.");
      return;
    }
    if (!classe) {
      fb.showWarning("Selecione o grupo.");
      return;
    }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/usuarios/perfil/incluir", "POST", {
        usuario: usu,
        classe,
        senha: senhaAtual,
        confirmacao_senha: confirmacaoSenha,
        administrador,
        usuario_alteracao: auditCtx.usuario_alteracao,
        plataforma: auditCtx.plataforma,
      });
      if (j?.success) {
        fb.showSuccess(j?.message || "Usuario incluido.");
        await consultar();
      } else {
        fb.showError(j?.message || "Falha ao incluir usuario.");
      }
    } catch (e) {
      fb.showError(`Falha ao incluir usuario: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const alterar = async () => {
    if (!conn) return;
    const usu = usuario.trim().toUpperCase();
    if (!usu) {
      fb.showWarning("Informe o usuario.");
      return;
    }
    if (!classe) {
      fb.showWarning("Selecione o grupo.");
      return;
    }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/usuarios/perfil/alterar", "POST", {
        usuario: usu,
        classe,
        senha_atual: senhaAtual || null,
        nova_senha: novaSenha || null,
        confirmacao_senha: confirmacaoSenha || null,
        administrador,
        usuario_alteracao: auditCtx.usuario_alteracao,
        plataforma: auditCtx.plataforma,
        usuario_logado: meuLogin || null,
      });
      if (j?.success) {
        fb.showSuccess(j?.message || "Usuario alterado.");
        await consultar();
      } else {
        fb.showError(j?.message || "Falha ao alterar usuario.");
      }
    } catch (e) {
      fb.showError(`Falha ao alterar usuario: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const excluir = () => {
    if (!conn) return;
    const usu = usuario.trim().toUpperCase();
    if (!usu) {
      fb.showWarning("Informe o usuario.");
      return;
    }
    Alert.alert(
      "Excluir usuario",
      `Confirma a exclusao do usuario ${usu}?`,
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Excluir",
          style: "destructive",
          onPress: async () => {
            setSaving(true);
            try {
              const j = await apiSend(conn, `/api/usuarios/perfil/${encodeURIComponent(usu)}/excluir`, "POST", {});
              if (j?.success) {
                fb.showSuccess(j?.message || "Usuario excluido.");
                setExists(false);
                setNomeFuncionario("");
                setClasse(null);
                setAdministrador(false);
                resetPasswords();
                setUsuario("");
              } else {
                fb.showError(j?.message || "Falha ao excluir usuario.");
              }
            } catch (e) {
              fb.showError(`Falha ao excluir usuario: ${e instanceof Error ? e.message : String(e)}`);
            } finally {
              setSaving(false);
            }
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="perfil-usuario-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.logo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Perfil do Usuario</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={[styles.formCard, styles.formCardWeb]}>
            {canManageOthers ? (
              <SelectField
                label="Usuario *"
                value={usuario || null}
                onChange={(v) => v != null && selecionarUsuario(String(v))}
                options={usuarioOptions}
                placeholder="Selecione ou busque um usuario"
                compactWeb
                testID="perfil-usuario-login"
              />
            ) : (
              <>
                <Text style={styles.label}>Usuario</Text>
                <TextInput
                  value={usuario}
                  editable={false}
                  style={[styles.input, styles.inputDisabled]}
                  testID="perfil-usuario-login"
                />
                <Text style={styles.note}>Voce esta vendo seu proprio perfil. Trocar de grupo exige permissao de Gerente/Supervisor.</Text>
              </>
            )}

            <Text style={styles.label}>Nome (Funcionario)</Text>
            <TextInput
              value={nomeFuncionario}
              editable={false}
              placeholder="Funcionario sera localizado pelo usuario informado"
              placeholderTextColor={colors.muted}
              style={[styles.input, styles.inputDisabled]}
              testID="perfil-usuario-nome-funcionario"
            />

            <SelectField
              label="Grupo *"
              value={classe}
              onChange={(v) => setClasse(v == null ? null : Number(v))}
              options={classeOptions}
              placeholder="Selecione o grupo"
              compactWeb
              disabled={!canManageOthers}
              testID="perfil-usuario-grupo"
            />

            {canManageOthers ? (
              <View style={styles.switchRow}>
                <Text style={styles.switchLabel}>Administrador</Text>
                <Switch value={administrador} onValueChange={setAdministrador} testID="perfil-usuario-admin-switch" />
              </View>
            ) : null}

            {exists ? (
              <>
                <Text style={styles.subTitle}>Alteracao de Senha (opcional)</Text>
                {dispensaSenhaAtual ? (
                  <Text style={styles.note}>
                    Como Gerente/Supervisor (ou master), voce pode definir uma nova senha para este
                    usuario sem informar a senha atual dele.
                  </Text>
                ) : (
                  <>
                    <Text style={styles.label}>Senha Atual</Text>
                    <TextInput
                      value={senhaAtual}
                      onChangeText={setSenhaAtual}
                      placeholder="Senha atual"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      secureTextEntry
                      maxLength={10}
                      testID="perfil-usuario-senha-atual"
                    />
                  </>
                )}
                <View style={styles.rowInline2}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Nova Senha</Text>
                    <TextInput
                      value={novaSenha}
                      onChangeText={setNovaSenha}
                      placeholder="Nova senha"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      secureTextEntry
                      maxLength={10}
                      testID="perfil-usuario-nova-senha"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Confirma Senha</Text>
                    <TextInput
                      value={confirmacaoSenha}
                      onChangeText={setConfirmacaoSenha}
                      placeholder="Confirme"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      secureTextEntry
                      maxLength={10}
                      testID="perfil-usuario-confirma-senha"
                    />
                  </View>
                </View>
              </>
            ) : (
              <>
                <Text style={styles.subTitle}>Inclusao de Usuario</Text>
                <View style={styles.rowInline2}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Senha *</Text>
                    <TextInput
                      value={senhaAtual}
                      onChangeText={setSenhaAtual}
                      placeholder="Senha"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      secureTextEntry
                      maxLength={10}
                      testID="perfil-usuario-senha"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.label}>Confirma Senha *</Text>
                    <TextInput
                      value={confirmacaoSenha}
                      onChangeText={setConfirmacaoSenha}
                      placeholder="Confirme"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      secureTextEntry
                      maxLength={10}
                      testID="perfil-usuario-confirma"
                    />
                  </View>
                </View>
              </>
            )}

            {canManageOthers ? (
              <Text style={styles.note}>Regra: um usuario so pode ser incluido se ja existir funcionario com o mesmo nome de guerra.</Text>
            ) : null}

            <View style={styles.actions}>
              {canManageOthers ? (
                <Pressable
                  onPress={incluir}
                  disabled={saving}
                  style={[styles.actionBtn, styles.actionPrimary, saving && { opacity: 0.7 }]}
                  testID="perfil-usuario-incluir"
                >
                  <Text style={styles.actionPrimaryText}>Inclui</Text>
                </Pressable>
              ) : null}
              <Pressable
                onPress={alterar}
                disabled={saving || !exists}
                style={[styles.actionBtn, styles.actionNeutral, (saving || !exists) && { opacity: 0.55 }]}
                testID="perfil-usuario-alterar"
              >
                <Text style={styles.actionNeutralText}>Altera</Text>
              </Pressable>
              {canManageOthers ? (
                <Pressable
                  onPress={excluir}
                  disabled={saving || !exists}
                  style={[styles.actionBtn, styles.actionDanger, (saving || !exists) && { opacity: 0.55 }]}
                  testID="perfil-usuario-excluir"
                >
                  <Text style={styles.actionDangerText}>Exclui</Text>
                </Pressable>
              ) : null}
            </View>
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
    backgroundColor: colors.brandPrimary,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  logo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  formCard: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  formCardWeb: WEB_FILTER_CARD,
  rowInline2: { flexDirection: "row", alignItems: "flex-start", gap: spacing.md },
  label: {
    fontSize: 12,
    color: colors.muted,
    marginBottom: 4,
    fontWeight: "500",
    textTransform: "uppercase",
    letterSpacing: 0.4,
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 11,
    fontSize: 14,
    color: colors.onSurface,
  },
  inputDisabled: {
    backgroundColor: colors.surfaceSecondary,
    color: colors.muted,
  },
  switchRow: {
    marginTop: spacing.xs,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: spacing.sm,
  },
  switchLabel: { color: colors.onSurface, fontSize: 14, fontWeight: "500" },
  subTitle: {
    marginTop: spacing.sm,
    fontSize: 13,
    fontWeight: "700",
    color: colors.brandPrimary,
    textTransform: "uppercase",
  },
  note: {
    marginTop: spacing.sm,
    color: colors.muted,
    fontSize: 12,
    lineHeight: 17,
  },
  actions: {
    marginTop: spacing.md,
    flexDirection: "row",
    gap: spacing.sm,
  },
  actionBtn: {
    flex: 1,
    borderRadius: radius.md,
    paddingVertical: 12,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
  },
  actionPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  actionNeutral: { backgroundColor: colors.surface, borderColor: colors.border },
  actionDanger: { backgroundColor: "#fff1f1", borderColor: "#f4b6b6" },
  actionPrimaryText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  actionNeutralText: { color: colors.onSurface, fontWeight: "700", fontSize: 14 },
  actionDangerText: { color: colors.error, fontWeight: "700", fontSize: 14 },
});
