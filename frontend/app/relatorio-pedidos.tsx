import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type Conn = { servidor: string; banco: string; api: string };
type PedidoItem = {
  pedido: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente: string; vendedor_cod: number | null; vendedor_nome: string;
};
type DescItem = {
  cod: number; tipo_label: string; descricao: string;
  percentual: number; valor_unitario: number; qtd: number; valor_total: number;
};
type MargemTotais = { venda: number; desconto: number; custo: number; margem: number; margem_pct: number };
type RelTotais = MargemTotais & { qtd_pedidos: number; produtos: number; servicos: number };
type Analise = { loading: boolean; error?: string | null; margem?: MargemTotais | null; descontos?: DescItem[] };

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];
const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function firstOfMonthISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function brDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

export default function RelatorioPedidosScreen() {
  const router = useRouter();
  const [conn, setConn] = useState<Conn | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(firstOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [situacao, setSituacao] = useState<string>("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pedidos, setPedidos] = useState<PedidoItem[]>([]);
  const [totais, setTotais] = useState<RelTotais | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [analises, setAnalises] = useState<Record<number, Analise>>({});

  // carrega conexão + vendedores
  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { setError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/funcionarios?servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`);
        const j = await r.json();
        const arr = Array.isArray(j) ? j : j?.items || [];
        setVendedorOpts(
          arr.map((f: { codigo: string | number; nome: string }) => ({
            value: String(f.codigo), label: (f.nome || "").trim() || `#${f.codigo}`,
          }))
        );
      } catch {
        // sem lista de vendedores
      }
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { setError("Informe o período."); return; }
    setLoading(true);
    setError(null);
    setExpandedId(null);
    setAnalises({});
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/pedidos?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (vendedor) url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      if (situacao) url += `&situacao=${encodeURIComponent(situacao)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { setError(j?.message || "Falha ao gerar relatório."); setPedidos([]); setTotais(null); }
      else { setPedidos(Array.isArray(j.pedidos) ? j.pedidos : []); setTotais(j.totais || null); }
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, situacao]);

  const loadAnalise = useCallback(async (pedido: number) => {
    if (!conn) return;
    setAnalises((prev) => ({ ...prev, [pedido]: { loading: true } }));
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const [mR, dR] = await Promise.all([
        fetch(`${base}/api/relatorios/descontos-margem?${qs}&data_ini=2000-01-01&data_fim=2100-12-31&pedido=${pedido}`),
        fetch(`${base}/api/pedidos/${pedido}/descontos?${qs}`),
      ]);
      const mJ = await mR.json();
      const dJ = await dR.json();
      setAnalises((prev) => ({
        ...prev,
        [pedido]: {
          loading: false,
          margem: mJ?.success ? (mJ.totais as MargemTotais) : null,
          descontos: dJ?.success && Array.isArray(dJ.items) ? (dJ.items as DescItem[]) : [],
        },
      }));
    } catch (e) {
      setAnalises((prev) => ({
        ...prev,
        [pedido]: { loading: false, error: e instanceof Error ? e.message : String(e) },
      }));
    }
  }, [conn]);

  const toggleExpand = useCallback((pedido: number) => {
    setExpandedId((cur) => {
      const next = cur === pedido ? null : pedido;
      if (next !== null && !analises[pedido]) loadAnalise(pedido);
      return next;
    });
  }, [analises, loadAnalise]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-pedidos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relpedidos-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Relatório de Pedidos</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
        {/* Filtros */}
        <View style={styles.filters}>
          <View style={styles.dateRow}>
            <View style={{ flex: 1 }}>
              <DateField label="De" value={dataIni} onChange={setDataIni} testID="relpedidos-di" />
            </View>
            <View style={{ flex: 1 }}>
              <DateField label="Até" value={dataFim} onChange={setDataFim} testID="relpedidos-df" />
            </View>
          </View>

          <Text style={styles.fieldLabel}>Vendedor (opcional)</Text>
          <SelectField
            value={vendedor}
            onChange={setVendedor}
            options={vendedorOpts}
            placeholder="Todos os vendedores"
            modalTitle="Selecione o vendedor"
            allowClear
            testID="relpedidos-vendedor"
          />

          <Text style={styles.fieldLabel}>Situação</Text>
          <View style={styles.sitRow}>
            {SITUACOES.map((s) => {
              const sel = situacao === s.value;
              return (
                <Pressable
                  key={s.value || "all"}
                  onPress={() => setSituacao(s.value)}
                  style={[styles.chip, sel && styles.chipSel]}
                  testID={`relpedidos-sit-${s.value || "todos"}`}
                >
                  <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
                </Pressable>
              );
            })}
          </View>

          <Pressable
            onPress={() => buscar()}
            disabled={loading}
            style={({ pressed }) => [styles.btn, (pressed || loading) && { opacity: 0.7 }]}
            testID="relpedidos-buscar"
          >
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : (
              <>
                <Ionicons name="search" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.btnText}>Gerar relatório</Text>
              </>
            )}
          </Pressable>
        </View>

        {error ? (
          <View style={styles.errorBox} testID="relpedidos-error">
            <Ionicons name="alert-circle-outline" size={16} color={colors.error} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {!loading && !error && pedidos.length === 0 ? (
          <Text style={styles.empty}>Nenhum pedido no período/filtros.</Text>
        ) : null}

        {totais && pedidos.length > 0 ? (
          <View style={styles.totaisBox} testID="relpedidos-totais">
            <Text style={styles.totaisTitle}>Totais do período</Text>
            <View style={styles.totaisRow}>
              <View style={[styles.tCard, { borderLeftColor: colors.brandPrimary }]}>
                <Text style={styles.tLabel}>Pedidos</Text>
                <Text style={styles.tValue} testID="relpedidos-tot-pedidos">{totais.qtd_pedidos}</Text>
              </View>
              <View style={[styles.tCard, { borderLeftColor: colors.success }]}>
                <Text style={styles.tLabel}>Margem média</Text>
                <Text style={[styles.tValue, { fontSize: 15 }]} testID="relpedidos-tot-margem">{formatBRL(totais.margem)}</Text>
                <Text style={styles.tSub}>{(totais.margem_pct || 0).toFixed(2).replace(".", ",")}%</Text>
              </View>
            </View>
            <View style={styles.totaisRow}>
              <View style={[styles.tCard, { borderLeftColor: colors.error }]}>
                <Text style={styles.tLabel}>Descontos</Text>
                <Text style={[styles.tValue, { fontSize: 14, color: colors.error }]} testID="relpedidos-tot-descontos">{formatBRL(totais.desconto)}</Text>
              </View>
              <View style={[styles.tCard, { borderLeftColor: "#1e88e5" }]}>
                <Text style={styles.tLabel}>Produtos</Text>
                <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-produtos">{formatBRL(totais.produtos)}</Text>
              </View>
              <View style={[styles.tCard, { borderLeftColor: colors.warning }]}>
                <Text style={styles.tLabel}>Serviços</Text>
                <Text style={[styles.tValue, { fontSize: 14 }]} testID="relpedidos-tot-servicos">{formatBRL(totais.servicos)}</Text>
              </View>
            </View>
          </View>
        ) : null}

        {pedidos.length > 0 ? (
          <Text style={styles.count}>{pedidos.length} pedido(s)</Text>
        ) : null}

        {pedidos.map((p) => {
          const open = expandedId === p.pedido;
          const an = analises[p.pedido];
          const sitColor = SIT_COLOR[p.situacao] || colors.muted;
          return (
            <View key={p.pedido} style={styles.card} testID={`relpedidos-row-${p.pedido}`}>
              <Pressable
                onPress={() => toggleExpand(p.pedido)}
                style={({ pressed }) => [styles.cardHead, pressed && { backgroundColor: colors.brandTertiary }]}
              >
                <View style={{ flex: 1 }}>
                  <View style={styles.cardTopRow}>
                    <Text style={styles.cardPedido}>#{p.pedido}</Text>
                    <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                      <Text style={[styles.sitTagText, { color: sitColor }]}>{p.situacao_label}</Text>
                    </View>
                  </View>
                  <Text style={styles.cardCliente} numberOfLines={1}>{p.cliente}</Text>
                  <Text style={styles.cardMeta} numberOfLines={1}>
                    {brDate(p.data)} · {p.vendedor_nome}
                  </Text>
                </View>
                <View style={{ alignItems: "flex-end" }}>
                  <Text style={styles.cardTotal}>{formatBRL(p.total)}</Text>
                  <Ionicons name={open ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
                </View>
              </Pressable>

              {open ? (
                <View style={styles.expand} testID={`relpedidos-expand-${p.pedido}`}>
                  {an?.loading ? (
                    <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.md }} />
                  ) : an?.error ? (
                    <Text style={styles.errorText}>Falha ao carregar análise: {an.error}</Text>
                  ) : (
                    <>
                      {/* Margem */}
                      <Text style={styles.expandTitle}>Margem</Text>
                      {an?.margem ? (
                        <View style={styles.margemGrid}>
                          <View style={styles.mItem}><Text style={styles.mLabel}>Venda</Text><Text style={styles.mVal}>{formatBRL(an.margem.venda)}</Text></View>
                          <View style={styles.mItem}><Text style={styles.mLabel}>Desconto</Text><Text style={[styles.mVal, { color: colors.error }]}>{formatBRL(an.margem.desconto)}</Text></View>
                          <View style={styles.mItem}><Text style={styles.mLabel}>Custo</Text><Text style={styles.mVal}>{formatBRL(an.margem.custo)}</Text></View>
                          <View style={styles.mItem}><Text style={styles.mLabel}>Margem</Text><Text style={[styles.mVal, { color: colors.success }]}>{formatBRL(an.margem.margem)} ({(an.margem.margem_pct || 0).toFixed(2).replace(".", ",")}%)</Text></View>
                        </View>
                      ) : (
                        <Text style={styles.muted}>Sem dados de margem.</Text>
                      )}

                      {/* Descontos concedidos */}
                      <Text style={[styles.expandTitle, { marginTop: spacing.md }]}>Descontos concedidos</Text>
                      {an?.descontos && an.descontos.length > 0 ? (
                        an.descontos.map((d) => (
                          <View key={d.cod} style={styles.descRow}>
                            <View style={{ flex: 1 }}>
                              <Text style={styles.descDesc} numberOfLines={1}>{d.descricao || "—"}</Text>
                              <Text style={styles.descMeta}>{d.tipo_label} · {(d.percentual || 0).toFixed(2).replace(".", ",")}% · qtd {d.qtd}</Text>
                            </View>
                            <Text style={[styles.descVal, { color: colors.error }]}>- {formatBRL(d.valor_total)}</Text>
                          </View>
                        ))
                      ) : (
                        <Text style={styles.muted}>Nenhum desconto concedido.</Text>
                      )}
                    </>
                  )}
                </View>
              ) : null}
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "600", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  filters: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm },
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4, marginTop: 4 },
  sitRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 12, color: colors.muted },
  chipTextSel: { color: colors.brandPrimary, fontWeight: "600" },
  btn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, marginTop: spacing.sm,
  },
  btnText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "600" },
  errorBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: "#FDE7E7", borderRadius: radius.md, padding: spacing.md,
  },
  errorText: { color: colors.error, fontSize: 13, flex: 1 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: spacing.lg },
  totaisBox: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginTop: spacing.sm },
  totaisTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  totaisRow: { flexDirection: "row", gap: spacing.sm },
  tCard: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.sm, borderLeftWidth: 3 },
  tLabel: { fontSize: 10, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.3 },
  tValue: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  tSub: { fontSize: 11, fontWeight: "600", color: colors.success },
  count: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, marginBottom: 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md },
  cardTopRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardPedido: { fontSize: 15, fontWeight: "700", color: colors.brandPrimary },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  sitTagText: { fontSize: 11, fontWeight: "600" },
  cardCliente: { fontSize: 14, color: colors.onSurface, marginTop: 3 },
  cardMeta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardTotal: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  expand: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surfaceSecondary },
  expandTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.xs },
  margemGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  mItem: { minWidth: "45%", flexGrow: 1 },
  mLabel: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.3 },
  mVal: { fontSize: 14, fontWeight: "600", color: colors.onSurface, marginTop: 1 },
  muted: { fontSize: 13, color: colors.muted },
  descRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  descDesc: { fontSize: 13, color: colors.onSurface },
  descMeta: { fontSize: 11, color: colors.muted, marginTop: 1 },
  descVal: { fontSize: 13, fontWeight: "600" },
});
