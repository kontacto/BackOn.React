// Hook que encapsula estado e regras dos ITENS do pedido + descontos
// (item, geral) e relatório de descontos. Mantém a lógica idêntica à tela
// original; a tela apenas orquestra e renderiza os componentes.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Platform } from "react-native";
import { useFocusEffect } from "expo-router";

import { apiGet, apiSend, apiDelete, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { formatBRL, parseNum, fmtNum, fmtMoney2, calcDescUnit } from "@/src/utils/format";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { ItemRow, ItemPrintData, ProdutoServico, DescontoRow, ToastTone, TipoPrecoM2 } from "./types";

// Unidades que ativam o comportamento m²/ml/m³ (Fase B — módulo Metro
// Quadrado, `pecas.uni`) — mesma checagem do legado
// (`Trim(tb("uni")) = "M2" Or ... = "ML" Or ... = "M3"`).
const UNIDADES_M2 = ["M2", "ML", "M3"];

type Params = {
  conn: Connection | null;
  editing: boolean;
  pedidoId: number | null;
  isAberto: boolean;
  usuarioCod: number;
  funcaoCod: number;
  classe: number | null;
  // Master (KONTACTO) bypassa a checagem de permissão AGENDAR no backend —
  // mesmo padrão de `master` já usado em Faturar/Reabrir/Cancelar
  // (pedido-geral.tsx). Default false; só o Pedido Geral usa Agendar hoje.
  master?: boolean;
  showToast: (m: string, t?: ToastTone) => void;
  // Módulo "Serviços" (Configurações > Módulos e Recursos) — desligado,
  // a busca de item só retorna produtos (tipo=P), nunca serviços.
  servicosOn: boolean;
  // Prefixo da API — "/api/pedidos" (rápido, default) ou "/api/pedido-completo"
  // (Pedido Completo web, mesma tabela pedido_venda_prod, resolução de
  // produto mais rica + expansão de kit no backend, transparente aqui).
  basePath?: string;
  // Impressão automática de item por Finalidade (FrmManPedBar.frm,
  // Command1_Click) — trazida do Pedido Bar pro Pedido Completo/Geral
  // 2026-07-20 (pedido explícito do usuário: "as funções do pedido bar,
  // com exceção da taxa de serviço"). Sem equivalente na O.S. ainda.
  // Default false.
  printPorFinalidade?: boolean;
};

export function usePedidoItens({
  conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, master = false, showToast, servicosOn,
  basePath = "/api/pedidos", printPorFinalidade = false,
}: Params) {
  const { showConfirm } = useFeedback();
  // -------- Itens do pedido
  const [itens, setItens] = useState<ItemRow[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [itensLoading, setItensLoading] = useState(false);

  // Modal de adicionar item (busca produto/serviço)
  const [addOpen, setAddOpen] = useState(false);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoServico[]>([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [selProd, setSelProd] = useState<ProdutoServico | null>(null);
  const [addQtd, setAddQtd] = useState("1");
  const [addValor, setAddValor] = useState("0,00");
  // Variação de Preço (Promoção, `pecas_promocao`) aplicável ao produto+
  // quantidade+momento atual, ver `verificarPromocao` abaixo — `null` quando
  // nenhuma bate. Só informativo (mostrado no "Confirmar Item"); o valor em
  // si já foi sugerido em `addValor` quando encontrado.
  const [promoAplicada, setPromoAplicada] = useState<{ codigo_promocao: string; descricao_promocao: string; p_venda: number } | null>(null);
  // Último valor SUGERIDO automaticamente (base do produto ou promoção) —
  // usado só pra saber se o atendente já digitou um valor manual por cima
  // (nesse caso a mudança de quantidade não sobrescreve o que foi digitado).
  const autoValorRef = useRef<number | null>(null);
  const [addDescPct, setAddDescPct] = useState("");
  const [addDescRs, setAddDescRs] = useState("");
  const [addAcr, setAddAcr] = useState("");
  const [addCompl, setAddCompl] = useState("");
  const [addSaving, setAddSaving] = useState(false);
  // Número de série escolhido (pecas_num_serie.codigo) — só usado pelo
  // Pedido Geral (PEDIDO_COMP) quando `selProd.controla_num_serie` é true
  // (Fase B, ver AddItemModal.tsx). `null` = nenhum escolhido ainda/produto
  // não controla série; o Pedido Bar nunca seta isso.
  const [selNumSerie, setSelNumSerie] = useState<number | null>(null);

  // Metro Quadrado (Fase B, ver AddItemModal.tsx) — só usado pelo Pedido
  // Geral quando `selProd.unidade` é M2/ML/M3. `precosM2` vem de
  // `GET /produtos/{codigo}/tipos-preco-m2` (só tipos com preço > 0
  // cadastrado); `previewM2` vem de `preco-m2-preview`, recalculado a cada
  // mudança de tipo/dimensão (debounce), pra mostrar o valor real sem
  // duplicar `_area_preco`/`ArredondaPBox` em JS.
  const [precosM2, setPrecosM2] = useState<TipoPrecoM2[]>([]);
  const [precosM2Loading, setPrecosM2Loading] = useState(false);
  // "Controla cabeça de chapa" (controle_aux.vidro_controla_cabeca_chapa) —
  // decide se a tela mostra os campos avançados Comprimento/Largura de
  // Chapa (empresas de vidro que arredondam pra tamanho padrão de chapa).
  const [vidroControlaCabecaChapa, setVidroControlaCabecaChapa] = useState(false);
  const [addTipoPrecoM2, setAddTipoPrecoM2] = useState<number | null>(null);
  const [addComprimento, setAddComprimento] = useState("");
  const [addLargura, setAddLargura] = useState("");
  const [addComprimentoChapa, setAddComprimentoChapa] = useState("");
  const [addLarguraChapa, setAddLarguraChapa] = useState("");
  const [previewM2, setPreviewM2] = useState<{ area_venda: number; valor_unitario: number } | null>(null);
  const [previewM2Loading, setPreviewM2Loading] = useState(false);

  // Ticket de impressão de um item só (ReciboPedidoModal em modo item) —
  // aberto manualmente pelo botão "Imprimir" de cada linha, ou
  // automaticamente por `checkAutoPrintItem` (ver abaixo).
  const [printItem, setPrintItem] = useState<ItemPrintData | null>(null);

  // Impressão automática de item por Finalidade (FrmManPedBar.frm,
  // Command1_Click, ver `CarregaImpressorasDirecionadas`) — ao incluir um
  // item cuja Finalidade (pecas.tipo_peca) tem impressora configurada em
  // Controle do Sistema > Impressoras por Grupo de Produtos: "automatica"
  // marcada abre o ticket sozinho, sem marcada pergunta antes ("Imprimir
  // este item para <Finalidade>?", mesmo texto do MsgBox legado), sem
  // registro pra aquela Finalidade não faz nada. Nunca trava o fluxo de
  // adicionar item se a checagem falhar (best-effort).
  const checkAutoPrintItem = async (item: ItemPrintData, tipoPeca: number | null) => {
    if (!printPorFinalidade || !conn || tipoPeca == null) return;
    try {
      const j = await apiGet(conn, "/api/controle-sistema/direcionamento-impressora/por-finalidade", {
        tipo: tipoPeca,
      });
      if (!j?.success || !j.configurado) return;
      if (j.automatica) {
        setPrintItem(item);
      } else {
        showConfirm(`Imprimir este item para ${item.finalidade_descricao || "impressão"}?`, () => setPrintItem(item));
      }
    } catch {
      // silencioso — não pode travar o fluxo de adicionar item
    }
  };

  // Agendar item de Serviço (Fase B — módulo Clínica, `AGENDA`/
  // `AGENDA_PEDIDO`) — item atualmente sendo agendado (abre AgendarModal),
  // lista de profissionais elegíveis pro serviço daquele item, e as ações
  // de gravar/cancelar. Só o Pedido Geral (PEDIDO_COMP) usa isso, gated por
  // `moduleOn("CLINICA")` na tela. Ver PENDENCIAS.md > "Transações" >
  // "Pedido Geral — Fase B: Clínica (Agendamento)".
  const [agendarItem, setAgendarItemState] = useState<ItemRow | null>(null);
  const [profissionaisAgenda, setProfissionaisAgenda] = useState<{ codigo: number; nome_guerra: string }[]>([]);
  const [profissionaisLoading, setProfissionaisLoading] = useState(false);
  const [agendaSaving, setAgendaSaving] = useState(false);

  const setAgendarItem = (item: ItemRow | null) => {
    setAgendarItemState(item);
    setProfissionaisAgenda([]);
    if (item && conn) {
      setProfissionaisLoading(true);
      apiGet(conn, "/api/agenda/profissionais", { servico: item.produto })
        .then((j) => { if (j?.success) setProfissionaisAgenda(j.items || []); })
        .catch(() => {})
        .finally(() => setProfissionaisLoading(false));
    }
  };

  const salvarAgendamento = async (payload: {
    funcionario: number; data: string; hora_ini: string;
    situacao_atendimento?: string; revisao?: boolean;
    descartavel_valor?: number | null; descartavel_obs?: string;
    hora_chegada?: string | null; hora_saida?: string | null;
    autorizado_por?: string;
  }) => {
    if (!conn || !agendarItem) return;
    setAgendaSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/item/${agendarItem.codauto}`, "POST", {
        ...payload,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao agendar."), "error"); return false; }
      showToast("Item agendado.", "success");
      setAgendarItemState(null);
      loadItens();
      return true;
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao agendar."), "error");
      return false;
    } finally { setAgendaSaving(false); }
  };

  // Troca de Profissional (exige autorização de gerente/supervisor/master,
  // validada no `AuthorizationSlide` — `autorizadoPor` só registra QUEM
  // autorizou, o backend não reverifica senha, ver `agenda_service.py`).
  const trocarProfissionalAgenda = async (novoFuncionario: number, autorizadoPor: string) => {
    if (!conn || !agendarItem?.agendamento) return false;
    setAgendaSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/${agendarItem.agendamento.codagenda}/trocar-profissional`, "POST", {
        novo_funcionario: novoFuncionario, autorizado_por: autorizadoPor,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao trocar profissional."), "error"); return false; }
      showToast("Profissional trocado.", "success");
      loadItens();
      return true;
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao trocar profissional."), "error");
      return false;
    } finally { setAgendaSaving(false); }
  };

  const cancelarAgendamento = async () => {
    if (!conn || !agendarItem) return;
    setAgendaSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/item/${agendarItem.codauto}/cancelar`, "POST", {
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao cancelar agendamento."), "error"); return; }
      showToast("Agendamento cancelado.", "success");
      setAgendarItemState(null);
      loadItens();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao cancelar agendamento."), "error");
    } finally { setAgendaSaving(false); }
  };

  // Modal de editar item existente
  const [editItem, setEditItem] = useState<ItemRow | null>(null);
  const [editQtd, setEditQtd] = useState("1");
  const [editValor, setEditValor] = useState("0,00");
  const [editDescPct, setEditDescPct] = useState("");
  const [editDescRs, setEditDescRs] = useState("");
  const [editAcr, setEditAcr] = useState("");
  const [editCompl, setEditCompl] = useState("");
  const [editSaving, setEditSaving] = useState(false);
  // Metro Quadrado — mesma ideia do "Confirmar Item", mas pra reeditar um
  // item m² já gravado. O tipo de preço usado originalmente não fica
  // salvo na linha (mesmo comportamento do legado — é resolvido na hora e
  // descartado), por isso o atendente sempre reescolhe o tipo ao editar;
  // comprimento/largura já vêm pré-preenchidos do item atual.
  const [editPrecosM2, setEditPrecosM2] = useState<TipoPrecoM2[]>([]);
  const [editTipoPrecoM2, setEditTipoPrecoM2] = useState<number | null>(null);
  const [editComprimento, setEditComprimento] = useState("");
  const [editLargura, setEditLargura] = useState("");
  const [editPreviewM2, setEditPreviewM2] = useState<{ area_venda: number; valor_unitario: number } | null>(null);
  const [editPreviewM2Loading, setEditPreviewM2Loading] = useState(false);

  // Modal relatório de descontos
  const [descModalOpen, setDescModalOpen] = useState(false);
  const [descItems, setDescItems] = useState<DescontoRow[]>([]);
  const [descTotalApi, setDescTotalApi] = useState(0);
  const [descLoading, setDescLoading] = useState(false);

  // Desconto geral sobre o total
  const [geralModalOpen, setGeralModalOpen] = useState(false);
  const [geralValor, setGeralValor] = useState("");
  const [geralAtual, setGeralAtual] = useState(0);
  const [geralLimite, setGeralLimite] = useState(100);
  const [geralSaving, setGeralSaving] = useState(false);

  const descTotalItens = useMemo(
    () => itens.reduce((s, it) => s + (it.desconto || 0) * (it.qtd || 0), 0),
    [itens]
  );

  // "Pedido Totalizado [F9]" (FrmManPedBar.frm, Command65_Click) — não é só
  // uma lista de produtos, é o TOTAL de cada produto: agrupa por produto
  // (somando quantidade e valor, mesmo que o preço unitário tenha variado
  // entre inclusões — ex. desconto aplicado diferente em rodadas
  // separadas) em vez de uma linha por inclusão crua. Puramente derivado
  // dos itens já carregados — sem chamada à API, é só um relatório
  // read-only sobre dados que já estão na tela.
  const [pedidoTotalizadoOpen, setPedidoTotalizadoOpen] = useState(false);

  const pedidoTotalizadoGrupos = useMemo(() => {
    const grupos = new Map<string, { produto: string; cod_fab: string; descricao: string; qtd: number; valorTotal: number }>();
    for (const item of itens) {
      const totalLinha = item.qtd * item.valor_unitario;
      const atual = grupos.get(item.produto);
      if (atual) {
        atual.qtd += item.qtd;
        atual.valorTotal += totalLinha;
      } else {
        grupos.set(item.produto, {
          produto: item.produto, cod_fab: item.cod_fab, descricao: item.descricao,
          qtd: item.qtd, valorTotal: totalLinha,
        });
      }
    }
    return Array.from(grupos.values());
  }, [itens]);

  const pedidoTotalizadoTotal = useMemo(
    () => pedidoTotalizadoGrupos.reduce((s, g) => s + g.valorTotal, 0),
    [pedidoTotalizadoGrupos]
  );

  const baseGeral = useMemo(
    () => itens.reduce((s, it) => s + (it.p_normal || 0) * (it.qtd || 0), 0),
    [itens]
  );

  // -------- Itens do pedido (carrega só em modo edição)
  const loadItens = useCallback(async () => {
    if (!conn || !editing || !pedidoId) return;
    setItensLoading(true);
    try {
      const j = await apiGet(conn, `${basePath}/${pedidoId}/itens`);
      if (j?.success) {
        setItens(j.items || []);
        setSubtotal(j.subtotal || 0);
      }
    } catch {
      // silencioso
    } finally {
      setItensLoading(false);
    }
  }, [conn, editing, pedidoId, basePath]);

  // Recarrega itens ao focar a tela (ex.: voltar da lista de produtos)
  useFocusEffect(
    useCallback(() => {
      loadItens();
    }, [loadItens])
  );

  // Busca de produto/serviço em si — extraída da debounce abaixo pra também
  // poder ser chamada direto no Enter (bypass do debounce, mesmo
  // comportamento do KPDV — ver comentário da debounce mais abaixo).
  // Retorna os itens encontrados (não só popula o state) pra quem chamou
  // poder decidir na hora — ex.: 1 resultado só pula direto pra "Confirmar
  // Item" (`AddItemModal.tsx`). `buscaReqIdRef` descarta resultado de uma
  // busca já superada por uma mais nova (usuário continuou digitando
  // enquanto a resposta anterior ainda não tinha voltado) — mesmo
  // raciocínio do `CancellationTokenSource` do KPDV
  // (`VendaViewModel.BuscarAsync`), só que sem abortar a requisição HTTP
  // em si (`apiGet` não suporta `AbortSignal` hoje), só ignorando a
  // resposta se ela já estiver desatualizada.
  const buscaReqIdRef = useRef(0);
  const buscarProdutos = useCallback(async (termo: string): Promise<ProdutoServico[]> => {
    if (!conn || !termo.trim()) { setProdResults([]); return []; }
    const meuId = ++buscaReqIdRef.current;
    setProdLoading(true);
    try {
      const j = await apiGet(conn, `/api/produtos-servicos`, {
        search: termo, page: 1, size: 30, tipo: servicosOn ? "all" : "P",
      });
      const items: ProdutoServico[] = j?.items || [];
      if (buscaReqIdRef.current === meuId) setProdResults(items);
      return items;
    } catch {
      if (buscaReqIdRef.current === meuId) setProdResults([]);
      return [];
    } finally {
      if (buscaReqIdRef.current === meuId) setProdLoading(false);
    }
  }, [conn, servicosOn]);

  // Variação de Preço (Promoção) aplicável agora pro produto+quantidade
  // informados — consulta `GET /produtos/{codigo}/preco-promocional`
  // (`pedido_common._preco_promocional`, dias da semana/período de data/
  // período de hora, todos opcionais e combináveis). Só produtos (tipo "P")
  // têm promoção — serviço nunca chama a API. Best-effort: qualquer falha
  // (rede, produto sem promoção) resulta em `null`, nunca trava o fluxo de
  // adicionar item.
  const verificarPromocao = useCallback(async (p: ProdutoServico, qtd: number) => {
    if (!conn || p.tipo !== "P" || !qtd || qtd <= 0) return null;
    try {
      const j = await apiGet(conn, `/api/produtos/${encodeURIComponent(p.codigo)}/preco-promocional`, { qtd });
      return j?.success && j.promocao ? (j.promocao as { codigo_promocao: string; descricao_promocao: string; p_venda: number }) : null;
    } catch {
      return null;
    }
  }, [conn]);

  // Metro Quadrado — tipos de preço disponíveis pro produto (só os
  // cadastrados com valor > 0, ver `TIPOS_PRECO_M2` em pedido_common.py).
  // `eh_produto_m2` decide se o "Confirmar Item" mostra os campos de m²
  // (Comprimento/Largura + seletor de tipo) no lugar do "Valor unitário"
  // de digitação livre.
  const ehProdutoM2 = useCallback((p: ProdutoServico | null) => {
    return !!p && p.tipo === "P" && UNIDADES_M2.includes((p.unidade || "").toUpperCase());
  }, []);

  const buscarTiposPrecoM2 = useCallback(async (codigo: string) => {
    if (!conn) return [];
    setPrecosM2Loading(true);
    try {
      const j = await apiGet(conn, `/api/produtos/${encodeURIComponent(codigo)}/tipos-preco-m2`);
      const items: TipoPrecoM2[] = j?.success ? j.items || [] : [];
      setPrecosM2(items);
      setVidroControlaCabecaChapa(!!j?.vidro_controla_cabeca_chapa);
      return items;
    } catch {
      setPrecosM2([]);
      setVidroControlaCabecaChapa(false);
      return [];
    } finally {
      setPrecosM2Loading(false);
    }
  }, [conn]);

  // -------- Busca produto/serviço (debounce) dentro do modal de adicionar.
  // Com o campo de busca vazio, a lista padrão exibida é a dos itens já no
  // pedido (`pedidoProdutos` abaixo) — só dispara a busca na API quando o
  // usuário efetivamente digita algo. Padronizado com a busca de produto do
  // KPDV (pedido explícito do usuário, 2026-08-26 — "temos que padronizar
  // essas buscas como a busca de produtos do KPDV"): debounce de 350ms
  // (`VendaViewModel.BuscarAsync`, KPDV) contado a partir da ÚLTIMA tecla —
  // nunca precisa de Enter pra buscar em nenhuma tela (Bar, Geral ou O.S.).
  // Isso reverte a exceção "só busca no Enter" que existia só pro Pedido
  // Geral desde 2026-07-20 — decisão revista pelo próprio usuário nesta
  // rodada, parâmetro `buscaProdutoSoEnter` removido (não é mais lido em
  // lugar nenhum).
  useEffect(() => {
    if (!addOpen || !conn || !prodTerm.trim()) {
      setProdResults([]);
      return;
    }
    const t = setTimeout(() => { buscarProdutos(prodTerm); }, 350);
    return () => clearTimeout(t);
  }, [prodTerm, addOpen, conn, servicosOn, buscarProdutos]);

  // Itens já lançados no pedido, deduplicados por produto — lista padrão do
  // modal de Adicionar Item enquanto a busca está vazia (facilita repetir um
  // item já pedido, ex.: mais uma rodada da mesma bebida). Taxa de Serviço
  // (S002) fica de fora dessa lista — ela tem fluxo próprio (botão "Tx
  // Serviço", idempotente) e não pode ser adicionada de novo por aqui, só
  // atualizada; outros serviços continuam aparecendo normalmente.
  const pedidoProdutos = useMemo<ProdutoServico[]>(() => {
    const porCodigo = new Map<string, ProdutoServico>();
    for (const it of itens) {
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
          imagem_codigo: it.imagem_codigo,
        });
      }
    }
    return Array.from(porCodigo.values());
  }, [itens]);

  const openAddModal = () => {
    setSelProd(null);
    setProdTerm("");
    setProdResults([]);
    setAddQtd("1");
    setAddValor("0,00");
    setAddCompl("");
    setSelNumSerie(null);
    setPromoAplicada(null);
    autoValorRef.current = null;
    setPrecosM2([]);
    setVidroControlaCabecaChapa(false);
    setAddTipoPrecoM2(null);
    setAddComprimento(""); setAddLargura("");
    setAddComprimentoChapa(""); setAddLarguraChapa("");
    setPreviewM2(null);
    setAddOpen(true);
  };

  const pickProduto = (p: ProdutoServico) => {
    setSelProd(p);
    setAddQtd("1");
    setAddDescPct(""); setAddDescRs(""); setAddAcr("");
    setAddCompl("");
    setSelNumSerie(null);
    setPromoAplicada(null);
    setPrecosM2([]);
    setAddTipoPrecoM2(null);
    setAddComprimento(""); setAddLargura("");
    setAddComprimentoChapa(""); setAddLarguraChapa("");
    setPreviewM2(null);

    if (ehProdutoM2(p)) {
      // Metro Quadrado: o "Valor unitário" não é digitado — vem do tipo de
      // preço escolhido × área calculada (ver `previewM2` abaixo). Só busca
      // os tipos disponíveis; nada a sugerir em `addValor` ainda.
      setAddValor("0,00");
      autoValorRef.current = null;
      buscarTiposPrecoM2(p.codigo);
      return;
    }

    const valorBase = p.valor;
    setAddValor(formatBRL(valorBase).replace("R$", "").trim());
    autoValorRef.current = valorBase;
    // Verifica Variação de Preço pra qtd=1 (o default) assim que o produto é
    // escolhido — se bater, já sugere o preço promocional no lugar do preço
    // base. Assíncrono de propósito: não atrasa a seleção do produto em si.
    verificarPromocao(p, 1).then((promo) => {
      if (!promo) return;
      setPromoAplicada(promo);
      autoValorRef.current = promo.p_venda;
      setAddValor(formatBRL(promo.p_venda).replace("R$", "").trim());
    });
  };

  // Reconfere a Variação de Preço sempre que a quantidade muda (debounce
  // 400ms) — tiers de promoção são "a partir de N unidades", então trocar a
  // quantidade pode ligar/desligar/trocar qual linha se aplica. Só
  // atualiza `addValor` sozinho quando o valor atual ainda é o último
  // sugerido automaticamente (`autoValorRef`) — se o atendente já digitou
  // um valor manual por cima, a sugestão de promoção não é mais forçada,
  // só o aviso (`promoAplicada`) é atualizado.
  useEffect(() => {
    if (!addOpen || !selProd || selProd.tipo !== "P" || ehProdutoM2(selProd)) return;
    const qtd = parseNum(addQtd);
    if (qtd <= 0) return;
    const t = setTimeout(() => {
      verificarPromocao(selProd, qtd).then((promo) => {
        const novoBase = promo ? promo.p_venda : selProd.valor;
        const valorAtual = parseNum(addValor);
        const semDivergencia = autoValorRef.current == null || Math.abs(valorAtual - autoValorRef.current) < 0.005;
        setPromoAplicada(promo);
        if (semDivergencia && Math.abs(valorAtual - novoBase) >= 0.005) {
          setAddValor(formatBRL(novoBase).replace("R$", "").trim());
        }
        autoValorRef.current = novoBase;
      });
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addQtd, addOpen, selProd, verificarPromocao]);

  // Metro Quadrado — recalcula o preview (área calculada × preço do tipo
  // escolhido) sempre que tipo/comprimento/largura/chapa mudam (debounce
  // 300ms). `addValor` acompanha o preview — mesmo campo que o resumo
  // "Confirmar Item" já lê pra mostrar o total, só que aqui é sempre
  // computado (não editável pelo atendente, ver AddItemModal.tsx).
  useEffect(() => {
    if (!addOpen || !selProd || !ehProdutoM2(selProd) || addTipoPrecoM2 == null) { setPreviewM2(null); return; }
    const comprimento = parseNum(addComprimento);
    const largura = parseNum(addLargura);
    if (comprimento <= 0 || largura <= 0) { setPreviewM2(null); return; }
    const t = setTimeout(async () => {
      if (!conn) return;
      setPreviewM2Loading(true);
      try {
        const j = await apiGet(conn, `/api/produtos/${encodeURIComponent(selProd.codigo)}/preco-m2-preview`, {
          tipo_preco: addTipoPrecoM2, comprimento, largura,
          comprimento_chapa: parseNum(addComprimentoChapa) || undefined,
          largura_chapa: parseNum(addLarguraChapa) || undefined,
          controla_num_serie: !!selProd.controla_num_serie,
        });
        if (j?.success) {
          setPreviewM2({ area_venda: j.area_venda, valor_unitario: j.valor_unitario });
          setAddValor(formatBRL(j.valor_unitario).replace("R$", "").trim());
        } else {
          setPreviewM2(null);
        }
      } catch {
        setPreviewM2(null);
      } finally {
        setPreviewM2Loading(false);
      }
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [addOpen, selProd, addTipoPrecoM2, addComprimento, addLargura, addComprimentoChapa, addLarguraChapa, conn]);

  // `extra` — contribuição do seletor de Modificadores (Fase 2, Pedido Bar,
  // ver AddItemModal.tsx): acréscimo/desconto UNITÁRIO somado ao que o
  // usuário já digitou nos campos manuais, e um texto extra pra anexar ao
  // Complemento (por enquanto é isso que sai impresso como "Obs" do item —
  // pedido explícito do usuário, 2026-07-23). `undefined` = comportamento
  // idêntico ao de antes (Pedido Geral/O.S., ainda sem seletor).
  const handleAddItem = async (extra?: { acrescimoExtra?: number; descontoExtra?: number; complementoExtra?: string }) => {
    if (!conn || !pedidoId || !selProd) return;
    // Produto com controla_num_serie sempre lança 1 unidade (mesma regra do
    // `Campo(4) = 1` do legado ao escolher o número de série) — o backend já
    // força isso também, este é só um segundo checo pra não mandar uma
    // quantidade errada na tela antes de validar.
    const qtd = selProd.controla_num_serie ? 1 : parseNum(addQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    if (selProd.controla_num_serie && !selNumSerie) {
      showToast("Selecione um número de série disponível para este produto.", "error");
      return;
    }
    const eM2 = ehProdutoM2(selProd);
    if (eM2 && (addTipoPrecoM2 == null || parseNum(addComprimento) <= 0 || parseNum(addLargura) <= 0)) {
      showToast("Informe o tipo de preço e as dimensões (comprimento/largura) para este produto.", "error");
      return;
    }
    const pNormal = parseNum(addValor);
    const descUnit = calcDescUnit(pNormal, addDescPct, addDescRs) + (extra?.descontoExtra || 0);
    const acr = parseNum(addAcr) + (extra?.acrescimoExtra || 0);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    const complemento = extra?.complementoExtra
      ? (addCompl.trim() ? `${addCompl.trim()} | ${extra.complementoExtra}` : extra.complementoExtra)
      : addCompl;
    setAddSaving(true);
    try {
      const j = await apiSend(conn, `${basePath}/${pedidoId}/itens`, "POST", {
        produto: selProd.codigo,
        qtd,
        valor_unitario: pNormal,
        desconto: descUnit,
        desconto_pct: parseNum(addDescPct),
        acrescimo: acr,
        usuario_codigo: usuarioCod,
        funcao: funcaoCod,
        classe,
        plataforma: Platform.OS,
        complemento,
        ...(selNumSerie ? { cod_num_serie: selNumSerie } : {}),
        ...(eM2 ? {
          tipo_preco_m2: addTipoPrecoM2,
          comprimento: parseNum(addComprimento),
          largura: parseNum(addLargura),
          ...(parseNum(addComprimentoChapa) > 0 ? { comprimento_chapa: parseNum(addComprimentoChapa) } : {}),
          ...(parseNum(addLarguraChapa) > 0 ? { largura_chapa: parseNum(addLarguraChapa) } : {}),
        } : {}),
      });
      if (!j?.success) { showToast(j?.message || "Falha ao adicionar.", "error"); }
      else {
        setAddOpen(false);
        showToast("Item adicionado.", "success");
        loadItens();
        if (j.item) checkAutoPrintItem(j.item, j.tipo_peca ?? null);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setAddSaving(false); }
  };

  // Adiciona o item direto na lista (qtd=1, valor cheio, sem desconto/
  // acréscimo), sem passar pela tela "Confirmar Item" — acionado pelo botão
  // "+" na linha da busca. Mantém o modal aberto pra permitir adicionar
  // vários itens em sequência.
  const quickAddItem = async (p: ProdutoServico) => {
    if (!conn || !pedidoId) return;
    setAddSaving(true);
    try {
      const promo = await verificarPromocao(p, 1);
      const j = await apiSend(conn, `${basePath}/${pedidoId}/itens`, "POST", {
        produto: p.codigo,
        qtd: 1,
        valor_unitario: promo ? promo.p_venda : p.valor,
        desconto: 0,
        desconto_pct: 0,
        acrescimo: 0,
        usuario_codigo: usuarioCod,
        funcao: funcaoCod,
        classe,
        plataforma: Platform.OS,
        complemento: "",
      });
      if (!j?.success) { showToast(j?.message || "Falha ao adicionar.", "error"); }
      else {
        showToast(`${p.descricao} adicionado.`, "success");
        loadItens();
        if (j.item) checkAutoPrintItem(j.item, j.tipo_peca ?? null);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setAddSaving(false); }
  };

  const openEditModal = (it: ItemRow) => {
    if (!isAberto) { showToast("Pedido não pode ser alterado.", "error"); return; }
    setEditItem(it);
    setEditQtd(fmtNum(it.qtd));
    setEditValor(formatBRL(it.p_normal || it.valor_unitario).replace("R$", "").trim());
    setEditDescPct("");
    setEditDescRs(it.desconto > 0 ? fmtMoney2(it.desconto) : "");
    setEditAcr(it.acrescimo > 0 ? fmtMoney2(it.acrescimo) : "");
    setEditCompl(it.complemento || "");
    setEditPrecosM2([]);
    setEditTipoPrecoM2(null);
    setEditPreviewM2(null);
    if (it.comprimento && it.largura) {
      setEditComprimento(fmtNum(it.comprimento));
      setEditLargura(fmtNum(it.largura));
      buscarTiposPrecoM2(it.produto).then((items) => setEditPrecosM2(items));
    } else {
      setEditComprimento("");
      setEditLargura("");
    }
  };

  // Reeditar item m² — recalcula o preview sempre que tipo/dimensão muda
  // (debounce 300ms), mesmo princípio do "Confirmar Item".
  useEffect(() => {
    if (!editItem || !editItem.comprimento || !editItem.largura || editTipoPrecoM2 == null) { setEditPreviewM2(null); return; }
    const comprimento = parseNum(editComprimento);
    const largura = parseNum(editLargura);
    if (comprimento <= 0 || largura <= 0) { setEditPreviewM2(null); return; }
    const t = setTimeout(async () => {
      if (!conn) return;
      setEditPreviewM2Loading(true);
      try {
        const j = await apiGet(conn, `/api/produtos/${encodeURIComponent(editItem.produto)}/preco-m2-preview`, {
          tipo_preco: editTipoPrecoM2, comprimento, largura,
        });
        if (j?.success) {
          setEditPreviewM2({ area_venda: j.area_venda, valor_unitario: j.valor_unitario });
          setEditValor(formatBRL(j.valor_unitario).replace("R$", "").trim());
        } else {
          setEditPreviewM2(null);
        }
      } catch {
        setEditPreviewM2(null);
      } finally {
        setEditPreviewM2Loading(false);
      }
    }, 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editItem, editTipoPrecoM2, editComprimento, editLargura, conn]);

  const handleUpdateItem = async () => {
    if (!conn || !pedidoId || !editItem) return;
    const qtd = parseNum(editQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const eM2 = !!(editItem.comprimento && editItem.largura);
    if (eM2 && (editTipoPrecoM2 == null || parseNum(editComprimento) <= 0 || parseNum(editLargura) <= 0)) {
      showToast("Informe o tipo de preço e as dimensões (comprimento/largura) para este produto.", "error");
      return;
    }
    const pNormal = parseNum(editValor);
    const descUnit = calcDescUnit(pNormal, editDescPct, editDescRs);
    const acr = parseNum(editAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setEditSaving(true);
    try {
      const j = await apiSend(conn, `${basePath}/${pedidoId}/itens/${editItem.codauto}`, "PUT", {
        qtd,
        valor_unitario: pNormal,
        complemento: editCompl,
        desconto: descUnit,
        desconto_pct: parseNum(editDescPct),
        acrescimo: acr,
        usuario_codigo: usuarioCod,
        funcao: funcaoCod,
        classe,
        plataforma: Platform.OS,
        ...(eM2 ? {
          tipo_preco_m2: editTipoPrecoM2,
          comprimento: parseNum(editComprimento),
          largura: parseNum(editLargura),
        } : {}),
      });
      if (!j?.success) { showToast(j?.message || "Falha ao salvar.", "error"); }
      else {
        setEditItem(null);
        showToast("Item atualizado.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  const handleDeleteItem = async (it: ItemRow) => {
    if (!conn || !pedidoId) return;
    setEditSaving(true);
    try {
      const j = await apiDelete(conn, `${basePath}/${pedidoId}/itens/${it.codauto}`, {
        usuario_alteracao: usuarioCod, classe: classe ?? undefined, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao remover.", "error"); }
      else {
        setEditItem(null);
        showToast(
          j.devolvido_para ? `Item devolvido para o Pedido nº ${j.devolvido_para}.` : "Item removido.",
          "success"
        );
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  const openDescontos = async () => {
    if (!conn || !pedidoId) return;
    setDescModalOpen(true);
    setDescLoading(true);
    try {
      const j = await apiGet(conn, `${basePath}/${pedidoId}/descontos`);
      if (j?.success) {
        setDescItems(j.items || []);
        setDescTotalApi(j.total || 0);
      }
    } catch {
      // silencioso
    } finally { setDescLoading(false); }
  };

  const openGeralModal = async () => {
    if (!conn || !pedidoId) return;
    setGeralModalOpen(true);
    try {
      const [rl, rd] = await Promise.all([
        apiGet(conn, `/api/controle/desconto-limites`),
        apiGet(conn, `${basePath}/${pedidoId}/descontos`),
      ]);
      if (rl?.success) {
        const lim = funcaoCod === 2 ? rl.supervisor : funcaoCod === 3 ? rl.vendedor : rl.gerente;
        setGeralLimite(Number(lim) || 100);
      }
      const gRows = (rd?.items || []).filter((d: DescontoRow) => d.tipo_desconto === "G");
      const atual = gRows.reduce((s: number, d: DescontoRow) => s + (d.valor_total || 0), 0);
      setGeralAtual(atual);
      setGeralValor(atual > 0 ? fmtMoney2(atual) : "");
    } catch {
      // silencioso
    }
  };

  const submitGeral = async (valor: number) => {
    if (!conn || !pedidoId) return;
    setGeralSaving(true);
    try {
      const j = await apiSend(conn, `${basePath}/${pedidoId}/desconto-geral`, "POST", {
        valor, usuario_codigo: usuarioCod, funcao: funcaoCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha no desconto geral.", "error"); }
      else {
        setGeralAtual(valor);
        setGeralModalOpen(false);
        showToast(valor > 0 ? "Desconto geral aplicado." : "Desconto geral removido.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setGeralSaving(false); }
  };

  const handleApplyGeral = () => {
    const valor = parseNum(geralValor);
    if (valor <= 0) { showToast("Informe um valor maior que zero.", "error"); return; }
    if (valor > baseGeral + 1e-6) { showToast("Desconto maior que o total dos itens.", "error"); return; }
    const pctEf = baseGeral > 0 ? (valor / baseGeral) * 100 : 0;
    if (pctEf > geralLimite + 1e-6) {
      showToast(`Desconto (${pctEf.toFixed(1)}%) acima do limite (${fmtNum(geralLimite)}%) da sua função.`, "error");
      return;
    }
    submitGeral(valor);
  };

  // -------- Taxa de Serviço (botão "Incluir Tx Serviço [F10]" do Pedido
  // Bar, FrmManPedBar.frm Command50_Click) — 10% do subtotal atual (sem a
  // própria taxa), código de serviço reservado "S002". Idempotente: se já
  // existe uma linha S002, um novo clique ATUALIZA o valor dela em vez de
  // empilhar outra (decisão explícita do usuário — diferente do legado,
  // que empilhava). Sem confirmação — pedido explícito do usuário: só
  // avisa via toast que foi incluída/atualizada.
  const [taxaServicoSaving, setTaxaServicoSaving] = useState(false);

  const handleTaxaServico = async () => {
    if (!conn || !pedidoId) return;
    setTaxaServicoSaving(true);
    try {
      const j = await apiSend(conn, `${basePath}/${pedidoId}/taxa-servico`, "POST", {
        usuario_codigo: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(
          `Taxa de serviço ${j.atualizado ? "atualizada" : "incluída"} (${formatBRL(j.valor)}).`,
          "success"
        );
        loadItens();
      } else {
        showToast(j?.message || "Falha ao incluir taxa de serviço.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally {
      setTaxaServicoSaving(false);
    }
  };

  return {
    // conexão (repassada pro seletor de Modificadores em AddItemModal.tsx —
    // Fase 2, precisa chamar a API por conta própria pra buscar as
    // categorias associadas ao produto selecionado)
    conn,
    // listagem
    itens, subtotal, itensLoading, loadItens, descTotalItens, baseGeral,
    // add modal
    addOpen, setAddOpen, prodTerm, setProdTerm, prodResults, prodLoading, pedidoProdutos, buscarProdutos,
    selProd, setSelProd, addQtd, setAddQtd, addValor, setAddValor, promoAplicada,
    addDescPct, setAddDescPct, addDescRs, setAddDescRs, addAcr, setAddAcr,
    addCompl, setAddCompl, addSaving, openAddModal, pickProduto, handleAddItem, quickAddItem,
    // número de série (Fase B, só Pedido Geral)
    selNumSerie, setSelNumSerie,
    // Metro Quadrado (Fase B, só Pedido Geral)
    ehProdutoM2, precosM2, precosM2Loading, vidroControlaCabecaChapa,
    addTipoPrecoM2, setAddTipoPrecoM2,
    addComprimento, setAddComprimento, addLargura, setAddLargura,
    addComprimentoChapa, setAddComprimentoChapa, addLarguraChapa, setAddLarguraChapa,
    previewM2, previewM2Loading,
    // ticket de impressão de item
    printItem, setPrintItem,
    // agendar item de Serviço (Fase B — módulo Clínica)
    agendarItem, setAgendarItem, profissionaisAgenda, profissionaisLoading, agendaSaving,
    salvarAgendamento, cancelarAgendamento, trocarProfissionalAgenda,
    // edit modal
    editItem, setEditItem, editQtd, setEditQtd, editValor, setEditValor,
    editDescPct, setEditDescPct, editDescRs, setEditDescRs, editAcr, setEditAcr,
    editCompl, setEditCompl, editSaving, openEditModal, handleUpdateItem, handleDeleteItem,
    // Metro Quadrado — reeditar item m² (Fase B, só Pedido Geral)
    editPrecosM2, editTipoPrecoM2, setEditTipoPrecoM2,
    editComprimento, setEditComprimento, editLargura, setEditLargura,
    editPreviewM2, editPreviewM2Loading,
    // descontos report
    descModalOpen, setDescModalOpen, descItems, descTotalApi, descLoading, openDescontos,
    // desconto geral
    geralModalOpen, setGeralModalOpen, geralValor, setGeralValor, geralAtual,
    geralLimite, geralSaving, openGeralModal, submitGeral, handleApplyGeral,
    // taxa de serviço
    taxaServicoSaving, handleTaxaServico,
    // pedido totalizado
    pedidoTotalizadoOpen, setPedidoTotalizadoOpen, pedidoTotalizadoGrupos, pedidoTotalizadoTotal,
  };
}

export type UsePedidoItens = ReturnType<typeof usePedidoItens>;
