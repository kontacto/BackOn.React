// Cotação de Compra (Transações > Gestão de Compras > Compra). Aba
// "Cotações" do legado `FrmGesCom.frm` — nunca foi desenvolvida lá (0
// controles no próprio .frm). Construída do zero a partir de anotações
// manuscritas do usuário ("Compras Mapa de Cotação") — ver
// backend/services/cotacao_compra_service.py e PENDENCIAS.md > "Gestão
// de Compras" > "Cotação" para o racional completo e as decisões de
// escopo confirmadas (sem envio de e-mail, sem geração de Pedido de
// Compra formal nesta rodada).
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

type Resposta = {
  cod: number; cotacao_item: number; fornecedor: number; fornecedor_nome: string;
  valor_unit: number; marca: string | null; prazo: string | null; cond_pagamento: string | null;
  data_resposta: string;
};
type Item = {
  cod: number; produto: string; produto_descricao: string | null; qtd: number;
  fornecedor_vencedor: number | null; fornecedor_vencedor_nome: string | null; valor_vencedor: number | null;
  respostas: Resposta[];
};
type CotListItem = {
  codigo: number; data: string; descricao: string | null; situacao: string;
  usuario_nome: string | null; total_itens: number; total_decididos: number;
};
type Fornecedor = { codigo_int: number; nome: string; fantasia: string };

const SIT_LABEL: Record<string, string> = { A: "Aberta", F: "Finalizada", C: "Cancelada" };

function money(v: number | null | undefined): string {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function CotacaoCompraScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cotação de Compra está disponível apenas no web."
        testID="cotacao-compra-web-only"
      />
    );
  }

  if (!moduleOn("Curva_abc")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Curva ABC/Compras está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="cotacao-compra-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  const [codigo, setCodigo] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string | null>(null);
  const [data, setData] = useState<string | null>(null);
  const [usuarioNome, setUsuarioNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [itens, setItens] = useState<Item[]>([]);

  const [produtoCodigo, setProdutoCodigo] = useState("");
  const [produtoInfo, setProdutoInfo] = useState<{ descricao: string; custoMedio: number; estoque: number; ultimaData: string | null; ultimaValor: number | null } | null>(null);
  const [buscandoProduto, setBuscandoProduto] = useState(false);
  const [qtd, setQtd] = useState("");
  const [saving, setSaving] = useState(false);

  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [ajudaSearch, setAjudaSearch] = useState("");
  const [ajudaResultados, setAjudaResultados] = useState<{ codigo: string; descricao: string }[]>([]);

  const [respondendoItem, setRespondendoItem] = useState<number | null>(null);
  const [respFornecedor, setRespFornecedor] = useState<Fornecedor | null>(null);
  const [respFornecedorModalOpen, setRespFornecedorModalOpen] = useState(false);
  const [respFornecedorBusca, setRespFornecedorBusca] = useState("");
  const [respFornecedorResultados, setRespFornecedorResultados] = useState<Fornecedor[]>([]);
  const [respValor, setRespValor] = useState("");
  const [respMarca, setRespMarca] = useState("");
  const [respPrazo, setRespPrazo] = useState("");
  const [respCondPag, setRespCondPag] = useState("");

  const [consultarOpen, setConsultarOpen] = useState(false);
  const [filtroSituacoes, setFiltroSituacoes] = useState<string[]>(["A", "F", "C"]);
  const [filtroDataIni, setFiltroDataIni] = useState<string | null>(null);
  const [filtroDataFim, setFiltroDataFim] = useState<string | null>(null);
  const [filtroDescricao, setFiltroDescricao] = useState("");
  const [resultados, setResultados] = useState<CotListItem[]>([]);
  const [buscandoConsulta, setBuscandoConsulta] = useState(false);

  const situacaoAberta = !situacao || situacao === "A";
  const podeGravar = can("COTACAO_COMPRA.GRAVAR") && situacaoAberta;
  const podeExcluir = can("COTACAO_COMPRA.EXCLUIR") && situacaoAberta;
  const podeVencedor = can("COTACAO_COMPRA.VENCEDOR") && situacaoAberta;
  const podeFinalizar = can("COTACAO_COMPRA.FINALIZAR") && situacao === "A";
  const podeReabrir = can("COTACAO_COMPRA.REABRIR") && situacao === "F";
  const podeCancelar = can("COTACAO_COMPRA.CANCELAR") && (situacao === "A" || situacao === "F");
  const podeImprimir = can("COTACAO_COMPRA.IMPRIMIR") && !!codigo;

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
    setProdutoCodigo(""); setProdutoInfo(null); setQtd("");
    setRespondendoItem(null);
  }, []);

  const carregarCotacao = useCallback(async (c: Connection, cod: number) => {
    const r = await apiGet(c, `/api/cotacoes-compra/${cod}`);
    if (r?.success) {
      const it = r.item;
      setCodigo(it.codigo);
      setSituacao(it.situacao || "A");
      setData(it.data);
      setUsuarioNome(it.usuario_nome || "");
      setDescricao(it.descricao || "");
      setItens(it.itens || []);
    } else {
      fb.showError(r?.message || "Não foi possível carregar a cotação.");
    }
  }, [fb]);

  const resolverProduto = useCallback(async (termo: string) => {
    if (!conn) return;
    const t = termo.trim();
    if (!t) { setProdutoInfo(null); return; }
    setBuscandoProduto(true);
    try {
      const r = await apiGet(conn, `/api/cotacoes-compra/produto/${encodeURIComponent(t)}`);
      if (r?.success && r.found) {
        setProdutoCodigo(r.codigo);
        setProdutoInfo({
          descricao: r.descricao, custoMedio: r.custo_medio || 0, estoque: r.estoque || 0,
          ultimaData: r.ultima_compra_data, ultimaValor: r.ultima_compra_valor,
        });
      } else {
        setProdutoInfo(null);
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

  const incluirItem = useCallback(async () => {
    if (!conn) return;
    if (!produtoCodigo.trim()) { fb.showError("Informe o produto."); return; }
    const qtdNum = parseFloat(qtd.replace(",", "."));
    if (!qtdNum || qtdNum <= 0) { fb.showError("Informe uma quantidade válida."); return; }

    setSaving(true);
    try {
      const r = await apiSend(conn, "/api/cotacoes-compra/itens", "POST", {
        codigo, descricao, produto: produtoCodigo.trim(), qtd: qtdNum,
        ...auditCtx,
      });
      if (r?.success) {
        await carregarCotacao(conn, codigo || r.codigo);
        setProdutoCodigo(""); setProdutoInfo(null); setQtd("");
      } else {
        fb.showError(r?.message || "Não foi possível incluir o item.");
      }
    } finally {
      setSaving(false);
    }
  }, [conn, produtoCodigo, qtd, codigo, descricao, auditCtx, fb, carregarCotacao]);

  const excluirItem = useCallback((item: Item) => {
    if (!conn || !codigo) return;
    fb.showConfirm(
      `Confirma excluir o item "${item.produto_descricao || item.produto}"? As respostas já lançadas para ele também serão excluídas.`,
      async () => {
        const r = await apiSend(conn, `/api/cotacoes-compra/itens/${item.cod}/excluir`, "POST", auditCtx);
        if (r?.success) await carregarCotacao(conn, codigo);
        else fb.showError(r?.message || "Não foi possível excluir o item.");
      },
      { destructive: true, confirmText: "Excluir" },
    );
  }, [conn, codigo, auditCtx, fb, carregarCotacao]);

  const buscarFornecedor = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/fornecedores", { search: termo });
    if (r?.items) setRespFornecedorResultados(r.items);
  }, [conn]);

  const abrirResposta = useCallback((itemCod: number) => {
    setRespondendoItem(itemCod);
    setRespFornecedor(null); setRespValor(""); setRespMarca(""); setRespPrazo(""); setRespCondPag("");
  }, []);

  const lancarResposta = useCallback(async () => {
    if (!conn || !respondendoItem) return;
    if (!respFornecedor) { fb.showError("Selecione o fornecedor."); return; }
    const valorNum = parseFloat(respValor.replace(",", "."));
    if (!valorNum || valorNum <= 0) { fb.showError("Informe um valor unitário válido."); return; }

    const r = await apiSend(conn, `/api/cotacoes-compra/itens/${respondendoItem}/respostas`, "POST", {
      fornecedor: respFornecedor.codigo_int, valor_unit: valorNum,
      marca: respMarca.trim() || undefined, prazo: respPrazo.trim() || undefined,
      cond_pagamento: respCondPag.trim() || undefined,
      ...auditCtx,
    });
    if (r?.success && codigo) {
      await carregarCotacao(conn, codigo);
      setRespondendoItem(null);
    } else {
      fb.showError(r?.message || "Não foi possível lançar a resposta.");
    }
  }, [conn, respondendoItem, respFornecedor, respValor, respMarca, respPrazo, respCondPag, auditCtx, codigo, fb, carregarCotacao]);

  const excluirResposta = useCallback((resp: Resposta) => {
    if (!conn || !codigo) return;
    fb.showConfirm(
      `Confirma excluir a resposta de "${resp.fornecedor_nome}"?`,
      async () => {
        const r = await apiSend(conn, `/api/cotacoes-compra/respostas/${resp.cod}/excluir`, "POST", auditCtx);
        if (r?.success) await carregarCotacao(conn, codigo);
        else fb.showError(r?.message || "Não foi possível excluir a resposta.");
      },
      { destructive: true, confirmText: "Excluir" },
    );
  }, [conn, codigo, auditCtx, fb, carregarCotacao]);

  const marcarVencedor = useCallback((resp: Resposta) => {
    if (!conn || !codigo) return;
    fb.showConfirm(
      `Confirma marcar "${resp.fornecedor_nome}" (${money(resp.valor_unit)}) como vencedor deste item?`,
      async () => {
        const r = await apiSend(conn, `/api/cotacoes-compra/respostas/${resp.cod}/marcar-vencedor`, "POST", auditCtx);
        if (r?.success) await carregarCotacao(conn, codigo);
        else fb.showError(r?.message || "Não foi possível marcar o vencedor.");
      },
    );
  }, [conn, codigo, auditCtx, fb, carregarCotacao]);

  const acaoCotacao = useCallback((
    endpoint: string, mensagemConfirma: string, mensagemSucesso: string, destructive = false,
  ) => {
    if (!conn || !codigo) return;
    fb.showConfirm(mensagemConfirma, async () => {
      const r = await apiSend(conn, `/api/cotacoes-compra/${codigo}/${endpoint}`, "POST", auditCtx);
      if (r?.success) {
        fb.showSuccess(mensagemSucesso);
        await carregarCotacao(conn, codigo);
      } else {
        fb.showError(r?.message || "Não foi possível concluir a ação.");
      }
    }, { destructive, confirmText: destructive ? "Confirmar" : undefined });
  }, [conn, codigo, auditCtx, fb, carregarCotacao]);

  const handleFinalizar = useCallback(() => {
    const semVencedor = itens.filter((it) => !it.fornecedor_vencedor).length;
    const aviso = semVencedor > 0
      ? `${semVencedor} item(ns) ainda sem fornecedor vencedor marcado. Confirma finalizar mesmo assim?`
      : "Confirma finalizar esta cotação? A decisão de compra fica registrada, sem gerar Pedido de Compra automaticamente.";
    acaoCotacao("finalizar", aviso, "Cotação finalizada.", semVencedor > 0);
  }, [itens, acaoCotacao]);

  const handleImprimir = useCallback(async () => {
    if (!conn || !codigo) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const linhas = itens.map((it) => {
      const respostasHtml = (it.respostas || []).map((r) => `
        <div class="row3" style="${it.fornecedor_vencedor === r.fornecedor ? "font-weight:bold;" : ""}">
          <span>${escHtml(r.fornecedor_nome)}${it.fornecedor_vencedor === r.fornecedor ? " ★ Vencedor" : ""}</span>
          <span>${escHtml(r.marca || "")} ${escHtml(r.prazo || "")}</span>
          <span>${money(r.valor_unit)}</span>
        </div>`).join("");
      return `
        <div class="mb"><b>${escHtml(it.produto)} — ${escHtml(it.produto_descricao || "")}</b> (qtd ${it.qtd})</div>
        ${respostasHtml || '<div class="mb">Sem respostas lançadas.</div>'}
        <div class="hr"></div>`;
    }).join("");
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, `Cotação de Compra nº ${codigo} — Comparativo`)}
      <div class="mb"><b>Data:</b> ${data ? new Date(data + "T00:00:00").toLocaleDateString("pt-BR") : ""} &nbsp; <b>Situação:</b> ${SIT_LABEL[situacao || "A"]}</div>
      ${descricao ? `<div class="mb"><b>Descrição:</b> ${escHtml(descricao)}</div>` : ""}
      <div class="hr"></div>
      ${linhas}
    `;
    printHtml(html, `Cotação ${codigo}`);
  }, [conn, codigo, itens, data, situacao, descricao]);

  const buscarConsulta = useCallback(async () => {
    if (!conn) return;
    setBuscandoConsulta(true);
    try {
      const r = await apiGet(conn, "/api/cotacoes-compra", {
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

  const selecionarCotacao = useCallback(async (cod: number) => {
    if (!conn) return;
    setConsultarOpen(false);
    await carregarCotacao(conn, cod);
  }, [conn, carregarCotacao]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="cotacao-compra-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Cotação de Compra</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.guideCard}>
            <Ionicons name="bulb-outline" size={20} color={colors.brandPrimary} />
            <Text style={styles.guideText}>
              Monte uma lista de produtos, lance o preço que cada fornecedor ofereceu (consultado por telefone,
              e-mail ou WhatsApp fora do sistema) e marque o vencedor de cada item para comparar. Ao finalizar, a
              decisão fica registrada — sem gerar Pedido de Compra automaticamente.
            </Text>
          </View>

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
                  style={[styles.input, !situacaoAberta && styles.inputDisabled]}
                  value={descricao}
                  onChangeText={setDescricao}
                  editable={situacaoAberta}
                  placeholder="Ex.: Reposição de material de escritório"
                  testID="cotacao-descricao"
                />
              </View>
            </View>
          </View>

          <View style={styles.card}>
            {podeGravar ? (
              <>
                <Text style={styles.sectionTitle}>Adicionar Produto à Cotação</Text>
                <View style={styles.rowFields}>
                  <View style={styles.colProduto}>
                    <Text style={styles.label}>Produto</Text>
                    <View style={styles.inputWithBtn}>
                      <TextInput
                        style={[styles.input, { flex: 1, minWidth: 0 }]}
                        value={produtoCodigo}
                        onChangeText={(v) => { setProdutoCodigo(v); setProdutoInfo(null); }}
                        onBlur={() => resolverProduto(produtoCodigo)}
                        placeholder="Código do produto"
                        testID="cotacao-produto"
                      />
                      <Pressable
                        style={styles.helpBtn}
                        onPress={() => { setAjudaOpen(true); setAjudaSearch(""); setAjudaResultados([]); }}
                        testID="cotacao-ajuda-btn"
                      >
                        <Ionicons name="list-outline" size={18} color={colors.brandPrimary} />
                      </Pressable>
                    </View>
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.label}>Quantidade</Text>
                    <TextInput style={styles.input} value={qtd} onChangeText={setQtd} keyboardType="numeric" testID="cotacao-qtd" />
                  </View>
                  <Pressable
                    style={[styles.incluirBtn, saving && { opacity: 0.6 }]}
                    onPress={incluirItem}
                    disabled={saving}
                    testID="cotacao-incluir-item-btn"
                  >
                    <Ionicons name="add-circle-outline" size={18} color={colors.onBrandPrimary} />
                    <Text style={styles.incluirBtnText}>{saving ? "Gravando…" : "Incluir"}</Text>
                  </Pressable>
                </View>
                {buscandoProduto ? <Text style={styles.hint}>Buscando…</Text> : null}
                {produtoInfo ? (
                  <Text style={styles.hint}>
                    {produtoInfo.descricao} — Custo médio: {money(produtoInfo.custoMedio)} · Estoque: {produtoInfo.estoque}
                    {produtoInfo.ultimaValor != null ? ` · Última compra: ${money(produtoInfo.ultimaValor)}${produtoInfo.ultimaData ? ` em ${new Date(produtoInfo.ultimaData).toLocaleDateString("pt-BR")}` : ""}` : " · Sem compras anteriores registradas"}
                  </Text>
                ) : null}
              </>
            ) : null}

            <View style={styles.toolbarRow}>
              {codigo ? (
                <Pressable style={ps.secondaryBtn} onPress={handleNova} testID="cotacao-nova-btn">
                  <Text style={ps.secondaryBtnText}>Nova</Text>
                </Pressable>
              ) : null}
              {podeFinalizar ? (
                <Pressable style={styles.actionBtn} onPress={handleFinalizar} testID="cotacao-finalizar-btn">
                  <Text style={styles.actionBtnText}>Finalizar</Text>
                </Pressable>
              ) : null}
              {podeReabrir ? (
                <Pressable
                  style={styles.actionBtn}
                  onPress={() => acaoCotacao("reabrir", "Confirma reabrir esta cotação?", "Cotação reaberta.")}
                  testID="cotacao-reabrir-btn"
                >
                  <Text style={styles.actionBtnText}>Reabrir</Text>
                </Pressable>
              ) : null}
              {podeCancelar ? (
                <Pressable
                  style={[styles.actionBtn, styles.dangerBtn]}
                  onPress={() => acaoCotacao("cancelar", "Confirma cancelar esta cotação?", "Cotação cancelada.", true)}
                  testID="cotacao-cancelar-btn"
                >
                  <Text style={[styles.actionBtnText, styles.dangerBtnText]}>Cancelar</Text>
                </Pressable>
              ) : null}
              {podeImprimir ? (
                <Pressable style={ps.secondaryBtn} onPress={handleImprimir} testID="cotacao-imprimir-btn">
                  <Text style={ps.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
              <Pressable style={styles.consultarBtnInline} onPress={abrirConsultar} testID="cotacao-consultar-btn">
                <Ionicons name="search-outline" size={18} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Itens ({itens.length})</Text>
            {itens.map((it) => {
              const menorValor = it.respostas.length ? Math.min(...it.respostas.map((r) => r.valor_unit)) : null;
              return (
                <View key={it.cod} style={styles.itemBlock}>
                  <View style={styles.itemHeaderRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemTitle}>{it.produto} — {it.produto_descricao}</Text>
                      <Text style={styles.itemSub}>
                        Qtd: {it.qtd}
                        {it.fornecedor_vencedor_nome ? ` · Vencedor: ${it.fornecedor_vencedor_nome} (${money(it.valor_vencedor)})` : ""}
                      </Text>
                    </View>
                    {podeGravar ? (
                      <Pressable style={styles.miniBtn} onPress={() => abrirResposta(it.cod)} testID={`cotacao-add-resposta-${it.cod}`}>
                        <Ionicons name="add-outline" size={14} color={colors.brandPrimary} />
                        <Text style={styles.miniBtnText}>Resposta</Text>
                      </Pressable>
                    ) : null}
                    {podeExcluir ? (
                      <Pressable style={ps.deleteBtn} onPress={() => excluirItem(it)} testID={`cotacao-excluir-item-${it.cod}`}>
                        <Ionicons name="trash-outline" size={16} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>

                  {respondendoItem === it.cod ? (
                    <View style={styles.respostaForm}>
                      <View style={styles.rowFields}>
                        <View style={styles.colFlex}>
                          <Text style={styles.label}>Fornecedor</Text>
                          {respFornecedor ? (
                            <View style={styles.selectedChipRow}>
                              <View style={styles.selectedChip}>
                                <Text style={styles.selectedChipText} numberOfLines={1}>{respFornecedor.fantasia || respFornecedor.nome}</Text>
                                <Pressable onPress={() => setRespFornecedor(null)} hitSlop={6}>
                                  <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                                </Pressable>
                              </View>
                            </View>
                          ) : (
                            <Pressable
                              style={styles.pickerBtn}
                              onPress={() => { setRespFornecedorModalOpen(true); setRespFornecedorBusca(""); setRespFornecedorResultados([]); }}
                              testID={`cotacao-resposta-fornecedor-${it.cod}`}
                            >
                              <Ionicons name="business-outline" size={16} color={colors.muted} />
                              <Text style={styles.pickerBtnText}>Selecionar fornecedor</Text>
                            </Pressable>
                          )}
                        </View>
                        <View style={styles.colTiny}>
                          <Text style={styles.label}>Valor Unit.</Text>
                          <TextInput style={styles.input} value={respValor} onChangeText={setRespValor} keyboardType="numeric" testID={`cotacao-resposta-valor-${it.cod}`} />
                        </View>
                      </View>
                      <View style={styles.rowFields}>
                        <View style={styles.colNarrow}>
                          <Text style={styles.label}>Marca</Text>
                          <TextInput style={styles.input} value={respMarca} onChangeText={setRespMarca} testID={`cotacao-resposta-marca-${it.cod}`} />
                        </View>
                        <View style={styles.colNarrow}>
                          <Text style={styles.label}>Prazo</Text>
                          <TextInput style={styles.input} value={respPrazo} onChangeText={setRespPrazo} placeholder="Ex.: 5 dias" testID={`cotacao-resposta-prazo-${it.cod}`} />
                        </View>
                        <View style={styles.colFlex}>
                          <Text style={styles.label}>Cond. Pagamento</Text>
                          <TextInput style={styles.input} value={respCondPag} onChangeText={setRespCondPag} placeholder="Ex.: 30/60 dias" testID={`cotacao-resposta-condpag-${it.cod}`} />
                        </View>
                      </View>
                      <View style={styles.toolbarRow}>
                        <Pressable style={styles.incluirBtn} onPress={lancarResposta} testID={`cotacao-lancar-resposta-${it.cod}`}>
                          <Text style={styles.incluirBtnText}>Lançar Resposta</Text>
                        </Pressable>
                        <Pressable style={ps.secondaryBtn} onPress={() => setRespondendoItem(null)}>
                          <Text style={ps.secondaryBtnText}>Cancelar</Text>
                        </Pressable>
                      </View>
                    </View>
                  ) : null}

                  {it.respostas.length === 0 ? (
                    <Text style={styles.hint}>Nenhuma resposta lançada ainda.</Text>
                  ) : (
                    it.respostas.map((r) => {
                      const isVencedor = it.fornecedor_vencedor === r.fornecedor;
                      const isMenor = r.valor_unit === menorValor;
                      return (
                        <View key={r.cod} style={[styles.respRow, isVencedor && styles.respRowVencedor]}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.respNome}>
                              {r.fornecedor_nome} {isVencedor ? "★ Vencedor" : isMenor ? "· menor preço" : ""}
                            </Text>
                            <Text style={styles.respSub}>
                              {money(r.valor_unit)}{r.marca ? ` · ${r.marca}` : ""}{r.prazo ? ` · Prazo: ${r.prazo}` : ""}{r.cond_pagamento ? ` · ${r.cond_pagamento}` : ""}
                            </Text>
                          </View>
                          {podeVencedor && !isVencedor ? (
                            <Pressable style={styles.miniBtn} onPress={() => marcarVencedor(r)} testID={`cotacao-marcar-vencedor-${r.cod}`}>
                              <Ionicons name="trophy-outline" size={14} color={colors.brandPrimary} />
                            </Pressable>
                          ) : null}
                          {podeExcluir ? (
                            <Pressable style={ps.deleteBtn} onPress={() => excluirResposta(r)} testID={`cotacao-excluir-resposta-${r.cod}`}>
                              <Ionicons name="trash-outline" size={14} color={colors.error} />
                            </Pressable>
                          ) : null}
                        </View>
                      );
                    })
                  )}
                </View>
              );
            })}
            {itens.length === 0 ? <Text style={styles.hint}>Nenhum produto incluído.</Text> : null}
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
                testID="cotacao-ajuda-search"
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

      {/* Fornecedor — busca (pra lançar resposta) */}
      <AppModal visible={respFornecedorModalOpen} transparent animationType="fade" onRequestClose={() => setRespFornecedorModalOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Buscar Fornecedor</Text>
              <Pressable onPress={() => setRespFornecedorModalOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={ps.searchWrap}>
              <Ionicons name="search-outline" size={18} color={colors.muted} />
              <TextInput
                style={ps.searchInput}
                value={respFornecedorBusca}
                onChangeText={(v) => { setRespFornecedorBusca(v); buscarFornecedor(v); }}
                placeholder="Nome ou código"
                autoFocus
                testID="cotacao-resposta-fornecedor-search"
              />
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {respFornecedorResultados.map((f) => (
                <Pressable
                  key={f.codigo_int}
                  style={ps.resultRow}
                  onPress={() => { setRespFornecedor(f); setRespFornecedorModalOpen(false); }}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={ps.resultNome}>{f.fantasia || f.nome}</Text>
                    <Text style={ps.resultSub}>{f.nome}</Text>
                  </View>
                </Pressable>
              ))}
              {respFornecedorResultados.length === 0 ? <Text style={ps.emptyText}>Digite pra buscar.</Text> : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>

      {/* Consultar — lista de cotações */}
      <AppModal visible={consultarOpen} transparent animationType="fade" onRequestClose={() => setConsultarOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact, { maxWidth: 780 }]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Consultar Cotações</Text>
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
                  onChange={(v) => { setFiltroDataIni(v || null); if (v) setFiltroDataFim(v); }}
                  testID="cotacao-filtro-de"
                  onSubmitEditing={() => {
                    document.querySelector<HTMLInputElement>('[data-testid="cotacao-filtro-ate"]')?.focus();
                  }}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={filtroDataFim} onChange={setFiltroDataFim} testID="cotacao-filtro-ate" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Descrição</Text>
                <TextInput style={styles.input} value={filtroDescricao} onChangeText={setFiltroDescricao} testID="cotacao-filtro-descricao" />
              </View>
              <Pressable style={styles.buscarBtnInline} onPress={buscarConsulta} testID="cotacao-buscar-btn">
                <Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.buscarBtnInlineText}>{buscandoConsulta ? "Buscando…" : "Buscar"}</Text>
              </Pressable>
            </View>

            <ScrollView style={{ maxHeight: 380, marginTop: spacing.md }}>
              {resultados.map((r) => (
                <Pressable key={r.codigo} style={styles.resultRow} onPress={() => selecionarCotacao(r.codigo)}>
                  <View style={[styles.sitBadge, { backgroundColor: SIT_COLOR[r.situacao] || colors.muted }]}>
                    <Text style={styles.sitBadgeText}>{r.codigo}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultTitle}>{r.descricao || "(sem descrição)"}</Text>
                    <Text style={styles.resultSub}>
                      {new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR")} · {r.usuario_nome || "—"} · {SIT_LABEL[r.situacao] || r.situacao} · {r.total_decididos}/{r.total_itens} decididos
                    </Text>
                  </View>
                </Pressable>
              ))}
              {resultados.length === 0 && !buscandoConsulta ? (
                <Text style={ps.emptyText}>Nenhuma cotação encontrada.</Text>
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
  guideCard: {
    flexDirection: "row", gap: spacing.sm, alignItems: "flex-start",
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  guideText: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 18 },
  card: { ...WEB_FILTER_CARD, gap: spacing.md, marginBottom: spacing.md },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  readonlyValue: { fontSize: 14, color: colors.onSurface, fontWeight: "500", paddingVertical: 8 },
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
  colProduto: { width: 240 },
  colNarrow: { width: 140 },
  colTiny: { width: 100 },
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
  miniBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.sm, paddingVertical: 5,
  },
  miniBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 11 },
  itemBlock: { paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border, gap: 6 },
  itemHeaderRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  itemTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  itemSub: { fontSize: 11.5, color: colors.muted, marginTop: 2 },
  respostaForm: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.sm, gap: spacing.sm,
  },
  respRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 6, paddingHorizontal: spacing.sm, marginLeft: spacing.md,
    borderLeftWidth: 2, borderLeftColor: colors.border,
  },
  respRowVencedor: { borderLeftColor: colors.success, backgroundColor: "#E9F5EF" },
  respNome: { fontSize: 12.5, fontWeight: "600", color: colors.onSurface },
  respSub: { fontSize: 11.5, color: colors.muted, marginTop: 1 },
  pickerBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    backgroundColor: colors.surface, paddingHorizontal: spacing.md, paddingVertical: 11,
  },
  pickerBtnText: { fontSize: 13, color: colors.muted },
  selectedChipRow: { flexDirection: "row" },
  selectedChip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, maxWidth: 280,
  },
  selectedChipText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600", flexShrink: 1 },
  sitBadge: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: radius.pill, alignSelf: "flex-start" },
  sitBadgeText: { color: "#fff", fontSize: 12, fontWeight: "700" },
  chipsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm, flexWrap: "wrap" },
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
