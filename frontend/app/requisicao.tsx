// Requisição (Transações > Movimentações) — pedido interno de
// produtos/serviços com fechamento (baixa de estoque), reabertura e
// cancelamento. Legado: `FrmManReq.frm`. Ver backend/services/
// requisicao_service.py para as regras de negócio e as decisões
// conscientes em relação ao `.frm` original (fluxo de autorização em 2
// etapas é código morto no legado, NFe/vínculo O.S./Projeto fora de
// escopo) — não duplicar esse raciocínio aqui.
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
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, apiBase } from "@/src/utils/api";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { styles as ps, SIT_COLOR } from "@/src/components/pedido/styles";

type Item = { cod: number; prod: string; descricao: string | null; qtd: number; p_unit: number };
type ReqListItem = {
  codigo: number; data: string; descricao: string | null; situacao: string;
  usuario_nome: string | null; total: number;
};

const SIT_LABEL: Record<string, string> = { A: "Aberta", F: "Fechada", C: "Cancelada" };

function formatPreco(v: string | number): string {
  const n = typeof v === "number" ? v : parseFloat(v.replace(",", "."));
  if (!isFinite(n)) return "";
  return n.toFixed(2).replace(".", ",");
}

function money(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function RequisicaoScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Requisição está disponível apenas no web."
        testID="requisicao-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  const [codigo, setCodigo] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string | null>(null);
  const [data, setData] = useState<string | null>(null);
  const [usuarioNome, setUsuarioNome] = useState<string>("");
  const [descricao, setDescricao] = useState("");
  const [itens, setItens] = useState<Item[]>([]);

  const [produtoCodigo, setProdutoCodigo] = useState("");
  const [produtoDescricao, setProdutoDescricao] = useState("");
  const [produtoEstoque, setProdutoEstoque] = useState<number | null>(null);
  const [buscandoProduto, setBuscandoProduto] = useState(false);
  const [qtd, setQtd] = useState("");
  const [precoUnit, setPrecoUnit] = useState("");
  const [saving, setSaving] = useState(false);

  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [ajudaSearch, setAjudaSearch] = useState("");
  const [ajudaResultados, setAjudaResultados] = useState<{ codigo: string; descricao: string }[]>([]);

  const [consultarOpen, setConsultarOpen] = useState(false);
  const [filtroSituacoes, setFiltroSituacoes] = useState<string[]>(["A", "F", "C"]);
  const [filtroDataIni, setFiltroDataIni] = useState<string | null>(null);
  const [filtroDataFim, setFiltroDataFim] = useState<string | null>(null);
  const [filtroDescricao, setFiltroDescricao] = useState("");
  const [resultados, setResultados] = useState<ReqListItem[]>([]);
  const [buscandoConsulta, setBuscandoConsulta] = useState(false);

  const situacaoAberta = !situacao || situacao === "A";
  const podeGravar = can("REQUISICAO.GRAVAR") && situacaoAberta;
  const podeExcluir = can("REQUISICAO.EXCLUIR") && situacaoAberta;
  const podeFechar = can("REQUISICAO.FECHAR") && situacao === "A";
  const podeReabrir = can("REQUISICAO.REABRIR") && situacao === "F";
  const podeCancelar = can("REQUISICAO.CANCELAR") && (situacao === "A" || situacao === "F");
  const podeImprimir = can("REQUISICAO.IMPRIMIR") && !!codigo;

  const total = itens.reduce((s, it) => s + it.qtd * it.p_unit, 0);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const handleNova = useCallback(() => {
    setCodigo(null); setSituacao(null); setData(null); setUsuarioNome(""); setDescricao("");
    setItens([]);
    setProdutoCodigo(""); setProdutoDescricao(""); setProdutoEstoque(null);
    setQtd(""); setPrecoUnit("");
  }, []);

  const carregarRequisicao = useCallback(async (c: Connection, cod: number) => {
    const r = await apiGet(c, `/api/requisicoes/${cod}`);
    if (r?.success) {
      const it = r.item;
      setCodigo(it.codigo);
      setSituacao(it.situacao || "A");
      setData(it.data);
      setUsuarioNome(it.usuario_nome || "");
      setDescricao(it.descricao || "");
      setItens(it.itens || []);
    } else {
      fb.showError(r?.message || "Não foi possível carregar a requisição.");
    }
  }, [fb]);

  const resolverProduto = useCallback(async (termo: string) => {
    if (!conn) return;
    const t = termo.trim();
    if (!t) { setProdutoDescricao(""); setProdutoEstoque(null); return; }
    setBuscandoProduto(true);
    try {
      const r = await apiGet(conn, `/api/requisicoes/produto/${encodeURIComponent(t)}`);
      if (r?.success && r.found) {
        setProdutoCodigo(r.codigo);
        setProdutoDescricao(r.descricao);
        setProdutoEstoque(r.estoque ?? null);
        setPrecoUnit(formatPreco(r.preco ?? 0));
      } else {
        setProdutoDescricao(""); setProdutoEstoque(null);
        fb.showError("Produto ou serviço não cadastrado.");
      }
    } finally {
      setBuscandoProduto(false);
    }
  }, [conn, fb]);

  const buscarAjuda = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/produtos-servicos", { search: termo, tipo: "all", size: 30 });
    if (r?.items) {
      setAjudaResultados(r.items.map((it: any) => ({ codigo: it.codigo, descricao: it.descricao })));
    }
  }, [conn]);

  const incluirItem = useCallback(async () => {
    if (!conn) return;
    if (!produtoCodigo.trim()) { fb.showError("Informe o produto ou serviço."); return; }
    const qtdNum = parseFloat(qtd.replace(",", "."));
    if (!qtdNum || qtdNum <= 0) { fb.showError("Informe uma quantidade válida."); return; }
    const precoNum = parseFloat((precoUnit || "0").replace(",", "."));

    const gravar = async () => {
      setSaving(true);
      try {
        const r = await apiSend(conn, "/api/requisicoes/itens", "POST", {
          codigo, descricao, produto: produtoCodigo.trim(), qtd: qtdNum, p_unit: precoNum,
          ...auditCtx,
        });
        if (r?.success) {
          if (!codigo) await carregarRequisicao(conn, r.codigo);
          else await carregarRequisicao(conn, codigo);
          setProdutoCodigo(""); setProdutoDescricao(""); setProdutoEstoque(null);
          setQtd(""); setPrecoUnit("");
        } else {
          fb.showError(r?.message || "Não foi possível incluir o item.");
        }
      } finally {
        setSaving(false);
      }
    };

    if (produtoEstoque !== null && qtdNum > produtoEstoque) {
      fb.showConfirm(
        `A quantidade requisitada (${qtdNum}) é maior que o estoque disponível (${produtoEstoque}). Deseja continuar?`,
        gravar,
      );
    } else {
      gravar();
    }
  }, [conn, produtoCodigo, qtd, precoUnit, produtoEstoque, codigo, descricao, auditCtx, fb, carregarRequisicao]);

  const excluirItem = useCallback((item: Item) => {
    if (!conn || !codigo) return;
    fb.showConfirm(
      `Confirma excluir o item "${item.descricao || item.prod}"?`,
      async () => {
        const r = await apiSend(conn, `/api/requisicoes/itens/${item.cod}/excluir`, "POST", auditCtx);
        if (r?.success) await carregarRequisicao(conn, codigo);
        else fb.showError(r?.message || "Não foi possível excluir o item.");
      },
      { destructive: true, confirmText: "Excluir" },
    );
  }, [conn, codigo, auditCtx, fb, carregarRequisicao]);

  const acaoRequisicao = useCallback((
    endpoint: string, mensagemConfirma: string, mensagemSucesso: string, destructive = false,
  ) => {
    if (!conn || !codigo) return;
    fb.showConfirm(mensagemConfirma, async () => {
      const r = await apiSend(conn, `/api/requisicoes/${codigo}/${endpoint}`, "POST", auditCtx);
      if (r?.success) {
        fb.showSuccess(mensagemSucesso);
        await carregarRequisicao(conn, codigo);
      } else {
        fb.showError(r?.message || "Não foi possível concluir a ação.");
      }
    }, { destructive, confirmText: destructive ? "Confirmar" : undefined });
  }, [conn, codigo, auditCtx, fb, carregarRequisicao]);

  const handleImprimir = useCallback(async () => {
    if (!conn || !codigo) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const linhas = itens.map((it) => `
      <div class="row3">
        <span>${escHtml(it.descricao || it.prod)}</span>
        <span>${it.qtd} x ${money(it.p_unit)}</span>
        <span>${money(it.qtd * it.p_unit)}</span>
      </div>`).join("");
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, `Requisição nº ${codigo}`)}
      <div class="mb"><b>Data:</b> ${data ? new Date(data + "T00:00:00").toLocaleDateString("pt-BR") : ""} &nbsp; <b>Usuário:</b> ${escHtml(usuarioNome)} &nbsp; <b>Situação:</b> ${SIT_LABEL[situacao || "A"]}</div>
      ${descricao ? `<div class="mb"><b>Descrição:</b> ${escHtml(descricao)}</div>` : ""}
      <div class="hr"></div>
      ${linhas}
      <div class="hr"></div>
      <div class="row big"><span>Total</span><span>${money(total)}</span></div>
    `;
    printHtml(html, `Requisição ${codigo}`);
  }, [conn, codigo, itens, data, usuarioNome, situacao, descricao, total]);

  const buscarConsulta = useCallback(async () => {
    if (!conn) return;
    setBuscandoConsulta(true);
    try {
      const r = await apiGet(conn, "/api/requisicoes", {
        situacao: filtroSituacoes.join(","),
        data_ini: filtroDataIni || undefined,
        data_fim: filtroDataFim || undefined,
        descricao: filtroDescricao.trim() || undefined,
      });
      setResultados(r?.items || []);
    } finally {
      setBuscandoConsulta(false);
    }
  }, [conn, filtroSituacoes, filtroDataIni, filtroDataFim, filtroDescricao]);

  const abrirConsultar = useCallback(() => {
    setConsultarOpen(true);
    setFiltroSituacoes(["A", "F", "C"]); setFiltroDataIni(null); setFiltroDataFim(null); setFiltroDescricao("");
    setResultados([]);
    buscarConsulta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFiltroSituacao = (s: string) => {
    setFiltroSituacoes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const selecionarRequisicao = useCallback(async (cod: number) => {
    if (!conn) return;
    setConsultarOpen(false);
    await carregarRequisicao(conn, cod);
  }, [conn, carregarRequisicao]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="requisicao-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Requisição</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Nº</Text>
                <Text style={styles.readonlyValue}>{codigo ?? "Nova"}</Text>
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Situação</Text>
                {situacao ? (
                  <View style={[styles.sitBadge, { backgroundColor: SIT_COLOR[situacao] || colors.muted }]}>
                    <Text style={styles.sitBadgeText}>{SIT_LABEL[situacao] || situacao}</Text>
                  </View>
                ) : (
                  <Text style={styles.readonlyValue}>—</Text>
                )}
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Data</Text>
                <Text style={styles.readonlyValue}>{data ? new Date(data + "T00:00:00").toLocaleDateString("pt-BR") : "—"}</Text>
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Usuário</Text>
                <Text style={styles.readonlyValue}>{usuarioNome || "—"}</Text>
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Descrição</Text>
                <TextInput
                  style={[styles.input, styles.inputMultiline, !situacaoAberta && styles.inputDisabled]}
                  value={descricao}
                  onChangeText={setDescricao}
                  editable={situacaoAberta}
                  multiline
                  testID="requisicao-descricao"
                />
              </View>
            </View>
          </View>

          <View style={styles.card}>
            {podeGravar ? (
              <>
                <Text style={styles.sectionTitle}>Incluir Item</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colProduto}>
                    <Text style={styles.label}>Produto ou Serviço</Text>
                    <View style={styles.inputWithBtn}>
                      <TextInput
                        style={[styles.input, { flex: 1, minWidth: 0 }]}
                        value={produtoCodigo}
                        onChangeText={(v) => { setProdutoCodigo(v); setProdutoDescricao(""); setProdutoEstoque(null); }}
                        onBlur={() => resolverProduto(produtoCodigo)}
                        placeholder="Código do produto ou serviço"
                        testID="requisicao-produto"
                      />
                      <Pressable
                        style={styles.helpBtn}
                        onPress={() => { setAjudaOpen(true); setAjudaSearch(""); setAjudaResultados([]); }}
                        testID="requisicao-ajuda-btn"
                      >
                        <Ionicons name="list-outline" size={18} color={colors.brandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Quantidade</Text>
                    <TextInput style={styles.input} value={qtd} onChangeText={setQtd} keyboardType="numeric" testID="requisicao-qtd" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Preço Unitário</Text>
                    <TextInput
                      style={styles.input}
                      value={precoUnit}
                      onChangeText={setPrecoUnit}
                      onBlur={() => setPrecoUnit((v) => (v.trim() ? formatPreco(v) : v))}
                      keyboardType="numeric"
                      testID="requisicao-preco"
                    />
                  </View>
                </View>
                {buscandoProduto ? <Text style={styles.hint}>Buscando…</Text> : null}
                {produtoDescricao ? (
                  <Text style={styles.hint}>
                    {produtoDescricao}{produtoEstoque !== null ? ` — Estoque atual: ${produtoEstoque}` : " (serviço)"}
                  </Text>
                ) : null}
              </>
            ) : null}

            <View style={styles.toolbarRow}>
              {codigo ? (
                <Pressable style={ps.secondaryBtn} onPress={handleNova} testID="requisicao-nova-btn">
                  <Text style={ps.secondaryBtnText}>Nova</Text>
                </Pressable>
              ) : null}
              {podeGravar ? (
                <Pressable
                  style={[styles.incluirBtn, saving && { opacity: 0.6 }]}
                  onPress={incluirItem}
                  disabled={saving}
                  testID="requisicao-incluir-item-btn"
                >
                  <Ionicons name="add-circle-outline" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.incluirBtnText}>{saving ? "Gravando…" : "Incluir Item"}</Text>
                </Pressable>
              ) : null}
              {podeFechar ? (
                <Pressable
                  style={styles.actionBtn}
                  onPress={() => acaoRequisicao("fechar", "Confirma o fechamento desta requisição? O estoque dos itens será baixado.", "Requisição fechada.", true)}
                  testID="requisicao-fechar-btn"
                >
                  <Text style={styles.actionBtnText}>Fechar</Text>
                </Pressable>
              ) : null}
              {podeReabrir ? (
                <Pressable
                  style={styles.actionBtn}
                  onPress={() => acaoRequisicao("reabrir", "Confirma reabrir esta requisição? O estoque dos itens será devolvido.", "Requisição reaberta.")}
                  testID="requisicao-reabrir-btn"
                >
                  <Text style={styles.actionBtnText}>Reabrir</Text>
                </Pressable>
              ) : null}
              {podeCancelar ? (
                <Pressable
                  style={[styles.actionBtn, styles.dangerBtn]}
                  onPress={() => acaoRequisicao("cancelar", "Confirma cancelar esta requisição?", "Requisição cancelada.", true)}
                  testID="requisicao-cancelar-btn"
                >
                  <Text style={[styles.actionBtnText, styles.dangerBtnText]}>Cancelar</Text>
                </Pressable>
              ) : null}
              {podeImprimir ? (
                <Pressable style={ps.secondaryBtn} onPress={handleImprimir} testID="requisicao-imprimir-btn">
                  <Text style={ps.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
              <Pressable style={styles.consultarBtnInline} onPress={abrirConsultar} testID="requisicao-consultar-btn">
                <Ionicons name="search-outline" size={18} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Itens ({itens.length})</Text>
            {itens.map((it) => (
              <View key={it.cod} style={styles.itemRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemTitle}>{it.descricao || it.prod}</Text>
                  <Text style={styles.itemSub}>{it.prod} · {it.qtd} x {money(it.p_unit)} = {money(it.qtd * it.p_unit)}</Text>
                </View>
                {podeExcluir ? (
                  <Pressable style={ps.deleteBtn} onPress={() => excluirItem(it)} testID={`requisicao-excluir-item-${it.cod}`}>
                    <Ionicons name="trash-outline" size={16} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            ))}
            {itens.length === 0 ? <Text style={styles.hint}>Nenhum item incluído.</Text> : null}
            {itens.length > 0 ? (
              <View style={styles.totalRow}>
                <Text style={styles.totalLabel}>Total</Text>
                <Text style={styles.totalValue}>{money(total)}</Text>
              </View>
            ) : null}
          </View>
        </View>
      </ScrollView>

      {/* Ajuda — busca de produto/serviço */}
      <AppModal visible={ajudaOpen} transparent animationType="fade" onRequestClose={() => setAjudaOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Buscar Produto/Serviço</Text>
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
                testID="requisicao-ajuda-search"
              />
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {ajudaResultados.map((it) => (
                <Pressable
                  key={it.codigo}
                  style={ps.resultRow}
                  onPress={() => { setProdutoCodigo(it.codigo); setAjudaOpen(false); resolverProduto(it.codigo); }}
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

      {/* Consultar — lista de requisições */}
      <AppModal visible={consultarOpen} transparent animationType="fade" onRequestClose={() => setConsultarOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact, { maxWidth: 780 }]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Consultar Requisições</Text>
              <Pressable onPress={() => setConsultarOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>

            <View style={styles.chipsRow}>
              {(["A", "F", "C"] as const).map((s) => (
                <Pressable
                  key={s}
                  onPress={() => toggleFiltroSituacao(s)}
                  style={[styles.chip, filtroSituacoes.includes(s) && { backgroundColor: SIT_COLOR[s], borderColor: SIT_COLOR[s] }]}
                >
                  <Text style={[styles.chipText, filtroSituacoes.includes(s) && styles.chipTextSel]}>{SIT_LABEL[s]}</Text>
                </Pressable>
              ))}
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
                  testID="requisicao-filtro-de"
                  onSubmitEditing={() => {
                    document.querySelector<HTMLInputElement>('[data-testid="requisicao-filtro-ate"]')?.focus();
                  }}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={filtroDataFim} onChange={setFiltroDataFim} testID="requisicao-filtro-ate" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Descrição</Text>
                <TextInput style={styles.input} value={filtroDescricao} onChangeText={setFiltroDescricao} testID="requisicao-filtro-descricao" />
              </View>
              <Pressable style={styles.buscarBtnInline} onPress={buscarConsulta} testID="requisicao-buscar-btn">
                <Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.buscarBtnInlineText}>{buscandoConsulta ? "Buscando…" : "Buscar"}</Text>
              </Pressable>
            </View>

            <ScrollView style={{ maxHeight: 380, marginTop: spacing.md }}>
              {resultados.map((r) => (
                <Pressable key={r.codigo} style={styles.resultRow} onPress={() => selecionarRequisicao(r.codigo)}>
                  <View style={[styles.sitBadge, { backgroundColor: SIT_COLOR[r.situacao] || colors.muted }]}>
                    <Text style={styles.sitBadgeText}>{r.codigo}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultTitle}>{r.descricao || "(sem descrição)"}</Text>
                    <Text style={styles.resultSub}>
                      {new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR")} · {r.usuario_nome || "—"} · {SIT_LABEL[r.situacao] || r.situacao} · {money(r.total)}
                    </Text>
                  </View>
                </Pressable>
              ))}
              {resultados.length === 0 && !buscandoConsulta ? (
                <Text style={ps.emptyText}>Nenhuma requisição encontrada.</Text>
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
  card: { ...WEB_FILTER_CARD, gap: spacing.md, marginBottom: spacing.md },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  readonlyValue: { fontSize: 14, color: colors.onSurface, fontWeight: "500", paddingVertical: 8 },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface,
  },
  inputMultiline: { minHeight: 60, textAlignVertical: "top" },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  inputWithBtn: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  helpBtn: {
    width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 180 },
  colProduto: { width: 280 },
  colNarrow: { width: 140 },
  colTiny: { width: 90 },
  buscarBtnInline: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingHorizontal: spacing.lg, paddingVertical: 11,
  },
  buscarBtnInlineText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  toolbarRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "center", marginTop: spacing.sm },
  actionBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill,
    backgroundColor: colors.brandPrimary,
  },
  actionBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  dangerBtn: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.error },
  dangerBtnText: { color: colors.error },
  consultarBtnInline: {
    width: 40, height: 40, borderRadius: radius.sm, alignItems: "center", justifyContent: "center",
    backgroundColor: colors.brandPrimary,
  },
  incluirBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  incluirBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  itemTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  itemSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  totalRow: { flexDirection: "row", justifyContent: "space-between", paddingTop: spacing.sm },
  totalLabel: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  totalValue: { fontSize: 16, fontWeight: "700", color: colors.brandPrimary },
  sitBadge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, alignSelf: "flex-start" },
  sitBadgeText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  chipsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
  resultRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});
