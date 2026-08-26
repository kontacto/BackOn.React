// "Recebimento de Mercadoria" — migração de `Geral\FrmtraRec.frm` (o maior
// form do sistema legado). Ver `backend/services/recebimento_service.py` e
// PENDENCIAS.md > "Recebimento de Mercadoria" pro racional completo
// (achados da fonte, citação exata, decisões de negócio).
//
// **Fase 1 (digitação manual, sem XML)**: rascunho (`nf_recebimento`/
// `nf_recebimento_itens`/`nf_recebimento_vencimento`) enquanto sendo
// digitado. "Criticar" compara cabeçalho x soma dos itens e auto-ajusta
// dentro da tolerância configurada (Controle do Sistema). "Atualizar"
// promove pra `n_fiscal`/`n_fiscal_itens`/`nf_vencimento`, recalcula custo
// médio ponderado, atualiza preço de venda por margem (quando o Tipo de
// Movimentação permitir), soma ao estoque e baixa Pedido de Compra em
// aberto (FIFO) — tudo automático no backend, nenhuma ação extra aqui.
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import ProdutoSearchModal, { ProdutoRow } from "@/src/components/ProdutoSearchModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";

type TipoMov = { codigo: string; descricao: string; origem_destino: string };

type ItemRecebimento = {
  codautonum?: number;
  codigo_int: string;
  descricao: string;
  qtd: string;
  qtd_un_compra: string;
  p_unit: string;
  base_icms: string;
  valor_icms: string;
  alqt_icms: string;
  base_ipi: string;
  alqt_ipi: string;
  valor_ipi: string;
  base_sub: string;
  valor_sub: string;
  base_iss: string;
  valor_iss: string;
  frete: string;
  seguro: string;
  despesas: string;
  desconto: string;
  numero_pedido: string;
  atualiza_preco: boolean;
  // Preenchidos só pela Importação de XML (Fase 2) — sem campo editável na
  // tela (mesma simplificação já documentada no backend), só round-trip
  // até "Salvar Rascunho"/"Atualizar".
  vinculado: boolean;
  tributacaoPis: string; basePis: string; alqtPis: string; valorPis: string;
  tributacaoCofins: string; baseCofins: string; alqtCofins: string; valorCofins: string;
};

type Vencimento = { data_venc: string | null; valor: string };

const RECEBIMENTO_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Importar XML",
    texto: "Escolha o arquivo XML da NF-e do fornecedor pra preencher o cabeçalho e os itens automaticamente, em vez de digitar tudo na mão. Itens cujo produto não foi reconhecido no cadastro ficam destacados — use \"Vincular Produto\" pra escolher o produto certo antes de gravar.",
    icon: { lib: "ion", name: "cloud-upload-outline" },
  },
  {
    titulo: "Fornecedor e Nota",
    texto: "Escolha o fornecedor e informe Número/Série da nota — o sistema bloqueia se já existir uma nota igual (mesmo número, série e fornecedor).",
    icon: { lib: "ion", name: "business-outline" },
  },
  {
    titulo: "Criticar",
    texto: "Confere se a soma dos valores dos itens bate com os totais do cabeçalho (ICMS, IPI, frete, etc.). Diferenças pequenas (dentro do limite configurado em Controle do Sistema) são ajustadas automaticamente no item de maior valor; diferenças maiores bloqueiam a Atualização até serem corrigidas.",
    icon: { lib: "ion", name: "checkmark-done-outline" },
  },
  {
    titulo: "Atualizar",
    texto: "Gera a Nota Fiscal definitiva, recalcula o custo médio dos produtos, atualiza o preço de venda (quando o Tipo de Movimentação permitir), soma a quantidade recebida ao estoque e baixa automaticamente Pedidos de Compra em aberto do mesmo fornecedor. Ação irreversível nesta fase — depois de atualizado, o rascunho não pode mais ser editado.",
    icon: { lib: "ion", name: "sync-circle-outline" },
    cor: colors.brandPrimary,
  },
  {
    titulo: "Custo médio",
    texto: "O custo do produto é recalculado ponderando o estoque que já existia com o que está sendo recebido agora — quanto maior a quantidade recebida, mais peso ela tem no novo custo.",
    icon: { lib: "ion", name: "calculator-outline" },
  },
  {
    titulo: "Atualiza Preço",
    texto: "Marque esta opção no item para que o Preço de Venda seja recalculado automaticamente a partir do novo custo e da margem cadastrada no produto — só tem efeito se o Tipo de Movimentação permitir alterar preço de venda.",
    icon: { lib: "ion", name: "pricetag-outline" },
  },
  {
    titulo: "Nº do Pedido de Compra",
    texto: "Preenchido automaticamente após Atualizar, quando o item consome um Pedido de Compra em aberto do mesmo fornecedor (mais antigo primeiro) — não precisa ser digitado.",
    icon: { lib: "ion", name: "cart-outline" },
  },
  {
    titulo: "Vencimentos",
    texto: "A soma dos vencimentos precisa bater exatamente com o Valor Total da nota — a Atualização é bloqueada se não bater.",
    icon: { lib: "ion", name: "calendar-outline" },
    cor: colors.warning,
  },
];

export default function RecebimentoScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Recebimento de Mercadoria está disponível apenas no web." testID="recebimento-web-only" />;
  }

  const canAbrir = can("RECEBIMENTO.ABRIR") || isMaster;
  const canGravar = can("RECEBIMENTO.GRAVAR") || isMaster;
  const canCriticar = can("RECEBIMENTO.CRITICAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [codigo, setCodigo] = useState<number | null>(null);
  const [promovida, setPromovida] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [criticando, setCriticando] = useState(false);
  const [atualizando, setAtualizando] = useState(false);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);
  const [resultado, setResultado] = useState<{ n_fiscal: number } | null>(null);

  const [tiposMov, setTiposMov] = useState<TipoMov[]>([]);
  const [mov, setMov] = useState<string | null>(null);
  const [numNf, setNumNf] = useState("");
  const [serieNf, setSerieNf] = useState("");
  const [cfop, setCfop] = useState("");
  const [dataEmissao, setDataEmissao] = useState<string | null>(null);
  const [dataMov, setDataMov] = useState<string | null>(null);
  const [frete, setFrete] = useState("");
  const [freteFora, setFreteFora] = useState("");
  const [seguro, setSeguro] = useState("");
  const [despesas, setDespesas] = useState("");
  const [desconto, setDesconto] = useState("");
  const [obs, setObs] = useState("");

  const [fornecedor, setFornecedor] = useState<FornecedorRow | null>(null);
  const [fornSearchOpen, setFornSearchOpen] = useState(false);
  const [fornSearchTerm, setFornSearchTerm] = useState("");
  const [fornSearchLoading, setFornSearchLoading] = useState(false);
  const [fornSearchResults, setFornSearchResults] = useState<FornecedorRow[]>([]);

  const [itens, setItens] = useState<ItemRecebimento[]>([]);
  const [produtoSearchOpen, setProdutoSearchOpen] = useState(false);
  const [produtoSearchTerm, setProdutoSearchTerm] = useState("");
  const [produtoSearchLoading, setProdutoSearchLoading] = useState(false);
  const [produtoSearchResults, setProdutoSearchResults] = useState<ProdutoRow[]>([]);
  const [vinculandoIdx, setVinculandoIdx] = useState<number | null>(null);

  const [vencimentos, setVencimentos] = useState<Vencimento[]>([]);

  const xmlInputRef = useRef<HTMLInputElement | null>(null);
  const [importandoXml, setImportandoXml] = useState(false);

  const apiUrl = useCallback((path: string) => `${(conn?.api || "").replace(/\/+$/, "")}${path}`, [conn]);

  const ensureConn = useCallback(async (): Promise<Connection | null> => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
    if (c) setConn(c);
    return c;
  }, [conn, router]);

  useEffect(() => {
    (async () => {
      const c = await ensureConn();
      if (!c) return;
      try {
        const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/tipo-mov-nf?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`);
        const j = await r.json();
        const todos: TipoMov[] = j?.items || j || [];
        setTiposMov(todos.filter((t) => (t.origem_destino || "").trim().toUpperCase() === "F"));
      } catch {
        setTiposMov([]);
      }
      try {
        const r2 = await fetch(`${c.api.replace(/\/+$/, "")}/api/recebimento/novo`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: c.servidor, banco: c.banco, classe, master: isMaster }),
        });
        const j2 = await r2.json();
        if (j2?.success) setCodigo(j2.codigo);
        else fb.showError(friendlyApiError(j2, "Não foi possível iniciar o recebimento."));
      } catch (e) {
        fb.showError(friendlyCatchError(e));
      } finally {
        setCarregando(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buscarFornecedores = useCallback(async (termo: string) => {
    const c = await ensureConn();
    if (!c) return;
    setFornSearchLoading(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(termo)}`;
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/fornecedores?${qs}`);
      const j = await r.json();
      setFornSearchResults(j?.items || j || []);
    } catch {
      setFornSearchResults([]);
    } finally {
      setFornSearchLoading(false);
    }
  }, [ensureConn]);

  const buscarProdutos = useCallback(async (termo: string) => {
    const c = await ensureConn();
    if (!c) return;
    setProdutoSearchLoading(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&termo=${encodeURIComponent(termo)}&tipo=P`;
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/produtos-servicos?${qs}`);
      const j = await r.json();
      setProdutoSearchResults(j?.items || j || []);
    } catch {
      setProdutoSearchResults([]);
    } finally {
      setProdutoSearchLoading(false);
    }
  }, [ensureConn]);

  const num = (v: string) => (v ? parseFloat(v.replace(",", ".")) || 0 : 0);
  const valorTotalItens = itens.reduce((soma, it) => soma + num(it.qtd) * num(it.p_unit), 0);
  const somaVencimentos = vencimentos.reduce((s, v) => s + num(v.valor), 0);

  const salvarCabecalho = async () => {
    const c = await ensureConn();
    if (!c || !codigo) return false;
    if (!fornecedor) { fb.showError("Selecione o Fornecedor."); return false; }
    if (!mov) { fb.showError("Selecione o Tipo de Movimentação."); return false; }
    if (!numNf.trim()) { fb.showError("Informe o Número da Nota Fiscal."); return false; }
    if (!dataEmissao) { fb.showError("Informe a Data de Emissão."); return false; }
    setSalvando(true);
    try {
      const dados = {
        fornecedor: Number(fornecedor.codigo_int), num_nf: Number(numNf), serie_nf: serieNf.trim(),
        mov, cfop: cfop.trim(), data: dataEmissao, data_mov: dataMov || dataEmissao,
        valor_total: valorTotalItens, frete: num(frete), frete_fora: num(freteFora),
        seguro: num(seguro), despesas: num(despesas), desconto: num(desconto), obs: obs.trim(),
      };
      const r = await fetch(apiUrl("/api/recebimento/cabecalho"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, codigo, dados }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível gravar o cabeçalho.")); return false; }
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e));
      return false;
    } finally {
      setSalvando(false);
    }
  };

  const salvarItens = async (lista: ItemRecebimento[]) => {
    const c = await ensureConn();
    if (!c || !codigo) return false;
    try {
      const payload = lista.map((it) => ({
        codigo_int: it.codigo_int, qtd: num(it.qtd), qtd_un_compra: num(it.qtd_un_compra) || 1, p_unit: num(it.p_unit),
        valor_total: num(it.qtd) * num(it.p_unit),
        base_icms: num(it.base_icms), valor_icms: num(it.valor_icms), alqt_icms: num(it.alqt_icms),
        base_ipi: num(it.base_ipi), alqt_ipi: num(it.alqt_ipi), valor_ipi: num(it.valor_ipi),
        base_sub: num(it.base_sub), valor_sub: num(it.valor_sub),
        base_iss: num(it.base_iss), valor_iss: num(it.valor_iss),
        frete: num(it.frete), seguro: num(it.seguro), despesas: num(it.despesas), desconto: num(it.desconto),
        atualiza_preco: it.atualiza_preco,
        tributacao_pis: it.tributacaoPis || null, base_pis: num(it.basePis), alqt_pis: num(it.alqtPis), valor_pis: num(it.valorPis),
        tributacao_cofins: it.tributacaoCofins || null, base_cofins: num(it.baseCofins), alqt_cofins: num(it.alqtCofins), valor_cofins: num(it.valorCofins),
      }));
      const r = await fetch(apiUrl("/api/recebimento/itens"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, codigo, itens: payload }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível gravar os itens.")); return false; }
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e));
      return false;
    }
  };

  const salvarVencimentos = async (lista: Vencimento[]) => {
    const c = await ensureConn();
    if (!c || !codigo) return false;
    try {
      const payload = lista.filter((v) => v.data_venc).map((v) => ({ data_venc: v.data_venc, valor: num(v.valor) }));
      const r = await fetch(apiUrl("/api/recebimento/vencimentos"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, codigo, vencimentos: payload }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível gravar os vencimentos.")); return false; }
      return true;
    } catch (e) {
      fb.showError(friendlyCatchError(e));
      return false;
    }
  };

  const selecionarProduto = (p: ProdutoRow) => {
    setProdutoSearchOpen(false);
    if (vinculandoIdx !== null) {
      setItens((cur) => cur.map((it, i) => (i === vinculandoIdx ? { ...it, codigo_int: p.codigo, descricao: p.descricao, vinculado: true } : it)));
      setVinculandoIdx(null);
      return;
    }
    setItens((cur) => [...cur, {
      codigo_int: p.codigo, descricao: p.descricao, qtd: "1", qtd_un_compra: "1", p_unit: "0",
      base_icms: "0", valor_icms: "0", alqt_icms: "0", base_ipi: "0", alqt_ipi: "0", valor_ipi: "0",
      base_sub: "0", valor_sub: "0", base_iss: "0", valor_iss: "0",
      frete: "0", seguro: "0", despesas: "0", desconto: "0", numero_pedido: "", atualiza_preco: false,
      vinculado: true, tributacaoPis: "", basePis: "0", alqtPis: "0", valorPis: "0",
      tributacaoCofins: "", baseCofins: "0", alqtCofins: "0", valorCofins: "0",
    }]);
  };

  const abrirVincularProduto = (idx: number) => {
    setVinculandoIdx(idx);
    setProdutoSearchOpen(true);
  };

  const atualizarItem = (idx: number, campo: keyof ItemRecebimento, valor: string | boolean) => {
    setItens((cur) => cur.map((it, i) => (i === idx ? { ...it, [campo]: valor } : it)));
  };

  const removerItem = (idx: number) => setItens((cur) => cur.filter((_, i) => i !== idx));

  // Importação de XML (Fase 2) — o backend só RESOLVE (fornecedor/produto/
  // CFOP/PIS-COFINS), nunca grava o documento em si; o resultado é aplicado
  // no rascunho já aberto (mesmo padrão de "Importar de..." em nfe-avulsa.tsx),
  // e o usuário segue com Salvar Rascunho/Criticar/Atualizar normalmente.
  const abrirSeletorXml = () => {
    if (!codigo) return;
    xmlInputRef.current?.click();
  };

  const importarXml = async (conteudoXml: string) => {
    const c = await ensureConn();
    if (!c || !codigo) return;
    setImportandoXml(true);
    try {
      const r = await fetch(apiUrl("/api/recebimento/importar-xml"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, codigo, conteudo_xml: conteudoXml, classe, master: isMaster }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível importar o XML."), undefined, 5000); return; }

      const h = j.header || {};
      if (h.num_nf != null) setNumNf(String(h.num_nf));
      if (h.serie_nf != null) setSerieNf(String(h.serie_nf));
      if (h.data) { setDataEmissao(h.data); setDataMov(h.data_saida || h.data); }
      if (h.frete != null) setFrete(String(h.frete));
      if (h.seguro != null) setSeguro(String(h.seguro));
      if (h.desconto != null) setDesconto(String(h.desconto));
      if (h.despesas != null) setDespesas(String(h.despesas));
      if (h.chave_acesso) setObs((cur) => cur || `Chave de acesso: ${h.chave_acesso}`);

      if (h.fornecedor) {
        try {
          const qsBase = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const rf = await fetch(`${c.api.replace(/\/+$/, "")}/api/fornecedores?${qsBase}&search=${h.fornecedor}`);
          const jf = await rf.json();
          const lista: FornecedorRow[] = jf?.items || jf || [];
          const found = lista.find((f) => Number(f.codigo_int) === Number(h.fornecedor)) || lista[0];
          if (found) setFornecedor(found);
        } catch { /* fornecedor já foi resolvido/criado no backend; só a exibição do nome falhou */ }
      }

      const novosItens: ItemRecebimento[] = (j.itens || []).map((it: any) => ({
        codigo_int: it.codigo_int || "", descricao: it.descricao || it.xProd || it.cProd || "",
        qtd: String(it.qtd ?? "0"), qtd_un_compra: String(it.qtd_un_compra ?? "1"), p_unit: String(it.p_unit ?? "0"),
        base_icms: String(it.base_icms ?? "0"), valor_icms: String(it.valor_icms ?? "0"), alqt_icms: String(it.alqt_icms ?? "0"),
        base_ipi: String(it.base_ipi ?? "0"), alqt_ipi: String(it.alqt_ipi ?? "0"), valor_ipi: String(it.valor_ipi ?? "0"),
        base_sub: String(it.base_sub ?? "0"), valor_sub: String(it.valor_sub ?? "0"),
        base_iss: "0", valor_iss: "0",
        frete: String(it.frete ?? "0"), seguro: String(it.seguro ?? "0"), despesas: String(it.despesas ?? "0"),
        desconto: String(it.desconto ?? "0"), numero_pedido: "", atualiza_preco: false,
        vinculado: it.vinculado !== false,
        tributacaoPis: it.tributacao_pis || "", basePis: String(it.base_pis ?? "0"), alqtPis: String(it.alqt_pis ?? "0"), valorPis: String(it.valor_pis ?? "0"),
        tributacaoCofins: it.tributacao_cofins || "", baseCofins: String(it.base_cofins ?? "0"), alqtCofins: String(it.alqt_cofins ?? "0"), valorCofins: String(it.valor_cofins ?? "0"),
      }));
      setItens((cur) => [...cur, ...novosItens]);

      if (j.vencimentos?.length) {
        setVencimentos((cur) => [...cur, ...j.vencimentos.map((v: any) => ({ data_venc: v.data_venc, valor: String(v.valor ?? "0") }))]);
      }

      const semVinculo = (j.itens_sem_vinculo || []).length;
      if (semVinculo > 0) {
        fb.showWarning(
          `${novosItens.length} item(ns) importado(s) — ${semVinculo} sem produto vinculado. Use "Vincular Produto" nos itens destacados antes de salvar.`,
          undefined, 5000,
        );
      } else {
        fb.showSuccess(`${novosItens.length} item(ns) importado(s) do XML — revise antes de salvar.`, undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setImportandoXml(false);
    }
  };

  const handleArquivoXmlSelecionado = (e: any) => {
    const file: File | undefined = e.target?.files?.[0];
    e.target.value = "";
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => importarXml(String(reader.result || ""));
    reader.onerror = () => fb.showError("Falha ao ler o arquivo selecionado.");
    reader.readAsText(file);
  };

  const adicionarVencimento = () => setVencimentos((cur) => [...cur, { data_venc: dataEmissao, valor: "0" }]);
  const atualizarVencimento = (idx: number, campo: keyof Vencimento, valor: string | null) => {
    setVencimentos((cur) => cur.map((v, i) => (i === idx ? { ...v, [campo]: valor } : v)));
  };
  const removerVencimento = (idx: number) => setVencimentos((cur) => cur.filter((_, i) => i !== idx));

  const gravarRascunho = async () => {
    if (itens.some((it) => !it.vinculado)) {
      fb.showError('Existem itens do XML sem produto vinculado — use "Vincular Produto" antes de gravar.');
      return;
    }
    const okCab = await salvarCabecalho();
    if (!okCab) return;
    if (itens.length > 0) {
      const okItens = await salvarItens(itens);
      if (!okItens) return;
    }
    if (vencimentos.length > 0) {
      const okVenc = await salvarVencimentos(vencimentos);
      if (!okVenc) return;
    }
    fb.showSuccess("Rascunho gravado.");
  };

  const criticar = async () => {
    const c = await ensureConn();
    if (!c || !codigo) return;
    const okCab = await salvarCabecalho();
    if (!okCab) return;
    const okItens = await salvarItens(itens);
    if (!okItens) return;
    setCriticando(true);
    try {
      const r = await fetch(apiUrl("/api/recebimento/criticar"), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, codigo, classe, master: isMaster }),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível criticar o recebimento.")); return; }
      if (j.divergencias?.length) {
        fb.showWarning(`Crítica encontrou ${j.divergencias.length} divergência(s) fora da tolerância — corrija antes de atualizar.`, undefined, 5000);
      } else if (j.ajustes?.length) {
        fb.showSuccess(`Crítica ajustou ${j.ajustes.length} item(ns) automaticamente dentro da tolerância.`, undefined, 5000);
        const g = await fetch(apiUrl(`/api/recebimento/${codigo}?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`));
        const gj = await g.json();
        if (gj?.success) aplicarRascunhoCarregado(gj);
      } else {
        fb.showSuccess("Crítica sem divergências.");
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setCriticando(false);
    }
  };

  const aplicarRascunhoCarregado = (j: any) => {
    const novosItens: ItemRecebimento[] = (j.itens || []).map((it: any) => ({
      codautonum: it.codautonum, codigo_int: it.codigo_int, descricao: it.codigo_int,
      qtd: String(it.qtd ?? "0"), qtd_un_compra: String(it.qtd_un_compra ?? "1"), p_unit: String(it.p_unit ?? "0"),
      base_icms: String(it.base_icms ?? "0"), valor_icms: String(it.valor_icms ?? "0"), alqt_icms: String(it.alqt_icms ?? "0"),
      base_ipi: String(it.base_ipi ?? "0"), alqt_ipi: String(it.alqt_ipi ?? "0"), valor_ipi: String(it.valor_ipi ?? "0"),
      base_sub: String(it.base_sub ?? "0"), valor_sub: String(it.valor_sub ?? "0"),
      base_iss: String(it.base_iss ?? "0"), valor_iss: String(it.valor_iss ?? "0"),
      frete: String(it.frete ?? "0"), seguro: String(it.seguro ?? "0"), despesas: String(it.despesas ?? "0"),
      desconto: String(it.desconto ?? "0"), numero_pedido: it.numero_pedido ? String(it.numero_pedido) : "",
      atualiza_preco: !!it.atualiza_preco,
    }));
    setItens((cur) => cur.map((it, i) => novosItens[i] ? { ...it, ...novosItens[i], descricao: it.descricao } : it));
  };

  const atualizar = async () => {
    const c = await ensureConn();
    if (!c || !codigo) return;
    if (itens.length === 0) { fb.showError("Lance ao menos um item antes de atualizar."); return; }
    if (itens.some((it) => !it.vinculado)) {
      fb.showError('Existem itens do XML sem produto vinculado — use "Vincular Produto" antes de atualizar.');
      return;
    }
    if (Math.round(somaVencimentos * 100) !== Math.round(valorTotalItens * 100)) {
      fb.showError(`Os vencimentos somam ${formatBRL(somaVencimentos)}, mas o total dos itens é ${formatBRL(valorTotalItens)} — ajuste antes de atualizar.`);
      return;
    }
    const okCab = await salvarCabecalho();
    if (!okCab) return;
    const okItens = await salvarItens(itens);
    if (!okItens) return;
    const okVenc = await salvarVencimentos(vencimentos);
    if (!okVenc) return;

    setAtualizando(true);
    try {
      const body = {
        servidor: c.servidor, banco: c.banco, codigo,
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(apiUrl("/api/recebimento/atualizar"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Recebimento atualizado.", undefined, 5000);
        setResultado({ n_fiscal: j.n_fiscal });
        setPromovida(true);
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível atualizar o recebimento."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setAtualizando(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Recebimento de Mercadoria." testID="recebimento-no-perm" />;
  }

  const opcoesMov: SelectOption[] = tiposMov.map((t) => ({ value: t.codigo, label: `${t.codigo} — ${t.descricao}` }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="recebimento-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Recebimento de Mercadoria</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="recebimento-ajuda"
        />
      </View>

      {carregando ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            {promovida ? (
              <View style={[styles.card, { backgroundColor: colors.surfaceSecondary }]}>
                <Text style={styles.hint}>Este recebimento já foi atualizado — o rascunho não pode mais ser editado nesta fase.</Text>
              </View>
            ) : null}

            <View style={styles.card}>
              <AccordionSection title="Cabeçalho" defaultExpanded testID="recebimento-cabecalho-section">
                <View style={styles.fieldsRow}>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Tipo de Movimentação</Text>
                    <SelectField
                      value={mov} onChange={(v) => setMov(v as string)} options={opcoesMov}
                      compactWeb placeholder="Selecione" disabled={promovida} testID="recebimento-mov"
                    />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.fieldLabel}>CFOP</Text>
                    <TextInput value={cfop} onChangeText={setCfop} editable={!promovida} style={styles.input} testID="recebimento-cfop" />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>Fornecedor</Text>
                {fornecedor ? (
                  <View style={styles.clienteRow}>
                    <Ionicons name="business-outline" size={22} color={colors.brandPrimary} />
                    <Text style={styles.clienteNome} numberOfLines={1}>{fornecedor.nome}</Text>
                    {!promovida ? (
                      <Pressable onPress={() => setFornSearchOpen(true)} testID="recebimento-trocar-fornecedor">
                        <Text style={styles.trocarText}>Trocar</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ) : (
                  <Pressable onPress={() => setFornSearchOpen(true)} style={styles.selecionarBtn} disabled={promovida} testID="recebimento-selecionar-fornecedor">
                    <Ionicons name="search" size={18} color="#fff" />
                    <Text style={styles.selecionarBtnText}>Selecionar Fornecedor</Text>
                  </Pressable>
                )}

                <View style={styles.fieldsRow}>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Nº da Nota</Text>
                    <TextInput value={numNf} onChangeText={setNumNf} keyboardType="numeric" editable={!promovida} style={styles.input} testID="recebimento-num-nf" />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Série</Text>
                    <TextInput value={serieNf} onChangeText={setSerieNf} editable={!promovida} style={styles.input} testID="recebimento-serie-nf" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Data de Emissão</Text>
                    <WebDateField value={dataEmissao} onChange={(v) => { setDataEmissao(v); if (v) setDataMov(v); }} testID="recebimento-data-emissao" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Data de Movimento</Text>
                    <WebDateField value={dataMov} onChange={setDataMov} testID="recebimento-data-mov" />
                  </View>
                </View>

                <View style={styles.fieldsRow}>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Frete</Text>
                    <TextInput value={frete} onChangeText={setFrete} keyboardType="numeric" editable={!promovida} style={styles.input} />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Frete Fora Nota</Text>
                    <TextInput value={freteFora} onChangeText={setFreteFora} keyboardType="numeric" editable={!promovida} style={styles.input} />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Seguro</Text>
                    <TextInput value={seguro} onChangeText={setSeguro} keyboardType="numeric" editable={!promovida} style={styles.input} />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Despesas</Text>
                    <TextInput value={despesas} onChangeText={setDespesas} keyboardType="numeric" editable={!promovida} style={styles.input} />
                  </View>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Desconto</Text>
                    <TextInput value={desconto} onChangeText={setDesconto} keyboardType="numeric" editable={!promovida} style={styles.input} />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>Observações</Text>
                <TextInput value={obs} onChangeText={setObs} editable={!promovida} style={[styles.input, { minHeight: 60 }]} multiline testID="recebimento-obs" />
              </AccordionSection>
            </View>

            <View style={styles.card}>
              <View style={styles.itensHeaderRow}>
                <Text style={styles.sectionTitle}>Itens</Text>
                {!promovida ? (
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <Pressable onPress={abrirSeletorXml} disabled={importandoXml} style={styles.secondaryBtn} testID="recebimento-importar-xml">
                      {importandoXml ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Text style={styles.secondaryBtnText}>Importar XML</Text>}
                    </Pressable>
                    <Pressable onPress={() => { setVinculandoIdx(null); setProdutoSearchOpen(true); }} style={styles.addItemBtn} testID="recebimento-add-item">
                      <Ionicons name="add" size={16} color="#fff" />
                      <Text style={styles.addItemBtnText}>Item</Text>
                    </Pressable>
                    {Platform.OS === "web" ? (
                      // eslint-disable-next-line react/no-unknown-property
                      <input ref={xmlInputRef} type="file" accept=".xml" style={{ display: "none" }} onChange={handleArquivoXmlSelecionado} />
                    ) : null}
                  </View>
                ) : null}
              </View>
              {itens.length === 0 ? (
                <Text style={styles.hint}>Nenhum item lançado.</Text>
              ) : (
                itens.map((it, idx) => (
                  <View
                    key={`${it.codigo_int}-${idx}`}
                    style={[styles.itemCard, !it.vinculado && styles.itemCardSemVinculo]}
                    testID={`recebimento-item-${idx}`}
                  >
                    <View style={styles.itemHeaderRow}>
                      <Text style={styles.itemDescricao} numberOfLines={1}>{it.codigo_int || "(sem código)"} — {it.descricao}</Text>
                      {it.numero_pedido ? <Text style={styles.pedidoBadge}>Pedido {it.numero_pedido}</Text> : null}
                      {!promovida ? (
                        <Pressable onPress={() => removerItem(idx)} hitSlop={8}>
                          <Ionicons name="trash-outline" size={16} color={colors.error} />
                        </Pressable>
                      ) : null}
                    </View>
                    {!it.vinculado ? (
                      <View style={styles.semVinculoRow}>
                        <Ionicons name="alert-circle-outline" size={16} color={colors.warning} />
                        <Text style={styles.semVinculoText}>Produto do XML não encontrado no cadastro.</Text>
                        {!promovida ? (
                          <Pressable onPress={() => abrirVincularProduto(idx)} testID={`recebimento-vincular-${idx}`}>
                            <Text style={styles.vincularText}>Vincular Produto</Text>
                          </Pressable>
                        ) : null}
                      </View>
                    ) : null}
                    <View style={styles.fieldsRow}>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Qtd.</Text>
                        <TextInput value={it.qtd} onChangeText={(v) => atualizarItem(idx, "qtd", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Qtd. Un. Compra</Text>
                        <TextInput value={it.qtd_un_compra} onChangeText={(v) => atualizarItem(idx, "qtd_un_compra", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor Unit.</Text>
                        <TextInput value={it.p_unit} onChangeText={(v) => atualizarItem(idx, "p_unit", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Total Item</Text>
                        <Text style={styles.itemTotalValor}>{formatBRL(num(it.qtd) * num(it.p_unit))}</Text>
                      </View>
                    </View>
                    <View style={styles.fieldsRow}>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Alq. ICMS</Text>
                        <TextInput value={it.alqt_icms} onChangeText={(v) => atualizarItem(idx, "alqt_icms", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor ICMS</Text>
                        <TextInput value={it.valor_icms} onChangeText={(v) => atualizarItem(idx, "valor_icms", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Alq. IPI</Text>
                        <TextInput value={it.alqt_ipi} onChangeText={(v) => atualizarItem(idx, "alqt_ipi", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor IPI</Text>
                        <TextInput value={it.valor_ipi} onChangeText={(v) => atualizarItem(idx, "valor_ipi", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor ST</Text>
                        <TextInput value={it.valor_sub} onChangeText={(v) => atualizarItem(idx, "valor_sub", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                    </View>
                    <View style={styles.fieldsRow}>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Frete Item</Text>
                        <TextInput value={it.frete} onChangeText={(v) => atualizarItem(idx, "frete", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Seguro Item</Text>
                        <TextInput value={it.seguro} onChangeText={(v) => atualizarItem(idx, "seguro", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Despesas Item</Text>
                        <TextInput value={it.despesas} onChangeText={(v) => atualizarItem(idx, "despesas", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Desconto Item</Text>
                        <TextInput value={it.desconto} onChangeText={(v) => atualizarItem(idx, "desconto", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={[styles.colTiny, { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 18 }]}>
                        <Switch
                          value={it.atualiza_preco} onValueChange={(v) => atualizarItem(idx, "atualiza_preco", v)}
                          disabled={promovida} testID={`recebimento-atualiza-preco-${idx}`}
                        />
                        <Text style={styles.fieldLabel}>Atualiza Preço</Text>
                      </View>
                    </View>
                  </View>
                ))
              )}
            </View>

            <View style={styles.card}>
              <View style={styles.itensHeaderRow}>
                <Text style={styles.sectionTitle}>Vencimentos</Text>
                {!promovida ? (
                  <Pressable onPress={adicionarVencimento} style={styles.addItemBtn} testID="recebimento-add-vencimento">
                    <Ionicons name="add" size={16} color="#fff" />
                    <Text style={styles.addItemBtnText}>Vencimento</Text>
                  </Pressable>
                ) : null}
              </View>
              {vencimentos.length === 0 ? (
                <Text style={styles.hint}>Nenhum vencimento lançado.</Text>
              ) : (
                vencimentos.map((v, idx) => (
                  <View key={idx} style={styles.fieldsRow}>
                    <View style={styles.colHalf}>
                      <Text style={styles.fieldLabel}>Data</Text>
                      <WebDateField value={v.data_venc} onChange={(val) => atualizarVencimento(idx, "data_venc", val)} disabled={promovida} />
                    </View>
                    <View style={styles.colTiny}>
                      <Text style={styles.fieldLabel}>Valor</Text>
                      <TextInput value={v.valor} onChangeText={(val) => atualizarVencimento(idx, "valor", val)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                    </View>
                    {!promovida ? (
                      <Pressable onPress={() => removerVencimento(idx)} hitSlop={8} style={{ marginTop: 22 }}>
                        <Ionicons name="trash-outline" size={16} color={colors.error} />
                      </Pressable>
                    ) : null}
                  </View>
                ))
              )}
              <Text style={[styles.hint, { marginTop: spacing.sm }]}>
                Soma dos vencimentos: {formatBRL(somaVencimentos)} / Total dos itens: {formatBRL(valorTotalItens)}
              </Text>
            </View>

            {!promovida ? (
              <View style={styles.bulkBar} testID="recebimento-bulk-bar">
                <View>
                  <Text style={styles.bulkBarLabel}>{itens.length} item{itens.length === 1 ? "" : "s"}</Text>
                  <Text style={styles.hint}>Total: {formatBRL(valorTotalItens)}</Text>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Pressable onPress={gravarRascunho} disabled={salvando} style={styles.secondaryBtn}>
                    {salvando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Text style={styles.secondaryBtnText}>Salvar Rascunho</Text>}
                  </Pressable>
                  {canCriticar ? (
                    <Pressable onPress={criticar} disabled={criticando} style={styles.secondaryBtn} testID="recebimento-criticar">
                      {criticando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Text style={styles.secondaryBtnText}>Criticar</Text>}
                    </Pressable>
                  ) : null}
                  {canGravar ? (
                    <Pressable onPress={atualizar} disabled={atualizando} style={styles.bulkBtn} testID="recebimento-atualizar">
                      {atualizando ? <ActivityIndicator color="#fff" size="small" /> : (
                        <><Ionicons name="sync-circle-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Atualizar</Text></>
                      )}
                    </Pressable>
                  ) : null}
                </View>
              </View>
            ) : null}
          </View>
        </ScrollView>
      )}

      <AppModal visible={!!resultado} transparent animationType="fade" onRequestClose={() => setResultado(null)}>
        <Pressable style={styles.modalBg} onPress={() => setResultado(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Recebimento atualizado</Text>
              <Pressable onPress={() => setResultado(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>Nota Fiscal nº {resultado?.n_fiscal} gerada — custo, preço, estoque e Pedidos de Compra em aberto já foram atualizados.</Text>
          </Pressable>
        </Pressable>
      </AppModal>

      <FornecedorSearchModal
        visible={fornSearchOpen}
        onClose={() => setFornSearchOpen(false)}
        term={fornSearchTerm}
        setTerm={(v) => { setFornSearchTerm(v); buscarFornecedores(v); }}
        loading={fornSearchLoading}
        results={fornSearchResults}
        onPick={(f) => { setFornecedor(f); setFornSearchOpen(false); }}
      />

      <ProdutoSearchModal
        visible={produtoSearchOpen}
        onClose={() => setProdutoSearchOpen(false)}
        term={produtoSearchTerm}
        setTerm={(v) => { setProdutoSearchTerm(v); buscarProdutos(v); }}
        loading={produtoSearchLoading}
        results={produtoSearchResults}
        onPick={selecionarProduto}
      />

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Recebimento de Mercadoria" itens={RECEBIMENTO_AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm, zIndex: 100 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 4 },

  fieldsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  colHalf: { flexBasis: "47%", flexGrow: 1 },
  colNarrow: { width: 110 },
  colTiny: { width: 110 },
  input: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: 10, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface },
  itemTotalValor: { fontSize: 13, fontWeight: "700", color: colors.onSurface, paddingVertical: 8 },

  clienteRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: 6 },
  clienteNome: { flex: 1, fontSize: 15, fontWeight: "700", color: colors.onSurface },
  trocarText: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  selecionarBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8, backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, alignSelf: "flex-start", paddingHorizontal: spacing.lg, marginTop: 6 },
  selecionarBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },

  itensHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addItemBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 6 },
  addItemBtnText: { color: "#fff", fontWeight: "600", fontSize: 12 },

  itemCard: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, padding: spacing.sm, marginTop: spacing.sm },
  itemCardSemVinculo: { borderColor: colors.warning, borderWidth: 1.5 },
  itemHeaderRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, justifyContent: "space-between", marginBottom: 4 },
  itemDescricao: { flex: 1, fontSize: 13, fontWeight: "600", color: colors.onSurface },
  pedidoBadge: { fontSize: 11, fontWeight: "600", color: colors.brandPrimary, backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2 },
  semVinculoRow: { flexDirection: "row", alignItems: "center", gap: 6, marginBottom: spacing.sm },
  semVinculoText: { flex: 1, fontSize: 12, color: colors.warning },
  vincularText: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary },

  bulkBar: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm, backgroundColor: colors.surfaceSecondary },
  bulkBarLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  bulkBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  bulkBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  secondaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 480, borderWidth: 1, borderColor: colors.border },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
});
