// Financeiro > Contas a Receber — gerencia o que já foi lançado em
// `Duplicata_Receber`/`Duplicata_Rec_Venc` (via Transferência p/Contas
// Pagar/Receber, Contratos/Faturar, ou lançamento manual avulso aqui
// mesmo). Fonte VB6 rastreada: `Geral/FRMCONNFREC.frm` (consulta) +
// `Geral/frmTraNFRec.frm` (CRUD/avulso) + `Revenda/FrmManDur.frm`
// (manutenção de duplicata/parcelas) — ver
// backend/services/contas_receber_service.py pro rastreio completo.
//
// Escopo desta 1ª rodada (AskUserQuestion, 2026-08-28): lançamento avulso
// + baixa manual (funcionalidade NOVA, sem precedente no legado — só
// existe baixa via retorno CNAB lá) + exclusão com guarda. Boleto avulso/
// Centro de Resultados/Emitir Fatura ficam de fora, aguardando o usuário
// confirmar escopo com Leandro.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import { styles as ps } from "@/src/components/pedido/styles";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import LoteBaixaModal from "@/src/components/financeiro/LoteBaixaModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR, parseNum, todayISO } from "@/src/utils/format";
import { printHtml, escHtml } from "@/src/utils/printHtml";

const isWeb = Platform.OS === "web";

type Duplicata = {
  codigo: number; cliente: number; cliente_nome: string; duplicata: number; desmembramento: string | null;
  dt_emissao: string | null; valor: number; situacao: string; num_parcelas: number; parcelas_pagas: number;
  proximo_vencimento: string | null; valor_em_aberto: number; vencido: boolean;
};

type Parcela = {
  codigo: number; desmembramento: number; dt_vencimento: string | null; valor: number; situacao: string;
  data_pag: string | null; valor_pag: number | null; desconto_pag: number | null; juros_pag: number | null;
  conta: number | null; forma_pag: string | null; observacao: string | null;
  // "Cadastro de Vencimentos" (FrmManDur.frm, combo Situação) — 0-based:
  // 0=Normal, 1=Jurídico, 2=Protestado. Achado do usuário 2026-08-31.
  situacao_duplicata: number;
};

const SITUACAO_VENCIMENTO_OPTIONS = [
  { value: 0, label: "Normal" },
  { value: 1, label: "Jurídico" },
  { value: 2, label: "Protestado" },
];

type Detalhe = { header: Duplicata; parcelas: Parcela[]; notas: { codigo: number; nota_fiscal: number; serie: string }[] };

// 1 linha de `GridCheques` (`FrmManPar.frm::Command2_Click`) — cheque(s)
// pré-datado(s) recebido(s) como parte da própria baixa. Achado do
// usuário 2026-08-31.
type ChequeItem = {
  banco?: number | null; agencia?: string; conta?: string; numero_ch?: number | null;
  valor: number; bom_para?: string | null; nome_cheque?: string; telefone?: string;
};

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que esta tela faz", texto: "Lista as duplicatas a receber já lançadas (vindas de Nota Fiscal, Comanda, Contrato faturado, ou digitadas aqui mesmo) e deixa acompanhar/baixar as parcelas.", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Lançamento avulso", texto: "Use quando você tem um valor a receber que não veio de Nota Fiscal nem Comanda — digite cliente, valor e vencimento(s) direto.", icon: { lib: "ion", name: "add-circle-outline" } },
  { titulo: "Baixa manual", texto: "Marca uma parcela como paga quando o cliente pagou por dinheiro, PIX ou transferência direta (sem passar por boleto/banco). Uma vez baixada, a parcela não pode mais ser editada.", icon: { lib: "ion", name: "checkmark-done-outline" } },
  { titulo: "Cancelar baixa", texto: "Desfaz uma baixa feita por engano — a parcela volta pra Aberto e os dados de pagamento são apagados.", icon: { lib: "ion", name: "arrow-undo-outline" } },
  { titulo: "Pagamento/Cancelamento em Lote", texto: "Dá baixa (ou cancela) em várias parcelas de uma vez, filtrando por período — sem precisar abrir cada duplicata.", icon: { lib: "ion", name: "layers-outline" } },
  { titulo: "Baixa por Montante", texto: "Escolha um cliente e várias parcelas em aberto, informe um valor único recebido — o sistema distribui esse valor entre as parcelas, da mais antiga pra mais nova.", icon: { lib: "ion", name: "calculator-outline" } },
  { titulo: "Editar parcela", texto: "Corrige data de vencimento, valor ou observação de uma parcela ainda em aberto. Uma parcela já paga não pode mais ser editada.", icon: { lib: "ion", name: "create-outline" } },
  { titulo: "Vencido", texto: "Parcela em aberto cuja data de vencimento já passou — aparece em destaque vermelho.", icon: { lib: "ion", name: "alert-circle-outline" } },
  { titulo: "Excluir", texto: "Só é possível excluir uma duplicata se NENHUMA parcela dela já tiver sido paga.", icon: { lib: "ion", name: "trash-outline" } },
  { titulo: "Alterar Número", texto: "Troca o número da duplicata (bloqueia se já existir outra com esse número). Se ela já tiver sido transferida pro Fluxo de Caixa, as previsões vinculadas são removidas — gere uma nova transferência depois com o número novo.", icon: { lib: "ion", name: "create-outline" } },
  { titulo: "Recibo", texto: "Emite um recibo numerado (sequencial, controlado pelo sistema) pra uma parcela já paga — os campos vêm preenchidos automaticamente a partir do pagamento, mas você pode ajustar antes de gravar. Depois de gravado, o número não muda mais.", icon: { lib: "ion", name: "receipt-outline" } },
  { titulo: "Notas Fiscais", texto: "Vincule mais de uma Nota Fiscal na mesma duplicata (útil quando o cliente tem filiais faturando junto). Só mostra NFs em aberto do mesmo CNPJ/CPF. Desvincular só é permitido se nenhuma parcela já tiver sido paga.", icon: { lib: "ion", name: "document-text-outline" } },
  { titulo: "Cheques Pré-Datados na Baixa", texto: "Ao dar baixa numa parcela recebida (total ou parcialmente) em cheque pré-datado, cadastre cada cheque ali mesmo — eles entram no controle de cheques da empresa, prontos pra compensar na data de bom para.", icon: { lib: "ion", name: "wallet-outline" } },
];

const SITUACOES: { key: string; label: string }[] = [
  { key: "", label: "Todas" }, { key: "A", label: "Aberto" }, { key: "V", label: "Vencido" }, { key: "PG", label: "Pago" },
];

export default function ContasReceberScreen() {
  const router = useRouter();
  // `?situacao=` — deep-link a partir do Painel Financeiro (cards
  // "Contas a Receber em Atraso"/"Contas a Receber Hoje"), pra abrir esta
  // tela já filtrada em vez do padrão "Aberto" — ver painel-financeiro.tsx.
  const params = useLocalSearchParams<{ situacao?: string }>();
  const { can, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [filtrosExpandido, setFiltrosExpandido] = useState(true);
  const [busca, setBusca] = useState("");
  const [situacao, setSituacao] = useState(() => (typeof params.situacao === "string" ? params.situacao : "A"));
  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [usarPeriodo, setUsarPeriodo] = useState(false);
  const [items, setItems] = useState<Duplicata[]>([]);

  // Filtros extras — rastreados de `FRMCONDUr.frm` ("Consulta de
  // Duplicatas à Receber..."), achado do usuário 2026-08-31, integrados
  // na própria listagem em vez de uma tela separada.
  const [duplicataNum, setDuplicataNum] = useState("");
  const [valorFiltro, setValorFiltro] = useState("");
  const [numeroBoleto, setNumeroBoleto] = useState("");
  const [situacaoDuplicataFiltro, setSituacaoDuplicataFiltro] = useState<number | null>(null);
  const [recebidoIni, setRecebidoIni] = useState<string | null>(null);
  const [recebidoFim, setRecebidoFim] = useState<string | null>(null);

  const [tiposMov, setTiposMov] = useState<SelectOption[]>([]);
  const [contasOpts, setContasOpts] = useState<SelectOption[]>([]);
  const [formaPagOpts, setFormaPagOpts] = useState<SelectOption[]>([]);
  const [loteOpen, setLoteOpen] = useState(false);

  // ---- Lançamento avulso ----
  const [avulsoOpen, setAvulsoOpen] = useState(false);
  const [salvandoAvulso, setSalvandoAvulso] = useState(false);
  const [avClienteCod, setAvClienteCod] = useState<number | null>(null);
  const [avClienteNome, setAvClienteNome] = useState("");
  const [avClienteSearchOpen, setAvClienteSearchOpen] = useState(false);
  const [avClienteTerm, setAvClienteTerm] = useState("");
  const [avClienteResults, setAvClienteResults] = useState<ClienteRow[]>([]);
  const [avClienteLoading, setAvClienteLoading] = useState(false);
  const [avNumero, setAvNumero] = useState("");
  const [avSerie, setAvSerie] = useState("");
  const [avTipoMov, setAvTipoMov] = useState<string | null>(null);
  const [avDtEmissao, setAvDtEmissao] = useState<string | null>(todayISO());
  const [avValor, setAvValor] = useState("");
  const [avParcelas, setAvParcelas] = useState("1");
  const [avDtVenc, setAvDtVenc] = useState<string | null>(todayISO());
  const [avObs, setAvObs] = useState("");

  // ---- Detalhe / parcelas ----
  const [detalheOpen, setDetalheOpen] = useState(false);
  const [detalheLoading, setDetalheLoading] = useState(false);
  const [detalhe, setDetalhe] = useState<Detalhe | null>(null);
  const [excluindo, setExcluindo] = useState(false);
  // "Alterar Número da Duplicata" (`FrmManDur.frm::Command15_Click`) —
  // achado do usuário 2026-08-31. Modal próprio em vez do InputBox nativo
  // do legado (padrão do projeto: nunca usar prompt()/alert() do browser).
  const [alterarNumeroOpen, setAlterarNumeroOpen] = useState(false);
  const [novoNumero, setNovoNumero] = useState("");
  const [alterandoNumero, setAlterandoNumero] = useState(false);

  // "Emitir Recibo" (`FrmManPar.frm::Command13` — botão real na tela de
  // Baixa, mas com o Click comentado/morto na fonte real; completa a
  // intenção documentada no comentário morto: pré-preenche Recebemos/
  // Valor a partir da parcela paga, editável antes de gravar). Achado do
  // usuário 2026-08-31.
  const [reciboParcela, setReciboParcela] = useState<Parcela | null>(null);
  const [reciboRecebemos, setReciboRecebemos] = useState("");
  const [reciboValor, setReciboValor] = useState("");
  const [reciboReferente, setReciboReferente] = useState("");
  const [reciboData, setReciboData] = useState<string | null>(null);
  const [reciboAssinatura, setReciboAssinatura] = useState("");
  const [emitindoRecibo, setEmitindoRecibo] = useState(false);

  // "Notas Fiscais" — vincular/desvincular NF adicional numa duplicata já
  // existente (`FrmManDur.frm::Command5_Click`/`NF2_DblClick`/
  // `NF_DblClick`). Achado do usuário 2026-08-31.
  const [notasVincularOpen, setNotasVincularOpen] = useState(false);
  const [notasDisponiveis, setNotasDisponiveis] = useState<{ codigo: number; codigo_cliente: number; cliente_nome: string; nota_fiscal: number; serie: string | null; valor: number }[]>([]);
  const [notasCarregando, setNotasCarregando] = useState(false);
  const [vinculandoNf, setVinculandoNf] = useState<number | null>(null);
  const [desvinculandoNf, setDesvinculandoNf] = useState<number | null>(null);

  // ---- Baixa manual de 1 parcela ----
  const [baixaVenc, setBaixaVenc] = useState<Parcela | null>(null);
  const [baixaData, setBaixaData] = useState<string | null>(todayISO());
  const [baixaValor, setBaixaValor] = useState("");
  const [baixaDesconto, setBaixaDesconto] = useState("");
  const [baixaOutrosDesc, setBaixaOutrosDesc] = useState("");
  const [baixaJuros, setBaixaJuros] = useState("");
  const [baixaOutrosAcresc, setBaixaOutrosAcresc] = useState("");
  const [baixaTarifa, setBaixaTarifa] = useState("");
  const [baixaBanco, setBaixaBanco] = useState("");
  const [baixaAgencia, setBaixaAgencia] = useState("");
  const [baixaBoleto, setBaixaBoleto] = useState("");
  const [baixaConta, setBaixaConta] = useState<number | null>(null);
  const [baixaFormaPag, setBaixaFormaPag] = useState<string | null>(null);
  const [baixaObs, setBaixaObs] = useState("");
  // Cheque(s) pré-datado(s) recebido(s) junto com esta baixa
  // (`GridCheques`/`GravaChequePre`) — achado do usuário 2026-08-31.
  const [baixaCheques, setBaixaCheques] = useState<ChequeItem[]>([]);
  const [novoChequeBanco, setNovoChequeBanco] = useState("");
  const [novoChequeAgencia, setNovoChequeAgencia] = useState("");
  const [novoChequeConta, setNovoChequeConta] = useState("");
  const [novoChequeNumero, setNovoChequeNumero] = useState("");
  const [novoChequeValor, setNovoChequeValor] = useState("");
  const [novoChequeBomPara, setNovoChequeBomPara] = useState<string | null>(null);
  const [novoChequeNome, setNovoChequeNome] = useState("");
  const [novoChequeTelefone, setNovoChequeTelefone] = useState("");
  const [baixando, setBaixando] = useState(false);

  // ---- Cancelar baixa ----
  const [cancelandoBaixa, setCancelandoBaixa] = useState<number | null>(null);

  // ---- Editar parcela em aberto ----
  const [editParcela, setEditParcela] = useState<Parcela | null>(null);
  const [editDtVenc, setEditDtVenc] = useState<string | null>(null);
  const [editValor, setEditValor] = useState("");
  const [editObs, setEditObs] = useState("");
  const [editSituacao, setEditSituacao] = useState(0);
  const [editando, setEditando] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number" ? cod : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      const master = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(master ? -2 : (typeof vCod === "number" ? vCod : -2));
      setLoading(false);
    })();
  }, []);

  useEffect(() => {
    if (!conn) return;
    (async () => {
      try {
        const j = await apiGet(conn, "/api/contas-receber-tipos-mov");
        if (j?.success) setTiposMov((j.items || []).map((i: any) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })));
      } catch { /* combo fica vazio, não trava a tela */ }
      try {
        const [c, f] = await Promise.all([apiGet(conn, "/api/contas"), apiGet(conn, "/api/forma-pagamento")]);
        if (c?.success) setContasOpts((c.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
        if (f?.success) setFormaPagOpts((f.items || []).map((i: any) => ({ value: i.codigo, label: i.descricao })));
      } catch { /* combos ficam vazios, não trava a tela */ }
    })();
  }, [conn]);

  const carregar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    try {
      const params: Record<string, string> = {};
      if (situacao) params.situacao = situacao;
      if (busca.trim()) params.busca = busca.trim();
      if (usarPeriodo && dataIni && dataFim) {
        params.data_ini = dataIni;
        params.data_fim = dataFim;
      }
      if (duplicataNum.trim()) params.duplicata_num = duplicataNum.trim();
      if (valorFiltro.trim()) params.valor = String(parseNum(valorFiltro));
      if (numeroBoleto.trim()) params.numero_boleto = numeroBoleto.trim();
      if (situacaoDuplicataFiltro !== null) params.situacao_duplicata = String(situacaoDuplicataFiltro);
      if (recebidoIni && recebidoFim) {
        params.recebido_ini = recebidoIni;
        params.recebido_fim = recebidoFim;
      }
      const j = await apiGet(conn, "/api/contas-receber", params);
      if (j?.success) {
        setItems(j.items || []);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, situacao, busca, usarPeriodo, dataIni, dataFim, duplicataNum, valorFiltro, numeroBoleto, situacaoDuplicataFiltro, recebidoIni, recebidoFim, feedback]);

  // Situação re-busca sozinha ao trocar o chip; busca por texto/período continuam manuais (Enter/Buscar).
  useEffect(() => { if (conn) carregar(); }, [conn, situacao]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Busca de cliente (avulso) ----
  useEffect(() => {
    if (!avClienteSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setAvClienteLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(avClienteTerm)}`;
        const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
        const j = await r.json();
        setAvClienteResults(j?.items || []);
      } catch { setAvClienteResults([]); } finally { setAvClienteLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [avClienteTerm, avClienteSearchOpen, conn]);

  const abrirAvulso = () => {
    setAvClienteCod(null); setAvClienteNome(""); setAvNumero(""); setAvSerie("");
    setAvTipoMov(null); setAvDtEmissao(todayISO()); setAvValor(""); setAvParcelas("1");
    setAvDtVenc(todayISO()); setAvObs("");
    setAvulsoOpen(true);
  };

  const salvarAvulso = useCallback(async () => {
    if (!conn) return;
    if (!avClienteCod) { feedback.showError("Selecione o cliente."); return; }
    if (!avNumero.trim() || !/^\d+$/.test(avNumero.trim())) { feedback.showError("Informe um número válido."); return; }
    if (!avTipoMov) { feedback.showError("Selecione o Tipo de Movimentação."); return; }
    const valorNum = parseNum(avValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor."); return; }
    const parcelasNum = parseInt(avParcelas || "1", 10) || 1;
    if (!avDtVenc) { feedback.showError("Informe a data do 1º vencimento."); return; }

    setSalvandoAvulso(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/avulsa", "POST", {
        cliente: avClienteCod, numero: parseInt(avNumero.trim(), 10), serie: avSerie.trim(),
        tipo_mov: avTipoMov, dt_emissao: avDtEmissao, valor: valorNum, parcelas: parcelasNum,
        dt_primeiro_vencimento: avDtVenc, observacao: avObs,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Duplicata lançada com sucesso.");
        setAvulsoOpen(false);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível lançar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setSalvandoAvulso(false);
    }
  }, [conn, avClienteCod, avNumero, avSerie, avTipoMov, avDtEmissao, avValor, avParcelas, avDtVenc, avObs, usuarioCod, classePerm, feedback, carregar]);

  const abrirDetalhe = useCallback(async (codigo: number) => {
    if (!conn) return;
    setDetalheOpen(true);
    setDetalheLoading(true);
    setDetalhe(null);
    try {
      const j = await apiGet(conn, `/api/contas-receber/${codigo}`);
      if (j?.success) {
        setDetalhe({ header: j.header, parcelas: j.parcelas || [], notas: j.notas || [] });
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível carregar o detalhe."));
        setDetalheOpen(false);
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
      setDetalheOpen(false);
    } finally {
      setDetalheLoading(false);
    }
  }, [conn, feedback]);

  const excluirDuplicata = useCallback(async () => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Excluir a duplicata #${detalhe.header.duplicata}? Esta ação não pode ser desfeita.`,
      async () => {
        setExcluindo(true);
        try {
          const j = await apiSend(conn, "/api/contas-receber/excluir", "POST", {
            codigo_duplicata: detalhe.header.codigo, usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
          });
          if (j?.success) {
            feedback.showSuccess("Duplicata excluída.");
            setDetalheOpen(false);
            carregar();
          } else {
            feedback.showError(friendlyApiError(j, "Não foi possível excluir."));
          }
        } catch (e) {
          feedback.showError(friendlyCatchError(e));
        } finally {
          setExcluindo(false);
        }
      },
    );
  }, [conn, detalhe, usuarioCod, classePerm, feedback, carregar]);

  const abrirAlterarNumero = () => {
    if (!detalhe) return;
    setNovoNumero(String(detalhe.header.duplicata));
    setAlterarNumeroOpen(true);
  };

  const confirmarAlterarNumero = useCallback(async () => {
    if (!conn || !detalhe) return;
    const novo = parseInt(novoNumero, 10);
    if (!novo || novo <= 0) { feedback.showError("Informe um número válido."); return; }
    setAlterandoNumero(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/alterar-numero", "POST", {
        codigo_duplicata: detalhe.header.codigo, novo_numero: novo,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Número da duplicata alterado. Previsões de Transferência vinculadas a ela foram removidas — gere uma nova transferência se precisar.", undefined, 5000);
        setAlterarNumeroOpen(false);
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível alterar o número."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setAlterandoNumero(false);
    }
  }, [conn, detalhe, novoNumero, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const abrirRecibo = useCallback((p: Parcela) => {
    if (!detalhe) return;
    setReciboParcela(p);
    setReciboRecebemos(detalhe.header.cliente_nome || "");
    setReciboValor(String(p.valor_pag ?? p.valor));
    setReciboReferente(`Duplicata Nº ${detalhe.header.duplicata}/${p.desmembramento}`);
    setReciboData(p.data_pag || todayISO());
    setReciboAssinatura("");
  }, [detalhe]);

  const confirmarEmitirRecibo = useCallback(async () => {
    if (!conn) return;
    const valorNum = parseNum(reciboValor);
    if (!reciboRecebemos.trim()) { feedback.showError("Informe quem está pagando (Recebemos de)."); return; }
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe um valor válido."); return; }
    if (!reciboReferente.trim()) { feedback.showError("Informe a que o recibo se refere."); return; }
    setEmitindoRecibo(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/emitir-recibo", "POST", {
        recebemos: reciboRecebemos.trim(), valor: valorNum, referente: reciboReferente.trim(),
        data_recibo: reciboData, assinatura: reciboAssinatura.trim() || undefined,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao emitir o recibo.")); return; }
      const html = `
        <div class="center bold" style="font-size:20px;margin-bottom:12px;">Recibo Nº ${escHtml(j.numero)}</div>
        <p>Recebemos de <b>${escHtml(j.recebemos)}</b>.</p>
        <p>A importância de <b>R$ ${escHtml(formatBRL(j.valor))}</b> (${escHtml(j.valor_extenso)}).</p>
        <p>Referente à ${escHtml(j.referente)}</p>
        <p style="margin-top:24px;">${escHtml(formatDateBR(j.data))}</p>
        <p style="margin-top:48px;text-align:center;">____________________________________<br/>${escHtml(j.assinatura)}</p>
      `;
      printHtml(html, `Recibo ${j.numero}`);
      feedback.showSuccess(`Recibo ${j.numero} emitido.`, undefined, 5000);
      setReciboParcela(null);
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao emitir o recibo."));
    } finally {
      setEmitindoRecibo(false);
    }
  }, [conn, reciboRecebemos, reciboValor, reciboReferente, reciboData, reciboAssinatura, usuarioCod, classePerm, feedback]);

  const abrirVincularNf = useCallback(async () => {
    if (!conn || !detalhe) return;
    setNotasVincularOpen(true);
    setNotasCarregando(true);
    try {
      const j = await apiGet(conn, `/api/contas-receber/${detalhe.header.codigo}/notas-disponiveis`);
      if (j?.success) {
        setNotasDisponiveis(j.items || []);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar notas disponíveis."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setNotasCarregando(false);
    }
  }, [conn, detalhe, feedback]);

  const vincularNf = useCallback(async (nfFiscal: number) => {
    if (!conn || !detalhe) return;
    setVinculandoNf(nfFiscal);
    try {
      const j = await apiSend(conn, "/api/contas-receber/vincular-nf", "POST", {
        codigo_duplicata: detalhe.header.codigo, nf_fiscal: nfFiscal,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Nota Fiscal vinculada.");
        setNotasVincularOpen(false);
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível vincular."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setVinculandoNf(null);
    }
  }, [conn, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const desvincularNf = useCallback((nfFiscal: number, notaFiscalNum: number) => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Desvincular a Nota Fiscal ${notaFiscalNum} desta duplicata?`,
      async () => {
        setDesvinculandoNf(nfFiscal);
        try {
          const j = await apiSend(conn, "/api/contas-receber/desvincular-nf", "POST", {
            codigo_duplicata: detalhe.header.codigo, nf_fiscal: nfFiscal,
            usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
          });
          if (j?.success) {
            feedback.showSuccess("Nota Fiscal desvinculada.");
            abrirDetalhe(detalhe.header.codigo);
            carregar();
          } else {
            feedback.showError(friendlyApiError(j, "Não foi possível desvincular."));
          }
        } catch (e) {
          feedback.showError(friendlyCatchError(e));
        } finally {
          setDesvinculandoNf(null);
        }
      },
    );
  }, [conn, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const abrirBaixa = (p: Parcela) => {
    setBaixaVenc(p);
    setBaixaData(todayISO());
    setBaixaValor(String(p.valor).replace(".", ","));
    setBaixaDesconto(""); setBaixaOutrosDesc(""); setBaixaJuros(""); setBaixaOutrosAcresc(""); setBaixaTarifa("");
    setBaixaBanco(""); setBaixaAgencia(""); setBaixaBoleto(""); setBaixaObs("");
    setBaixaConta(p.conta ?? null); setBaixaFormaPag(p.forma_pag ?? null);
    setBaixaCheques([]);
    setNovoChequeBanco(""); setNovoChequeAgencia(""); setNovoChequeConta(""); setNovoChequeNumero("");
    setNovoChequeValor(""); setNovoChequeBomPara(null); setNovoChequeNome(""); setNovoChequeTelefone("");
  };

  const adicionarChequePre = () => {
    const valorNum = parseNum(novoChequeValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor do cheque."); return; }
    setBaixaCheques((atual) => [...atual, {
      banco: novoChequeBanco ? parseInt(novoChequeBanco, 10) : null,
      agencia: novoChequeAgencia.trim(), conta: novoChequeConta.trim(),
      numero_ch: novoChequeNumero ? parseInt(novoChequeNumero, 10) : null,
      valor: valorNum, bom_para: novoChequeBomPara, nome_cheque: novoChequeNome.trim(),
      telefone: novoChequeTelefone.trim(),
    }]);
    setNovoChequeBanco(""); setNovoChequeAgencia(""); setNovoChequeConta(""); setNovoChequeNumero("");
    setNovoChequeValor(""); setNovoChequeBomPara(null); setNovoChequeNome(""); setNovoChequeTelefone("");
  };

  const removerChequePre = (i: number) => {
    setBaixaCheques((atual) => atual.filter((_, idx) => idx !== i));
  };

  const confirmarBaixa = useCallback(async () => {
    if (!conn || !baixaVenc || !detalhe) return;
    const valorNum = parseNum(baixaValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor pago."); return; }
    if (!baixaData) { feedback.showError("Informe a data do pagamento."); return; }
    if (valorNum > baixaVenc.valor + 0.005) {
      feedback.showError("O valor não pode ser superior ao do vencimento. Use os campos Juros/Outros Acréscimo.");
      return;
    }
    setBaixando(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/baixar", "POST", {
        codigo_venc: baixaVenc.codigo, data_pag: baixaData, valor_pag: valorNum,
        desconto_pag: parseNum(baixaDesconto || "0"), outros_desc_pag: parseNum(baixaOutrosDesc || "0"),
        juros_pag: parseNum(baixaJuros || "0"), outros_acres_pag: parseNum(baixaOutrosAcresc || "0"),
        tarifa_banco: baixaTarifa ? parseNum(baixaTarifa) : null,
        banco_cedente: baixaBanco ? parseInt(baixaBanco, 10) : null,
        agencia_cedente: baixaAgencia ? parseInt(baixaAgencia, 10) : null,
        numero_boleto: baixaBoleto ? parseNum(baixaBoleto) : null,
        conta: baixaConta, forma_pag: baixaFormaPag, observacao: baixaObs, cheques: baixaCheques,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Baixa registrada.");
        setBaixaVenc(null);
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível dar baixa."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBaixando(false);
    }
  }, [conn, baixaVenc, baixaValor, baixaData, baixaDesconto, baixaOutrosDesc, baixaJuros, baixaOutrosAcresc,
      baixaTarifa, baixaBanco, baixaAgencia, baixaBoleto, baixaConta, baixaFormaPag, baixaObs, baixaCheques,
      detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const executarCancelamento = useCallback(async (p: Parcela, excluirCheques?: boolean) => {
    if (!conn || !detalhe) return;
    setCancelandoBaixa(p.codigo);
    try {
      const j = await apiSend(conn, "/api/contas-receber/cancelar-baixa", "POST", {
        codigo_venc: p.codigo, excluir_cheques: excluirCheques,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Baixa cancelada.");
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else if (j?.exige_confirmacao_cheque) {
        setCancelandoBaixa(null);
        feedback.showConfirm(
          j.message || `Existe(m) ${j.qtd_cheques} cheque(s) associado(s) a esta duplicata. Deseja excluir também?`,
          () => executarCancelamento(p, true),
          { confirmText: "Excluir cheque(s)", cancelText: "Manter cheque(s)", onCancel: () => executarCancelamento(p, false) },
        );
        return;
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível cancelar a baixa."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setCancelandoBaixa(null);
    }
  }, [conn, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const cancelarBaixa = useCallback((p: Parcela) => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Cancelar a baixa da parcela ${p.desmembramento}? Ela volta pra Aberto.`,
      () => executarCancelamento(p),
    );
  }, [conn, detalhe, feedback, executarCancelamento]);

  const abrirEditar = (p: Parcela) => {
    setEditParcela(p);
    setEditDtVenc(p.dt_vencimento);
    setEditValor(String(p.valor).replace(".", ","));
    setEditObs(p.observacao || "");
    setEditSituacao(p.situacao_duplicata || 0);
  };

  const confirmarEditar = useCallback(async () => {
    if (!conn || !editParcela || !detalhe) return;
    const valorNum = parseNum(editValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor."); return; }
    if (!editDtVenc) { feedback.showError("Informe a data de vencimento."); return; }
    setEditando(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/editar-parcela", "POST", {
        codigo_venc: editParcela.codigo, dt_vencimento: editDtVenc, valor: valorNum, observacao: editObs,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      // Situação do Vencimento (Normal/Jurídico/Protestado) — endpoint
      // dedicado, separado de propósito de editar-parcela (ver docstring
      // de _alterar_situacao_vencimento_sync no backend); só chama se
      // realmente mudou, pra não gerar log de auditoria à toa.
      if (j?.success && editSituacao !== (editParcela.situacao_duplicata || 0)) {
        await apiSend(conn, "/api/contas-receber/vencimento/situacao", "POST", {
          codigo_venc: editParcela.codigo, situacao_duplicata: editSituacao,
          usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
        });
      }
      if (j?.success) {
        feedback.showSuccess("Parcela atualizada.");
        setEditParcela(null);
        abrirDetalhe(detalhe.header.codigo);
        carregar();
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível editar a parcela."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setEditando(false);
    }
  }, [conn, editParcela, editDtVenc, editValor, editObs, editSituacao, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contas a Receber está disponível apenas no web." testID="contas-receber-web-only" />;
  }
  if (!loading && !can("CONTAS_RECEBER.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Contas a Receber." testID="contas-receber-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="contas-receber-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Contas a Receber</Text>
        {can("CONTAS_RECEBER.GRAVAR") || masterPerm ? (
          <IconButtonWithTooltip icon="add-circle-outline" label="Lançamento avulso" color={colors.onBrandPrimary} onPress={abrirAvulso} testID="contas-receber-avulso-btn" />
        ) : null}
        {can("CONTAS_RECEBER.BAIXAR") || masterPerm ? (
          <IconButtonWithTooltip icon="layers-outline" label="Pagamento/Cancelamento em Lote" color={colors.onBrandPrimary} onPress={() => setLoteOpen(true)} testID="contas-receber-lote-btn" />
        ) : null}
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary} onPress={() => setAjudaOpen(true)} testID="contas-receber-ajuda-btn" />
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : (
            <View style={{ gap: spacing.md }}>
              <AccordionSection title="Buscar e Filtrar" defaultExpanded>
                <View style={{ gap: spacing.sm }}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                    {SITUACOES.map((s) => (
                      <Pressable
                        key={s.key} onPress={() => setSituacao(s.key)}
                        style={[chipStyle(), situacao === s.key && chipSelStyle()]}
                        testID={`contas-receber-chip-${s.key || "todas"}`}
                      >
                        <Text style={[chipTextStyle(), situacao === s.key && chipTextSelStyle()]}>{s.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" }}>
                    <View style={{ flex: 1, minWidth: 220 }}>
                      <Text style={fieldLabel()}>Buscar por cliente ou nº da duplicata</Text>
                      <TextInput value={busca} onChangeText={setBusca} style={inputStyle()} testID="contas-receber-busca" onSubmitEditing={carregar} />
                    </View>
                    <Pressable onPress={() => setUsarPeriodo((v) => !v)} style={[chipStyle(), usarPeriodo && chipSelStyle(), { marginBottom: 2 }]}>
                      <Text style={[chipTextStyle(), usarPeriodo && chipTextSelStyle()]}>Filtrar por vencimento</Text>
                    </Pressable>
                    {usarPeriodo ? (
                      <>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>De</Text>
                          <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="contas-receber-data-ini" />
                        </View>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>Até</Text>
                          <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="contas-receber-data-fim" />
                        </View>
                      </>
                    ) : null}
                    <Pressable onPress={carregar} disabled={buscando} style={[secondaryBtnStyle(), { alignSelf: "flex-end" }]} testID="contas-receber-buscar-btn">
                      {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                        <><Ionicons name="search" size={16} color={colors.brandPrimary} /><Text style={secondaryBtnLabelStyle()}>Buscar</Text></>
                      )}
                    </Pressable>
                  </View>
                  {/* Filtros avançados (`FRMCONDUr.frm`, "Consulta de
                      Duplicatas à Receber...") — achado do usuário
                      2026-08-31, integrados aqui em vez de tela separada. */}
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap", marginTop: spacing.xs, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border }}>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Duplicata</Text>
                      <TextInput value={duplicataNum} onChangeText={setDuplicataNum} keyboardType="numeric" style={inputStyle()} testID="contas-receber-filtro-duplicata" />
                    </View>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Valor</Text>
                      <TextInput value={valorFiltro} onChangeText={setValorFiltro} keyboardType="numeric" style={inputStyle()} testID="contas-receber-filtro-valor" />
                    </View>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>Nº do Boleto</Text>
                      <TextInput value={numeroBoleto} onChangeText={setNumeroBoleto} keyboardType="numeric" style={inputStyle()} testID="contas-receber-filtro-boleto" />
                    </View>
                    <View style={{ width: 160 }}>
                      <Text style={fieldLabel()}>Situação do Vencimento</Text>
                      <SelectField value={situacaoDuplicataFiltro} onChange={(v) => setSituacaoDuplicataFiltro(v as number | null)} options={SITUACAO_VENCIMENTO_OPTIONS} placeholder="Todas" compactWeb allowClear testID="contas-receber-filtro-situacao-venc" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>Recebido de</Text>
                      <WebDateField value={recebidoIni} onChange={(v) => { setRecebidoIni(v || null); if (v) setRecebidoFim(v); }} testID="contas-receber-recebido-ini" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>até</Text>
                      <WebDateField value={recebidoFim} onChange={(v) => setRecebidoFim(v || null)} testID="contas-receber-recebido-fim" />
                    </View>
                  </View>
                </View>
              </AccordionSection>

              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Duplicatas ({items.length})</Text>
                {items.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhuma duplicata encontrada.</Text>
                ) : (
                  items.map((it) => (
                    <Pressable key={it.codigo} onPress={() => abrirDetalhe(it.codigo)} style={itemRowStyle()} testID={`contas-receber-item-${it.codigo}`}>
                      <View style={[situacaoDotStyle(), { backgroundColor: it.vencido ? colors.error : it.situacao === "PG" ? colors.success : colors.brandPrimary }]} />
                      <View style={{ flex: 1, marginLeft: spacing.sm }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: it.vencido ? colors.error : colors.onSurface }}>
                          Duplicata #{it.duplicata}{it.desmembramento ? `/${it.desmembramento}` : ""}{"  ·  "}{it.cliente_nome}
                        </Text>
                        <Text style={{ fontSize: 12, color: it.vencido ? colors.error : colors.muted }}>
                          {formatDateBR(it.dt_emissao)}{it.proximo_vencimento ? ` · Próx. venc. ${formatDateBR(it.proximo_vencimento)}${it.vencido ? " (vencido)" : ""}` : ""}
                          {" · "}{it.parcelas_pagas}/{it.num_parcelas} paga(s)
                        </Text>
                      </View>
                      <View style={{ alignItems: "flex-end" }}>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>{formatBRL(it.valor)}</Text>
                        {it.situacao !== "PG" ? <Text style={{ fontSize: 11, color: colors.muted }}>Em aberto: {formatBRL(it.valor_em_aberto)}</Text> : null}
                      </View>
                    </Pressable>
                  ))
                )}
              </View>
            </View>
          )}
        </View>
      </ScrollView>

      {/* ---- Modal: Lançamento avulso ---- */}
      <Modal visible={avulsoOpen} transparent animationType="slide" onRequestClose={() => setAvulsoOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setAvulsoOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <View style={ps.modalHeader}>
                <Text style={ps.modalTitle}>Lançamento Avulso</Text>
                <Pressable onPress={() => setAvulsoOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <View style={{ gap: spacing.sm }}>
                <View>
                  <Text style={fieldLabel()}>Cliente *</Text>
                  <Pressable onPress={() => setAvClienteSearchOpen(true)} style={[inputStyle(), { justifyContent: "center" }]} testID="contas-receber-avulso-cliente-btn">
                    <Text style={{ color: avClienteNome ? colors.onSurface : colors.muted }}>{avClienteNome || "Buscar cliente…"}</Text>
                  </Pressable>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 120 }}>
                    <Text style={fieldLabel()}>Número *</Text>
                    <TextInput value={avNumero} onChangeText={setAvNumero} keyboardType="numeric" style={inputStyle()} testID="contas-receber-avulso-numero" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Série</Text>
                    <TextInput value={avSerie} onChangeText={setAvSerie} style={inputStyle()} testID="contas-receber-avulso-serie" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Tipo de Movimentação *</Text>
                    <SelectField value={avTipoMov} onChange={(v) => setAvTipoMov(v as string)} options={tiposMov} compactWeb testID="contas-receber-avulso-tipomov" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Data de Emissão</Text>
                    <WebDateField value={avDtEmissao} onChange={(v) => setAvDtEmissao(v || null)} testID="contas-receber-avulso-dtemissao" />
                  </View>
                  <View style={{ width: 130 }}>
                    <Text style={fieldLabel()}>Valor *</Text>
                    <TextInput value={avValor} onChangeText={setAvValor} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-avulso-valor" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Parcelas</Text>
                    <TextInput value={avParcelas} onChangeText={setAvParcelas} keyboardType="numeric" style={inputStyle()} testID="contas-receber-avulso-parcelas" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>1º Vencimento *</Text>
                    <WebDateField value={avDtVenc} onChange={(v) => setAvDtVenc(v || null)} testID="contas-receber-avulso-dtvenc" />
                  </View>
                </View>
                <Text style={[fieldLabel(), { fontStyle: "italic" }]}>
                  Com mais de 1 parcela, o valor é dividido igualmente (a última absorve o arredondamento) e o vencimento avança 1 mês por parcela.
                </Text>
                <View>
                  <Text style={fieldLabel()}>Observação</Text>
                  <TextInput value={avObs} onChangeText={setAvObs} style={[inputStyle(), { minHeight: 60 }]} multiline testID="contas-receber-avulso-obs" />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setAvulsoOpen(false)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={salvarAvulso} disabled={salvandoAvulso} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-avulso-salvar">
                    {salvandoAvulso ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <ClientSearchModal
        visible={avClienteSearchOpen} onClose={() => setAvClienteSearchOpen(false)}
        term={avClienteTerm} setTerm={setAvClienteTerm} loading={avClienteLoading} results={avClienteResults}
        onPick={(c) => { setAvClienteCod(Number(c.codigo)); setAvClienteNome(c.nome); setAvClienteSearchOpen(false); }}
        onCreate={() => setAvClienteSearchOpen(false)}
      />

      {/* ---- Modal: Detalhe da duplicata ---- */}
      <Modal visible={detalheOpen} transparent animationType="slide" onRequestClose={() => setDetalheOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setDetalheOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            {detalheLoading || !detalhe ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 40 }} />
            ) : (
              <ScrollView>
                <View style={ps.modalHeader}>
                  <Text style={ps.modalTitle}>Duplicata #{detalhe.header.duplicata}{detalhe.header.desmembramento ? `/${detalhe.header.desmembramento}` : ""}</Text>
                  <Pressable onPress={() => setDetalheOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
                </View>
                <Text style={{ fontSize: 14, color: colors.onSurface, marginBottom: 4 }}>{detalhe.header.cliente_nome}</Text>
                <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.md }}>
                  Emissão {formatDateBR(detalhe.header.dt_emissao)} · Valor total {formatBRL(detalhe.header.valor)}
                </Text>

                <Text style={labelStyle()}>Parcelas</Text>
                {detalhe.parcelas.map((p) => (
                  <View key={p.codigo} style={parcelaRowStyle()}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
                        Parcela {p.desmembramento} · {formatBRL(p.valor)}
                      </Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>
                        Venc. {formatDateBR(p.dt_vencimento)}
                        {p.situacao === "PG" ? ` · Pago em ${formatDateBR(p.data_pag)} (${formatBRL(p.valor_pag || 0)})` : " · Aberto"}
                      </Text>
                    </View>
                    {p.situacao !== "PG" ? (
                      <View style={{ flexDirection: "row", gap: spacing.xs }}>
                        {can("CONTAS_RECEBER.GRAVAR") || masterPerm ? (
                          <Pressable onPress={() => abrirEditar(p)} style={smallBtnStyle()} testID={`contas-receber-editar-${p.codigo}`}>
                            <Ionicons name="create-outline" size={14} color={colors.brandPrimary} />
                            <Text style={smallBtnLabelStyle()}>Editar</Text>
                          </Pressable>
                        ) : null}
                        {can("CONTAS_RECEBER.BAIXAR") || masterPerm ? (
                          <Pressable onPress={() => abrirBaixa(p)} style={smallBtnStyle()} testID={`contas-receber-baixar-${p.codigo}`}>
                            <Ionicons name="checkmark-done-outline" size={14} color={colors.brandPrimary} />
                            <Text style={smallBtnLabelStyle()}>Baixar</Text>
                          </Pressable>
                        ) : null}
                      </View>
                    ) : p.situacao === "PG" ? (
                      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                        <View style={[situacaoBadgeStyle(), { backgroundColor: colors.success + "22" }]}>
                          <Text style={[situacaoBadgeTextStyle(), { color: colors.success }]}>Pago</Text>
                        </View>
                        {(can("CONTAS_RECEBER.BAIXAR") || masterPerm) ? (
                          <Pressable onPress={() => abrirRecibo(p)} style={smallBtnStyle()} testID={`contas-receber-recibo-${p.codigo}`}>
                            <Ionicons name="receipt-outline" size={14} color={colors.brandPrimary} />
                            <Text style={smallBtnLabelStyle()}>Recibo</Text>
                          </Pressable>
                        ) : null}
                        {(can("CONTAS_RECEBER.BAIXAR") || masterPerm) ? (
                          <Pressable onPress={() => cancelarBaixa(p)} disabled={cancelandoBaixa === p.codigo} style={smallBtnStyle()} testID={`contas-receber-cancelar-baixa-${p.codigo}`}>
                            {cancelandoBaixa === p.codigo ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                              <><Ionicons name="arrow-undo-outline" size={14} color={colors.brandPrimary} /><Text style={smallBtnLabelStyle()}>Cancelar</Text></>
                            )}
                          </Pressable>
                        ) : null}
                      </View>
                    ) : null}
                  </View>
                ))}

                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.lg, marginBottom: spacing.xs }}>
                  <Text style={labelStyle()}>Notas Fiscais</Text>
                  {(can("CONTAS_RECEBER.GRAVAR") || masterPerm) ? (
                    <Pressable onPress={abrirVincularNf} style={smallBtnStyle()} testID="contas-receber-vincular-nf-btn">
                      <Ionicons name="add" size={14} color={colors.brandPrimary} />
                      <Text style={smallBtnLabelStyle()}>Vincular NF</Text>
                    </Pressable>
                  ) : null}
                </View>
                {detalhe.notas.length === 0 ? (
                  <Text style={{ fontSize: 12, color: colors.muted }}>Nenhuma nota fiscal vinculada.</Text>
                ) : detalhe.notas.map((n) => (
                  <View key={n.codigo} style={parcelaRowStyle()}>
                    <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>
                      NF {n.nota_fiscal}{n.serie ? `/${n.serie}` : ""}
                    </Text>
                    {(can("CONTAS_RECEBER.GRAVAR") || masterPerm) ? (
                      <Pressable onPress={() => desvincularNf(n.codigo, n.nota_fiscal)} disabled={desvinculandoNf === n.codigo} style={smallBtnStyle()} testID={`contas-receber-desvincular-nf-${n.codigo}`}>
                        {desvinculandoNf === n.codigo ? <ActivityIndicator color={colors.error} size="small" /> : (
                          <><Ionicons name="close-circle-outline" size={14} color={colors.error} /><Text style={[smallBtnLabelStyle(), { color: colors.error }]}>Desvincular</Text></>
                        )}
                      </Pressable>
                    ) : null}
                  </View>
                ))}

                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
                  {(can("CONTAS_RECEBER.GRAVAR") || masterPerm) ? (
                    <Pressable onPress={abrirAlterarNumero} style={ps.secondaryBtn} testID="contas-receber-alterar-numero-btn">
                      <Ionicons name="create-outline" size={16} color={colors.brandPrimary} /><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Alterar Número</Text>
                    </Pressable>
                  ) : null}
                  {(can("CONTAS_RECEBER.EXCLUIR") || masterPerm) ? (
                    <Pressable onPress={excluirDuplicata} disabled={excluindo} style={[ps.secondaryBtn, { borderColor: colors.error }]} testID="contas-receber-excluir-btn">
                      {excluindo ? <ActivityIndicator color={colors.error} size="small" /> : (
                        <><Ionicons name="trash-outline" size={16} color={colors.error} /><Text style={{ color: colors.error, fontWeight: "600" }}>Excluir Duplicata</Text></>
                      )}
                    </Pressable>
                  ) : null}
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* "Vincular Nota Fiscal" — lista NFs em aberto do mesmo grupo
          CGC/CPF (matriz/filiais), toque vincula direto (mesmo padrão de
          "duplo-clique inclui" do legado, `NF2_DblClick`). */}
      <Modal visible={notasVincularOpen} transparent animationType="slide" onRequestClose={() => setNotasVincularOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setNotasVincularOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Vincular Nota Fiscal</Text>
              <Pressable onPress={() => setNotasVincularOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.sm }}>
              Notas fiscais em aberto do mesmo CNPJ/CPF (matriz e filiais). Toque pra vincular a esta duplicata.
            </Text>
            {notasCarregando ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : notasDisponiveis.length === 0 ? (
              <Text style={{ fontSize: 13, color: colors.muted, textAlign: "center", marginVertical: 24 }}>Nenhuma nota fiscal disponível.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 360 }}>
                {notasDisponiveis.map((n) => (
                  <Pressable key={n.codigo} onPress={() => vincularNf(n.codigo)} disabled={vinculandoNf === n.codigo} style={parcelaRowStyle()} testID={`contas-receber-nf-disponivel-${n.codigo}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>NF {n.nota_fiscal}{n.serie ? `/${n.serie}` : ""} · {formatBRL(n.valor)}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>{n.cliente_nome}</Text>
                    </View>
                    {vinculandoNf === n.codigo ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Ionicons name="add-circle-outline" size={20} color={colors.brandPrimary} />}
                  </Pressable>
                ))}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* "Alterar Número da Duplicata" — modal próprio (o legado usa um
          InputBox nativo, nunca replicado neste projeto). Efeito colateral
          real explicado no texto: renumerar apaga previsões de
          Transferência p/Fluxo de Caixa vinculadas, já que elas
          referenciam o número antigo. */}
      <Modal visible={alterarNumeroOpen} transparent animationType="slide" onRequestClose={() => setAlterarNumeroOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setAlterarNumeroOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Alterar Número da Duplicata</Text>
              <Pressable onPress={() => setAlterarNumeroOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <View style={{ gap: spacing.sm }}>
              <Text style={{ fontSize: 12, color: colors.muted }}>
                Se esta duplicata já tiver sido transferida pro Fluxo de Caixa, as previsões vinculadas a ela serão removidas (referenciam o número antigo) — será preciso gerar uma nova transferência depois.
              </Text>
              <View>
                <Text style={fieldLabel()}>Novo Número</Text>
                <TextInput value={novoNumero} onChangeText={setNovoNumero} keyboardType="numeric" style={inputStyle()} testID="contas-receber-novo-numero" />
              </View>
              <View style={ps.modalBtns}>
                <Pressable onPress={() => setAlterarNumeroOpen(false)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                <Pressable onPress={confirmarAlterarNumero} disabled={alterandoNumero} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-alterar-numero-confirmar">
                  {alterandoNumero ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Confirmar</Text>}
                </Pressable>
              </View>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* "Emitir Recibo" — tier "confirmação pontual" (~420px). Recebemos/
          Valor/Referente pré-preenchidos a partir da parcela paga,
          editáveis (mesmo princípio do formulário legado standalone
          `frmmanrecibo.frm`, que também sempre exige preenchimento
          manual antes de gravar). */}
      <Modal visible={!!reciboParcela} transparent animationType="slide" onRequestClose={() => setReciboParcela(null)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setReciboParcela(null)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <View style={ps.modalHeader}>
                <Text style={ps.modalTitle}>Emitir Recibo</Text>
                <Pressable onPress={() => setReciboParcela(null)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <View style={{ gap: spacing.sm }}>
                <View>
                  <Text style={fieldLabel()}>Recebemos de *</Text>
                  <TextInput value={reciboRecebemos} onChangeText={setReciboRecebemos} style={inputStyle()} testID="contas-receber-recibo-recebemos" />
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Valor *</Text>
                    <TextInput value={reciboValor} onChangeText={setReciboValor} keyboardType="numeric" style={inputStyle()} testID="contas-receber-recibo-valor" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Data</Text>
                    <WebDateField value={reciboData} onChange={(v) => setReciboData(v || null)} testID="contas-receber-recibo-data" />
                  </View>
                </View>
                <View>
                  <Text style={fieldLabel()}>Referente à *</Text>
                  <TextInput value={reciboReferente} onChangeText={setReciboReferente} style={inputStyle()} testID="contas-receber-recibo-referente" />
                </View>
                <View>
                  <Text style={fieldLabel()}>Assinatura</Text>
                  <TextInput
                    value={reciboAssinatura} onChangeText={setReciboAssinatura}
                    placeholder="Padrão: razão social da empresa" placeholderTextColor={colors.muted}
                    style={inputStyle()} testID="contas-receber-recibo-assinatura"
                  />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setReciboParcela(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={confirmarEmitirRecibo} disabled={emitindoRecibo} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-recibo-confirmar">
                    {emitindoRecibo ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar e Imprimir</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ---- Modal: Baixar parcela ---- */}
      <Modal visible={!!baixaVenc} transparent animationType="slide" onRequestClose={() => setBaixaVenc(null)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setBaixaVenc(null)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <View style={ps.modalHeader}>
                <Text style={ps.modalTitle}>Dar Baixa — Parcela {baixaVenc?.desmembramento}</Text>
                <Pressable onPress={() => setBaixaVenc(null)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <View style={{ gap: spacing.sm }}>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Data do Pagamento *</Text>
                    <WebDateField value={baixaData} onChange={(v) => setBaixaData(v || null)} testID="contas-receber-baixa-data" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Forma de Pagamento *</Text>
                    <SelectField value={baixaFormaPag} onChange={(v) => setBaixaFormaPag(v as string)} options={formaPagOpts} compactWeb allowClear testID="contas-receber-baixa-formapag" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Conta *</Text>
                    <SelectField value={baixaConta} onChange={(v) => setBaixaConta(v == null ? null : Number(v))} options={contasOpts} compactWeb allowClear testID="contas-receber-baixa-conta" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Valor Pago *</Text>
                    <TextInput value={baixaValor} onChangeText={setBaixaValor} keyboardType="numeric" style={inputStyle()} testID="contas-receber-baixa-valor" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Desconto</Text>
                    <TextInput value={baixaDesconto} onChangeText={setBaixaDesconto} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-desconto" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Outros Desconto</Text>
                    <TextInput value={baixaOutrosDesc} onChangeText={setBaixaOutrosDesc} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-outrosdesc" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Juros/Multa</Text>
                    <TextInput value={baixaJuros} onChangeText={setBaixaJuros} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-juros" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Outros Acréscimo</Text>
                    <TextInput value={baixaOutrosAcresc} onChangeText={setBaixaOutrosAcresc} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-outrosacresc" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Tarifa Banco</Text>
                    <TextInput value={baixaTarifa} onChangeText={setBaixaTarifa} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-baixa-tarifa" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Nº Boleto</Text>
                    <TextInput value={baixaBoleto} onChangeText={setBaixaBoleto} keyboardType="numeric" style={inputStyle()} testID="contas-receber-baixa-boleto" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Banco</Text>
                    <TextInput value={baixaBanco} onChangeText={setBaixaBanco} keyboardType="numeric" style={inputStyle()} testID="contas-receber-baixa-banco" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Agência</Text>
                    <TextInput value={baixaAgencia} onChangeText={setBaixaAgencia} keyboardType="numeric" style={inputStyle()} testID="contas-receber-baixa-agencia" />
                  </View>
                </View>
                <View style={{ borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm, gap: spacing.xs }}>
                  <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>Cheques Pré-Datados (opcional)</Text>
                  <Text style={{ fontSize: 11, color: colors.muted }}>
                    Se o cliente deixou cheque(s) pré-datado(s) como parte deste pagamento, cadastre aqui — eles ficam registrados como "a receber" na data de bom para, sem precisar de outra tela.
                  </Text>
                  <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
                    <View style={{ width: 90 }}>
                      <Text style={fieldLabel()}>Banco</Text>
                      <TextInput value={novoChequeBanco} onChangeText={setNovoChequeBanco} keyboardType="numeric" style={inputStyle()} testID="contas-receber-cheque-banco" />
                    </View>
                    <View style={{ width: 90 }}>
                      <Text style={fieldLabel()}>Agência</Text>
                      <TextInput value={novoChequeAgencia} onChangeText={setNovoChequeAgencia} style={inputStyle()} testID="contas-receber-cheque-agencia" />
                    </View>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Conta</Text>
                      <TextInput value={novoChequeConta} onChangeText={setNovoChequeConta} style={inputStyle()} testID="contas-receber-cheque-conta" />
                    </View>
                    <View style={{ width: 100 }}>
                      <Text style={fieldLabel()}>Nº Cheque</Text>
                      <TextInput value={novoChequeNumero} onChangeText={setNovoChequeNumero} keyboardType="numeric" style={inputStyle()} testID="contas-receber-cheque-numero" />
                    </View>
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.xs, flexWrap: "wrap" }}>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Valor *</Text>
                      <TextInput value={novoChequeValor} onChangeText={setNovoChequeValor} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-receber-cheque-valor" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>Bom Para</Text>
                      <WebDateField value={novoChequeBomPara} onChange={(v) => setNovoChequeBomPara(v || null)} testID="contas-receber-cheque-bompara" />
                    </View>
                    <View style={{ flex: 1, minWidth: 140 }}>
                      <Text style={fieldLabel()}>Nome no Cheque</Text>
                      <TextInput value={novoChequeNome} onChangeText={setNovoChequeNome} style={inputStyle()} testID="contas-receber-cheque-nome" />
                    </View>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>Telefone</Text>
                      <TextInput value={novoChequeTelefone} onChangeText={setNovoChequeTelefone} keyboardType="numeric" style={inputStyle()} testID="contas-receber-cheque-telefone" />
                    </View>
                  </View>
                  <Pressable
                    onPress={adicionarChequePre}
                    style={[ps.secondaryBtn, { alignSelf: "flex-start", flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8 }]}
                    testID="contas-receber-cheque-adicionar"
                  >
                    <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                    <Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Adicionar Cheque</Text>
                  </Pressable>
                  {baixaCheques.length > 0 && (
                    <View style={{ gap: spacing.xs }}>
                      {baixaCheques.map((c, i) => (
                        <View key={i} style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surfaceTertiary, borderRadius: 6, paddingVertical: 6, paddingHorizontal: spacing.sm }}>
                          <Text style={{ fontSize: 12, color: colors.onSurface, flex: 1 }}>
                            {formatBRL(c.valor)}{c.banco ? ` · Banco ${c.banco}` : ""}{c.numero_ch ? ` · Cheque nº ${c.numero_ch}` : ""}{c.bom_para ? ` · Bom p/ ${c.bom_para}` : ""}
                          </Text>
                          <Pressable onPress={() => removerChequePre(i)} hitSlop={8} testID={`contas-receber-cheque-remover-${i}`}>
                            <Ionicons name="trash-outline" size={16} color={colors.error} />
                          </Pressable>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
                <View>
                  <Text style={fieldLabel()}>Observação</Text>
                  <TextInput value={baixaObs} onChangeText={setBaixaObs} style={[inputStyle(), { minHeight: 50 }]} multiline testID="contas-receber-baixa-obs" />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setBaixaVenc(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={confirmarBaixa} disabled={baixando} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-baixa-confirmar">
                    {baixando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Confirmar Baixa</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ---- Modal: Editar parcela ---- */}
      <Modal visible={!!editParcela} transparent animationType="slide" onRequestClose={() => setEditParcela(null)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setEditParcela(null)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Editar Parcela {editParcela?.desmembramento}</Text>
              <Pressable onPress={() => setEditParcela(null)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <View style={{ gap: spacing.sm }}>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ width: 150 }}>
                  <Text style={fieldLabel()}>Vencimento *</Text>
                  <WebDateField value={editDtVenc} onChange={(v) => setEditDtVenc(v || null)} testID="contas-receber-editar-data" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Valor *</Text>
                  <TextInput value={editValor} onChangeText={setEditValor} keyboardType="numeric" style={inputStyle()} testID="contas-receber-editar-valor" />
                </View>
              </View>
              <View>
                <Text style={fieldLabel()}>Observação</Text>
                <TextInput value={editObs} onChangeText={setEditObs} style={[inputStyle(), { minHeight: 60 }]} multiline testID="contas-receber-editar-obs" />
              </View>
              <View>
                <Text style={fieldLabel()}>Situação do Vencimento</Text>
                <SelectField value={editSituacao} onChange={(v) => setEditSituacao((v as number) ?? 0)} options={SITUACAO_VENCIMENTO_OPTIONS} compactWeb testID="contas-receber-editar-situacao" />
              </View>
              <View style={ps.modalBtns}>
                <Pressable onPress={() => setEditParcela(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                <Pressable onPress={confirmarEditar} disabled={editando} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-receber-editar-confirmar">
                  {editando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar</Text>}
                </Pressable>
              </View>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <LoteBaixaModal
        visible={loteOpen} onClose={() => setLoteOpen(false)} conn={conn} apiBase="contas-receber"
        entidadeLabel="Cliente" permitirMontante contasOpts={contasOpts} formaPagOpts={formaPagOpts}
        usuarioCod={usuarioCod} classe={classePerm} onDone={carregar}
      />

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Contas a Receber" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

function headerStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary };
}
function headerTitleStyle() {
  return { flex: 1, fontSize: 17, fontWeight: "700" as const, color: colors.onBrandPrimary };
}
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 };
}
function fieldLabel() {
  return { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const };
}
function inputStyle() {
  return { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.sm, paddingVertical: 10, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary } as const;
}
function itemRowStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border };
}
function situacaoDotStyle() {
  return { width: 8, height: 8, borderRadius: 4 };
}
function chipStyle() {
  return { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface };
}
function chipSelStyle() {
  return { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary };
}
function chipTextStyle() {
  return { fontSize: 12, fontWeight: "600" as const, color: colors.onSurface };
}
function chipTextSelStyle() {
  return { color: colors.onBrandPrimary };
}
function secondaryBtnStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 100 };
}
function secondaryBtnLabelStyle() {
  return { color: colors.brandPrimary, fontWeight: "600" as const, fontSize: 14 };
}
function parcelaRowStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border };
}
function smallBtnStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, gap: 4, paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary };
}
function smallBtnLabelStyle() {
  return { fontSize: 12, fontWeight: "600" as const, color: colors.brandPrimary };
}
function situacaoBadgeStyle() {
  return { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill };
}
function situacaoBadgeTextStyle() {
  return { fontSize: 10, fontWeight: "700" as const };
}
