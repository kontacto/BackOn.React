import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Modal,
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
import { useLocalSearchParams, useRouter } from "expo-router";
import { Image } from "expo-image";
import { Ionicons } from "@expo/vector-icons";

import {
  Connection,
  addConnection,
  deleteConnection,
  listConnections,
  updateConnection,
} from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";

const EMPTY_IMG =
  "https://images.unsplash.com/photo-1449247709967-d4461a6a6103?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NDQ2Mzl8MHwxfHNlYXJjaHwxfHxjbGVhbiUyMGVtcHR5JTIwZGVzayUyMG1pbmltYWxpc3R8ZW58MHx8fHwxNzgxMTE2MTU3fDA&ixlib=rb-4.1.0&q=85";

export default function ConnectionsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ initial?: string }>();
  const isInitial = params.initial === "1";

  const [items, setItems] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [editorVisible, setEditorVisible] = useState(false);
  const [editing, setEditing] = useState<Connection | null>(null);
  const [empresa, setEmpresa] = useState("");
  const [servidor, setServidor] = useState("");
  const [banco, setBanco] = useState("");
  const [api, setApi] = useState("");
  const [logo, setLogo] = useState("");
  const [imagensUrl, setImagensUrl] = useState("");
  const [permitirBiometria, setPermitirBiometria] = useState(false);
  const feedback = useFeedback();
  const [saving, setSaving] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Connection | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    const list = await listConnections();
    setItems(list);
    setLoading(false);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const openCreate = () => {
    setEditing(null);
    setEmpresa("");
    setServidor("");
    setBanco("");
    setApi("");
    setLogo("");
    setImagensUrl("");
    setPermitirBiometria(false);
    // (mensagens de erro agora via feedback global centralizado)
    setEditorVisible(true);
  };

  const openEdit = (c: Connection) => {
    setEditing(c);
    setEmpresa(c.empresa);
    setServidor(c.servidor);
    setBanco(c.banco ?? "");
    setApi(c.api ?? "");
    setLogo(c.logo ?? "");
    setImagensUrl(c.imagensUrl ?? "");
    setPermitirBiometria(c.permitirBiometria ?? false);
    // (mensagens de erro agora via feedback global centralizado)
    setEditorVisible(true);
  };

  const closeEditor = () => {
    setEditorVisible(false);
    setEditing(null);
    setEmpresa("");
    setServidor("");
    setBanco("");
    setApi("");
    setLogo("");
    setImagensUrl("");
    setPermitirBiometria(false);
    // (mensagens de erro agora via feedback global centralizado)
  };

  const handleSave = async () => {
    const e = empresa.trim();
    const s = servidor.trim();
    const b = banco.trim();
    const a = api.trim();
    if (!e) {
      feedback.showError("Informe o nome da Empresa.");
      return;
    }
    if (!s) {
      feedback.showError("Informe o Servidor.");
      return;
    }
    if (!b) {
      feedback.showError("Informe o Banco.");
      return;
    }
    if (!a) {
      feedback.showError("Informe o endereço da API.");
      return;
    }
    if (!/^https?:\/\//i.test(a)) {
      feedback.showError("A API deve começar com http:// ou https://");
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateConnection(editing.id, { empresa: e, servidor: s, banco: b, api: a, logo: logo.trim(), imagensUrl: imagensUrl.trim(), permitirBiometria });
      } else {
        await addConnection({ empresa: e, servidor: s, banco: b, api: a, logo: logo.trim(), imagensUrl: imagensUrl.trim(), permitirBiometria });
      }
      await reload();
      closeEditor();
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) return;
    await deleteConnection(confirmDelete.id);
    setConfirmDelete(null);
    await reload();
  };

  const handleBack = () => {
    if (items.length === 0) return;
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/login");
    }
  };

  const renderItem = ({ item }: { item: Connection }) => (
    <View style={styles.card} testID={`connection-card-${item.id}`}>
      <View style={styles.cardIcon}>
        <Ionicons name="server-outline" size={20} color={colors.brandPrimary} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.cardTitle} numberOfLines={1}>
          {item.empresa}
        </Text>
        <Text style={styles.cardSub} numberOfLines={1}>
          {item.servidor}
        </Text>
        <Text style={styles.cardSub} numberOfLines={1}>
          Banco: {item.banco || "—"}
        </Text>
        <Text style={styles.cardSub} numberOfLines={1}>
          API: {item.api || "—"}
        </Text>
      </View>
      <Pressable
        onPress={() => openEdit(item)}
        style={({ pressed }) => [styles.cardAction, pressed && styles.pressed]}
        hitSlop={8}
        testID={`connection-edit-${item.id}`}
      >
        <Ionicons name="create-outline" size={18} color={colors.onSurfaceTertiary} />
      </Pressable>
      <Pressable
        onPress={() => setConfirmDelete(item)}
        style={({ pressed }) => [styles.cardAction, pressed && styles.pressed]}
        hitSlop={8}
        testID={`connection-delete-${item.id}`}
      >
        <Ionicons name="trash-outline" size={18} color={colors.error} />
      </Pressable>
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="connections-screen">
      <View style={styles.header}>
        {isInitial && items.length === 0 ? (
          <View style={styles.iconBtn} />
        ) : (
          <Pressable
            onPress={handleBack}
            style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
            hitSlop={12}
            testID="connections-back-button"
          >
            <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
          </Pressable>
        )}
        <Text style={styles.headerTitle}>Conexões</Text>
        <View style={styles.iconBtn} />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : items.length === 0 ? (
        <ScrollView contentContainerStyle={styles.emptyWrap} testID="connections-empty-state">
          <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" />
          <Text style={styles.emptyTitle}>Nenhuma conexão configurada</Text>
          <Text style={styles.emptySub}>
            {isInitial
              ? "Para começar, cadastre a primeira conexão com sua empresa, servidor e banco."
              : "Adicione uma conexão para acessar seu servidor corporativo."}
          </Text>
        </ScrollView>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(c) => c.id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
          testID="connections-list"
        />
      )}

      <View style={styles.footer}>
        <Pressable
          onPress={openCreate}
          style={({ pressed }) => [styles.primaryBtn, pressed && styles.primaryBtnPressed]}
          testID="connections-new-button"
        >
          <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
          <Text style={styles.primaryBtnText}>Nova Conexão</Text>
        </Pressable>
      </View>

      <Modal
        visible={editorVisible}
        transparent
        animationType="slide"
        onRequestClose={closeEditor}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={{ flex: 1 }}
        >
          <Pressable style={styles.backdrop} onPress={closeEditor} />
          <View style={styles.sheet} testID="connection-editor-sheet">
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>
              {editing ? "Editar conexão" : "Nova conexão"}
            </Text>

          <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 560 }}>
            <View style={{ marginTop: spacing.md }}>
              <Text style={styles.label}>Empresa</Text>
              <TextInput
                value={empresa}
                onChangeText={setEmpresa}
                placeholder="Ex: Acme S/A"
                placeholderTextColor={colors.muted}
                autoCapitalize="words"
                style={styles.input}
                testID="connection-empresa-input"
              />
            </View>

            <View style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>Servidor (instância SQL Server)</Text>
              <TextInput
                value={servidor}
                onChangeText={setServidor}
                placeholder="Ex: 192.168.0.10 ou erp.acme.com\SQLEXPRESS"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
                testID="connection-servidor-input"
              />
            </View>

            <View style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>Banco</Text>
              <TextInput
                value={banco}
                onChangeText={setBanco}
                placeholder="Ex: KontactoDB"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
                testID="connection-banco-input"
              />
            </View>

            <View style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>API (endereço do backend)</Text>
              <TextInput
                value={api}
                onChangeText={setApi}
                placeholder="Ex: http://192.168.0.50:8001"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                style={styles.input}
                testID="connection-api-input"
              />
              <Text style={styles.helper}>
                URL do backend BackOn rodando na rede do cliente (sem o /api no final).
              </Text>
            </View>

            <View style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>Logo (URL — opcional)</Text>
              <TextInput
                value={logo}
                onChangeText={setLogo}
                placeholder="Ex: https://kontacto.com.br/logos/estela.png"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                style={styles.input}
                testID="connection-logo-input"
              />
              <Text style={styles.helper}>
                Link público da logo do cliente (PNG/JPG). Aparece na tela Principal.
              </Text>
            </View>

            <View style={{ marginTop: spacing.lg }}>
              <Text style={styles.label}>Imagens Produtos (URL opcional)</Text>
              <TextInput
                value={imagensUrl}
                onChangeText={setImagensUrl}
                placeholder="Ex: https://cdn.cliente.com/produtos"
                placeholderTextColor={colors.muted}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
                style={styles.input}
                testID="connection-imagens-input"
              />
              <Text style={styles.helper}>
                Local onde ficam as imagens dos produtos. O arquivo deve ter o nome do código do produto
                (ex: 1234.jpg ou 1234.png). Usado para exibir as fotos na lista de produtos.
              </Text>
            </View>

            <View style={styles.switchRow}>
              <View style={{ flex: 1, paddingRight: spacing.md }}>
                <Text style={styles.label}>Permitir Login por Biometria</Text>
                <Text style={styles.helper}>
                  Habilita entrar com digital/Face ID neste dispositivo após o primeiro login.
                </Text>
              </View>
              <Switch
                value={permitirBiometria}
                onValueChange={setPermitirBiometria}
                trackColor={{ false: colors.border, true: colors.brandPrimary }}
                testID="connection-biometria-switch"
              />
            </View>
          </ScrollView>

            <View style={styles.sheetActions}>
              <Pressable
                onPress={closeEditor}
                style={({ pressed }) => [styles.secondaryBtn, pressed && styles.pressed]}
                testID="connection-cancel-button"
              >
                <Text style={styles.secondaryBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable
                onPress={handleSave}
                disabled={saving}
                style={({ pressed }) => [
                  styles.primaryBtn,
                  { flex: 1 },
                  (pressed || saving) && styles.primaryBtnPressed,
                ]}
                testID="connection-save-button"
              >
                {saving ? (
                  <ActivityIndicator color={colors.onBrandPrimary} />
                ) : (
                  <Text style={styles.primaryBtnText}>Salvar</Text>
                )}
              </Pressable>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      <Modal
        visible={!!confirmDelete}
        transparent
        animationType="fade"
        onRequestClose={() => setConfirmDelete(null)}
      >
        <View style={styles.dialogBackdrop}>
          <View style={styles.dialog} testID="connection-delete-dialog">
            <Text style={styles.dialogTitle}>Excluir conexão?</Text>
            <Text style={styles.dialogText}>
              {confirmDelete
                ? `Tem certeza que deseja excluir "${confirmDelete.empresa}"?`
                : ""}
            </Text>
            <View style={styles.dialogActions}>
              <Pressable
                onPress={() => setConfirmDelete(null)}
                style={({ pressed }) => [styles.secondaryBtn, pressed && styles.pressed]}
                testID="connection-delete-cancel"
              >
                <Text style={styles.secondaryBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable
                onPress={handleDelete}
                style={({ pressed }) => [styles.dangerBtn, pressed && styles.pressed]}
                testID="connection-delete-confirm"
              >
                <Text style={styles.dangerBtnText}>Excluir</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  headerTitle: { fontSize: 17, fontWeight: "500", color: colors.onSurface },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: { opacity: 0.7 },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xxl,
    paddingBottom: spacing.xl,
  },
  emptyImg: {
    width: 220,
    height: 160,
    borderRadius: radius.lg,
    marginBottom: spacing.xl,
  },
  emptyTitle: {
    fontSize: 18,
    fontWeight: "500",
    color: colors.onSurface,
    textAlign: "center",
  },
  emptySub: {
    marginTop: spacing.sm,
    fontSize: 14,
    color: colors.onSurfaceTertiary,
    textAlign: "center",
    lineHeight: 20,
  },
  listContent: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: 100,
  },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
  },
  cardIcon: {
    width: 40,
    height: 40,
    borderRadius: radius.md,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.brandTertiary,
  },
  cardTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardAction: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: "center",
    justifyContent: "center",
  },
  footer: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.divider,
  },
  primaryBtn: {
    flexDirection: "row",
    gap: 6,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.md,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
  },
  primaryBtnPressed: { opacity: 0.85 },
  primaryBtnText: {
    color: colors.onBrandPrimary,
    fontWeight: "500",
    fontSize: 15,
  },
  secondaryBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
  },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "500", fontSize: 14 },
  dangerBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: radius.md,
    backgroundColor: colors.error,
    alignItems: "center",
    justifyContent: "center",
    minHeight: 50,
  },
  dangerBtnText: { color: colors.onError, fontWeight: "500", fontSize: 14 },
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: "rgba(0,0,0,0.4)" },
  sheet: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: colors.surfaceSecondary,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.md,
    paddingBottom: spacing.xxl,
  },
  sheetHandle: {
    alignSelf: "center",
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.borderStrong,
    marginBottom: spacing.md,
  },
  sheetTitle: { fontSize: 17, fontWeight: "500", color: colors.onSurface },
  label: {
    fontSize: 13,
    fontWeight: "500",
    color: colors.onSurfaceTertiary,
    marginBottom: spacing.sm,
  },
  input: {
    backgroundColor: colors.surface,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    fontSize: 15,
    color: colors.onSurface,
    minHeight: 48,
  },
  helper: { marginTop: 6, fontSize: 11, color: colors.muted },
  switchRow: {
    marginTop: spacing.lg,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  errorText: { marginTop: spacing.md, color: colors.error, fontSize: 13 },
  sheetActions: {
    flexDirection: "row",
    gap: spacing.sm,
    marginTop: spacing.xl,
  },
  dialogBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
  },
  dialog: {
    width: "100%",
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.xl,
  },
  dialogTitle: { fontSize: 17, fontWeight: "500", color: colors.onSurface },
  dialogText: {
    marginTop: spacing.sm,
    fontSize: 14,
    color: colors.onSurfaceTertiary,
    lineHeight: 20,
  },
  dialogActions: { marginTop: spacing.xl, flexDirection: "row", gap: spacing.sm },
});
