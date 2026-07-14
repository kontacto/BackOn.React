// Hook que encapsula estado e regras dos ITENS do pedido + descontos
// (item, geral) e relatório de descontos. Mantém a lógica idêntica à tela
// original; a tela apenas orquestra e renderiza os componentes.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";
import { useFocusEffect } from "expo-router";

import { apiGet, apiSend, apiDelete } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { formatBRL, parseNum, fmtNum, fmtMoney2, calcDescUnit } from "@/src/utils/format";
import { ItemRow, ProdutoServico, DescontoRow, ToastTone } from "./types";

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
};

export function usePedidoItens({ conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, showToast, servicosOn }: Params) {
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

  const baseGeral = useMemo(
    () => itens.reduce((s, it) => s + (it.p_normal || 0) * (it.qtd || 0), 0),
    [itens]
  );

  // -------- Itens do pedido (carrega só em modo edição)
  const loadItens = useCallback(async () => {
    if (!conn || !editing || !pedidoId) return;
    setItensLoading(true);
    try {
      const j = await apiGet(conn, `/api/pedidos/${pedidoId}/itens`);
      if (j?.success) {
        setItens(j.items || []);
        setSubtotal(j.subtotal || 0);
      }
    } catch {
      // silencioso
    } finally {
      setItensLoading(false);
    }
  }, [conn, editing, pedidoId]);

  // Recarrega itens ao focar a tela (ex.: voltar da lista de produtos)
  useFocusEffect(
    useCallback(() => {
      loadItens();
    }, [loadItens])
  );

  // -------- Busca produto/serviço (debounce) dentro do modal de adicionar
  useEffect(() => {
    if (!addOpen || !conn) return;
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
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/itens`, "POST", {
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
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/itens/${editItem.codauto}`, "PUT", {
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
      const j = await apiDelete(conn, `/api/pedidos/${pedidoId}/itens/${it.codauto}`, {
        usuario_alteracao: usuarioCod, classe: classe ?? undefined, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao remover.", "error"); }
      else {
        setEditItem(null);
        showToast("Item removido.", "success");
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
      const j = await apiGet(conn, `/api/pedidos/${pedidoId}/descontos`);
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
        apiGet(conn, `/api/pedidos/${pedidoId}/descontos`),
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
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/desconto-geral`, "POST", {
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

  return {
    // listagem
    itens, subtotal, itensLoading, loadItens, descTotalItens, baseGeral,
    // add modal
    addOpen, setAddOpen, prodTerm, setProdTerm, prodResults, prodLoading,
    selProd, setSelProd, addQtd, setAddQtd, addValor, setAddValor,
    addDescPct, setAddDescPct, addDescRs, setAddDescRs, addAcr, setAddAcr,
    addCompl, setAddCompl, addSaving, openAddModal, pickProduto, handleAddItem,
    // edit modal
    editItem, setEditItem, editQtd, setEditQtd, editValor, setEditValor,
    editDescPct, setEditDescPct, editDescRs, setEditDescRs, editAcr, setEditAcr,
    editCompl, setEditCompl, editSaving, openEditModal, handleUpdateItem, handleDeleteItem,
    // descontos report
    descModalOpen, setDescModalOpen, descItems, descTotalApi, descLoading, openDescontos,
    // desconto geral
    geralModalOpen, setGeralModalOpen, geralValor, setGeralValor, geralAtual,
    geralLimite, geralSaving, openGeralModal, submitGeral, handleApplyGeral,
  };
}

export type UsePedidoItens = ReturnType<typeof usePedidoItens>;
