import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { exportReportPdf } from "@/src/utils/export-report";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_MAX_WIDTH, WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type PedidoRow = {
  pedido: number; data: string; situacao: string; cliente: string;
  venda: number; desconto: number; custo: number; margem: number; margem_pct: number;
  origem?: "P" | "OS";
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
function round2(n: number): number {
  return Math.round((n || 0) * 100) / 100;
}

type RelResult = { vendedores: VendedorGroup[]; totais: Totais | null };

// Marca a origem (P/OS) em cada linha do grupo.
function tagOrigem(vendedores: VendedorGroup[], origem: "P" | "OS"): VendedorGroup[] {
  return (vendedores || []).map((g) => ({
    ...g,
    pedidos: (g.pedidos || []).map((p) => ({ ...p, origem })),
  }));
}

// Mescla os dois relatórios (Pedidos + OS) por vendedor, recalculando subtotais e totais.
function mergeReports(jp: { vendedores?: VendedorGroup[]; totais?: Totais } | null,
                      jo: { vendedores?: VendedorGroup[]; totais?: Totais } | null): RelResult {
  const map = new Map<string, VendedorGroup>();
  const addGroups = (groups: VendedorGroup[] | undefined, origem: "P" | "OS") => {
    (groups || []).forEach((g) => {
      const key = g.vendedor || "";
      const rows = (g.pedidos || []).map((p) => ({ ...p, origem }));
      const ex = map.get(key);
      if (!ex) {
        map.set(key, { ...g, pedidos: [...rows] });
      } else {
        ex.pedidos = [...ex.pedidos, ...rows];
        ex.sub_venda += g.sub_venda;
        ex.sub_desconto += g.sub_desconto;
        ex.sub_custo += g.sub_custo;
        ex.sub_margem += g.sub_margem;
      }
    });
  };
  addGroups(jp?.vendedores, "P");
  addGroups(jo?.vendedores, "OS");
  const vendedores = Array.from(map.values())
    .map((g) => ({
      ...g,
      sub_venda: round2(g.sub_venda),
      sub_desconto: round2(g.sub_desconto),
      sub_custo: round2(g.sub_custo),
      sub_margem: round2(g.sub_margem),
      sub_margem_pct: g.sub_venda > 0 ? round2((g.sub_margem / g.sub_venda) * 100) : 0,
    }))
    .sort((a, b) => b.sub_venda - a.sub_venda);
  const tp = jp?.totais; const to = jo?.totais;
  const venda = round2((tp?.venda || 0) + (to?.venda || 0));
  const desconto = round2((tp?.desconto || 0) + (to?.desconto || 0));
  const custo = round2((tp?.custo || 0) + (to?.custo || 0));
  const margem = round2((tp?.margem || 0) + (to?.margem || 0));
  const totais: Totais = {
    venda, desconto, custo, margem,
    margem_pct: venda > 0 ? round2((margem / venda) * 100) : 0,
    qtd_pedidos: (tp?.qtd_pedidos || 0) + (to?.qtd_pedidos || 0),
  };
  return { vendedores, totais };
}

export default function RelatorioDescontosScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const params = useLocalSearchParams<{ pedido?: string }>();
  const pedidoParam = params.pedido ? parseInt(String(params.pedido), 10) : null;

  const [conn, setConn] = useState<Conn | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(firstOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [clienteFiltro, setClienteFiltro] = useState<string>("");
  const [codigoFiltro, setCodigoFiltro] = useState<string>(pedidoParam ? String(pedidoParam) : "");
  const [origem, setOrigem] = useState<"all" | "P" | "OS">(pedidoParam ? "P" : "all");

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
      const qsBase = `servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${di}&data_fim=${df}`;
      const vendQs = vendedor ? `&vendedor=${encodeURIComponent(String(vendedor))}` : "";
      const cliQs = clienteFiltro.trim() ? `&cliente_nome=${encodeURIComponent(clienteFiltro.trim())}` : "";
      const codNum = parseInt(codigoFiltro, 10);
      const hasCod = Number.isFinite(codNum) && codNum > 0;

      const fetchPed = async () => {
        let url = `${base}/api/relatorios/descontos-margem?${qsBase}${vendQs}${cliQs}`;
        if (hasCod) url += `&pedido=${codNum}`;
        return (await fetch(url)).json();
      };
      const fetchOS = async () => {
        let url = `${base}/api/relatorios/os/descontos-margem?${qsBase}${vendQs}${cliQs}`;
        if (hasCod) url += `&os_cod=${codNum}`;
        return (await fetch(url)).json();
      };

      let result: RelResult;
      if (origem === "P") {
        const j = await fetchPed();
        if (!j?.success) { setError(j?.message || "Falha ao gerar relatório."); setVendedores([]); setTotais(null); return; }
        result = { vendedores: tagOrigem(j.vendedores || [], "P"), totais: j.totais || null };
      } else if (origem === "OS") {
        const j = await fetchOS();
        if (!j?.success) { setError(j?.message || "Falha ao gerar relatório."); setVendedores([]); setTotais(null); return; }
        result = { vendedores: tagOrigem(j.vendedores || [], "OS"), totais: j.totais || null };
      } else {
        const [jp, jo] = await Promise.all([fetchPed(), fetchOS()]);
        if (!jp?.success && !jo?.success) {
          setError(jp?.message || jo?.message || "Falha ao gerar relatório.");
          setVendedores([]); setTotais(null); return;
        }
        result = mergeReports(jp?.success ? jp : null, jo?.success ? jo : null);
      }
      setVendedores(result.vendedores);
      setTotais(result.totais);
      const exp: Record<string, boolean> = {};
      result.vendedores.forEach((g) => { exp[g.vendedor] = true; });
      setExpanded(exp);
    } catch (e) {
      setError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, codigoFiltro, clienteFiltro, origem]);

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
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
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

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
        {!pedidoParam ? (
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Origem</Text>
            <View style={styles.origemRow}>
              {([
                { key: "all" as const, label: "Todos" },
                { key: "P" as const, label: "Pedidos" },
                { key: "OS" as const, label: "OS" },
              ]).map((o) => {
                const sel = origem === o.key;
                return (
                  <Pressable
                    key={o.key}
                    onPress={() => setOrigem(o.key)}
                    style={({ pressed }) => [styles.origemChip, sel && styles.origemChipSel, pressed && { opacity: 0.8 }]}
                    testID={`rel-origem-${o.key}`}
                  >
                    <Text style={[styles.origemChipText, sel && styles.origemChipTextSel]}>{o.label}</Text>
                  </Pressable>
                );
              })}
            </View>
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
              allowClear
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
            <Text style={styles.fieldLabel}>Código (Pedido / OS) (opcional)</Text>
            <TextInput
              value={codigoFiltro}
              onChangeText={setCodigoFiltro}
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
                          key={`${p.origem || "P"}-${p.pedido}`}
                          onPress={() =>
                            p.origem === "OS"
                              ? router.push({ pathname: "/os-form", params: { codigo: String(p.pedido) } })
                              : router.push({ pathname: "/pedido-form", params: { pedido: String(p.pedido) } })
                          }
                          style={({ pressed }) => [styles.pedRow, pressed && { backgroundColor: colors.brandTertiary }]}
                          testID={`rel-pedido-${p.origem || "P"}-${p.pedido}`}
                        >
                          <View style={{ flex: 1 }}>
                            <Text style={styles.pedTitle}>{p.origem === "OS" ? "OS #" : "#"}{p.pedido} · {brDate(p.data)}</Text>
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
        </View>
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
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  origemRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.xs },
  origemChip: {
    flex: 1, alignItems: "center", justifyContent: "center",
    paddingVertical: 9, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  origemChipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  origemChipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  origemChipTextSel: { color: colors.brandPrimary, fontWeight: "700" },
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
