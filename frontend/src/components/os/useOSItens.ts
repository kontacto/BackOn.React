// Hook de itens da O.S. Completa (`os_produto`, via `/api/os-completo/{codigo}/...`)
// — versão DEDICADA e mais enxuta que `pedido/usePedidoItens.ts`: sem
// kit/m²/número de série/clínica/taxa de serviço/pedido totalizado
// (conceitos exclusivos do Pedido, sem equivalente na O.S.), com Vendedor+
// Executor+Situação/Destino POR ITEM no lugar (`os_produto.vendedor`/
// `.executor`/`.situacao` — diferente do Pedido, que só tem um vendedor no
// cabeçalho). A superfície pública é compatível com `ItemListItens`
// (`pedido/ItemList.tsx`), permitindo reaproveitar aquele componente sem
// alterá-lo além do já feito lá (ver o comentário de `hasSituacaoActions`).
import { useCallback, useEffect, useMemo, useState } from "react";
import { Platform } from "react-native";

import { apiGet, apiSend, apiDelete, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { formatBRL, parseNum, fmtNum, fmtMoney2, calcDescUnit } from "@/src/utils/format";
import { ItemRow, ProdutoServico, DescontoRow, ToastTone } from "@/src/components/pedido/types";
import { AgendaSalvarPayload } from "@/src/components/pedido/agendaTypes";
import { OSItemRow } from "./types";

type Params = {
  conn: Connection | null;
  editing: boolean;
  osId: number | null;
  isAberto: boolean;
  usuarioCod: number;
  funcaoCod: number;
  classe: number | null;
  // Master (KONTACTO) bypassa a checagem de permissão AGENDAR no backend —
  // mesmo padrão de `master` em `usePedidoItens.ts`. Default false.
  master?: boolean;
  showToast: (m: string, t?: ToastTone) => void;
  servicosOn: boolean;
  // Agendar/cancelar o atendimento de um item agora TAMBÉM alimenta
  // `os.data_agendamento`/`hora_agendamento` no backend (user-directed
  // 2026-08-15, ver AssistenciaTecnicaCampo.md seção 9) — opcional, chamado
  // depois de `loadItens()` em sucesso, pro chamador (os-geral.tsx)
  // recarregar só o cabeçalho e refletir isso na tela sem sair/voltar.
  onAgendamentoAlterado?: () => void;
};

const BASE_PATH = "/api/os-completo";

export function useOSItens({
  conn, editing, osId, isAberto, usuarioCod, funcaoCod, classe, master, showToast, servicosOn,
  onAgendamentoAlterado,
}: Params) {
  const [itens, setItens] = useState<OSItemRow[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [itensLoading, setItensLoading] = useState(false);

  const loadItens = useCallback(async () => {
    if (!conn || !editing || !osId) return;
    setItensLoading(true);
    try {
      const j = await apiGet(conn, `${BASE_PATH}/${osId}/itens`);
      if (j?.success) {
        const mapped: OSItemRow[] = (j.items || []).map((r: Record<string, unknown>) => ({
          codauto: r.cod_os_prod as number, cod_os_prod: r.cod_os_prod as number,
          produto: r.produto as string, tipo: r.tipo as "P" | "S" | "?",
          descricao: r.descricao as string, complemento: (r.complemento as string) || "",
          cod_fab: (r.cod_fab as string) || "", unidade: (r.unidade as string) || "",
          qtd: r.qtd as number, p_normal: r.p_normal as number, valor_unitario: r.valor_unitario as number,
          desconto: r.desconto as number, acrescimo: r.acrescimo as number, total: r.total as number,
          data_inclusao: null, hora_inclusao: "", finalidade_descricao: "",
          vendedor: (r.vendedor as number) ?? null, vendedor_nome: (r.vendedor_nome as string) || "",
          executor: (r.executor as number) ?? null, executor_nome: (r.executor_nome as string) || "",
          situacao: (r.situacao as number) ?? 0,
          pontuacao_e: (r.pontuacao_e as number) ?? null,
          pontuacao_v: (r.pontuacao_v as number) ?? null,
          pontuacao_a: (r.pontuacao_a as number) ?? null,
          usuario_autorizacao: (r.usuario_autorizacao as number) ?? null,
          usuario_autorizacao_nome: (r.usuario_autorizacao_nome as string) || "",
          data_autorizacao: (r.data_autorizacao as string) ?? null,
          hora_autorizacao: (r.hora_autorizacao as string) || "",
          qtd_autorizada: (r.qtd_autorizada as number) ?? 0,
          usuario_expedicao: (r.usuario_expedicao as number) ?? null,
          usuario_expedicao_nome: (r.usuario_expedicao_nome as string) || "",
          data_expedicao: (r.data_expedicao as string) ?? null,
          hora_expedicao: (r.hora_expedicao as string) || "",
          agendamento: (r.agendamento as OSItemRow["agendamento"]) ?? null,
        }));
        setItens(mapped);
        setSubtotal(j.subtotal || 0);
      }
    } catch {
      // silencioso
    } finally {
      setItensLoading(false);
    }
  }, [conn, editing, osId]);

  useEffect(() => { loadItens(); }, [loadItens]);

  const descTotalItens = useMemo(
    () => itens.reduce((s, it) => s + (it.desconto || 0) * (it.qtd || 0), 0),
    [itens]
  );
  const baseGeral = useMemo(
    () => itens.reduce((s, it) => s + (it.p_normal || 0) * (it.qtd || 0), 0),
    [itens]
  );

  // -------- Adicionar item
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
  const [addVendedor, setAddVendedor] = useState<number | null>(null);
  const [addExecutor, setAddExecutor] = useState<number | null>(null);
  const [addSituacao, setAddSituacao] = useState(0);
  const [addSaving, setAddSaving] = useState(false);

  const buscarProdutos = useCallback(async (termo: string): Promise<ProdutoServico[]> => {
    if (!conn || !termo.trim()) { setProdResults([]); return []; }
    setProdLoading(true);
    try {
      const j = await apiGet(conn, `/api/produtos-servicos`, {
        search: termo, page: 1, size: 30, tipo: servicosOn ? "all" : "P",
      });
      const items: ProdutoServico[] = j?.items || [];
      setProdResults(items);
      return items;
    } catch {
      setProdResults([]);
      return [];
    } finally {
      setProdLoading(false);
    }
  }, [conn, servicosOn]);

  useEffect(() => {
    if (!addOpen || selProd) return;
    const t = setTimeout(() => { buscarProdutos(prodTerm); }, 300);
    return () => clearTimeout(t);
  }, [prodTerm, addOpen, selProd, buscarProdutos]);

  const openAddModal = () => {
    if (!isAberto) { showToast("O.S. não pode ser alterada.", "error"); return; }
    setSelProd(null); setProdTerm(""); setProdResults([]);
    setAddQtd("1"); setAddValor("0,00"); setAddDescPct(""); setAddDescRs(""); setAddAcr("");
    setAddCompl(""); setAddVendedor(null); setAddExecutor(null); setAddSituacao(0);
    setAddOpen(true);
  };

  const pickProduto = (p: ProdutoServico) => {
    setSelProd(p);
    setAddQtd("1");
    setAddValor(formatBRL(p.valor).replace("R$", "").trim());
    setAddDescPct(""); setAddDescRs(""); setAddAcr(""); setAddCompl("");
  };

  const handleAddItem = async () => {
    if (!conn || !osId || !selProd) return;
    const qtd = parseNum(addQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(addValor);
    const descUnit = calcDescUnit(pNormal, addDescPct, addDescRs);
    const acr = parseNum(addAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setAddSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/itens`, "POST", {
        produto: selProd.codigo, qtd, valor_unitario: pNormal,
        desconto: descUnit, desconto_pct: parseNum(addDescPct), acrescimo: acr,
        complemento: addCompl, vendedor: addVendedor, executor: addExecutor, situacao: addSituacao,
        usuario_codigo: usuarioCod, funcao: funcaoCod, classe, plataforma: Platform.OS,
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

  // -------- Editar item
  const [editItem, setEditItemState] = useState<OSItemRow | null>(null);
  const [editQtd, setEditQtd] = useState("1");
  const [editValor, setEditValor] = useState("0,00");
  const [editDescPct, setEditDescPct] = useState("");
  const [editDescRs, setEditDescRs] = useState("");
  const [editAcr, setEditAcr] = useState("");
  const [editCompl, setEditCompl] = useState("");
  const [editVendedor, setEditVendedor] = useState<number | null>(null);
  const [editExecutor, setEditExecutor] = useState<number | null>(null);
  const [editSituacao, setEditSituacao] = useState(0);
  const [editSaving, setEditSaving] = useState(false);

  // Assinatura `(item: ItemRow) => void` — mesma exigida por `ItemListItens`
  // (`pedido/ItemList.tsx`) — internamente sempre é um `OSItemRow` de
  // verdade (só `useOSItens` popula `itens`), daí o cast seguro.
  const openEditModal = (item: ItemRow) => {
    const it = item as OSItemRow;
    if (!isAberto) { showToast("O.S. não pode ser alterada.", "error"); return; }
    setEditItemState(it);
    setEditQtd(fmtNum(it.qtd));
    setEditValor(formatBRL(it.p_normal || it.valor_unitario).replace("R$", "").trim());
    setEditDescPct("");
    setEditDescRs(it.desconto > 0 ? fmtMoney2(it.desconto) : "");
    setEditAcr(it.acrescimo > 0 ? fmtMoney2(it.acrescimo) : "");
    setEditCompl(it.complemento || "");
    setEditVendedor(it.vendedor);
    setEditExecutor(it.executor);
    setEditSituacao(it.situacao ?? 0);
  };

  const handleUpdateItem = async () => {
    if (!conn || !osId || !editItem) return;
    const qtd = parseNum(editQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(editValor);
    const descUnit = calcDescUnit(pNormal, editDescPct, editDescRs);
    const acr = parseNum(editAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setEditSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/itens/${editItem.cod_os_prod}`, "PUT", {
        qtd, valor_unitario: pNormal, complemento: editCompl,
        desconto: descUnit, desconto_pct: parseNum(editDescPct), acrescimo: acr,
        vendedor: editVendedor, executor: editExecutor, situacao: editSituacao,
        usuario_codigo: usuarioCod, funcao: funcaoCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao salvar.", "error"); }
      else {
        setEditItemState(null);
        showToast("Item atualizado.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  const handleDeleteItem = async () => {
    if (!conn || !osId || !editItem) return;
    setEditSaving(true);
    try {
      const j = await apiDelete(conn, `${BASE_PATH}/${osId}/itens/${editItem.cod_os_prod}`, {
        usuario_alteracao: usuarioCod, classe: classe ?? undefined, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao remover.", "error"); }
      else {
        setEditItemState(null);
        showToast("Item removido.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  // -------- Descontos concedidos (relatório)
  const [descModalOpen, setDescModalOpen] = useState(false);
  const [descItems, setDescItems] = useState<DescontoRow[]>([]);
  const [descTotalApi, setDescTotalApi] = useState(0);
  const [descLoading, setDescLoading] = useState(false);

  const openDescontos = async () => {
    if (!conn || !osId) return;
    setDescModalOpen(true);
    setDescLoading(true);
    try {
      const j = await apiGet(conn, `${BASE_PATH}/${osId}/descontos`);
      if (j?.success) { setDescItems(j.items || []); setDescTotalApi(j.total || 0); }
    } catch {
      // silencioso
    } finally { setDescLoading(false); }
  };

  // -------- Desconto geral
  const [geralModalOpen, setGeralModalOpen] = useState(false);
  const [geralValor, setGeralValor] = useState("");
  const [geralAtual, setGeralAtual] = useState(0);
  const [geralLimite, setGeralLimite] = useState(100);
  const [geralSaving, setGeralSaving] = useState(false);

  const openGeralModal = async () => {
    if (!conn || !osId) return;
    setGeralModalOpen(true);
    try {
      const [rl, rd] = await Promise.all([
        apiGet(conn, `/api/controle/desconto-limites`),
        apiGet(conn, `${BASE_PATH}/${osId}/descontos`),
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
    if (!conn || !osId) return;
    setGeralSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/desconto-geral`, "POST", {
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

  // -------- Pontuação de Técnicos (os_produto.Pontuacao_A/E/V) — nota
  // 0-999 do Executor/Vendedor/Atendente por item.
  const [pontuacaoModalOpen, setPontuacaoModalOpen] = useState(false);
  const [pontuacaoSaving, setPontuacaoSaving] = useState(false);

  const savePontuacao = async (
    codOsProd: number, valores: { pontuacao_e?: number | null; pontuacao_v?: number | null; pontuacao_a?: number | null }
  ) => {
    if (!conn || !osId) return;
    setPontuacaoSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/itens/${codOsProd}/pontuacao`, "PUT", {
        pontuacao_e: valores.pontuacao_e, pontuacao_v: valores.pontuacao_v, pontuacao_a: valores.pontuacao_a,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao gravar pontuação.", "error"); }
      else {
        showToast("Pontuação gravada.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setPontuacaoSaving(false); }
  };

  // -------- Alteração de Executor/Vendedor pós-fechamento (CmdAltExec,
  // branch F/PG de CmDaltera_Click) — corrige o executor/vendedor de um
  // item já lançado com a O.S. Fechada ou Faturada, sem reabrir a O.S.
  const [altExecutorModalOpen, setAltExecutorModalOpen] = useState(false);
  const [altExecutorSaving, setAltExecutorSaving] = useState(false);

  const salvarAlterarExecutor = async (
    codOsProd: number, valores: { vendedor?: number | null; executor?: number | null }, propagarDemais: boolean
  ): Promise<boolean> => {
    if (!conn || !osId) return false;
    setAltExecutorSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/itens/${codOsProd}/executor`, "PUT", {
        vendedor: valores.vendedor ?? null, executor: valores.executor ?? null,
        propagar_demais: propagarDemais,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha ao alterar executor/vendedor.", "error"); return false; }
      const propagados = (j.propagados || []).length;
      showToast(propagados > 0 ? `Alterado e propagado pra mais ${propagados} item(ns).` : "Executor/vendedor alterado.", "success");
      loadItens();
      return true;
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
      return false;
    } finally { setAltExecutorSaving(false); }
  };

  // -------- Autorização/Expedição de Itens (os_produto.usuario_autorizacao/
  // data_autorizacao/.../usuario_expedicao/data_expedicao) — 4 ações em
  // lote sobre os itens marcados na lista, gated pelas flags de empresa
  // exige_aprovacao_itens_os/exige_expedicao_itens_os (ver OSData).
  const [autorizacaoModalOpen, setAutorizacaoModalOpen] = useState(false);
  const [autorizacaoSaving, setAutorizacaoSaving] = useState(false);
  const [autorizacaoSelecionados, setAutorizacaoSelecionados] = useState<number[]>([]);

  const toggleAutorizacaoSelecionado = (codOsProd: number) => {
    setAutorizacaoSelecionados((prev) =>
      prev.includes(codOsProd) ? prev.filter((c) => c !== codOsProd) : [...prev, codOsProd]
    );
  };

  const _autorizacaoAction = async (path: string, verboSucesso: string) => {
    if (!conn || !osId || autorizacaoSelecionados.length === 0) return;
    setAutorizacaoSaving(true);
    try {
      const j = await apiSend(conn, `${BASE_PATH}/${osId}/itens/${path}`, "POST", {
        cod_os_prod: autorizacaoSelecionados, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(j?.message || "Falha na operação.", "error"); }
      else {
        const okKey = j.autorizados ? "autorizados" : j.expedidos ? "expedidos" : "removidos";
        const okCount = (j[okKey] || []).length;
        const bloqCount = (j.bloqueados || []).length;
        if (bloqCount > 0) {
          showToast(j.message || `${okCount} item(ns) ${verboSucesso}, ${bloqCount} bloqueado(s).`, "info");
        } else {
          showToast(`${okCount} item(ns) ${verboSucesso}.`, "success");
        }
        setAutorizacaoSelecionados([]);
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setAutorizacaoSaving(false); }
  };

  const autorizarItens = () => _autorizacaoAction("autorizar", "autorizado(s)");
  const removerAutorizacaoItens = () => _autorizacaoAction("remover-autorizacao", "com autorização removida");
  const expedirItens = () => _autorizacaoAction("expedir", "com expedição autorizada");
  const removerExpedicaoItens = () => _autorizacaoAction("remover-expedicao", "com expedição removida");

  // -------- Agendar item de Serviço (módulo Assistência — `AGENDA`/
  // `AGENDA_OS`, mesmo mecanismo do Pedido Geral via `AGENDA_PEDIDO`, ver
  // `agenda_service.py`). Implementação real (não mais no-op) — mesma
  // lógica de `pedido/usePedidoItens.ts`, só as rotas trocam pra
  // `/api/agenda/os-item/...` e `codauto` aqui é sempre o `cod_os_prod`
  // (já mapeado como `codauto` em `loadItens` acima). Superfície
  // compatível com `AgendaItens` (`pedido/agendaTypes.ts`), reaproveitada
  // por `AgendarModal.tsx` sem nenhuma mudança no componente.
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

  const salvarAgendamento = async (payload: AgendaSalvarPayload) => {
    if (!conn || !agendarItem) return;
    setAgendaSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/os-item/${agendarItem.codauto}`, "POST", {
        ...payload,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao agendar."), "error"); return false; }
      showToast("Item agendado.", "success");
      setAgendarItemState(null);
      loadItens();
      onAgendamentoAlterado?.();
      return true;
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao agendar."), "error");
      return false;
    } finally { setAgendaSaving(false); }
  };

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
      const j = await apiSend(conn, `/api/agenda/os-item/${agendarItem.codauto}/cancelar`, "POST", {
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { showToast(friendlyApiError(j, "Falha ao cancelar agendamento."), "error"); return; }
      showToast("Agendamento cancelado.", "success");
      setAgendarItemState(null);
      loadItens();
      onAgendamentoAlterado?.();
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao cancelar agendamento."), "error");
    } finally { setAgendaSaving(false); }
  };

  // -------- Sem equivalente na O.S. (kit/m²/número de série/taxa de
  // serviço/pedido totalizado) — no-ops que só existem pra satisfazer a
  // superfície de `ItemListItens` (`pedido/ItemList.tsx`); os gates que
  // decidiriam chamá-los (`canTaxaServico`/`canImprimirItem`/
  // `showPedidoTotalizado`) ficam sempre falsos pra `tela === "OS_COMP"`.
  const taxaServicoSaving = false;
  const handleTaxaServico = () => {};
  const setPrintItem = (_item: ItemRow) => {};
  const setPedidoTotalizadoOpen = (_open: boolean) => {};

  return {
    conn,
    // listagem
    itens, subtotal, itensLoading, loadItens, descTotalItens, baseGeral,
    // adicionar item
    addOpen, setAddOpen, prodTerm, setProdTerm, prodResults, prodLoading, buscarProdutos,
    selProd, setSelProd, addQtd, setAddQtd, addValor, setAddValor,
    addDescPct, setAddDescPct, addDescRs, setAddDescRs, addAcr, setAddAcr,
    addCompl, setAddCompl, addVendedor, setAddVendedor, addExecutor, setAddExecutor,
    addSituacao, setAddSituacao, addSaving, openAddModal, pickProduto, handleAddItem,
    // editar item
    editItem, setEditItem: setEditItemState, editQtd, setEditQtd, editValor, setEditValor,
    editDescPct, setEditDescPct, editDescRs, setEditDescRs, editAcr, setEditAcr,
    editCompl, setEditCompl, editVendedor, setEditVendedor, editExecutor, setEditExecutor,
    editSituacao, setEditSituacao, editSaving, openEditModal, handleUpdateItem, handleDeleteItem,
    // descontos concedidos
    descModalOpen, setDescModalOpen, descItems, descTotalApi, descLoading, openDescontos,
    // desconto geral
    geralModalOpen, setGeralModalOpen, geralValor, setGeralValor, geralAtual,
    geralLimite, geralSaving, openGeralModal, submitGeral, handleApplyGeral,
    // pontuação de técnicos
    pontuacaoModalOpen, setPontuacaoModalOpen, pontuacaoSaving, savePontuacao,
    // alteração de executor/vendedor pós-fechamento
    altExecutorModalOpen, setAltExecutorModalOpen, altExecutorSaving, salvarAlterarExecutor,
    // autorização/expedição de itens
    autorizacaoModalOpen, setAutorizacaoModalOpen, autorizacaoSaving, autorizacaoSelecionados,
    toggleAutorizacaoSelecionado, setAutorizacaoSelecionados,
    autorizarItens, removerAutorizacaoItens, expedirItens, removerExpedicaoItens,
    // agendar item de Serviço (módulo Assistência)
    agendarItem, setAgendarItem, profissionaisAgenda, profissionaisLoading, agendaSaving,
    salvarAgendamento, cancelarAgendamento, trocarProfissionalAgenda,
    // no-ops (ver comentário acima)
    taxaServicoSaving, handleTaxaServico, setPrintItem, setPedidoTotalizadoOpen,
  };
}

export type UseOSItens = ReturnType<typeof useOSItens>;
