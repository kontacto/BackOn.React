import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
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

type Item = { codigo: number; num_serie: string; disponivel: boolean; detalhes: string };
type Produto = { codigo_int: string; codigo_fab: string; descricao: string };

// Cadastro/Tabelas Auxiliares > Números de Série (tabela `pecas_num_serie`,
// vinculada a `pecas.controla_num_serie`). Legado: FrmManNDS. `num_serie` é
// único GLOBALMENTE (não por produto) — mesmo comportamento do legado.
// Produto é selecionado por busca (só produtos com controla_num_serie=1
// aparecem) — precisa estar cadastrado antes de poder receber um número de
// série. Código Fab. é preenchido automaticamente a partir do produto
// selecionado (`pecas.codigo_fab`). Guard de exclusão: bloqueia se o número
// de série pertence a uma Comanda paga ou a uma Nota Fiscal ativa (checado
// no backend).
export default function NumSerieScreen() {
  const router = useRouter();
  const { can, isMaster, isManagerFuncao } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Números de Série está disponível apenas no web."
        testID="num-serie-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  const [produtoPickerOpen, setProdutoPickerOpen] = useState(false);
  const [produtoSearch, setProdutoSearch] = useState("");
  const [produtoResults, setProdutoResults] = useState<Produto[]>([]);
  const [produtoSearching, setProdutoSearching] = useState(false);
  const [produtoDescricao, setProdutoDescricao] = useState("");
  const [codigoInt, setCodigoInt] = useState<string | null>(null);
  const [codigoFab, setCodigoFab] = useState("");

  const [numSerie, setNumSerie] = useState("");
  const [disponivel, setDisponivel] = useState(true);
  const [detalhes, setDetalhes] = useState("");
  const [buscandoSerie, setBuscandoSerie] = useState(false);

  const [items, setItems] = useState<Item[]>([]);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const canSave = can("NUM_SERIE.GRAVAR") || isMaster;
  const canDel = can("NUM_SERIE.EXCLUIR") || isMaster;
  const canEditDisponivel = isMaster || isManagerFuncao;

  useFocusEffect(
    useCallback(() => {
      (async () => {
        const s = await getSession();
        if (!s) { router.replace("/login"); return; }
        const c = (await listConnections()).find((x) => x.empresa === s.empresa) ?? null;
        setConn(c);
      })();
    }, [router])
  );

  const carregarItens = async (c: Connection, cod: string) => {
    setItemsLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&codigo_int=${encodeURIComponent(cod)}`;
      const r = await fetch(`${base}/api/tabelas/num-serie?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setItemsLoading(false); }
  };

  const buscarProdutos = useCallback(async (termo: string) => {
    if (!conn) return;
    setProdutoSearching(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(termo)}`;
      const r = await fetch(`${base}/api/tabelas/num-serie/produtos?${qs}`);
      const j = await r.json();
      setProdutoResults(j?.success ? j.items || [] : []);
    } catch { setProdutoResults([]); } finally { setProdutoSearching(false); }
  }, [conn]);

  useEffect(() => {
    if (!produtoPickerOpen) return;
    const t = setTimeout(() => buscarProdutos(produtoSearch), 300);
    return () => clearTimeout(t);
  }, [produtoSearch, produtoPickerOpen, buscarProdutos]);

  const abrirPickerProduto = () => {
    setProdutoSearch("");
    setProdutoResults([]);
    setProdutoPickerOpen(true);
  };

  const selecionarProduto = (p: Produto) => {
    setCodigoInt(p.codigo_int);
    setCodigoFab(p.codigo_fab);
    setProdutoDescricao(p.descricao);
    setProdutoPickerOpen(false);
    if (conn) carregarItens(conn, p.codigo_int);
  };

  const buscarSerie = async (termo: string) => {
    if (!conn || !termo.trim()) return;
    setBuscandoSerie(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&num_serie=${encodeURIComponent(termo.trim())}`;
      const r = await fetch(`${base}/api/tabelas/num-serie/buscar?${qs}`);
      const j = await r.json();
      if (j?.success && j.encontrado) {
        setDisponivel(!!j.disponivel);
        setDetalhes(j.detalhes || "");
        if (j.codigo_int && j.codigo_int !== codigoInt) {
          setCodigoInt(j.codigo_int);
          setCodigoFab(j.codigo_fab || "");
          setProdutoDescricao(j.descricao || "");
          carregarItens(conn, j.codigo_int);
        }
      }
    } catch {
      // silencioso — se não encontrar, assume novo registro
    } finally { setBuscandoSerie(false); }
  };

  const openNew = () => {
    setProdutoDescricao("");
    setCodigoInt(null);
    setCodigoFab("");
    setNumSerie("");
    setDisponivel(true);
    setDetalhes("");
    setItems([]);
  };

  const selecionarItem = (it: Item) => {
    setNumSerie(it.num_serie);
    setDisponivel(it.disponivel);
    setDetalhes(it.detalhes);
  };

  const save = async () => {
    if (!conn) return;
    if (!codigoInt) { fb.showWarning("Defina o produto."); return; }
    if (!numSerie.trim()) { fb.showWarning("Defina o número de série."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/num-serie`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo_int: codigoInt, num_serie: numSerie.trim(), disponivel, detalhes,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Registro gravado.");
        carregarItens(conn, codigoInt);
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  };

  const excluir = () => {
    if (!conn) return;
    if (!numSerie.trim()) { fb.showWarning("Defina o número de série."); return; }
    Alert.alert(
      "Excluir",
      `Confirma a exclusão do número de série "${numSerie.trim()}"?`,
      [
        { text: "Cancelar", style: "cancel" },
        {
          text: "Excluir",
          style: "destructive",
          onPress: async () => {
            setSaving(true);
            try {
              const base = conn.api.replace(/\/+$/, "");
              const r = await fetch(`${base}/api/tabelas/num-serie/${encodeURIComponent(numSerie.trim())}/excluir`, {
                method: "POST", headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
              });
              const j = await r.json();
              if (j?.success) {
                fb.showSuccess(j.message || "Registro excluído.");
                setNumSerie(""); setDisponivel(true); setDetalhes("");
                if (codigoInt) carregarItens(conn, codigoInt);
              } else {
                fb.showError(j?.message || "Falha ao excluir.");
              }
            } catch (e) {
              fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
            } finally { setSaving(false); }
          },
        },
      ]
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="num-serie-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Números de Série</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <Text style={styles.label}>Produto</Text>
            <Pressable onPress={abrirPickerProduto} style={styles.input} testID="num-serie-produto">
              <Text style={produtoDescricao ? styles.pickerText : styles.pickerPlaceholder} numberOfLines={1}>
                {produtoDescricao || "Buscar produto…"}
              </Text>
            </Pressable>

            <Text style={styles.label}>Código Fab.</Text>
            <TextInput value={codigoFab} editable={false} style={[styles.input, styles.inputDisabled]} testID="num-serie-codigo-fab" />

            <Text style={styles.label}>Número de Série</Text>
            <TextInput
              value={numSerie}
              onChangeText={setNumSerie}
              onBlur={() => buscarSerie(numSerie)}
              placeholder="Digite ou selecione na lista abaixo"
              placeholderTextColor={colors.muted}
              style={styles.input}
              maxLength={30}
              testID="num-serie-numero"
            />
            {buscandoSerie ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 4 }} /> : null}

            <Text style={styles.label}>Disponível</Text>
            <View style={styles.pillRow}>
              <Pressable
                disabled={!canEditDisponivel}
                onPress={() => setDisponivel(true)}
                style={[styles.pill, disponivel && styles.pillActive, !canEditDisponivel && styles.pillDisabled]}
                testID="num-serie-disponivel-sim"
              >
                <Text style={[styles.pillText, disponivel && styles.pillTextActive]}>Sim</Text>
              </Pressable>
              <Pressable
                disabled={!canEditDisponivel}
                onPress={() => setDisponivel(false)}
                style={[styles.pill, !disponivel && styles.pillActive, !canEditDisponivel && styles.pillDisabled]}
                testID="num-serie-disponivel-nao"
              >
                <Text style={[styles.pillText, !disponivel && styles.pillTextActive]}>Não</Text>
              </Pressable>
            </View>

            <Text style={styles.label}>Detalhes</Text>
            <TextInput
              value={detalhes}
              onChangeText={setDetalhes}
              style={[styles.input, styles.textArea]}
              multiline
              numberOfLines={4}
              testID="num-serie-detalhes"
            />

            <View style={styles.btnRow}>
              <Pressable onPress={openNew} style={styles.secondaryBtn} testID="num-serie-novo">
                <Text style={styles.secondaryBtnText}>Novo</Text>
              </Pressable>
              {canSave ? (
                <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="num-serie-gravar">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
              {canDel ? (
                <Pressable onPress={excluir} disabled={saving} style={[styles.dangerBtn, saving && { opacity: 0.6 }]} testID="num-serie-excluir">
                  <Text style={styles.dangerBtnText}>Excluir</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          <View style={[styles.card, { marginTop: spacing.md }]}>
            <Text style={styles.cardTitle}>Números de série do produto</Text>
            {itemsLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!itemsLoading && !codigoInt ? <Text style={styles.empty}>Selecione um produto para ver os números de série.</Text> : null}
            {!itemsLoading && codigoInt && items.length === 0 ? <Text style={styles.empty}>Nenhum número de série cadastrado.</Text> : null}
            {items.map((it) => (
              <Pressable key={it.codigo} onPress={() => selecionarItem(it)} style={styles.row} testID={`num-serie-item-${it.codigo}`}>
                <Text style={styles.rowTitle}>{it.num_serie}</Text>
                <Text style={[styles.rowBadge, it.disponivel ? styles.rowBadgeOn : styles.rowBadgeOff]}>
                  {it.disponivel ? "Disponível" : "Indisponível"}
                </Text>
                {it.detalhes ? <Text style={styles.rowSub} numberOfLines={1}>{it.detalhes}</Text> : null}
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>

      <Modal visible={produtoPickerOpen} transparent animationType="slide" onRequestClose={() => setProdutoPickerOpen(false)}>
        <Pressable style={styles.pickerBg} onPress={() => setProdutoPickerOpen(false)}>
          <Pressable style={styles.pickerCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.pickerHeader}>
              <Text style={styles.pickerTitle}>Selecionar Produto</Text>
              <Pressable onPress={() => setProdutoPickerOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={produtoSearch}
                onChangeText={setProdutoSearch}
                placeholder="Código, descrição ou código de barras…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                autoFocus={Platform.OS === "web"}
                testID="num-serie-produto-search"
              />
            </View>
            {produtoSearching ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.sm }} /> : null}
            <ScrollView style={{ maxHeight: 360 }} keyboardShouldPersistTaps="handled">
              {!produtoSearching && produtoResults.length === 0 ? (
                <Text style={styles.empty}>Nenhum produto com controle de número de série encontrado.</Text>
              ) : null}
              {produtoResults.map((p) => (
                <Pressable
                  key={p.codigo_int}
                  onPress={() => selecionarProduto(p)}
                  style={styles.optRow}
                  testID={`num-serie-produto-opt-${p.codigo_int}`}
                >
                  <Text style={styles.optLabel} numberOfLines={1}>{p.descricao}</Text>
                  <Text style={styles.optSub}>{p.codigo_int} · Fab. {p.codigo_fab || "—"}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, paddingBottom: 40 },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, maxWidth: 560, gap: spacing.xs },
  cardTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface, justifyContent: "center" },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  pickerText: { fontSize: 14, color: colors.onSurface },
  pickerPlaceholder: { fontSize: 14, color: colors.muted },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  pillRow: { flexDirection: "row", gap: spacing.sm },
  pill: { paddingHorizontal: spacing.lg, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillDisabled: { opacity: 0.5 },
  pillText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  pillTextActive: { color: "#fff" },
  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { flex: 1, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center" },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  secondaryBtn: { flex: 1, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center" },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 14 },
  dangerBtn: { flex: 1, borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center" },
  dangerBtnText: { color: colors.error, fontWeight: "700", fontSize: 14 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 12, marginBottom: 4 },
  row: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingVertical: spacing.sm },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowBadge: { fontSize: 11, fontWeight: "600", marginTop: 2 },
  rowBadgeOn: { color: colors.success },
  rowBadgeOff: { color: colors.error },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  pickerBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
  },
  pickerCard: {
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
    padding: spacing.lg,
  },
  pickerHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  pickerTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  optRow: { paddingVertical: 10, paddingHorizontal: spacing.xs, borderBottomWidth: 1, borderBottomColor: colors.border },
  optLabel: { fontSize: 14, color: colors.onSurface },
  optSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
});
