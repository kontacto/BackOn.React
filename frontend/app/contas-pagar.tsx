// Financeiro > Contas a Pagar — espelho de contas-receber.tsx pro lado
// Pagar. Fonte VB6: `Geral/FRMCONNFPAG.frm` (consulta) +
// `Geral/frmTraNFPag.frm` (CRUD/avulso) + `Revenda/frmmandup.frm`
// (duplicata/parcelas) — ver backend/services/contas_pagar_service.py
// pro rastreio completo.
//
// Mesmo escopo já aprovado pro lado Receber (AskUserQuestion, 2026-08-28):
// lançamento avulso + baixa manual (funcionalidade NOVA — o legado só
// baixa via retorno CNAB, e só pro lado Receber; Pagar nunca teve nem
// isso) + exclusão com guarda. Sem Centro de Resultados/Emitir Fatura —
// o legado (`frmmandup.frm`) nem tem esses botões neste lado.
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
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
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

const isWeb = Platform.OS === "web";

type Duplicata = {
  codigo: number; fornecedor: number; fornecedor_nome: string; duplicata: number; desmembramento: string | null;
  dt_emissao: string | null; valor: number; situacao: string; num_parcelas: number; parcelas_pagas: number;
  proximo_vencimento: string | null; valor_em_aberto: number; vencido: boolean;
};

type Parcela = {
  codigo: number; desmembramento: number; dt_vencimento: string | null; valor: number; situacao: string;
  data_pag: string | null; valor_pag: number | null; desconto_pag: number | null; juros_pag: number | null;
  conta: number | null; forma_pag: string | null; observacao: string | null;
};

type Detalhe = { header: Duplicata; parcelas: Parcela[]; notas: { codigo: number; nota_fiscal: number; serie: string }[] };

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que esta tela faz", texto: "Lista as duplicatas a pagar já lançadas (vindas de Nota Fiscal de compra ou digitadas aqui mesmo) e deixa acompanhar/baixar as parcelas.", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Lançamento avulso", texto: "Use quando você tem um valor a pagar que não veio de Nota Fiscal — digite fornecedor, valor e vencimento(s) direto.", icon: { lib: "ion", name: "add-circle-outline" } },
  { titulo: "Baixa manual", texto: "Marca uma parcela como paga quando você pagou por dinheiro, PIX ou transferência direta. Uma vez baixada, a parcela não pode mais ser editada.", icon: { lib: "ion", name: "checkmark-done-outline" } },
  { titulo: "Cancelar baixa", texto: "Desfaz uma baixa feita por engano — a parcela volta pra Aberto e os dados de pagamento são apagados.", icon: { lib: "ion", name: "arrow-undo-outline" } },
  { titulo: "Pagamento/Cancelamento em Lote", texto: "Dá baixa (ou cancela) em várias parcelas de uma vez, filtrando por período — sem precisar abrir cada duplicata.", icon: { lib: "ion", name: "layers-outline" } },
  { titulo: "Editar parcela", texto: "Corrige data de vencimento, valor ou observação de uma parcela ainda em aberto. Uma parcela já paga não pode mais ser editada.", icon: { lib: "ion", name: "create-outline" } },
  { titulo: "Vencido", texto: "Parcela em aberto cuja data de vencimento já passou — aparece em destaque vermelho.", icon: { lib: "ion", name: "alert-circle-outline" } },
  { titulo: "Excluir", texto: "Só é possível excluir uma duplicata se NENHUMA parcela dela já tiver sido paga.", icon: { lib: "ion", name: "trash-outline" } },
  { titulo: "Alterar Número", texto: "Troca o número da duplicata (bloqueia se já existir outra com esse número). Se ela já tiver sido transferida pro Fluxo de Caixa, as previsões vinculadas são removidas — gere uma nova transferência depois com o número novo.", icon: { lib: "ion", name: "create-outline" } },
  { titulo: "Notas Fiscais", texto: "Vincule mais de uma Nota Fiscal na mesma duplicata (útil quando o fornecedor tem filiais faturando junto). Só mostra NFs em aberto do mesmo documento. Desvincular só é permitido se nenhuma parcela já tiver sido paga.", icon: { lib: "ion", name: "document-text-outline" } },
];

const SITUACOES: { key: string; label: string }[] = [
  { key: "", label: "Todas" }, { key: "A", label: "Aberto" }, { key: "V", label: "Vencido" }, { key: "PG", label: "Pago" },
];

export default function ContasPagarScreen() {
  const router = useRouter();
  // `?situacao=` — deep-link a partir do Painel Financeiro (cards
  // "Pagamentos em Atraso"/"À Pagar Hoje"), pra abrir esta tela já
  // filtrada em vez do padrão "Aberto" — ver painel-financeiro.tsx.
  const params = useLocalSearchParams<{ situacao?: string }>();
  const { can, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [busca, setBusca] = useState("");
  const [situacao, setSituacao] = useState(() => (typeof params.situacao === "string" ? params.situacao : "A"));
  const [dataIni, setDataIni] = useState<string | null>(todayISO());
  const [dataFim, setDataFim] = useState<string | null>(todayISO());
  const [usarPeriodo, setUsarPeriodo] = useState(false);
  const [items, setItems] = useState<Duplicata[]>([]);

  // Filtros extras, rastreados de `Revenda/frmcondup.frm` ("Consulta de
  // Duplicatas a Pagar..."), mirror dos que já existem em
  // contas-receber.tsx a partir de `FRMCONDur.frm`. Achado do usuário
  // 2026-08-31 — ver AJUSTES.md #039. Sem "Situação do Vencimento"
  // (Protestado/etc.) — confirmado ausente na fonte real do lado Pagar.
  const [duplicataNum, setDuplicataNum] = useState("");
  const [valorFiltro, setValorFiltro] = useState("");
  const [numeroBoleto, setNumeroBoleto] = useState("");
  const [numDocPag, setNumDocPag] = useState("");
  const [emissaoIni, setEmissaoIni] = useState<string | null>(null);
  const [emissaoFim, setEmissaoFim] = useState<string | null>(null);

  const [tiposMov, setTiposMov] = useState<SelectOption[]>([]);
  const [contasOpts, setContasOpts] = useState<SelectOption[]>([]);
  const [formaPagOpts, setFormaPagOpts] = useState<SelectOption[]>([]);
  const [loteOpen, setLoteOpen] = useState(false);

  // ---- Lançamento avulso ----
  const [avulsoOpen, setAvulsoOpen] = useState(false);
  const [salvandoAvulso, setSalvandoAvulso] = useState(false);
  const [avFornCod, setAvFornCod] = useState<number | null>(null);
  const [avFornNome, setAvFornNome] = useState("");
  const [avFornSearchOpen, setAvFornSearchOpen] = useState(false);
  const [avFornTerm, setAvFornTerm] = useState("");
  const [avFornResults, setAvFornResults] = useState<FornecedorRow[]>([]);
  const [avFornLoading, setAvFornLoading] = useState(false);
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
  // "Alterar Nº Duplicata" (`frmmandup.frm::Command15_Click`) — mirror do
  // já existente em Contas a Receber. Modal próprio (nunca prompt()/
  // alert() do navegador, padrão do projeto).
  const [alterarNumeroOpen, setAlterarNumeroOpen] = useState(false);
  const [novoNumero, setNovoNumero] = useState("");
  const [alterandoNumero, setAlterandoNumero] = useState(false);

  // "Notas Fiscais" — vincular/desvincular NF adicional numa duplicata já
  // existente (`frmmandup.frm::Command5_Click`/`NF2_DblClick`/
  // `NF_DblClick`). Mirror do já existente em Contas a Receber.
  const [notasVincularOpen, setNotasVincularOpen] = useState(false);
  const [notasDisponiveis, setNotasDisponiveis] = useState<{ codigo: number; codigo_fornecedor: number; fornecedor_nome: string; nota_fiscal: number; serie: string | null; valor: number }[]>([]);
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
  const [baixaDocumento, setBaixaDocumento] = useState("");
  const [baixaConta, setBaixaConta] = useState<number | null>(null);
  const [baixaFormaPag, setBaixaFormaPag] = useState<string | null>(null);
  const [baixaObs, setBaixaObs] = useState("");
  const [baixando, setBaixando] = useState(false);

  // ---- Cancelar baixa ----
  const [cancelandoBaixa, setCancelandoBaixa] = useState<number | null>(null);

  // ---- Editar parcela em aberto ----
  const [editParcela, setEditParcela] = useState<Parcela | null>(null);
  const [editDtVenc, setEditDtVenc] = useState<string | null>(null);
  const [editValor, setEditValor] = useState("");
  const [editObs, setEditObs] = useState("");
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
        const j = await apiGet(conn, "/api/contas-pagar-tipos-mov");
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
      if (numDocPag.trim()) params.num_doc_pag = numDocPag.trim();
      if (emissaoIni && emissaoFim) {
        params.emissao_ini = emissaoIni;
        params.emissao_fim = emissaoFim;
      }
      const j = await apiGet(conn, "/api/contas-pagar", params);
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
  }, [conn, situacao, busca, usarPeriodo, dataIni, dataFim, duplicataNum, valorFiltro, numeroBoleto, numDocPag, emissaoIni, emissaoFim, feedback]);

  // Situação re-busca sozinha ao trocar o chip; busca por texto/período continuam manuais (Enter/Buscar).
  useEffect(() => { if (conn) carregar(); }, [conn, situacao]); // eslint-disable-line react-hooks/exhaustive-deps

  // ---- Busca de fornecedor (avulso) ----
  useEffect(() => {
    if (!avFornSearchOpen || !conn) return;
    const term = avFornTerm.trim();
    if (term.length < 2) { setAvFornResults([]); return; }
    setAvFornLoading(true);
    const t = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(term)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setAvFornResults(j?.success ? (j.items || []) : []);
      } catch { setAvFornResults([]); } finally { setAvFornLoading(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [avFornTerm, avFornSearchOpen, conn]);

  const abrirAvulso = () => {
    setAvFornCod(null); setAvFornNome(""); setAvNumero(""); setAvSerie("");
    setAvTipoMov(null); setAvDtEmissao(todayISO()); setAvValor(""); setAvParcelas("1");
    setAvDtVenc(todayISO()); setAvObs("");
    setAvulsoOpen(true);
  };

  const salvarAvulso = useCallback(async () => {
    if (!conn) return;
    if (!avFornCod) { feedback.showError("Selecione o fornecedor."); return; }
    if (!avNumero.trim() || !/^\d+$/.test(avNumero.trim())) { feedback.showError("Informe um número válido."); return; }
    if (!avTipoMov) { feedback.showError("Selecione o Tipo de Movimentação."); return; }
    const valorNum = parseNum(avValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor."); return; }
    const parcelasNum = parseInt(avParcelas || "1", 10) || 1;
    if (!avDtVenc) { feedback.showError("Informe a data do 1º vencimento."); return; }

    setSalvandoAvulso(true);
    try {
      const j = await apiSend(conn, "/api/contas-pagar/avulsa", "POST", {
        fornecedor: avFornCod, numero: parseInt(avNumero.trim(), 10), serie: avSerie.trim(),
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
  }, [conn, avFornCod, avNumero, avSerie, avTipoMov, avDtEmissao, avValor, avParcelas, avDtVenc, avObs, usuarioCod, classePerm, feedback, carregar]);

  const abrirDetalhe = useCallback(async (codigo: number) => {
    if (!conn) return;
    setDetalheOpen(true);
    setDetalheLoading(true);
    setDetalhe(null);
    try {
      const j = await apiGet(conn, `/api/contas-pagar/${codigo}`);
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
      const j = await apiSend(conn, "/api/contas-pagar/alterar-numero", "POST", {
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

  const abrirVincularNf = useCallback(async () => {
    if (!conn || !detalhe) return;
    setNotasVincularOpen(true);
    setNotasCarregando(true);
    try {
      const j = await apiGet(conn, `/api/contas-pagar/${detalhe.header.codigo}/notas-disponiveis`);
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
      const j = await apiSend(conn, "/api/contas-pagar/vincular-nf", "POST", {
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
          const j = await apiSend(conn, "/api/contas-pagar/desvincular-nf", "POST", {
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

  const excluirDuplicata = useCallback(async () => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Excluir a duplicata #${detalhe.header.duplicata}? Esta ação não pode ser desfeita.`,
      async () => {
        setExcluindo(true);
        try {
          const j = await apiSend(conn, "/api/contas-pagar/excluir", "POST", {
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

  const abrirBaixa = (p: Parcela) => {
    setBaixaVenc(p);
    setBaixaData(todayISO());
    setBaixaValor(String(p.valor).replace(".", ","));
    setBaixaDesconto(""); setBaixaOutrosDesc(""); setBaixaJuros(""); setBaixaOutrosAcresc(""); setBaixaTarifa("");
    setBaixaBanco(""); setBaixaAgencia(""); setBaixaBoleto(""); setBaixaDocumento(""); setBaixaObs("");
    setBaixaConta(p.conta ?? null); setBaixaFormaPag(p.forma_pag ?? null);
  };

  const confirmarBaixa = useCallback(async () => {
    if (!conn || !baixaVenc || !detalhe) return;
    const valorNum = parseNum(baixaValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor pago."); return; }
    if (!baixaData) { feedback.showError("Informe a data do pagamento."); return; }
    setBaixando(true);
    try {
      const j = await apiSend(conn, "/api/contas-pagar/baixar", "POST", {
        codigo_venc: baixaVenc.codigo, data_pag: baixaData, valor_pag: valorNum,
        desconto_pag: parseNum(baixaDesconto || "0"), outros_desc_pag: parseNum(baixaOutrosDesc || "0"),
        juros_pag: parseNum(baixaJuros || "0"), outros_acres_pag: parseNum(baixaOutrosAcresc || "0"),
        tarifa_banco: baixaTarifa ? parseNum(baixaTarifa) : null,
        banco_cedente: baixaBanco ? parseInt(baixaBanco, 10) : null,
        agencia_cedente: baixaAgencia ? parseInt(baixaAgencia, 10) : null,
        numero_boleto: baixaBoleto ? parseNum(baixaBoleto) : null,
        num_doc_pag: baixaDocumento || null,
        conta: baixaConta, forma_pag: baixaFormaPag, observacao: baixaObs,
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
      baixaTarifa, baixaBanco, baixaAgencia, baixaBoleto, baixaDocumento, baixaConta, baixaFormaPag, baixaObs,
      detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const cancelarBaixa = useCallback((p: Parcela) => {
    if (!conn || !detalhe) return;
    feedback.showConfirm(
      `Cancelar a baixa da parcela ${p.desmembramento}? Ela volta pra Aberto.`,
      async () => {
        setCancelandoBaixa(p.codigo);
        try {
          const j = await apiSend(conn, "/api/contas-pagar/cancelar-baixa", "POST", {
            codigo_venc: p.codigo, usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
          });
          if (j?.success) {
            feedback.showSuccess("Baixa cancelada.");
            abrirDetalhe(detalhe.header.codigo);
            carregar();
          } else {
            feedback.showError(friendlyApiError(j, "Não foi possível cancelar a baixa."));
          }
        } catch (e) {
          feedback.showError(friendlyCatchError(e));
        } finally {
          setCancelandoBaixa(null);
        }
      },
    );
  }, [conn, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  const abrirEditar = (p: Parcela) => {
    setEditParcela(p);
    setEditDtVenc(p.dt_vencimento);
    setEditValor(String(p.valor).replace(".", ","));
    setEditObs(p.observacao || "");
  };

  const confirmarEditar = useCallback(async () => {
    if (!conn || !editParcela || !detalhe) return;
    const valorNum = parseNum(editValor);
    if (!valorNum || valorNum <= 0) { feedback.showError("Informe o valor."); return; }
    if (!editDtVenc) { feedback.showError("Informe a data de vencimento."); return; }
    setEditando(true);
    try {
      const j = await apiSend(conn, "/api/contas-pagar/editar-parcela", "POST", {
        codigo_venc: editParcela.codigo, dt_vencimento: editDtVenc, valor: valorNum, observacao: editObs,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
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
  }, [conn, editParcela, editDtVenc, editValor, editObs, detalhe, usuarioCod, classePerm, feedback, abrirDetalhe, carregar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contas a Pagar está disponível apenas no web." testID="contas-pagar-web-only" />;
  }
  if (!loading && !can("CONTAS_PAGAR.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar Contas a Pagar." testID="contas-pagar-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="contas-pagar-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Contas a Pagar</Text>
        {can("CONTAS_PAGAR.GRAVAR") || masterPerm ? (
          <IconButtonWithTooltip icon="add-circle-outline" label="Lançamento avulso" color={colors.onBrandPrimary} onPress={abrirAvulso} testID="contas-pagar-avulso-btn" />
        ) : null}
        {can("CONTAS_PAGAR.BAIXAR") || masterPerm ? (
          <IconButtonWithTooltip icon="layers-outline" label="Pagamento/Cancelamento em Lote" color={colors.onBrandPrimary} onPress={() => setLoteOpen(true)} testID="contas-pagar-lote-btn" />
        ) : null}
        <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary} onPress={() => setAjudaOpen(true)} testID="contas-pagar-ajuda-btn" />
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
                        testID={`contas-pagar-chip-${s.key || "todas"}`}
                      >
                        <Text style={[chipTextStyle(), situacao === s.key && chipTextSelStyle()]}>{s.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" }}>
                    <View style={{ flex: 1, minWidth: 220 }}>
                      <Text style={fieldLabel()}>Buscar por fornecedor ou nº da duplicata</Text>
                      <TextInput value={busca} onChangeText={setBusca} style={inputStyle()} testID="contas-pagar-busca" onSubmitEditing={carregar} />
                    </View>
                    <Pressable onPress={() => setUsarPeriodo((v) => !v)} style={[chipStyle(), usarPeriodo && chipSelStyle(), { marginBottom: 2 }]}>
                      <Text style={[chipTextStyle(), usarPeriodo && chipTextSelStyle()]}>Filtrar por vencimento</Text>
                    </Pressable>
                    {usarPeriodo ? (
                      <>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>De</Text>
                          <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="contas-pagar-data-ini" />
                        </View>
                        <View style={{ width: 150 }}>
                          <Text style={fieldLabel()}>Até</Text>
                          <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="contas-pagar-data-fim" />
                        </View>
                      </>
                    ) : null}
                    <Pressable onPress={carregar} disabled={buscando} style={[secondaryBtnStyle(), { alignSelf: "flex-end" }]} testID="contas-pagar-buscar-btn">
                      {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                        <><Ionicons name="search" size={16} color={colors.brandPrimary} /><Text style={secondaryBtnLabelStyle()}>Buscar</Text></>
                      )}
                    </Pressable>
                  </View>
                  {/* Filtros avançados (`frmcondup.frm`, "Consulta de
                      Duplicatas a Pagar...") — mirror dos já existentes em
                      Contas a Receber. Achado do usuário 2026-08-31 — ver
                      AJUSTES.md #039. */}
                  <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap", marginTop: spacing.xs, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border }}>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Duplicata</Text>
                      <TextInput value={duplicataNum} onChangeText={setDuplicataNum} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-filtro-duplicata" />
                    </View>
                    <View style={{ width: 110 }}>
                      <Text style={fieldLabel()}>Valor</Text>
                      <TextInput value={valorFiltro} onChangeText={setValorFiltro} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-filtro-valor" />
                    </View>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>Nº do Boleto</Text>
                      <TextInput value={numeroBoleto} onChangeText={setNumeroBoleto} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-filtro-boleto" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>Nº Doc. Pagamento</Text>
                      <TextInput value={numDocPag} onChangeText={setNumDocPag} style={inputStyle()} testID="contas-pagar-filtro-numdocpag" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>Emissão de</Text>
                      <WebDateField value={emissaoIni} onChange={(v) => { setEmissaoIni(v || null); if (v) setEmissaoFim(v); }} testID="contas-pagar-emissao-ini" />
                    </View>
                    <View style={{ width: 150 }}>
                      <Text style={fieldLabel()}>até</Text>
                      <WebDateField value={emissaoFim} onChange={(v) => setEmissaoFim(v || null)} testID="contas-pagar-emissao-fim" />
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
                    <Pressable key={it.codigo} onPress={() => abrirDetalhe(it.codigo)} style={itemRowStyle()} testID={`contas-pagar-item-${it.codigo}`}>
                      <View style={[situacaoDotStyle(), { backgroundColor: it.vencido ? colors.error : it.situacao === "PG" ? colors.success : colors.brandPrimary }]} />
                      <View style={{ flex: 1, marginLeft: spacing.sm }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: it.vencido ? colors.error : colors.onSurface }}>
                          Duplicata #{it.duplicata}{it.desmembramento ? `/${it.desmembramento}` : ""}{"  ·  "}{it.fornecedor_nome}
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
                  <Text style={fieldLabel()}>Fornecedor *</Text>
                  <Pressable onPress={() => setAvFornSearchOpen(true)} style={[inputStyle(), { justifyContent: "center" }]} testID="contas-pagar-avulso-fornecedor-btn">
                    <Text style={{ color: avFornNome ? colors.onSurface : colors.muted }}>{avFornNome || "Buscar fornecedor…"}</Text>
                  </Pressable>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 120 }}>
                    <Text style={fieldLabel()}>Número *</Text>
                    <TextInput value={avNumero} onChangeText={setAvNumero} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-avulso-numero" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Série</Text>
                    <TextInput value={avSerie} onChangeText={setAvSerie} style={inputStyle()} testID="contas-pagar-avulso-serie" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Tipo de Movimentação *</Text>
                    <SelectField value={avTipoMov} onChange={(v) => setAvTipoMov(v as string)} options={tiposMov} compactWeb testID="contas-pagar-avulso-tipomov" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Data de Emissão</Text>
                    <WebDateField value={avDtEmissao} onChange={(v) => setAvDtEmissao(v || null)} testID="contas-pagar-avulso-dtemissao" />
                  </View>
                  <View style={{ width: 130 }}>
                    <Text style={fieldLabel()}>Valor *</Text>
                    <TextInput value={avValor} onChangeText={setAvValor} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-avulso-valor" />
                  </View>
                  <View style={{ width: 90 }}>
                    <Text style={fieldLabel()}>Parcelas</Text>
                    <TextInput value={avParcelas} onChangeText={setAvParcelas} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-avulso-parcelas" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>1º Vencimento *</Text>
                    <WebDateField value={avDtVenc} onChange={(v) => setAvDtVenc(v || null)} testID="contas-pagar-avulso-dtvenc" />
                  </View>
                </View>
                <Text style={[fieldLabel(), { fontStyle: "italic" }]}>
                  Com mais de 1 parcela, o valor é dividido igualmente (a última absorve o arredondamento) e o vencimento avança 1 mês por parcela.
                </Text>
                <View>
                  <Text style={fieldLabel()}>Observação</Text>
                  <TextInput value={avObs} onChangeText={setAvObs} style={[inputStyle(), { minHeight: 60 }]} multiline testID="contas-pagar-avulso-obs" />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setAvulsoOpen(false)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={salvarAvulso} disabled={salvandoAvulso} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-pagar-avulso-salvar">
                    {salvandoAvulso ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar</Text>}
                  </Pressable>
                </View>
              </View>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <FornecedorSearchModal
        visible={avFornSearchOpen} onClose={() => setAvFornSearchOpen(false)}
        term={avFornTerm} setTerm={setAvFornTerm} loading={avFornLoading} results={avFornResults}
        onPick={(f) => { setAvFornCod(Number(f.codigo_int)); setAvFornNome(f.nome); setAvFornSearchOpen(false); }}
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
                <Text style={{ fontSize: 14, color: colors.onSurface, marginBottom: 4 }}>{detalhe.header.fornecedor_nome}</Text>
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
                        {can("CONTAS_PAGAR.GRAVAR") || masterPerm ? (
                          <Pressable onPress={() => abrirEditar(p)} style={smallBtnStyle()} testID={`contas-pagar-editar-${p.codigo}`}>
                            <Ionicons name="create-outline" size={14} color={colors.brandPrimary} />
                            <Text style={smallBtnLabelStyle()}>Editar</Text>
                          </Pressable>
                        ) : null}
                        {can("CONTAS_PAGAR.BAIXAR") || masterPerm ? (
                          <Pressable onPress={() => abrirBaixa(p)} style={smallBtnStyle()} testID={`contas-pagar-baixar-${p.codigo}`}>
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
                        {(can("CONTAS_PAGAR.BAIXAR") || masterPerm) ? (
                          <Pressable onPress={() => cancelarBaixa(p)} disabled={cancelandoBaixa === p.codigo} style={smallBtnStyle()} testID={`contas-pagar-cancelar-baixa-${p.codigo}`}>
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
                  {(can("CONTAS_PAGAR.GRAVAR") || masterPerm) ? (
                    <Pressable onPress={abrirVincularNf} style={smallBtnStyle()} testID="contas-pagar-vincular-nf-btn">
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
                    {(can("CONTAS_PAGAR.GRAVAR") || masterPerm) ? (
                      <Pressable onPress={() => desvincularNf(n.codigo, n.nota_fiscal)} disabled={desvinculandoNf === n.codigo} style={smallBtnStyle()} testID={`contas-pagar-desvincular-nf-${n.codigo}`}>
                        {desvinculandoNf === n.codigo ? <ActivityIndicator color={colors.error} size="small" /> : (
                          <><Ionicons name="close-circle-outline" size={14} color={colors.error} /><Text style={[smallBtnLabelStyle(), { color: colors.error }]}>Desvincular</Text></>
                        )}
                      </Pressable>
                    ) : null}
                  </View>
                ))}

                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg }}>
                  {(can("CONTAS_PAGAR.GRAVAR") || masterPerm) ? (
                    <Pressable onPress={abrirAlterarNumero} style={ps.secondaryBtn} testID="contas-pagar-alterar-numero-btn">
                      <Ionicons name="create-outline" size={16} color={colors.brandPrimary} /><Text style={{ color: colors.brandPrimary, fontWeight: "600" }}>Alterar Número</Text>
                    </Pressable>
                  ) : null}
                  {(can("CONTAS_PAGAR.EXCLUIR") || masterPerm) ? (
                    <Pressable onPress={excluirDuplicata} disabled={excluindo} style={[ps.secondaryBtn, { borderColor: colors.error }]} testID="contas-pagar-excluir-btn">
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

      {/* "Vincular Nota Fiscal" — lista NFs em aberto do mesmo grupo de
          documento (matriz/filiais), toque vincula direto (mesmo padrão
          de "duplo-clique inclui" do legado, `NF2_DblClick`). */}
      <Modal visible={notasVincularOpen} transparent animationType="slide" onRequestClose={() => setNotasVincularOpen(false)}>
        <Pressable style={[ps.modalBg, isWeb && ps.modalBgWebCompact]} onPress={() => setNotasVincularOpen(false)}>
          <Pressable style={[ps.modalCard, isWeb && ps.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={ps.modalHeader}>
              <Text style={ps.modalTitle}>Vincular Nota Fiscal</Text>
              <Pressable onPress={() => setNotasVincularOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.sm }}>
              Notas fiscais em aberto do mesmo fornecedor (matriz e filiais). Toque pra vincular a esta duplicata.
            </Text>
            {notasCarregando ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : notasDisponiveis.length === 0 ? (
              <Text style={{ fontSize: 13, color: colors.muted, textAlign: "center", marginVertical: 24 }}>Nenhuma nota fiscal disponível.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 360 }}>
                {notasDisponiveis.map((n) => (
                  <Pressable key={n.codigo} onPress={() => vincularNf(n.codigo)} disabled={vinculandoNf === n.codigo} style={parcelaRowStyle()} testID={`contas-pagar-nf-disponivel-${n.codigo}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>NF {n.nota_fiscal}{n.serie ? `/${n.serie}` : ""} · {formatBRL(n.valor)}</Text>
                      <Text style={{ fontSize: 12, color: colors.muted }}>{n.fornecedor_nome}</Text>
                    </View>
                    {vinculandoNf === n.codigo ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Ionicons name="add-circle-outline" size={20} color={colors.brandPrimary} />}
                  </Pressable>
                ))}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* "Alterar Nº Duplicata" — modal próprio (o legado usa um InputBox
          nativo, nunca replicado neste projeto). */}
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
                <TextInput value={novoNumero} onChangeText={setNovoNumero} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-novo-numero" />
              </View>
              <View style={ps.modalBtns}>
                <Pressable onPress={() => setAlterarNumeroOpen(false)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                <Pressable onPress={confirmarAlterarNumero} disabled={alterandoNumero} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-pagar-alterar-numero-confirmar">
                  {alterandoNumero ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Confirmar</Text>}
                </Pressable>
              </View>
            </View>
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
                    <WebDateField value={baixaData} onChange={(v) => setBaixaData(v || null)} testID="contas-pagar-baixa-data" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Forma de Pagamento *</Text>
                    <SelectField value={baixaFormaPag} onChange={(v) => setBaixaFormaPag(v as string)} options={formaPagOpts} compactWeb allowClear testID="contas-pagar-baixa-formapag" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Conta *</Text>
                    <SelectField value={baixaConta} onChange={(v) => setBaixaConta(v == null ? null : Number(v))} options={contasOpts} compactWeb allowClear testID="contas-pagar-baixa-conta" />
                  </View>
                  <View style={{ width: 150 }}>
                    <Text style={fieldLabel()}>Valor Pago *</Text>
                    <TextInput value={baixaValor} onChangeText={setBaixaValor} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-baixa-valor" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Desconto</Text>
                    <TextInput value={baixaDesconto} onChangeText={setBaixaDesconto} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-baixa-desconto" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Outros Desconto</Text>
                    <TextInput value={baixaOutrosDesc} onChangeText={setBaixaOutrosDesc} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-baixa-outrosdesc" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Juros/Multa</Text>
                    <TextInput value={baixaJuros} onChangeText={setBaixaJuros} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-baixa-juros" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Outros Acréscimo</Text>
                    <TextInput value={baixaOutrosAcresc} onChangeText={setBaixaOutrosAcresc} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-baixa-outrosacresc" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Tarifa Banco</Text>
                    <TextInput value={baixaTarifa} onChangeText={setBaixaTarifa} keyboardType="numeric" style={inputStyle()} placeholder="0,00" testID="contas-pagar-baixa-tarifa" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Nº Boleto</Text>
                    <TextInput value={baixaBoleto} onChangeText={setBaixaBoleto} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-baixa-boleto" />
                  </View>
                </View>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Banco</Text>
                    <TextInput value={baixaBanco} onChangeText={setBaixaBanco} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-baixa-banco" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Agência</Text>
                    <TextInput value={baixaAgencia} onChangeText={setBaixaAgencia} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-baixa-agencia" />
                  </View>
                </View>
                <View>
                  <Text style={fieldLabel()}>Documento</Text>
                  <TextInput value={baixaDocumento} onChangeText={setBaixaDocumento} style={inputStyle()} testID="contas-pagar-baixa-documento" />
                </View>
                <View>
                  <Text style={fieldLabel()}>Observação</Text>
                  <TextInput value={baixaObs} onChangeText={setBaixaObs} style={[inputStyle(), { minHeight: 50 }]} multiline testID="contas-pagar-baixa-obs" />
                </View>
                <View style={ps.modalBtns}>
                  <Pressable onPress={() => setBaixaVenc(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                  <Pressable onPress={confirmarBaixa} disabled={baixando} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-pagar-baixa-confirmar">
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
                  <WebDateField value={editDtVenc} onChange={(v) => setEditDtVenc(v || null)} testID="contas-pagar-editar-data" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Valor *</Text>
                  <TextInput value={editValor} onChangeText={setEditValor} keyboardType="numeric" style={inputStyle()} testID="contas-pagar-editar-valor" />
                </View>
              </View>
              <View>
                <Text style={fieldLabel()}>Observação</Text>
                <TextInput value={editObs} onChangeText={setEditObs} style={[inputStyle(), { minHeight: 60 }]} multiline testID="contas-pagar-editar-obs" />
              </View>
              <View style={ps.modalBtns}>
                <Pressable onPress={() => setEditParcela(null)} style={ps.secondaryBtn}><Text>Cancelar</Text></Pressable>
                <Pressable onPress={confirmarEditar} disabled={editando} style={[ps.primaryBtn, { flex: 1 }]} testID="contas-pagar-editar-confirmar">
                  {editando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={{ color: colors.onBrandPrimary, fontWeight: "600" }}>Gravar</Text>}
                </Pressable>
              </View>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      <LoteBaixaModal
        visible={loteOpen} onClose={() => setLoteOpen(false)} conn={conn} apiBase="contas-pagar"
        entidadeLabel="Fornecedor" contasOpts={contasOpts} formaPagOpts={formaPagOpts}
        usuarioCod={usuarioCod} classe={classePerm} onDone={carregar}
      />

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Contas a Pagar" itens={AJUDA_ITENS} />
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
