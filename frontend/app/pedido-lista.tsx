// Lista de Pedido COMPARTILHADA por todas as versões de Pedido exceto o
// Pedido Bar (que tem sua própria lista, `app/pedidos.tsx`, com o painel de
// colunas Mesa/Comanda/Balcão/Entrega/Fiado — específico do segmento Bar).
// Hoje usada só pelo Pedido Geral (`pedido-geral.tsx`, ex-"Pedido
// Completo"), mas desenhada pra ser reaproveitada por futuras versões de
// Pedido que não sejam do segmento Bar — decisão explícita do usuário,
// 2026-07-20 ("por enquanto a lista de pedido Bar será exclusiva para o
// mesmo, as outras versões de pedido compartilharão a mesma tela de Lista
// de Pedido"). Reaproveita o mesmo endpoint `POST /api/pedidos` (já suporta
// busca/situação/vendedor/período) que `pedidos.tsx` usa — sem view por
// colunas nem totalizadores de tipo, sem os filtros específicos de Bar
// (tipo de cliente, data de entrega, ordenar por).
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;
type PedidoRow = {
  pedido: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente_nome: string; vendedor_nome: string;
};

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];

export default function PedidoListaScreen() {
  const router = useRouter();
  const { can, isManagerFuncao, isMaster, usuarioCodigo } = usePermissions();
  const feedback = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Esta lista de Pedidos está disponível apenas no web." testID="pedido-lista-web-only" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [ownVendedor, setOwnVendedor] = useState<number | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [items, setItems] = useState<PedidoRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);

  const usuarioCod = isMaster ? -2 : (usuarioCodigo ?? -2);
  const effVendedor = isManagerFuncao
    ? (vendedor == null ? "all" : String(vendedor))
    : (ownVendedor != null ? String(ownVendedor) : "-1");

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      const own = (s.funcionario as { codigo_int?: number } | null)?.codigo_int;
      setOwnVendedor(own ?? null);
      if (c && isManagerFuncao) {
        try {
          const base = c.api.replace(/\/+$/, "");
          const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const j = await fetch(`${base}/api/funcionarios?${qs}`).then((r) => r.json());
          const fs: { codigo: number; nome: string; nome_guerra: string }[] = Array.isArray(j?.items) ? j.items : [];
          setVendedorOpts(fs.map((f) => ({ value: f.codigo, label: f.nome_guerra || f.nome || `#${f.codigo}` })));
        } catch {
          // silencioso
        }
      }
      setLoadingConn(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isManagerFuncao]);

  const load = useCallback(async (c: Conn, term: string, sit: string, vend: string, di: string | null, df: string | null, pg: number, append: boolean) => {
    if (aborter.current) aborter.current.abort();
    const ac = new AbortController();
    aborter.current = ac;
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/pedidos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: c.servidor, banco: c.banco,
          search: term, situacao: sit, vendedor: vend,
          data_ini: di, data_fim: df, page: pg, size: 20,
        }),
        signal: ac.signal,
      });
      const j = await r.json();
      if (!j?.success) {
        feedback.showError(j?.message || "Falha na consulta.");
        if (!append) setItems([]);
      } else {
        setItems((prev) => (append ? [...prev, ...j.items] : j.items));
        setTotal(j.total || 0);
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError") {
        feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    } finally {
      if (aborter.current === ac) setLoading(false);
    }
  }, [feedback]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => { setPage(1); load(conn, search, situacao, effVendedor, dataIni, dataFim, 1, false); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, search, situacao, effVendedor, dataIni, dataFim]);

  const loadMore = () => {
    if (!conn || loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(conn, search, situacao, effVendedor, dataIni, dataFim, next, true);
  };

  const abrirPedido = (item: PedidoRow) => {
    router.push({ pathname: "/pedido-geral", params: { pedido: String(item.pedido) } } as never);
  };

  const canGravar = can("PEDIDO_COMP.GRAVAR");

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="pedido-lista-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="pedido-lista-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>Pedidos ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.shellOuter}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={search}
                onChangeText={setSearch}
                placeholder="Buscar por cliente ou nº do pedido…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="pedido-lista-search"
              />
            </View>
            <View style={styles.chipsRow}>
              {SITUACOES.map((s) => {
                const sel = situacao === s.value;
                return (
                  <Pressable
                    key={s.value || "all"}
                    onPress={() => setSituacao(s.value)}
                    style={[styles.chip, sel && styles.chipSel]}
                    testID={`pedido-lista-chip-${s.value || "all"}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
                  </Pressable>
                );
              })}
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>De</Text>
                <WebDateField
                  value={dataIni}
                  onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }}
                  testID="pedido-lista-data-ini"
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="pedido-lista-data-fim" />
              </View>
              {isManagerFuncao ? (
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Vendedor</Text>
                  <SelectField
                    value={vendedor}
                    onChange={setVendedor}
                    options={vendedorOpts}
                    placeholder="Todos os vendedores"
                    modalTitle="Selecionar vendedor"
                    allowClear
                    compactWeb
                    testID="pedido-lista-vendedor"
                  />
                </View>
              ) : null}
            </View>
          </View>

          {loading && items.length === 0 ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          <FlatList
            data={items}
            keyExtractor={(i) => String(i.pedido)}
            contentContainerStyle={styles.listContent}
            onEndReached={loadMore}
            onEndReachedThreshold={0.4}
            ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum pedido encontrado.</Text> : null}
            renderItem={({ item }) => (
              <Pressable onPress={() => abrirPedido(item)} style={styles.row} testID={`pedido-lista-${item.pedido}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowTitle} numberOfLines={1}>#{item.pedido} · {item.cliente_nome || "(sem cliente)"}</Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    {item.data ? formatDateBR(item.data) : "—"} · {item.vendedor_nome || "—"} · {item.situacao_label}
                  </Text>
                </View>
                <Text style={styles.rowValor}>{formatBRL(item.total)}</Text>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            )}
          />
        </View>
      </View>

      {canGravar ? (
        <Pressable onPress={() => router.push("/pedido-geral" as never)} style={styles.fab} testID="pedido-lista-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  shellOuter: { flex: 1, alignItems: "center" },
  shell: { ...WEB_CONTENT_SHELL, flex: 1 },
  scrollWeb: WEB_SCROLL_CENTER,
  filterCard: { ...WEB_FILTER_CARD, marginTop: spacing.md, marginBottom: spacing.sm, gap: spacing.sm },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" },
  colNarrow: { width: 160 },
  colFlex: { flex: 1, minWidth: 200 },
  label: { fontSize: 11, color: colors.muted, marginBottom: 4 },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: 100, gap: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, minHeight: 72,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
});
