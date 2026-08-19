// Margem de Lucro (por produto) — migração de Gilson Pneus\FrmRelPecMLC.frm
// (Painel de Relatórios > Margem). "Foto" do catálogo: preço de venda ATUAL
// × custo de reposição ATUAL de cada produto Ativo, sem período — diferente
// do outro relatório do grupo ("Margem de Lucro x DAV",
// relatorio-margem-lucro.tsx), que é por período/DAV. Ver PENDENCIAS.md >
// "Painel de Relatórios (VB6)" > "Grupo Margem" pro rastreio completo.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import NiveisModal from "@/src/components/NiveisModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError, friendlyApiError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportMargemProdutoPdf, MargemProdutoPayload } from "@/src/utils/export-margem-produto";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

function moeda(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function pct(v: number | null): string {
  return v === null || v === undefined
    ? "—"
    : `${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}

export default function RelatorioMargemProdutoScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Connection | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);

  const [ordenarPor, setOrdenarPor] = useState<"codigo" | "descricao">("codigo");
  const [nivel, setNivel] = useState("");
  const [nivelLabel, setNivelLabel] = useState("");
  const [niveisOpen, setNiveisOpen] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<MargemProdutoPayload | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      setConn(c);
      setEmpresa(await fetchEmpresaHeader(c.api, c.servidor, c.banco));
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/relatorios/margem-produto?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&ordenar_por=${ordenarPor}`;
      if (nivel) url += `&nivel=${encodeURIComponent(nivel)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) {
        feedback.showError(friendlyApiError(j, "Falha ao gerar relatório."));
        setResultado(null);
      } else {
        setResultado({
          titulo: "Margem de Lucro",
          codigoLabel: j.codigo_label || "Código",
          nivelLabel,
          itens: j.itens || [],
          totalCusto: j.total_custo || 0,
          totalVenda: j.total_venda || 0,
          margemTotalPct: j.margem_total_pct ?? null,
          empresa,
        });
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, ordenarPor, nivel, nivelLabel, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportMargemProdutoPdf(resultado);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao imprimir."));
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("margem-de-lucro", [
      {
        name: "Margem de Lucro",
        rows: [
          ...resultado.itens.map((it) => ({
            [resultado.codigoLabel]: it.codigo,
            Descrição: it.descricao,
            "Preço Custo": it.custo,
            "Preço Venda": it.venda,
            "Margem %": it.margem_pct ?? "",
          })),
          {
            [resultado.codigoLabel]: "", Descrição: "TOTAL GERAL",
            "Preço Custo": resultado.totalCusto, "Preço Venda": resultado.totalVenda,
            "Margem %": resultado.margemTotalPct ?? "",
          },
        ],
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-margem-produto-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.headerBtn} testID="relmp-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Margem de Lucro</Text>
        <Pressable onPress={() => setAjudaOpen(true)} hitSlop={12} style={styles.headerBtn} testID="relmp-ajuda">
          <Ionicons name="information-circle-outline" size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Nível</Text>
            <Pressable style={styles.selector} onPress={() => setNiveisOpen(true)} testID="relmp-nivel">
              <Text style={nivel ? styles.selectorText : styles.selectorPlaceholder} numberOfLines={1}>
                {nivel ? nivelLabel : "Todos os níveis"}
              </Text>
              {nivel ? (
                <Pressable onPress={() => { setNivel(""); setNivelLabel(""); }} hitSlop={8} testID="relmp-nivel-clear">
                  <Ionicons name="close-circle" size={18} color={colors.muted} />
                </Pressable>
              ) : <Ionicons name="git-branch-outline" size={18} color={colors.muted} />}
            </Pressable>

            <Text style={styles.fieldLabel}>Ordenar por</Text>
            <View style={styles.chipRow}>
              {([{ k: "codigo" as const, l: "Código" }, { k: "descricao" as const, l: "Descrição" }]).map((o) => (
                <Pressable key={o.k} onPress={() => setOrdenarPor(o.k)} style={[styles.chip, ordenarPor === o.k && styles.chipSel]} testID={`relmp-ordenar-${o.k}`}>
                  <Text style={[styles.chipText, ordenarPor === o.k && styles.chipTextSel]}>{o.l}</Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar} disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="relmp-selecionar"
              >
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar</Text>
                  </>
                )}
              </Pressable>

              {resultado ? (
                <>
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="relmp-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="relmp-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              <View style={styles.tableHead}>
                <Text style={[styles.thCodigo]}>{resultado.codigoLabel}</Text>
                <Text style={[styles.thDesc]}>Descrição</Text>
                <Text style={[styles.thNum]}>Custo</Text>
                <Text style={[styles.thNum]}>Venda</Text>
                <Text style={[styles.thNum]}>Margem</Text>
              </View>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum produto encontrado.</Text>
              ) : resultado.itens.map((it, idx) => (
                <View key={`${it.codigo}-${idx}`} style={styles.row}>
                  <Text style={styles.tdCodigo} numberOfLines={1}>{it.codigo}</Text>
                  <Text style={styles.tdDesc} numberOfLines={1}>{it.descricao}</Text>
                  <Text style={styles.tdNum}>{moeda(it.custo)}</Text>
                  <Text style={styles.tdNum}>{moeda(it.venda)}</Text>
                  <Text style={[styles.tdNum, styles.tdMargem]}>{pct(it.margem_pct)}</Text>
                </View>
              ))}
              {resultado.itens.length > 0 ? (
                <View style={styles.rowTotal}>
                  <Text style={styles.rowTotalLabel}>TOTAL GERAL</Text>
                  <View style={{ flex: 1 }} />
                  <Text style={styles.rowTotalValue}>{moeda(resultado.totalCusto)}</Text>
                  <Text style={styles.rowTotalValue}>{moeda(resultado.totalVenda)}</Text>
                  <Text style={[styles.rowTotalValue, styles.tdMargem]}>{pct(resultado.margemTotalPct)}</Text>
                </View>
              ) : null}
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Escolha um nível (opcional) e clique em Selecionar.</Text>
          ) : null}
        </View>
      </ScrollView>

      <NiveisModal
        visible={niveisOpen}
        conn={conn}
        onClose={() => setNiveisOpen(false)}
        onPick={(codigo, label) => { setNivel(codigo); setNivelLabel(codigo ? label : ""); setNiveisOpen(false); }}
      />

      {ajudaOpen ? (
        <Pressable style={styles.ajudaBackdrop} onPress={() => setAjudaOpen(false)} testID="relmp-ajuda-backdrop">
          <Pressable style={styles.ajudaCard} onPress={() => {}}>
            <Text style={styles.ajudaTitle}>Como este relatório funciona</Text>
            <Text style={styles.ajudaText}>
              É uma FOTO do catálogo hoje — não considera vendas nem período. Compara, produto a
              produto (só produtos Ativos), o Preço de Venda atual com o Custo de Reposição atual.
            </Text>
            <Text style={styles.ajudaText}>
              Margem % = ((Venda − Custo) / Custo) × 100. Produtos com custo cadastrado como 0
              mostram "—" na margem (não dá pra calcular percentual sobre custo zero).
            </Text>
            <Text style={styles.ajudaText}>
              Nível filtra pra um ramo específico da Classificação Mercadológica — sem escolher
              nenhum, traz todos os produtos.
            </Text>
            <Pressable style={styles.ajudaFechar} onPress={() => setAjudaOpen(false)} testID="relmp-ajuda-fechar">
              <Text style={styles.ajudaFecharText}>Entendi</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  headerBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 16, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  selector: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 11, borderWidth: 1, borderColor: colors.border,
    minHeight: 42, gap: spacing.sm, maxWidth: 420,
  },
  selectorText: { flex: 1, fontSize: 14, color: colors.onSurface },
  selectorPlaceholder: { flex: 1, fontSize: 14, color: colors.muted },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  actionBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  actionBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  tableHead: { flexDirection: "row", paddingBottom: 6, borderBottomWidth: 2, borderBottomColor: colors.brandPrimary, gap: spacing.sm },
  thCodigo: { width: 90, fontSize: 10, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  thDesc: { flex: 1, fontSize: 10, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  thNum: { width: 90, fontSize: 10, fontWeight: "700", color: colors.muted, textTransform: "uppercase", textAlign: "right" },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  tdCodigo: { width: 90, fontSize: 12, color: colors.onSurface },
  tdDesc: { flex: 1, fontSize: 12, color: colors.onSurface },
  tdNum: { width: 90, fontSize: 12, color: colors.onSurface, textAlign: "right" },
  tdMargem: { color: colors.brandPrimary, fontWeight: "700" },
  rowTotal: {
    flexDirection: "row", alignItems: "center", paddingVertical: 8, marginTop: 4, gap: spacing.sm,
    borderTopWidth: 2, borderTopColor: colors.brandPrimary,
  },
  rowTotalLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowTotalValue: { width: 90, fontSize: 13, fontWeight: "700", color: colors.onSurface, textAlign: "right" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },

  ajudaBackdrop: {
    position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
    backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center", justifyContent: "center", padding: spacing.lg,
  },
  ajudaCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg,
    maxWidth: 480, width: "100%", gap: spacing.sm,
  },
  ajudaTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  ajudaText: { fontSize: 13, color: colors.onSurface, lineHeight: 19 },
  ajudaFechar: {
    alignSelf: "flex-end", marginTop: spacing.sm, backgroundColor: colors.brandPrimary,
    borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  ajudaFecharText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13 },
});
