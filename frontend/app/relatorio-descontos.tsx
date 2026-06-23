import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { exportReportPdf } from "@/src/utils/export-report";
import { colors, radius, spacing } from "@/src/theme/colors";

type Conn = { servidor: string; banco: string; api: string };
type PedidoRow = {
  pedido: number; data: string; situacao: string; cliente: string;
  venda: number; desconto: number; custo: number; margem: number; margem_pct: number;
};
type VendedorGroup = {
  vendedor: string; vendedor_nome: string; pedidos: PedidoRow[];
  sub_venda: number; sub_desconto: number; sub_custo: number; sub_margem: number; sub_margem_pct: number;
};
type Totais = {
  venda: number; desconto: number; custo: number; margem: number; margem_pct: number; qtd_pedidos: number;
};

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
function brDate(iso: string): string {
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : iso;
}

export default function RelatorioDescontosScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ pedido?: string }>();
  const pedidoParam = params.pedido ? parseInt(String(params.pedido), 10) : null;

  const [conn, setConn] = useState<Conn | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(firstOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [clienteFiltro, setClienteFiltro] = useState<string>("");
  const [pedidoFiltro, setPedidoFiltro] = useState<string>(pedidoParam ? String(pedidoParam) : "");

  const [loading, setLoading] = useState(false);
  const [vendedores, setVendedores] = useState<VendedorGroup[]>([]);
  const [totais, setTotais] = useState<Totais | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [exporting, setExporting] = useState(false);

  // carrega conexão + funcionarios (vendedores)
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

  const buscar = useCallback(async (override?: { di?: string; df?: string }) => {
    if (!conn) return;
    const di = override?.di ?? dataIni;
    const df = override?.df ?? dataFim;
    if (!di || !df) { setError("Informe o período."); return; }
    setLoading(true);
    setError(null);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/descontos-margem?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${di}&data_fim=${df}`;
      if (vendedor) url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      if (clienteFiltro.trim()) url += `&cliente_nome=${encodeURIComponent(clienteFiltro.trim())}`;
      const pf = parseInt(pedidoFiltro, 10);
      if (Number.isFinite(pf) && pf > 0) url += `&pedido=${pf}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { setError(j?.message || "Falha ao gerar relatório."); setVendedores([]); setTotais(null); }
      else {
        setVendedores(j.vendedores || []);
        setTotais(j.totais || null);
        const exp: Record<string, boolean> = {};
        (j.vendedores || []).forEach((g: VendedorGroup) => { exp[g.vendedor] = true; });
        setExpanded(exp);
      }
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, pedidoFiltro, clienteFiltro]);

  // busca automática quando vier de um pedido específico (usa range amplo, sem depender do state)
  useEffect(() => {
    if (conn && pedidoParam) {
      setDataIni("2000-01-01");
      setDataFim("2100-12-31");
      buscar({ di: "2000-01-01", df: "2100-12-31" });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const margemColor = (pct: number) => (pct >= 30 ? colors.success : pct >= 10 ? colors.warning : colors.error);

  const headerTitle = useMemo(
    () => (pedidoParam ? `Análise do Pedido #${pedidoParam}` : "Descontos & Margem"),
    [pedidoParam]
  );

  const handleExport = useCallback(async () => {
    if (!totais) return;
    setExporting(true);
    setError(null);
    try {
      await exportReportPdf({
        titulo: headerTitle,
        periodo: pedidoParam ? undefined : `Período: ${brDate(dataIni || "")} a ${brDate(dataFim || "")}`,
        totais,
        vendedores,
      });
    } catch (e) {
      setError(`Falha ao exportar: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExporting(false);
    }
  }, [totais, vendedores, headerTitle, pedidoParam, dataIni, dataFim]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-descontos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relatorio-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>{headerTitle}</Text>
        {totais ? (
          <Pressable
            onPress={handleExport}
            disabled={exporting}
            hitSlop={12}
            style={({ pressed }) => [styles.backBtn, (pressed || exporting) && { opacity: 0.6 }]}
            testID="relatorio-export"
          >
            {exporting ? (
              <ActivityIndicator size="small" color={colors.onBrandPrimary} />
            ) : (
              <Ionicons name="share-outline" size={22} color={colors.onBrandPrimary} />
            )}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {!pedidoParam ? (
          <View style={styles.filters}>
            <View style={styles.dateRow}>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>De</Text>
                <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="rel-data-ini" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.fieldLabel}>Até</Text>
                <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="rel-data-fim" />
              </View>
            </View>
            <Text style={styles.fieldLabel}>Vendedor (opcional)</Text>
            <SelectField
              value={vendedor}
              onChange={setVendedor}
              options={vendedorOpts}
              placeholder="Todos os vendedores"
              modalTitle="Selecione o vendedor"
              testID="rel-vendedor"
            />
            <Text style={styles.fieldLabel}>Cliente (nome contém — opcional)</Text>
            <TextInput
              value={clienteFiltro}
              onChangeText={setClienteFiltro}
              placeholder="Ex.: João, Mercado…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoCapitalize="characters"
              testID="rel-cliente"
            />
            <Text style={styles.fieldLabel}>Código do pedido / pré-venda (opcional)</Text>
            <TextInput
              value={pedidoFiltro}
              onChangeText={setPedidoFiltro}
              keyboardType="number-pad"
              placeholder="Ex.: 1024"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="rel-pedido"
            />
            <Pressable
              onPress={buscar}
              disabled={loading}
              style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
              testID="rel-buscar"
            >
              {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="search" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.searchBtnText}>Gerar relatório</Text>
                </>
              )}
            </Pressable>
          </View>
        ) : loading ? (
          <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
        ) : null}

        {error ? (
          <View style={styles.errorBox} testID="rel-error">
            <Ionicons name="alert-circle-outline" size={16} color={colors.error} />
            <Text style={styles.errorText}>{error}</Text>
          </View>
        ) : null}

        {totais ? (
          <>
            <View style={styles.totaisCard} testID="rel-totais">
              <Text style={styles.totaisTitle}>
                Totais {pedidoParam ? "" : `· ${brDate(dataIni || "")} a ${brDate(dataFim || "")}`} ({totais.qtd_pedidos} pedido{totais.qtd_pedidos === 1 ? "" : "s"})
              </Text>
              <View style={styles.totaisGrid}>
                <View style={styles.totItem}><Text style={styles.totLbl}>Vendas</Text><Text style={styles.totVal}>{formatBRL(totais.venda)}</Text></View>
                <View style={styles.totItem}><Text style={styles.totLbl}>Descontos</Text><Text style={[styles.totVal, { color: colors.error }]}>{formatBRL(totais.desconto)}</Text></View>
                <View style={styles.totItem}><Text style={styles.totLbl}>Custo</Text><Text style={styles.totVal}>{formatBRL(totais.custo)}</Text></View>
                <View style={styles.totItem}>
                  <Text style={styles.totLbl}>Margem</Text>
                  <Text style={[styles.totVal, { color: margemColor(totais.margem_pct) }]}>
                    {formatBRL(totais.margem)} · {totais.margem_pct}%
                  </Text>
                </View>
              </View>
            </View>

            {vendedores.length === 0 ? (
              <Text style={styles.empty}>Nenhum pedido no período.</Text>
            ) : (
              vendedores.map((g) => (
                <View key={g.vendedor || "sem"} style={styles.groupCard} testID={`rel-grupo-${g.vendedor}`}>
                  <Pressable
                    onPress={() => setExpanded((e) => ({ ...e, [g.vendedor]: !e[g.vendedor] }))}
                    style={styles.groupHeader}
                  >
                    <Ionicons name={expanded[g.vendedor] ? "chevron-down" : "chevron-forward"} size={18} color={colors.brandPrimary} />
                    <View style={{ flex: 1 }}>
                      <Text style={styles.groupName} numberOfLines={1}>{g.vendedor_nome}</Text>
                      <Text style={styles.groupSub}>
                        {g.pedidos.length} ped. · Venda {formatBRL(g.sub_venda)} · Desc {formatBRL(g.sub_desconto)}
                      </Text>
                    </View>
                    <Text style={[styles.groupMargem, { color: margemColor(g.sub_margem_pct) }]}>{g.sub_margem_pct}%</Text>
                  </Pressable>

                  {expanded[g.vendedor] ? (
                    <View>
                      {g.pedidos.map((p) => (
                        <Pressable
                          key={p.pedido}
                          onPress={() => router.push({ pathname: "/pedido-form", params: { pedido: String(p.pedido) } })}
                          style={({ pressed }) => [styles.pedRow, pressed && { backgroundColor: colors.brandTertiary }]}
                          testID={`rel-pedido-${p.pedido}`}
                        >
                          <View style={{ flex: 1 }}>
                            <Text style={styles.pedTitle}>#{p.pedido} · {brDate(p.data)}</Text>
                            <Text style={styles.pedCliente} numberOfLines={1}>{p.cliente || "—"}</Text>
                            <Text style={styles.pedVals}>
                              Venda {formatBRL(p.venda)} · Desc {formatBRL(p.desconto)} · Custo {formatBRL(p.custo)}
                            </Text>
                          </View>
                          <View style={{ alignItems: "flex-end" }}>
                            <Text style={[styles.pedMargem, { color: margemColor(p.margem_pct) }]}>{formatBRL(p.margem)}</Text>
                            <Text style={[styles.pedMargemPct, { color: margemColor(p.margem_pct) }]}>{p.margem_pct}%</Text>
                          </View>
                        </Pressable>
                      ))}
                    </View>
                  ) : null}
                </View>
              ))
            )}
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  filters: { gap: spacing.sm },
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 13, marginTop: spacing.sm,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  errorBox: {
    flexDirection: "row", alignItems: "center", gap: 6, backgroundColor: "#fdecea",
    padding: spacing.sm, borderRadius: radius.sm,
  },
  errorText: { color: colors.error, fontSize: 12, flex: 1 },
  totaisCard: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  totaisTitle: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginBottom: spacing.sm },
  totaisGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  totItem: { width: "47%" },
  totLbl: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  totVal: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  groupCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, overflow: "hidden",
  },
  groupHeader: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md },
  groupName: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  groupSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  groupMargem: { fontSize: 16, fontWeight: "700" },
  pedRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  pedTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  pedCliente: { fontSize: 12, color: colors.muted, marginTop: 1 },
  pedVals: { fontSize: 11, color: colors.muted, marginTop: 2 },
  pedMargem: { fontSize: 14, fontWeight: "600" },
  pedMargemPct: { fontSize: 12, fontWeight: "500" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
