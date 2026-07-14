import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type OSItem = {
  os: number; data: string | null; situacao: string; situacao_label: string;
  total: number; cliente: string;
};
type Totais = {
  qtd_pedidos: number; venda: number; desconto: number; custo: number; margem: number; margem_pct: number;
};

const SIT_OPTS: SelectOption[] = [
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Pago" },
  { value: "C", label: "Cancelado" },
];

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
  const [y, m, d] = (iso || "").split("-");
  return d ? `${d}/${m}/${y}` : (iso || "—");
}

export default function RelatorioOSScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);
  const [dataIni, setDataIni] = useState<string | null>(firstOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [situacao, setSituacao] = useState<string | number | null>(null);

  const [loading, setLoading] = useState(false);
  const [osList, setOsList] = useState<OSItem[]>([]);
  const [totais, setTotais] = useState<Totais | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const r = await fetch(`${base}/api/funcionarios?servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`);
        const j = await r.json();
        const arr = Array.isArray(j) ? j : j?.items || [];
        setVendedorOpts(arr.map((f: { codigo: string | number; nome: string }) => ({
          value: String(f.codigo), label: (f.nome || "").trim() || `#${f.codigo}`,
        })));
      } catch {
        // sem lista
      }
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!dataIni || !dataFim) { feedback.showWarning("Informe o período."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/os?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&data_ini=${dataIni}&data_fim=${dataFim}`;
      if (vendedor) url += `&vendedor=${encodeURIComponent(String(vendedor))}`;
      if (situacao) url += `&situacao=${encodeURIComponent(String(situacao))}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setOsList([]); setTotais(null); }
      else { setOsList(Array.isArray(j.os) ? j.os : []); setTotais(j.totais || null); }
    } catch (e) {
      feedback.showError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, dataIni, dataFim, vendedor, situacao, feedback]);

  const margemColor = (pct: number) => (pct >= 30 ? colors.success : pct >= 10 ? colors.warning : colors.error);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-os-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="relos-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Relatório de OS</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
        <View style={[styles.filters, isWeb && styles.filtersWeb]}>
          <View style={styles.dateRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>De</Text>
              <DateField value={dataIni} onChange={setDataIni} allowClear={false} testID="relos-data-ini" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.fieldLabel}>Até</Text>
              <DateField value={dataFim} onChange={setDataFim} allowClear={false} testID="relos-data-fim" />
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
            testID="relos-vendedor"
          />
          <Text style={styles.fieldLabel}>Situação (opcional)</Text>
          <SelectField
            value={situacao}
            onChange={setSituacao}
            options={SIT_OPTS}
            placeholder="Todas as situações"
            modalTitle="Selecione a situação"
            allowClear
            testID="relos-situacao"
          />
          <Pressable
            onPress={buscar}
            disabled={loading}
            style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
            testID="relos-buscar"
          >
            {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <>
                <Ionicons name="search" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.searchBtnText}>Gerar relatório</Text>
              </>
            )}
          </Pressable>
        </View>

        {!loading && totais && osList.length === 0 ? (
          <Text style={styles.empty}>Nenhuma OS no período/filtros.</Text>
        ) : null}

        {totais && osList.length > 0 ? (
          <View style={styles.totaisCard} testID="relos-totais">
            <Text style={styles.totaisTitle}>
              Totais · {brDate(dataIni)} a {brDate(dataFim)} ({totais.qtd_pedidos} OS)
            </Text>
            <View style={styles.totaisGrid}>
              <View style={styles.totItem}><Text style={styles.totLbl}>Vendas</Text><Text style={styles.totVal}>{formatBRL(totais.venda)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>Descontos</Text><Text style={[styles.totVal, { color: colors.error }]}>{formatBRL(totais.desconto)}</Text></View>
              <View style={styles.totItem}><Text style={styles.totLbl}>Custo</Text><Text style={styles.totVal}>{formatBRL(totais.custo)}</Text></View>
              <View style={styles.totItem}>
                <Text style={styles.totLbl}>Margem</Text>
                <Text style={[styles.totVal, { color: margemColor(totais.margem_pct) }]}>
                  {formatBRL(totais.margem)} · {(totais.margem_pct || 0).toFixed(2).replace(".", ",")}%
                </Text>
              </View>
            </View>
          </View>
        ) : null}

        {osList.map((o) => (
          <Pressable
            key={o.os}
            onPress={() => router.push({ pathname: "/os-form", params: { codigo: String(o.os) } })}
            style={({ pressed }) => [styles.osCard, pressed && { backgroundColor: colors.brandTertiary }]}
            testID={`relos-os-${o.os}`}
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.osTitle}>OS #{o.os} · {brDate(o.data)}</Text>
              <Text style={styles.osCliente} numberOfLines={1}>{o.cliente || "—"}</Text>
              <Text style={styles.osSit}>{o.situacao_label}</Text>
            </View>
            <Text style={styles.osTotal}>{formatBRL(o.total)}</Text>
          </Pressable>
        ))}
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
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 13, marginTop: spacing.sm,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  totaisCard: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  totaisTitle: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginBottom: spacing.sm },
  totaisGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  totItem: { width: "47%" },
  totLbl: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  totVal: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  osCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  osTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  osCliente: { fontSize: 12, color: colors.muted, marginTop: 1 },
  osSit: { fontSize: 11, color: colors.brandPrimary, marginTop: 2, fontWeight: "500" },
  osTotal: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
