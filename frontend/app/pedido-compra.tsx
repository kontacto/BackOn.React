// Pedido de Compra (Transações > Gestão de Compras > Compra). Legado:
// `FrmPedCom.frm` ("Cadastro de Pedido de Compra de Material"), recuperado
// do histórico da sessão e rastreado por completo — ver
// backend/services/pedido_compra_service.py e PENDENCIAS.md > "Gestão de
// Compras" > "Pedido de Compra" para o racional completo das decisões de
// escopo (situação A/F/C, "Excluir Pedido" é botão morto no legado,
// Rateio Desp/Desc e Importar DAV ficaram fora desta rodada).
import { useCallback, useEffect, useState } from "react";
import { Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_FORNECEDOR } from "@/src/components/GestorDocumentosSection";
import AccordionSection from "@/src/components/pedido/AccordionSection";

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

type Fornecedor = { codigo_int: number; nome: string; fantasia: string };
type Fiscal = {
  qtdUnCompra: string; baseIcms: string; valorIcms: string; baseIpi: string; alqtIpi: string; valorIpi: string;
  baseSub: string; valorSub: string; baseIss: string; valorIss: string;
  frete: string; seguro: string; despesas: string; desconto: string;
};
type Item = {
  seq: number; codigo_int: string; produto_descricao: string | null; qtd: number; p_unit: number;
  qtd_un_compra: number; base_icms: number; valor_icms: number; base_ipi: number; alqt_ipi: number; valor_ipi: number;
  base_sub: number; valor_sub: number; base_iss: number; valor_iss: number;
  frete: number; seguro: number; despesas: number; desconto: number;
};
type PedListItem = {
  codigo: number; data: string; situacao: string; pedido_fornecedor: string | null;
  fornecedor: number; fornecedor_nome: string | null; total: number; total_itens: number;
};

const SIT_LABEL: Record<string, string> = { A: "Aberto", F: "Aprovado", C: "Rejeitado" };

const FISCAL_VAZIO: Fiscal = {
  qtdUnCompra: "1", baseIcms: "", valorIcms: "", baseIpi: "", alqtIpi: "", valorIpi: "",
  baseSub: "", valorSub: "", baseIss: "", valorIss: "", frete: "", seguro: "", despesas: "", desconto: "",
};

function money(v: number | null | undefined): string {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function num(v: string): number {
  const n = parseFloat((v || "0").replace(",", "."));
  return isFinite(n) ? n : 0;
}

function fiscalToPayload(f: Fiscal) {
  return {
    qtd_un_compra: num(f.qtdUnCompra) || 1,
    base_icms: num(f.baseIcms), valor_icms: num(f.valorIcms),
    base_ipi: num(f.baseIpi), alqt_ipi: num(f.alqtIpi), valor_ipi: num(f.valorIpi),
    base_sub: num(f.baseSub), valor_sub: num(f.valorSub),
    base_iss: num(f.baseIss), valor_iss: num(f.valorIss),
    frete: num(f.frete), seguro: num(f.seguro), despesas: num(f.despesas), desconto: num(f.desconto),
  };
}

function itemToFiscal(it: Item): Fiscal {
  const s = (n: number) => (n ? String(n) : "");
  return {
    qtdUnCompra: String(it.qtd_un_compra || 1), baseIcms: s(it.base_icms), valorIcms: s(it.valor_icms),
    baseIpi: s(it.base_ipi), alqtIpi: s(it.alqt_ipi), valorIpi: s(it.valor_ipi),
    baseSub: s(it.base_sub), valorSub: s(it.valor_sub), baseIss: s(it.base_iss), valorIss: s(it.valor_iss),
    frete: s(it.frete), seguro: s(it.seguro), despesas: s(it.despesas), desconto: s(it.desconto),
  };
}

export default function PedidoCompraScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Pedido de Compra está disponível apenas no web."
        testID="pedido-compra-web-only"
      />
    );
  }

  if (!moduleOn("Curva_abc")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Curva ABC/Compras está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="pedido-compra-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);

  const [codigo, setCodigo] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string | null>(null);
  const [data, setData] = useState<string | null>(null);
  const [resumo, setResumo] = useState<string | null>(null);

  const [fornecedor, setFornecedor] = useState<Fornecedor | null>(null);
  const [fornecedorModalOpen, setFornecedorModalOpen] = useState(false);
  const [fornecedorBusca, setFornecedorBusca] = useState("");
  const [fornecedorResultados, setFornecedorResultados] = useState<Fornecedor[]>([]);

  const [pedidoFornecedor, setPedidoFornecedor] = useState("");
  const [prazo, setPrazo] = useState("");
  const [formaPagamento, setFormaPagamento] = useState("");
  const [transportadora, setTransportadora] = useState("");
  const [dataEntrega, setDataEntrega] = useState<string | null>(null);
  const [acCliente, setAcCliente] = useState("");
  const [tipoFrete, setTipoFrete] = useState<0 | 1>(0);
  const [obsPedido, setObsPedido] = useState("");
  const [saving, setSaving] = useState(false);

  const [itens, setItens] = useState<Item[]>([]);

  const [editingSeq, setEditingSeq] = useState<number | null>(null);
  const [produtoCodigo, setProdutoCodigo] = useState("");
  const [produtoDescricao, setProdutoDescricao] = useState("");
  const [buscandoProduto, setBuscandoProduto] = useState(false);
  const [itemQtd, setItemQtd] = useState("");
  const [itemPUnit, setItemPUnit] = useState("");
  const [fiscal, setFiscal] = useState<Fiscal>(FISCAL_VAZIO);
  const [savingItem, setSavingItem] = useState(false);

  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [ajudaSearch, setAjudaSearch] = useState("");
  const [ajudaResultados, setAjudaResultados] = useState<{ codigo: string; descricao: string }[]>([]);

  const [consultarOpen, setConsultarOpen] = useState(false);
  const [filtroSituacoes, setFiltroSituacoes] = useState<string[]>(["A", "F", "C"]);
  const [filtroDataIni, setFiltroDataIni] = useState<string | null>(null);
  const [filtroDataFim, setFiltroDataFim] = useState<string | null>(null);
  const [filtroTermo, setFiltroTermo] = useState("");
  const [resultados, setResultados] = useState<PedListItem[]>([]);
  const [buscandoConsulta, setBuscandoConsulta] = useState(false);

  const [anexosOpen, setAnexosOpen] = useState(false);
  const [anexosSubGrupo, setAnexosSubGrupo] = useState<number | null>(null);

  const situacaoAberta = !situacao || situacao === "A";
  const podeGravar = can("PEDIDO_COMPRA.GRAVAR") && situacaoAberta;
  const podeExcluir = can("PEDIDO_COMPRA.EXCLUIR") && situacaoAberta;
  const podeAprovar = can("PEDIDO_COMPRA.APROVAR") && situacao === "A";
  const podeRejeitar = can("PEDIDO_COMPRA.REJEITAR") && situacao === "A";
  const podeReabrir = can("PEDIDO_COMPRA.REABRIR") && situacao === "F";
  const podeImprimir = can("PEDIDO_COMPRA.IMPRIMIR") && !!codigo;

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

  const handleNovo = useCallback(() => {
    setCodigo(null); setSituacao(null); setData(null); setResumo(null);
    setFornecedor(null); setPedidoFornecedor(""); setPrazo(""); setFormaPagamento("");
    setTransportadora(""); setDataEntrega(null); setAcCliente(""); setTipoFrete(0); setObsPedido("");
    setItens([]);
    setEditingSeq(null); setProdutoCodigo(""); setProdutoDescricao(""); setItemQtd(""); setItemPUnit(""); setFiscal(FISCAL_VAZIO);
  }, []);

  const carregarPedido = useCallback(async (c: Connection, cod: number) => {
    const r = await apiGet(c, `/api/pedidos-compra/${cod}`);
    if (r?.success) {
      const it = r.item;
      setCodigo(it.codigo); setSituacao(it.situacao || "A"); setData(it.data); setResumo(it.resumo);
      setFornecedor(it.fornecedor ? { codigo_int: it.fornecedor, nome: it.fornecedor_nome, fantasia: it.fornecedor_nome } : null);
      setPedidoFornecedor(it.pedido_fornecedor || "");
      setPrazo(it.prazo != null ? String(it.prazo) : "");
      setFormaPagamento(it.forma_pagamento || "");
      setTransportadora(it.transportadora || "");
      setDataEntrega(it.data_entrega || null);
      setAcCliente(it.ac_cliente || "");
      setTipoFrete(it.tipo_frete === 1 ? 1 : 0);
      setObsPedido(it.obs_pedido || "");
      setItens(it.itens || []);
    } else {
      fb.showError(r?.message || "Não foi possível carregar o pedido.");
    }
  }, [fb]);

  const buscarFornecedor = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/fornecedores", { search: termo });
    if (r?.items) setFornecedorResultados(r.items);
  }, [conn]);

  const selecionarFornecedor = useCallback(async (f: Fornecedor) => {
    setFornecedor(f);
    setFornecedorModalOpen(false);
    if (!conn || prazo.trim()) return;
    const r = await apiGet(conn, `/api/pedidos-compra/fornecedor/${f.codigo_int}`);
    if (r?.success && r.found && r.prazo_pgto) setPrazo(String(r.prazo_pgto));
  }, [conn, prazo]);

  const handleGravarCabecalho = useCallback(async () => {
    if (!conn) return;
    if (!fornecedor) { fb.showError("Selecione o fornecedor."); return; }
    setSaving(true);
    try {
      const r = await apiSend(conn, "/api/pedidos-compra", "POST", {
        codigo, data: data || new Date().toISOString().slice(0, 10), fornecedor: fornecedor.codigo_int,
        pedido_fornecedor: pedidoFornecedor.trim() || undefined,
        prazo: prazo.trim() ? parseInt(prazo, 10) : undefined,
        forma_pagamento: formaPagamento.trim() || undefined,
        ac_cliente: acCliente.trim() || undefined,
        transportadora: transportadora.trim() || undefined,
        data_entrega: dataEntrega || undefined,
        obs_pedido: obsPedido.trim() || undefined,
        tipo_frete: tipoFrete,
        ...auditCtx,
      });
      if (r?.success) {
        fb.showSuccess("Pedido gravado.");
        await carregarPedido(conn, r.codigo);
      } else {
        fb.showError(r?.message || "Não foi possível gravar o pedido.");
      }
    } finally {
      setSaving(false);
    }
  }, [conn, fornecedor, codigo, data, pedidoFornecedor, prazo, formaPagamento, acCliente, transportadora, dataEntrega, obsPedido, tipoFrete, auditCtx, fb, carregarPedido]);

  const resolverProduto = useCallback(async (termo: string) => {
    if (!conn) return;
    const t = termo.trim();
    if (!t) { setProdutoDescricao(""); return; }
    setBuscandoProduto(true);
    try {
      const r = await apiGet(conn, `/api/pedidos-compra/produto/${encodeURIComponent(t)}`);
      if (r?.success && r.found) {
        setProdutoCodigo(r.codigo);
        setProdutoDescricao(r.descricao);
        if (!itemPUnit.trim()) setItemPUnit(String(r.custo_medio || 0));
      } else {
        setProdutoDescricao("");
        fb.showError("Produto não cadastrado.");
      }
    } finally {
      setBuscandoProduto(false);
    }
  }, [conn, itemPUnit, fb]);

  const buscarAjuda = useCallback(async (termo: string) => {
    if (!conn) return;
    const r = await apiGet(conn, "/api/produtos-servicos", { search: termo, tipo: "P", size: 30 });
    if (r?.items) setAjudaResultados(r.items.map((it: any) => ({ codigo: it.codigo, descricao: it.descricao })));
  }, [conn]);

  const iniciarEdicaoItem = useCallback((it: Item) => {
    setEditingSeq(it.seq);
    setProdutoCodigo(it.codigo_int); setProdutoDescricao(it.produto_descricao || "");
    setItemQtd(String(it.qtd)); setItemPUnit(String(it.p_unit));
    setFiscal(itemToFiscal(it));
  }, []);

  const cancelarEdicaoItem = useCallback(() => {
    setEditingSeq(null);
    setProdutoCodigo(""); setProdutoDescricao(""); setItemQtd(""); setItemPUnit(""); setFiscal(FISCAL_VAZIO);
  }, []);

  const salvarItem = useCallback(async () => {
    if (!conn || !codigo) return;
    const qtdNum = num(itemQtd);
    if (!qtdNum || qtdNum <= 0) { fb.showError("Informe uma quantidade válida."); return; }
    const pUnitNum = num(itemPUnit);
    setSavingItem(true);
    try {
      const payload = { qtd: qtdNum, p_unit: pUnitNum, fiscal: fiscalToPayload(fiscal), ...auditCtx };
      const r = editingSeq
        ? await apiSend(conn, `/api/pedidos-compra/itens/${editingSeq}/editar`, "POST", payload)
        : await apiSend(conn, `/api/pedidos-compra/${codigo}/itens`, "POST", { ...payload, produto: produtoCodigo.trim() });
      if (r?.success) {
        await carregarPedido(conn, codigo);
        cancelarEdicaoItem();
      } else {
        fb.showError(r?.message || "Não foi possível gravar o item.");
      }
    } finally {
      setSavingItem(false);
    }
  }, [conn, codigo, itemQtd, itemPUnit, fiscal, editingSeq, produtoCodigo, auditCtx, fb, carregarPedido, cancelarEdicaoItem]);

  const excluirItem = useCallback((it: Item) => {
    if (!conn || !codigo) return;
    fb.showConfirm(
      `Confirma excluir o item "${it.produto_descricao || it.codigo_int}"?`,
      async () => {
        const r = await apiSend(conn, `/api/pedidos-compra/itens/${it.seq}/excluir`, "POST", auditCtx);
        if (r?.success) await carregarPedido(conn, codigo);
        else fb.showError(r?.message || "Não foi possível excluir o item.");
      },
      { destructive: true, confirmText: "Excluir" },
    );
  }, [conn, codigo, auditCtx, fb, carregarPedido]);

  const acaoPedido = useCallback((
    endpoint: string, mensagemConfirma: string, mensagemSucesso: string, destructive = false,
  ) => {
    if (!conn || !codigo) return;
    fb.showConfirm(mensagemConfirma, async () => {
      const r = await apiSend(conn, `/api/pedidos-compra/${codigo}/${endpoint}`, "POST", auditCtx);
      if (r?.success) {
        fb.showSuccess(mensagemSucesso);
        await carregarPedido(conn, codigo);
      } else {
        fb.showError(r?.message || "Não foi possível concluir a ação.");
      }
    }, { destructive, confirmText: destructive ? "Confirmar" : undefined });
  }, [conn, codigo, auditCtx, fb, carregarPedido]);

  const handleImprimir = useCallback(async () => {
    if (!conn || !codigo) return;
    const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
    const linhas = itens.map((it) => `
      <div class="row3">
        <span>${escHtml(it.codigo_int)} — ${escHtml(it.produto_descricao || "")}</span>
        <span>${it.qtd} x ${money(it.p_unit)}</span>
        <span>${money(it.qtd * it.p_unit)}</span>
      </div>`).join("");
    const html = `
      <style>${REPORT_HEADER_CSS}</style>
      ${buildReportHeaderHtml(empresa, `Pedido de Compra nº ${codigo}`)}
      <div class="mb"><b>Fornecedor:</b> ${escHtml(fornecedor?.fantasia || fornecedor?.nome || "")} &nbsp;
      <b>Data:</b> ${data ? new Date(data + "T00:00:00").toLocaleDateString("pt-BR") : ""} &nbsp;
      <b>Situação:</b> ${SIT_LABEL[situacao || "A"]}</div>
      ${pedidoFornecedor ? `<div class="mb"><b>Pedido Fornecedor:</b> ${escHtml(pedidoFornecedor)}</div>` : ""}
      ${obsPedido ? `<div class="mb"><b>Obs.:</b> ${escHtml(obsPedido)}</div>` : ""}
      <div class="hr"></div>
      ${linhas}
      <div class="hr"></div>
      <div class="row big"><span>Total</span><span>${money(total)}</span></div>
    `;
    printHtml(html, `Pedido de Compra ${codigo}`);
  }, [conn, codigo, itens, data, situacao, fornecedor, pedidoFornecedor, obsPedido, total]);

  const buscarConsulta = useCallback(async () => {
    if (!conn) return;
    setBuscandoConsulta(true);
    try {
      const r = await apiGet(conn, "/api/pedidos-compra", {
        situacao: filtroSituacoes.join(","),
        data_ini: filtroDataIni || undefined,
        data_fim: filtroDataFim || undefined,
        termo: filtroTermo.trim() || undefined,
      });
      setResultados(r?.items || []);
    } finally {
      setBuscandoConsulta(false);
    }
  }, [conn, filtroSituacoes, filtroDataIni, filtroDataFim, filtroTermo]);

  const abrirConsultar = useCallback(() => {
    setConsultarOpen(true);
    setFiltroSituacoes(["A", "F", "C"]); setFiltroDataIni(null); setFiltroDataFim(null); setFiltroTermo("");
    setResultados([]);
    buscarConsulta();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleFiltroSituacao = (s: string) => {
    setFiltroSituacoes((prev) => (prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]));
  };

  const selecionarPedido = useCallback(async (cod: number) => {
    if (!conn) return;
    setConsultarOpen(false);
    await carregarPedido(conn, cod);
  }, [conn, carregarPedido]);

  const abrirAnexos = useCallback(async () => {
    if (!conn) return;
    setAnexosOpen(true);
    if (!anexosSubGrupo) {
      const r = await apiSend(conn, "/api/gestor-documentos/sub-grupos", "POST", {
        cod_grupo: GESTOR_DOC_GRUPO_FORNECEDOR, descricao: "Pedidos de Compra", ...auditCtx,
      });
      if (r?.success) setAnexosSubGrupo(r.cod_sub_grupo);
    }
  }, [conn, anexosSubGrupo, auditCtx]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="pedido-compra-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Pedido de Compra</Text>
        <View style={styles.back} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.guideCard}>
            <Ionicons name="bulb-outline" size={20} color={colors.brandPrimary} />
            <Text style={styles.guideText}>
              Registre o pedido formal enviado ao fornecedor: escolha o fornecedor, preencha os dados de entrega e
              inclua os produtos. Depois de incluir os itens, use <Text style={styles.guideBold}>Aprovar</Text> para
              confirmar o pedido ou <Text style={styles.guideBold}>Rejeitar</Text> para descartá-lo.
            </Text>
          </View>

          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Nº</Text>
                <Text style={styles.readonlyValue}>{codigo ?? "Novo"}</Text>
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
                <Text style={styles.label}>Data do Pedido</Text>
                <WebDateField value={data} onChange={setData} testID="pedido-compra-data" disabled={!situacaoAberta} />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Fornecedor</Text>
                {fornecedor ? (
                  <View style={styles.selectedChipRow}>
                    <View style={styles.selectedChip}>
                      <Text style={styles.selectedChipText} numberOfLines={1}>{fornecedor.fantasia || fornecedor.nome}</Text>
                      {situacaoAberta ? (
                        <Pressable onPress={() => setFornecedor(null)} hitSlop={6}>
                          <Ionicons name="close-circle" size={16} color={colors.onBrandPrimary} />
                        </Pressable>
                      ) : null}
                    </View>
                  </View>
                ) : (
                  <Pressable
                    style={styles.pickerBtn}
                    onPress={() => { setFornecedorModalOpen(true); setFornecedorBusca(""); setFornecedorResultados([]); }}
                    testID="pedido-compra-fornecedor-btn"
                  >
                    <Ionicons name="business-outline" size={16} color={colors.muted} />
                    <Text style={styles.pickerBtnText}>Selecionar fornecedor</Text>
                  </Pressable>
                )}
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Pedido Fornecedor</Text>
                <TextInput style={[styles.input, !situacaoAberta && styles.inputDisabled]} value={pedidoFornecedor} onChangeText={setPedidoFornecedor} editable={situacaoAberta} testID="pedido-compra-pedido-fornecedor" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Prazo (dias)</Text>
                <TextInput style={[styles.input, !situacaoAberta && styles.inputDisabled]} value={prazo} onChangeText={setPrazo} editable={situacaoAberta} keyboardType="numeric" testID="pedido-compra-prazo" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Forma de Pagamento</Text>
                <TextInput style={[styles.input, !situacaoAberta && styles.inputDisabled]} value={formaPagamento} onChangeText={setFormaPagamento} editable={situacaoAberta} testID="pedido-compra-forma-pag" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Transportadora</Text>
                <TextInput style={[styles.input, !situacaoAberta && styles.inputDisabled]} value={transportadora} onChangeText={setTransportadora} editable={situacaoAberta} testID="pedido-compra-transportadora" />
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Previsão de Entrega</Text>
                <WebDateField value={dataEntrega} onChange={setDataEntrega} testID="pedido-compra-data-entrega" disabled={!situacaoAberta} />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Aos Cuidados</Text>
                <TextInput style={[styles.input, !situacaoAberta && styles.inputDisabled]} value={acCliente} onChangeText={setAcCliente} editable={situacaoAberta} testID="pedido-compra-ac" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Tipo de Frete</Text>
                <View style={styles.chipsRow}>
                  <Pressable
                    onPress={() => situacaoAberta && setTipoFrete(0)}
                    style={[styles.chip, tipoFrete === 0 && styles.chipSel]}
                    testID="pedido-compra-frete-cif"
                  >
                    <Text style={[styles.chipText, tipoFrete === 0 && styles.chipTextSel]}>CIF</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => situacaoAberta && setTipoFrete(1)}
                    style={[styles.chip, tipoFrete === 1 && styles.chipSel]}
                    testID="pedido-compra-frete-fob"
                  >
                    <Text style={[styles.chipText, tipoFrete === 1 && styles.chipTextSel]}>FOB</Text>
                  </Pressable>
                </View>
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Obs.</Text>
                <TextInput
                  style={[styles.input, styles.inputMultiline, !situacaoAberta && styles.inputDisabled]}
                  value={obsPedido} onChangeText={setObsPedido} editable={situacaoAberta} multiline
                  testID="pedido-compra-obs"
                />
              </View>
            </View>

            {resumo ? (
              <AccordionSection title="Histórico do pedido" testID="pedido-compra-historico">
                <Text style={styles.historicoText}>{resumo}</Text>
              </AccordionSection>
            ) : null}

            <View style={styles.toolbarRow}>
              {codigo ? (
                <Pressable style={ps.secondaryBtn} onPress={handleNovo} testID="pedido-compra-novo-btn">
                  <Text style={ps.secondaryBtnText}>Novo</Text>
                </Pressable>
              ) : null}
              {podeGravar ? (
                <Pressable style={[styles.actionBtn, saving && { opacity: 0.6 }]} onPress={handleGravarCabecalho} disabled={saving} testID="pedido-compra-gravar-btn">
                  <Text style={styles.actionBtnText}>{saving ? "Gravando…" : "Gravar"}</Text>
                </Pressable>
              ) : null}
              {podeAprovar ? (
                <Pressable
                  style={styles.actionBtn}
                  onPress={() => acaoPedido("aprovar", "Confirma aprovar este pedido de compra?", "Pedido aprovado.")}
                  testID="pedido-compra-aprovar-btn"
                >
                  <Text style={styles.actionBtnText}>Aprovar</Text>
                </Pressable>
              ) : null}
              {podeRejeitar ? (
                <Pressable
                  style={[styles.actionBtn, styles.dangerBtn]}
                  onPress={() => acaoPedido("rejeitar", "Confirma rejeitar este pedido de compra?", "Pedido rejeitado.", true)}
                  testID="pedido-compra-rejeitar-btn"
                >
                  <Text style={[styles.actionBtnText, styles.dangerBtnText]}>Rejeitar</Text>
                </Pressable>
              ) : null}
              {podeReabrir ? (
                <Pressable
                  style={styles.actionBtn}
                  onPress={() => acaoPedido("reabrir", "Confirma reabrir este pedido de compra?", "Pedido reaberto.")}
                  testID="pedido-compra-reabrir-btn"
                >
                  <Text style={styles.actionBtnText}>Reabrir</Text>
                </Pressable>
              ) : null}
              {podeImprimir ? (
                <Pressable style={ps.secondaryBtn} onPress={handleImprimir} testID="pedido-compra-imprimir-btn">
                  <Text style={ps.secondaryBtnText}>Imprimir</Text>
                </Pressable>
              ) : null}
              {codigo ? (
                <Pressable style={ps.secondaryBtn} onPress={abrirAnexos} testID="pedido-compra-anexos-btn">
                  <Text style={ps.secondaryBtnText}>Anexos</Text>
                </Pressable>
              ) : null}
              <Pressable style={styles.consultarBtnInline} onPress={abrirConsultar} testID="pedido-compra-consultar-btn">
                <Ionicons name="search-outline" size={18} color={colors.onBrandPrimary} />
              </Pressable>
            </View>
          </View>

          {codigo ? (
            <View style={styles.card}>
              {podeGravar ? (
                <>
                  <Text style={styles.sectionTitle}>{editingSeq ? "Editar Item" : "Adicionar Item"}</Text>
                  <View style={styles.rowFields}>
                    <View style={styles.colProduto}>
                      <Text style={styles.label}>Produto</Text>
                      <View style={styles.inputWithBtn}>
                        <TextInput
                          style={[styles.input, { flex: 1, minWidth: 0 }, !!editingSeq && styles.inputDisabled]}
                          value={produtoCodigo}
                          onChangeText={(v) => { setProdutoCodigo(v); setProdutoDescricao(""); }}
                          onBlur={() => resolverProduto(produtoCodigo)}
                          editable={!editingSeq}
                          placeholder="Código do produto"
                          testID="pedido-compra-produto"
                        />
                        {!editingSeq ? (
                          <Pressable
                            style={styles.helpBtn}
                            onPress={() => { setAjudaOpen(true); setAjudaSearch(""); setAjudaResultados([]); }}
                            testID="pedido-compra-ajuda-btn"
                          >
                            <Ionicons name="list-outline" size={18} color={colors.brandPrimary} />
                          </Pressable>
                        ) : null}
                      </View>
                    </View>
                    <View style={styles.colTiny}>
                      <Text style={styles.label}>Quantidade</Text>
                      <TextInput style={styles.input} value={itemQtd} onChangeText={setItemQtd} keyboardType="numeric" testID="pedido-compra-item-qtd" />
                    </View>
                    <View style={styles.colTiny}>
                      <Text style={styles.label}>Preço Unit.</Text>
                      <TextInput style={styles.input} value={itemPUnit} onChangeText={setItemPUnit} keyboardType="numeric" testID="pedido-compra-item-preco" />
                    </View>
                  </View>
                  {buscandoProduto ? <Text style={styles.hint}>Buscando…</Text> : null}
                  {produtoDescricao ? <Text style={styles.hint}>{produtoDescricao}</Text> : null}

                  <AccordionSection title="Impostos e Custos Adicionais (opcional)" testID="pedido-compra-fiscal">
                    <View style={styles.rowFields}>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Qtd Un. Compra</Text>
                        <TextInput style={styles.input} value={fiscal.qtdUnCompra} onChangeText={(v) => setFiscal((f) => ({ ...f, qtdUnCompra: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Base ICMS</Text>
                        <TextInput style={styles.input} value={fiscal.baseIcms} onChangeText={(v) => setFiscal((f) => ({ ...f, baseIcms: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Valor ICMS</Text>
                        <TextInput style={styles.input} value={fiscal.valorIcms} onChangeText={(v) => setFiscal((f) => ({ ...f, valorIcms: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Base IPI</Text>
                        <TextInput style={styles.input} value={fiscal.baseIpi} onChangeText={(v) => setFiscal((f) => ({ ...f, baseIpi: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Alíq. IPI (%)</Text>
                        <TextInput style={styles.input} value={fiscal.alqtIpi} onChangeText={(v) => setFiscal((f) => ({ ...f, alqtIpi: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Valor IPI</Text>
                        <TextInput style={styles.input} value={fiscal.valorIpi} onChangeText={(v) => setFiscal((f) => ({ ...f, valorIpi: v }))} keyboardType="numeric" />
                      </View>
                    </View>
                    <View style={styles.rowFields}>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Base ICMS-ST</Text>
                        <TextInput style={styles.input} value={fiscal.baseSub} onChangeText={(v) => setFiscal((f) => ({ ...f, baseSub: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Valor ICMS-ST</Text>
                        <TextInput style={styles.input} value={fiscal.valorSub} onChangeText={(v) => setFiscal((f) => ({ ...f, valorSub: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Base ISS</Text>
                        <TextInput style={styles.input} value={fiscal.baseIss} onChangeText={(v) => setFiscal((f) => ({ ...f, baseIss: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Valor ISS</Text>
                        <TextInput style={styles.input} value={fiscal.valorIss} onChangeText={(v) => setFiscal((f) => ({ ...f, valorIss: v }))} keyboardType="numeric" />
                      </View>
                    </View>
                    <View style={styles.rowFields}>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Frete</Text>
                        <TextInput style={styles.input} value={fiscal.frete} onChangeText={(v) => setFiscal((f) => ({ ...f, frete: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Seguro</Text>
                        <TextInput style={styles.input} value={fiscal.seguro} onChangeText={(v) => setFiscal((f) => ({ ...f, seguro: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Despesas</Text>
                        <TextInput style={styles.input} value={fiscal.despesas} onChangeText={(v) => setFiscal((f) => ({ ...f, despesas: v }))} keyboardType="numeric" />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.label}>Desconto</Text>
                        <TextInput style={styles.input} value={fiscal.desconto} onChangeText={(v) => setFiscal((f) => ({ ...f, desconto: v }))} keyboardType="numeric" />
                      </View>
                    </View>
                  </AccordionSection>

                  <View style={styles.toolbarRow}>
                    <Pressable
                      style={[styles.incluirBtn, savingItem && { opacity: 0.6 }]}
                      onPress={salvarItem}
                      disabled={savingItem}
                      testID="pedido-compra-salvar-item-btn"
                    >
                      <Ionicons name={editingSeq ? "checkmark-circle-outline" : "add-circle-outline"} size={18} color={colors.onBrandPrimary} />
                      <Text style={styles.incluirBtnText}>{savingItem ? "Gravando…" : editingSeq ? "Salvar Alterações" : "Incluir Item"}</Text>
                    </Pressable>
                    {editingSeq ? (
                      <Pressable style={ps.secondaryBtn} onPress={cancelarEdicaoItem} testID="pedido-compra-cancelar-edicao-btn">
                        <Text style={ps.secondaryBtnText}>Cancelar</Text>
                      </Pressable>
                    ) : null}
                  </View>
                </>
              ) : null}

              <Text style={styles.sectionTitle}>Itens ({itens.length})</Text>
              {itens.map((it) => (
                <Pressable key={it.seq} style={styles.itemRow} onPress={() => podeGravar && iniciarEdicaoItem(it)}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemTitle}>{it.codigo_int} — {it.produto_descricao}</Text>
                    <Text style={styles.itemSub}>{it.qtd} x {money(it.p_unit)} = {money(it.qtd * it.p_unit)}</Text>
                  </View>
                  {podeExcluir ? (
                    <Pressable style={ps.deleteBtn} onPress={() => excluirItem(it)} testID={`pedido-compra-excluir-item-${it.seq}`}>
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                    </Pressable>
                  ) : null}
                </Pressable>
              ))}
              {itens.length === 0 ? <Text style={styles.hint}>Nenhum item incluído.</Text> : null}
              {itens.length > 0 ? (
                <View style={styles.totalRow}>
                  <Text style={styles.totalLabel}>Total</Text>
                  <Text style={styles.totalValue}>{money(total)}</Text>
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>

      {/* Fornecedor — busca */}
      <AppModal visible={fornecedorModalOpen} transparent animationType="fade" onRequestClose={() => setFornecedorModalOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Buscar Fornecedor</Text>
              <Pressable onPress={() => setFornecedorModalOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={ps.searchWrap}>
              <Ionicons name="search-outline" size={18} color={colors.muted} />
              <TextInput
                style={ps.searchInput}
                value={fornecedorBusca}
                onChangeText={(v) => { setFornecedorBusca(v); buscarFornecedor(v); }}
                placeholder="Nome ou código"
                autoFocus
                testID="pedido-compra-fornecedor-search"
              />
            </View>
            <ScrollView style={{ maxHeight: 360 }}>
              {fornecedorResultados.map((f) => (
                <Pressable key={f.codigo_int} style={ps.resultRow} onPress={() => selecionarFornecedor(f)}>
                  <View style={{ flex: 1 }}>
                    <Text style={ps.resultNome}>{f.fantasia || f.nome}</Text>
                    <Text style={ps.resultSub}>{f.nome}</Text>
                  </View>
                </Pressable>
              ))}
              {fornecedorResultados.length === 0 ? <Text style={ps.emptyText}>Digite pra buscar.</Text> : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>

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
                testID="pedido-compra-ajuda-search"
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

      {/* Consultar — lista de pedidos */}
      <AppModal visible={consultarOpen} transparent animationType="fade" onRequestClose={() => setConsultarOpen(false)}>
        <View style={[ps.modalBg, ps.modalBgWebCompact]}>
          <View style={[ps.modalCard, ps.modalCardWebCompact, { maxWidth: 780 }]}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Consultar Pedidos de Compra</Text>
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
                  testID="pedido-compra-filtro-de"
                  onSubmitEditing={() => {
                    document.querySelector<HTMLInputElement>('[data-testid="pedido-compra-filtro-ate"]')?.focus();
                  }}
                />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Até</Text>
                <WebDateField value={filtroDataFim} onChange={setFiltroDataFim} testID="pedido-compra-filtro-ate" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Pedido Fornecedor / Obs.</Text>
                <TextInput style={styles.input} value={filtroTermo} onChangeText={setFiltroTermo} testID="pedido-compra-filtro-termo" />
              </View>
              <Pressable style={styles.buscarBtnInline} onPress={buscarConsulta} testID="pedido-compra-buscar-btn">
                <Ionicons name="search-outline" size={16} color={colors.onBrandPrimary} />
                <Text style={styles.buscarBtnInlineText}>{buscandoConsulta ? "Buscando…" : "Buscar"}</Text>
              </Pressable>
            </View>

            <ScrollView style={{ maxHeight: 380, marginTop: spacing.md }}>
              {resultados.map((r) => (
                <Pressable key={r.codigo} style={styles.resultRow} onPress={() => selecionarPedido(r.codigo)}>
                  <View style={[styles.sitBadge, { backgroundColor: SIT_COLOR[r.situacao] || colors.muted }]}>
                    <Text style={styles.sitBadgeText}>{r.codigo}</Text>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultTitle}>{r.fornecedor_nome || "—"}{r.pedido_fornecedor ? ` · Ped. Forn. ${r.pedido_fornecedor}` : ""}</Text>
                    <Text style={styles.resultSub}>
                      {new Date(r.data + "T00:00:00").toLocaleDateString("pt-BR")} · {SIT_LABEL[r.situacao] || r.situacao} · {r.total_itens} item(ns) · {money(r.total)}
                    </Text>
                  </View>
                </Pressable>
              ))}
              {resultados.length === 0 && !buscandoConsulta ? (
                <Text style={ps.emptyText}>Nenhum pedido encontrado.</Text>
              ) : null}
            </ScrollView>
          </View>
        </View>
      </AppModal>

      {/* Anexos */}
      <AppModal visible={anexosOpen} transparent animationType="slide" onRequestClose={() => setAnexosOpen(false)}>
        <View style={styles.anexosBg}>
          <View style={styles.anexosCard}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Anexos do Pedido nº {codigo}</Text>
              <Pressable onPress={() => setAnexosOpen(false)} hitSlop={10}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {conn && fornecedor && anexosSubGrupo ? (
              <ScrollView style={{ maxHeight: 560 }}>
                <GestorDocumentosSection
                  api={conn.api}
                  servidor={conn.servidor}
                  banco={conn.banco}
                  codGrupo={GESTOR_DOC_GRUPO_FORNECEDOR}
                  codigoEntidade={fornecedor.codigo_int}
                  codSubGrupo={anexosSubGrupo}
                  referencia={codigo || undefined}
                />
              </ScrollView>
            ) : (
              <Text style={styles.hint}>Carregando…</Text>
            )}
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
    padding: spacing.md, marginBottom: spacing.md,
  },
  guideText: { flex: 1, fontSize: 12.5, color: colors.onSurface, lineHeight: 18 },
  guideBold: { fontWeight: "700" },
  card: { ...WEB_FILTER_CARD, gap: spacing.md, marginBottom: spacing.md },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  readonlyValue: { fontSize: 14, color: colors.onSurface, fontWeight: "500", paddingVertical: 8 },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4 },
  historicoText: { fontSize: 12, color: colors.onSurface, lineHeight: 18 },
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
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 180 },
  colProduto: { width: 220 },
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
  chipsRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm, flexWrap: "wrap" },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: "#fff" },
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
  resultRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultTitle: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  anexosBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)",
    justifyContent: "center", alignItems: "center", padding: spacing.xl,
  },
  anexosCard: {
    width: "100%", maxWidth: 920, maxHeight: "88%",
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg,
  },
});
