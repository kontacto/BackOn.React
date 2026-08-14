// Card rico do "Painel de Pedidos" (app/pedidos.tsx, visão "2 colunas") —
// além de abrir o pedido completo, permite agilizar o atendimento direto do
// card, sem precisar abrir a tela do pedido: adicionar item, faturar (com
// forma de pagamento) e imprimir a conta. A ideia (pedido explícito do
// usuário, 2026-07-17) é reservar a tela cheia do pedido pra quando
// realmente precisar de mais recursos (descontos, edição de item, etc.).
import { useMemo, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import MaterialCommunityIcons from "@expo/vector-icons/MaterialCommunityIcons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, formatDateBR, fmtNum, parseNum } from "@/src/utils/format";
import { apiGet, apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { styles } from "./styles";
import { ClienteRow, ItemPrintData, ItemRow, ModificadorCategoriaVenda, PedidoData, ProdutoServico } from "./types";
import { TIPO_COLOR, TIPO_ICON } from "./painelTipos";
import ReciboPedidoModal from "./ReciboPedidoModal";

const isWeb = Platform.OS === "web";

export type PainelPedidoItem = {
  pedido: number; situacao: string; situacao_label: string; total: number;
  cliente: number | null; cliente_nome: string; vendedor_nome: string;
  data: string | null; hora_aberto: string; localizacao_descricao: string;
  qtd_pessoas: number | null;
  // Taxa de Serviço (S002) já lançada neste pedido — resolvido pelo
  // backend (`_list_pedidos_sync`) pra colorir o ícone do botão "Tx
  // Serviço" sem precisar carregar os itens do card. Pedido explícito do
  // usuário, 2026-07-17.
  taxa_servico_incluida: boolean;
  // Tem ao menos 1 item de produto/serviço (fora a própria S002) — usado
  // pra desabilitar o botão "Tx Serviço" num pedido ainda vazio (mesmo
  // bloqueio reforçado no backend). Pedido explícito do usuário,
  // 2026-07-18.
  tem_itens: boolean;
};

type Props = {
  item: PainelPedidoItem;
  tipoKey: string;
  nowMs: number;
  conn: Connection;
  usuarioCod: number;
  funcaoCod: number;
  classe: number | null;
  isMaster: boolean;
  canAddItem: boolean;
  canFaturar: boolean;
  canImprimir: boolean;
  canTaxaServico: boolean;
  formasPagamento: { codigo: string; descricao: string }[];
  onAbrir: () => void;
  onChanged: () => void;
};

// Retorna "" (sem hora) quando o pedido já passou de 24h aberto — a data
// (linha 2 do card) já indica que é de outro dia, mostrar "26:43" (ou
// mais) não agrega nada. Pedido explícito do usuário, 2026-07-18.
function formatTempoAberto(data: string | null, horaAberto: string, nowMs: number): string {
  if (!data) return "—";
  const [y, m, d] = data.split("-").map((n) => parseInt(n, 10));
  const [hh, mm, ss] = (horaAberto || "00:00:00").split(":").map((n) => parseInt(n, 10) || 0);
  const opened = new Date(y, (m || 1) - 1, d || 1, hh || 0, mm || 0, ss || 0).getTime();
  if (Number.isNaN(opened)) return "—";
  const diff = Math.max(0, Math.floor((nowMs - opened) / 1000));
  const h = Math.floor(diff / 3600);
  if (h >= 24) return "";
  const min = Math.floor((diff % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(min).padStart(2, "0")}`;
}

export default function PainelPedidoCard({
  item, tipoKey, nowMs, conn, usuarioCod, funcaoCod, classe, isMaster,
  canAddItem, canFaturar, canImprimir, canTaxaServico, formasPagamento, onAbrir, onChanged,
}: Props) {
  const feedback = useFeedback();
  const icon = TIPO_ICON[tipoKey];
  // Borda esquerda + ícone + texto sempre replicam a cor da COLUNA
  // (TIPO_COLOR) — nunca sobrescritos por vermelho só porque o pedido
  // está parado. Antes (2026-07-17) "parado" virava vermelho sólido,
  // mascarando a cor do tipo; corrigido 2026-08-11, pedido explícito do
  // usuário ("quero que o tema de cor dos cards da coluna Mesa tenha a
  // cor da coluna. propague para as demais colunas") — motivado por
  // "parado" ter deixado de ser um sinal de Fiado (ver `stale` doc em
  // `pedidos.tsx`: fiado agora é decidido só por arrasto manual pra
  // coluna Fiado, cuja própria TIPO_COLOR já é vermelha). O reordenar
  // pedidos parados pro fim da coluna (`isStale`/`ordenar` em
  // `pedidos.tsx`) continua sem mudança — só a COR deixou de depender
  // disso, por isso a prop `stale` (que só servia pra isso) foi removida
  // deste componente.
  const accentColor = TIPO_COLOR[tipoKey] || colors.brandPrimary;
  const textColor = colors.onSurface;

  // -------- Tooltip dos botões de ação — um só de cada vez, hover no web
  // (mobile não tem hover, os ícones ficam só com o testID pra achar no toque).
  const [hoverBtn, setHoverBtn] = useState<string | null>(null);
  const renderTooltip = (key: string, label: string) =>
    hoverBtn === key ? (
      <View style={ps.tooltip} pointerEvents="none">
        <View style={ps.tooltipInner}>
          <Text style={ps.tooltipText}>{label}</Text>
        </View>
      </View>
    ) : null;

  // -------- Qtd. Pessoas (inline, +/-)
  const [qtdSaving, setQtdSaving] = useState(false);
  const setQtdPessoas = async (novaQtd: number) => {
    if (qtdSaving) return;
    setQtdSaving(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${item.pedido}/qtd-pessoas`, "POST", {
        qtd_pessoas: Math.max(0, novaQtd), usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) feedback.showError(j?.message || "Falha ao gravar qtd. de pessoas.");
      else onChanged();
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setQtdSaving(false);
    }
  };

  // -------- Adicionar item rápido (busca produto, toque adiciona qtd=1)
  const [addOpen, setAddOpen] = useState(false);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoServico[]>([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [addingCodigo, setAddingCodigo] = useState<string | null>(null);
  // Qtd. digitável por produto na lista do modal — default "1", só quando
  // o usuário edita é que passa a valer pro "+" daquela linha. Pedido
  // explícito do usuário, 2026-07-18 ("possibilitar eu digitar uma qtd do
  // item pra adicionar uma qtd específica").
  const [qtyByProduto, setQtyByProduto] = useState<Record<string, string>>({});
  const getQty = (codigo: string) => qtyByProduto[codigo] ?? "1";
  let prodSearchTimer: ReturnType<typeof setTimeout> | null = null;

  // Itens já lançados neste pedido — lista padrão do modal enquanto a
  // busca está vazia (facilita repetir um item já pedido, ex.: mais uma
  // rodada da mesma bebida), mesmo comportamento do "Adicionar Item" da
  // tela de Pedido (`usePedidoItens.pedidoProdutos`/`AddItemModal.tsx`).
  // Taxa de Serviço (S002) fica de fora — tem fluxo próprio. Pedido
  // explícito do usuário, 2026-07-17.
  const [pedidoItensAtuais, setPedidoItensAtuais] = useState<ItemRow[]>([]);
  const pedidoProdutosAtuais = useMemo<ProdutoServico[]>(() => {
    const porCodigo = new Map<string, ProdutoServico>();
    for (const it of pedidoItensAtuais) {
      if (it.produto === "S002") continue;
      if (!porCodigo.has(it.produto)) {
        porCodigo.set(it.produto, {
          tipo: it.tipo === "S" ? "S" : "P",
          codigo: it.produto,
          descricao: it.descricao,
          valor: it.p_normal || it.valor_unitario,
          estoque: null,
          cod_fab: it.cod_fab,
          unidade: it.unidade,
        });
      }
    }
    return Array.from(porCodigo.values());
  }, [pedidoItensAtuais]);
  const buscandoProduto = prodTerm.trim().length > 0;
  const listaProdutosExibida = buscandoProduto ? prodResults : pedidoProdutosAtuais;

  const buscarProdutos = (term: string) => {
    setProdTerm(term);
    if (prodSearchTimer) clearTimeout(prodSearchTimer);
    if (!term.trim()) { setProdResults([]); return; }
    prodSearchTimer = setTimeout(async () => {
      setProdLoading(true);
      try {
        const j = await apiGet(conn, "/api/produtos-servicos", { search: term, page: 1, size: 20, tipo: "P" });
        setProdResults(j?.items || []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 300);
  };

  // -------- Accordion "Itens do pedido" (Descrição/Qtd/Imprimir/Valor) —
  // não mexe na largura do card, só expande a altura pra baixo. Reaproveita
  // `pedidoItensAtuais`/`carregarItensAtuais` (já usados pelo modal
  // "Adicionar item"). Pedido explícito do usuário, 2026-07-18. Lista
  // TOTALIZADA (agrupa por produto, soma qtd/valor) — pedido explícito do
  // usuário no mesmo dia ("a lista de item totalizada"), inclui S002 (Taxa
  // de Serviço) ao contrário de `pedidoProdutosAtuais` acima (aquela é só
  // pra repetir item no "Adicionar item", essa é a listagem em si).
  // `sample` guarda uma linha original do grupo — usada só pra montar o
  // ticket de impressão (codauto/tipo/complemento/finalidade), com a `qtd`
  // sobrescrita pelo total do grupo.
  const itensAccordionGrupos = useMemo(() => {
    const grupos = new Map<string, { produto: string; descricao: string; qtd: number; total: number; sample: ItemRow }>();
    for (const it of pedidoItensAtuais) {
      const atual = grupos.get(it.produto);
      if (atual) {
        atual.qtd += it.qtd;
        atual.total += it.total;
      } else {
        grupos.set(it.produto, { produto: it.produto, descricao: it.descricao, qtd: it.qtd, total: it.total, sample: it });
      }
    }
    return Array.from(grupos.values());
  }, [pedidoItensAtuais]);

  const [itensExpandido, setItensExpandido] = useState(false);
  const [itensAccordionLoading, setItensAccordionLoading] = useState(false);
  const toggleItensExpandido = async () => {
    const abrindo = !itensExpandido;
    setItensExpandido(abrindo);
    if (abrindo) {
      setItensAccordionLoading(true);
      await carregarItensAtuais();
      setItensAccordionLoading(false);
    }
  };

  const carregarItensAtuais = async () => {
    try {
      const j = await apiGet(conn, `/api/pedidos/${item.pedido}/itens`);
      setPedidoItensAtuais(j?.items || []);
    } catch {
      setPedidoItensAtuais([]);
    }
  };

  // -------- Impressão automática de item por Finalidade — mesmo mecanismo
  // de `usePedidoItens.checkAutoPrintItem`, reimplementado aqui porque este
  // card não usa aquele hook (busca+add próprios, mais enxuto — ver
  // comentário do topo do arquivo). Sem isso, adicionar item por aqui nunca
  // disparava o ticket de cozinha/bar, só adicionando pela tela cheia do
  // pedido. Pedido explícito do usuário, 2026-07-18 ("na lista de pedidos
  // bar, não imprime item da cozinha, adicionando do card").
  const [printItem, setPrintItem] = useState<ItemPrintData | null>(null);
  const [printItemPedido, setPrintItemPedido] = useState<PedidoData | null>(null);
  const [printItemCliente, setPrintItemCliente] = useState<ClienteRow | null>(null);
  const [printItemClienteResumo, setPrintItemClienteResumo] = useState<{ codigo: number; nome: string; cgc_cpf: string; e_mail: string; telefone: string; endereco: string } | null>(null);

  // Busca pedido+cliente e abre o ticket de item — usada tanto pelo disparo
  // automático por Finalidade quanto pelo botão manual "Imprimir" de cada
  // linha no accordion de itens (ver mais abaixo).
  const abrirTicketItem = async (printData: ItemPrintData) => {
    if (!conn) return;
    const [jp, jc] = await Promise.all([
      apiGet(conn, `/api/pedidos/${item.pedido}`),
      item.cliente ? apiGet(conn, `/api/clientes/${item.cliente}/resumo`) : Promise.resolve(null),
    ]);
    if (jp?.success) setPrintItemPedido(jp.pedido);
    const resumo = jc?.success ? jc.cliente : null;
    setPrintItemClienteResumo(resumo);
    setPrintItemCliente(item.cliente ? { codigo: item.cliente, nome: resumo?.nome || item.cliente_nome, cgc_cpf: resumo?.cgc_cpf || "", telefone: resumo?.telefone || "" } : null);
    setPrintItem(printData);
  };

  const checkAutoPrintItem = async (printData: ItemPrintData, tipoPeca: number | null) => {
    if (!conn || tipoPeca == null) return;
    try {
      const j = await apiGet(conn, "/api/controle-sistema/direcionamento-impressora/por-finalidade", { tipo: tipoPeca });
      if (!j?.success || !j.configurado) return;
      if (j.automatica) {
        abrirTicketItem(printData);
      } else {
        feedback.showConfirm(`Imprimir este item para ${printData.finalidade_descricao || "impressão"}?`, () => abrirTicketItem(printData));
      }
    } catch {
      // silencioso — não pode travar o fluxo de adicionar item
    }
  };

  const quickAddItem = async (
    p: ProdutoServico,
    extra?: { acrescimoExtra?: number; descontoExtra?: number; complementoExtra?: string },
  ): Promise<boolean> => {
    const qtd = parseNum(getQty(p.codigo));
    if (qtd <= 0) { feedback.showWarning("Quantidade deve ser maior que zero."); return false; }
    setAddingCodigo(p.codigo);
    try {
      // Variação de Preço (Promoção, `pecas_promocao`) — mesma checagem do
      // "Confirmar Item" da tela cheia (ver `usePedidoItens.verificarPromocao`),
      // pra não dar preço diferente pro mesmo produto+quantidade só por ter
      // sido incluído pelo atalho do card em vez do modal completo.
      let valorUnitario = p.valor;
      if (p.tipo === "P" && conn) {
        try {
          const jp = await apiGet(conn, `/api/produtos/${encodeURIComponent(p.codigo)}/preco-promocional`, { qtd });
          if (jp?.success && jp.promocao) valorUnitario = jp.promocao.p_venda;
        } catch {
          // best-effort — segue com o preço base se a checagem falhar
        }
      }
      const j = await apiSend(conn, `/api/pedidos/${item.pedido}/itens`, "POST", {
        produto: p.codigo, qtd, valor_unitario: valorUnitario,
        desconto: extra?.descontoExtra || 0, desconto_pct: 0, acrescimo: extra?.acrescimoExtra || 0,
        usuario_codigo: usuarioCod, funcao: funcaoCod, classe, plataforma: Platform.OS,
        complemento: extra?.complementoExtra || "",
      });
      if (!j?.success) { feedback.showError(j?.message || "Falha ao adicionar item."); return false; }
      feedback.showSuccess(`${fmtNum(qtd)}x ${p.descricao} adicionado.`);
      setQtyByProduto((prev) => ({ ...prev, [p.codigo]: "1" }));
      onChanged();
      carregarItensAtuais();
      if (j.item) checkAutoPrintItem(j.item, j.tipo_peca ?? null);
      return true;
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      return false;
    } finally {
      setAddingCodigo(null);
    }
  };

  const abrirAddModal = () => {
    setProdTerm("");
    setProdResults([]);
    setAddOpen(true);
    carregarItensAtuais();
  };

  // -------- Modificadores (Fase 2) no "+" rápido deste card — mesmo padrão
  // de AddItemModal.tsx, reimplementado aqui porque este card não usa aquele
  // componente (busca+add próprios, ver comentário do topo do arquivo).
  // Produto com modificador associado não pode pular direto pro "+" rápido —
  // precisa passar por uma etapa de confirmação pra escolher o modificador
  // antes. Pedido explícito do usuário, 2026-07-23 (esta rodada fechou o gap
  // deixado de fora quando a Fase 2 foi implementada só na tela cheia).
  const [modProd, setModProd] = useState<ProdutoServico | null>(null);
  const [modCategorias, setModCategorias] = useState<ModificadorCategoriaVenda[]>([]);
  const [modSelecionados, setModSelecionados] = useState<Map<number, Set<number>>>(new Map());

  const buscarModificadoresProduto = async (p: ProdutoServico): Promise<ModificadorCategoriaVenda[]> => {
    try {
      const j = await apiGet(conn, `/api/modificadores/por-item/${p.tipo}/${encodeURIComponent(p.codigo)}/completo`);
      return j?.success ? (j.items || []) : [];
    } catch {
      return [];
    }
  };

  const toggleModificador = (cat: ModificadorCategoriaVenda, modCodigo: number) => {
    setModSelecionados((prev) => {
      const next = new Map(prev);
      const atual = new Set(next.get(cat.codigo) || []);
      if (cat.selecao_multipla) {
        if (atual.has(modCodigo)) atual.delete(modCodigo); else atual.add(modCodigo);
      } else if (atual.has(modCodigo)) {
        if (!cat.obrigatorio) atual.clear();
      } else {
        atual.clear();
        atual.add(modCodigo);
      }
      next.set(cat.codigo, atual);
      return next;
    });
  };

  let modAcrescimoTotal = 0;
  let modDescontoTotal = 0;
  const modNomesEscolhidos: string[] = [];
  for (const cat of modCategorias) {
    const sel = modSelecionados.get(cat.codigo);
    if (!sel || sel.size === 0) continue;
    for (const mod of cat.modificadores) {
      if (!sel.has(mod.codigo)) continue;
      modAcrescimoTotal += mod.acrescimo || 0;
      modDescontoTotal += mod.desconto || 0;
      modNomesEscolhidos.push(mod.nome);
    }
  }
  const modNomesTexto = modNomesEscolhidos.join(", ");
  const categoriasObrigatoriasFaltando = modCategorias.filter(
    (cat) => cat.obrigatorio && (modSelecionados.get(cat.codigo)?.size || 0) === 0,
  );

  const iniciarAddProduto = async (p: ProdutoServico) => {
    if (addingCodigo === p.codigo) return;
    setAddingCodigo(p.codigo);
    const cats = await buscarModificadoresProduto(p);
    setAddingCodigo(null);
    if (cats.length > 0) {
      setModCategorias(cats);
      setModSelecionados(new Map());
      setModProd(p);
    } else {
      quickAddItem(p);
    }
  };

  const handleConfirmarModificadores = async () => {
    if (categoriasObrigatoriasFaltando.length > 0) {
      feedback.showError(`Selecione uma opção em: ${categoriasObrigatoriasFaltando.map((c) => c.nome).join(", ")}.`);
      return;
    }
    if (!modProd) return;
    const ok = await quickAddItem(modProd, {
      acrescimoExtra: modAcrescimoTotal,
      descontoExtra: modDescontoTotal,
      complementoExtra: modNomesTexto || undefined,
    });
    if (ok) {
      setModProd(null);
      setModCategorias([]);
      setModSelecionados(new Map());
    }
  };

  // -------- Taxa de Serviço (10% do subtotal, código S002) — mesma regra
  // de `usePedidoItens.handleTaxaServico` (idempotente: reclicar atualiza a
  // linha já lançada em vez de duplicar), reimplementada aqui em vez de
  // reaproveitar o hook inteiro — mesmo motivo já documentado no card pro
  // "+ Item" (hook carrega muito mais estado do que um card precisa).
  // Pedido explícito do usuário, 2026-07-17.
  const [taxaServicoSaving, setTaxaServicoSaving] = useState(false);
  const handleTaxaServico = async () => {
    if (!item.tem_itens) {
      feedback.showWarning("Inclua ao menos um item no pedido antes de lançar a Taxa de Serviço.");
      return;
    }
    setTaxaServicoSaving(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${item.pedido}/taxa-servico`, "POST", {
        usuario_codigo: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (j?.success) {
        feedback.showSuccess(`Taxa de serviço ${j.atualizado ? "atualizada" : "incluída"} (${formatBRL(j.valor)}).`);
        onChanged();
        carregarItensAtuais();
      } else {
        feedback.showError(j?.message || "Falha ao incluir taxa de serviço.");
      }
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setTaxaServicoSaving(false);
    }
  };

  // -------- Faturar rápido (1 forma de pagamento, valor cheio)
  const [faturarOpen, setFaturarOpen] = useState(false);
  const [formaSel, setFormaSel] = useState<string | null>(null);
  const [faturarSaving, setFaturarSaving] = useState(false);

  const handleFaturar = async () => {
    if (!formaSel) { feedback.showWarning("Selecione a forma de pagamento."); return; }
    setFaturarSaving(true);
    try {
      const jf = await apiSend(conn, `/api/pedidos/${item.pedido}/forma-pag-simples`, "POST", {
        forma_pag: formaSel, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!jf?.success) { feedback.showError(jf?.message || "Falha ao definir forma de pagamento."); return; }
      const j = await apiSend(conn, `/api/pedidos/${item.pedido}/faturar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) feedback.showError(j?.message || "Falha ao faturar.");
      else { feedback.showSuccess(`Pedido ${item.pedido} faturado.`); setFaturarOpen(false); onChanged(); }
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setFaturarSaving(false);
    }
  };

  // -------- Imprimir conta (busca pedido + itens + resumo do cliente, abre ReciboPedidoModal)
  const [imprimirOpen, setImprimirOpen] = useState(false);
  const [imprimirLoading, setImprimirLoading] = useState(false);
  const [printPedido, setPrintPedido] = useState<PedidoData | null>(null);
  const [printItens, setPrintItens] = useState<ItemRow[]>([]);
  const [printCliente, setPrintCliente] = useState<ClienteRow | null>(null);
  const [printClienteResumo, setPrintClienteResumo] = useState<{ codigo: number; nome: string; cgc_cpf: string; e_mail: string; telefone: string; endereco: string } | null>(null);

  const printGrupos = useMemo(() => {
    const grupos = new Map<string, { produto: string; cod_fab: string; descricao: string; qtd: number; valorTotal: number }>();
    for (const it of printItens) {
      const totalLinha = it.qtd * it.valor_unitario;
      const atual = grupos.get(it.produto);
      if (atual) { atual.qtd += it.qtd; atual.valorTotal += totalLinha; }
      else grupos.set(it.produto, { produto: it.produto, cod_fab: it.cod_fab, descricao: it.descricao, qtd: it.qtd, valorTotal: totalLinha });
    }
    return Array.from(grupos.values());
  }, [printItens]);

  const handleImprimir = async () => {
    setImprimirLoading(true);
    try {
      const [jp, ji, jc] = await Promise.all([
        apiGet(conn, `/api/pedidos/${item.pedido}`),
        apiGet(conn, `/api/pedidos/${item.pedido}/itens`),
        item.cliente ? apiGet(conn, `/api/clientes/${item.cliente}/resumo`) : Promise.resolve(null),
      ]);
      if (!jp?.success) { feedback.showError(jp?.message || "Falha ao carregar pedido."); return; }
      setPrintPedido(jp.pedido);
      setPrintItens(ji?.items || []);
      const resumo = jc?.success ? jc.cliente : null;
      setPrintClienteResumo(resumo);
      setPrintCliente(item.cliente ? { codigo: item.cliente, nome: resumo?.nome || item.cliente_nome, cgc_cpf: resumo?.cgc_cpf || "", telefone: resumo?.telefone || "" } : null);
      setImprimirOpen(true);
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setImprimirLoading(false);
    }
  };

  return (
    <>
      <View style={[ps.card, { borderLeftColor: accentColor, borderLeftWidth: 4 }]} testID={`painel-card-${item.pedido}`}>
        {/* zIndex só quando o tooltip do nome está visível — elevar esta
            linha sempre (fixo) fazia os tooltips dos botões de ação
            (renderizados acima do próprio botão, esticando até perto de
            line1) ficarem por trás dela. Condicional preserva a ordem
            natural do DOM (actionsRow por último = já pinta por cima sem
            precisar de zIndex) pro resto dos tooltips. Pedido explícito do
            usuário, 2026-07-18 ("verificar todos os tooltip"). */}
        <Pressable
          onPress={onAbrir}
          style={[ps.line1, hoverBtn === "nome" && { zIndex: 5 }]}
          testID={`painel-card-abrir-${item.pedido}`}
        >
          <View style={ps.line1Left}>
            {icon ? (
              icon.lib === "mci" ? (
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                <MaterialCommunityIcons name={icon.name as any} size={14} color={accentColor} />
              ) : (
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                <Ionicons name={icon.name as any} size={14} color={accentColor} />
              )
            ) : null}
            <Pressable
              onPress={onAbrir}
              onHoverIn={() => setHoverBtn("nome")}
              onHoverOut={() => setHoverBtn(null)}
              style={ps.nomeWrap}
              testID={`painel-card-nome-${item.pedido}`}
            >
              <Text style={[ps.line1Text, { color: textColor }]} numberOfLines={1}>
                #{item.pedido} · {item.cliente_nome || "(sem cliente)"}
              </Text>
              {hoverBtn === "nome" ? (
                <View style={ps.nomeTooltip} pointerEvents="none">
                  <View style={ps.tooltipInner}>
                    <Text style={ps.tooltipText}>{item.cliente_nome || "(sem cliente)"}</Text>
                  </View>
                </View>
              ) : null}
            </Pressable>
          </View>
          <Text style={[ps.line1Valor, { color: colors.brandPrimary }]}>{formatBRL(item.total)}</Text>
        </Pressable>

        <View style={ps.line2}>
          <Text style={[ps.line2Text, { color: textColor }]} numberOfLines={1}>
            {[formatDateBR(item.data), item.vendedor_nome || "—", formatTempoAberto(item.data, item.hora_aberto, nowMs)]
              .filter(Boolean)
              .join(" · ")}
          </Text>
          <View style={ps.pessoasStepper}>
            <Pressable
              onPress={() => setQtdPessoas((item.qtd_pessoas || 0) - 1)}
              disabled={qtdSaving || (item.qtd_pessoas || 0) <= 0}
              hitSlop={6}
              testID={`painel-card-pessoas-menos-${item.pedido}`}
            >
              <Ionicons name="remove-circle-outline" size={15} color={(item.qtd_pessoas || 0) <= 0 ? colors.border : colors.brandPrimary} />
            </Pressable>
            <Text style={ps.pessoasValue}>{item.qtd_pessoas || "—"}</Text>
            <Pressable
              onPress={() => setQtdPessoas((item.qtd_pessoas || 0) + 1)}
              disabled={qtdSaving}
              hitSlop={6}
              testID={`painel-card-pessoas-mais-${item.pedido}`}
            >
              <Ionicons name="add-circle-outline" size={15} color={colors.brandPrimary} />
            </Pressable>
          </View>
        </View>

        <View style={ps.actionsRow}>
          <View style={ps.actionWrap}>
            <Pressable
              onPress={onAbrir}
              onHoverIn={() => setHoverBtn("abrir")}
              onHoverOut={() => setHoverBtn(null)}
              style={ps.actionBtn}
              testID={`painel-card-action-abrir-${item.pedido}`}
            >
              <Ionicons name="open-outline" size={18} color={colors.brandPrimary} />
            </Pressable>
            {renderTooltip("abrir", "Abrir pedido")}
          </View>
          {canAddItem ? (
            <View style={ps.actionWrap}>
              <Pressable
                onPress={abrirAddModal}
                onHoverIn={() => setHoverBtn("item")}
                onHoverOut={() => setHoverBtn(null)}
                style={ps.actionBtn}
                testID={`painel-card-action-item-${item.pedido}`}
              >
                <Ionicons name="add-circle-outline" size={18} color={colors.brandPrimary} />
              </Pressable>
              {renderTooltip("item", "Adicionar item")}
            </View>
          ) : null}
          {canFaturar ? (
            <View style={ps.actionWrap}>
              <Pressable
                onPress={() => { setFormaSel(null); setFaturarOpen(true); }}
                onHoverIn={() => setHoverBtn("faturar")}
                onHoverOut={() => setHoverBtn(null)}
                style={ps.actionBtn}
                testID={`painel-card-action-faturar-${item.pedido}`}
              >
                <Ionicons name="cash-outline" size={18} color={colors.success} />
              </Pressable>
              {renderTooltip("faturar", "Faturar")}
            </View>
          ) : null}
          {canImprimir && isWeb ? (
            <View style={ps.actionWrap}>
              <Pressable
                onPress={handleImprimir}
                onHoverIn={() => setHoverBtn("imprimir")}
                onHoverOut={() => setHoverBtn(null)}
                style={ps.actionBtn}
                disabled={imprimirLoading}
                testID={`painel-card-action-imprimir-${item.pedido}`}
              >
                {imprimirLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Ionicons name="print-outline" size={18} color={colors.brandPrimary} />}
              </Pressable>
              {renderTooltip("imprimir", "Imprimir conta")}
            </View>
          ) : null}
          {canTaxaServico ? (
            <View style={ps.actionWrap}>
              <Pressable
                onPress={handleTaxaServico}
                onHoverIn={() => setHoverBtn("taxa")}
                onHoverOut={() => setHoverBtn(null)}
                disabled={taxaServicoSaving || !item.tem_itens}
                style={[ps.actionBtn, !item.tem_itens && { opacity: 0.4 }]}
                testID={`painel-card-action-taxa-servico-${item.pedido}`}
              >
                {taxaServicoSaving ? (
                  <ActivityIndicator size="small" color={colors.brandPrimary} />
                ) : (
                  <MaterialCommunityIcons
                    name="room-service"
                    size={18}
                    color={item.taxa_servico_incluida ? colors.success : colors.brandPrimary}
                  />
                )}
              </Pressable>
              {renderTooltip("taxa", item.tem_itens ? "Taxa de serviço" : "Inclua um item primeiro")}
            </View>
          ) : null}
          <View style={ps.actionWrap}>
            <Pressable
              onPress={toggleItensExpandido}
              onHoverIn={() => setHoverBtn("expandir")}
              onHoverOut={() => setHoverBtn(null)}
              style={ps.actionBtn}
              testID={`painel-card-action-expandir-${item.pedido}`}
            >
              <Ionicons name={itensExpandido ? "chevron-up-outline" : "chevron-down-outline"} size={18} color={colors.brandPrimary} />
            </Pressable>
            {renderTooltip("expandir", itensExpandido ? "Ocultar itens" : "Ver itens")}
          </View>
        </View>

        {/* -------- Accordion: itens do pedido (Descrição/Qtd/Imprimir/Valor) -------- */}
        {itensExpandido ? (
          <View style={ps.itensAccordion}>
            {itensAccordionLoading ? (
              <ActivityIndicator size="small" color={colors.brandPrimary} style={{ marginVertical: 6 }} />
            ) : itensAccordionGrupos.length === 0 ? (
              <Text style={ps.itensAccordionEmpty}>Nenhum item incluído.</Text>
            ) : (
              itensAccordionGrupos.map((g) => (
                <View
                  key={g.produto}
                  style={[ps.itensAccordionRow, hoverBtn === `desc-${g.produto}` && { zIndex: 5 }]}
                >
                  <Pressable
                    style={ps.itensAccordionDescWrap}
                    onHoverIn={() => setHoverBtn(`desc-${g.produto}`)}
                    onHoverOut={() => setHoverBtn(null)}
                  >
                    <Text style={ps.itensAccordionDesc} numberOfLines={1}>{g.descricao}</Text>
                    {hoverBtn === `desc-${g.produto}` ? (
                      <View style={ps.itensAccordionDescTooltip} pointerEvents="none">
                        <View style={ps.tooltipInner}>
                          <Text style={ps.tooltipText}>{g.descricao}</Text>
                        </View>
                      </View>
                    ) : null}
                  </Pressable>
                  <Text style={ps.itensAccordionQtd}>{fmtNum(g.qtd)}</Text>
                  <Pressable
                    onPress={() => abrirTicketItem({ ...g.sample, qtd: g.qtd })}
                    hitSlop={6}
                    style={ps.itensAccordionPrintBtn}
                    testID={`painel-card-item-imprimir-${g.produto}`}
                  >
                    <Ionicons name="print-outline" size={14} color={colors.brandPrimary} />
                  </Pressable>
                  <Text style={ps.itensAccordionValor}>{formatBRL(g.total)}</Text>
                </View>
              ))
            )}
          </View>
        ) : null}
      </View>

      {/* -------- Modal: adicionar item rápido -------- */}
      <Modal
        visible={addOpen}
        transparent
        animationType="slide"
        onRequestClose={() => { setAddOpen(false); setModProd(null); setModCategorias([]); }}
      >
        <Pressable
          style={[styles.modalBg, isWeb && styles.modalBgWebCompact]}
          onPress={() => { setAddOpen(false); setModProd(null); setModCategorias([]); }}
        >
          <Pressable
            style={[styles.modalCard, isWeb && (modProd ? styles.modalCardWebCompactNarrow : styles.modalCardWebCompact)]}
            onPress={(e) => e.stopPropagation()}
          >
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {modProd ? "Escolher modificadores" : `Adicionar item — Pedido ${item.pedido}`}
              </Text>
              <Pressable
                onPress={() => { setAddOpen(false); setModProd(null); setModCategorias([]); }}
                hitSlop={8}
              >
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {modProd ? (
              <ScrollView style={{ maxHeight: 460 }} keyboardShouldPersistTaps="handled">
                <View style={{ gap: spacing.sm }}>
                  <View style={styles.selProdBox}>
                    <Text style={styles.itemDesc} numberOfLines={2}>{modProd.descricao}</Text>
                    <Text style={styles.resultSub}>#{modProd.codigo}</Text>
                  </View>
                  <View style={modStyles.wrap}>
                      {modCategorias.map((cat) => {
                        const sel = modSelecionados.get(cat.codigo) || new Set<number>();
                        const faltando = categoriasObrigatoriasFaltando.some((c) => c.codigo === cat.codigo);
                        return (
                          <View key={cat.codigo} style={modStyles.categoria}>
                            <View style={modStyles.categoriaHeader}>
                              <Text style={modStyles.categoriaNome}>{cat.nome}</Text>
                              <View style={[modStyles.badge, cat.obrigatorio ? modStyles.badgeObrig : modStyles.badgeOpc]}>
                                <Text style={[modStyles.badgeText, cat.obrigatorio ? modStyles.badgeTextObrig : modStyles.badgeTextOpc]}>
                                  {cat.obrigatorio ? "Obrigatório" : "Opcional"}{cat.selecao_multipla ? " · Vários" : ""}
                                </Text>
                              </View>
                            </View>
                            {faltando ? <Text style={modStyles.avisoFaltando}>Selecione uma opção.</Text> : null}
                            {cat.modificadores.map((mod) => {
                              const ativo = sel.has(mod.codigo);
                              return (
                                <Pressable
                                  key={mod.codigo}
                                  style={modStyles.modRow}
                                  onPress={() => toggleModificador(cat, mod.codigo)}
                                  testID={`painel-add-item-mod-${cat.codigo}-${mod.codigo}`}
                                >
                                  <Ionicons
                                    name={cat.selecao_multipla ? (ativo ? "checkbox" : "square-outline") : (ativo ? "radio-button-on" : "radio-button-off")}
                                    size={18}
                                    color={ativo ? colors.brandPrimary : colors.muted}
                                  />
                                  <Text style={modStyles.modNome}>{mod.nome}</Text>
                                  {mod.acrescimo > 0 ? <Text style={modStyles.modValor}>+{formatBRL(mod.acrescimo)}</Text> : null}
                                  {mod.desconto > 0 ? <Text style={[modStyles.modValor, { color: colors.error }]}>-{formatBRL(mod.desconto)}</Text> : null}
                                </Pressable>
                              );
                            })}
                          </View>
                        );
                      })}
                  </View>
                  <View style={styles.modalBtns}>
                    <Pressable
                      onPress={() => { setModProd(null); setModCategorias([]); }}
                      style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}
                    >
                      <Text style={styles.secondaryBtnText}>Voltar</Text>
                    </Pressable>
                    <Pressable
                      onPress={handleConfirmarModificadores}
                      disabled={addingCodigo === modProd.codigo}
                      style={({ pressed }) => [styles.primaryBtn, (pressed || addingCodigo === modProd.codigo) && { opacity: 0.8 }]}
                      testID="painel-add-item-mod-confirm"
                    >
                      {addingCodigo === modProd.codigo ? (
                        <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                      ) : (
                        <Text style={styles.primaryBtnText}>Adicionar</Text>
                      )}
                    </Pressable>
                  </View>
                </View>
              </ScrollView>
            ) : (
              <>
                <View style={styles.searchWrap}>
                  <Ionicons name="search" size={16} color={colors.muted} />
                  <TextInput
                    value={prodTerm}
                    onChangeText={buscarProdutos}
                    placeholder="Buscar produto…"
                    placeholderTextColor={colors.muted}
                    style={styles.searchInput}
                    autoFocus
                    testID="painel-add-item-search"
                  />
                </View>
                {!buscandoProduto && pedidoProdutosAtuais.length > 0 ? (
                  <Text style={styles.resultSub}>Itens do pedido — toque em + pra repetir, ou busque outro produto</Text>
                ) : null}
                {prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
                <ScrollView style={{ maxHeight: 380 }}>
                  {listaProdutosExibida.map((p) => (
                    <View key={`${p.tipo}-${p.codigo}`} style={styles.resultRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.resultNome} numberOfLines={1}>{p.descricao}</Text>
                        <Text style={styles.resultSub}>{formatBRL(p.valor)}</Text>
                      </View>
                      <TextInput
                        value={getQty(p.codigo)}
                        onChangeText={(v) => setQtyByProduto((prev) => ({ ...prev, [p.codigo]: v }))}
                        selectTextOnFocus
                        keyboardType="numeric"
                        style={ps.qtyInput}
                        testID={`painel-add-item-qty-${p.codigo}`}
                      />
                      <Pressable
                        onPress={() => iniciarAddProduto(p)}
                        disabled={addingCodigo === p.codigo}
                        style={styles.quickAddBtn}
                        testID={`painel-add-item-pick-${p.codigo}`}
                      >
                        {addingCodigo === p.codigo ? (
                          <ActivityIndicator size="small" color={colors.onBrandPrimary} />
                        ) : (
                          <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
                        )}
                      </Pressable>
                    </View>
                  ))}
                  {!prodLoading && buscandoProduto && listaProdutosExibida.length === 0 ? (
                    <View style={styles.emptyBox}>
                      <Text style={styles.emptyText}>Nenhum produto encontrado.</Text>
                    </View>
                  ) : null}
                  {!prodLoading && !buscandoProduto && listaProdutosExibida.length === 0 ? (
                    <View style={styles.emptyBox}>
                      <Text style={styles.emptyText}>Nenhum item neste pedido ainda — busque um produto.</Text>
                    </View>
                  ) : null}
                </ScrollView>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* -------- Modal: faturar rápido -------- */}
      <Modal visible={faturarOpen} transparent animationType="slide" onRequestClose={() => setFaturarOpen(false)}>
        <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => setFaturarOpen(false)}>
          <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Faturar — Pedido {item.pedido}</Text>
              <Pressable onPress={() => setFaturarOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={ps.faturarCliente} numberOfLines={1}>{item.cliente_nome || "(sem cliente)"}</Text>
            <Text style={ps.faturarValor}>{formatBRL(item.total)}</Text>
            <ScrollView style={{ maxHeight: 300 }}>
              {formasPagamento.map((f) => {
                const sel = formaSel === f.codigo;
                return (
                  <Pressable
                    key={f.codigo}
                    onPress={() => setFormaSel(f.codigo)}
                    style={[ps.formaRow, sel && ps.formaRowSel]}
                    testID={`painel-faturar-forma-${f.codigo}`}
                  >
                    <Ionicons name={sel ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={ps.formaLabel}>{f.descricao}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            <View style={styles.modalBtns}>
              <Pressable onPress={() => setFaturarOpen(false)} style={[styles.secondaryBtn, { flex: 1, alignItems: "center" }]}>
                <Text style={styles.secondaryBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable
                onPress={handleFaturar}
                disabled={faturarSaving || !formaSel}
                style={[styles.primaryBtn, { flex: 1, opacity: !formaSel ? 0.6 : 1 }]}
                testID="painel-faturar-confirmar"
              >
                {faturarSaving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryBtnText}>Faturar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* -------- Imprimir conta -------- */}
      <ReciboPedidoModal
        visible={imprimirOpen}
        onClose={() => setImprimirOpen(false)}
        conn={conn}
        pedido={printPedido}
        cliente={printCliente}
        clienteResumo={printClienteResumo}
        it={{ itens: printItens, pedidoTotalizadoGrupos: printGrupos }}
      />

      {/* -------- Ticket de cozinha/bar (impressão automática por Finalidade) -------- */}
      <ReciboPedidoModal
        visible={!!printItem}
        onClose={() => setPrintItem(null)}
        conn={conn}
        pedido={printItemPedido}
        cliente={printItemCliente}
        clienteResumo={printItemClienteResumo}
        it={{ itens: [], pedidoTotalizadoGrupos: [] }}
        item={printItem}
      />
    </>
  );
}

const ps = StyleSheet.create({
  // Card o mais compacto possível (pedido explícito do usuário, 2026-07-17)
  // — 2 linhas de informação, sem rótulos, mais a barra de ações.
  // Largura-alvo fixa (não `flex:1`/`width:"100%"`) — o container pai
  // (`colCardsGrid` em app/pedidos.tsx) quebra linha em vez de esticar;
  // sem isso o card herdaria 100% da coluna e ficaria enorme quando poucos
  // tipos estão marcados no filtro (bug reportado com print, 2026-07-18).
  // `flexBasis`+`flexShrink` (não `width` rígido) porque as colunas
  // continuam lado a lado numa linha só, sem quebrar (pedido explícito do
  // usuário no mesmo dia) — com as 5 colunas de tipo ativas a coluna pode
  // ficar mais estreita que 280px; o card encolhe até `minWidth` em vez de
  // estourar a coluna. `flexGrow: 0` garante que nunca cresce além de
  // 280px quando a coluna é mais larga (poucos tipos ativos).
  card: {
    flexBasis: 280, flexGrow: 0, flexShrink: 1, minWidth: 220,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.border, padding: 6, gap: 3,
  },
  // Linha 1: [ícone] Nº · Cliente (esquerda) — Valor total (direita).
  line1: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 6 },
  line1Left: { flex: 1, minWidth: 0, flexDirection: "row", alignItems: "center", gap: 4 },
  line1Text: { fontSize: 13, fontWeight: "700" },
  // Wrapper do nome do cliente — position:relative pra ancorar o tooltip
  // com o nome completo (nome truncado em 1 linha no card compacto).
  // Pedido explícito do usuário, 2026-07-18.
  nomeWrap: { flex: 1, minWidth: 0, position: "relative" },
  nomeTooltip: {
    position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 20, maxWidth: 260,
  },
  line1Valor: { fontSize: 13, fontWeight: "700", flexShrink: 0 },
  // Linha 2: usuário · tempo aberto — qtd. pessoas (+/-), tudo sem rótulo.
  line2: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 6 },
  line2Text: { flex: 1, minWidth: 0, fontSize: 11 },
  pessoasStepper: { flexDirection: "row", alignItems: "center", gap: 2, flexShrink: 0 },
  pessoasValue: { fontSize: 11, fontWeight: "700", color: colors.onSurface, minWidth: 14, textAlign: "center" },
  actionsRow: { flexDirection: "row", gap: 4, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 4, marginTop: 1 },
  // Wrapper com position:relative pra ancorar o tooltip absoluto — mesmo
  // padrão já usado pela etiqueta de desconto em ItemList.tsx.
  actionWrap: { flex: 1, position: "relative" },
  actionBtn: {
    height: 28, borderRadius: radius.sm, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  tooltip: {
    position: "absolute", bottom: "100%", left: 0, right: 0, marginBottom: 4,
    alignItems: "center",
  },
  tooltipInner: {
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4, zIndex: 10,
  },
  tooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  faturarCliente: { fontSize: 13, fontWeight: "600", color: colors.onSurface, textAlign: "center", marginTop: -4, marginBottom: spacing.xs },
  faturarValor: { fontSize: 24, fontWeight: "700", color: colors.brandPrimary, textAlign: "center", marginBottom: spacing.sm },
  formaRow: { flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10, paddingHorizontal: 4 },
  formaRowSel: { backgroundColor: colors.brandTertiary, borderRadius: radius.sm },
  formaLabel: { fontSize: 14, color: colors.onSurface },
  // Qtd. digitável por produto, na lista do modal "Adicionar item".
  qtyInput: {
    width: 40, height: 32, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surface, textAlign: "center", fontSize: 13, color: colors.onSurface,
    marginRight: spacing.sm,
  },
  // Accordion "itens do pedido" — só expande a ALTURA do card (largura
  // herdada do card pai, nunca mexida). Pedido explícito do usuário,
  // 2026-07-18.
  itensAccordion: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: 4, paddingTop: 4, gap: 3 },
  itensAccordionEmpty: { fontSize: 11, color: colors.muted, textAlign: "center", paddingVertical: 4 },
  itensAccordionRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  // Wrapper com position:relative pra ancorar o tooltip com o nome completo
  // do item (a descrição trunca em 1 linha na largura estreita do card) —
  // mesmo padrão do tooltip do nome do cliente em line1. Pedido explícito
  // do usuário, 2026-07-18.
  itensAccordionDescWrap: { flex: 1, minWidth: 0, position: "relative" },
  itensAccordionDescTooltip: { position: "absolute", top: "100%", left: 0, marginTop: 4, zIndex: 20, maxWidth: 220 },
  itensAccordionDesc: { fontSize: 11, color: colors.onSurface },
  itensAccordionQtd: { fontSize: 11, color: colors.muted, minWidth: 22, textAlign: "right" },
  itensAccordionPrintBtn: { padding: 2 },
  itensAccordionValor: { fontSize: 11, fontWeight: "600", color: colors.onSurface, minWidth: 56, textAlign: "right" },
});

// Mesmo desenho do seletor de Modificadores de AddItemModal.tsx (não
// exportado de lá — duplicado aqui de propósito, mesmo motivo já documentado
// no topo do arquivo pra outras funções deste card: instanciar um hook/
// componente maior por card sairia mais caro do que replicar este trecho
// pequeno).
const modStyles = StyleSheet.create({
  wrap: { gap: spacing.sm, marginTop: 4 },
  categoria: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    padding: spacing.sm, gap: 4,
  },
  categoriaHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  categoriaNome: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  badge: { borderRadius: radius.pill, paddingHorizontal: 8, paddingVertical: 2 },
  badgeObrig: { backgroundColor: "#FDECEC" },
  badgeOpc: { backgroundColor: colors.brandTertiary },
  badgeText: { fontSize: 10, fontWeight: "700" },
  badgeTextObrig: { color: colors.error },
  badgeTextOpc: { color: colors.brandPrimary },
  avisoFaltando: { fontSize: 11, color: colors.error },
  modRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6 },
  modNome: { flex: 1, fontSize: 13, color: colors.onSurface },
  modValor: { fontSize: 12, fontWeight: "600", color: colors.success },
});
