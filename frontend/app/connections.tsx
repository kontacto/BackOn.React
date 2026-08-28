import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
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
import { Ionicons } from "@/src/components/Ionicons";

import {
  Connection,
  addConnection,
  deleteConnection,
  listConnections,
  updateConnection,
} from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { AppImage } from "@/src/components/AppImage";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";

// Modo Didático — pedido explícito do usuário, 2026-08-27 ("modo
// educativo"), na PRIMEIRA tela que qualquer instalação nova mostra
// (antes até do login) — quem preenche isso pela 1ª vez pode nunca ter
// mexido no sistema, então os termos técnicos (Servidor, Banco, API)
// merecem explicação em linguagem simples, não só o placeholder de
// exemplo já existente em cada campo.
const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que é uma Conexão?", texto: "É o \"endereço\" completo de uma empresa/loja: onde fica o banco de dados dela e onde está rodando o sistema (Backend). Cada Conexão é uma empresa diferente — numa mesma máquina você pode ter várias, e escolher qual usar a cada login.", icon: { lib: "ion", name: "link-outline" } },
  { titulo: "Empresa", texto: "Só um nome/apelido pra você reconhecer essa Conexão na lista (ex.: o nome da loja). Não afeta nada tecnicamente.", icon: { lib: "ion", name: "business-outline" } },
  { titulo: "Servidor", texto: "O endereço do SQL Server onde o banco de dados dessa empresa está instalado — o mesmo servidor que o sistema antigo (VB6) já usa nessa máquina. Pode ser um IP (192.168.0.10) ou um nome de instância (NOMEDAMAQUINA\\SQLEXPRESS).", icon: { lib: "ion", name: "server-outline" } },
  { titulo: "Banco", texto: "O nome do banco de dados dessa empresa dentro do SQL Server (ex.: KontactoDB). Se você não souber esse nome, quem instalou/restaurou o banco no cliente sabe.", icon: { lib: "ion", name: "file-tray-stacked-outline" } },
  { titulo: "API", texto: "O endereço onde o Backend (o \"motor\" do sistema) está rodando. Numa instalação normal, é sempre http://localhost:8081 se você estiver usando o navegador na MESMA máquina onde o Backend foi instalado.", icon: { lib: "ion", name: "hardware-chip-outline" } },
  { titulo: "Logo e Imagens (opcionais)", texto: "Só afetam a aparência do sistema (logo do cliente na tela Principal, fotos de produtos) — pode deixar em branco e preencher depois, sem travar o uso do sistema.", icon: { lib: "ion", name: "image-outline" } },
];


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
  const [ajudaOpen, setAjudaOpen] = useState(false);

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

  const handleCopy = async (item: Connection) => {
    await addConnection({
      empresa: `${item.empresa} (cópia)`,
      servidor: item.servidor,
      banco: item.banco,
      api: item.api,
      logo: item.logo,
      imagensUrl: item.imagensUrl,
      permitirBiometria: item.permitirBiometria,
    });
    await reload();
    feedback.showSuccess(`Conexão "${item.empresa}" copiada.`);
  };

  const handleBack = () => {
    if (items.length === 0) return;
    if (router.canGoBack()) {
      router.back();
    } else {
      router.replace("/login");
    }
  };

  // Tooltip dos botões que são só ícone (sem texto ao lado) — hover no web,
  // um só de cada vez. Mesmo padrão de PainelPedidoCard.tsx (`hoverBtn` +
  // `renderTooltip`), regra [GLOBAL] em CLAUDE.md > "Padrões de UI".
  const [hoverBtn, setHoverBtn] = useState<string | null>(null);
  // `below`: o botão de voltar fica colado no topo da tela — um tooltip
  // "acima" do ícone ficaria fora da viewport, invisível.
  const renderTooltip = (key: string, label: string, below = false) =>
    hoverBtn === key ? (
      <View style={[styles.tooltip, below && styles.tooltipBelow]} pointerEvents="none">
        <View style={styles.tooltipInner}>
          <Text style={styles.tooltipText}>{label}</Text>
        </View>
      </View>
    ) : null;

  const renderItem = ({ item }: { item: Connection }) => (
    <View style={[styles.card, Platform.OS === "web" && styles.cardWeb]} testID={`connection-card-${item.id}`}>
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
      <View style={[styles.cardActionWrap, hoverBtn === `edit-${item.id}` && styles.wrapHovered]}>
        <Pressable
          onPress={() => openEdit(item)}
          onHoverIn={() => setHoverBtn(`edit-${item.id}`)}
          onHoverOut={() => setHoverBtn(null)}
          style={({ pressed }) => [styles.cardAction, pressed && styles.pressed]}
          hitSlop={8}
          testID={`connection-edit-${item.id}`}
        >
          <Ionicons name="create-outline" size={18} color={colors.onSurfaceTertiary} />
        </Pressable>
        {renderTooltip(`edit-${item.id}`, "Editar conexão")}
      </View>
      <View style={[styles.cardActionWrap, hoverBtn === `copy-${item.id}` && styles.wrapHovered]}>
        <Pressable
          onPress={() => handleCopy(item)}
          onHoverIn={() => setHoverBtn(`copy-${item.id}`)}
          onHoverOut={() => setHoverBtn(null)}
          style={({ pressed }) => [styles.cardAction, pressed && styles.pressed]}
          hitSlop={8}
          testID={`connection-copy-${item.id}`}
        >
          <Ionicons name="copy-outline" size={18} color={colors.onSurfaceTertiary} />
        </Pressable>
        {renderTooltip(`copy-${item.id}`, "Copiar conexão")}
      </View>
      <View style={[styles.cardActionWrap, hoverBtn === `delete-${item.id}` && styles.wrapHovered]}>
        <Pressable
          onPress={() => setConfirmDelete(item)}
          onHoverIn={() => setHoverBtn(`delete-${item.id}`)}
          onHoverOut={() => setHoverBtn(null)}
          style={({ pressed }) => [styles.cardAction, pressed && styles.pressed]}
          hitSlop={8}
          testID={`connection-delete-${item.id}`}
        >
          <Ionicons name="trash-outline" size={18} color={colors.error} />
        </Pressable>
        {renderTooltip(`delete-${item.id}`, "Excluir conexão")}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="connections-screen">
      <View style={styles.header}>
        <View style={styles.headerSide}>
          {isInitial && items.length === 0 ? (
            <View style={styles.iconBtn} />
          ) : (
            <View style={[styles.cardActionWrap, hoverBtn === "back" && styles.wrapHovered]}>
              <Pressable
                onPress={handleBack}
                onHoverIn={() => setHoverBtn("back")}
                onHoverOut={() => setHoverBtn(null)}
                style={({ pressed }) => [styles.iconBtn, pressed && styles.pressed]}
                hitSlop={12}
                testID="connections-back-button"
              >
                <Ionicons name="chevron-back" size={22} color={colors.onSurface} />
              </Pressable>
              {renderTooltip("back", "Voltar", true)}
            </View>
          )}
          <AppImage source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} contentFit="contain" />
        </View>
        <Text style={styles.headerTitle}>Conexões</Text>
        <View style={[styles.headerSide, { justifyContent: "flex-end" }]}>
          {Platform.OS === "web" && !loading && items.length > 0 ? (
            <Pressable
              onPress={openCreate}
              style={({ pressed }) => [styles.headerNewBtn, pressed && styles.primaryBtnPressed]}
              testID="connections-new-button-top"
            >
              <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
              <Text style={styles.headerNewBtnText}>Nova Conexão</Text>
            </Pressable>
          ) : null}
          <IconButtonWithTooltip
            icon="information-circle-outline"
            label="Ajuda"
            onPress={() => setAjudaOpen(true)}
            color={colors.onSurface}
            style={{ marginLeft: spacing.sm }}
            testID="connections-ajuda-btn"
          />
        </View>
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      ) : items.length === 0 ? (
        <ScrollView contentContainerStyle={[styles.emptyWrap, Platform.OS === "web" && styles.emptyWrapWeb]} testID="connections-empty-state">
          <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
            <View style={[styles.webEmptyCard, Platform.OS === "web" && styles.webCardShadow]}>
            <AppImage source={require("../assets/images/kontacto-icon.png")} style={styles.emptyImg} contentFit="contain" />
            <Text style={styles.emptyTitle}>Nenhuma conexão configurada</Text>
            <Text style={styles.emptySub}>
              {isInitial
                ? "Para começar, cadastre a primeira conexão com sua empresa, servidor e banco."
                : "Adicione uma conexão para acessar seu servidor corporativo."}
            </Text>
            <Pressable
              onPress={openCreate}
              style={({ pressed }) => [styles.primaryBtn, Platform.OS === "web" && styles.primaryBtnWeb, styles.emptyCtaWeb, pressed && styles.primaryBtnPressed]}
              testID="connections-new-button-inline"
            >
              <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
              <Text style={styles.primaryBtnText}>Nova Conexão</Text>
            </Pressable>
            </View>
          </View>
        </ScrollView>
      ) : (
        <View style={Platform.OS === "web" ? styles.listShellWeb : undefined}>
          <View style={Platform.OS === "web" ? styles.webFrame : undefined}>
            <FlatList
              data={items}
              keyExtractor={(c) => c.id}
              renderItem={renderItem}
              contentContainerStyle={styles.listContent}
              ItemSeparatorComponent={() => <View style={{ height: spacing.sm }} />}
              testID="connections-list"
            />
          </View>
        </View>
      )}

      {/* No web, o botão "Nova Conexão" subiu pro topo (header) — pedido
          explícito do usuário, 2026-07-18. Footer fixo continua só pra
          mobile (comportamento inalterado, per "Platform Scope"). */}
      {Platform.OS !== "web" && !(Platform.OS === "windows" && items.length === 0) ? (
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
      ) : null}

      <AppModal
        visible={editorVisible}
        transparent
        animationType="slide"
        onRequestClose={closeEditor}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === "ios" ? "padding" : undefined}
          style={[{ flex: 1 }, Platform.OS === "web" && styles.editorHostWeb]}
        >
          <Pressable style={styles.backdrop} onPress={closeEditor} />
          <View style={[styles.sheet, Platform.OS === "web" && styles.sheetWeb]} testID="connection-editor-sheet">
            <View style={styles.sheetHandle} />
            <Text style={styles.sheetTitle}>
              {editing ? "Editar conexão" : "Nova conexão"}
            </Text>

          <ScrollView keyboardShouldPersistTaps="handled" style={Platform.OS === "web" ? styles.sheetScrollWeb : { maxHeight: 560 }} contentContainerStyle={Platform.OS === "web" ? styles.sheetContentWeb : undefined}>
            <View style={Platform.OS === "web" ? styles.formGridWeb : { marginTop: spacing.md }}>
              <View style={Platform.OS === "web" ? styles.formFieldWeb : { marginTop: spacing.md }}>
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

              <View style={Platform.OS === "web" ? styles.formFieldWeb : styles.formFieldGap}>
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

              <View style={Platform.OS === "web" ? styles.formFieldWeb : styles.formFieldGap}>
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

              <View style={Platform.OS === "web" ? styles.formFieldWeb : styles.formFieldGap}>
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

              <View style={Platform.OS === "web" ? styles.formFieldWeb : styles.formFieldGap}>
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

              <View style={Platform.OS === "web" ? styles.formFieldWeb : styles.formFieldGap}>
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

              <View style={[styles.switchRow, Platform.OS === "web" && styles.switchRowWeb]}>
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
      </AppModal>

      <AppModal
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
      </AppModal>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Conexões" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  headerSide: { flex: 1, flexDirection: "row", alignItems: "center" },
  headerTitle: { fontSize: 17, fontWeight: "500", color: colors.onSurface, textAlign: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  iconBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  pressed: { opacity: 0.7 },
  headerNewBtn: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    backgroundColor: colors.brandPrimary,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
  },
  headerNewBtnText: {
    color: colors.onBrandPrimary,
    fontWeight: "500",
    fontSize: 13,
  },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  emptyWrap: {
    flexGrow: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xxl,
    paddingBottom: spacing.xl,
  },
  emptyWrapWeb: {
    paddingHorizontal: spacing.xl,
    alignItems: "center",
    justifyContent: "flex-start",
    paddingTop: spacing.xl,
  },
  webCardShadow: {
    shadowColor: "#000",
    shadowOpacity: 0.08,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 8 },
  },
  webEmptyCard: {
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
    paddingVertical: spacing.xl,
    paddingHorizontal: spacing.xl,
    minHeight: 420,
  },
  emptyCtaWeb: {
    marginTop: spacing.lg,
    alignSelf: "center",
    width: "100%",
    maxWidth: 240,
    justifyContent: "center",
  },
  // Marca da Kontacto (`kontacto-icon.png`, 377×378px — quase quadrado),
  // não mais uma foto de banco de imagens genérica (Unsplash, `EMPTY_IMG`
  // removido) — pedido explícito do usuário, 2026-08-27: "colocar a logo
  // da Kontacto nessa tela". `contentFit="contain"` (não "cover") porque
  // é uma marca, não pode cortar; sem `borderRadius` — o recorte fazia
  // sentido pra enquadrar uma foto retangular, não uma marca com fundo
  // transparente.
  emptyImg: {
    width: 140,
    height: 140,
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
  listContentWeb: {
    paddingHorizontal: 0,
    paddingTop: spacing.md,
    paddingBottom: spacing.lg,
    alignItems: "center",
  },
  listShellWeb: {
    flex: 1,
    alignItems: "center",
  },
  webFrame: {
    width: "100%",
    maxWidth: 980,
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
  cardWeb: {
    width: "100%",
    maxWidth: 760,
    alignSelf: "center",
    marginHorizontal: spacing.md,
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
  // Wrapper com position:relative pra ancorar o tooltip absoluto — mesmo
  // padrão de PainelPedidoCard.tsx.
  cardActionWrap: { position: "relative" },
  // Eleva o wrap (e seu tooltip absoluto) por cima dos irmãos seguintes —
  // sem isso, o tooltip ficava visualmente atrás do próximo botão-ícone
  // por causa da ordem no DOM. Só aplicado enquanto o tooltip está visível.
  wrapHovered: { zIndex: 20 },
  tooltip: {
    position: "absolute", bottom: "100%", left: 0, right: 0, marginBottom: 4,
    alignItems: "center", zIndex: 10,
  },
  // Variante pro botão de voltar (colado no topo — "acima" ficaria fora
  // da viewport).
  tooltipBelow: { bottom: undefined, marginBottom: 0, top: "100%", marginTop: 4 },
  tooltipInner: {
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  tooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
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
  sheetWeb: {
    position: "relative",
    width: "92%",
    maxWidth: 1100,
    maxHeight: "88%",
    alignSelf: "center",
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    paddingBottom: spacing.lg,
    overflow: "hidden",
  },
  sheetScrollWeb: {
    flex: 1,
    maxHeight: undefined,
  },
  editorHostWeb: {
    justifyContent: "center",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
  },
  sheetContentWeb: {
    paddingBottom: spacing.md,
  },
  formGridWeb: {
    flexDirection: "row",
    flexWrap: "wrap",
    columnGap: spacing.lg,
  },
  formFieldWeb: {
    flexBasis: "48%",
    flexGrow: 1,
    marginTop: spacing.lg,
  },
  formFieldGap: {
    marginTop: spacing.lg,
  },
  switchRowWeb: {
    width: "100%",
    marginTop: spacing.lg,
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
  primaryBtnWeb: {
    width: "100%",
    maxWidth: 240,
    alignSelf: "center",
    paddingHorizontal: spacing.lg,
  },
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
