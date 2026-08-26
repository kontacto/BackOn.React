// Apuração Fiscal — migração de Geral\FrmCalImp.frm. Relatório item-a-item
// de PIS/COFINS/ICMS/FCP (NFC-e ou NF-e) e rateio de DIFAL num período,
// com exportação pra Excel ("Gerar Planilha" no legado). Puramente
// consulta — sem Gravar/Excluir. Ver backend/services/apuracao_fiscal_
// service.py e PENDENCIAS.md > "Apuração Fiscal" pro rastreio completo.
// Rateio DIFAL (2026-08-24): o legado tinha o rótulo das colunas "$
// Origem"/"$ Destino" invertido em relação à fórmula — confirmado contra
// o Convênio ICMS 93/2015 (fonte oficial CONFAZ, Cláusula décima) que
// `percentual_origem` é a fatia retida pela UF de ORIGEM. Corrigido aqui
// — os rótulos "Origem"/"Destino" já são os reais, não precisam de aviso.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { apiGet, ConnLike, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = ConnLike;
type Modo = "NFCE" | "NFE" | "DIFAL";

type ItemRow = {
  documento: number | string | null;
  comanda: number | string | null;
  emissao: string | null;
  codigo_fab: string | null;
  descricao: string | null;
  cfop: string | null;
  cst: string | null;
  qtd: number;
  valor_unitario: number;
  valor_total: number;
  cst_pis: string | null;
  valor_pis: number;
  cst_cofins: string | null;
  valor_cofins: number;
  aliquota_icms: number;
  valor_icms: number;
  aliquota_fcp: number;
  valor_fcp: number;
  aliquota_fcp_retido: number;
  valor_fcp_retido: number;
  aliquota_interestadual?: number;
  aliquota_interna_destino?: number;
  percentual_origem?: number;
  valor_fcp_difal?: number;
  valor_origem?: number;
  valor_destino?: number;
};

type ColDef = { key: keyof ItemRow; label: string; width: number; money?: boolean; pct?: boolean; align?: "left" | "right" | "center" };

const COLS_COMUNS: ColDef[] = [
  { key: "documento", label: "Nº", width: 70, align: "center" },
  { key: "emissao", label: "Emissão", width: 90, align: "center" },
  { key: "codigo_fab", label: "Cód. Fab.", width: 110 },
  { key: "descricao", label: "Descrição", width: 220 },
  { key: "cfop", label: "CFOP", width: 60, align: "center" },
  { key: "cst", label: "CST", width: 60, align: "center" },
  { key: "qtd", label: "Qtd.", width: 60, align: "right" },
  { key: "valor_unitario", label: "$ Unitário", width: 90, align: "right", money: true },
  { key: "valor_total", label: "$ Total", width: 100, align: "right", money: true },
  { key: "cst_pis", label: "CST Pis", width: 70, align: "center" },
  { key: "valor_pis", label: "$ Pis", width: 85, align: "right", money: true },
  { key: "cst_cofins", label: "CST Cofins", width: 80, align: "center" },
  { key: "valor_cofins", label: "$ Cofins", width: 90, align: "right", money: true },
  { key: "aliquota_icms", label: "% Icms", width: 75, align: "right", pct: true },
  { key: "valor_icms", label: "$ Icms", width: 90, align: "right", money: true },
  { key: "aliquota_fcp", label: "% FCP", width: 70, align: "right", pct: true },
  { key: "valor_fcp", label: "$ FCP", width: 85, align: "right", money: true },
  { key: "aliquota_fcp_retido", label: "% FCP Ret.", width: 80, align: "right", pct: true },
  { key: "valor_fcp_retido", label: "$ FCP Ret.", width: 90, align: "right", money: true },
];

const COLS_DIFAL_EXTRA: ColDef[] = [
  { key: "aliquota_interestadual", label: "% Al. Inter.", width: 85, align: "right", pct: true },
  { key: "aliquota_interna_destino", label: "% Al. Dest.", width: 85, align: "right", pct: true },
  { key: "percentual_origem", label: "% Origem", width: 80, align: "right", pct: true },
  { key: "valor_fcp_difal", label: "$ FCP Partilha", width: 100, align: "right", money: true },
  { key: "valor_origem", label: "$ Origem", width: 90, align: "right", money: true },
  { key: "valor_destino", label: "$ Destino", width: 90, align: "right", money: true },
];

const COMANDA_COL: ColDef = { key: "comanda", label: "Comanda", width: 80, align: "center" };

function colsFor(modo: Modo): ColDef[] {
  if (modo === "NFCE") return [COLS_COMUNS[0], COMANDA_COL, ...COLS_COMUNS.slice(1)];
  if (modo === "DIFAL") return [...COLS_COMUNS, ...COLS_DIFAL_EXTRA];
  return COLS_COMUNS;
}

function fmtMoeda(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function fmtPct(v: number): string {
  return `${(v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
}
function brDate(iso: string | null): string {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}
function todayISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
function firstDayOfMonthISO(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-01`;
}

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "NFC-e / NF-e / Somente DIFAL", texto: "Escolhe a fonte dos dados: NFC-e (cupons fiscais), NF-e (notas de venda), ou Somente DIFAL — mostra só os itens de NF-e com partilha de ICMS entre estado de origem e destino (venda interestadual para consumidor final).", icon: { lib: "ion", name: "swap-horizontal-outline" } },
  { titulo: "% Icms (NFC-e)", texto: "Na NFC-e essa alíquota é calculada na hora (Valor Icms ÷ Base Icms), porque o cupom fiscal não guarda a alíquota separadamente — pode aparecer diferente de uma alíquota redonda por causa de arredondamento.", icon: { lib: "ion", name: "calculator-outline" } },
  { titulo: "$ Origem / $ Destino (Somente DIFAL)", texto: "Divisão do valor do DIFAL entre a UF de origem (onde a empresa fica) e a UF de destino (onde mora o cliente), conforme o cronograma oficial de partilha do Convênio ICMS 93/2015 — a fatia de cada uma muda ano a ano (ex.: 60% origem/40% destino em 2016, 20%/80% em 2018), nunca é fixa.", icon: { lib: "ion", name: "swap-horizontal-outline" } },
  { titulo: "Gerar Planilha", texto: "Exporta exatamente as linhas e totais mostrados na tela para um arquivo Excel (.xlsx).", icon: { lib: "ion", name: "download-outline" } },
];

export default function ApuracaoFiscalScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Apuração Fiscal está disponível apenas no web."
        testID="apuracao-fiscal-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [modo, setModo] = useState<Modo>("NFCE");
  const [dataIni, setDataIni] = useState<string | null>(firstDayOfMonthISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [cfop, setCfop] = useState("");
  const [loading, setLoading] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [itens, setItens] = useState<ItemRow[]>([]);
  const [totais, setTotais] = useState<Record<string, number>>({});
  const [consultado, setConsultado] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn({ servidor: c.servidor, banco: c.banco, api: c.api });
    })();
  }, [router]);

  const consultar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/apuracao-fiscal", {
        modo, data_ini: dataIni || undefined, data_fim: dataFim || undefined, cfop: cfop.trim() || undefined,
      });
      if (j?.success) {
        setItens(j.itens || []);
        setTotais(j.totais || {});
        setConsultado(true);
        if ((j.itens || []).length === 0) fb.showInfo(j.message || "Nenhum registro encontrado.");
      } else {
        setItens([]); setTotais({});
        fb.showError(friendlyApiError(j, "Falha ao apurar."));
      }
    } catch (e) {
      setItens([]); setTotais({});
      fb.showError(friendlyCatchError(e, "Falha ao apurar."));
    } finally {
      setLoading(false);
    }
  }, [conn, modo, dataIni, dataFim, cfop, fb]);

  const cols = colsFor(modo);

  const gerarPlanilha = () => {
    if (itens.length === 0) { fb.showInfo("Consulte antes de exportar."); return; }
    const rows = itens.map((it) => {
      const row: Record<string, unknown> = {};
      for (const c of cols) {
        const v = it[c.key];
        row[c.label] = c.key === "emissao" ? brDate(v as string | null) : (v ?? "");
      }
      return row;
    });
    const totalRow: Record<string, unknown> = {};
    for (const c of cols) totalRow[c.label] = "";
    const descCol = cols.find((c) => c.key === "descricao");
    totalRow[descCol ? descCol.label : cols[0].label] = "TOTAL GERAL";
    for (const c of cols) {
      const chave = `total_${c.key}`;
      if (chave in totais) totalRow[c.label] = totais[chave];
    }
    rows.push(totalRow);
    exportSheetsToXlsx(`apuracao-fiscal-${modo.toLowerCase()}`, [{ name: "Apuração Fiscal", rows }]);
  };

  const renderCell = (item: ItemRow, c: ColDef) => {
    const v = item[c.key];
    let text = String(v ?? "");
    if (c.key === "emissao") text = brDate(v as string | null);
    else if (c.money) text = fmtMoeda(v as number);
    else if (c.pct) text = fmtPct(v as number);
    return (
      <Text
        key={c.key as string}
        numberOfLines={2}
        style={[styles.cell, { width: c.width, textAlign: c.align || "left" }]}
      >
        {text}
      </Text>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="apuracao-fiscal-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Apuração Fiscal</Text>
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} testID="apuracao-fiscal-ajuda" />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterCard}>
          <View style={styles.modoRow}>
            {(["NFCE", "NFE", "DIFAL"] as Modo[]).map((m) => (
              <Pressable
                key={m}
                onPress={() => setModo(m)}
                style={[styles.modoBtn, modo === m && styles.modoBtnSel]}
                testID={`apuracao-fiscal-modo-${m}`}
              >
                <Text style={[styles.modoBtnText, modo === m && styles.modoBtnTextSel]}>
                  {m === "NFCE" ? "NFC-e" : m === "NFE" ? "NF-e" : "Somente DIFAL"}
                </Text>
              </Pressable>
            ))}
          </View>

          <View style={styles.rowFields}>
            <View style={styles.colDate}>
              <Text style={styles.label}>Período de</Text>
              <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="apuracao-fiscal-data-ini" />
            </View>
            <View style={styles.colDate}>
              <Text style={styles.label}>até</Text>
              <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="apuracao-fiscal-data-fim" />
            </View>
            <View style={styles.colCfop}>
              <Text style={styles.label}>CFOP</Text>
              <TextInput value={cfop} onChangeText={setCfop} style={styles.input} placeholder="opcional" placeholderTextColor={colors.muted} testID="apuracao-fiscal-cfop" />
            </View>
            <Pressable onPress={consultar} disabled={loading} style={[styles.primaryBtn, loading && { opacity: 0.6 }]} testID="apuracao-fiscal-consultar">
              {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Consultar</Text>}
            </Pressable>
            {can("APURACAO_FISCAL.EXPORTAR") ? (
              <Pressable onPress={gerarPlanilha} style={styles.secondaryBtn} testID="apuracao-fiscal-planilha">
                <Text style={styles.secondaryBtnText}>Gerar Planilha</Text>
              </Pressable>
            ) : null}
          </View>
        </View>

        {consultado && itens.length > 0 ? (
          <View style={styles.totaisCard}>
            <Text style={styles.totaisTitle}>Totais do período</Text>
            <View style={styles.totaisRow}>
              {cols.filter((c) => c.money).map((c) => (
                <View key={c.key as string} style={styles.totalItem}>
                  <Text style={styles.totalLabel}>{c.label}</Text>
                  <Text style={styles.totalValue}>{fmtMoeda(totais[`total_${c.key}`] || 0)}</Text>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        <View style={styles.tableArea}>
          <ScrollView horizontal showsHorizontalScrollIndicator>
            <View>
              <View style={styles.tableHeaderRow}>
                {cols.map((c) => (
                  <Text key={c.key as string} style={[styles.headerCell, { width: c.width, textAlign: c.align || "left" }]} numberOfLines={2}>
                    {c.label}
                  </Text>
                ))}
              </View>
              <FlatList
                data={itens}
                keyExtractor={(_, idx) => String(idx)}
                renderItem={({ item }) => (
                  <View style={styles.tableRow}>
                    {cols.map((c) => renderCell(item, c))}
                  </View>
                )}
                style={{ maxHeight: 520 }}
                initialNumToRender={40}
                windowSize={10}
                ListEmptyComponent={
                  !loading ? (
                    <Text style={styles.empty}>
                      {consultado ? "Nenhum registro encontrado." : "Escolha o período e clique em Consultar."}
                    </Text>
                  ) : null
                }
              />
            </View>
          </ScrollView>
        </View>
      </View>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Apuração Fiscal" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary, gap: spacing.sm },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { ...WEB_CONTENT_SHELL, maxWidth: 1500, flex: 1, paddingBottom: spacing.lg },
  filterCard: { ...WEB_FILTER_CARD, gap: spacing.sm },
  modoRow: { flexDirection: "row", gap: spacing.sm },
  modoBtn: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  modoBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  modoBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  modoBtnTextSel: { color: "#fff" },
  rowFields: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, flexWrap: "wrap" },
  colDate: { width: 150 },
  colCfop: { width: 110 },
  label: { fontSize: 11, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 13, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center" },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  secondaryBtn: { borderRadius: radius.pill, paddingVertical: 11, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.brandPrimary },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "700", fontSize: 13 },
  totaisCard: { ...WEB_FILTER_CARD, marginTop: spacing.sm, gap: spacing.xs },
  totaisTitle: { fontSize: 12, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  totaisRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.lg },
  totalItem: { minWidth: 100 },
  totalLabel: { fontSize: 11, color: colors.muted },
  totalValue: { fontSize: 15, fontWeight: "700", color: colors.onSurface, fontVariant: ["tabular-nums"] },
  tableArea: { marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, overflow: "hidden", flex: 1 },
  tableHeaderRow: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderBottomWidth: 1, borderBottomColor: colors.border },
  headerCell: { fontSize: 10.5, fontWeight: "700", color: colors.onSurface, paddingHorizontal: 6, paddingVertical: 8 },
  tableRow: { flexDirection: "row", borderBottomWidth: 1, borderBottomColor: colors.border },
  cell: { fontSize: 11.5, color: colors.onSurface, paddingHorizontal: 6, paddingVertical: 6 },
  empty: { textAlign: "center", color: colors.muted, padding: spacing.xl, width: 900 },
});
