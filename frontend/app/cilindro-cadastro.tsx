import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import WebDateField from "@/src/components/WebDateField";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;

type CilindroItem = {
  cod: number; codigo: string; capacidade: number; pressao: number; padrao: string;
  descricao: string; grupo_gas: string; situacao: string; preco_venda: number;
};

type ProdutoBusca = { tipo: string; codigo: number; descricao: string; cod_fab: string };

// Cliente x Cilindro e Cilindro/Nº Série — popups da tela de Cadastro no
// legado (Frame3/Frame4 de FrmManCil.frm, abertos pelos botões "Cliente/
// Cilindro" e "Cilindro/Nº Série" de Frame1), não telas próprias. Ver
// "Pedido de Cilindro" e PENDENCIAS.md > "Cilindros".
type VinculoItem = {
  cliente: number; cliente_nome: string; cilindro: number;
  codigo: string; capacidade: number; pressao: number; padrao: string; descricao: string;
};

type ClienteBusca = { codigo: number; nome: string; cgc_cpf?: string; telefone?: string };
type FornecedorBusca = { codigo_int: number; codigo: string; nome: string; fantasia?: string };

type SerieItem = {
  codigo: number; numero_de_serie: string; cilindro: number; cilindro_codigo: string;
  capacidade: number; pressao: number; padrao: string; descricao: string;
  destino: number; tipo_destino: number; carga: number; situacao: string;
  revisao?: string | null; prazo_revisao?: number; proxima_revisao?: string | null;
};

const isCompactWeb = Platform.OS === "web";

const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);
const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);

// Cadastro de Cilindros (tabela `Cilindro`). Legado: FrmManCil.frm (Frame1
// "Cadastro" + Frame2 "Consulta"). Tela compacta, sem abas — igual
// Fornecedores ("Exception — compact single-view screens" no CLAUDE.md),
// já que o legado também não tem controle de abas nesta tela. Ver memória
// de projeto "Cilindros" e PENDENCIAS.md.
//
// Regra real (não um truque VB6): a chave de duplicidade é a COMBINAÇÃO
// (codigo, capacidade, pressao, padrao) — validada no backend
// (cilindro_service._save_cilindro_sync), não apenas um código único.
export default function CilindroCadastroScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cadastro de Cilindros está disponível apenas no web."
        testID="cilindro-cadastro-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<CilindroItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [padraoOptions, setPadraoOptions] = useState<SelectOption[]>([]);
  const [situacaoOptions, setSituacaoOptions] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCod, setEditingCod] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const [codigo, setCodigo] = useState("");
  const [codigoDescricao, setCodigoDescricao] = useState<string | null>(null);
  const [codigoChecando, setCodigoChecando] = useState(false);
  const [capacidade, setCapacidade] = useState("");
  const [pressao, setPressao] = useState("");
  const [padrao, setPadrao] = useState<string | null>(null);
  const [descricao, setDescricao] = useState("");
  const [situacao, setSituacao] = useState<string | null>("A");

  const [qtdProduto, setQtdProduto] = useState("1");
  const [unQtdProduto, setUnQtdProduto] = useState("M3");
  const [unCp, setUnCp] = useState("LT");
  const [fator, setFator] = useState("1");
  const [pesoLiq, setPesoLiq] = useState("");
  const [pesoBruto, setPesoBruto] = useState("");
  const [precoVenda, setPrecoVenda] = useState("");
  const [precoCusto, setPrecoCusto] = useState("");
  const [precoLocacao, setPrecoLocacao] = useState("");
  const [prazoRevisao, setPrazoRevisao] = useState("3");
  const [eCilindro, setECilindro] = useState(true);

  const [produtoModalOpen, setProdutoModalOpen] = useState(false);
  const [produtoBusca, setProdutoBusca] = useState("");
  const [produtoResultados, setProdutoResultados] = useState<ProdutoBusca[]>([]);
  const [produtoBuscando, setProdutoBuscando] = useState(false);

  // ---- Clientes x Cilindro (popup) ----
  const [vinculoModalOpen, setVinculoModalOpen] = useState(false);
  const [vinculos, setVinculos] = useState<VinculoItem[]>([]);
  const [vinculoSearch, setVinculoSearch] = useState("");
  const [vinculoLoading, setVinculoLoading] = useState(false);
  const [vinculoSaving, setVinculoSaving] = useState(false);
  const [vinculoCliente, setVinculoCliente] = useState<{ codigo: number; nome: string } | null>(null);
  const [vinculoCilindro, setVinculoCilindro] = useState<CilindroItem | null>(null);

  // ---- Cilindro/Nº Série (popup) ----
  const [serieModalOpen, setSerieModalOpen] = useState(false);
  const [series, setSeries] = useState<SerieItem[]>([]);
  const [serieSearch, setSerieSearch] = useState("");
  const [serieLoading, setSerieLoading] = useState(false);
  const [serieSaving, setSerieSaving] = useState(false);
  const [serieEditandoCodigo, setSerieEditandoCodigo] = useState<number | null>(null);
  const [numeroSerie, setNumeroSerie] = useState("");
  const [serieCilindro, setSerieCilindro] = useState<CilindroItem | null>(null);
  const [serieDestinoTipo, setSerieDestinoTipo] = useState<"C" | "F">("C");
  const [serieDestinoCodigo, setSerieDestinoCodigo] = useState("");
  const [serieDestinoNome, setSerieDestinoNome] = useState("");
  const [serieDataCompra, setSerieDataCompra] = useState<string | null>(null);
  const [serieNfCompra, setSerieNfCompra] = useState("");
  const [serieFornecedorCompra, setSerieFornecedorCompra] = useState("");
  const [serieFabricacao, setSerieFabricacao] = useState<string | null>(null);
  const [serieEntrada, setSerieEntrada] = useState<string | null>(null);
  const [serieSaida, setSerieSaida] = useState<string | null>(null);
  const [serieRevisao, setSerieRevisao] = useState<string | null>(null);
  const [serieCarga, setSerieCarga] = useState<"CHEIO" | "VAZIO">("CHEIO");
  const [serieSituacao, setSerieSituacao] = useState<string | null>("A");

  // ---- Pickers compartilhados (Cliente / Cilindro / Fornecedor) ----
  const [clientePickerOpen, setClientePickerOpen] = useState(false);
  const [clientePickerTarget, setClientePickerTarget] = useState<"vinculo" | "destino">("vinculo");
  const [clienteBusca, setClienteBusca] = useState("");
  const [clienteResultados, setClienteResultados] = useState<ClienteBusca[]>([]);
  const [clienteBuscando, setClienteBuscando] = useState(false);

  const [cilindroPickerOpen, setCilindroPickerOpen] = useState(false);
  const [cilindroPickerTarget, setCilindroPickerTarget] = useState<"vinculo" | "serie">("vinculo");
  const [cilindroPickerBusca, setCilindroPickerBusca] = useState("");
  const [cilindroPickerResultados, setCilindroPickerResultados] = useState<CilindroItem[]>([]);
  const [cilindroPickerBuscando, setCilindroPickerBuscando] = useState(false);

  const [fornecedorPickerOpen, setFornecedorPickerOpen] = useState(false);
  const [fornecedorBusca, setFornecedorBusca] = useState("");
  const [fornecedorResultados, setFornecedorResultados] = useState<FornecedorBusca[]>([]);
  const [fornecedorBuscando, setFornecedorBuscando] = useState(false);

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(search)}&size=50`;
      const r = await fetch(`${base}/api/cilindros?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [search]);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    try {
      const [rPadrao, rSit] = await Promise.all([
        fetch(`${base}/api/cilindro-fabricante?${qs}`).then((r) => r.json()).catch(() => null),
        fetch(`${base}/api/tabelas/situacao?${qs}`).then((r) => r.json()).catch(() => null),
      ]);
      if (rPadrao?.success) setPadraoOptions(rPadrao.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
      if (rSit?.success) setSituacaoOptions(rSit.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
    } catch {
      // silencioso — combos ficam vazios
    }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c);
      loadLookups(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (conn) load(conn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const resetForm = () => {
    setCodigo(""); setCodigoDescricao(null); setCapacidade(""); setPressao(""); setPadrao(null);
    setDescricao(""); setSituacao("A");
    setQtdProduto("1"); setUnQtdProduto("M3"); setUnCp("LT"); setFator("1");
    setPesoLiq(""); setPesoBruto(""); setPrecoVenda(""); setPrecoCusto(""); setPrecoLocacao("");
    setPrazoRevisao("3"); setECilindro(true);
  };

  const openNew = () => {
    setEditingCod(null);
    resetForm();
    setFormOpen(true);
  };

  const openEdit = async (item: CilindroItem) => {
    if (!conn) return;
    setEditingCod(item.cod);
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/cilindros/${item.cod}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d = j.item;
      setCodigo(d.codigo || ""); setCodigoDescricao(null);
      setCapacidade(String(d.capacidade ?? "")); setPressao(String(d.pressao ?? "")); setPadrao(d.padrao || null);
      setDescricao(d.descricao || ""); setSituacao(d.situacao || "A");
      setQtdProduto(String(d.qtd_produto ?? "1")); setUnQtdProduto(d.un_qtd_produto || "M3"); setUnCp(d.un_cp || "LT");
      setFator(String(d.fator ?? "1"));
      setPesoLiq(String(d.peso_liq ?? "")); setPesoBruto(String(d.peso_bruto ?? ""));
      setPrecoVenda(String(d.preco_venda ?? "")); setPrecoCusto(String(d.preco_custo ?? "")); setPrecoLocacao(String(d.preco_locacao ?? ""));
      setPrazoRevisao(String(d.prazo_revisao ?? "3")); setECilindro(d.E_CILINDRO ?? true);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  // Busca o produto de venda no lostfocus do código (Pecas.codigo_fab) —
  // mesmo padrão já usado em Produto Completo/Fornecedores: confirma que o
  // código digitado existe e mostra a descrição, sem travar a digitação.
  const buscarProduto = useCallback(async () => {
    const raw = codigo.trim();
    setCodigoDescricao(null);
    if (!raw || !conn) return;
    setCodigoChecando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/cilindros/produto/${encodeURIComponent(raw)}?${qs}`);
      const j = await r.json();
      if (j?.success && j?.found) setCodigoDescricao(j.descricao || "");
      else if (j?.success) fb.showWarning("Produto de Venda não cadastrado.");
    } catch {
      // silencioso — validação real acontece na gravação
    } finally {
      setCodigoChecando(false);
    }
  }, [codigo, conn, fb]);

  // Modal de busca do Produto de Venda — mesma tabela/endpoint já usado
  // pelo picker de item de Pedido/O.S. (`/api/produtos-servicos`), filtrado
  // a `tipo=P` (só produtos físicos fazem sentido como cilindro, não
  // serviços). Sem isso o usuário precisaria já saber de cor o Código de
  // Fábrica exato pra digitar no campo — inviável na prática.
  const buscarProdutos = useCallback(async (termo: string) => {
    if (!conn) return;
    setProdutoBuscando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(termo)}&tipo=P&size=20`;
      const r = await fetch(`${base}/api/produtos-servicos?${qs}`);
      const j = await r.json();
      setProdutoResultados(j?.success ? j.items || [] : []);
    } catch {
      setProdutoResultados([]);
    } finally {
      setProdutoBuscando(false);
    }
  }, [conn]);

  const abrirBuscaProduto = () => {
    setProdutoBusca("");
    setProdutoResultados([]);
    setProdutoModalOpen(true);
    buscarProdutos("");
  };

  const selecionarProduto = (p: ProdutoBusca) => {
    if (!p.cod_fab) {
      fb.showWarning("Este produto não tem Código de Fábrica cadastrado — necessário pra vincular ao Cilindro.");
      return;
    }
    setCodigo(p.cod_fab);
    setCodigoDescricao(p.descricao || "");
    setProdutoModalOpen(false);
  };

  // ============================================================
  // Pickers compartilhados (Cliente / Cilindro / Fornecedor)
  // ============================================================
  const buscarClientes = useCallback(async (termo: string) => {
    if (!conn) return;
    setClienteBuscando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(termo)}`;
      const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
      const j = await r.json();
      setClienteResultados(j?.success ? j.items || [] : []);
    } catch { setClienteResultados([]); } finally { setClienteBuscando(false); }
  }, [conn]);

  const abrirClientePicker = (target: "vinculo" | "destino") => {
    setClientePickerTarget(target);
    setClienteBusca("");
    setClienteResultados([]);
    setClientePickerOpen(true);
    buscarClientes("");
  };

  const selecionarCliente = (c: ClienteBusca) => {
    if (clientePickerTarget === "vinculo") {
      setVinculoCliente({ codigo: c.codigo, nome: c.nome });
    } else {
      setSerieDestinoTipo("C");
      setSerieDestinoCodigo(String(c.codigo));
      setSerieDestinoNome(c.nome);
    }
    setClientePickerOpen(false);
  };

  const buscarCilindrosPicker = useCallback(async (termo: string) => {
    if (!conn) return;
    setCilindroPickerBuscando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(termo)}&size=30`;
      const r = await fetch(`${base}/api/cilindros?${qs}`);
      const j = await r.json();
      setCilindroPickerResultados(j?.success ? j.items || [] : []);
    } catch { setCilindroPickerResultados([]); } finally { setCilindroPickerBuscando(false); }
  }, [conn]);

  const abrirCilindroPicker = (target: "vinculo" | "serie") => {
    setCilindroPickerTarget(target);
    setCilindroPickerBusca("");
    setCilindroPickerResultados([]);
    setCilindroPickerOpen(true);
    buscarCilindrosPicker("");
  };

  const selecionarCilindroPicker = (c: CilindroItem) => {
    if (cilindroPickerTarget === "vinculo") setVinculoCilindro(c);
    else setSerieCilindro(c);
    setCilindroPickerOpen(false);
  };

  const buscarFornecedores = useCallback(async (termo: string) => {
    if (!conn) return;
    setFornecedorBuscando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(termo)}`;
      const r = await fetch(`${base}/api/fornecedores?${qs}`);
      const j = await r.json();
      setFornecedorResultados(j?.success ? j.items || [] : []);
    } catch { setFornecedorResultados([]); } finally { setFornecedorBuscando(false); }
  }, [conn]);

  const abrirFornecedorPicker = () => {
    setFornecedorBusca("");
    setFornecedorResultados([]);
    setFornecedorPickerOpen(true);
    buscarFornecedores("");
  };

  const selecionarFornecedor = (f: FornecedorBusca) => {
    setSerieDestinoTipo("F");
    setSerieDestinoCodigo(String(f.codigo_int));
    setSerieDestinoNome(f.nome);
    setFornecedorPickerOpen(false);
  };

  // ============================================================
  // Clientes x Cilindro
  // ============================================================
  const loadVinculos = useCallback(async (term?: string) => {
    if (!conn) return;
    setVinculoLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(term ?? vinculoSearch)}&size=50`;
      const r = await fetch(`${base}/api/cilindro-cliente?${qs}`);
      const j = await r.json();
      setVinculos(j?.success ? j.items || [] : []);
    } catch { setVinculos([]); } finally { setVinculoLoading(false); }
  }, [conn, vinculoSearch]);

  const abrirVinculoModal = () => {
    setVinculoCliente(null);
    setVinculoCilindro(null);
    setVinculoSearch("");
    setVinculoModalOpen(true);
    loadVinculos("");
  };

  const salvarVinculo = async () => {
    if (!conn) return;
    if (!vinculoCliente) { fb.showWarning("Selecione o Cliente."); return; }
    if (!vinculoCilindro) { fb.showWarning("Selecione o Cilindro."); return; }
    setVinculoSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/cilindro-cliente`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          cliente: vinculoCliente.codigo, cilindro: vinculoCilindro.cod,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Vínculo gravado.");
        setVinculoCliente(null); setVinculoCilindro(null);
        loadVinculos();
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setVinculoSaving(false); }
  };

  const excluirVinculo = (v: VinculoItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Remover o vínculo entre "${v.cliente_nome}" e o cilindro "${v.codigo}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/cilindro-cliente/${v.cilindro}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, cliente: v.cliente }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); loadVinculos(); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  // ============================================================
  // Cilindro/Nº Série
  // ============================================================
  const loadSeries = useCallback(async (term?: string) => {
    if (!conn) return;
    setSerieLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(term ?? serieSearch)}&size=50`;
      const r = await fetch(`${base}/api/cilindro-serie?${qs}`);
      const j = await r.json();
      setSeries(j?.success ? j.items || [] : []);
    } catch { setSeries([]); } finally { setSerieLoading(false); }
  }, [conn, serieSearch]);

  const resetSerieForm = () => {
    setSerieEditandoCodigo(null);
    setNumeroSerie(""); setSerieCilindro(null);
    setSerieDestinoTipo("C"); setSerieDestinoCodigo(""); setSerieDestinoNome("");
    setSerieDataCompra(null); setSerieNfCompra(""); setSerieFornecedorCompra("");
    setSerieFabricacao(null); setSerieEntrada(null); setSerieSaida(null); setSerieRevisao(null);
    setSerieCarga("CHEIO"); setSerieSituacao("A");
  };

  const abrirSerieModal = () => {
    resetSerieForm();
    setSerieSearch("");
    setSerieModalOpen(true);
    loadSeries("");
  };

  const buscarDetalheSerie = useCallback(async (codigo: number) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/cilindro-serie/${codigo}?${qs}`);
      const j = await r.json();
      if (j?.success) {
        const d = j.item;
        setSerieDataCompra(d.data_compra ? String(d.data_compra).slice(0, 10) : null);
        setSerieNfCompra(d.nf_compra ? String(d.nf_compra) : "");
        setSerieFornecedorCompra(d.fornecedor ? String(d.fornecedor) : "");
        setSerieFabricacao(d.fabricacao ? String(d.fabricacao).slice(0, 10) : null);
        setSerieEntrada(d.entrada ? String(d.entrada).slice(0, 10) : null);
        setSerieSaida(d.saida ? String(d.saida).slice(0, 10) : null);
        setSerieRevisao(d.revisao ? String(d.revisao).slice(0, 10) : null);
      }
    } catch {
      // silencioso — os campos de data ficam em branco, usuário pode preencher de novo
    }
  }, [conn]);

  const editarSerie = (item: SerieItem) => {
    setSerieEditandoCodigo(item.codigo);
    setNumeroSerie(item.numero_de_serie);
    setSerieCilindro({
      cod: item.cilindro, codigo: item.cilindro_codigo, capacidade: item.capacidade,
      pressao: item.pressao, padrao: item.padrao, descricao: item.descricao,
      situacao: "", grupo_gas: "", preco_venda: 0,
    });
    setSerieDestinoTipo(item.tipo_destino === 1 ? "F" : "C");
    setSerieDestinoCodigo(item.destino ? String(item.destino) : "");
    setSerieDestinoNome("");
    setSerieCarga(item.carga === 1 ? "VAZIO" : "CHEIO");
    setSerieSituacao(item.situacao || "A");
    buscarDetalheSerie(item.codigo);
  };

  const salvarSerie = async () => {
    if (!conn) return;
    if (!numeroSerie.trim()) { fb.showWarning("Informe o Número de Série."); return; }
    if (!serieCilindro) { fb.showWarning("Selecione o Cilindro."); return; }
    setSerieSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/cilindro-serie`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: serieEditandoCodigo,
          dados: {
            numero_de_serie: numeroSerie.trim(),
            cilindro: serieCilindro.cod,
            destino: int_(serieDestinoCodigo),
            tipo_destino: serieDestinoTipo,
            data_compra: serieDataCompra,
            nf_compra: serieNfCompra ? int_(serieNfCompra) : null,
            fornecedor: serieFornecedorCompra ? int_(serieFornecedorCompra) : null,
            fabricacao: serieFabricacao,
            entrada: serieEntrada,
            saida: serieSaida,
            revisao: serieRevisao,
            carga: serieCarga,
            situacao: (serieSituacao || "A").toUpperCase(),
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Registro gravado.");
        setSerieEditandoCodigo(j.codigo);
        loadSeries();
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSerieSaving(false); }
  };

  const excluirSerie = (item: SerieItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão do número de série "${item.numero_de_serie}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/cilindro-serie/${item.codigo}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) {
              fb.showSuccess(j.message || "Excluído."); loadSeries();
              if (serieEditandoCodigo === item.codigo) resetSerieForm();
            } else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const save = async () => {
    if (!conn) return;
    if (!codigo.trim()) { fb.showWarning("Informe o Produto de Venda."); return; }
    if (!padrao) { fb.showWarning("Informe o Padrão."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/cilindros`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          cod: editingCod,
          dados: {
            codigo: codigo.trim(), capacidade: int_(capacidade), pressao: int_(pressao), padrao,
            descricao: descricao.trim(), situacao: (situacao || "A").toUpperCase(),
            qtd_produto: num(qtdProduto) || 1, un_qtd_produto: unQtdProduto.trim() || "M3",
            un_cp: unCp.trim() || "LT", fator: num(fator) || 1,
            peso_liq: num(pesoLiq), peso_bruto: num(pesoBruto),
            preco_venda: num(precoVenda), preco_custo: num(precoCusto), preco_locacao: num(precoLocacao),
            prazo_revisao: int_(prazoRevisao) || 3, E_CILINDRO: eCilindro,
          },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Cilindro gravado.");
        setEditingCod(j.cod);
        load(conn);
      } else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = (item: CilindroItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão do cilindro "${item.codigo} - ${item.descricao}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/cilindros/${item.cod}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const canSave = can("CILINDRO.GRAVAR") || isMaster;
  const canDel = can("CILINDRO.EXCLUIR") || isMaster;

  const canOpenVinculo = can("CIL_CLIENTE.ABRIR") || isMaster;
  const canSaveVinculo = can("CIL_CLIENTE.GRAVAR") || isMaster;
  const canDelVinculo = can("CIL_CLIENTE.EXCLUIR") || isMaster;

  const canOpenSerie = can("CILINDRO_SERIE.ABRIR") || isMaster;
  const canSaveSerie = can("CILINDRO_SERIE.GRAVAR") || isMaster;
  const canDelSerie = can("CILINDRO_SERIE.EXCLUIR") || isMaster;

  // ============================================================
  // Formulário (tela cheia, compacta — sem abas)
  // ============================================================
  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cilindro-cadastro-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setFormOpen(false)} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="cilindro-cadastro-form-back-button">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
          <Text style={styles.headerTitle} numberOfLines={1}>{editingCod ? `Cilindro #${editingCod}` : "Novo Cilindro"}</Text>
          {canSave ? (
            <Pressable onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="cilindro-cadastro-salvar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : <View style={{ width: 40 }} />}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colProduto}>
                  <Text style={styles.label}>Produto de Venda *</Text>
                  <View style={styles.inputWithBtn}>
                    <TextInput
                      value={codigo}
                      onChangeText={(v) => { setCodigo(v); setCodigoDescricao(null); }}
                      onBlur={buscarProduto}
                      style={[styles.input, { flex: 1, minWidth: 0 }]}
                      autoCapitalize="characters"
                      maxLength={20}
                      testID="cilindro-codigo"
                    />
                    <Pressable onPress={abrirBuscaProduto} style={styles.searchBtn} testID="cilindro-buscar-produto">
                      <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                    </Pressable>
                  </View>
                  {codigoChecando ? <Text style={styles.hint}>Verificando…</Text> : null}
                </View>
                <View style={styles.colDescProduto}>
                  <Text style={styles.label}>Descrição do Produto</Text>
                  <TextInput
                    value={codigoDescricao || ""}
                    editable={false}
                    style={[styles.input, styles.inputDisabled]}
                    testID="cilindro-produto-descricao"
                  />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Capacidade</Text>
                  <TextInput value={capacidade} onChangeText={(v) => setCapacidade(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="cilindro-capacidade" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Pressão</Text>
                  <TextInput value={pressao} onChangeText={(v) => setPressao(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="cilindro-pressao" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Padrão *</Text>
                  <SelectField value={padrao} onChange={(v) => setPadrao(v as string)} options={padraoOptions} testID="cilindro-padrao" modalTitle="Padrão" compactWeb />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Situação</Text>
                  <SelectField value={situacao} onChange={(v) => setSituacao(v as string)} options={situacaoOptions} testID="cilindro-situacao" modalTitle="Situação" compactWeb />
                </View>
              </View>

              <Text style={styles.label}>Descrição</Text>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={60} testID="cilindro-descricao" />

              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Qtd. Produto</Text>
                  <TextInput value={qtdProduto} onChangeText={setQtdProduto} style={styles.input} keyboardType="decimal-pad" testID="cilindro-qtd-produto" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Un. Qtd.</Text>
                  <TextInput value={unQtdProduto} onChangeText={setUnQtdProduto} style={styles.input} autoCapitalize="characters" maxLength={6} testID="cilindro-un-qtd" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Un. C/P</Text>
                  <TextInput value={unCp} onChangeText={setUnCp} style={styles.input} autoCapitalize="characters" maxLength={6} testID="cilindro-un-cp" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Fator</Text>
                  <TextInput value={fator} onChangeText={setFator} style={styles.input} keyboardType="decimal-pad" testID="cilindro-fator" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Prazo Revisão</Text>
                  <TextInput value={prazoRevisao} onChangeText={(v) => setPrazoRevisao(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="cilindro-prazo-revisao" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Peso Líquido</Text>
                  <TextInput value={pesoLiq} onChangeText={setPesoLiq} style={styles.input} keyboardType="decimal-pad" testID="cilindro-peso-liq" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Peso Bruto</Text>
                  <TextInput value={pesoBruto} onChangeText={setPesoBruto} style={styles.input} keyboardType="decimal-pad" testID="cilindro-peso-bruto" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Preço Venda</Text>
                  <TextInput value={precoVenda} onChangeText={setPrecoVenda} style={styles.input} keyboardType="decimal-pad" testID="cilindro-preco-venda" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Preço Custo</Text>
                  <TextInput value={precoCusto} onChangeText={setPrecoCusto} style={styles.input} keyboardType="decimal-pad" testID="cilindro-preco-custo" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Preço Locação</Text>
                  <TextInput value={precoLocacao} onChangeText={setPrecoLocacao} style={styles.input} keyboardType="decimal-pad" testID="cilindro-preco-locacao" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>É Cilindro</Text>
                  <View style={styles.switchInline}>
                    <Switch value={eCilindro} onValueChange={setECilindro} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="cilindro-e-cilindro" />
                  </View>
                </View>
              </View>
            </View>

            {editingCod && canDel ? (
              <View style={styles.toolbarRow}>
                <Pressable onPress={() => remove({ cod: editingCod, codigo, capacidade: int_(capacidade), pressao: int_(pressao), padrao: padrao || "", descricao, grupo_gas: "", situacao: situacao || "A", preco_venda: num(precoVenda) })} style={[styles.secondaryBtn, styles.dangerBtn]} testID="cilindro-excluir">
                  <Ionicons name="trash-outline" size={16} color={colors.error} />
                  <Text style={styles.dangerBtnText}>Excluir Cilindro</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </ScrollView>

        <AppModal visible={produtoModalOpen} transparent animationType="slide" onRequestClose={() => setProdutoModalOpen(false)}>
          <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setProdutoModalOpen(false)}>
            <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
              <View style={styles.slideHeader}>
                <Text style={styles.slideTitle}>Buscar Produto de Venda</Text>
                <Pressable onPress={() => setProdutoModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <TextInput
                value={produtoBusca}
                onChangeText={(v) => { setProdutoBusca(v); buscarProdutos(v); }}
                placeholder="Buscar por descrição ou código…"
                placeholderTextColor={colors.muted}
                style={styles.input}
                autoFocus
                testID="cilindro-produto-busca"
              />
              {produtoBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
              <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
                {produtoResultados.map((p) => (
                  <Pressable
                    key={p.codigo}
                    onPress={() => selecionarProduto(p)}
                    style={styles.gridRow}
                    testID={`cilindro-produto-${p.codigo}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText} numberOfLines={1}>{p.descricao}</Text>
                      <Text style={styles.hint}>{p.cod_fab || "sem código de fábrica"}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>
                ))}
                {!produtoBuscando && produtoResultados.length === 0 ? (
                  <Text style={styles.hint}>Nenhum produto encontrado.</Text>
                ) : null}
              </ScrollView>
            </Pressable>
          </Pressable>
        </AppModal>
      </SafeAreaView>
    );
  }

  // ============================================================
  // Lista / Consulta
  // ============================================================
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cilindro-cadastro-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle}>Cadastro de Cilindros</Text>
        {canOpenVinculo ? (
          <Pressable onPress={abrirVinculoModal} style={styles.iconBtn} hitSlop={8} testID="cilindro-abrir-vinculo">
            <Ionicons name="people-outline" size={20} color={colors.onBrandPrimary} />
          </Pressable>
        ) : null}
        {canOpenSerie ? (
          <Pressable onPress={abrirSerieModal} style={styles.iconBtn} hitSlop={8} testID="cilindro-abrir-serie">
            <Ionicons name="barcode-outline" size={20} color={colors.onBrandPrimary} />
          </Pressable>
        ) : null}
        {!canOpenVinculo && !canOpenSerie ? <View style={{ width: 40 }} /> : null}
      </View>

      <View style={styles.listShell}>
        <View style={styles.filterBox}>
          <TextInput value={search} onChangeText={setSearch} placeholder="Buscar por código, descrição ou grupo…" placeholderTextColor={colors.muted} style={styles.input} testID="cilindro-search" />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum cilindro cadastrado.</Text> : null}
          {items.map((it) => (
            <View key={it.cod} style={styles.row} testID={`cilindro-${it.cod}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <Text style={styles.rowTitle}>{it.descricao || it.codigo}</Text>
                <Text style={styles.rowSub}>
                  {it.codigo} · Cap. {it.capacidade} · Pressão {it.pressao} · Padrão {it.padrao}
                  {it.situacao && it.situacao !== "A" ? ` · ${it.situacao}` : ""}
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`cilindro-del-${it.cod}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="cilindro-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      {/* ============================================================ */}
      {/* Clientes x Cilindro */}
      {/* ============================================================ */}
      <AppModal visible={vinculoModalOpen} transparent animationType="slide" onRequestClose={() => setVinculoModalOpen(false)}>
        <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setVinculoModalOpen(false)}>
          <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact, styles.slideCardTall]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Clientes x Cilindro</Text>
              <Pressable onPress={() => setVinculoModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>

            {canSaveVinculo ? (
              <>
                <Text style={styles.label}>Cliente</Text>
                <Pressable onPress={() => abrirClientePicker("vinculo")} style={styles.pickerBtn} testID="vinculo-escolher-cliente">
                  <Text style={styles.pickerBtnText} numberOfLines={1}>{vinculoCliente ? vinculoCliente.nome : "Selecionar cliente…"}</Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <Text style={styles.label}>Cilindro</Text>
                <Pressable onPress={() => abrirCilindroPicker("vinculo")} style={styles.pickerBtn} testID="vinculo-escolher-cilindro">
                  <Text style={styles.pickerBtnText} numberOfLines={1}>
                    {vinculoCilindro ? `${vinculoCilindro.codigo} · Cap.${vinculoCilindro.capacidade} · Pressão ${vinculoCilindro.pressao} · Padrão ${vinculoCilindro.padrao}` : "Selecionar cilindro…"}
                  </Text>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>

                <View style={styles.modalActionsRow}>
                  <Pressable onPress={salvarVinculo} disabled={vinculoSaving} style={styles.primaryBtn} testID="vinculo-gravar">
                    {vinculoSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Gravar Vínculo</Text>}
                  </Pressable>
                </View>
                <View style={styles.divider} />
              </>
            ) : null}

            <TextInput
              value={vinculoSearch}
              onChangeText={(v) => { setVinculoSearch(v); loadVinculos(v); }}
              placeholder="Buscar por cliente ou cilindro…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="vinculo-search"
            />
            <ScrollView style={{ maxHeight: 320, marginTop: spacing.sm }}>
              {vinculoLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
              {vinculos.map((v) => (
                <View key={`${v.cliente}-${v.cilindro}`} style={styles.gridRow} testID={`vinculo-item-${v.cliente}-${v.cilindro}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{v.cliente_nome}</Text>
                    <Text style={styles.hint}>{v.codigo} · Cap.{v.capacidade} · Pressão {v.pressao} · Padrão {v.padrao}</Text>
                  </View>
                  {canDelVinculo ? (
                    <Pressable onPress={() => excluirVinculo(v)} hitSlop={8} testID={`vinculo-del-${v.cliente}-${v.cilindro}`}>
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                  ) : null}
                </View>
              ))}
              {!vinculoLoading && vinculos.length === 0 ? <Text style={styles.hint}>Nenhum vínculo cadastrado.</Text> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* ============================================================ */}
      {/* Cilindro/Nº Série */}
      {/* ============================================================ */}
      <AppModal visible={serieModalOpen} transparent animationType="slide" onRequestClose={() => setSerieModalOpen(false)}>
        <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setSerieModalOpen(false)}>
          <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact, styles.slideCardTall]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Cilindro / Nº Série</Text>
              <View style={styles.slideHeaderActions}>
                {canSaveSerie ? (
                  <Pressable onPress={salvarSerie} disabled={serieSaving} style={styles.headerSaveBtn} testID="serie-gravar-topo">
                    {serieSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.headerSaveBtnText}>Gravar</Text>}
                  </Pressable>
                ) : null}
                <Pressable onPress={() => setSerieModalOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
            </View>

            <ScrollView keyboardShouldPersistTaps="handled" style={{ maxHeight: 560 }}>
              {canSaveSerie ? (
                <>
                  <View style={styles.rowFields}>
                    <View style={styles.colFlex}>
                      <Text style={styles.label}>Número de Série *</Text>
                      <TextInput value={numeroSerie} onChangeText={setNumeroSerie} style={styles.input} testID="serie-numero" />
                    </View>
                  </View>

                  <Text style={styles.label}>Cilindro *</Text>
                  <Pressable onPress={() => abrirCilindroPicker("serie")} style={styles.pickerBtn} testID="serie-escolher-cilindro">
                    <Text style={styles.pickerBtnText} numberOfLines={1}>
                      {serieCilindro ? `${serieCilindro.codigo} · Cap.${serieCilindro.capacidade} · Pressão ${serieCilindro.pressao} · Padrão ${serieCilindro.padrao}` : "Selecionar cilindro cadastrado…"}
                    </Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                  </Pressable>

                  <View style={styles.rowFields}>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Carga</Text>
                      <View style={styles.pillRow}>
                        <Pressable onPress={() => setSerieCarga("CHEIO")} style={[styles.pillBtn, serieCarga === "CHEIO" && styles.pillBtnSel]}>
                          <Text style={[styles.pillBtnText, serieCarga === "CHEIO" && styles.pillBtnTextSel]}>Cheio</Text>
                        </Pressable>
                        <Pressable onPress={() => setSerieCarga("VAZIO")} style={[styles.pillBtn, serieCarga === "VAZIO" && styles.pillBtnSel]}>
                          <Text style={[styles.pillBtnText, serieCarga === "VAZIO" && styles.pillBtnTextSel]}>Vazio</Text>
                        </Pressable>
                      </View>
                    </View>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Situação</Text>
                      <SelectField value={serieSituacao} onChange={(v) => setSerieSituacao(v as string)} options={situacaoOptions} testID="serie-situacao" modalTitle="Situação" compactWeb />
                    </View>
                  </View>

                  <Text style={styles.label}>Destino Atual</Text>
                  <View style={styles.rowFields}>
                    <View style={styles.colFlex}>
                      <View style={styles.pillRow}>
                        <Pressable onPress={() => setSerieDestinoTipo("C")} style={[styles.pillBtn, serieDestinoTipo === "C" && styles.pillBtnSel]}>
                          <Text style={[styles.pillBtnText, serieDestinoTipo === "C" && styles.pillBtnTextSel]}>Cliente</Text>
                        </Pressable>
                        <Pressable onPress={() => setSerieDestinoTipo("F")} style={[styles.pillBtn, serieDestinoTipo === "F" && styles.pillBtnSel]}>
                          <Text style={[styles.pillBtnText, serieDestinoTipo === "F" && styles.pillBtnTextSel]}>Fornecedor</Text>
                        </Pressable>
                      </View>
                    </View>
                    <View style={styles.colFlex}>
                      <Pressable
                        onPress={() => (serieDestinoTipo === "C" ? abrirClientePicker("destino") : abrirFornecedorPicker())}
                        style={styles.pickerBtn}
                        testID="serie-escolher-destino"
                      >
                        <Text style={styles.pickerBtnText} numberOfLines={1}>
                          {serieDestinoCodigo ? (serieDestinoNome || `#${serieDestinoCodigo}`) : "Pátio (estoque próprio)"}
                        </Text>
                        <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                      </Pressable>
                    </View>
                  </View>

                  <View style={styles.rowFields}>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Data Compra</Text>
                      <WebDateField value={serieDataCompra} onChange={setSerieDataCompra} testID="serie-data-compra" />
                    </View>
                    <View style={styles.colTiny}>
                      <Text style={styles.label}>NF Compra</Text>
                      <TextInput value={serieNfCompra} onChangeText={(v) => setSerieNfCompra(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="serie-nf-compra" />
                    </View>
                    <View style={styles.colTiny}>
                      <Text style={styles.label}>Fornecedor (compra)</Text>
                      <TextInput value={serieFornecedorCompra} onChangeText={(v) => setSerieFornecedorCompra(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="serie-fornecedor-compra" />
                    </View>
                  </View>

                  <View style={styles.rowFields}>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Fabricação</Text>
                      <WebDateField value={serieFabricacao} onChange={setSerieFabricacao} testID="serie-fabricacao" />
                    </View>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Últ. Entrada</Text>
                      <WebDateField value={serieEntrada} onChange={setSerieEntrada} testID="serie-entrada" />
                    </View>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Últ. Saída</Text>
                      <WebDateField value={serieSaida} onChange={setSerieSaida} testID="serie-saida" />
                    </View>
                    <View style={styles.colNarrow}>
                      <Text style={styles.label}>Últ. Revisão</Text>
                      <WebDateField value={serieRevisao} onChange={setSerieRevisao} testID="serie-revisao" />
                    </View>
                  </View>

                  <View style={styles.modalActionsRow}>
                    {serieEditandoCodigo ? (
                      <Pressable onPress={resetSerieForm} style={styles.secondaryBtn} testID="serie-novo">
                        <Text style={styles.secondaryBtnText}>Novo</Text>
                      </Pressable>
                    ) : null}
                    {serieEditandoCodigo && canDelSerie ? (
                      <Pressable
                        onPress={() => excluirSerie({
                          codigo: serieEditandoCodigo, numero_de_serie: numeroSerie, cilindro: serieCilindro?.cod || 0,
                          cilindro_codigo: serieCilindro?.codigo || "", capacidade: serieCilindro?.capacidade || 0,
                          pressao: serieCilindro?.pressao || 0, padrao: serieCilindro?.padrao || "", descricao: "",
                          destino: int_(serieDestinoCodigo), tipo_destino: serieDestinoTipo === "F" ? 1 : 0,
                          carga: serieCarga === "VAZIO" ? 1 : 0, situacao: serieSituacao || "A",
                        })}
                        style={[styles.secondaryBtn, styles.dangerBtn]}
                        testID="serie-excluir"
                      >
                        <Ionicons name="trash-outline" size={16} color={colors.error} />
                        <Text style={styles.dangerBtnText}>Excluir</Text>
                      </Pressable>
                    ) : null}
                  </View>
                  <View style={styles.divider} />
                </>
              ) : null}

              <Text style={styles.label}>Registros</Text>
              <TextInput
                value={serieSearch}
                onChangeText={(v) => { setSerieSearch(v); loadSeries(v); }}
                placeholder="Buscar por número de série ou cilindro…"
                placeholderTextColor={colors.muted}
                style={styles.input}
                testID="serie-search"
              />
              {serieLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
              {series.map((s) => (
                <Pressable key={s.codigo} onPress={() => editarSerie(s)} style={styles.gridRow} testID={`serie-item-${s.codigo}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{s.numero_de_serie}</Text>
                    <Text style={styles.hint}>
                      {s.cilindro_codigo} · Cap.{s.capacidade} · Pressão {s.pressao} · Padrão {s.padrao}
                      {s.proxima_revisao ? ` · Próx. revisão ${s.proxima_revisao}` : ""}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              {!serieLoading && series.length === 0 ? <Text style={styles.hint}>Nenhum registro.</Text> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* Pickers compartilhados */}
      <AppModal visible={clientePickerOpen} transparent animationType="slide" onRequestClose={() => setClientePickerOpen(false)}>
        <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setClientePickerOpen(false)}>
          <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Buscar Cliente</Text>
              <Pressable onPress={() => setClientePickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <TextInput
              value={clienteBusca}
              onChangeText={(v) => { setClienteBusca(v); buscarClientes(v); }}
              placeholder="Nome, CPF/CNPJ ou telefone…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoFocus
              testID="cliente-picker-busca"
            />
            {clienteBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
            <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
              {clienteResultados.map((c) => (
                <Pressable key={c.codigo} onPress={() => selecionarCliente(c)} style={styles.gridRow} testID={`cliente-picker-${c.codigo}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText} numberOfLines={1}>{c.nome}</Text>
                    <Text style={styles.hint}>#{c.codigo}{c.cgc_cpf ? ` · ${c.cgc_cpf}` : ""}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              {!clienteBuscando && clienteResultados.length === 0 ? <Text style={styles.hint}>Nenhum cliente encontrado.</Text> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={cilindroPickerOpen} transparent animationType="slide" onRequestClose={() => setCilindroPickerOpen(false)}>
        <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setCilindroPickerOpen(false)}>
          <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Buscar Cilindro</Text>
              <Pressable onPress={() => setCilindroPickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <TextInput
              value={cilindroPickerBusca}
              onChangeText={(v) => { setCilindroPickerBusca(v); buscarCilindrosPicker(v); }}
              placeholder="Buscar por código, descrição ou grupo…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoFocus
              testID="cilindro-picker-busca"
            />
            {cilindroPickerBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
            <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
              {cilindroPickerResultados.map((c) => (
                <Pressable key={c.cod} onPress={() => selecionarCilindroPicker(c)} style={styles.gridRow} testID={`cilindro-picker-${c.cod}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText} numberOfLines={1}>{c.descricao || c.codigo}</Text>
                    <Text style={styles.hint}>{c.codigo} · Cap.{c.capacidade} · Pressão {c.pressao} · Padrão {c.padrao}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              {!cilindroPickerBuscando && cilindroPickerResultados.length === 0 ? <Text style={styles.hint}>Nenhum cilindro encontrado.</Text> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={fornecedorPickerOpen} transparent animationType="slide" onRequestClose={() => setFornecedorPickerOpen(false)}>
        <Pressable style={[styles.slideBg, isCompactWeb && styles.slideBgWebCompact]} onPress={() => setFornecedorPickerOpen(false)}>
          <Pressable style={[styles.slideCard, isCompactWeb && styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Buscar Fornecedor</Text>
              <Pressable onPress={() => setFornecedorPickerOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <TextInput
              value={fornecedorBusca}
              onChangeText={(v) => { setFornecedorBusca(v); buscarFornecedores(v); }}
              placeholder="Nome, fantasia ou código…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoFocus
              testID="fornecedor-picker-busca"
            />
            {fornecedorBuscando ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
            <ScrollView style={{ maxHeight: 420, marginTop: spacing.sm }} keyboardShouldPersistTaps="handled">
              {fornecedorResultados.map((f) => (
                <Pressable key={f.codigo_int} onPress={() => selecionarFornecedor(f)} style={styles.gridRow} testID={`fornecedor-picker-${f.codigo_int}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText} numberOfLines={1}>{f.nome}</Text>
                    <Text style={styles.hint}>{f.codigo}{f.fantasia ? ` · ${f.fantasia}` : ""}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={16} color={colors.muted} />
                </Pressable>
              ))}
              {!fornecedorBuscando && fornecedorResultados.length === 0 ? <Text style={styles.hint}>Nenhum fornecedor encontrado.</Text> : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, opacity: 0.75 },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 150 },
  colTiny: { width: 100 },
  colProduto: { width: 240 },
  colDescProduto: { width: 220 },
  switchInline: { paddingVertical: 11, alignItems: "flex-start" },

  toolbarRow: { flexDirection: "row", justifyContent: "flex-end", marginBottom: spacing.lg },
  secondaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  secondaryBtnText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  dangerBtn: { backgroundColor: colors.surface, borderColor: colors.error },
  dangerBtnText: { fontSize: 13, fontWeight: "600", color: colors.error },

  pickerBtn: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11 },
  pickerBtnText: { flex: 1, fontSize: 14, color: colors.onSurface },
  pillRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },
  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 110 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  slideCardTall: { maxHeight: "90%" },

  inputWithBtn: { flexDirection: "row", alignItems: "center", minWidth: 0 },
  searchBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.brandPrimary, marginLeft: 8 },
  gridRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 10, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: "transparent", marginBottom: 6 },
  gridRowText: { fontSize: 13, color: colors.onSurface },

  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  slideBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  slideCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  slideCardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  slideHeaderActions: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  headerSaveBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, minWidth: 76 },
  headerSaveBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  slideTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
});
