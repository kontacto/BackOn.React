// Hook que encapsula estado e regras dos ITENS do pedido + descontos
// (item, geral) e relatório de descontos. Mantém a lógica idêntica à tela
// original; a tela apenas orquestra e renderiza os componentes.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import { useFocusEffect } from "expo-router";

import { apiGet, apiSend, apiDelete } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { formatBRL, parseNum, fmtNum, fmtMoney2, calcDescUnit } from "@/src/utils/format";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { ItemRow, ItemPrintData, ProdutoServico, DescontoRow, ToastTone } from "./types";

type Params = {
  conn: Connection | null;
  editing: boolean;
  pedidoId: number | null;
  isAberto: boolean;
  usuarioCod: number;
  funcaoCod: number;
  classe: number | null;
  showToast: (m: string, t?: ToastTone) => void;
  // Módulo "Serviços" (Configurações > Módulos e Recursos) — desligado,
  // a busca de item só retorna produtos (tipo=P), nunca serviços.
  servicosOn: boolean;
  // Prefixo da API — "/api/pedidos" (rápido, default) ou "/api/pedido-completo"
  // (Pedido Completo web, mesma tabela pedido_venda_prod, resolução de
  // produto mais rica + expansão de kit no backend, transparente aqui).
  basePath?: string;
  // Impressão automática de item por Finalidade (FrmManPedBar.frm,
  // Command1_Click) — só o Pedido Bar tem esse comportamento (conceito de
  // Finalidade/grupo de produto ligado a impressora é do segmento Bar,
  // sem equivalente no Pedido Completo/O.S.). Default false.
  printPorFinalidade?: boolean;
};

export function usePedidoItens({
  conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, showToast, servicosOn,
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
  const [addDescPct, setAddDescPct] = useState("");
  const [addDescRs, setAddDescRs] = useState("");
  const [addAcr, setAddAcr] = useState("");
  const [addCompl, setAddCompl] = useState("");
  const [addSaving, setAddSaving] = useState(false);

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

  // Modal de editar item existente
  const [editItem, setEditItem] = useState<ItemRow | null>(null);
  const [editQtd, setEditQtd] = useState("1");
  const [editValor, setEditValor] = useState("0,00");
  const [editDescPct, setEditDescPct] = useState("");
  const [editDescRs, setEditDescRs] = useState("");
  const [editAcr, setEditAcr] = useState("");
  const [editCompl, setEditCompl] = useState("");
  const [editSaving, setEditSaving] = useState(false);

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

  // -------- Busca produto/serviço (debounce) dentro do modal de adicionar.
  // Com o campo de busca vazio, a lista padrão exibida é a dos itens já no
  // pedido (`pedidoProdutos` abaixo) — só dispara a busca na API quando o
  // usuário efetivamente digita algo.
  useEffect(() => {
    if (!addOpen || !conn || !prodTerm.trim()) {
      setProdResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setProdLoading(true);
      try {
        const j = await apiGet(conn, `/api/produtos-servicos`, {
          search: prodTerm, page: 1, size: 30, tipo: servicosOn ? "all" : "P",
        });
        setProdResults(j?.items || []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [prodTerm, addOpen, conn, servicosOn]);

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
    setAddOpen(true);
  };

  const pickProduto = (p: ProdutoServico) => {
    setSelProd(p);
    setAddQtd("1");
    setAddValor(formatBRL(p.valor).replace("R$", "").trim());
    setAddDescPct(""); setAddDescRs(""); setAddAcr("");
    setAddCompl("");
  };

  const handleAddItem = async () => {
    if (!conn || !pedidoId || !selProd) return;
    const qtd = parseNum(addQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(addValor);
    const descUnit = calcDescUnit(pNormal, addDescPct, addDescRs);
    const acr = parseNum(addAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
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
        complemento: addCompl,
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
      const j = await apiSend(conn, `${basePath}/${pedidoId}/itens`, "POST", {
        produto: p.codigo,
        qtd: 1,
        valor_unitario: p.valor,
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
  };

  const handleUpdateItem = async () => {
    if (!conn || !pedidoId || !editItem) return;
    const qtd = parseNum(editQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
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
    // listagem
    itens, subtotal, itensLoading, loadItens, descTotalItens, baseGeral,
    // add modal
    addOpen, setAddOpen, prodTerm, setProdTerm, prodResults, prodLoading, pedidoProdutos,
    selProd, setSelProd, addQtd, setAddQtd, addValor, setAddValor,
    addDescPct, setAddDescPct, addDescRs, setAddDescRs, addAcr, setAddAcr,
    addCompl, setAddCompl, addSaving, openAddModal, pickProduto, handleAddItem, quickAddItem,
    // ticket de impressão de item
    printItem, setPrintItem,
    // edit modal
    editItem, setEditItem, editQtd, setEditQtd, editValor, setEditValor,
    editDescPct, setEditDescPct, editDescRs, setEditDescRs, editAcr, setEditAcr,
    editCompl, setEditCompl, editSaving, openEditModal, handleUpdateItem, handleDeleteItem,
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
