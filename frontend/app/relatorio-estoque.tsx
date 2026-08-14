// Estoque — migração de FrmRelPecNiv.frm (Painel de Relatórios >
// Estoque). Detalhe produto-a-produto dentro de um nível escolhido
// (complementar ao agregado "Estoque por Nível"). Só produtos ativos.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import NiveisModal from "@/src/components/NiveisModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { exportEstoquePdf, EstoquePayload } from "@/src/utils/export-estoque";
import { fetchEmpresaHeader, EmpresaHeader } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Ordenacao = "codigo" | "descricao";

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

export default function RelatorioEstoqueScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [nivelCodigo, setNivelCodigo] = useState("");
  const [nivelLabel, setNivelLabel] = useState("");
  const [modalNiveisAberto, setModalNiveisAberto] = useState(false);
  const [ordenacao, setOrdenacao] = useState<Ordenacao>("codigo");

  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<EstoquePayload | null>(null);
  const [empresa, setEmpresa] = useState<EmpresaHeader | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      setEmpresa(await fetchEmpresaHeader(cc.api, cc.servidor, cc.banco));
    })();
  }, [router]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!nivelCodigo) { feedback.showWarning("Selecione o nível."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const url = `${base}/api/relatorios/estoque?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&nivel=${encodeURIComponent(nivelCodigo)}&ordenar_por=${ordenacao}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao gerar relatório."); setResultado(null); }
      else setResultado({ titulo: "Estoque", nivelLabel, itens: j.itens || [], empresa });
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, nivelCodigo, nivelLabel, ordenacao, empresa, feedback]);

  const imprimir = useCallback(async () => {
    if (!resultado) return;
    try {
      await exportEstoquePdf(resultado);
    } catch (e) {
      feedback.showError(`Falha ao imprimir: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [resultado, feedback]);

  const gerarPlanilha = useCallback(() => {
    if (!resultado) return;
    exportSheetsToXlsx("estoque", [
      {
        name: "Estoque",
        rows: resultado.itens.map((i) => ({
          Código: i.codigo_int, Descrição: i.descricao, Qtd: i.quant,
          "Custo Invent.": i.custo_inventario, "Preço Venda": i.p_venda,
          Área: i.area, Prateleira: i.prateleira, Escaninho: i.escaninho,
        })),
      },
    ]);
  }, [resultado]);

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="relatorio-estoque-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="rele-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Estoque</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.fieldLabel}>Nível</Text>
            <Pressable onPress={() => setModalNiveisAberto(true)} style={styles.nivelBox} testID="rele-definir-nivel">
              <Text style={styles.nivelBoxText} numberOfLines={2}>{nivelLabel || "Selecionar Nível…"}</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.muted} />
            </Pressable>

            <Text style={styles.fieldLabel}>Ordenar por</Text>
            <View style={styles.chipRow}>
              <Pressable onPress={() => setOrdenacao("codigo")} style={[styles.chip, ordenacao === "codigo" && styles.chipSel]} testID="rele-ord-codigo">
                <Text style={[styles.chipText, ordenacao === "codigo" && styles.chipTextSel]}>Código</Text>
              </Pressable>
              <Pressable onPress={() => setOrdenacao("descricao")} style={[styles.chip, ordenacao === "descricao" && styles.chipSel]} testID="rele-ord-descricao">
                <Text style={[styles.chipText, ordenacao === "descricao" && styles.chipTextSel]}>Descrição</Text>
              </Pressable>
            </View>

            <View style={styles.actionsRow}>
              <Pressable
                onPress={buscar}
                disabled={loading}
                style={({ pressed }) => [styles.searchBtn, (pressed || loading) && { opacity: 0.85 }]}
                testID="rele-selecionar"
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
                  <Pressable onPress={imprimir} style={styles.actionBtn} testID="rele-imprimir">
                    <Ionicons name="print-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Imprimir</Text>
                  </Pressable>
                  <Pressable onPress={gerarPlanilha} style={styles.actionBtn} testID="rele-planilha">
                    <Ionicons name="grid-outline" size={15} color={colors.brandPrimary} />
                    <Text style={styles.actionBtnText}>Gerar Planilha</Text>
                  </Pressable>
                </>
              ) : null}
            </View>
          </View>

          {resultado ? (
            <View style={styles.card}>
              {resultado.itens.length === 0 ? (
                <Text style={styles.empty}>Nenhum produto no nível selecionado.</Text>
              ) : resultado.itens.map((i) => (
                <View key={i.codigo_int} style={styles.row}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowLabel} numberOfLines={1}>{i.descricao}</Text>
                    <Text style={styles.rowMeta}>
                      {i.codigo_int} · Qtd {i.quant} · {[i.area, i.prateleira, i.escaninho].filter(Boolean).join(" / ") || "sem localização"}
                    </Text>
                  </View>
                  <View style={{ alignItems: "flex-end" }}>
                    <Text style={styles.rowValue}>{formatBRL(i.p_venda)}</Text>
                    <Text style={styles.rowValueSecondary}>Custo {formatBRL(i.custo_inventario)}</Text>
                  </View>
                </View>
              ))}
            </View>
          ) : !loading ? (
            <Text style={styles.empty}>Selecione o nível e clique em Selecionar.</Text>
          ) : null}
        </View>
      </ScrollView>

      {conn ? (
        <NiveisModal
          visible={modalNiveisAberto}
          conn={conn}
          onClose={() => setModalNiveisAberto(false)}
          onPick={(codigo, label) => {
            setNivelCodigo(codigo);
            setNivelLabel(label);
            setModalNiveisAberto(false);
          }}
        />
      ) : null}
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
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  nivelBox: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    height: 44, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, backgroundColor: colors.surface,
  },
  nivelBoxText: { flex: 1, fontSize: 13, color: colors.onSurface },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
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
  row: { flexDirection: "row", alignItems: "center", paddingVertical: 6, gap: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface },
  rowMeta: { fontSize: 10, color: colors.muted, marginTop: 2 },
  rowValue: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  rowValueSecondary: { fontSize: 10, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: 24 },
});
