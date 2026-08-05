// Checkout — venda direta de balcão (migração de FrmPafOFF.frm, "Emissão de
// Cupom Fiscal"/PDV). Fase 1 (núcleo) + Fase 2 (importar Pedido/O.S. como
// DAV) — ver PENDENCIAS.md > "Checkout" pro que ainda falta (TEF real,
// abastecimento de posto, agenda, venda externa por ficha, emissão fiscal
// automática — que já existe separada no Gestor de Comandas).
//
// Web-only por enquanto (mesmo padrão de "Pedido Geral"/"O.S. Completa") —
// tela nova de back-office, sem versão mobile simplificada nesta fase.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ActivityIndicator, Platform, Pressable, ScrollView, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, fmtNum } from "@/src/utils/format";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { styles as ps } from "@/src/components/pedido/styles";
import PedidoHeader from "@/src/components/pedido/PedidoHeader";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { ClienteRow } from "@/src/components/pedido/types";
import FecharVendaModal, { FormaPagamentoLancada } from "@/src/components/checkout/FecharVendaModal";
import ImportarDavModal from "@/src/components/checkout/ImportarDavModal";
import ConfiguracaoImpressaoModal from "@/src/components/checkout/ConfiguracaoImpressaoModal";
import DemonstrativoCupomFiscal from "@/src/components/checkout/DemonstrativoCupomFiscal";
import { buildReciboTexto } from "@/src/utils/reciboTexto";
import {
  ImpressaoSilenciosaConfig, clearImpressaoSilenciosaConfig, impressaoSilenciosaKey,
  loadImpressaoSilenciosaConfig, saveImpressaoSilenciosaConfig,
} from "@/src/utils/storage/impressaoSilenciosa";

const isWeb = Platform.OS === "web";

type ItemRow = {
  id_mov: number;
  codigo: string;
  descricao: string;
  qtd: number;
  p_unit: number;
  preco_bruto: number;
  total: number;
  desconto_unit: number;
  acrescimo_unit: number;
  // "P" (Pedido) ou "O" (O.S.) quando o item veio de uma importação de DAV
  // — esses itens não podem ser cancelados individualmente (ver
  // checkout_service._cancelar_item_sync).
  origemDav: string | null;
};

type FormaPagRow = { descricao: string; forma_pag: string; valor: number };

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "Nova Venda", texto: "Abre sozinha assim que a tela carrega (sem precisar de um Pedido/O.S. prévio nem de clicar em nada) — depois de Fechar ou Cancelar uma venda, a próxima já abre automaticamente também.", icon: { lib: "ion", name: "add-circle-outline" } },
  { titulo: "Bipar ou Digitar Produto", texto: "Campo pronto pro leitor de código de barras — bipe e o item já entra na venda direto, sem precisar do mouse. Pra digitar quantidade ou desconto diferentes do padrão (1 e 0%), use Tab antes de bipar/pressionar Enter.", icon: { lib: "ion", name: "add" } },
  { titulo: "Importar Pedido/O.S.", texto: "Traz os itens de um Pedido de Venda ou O.S. já Fechado pra dentro desta venda. O documento de origem é marcado como Faturado, e os itens importados não podem ser cancelados individualmente aqui.", icon: { lib: "ion", name: "download-outline" } },
  { titulo: "Cancelar item (✕ na linha)", texto: "Remove o item da venda e devolve a quantidade ao estoque. Só disponível pra itens lançados diretamente — itens de um Pedido/O.S. importado só saem cancelando a venda inteira.", icon: { lib: "ion", name: "close-circle-outline" }, cor: colors.error },
  { titulo: "Desconto Geral", texto: "Aplica um percentual de desconto sobre o total da venda, distribuído entre todos os itens.", icon: { lib: "ion", name: "pricetag-outline" } },
  { titulo: "Cliente", texto: "Vincula um cliente à venda. Sem cliente definido, a venda fica em nome de \"Clientes Diversos\".", icon: { lib: "ion", name: "person-outline" } },
  { titulo: "Fechar Venda", texto: "Lança uma ou mais formas de pagamento (Dinheiro, Cheque, Cartão, etc.) e finaliza a venda. Calcula o troco automaticamente quando o valor pago é maior que o total. O cupom é impresso automaticamente nesse momento, sem precisar de nenhum botão — igual ao sistema antigo — desde que a impressão desta estação esteja configurada.", icon: { lib: "ion", name: "cash-outline" }, cor: colors.brandPrimary },
  { titulo: "Cancelar Venda", texto: "Cancela a venda inteira, antes de fechada — devolve todo o estoque. Ação definitiva.", icon: { lib: "ion", name: "trash-outline" }, cor: colors.error },
  { titulo: "Configurar Impressão (⚙ no cabeçalho)", texto: "Define o computador e a impressora desta estação (precisa do Agente de Impressão instalado na máquina). Configurado, o cupom é impresso sozinho ao Fechar a Venda, sem diálogo nenhum. Só aparece pra Gerente, Supervisor ou Master.", icon: { lib: "ion", name: "settings-outline" } },
];

export default function CheckoutScreen() {
  const router = useRouter();
  const { can, isMaster, isManagerFuncao, classe } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [vendedor, setVendedor] = useState<number | null>(null);
  const [funcaoCod, setFuncaoCod] = useState<number>(3);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);

  const [comanda, setComanda] = useState<number | null>(null);
  const [situacao, setSituacao] = useState<string>("A");
  const [itens, setItens] = useState<ItemRow[]>([]);
  const [valorVenda, setValorVenda] = useState(0);
  const [clienteNome, setClienteNome] = useState("");
  const [clienteCodigo, setClienteCodigo] = useState<number | null>(null);
  const [clienteCgcCpf, setClienteCgcCpf] = useState("");
  const [atendenteNome, setAtendenteNome] = useState("");
  const [vendaData, setVendaData] = useState<string | null>(null);
  const [formasPagamento, setFormasPagamento] = useState<FormaPagRow[]>([]);
  const [troco, setTroco] = useState(0);

  const [abrindo, setAbrindo] = useState(false);
  const [codigoInput, setCodigoInput] = useState("");
  const [qtdInput, setQtdInput] = useState("1");
  const [descontoItemPct, setDescontoItemPct] = useState("0");
  const [addingItem, setAddingItem] = useState(false);
  const [preview, setPreview] = useState<{
    descricao: string; preco: number; desc_v: number; desc_s: number; desc_g: number;
    unidade: string | null; estoque: number | null;
  } | null>(null);

  // Operação 100% por teclado/leitor de código de barras — nunca precisa do
  // mouse pra navegar entre os campos. O leitor "digita" o código e manda um
  // Enter sozinho: Enter no campo Código já busca E inclui o item na venda
  // (assumindo Qtd/Desc já preenchidos, padrão 1/0%), e o foco volta pro
  // próprio campo Código em seguida — pronto pro próximo bipe. Tab/Enter nos
  // campos Qtd/Desconto só serve pra quem quer AJUSTAR esses valores antes
  // de bipar (ex.: digitar Qtd=3 primeiro, depois bipar o código).
  const codigoRef = useRef<TextInput>(null);
  const qtdRef = useRef<TextInput>(null);
  const descRef = useRef<TextInput>(null);

  const [descGeralOpen, setDescGeralOpen] = useState(false);
  const [descGeralPct, setDescGeralPct] = useState("0");
  const [descGeralSaving, setDescGeralSaving] = useState(false);

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const [fecharOpen, setFecharOpen] = useState(false);
  const [importarOpen, setImportarOpen] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [configImpressaoOpen, setConfigImpressaoOpen] = useState(false);
  const [impressaoConfig, setImpressaoConfig] = useState<ImpressaoSilenciosaConfig | null>(null);

  const [toast, setToast] = useState<{ msg: string; tone: "success" | "error" | "info" } | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: "success" | "error" | "info" = "info", durationMs = 1800) => {
    setToast({ msg: m, tone: t });
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), durationMs);
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number" ? cod : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      setVendedor(vCod);
      const master = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(master ? -2 : (typeof vCod === "number" ? vCod : -2));
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = cf ? parseInt(cf, 10) : NaN;
      setFuncaoCod(master ? 1 : (Number.isFinite(fc) && fc > 0 ? fc : 3));
      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (!conn) return;
    (async () => {
      const cfg = await loadImpressaoSilenciosaConfig(impressaoSilenciosaKey(conn.empresa, conn.banco));
      setImpressaoConfig(cfg);
    })();
  }, [conn]);

  const salvarConfigImpressao = useCallback(async (cfg: ImpressaoSilenciosaConfig) => {
    if (!conn) return;
    await saveImpressaoSilenciosaConfig(impressaoSilenciosaKey(conn.empresa, conn.banco), cfg);
    setImpressaoConfig(cfg);
    showToast("Impressão silenciosa configurada nesta estação.", "success");
  }, [conn, showToast]);

  const removerConfigImpressao = useCallback(async () => {
    if (!conn) return;
    await clearImpressaoSilenciosaConfig(impressaoSilenciosaKey(conn.empresa, conn.banco));
    setImpressaoConfig(null);
    showToast("Impressão silenciosa desativada — configure novamente para voltar a imprimir automaticamente.", "info");
  }, [conn, showToast]);

  const reloadVenda = useCallback(async (cmd: number) => {
    if (!conn) return;
    try {
      const j = await apiGet(conn, `/api/checkout/${cmd}`);
      if (j?.success) {
        setSituacao(j.situacao);
        setValorVenda(j.valor_venda || 0);
        setClienteNome(j.cliente_nome || "");
        setClienteCodigo(j.cliente ?? null);
        setClienteCgcCpf(j.cliente_cgc_cpf || "");
        setAtendenteNome(j.atendente_nome || "");
        setVendaData(j.data ?? null);
        setFormasPagamento(j.formas_pagamento || []);
        setTroco(j.troco || 0);
        setItens((j.itens || []).map((it: any) => ({
          id_mov: it.id_mov, codigo: it.codigo, descricao: it.descricao, qtd: it.qtd,
          p_unit: it.p_unit, preco_bruto: it.preco_bruto, total: it.total,
          desconto_unit: it.desconto_unit, acrescimo_unit: it.acrescimo_unit,
          origemDav: it.origem_dav ?? null,
        })));
      }
    } catch (e) {
      showToast(friendlyCatchError(e), "error");
    }
  }, [conn, showToast]);

  const abrirVenda = useCallback(async () => {
    if (!conn || !vendedor) return;
    setAbrindo(true);
    try {
      const j = await apiSend(conn, "/api/checkout/abrir", "POST", {
        atendente: vendedor, master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        setComanda(j.comanda);
        setSituacao("A");
        setItens([]);
        setValorVenda(0);
        setClienteNome("");
        setClienteCodigo(null);
      } else {
        showToast(friendlyApiError(j, "Não foi possível abrir a venda."), "error");
      }
    } catch (e) {
      showToast(friendlyCatchError(e), "error");
    } finally {
      setAbrindo(false);
    }
  }, [conn, vendedor, isMaster, classe, usuarioCod, showToast]);

  // Abre a venda sozinho assim que a tela carrega — "ao clicar no card
  // Checkout, tem que abrir direto a tela" (pedido explícito do usuário).
  // Nenhuma tela intermediária de "Nenhuma venda em andamento" esperando
  // clique — dispara de novo automaticamente sempre que `comanda` volta a
  // ficar nulo (venda cancelada, ou "Nova Venda" após fechar).
  useEffect(() => {
    if (loading || !conn || !vendedor || comanda || abrindo) return;
    if (!can("CHECKOUT.ABRIR")) return;
    abrirVenda();
  }, [loading, conn, vendedor, comanda, abrindo, can, abrirVenda]);

  // Autofoca o campo Código sempre que uma venda aberta fica pronta pra
  // receber itens — cobre tanto a abertura inicial quanto o retorno ao
  // campo depois de qualquer modal (Cliente, Fechar Venda, etc.) fechar.
  useEffect(() => {
    if (comanda && situacao === "A") {
      codigoRef.current?.focus();
    }
  }, [comanda, situacao]);

  const buscarPreview = useCallback(async () => {
    const codigo = codigoInput.trim();
    if (!codigo || !conn) { setPreview(null); return; }
    const qtd = parseFloat(qtdInput.replace(",", ".")) || 1;
    try {
      const j = await apiGet(conn, "/api/checkout/produto", { codigo, qtd });
      if (j?.success) {
        setPreview({
          descricao: j.descricao, preco: j.preco, desc_v: j.desc_v, desc_s: j.desc_s, desc_g: j.desc_g,
          unidade: j.unidade ?? null, estoque: j.estoque ?? null,
        });
      } else {
        setPreview(null);
        showToast(friendlyApiError(j, "Produto não encontrado."), "error");
      }
    } catch (e) {
      setPreview(null);
      showToast(friendlyCatchError(e), "error");
    }
  }, [codigoInput, qtdInput, conn, showToast]);

  const adicionarItem = useCallback(async () => {
    if (!conn || !comanda) return;
    const codigo = codigoInput.trim();
    if (!codigo) return;
    setAddingItem(true);
    try {
      const j = await apiSend(conn, `/api/checkout/${comanda}/itens`, "POST", {
        codigo,
        qtd: parseFloat(qtdInput.replace(",", ".")) || 1,
        vendedor,
        funcao: funcaoCod,
        desconto_percentual: parseFloat(descontoItemPct.replace(",", ".")) || 0,
        master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        setCodigoInput(""); setQtdInput("1"); setDescontoItemPct("0"); setPreview(null);
        await reloadVenda(comanda);
        showToast("Item incluído.", "success");
        // Refoca o campo Código pro próximo bipe/digitação — sem isso, o
        // operador teria que clicar de volta no campo a cada item (quebra
        // o fluxo 100% teclado/leitor de código de barras).
        codigoRef.current?.focus();
      } else {
        showToast(friendlyApiError(j, "Não foi possível incluir o item."), "error");
      }
    } catch (e) {
      showToast(friendlyCatchError(e), "error");
    } finally {
      setAddingItem(false);
    }
  }, [conn, comanda, codigoInput, qtdInput, vendedor, funcaoCod, descontoItemPct, isMaster, classe, usuarioCod, reloadVenda, showToast]);

  const cancelarItem = useCallback((id_mov: number) => {
    if (!conn || !comanda) return;
    feedback.showConfirm("Cancelar este item da venda?", async () => {
      try {
        const j = await apiSend(conn, `/api/checkout/${comanda}/itens/${id_mov}`, "DELETE", {
          master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
        });
        if (j?.success) {
          await reloadVenda(comanda);
          showToast("Item cancelado.", "success");
        } else {
          showToast(friendlyApiError(j, "Não foi possível cancelar o item."), "error");
        }
      } catch (e) {
        showToast(friendlyCatchError(e), "error");
      }
    });
  }, [conn, comanda, isMaster, classe, usuarioCod, reloadVenda, showToast, feedback]);

  const aplicarDescontoGeral = useCallback(async () => {
    if (!conn || !comanda) return;
    const pct = parseFloat(descGeralPct.replace(",", ".")) || 0;
    if (pct <= 0) { showToast("Informe um percentual maior que zero.", "error"); return; }
    setDescGeralSaving(true);
    try {
      const j = await apiSend(conn, `/api/checkout/${comanda}/desconto-geral`, "POST", {
        desconto_percentual: pct, funcao: funcaoCod, master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        setDescGeralOpen(false); setDescGeralPct("0");
        await reloadVenda(comanda);
        showToast("Desconto geral aplicado.", "success");
      } else {
        showToast(friendlyApiError(j, "Não foi possível aplicar o desconto."), "error");
      }
    } catch (e) {
      showToast(friendlyCatchError(e), "error");
    } finally {
      setDescGeralSaving(false);
    }
  }, [conn, comanda, descGeralPct, funcaoCod, isMaster, classe, usuarioCod, reloadVenda, showToast]);

  const importarDav = useCallback(async (tipoDav: string, documento: number) => {
    if (!conn || !comanda) return { success: false, message: "Venda não encontrada." };
    try {
      const j = await apiSend(conn, `/api/checkout/${comanda}/importar-dav`, "POST", {
        tipo_dav: tipoDav, documento, master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        await reloadVenda(comanda);
        setImportarOpen(false);
        showToast(`${j.itens_importados} item(ns) importado(s).`, "success");
      }
      return j;
    } catch (e) {
      return { success: false, message: friendlyCatchError(e) };
    }
  }, [conn, comanda, isMaster, classe, usuarioCod, reloadVenda, showToast]);

  useEffect(() => {
    if (!searchOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term: searchTerm });
        setSearchResults(j?.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, searchOpen, conn]);

  const definirCliente = useCallback(async (c: ClienteRow | null) => {
    if (!conn || !comanda) return;
    try {
      const j = await apiSend(conn, `/api/checkout/${comanda}/cliente`, "PUT", {
        cliente: c?.codigo ?? null, usuario_alteracao: usuarioCod, classe, plataforma: "web",
      });
      if (j?.success) {
        setClienteNome(c?.nome || "");
        setClienteCodigo(c?.codigo ?? null);
        setSearchOpen(false);
      } else {
        showToast(friendlyApiError(j, "Não foi possível definir o cliente."), "error");
      }
    } catch (e) {
      showToast(friendlyCatchError(e), "error");
    }
  }, [conn, comanda, usuarioCod, classe, showToast]);

  // Imprime o comprovante da venda de forma automática/silenciosa ao final
  // do fechamento — assim como acontece no legado (`Imprime_Comprovante`
  // era chamada direto ao fechar a venda, sem botão manual de "Imprimir").
  // Busca o estado FINAL da venda direto da API (não do state local, que
  // ainda não refletiu o resultado do fechar no mesmo tick) — devolve só o
  // texto complementar pro toast de "Venda fechada", nunca lança exceção.
  const imprimirVendaAutomatico = useCallback(async (cmd: number): Promise<string> => {
    if (!conn) return "";
    if (!impressaoConfig) {
      return "Configure a impressão desta estação (ícone ⚙ no cabeçalho) para imprimir automaticamente.";
    }
    try {
      const [jv, je, jm] = await Promise.all([
        apiGet(conn, `/api/checkout/${cmd}`),
        apiGet(conn, "/api/controle/empresa").catch(() => null),
        apiGet(conn, "/api/controle/mensagens-pdv").catch(() => null),
      ]);
      if (!jv?.success) return "Não foi possível gerar o cupom.";
      const conteudo = buildReciboTexto(je?.success ? je : null, {
        titulo: `COMANDA Nº ${cmd}`,
        itens: (jv.itens || []).map((it: any) => ({
          descricao: it.descricao, qtd: it.qtd, p_unit: it.p_unit, preco_bruto: it.preco_bruto, total: it.total,
        })),
        valorTotal: jv.valor_venda || 0,
        formasPagamento: jv.formas_pagamento || [],
        troco: jv.troco || 0,
        clienteNome: jv.cliente_nome || "",
        clienteCgcCpf: jv.cliente_cgc_cpf || "",
        atendenteNome: jv.atendente_nome || "",
        data: jv.data ?? null,
        mensagens: jm?.success ? (jm.linhas || []) : [],
      });
      const j = await apiSend(conn, "/api/impressao/fila", "POST", {
        servidor: conn.servidor, banco: conn.banco,
        computador: impressaoConfig.computador, impressora: impressaoConfig.impressora,
        conteudo, tipo: "TEXTO",
        usuario_alteracao: usuarioCod, classe, plataforma: "web",
      });
      return j?.success ? "Cupom enviado para impressão." : `Impressão falhou: ${friendlyApiError(j, "erro desconhecido")}`;
    } catch (e) {
      return `Impressão falhou: ${friendlyCatchError(e)}`;
    }
  }, [conn, impressaoConfig, usuarioCod, classe]);

  const fecharVenda = useCallback(async (formas: FormaPagamentoLancada[]) => {
    if (!conn || !comanda) return { success: false, message: "Venda não encontrada." };
    try {
      const j = await apiSend(conn, `/api/checkout/${comanda}/fechar`, "POST", {
        formas, master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        setSituacao("PG");
        setFecharOpen(false);
        const resultadoImpressao = await imprimirVendaAutomatico(comanda);
        const msg = j.troco > 0 ? `Venda fechada! Troco: ${formatBRL(j.troco)}.` : "Venda fechada com sucesso!";
        showToast(`${msg} ${resultadoImpressao}`, "success", 5000);
      }
      return j;
    } catch (e) {
      return { success: false, message: friendlyCatchError(e) };
    }
  }, [conn, comanda, isMaster, classe, usuarioCod, showToast, imprimirVendaAutomatico]);

  const cancelarVenda = useCallback(() => {
    if (!conn || !comanda) return;
    feedback.showConfirm("Cancelar esta venda inteira? Todo o estoque lançado será devolvido.", async () => {
      try {
        const j = await apiSend(conn, `/api/checkout/${comanda}/cancelar`, "POST", {
          motivo: "Cancelado pelo operador", master: isMaster, classe, usuario_alteracao: usuarioCod, plataforma: "web",
        });
        if (j?.success) {
          setComanda(null);
          showToast("Venda cancelada.", "success");
        } else {
          showToast(friendlyApiError(j, "Não foi possível cancelar a venda."), "error");
        }
      } catch (e) {
        showToast(friendlyCatchError(e), "error");
      }
    });
  }, [conn, comanda, isMaster, classe, usuarioCod, showToast, feedback]);

  const isAberta = situacao === "A";
  const totalBruto = itens.reduce((s, it) => s + it.qtd * it.preco_bruto, 0);
  const totalDescontos = itens.reduce((s, it) => s + it.qtd * it.desconto_unit, 0);
  const totalAcrescimos = itens.reduce((s, it) => s + it.qtd * it.acrescimo_unit, 0);

  if (Platform.OS !== "web") {
    return <LockedView title="Disponível somente na versão web" message="Checkout está disponível apenas no web." testID="checkout-web-only" />;
  }
  if (!loading && !can("CHECKOUT.ABRIR") && !isMaster) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Checkout." testID="checkout-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="checkout-screen">
      <PedidoHeader
        title={comanda ? `Checkout — Venda #${comanda}` : "Checkout"}
        saving={false}
        canSave={false}
        onBack={() => router.back()}
        onSave={() => {}}
        onPrintConfig={isManagerFuncao ? () => setConfigImpressaoOpen(true) : undefined}
        onHelp={() => setAjudaOpen(true)}
      />

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, isWeb && WEB_SCROLL_CENTER]}>
        <View style={isWeb ? WEB_CONTENT_SHELL : undefined}>
          {loading || (!comanda && abrindo) ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : !comanda ? (
            // Fallback raro (abrir automaticamente falhou, ex.: sem
            // permissão ou erro de rede) — a venda normalmente já abre
            // sozinha (ver useEffect de auto-abertura acima), então este
            // bloco quase nunca aparece de verdade.
            <View style={{ alignItems: "center", marginTop: 60, gap: spacing.md }}>
              <Ionicons name="cart-outline" size={48} color={colors.muted} />
              <Text style={{ color: colors.muted, fontSize: 15 }}>Não foi possível abrir a venda automaticamente.</Text>
              <Pressable
                onPress={abrirVenda}
                disabled={abrindo || !can("CHECKOUT.ABRIR")}
                style={[primaryBtnStyle(), { paddingHorizontal: spacing.xl }]}
                testID="checkout-nova-venda"
              >
                {abrindo ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="add-circle-outline" size={20} color={colors.onBrandPrimary} />
                    <Text style={primaryBtnLabelStyle()}>Tentar de novo</Text>
                  </>
                )}
              </Pressable>
            </View>
          ) : (
            <View style={{ gap: spacing.md }}>
              {/* Cabeçalho: Atendente + Cliente */}
              <View style={cardStyle()}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center" }}>
                  <Text style={labelStyle()}>Atendente</Text>
                  <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }}>{atendenteNome || "—"}</Text>
                </View>
                <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.xs }}>
                  <Text style={{ flex: 1, fontSize: 15, color: colors.onSurface }}>
                    {clienteNome || "Clientes Diversos"}
                  </Text>
                  {isAberta ? (
                    <IconButtonWithTooltip
                      icon="search"
                      label="Buscar cliente"
                      size={20}
                      onPress={() => { setSearchTerm(""); setSearchResults([]); setSearchOpen(true); }}
                      testID="checkout-buscar-cliente"
                    />
                  ) : null}
                </View>
              </View>

              {/* 2 colunas: Registro de Itens (bipe/digite) + Demonstrativo do Cupom Fiscal */}
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                {isAberta && can("CHECKOUT.ADD_ITEM") ? (
                  <View style={[cardStyle(), { flex: 1, minWidth: 320 }]}>
                    <Text style={labelStyle()}>Bipar ou Digitar Produto/Serviço</Text>
                    <TextInput
                      ref={codigoRef}
                      value={codigoInput}
                      onChangeText={setCodigoInput}
                      onBlur={buscarPreview}
                      onSubmitEditing={adicionarItem}
                      blurOnSubmit={false}
                      placeholder="Código (bipe o leitor de código de barras aqui)"
                      placeholderTextColor={colors.muted}
                      selectTextOnFocus
                      style={[inputStyle(), { fontSize: 16 }]}
                      testID="checkout-codigo-input"
                    />

                    {preview ? (
                      <View style={{ gap: 2 }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{preview.descricao}</Text>
                        <View style={{ flexDirection: "row", gap: spacing.md, flexWrap: "wrap" }}>
                          {preview.unidade ? <Text style={{ fontSize: 12, color: colors.muted }}>Un.: {preview.unidade}</Text> : null}
                          {preview.estoque !== null ? <Text style={{ fontSize: 12, color: colors.muted }}>Estoque: {fmtNum(preview.estoque)}</Text> : null}
                          <Text style={{ fontSize: 12, color: colors.muted }}>Preço: {formatBRL(preview.preco)}</Text>
                          <Text style={{ fontSize: 12, color: colors.muted }}>Limite desc.: {preview.desc_v}%</Text>
                        </View>
                      </View>
                    ) : null}

                    <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" }}>
                      <View style={{ width: 90 }}>
                        <Text style={ps.fieldLabel}>Quantidade</Text>
                        <TextInput
                          ref={qtdRef}
                          value={qtdInput}
                          onChangeText={setQtdInput}
                          keyboardType="numeric"
                          onSubmitEditing={() => codigoRef.current?.focus()}
                          selectTextOnFocus
                          style={inputStyle()}
                          testID="checkout-qtd-input"
                        />
                      </View>
                      <View style={{ width: 100 }}>
                        <Text style={ps.fieldLabel}>Desconto %</Text>
                        <TextInput
                          ref={descRef}
                          value={descontoItemPct}
                          onChangeText={setDescontoItemPct}
                          keyboardType="numeric"
                          onSubmitEditing={() => codigoRef.current?.focus()}
                          selectTextOnFocus
                          style={inputStyle()}
                          testID="checkout-desconto-input"
                        />
                      </View>
                      <Pressable
                        onPress={adicionarItem}
                        disabled={addingItem || !codigoInput.trim()}
                        style={[primaryBtnStyle(), { flex: 1 }]}
                        testID="checkout-add-item-btn"
                      >
                        {addingItem ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                          <>
                            <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
                            <Text style={primaryBtnLabelStyle()}>Adicionar</Text>
                          </>
                        )}
                      </Pressable>
                    </View>
                    <Text style={{ fontSize: 11, color: colors.muted, fontStyle: "italic" }}>
                      Bipe o código de barras ou digite e pressione Enter — o item entra direto na venda, sem precisar do mouse.
                    </Text>
                  </View>
                ) : null}

                <DemonstrativoCupomFiscal
                  comanda={comanda}
                  itens={itens}
                  valorVenda={valorVenda}
                  podeCancelar={isAberta && can("CHECKOUT.DEL_ITEM")}
                  onCancelarItem={cancelarItem}
                />
              </View>

              {/* Totais */}
              <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                <StatBox label="Total Bruto" valor={totalBruto} />
                <StatBox label="Descontos" valor={totalDescontos} cor={colors.error} />
                <StatBox label="Acréscimos" valor={totalAcrescimos} />
                <StatBox label="Total a Pagar" valor={valorVenda} cor={colors.brandPrimary} destaque />
              </View>

              {/* Ações */}
              {isAberta ? (
                <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                  {can("CHECKOUT.ADD_ITEM") ? (
                    <Pressable onPress={() => setImportarOpen(true)} style={actionBtnStyle()} testID="checkout-importar-dav-btn">
                      <Ionicons name="download-outline" size={16} color={colors.onSurface} />
                      <Text style={actionBtnLabel()}>Importar Pedido/O.S.</Text>
                    </Pressable>
                  ) : null}
                  {can("CHECKOUT.DESC_GERAL") ? (
                    <Pressable onPress={() => setDescGeralOpen((v) => !v)} style={actionBtnStyle()} testID="checkout-desconto-geral-toggle">
                      <Ionicons name="pricetag-outline" size={16} color={colors.onSurface} />
                      <Text style={actionBtnLabel()}>Desconto Geral</Text>
                    </Pressable>
                  ) : null}
                  {can("CHECKOUT.FECHAR") ? (
                    <Pressable
                      onPress={() => setFecharOpen(true)}
                      disabled={itens.length === 0}
                      style={[actionBtnStyle(), { backgroundColor: colors.brandPrimary, opacity: itens.length === 0 ? 0.5 : 1 }]}
                      testID="checkout-fechar-btn"
                    >
                      <Ionicons name="cash-outline" size={16} color={colors.onBrandPrimary} />
                      <Text style={[actionBtnLabel(), { color: colors.onBrandPrimary }]}>Fechar Venda</Text>
                    </Pressable>
                  ) : null}
                  {can("CHECKOUT.CANCELAR") ? (
                    <Pressable onPress={cancelarVenda} style={[actionBtnStyle(), { borderColor: colors.error }]} testID="checkout-cancelar-venda-btn">
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                      <Text style={[actionBtnLabel(), { color: colors.error }]}>Cancelar Venda</Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : (
                <View style={{ alignItems: "center", padding: spacing.lg }}>
                  <Ionicons name="checkmark-circle" size={32} color={colors.success} />
                  <Text style={{ color: colors.success, fontWeight: "600", marginTop: spacing.xs }}>Venda fechada com sucesso.</Text>
                  <Pressable onPress={() => setComanda(null)} style={[primaryBtnStyle(), { marginTop: spacing.md }]} testID="checkout-nova-venda-apos-fechar">
                    <Ionicons name="add-circle-outline" size={18} color={colors.onBrandPrimary} />
                    <Text style={primaryBtnLabelStyle()}>Nova Venda</Text>
                  </Pressable>
                </View>
              )}

              {descGeralOpen && isAberta ? (
                <View style={cardStyle()}>
                  <Text style={labelStyle()}>Desconto Geral da Venda</Text>
                  <View style={{ flexDirection: "row", gap: spacing.sm }}>
                    <TextInput
                      value={descGeralPct}
                      onChangeText={setDescGeralPct}
                      keyboardType="numeric"
                      placeholder="% de desconto"
                      placeholderTextColor={colors.muted}
                      style={[inputStyle(), { width: 120 }]}
                      testID="checkout-desconto-geral-input"
                    />
                    <Pressable onPress={aplicarDescontoGeral} disabled={descGeralSaving} style={primaryBtnStyle()} testID="checkout-desconto-geral-aplicar">
                      {descGeralSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Aplicar</Text>}
                    </Pressable>
                  </View>
                </View>
              ) : null}
            </View>
          )}
        </View>
      </ScrollView>

      <ScreenToast toast={toast} testID="checkout-toast" />
      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Checkout" itens={AJUDA_ITENS} />
      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => definirCliente(c)}
        onCreate={() => setSearchOpen(false)}
      />
      {conn ? (
        <FecharVendaModal
          visible={fecharOpen}
          onClose={() => setFecharOpen(false)}
          conn={conn}
          totalDevido={valorVenda}
          onConfirm={fecharVenda}
        />
      ) : null}
      <ImportarDavModal
        visible={importarOpen}
        onClose={() => setImportarOpen(false)}
        onConfirm={importarDav}
      />
      <ConfiguracaoImpressaoModal
        visible={configImpressaoOpen}
        onClose={() => setConfigImpressaoOpen(false)}
        config={impressaoConfig}
        onSave={salvarConfigImpressao}
        onClear={removerConfigImpressao}
      />
    </SafeAreaView>
  );
}

function cardStyle() {
  return {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.md, gap: spacing.sm,
  } as const;
}
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 };
}
function inputStyle() {
  return {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
    backgroundColor: colors.surfaceSecondary,
  } as const;
}
function StatBox({ label, valor, cor, destaque }: { label: string; valor: number; cor?: string; destaque?: boolean }) {
  return (
    <View
      style={{
        flex: 1, minWidth: 140, borderRadius: radius.md, padding: spacing.md,
        backgroundColor: destaque ? (cor || colors.brandPrimary) : colors.surface,
        borderWidth: destaque ? 0 : 1, borderColor: colors.border,
      }}
    >
      <Text style={{ fontSize: 11, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.5, color: destaque ? colors.onBrandPrimary : colors.muted }}>
        {label}
      </Text>
      <Text style={{ fontSize: 18, fontWeight: "800", marginTop: 2, color: destaque ? colors.onBrandPrimary : (cor || colors.onSurface) }}>
        {formatBRL(valor)}
      </Text>
    </View>
  );
}
function actionBtnStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const, gap: 6,
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: 10, backgroundColor: colors.surface,
  };
}
function actionBtnLabel() {
  return { fontSize: 13, fontWeight: "700" as const, color: colors.onSurface };
}
function primaryBtnStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 12, minWidth: 120,
  };
}
function primaryBtnLabelStyle() {
  return { color: colors.onBrandPrimary, fontWeight: "600" as const, fontSize: 14 };
}
