import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";

type Tipo = "all" | "P" | "S";
type Item = {
  tipo: "P" | "S";
  codigo: string;
  descricao: string;
  valor: number;
  estoque: number | null;
  cod_fab?: string;
  unidade?: string;
};

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function parseNum(s: string): number {
  const n = parseFloat(String(s).replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export default function ProdutosScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const servicosOn = moduleOn("servicos");
  const params = useLocalSearchParams<{ pedido?: string }>();
  const selectPedido = params.pedido ? parseInt(String(params.pedido), 10) : null;
  const selecting = !!selectPedido;

  const [selItem, setSelItem] = useState<Item | null>(null);
  const [selQtd, setSelQtd] = useState("1");
  const [selValor, setSelValor] = useState("0,00");
  const [selCompl, setSelCompl] = useState("");
  const [selDesc, setSelDesc] = useState("");
  const [selDescMode, setSelDescMode] = useState<"rs" | "pct">("pct");
  const [selSaving, setSelSaving] = useState(false);
  // Permissão de desconto do usuário logado
  const [funcaoCod, setFuncaoCod] = useState<number>(1); // 1=gerente,2=supervisor,3=vendedor
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [descLimite, setDescLimite] = useState<number>(100); // % máximo permitido
  const [toast, setToast] = useState<string | null>(null);
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  const [tipo, setTipo] = useState<Tipo>("all");
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      // Função/permissão de desconto do usuário logado
      const isMaster = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = cf ? parseInt(cf, 10) : NaN;
      const funcao = isMaster ? 1 : Number.isFinite(fc) && fc > 0 ? fc : 1;
      setFuncaoCod(funcao);
      const vCod = s?.funcionario?.codigo_int;
      setUsuarioCod(isMaster ? -2 : typeof vCod === "number" ? vCod : -2);
      if (c) {
        try {
          const base = c.api.replace(/\/+$/, "");
          const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const rl = await fetch(`${base}/api/controle/desconto-limites?${qs}`).then((r) => r.json());
          if (rl?.success) {
            const lim = funcao === 2 ? rl.supervisor : funcao === 3 ? rl.vendedor : rl.gerente;
            setDescLimite(Number(lim) || 100);
          }
        } catch {
          // mantém limite padrão
        }
      }
    })();
  }, []);

  const load = useCallback(
    async (term: string, pg: number, tp: Tipo, append: boolean) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      setError(null);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const url =
          `${base}/api/produtos-servicos` +
          `?servidor=${encodeURIComponent(conn.servidor)}` +
          `&banco=${encodeURIComponent(conn.banco)}` +
          `&search=${encodeURIComponent(term)}` +
          `&page=${pg}&size=40&tipo=${servicosOn ? tp : "P"}`;
        const r = await fetch(url, { signal: ac.signal });
        const j = await r.json();
        if (!j?.success) {
          setError(j?.message || "Falha ao consultar.");
          if (!append) setItems([]);
        } else {
          const fetched: Item[] = j.items || [];
          setItems((prev) => (append ? [...prev, ...fetched] : fetched));
          setTotal(j.total || 0);
        }
      } catch (e: unknown) {
        if ((e as { name?: string })?.name !== "AbortError") {
          setError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        }
      } finally {
        if (aborter.current === ac) {
          setLoading(false);
          aborter.current = null;
        }
      }
    },
    [conn, servicosOn]
  );

  // Recarrega quando muda search / tipo (debounce 300ms na busca)
  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => {
      setPage(1);
      load(search, 1, tipo, false);
    }, 300);
    return () => clearTimeout(t);
  }, [search, tipo, conn, load]);

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, next, tipo, true);
  };

  // Tipo da rota da foto — codigo é string (nvarchar). URL-encode pra segurança.
  const fotoUrl = useCallback(
    (item: Item): string | null => {
      if (!conn) return null;
      if (item.tipo === "S") return null;
      return `${conn.api.replace(/\/+$/, "")}/api/produtos/foto/${encodeURIComponent(item.codigo)}`;
    },
    [conn]
  );

  const counts = useMemo(() => {
    const p = items.filter((i) => i.tipo === "P").length;
    const s = items.filter((i) => i.tipo === "S").length;
    return { p, s };
  }, [items]);

  const showToast = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 2500);
  }, []);

  const pickForOrder = (item: Item) => {
    setSelItem(item);
    setSelQtd("1");
    setSelValor(formatBRL(item.valor).replace("R$", "").trim());
    setSelCompl("");
    setSelDesc("");
    setSelDescMode("pct");
  };

  const addToOrder = async () => {
    if (!conn || !selectPedido || !selItem) return;
    const qtd = parseNum(selQtd);
    if (qtd <= 0) { showToast("Quantidade inválida."); return; }
    const pNormal = parseNum(selValor);
    // Calcula desconto unitário (R$) e % a partir do modo escolhido
    let descRs = 0;
    let descPct = 0;
    const dVal = parseNum(selDesc);
    if (dVal > 0 && pNormal > 0) {
      if (selDescMode === "pct") {
        descPct = dVal;
        descRs = Math.round(((pNormal * dVal) / 100) * 100) / 100;
      } else {
        descRs = dVal;
        descPct = Math.round((descRs / pNormal) * 10000) / 100;
      }
    }
    // Valida limite por função
    if (descPct > descLimite + 0.001) {
      showToast(`Desconto acima do limite permitido (${descLimite}%).`);
      return;
    }
    setSelSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/pedidos/${selectPedido}/itens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco,
          produto: selItem.codigo,
          qtd,
          valor_unitario: pNormal,
          desconto: descRs,
          desconto_pct: descPct,
          usuario_codigo: usuarioCod,
          funcao: funcaoCod,
          complemento: selCompl,
        }),
      });
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao adicionar."); }
      else {
        setSelItem(null);
        showToast("Adicionado ao pedido!");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSelSaving(false); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="produtos-screen">
      {!(selecting ? can("PEDIDO.GRAVAR") : can("PRODUTO.ABRIR")) ? (
        <LockedView testID="produtos-locked" />
      ) : (
      <>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>
          {selecting ? `Adicionar ao Pedido #${selectPedido}` : `Produtos & Serviços (${total})`}
        </Text>
        <View style={{ width: 40 }} />
      </View>

      {selecting ? (
        <View style={styles.selectBanner}>
          <Ionicons name="cart-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.selectBannerText}>Toque em um item para adicioná-lo ao pedido.</Text>
        </View>
      ) : null}

      <View style={styles.searchWrap}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por código ou descrição…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="produtos-search-input"
        />
      </View>

      {/* Chips de tipo — ocultos quando o módulo Serviços está desligado */}
      {servicosOn ? (
      <View style={styles.chips}>
        {([
          { key: "all" as const, label: "Tudo", count: counts.p + counts.s },
          { key: "P" as const, label: "Produtos", count: counts.p },
          { key: "S" as const, label: "Serviços", count: counts.s },
        ]).map((c) => {
          const sel = tipo === c.key;
          return (
            <Pressable
              key={c.key}
              onPress={() => setTipo(c.key)}
              style={({ pressed }) => [
                styles.chip,
                sel && styles.chipSel,
                pressed && { opacity: 0.7 },
              ]}
              testID={`produtos-chip-${c.key}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      ) : null}

      {error ? (
        <Text style={styles.errorText} testID="produtos-error">
          {error}
        </Text>
      ) : null}

      <FlatList
        data={items}
        keyExtractor={(i) => `${i.tipo}-${i.codigo}`}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.empty}>Nenhum item encontrado.</Text>
          ) : null
        }
        ListFooterComponent={
          loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : null
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() => { if (selecting) pickForOrder(item); }}
            disabled={!selecting}
            style={({ pressed }) => [styles.card, selecting && pressed && { opacity: 0.7 }]}
            testID={`item-${item.tipo}-${item.codigo}`}
          >
            {item.tipo === "P" ? (
              <ProdutoFoto url={fotoUrl(item)} />
            ) : (
              <View style={[styles.thumb, styles.thumbServico]}>
                <Ionicons name="construct-outline" size={26} color={colors.brandPrimary} />
              </View>
            )}

            <View style={{ flex: 1 }}>
              <View style={styles.cardTitleRow}>
                <Text style={styles.cardTitle} numberOfLines={2}>
                  {item.descricao || "—"}
                </Text>
                <View
                  style={[
                    styles.tipoTag,
                    item.tipo === "P" ? styles.tagProd : styles.tagServ,
                  ]}
                >
                  <Text style={[styles.tipoTagText, item.tipo === "P" ? { color: colors.brandPrimary } : { color: colors.warning }]}>
                    {item.tipo === "P" ? "PRODUTO" : "SERVIÇO"}
                  </Text>
                </View>
              </View>
              <Text style={styles.cardSub}>
                Código: <Text style={styles.cardSubBold}>#{item.codigo}</Text>
              </Text>
              <View style={styles.cardFooter}>
                <Text style={styles.cardValor}>{formatBRL(item.valor)}</Text>
                {item.tipo === "P" ? (
                  <Text
                    style={[
                      styles.estoque,
                      (item.estoque ?? 0) <= 0 && { color: colors.error },
                    ]}
                  >
                    Estoque: {item.estoque ?? 0}
                  </Text>
                ) : (
                  <Text style={styles.estoque}>por hora</Text>
                )}
              </View>
            </View>
            {selecting ? (
              <Ionicons name="add-circle" size={26} color={colors.brandPrimary} />
            ) : null}
          </Pressable>
        )}
      />

      {/* Modal de quantidade ao adicionar item ao pedido */}
      <Modal visible={!!selItem} transparent animationType="slide" onRequestClose={() => setSelItem(null)}>
        <Pressable style={styles.modalBg} onPress={() => setSelItem(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Adicionar ao Pedido</Text>
              <Pressable onPress={() => setSelItem(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {selItem ? (
              <View style={{ gap: spacing.sm }}>
                <View style={styles.selProdBox}>
                  <Text style={styles.itemDesc} numberOfLines={2}>{selItem.descricao}</Text>
                  <Text style={styles.cardSub}>#{selItem.codigo}{selItem.cod_fab ? ` · ${selItem.cod_fab}` : ""}</Text>
                </View>
                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Quantidade</Text>
                    <View style={styles.qtdInputRow}>
                      <TextInput value={selQtd} onChangeText={setSelQtd} keyboardType="decimal-pad" style={[styles.modalInput, { flex: 1 }]} testID="produtos-add-qtd" />
                      <TouchableOpacity
                        onPress={() => setSelQtd(String(parseNum(selQtd) + 1).replace(".", ","))}
                        activeOpacity={0.7}
                        style={styles.plusBtn}
                        testID="produtos-add-qtd-plus"
                      >
                        <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                      </TouchableOpacity>
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor unitário</Text>
                    <TextInput value={selValor} onChangeText={setSelValor} keyboardType="decimal-pad" style={styles.modalInput} testID="produtos-add-valor" />
                  </View>
                </View>
                <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                <TextInput value={selCompl} onChangeText={setSelCompl} placeholder="Descrição complementar" placeholderTextColor={colors.muted} style={styles.modalInput} testID="produtos-add-compl" />

                {/* Desconto com alternância R$ / % */}
                <View style={styles.descHeader}>
                  <Text style={styles.fieldLabel}>Desconto (máx. {descLimite}%)</Text>
                  <View style={styles.modeToggle}>
                    <TouchableOpacity
                      onPress={() => setSelDescMode("pct")}
                      style={[styles.modeBtn, selDescMode === "pct" && styles.modeBtnSel]}
                      testID="produtos-add-desc-pct"
                    >
                      <Text style={[styles.modeBtnText, selDescMode === "pct" && styles.modeBtnTextSel]}>%</Text>
                    </TouchableOpacity>
                    <TouchableOpacity
                      onPress={() => setSelDescMode("rs")}
                      style={[styles.modeBtn, selDescMode === "rs" && styles.modeBtnSel]}
                      testID="produtos-add-desc-rs"
                    >
                      <Text style={[styles.modeBtnText, selDescMode === "rs" && styles.modeBtnTextSel]}>R$</Text>
                    </TouchableOpacity>
                  </View>
                </View>
                <TextInput
                  value={selDesc}
                  onChangeText={setSelDesc}
                  keyboardType="decimal-pad"
                  placeholder={selDescMode === "pct" ? "0 %" : "R$ 0,00"}
                  placeholderTextColor={colors.muted}
                  style={styles.modalInput}
                  testID="produtos-add-desc"
                />

                <View style={styles.previewRow}>
                  <Text style={styles.fieldLabel}>Total do item</Text>
                  <Text style={styles.cardValor}>
                    {(() => {
                      const pn = parseNum(selValor);
                      const dv = parseNum(selDesc);
                      const descRs = dv > 0 && pn > 0 ? (selDescMode === "pct" ? (pn * dv) / 100 : dv) : 0;
                      return formatBRL(parseNum(selQtd) * Math.max(pn - descRs, 0));
                    })()}
                  </Text>
                </View>
                <Pressable
                  onPress={addToOrder}
                  disabled={selSaving}
                  style={({ pressed }) => [styles.primaryBtn, (pressed || selSaving) && { opacity: 0.8 }]}
                  testID="produtos-add-confirm"
                >
                  {selSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Adicionar ao Pedido</Text>}
                </Pressable>
              </View>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? (
        <View style={styles.toast} testID="produtos-toast">
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
      </>
      )}
    </SafeAreaView>
  );
}

// Foto do produto com fallback (placeholder com ícone quando o endpoint retorna 204).
function ProdutoFoto({ url }: { url: string | null }) {
  const [erro, setErro] = useState(false);
  useEffect(() => {
    setErro(false);
  }, [url]);
  if (!url || erro) {
    return (
      <View style={[styles.thumb, styles.thumbProduto]}>
        <Ionicons name="cube-outline" size={26} color={colors.brandPrimary} />
      </View>
    );
  }
  return (
    <Image
      source={{ uri: url }}
      style={styles.thumb}
      onError={() => setErro(true)}
      resizeMode="cover"
    />
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  backBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  headerTitle: {
    flex: 1, color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  chips: {
    flexDirection: "row", gap: 8,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md, marginBottom: spacing.sm,
    height: 56, alignItems: "center",
  },
  chip: {
    flexShrink: 0,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    height: 36, justifyContent: "center",
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  errorText: {
    color: colors.error, fontSize: 13, marginHorizontal: spacing.lg, marginBottom: spacing.sm,
  },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  thumb: {
    width: 64, height: 64, borderRadius: radius.sm,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  thumbProduto: { backgroundColor: colors.brandTertiary },
  thumbServico: { backgroundColor: "#fff4e0" },
  cardTitleRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm },
  cardTitle: { flex: 1, fontSize: 14, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardSubBold: { color: colors.onSurface, fontWeight: "500" },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  cardValor: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  estoque: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  tipoTag: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 4, alignSelf: "flex-start",
  },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  tipoTagText: { fontSize: 10, fontWeight: "600", letterSpacing: 0.4 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40 },
  selectBanner: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.brandTertiary, marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  selectBannerText: { color: colors.onSurface, fontSize: 13, flex: 1 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  itemDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  selProdBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  qtdRow: { flexDirection: "row", gap: spacing.sm },
  descHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  modeToggle: { flexDirection: "row", borderWidth: 1, borderColor: colors.border, borderRadius: 8, overflow: "hidden" },
  modeBtn: { paddingHorizontal: 14, paddingVertical: 4, backgroundColor: colors.surface },
  modeBtnSel: { backgroundColor: colors.brandPrimary },
  modeBtnText: { fontSize: 13, fontWeight: "600", color: colors.muted },
  modeBtnTextSel: { color: colors.onBrandPrimary },
  qtdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  plusBtn: {
    width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  modalInput: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  previewRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: spacing.sm,
  },
  primaryBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: "center", justifyContent: "center", marginTop: spacing.sm,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  toast: {
    position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.xxl,
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md,
    alignItems: "center",
    shadowColor: "#000", shadowOpacity: 0.3, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 10,
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
});
