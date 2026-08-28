// "Gerar NFe" (NF-e Avulsa) — migração de `NFe\frmtranfe.frm`. Ver
// `backend/services/nfe_avulsa_service.py` e PENDENCIAS.md > "NF-e
// Avulsa" pro racional completo (achados da fonte, decisões de negócio
// confirmadas com o usuário). **Não confundir com "Manutenção de Notas
// Fiscais" (`notas-fiscais.tsx`)** — aquela é consulta/pós-emissão
// (DANFE/cancelar/carta de correção), essa tela nunca é tocada aqui.
//
// Fluxo: rascunho (`nf_aux`/`nf_aux_itens`) enquanto sendo digitado —
// ICMS/IPI/ISS por item são sugeridos via cascata de tributação mas
// livremente editáveis; PIS/COFINS nunca é digitável (calculado só na
// emissão). Ao Emitir, promove pra `n_fiscal`/`n_fiscal_itens` real.
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
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
import { fetchEmpresaHeader } from "@/src/utils/print-report-header";
import { printFullHtml } from "@/src/utils/printHtml";
import { buildDanfeHtml } from "@/src/utils/danfeFacsimile";
import { showApoioFiscalError } from "@/src/utils/apoioFiscal";
import ApoioFiscalBackOnModal, { ApoioFiscalInfo } from "@/src/components/ApoioFiscalBackOnModal";

type TipoMov = { codigo: string; descricao: string; origem_destino: string; cfop: string | null; cfop_fora: string | null };

type ItemRascunho = {
  codigo_int: string;
  descricao: string;
  qtd: string;
  p_unit: string;
  alqt_icms: string;
  base_icms: string;
  valor_icms: string;
  base_ipi: string;
  alqt_ipi: string;
  valor_ipi: string;
  base_iss: string;
  valor_iss: string;
  /** CFOP próprio do item — vazio usa o CFOP do cabeçalho na emissão
   * (`_emitir_nfe_avulsa_sync`, backend). Ver CLAUDE.md/PENDENCIAS.md >
   * "CFOP por item". */
  cod_fiscal: string;
};

const NFE_AVULSA_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Tipo de Movimentação",
    texto: "Define se a nota é de entrada ou saída e se a \"parte contrária\" é um Cliente ou um Fornecedor — escolha antes de buscar o destinatário.",
    icon: { lib: "ion", name: "swap-horizontal-outline" },
  },
  {
    titulo: "Impostos sugeridos",
    texto: "Ao adicionar um item, o sistema já sugere ICMS/IPI/ISS com base na tabela de Taxas — mas você pode digitar valores diferentes livremente antes de gravar.",
    icon: { lib: "ion", name: "calculator-outline" },
  },
  {
    titulo: "PIS/COFINS",
    texto: "PIS e COFINS não aparecem aqui para digitar — são calculados automaticamente só no momento de Emitir a nota.",
    icon: { lib: "ion", name: "information-circle-outline" },
  },
  {
    titulo: "Destinatário sem endereço",
    texto: "Toda NF-e exige o endereço completo do destinatário (comercial, se for empresa). Se faltar, a emissão é bloqueada até completar o cadastro.",
    icon: { lib: "ion", name: "alert-circle-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Emitir NF-e",
    texto: "Emite a NF-e real junto ao SEFAZ. Ação irreversível — depois de emitida, o rascunho não pode mais ser editado; para desfazer, é preciso cancelar o documento fiscal na tela de Manutenção de Notas Fiscais.",
    icon: { lib: "ion", name: "receipt-outline" },
    cor: colors.brandPrimary,
  },
  {
    titulo: "CFOP Item",
    texto: "CFOP próprio deste item — deixe em branco para usar o CFOP do cabeçalho da nota. Só preencha quando este item específico precisar de um CFOP diferente dos demais (ex.: devolução com itens de naturezas fiscais distintas).",
    icon: { lib: "ion", name: "git-branch-outline" },
  },
  {
    titulo: "Importar de...",
    texto: "Traz cabeçalho e itens de outro documento já existente (Pedido de Venda, Devolução, Pedido de Compra, Requisição, outra Nota Fiscal ou uma Comanda) pro rascunho, em vez de digitar tudo na mão. Alguns campos não vêm preenchidos (ex.: CFOP em Pedido/Compra) — sempre revise antes de gravar ou emitir.",
    icon: { lib: "ion", name: "download-outline" },
  },
  {
    titulo: "Frete por Conta",
    texto: "Define quem é responsável pelo transporte da mercadoria — vai direto no XML da NF-e (campo obrigatório do SEFAZ). Se não escolher nada, a nota sai como \"Emitente (CIF)\".",
    icon: { lib: "ion", name: "car-outline" },
  },
];

// 6 sub-rotinas de importação automática de `NFe\frmtranfe.frm` — ver
// PENDENCIAS.md > "6 sub-rotinas de importação automática" pro racional
// completo. `endpoint` bate com as rotas novas de
// `backend/routes/nfe_avulsa.py` (`POST /nfe-avulsa/importar/{endpoint}`).
const TIPOS_IMPORTACAO: { value: string; label: string; endpoint: string; placeholder: string }[] = [
  { value: "pedido", label: "Pedido de Venda", endpoint: "pedido", placeholder: "Nº do Pedido" },
  { value: "devolucao", label: "Devolução", endpoint: "devolucao", placeholder: "Nº da Devolução" },
  { value: "compra", label: "Pedido de Compra", endpoint: "compra", placeholder: "Nº do Pedido de Compra" },
  { value: "requisicao", label: "Requisição", endpoint: "requisicao", placeholder: "Nº da Requisição" },
  { value: "nota-fiscal", label: "Outra Nota Fiscal", endpoint: "nota-fiscal", placeholder: "Nº/Código da Nota Fiscal" },
  { value: "complementar", label: "Complementar (de Comanda)", endpoint: "complementar", placeholder: "Nº da Comanda" },
];

// "Frete por conta" — grava em n_fiscal.paga_frete (smallint), traduzido
// pro código real <modFrete> na emissão (ver
// nfe_emissao_service._resolver_mod_frete). Achado real 2026-08-21: o
// legado grava e usa esse valor de verdade (Grava_Frete/DAO_NFE.vb) —
// não é um campo decorativo.
const OPCOES_PAGA_FRETE: SelectOption[] = [
  { value: "1", label: "Emitente (CIF)" },
  { value: "2", label: "Destinatário (FOB)" },
  { value: "3", label: "Terceiros" },
  { value: "4", label: "Próprio Remetente" },
  { value: "5", label: "Próprio Destinatário" },
  { value: "6", label: "Sem Transporte" },
];

export default function NfeAvulsaScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ importar_devolucao_ids?: string }>();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gerar NFe está disponível apenas no web." testID="nfe-avulsa-web-only" />;
  }

  const canAbrir = can("NFE_AVULSA.ABRIR") || isMaster;
  const canGravar = can("NFE_AVULSA.GRAVAR") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [codigo, setCodigo] = useState<number | null>(null);
  // "1,2,3" — ids de `devolucao_itens` que originaram este rascunho, só
  // quando aberto a partir do Gestor de Devolução ("Emitir NF-e"). Ver
  // `nfe_avulsa_service._ensure_nf_aux_ids_devolucao_origem_col` — vai
  // junto em `salvarCabecalho()` e é lido de volta na emissão pra
  // atualizar `devolucao_itens.Nfe` com a nota real gerada.
  const [idsDevolucaoOrigem, setIdsDevolucaoOrigem] = useState("");
  const [promovida, setPromovida] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [emitindo, setEmitindo] = useState(false);
  const [ajudaVisivel, setAjudaVisivel] = useState(false);
  const [resultado, setResultado] = useState<{ chave_acesso: string; protocolo_sefaz: string; nota_fisc: number } | null>(null);
  const [apoioFiscalInfo, setApoioFiscalInfo] = useState<ApoioFiscalInfo | null>(null);
  const [baixandoDanfe, setBaixandoDanfe] = useState(false);

  const [tiposMov, setTiposMov] = useState<TipoMov[]>([]);
  const [mov, setMov] = useState<string | null>(null);
  const [cfop, setCfop] = useState("");
  const [dataEmissao, setDataEmissao] = useState<string | null>(null);
  const [dataMov, setDataMov] = useState<string | null>(null);
  const [frete, setFrete] = useState("");
  const [pagaFrete, setPagaFrete] = useState<string | null>(null);
  const [seguro, setSeguro] = useState("");
  const [despesas, setDespesas] = useState("");
  const [desconto, setDesconto] = useState("");
  // Só preenchidos pela importação "Complementar" (cobrança de FCP não
  // destacado na NFC-e original) — sem campo próprio na tela hoje, mas
  // precisam ser persistidos no cabeçalho pra não se perder ao salvar.
  const [baseFcp, setBaseFcp] = useState("");
  const [valorFcp, setValorFcp] = useState("");

  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [fornecedor, setFornecedor] = useState<FornecedorRow | null>(null);
  const [clienteSearchOpen, setClienteSearchOpen] = useState(false);
  const [clienteSearchTerm, setClienteSearchTerm] = useState("");
  const [clienteSearchLoading, setClienteSearchLoading] = useState(false);
  const [clienteSearchResults, setClienteSearchResults] = useState<ClienteRow[]>([]);
  const [fornSearchOpen, setFornSearchOpen] = useState(false);
  const [fornSearchTerm, setFornSearchTerm] = useState("");
  const [fornSearchLoading, setFornSearchLoading] = useState(false);
  const [fornSearchResults, setFornSearchResults] = useState<FornecedorRow[]>([]);

  const [itens, setItens] = useState<ItemRascunho[]>([]);
  const [produtoSearchOpen, setProdutoSearchOpen] = useState(false);
  const [produtoSearchTerm, setProdutoSearchTerm] = useState("");
  const [produtoSearchLoading, setProdutoSearchLoading] = useState(false);
  const [produtoSearchResults, setProdutoSearchResults] = useState<ProdutoRow[]>([]);

  const [importarOpen, setImportarOpen] = useState(false);
  const [importarTipo, setImportarTipo] = useState<string | null>(null);
  const [importarDocumento, setImportarDocumento] = useState("");
  const [importando, setImportando] = useState(false);

  const movSelecionado = tiposMov.find((t) => t.codigo === mov) || null;
  const isFornecedor = movSelecionado?.origem_destino === "F";
  const destinatarioNome = isFornecedor ? fornecedor?.nome : cliente?.nome;

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
        setTiposMov(j?.items || j || []);
      } catch {
        setTiposMov([]);
      }
      try {
        const r2 = await fetch(`${c.api.replace(/\/+$/, "")}/api/nfe-avulsa/novo`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: c.servidor, banco: c.banco, classe, master: isMaster }),
        });
        const j2 = await r2.json();
        if (j2?.success) setCodigo(j2.codigo);
        else fb.showError(friendlyApiError(j2, "Não foi possível iniciar o rascunho."));
      } catch (e) {
        fb.showError(friendlyCatchError(e));
      } finally {
        setCarregando(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const buscarClientes = useCallback(async (termo: string) => {
    const c = await ensureConn();
    if (!c) return;
    setClienteSearchLoading(true);
    try {
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&term=${encodeURIComponent(termo)}`;
      const r = await fetch(`${c.api.replace(/\/+$/, "")}/api/clientes/find/search?${qs}`);
      const j = await r.json();
      setClienteSearchResults(j?.items || []);
    } catch {
      setClienteSearchResults([]);
    } finally {
      setClienteSearchLoading(false);
    }
  }, [ensureConn]);

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

  const salvarCabecalho = async () => {
    const c = await ensureConn();
    if (!c || !codigo) return false;
    if (!destinatarioNome) { fb.showError("Selecione o Cliente/Fornecedor."); return false; }
    if (!mov) { fb.showError("Selecione o Tipo de Movimentação."); return false; }
    if (!cfop.trim()) { fb.showError("Informe o CFOP."); return false; }
    if (!dataEmissao) { fb.showError("Informe a Data de Emissão."); return false; }
    setSalvando(true);
    try {
      const dados = {
        fornecedor: isFornecedor ? Number(fornecedor?.codigo_int) : cliente?.codigo,
        mov, cfop: cfop.trim(), data: dataEmissao, data_mov: dataMov || dataEmissao,
        valor_total: valorTotalItens, frete: num(frete), seguro: num(seguro), despesas: num(despesas), desconto: num(desconto),
        BASE_FCP: num(baseFcp), VALOR_FCP: num(valorFcp),
        paga_frete: pagaFrete ? Number(pagaFrete) : null,
        ids_devolucao_origem: idsDevolucaoOrigem || null,
      };
      const r = await fetch(apiUrl("/api/nfe-avulsa/cabecalho"), {
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

  const salvarItens = async (lista: ItemRascunho[]) => {
    const c = await ensureConn();
    if (!c || !codigo) return false;
    try {
      const payload = lista.map((it) => ({
        codigo_int: it.codigo_int, qtd: num(it.qtd), p_unit: num(it.p_unit),
        valor_total: num(it.qtd) * num(it.p_unit),
        alqt_icms: num(it.alqt_icms), base_icms: num(it.base_icms), valor_icms: num(it.valor_icms),
        base_ipi: num(it.base_ipi), alqt_ipi: num(it.alqt_ipi), valor_ipi: num(it.valor_ipi),
        base_iss: num(it.base_iss), valor_iss: num(it.valor_iss),
        cod_fiscal: it.cod_fiscal?.trim() || null,
      }));
      const r = await fetch(apiUrl("/api/nfe-avulsa/itens"), {
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

  const selecionarProduto = async (p: ProdutoRow) => {
    setProdutoSearchOpen(false);
    const c = await ensureConn();
    let sugestao: any = null;
    if (c && mov) {
      try {
        const uf = isFornecedor ? "" : "";
        const r = await fetch(apiUrl("/api/nfe-avulsa/sugerir-tributacao"), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: c.servidor, banco: c.banco, codigo_int: p.codigo, mov, uf_destino: uf || "RJ",
            nao_contribuinte: true, simples_nacional_cliente: false, consumidor_final: !isFornecedor,
          }),
        });
        const j = await r.json();
        if (j?.success) sugestao = j.sugestao;
      } catch {
        sugestao = null;
      }
    }
    setItens((cur) => [...cur, {
      codigo_int: p.codigo, descricao: p.descricao, qtd: "1", p_unit: "0",
      alqt_icms: sugestao?.alqt_icms ? String(sugestao.alqt_icms) : "0",
      base_icms: "0", valor_icms: "0", base_ipi: "0", alqt_ipi: "0", valor_ipi: "0",
      base_iss: sugestao?.base_iss ? String(sugestao.base_iss) : "0", valor_iss: sugestao?.valor_iss ? String(sugestao.valor_iss) : "0",
      cod_fiscal: "",
    }]);
  };

  // 6 sub-rotinas de importação automática — endpoints são READ-ONLY (não
  // escrevem em `nf_aux`), só resolvem o documento de origem. O cabeçalho/
  // itens retornados são aplicados no estado local, exatamente como um
  // item adicionado manualmente (`selecionarProduto` acima) — usuário
  // revisa/ajusta e confirma com "Salvar Rascunho"/"Emitir" normalmente.
  // Compartilhada pelos dois pontos de entrada: modal manual
  // (`handleImportar`) e o atalho automático vindo do Gestor de Devolução
  // (`?importar_devolucao_ids=...`, ver useEffect logo abaixo).
  const aplicarImportacaoResposta = (c: Connection, j: any) => {
    const header = j.header || {};
    if (header.mov) setMov(header.mov);
    if (header.cfop) setCfop(header.cfop);
    if (header.BASE_FCP != null) setBaseFcp(String(header.BASE_FCP));
    if (header.VALOR_FCP != null) setValorFcp(String(header.VALOR_FCP));
    if (header.ids_devolucao_origem) setIdsDevolucaoOrigem(String(header.ids_devolucao_origem));

    const buscaDestinatario = (async () => {
      if (!(header.fornecedor && header.tipo_pessoa)) return;
      const base = c.api.replace(/\/+$/, "");
      const qsBase = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      if (header.tipo_pessoa === "F") {
        const rf = await fetch(`${base}/api/fornecedores?${qsBase}&search=${header.fornecedor}`);
        const jf = await rf.json();
        const found = (jf?.items || jf || [])[0];
        if (found) setFornecedor(found);
      } else {
        const rc = await fetch(`${base}/api/clientes/find/search?${qsBase}&term=${header.fornecedor}`);
        const jc = await rc.json();
        const found = (jc?.items || [])[0];
        if (found) setCliente(found);
      }
    })();

    const novosItens: ItemRascunho[] = (j.itens || []).map((it: any) => ({
      codigo_int: it.codigo_int, descricao: it.descricao || it.codigo_int,
      qtd: String(it.qtd ?? "0"), p_unit: String(it.p_unit ?? "0"),
      alqt_icms: String(it.alqt_icms ?? "0"), base_icms: String(it.base_icms ?? "0"), valor_icms: String(it.valor_icms ?? "0"),
      base_ipi: String(it.base_ipi ?? "0"), alqt_ipi: String(it.alqt_ipi ?? "0"), valor_ipi: String(it.valor_ipi ?? "0"),
      base_iss: String(it.base_iss ?? "0"), valor_iss: String(it.valor_iss ?? "0"),
      cod_fiscal: it.cod_fiscal ? String(it.cod_fiscal) : "",
    }));
    setItens((cur) => [...cur, ...novosItens]);
    return { itensImportados: novosItens.length, aguardaDestinatario: buscaDestinatario };
  };

  // Atalho vindo do Gestor de Devolução ("Emitir NF-e") — acionado 2026-08-24,
  // achado real (Leandro): "dentro do gestor de devolução quem chama a tela
  // gerar nfe avulsa, que já abre carregada com os dados da devolução, sem
  // o usuário precisar digitar manualmente". Roda uma única vez, assim que o
  // rascunho (`codigo`) e a conexão estão prontos — mesmo endpoint/lógica do
  // modal "Importar de..." manual, só sem exigir o usuário abrir o modal e
  // digitar o número.
  const autoImportouDevolucao = useRef(false);
  useEffect(() => {
    if (autoImportouDevolucao.current || !conn || !codigo || !params.importar_devolucao_ids) return;
    autoImportouDevolucao.current = true;
    const ids = params.importar_devolucao_ids.split(",").map((s) => parseInt(s, 10)).filter((n) => !isNaN(n));
    if (ids.length === 0) return;
    (async () => {
      setImportando(true);
      try {
        const r = await fetch(apiUrl("/api/nfe-avulsa/importar/devolucao"), {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ids_devolucao: ids }),
        });
        const j = await r.json();
        if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível carregar a devolução nesta NF-e.")); return; }
        const { itensImportados, aguardaDestinatario } = aplicarImportacaoResposta(conn, j);
        await aguardaDestinatario;
        fb.showSuccess(
          `Devolução importada — ${itensImportados} item(ns). Revise e emita a NF-e quando estiver pronto.`,
          undefined, 5000,
        );
      } catch (e) {
        fb.showError(friendlyCatchError(e));
      } finally {
        setImportando(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, codigo, params.importar_devolucao_ids]);

  const handleImportar = async () => {
    if (!importarTipo || !importarDocumento.trim()) {
      fb.showError("Escolha o tipo de documento e informe o número.");
      return;
    }
    const tipo = TIPOS_IMPORTACAO.find((t) => t.value === importarTipo);
    const c = await ensureConn();
    if (!c || !tipo) return;
    setImportando(true);
    try {
      const corpo = tipo.value === "devolucao"
        ? { servidor: c.servidor, banco: c.banco, ids_devolucao: [Number(importarDocumento)] }
        : { servidor: c.servidor, banco: c.banco, documento: Number(importarDocumento) };
      const r = await fetch(apiUrl(`/api/nfe-avulsa/importar/${tipo.endpoint}`), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpo),
      });
      const j = await r.json();
      if (!j?.success) { fb.showError(friendlyApiError(j, "Não foi possível importar este documento.")); return; }

      const { itensImportados, aguardaDestinatario } = aplicarImportacaoResposta(c, j);
      await aguardaDestinatario;
      fb.showSuccess(`${itensImportados} item(ns) importado(s) — revise os dados antes de salvar.`, undefined, 5000);
      setImportarOpen(false);
      setImportarTipo(null);
      setImportarDocumento("");
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setImportando(false);
    }
  };

  const atualizarItem = (idx: number, campo: keyof ItemRascunho, valor: string) => {
    setItens((cur) => cur.map((it, i) => (i === idx ? { ...it, [campo]: valor } : it)));
  };

  const removerItem = (idx: number) => {
    setItens((cur) => cur.filter((_, i) => i !== idx));
  };

  const gravarRascunho = async () => {
    const okCab = await salvarCabecalho();
    if (!okCab) return;
    if (itens.length > 0) {
      const okItens = await salvarItens(itens);
      if (!okItens) return;
    }
    fb.showSuccess("Rascunho gravado.");
  };

  const emitir = async () => {
    const c = await ensureConn();
    if (!c || !codigo) return;
    const okCab = await salvarCabecalho();
    if (!okCab) return;
    if (itens.length === 0) { fb.showError("Lance ao menos um item antes de emitir."); return; }
    const okItens = await salvarItens(itens);
    if (!okItens) return;

    setEmitindo(true);
    try {
      const body = {
        servidor: c.servidor, banco: c.banco, codigo,
        usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
      };
      const r = await fetch(apiUrl("/api/nfe-avulsa/emitir"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "NF-e avulsa emitida.", undefined, 5000);
        setResultado({ chave_acesso: j.chave_acesso, protocolo_sefaz: j.protocolo_sefaz, nota_fisc: j.nota_fisc });
        setPromovida(true);
      } else {
        const info = showApoioFiscalError(fb, j, "Não foi possível emitir a NF-e.", 5000);
        if (info) setApoioFiscalInfo(info);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setEmitindo(false);
    }
  };

  const baixarDanfe = async () => {
    if (!conn || !resultado?.nota_fisc) return;
    setBaixandoDanfe(true);
    try {
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(apiUrl(`/api/notas-fiscais/${resultado.nota_fisc}/danfe?${qs}`));
      const j = await r.json();
      if (!j?.success) { fb.showWarning(friendlyApiError(j, "Não foi possível gerar o DANFE.")); return; }
      const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
      printFullHtml(buildDanfeHtml(empresa, j.detalhe, j.modelo_danfe));
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setBaixandoDanfe(false);
    }
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Gerar NFe." testID="nfe-avulsa-no-perm" />;
  }

  const opcoesMov: SelectOption[] = tiposMov.map((t) => ({ value: t.codigo, label: `${t.codigo} — ${t.descricao}` }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="nfe-avulsa-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Gerar NFe</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
          size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="nfe-avulsa-ajuda"
        />
      </View>

      {carregando ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      ) : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            {promovida ? (
              <View style={[styles.card, { backgroundColor: colors.surfaceSecondary }]}>
                <Text style={styles.hint}>Esta NF-e já foi emitida — o rascunho não pode mais ser editado nesta fase.</Text>
              </View>
            ) : null}

            <View style={styles.card}>
              <AccordionSection title="Cabeçalho" defaultExpanded testID="nfe-avulsa-cabecalho-section">
                <View style={styles.fieldsRow}>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Tipo de Movimentação</Text>
                    <SelectField
                      value={mov} onChange={(v) => setMov(v as string)} options={opcoesMov}
                      compactWeb placeholder="Selecione" disabled={promovida} testID="nfe-avulsa-mov"
                    />
                  </View>
                  <View style={styles.colNarrow}>
                    <Text style={styles.fieldLabel}>CFOP</Text>
                    <TextInput value={cfop} onChangeText={setCfop} editable={!promovida} style={styles.input} testID="nfe-avulsa-cfop" />
                  </View>
                </View>

                <Text style={styles.fieldLabel}>{isFornecedor ? "Fornecedor" : "Cliente"}</Text>
                {destinatarioNome ? (
                  <View style={styles.clienteRow}>
                    <Ionicons name="person-circle-outline" size={22} color={colors.brandPrimary} />
                    <Text style={styles.clienteNome} numberOfLines={1}>{destinatarioNome}</Text>
                    {!promovida ? (
                      <Pressable onPress={() => (isFornecedor ? setFornSearchOpen(true) : setClienteSearchOpen(true))} testID="nfe-avulsa-trocar-destinatario">
                        <Text style={styles.trocarText}>Trocar</Text>
                      </Pressable>
                    ) : null}
                  </View>
                ) : (
                  <Pressable
                    onPress={() => mov && (isFornecedor ? setFornSearchOpen(true) : setClienteSearchOpen(true))}
                    style={[styles.selecionarBtn, !mov && { opacity: 0.5 }]}
                    disabled={!mov || promovida}
                    testID="nfe-avulsa-selecionar-destinatario"
                  >
                    <Ionicons name="search" size={18} color="#fff" />
                    <Text style={styles.selecionarBtnText}>{mov ? `Selecionar ${isFornecedor ? "Fornecedor" : "Cliente"}` : "Escolha o Tipo de Movimentação primeiro"}</Text>
                  </Pressable>
                )}

                <View style={styles.fieldsRow}>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Data de Emissão</Text>
                    <WebDateField value={dataEmissao} onChange={(v) => { setDataEmissao(v); if (v) setDataMov(v); }} testID="nfe-avulsa-data-emissao" />
                  </View>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Data de Movimento</Text>
                    <WebDateField value={dataMov} onChange={setDataMov} testID="nfe-avulsa-data-mov" />
                  </View>
                </View>

                <View style={styles.fieldsRow}>
                  <View style={styles.colTiny}>
                    <Text style={styles.fieldLabel}>Frete</Text>
                    <TextInput value={frete} onChangeText={setFrete} keyboardType="numeric" editable={!promovida} style={styles.input} />
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

                <View style={styles.fieldsRow}>
                  <View style={styles.colHalf}>
                    <Text style={styles.fieldLabel}>Frete por Conta</Text>
                    <SelectField
                      value={pagaFrete} onChange={(v) => setPagaFrete(v as string)} options={OPCOES_PAGA_FRETE}
                      compactWeb placeholder="Emitente (CIF)" disabled={promovida} testID="nfe-avulsa-paga-frete"
                    />
                  </View>
                </View>
              </AccordionSection>
            </View>

            <View style={styles.card}>
              <View style={styles.itensHeaderRow}>
                <Text style={styles.sectionTitle}>Itens</Text>
                {!promovida ? (
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <Pressable onPress={() => setImportarOpen(true)} style={styles.secondaryBtn} testID="nfe-avulsa-importar">
                      <Text style={styles.secondaryBtnText}>Importar de...</Text>
                    </Pressable>
                    <Pressable onPress={() => setProdutoSearchOpen(true)} style={styles.addItemBtn} testID="nfe-avulsa-add-item" disabled={!mov}>
                      <Ionicons name="add" size={16} color="#fff" />
                      <Text style={styles.addItemBtnText}>Item</Text>
                    </Pressable>
                  </View>
                ) : null}
              </View>
              {itens.length === 0 ? (
                <Text style={styles.hint}>Nenhum item lançado.</Text>
              ) : (
                itens.map((it, idx) => (
                  <View key={`${it.codigo_int}-${idx}`} style={styles.itemCard} testID={`nfe-avulsa-item-${idx}`}>
                    <View style={styles.itemHeaderRow}>
                      <Text style={styles.itemDescricao} numberOfLines={1}>{it.codigo_int} — {it.descricao}</Text>
                      {!promovida ? (
                        <Pressable onPress={() => removerItem(idx)} hitSlop={8}>
                          <Ionicons name="trash-outline" size={16} color={colors.error} />
                        </Pressable>
                      ) : null}
                    </View>
                    <View style={styles.fieldsRow}>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Qtd.</Text>
                        <TextInput value={it.qtd} onChangeText={(v) => atualizarItem(idx, "qtd", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor Unit.</Text>
                        <TextInput value={it.p_unit} onChangeText={(v) => atualizarItem(idx, "p_unit", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Alq. ICMS</Text>
                        <TextInput value={it.alqt_icms} onChangeText={(v) => atualizarItem(idx, "alqt_icms", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor ICMS</Text>
                        <TextInput value={it.valor_icms} onChangeText={(v) => atualizarItem(idx, "valor_icms", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>CFOP Item</Text>
                        <TextInput
                          value={it.cod_fiscal}
                          onChangeText={(v) => atualizarItem(idx, "cod_fiscal", v)}
                          placeholder={cfop || "cabeçalho"}
                          placeholderTextColor={colors.muted}
                          editable={!promovida}
                          style={styles.input}
                          testID={`nfe-avulsa-item-cfop-${idx}`}
                        />
                      </View>
                    </View>
                    <View style={styles.fieldsRow}>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Alq. IPI</Text>
                        <TextInput value={it.alqt_ipi} onChangeText={(v) => atualizarItem(idx, "alqt_ipi", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor IPI</Text>
                        <TextInput value={it.valor_ipi} onChangeText={(v) => atualizarItem(idx, "valor_ipi", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Valor ISS</Text>
                        <TextInput value={it.valor_iss} onChangeText={(v) => atualizarItem(idx, "valor_iss", v)} keyboardType="numeric" editable={!promovida} style={styles.input} />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.fieldLabel}>Total Item</Text>
                        <Text style={styles.itemTotalValor}>{formatBRL(num(it.qtd) * num(it.p_unit))}</Text>
                      </View>
                    </View>
                  </View>
                ))
              )}
              <Text style={[styles.hint, { marginTop: spacing.sm }]}>PIS/COFINS não é digitado aqui — calculado automaticamente ao Emitir.</Text>
            </View>

            {!promovida ? (
              <View style={styles.bulkBar} testID="nfe-avulsa-bulk-bar">
                <View>
                  <Text style={styles.bulkBarLabel}>{itens.length} item{itens.length === 1 ? "" : "s"}</Text>
                  <Text style={styles.hint}>Total: {formatBRL(valorTotalItens)}</Text>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Pressable onPress={gravarRascunho} disabled={salvando} style={styles.secondaryBtn}>
                    {salvando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Text style={styles.secondaryBtnText}>Salvar Rascunho</Text>}
                  </Pressable>
                  {canGravar ? (
                    <Pressable onPress={emitir} disabled={emitindo} style={styles.bulkBtn} testID="nfe-avulsa-emitir">
                      {emitindo ? <ActivityIndicator color="#fff" size="small" /> : (
                        <><Ionicons name="receipt-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Emitir NF-e</Text></>
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
              <Text style={styles.modalTitle}>NF-e emitida</Text>
              <Pressable onPress={() => setResultado(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>Nota fiscal nº {resultado?.nota_fisc}</Text>
            <Text style={styles.hint}>Protocolo SEFAZ: {resultado?.protocolo_sefaz}</Text>
            <Text style={[styles.hint, { marginTop: spacing.sm }]}>Chave de acesso:</Text>
            <Text selectable style={styles.chaveAcesso}>{resultado?.chave_acesso}</Text>
            <Pressable onPress={baixarDanfe} disabled={baixandoDanfe} style={[styles.bulkBtn, { marginTop: spacing.md, alignSelf: "flex-start" }, baixandoDanfe && { opacity: 0.7 }]} testID="nfe-avulsa-danfe">
              {baixandoDanfe ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.bulkBtnText}>Baixar DANFE</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={importarOpen} transparent animationType="fade" onRequestClose={() => setImportarOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setImportarOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Importar de...</Text>
              <Pressable onPress={() => setImportarOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={[styles.hint, { marginBottom: spacing.sm }]}>
              Importa cabeçalho/itens de outro documento já existente pro rascunho — revise tudo antes de gravar.
            </Text>
            <Text style={styles.fieldLabel}>Tipo de Documento</Text>
            <SelectField
              value={importarTipo}
              onChange={(v) => setImportarTipo(v as string)}
              options={TIPOS_IMPORTACAO.map((t) => ({ value: t.value, label: t.label }))}
              compactWeb
              testID="nfe-avulsa-importar-tipo"
            />
            <Text style={[styles.fieldLabel, { marginTop: spacing.sm }]}>
              {TIPOS_IMPORTACAO.find((t) => t.value === importarTipo)?.placeholder || "Número do Documento"}
            </Text>
            <TextInput
              value={importarDocumento}
              onChangeText={setImportarDocumento}
              keyboardType="numeric"
              style={styles.input}
              placeholderTextColor={colors.muted}
              testID="nfe-avulsa-importar-documento"
            />
            <Pressable
              onPress={handleImportar}
              disabled={importando}
              style={[styles.bulkBtn, { marginTop: spacing.md, alignSelf: "flex-start" }, importando && { opacity: 0.7 }]}
              testID="nfe-avulsa-importar-confirmar"
            >
              {importando ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.bulkBtnText}>Importar</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>

      <ClientSearchModal
        visible={clienteSearchOpen}
        onClose={() => setClienteSearchOpen(false)}
        term={clienteSearchTerm}
        setTerm={(v) => { setClienteSearchTerm(v); buscarClientes(v); }}
        loading={clienteSearchLoading}
        results={clienteSearchResults}
        onPick={(c) => { setCliente(c); setClienteSearchOpen(false); }}
        onCreate={() => setClienteSearchOpen(false)}
      />

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

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Gerar NFe (NF-e Avulsa)" itens={NFE_AVULSA_AJUDA_ITENS} />
      <ApoioFiscalBackOnModal visible={!!apoioFiscalInfo} info={apoioFiscalInfo} onClose={() => setApoioFiscalInfo(null)} />
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
  colTiny: { width: 96 },
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
  itemHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 4 },
  itemDescricao: { flex: 1, fontSize: 13, fontWeight: "600", color: colors.onSurface },

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
  chaveAcesso: { fontSize: 12, color: colors.onSurface, fontFamily: Platform.OS === "web" ? "monospace" : undefined, marginTop: 4, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.sm },
});
