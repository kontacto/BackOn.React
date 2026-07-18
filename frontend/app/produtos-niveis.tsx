import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { buildTree, NivelFlat, NivelNode } from "@/src/utils/nivelTree";

type ModoFiltro = "nivel" | "ncm";
type TabKey = "gravar" | "reajuste" | "leiTransp" | "estoque";

const TABS: { key: TabKey; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { key: "gravar", label: "Gravar Campos", icon: "create-outline" },
  { key: "reajuste", label: "Reajuste de Preço", icon: "pricetag-outline" },
  { key: "leiTransp", label: "% Lei Transparência", icon: "receipt-outline" },
  { key: "estoque", label: "Utilidades de Estoque", icon: "cube-outline" },
];

const TIPO_GARANTIA_OPTIONS: SelectOption[] = [
  { value: "0", label: "Nenhum" },
  { value: "1", label: "Ano(s)" },
  { value: "2", label: "Dia(s)" },
  { value: "3", label: "Hora(s)" },
  { value: "4", label: "Mês(es)" },
  { value: "5", label: "Km" },
];

const POLITICA_PRECO_OPTIONS: SelectOption[] = [
  { value: "E", label: "Entrada" },
  { value: "C", label: "Controlado" },
  { value: "T", label: "Tabelado" },
  { value: "N", label: "Não atualizar" },
];

const SIM_NAO_OPTIONS: SelectOption[] = [
  { value: "sim", label: "Sim" },
  { value: "nao", label: "Não" },
];

function numOrNull(s: string): number | null {
  const t = (s || "").trim().replace(",", ".");
  if (!t) return null;
  const n = parseFloat(t);
  return isNaN(n) ? null : n;
}
function intOrNull(s: string): number | null {
  const t = (s || "").trim();
  if (!t) return null;
  const n = parseInt(t, 10);
  return isNaN(n) ? null : n;
}
function strOrNull(s: string): string | null {
  const t = (s || "").trim();
  return t ? t : null;
}
function boolOrNull(s: "sim" | "nao" | ""): boolean | null {
  if (s === "sim") return true;
  if (s === "nao") return false;
  return null;
}

type CamposGravar = {
  cstPis: string; percValorPis: string; cstCofins: string; percValorCofins: string; codIcms: string;
  percMva: string; outrosTribFederais: string;
  descG: string; descS: string; descV: string;
  comissao: string; valorComissao: string; valorDescBaseComissao: string;
  comissaoE: string; valorComissaoE: string; valorDescBaseComissaoE: string;
  comissaoA: string; valorComissaoA: string; valorDescBaseComissaoA: string;
  pagaComissao: "sim" | "nao" | ""; aceitaDesconto: "sim" | "nao" | "";
  tipoGarantia: string; prazoGarantia: string;
  margemLucro: string; margemTabela: string;
  estoqueMinimo: string; origem: string; tipoPeca: string; politicaPreco: string;
  precoVariado: "sim" | "nao" | ""; situacao: string;
  ufProtocoloSt: string;
};

const CAMPOS_INICIAL: CamposGravar = {
  cstPis: "", percValorPis: "", cstCofins: "", percValorCofins: "", codIcms: "",
  percMva: "", outrosTribFederais: "",
  descG: "", descS: "", descV: "",
  comissao: "", valorComissao: "", valorDescBaseComissao: "",
  comissaoE: "", valorComissaoE: "", valorDescBaseComissaoE: "",
  comissaoA: "", valorComissaoA: "", valorDescBaseComissaoA: "",
  pagaComissao: "", aceitaDesconto: "",
  tipoGarantia: "", prazoGarantia: "",
  margemLucro: "", margemTabela: "",
  estoqueMinimo: "", origem: "", tipoPeca: "", politicaPreco: "",
  precoVariado: "", situacao: "",
  ufProtocoloSt: "",
};

type PreviewResult = { total_pecas: number; total_servicos: number; total: number };
type PreviewItem = { tipo: "P" | "S"; codigo: string; descricao: string; valor: number; custo_reposicao: number | null };

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

// Mesmo limite de "backend/services/produtos_niveis_service.py::PREVIEW_ITENS_LIMITE"
// — só afeta a listagem de conferência, não a ação em massa em si.
const PREVIEW_ITENS_LIMITE = 300;
type ConfirmState = { title: string; message: string; run: () => Promise<void> };

// Alterações Cadastro de Produtos Níveis — alteração em massa de pecas/servicos
// filtrando por faixa de NCM (codigo_mercosul) ou por nível (grupo mercadológico,
// tabela `niveis`). Legado VB6: FrmAltNiv. Web-only.
export default function ProdutosNiveisScreen() {
  const router = useRouter();
  const { can, isMaster, isManagerFuncao, classe, moduleOn } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Alterações Cadastro de Produtos/Serviços Níveis está disponível apenas no web."
        testID="produtos-niveis-web-only"
      />
    );
  }
  if (!can("PRODUTO_NIVEIS.ABRIR")) {
    return <LockedView testID="produtos-niveis-locked" />;
  }

  return (
    <ProdutosNiveisWebScreen
      router={router} can={can} isMaster={isMaster} isManagerFuncao={isManagerFuncao}
      classe={classe} servicosOn={moduleOn("servicos")}
    />
  );
}

function ProdutosNiveisWebScreen({
  router, can, isMaster, isManagerFuncao, classe, servicosOn,
}: {
  router: ReturnType<typeof useRouter>;
  can: (perm: string) => boolean;
  isMaster: boolean;
  isManagerFuncao: boolean;
  classe: number | null;
  servicosOn: boolean;
}) {
  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioAlteracao, setUsuarioAlteracao] = useState<number | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 1500); };

  // ---------------- Filtro ----------------
  const [modoFiltro, setModoFiltro] = useState<ModoFiltro>("nivel");
  const [niveisFlat, setNiveisFlat] = useState<NivelFlat[]>([]);
  const [nivelExpanded, setNivelExpanded] = useState<Set<number>>(new Set());
  const [nivelSelecionado, setNivelSelecionado] = useState<number | null>(null);
  const [nivelIncluirInferiores, setNivelIncluirInferiores] = useState(true);
  const [ncmDe, setNcmDe] = useState("");
  const [ncmAte, setNcmAte] = useState("");
  const [incluirPecas, setIncluirPecas] = useState(true);
  const [incluirServicos, setIncluirServicos] = useState(true);

  // ---------------- Lookups ----------------
  const [cstPisOptions, setCstPisOptions] = useState<SelectOption[]>([]);
  const [cstCofinsOptions, setCstCofinsOptions] = useState<SelectOption[]>([]);
  const [icmsOptions, setIcmsOptions] = useState<SelectOption[]>([]);
  const [origemOptions, setOrigemOptions] = useState<SelectOption[]>([]);
  const [tipoPecaOptions, setTipoPecaOptions] = useState<SelectOption[]>([]);
  const [ufOptions, setUfOptions] = useState<SelectOption[]>([]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      const func = (s.funcionario ?? {}) as Record<string, unknown>;
      const fid = func?.codigo_int ?? func?.codigo;
      setUsuarioAlteracao(fid != null ? parseInt(String(fid), 10) : null);

      const j = await apiGet(c, "/api/tabelas/grupos-mercadologicos");
      setNiveisFlat(j?.success ? j.items || [] : []);

      const toOpts = (items: { codigo: string | number; descricao: string }[]): SelectOption[] =>
        items.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));
      const loadLookup = async (path: string, setter: (o: SelectOption[]) => void) => {
        try {
          const r = await apiGet(c, path);
          if (r?.success && Array.isArray(r.items)) setter(toOpts(r.items));
        } catch { /* lookup opcional */ }
      };
      await Promise.all([
        loadLookup("/api/cst-pis", setCstPisOptions),
        loadLookup("/api/cst-cofins", setCstCofinsOptions),
        loadLookup("/api/tabelas/icms", setIcmsOptions),
        loadLookup("/api/tabelas/origem", setOrigemOptions),
        loadLookup("/api/tipo-peca", setTipoPecaOptions),
        loadLookup("/api/uf", setUfOptions),
      ]);
    })();
  }, [router]);

  const nivelTree = useMemo(() => buildTree(niveisFlat), [niveisFlat]);
  const nivelSelecionadoNode = useMemo(() => {
    const flatten = (nodes: NivelNode[]): NivelNode[] => nodes.flatMap((n) => [n, ...flatten(n.children)]);
    return flatten(nivelTree).find((n) => n.cod_nivel === nivelSelecionado) || null;
  }, [nivelTree, nivelSelecionado]);

  const toggleNivelExpand = (cod: number) => {
    setNivelExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(cod)) next.delete(cod); else next.add(cod);
      return next;
    });
  };

  // ---------------- Slide de seleção de Nível ----------------
  const [nivelModalVisible, setNivelModalVisible] = useState(false);
  const [nivelSearch, setNivelSearch] = useState("");
  const nivelTerm = nivelSearch.trim().toLowerCase();
  const matchesNivelSearch = useCallback((n: NivelNode): boolean =>
    n.descricao.toLowerCase().includes(nivelTerm) || n.children.some(matchesNivelSearch), [nivelTerm]);
  const visibleNivelTree = nivelTerm ? nivelTree.filter(matchesNivelSearch) : nivelTree;

  useEffect(() => {
    if (!nivelTerm) return;
    setNivelExpanded((prev) => {
      const next = new Set(prev);
      const walk = (nodes: NivelNode[]) => {
        for (const n of nodes) {
          if (matchesNivelSearch(n)) next.add(n.cod_nivel);
          walk(n.children);
        }
      };
      walk(nivelTree);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nivelTerm]);

  const selecionarNivel = (cod: number) => {
    setNivelSelecionado(cod);
    setNivelModalVisible(false);
    setNivelSearch("");
  };

  // Ao abrir o slide, já expande os níveis raiz para o usuário ver a árvore
  // de cara, sem precisar clicar em cada seta.
  const abrirNivelModal = () => {
    setNivelExpanded((prev) => {
      const next = new Set(prev);
      nivelTree.forEach((n) => next.add(n.cod_nivel));
      return next;
    });
    setNivelModalVisible(true);
  };

  const filtroBody = useCallback(() => ({
    modo_filtro: modoFiltro,
    nivel_cod_nivel: modoFiltro === "nivel" ? nivelSelecionado : null,
    nivel_incluir_inferiores: nivelIncluirInferiores,
    ncm_de: modoFiltro === "ncm" ? ncmDe.trim() : null,
    ncm_ate: modoFiltro === "ncm" ? ncmAte.trim() : null,
    incluir_pecas: incluirPecas,
    incluir_servicos: servicosOn && incluirServicos,
    classe, master: isMaster,
    usuario_alteracao: usuarioAlteracao,
    plataforma: Platform.OS,
  }), [modoFiltro, nivelSelecionado, nivelIncluirInferiores, ncmDe, ncmAte, incluirPecas, incluirServicos, servicosOn, classe, isMaster, usuarioAlteracao]);

  const currentSignature = JSON.stringify(filtroBody());

  // ---------------- Prévia ----------------
  const [previewResult, setPreviewResult] = useState<PreviewResult | null>(null);
  const [previewSignature, setPreviewSignature] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const canConfirm = !!previewResult && previewSignature === currentSignature;

  const runPreview = async () => {
    if (!conn) return;
    setPreviewLoading(true);
    try {
      const j = await apiSend(conn, "/api/produtos-niveis/preview", "POST", filtroBody());
      if (j?.success) {
        setPreviewResult({ total_pecas: j.total_pecas, total_servicos: j.total_servicos, total: j.total });
        setPreviewSignature(currentSignature);
      } else {
        setPreviewResult(null); setPreviewSignature(null);
        showToast(j?.message || "Falha ao calcular prévia.");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPreviewLoading(false);
    }
  };

  // ---------------- Itens da prévia ----------------
  const [previewItensVisible, setPreviewItensVisible] = useState(false);
  const [previewItensLoading, setPreviewItensLoading] = useState(false);
  const [previewItens, setPreviewItens] = useState<PreviewItem[]>([]);

  const verItensPrevia = async () => {
    if (!conn || !previewResult) return;
    setPreviewItensVisible(true);
    setPreviewItensLoading(true);
    try {
      const j = await apiSend(conn, "/api/produtos-niveis/preview-itens", "POST", filtroBody());
      if (j?.success) setPreviewItens(j.items || []);
      else { setPreviewItens([]); showToast(j?.message || "Falha ao listar itens."); }
    } catch (e) {
      setPreviewItens([]);
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setPreviewItensLoading(false);
    }
  };

  // ---------------- Confirmação ----------------
  const [confirmState, setConfirmState] = useState<ConfirmState | null>(null);
  const [confirmLoading, setConfirmLoading] = useState(false);

  const askConfirmFiltrado = (title: string, run: () => Promise<void>) => {
    if (!canConfirm || !previewResult) { showToast("Rode a prévia antes de confirmar."); return; }
    setConfirmState({
      title,
      message: `${previewResult.total_pecas} produto(s) e ${previewResult.total_servicos} serviço(s) serão afetados.`,
      run,
    });
  };
  const askConfirmLivre = (title: string, message: string, run: () => Promise<void>) => {
    setConfirmState({ title, message, run });
  };

  // Usuário com a tela liberada mas sem cargo de gerente/supervisor/master
  // (funcionarios.cod_funcao 1/2) precisa de senha de autorização de quem tem
  // alçada antes de qualquer ação desta tela ser executada.
  const [authVisible, setAuthVisible] = useState(false);
  const [pendingRun, setPendingRun] = useState<(() => Promise<void>) | null>(null);

  const executarAcao = async (run: () => Promise<void>) => {
    setConfirmLoading(true);
    try {
      await run();
    } finally {
      setConfirmLoading(false);
    }
  };

  const doConfirm = async () => {
    if (!confirmState) return;
    if (!isManagerFuncao) {
      const run = confirmState.run;
      setConfirmState(null);
      setPendingRun(() => run);
      setAuthVisible(true);
      return;
    }
    setConfirmLoading(true);
    try {
      await confirmState.run();
    } finally {
      setConfirmLoading(false);
      setConfirmState(null);
    }
  };

  // ---------------- Aba: Gravar Campos ----------------
  const [campos, setCampos] = useState<CamposGravar>(CAMPOS_INICIAL);
  const setCampo = (k: keyof CamposGravar, v: string) => setCampos((c) => ({ ...c, [k]: v }));
  const [openSections, setOpenSections] = useState<Set<string>>(new Set(["tributacao"]));
  const toggleSection = (id: string) =>
    setOpenSections((prev) => { const n = new Set(prev); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  const gravarCampos = async () => {
    if (!conn) return;
    const body = {
      ...filtroBody(),
      confirmar: true,
      cst_pis: strOrNull(campos.cstPis),
      perc_valor_pis: numOrNull(campos.percValorPis),
      cst_cofins: strOrNull(campos.cstCofins),
      perc_valor_cofins: numOrNull(campos.percValorCofins),
      cod_icms: strOrNull(campos.codIcms),
      perc_mva: numOrNull(campos.percMva),
      outros_trib_federais: numOrNull(campos.outrosTribFederais),
      desc_g: numOrNull(campos.descG),
      desc_s: numOrNull(campos.descS),
      desc_v: numOrNull(campos.descV),
      comissao: numOrNull(campos.comissao),
      valor_comissao: numOrNull(campos.valorComissao),
      valor_desc_base_comissao: numOrNull(campos.valorDescBaseComissao),
      comissao_e: numOrNull(campos.comissaoE),
      valor_comissao_e: numOrNull(campos.valorComissaoE),
      valor_desc_base_comissao_e: numOrNull(campos.valorDescBaseComissaoE),
      comissao_a: numOrNull(campos.comissaoA),
      valor_comissao_a: numOrNull(campos.valorComissaoA),
      valor_desc_base_comissao_a: numOrNull(campos.valorDescBaseComissaoA),
      paga_comissao: boolOrNull(campos.pagaComissao),
      aceita_desconto: boolOrNull(campos.aceitaDesconto),
      tipo_garantia: intOrNull(campos.tipoGarantia),
      prazo_garantia: intOrNull(campos.prazoGarantia),
      margem_lucro: numOrNull(campos.margemLucro),
      margem_tabela: numOrNull(campos.margemTabela),
      estoque_minimo: numOrNull(campos.estoqueMinimo),
      origem: strOrNull(campos.origem),
      tipo_peca: intOrNull(campos.tipoPeca),
      politica_preco: strOrNull(campos.politicaPreco),
      preco_variado: boolOrNull(campos.precoVariado),
      situacao: strOrNull(campos.situacao),
      uf_protocolo_st: strOrNull(campos.ufProtocoloSt),
    };
    const j = await apiSend(conn, "/api/produtos-niveis/gravar-campos", "POST", body);
    showToast(j?.message || (j?.success ? "Alterações gravadas." : "Falha ao gravar."));
    if (j?.success) { setCampos(CAMPOS_INICIAL); runPreview(); }
  };

  // ---------------- Aba: Reajuste de Preço ----------------
  const [percentualReajuste, setPercentualReajuste] = useState("");
  const [alterarPrecoTabela, setAlterarPrecoTabela] = useState(false);
  const [peloCustoReposicao, setPeloCustoReposicao] = useState(false);
  const [arredondar, setArredondar] = useState(false);

  const reajustarPreco = async () => {
    if (!conn) return;
    const pct = numOrNull(percentualReajuste);
    if (pct == null) { showToast("Informe o percentual de reajuste."); return; }
    const body = {
      ...filtroBody(), confirmar: true, percentual: pct,
      alterar_preco_tabela: alterarPrecoTabela, pelo_custo_reposicao: peloCustoReposicao, arredondar,
    };
    const j = await apiSend(conn, "/api/produtos-niveis/reajustar-preco", "POST", body);
    showToast(j?.message || (j?.success ? "Reajuste aplicado." : "Falha ao reajustar."));
    if (j?.success) runPreview();
  };

  // ---------------- Aba: % Lei Transparência ----------------
  const [percentualLei, setPercentualLei] = useState("");

  const processarLeiTransp = async () => {
    if (!conn) return;
    const pct = numOrNull(percentualLei);
    if (pct == null) { showToast("Informe o percentual da Lei da Transparência."); return; }
    const j = await apiSend(conn, "/api/produtos-niveis/lei-transparencia", "POST", { ...filtroBody(), confirmar: true, percentual: pct });
    showToast(j?.message || (j?.success ? "Processamento concluído." : "Falha ao processar."));
  };

  // ---------------- Aba: Utilidades de Estoque ----------------
  const desativarEstoque = async (negativo: boolean) => {
    if (!conn) return;
    const path = negativo ? "desativar-estoque-negativo" : "desativar-estoque-zerado";
    const j = await apiSend(conn, `/api/produtos-niveis/${path}`, "POST", { ...filtroBody(), confirmar: true });
    showToast(j?.message || (j?.success ? "Produtos desativados." : "Falha."));
    if (j?.success) runPreview();
  };

  const [buscaItem, setBuscaItem] = useState("");
  const reprocessarItem = async () => {
    if (!conn || !buscaItem.trim()) { showToast("Informe o código ou descrição do produto."); return; }
    const j = await apiSend(conn, "/api/produtos-niveis/reprocessar-item", "POST", {
      busca: buscaItem.trim(), classe, master: isMaster, usuario_alteracao: usuarioAlteracao, plataforma: Platform.OS,
    });
    if (j?.success) showToast(`Produto ${j.codigo_int}: qtd=${j.qtd}, reservado=${j.reservado}, reservado_os=${j.reservado_os}.`);
    else showToast(j?.message || "Falha.");
  };

  const reprocessarReservados = async () => {
    if (!conn) return;
    const j = await apiSend(conn, "/api/produtos-niveis/reprocessar-reservados", "POST", {
      classe, master: isMaster, usuario_alteracao: usuarioAlteracao, plataforma: Platform.OS,
    });
    showToast(j?.message || (j?.success ? `${j.itens_processados} produto(s) processados.` : "Falha."));
  };

  const canReprocItem = can("PRODUTO_NIVEIS.REPROC_ITEM");
  const canReprocReserv = can("PRODUTO_NIVEIS.REPROC_RESERV");

  // ---------------- UI ----------------
  const [tab, setTab] = useState<TabKey>("gravar");

  // Preço "antes → depois" na lista de itens da prévia — só é exato (mesma
  // fórmula do backend em `_reajustar_preco_sync`) quando a aba ativa é
  // Reajuste de Preço e há um percentual preenchido. Campos de Gravar Campos
  // (ex.: margem_lucro/margem_tabela) são só informativos e não recalculam
  // p_venda neste sistema, então não entram nesse cálculo.
  const percentualReajusteNum = numOrNull(percentualReajuste);
  const reajusteAtivo = tab === "reajuste" && percentualReajusteNum != null;
  const calcularNovoValor = (it: PreviewItem): number | null => {
    if (!reajusteAtivo || percentualReajusteNum == null) return null;
    const fator = 1 + percentualReajusteNum / 100;
    if (it.tipo === "S") {
      if (peloCustoReposicao) return null; // reajuste "pelo custo" não altera serviços
      return it.valor * fator;
    }
    const base = peloCustoReposicao ? it.custo_reposicao : it.valor;
    if (base == null) return null;
    let novo = base * fator;
    if (arredondar && novo % 1 !== 0) novo = Math.floor(novo) + 1;
    return novo;
  };

  const renderNivelNode = (n: NivelNode): React.ReactNode => {
    const isOpen = nivelExpanded.has(n.cod_nivel);
    const hasChildren = n.children.length > 0;
    const isSel = nivelSelecionado === n.cod_nivel;
    return (
      <View key={n.cod_nivel} style={{ marginLeft: (n.depth - 1) * spacing.lg }}>
        <View style={[styles.nivelRow, isSel && styles.nivelRowSel]} testID={`produtos-niveis-nivel-${n.cod_nivel}`}>
          <Pressable onPress={() => hasChildren && toggleNivelExpand(n.cod_nivel)} hitSlop={8} style={{ opacity: hasChildren ? 1 : 0.25 }}>
            <Ionicons name={isOpen ? "chevron-down" : "chevron-forward"} size={14} color={colors.muted} />
          </Pressable>
          <Pressable style={{ flex: 1 }} onPress={() => selecionarNivel(n.cod_nivel)}>
            <Text style={[styles.nivelRowText, isSel && styles.nivelRowTextSel]}>{n.descricao}</Text>
          </Pressable>
        </View>
        {isOpen ? n.children.map(renderNivelNode) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="produtos-niveis-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="produtos-niveis-back-button">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>Alterações Cadastro de Produtos/Serviços Níveis</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {/* ============ Filtro ============ */}
          <View style={styles.card} testID="produtos-niveis-filtro-card">
            <Text style={styles.sectionTitle}>Filtro</Text>

            <View style={styles.radioRow}>
              <RadioOpt label="Por Nível" selected={modoFiltro === "nivel"} onPress={() => setModoFiltro("nivel")} testID="produtos-niveis-modo-nivel" />
              <RadioOpt label="Por Faixa de NCM" selected={modoFiltro === "ncm"} onPress={() => setModoFiltro("ncm")} testID="produtos-niveis-modo-ncm" />
            </View>

            {modoFiltro === "nivel" ? (
              <>
                <Pressable onPress={abrirNivelModal} style={styles.selectorBtn} testID="produtos-niveis-abrir-nivel-modal">
                  <Ionicons name="layers-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.selectorBtnText} numberOfLines={1}>
                    {nivelSelecionadoNode ? nivelSelecionadoNode.descricao : "Selecionar nível…"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
                <View style={styles.switchRow}>
                  <Switch value={nivelIncluirInferiores} onValueChange={setNivelIncluirInferiores} testID="produtos-niveis-incluir-inferiores" />
                  <Text style={styles.switchLabel}>Aplicar também aos níveis inferiores</Text>
                </View>
              </>
            ) : (
              <View style={styles.formGrid}>
                <Field label="NCM de" style={styles.colHalf}>
                  <TextInput value={ncmDe} onChangeText={setNcmDe} keyboardType="numeric" placeholder="Ex.: 84159090" placeholderTextColor={colors.muted} style={styles.input} testID="produtos-niveis-ncm-de" />
                </Field>
                <Field label="NCM até" style={styles.colHalf}>
                  <TextInput value={ncmAte} onChangeText={setNcmAte} keyboardType="numeric" placeholder="Ex.: 84159090" placeholderTextColor={colors.muted} style={styles.input} testID="produtos-niveis-ncm-ate" />
                </Field>
              </View>
            )}

            <View style={styles.switchRow}>
              <Switch value={incluirPecas} onValueChange={setIncluirPecas} testID="produtos-niveis-incluir-pecas" />
              <Text style={styles.switchLabel}>Incluir Produtos</Text>
            </View>
            {servicosOn ? (
              <View style={styles.switchRow}>
                <Switch value={incluirServicos} onValueChange={setIncluirServicos} testID="produtos-niveis-incluir-servicos" />
                <Text style={styles.switchLabel}>Incluir Serviços</Text>
              </View>
            ) : null}

            <Pressable onPress={runPreview} disabled={previewLoading} style={[styles.crudBtn, styles.crudBtnPrimary, previewLoading && { opacity: 0.6 }]} testID="produtos-niveis-preview-button">
              {previewLoading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.crudBtnPrimaryText}>Ver Prévia</Text>}
            </Pressable>
            {previewResult ? (
              <Pressable
                onPress={verItensPrevia}
                disabled={previewResult.total === 0}
                style={styles.previewRow}
                testID="produtos-niveis-preview-result"
              >
                <Text style={styles.previewText}>
                  {previewResult.total_pecas} produto(s) e {previewResult.total_servicos} serviço(s) — {previewResult.total} no total.
                  {previewSignature !== currentSignature ? " O filtro mudou — rode a prévia novamente antes de confirmar." : ""}
                </Text>
                {previewResult.total > 0 ? (
                  <View style={styles.previewLinkRow}>
                    <Text style={styles.previewLinkText}>Ver produtos/serviços</Text>
                    <Ionicons name="chevron-forward" size={14} color={colors.brandPrimary} />
                  </View>
                ) : null}
              </Pressable>
            ) : null}
          </View>

          {/* ============ Tabs ============ */}
          <View style={styles.tabBar}>
            {TABS.map((t) => {
              const sel = tab === t.key;
              return (
                <Pressable key={t.key} onPress={() => setTab(t.key)} style={[styles.tabBtn, sel && styles.tabBtnSel]} testID={`produtos-niveis-tab-${t.key}`}>
                  <Ionicons name={t.icon} size={16} color={sel ? colors.onBrandPrimary : colors.muted} />
                  <Text style={[styles.tabLabel, sel && styles.tabLabelSel]}>{t.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {/* ============ Gravar Campos ============ */}
          {tab === "gravar" ? (
            <View style={styles.card} testID="produtos-niveis-tab-gravar">
              <Text style={styles.hint}>Deixe em branco os campos que não devem ser alterados.</Text>

              <Section id="tributacao" title="Tributação" open={openSections.has("tributacao")} onToggle={() => toggleSection("tributacao")}>
                <View style={styles.formGrid}>
                  <Field label="CST Pis" style={styles.colHalf}>
                    <SelectField value={campos.cstPis || null} onChange={(v) => setCampo("cstPis", v == null ? "" : String(v))} options={cstPisOptions} allowClear compactWeb testID="produtos-niveis-cst-pis" />
                  </Field>
                  <Field label="Alíquota Pis (%)" style={styles.colHalf}>
                    <TextInput value={campos.percValorPis} onChangeText={(v) => setCampo("percValorPis", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="CST Cofins" style={styles.colHalf}>
                    <SelectField value={campos.cstCofins || null} onChange={(v) => setCampo("cstCofins", v == null ? "" : String(v))} options={cstCofinsOptions} allowClear compactWeb testID="produtos-niveis-cst-cofins" />
                  </Field>
                  <Field label="Alíquota Cofins (%)" style={styles.colHalf}>
                    <TextInput value={campos.percValorCofins} onChangeText={(v) => setCampo("percValorCofins", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Cód. Icms" style={styles.colHalf}>
                    <SelectField value={campos.codIcms || null} onChange={(v) => setCampo("codIcms", v == null ? "" : String(v))} options={icmsOptions} allowClear compactWeb testID="produtos-niveis-cod-icms" />
                  </Field>
                  <Field label="Perc. MVA (só Produtos)" style={styles.colHalf}>
                    <TextInput value={campos.percMva} onChangeText={(v) => setCampo("percMva", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Outros Tributos (só Produtos)" style={styles.colHalf}>
                    <TextInput value={campos.outrosTribFederais} onChangeText={(v) => setCampo("outrosTribFederais", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
              </Section>

              <Section id="descontos" title="Descontos" open={openSections.has("descontos")} onToggle={() => toggleSection("descontos")}>
                <View style={styles.formGrid}>
                  <Field label="Desconto Gerente (%)" style={styles.colThird}>
                    <TextInput value={campos.descG} onChangeText={(v) => setCampo("descG", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Desconto Supervisor (%)" style={styles.colThird}>
                    <TextInput value={campos.descS} onChangeText={(v) => setCampo("descS", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Desconto Vendedor (%)" style={styles.colThird}>
                    <TextInput value={campos.descV} onChangeText={(v) => setCampo("descV", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
              </Section>

              <Section id="comissoes" title="Comissões" open={openSections.has("comissoes")} onToggle={() => toggleSection("comissoes")}>
                <Text style={styles.subTitle}>Vendedor</Text>
                <View style={styles.formGrid}>
                  <Field label="Comissão (%)" style={styles.colThird}>
                    <TextInput value={campos.comissao} onChangeText={(v) => setCampo("comissao", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Valor" style={styles.colThird}>
                    <TextInput value={campos.valorComissao} onChangeText={(v) => setCampo("valorComissao", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Desconto Base Comissão" style={styles.colThird}>
                    <TextInput value={campos.valorDescBaseComissao} onChangeText={(v) => setCampo("valorDescBaseComissao", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
                <Text style={styles.subTitle}>Executor</Text>
                <View style={styles.formGrid}>
                  <Field label="Comissão (%)" style={styles.colThird}>
                    <TextInput value={campos.comissaoE} onChangeText={(v) => setCampo("comissaoE", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Valor" style={styles.colThird}>
                    <TextInput value={campos.valorComissaoE} onChangeText={(v) => setCampo("valorComissaoE", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Desconto Base Comissão" style={styles.colThird}>
                    <TextInput value={campos.valorDescBaseComissaoE} onChangeText={(v) => setCampo("valorDescBaseComissaoE", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
                <Text style={styles.subTitle}>Atendente</Text>
                <View style={styles.formGrid}>
                  <Field label="Comissão (%)" style={styles.colThird}>
                    <TextInput value={campos.comissaoA} onChangeText={(v) => setCampo("comissaoA", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Valor" style={styles.colThird}>
                    <TextInput value={campos.valorComissaoA} onChangeText={(v) => setCampo("valorComissaoA", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Desconto Base Comissão" style={styles.colThird}>
                    <TextInput value={campos.valorDescBaseComissaoA} onChangeText={(v) => setCampo("valorDescBaseComissaoA", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
                <View style={styles.formGrid}>
                  <Field label="Paga Comissão" style={styles.colHalf}>
                    <SelectField value={campos.pagaComissao || null} onChange={(v) => setCampo("pagaComissao", v == null ? "" : String(v))} options={SIM_NAO_OPTIONS} allowClear compactWeb testID="produtos-niveis-paga-comissao" />
                  </Field>
                  <Field label="Aceita Desconto" style={styles.colHalf}>
                    <SelectField value={campos.aceitaDesconto || null} onChange={(v) => setCampo("aceitaDesconto", v == null ? "" : String(v))} options={SIM_NAO_OPTIONS} allowClear compactWeb testID="produtos-niveis-aceita-desconto" />
                  </Field>
                </View>
              </Section>

              <Section id="garantia" title="Garantia" open={openSections.has("garantia")} onToggle={() => toggleSection("garantia")}>
                <View style={styles.formGrid}>
                  <Field label="Tipo Garantia" style={styles.colHalf}>
                    <SelectField value={campos.tipoGarantia || null} onChange={(v) => setCampo("tipoGarantia", v == null ? "" : String(v))} options={TIPO_GARANTIA_OPTIONS} allowClear compactWeb testID="produtos-niveis-tipo-garantia" />
                  </Field>
                  <Field label="Prazo Garantia" style={styles.colHalf}>
                    <TextInput value={campos.prazoGarantia} onChangeText={(v) => setCampo("prazoGarantia", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                </View>
              </Section>

              <Section id="margem" title="Margem &amp; Preço (só Produtos)" open={openSections.has("margem")} onToggle={() => toggleSection("margem")}>
                <View style={styles.formGrid}>
                  <Field label="Margem Lucro (%)" style={styles.colHalf}>
                    <TextInput value={campos.margemLucro} onChangeText={(v) => setCampo("margemLucro", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Margem Tabela (%)" style={styles.colHalf}>
                    <TextInput value={campos.margemTabela} onChangeText={(v) => setCampo("margemTabela", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Preço Variado" style={styles.colHalf}>
                    <SelectField value={campos.precoVariado || null} onChange={(v) => setCampo("precoVariado", v == null ? "" : String(v))} options={SIM_NAO_OPTIONS} allowClear compactWeb testID="produtos-niveis-preco-variado" />
                  </Field>
                  <Field label="Tipo Preço" style={styles.colHalf}>
                    <SelectField value={campos.politicaPreco || null} onChange={(v) => setCampo("politicaPreco", v == null ? "" : String(v))} options={POLITICA_PRECO_OPTIONS} allowClear compactWeb testID="produtos-niveis-politica-preco" />
                  </Field>
                </View>
              </Section>

              <Section id="estoque-class" title="Estoque &amp; Classificação (só Produtos)" open={openSections.has("estoque-class")} onToggle={() => toggleSection("estoque-class")}>
                <View style={styles.formGrid}>
                  <Field label="Estoque Mínimo" style={styles.colHalf}>
                    <TextInput value={campos.estoqueMinimo} onChangeText={(v) => setCampo("estoqueMinimo", v)} keyboardType="numeric" style={styles.input} />
                  </Field>
                  <Field label="Origem" style={styles.colHalf}>
                    <SelectField value={campos.origem || null} onChange={(v) => setCampo("origem", v == null ? "" : String(v))} options={origemOptions} allowClear compactWeb testID="produtos-niveis-origem" />
                  </Field>
                  <Field label="Finalidade" style={styles.colHalf}>
                    <SelectField value={campos.tipoPeca || null} onChange={(v) => setCampo("tipoPeca", v == null ? "" : String(v))} options={tipoPecaOptions} allowClear compactWeb testID="produtos-niveis-tipo-peca" />
                  </Field>
                  <Field label="Situação (2 letras)" style={styles.colHalf}>
                    <TextInput value={campos.situacao} onChangeText={(v) => setCampo("situacao", v.toUpperCase().slice(0, 2))} autoCapitalize="characters" style={styles.input} />
                  </Field>
                </View>
              </Section>

              <Section id="protocolo-st" title="Protocolo ST (só Produtos)" open={openSections.has("protocolo-st")} onToggle={() => toggleSection("protocolo-st")}>
                <Text style={styles.hint}>Adiciona a UF informada ao Protocolo ST de cada produto do filtro (não remove UFs já cadastradas).</Text>
                <View style={styles.formGrid}>
                  <Field label="UF Protocolo ST" style={styles.colHalf}>
                    <SelectField value={campos.ufProtocoloSt || null} onChange={(v) => setCampo("ufProtocoloSt", v == null ? "" : String(v))} options={ufOptions} allowClear compactWeb testID="produtos-niveis-uf-protocolo-st" />
                  </Field>
                </View>
              </Section>

              {can("PRODUTO_NIVEIS.GRAVAR") ? (
                <Pressable
                  onPress={() => askConfirmFiltrado("Gravar Campos", gravarCampos)}
                  disabled={!canConfirm}
                  style={[styles.crudBtn, styles.crudBtnPrimary, !canConfirm && { opacity: 0.5 }]}
                  testID="produtos-niveis-gravar-button"
                >
                  <Text style={styles.crudBtnPrimaryText}>Confirmar e Gravar</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {/* ============ Reajuste de Preço ============ */}
          {tab === "reajuste" ? (
            <View style={styles.card} testID="produtos-niveis-tab-reajuste">
              <View style={styles.formGrid}>
                <Field label="Percentual de Reajuste (%)" style={styles.colHalf}>
                  <TextInput value={percentualReajuste} onChangeText={setPercentualReajuste} keyboardType="numeric" placeholder="Ex.: 10 ou -5" placeholderTextColor={colors.muted} style={styles.input} testID="produtos-niveis-percentual-reajuste" />
                </Field>
              </View>
              <View style={styles.switchRow}>
                <Switch value={alterarPrecoTabela} onValueChange={setAlterarPrecoTabela} />
                <Text style={styles.switchLabel}>Alterar Preço de Tabela também</Text>
              </View>
              <View style={styles.switchRow}>
                <Switch value={peloCustoReposicao} onValueChange={setPeloCustoReposicao} />
                <Text style={styles.switchLabel}>Basear no Custo de Reposição (em vez do Preço de Venda atual)</Text>
              </View>
              <View style={styles.switchRow}>
                <Switch value={arredondar} onValueChange={setArredondar} />
                <Text style={styles.switchLabel}>Arredondar para o inteiro seguinte quando houver centavos</Text>
              </View>
              {can("PRODUTO_NIVEIS.REAJUSTAR") ? (
                <Pressable
                  onPress={() => askConfirmFiltrado("Reajustar Preço", reajustarPreco)}
                  disabled={!canConfirm}
                  style={[styles.crudBtn, styles.crudBtnPrimary, !canConfirm && { opacity: 0.5 }]}
                  testID="produtos-niveis-reajustar-button"
                >
                  <Text style={styles.crudBtnPrimaryText}>Confirmar Reajuste</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {/* ============ % Lei Transparência ============ */}
          {tab === "leiTransp" ? (
            <View style={styles.card} testID="produtos-niveis-tab-lei-transp">
              <Text style={styles.hint}>Recalcula "Outros Tributos" de cada produto do filtro. Só afeta Produtos.</Text>
              <View style={styles.formGrid}>
                <Field label="Percentual Total de Tributos (%)" style={styles.colHalf}>
                  <TextInput value={percentualLei} onChangeText={setPercentualLei} keyboardType="numeric" style={styles.input} testID="produtos-niveis-percentual-lei" />
                </Field>
              </View>
              {can("PRODUTO_NIVEIS.LEI_TRANSP") ? (
                <Pressable
                  onPress={() => askConfirmFiltrado("% Lei Transparência", processarLeiTransp)}
                  disabled={!canConfirm}
                  style={[styles.crudBtn, styles.crudBtnPrimary, !canConfirm && { opacity: 0.5 }]}
                  testID="produtos-niveis-lei-transp-button"
                >
                  <Text style={styles.crudBtnPrimaryText}>Confirmar Processamento</Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {/* ============ Utilidades de Estoque ============ */}
          {tab === "estoque" ? (
            <View style={styles.card} testID="produtos-niveis-tab-estoque">
              <Text style={styles.sectionTitle}>Desativar por Estoque</Text>
              <Text style={styles.hint}>Marca situação = "D" (Desativado) para produtos do filtro com estoque negativo ou zerado.</Text>
              <View style={styles.crudBtnRow}>
                {can("PRODUTO_NIVEIS.DESATIVAR_NEG") ? (
                  <Pressable
                    onPress={() => askConfirmFiltrado("Desativar Estoque Negativo", () => desativarEstoque(true))}
                    disabled={!canConfirm}
                    style={[styles.crudBtn, styles.crudBtnDanger, !canConfirm && { opacity: 0.5 }]}
                    testID="produtos-niveis-desativar-neg-button"
                  >
                    <Text style={styles.crudBtnDangerText}>Desativar Estoque Negativo</Text>
                  </Pressable>
                ) : null}
                {can("PRODUTO_NIVEIS.DESATIVAR_ZERO") ? (
                  <Pressable
                    onPress={() => askConfirmFiltrado("Desativar Estoque Zerado", () => desativarEstoque(false))}
                    disabled={!canConfirm}
                    style={[styles.crudBtn, styles.crudBtnDanger, !canConfirm && { opacity: 0.5 }]}
                    testID="produtos-niveis-desativar-zero-button"
                  >
                    <Text style={styles.crudBtnDangerText}>Desativar Estoque Zerado</Text>
                  </Pressable>
                ) : null}
              </View>

              {(canReprocItem || canReprocReserv) ? (
                <View style={styles.perigoBox}>
                  <View style={styles.perigoHeader}>
                    <Ionicons name="warning-outline" size={16} color={colors.warning} />
                    <Text style={styles.perigoTitle}>Reprocessamento de Estoque</Text>
                  </View>
                  <Text style={styles.hint}>
                    Recalcula quantidade/reservado a partir de todo o histórico de movimentação, orçamentos, O.S. e pedidos. Operação pesada — use com cautela.
                  </Text>

                  {canReprocItem ? (
                    <>
                      <Field label="Buscar produto (código de fábrica, descrição ou código interno)">
                        <TextInput value={buscaItem} onChangeText={setBuscaItem} style={styles.input} placeholder="Ex.: 00012345" placeholderTextColor={colors.muted} testID="produtos-niveis-busca-item" />
                      </Field>
                      <Pressable
                        onPress={() => askConfirmLivre("Reprocessar Item", "Confirma o reprocessamento do estoque deste produto?", reprocessarItem)}
                        disabled={!buscaItem.trim()}
                        style={[styles.crudBtn, styles.crudBtnDanger, !buscaItem.trim() && { opacity: 0.5 }]}
                        testID="produtos-niveis-reprocessar-item-button"
                      >
                        <Text style={styles.crudBtnDangerText}>Reprocessar Estoque do Item</Text>
                      </Pressable>
                    </>
                  ) : null}

                  {canReprocReserv ? (
                    <Pressable
                      onPress={() => askConfirmLivre(
                        "Reprocessar Estoques Reservados",
                        "Esta operação NÃO respeita o filtro de NCM/Nível atual — processa TODOS os produtos do banco. Confirma?",
                        reprocessarReservados,
                      )}
                      style={[styles.crudBtn, styles.crudBtnDanger, { marginTop: spacing.sm }]}
                      testID="produtos-niveis-reprocessar-reservados-button"
                    >
                      <Text style={styles.crudBtnDangerText}>Reprocessar Estoques Reservados (Global)</Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>

      <Modal visible={nivelModalVisible} transparent animationType="slide" onRequestClose={() => setNivelModalVisible(false)} testID="produtos-niveis-nivel-modal">
        <Pressable style={styles.slideBg} onPress={() => setNivelModalVisible(false)}>
          <Pressable style={styles.slideCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.modalTitle}>Selecionar Nível</Text>
              <Pressable onPress={() => setNivelModalVisible(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={nivelSearch}
                onChangeText={setNivelSearch}
                placeholder="Buscar por descrição…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="produtos-niveis-nivel-search"
              />
            </View>
            <ScrollView style={styles.slideScroll} showsVerticalScrollIndicator={false}>
              {visibleNivelTree.length === 0 ? (
                <Text style={styles.hint}>Nenhum grupo mercadológico encontrado.</Text>
              ) : visibleNivelTree.map(renderNivelNode)}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={previewItensVisible} transparent animationType="slide" onRequestClose={() => setPreviewItensVisible(false)} testID="produtos-niveis-preview-itens-modal">
        <Pressable style={styles.slideBg} onPress={() => setPreviewItensVisible(false)}>
          <Pressable style={styles.slideCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.modalTitle}>Produtos/Serviços da Prévia</Text>
              <Pressable onPress={() => setPreviewItensVisible(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {previewItensLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
            {!previewItensLoading && reajusteAtivo ? (
              <Text style={styles.hint}>
                Preço atual (riscado) e preço após o reajuste de {percentualReajusteNum}% (se confirmado).
              </Text>
            ) : null}
            {!previewItensLoading && (
              previewItens.filter((i) => i.tipo === "P").length >= PREVIEW_ITENS_LIMITE ||
              previewItens.filter((i) => i.tipo === "S").length >= PREVIEW_ITENS_LIMITE
            ) ? (
              <Text style={styles.hint}>
                Mostrando os {PREVIEW_ITENS_LIMITE} primeiros por tipo (em ordem alfabética) — a ação em massa continua sendo aplicada a todos os itens do filtro, não só aos listados aqui.
              </Text>
            ) : null}
            <ScrollView style={styles.slideScroll} showsVerticalScrollIndicator={false}>
              {!previewItensLoading && previewItens.length === 0 ? (
                <Text style={styles.hint}>Nenhum item encontrado.</Text>
              ) : previewItens.map((it) => {
                const novoValor = calcularNovoValor(it);
                return (
                  <View key={`${it.tipo}-${it.codigo}`} style={styles.previewItemRow}>
                    <View style={[styles.previewItemTag, it.tipo === "P" ? styles.previewItemTagProd : styles.previewItemTagServ]}>
                      <Text style={styles.previewItemTagText}>{it.tipo === "P" ? "PRODUTO" : "SERVIÇO"}</Text>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.previewItemDesc} numberOfLines={1}>{it.descricao || "—"}</Text>
                      <Text style={styles.previewItemCod}>#{it.codigo}</Text>
                      {it.tipo === "P" && it.custo_reposicao != null ? (
                        <Text style={styles.previewItemCusto}>Custo repos.: {formatBRL(it.custo_reposicao)}</Text>
                      ) : null}
                    </View>
                    <View style={styles.previewItemPrecoCol}>
                      {novoValor != null ? (
                        <>
                          <Text style={styles.previewItemValorAntigo}>{formatBRL(it.valor)}</Text>
                          <Text style={styles.previewItemValor}>{formatBRL(novoValor)}</Text>
                        </>
                      ) : (
                        <Text style={styles.previewItemValor}>{formatBRL(it.valor)}</Text>
                      )}
                    </View>
                  </View>
                );
              })}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={!!confirmState} transparent animationType="fade" onRequestClose={() => setConfirmState(null)}>
        <Pressable style={styles.modalBg} onPress={() => !confirmLoading && setConfirmState(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{confirmState?.title}</Text>
            <Text style={styles.modalMessage}>{confirmState?.message}</Text>
            <View style={styles.crudBtnRow}>
              <Pressable onPress={() => setConfirmState(null)} disabled={confirmLoading} style={styles.crudBtn} testID="produtos-niveis-confirm-cancel">
                <Text style={styles.crudBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable onPress={doConfirm} disabled={confirmLoading} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="produtos-niveis-confirm-ok">
                {confirmLoading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.crudBtnPrimaryText}>Confirmar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <AuthorizationSlide
        visible={authVisible}
        conn={conn}
        message="Esta ação exige autorização de um gerente, supervisor ou administrador."
        onClose={() => { setAuthVisible(false); setPendingRun(null); }}
        onAuthorized={async () => {
          setAuthVisible(false);
          const run = pendingRun;
          setPendingRun(null);
          if (run) await executarAcao(run);
        }}
      />

      {toast ? <View style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

function RadioOpt({ label, selected, onPress, testID }: { label: string; selected: boolean; onPress: () => void; testID?: string }) {
  return (
    <Pressable onPress={onPress} style={[styles.radioBtn, selected && styles.radioBtnSel]} testID={testID}>
      <View style={[styles.radioCircle, selected && styles.radioCircleSel]}>{selected ? <View style={styles.radioDot} /> : null}</View>
      <Text style={styles.radioLabel}>{label}</Text>
    </Pressable>
  );
}

function Field({ label, children, style }: { label: string; children: React.ReactNode; style?: object }) {
  return (
    <View style={[{ marginBottom: spacing.md }, style]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

function Section({
  id, title, open, onToggle, children,
}: { id: string; title: string; open: boolean; onToggle: () => void; children: React.ReactNode }) {
  return (
    <View style={styles.sectionBox} testID={`produtos-niveis-section-${id}`}>
      <Pressable onPress={onToggle} style={styles.sectionHeaderRow}>
        <Text style={styles.sectionBoxTitle}>{title}</Text>
        <Ionicons name={open ? "chevron-up" : "chevron-down"} size={16} color={colors.muted} />
      </Pressable>
      {open ? <View style={styles.sectionBody}>{children}</View> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 15, fontWeight: "500" },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.sm },
  subTitle: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.sm, marginBottom: 4, textTransform: "uppercase" },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4, marginBottom: spacing.sm, fontStyle: "italic" },
  formGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.md },
  colHalf: { width: "49%" },
  colThird: { width: "32%" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  switchLabel: { fontSize: 13, color: colors.onSurface, flexShrink: 1 },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginBottom: spacing.md },
  radioBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  selectorBtn: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: 11,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.sm,
  },
  selectorBtnText: { flex: 1, fontSize: 14, color: colors.onSurface },
  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end", alignItems: "center" },
  slideCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.md, maxHeight: "85%", width: "100%", maxWidth: 560, alignSelf: "center",
  },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  slideScroll: { maxHeight: 420 },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, paddingHorizontal: spacing.sm, paddingVertical: spacing.sm, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  nivelRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderRadius: radius.sm, marginBottom: 2,
  },
  nivelRowSel: { backgroundColor: colors.brandTertiary },
  nivelRowText: { fontSize: 13, color: colors.onSurface },
  nivelRowTextSel: { fontWeight: "700", color: colors.brandPrimary },
  previewRow: { marginTop: spacing.sm },
  previewText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  previewLinkRow: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  previewLinkText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" },
  previewItemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  previewItemPrecoCol: { alignItems: "flex-end" },
  previewItemValorAntigo: { fontSize: 11, color: colors.muted, textDecorationLine: "line-through" },
  previewItemTag: { paddingHorizontal: 6, paddingVertical: 3, borderRadius: 4 },
  previewItemTagProd: { backgroundColor: colors.brandTertiary },
  previewItemTagServ: { backgroundColor: "#fff4e0" },
  previewItemTagText: { fontSize: 9, fontWeight: "700", color: colors.onSurface, letterSpacing: 0.3 },
  previewItemDesc: { fontSize: 13, color: colors.onSurface },
  previewItemCod: { fontSize: 11, color: colors.muted, marginTop: 2 },
  previewItemCusto: { fontSize: 11, color: colors.muted, marginTop: 2 },
  previewItemValor: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  tabBar: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.lg, flexWrap: "wrap" },
  tabBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 10,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  tabBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tabLabel: { fontSize: 13, fontWeight: "500", color: colors.muted },
  tabLabelSel: { color: colors.onBrandPrimary },
  sectionBox: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, marginBottom: spacing.md, overflow: "hidden" },
  sectionHeaderRow: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm, backgroundColor: colors.surfaceSecondary,
  },
  sectionBoxTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  sectionBody: { padding: spacing.md },
  crudBtnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, flexWrap: "wrap" },
  crudBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1,
    borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
  },
  crudBtnText: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary, marginTop: spacing.md },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  crudBtnDanger: { backgroundColor: colors.surface, borderColor: colors.error },
  crudBtnDangerText: { fontSize: 13, fontWeight: "600", color: colors.error },
  perigoBox: {
    marginTop: spacing.lg, padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.warning, backgroundColor: colors.surfaceSecondary,
  },
  perigoHeader: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 4 },
  perigoTitle: { fontSize: 13, fontWeight: "700", color: colors.warning },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "center", paddingHorizontal: spacing.xl },
  modalCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border,
    width: "100%", maxWidth: 480, alignSelf: "center", padding: spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  modalMessage: { fontSize: 14, color: colors.onSurface, lineHeight: 20 },
  toast: {
    position: "absolute", bottom: 40, left: spacing.lg, right: spacing.lg, alignSelf: "center",
    backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill,
  },
  toastText: { color: colors.surface, fontSize: 13, textAlign: "center" },
});
