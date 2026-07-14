import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  FlatList,
  Image,
  Modal,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";

type Cliente = {
  codigo: number;
  nome: string;
  cgc_cpf?: string;
  telefone?: string;
  e_mail?: string;
  tipo_descricao?: string;
  situacao?: string;
  lista_negra?: boolean;
  lista_negra_motivo?: string;
};

// Cor "luto" (preto) do botão Lista Negra quando o cliente já está
// cadastrado — legado: FrmListaN ("Cadastro de Clientes na Lista Negra").
// Sem cliente na lista, o botão fica azul (mesma cor do ícone padrão).
const LISTA_NEGRA_COR_ATIVA = "#000000";
// Largura fixa da etiqueta (tooltip) do motivo — precisa ser fixa (não
// min/maxWidth) pra centralizar com exatidão em relação ao botão.
const TOOLTIP_WIDTH = 180;

const FAB_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 4px 8px rgba(0, 0, 0, 0.25)" }
    : {
        shadowColor: "#000",
        shadowOpacity: 0.25,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 4 },
        elevation: 8,
      };

export default function ClientesScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const feedback = useFeedback();
  const auditCtx = useAuditContext();
  const params = useLocalSearchParams<{ modo?: string }>();
  // Entrando via card "Cliente Rápido" (Cadastros), força o cadastro rápido mesmo
  // na web — onde o padrão normalmente seria abrir o cadastro completo.
  const formRoute = params.modo === "rapido" ? "/cliente-form" : (Platform.OS === "web" ? "/cliente-completo" : "/cliente-form");
  const canNovoCliente = can("CLIENTE.GRAVAR");
  const canNovoPedido = can("PEDIDO.GRAVAR");
  const canListaNegra = can("CLIENTE.LISTA_NEGRA");
  const [items, setItems] = useState<Cliente[]>([]);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);

  const [listaNegraAlvo, setListaNegraAlvo] = useState<Cliente | null>(null);
  const [listaNegraMotivo, setListaNegraMotivo] = useState("");
  const [listaNegraHover, setListaNegraHover] = useState<number | null>(null);
  const [listaNegraTooltipPos, setListaNegraTooltipPos] = useState<{ top: number; left: number } | null>(null);
  const listaNegraBtnRefs = useRef<Record<number, View | null>>({});
  const [listaNegraSaving, setListaNegraSaving] = useState(false);

  const load = useCallback(async (q: string, p: number, append: boolean) => {
    setLoading(true);
    const session = await getSession();
    if (!session) {
      router.replace("/login");
      setLoading(false);
      return;
    }
    const conns = await listConnections();
    const conn = conns.find((c) => c.empresa === session.empresa);
    if (!conn) {
      feedback.showError("Conexão não encontrada.");
      setLoading(false);
      return;
    }
    try {
      const resp = await fetch(`${conn.api.replace(/\/+$/, "")}/api/clientes`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor,
          banco: conn.banco,
          search: q,
          page: p,
          size: 20,
        }),
      });
      const data = await resp.json();
      if (!data.success) {
        feedback.showError(data.message || "Erro ao carregar");
      } else {
        setItems((prev) => (append ? [...prev, ...data.items] : data.items));
        setTotal(data.total);
      }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [feedback]);

  useEffect(() => {
    const t = setTimeout(() => {
      setPage(1);
      load(search, 1, false);
    }, 400);
    return () => clearTimeout(t);
  }, [search, load]);

  // Recarrega a lista ao voltar para a tela (ex.: depois de criar/editar cliente),
  // mantendo o filtro de busca atual. Aplica reload em background sem mexer no
  // estado de search/page para não perder o contexto.
  useFocusEffect(
    useCallback(() => {
      load(search, 1, false);
      setPage(1);
    }, [load, search])
  );

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, next, true);
  };

  const getConn = async () => {
    const session = await getSession();
    const conns = await listConnections();
    return conns.find((c) => c.empresa === session?.empresa) ?? null;
  };

  const abrirListaNegra = (item: Cliente) => {
    setListaNegraAlvo(item);
    setListaNegraMotivo(item.lista_negra_motivo || "");
  };

  const fecharListaNegra = () => {
    setListaNegraAlvo(null);
    setListaNegraMotivo("");
  };

  // Etiqueta (tooltip) do motivo é renderizada FORA da FlatList (overlay de
  // tela inteira), medindo a posição real do botão na janela — dentro da
  // lista, o zIndex não escapa da célula virtualizada da FlatList e a
  // etiqueta ficava atrás dos cards seguintes.
  const abrirTooltipListaNegra = (codigo: number) => {
    setListaNegraHover(codigo);
    const node = listaNegraBtnRefs.current[codigo] as unknown as {
      measureInWindow?: (cb: (x: number, y: number, width: number, height: number) => void) => void;
    } | null;
    node?.measureInWindow?.((x, y, width, height) => {
      const winWidth = Dimensions.get("window").width;
      // Centralizada na mesma posição horizontal do botão (centro do botão =
      // centro da etiqueta) — nem grudada na borda esquerda, nem na direita.
      const centroBotao = x + width / 2;
      const left = Math.min(
        Math.max(8, centroBotao - TOOLTIP_WIDTH / 2),
        winWidth - TOOLTIP_WIDTH - 8
      );
      setListaNegraTooltipPos({ top: y + height + 6, left });
    });
  };

  const fecharTooltipListaNegra = () => {
    setListaNegraHover(null);
    setListaNegraTooltipPos(null);
  };

  const salvarListaNegra = async () => {
    if (!listaNegraAlvo) return;
    if (!listaNegraMotivo.trim()) {
      feedback.showWarning("Preencha o motivo corretamente.");
      return;
    }
    const conn = await getConn();
    if (!conn) {
      feedback.showError("Conexão não encontrada.");
      return;
    }
    setListaNegraSaving(true);
    try {
      const resp = await fetch(`${conn.api.replace(/\/+$/, "")}/api/clientes/${listaNegraAlvo.codigo}/lista-negra`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor,
          banco: conn.banco,
          motivo: listaNegraMotivo.trim(),
          ...auditCtx,
        }),
      });
      const data = await resp.json();
      if (data?.success) {
        feedback.showSuccess(data.message || "Registro gravado.");
        fecharListaNegra();
        load(search, 1, false);
        setPage(1);
      } else {
        feedback.showError(data?.message || "Falha ao gravar.");
      }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setListaNegraSaving(false);
    }
  };

  const excluirListaNegra = async () => {
    if (!listaNegraAlvo) return;
    const conn = await getConn();
    if (!conn) {
      feedback.showError("Conexão não encontrada.");
      return;
    }
    setListaNegraSaving(true);
    try {
      const resp = await fetch(`${conn.api.replace(/\/+$/, "")}/api/clientes/${listaNegraAlvo.codigo}/lista-negra/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const data = await resp.json();
      if (data?.success) {
        feedback.showSuccess(data.message || "Registro excluído.");
        fecharListaNegra();
        load(search, 1, false);
        setPage(1);
      } else {
        feedback.showError(data?.message || "Falha ao excluir.");
      }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setListaNegraSaving(false);
    }
  };

  if (!can("CLIENTE.ABRIR")) {
    return <LockedView testID="clientes-locked" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="clientes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={8} style={styles.backBtn} testID="clientes-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Clientes ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={[styles.searchWrap, Platform.OS === "web" && styles.searchWrapWeb]}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por nome, CPF/CNPJ ou telefone…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="clientes-search-input"
        />
      </View>

      <View style={Platform.OS === "web" ? styles.webListShell : undefined}>
        <FlatList
          style={Platform.OS === "web" ? styles.listWeb : undefined}
          data={items}
          keyExtractor={(c) => String(c.codigo)}
          contentContainerStyle={[styles.listContent, Platform.OS === "web" && styles.listContentWeb]}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.6}
          ListEmptyComponent={
            !loading ? (
              <Text style={styles.empty}>Nenhum cliente encontrado.</Text>
            ) : null
          }
          ListFooterComponent={
            loading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
            ) : null
          }
          renderItem={({ item }) => (
            <Pressable
              onPress={() =>
                router.push({
                  pathname: formRoute,
                  params: { codigo: String(item.codigo) },
                } as never)
              }
              style={({ pressed }) => [
                styles.card,
                Platform.OS === "web" && styles.cardWeb,
                pressed && { opacity: 0.7 },
              ]}
              testID={`cliente-${item.codigo}`}
            >
              <View style={[styles.cardIcon, Platform.OS === "web" && styles.cardIconWeb]}>
                <Ionicons name="person-outline" size={20} color={colors.brandPrimary} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, Platform.OS === "web" && styles.cardTitleWeb]} numberOfLines={1}>{item.nome}</Text>
                <Text style={[styles.cardSub, Platform.OS === "web" && styles.cardSubWeb]} numberOfLines={1}>
                  {item.telefone || "Sem telefone"}
                  {item.cgc_cpf ? ` · ${item.cgc_cpf}` : ""}
                </Text>
                {item.tipo_descricao ? (
                  <Text style={[styles.cardSub, Platform.OS === "web" && styles.cardSubWeb]} numberOfLines={1}>Tipo: {item.tipo_descricao}</Text>
                ) : null}
              </View>
              {canNovoPedido ? (
                <Pressable
                  onPress={(e) => {
                    e.stopPropagation();
                    router.push({
                      pathname: "/pedido-form",
                      params: { cliente: String(item.codigo), cliente_nome: item.nome },
                    });
                  }}
                  style={({ pressed }) => [styles.novoPedidoBtn, pressed && { opacity: 0.7 }]}
                  hitSlop={6}
                  testID={`cliente-${item.codigo}-novo-pedido`}
                >
                  <Ionicons name="add-circle" size={28} color={colors.brandPrimary} />
                  <Text style={styles.novoPedidoLabel}>Pedido</Text>
                </Pressable>
              ) : null}
              {canListaNegra ? (
                <Pressable
                  ref={(node) => { listaNegraBtnRefs.current[item.codigo] = node as unknown as View | null; }}
                  onPress={(e) => {
                    e.stopPropagation();
                    abrirListaNegra(item);
                  }}
                  onHoverIn={() => abrirTooltipListaNegra(item.codigo)}
                  onHoverOut={fecharTooltipListaNegra}
                  style={({ pressed }) => [styles.novoPedidoBtn, pressed && { opacity: 0.7 }]}
                  hitSlop={6}
                  testID={`cliente-${item.codigo}-lista-negra`}
                >
                  <View style={styles.listaNegraIconSlot}>
                    {item.lista_negra ? (
                      <Ionicons name="ban" size={28} color={LISTA_NEGRA_COR_ATIVA} />
                    ) : null}
                  </View>
                  <Text
                    style={[
                      styles.novoPedidoLabel,
                      item.lista_negra
                        ? { color: LISTA_NEGRA_COR_ATIVA, fontWeight: "700" }
                        : { color: colors.brandPrimary },
                    ]}
                  >
                    Lista Negra
                  </Text>
                </Pressable>
              ) : null}
            </Pressable>
          )}
        />
      </View>

      {canNovoCliente ? (
        <Pressable
          onPress={() => router.push(formRoute as never)}
          style={({ pressed }) => [
            styles.fab,
            FAB_SHADOW_STYLE,
            pressed && { opacity: 0.85, transform: [{ scale: 0.96 }] },
          ]}
          hitSlop={8}
          testID="clientes-fab-new"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}

      <Modal visible={!!listaNegraAlvo} transparent animationType="slide" onRequestClose={fecharListaNegra}>
        <Pressable style={styles.modalBg} onPress={fecharListaNegra}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Lista Negra</Text>
            <Text style={styles.label}>Cliente</Text>
            <TextInput
              value={listaNegraAlvo?.nome || ""}
              editable={false}
              style={[styles.input, styles.inputDisabled]}
              testID="lista-negra-cliente"
            />
            <Text style={styles.label}>Motivo *</Text>
            <TextInput
              value={listaNegraMotivo}
              onChangeText={setListaNegraMotivo}
              placeholder="Motivo do cliente estar na lista negra"
              placeholderTextColor={colors.muted}
              style={[styles.input, styles.textArea]}
              multiline
              numberOfLines={4}
              testID="lista-negra-motivo"
            />
            <View style={styles.modalActions}>
              {listaNegraAlvo?.lista_negra ? (
                <Pressable
                  onPress={excluirListaNegra}
                  disabled={listaNegraSaving}
                  style={[styles.modalBtn, styles.modalBtnDanger, listaNegraSaving && { opacity: 0.6 }]}
                  testID="lista-negra-excluir"
                >
                  <Text style={styles.modalBtnDangerText}>Excluir</Text>
                </Pressable>
              ) : null}
              <Pressable
                onPress={salvarListaNegra}
                disabled={listaNegraSaving}
                style={[styles.modalBtn, styles.modalBtnPrimary, listaNegraSaving && { opacity: 0.6 }]}
                testID="lista-negra-gravar"
              >
                {listaNegraSaving ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.modalBtnPrimaryText}>Gravar</Text>
                )}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {listaNegraHover != null && listaNegraTooltipPos ? (() => {
        const hoveredItem = items.find((i) => i.codigo === listaNegraHover);
        if (!hoveredItem?.lista_negra || !hoveredItem.lista_negra_motivo) return null;
        return (
          <View
            style={[styles.tooltip, { top: listaNegraTooltipPos.top, left: listaNegraTooltipPos.left }]}
            pointerEvents="none"
          >
            <Text style={styles.tooltipText} numberOfLines={4}>{hoveredItem.lista_negra_motivo}</Text>
          </View>
        );
      })() : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  backBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: {
    flex: 1, textAlign: "center", color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    marginHorizontal: spacing.lg, marginVertical: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  searchWrapWeb: {
    width: "100%",
    maxWidth: 620,
    alignSelf: "center",
  },
  searchInput: {
    flex: 1, fontSize: 14, color: colors.onSurface, minHeight: 36,
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
  },
  cardWeb: {
    width: "100%",
    minHeight: 87,
    borderRadius: radius.lg,
    paddingVertical: 12,
    paddingHorizontal: 12,
  },
  cardIcon: {
    width: 40, height: 40, borderRadius: radius.md,
    alignItems: "center", justifyContent: "center",
    backgroundColor: colors.brandTertiary,
  },
  cardIconWeb: {
    width: 31,
    height: 31,
    borderRadius: radius.lg,
  },
  cardTitle: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardTitleWeb: { fontSize: 13 },
  cardSubWeb: { fontSize: 10 },
  empty: {
    textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40,
  },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: 100 },
  listWeb: { width: "100%", maxWidth: 602, alignSelf: "center" },
  listContentWeb: { width: "100%", maxWidth: 602, alignSelf: "center", paddingBottom: 120 },
  webListShell: { flex: 1, alignItems: "center" },
  fab: {
    position: "absolute",
    right: spacing.lg,
    bottom: spacing.xl,
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  novoPedidoBtn: {
    padding: 4,
    marginLeft: 4,
    alignItems: "center",
    position: "relative",
  },
  novoPedidoLabel: {
    fontSize: 10,
    color: colors.brandPrimary,
    fontWeight: "600",
    marginTop: -2,
  },
  listaNegraIconSlot: {
    height: 28,
    alignItems: "center",
    justifyContent: "center",
  },
  tooltip: {
    position: "absolute",
    backgroundColor: "#1a1a1a",
    borderRadius: radius.sm,
    paddingHorizontal: 10,
    paddingVertical: 6,
    width: TOOLTIP_WIDTH,
    zIndex: 20,
    elevation: 6,
  },
  tooltipText: {
    color: "#fff",
    fontSize: 11,
    lineHeight: 15,
  },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 480 : undefined,
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  modalActions: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, marginBottom: spacing.sm },
  modalBtn: { flex: 1, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center" },
  modalBtnPrimary: { backgroundColor: colors.brandPrimary },
  modalBtnPrimaryText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  modalBtnDanger: { backgroundColor: "#fff1f1", borderWidth: 1, borderColor: "#f4b6b6" },
  modalBtnDangerText: { color: colors.error, fontWeight: "700", fontSize: 15 },
});
