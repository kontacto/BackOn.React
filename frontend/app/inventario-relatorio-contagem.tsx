// Relatório de Contagem (Inventário) — lista em branco (código/descrição,
// sem quantidade) pro conferente escrever no papel a contagem física; o
// digitador depois passa esses números pro sistema via Digitação de
// Estoque. Legado: `FrmRelInvCon.frm` (Contagem por Nível). O Nível fica
// à ESCOLHA do usuário — 5 seletores em cascata (Nível 1→5, "TODOS" em
// qualquer posição), mesmo padrão do legado (List(0)..List(4)); escolher
// um nível reseta os níveis mais fundos. Reaproveita o mesmo endpoint já
// usado pelo cadastro de Grupo Mercadológico (`/api/tabelas/
// grupos-mercadologicos`) pra montar a árvore, em vez de duplicar a busca.
// Pedido explícito do usuário, 2026-07-23. Ver
// backend/services/inventario_service.py e PENDENCIAS.md > "Inventário".
//
// Disponível sempre que houver um balanço aberto — não é obrigatório usar
// (dá pra digitar direto sem imprimir nada), mas fica acessível a partir
// do Painel.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiBase, friendlyApiError } from "@/src/utils/api";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type ItemRelatorio = { codigo_interno: string; descricao: string; grupo: string };
type NivelRow = { nivel1: string; nivel2: string; nivel3: string; nivel4: string; nivel5: string; descricao: string };

const TIPOS = [
  { valor: 0, label: "Revenda" },
  { valor: 1, label: "Consumo" },
  { valor: 2, label: "Imobilizado" },
];

const TODOS_OPTION: SelectOption = { value: "", label: "TODOS" };

export default function InventarioRelatorioContagemScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Relatório de Contagem está disponível apenas no web."
        testID="inventario-relatorio-contagem-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [tiposSel, setTiposSel] = useState<number[]>([0, 1, 2]);
  const [somenteAtivos, setSomenteAtivos] = useState(true);
  const [gerando, setGerando] = useState(false);
  const [itens, setItens] = useState<ItemRelatorio[] | null>(null);

  const [arvoreNiveis, setArvoreNiveis] = useState<NivelRow[]>([]);
  // 5 posições, "" = TODOS naquele nível — mesmo formato do seletor em
  // cascata do legado (List(0)..List(4)).
  const [nivelSel, setNivelSel] = useState<string[]>(["", "", "", "", ""]);

  const podeGerar = can("INVENTARIO.REL_CONTAGEM");

  const bootConn = useCallback(async () => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (c) setConn(c);
    return c || null;
  }, [conn, router]);

  useEffect(() => {
    (async () => {
      const c = await bootConn();
      if (!c) return;
      const r = await apiGet(c, "/api/tabelas/grupos-mercadologicos");
      if (r?.success) setArvoreNiveis(r.items || []);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Opções de cada nível dependem do que já foi escolhido nos níveis
  // anteriores — mesma cascata do legado. Um "nó" do nível N é uma linha
  // com nivel1..nivelN preenchidos e o resto vazio (não pega netos).
  const opcoesPorNivel = useMemo(() => {
    const nivelCols = ["nivel1", "nivel2", "nivel3", "nivel4", "nivel5"] as const;
    const resultado: SelectOption[][] = [[], [], [], [], []];
    for (let n = 0; n < 5; n++) {
      // nível 0 sempre disponível; os demais só se o nível anterior já
      // tiver um valor específico escolhido (não "TODOS").
      if (n > 0 && !nivelSel[n - 1]) continue;
      const vistos = new Map<string, string>();
      for (const row of arvoreNiveis) {
        const anterioresBatem = nivelCols.slice(0, n).every((col, i) => row[col] === nivelSel[i]);
        if (!anterioresBatem) continue;
        const valor = row[nivelCols[n]];
        const proximoVazio = n === 4 || row[nivelCols[n + 1]] === "";
        if (valor && proximoVazio && !vistos.has(valor)) vistos.set(valor, row.descricao);
      }
      resultado[n] = Array.from(vistos.entries())
        .sort(([, a], [, b]) => a.localeCompare(b, "pt-BR"))
        .map(([valor, descricao]) => ({ value: valor, label: `${valor} - ${descricao}` }));
    }
    return resultado;
  }, [arvoreNiveis, nivelSel]);

  const setNivel = useCallback((idx: number, valor: string) => {
    setNivelSel((prev) => {
      const next = [...prev];
      next[idx] = valor;
      for (let i = idx + 1; i < 5; i++) next[i] = ""; // escolher um nível reseta os mais fundos
      return next;
    });
  }, []);

  const toggleTipo = useCallback((valor: number) => {
    setTiposSel((prev) => (prev.includes(valor) ? prev.filter((v) => v !== valor) : [...prev, valor]));
  }, []);

  const gerar = useCallback(async () => {
    const c = conn || (await bootConn());
    if (!c) return;
    if (tiposSel.length === 0) { fb.showError("Selecione ao menos um tipo de produto."); return; }
    setGerando(true);
    try {
      const r = await apiGet(c, "/api/inventario/relatorio-contagem", {
        tipos: tiposSel.join(","),
        somente_ativos: somenteAtivos,
        nivel1: nivelSel[0] || undefined,
        nivel2: nivelSel[1] || undefined,
        nivel3: nivelSel[2] || undefined,
        nivel4: nivelSel[3] || undefined,
        nivel5: nivelSel[4] || undefined,
      });
      if (!r?.success) {
        fb.showError(friendlyApiError(r, "Não foi possível gerar o relatório."));
        return;
      }
      setItens(r.itens || []);
    } finally {
      setGerando(false);
    }
  }, [conn, bootConn, tiposSel, somenteAtivos, nivelSel, fb]);

  const grupos = useMemo(() => {
    if (!itens) return [];
    const porGrupo = new Map<string, ItemRelatorio[]>();
    for (const it of itens) {
      if (!porGrupo.has(it.grupo)) porGrupo.set(it.grupo, []);
      porGrupo.get(it.grupo)!.push(it);
    }
    return Array.from(porGrupo.entries()).map(([grupo, lista]) => ({ grupo, lista }));
  }, [itens]);

  const imprimir = useCallback(async () => {
    if (!conn || !itens) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const blocos = grupos.map((g) => `
      <div style="margin-top:10px;font-weight:700;border-bottom:1px solid #999;padding-bottom:2px;">${escHtml(g.grupo)} (${g.lista.length})</div>
      ${g.lista.map((it) => `
        <div class="row3" style="border-bottom:1px dotted #ccc;padding:3px 0;">
          <span>${escHtml(it.codigo_interno)}</span>
          <span>${escHtml(it.descricao)}</span>
          <span>______________</span>
        </div>`).join("")}
    `).join("");
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, "Relatório de Contagem")}
      <div class="row3" style="font-weight:700;border-bottom:1px solid #333;padding-bottom:3px;">
        <span>Código</span><span>Descrição</span><span>Quantidade</span>
      </div>
      ${blocos || '<div class="mb">Nenhum produto encontrado para os filtros selecionados.</div>'}
    `;
    printHtml(html, "Relatório de Contagem");
  }, [conn, itens, grupos]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="inventario-relatorio-contagem-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Relatório de Contagem</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <Text style={styles.hint}>
              Gere e imprima esta lista em branco pro conferente escrever a quantidade contada de cada produto no
              papel — o digitador passa esses números pro sistema depois, na tela de Digitação de Estoque. Não é
              obrigatório usar; dá pra digitar direto sem imprimir nada.
            </Text>

            <Text style={styles.label}>Tipos de produto</Text>
            <View style={styles.chipsRow}>
              {TIPOS.map((t) => {
                const sel = tiposSel.includes(t.valor);
                return (
                  <Pressable
                    key={t.valor}
                    onPress={() => toggleTipo(t.valor)}
                    style={[styles.chip, sel && styles.chipSel]}
                    testID={`inventario-contagem-tipo-${t.valor}`}
                  >
                    <Ionicons name={sel ? "checkbox" : "square-outline"} size={14} color={sel ? "#fff" : colors.muted} />
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{t.label}</Text>
                  </Pressable>
                );
              })}
              <Pressable
                onPress={() => setSomenteAtivos((v) => !v)}
                style={[styles.chip, somenteAtivos && styles.chipSel]}
                testID="inventario-contagem-somente-ativos"
              >
                <Ionicons name={somenteAtivos ? "checkbox" : "square-outline"} size={14} color={somenteAtivos ? "#fff" : colors.muted} />
                <Text style={[styles.chipText, somenteAtivos && styles.chipTextSel]}>Somente produtos ativos</Text>
              </Pressable>
            </View>

            <Text style={styles.label}>Nível (opcional — filtra em cascata, deixe em TODOS pra não restringir)</Text>
            <View style={styles.nivelRow}>
              {[0, 1, 2, 3, 4].map((idx) => (
                <View key={idx} style={styles.nivelCol}>
                  <SelectField
                    label={`Nível ${idx + 1}`}
                    value={nivelSel[idx] || null}
                    onChange={(v) => setNivel(idx, (v as string) || "")}
                    options={[TODOS_OPTION, ...opcoesPorNivel[idx]]}
                    disabled={idx > 0 && !nivelSel[idx - 1]}
                    compactWeb
                    testID={`inventario-contagem-nivel-${idx + 1}`}
                  />
                </View>
              ))}
            </View>

            <View style={styles.actionsRow}>
              {podeGerar ? (
                <Pressable
                  style={[styles.primaryBtn, gerando && styles.btnDisabled]}
                  onPress={gerar}
                  disabled={gerando}
                  testID="inventario-contagem-gerar"
                >
                  {gerando ? (
                    <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                  ) : (
                    <Ionicons name="list-outline" size={16} color={colors.onBrandPrimary} />
                  )}
                  <Text style={styles.primaryBtnText}>{gerando ? "Gerando…" : "Gerar Relatório"}</Text>
                </Pressable>
              ) : null}
              {itens && itens.length > 0 ? (
                <Pressable style={styles.secondaryBtn} onPress={imprimir} testID="inventario-contagem-imprimir">
                  <Ionicons name="print-outline" size={16} color={colors.onSurface} />
                  <Text style={styles.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          {itens ? (
            <View style={[styles.card, { marginTop: spacing.md }]}>
              <Text style={styles.listTitle}>
                {itens.length} {itens.length === 1 ? "produto" : "produtos"} — {grupos.length} {grupos.length === 1 ? "grupo" : "grupos"}
              </Text>
              {grupos.map((g) => (
                <View key={g.grupo} style={{ marginTop: spacing.sm }}>
                  <Text style={styles.groupTitle}>{g.grupo} ({g.lista.length})</Text>
                  {g.lista.map((it) => (
                    <View key={it.codigo_interno} style={styles.listRow}>
                      <Text style={styles.listRowCodigo}>{it.codigo_interno}</Text>
                      <Text style={styles.listRowDescricao}>{it.descricao}</Text>
                    </View>
                  ))}
                </View>
              ))}
            </View>
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
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, gap: spacing.sm },
  hint: { fontSize: 12, color: colors.muted, lineHeight: 17 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 },
  nivelRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: 4 },
  nivelCol: { width: 190 },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 7, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  secondaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  btnDisabled: { opacity: 0.6 },
  listTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  groupTitle: {
    fontSize: 12, fontWeight: "700", color: colors.brandPrimary,
    textTransform: "uppercase", marginBottom: 2,
  },
  listRow: {
    flexDirection: "row", gap: spacing.sm,
    paddingVertical: 6,
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  listRowCodigo: { fontSize: 12, color: colors.muted, width: 60 },
  listRowDescricao: { fontSize: 13, color: colors.onSurface, flex: 1 },
});
