// Movimentação de Produtos (Transações > Movimentações) — lançamento manual
// avulso de entrada/saída de estoque, fora do fluxo de Pedido/O.S./Notas
// Fiscais. Legado: `frmEntPro.frm`. Ver backend/services/
// movimentacao_produtos_service.py para as regras de negócio e as decisões
// conscientes em relação ao `.frm` original (Alterar não existe, Excluir
// reverte o estoque, etc.) — não duplicar esse raciocínio aqui.
import { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { styles as ps } from "@/src/components/pedido/styles";

type TipoMov = { codigo: string; descricao: string };
type MovItem = {
  id_mov: number; data: string; codigo_int: string; descricao: string | null;
  qtd: number; p_unit: number; tipo: string; tipo_descricao: string | null; num_nf: number | null;
};

function formatPreco(v: string | number): string {
  const n = typeof v === "number" ? v : parseFloat(v.replace(",", "."));
  if (!isFinite(n)) return "";
  return n.toFixed(2).replace(".", ",");
}

export default function MovimentacaoProdutosScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Movimentação de Produtos está disponível apenas no web."
        testID="movimentacao-produtos-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [tipos, setTipos] = useState<TipoMov[]>([]);
  const [dataSistema, setDataSistema] = useState<string | null>(null);

  const [data, setData] = useState<string | null>(null);
  const [tipo, setTipo] = useState<string | null>(null);
  const [codigoProduto, setCodigoProduto] = useState("");
  const [produtoDescricao, setProdutoDescricao] = useState("");
  const [produtoEstoque, setProdutoEstoque] = useState<number | null>(null);
  const [buscandoProduto, setBuscandoProduto] = useState(false);
  const [qtd, setQtd] = useState("");
  const [precoUnit, setPrecoUnit] = useState("");
  const [numNf, setNumNf] = useState("");
  const [saving, setSaving] = useState(false);

  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [ajudaSearch, setAjudaSearch] = useState("");
  const [ajudaResultados, setAjudaResultados] = useState<{ codigo: string; descricao: string }[]>([]);

  const [consultarOpen, setConsultarOpen] = useState(false);
  const [filtroTipo, setFiltroTipo] = useState<string | null>(null);
  const [filtroDataIni, setFiltroDataIni] = useState<string | null>(null);
  const [filtroDataFim, setFiltroDataFim] = useState<string | null>(null);
  const [filtroProduto, setFiltroProduto] = useState("");
  const [resultados, setResultados] = useState<MovItem[]>([]);
  const [buscandoConsulta, setBuscandoConsulta] = useState(false);

  const podeGravar = can("MOV_PRODUTOS.GRAVAR");
  const podeExcluir = can("MOV_PRODUTOS.EXCLUIR");

  const tipoOptions: SelectOption[] = tipos.map((t) => ({ value: t.codigo, label: `${t.codigo} - ${t.descricao}` }));

  const resetForm = useCallback(() => {
    setCodigoProduto(""); setProdutoDescricao(""); setProdutoEstoque(null);
    setQtd(""); setPrecoUnit(""); setNumNf("");
    setData(dataSistema);
    // Mantém o Tipo de Movimentação selecionado — diferente do legado
    // (que resetava pro primeiro item da lista a cada Incluir), decisão
    // deliberada: é comum lançar várias movimentações seguidas do MESMO
    // tipo (ex.: várias entradas de uma mesma nota), forçar reseleção a
    // cada uma seria só atrito sem ganho de correção de dados.
  }, [dataSistema]);

  const loadTipos = useCallback(async (c: Connection) => {
    const r = await apiGet(c, "/api/movimentacao-produtos/tipos");
    if (r?.success) {
      setTipos(r.tipos || []);
      setDataSistema(r.data_sistema || null);
      setData((d) => d || r.data_sistema || null);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      loadTipos(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const resolverProduto = useCallback(async (codigo: string) => {
    if (!conn) return;
    const termo = codigo.trim();
    if (!termo) { setProdutoDescricao(""); setProdutoEstoque(null); return; }
    setBuscandoProduto(true);
    try {
      const r = await apiGet(conn, `/api/movimentacao-produtos/produto/${encodeURIComponent(termo)}`);
      if (r?.success && r.found) {
        setCodigoProduto(r.codigo_int);
        setProdutoDescricao(r.descricao);
        setProdutoEstoque(r.qtd);
        setPrecoUnit(formatPreco(r.p_custo ?? 0));
      } else {
        setProdutoDescricao(""); setProdutoEstoque(null);
        fb.showError("Produto não cadastrado.");
      }
    } finally {
      setBuscandoProduto(false);
    }
  }, [conn, fb]);

  const buscarAjuda = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/produtos-servicos", { search: termo, tipo: "P", size: 30 });
    if (r?.items) {
      setAjudaResultados(r.items.map((it: any) => ({ codigo: it.codigo, descricao: it.descricao })));
    }
  }, [conn]);

  const handleIncluir = useCallback(async () => {
    if (!conn) return;
    if (!data) { fb.showError("Informe a data de entrada."); return; }
    if (!tipo) { fb.showError("Selecione o tipo de movimentação."); return; }
    if (!codigoProduto.trim()) { fb.showError("Informe o produto."); return; }
    const qtdNum = parseFloat(qtd.replace(",", "."));
    if (!qtdNum || qtdNum <= 0) { fb.showError("Informe uma quantidade válida."); return; }
    const precoNum = parseFloat((precoUnit || "0").replace(",", "."));

    setSaving(true);
    try {
      const r = await apiSend(conn, "/api/movimentacao-produtos", "POST", {
        data, tipo, codigo_int: codigoProduto.trim(), qtd: qtdNum, p_unit: precoNum,
        num_nf: numNf.trim() ? parseInt(numNf.trim(), 10) : null,
        ...auditCtx,
      });
      if (r?.success) {
        fb.showSuccess(`Estoque atualizado: ${r.estoque}`);
        resetForm();
      } else {
        fb.showError(r?.message || "Não foi possível gravar a movimentação.");
      }
    } finally {
      setSaving(false);
    }
  }, [conn, data, tipo, codigoProduto, qtd, precoUnit, numNf, auditCtx, fb, resetForm]);

  const buscarConsulta = useCallback(async () => {
    if (!conn) return;
    setBuscandoConsulta(true);
    try {
      const r = await apiGet(conn, "/api/movimentacao-produtos", {
        data_ini: filtroDataIni || undefined,
        data_fim: filtroDataFim || undefined,
        tipo: filtroTipo || undefined,
        codigo_int: filtroProduto.trim() || undefined,
      });
      setResultados(r?.items || []);
    } finally {
      setBuscandoConsulta(false);
    }
  }, [conn, filtroDataIni, filtroDataFim, filtroTipo, filtroProduto]);

  const abrirConsultar = useCallback(() => {
    setConsultarOpen(true);
    setFiltroTipo(null); setFiltroDataIni(null); setFiltroDataFim(null); setFiltroProduto("");
    setResultados([]);
    buscarConsulta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleExcluir = useCallback((item: MovItem) => {
    if (!conn) return;
    fb.showConfirm(
      `Confirma excluir a movimentação de ${item.qtd} un. de "${item.descricao || item.codigo_int}"? O estoque será revertido.`,
      async () => {
        const r = await apiSend(conn, `/api/movimentacao-produtos/${item.id_mov}/excluir`, "POST", auditCtx);
        if (r?.success) {
          fb.showSuccess("Movimentação excluída.");
          buscarConsulta();
        } else {
          fb.showError(r?.message || "Não foi possível excluir.");
        }
      },
      { destructive: true, confirmText: "Excluir" },
    );
  }, [conn, auditCtx, fb, buscarConsulta]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="movimentacao-produtos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Movimentação de Produtos</Text>
        <Pressable onPress={abrirConsultar} hitSlop={12} style={styles.back} testID="mov-produtos-consultar-btn">
          <Ionicons name="search-outline" size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Data de Entrada</Text>
                <WebDateField value={data} onChange={setData} max={dataSistema || undefined} testID="mov-produtos-data" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Tipo de Movimentação</Text>
                <SelectField
                  value={tipo}
                  onChange={(v) => setTipo(v as string | null)}
                  options={tipoOptions}
                  placeholder="Selecione…"
                  compactWeb
                  testID="mov-produtos-tipo"
                />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Código do Produto</Text>
                <View style={styles.inputWithBtn}>
                  <TextInput
                    style={[styles.input, { flex: 1, minWidth: 0 }]}
                    value={codigoProduto}
                    onChangeText={(v) => { setCodigoProduto(v); setProdutoDescricao(""); setProdutoEstoque(null); }}
                    onBlur={() => resolverProduto(codigoProduto)}
                    placeholder="Código interno ou de fábrica"
                    testID="mov-produtos-codigo"
                  />
                  <Pressable
                    style={styles.helpBtn}
                    onPress={() => { setAjudaOpen(true); setAjudaSearch(""); setAjudaResultados([]); }}
                    testID="mov-produtos-ajuda-btn"
                  >
                    <Ionicons name="list-outline" size={18} color={colors.brandPrimary} />
                  </Pressable>
                </View>
              </View>
            </View>
            {(buscandoProduto || produtoDescricao) ? (
              <Text style={styles.hint}>
                {buscandoProduto ? "Buscando…" : `${produtoDescricao}${produtoEstoque !== null ? ` — Estoque atual: ${produtoEstoque}` : ""}`}
              </Text>
            ) : null}

            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Quantidade</Text>
                <TextInput style={styles.input} value={qtd} onChangeText={setQtd} keyboardType="numeric" testID="mov-produtos-qtd" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Preço Unitário</Text>
                <TextInput
                  style={styles.input}
                  value={precoUnit}
                  onChangeText={setPrecoUnit}
                  onBlur={() => setPrecoUnit((v) => (v.trim() ? formatPreco(v) : v))}
                  keyboardType="numeric"
                  testID="mov-produtos-preco"
                />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Número da Nota Fiscal</Text>
                <TextInput style={styles.input} value={numNf} onChangeText={setNumNf} keyboardType="numeric" testID="mov-produtos-nf" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Série</Text>
                <TextInput style={[styles.input, styles.inputDisabled]} value="MV" editable={false} />
              </View>
            </View>

            {podeGravar ? (
              <Pressable
                style={[styles.incluirBtn, saving && { opacity: 0.6 }]}
                onPress={handleIncluir}
                disabled={saving}
                testID="mov-produtos-incluir-btn"
              >
                <Ionicons name="add-circle-outline" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.incluirBtnText}>{saving ? "Gravando…" : "Incluir"}</Text>
              </Pressable>
            ) : null}
          </View>
        </View>
      </ScrollView>

      {/* Ajuda — busca de produto */}
      <AppModal visible={ajudaOpen} transparent animationType="fade" onRequestClose={() => setAjudaOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Buscar Produto</Text>
              <Pressable onPress={() => setAjudaOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={ps.searchWrap}>
              <Ionicons name="search-outline" size={18} color={colors.muted} />
              <TextInput
                style={ps.searchInput}
                value={ajudaSearch}
                onChangeText={(v) => { setAjudaSearch(v); buscarAjuda(v); }}
                placeholder="Código ou descrição"
                autoFocus
                testID="mov-produtos-ajuda-search"
              />
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {ajudaResultados.map((it) => (
                <Pressable
                  key={it.codigo}
                  style={ps.resultRow}
                  onPress={() => { setCodigoProduto(it.codigo); setAjudaOpen(false); resolverProduto(it.codigo); }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={ps.resultNome}>{it.descricao}</Text>
                    <Text style={ps.resultSub}>{it.codigo}</Text>
                  </View>
                </Pressable>
              ))}
              {ajudaResultados.length === 0 ? <Text style={ps.emptyText}>Digite pra buscar.</Text> : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>

      {/* Consultar — histórico de movimentações lançadas por esta tela */}
      <AppModal visible={consultarOpen} transparent animationType="fade" onRequestClose={() => setConsultarOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact, { maxWidth: 760 }]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Consultar Movimentações</Text>
              <Pressable onPress={() => setConsultarOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>De</Text>
                <WebDateField
                  value={filtroDataIni}
                  onChange={(v) => {
                    setFiltroDataIni(v || null);
                    if (v) setFiltroDataFim(v);
                  }}
                  testID="mov-produtos-filtro-de"
                  onSubmitEditing={() => {
                    document.querySelector<HTMLInputElement>('[data-testid="mov-produtos-filtro-ate"]')?.focus();
                  }}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={filtroDataFim} onChange={setFiltroDataFim} testID="mov-produtos-filtro-ate" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Tipo</Text>
                <SelectField
                  value={filtroTipo}
                  onChange={(v) => setFiltroTipo(v as string | null)}
                  options={tipoOptions}
                  placeholder="Todos"
                  allowClear
                  compactWeb
                  testID="mov-produtos-filtro-tipo"
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Produto</Text>
                <TextInput style={styles.input} value={filtroProduto} onChangeText={setFiltroProduto} testID="mov-produtos-filtro-produto" />
              </View>
              <Pressable style={styles.buscarBtnInline} onPress={buscarConsulta} testID="mov-produtos-buscar-btn">
                <Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.buscarBtnInlineText}>{buscandoConsulta ? "Buscando…" : "Buscar"}</Text>
              </Pressable>
            </View>

            <ScrollView style={{ maxHeight: 380, marginTop: spacing.md }}>
              {resultados.map((item) => (
                <View key={item.id_mov} style={styles.resultRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultTitle}>
                      {item.descricao || item.codigo_int} — {item.qtd} un. × {item.p_unit}
                    </Text>
                    <Text style={styles.resultSub}>
                      {item.data} · {item.tipo_descricao || item.tipo}{item.num_nf ? ` · NF ${item.num_nf}` : ""}
                    </Text>
                  </View>
                  {podeExcluir ? (
                    <Pressable style={ps.deleteBtn} onPress={() => handleExcluir(item)} testID={`mov-produtos-excluir-${item.id_mov}`}>
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                    </Pressable>
                  ) : null}
                </View>
              ))}
              {resultados.length === 0 && !buscandoConsulta ? (
                <Text style={ps.emptyText}>Nenhuma movimentação encontrada.</Text>
              ) : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, gap: spacing.md },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  inputWithBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  helpBtn: {
    width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 180 },
  colNarrow: { width: 140 },
  colTiny: { width: 90 },
  buscarBtnInline: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingHorizontal: spacing.lg, paddingVertical: 11,
  },
  buscarBtnInlineText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  incluirBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    alignSelf: "flex-start",
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10, marginTop: spacing.sm,
  },
  incluirBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  resultRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
