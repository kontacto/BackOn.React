// Painel Financeiro (Financeiro > Fluxo de Caixa) — tela única com 2
// abas, pedido explícito do usuário 2026-08-31 ("quero as duas telas
// juntas... não preciso acessar outra tela"): Painel de Movimentações
// (migração de `Kontacto\FrmPnlCon.frm`) e Previsões (migração de
// `Tesouraria\FrmManPrev.frm`) — antes eram 2 rotas separadas
// (`/painel-financeiro` e `/previsoes`), agora vivem juntas aqui.
//
// Painel de Movimentações: dashboard do Fluxo de Caixa (saldo/totais do
// período, 4 blocos de alerta, grade de movimentações) + lançamento
// direto rápido (Pagar/Cheque, Receber/Depósito, Transferência, Saque) —
// grava direto em `movimentacoes`, sem passar por Previsões.
//
// Previsões: CRUD de lançamentos futuros/recorrentes MANUAIS (aluguel
// mensal, assinatura recorrente, etc. — sem vínculo com duplicata) +
// motor de Efetivação (previsão → movimentação real, saldo da conta
// mudando de verdade). Achado importante (ver PENDENCIAS.md > "Painel
// Financeiro"): nunca toca previsões com `cod_transf_caixa>0` (essas são
// exclusivas da Transferência p/Fluxo de Caixa) — só previsões criadas
// aqui mesmo.
//
// Ver services/painel_financeiro_service.py + services/previsoes_service.py
// e PENDENCIAS.md > "Painel Financeiro (Fluxo de Caixa)" pro rastreio
// completo (inclusive achados de paridade com o legado ainda em aberto —
// "Saldo Previsto" do Painel não replica hoje a expansão virtual de
// recorrências futuras que o VB6 faz).
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { AppModal } from "@/src/components/AppModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import WebDateField from "@/src/components/WebDateField";
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import FornecedorSearchModal, { FornecedorRow } from "@/src/components/FornecedorSearchModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { loadPainelFinanceiroFiltros, painelFinanceiroFiltrosKey, savePainelFinanceiroFiltros } from "@/src/utils/storage/painelFinanceiroFilters";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

const isWeb = Platform.OS === "web";
type Aba = "painel" | "previsoes" | "relatorios";

// ===== Painel de Movimentações =====
type Periodo = "hoje" | "ontem" | "semana" | "mes" | "30dias" | "tudo";
const PERIODOS: { value: Periodo; label: string }[] = [
  { value: "hoje", label: "Hoje" }, { value: "ontem", label: "Ontem" },
  { value: "semana", label: "Semana" }, { value: "mes", label: "Mês" },
  { value: "30dias", label: "30 dias" }, { value: "tudo", label: "Tudo" },
];
const TIPO_LABEL: Record<number, string> = { 0: "Pagar", 1: "Receber", 2: "Transferência", 3: "Saque" };
const TIPO_LABEL_LONGO: Record<number, string> = { 0: "Pagar / Cheque", 1: "Receber / Depósito", 2: "Transferência", 3: "Saque" };
function tipoColor(tipo: number) { return tipo === 1 ? colors.success : tipo === 3 ? colors.warning : tipo === 0 ? colors.error : colors.brandPrimary; }

type Alerta = { total: number; qtd: number };
type Resumo = {
  saldo_atual: number; saldo_previsto: number; saldo_anterior_periodo: number;
  total_receitas_periodo: number; total_despesas_periodo: number; saldo_fim_periodo: number;
  alertas: { contas_a_receber_atraso: Alerta; contas_a_receber_hoje: Alerta; pagamentos_atraso: Alerta; a_pagar_hoje: Alerta };
};
type Movimentacao = {
  codigo: number; conta: number; classe: number | null; data_liquidacao: string | null;
  documento: string | null; favorecido_nome: string; valor: number; tipo: number;
  memorando: string; credito: boolean; editavel: boolean;
};
type PontoSaldo = { data: string; saldo: number };
type RateioLinhaPainel = { centro_custo: number | null; classe: number | null; sub_classe: number | null; valor: number; memorando: string; credito_debito: string };

const AJUDA_ITENS_PAINEL: HelpItem[] = [
  { titulo: "Saldo Atual x Saldo Previsto", texto: "Saldo Atual é o saldo real das contas agora. Saldo Previsto projeta as Previsões (pendentes e dentro do período) somadas/descontadas do Saldo Atual — uma projeção, não o saldo de verdade ainda. Só existe com um período definido (não em \"Tudo\").", icon: { lib: "ion", name: "trending-up-outline" } },
  { titulo: "Previsões a partir de hoje / Desconsiderar Pendências", texto: "2 opções que ajustam o Saldo Previsto (mutuamente exclusivas): a 1ª ignora previsões já vencidas antes de hoje na projeção; a 2ª tira as Pendências (previsões vencidas antes do período) do cálculo por completo.", icon: { lib: "ion", name: "options-outline" } },
  { titulo: "Saldo Anterior ao Período", texto: "É o saldo que a conta já tinha ANTES do período selecionado começar — junto com as Entradas e Saídas do período, forma o Saldo ao Fim do Período.", icon: { lib: "ion", name: "time-outline" } },
  { titulo: "Os 4 alertas", texto: "Contas a Receber em Atraso/Hoje e Pagamentos em Atraso/Hoje somam valores vencidos ou vencendo hoje — vindos de Previsões e de duplicatas do comercial ainda em aberto. Servem de aviso, não bloqueiam nada.", icon: { lib: "ion", name: "alert-circle-outline" } },
  { titulo: "Pagar/Receber/Transferência/Saque", texto: "Lançamento direto: grava na hora em Fluxo de Caixa, sem passar por Previsões. Use pra algo que já aconteceu agora (ex.: sacou dinheiro, recebeu um depósito).", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Lançamentos de outra tela", texto: "Um lançamento marcado com um cadeado veio de outra tela (Transferência p/Fluxo de Caixa, Previsões ou Agrupamento de Comandas) — só pode ser alterado/excluído na tela de origem.", icon: { lib: "ion", name: "lock-closed-outline" } },
  { titulo: "Gráfico de saldo", texto: "Mostra a evolução do saldo REALIZADO ao longo do período — nunca uma projeção. É só uma forma visual de enxergar a mesma informação que já aparece em números logo acima.", icon: { lib: "ion", name: "analytics-outline" } },
];

function monthLabel(ref: string): string {
  const [ano, mes] = ref.split("-").map((x) => parseInt(x, 10));
  const nomes = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  return `${nomes[mes - 1]}/${ano}`;
}
function shiftMonth(ref: string, delta: number): string {
  const [ano, mes] = ref.split("-").map((x) => parseInt(x, 10));
  const d = new Date(ano, mes - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// ===== Previsões =====
const FREQUENCIAS: SelectOption[] = [
  { value: 0, label: "Diário" }, { value: 1, label: "Semanal" }, { value: 2, label: "Decendial" },
  { value: 3, label: "Quinzenal" }, { value: 4, label: "Mensal" }, { value: 5, label: "Bimestral" },
  { value: 6, label: "Trimestral" }, { value: 7, label: "Quadrimestral" }, { value: 8, label: "Semestral" },
  { value: 9, label: "Anual" }, { value: 10, label: "Única Vez" },
];
const TIPO_LABEL_PREV: Record<number, string> = { 0: "Pagar", 1: "Receber", 2: "Transferência" };
function todayIso(): string { return new Date().toISOString().slice(0, 10); }

type Previsao = {
  codigo: number; conta: number; conta_descricao: string; classe: number | null; classe_descricao: string | null;
  conta_destino_descricao: string | null; sub_classe: number | null; documento: string | null;
  data_documento: string | null; data_vencimento: string | null; favorecido: number | null;
  favorecido_nome: string; valor: number; tipo: number; memorando: string; frequencia: number;
  // "Transferência Para Movimentação" (achado do usuário 2026-08-31) —
  // previsão que pertence a outra tela (Contas a Pagar/Receber) não pode
  // ser selecionada aqui; `bloqueio_motivo` é a mensagem específica
  // (`_bloqueio_transf_caixa`, backend).
  bloqueada: boolean; bloqueio_motivo: string | null;
  cod_transf_caixa: number | null; flag_transf_caixa: string | null;
  // Valor atual de `duplicata_rec_venc.situacao_duplicata` (só preenchido
  // quando flag_transf_caixa="R") — mostrado na lista e usado pra
  // pré-carregar o modal de Alterar Situação com o valor real, não sempre
  // "Normal" (achado do usuário 2026-08-31, "continua não alterando").
  situacao_duplicata_atual: number | null;
};

const SITUACAO_VENCIMENTO_OPTIONS = [
  { value: 0, label: "Normal" },
  { value: 1, label: "Jurídico" },
  { value: 2, label: "Protestado" },
];
type RateioLinhaPrev = { centro_custo: number | null; classe: number | null; sub_classe: number | null; valor: number; memorando: string; credito_debito: string; repete_lancamento: boolean };
// Plano de Contas (`GET /api/financeiro/plano-contas`) — tipo "D"=Despesa/
// "R"=Receita, alimenta as comboboxes de Classe/Sub-Classe da Previsão.
type PlanoContasClasse = { codigo: number; descricao: string; tipo: string; sub_classes: { codigo: number; classe: number; descricao: string; tipo: string; ativa: boolean }[] };

const AJUDA_ITENS_PREV: HelpItem[] = [
  { titulo: "O que esta aba faz", texto: "Cadastra lançamentos futuros/recorrentes que você digita manualmente (aluguel, assinatura, etc.) — sem vínculo com nenhuma duplicata. Quando chega a hora, você Efetiva: a previsão vira um lançamento real no Fluxo de Caixa e o saldo da conta muda de verdade.", icon: { lib: "ion", name: "calendar-outline" } },
  { titulo: "Pagar / Receber / Transferência", texto: "Pagar e Receber lançam contra 1 conta (com Classe/Sub-Classe contábil). Transferência move de uma conta pra outra — escolha a conta de destino em vez de Classe.", icon: { lib: "ion", name: "swap-horizontal-outline" } },
  { titulo: "Frequência", texto: "Define de quanto em quanto tempo essa previsão se repete. Ao efetivar, a MESMA previsão avança pra próxima data — não cria uma nova. \"Única Vez\" some da lista depois de efetivada.", icon: { lib: "ion", name: "repeat-outline" } },
  { titulo: "Parcelas", texto: "Só ao criar: gera várias previsões mensais de uma vez (ex.: 12 parcelas de um contrato).", icon: { lib: "ion", name: "layers-outline" } },
  { titulo: "Centro de Custo (rateio)", texto: "Opcional — divide o valor entre um ou mais centros de custo. A soma do rateio precisa bater exatamente com o Valor da previsão.", icon: { lib: "ion", name: "pie-chart-outline" } },
  { titulo: "Efetivar", texto: "Marque uma ou mais previsões já vencidas/a vencer e clique Efetivar Selecionadas — abre a Transferência Para Movimentação, onde você confirma a Data de Liquidação e, se quiser, redireciona pra outra Conta. Só então lança de verdade no Fluxo de Caixa e muda o saldo.", icon: { lib: "ion", name: "checkmark-done-outline" } },
  { titulo: "Cadeado (previsão bloqueada)", texto: "Essa previsão nasceu de outra tela (Contas a Pagar, Contas a Receber, etc.) — a baixa dela precisa ser feita por lá, não aqui. Se for do Contas a Receber, tocar marca o item (cadeado abre) — marque quantos quiser e clique \"Alterar Situação\" pra corrigir Normal/Jurídico/Protestado de vários de uma vez.", icon: { lib: "ion", name: "lock-closed-outline" } },
  { titulo: "Receita x Despesa", texto: "Soma quanto você já tem de Receber x quanto já tem de Pagar entre TODAS as previsões do período/conta selecionados — independente do filtro de Tipo da lista (Transferência não entra, não é receita nem despesa).", icon: { lib: "ion", name: "bar-chart-outline" } },
];

// Receita x Despesa — "recurso extra" do Carlos, sugestão do usuário
// 2026-08-29: soma Receber (tipo=1) x Pagar (tipo=0), sempre a partir de
// `totaisGrafico` (busca própria que ignora o filtro de Tipo da lista —
// ver `buscarTotaisGrafico` abaixo). Cada valor aqui é um compromisso
// futuro já declarado pelo próprio usuário (data_vencimento real) —
// diferente do gráfico de saldo do Painel, isso não é projeção nenhuma.
function ReceitaDespesaBars({ receber, pagar }: { receber: number; pagar: number }) {
  const max = Math.max(receber, pagar, 1);
  return (
    <View style={{ gap: 6 }}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Text style={{ width: 70, fontSize: 12, color: colors.muted }}>Receber</Text>
        <View style={{ flex: 1, height: 16, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, overflow: "hidden" }}>
          <View style={{ width: `${(receber / max) * 100}%`, height: "100%", backgroundColor: colors.success }} />
        </View>
        <Text style={{ width: 100, fontSize: 12, fontWeight: "700", color: colors.success, textAlign: "right" }}>{formatBRL(receber)}</Text>
      </View>
      <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm }}>
        <Text style={{ width: 70, fontSize: 12, color: colors.muted }}>Pagar</Text>
        <View style={{ flex: 1, height: 16, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, overflow: "hidden" }}>
          <View style={{ width: `${(pagar / max) * 100}%`, height: "100%", backgroundColor: colors.error }} />
        </View>
        <Text style={{ width: 100, fontSize: 12, fontWeight: "700", color: colors.error, textAlign: "right" }}>{formatBRL(pagar)}</Text>
      </View>
    </View>
  );
}

function resumirFalhas(falhas: { codigo: number; message: string }[]): string {
  const grupos = new Map<string, number[]>();
  for (const f of falhas) {
    const lista = grupos.get(f.message) || [];
    lista.push(f.codigo);
    grupos.set(f.message, lista);
  }
  return Array.from(grupos.entries()).map(([m, c]) => `${c.length}x (${c.join(", ")}): ${m}`).join("\n\n");
}

export default function PainelFinanceiroScreen() {
  const router = useRouter();
  const { can, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const podeAbrirPainel = can("PAINEL_MOV.ABRIR");
  const podeAbrirPrevisoes = can("PREVISOES.ABRIR");
  const [aba, setAba] = useState<Aba>(podeAbrirPainel ? "painel" : "previsoes");
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [contas, setContas] = useState<SelectOption[]>([]);
  const [contasSaldo, setContasSaldo] = useState<{ codigo: number; descricao: string; saldo_atual: number }[]>([]);
  const [planoContas, setPlanoContas] = useState<PlanoContasClasse[]>([]);

  // Filtros persistidos por empresa+banco (achado do usuário 2026-08-31,
  // "gravar filtro para próximo acesso") — mesmo padrão de
  // src/utils/storage/pedidosFilters.ts: restaura na 1ª carga, salva a
  // cada mudança depois disso. `filtrosRestauradosRef` guarda contra o
  // efeito de save disparar ANTES da restauração terminar (sobrescreveria
  // o storage com os defaults iniciais).
  const filtrosRestauradosRef = useRef(false);
  const storageKeyRef = useRef<string | null>(null);

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
      if (c) {
        const key = painelFinanceiroFiltrosKey(c.empresa, c.banco);
        storageKeyRef.current = key;
        const saved = await loadPainelFinanceiroFiltros(key);
        if (saved) {
          setContaFiltro(saved.contaFiltro);
          setPeriodo(saved.periodo as Periodo);
          setMesRef(saved.mesRef);
          setPartirDeHoje(saved.partirDeHoje);
          setDesconsiderarPendencias(saved.desconsiderarPendencias);
          setPrevContaFiltro(saved.prevContaFiltro);
          setTipoFiltro(saved.tipoFiltro);
          setFiltroData(saved.filtroData as "todas" | "atraso" | "hoje" | "mes");
          setPrevMesRef(saved.prevMesRef);
          setRelContaFiltro(saved.relContaFiltro);
        }
        const j = await apiGet(c, "/api/contas-caixa");
        if (j?.success) {
          const items: { codigo: number; descricao: string; saldo_atual: number; conta_principal_painel?: boolean }[] = j.items || [];
          setContas(items.map((x) => ({ value: x.codigo, label: x.descricao })));
          setContasSaldo(items);
          // Conta Principal do Painel (`Contas.ContaPrincipalPainel`,
          // marcada com ★ no Cadastro de Contas) — regra geral, achado
          // do usuário 2026-08-31: "todas as telas e relatórios que
          // possuem contas, selecionar a conta padrão no carregamento
          // da página" (em vez de nascer em "Todas as contas"). Só se
          // aplica na 1ª visita — se já existe filtro salvo, a escolha
          // salva prevalece (mesmo critério de pedidos.tsx).
          if (!saved) {
            const padrao = items.find((x) => x.conta_principal_painel);
            if (padrao) {
              setContaFiltro(padrao.codigo);
              setPrevContaFiltro(padrao.codigo);
              setRelContaFiltro(padrao.codigo);
            }
          }
        }
        // Plano de Contas (classes/sub_classes) — cadastro real, usado
        // pra alimentar as comboboxes de Classe/Sub-Classe da Previsão
        // (achado do usuário 2026-08-31: "é um cadastro, as opções tem
        // que vir do banco e não digitação livre").
        const jp = await apiGet(c, "/api/financeiro/plano-contas");
        if (jp?.success) setPlanoContas(jp.items || []);
        filtrosRestauradosRef.current = true;
      }
      setLoading(false);
    })();
  }, []);

  // ===== Painel de Movimentações — estado e ações =====
  const [buscando, setBuscando] = useState(false);
  const [contaFiltro, setContaFiltro] = useState<number | null>(null);
  const [periodo, setPeriodo] = useState<Periodo>("mes");
  const [mesRef, setMesRef] = useState(() => {
    const hoje = new Date();
    return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
  });
  const [resumo, setResumo] = useState<Resumo | null>(null);
  const [itens, setItens] = useState<Movimentacao[]>([]);
  const [serie, setSerie] = useState<{ saldo_inicial: number; pontos: PontoSaldo[] } | null>(null);
  // 2 checkboxes do cabeçalho do Painel legado (`FrmPnlCon.frm`,
  // `pCheck5`/`pCheck6`) — mutuamente exclusivos na tela original
  // (marcar um desmarca o outro), afetam só o cálculo de Saldo Previsto.
  const [partirDeHoje, setPartirDeHoje] = useState(false);
  const [desconsiderarPendencias, setDesconsiderarPendencias] = useState(false);

  const [lancarOpen, setLancarOpen] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [excluindoCodigo, setExcluindoCodigo] = useState<number | null>(null);
  const [fTipo, setFTipo] = useState(0);
  const [fConta, setFConta] = useState<number | null>(null);
  const [fContaDestino, setFContaDestino] = useState<number | null>(null);
  const [fFavorecido, setFFavorecido] = useState("");
  const [fClasse, setFClasse] = useState<number | null>(null);
  const [fSubClasse, setFSubClasse] = useState<number | null>(null);
  const [fDocumento, setFDocumento] = useState("");
  const [fDataLiquidacao, setFDataLiquidacao] = useState<string | null>(null);
  const [fValor, setFValor] = useState("");
  const [fMemorando, setFMemorando] = useState("");
  const [fRateio, setFRateio] = useState<RateioLinhaPainel[]>([]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    try {
      const qs = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, periodo });
      if (contaFiltro) qs.set("conta", String(contaFiltro));
      if (periodo === "mes") qs.set("mes_ref", mesRef);
      const qsResumo = new URLSearchParams(qs);
      if (partirDeHoje) qsResumo.set("partir_de_hoje", "true");
      if (desconsiderarPendencias) qsResumo.set("desconsiderar_pendencias", "true");
      const [rResumo, rMov, rSerie] = await Promise.all([
        fetch(`${conn.api}/api/painel-financeiro/resumo?${qsResumo.toString()}`).then((r) => r.json()),
        fetch(`${conn.api}/api/painel-financeiro/movimentacoes?${qs.toString()}`).then((r) => r.json()),
        fetch(`${conn.api}/api/painel-financeiro/serie-saldo?${qs.toString()}`).then((r) => r.json()),
      ]);
      if (rResumo?.success) setResumo(rResumo); else { setResumo(null); feedback.showError(friendlyApiError(rResumo, "Não foi possível buscar o resumo.")); }
      if (rMov?.success) setItens(rMov.items || []); else setItens([]);
      if (rSerie?.success) setSerie({ saldo_inicial: rSerie.saldo_inicial, pontos: rSerie.pontos || [] }); else setSerie(null);
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, contaFiltro, periodo, mesRef, partirDeHoje, desconsiderarPendencias, feedback]);

  useEffect(() => { if (conn && podeAbrirPainel) buscar(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [conn, contaFiltro, periodo, mesRef, partirDeHoje, desconsiderarPendencias]);

  const abrirLancamento = (tipo: number) => {
    setFTipo(tipo); setFConta(contaFiltro); setFContaDestino(null);
    setFFavorecido(""); setFClasse(null); setFSubClasse(null); setFDocumento("");
    setFDataLiquidacao(new Date().toISOString().slice(0, 10));
    setFValor(""); setFMemorando(""); setFRateio([]);
    setLancarOpen(true);
  };

  const somaRateio = fRateio.reduce((s, r) => s + (Number(r.valor) || 0), 0);
  const valorNum = Number(fValor.replace(",", ".")) || 0;

  const salvarLancamento = async () => {
    if (!conn) return;
    setSalvando(true);
    try {
      const j = await apiSend(conn, "/api/painel-financeiro/lancamentos", "POST", {
        conta: fConta, conta_destino: fTipo === 2 ? fContaDestino : undefined, tipo: fTipo,
        documento: fDocumento, data_liquidacao: fDataLiquidacao,
        favorecido_nome: fFavorecido, classe_lancamento: fTipo !== 2 ? fClasse : null, sub_classe_lancamento: fTipo !== 2 ? fSubClasse : null,
        valor: valorNum, memorando: fMemorando,
        rateio: fRateio.map((r) => ({ centro_custo: r.centro_custo, classe: r.classe, sub_classe: r.sub_classe, valor: Number(r.valor) || 0, memorando: r.memorando, credito_debito: r.credito_debito })),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Lançamento gravado.");
        setLancarOpen(false);
        buscar();
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setSalvando(false);
    }
  };

  const excluirLancamento = (codigo: number) => {
    if (!conn) return;
    feedback.showConfirm("Excluir este lançamento? O saldo da conta será revertido.", async () => {
      setExcluindoCodigo(codigo);
      try {
        const resp = await fetch(`${conn.api}/api/painel-financeiro/lancamentos/${codigo}`, {
          method: "DELETE",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, codigo, usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web" }),
        });
        const j = await resp.json();
        if (j?.success) { feedback.showSuccess("Lançamento excluído."); buscar(); }
        else feedback.showError(friendlyApiError(j, "Falha ao excluir."));
      } catch (e) {
        feedback.showError(friendlyCatchError(e));
      } finally {
        setExcluindoCodigo(null);
      }
    });
  };

  const adicionarLinhaRateio = () => setFRateio((prev) => [...prev, { centro_custo: null, classe: null, sub_classe: null, valor: 0, memorando: "", credito_debito: "C" }]);
  const removerLinhaRateio = (idx: number) => setFRateio((prev) => prev.filter((_, i) => i !== idx));
  const atualizarLinhaRateio = (idx: number, patch: Partial<RateioLinhaPainel>) => setFRateio((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  // ===== Previsões — estado e ações =====
  const [prevBuscando, setPrevBuscando] = useState(false);
  const [prevAjudaOpen, setPrevAjudaOpen] = useState(false);
  const [prevContaFiltro, setPrevContaFiltro] = useState<number | null>(null);
  // Filtro de Conta da aba Relatórios — achado do usuário 2026-08-31
  // ("Previsões e Relatórios precisam ter filtro de contas"): só afeta o
  // sub-relatório "Receitas x Despesas por Mês" (`receitas-despesas-mes`,
  // já aceita `conta` no backend, só não era passado daqui); "Saldos
  // Atuais das Contas" mostra todas por natureza, e "Duplicatas à Pagar/
  // Receber em Aberto" não tem coluna `conta` (achado já documentado em
  // `_alertas_sync`), então não há o que filtrar ali.
  const [relContaFiltro, setRelContaFiltro] = useState<number | null>(null);
  const [tipoFiltro, setTipoFiltro] = useState<number | null>(null);
  const [filtroData, setFiltroData] = useState<"todas" | "atraso" | "hoje" | "mes">("todas");
  // Filtro de período mensal navegável (achado do usuário 2026-08-31,
  // "adicionar filtro de período mensal") — mesmo padrão de mês/setas já
  // usado na aba Painel de Movimentações (`mesRef`/`shiftMonth`), estado
  // próprio pra não interferir no filtro da outra aba.
  const [prevMesRef, setPrevMesRef] = useState(() => {
    const hoje = new Date();
    return `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, "0")}`;
  });
  const [busca, setBusca] = useState("");

  useEffect(() => {
    if (!filtrosRestauradosRef.current || !storageKeyRef.current) return;
    savePainelFinanceiroFiltros(storageKeyRef.current, {
      contaFiltro, periodo, mesRef, partirDeHoje, desconsiderarPendencias,
      prevContaFiltro, tipoFiltro, filtroData, prevMesRef, relContaFiltro,
    });
  }, [contaFiltro, periodo, mesRef, partirDeHoje, desconsiderarPendencias, prevContaFiltro, tipoFiltro, filtroData, prevMesRef, relContaFiltro]);

  const [prevItens, setPrevItens] = useState<Previsao[]>([]);
  const [selecionados, setSelecionados] = useState<Record<number, boolean>>({});
  const [efetivando, setEfetivando] = useState(false);
  // "Transferência Para Movimentação" (FrmManPrev.frm, Frame5/Command11-13)
  // — modal que pede Data de Liquidação + Conta antes de efetivar de
  // verdade, achado do usuário 2026-08-31 ("a tela de transferência que
  // nos permite informar a data de liquidação e conta que está baixando
  // esse registro"). Escopo desta rodada: só o modo "Todos os Itens
  // Selecionados" (Option1) — os modos "Por Faixa de Data"/"Por
  // Favorecido" do legado ficam de fora, já cobertos na prática pela
  // busca/filtro que a lista já tem antes de marcar manualmente.
  const [transfModalOpen, setTransfModalOpen] = useState(false);
  const [transfDataLiq, setTransfDataLiq] = useState<string | null>(null);
  const [transfConta, setTransfConta] = useState<number | null>(null);

  // Alterar Situação do Vencimento (Normal/Jurídico/Protestado) direto de
  // itens bloqueados por serem de Contas a Receber (`flag_transf_caixa ===
  // "R"`) — achado do usuário 2026-08-31 ("possibilitar da tela de
  // Previsão alterar a situação do vencimento dando um clique em
  // lançamentos bloqueados", depois "permitir fazer essa alteração em
  // lote"). Clicar num item bloqueado (checkbox ou linha) MARCA ele nesse
  // conjunto próprio (não no `selecionados` do Efetivar) — não abre o
  // modal na hora, só depois que o usuário confirma "Alterar Situação",
  // mesmo padrão 2 passos do Efetivar Selecionadas.
  const [situacaoVencSelecionados, setSituacaoVencSelecionados] = useState<Record<number, boolean>>({});
  const [situacaoVencModalOpen, setSituacaoVencModalOpen] = useState(false);
  const [situacaoVencValor, setSituacaoVencValor] = useState(0);
  const [situacaoVencSalvando, setSituacaoVencSalvando] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [prevSalvando, setPrevSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);
  const [autorizarOpen, setAutorizarOpen] = useState(false);
  const [codigoEditando, setCodigoEditando] = useState<number | null>(null);
  const [prevFConta, setPrevFConta] = useState<number | null>(null);
  const [prevFContaDestino, setPrevFContaDestino] = useState<number | null>(null);
  const [prevFTipo, setPrevFTipo] = useState(0);
  const [prevFFavorecido, setPrevFFavorecido] = useState("");
  const [prevFClasse, setPrevFClasse] = useState<number | null>(null);
  const [prevFSubClasse, setPrevFSubClasse] = useState<number | null>(null);
  const [prevFDocumento, setPrevFDocumento] = useState("");
  const [prevFDataDocumento, setPrevFDataDocumento] = useState<string | null>(null);
  const [prevFDataVencimento, setPrevFDataVencimento] = useState<string | null>(null);
  const [prevFValor, setPrevFValor] = useState("");
  const [prevFMemorando, setPrevFMemorando] = useState("");
  const [prevFFrequencia, setPrevFFrequencia] = useState<number>(10);
  const [prevFParcelas, setPrevFParcelas] = useState("1");
  const [prevFRateio, setPrevFRateio] = useState<RateioLinhaPrev[]>([]);

  const buscarPrevisoes = useCallback(async () => {
    if (!conn) return;
    setPrevBuscando(true);
    try {
      const qs = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, filtro_data: filtroData });
      if (prevContaFiltro) qs.set("conta", String(prevContaFiltro));
      if (tipoFiltro !== null) qs.set("tipo", String(tipoFiltro));
      if (busca.trim()) qs.set("busca", busca.trim());
      if (filtroData === "mes") qs.set("mes_ref", prevMesRef);
      const resp = await fetch(`${conn.api}/api/previsoes?${qs.toString()}`);
      const j = await resp.json();
      if (j?.success) {
        setPrevItens(j.items || []);
        setSelecionados({});
      } else {
        setPrevItens([]);
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setPrevBuscando(false);
    }
  }, [conn, prevContaFiltro, tipoFiltro, filtroData, prevMesRef, busca, feedback]);

  // Totais do gráfico Receita x Despesa — busca À PARTE, sempre SEM o
  // filtro de Tipo (respeita conta/período/busca, igual à lista, mas
  // ignora Tipo de propósito). Motivo: o gráfico existe pra COMPARAR
  // Receber x Pagar — se ele seguisse o filtro de Tipo também, filtrar
  // a lista só por "Pagar" zerava o lado "Receber" do gráfico, dando a
  // impressão de que não existe nada a receber (achado real do usuário,
  // 2026-08-31 — o gráfico "sumia" um lado sempre que a lista era
  // filtrada por tipo, o que não faz sentido pro propósito do gráfico).
  const [totaisGrafico, setTotaisGrafico] = useState<{ receber: number; pagar: number } | null>(null);
  const buscarTotaisGrafico = useCallback(async () => {
    if (!conn) return;
    try {
      const qs = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, filtro_data: filtroData });
      if (prevContaFiltro) qs.set("conta", String(prevContaFiltro));
      if (busca.trim()) qs.set("busca", busca.trim());
      if (filtroData === "mes") qs.set("mes_ref", prevMesRef);
      const resp = await fetch(`${conn.api}/api/previsoes?${qs.toString()}`);
      const j = await resp.json();
      if (j?.success) {
        const items: Previsao[] = j.items || [];
        setTotaisGrafico({
          receber: items.filter((it) => it.tipo === 1).reduce((s, it) => s + it.valor, 0),
          pagar: items.filter((it) => it.tipo === 0).reduce((s, it) => s + it.valor, 0),
        });
      }
    } catch {
      // silencioso — o gráfico é só um complemento visual, não crítico
    }
  }, [conn, prevContaFiltro, filtroData, prevMesRef, busca]);

  useEffect(() => { if (conn && podeAbrirPrevisoes) buscarPrevisoes(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [conn, prevContaFiltro, tipoFiltro, filtroData, prevMesRef]);
  useEffect(() => { if (conn && podeAbrirPrevisoes) buscarTotaisGrafico(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [conn, prevContaFiltro, filtroData, prevMesRef]);

  // Bloqueio de item — quando dá pra corrigir aqui mesmo (Contas a
  // Receber, flag_transf_caixa="R"), MARCA o item no conjunto próprio de
  // "Alterar Situação" (2 passos, igual Efetivar Selecionadas — achado do
  // usuário 2026-08-31: "permitir fazer essa alteração em lote"). Pra
  // qualquer outro bloqueio (sem correção possível aqui), o toast
  // continua sendo o único feedback, como antes.
  const toggleItem = (it: Previsao) => {
    if (it.bloqueada) {
      if (it.flag_transf_caixa === "R" && it.cod_transf_caixa) {
        setSituacaoVencSelecionados((prev) => ({ ...prev, [it.codigo]: !prev[it.codigo] }));
      } else {
        feedback.showError(it.bloqueio_motivo || "Operação não permitida.");
      }
      return;
    }
    setSelecionados((prev) => ({ ...prev, [it.codigo]: !prev[it.codigo] }));
  };

  const situacaoVencItens = prevItens.filter((it) => situacaoVencSelecionados[it.codigo]);

  const abrirSituacaoVencModal = () => {
    if (situacaoVencItens.length === 0) { feedback.showError("Selecione ao menos um vencimento bloqueado."); return; }
    // Pré-carrega com o valor atual quando todos os selecionados já têm a
    // MESMA situação — evita reabrir sempre em "Normal" mesmo depois de
    // já ter gravado outra coisa (achado do usuário 2026-08-31).
    const atuais = new Set(situacaoVencItens.map((it) => it.situacao_duplicata_atual ?? 0));
    setSituacaoVencValor(atuais.size === 1 ? (situacaoVencItens[0].situacao_duplicata_atual ?? 0) : 0);
    setSituacaoVencModalOpen(true);
  };

  const confirmarSituacaoVencimento = useCallback(async () => {
    if (!conn) return;
    const codigosVenc = situacaoVencItens.map((it) => it.cod_transf_caixa).filter((c): c is number => !!c);
    if (codigosVenc.length === 0) return;
    setSituacaoVencSalvando(true);
    try {
      const j = await apiSend(conn, "/api/contas-receber/vencimento/situacao-lote", "POST", {
        codigos_venc: codigosVenc, situacao_duplicata: situacaoVencValor,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      const alterados: number[] = j?.alterados || [];
      const falhas: { codigo: number; message: string }[] = j?.falhas || [];
      if (alterados.length > 0) {
        feedback.showSuccess(`Situação atualizada em ${alterados.length} vencimento(s).` + (falhas.length > 0 ? ` ${falhas.length} falharam.` : ""), undefined, 5000);
      }
      if (falhas.length > 0 && alterados.length === 0) {
        feedback.showError(resumirFalhas(falhas), undefined, 5000);
      }
      if (alterados.length > 0) {
        setSituacaoVencModalOpen(false);
        setSituacaoVencSelecionados({});
        buscarPrevisoes();
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setSituacaoVencSalvando(false);
    }
  }, [conn, situacaoVencItens, situacaoVencValor, usuarioCod, classePerm, feedback, buscarPrevisoes]);
  const qtdSelecionados = Object.values(selecionados).filter(Boolean).length;
  const valorSelecionado = prevItens.filter((it) => selecionados[it.codigo]).reduce((s, it) => s + it.valor, 0);
  // Regra geral [GLOBAL] — toda lista sempre totaliza (achado do usuário
  // 2026-08-31: "Total: R$ 0,00" aparecia com a lista cheia mas nada
  // selecionado, sem mostrar o total real da lista).
  const valorTotalLista = prevItens.reduce((s, it) => s + it.valor, 0);

  const selecionadosItens = prevItens.filter((it) => selecionados[it.codigo]);
  const transfTotalCreditos = selecionadosItens.filter((it) => it.tipo === 1).reduce((s, it) => s + it.valor, 0);
  const transfTotalDebitos = selecionadosItens.filter((it) => it.tipo !== 1).reduce((s, it) => s + it.valor, 0);

  const abrirTransferenciaModal = () => {
    if (selecionadosItens.length === 0) { feedback.showError("Selecione ao menos uma previsão."); return; }
    setTransfDataLiq(todayIso());
    setTransfConta(null);
    setTransfModalOpen(true);
  };

  const confirmarTransferencia = useCallback(async () => {
    if (!conn) return;
    const codigos = selecionadosItens.map((it) => it.codigo);
    if (codigos.length === 0) return;
    if (!transfDataLiq) { feedback.showError("Preencha a Data de Liquidação."); return; }
    setEfetivando(true);
    try {
      // timeoutMs=45000 — achado real do usuário 2026-08-31: "Efetivar"
      // fica travado "processando" indefinidamente contra um banco real
      // (hipótese: lock de outra sessão/o próprio legado rodando em
      // paralelo). Sem timeout, o spinner nunca reseta e o usuário não
      // sabe se algo travou ou se ainda está em andamento — ver
      // PENDENCIAS.md > "Painel Financeiro" pro achado completo.
      const j = await apiSend(conn, "/api/previsoes/efetivar", "POST", {
        codigos, data_liquidacao: transfDataLiq, conta: transfConta,
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      }, 45000);
      const efetivados: number[] = j?.efetivados || [];
      const falhas: { codigo: number; message: string }[] = j?.falhas || [];
      if (efetivados.length > 0) {
        feedback.showSuccess(`${efetivados.length} previsão(ões) efetivada(s) com sucesso.` + (falhas.length > 0 ? ` ${falhas.length} falharam.` : ""), undefined, 5000);
      }
      if (falhas.length > 0) {
        const resumo = resumirFalhas(falhas);
        if (efetivados.length === 0) feedback.showError(resumo, undefined, 5000);
        else feedback.showWarning(`Falhas: ${resumo}`, undefined, 5000);
      }
      setTransfModalOpen(false);
      buscarPrevisoes();
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setEfetivando(false);
    }
  }, [conn, selecionadosItens, transfDataLiq, transfConta, usuarioCod, classePerm, feedback, buscarPrevisoes]);

  const abrirNovaPrevisao = () => {
    setCodigoEditando(null);
    setPrevFConta(prevContaFiltro); setPrevFContaDestino(null); setPrevFTipo(tipoFiltro ?? 0);
    setPrevFFavorecido(""); setPrevFClasse(null); setPrevFSubClasse(null); setPrevFDocumento("");
    const hoje = new Date().toISOString().slice(0, 10);
    setPrevFDataDocumento(hoje); setPrevFDataVencimento(hoje);
    setPrevFValor(""); setPrevFMemorando(""); setPrevFFrequencia(10); setPrevFParcelas("1"); setPrevFRateio([]);
    setFormOpen(true);
  };

  const abrirEdicaoPrevisao = async (it: Previsao) => {
    if (!conn) return;
    if (it.bloqueada) {
      if (it.flag_transf_caixa === "R" && it.cod_transf_caixa) {
        setSituacaoVencSelecionados((prev) => ({ ...prev, [it.codigo]: !prev[it.codigo] }));
      } else {
        feedback.showError(it.bloqueio_motivo || "Operação não permitida.");
      }
      return;
    }
    const j = await apiGet(conn, `/api/previsoes/${it.codigo}`);
    if (!j?.success) { feedback.showError(friendlyApiError(j, "Não foi possível abrir a previsão.")); return; }
    setCodigoEditando(it.codigo);
    setPrevFConta(j.conta); setPrevFContaDestino(j.tipo === 2 ? j.classe : null); setPrevFTipo(j.tipo);
    setPrevFFavorecido(j.favorecido_nome || ""); setPrevFClasse(j.tipo !== 2 ? (j.classe ?? null) : null); setPrevFSubClasse(j.tipo !== 2 ? (j.sub_classe ?? null) : null);
    setPrevFDocumento(j.documento || ""); setPrevFDataDocumento(j.data_documento); setPrevFDataVencimento(j.data_vencimento);
    setPrevFValor(String(j.valor ?? "")); setPrevFMemorando(j.memorando || ""); setPrevFFrequencia(j.frequencia ?? 10);
    setPrevFParcelas("1");
    setPrevFRateio((j.rateio || []).map((r: { centro_custo: number; classe: number | null; sub_classe: number | null; valor: number; memorando: string; credito_debito: string; repete_lancamento: boolean }) => ({
      centro_custo: r.centro_custo, classe: r.classe, sub_classe: r.sub_classe, valor: r.valor,
      memorando: r.memorando, credito_debito: r.credito_debito || "C", repete_lancamento: r.repete_lancamento,
    })));
    setFormOpen(true);
  };

  const prevSomaRateio = prevFRateio.reduce((s, r) => s + (Number(r.valor) || 0), 0);
  const prevValorNum = Number(prevFValor.replace(",", ".")) || 0;

  const salvarPrevisao = async () => {
    if (!conn) return;
    setPrevSalvando(true);
    try {
      const j = await apiSend(conn, "/api/previsoes", "POST", {
        codigo: codigoEditando, conta: prevFConta, conta_destino: prevFTipo === 2 ? prevFContaDestino : undefined,
        tipo: prevFTipo, documento: prevFDocumento, data_documento: prevFDataDocumento, data_vencimento: prevFDataVencimento,
        favorecido_nome: prevFFavorecido, classe_previsao: prevFTipo !== 2 ? prevFClasse : null, sub_classe_previsao: prevFTipo !== 2 ? prevFSubClasse : null,
        valor: prevValorNum, memorando: prevFMemorando, frequencia: prevFFrequencia,
        parcelas: codigoEditando ? 1 : (parseInt(prevFParcelas, 10) || 1),
        rateio: prevFRateio.map((r) => ({ centro_custo: r.centro_custo, classe: r.classe, sub_classe: r.sub_classe, valor: Number(r.valor) || 0, memorando: r.memorando, credito_debito: r.credito_debito, repete_lancamento: r.repete_lancamento })),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess("Previsão gravada.");
        setFormOpen(false);
        buscarPrevisoes();
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setPrevSalvando(false);
    }
  };

  const excluirPrevisao = async (autorizadoPor?: string) => {
    if (!conn || !codigoEditando) return;
    setExcluindo(true);
    try {
      const resp = await fetch(`${conn.api}/api/previsoes/${codigoEditando}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, codigo: codigoEditando, autorizado: !!autorizadoPor,
          usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
        }),
      });
      const j = await resp.json();
      if (j?.success) {
        feedback.showSuccess("Previsão excluída.");
        setFormOpen(false);
        setAutorizarOpen(false);
        buscarPrevisoes();
      } else if (j?.exige_autorizacao) {
        setAutorizarOpen(true);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao excluir."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setExcluindo(false);
    }
  };

  const adicionarLinhaRateioPrev = () => setPrevFRateio((prev) => [...prev, { centro_custo: null, classe: null, sub_classe: null, valor: 0, memorando: "", credito_debito: "C", repete_lancamento: false }]);
  const removerLinhaRateioPrev = (idx: number) => setPrevFRateio((prev) => prev.filter((_, i) => i !== idx));
  const atualizarLinhaRateioPrev = (idx: number, patch: Partial<RateioLinhaPrev>) => setPrevFRateio((prev) => prev.map((r, i) => (i === idx ? { ...r, ...patch } : r)));

  // ===== Relatórios — Fase 1 (5 dos ~20 relatórios reais do menu do
  // legado, `FrmPnlCon.frm` > "Relatórios" — os demais ficam registrados
  // em PENDENCIAS.md como próxima rodada, decisão do usuário 2026-08-31).
  // Reaproveita dado/endpoint já existente sempre que possível — só
  // "Receitas x Despesas por Mês" tem endpoint novo dedicado.
  const podeVerContasPagar = can("CONTAS_PAGAR.ABRIR");
  const podeVerContasReceber = can("CONTAS_RECEBER.ABRIR");
  const [relBuscando, setRelBuscando] = useState(false);
  const [relReceitasDespesas, setRelReceitasDespesas] = useState<{ mes: string; receitas: number; despesas: number; saldo: number }[]>([]);
  const [relDuplicatasPagar, setRelDuplicatasPagar] = useState<{ codigo: number; fornecedor_nome: string; valor_em_aberto: number; proximo_vencimento: string | null; vencido: boolean }[]>([]);
  const [relDuplicatasReceber, setRelDuplicatasReceber] = useState<{ codigo: number; cliente_nome: string; valor_em_aberto: number; proximo_vencimento: string | null; vencido: boolean }[]>([]);

  // "Duplicatas Recebidas" (réplica de `Revenda/frmreldur.frm`) — achado
  // do usuário 2026-08-31, análise de Contas a Receber. Diferente de
  // "Duplicatas à Receber em Aberto" acima (já pagas, não em aberto).
  // Escopo desta rodada: Período (Vencimento ou Data de Pagamento),
  // Cliente (código — sem busca por nome nesta 1ª rodada, ver "Melhorias
  // futuras" no texto de ajuda), Forma de Pagamento. Banco/Vendedor/
  // Comandas-NF's ficam de fora, registrados (mesmo padrão de #027).
  type DuRecItem = {
    // `desmembramento` aqui é `Duplicata_Receber.desmembramento`
    // (nvarchar — vira literalmente "CM" pra duplicata de origem
    // Comanda), NÃO o `Duplicata_Rec_Venc.desmembramento` numérico
    // (sequência de parcela) já usado em `Parcela` (contas-receber.tsx)
    // — mesma réplica do legado, que também exibe esse campo bruto no
    // relatório (`Grid.AddItem ... & dr.desmembramento`).
    duplicata: number; desmembramento: string; cliente_nome: string; valor: number;
    dt_vencimento: string | null; data_pag: string | null; juros_pag: number; outros_acrescimos: number;
    desconto_pag: number; outros_desc_pag: number; valor_pag: number; forma_pagamento: string | null;
  };
  const [duRecDataIni, setDuRecDataIni] = useState<string | null>(todayIso());
  const [duRecDataFim, setDuRecDataFim] = useState<string | null>(todayIso());
  const [duRecBase, setDuRecBase] = useState<"vencimento" | "pagamento">("vencimento");
  // Cliente — busca real (não só código cru), mesmo padrão já usado no
  // lançamento avulso desta mesma tela de Contas a Receber
  // (`ClientSearchModal` + `GET /api/clientes/find/search`).
  const [duRecClienteCod, setDuRecClienteCod] = useState<number | null>(null);
  const [duRecClienteNome, setDuRecClienteNome] = useState("");
  const [duRecClienteSearchOpen, setDuRecClienteSearchOpen] = useState(false);
  const [duRecClienteTerm, setDuRecClienteTerm] = useState("");
  const [duRecClienteResults, setDuRecClienteResults] = useState<ClienteRow[]>([]);
  const [duRecClienteLoading, setDuRecClienteLoading] = useState(false);
  const [duRecFormaPag, setDuRecFormaPag] = useState<string | null>(null);
  const [duRecFormaPagOpts, setDuRecFormaPagOpts] = useState<SelectOption[]>([]);
  const [duRecBancoCedente, setDuRecBancoCedente] = useState<number | null>(null);
  const [duRecBancoOpts, setDuRecBancoOpts] = useState<SelectOption[]>([]);
  // Vendedor — só funciona pra duplicata de origem Comanda no legado
  // (`Duplicata_Rec_Nf→Receber→movimentacao`, `serie_nf='CM'`); uma
  // duplicata originada de NF direto nunca aparece com esse filtro
  // ativo, é limitação real da fonte, não bug. "Comandas"/"NF's" — réplica
  // de `frmreldur.frm::Check1`/`Check2` (`dr.desmembramento='CM'`); os 2
  // marcados (ou os 2 desmarcados) = sem filtro, mesmo fallback do legado.
  const [duRecVendedor, setDuRecVendedor] = useState<number | null>(null);
  const [duRecVendedorOpts, setDuRecVendedorOpts] = useState<SelectOption[]>([]);
  const [duRecComandas, setDuRecComandas] = useState(true);
  const [duRecNotasFiscais, setDuRecNotasFiscais] = useState(true);
  const [duRecBuscando, setDuRecBuscando] = useState(false);
  const [duRecItens, setDuRecItens] = useState<DuRecItem[]>([]);
  const [duRecResumoFp, setDuRecResumoFp] = useState<{ forma_pagamento: string; valor: number }[]>([]);
  const [duRecTotal, setDuRecTotal] = useState(0);

  useEffect(() => {
    if (!conn) return;
    (async () => {
      const [fp, bc, fu] = await Promise.all([
        apiGet(conn, "/api/forma-pagamento"), apiGet(conn, "/api/bancos"), apiGet(conn, "/api/funcionarios"),
      ]);
      if (fp?.success) setDuRecFormaPagOpts((fp.items || []).map((x: { codigo: string; descricao: string }) => ({ value: x.codigo, label: x.descricao })));
      if (bc?.success) setDuRecBancoOpts((bc.items || []).map((x: { codigo: number; descricao: string }) => ({ value: x.codigo, label: x.descricao })));
      if (fu?.success) setDuRecVendedorOpts((fu.items || []).map((x: { codigo: number; nome: string; nome_guerra: string }) => ({ value: x.codigo, label: x.nome_guerra || x.nome })));
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  useEffect(() => {
    if (!duRecClienteSearchOpen || !conn) return;
    const t = setTimeout(async () => {
      setDuRecClienteLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(duRecClienteTerm)}`;
        const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
        const j = await r.json();
        setDuRecClienteResults(j?.items || []);
      } catch { setDuRecClienteResults([]); } finally { setDuRecClienteLoading(false); }
    }, 300);
    return () => clearTimeout(t);
  }, [duRecClienteTerm, duRecClienteSearchOpen, conn]);

  const buscarDuplicatasRecebidas = useCallback(async () => {
    if (!conn || !duRecDataIni || !duRecDataFim) return;
    setDuRecBuscando(true);
    try {
      const qs = new URLSearchParams({
        servidor: conn.servidor, banco: conn.banco, data_ini: duRecDataIni, data_fim: duRecDataFim, base: duRecBase,
      });
      if (duRecClienteCod) qs.set("cliente", String(duRecClienteCod));
      if (duRecFormaPag) qs.set("forma_pag", duRecFormaPag);
      if (duRecBancoCedente) qs.set("banco_cedente", String(duRecBancoCedente));
      if (duRecVendedor) qs.set("vendedor", String(duRecVendedor));
      qs.set("comandas", String(duRecComandas));
      qs.set("notas_fiscais", String(duRecNotasFiscais));
      const j = await apiGet(conn, `/api/painel-financeiro/duplicatas-recebidas?${qs.toString()}`);
      if (j?.success) {
        setDuRecItens(j.itens || []);
        setDuRecResumoFp(j.resumo_forma_pag || []);
        setDuRecTotal(j.total_valor_pag || 0);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao buscar Duplicatas Recebidas."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setDuRecBuscando(false);
    }
  }, [conn, duRecDataIni, duRecDataFim, duRecBase, duRecClienteCod, duRecFormaPag, duRecBancoCedente, duRecVendedor, duRecComandas, duRecNotasFiscais, feedback]);

  // Agrupamento por dia (mesma ideia do legado — "Total do Dia") —
  // calculado no frontend a partir da lista já buscada, sem chamada nova.
  const duRecPorDia = (() => {
    const grupos: { data: string; itens: DuRecItem[]; total: number }[] = [];
    for (const it of duRecItens) {
      const data = (duRecBase === "pagamento" ? it.data_pag : it.dt_vencimento) || "-";
      let g = grupos.find((x) => x.data === data);
      if (!g) { g = { data, itens: [], total: 0 }; grupos.push(g); }
      g.itens.push(it);
      g.total += it.valor_pag;
    }
    return grupos;
  })();

  useEffect(() => {
    if (conn && aba === "relatorios" && podeVerContasReceber) buscarDuplicatasRecebidas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, aba, podeVerContasReceber, duRecDataIni, duRecDataFim, duRecBase, duRecClienteCod, duRecFormaPag, duRecBancoCedente, duRecVendedor, duRecComandas, duRecNotasFiscais]);

  const imprimirDuplicatasRecebidas = useCallback(async () => {
    if (!conn) return;
    const { fetchEmpresaHeader, buildReportHeaderHtml } = await import("@/src/utils/print-report-header");
    const { printHtml, escHtml } = await import("@/src/utils/printHtml");
    const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
    const linhas = duRecPorDia.map((g) => `
      <tr style="background:#eef">
        <td colspan="4"><b>Total do Dia (${g.data === "-" ? "-" : formatDateBR(g.data)})</b></td>
        <td style="text-align:right"><b>${escHtml(formatBRL(g.total))}</b></td>
      </tr>
      ${g.itens.map((it) => `
        <tr>
          <td>${it.duplicata}/${it.desmembramento}</td>
          <td>${escHtml(it.cliente_nome)}</td>
          <td>${escHtml(it.forma_pagamento || "SEM FORMA CADASTRADA")}</td>
          <td style="text-align:right">${escHtml(formatDateBR(duRecBase === "pagamento" ? it.data_pag : it.dt_vencimento))}</td>
          <td style="text-align:right">${escHtml(formatBRL(it.valor_pag))}</td>
        </tr>
      `).join("")}
    `).join("");
    const resumo = duRecResumoFp.map((r) => `<tr><td>${escHtml(r.forma_pagamento)}</td><td style="text-align:right">${escHtml(formatBRL(r.valor))}</td></tr>`).join("");
    const html = `
      ${buildReportHeaderHtml(empresa, "Duplicatas Recebidas")}
      <p>Período (${duRecBase === "pagamento" ? "Data de Pagamento" : "Vencimento"}): ${formatDateBR(duRecDataIni)} até ${formatDateBR(duRecDataFim)}</p>
      <table style="width:100%;border-collapse:collapse;font-size:12px" border="1" cellpadding="4">
        <thead><tr><th>Documento</th><th>Cliente</th><th>Forma Pag.</th><th>Data</th><th>Recebido</th></tr></thead>
        <tbody>${linhas}</tbody>
      </table>
      <h3>Resumo por Forma de Pagamento</h3>
      <table style="width:50%;border-collapse:collapse;font-size:12px" border="1" cellpadding="4"><tbody>${resumo}</tbody></table>
      <p style="margin-top:12px"><b>TOTAL GERAL: ${escHtml(formatBRL(duRecTotal))}</b></p>
    `;
    printHtml(html, "Duplicatas Recebidas");
  }, [conn, duRecPorDia, duRecResumoFp, duRecTotal, duRecBase, duRecDataIni, duRecDataFim]);

  const exportarDuplicatasRecebidas = useCallback(async () => {
    const { exportSheetsToXlsx } = await import("@/src/utils/export-xlsx");
    exportSheetsToXlsx("duplicatas-recebidas", [{
      name: "Duplicatas Recebidas",
      rows: duRecItens.map((it) => ({
        Documento: `${it.duplicata}/${it.desmembramento}`, Cliente: it.cliente_nome,
        "Forma Pagamento": it.forma_pagamento || "SEM FORMA CADASTRADA",
        Vencimento: it.dt_vencimento, "Data Pagamento": it.data_pag, Valor: it.valor,
        Juros: it.juros_pag, "Outros Acréscimos": it.outros_acrescimos, Desconto: it.desconto_pag,
        "Outros Descontos": it.outros_desc_pag, "Valor Recebido": it.valor_pag,
      })),
    }]);
  }, [duRecItens]);

  // "Duplicatas Pagas" (`Revenda/frmreldup.frm`) — mirror mais simples de
  // "Duplicatas Recebidas" acima: só período (Vencimento/Data PG) +
  // Fornecedor, agrupado por dia (sem forma de pagamento — a fonte real
  // não junta essa tabela). Achado do usuário 2026-08-31, ver
  // AJUSTES.md #039.
  type DuPagItem = {
    duplicata: number; desmembramento: number; fornecedor_nome: string; valor: number;
    dt_vencimento: string | null; data_pag: string | null; juros_pag: number; outros_acres_pag: number;
    desconto_pag: number; outros_desc_pag: number; valor_pag: number; observacao: string | null;
  };
  const [duPagDataIni, setDuPagDataIni] = useState<string | null>(todayIso());
  const [duPagDataFim, setDuPagDataFim] = useState<string | null>(todayIso());
  const [duPagBase, setDuPagBase] = useState<"vencimento" | "pagamento">("vencimento");
  const [duPagFornCod, setDuPagFornCod] = useState<number | null>(null);
  const [duPagFornNome, setDuPagFornNome] = useState("");
  const [duPagFornSearchOpen, setDuPagFornSearchOpen] = useState(false);
  const [duPagFornTerm, setDuPagFornTerm] = useState("");
  const [duPagFornResults, setDuPagFornResults] = useState<FornecedorRow[]>([]);
  const [duPagFornLoading, setDuPagFornLoading] = useState(false);
  const [duPagBuscando, setDuPagBuscando] = useState(false);
  const [duPagItens, setDuPagItens] = useState<DuPagItem[]>([]);
  const [duPagTotal, setDuPagTotal] = useState(0);

  useEffect(() => {
    if (!duPagFornSearchOpen || !conn) return;
    const term = duPagFornTerm.trim();
    if (term.length < 2) { setDuPagFornResults([]); return; }
    setDuPagFornLoading(true);
    const t = setTimeout(async () => {
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(term)}`;
        const r = await fetch(`${base}/api/fornecedores?${qs}`);
        const j = await r.json();
        setDuPagFornResults(j?.success ? (j.items || []) : []);
      } catch { setDuPagFornResults([]); } finally { setDuPagFornLoading(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [duPagFornTerm, duPagFornSearchOpen, conn]);

  const buscarDuplicatasPagas = useCallback(async () => {
    if (!conn || !duPagDataIni || !duPagDataFim) return;
    setDuPagBuscando(true);
    try {
      const qs = new URLSearchParams({
        servidor: conn.servidor, banco: conn.banco, data_ini: duPagDataIni, data_fim: duPagDataFim, base: duPagBase,
      });
      if (duPagFornCod) qs.set("fornecedor", String(duPagFornCod));
      const j = await apiGet(conn, `/api/painel-financeiro/duplicatas-pagas?${qs.toString()}`);
      if (j?.success) {
        setDuPagItens(j.itens || []);
        setDuPagTotal(j.total?.valor_pag || 0);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao buscar Duplicatas Pagas."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setDuPagBuscando(false);
    }
  }, [conn, duPagDataIni, duPagDataFim, duPagBase, duPagFornCod, feedback]);

  const duPagPorDia = (() => {
    const grupos: { data: string; itens: DuPagItem[]; total: number }[] = [];
    for (const it of duPagItens) {
      const data = (duPagBase === "pagamento" ? it.data_pag : it.dt_vencimento) || "-";
      let g = grupos.find((x) => x.data === data);
      if (!g) { g = { data, itens: [], total: 0 }; grupos.push(g); }
      g.itens.push(it);
      g.total += it.valor_pag;
    }
    return grupos;
  })();

  useEffect(() => {
    if (conn && aba === "relatorios" && podeVerContasPagar) buscarDuplicatasPagas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, aba, podeVerContasPagar, duPagDataIni, duPagDataFim, duPagBase, duPagFornCod]);

  const imprimirDuplicatasPagas = useCallback(async () => {
    if (!conn) return;
    const { fetchEmpresaHeader, buildReportHeaderHtml } = await import("@/src/utils/print-report-header");
    const { printHtml, escHtml } = await import("@/src/utils/printHtml");
    const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
    const linhas = duPagPorDia.map((g) => `
      <tr style="background:#eef">
        <td colspan="3"><b>Total do Dia (${g.data === "-" ? "-" : formatDateBR(g.data)})</b></td>
        <td style="text-align:right"><b>${escHtml(formatBRL(g.total))}</b></td>
      </tr>
      ${g.itens.map((it) => `
        <tr>
          <td>${it.duplicata}/${it.desmembramento}</td>
          <td>${escHtml(it.fornecedor_nome)}</td>
          <td style="text-align:right">${escHtml(formatDateBR(duPagBase === "pagamento" ? it.data_pag : it.dt_vencimento))}</td>
          <td style="text-align:right">${escHtml(formatBRL(it.valor_pag))}</td>
        </tr>
      `).join("")}
    `).join("");
    const html = `
      ${buildReportHeaderHtml(empresa, "Duplicatas Pagas")}
      <p>Período (${duPagBase === "pagamento" ? "Data de Pagamento" : "Vencimento"}): ${formatDateBR(duPagDataIni)} até ${formatDateBR(duPagDataFim)}</p>
      <table style="width:100%;border-collapse:collapse;font-size:12px" border="1" cellpadding="4">
        <thead><tr><th>Documento</th><th>Fornecedor</th><th>Data</th><th>Pago</th></tr></thead>
        <tbody>${linhas}</tbody>
      </table>
      <p style="margin-top:12px"><b>TOTAL GERAL: ${escHtml(formatBRL(duPagTotal))}</b></p>
    `;
    printHtml(html, "Duplicatas Pagas");
  }, [conn, duPagPorDia, duPagTotal, duPagBase, duPagDataIni, duPagDataFim]);

  const exportarDuplicatasPagas = useCallback(async () => {
    const { exportSheetsToXlsx } = await import("@/src/utils/export-xlsx");
    exportSheetsToXlsx("duplicatas-pagas", [{
      name: "Duplicatas Pagas",
      rows: duPagItens.map((it) => ({
        Documento: `${it.duplicata}/${it.desmembramento}`, Fornecedor: it.fornecedor_nome,
        Vencimento: it.dt_vencimento, "Data Pagamento": it.data_pag, Valor: it.valor,
        Juros: it.juros_pag, "Outros Acréscimos": it.outros_acres_pag, Desconto: it.desconto_pag,
        "Outros Descontos": it.outros_desc_pag, "Valor Pago": it.valor_pag,
      })),
    }]);
  }, [duPagItens]);

  const buscarRelatorios = useCallback(async () => {
    if (!conn) return;
    setRelBuscando(true);
    try {
      const qs = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, periodo: "tudo" });
      if (relContaFiltro) qs.set("conta", String(relContaFiltro));
      const chamadas: Promise<void>[] = [
        fetch(`${conn.api}/api/painel-financeiro/receitas-despesas-mes?${qs.toString()}`).then((r) => r.json()).then((j) => { if (j?.success) setRelReceitasDespesas(j.linhas || []); }),
      ];
      if (podeVerContasPagar) {
        const qsP = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, situacao: "A" });
        chamadas.push(fetch(`${conn.api}/api/contas-pagar?${qsP.toString()}`).then((r) => r.json()).then((j) => { if (j?.success) setRelDuplicatasPagar(j.items || []); }));
      }
      if (podeVerContasReceber) {
        const qsR = new URLSearchParams({ servidor: conn.servidor, banco: conn.banco, situacao: "A" });
        chamadas.push(fetch(`${conn.api}/api/contas-receber?${qsR.toString()}`).then((r) => r.json()).then((j) => { if (j?.success) setRelDuplicatasReceber(j.items || []); }));
      }
      await Promise.all(chamadas);
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setRelBuscando(false);
    }
  }, [conn, podeVerContasPagar, podeVerContasReceber, relContaFiltro, feedback]);

  useEffect(() => { if (conn && aba === "relatorios") buscarRelatorios(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [conn, aba, relContaFiltro]);

  // "Movimentação de Contas" — mesmo dado já carregado pra aba Painel de
  // Movimentações (`itens`), só reagrupado por conta com subtotal —
  // nenhuma chamada nova à API.
  const movimentacaoPorConta = (() => {
    const grupos = new Map<number, { descricao: string; total: number; qtd: number }>();
    for (const it of itens) {
      const desc = contas.find((c) => c.value === it.conta)?.label || `Conta ${it.conta}`;
      const g = grupos.get(it.conta) || { descricao: desc, total: 0, qtd: 0 };
      g.total = _round2(g.total + (it.credito ? it.valor : -it.valor));
      g.qtd += 1;
      grupos.set(it.conta, g);
    }
    return Array.from(grupos.values());
  })();
  function _round2(v: number) { return Math.round(v * 100) / 100; }

  // "Contas a Receber" (atraso/hoje) vem de duplicata_rec_venc — mesma
  // fonte da tela Contas a Receber, navegação pra lá é literalmente a
  // mesma listagem. Usado tanto pelos cards de alerta quanto pelo
  // relatório "Duplicatas à Receber em Aberto".
  const navegarParaContasReceber = (situacaoAlvo: "V" | "A") => router.push(`/contas-receber?situacao=${situacaoAlvo}` as never);
  // "Duplicatas à Pagar em Aberto" (relatório) É a mesma fonte de Contas
  // a Pagar (Duplicata_Pag_Venc) — navegação normal.
  const navegarParaContasPagar = (situacaoAlvo: "V" | "A") => router.push(`/contas-pagar?situacao=${situacaoAlvo}` as never);
  // "Pagamentos em Atraso"/"À Pagar Hoje" (cards de alerta) são
  // DIFERENTES — vêm de `previsoes WHERE tipo=0` (achado real, ver
  // `_alertas_sync`), não de Duplicata_Pag_Venc. Achado do usuário
  // 2026-08-31: navegar pra Contas a Pagar trazia lista vazia, porque é
  // uma fonte de dado diferente da que o card resume. Correção: os 2
  // cards de Pagar levam pra aba Previsões (mesma tela, já filtrada por
  // Pagar + Atraso/Hoje) em vez de sair pra Contas a Pagar.
  const irParaPrevisoesPagar = (filtroDataAlvo: "atraso" | "hoje") => {
    setAba("previsoes");
    setTipoFiltro(0);
    setFiltroData(filtroDataAlvo);
  };

  // Classe/Sub-Classe (Plano de Contas) — cadastro real, nunca texto
  // livre (achado do usuário 2026-08-31). Classe filtrada por Despesa/
  // Receita conforme o tipo (Pagar/Saque=D, Receber=R); Sub-Classe
  // filtrada pela Classe já escolhida. Usado nos 2 modais (Lançamento
  // Direto do Painel e Nova/Editar Previsão).
  const classeOptionsPara = (tipoRD: "R" | "D"): SelectOption[] =>
    planoContas.filter((c) => c.tipo === tipoRD).map((c) => ({ value: c.codigo, label: c.descricao }));
  const subClasseOptionsPara = (classeCodigo: number | null): SelectOption[] => {
    const classe = planoContas.find((c) => c.codigo === classeCodigo);
    if (!classe) return [];
    return classe.sub_classes.filter((sc) => sc.ativa).map((sc) => ({ value: sc.codigo, label: sc.descricao }));
  };

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Painel Financeiro está disponível apenas no web." testID="painel-financeiro-web-only" />;
  }
  if (!loading && !podeAbrirPainel && !podeAbrirPrevisoes) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Painel Financeiro." testID="painel-financeiro-locked" />;
  }

  const abas: { key: Aba; label: string; icon: React.ComponentProps<typeof Ionicons>["name"] }[] = [
    ...(podeAbrirPainel ? [{ key: "painel" as const, label: "Painel de Movimentações", icon: "speedometer-outline" as const }] : []),
    ...(podeAbrirPrevisoes ? [{ key: "previsoes" as const, label: "Previsões", icon: "calendar-outline" as const }] : []),
    ...(podeAbrirPainel ? [{ key: "relatorios" as const, label: "Relatórios", icon: "bar-chart-outline" as const }] : []),
  ];

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="painel-financeiro-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        {abas.length > 1 ? (
          <View style={{ flex: 1, flexDirection: "row", justifyContent: "center", gap: spacing.sm }}>
            {abas.map((t) => (
              <Pressable key={t.key} onPress={() => setAba(t.key)} style={[tabBtnHeaderStyle(), aba === t.key && tabBtnHeaderSelStyle()]} testID={`painel-financeiro-aba-${t.key}`}>
                <Ionicons name={t.icon} size={15} color={aba === t.key ? colors.brandPrimary : colors.onBrandPrimary} />
                <Text style={[tabBtnHeaderLabelStyle(), aba === t.key && tabBtnHeaderLabelSelStyle()]}>{t.label}</Text>
              </Pressable>
            ))}
          </View>
        ) : (
          <Text style={headerTitleStyle()} numberOfLines={1}>Painel Financeiro</Text>
        )}
        {aba === "previsoes" && can("PREVISOES.GRAVAR") ? (
          <Pressable onPress={abrirNovaPrevisao} style={headerNovaPrevisaoBtnStyle()} testID="previsoes-novo-btn-header">
            <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
            <Text style={{ fontSize: 12, fontWeight: "600" as const, color: colors.onBrandPrimary }}>Nova Previsão</Text>
          </Pressable>
        ) : null}
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary}
          onPress={() => (aba === "painel" ? setAjudaOpen(true) : setPrevAjudaOpen(true))}
          testID="painel-financeiro-ajuda-btn"
        />
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : aba === "painel" ? (
            <View style={{ gap: spacing.md }}>
              {/* Filtros */}
              <View style={WEB_FILTER_CARD}>
                <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", alignItems: "flex-end" }}>
                  <View style={{ width: 220 }}>
                    <Text style={fieldLabel()}>Conta</Text>
                    <SelectField value={contaFiltro} onChange={(v) => setContaFiltro(v as number | null)} options={contas} placeholder="Todas as contas…" compactWeb allowClear testID="painel-financeiro-conta-filtro" />
                  </View>
                  <View style={{ flexDirection: "row", gap: 6 }}>
                    {PERIODOS.map((p) => (
                      <Pressable key={p.value} onPress={() => setPeriodo(p.value)} style={[chipStyle(), periodo === p.value && chipSelStyle()]} testID={`painel-financeiro-periodo-${p.value}`}>
                        <Text style={[chipTextStyle(), periodo === p.value && chipTextSelStyle()]}>{p.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                  {periodo === "mes" ? (
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                      <Pressable onPress={() => setMesRef((r) => shiftMonth(r, -1))} hitSlop={8} testID="painel-financeiro-mes-anterior"><Ionicons name="chevron-back-circle-outline" size={22} color={colors.brandPrimary} /></Pressable>
                      <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, minWidth: 90, textAlign: "center" }}>{monthLabel(mesRef)}</Text>
                      <Pressable onPress={() => setMesRef((r) => shiftMonth(r, 1))} hitSlop={8} testID="painel-financeiro-mes-proximo"><Ionicons name="chevron-forward-circle-outline" size={22} color={colors.brandPrimary} /></Pressable>
                    </View>
                  ) : null}
                  <CheckboxToggle
                    checked={partirDeHoje}
                    onToggle={() => { setPartirDeHoje((v) => !v); if (!partirDeHoje) setDesconsiderarPendencias(false); }}
                    label="Previsões a partir de hoje"
                    testID="painel-financeiro-partir-de-hoje"
                  />
                  <CheckboxToggle
                    checked={desconsiderarPendencias}
                    onToggle={() => { setDesconsiderarPendencias((v) => !v); if (!desconsiderarPendencias) setPartirDeHoje(false); }}
                    label="Desconsiderar Pendências"
                    testID="painel-financeiro-desconsiderar-pendencias"
                  />
                  {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : null}
                </View>
              </View>

              {/* 4 alertas — pedido explícito do usuário, 2026-08-31: ficam
                  ACIMA do bloco de Saldos/gráfico, não abaixo. */}
              {resumo ? (
                <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                  <AlertaCard icon="arrow-down-circle-outline" label="Contas a Receber em Atraso" alerta={resumo.alertas.contas_a_receber_atraso} cor={colors.success} onPress={podeVerContasReceber ? () => navegarParaContasReceber("V") : undefined} />
                  <AlertaCard icon="today-outline" label="Contas a Receber Hoje" alerta={resumo.alertas.contas_a_receber_hoje} cor={colors.success} onPress={podeVerContasReceber ? () => navegarParaContasReceber("A") : undefined} />
                  <AlertaCard icon="arrow-up-circle-outline" label="Pagamentos em Atraso" alerta={resumo.alertas.pagamentos_atraso} cor={colors.error} onPress={podeAbrirPrevisoes ? () => irParaPrevisoesPagar("atraso") : undefined} />
                  <AlertaCard icon="today-outline" label="A Pagar Hoje" alerta={resumo.alertas.a_pagar_hoje} cor={colors.error} onPress={podeAbrirPrevisoes ? () => irParaPrevisoesPagar("hoje") : undefined} />
                </View>
              ) : null}

              {/* Saldo/Totais */}
              {resumo ? (
                <View style={WEB_FILTER_CARD}>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                    <KpiBlock label="Saldo Atual" valor={resumo.saldo_atual} destaque tooltip="Soma do saldo real das contas selecionadas, agora." />
                    <KpiBlock label="Saldo Previsto" valor={resumo.saldo_previsto} tooltip="Saldo Atual + Pendências (previsões vencidas antes do período) e Previsões dentro do período — uma projeção, não o saldo real ainda." />
                    <KpiBlock label="Saldo Anterior ao Período" valor={resumo.saldo_anterior_periodo} tooltip="Saldo que a conta já tinha ANTES do período selecionado começar." />
                    <KpiBlock label="Entradas do Período" valor={resumo.total_receitas_periodo} cor={colors.success} tooltip="Soma de tudo que entrou nas contas dentro do período selecionado." />
                    <KpiBlock label="Saídas do Período" valor={resumo.total_despesas_periodo} cor={colors.error} tooltip="Soma de tudo que saiu das contas dentro do período selecionado." />
                    <KpiBlock label="Saldo ao Fim do Período" valor={resumo.saldo_fim_periodo} destaque tooltip="Saldo Anterior ao Período + Entradas − Saídas do período." />
                  </View>
                  {serie ? (
                    <View style={{ marginTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm }}>
                      <SaldoChart pontos={serie.pontos} saldoInicial={serie.saldo_inicial} />
                    </View>
                  ) : null}
                </View>
              ) : null}

              {/* Lançamento direto */}
              {can("PAINEL_MOV.LANCAR") ? (
                <View style={WEB_FILTER_CARD}>
                  <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Lançamento Direto</Text>
                  <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.sm }}>
                    {[0, 1, 2, 3].map((t) => (
                      <Pressable key={t} onPress={() => abrirLancamento(t)} style={[secondaryBtnStyle(), { borderColor: tipoColor(t) }]} testID={`painel-financeiro-lancar-${t}`}>
                        <Ionicons name="add-circle-outline" size={16} color={tipoColor(t)} />
                        <Text style={[secondaryBtnLabelStyle(), { color: tipoColor(t) }]}>{TIPO_LABEL_LONGO[t]}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              ) : null}

              {/* Grade de movimentações */}
              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Movimentações ({itens.length})</Text>
                {itens.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhuma movimentação no período.</Text>
                ) : (
                  itens.map((it) => (
                    <View key={it.codigo} style={itemRowStyle()} testID={`painel-financeiro-item-${it.codigo}`}>
                      {!it.editavel ? <Ionicons name="lock-closed-outline" size={14} color={colors.muted} style={{ marginRight: 6 }} /> : null}
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{it.favorecido_nome || "(sem favorecido)"}</Text>
                        <Text style={{ fontSize: 12, color: colors.muted }}>
                          {formatDateBR(it.data_liquidacao)}{it.documento ? ` · Doc. ${it.documento}` : ""}{it.memorando ? ` · ${it.memorando}` : ""}
                        </Text>
                      </View>
                      <View style={[flagBadgeStyle(), { backgroundColor: tipoColor(it.tipo) + "22" }]}>
                        <Text style={[flagBadgeTextStyle(), { color: tipoColor(it.tipo) }]}>{TIPO_LABEL[it.tipo]}</Text>
                      </View>
                      <Text style={{ fontSize: 14, fontWeight: "700", color: it.credito ? colors.success : colors.error, marginLeft: spacing.md, minWidth: 100, textAlign: "right" }}>
                        {it.credito ? "+" : "-"}{formatBRL(it.valor)}
                      </Text>
                      {it.editavel && can("PAINEL_MOV.EXCLUIR") ? (
                        <Pressable onPress={() => excluirLancamento(it.codigo)} disabled={excluindoCodigo === it.codigo} hitSlop={8} style={{ marginLeft: spacing.sm }} testID={`painel-financeiro-excluir-${it.codigo}`}>
                          {excluindoCodigo === it.codigo ? <ActivityIndicator size="small" color={colors.error} /> : <Ionicons name="trash-outline" size={18} color={colors.error} />}
                        </Pressable>
                      ) : <View style={{ width: 26 }} />}
                    </View>
                  ))
                )}
              </View>
            </View>
          ) : aba === "previsoes" ? (
            <View style={{ gap: spacing.md }}>
              <View style={WEB_FILTER_CARD}>
                <View style={{ flexDirection: "row", gap: spacing.lg, flexWrap: "wrap", alignItems: "flex-start" }}>
                  <View style={{ width: 190 }}>
                    <Text style={fieldLabel()}>Conta</Text>
                    <SelectField value={prevContaFiltro} onChange={(v) => setPrevContaFiltro(v as number | null)} options={contas} placeholder="Todas as contas…" compactWeb allowClear testID="previsoes-conta-filtro" />
                  </View>
                  <View>
                    <Text style={fieldLabel()}>Tipo</Text>
                    <View style={{ flexDirection: "row", gap: 6 }}>
                      {[null, 0, 1, 2].map((t) => (
                        <Pressable key={String(t)} onPress={() => setTipoFiltro(t)} style={[chipStyle(), tipoFiltro === t && chipSelStyle()]} testID={`previsoes-tipo-${t}`}>
                          <Text style={[chipTextStyle(), tipoFiltro === t && chipTextSelStyle()]}>{t === null ? "Todos" : TIPO_LABEL_PREV[t]}</Text>
                        </Pressable>
                      ))}
                    </View>
                  </View>
                  <View style={{ marginLeft: spacing.lg, paddingLeft: spacing.lg, borderLeftWidth: 1, borderLeftColor: colors.border }}>
                    <Text style={fieldLabel()}>Período</Text>
                    <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                      {(["todas", "atraso", "hoje", "mes"] as const).map((f) => (
                        <Pressable key={f} onPress={() => setFiltroData(f)} style={[chipStyle(), filtroData === f && chipSelStyle()]} testID={`previsoes-data-${f}`}>
                          <Text style={[chipTextStyle(), filtroData === f && chipTextSelStyle()]}>{f === "todas" ? "Todas" : f === "atraso" ? "Em Atraso" : f === "hoje" ? "Hoje" : "Mês"}</Text>
                        </Pressable>
                      ))}
                      {filtroData === "mes" ? (
                        <View style={{ flexDirection: "row", alignItems: "center", gap: 2, marginLeft: 4, paddingLeft: spacing.sm, borderLeftWidth: 1, borderLeftColor: colors.border }}>
                          <Pressable onPress={() => setPrevMesRef((r) => shiftMonth(r, -1))} hitSlop={8} testID="previsoes-mes-anterior"><Ionicons name="chevron-back-circle-outline" size={22} color={colors.brandPrimary} /></Pressable>
                          <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface, minWidth: 90, textAlign: "center" }}>{monthLabel(prevMesRef)}</Text>
                          <Pressable onPress={() => setPrevMesRef((r) => shiftMonth(r, 1))} hitSlop={8} testID="previsoes-mes-proximo"><Ionicons name="chevron-forward-circle-outline" size={22} color={colors.brandPrimary} /></Pressable>
                        </View>
                      ) : null}
                    </View>
                  </View>
                  <View style={{ flex: 1, minWidth: 160 }}>
                    <Text style={fieldLabel()}>Busca</Text>
                    <View style={{ position: "relative" as const, justifyContent: "center" as const }}>
                      <TextInput value={busca} onChangeText={setBusca} onSubmitEditing={buscarPrevisoes} style={[inputStyle(), { paddingRight: 34 }]} placeholder="Favorecido ou valor…" testID="previsoes-busca" />
                      <Pressable onPress={buscarPrevisoes} disabled={prevBuscando} hitSlop={8} style={{ position: "absolute" as const, right: 8 }} testID="previsoes-buscar-btn">
                        {prevBuscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : <Ionicons name="search-outline" size={18} color={colors.brandPrimary} />}
                      </Pressable>
                    </View>
                  </View>
                </View>
              </View>

              {totaisGrafico && (totaisGrafico.receber > 0 || totaisGrafico.pagar > 0) ? (
                <View style={WEB_FILTER_CARD}>
                  <Text style={[labelStyle(), { marginBottom: 2 }]}>Receita x Despesa</Text>
                  <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm }}>
                    Soma de TODAS as Previsões de Receber x Pagar —
                    {prevContaFiltro ? ` conta ${contas.find((c) => c.value === prevContaFiltro)?.label || prevContaFiltro}` : " todas as contas"},
                    {filtroData === "todas" ? " qualquer data" : filtroData === "atraso" ? " só as em atraso" : filtroData === "hoje" ? " só as de hoje" : ` só ${monthLabel(prevMesRef)}`}
                    {busca.trim() ? `, busca "${busca.trim()}"` : ""}. Ignora o filtro de Tipo da lista abaixo (senão um lado zeraria ao filtrar só por Pagar ou só por Receber).
                  </Text>
                  <ReceitaDespesaBars receber={totaisGrafico.receber} pagar={totaisGrafico.pagar} />
                </View>
              ) : null}

              <View style={WEB_FILTER_CARD}>
                {prevItens.length > 0 ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.sm, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Text style={[labelStyle(), { flex: 1 }]}>Previsões ({prevItens.length})</Text>
                    <Text style={{ fontSize: 13, color: colors.muted }}>Total da lista: <Text style={{ fontWeight: "700", color: colors.onSurface }}>{formatBRL(valorTotalLista)}</Text></Text>
                    <Text style={{ fontSize: 13, color: colors.muted }}>{qtdSelecionados} selecionada(s)</Text>
                    {qtdSelecionados > 0 ? (
                      <Text style={{ fontSize: 15, fontWeight: "700", color: colors.brandPrimary }}>Selecionado: {formatBRL(valorSelecionado)}</Text>
                    ) : null}
                    {can("PREVISOES.EFETIVAR") ? (
                      <Pressable onPress={abrirTransferenciaModal} disabled={efetivando || qtdSelecionados === 0} style={[primaryBtnStyle(), { paddingVertical: 6 }, qtdSelecionados === 0 && { opacity: 0.5 }]} testID="previsoes-efetivar-btn">
                        {efetivando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <><Ionicons name="checkmark-done-outline" size={16} color={colors.onBrandPrimary} /><Text style={primaryBtnLabelStyle()}>Efetivar Selecionadas</Text></>}
                      </Pressable>
                    ) : null}
                  </View>
                ) : (
                  <Text style={labelStyle()}>Previsões (0)</Text>
                )}
                {situacaoVencItens.length > 0 ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.sm, paddingBottom: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Ionicons name="lock-closed" size={16} color={colors.muted} />
                    <Text style={{ fontSize: 13, color: colors.muted, flex: 1 }}>{situacaoVencItens.length} vencimento(s) bloqueado(s) selecionado(s) pra alterar Situação</Text>
                    <Pressable onPress={abrirSituacaoVencModal} style={secondaryBtnStyle()} testID="previsoes-situacao-venc-btn">
                      <Ionicons name="create-outline" size={16} color={colors.brandPrimary} /><Text style={secondaryBtnLabelStyle()}>Alterar Situação</Text>
                    </Pressable>
                  </View>
                ) : null}
                {prevItens.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhuma previsão encontrada.</Text>
                ) : (
                  prevItens.map((it) => {
                    const sel = !!selecionados[it.codigo];
                    const selSituacao = !!situacaoVencSelecionados[it.codigo];
                    return (
                      <Pressable key={it.codigo} style={[itemRowStyle(), it.bloqueada && { opacity: selSituacao ? 1 : 0.55 }]} testID={`previsoes-item-${it.codigo}`}>
                        <Pressable onPress={() => toggleItem(it)} hitSlop={8} testID={`previsoes-item-check-${it.codigo}`}>
                          <Ionicons
                            name={it.bloqueada ? (selSituacao ? "lock-open" : "lock-closed") : sel ? "checkbox" : "square-outline"}
                            size={it.bloqueada ? 18 : 22}
                            color={it.bloqueada ? (selSituacao ? colors.brandPrimary : colors.muted) : sel ? colors.brandPrimary : colors.muted}
                          />
                        </Pressable>
                        <Pressable onPress={() => abrirEdicaoPrevisao(it)} style={{ flex: 1, flexDirection: "row", alignItems: "center", marginLeft: spacing.sm }}>
                          <View style={{ flex: 1 }}>
                            <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{it.favorecido_nome || "(sem favorecido)"}</Text>
                            <Text style={{ fontSize: 12, color: colors.muted }}>
                              {formatDateBR(it.data_vencimento)} · {it.conta_descricao}
                              {it.tipo === 2 ? ` → ${it.conta_destino_descricao || ""}` : it.classe_descricao ? ` · ${it.classe_descricao}` : ""}
                              {it.memorando ? ` · ${it.memorando}` : ""}
                              {it.flag_transf_caixa === "R" && it.situacao_duplicata_atual ? ` · situação: ${SITUACAO_VENCIMENTO_OPTIONS[it.situacao_duplicata_atual]?.label}` : it.bloqueada ? " · bloqueada" : ""}
                              {selSituacao ? " · selecionada p/ alterar situação" : ""}
                            </Text>
                          </View>
                          <View style={[flagBadgeStyle(), { backgroundColor: tipoColor(it.tipo) + "22" }]}>
                            <Text style={[flagBadgeTextStyle(), { color: tipoColor(it.tipo) }]}>{TIPO_LABEL_PREV[it.tipo]}</Text>
                          </View>
                          <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface, marginLeft: spacing.md, minWidth: 90, textAlign: "right" }}>{formatBRL(it.valor)}</Text>
                        </Pressable>
                      </Pressable>
                    );
                  })
                )}
              </View>
            </View>
          ) : (
            <View style={{ gap: spacing.md }}>
              {relBuscando ? <ActivityIndicator color={colors.brandPrimary} /> : null}

              <View style={WEB_FILTER_CARD}>
                <Text style={fieldLabel()}>Conta</Text>
                <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.xs }}>
                  Filtra o relatório "Receitas x Despesas por Mês" abaixo. Saldos e Duplicatas não são afetados — Saldos mostra todas as contas por natureza; Duplicatas não tem conta vinculada.
                </Text>
                <View style={{ width: 260 }}>
                  <SelectField value={relContaFiltro} onChange={(v) => setRelContaFiltro(v as number | null)} options={contas} placeholder="Todas as contas…" compactWeb allowClear testID="painel-financeiro-rel-conta-filtro" />
                </View>
              </View>

              <View style={WEB_FILTER_CARD}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
                  <Text style={labelStyle()}>Saldos Atuais das Contas</Text>
                  {contasSaldo.length > 0 ? (
                    <Text style={{ fontSize: 13, fontWeight: "700", color: colors.onSurface }}>Total: {formatBRL(contasSaldo.reduce((s, c) => s + c.saldo_atual, 0))}</Text>
                  ) : null}
                </View>
                {contasSaldo.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma conta cadastrada.</Text>
                ) : contasSaldo.map((c) => (
                  <View key={c.codigo} style={itemRowStyle()}>
                    <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{c.descricao}</Text>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: c.saldo_atual >= 0 ? colors.success : colors.error }}>{formatBRL(c.saldo_atual)}</Text>
                  </View>
                ))}
              </View>

              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: 2 }]}>Movimentação de Contas</Text>
                <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm }}>Mesmo período/conta da aba Painel de Movimentações ({PERIODOS.find((p) => p.value === periodo)?.label}).</Text>
                {movimentacaoPorConta.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma movimentação no período.</Text>
                ) : movimentacaoPorConta.map((g) => (
                  <View key={g.descricao} style={itemRowStyle()}>
                    <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{g.descricao}</Text>
                    <Text style={{ fontSize: 11, color: colors.muted, marginRight: spacing.sm }}>{g.qtd} lanç.</Text>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: g.total >= 0 ? colors.success : colors.error }}>{formatBRL(g.total)}</Text>
                  </View>
                ))}
              </View>

              <View style={WEB_FILTER_CARD}>
                <Text style={labelStyle()}>Receitas x Despesas por Mês</Text>
                <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm }}>
                  {relContaFiltro ? `Conta ${contas.find((c) => c.value === relContaFiltro)?.label || relContaFiltro}` : "Todas as contas"}.
                </Text>
                {relReceitasDespesas.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13 }}>Sem dados suficientes.</Text>
                ) : relReceitasDespesas.map((l) => (
                  <View key={l.mes} style={itemRowStyle()}>
                    <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{monthLabel(l.mes.slice(0, 7))}</Text>
                    <Text style={{ fontSize: 12, color: colors.success, marginRight: spacing.sm }}>+{formatBRL(l.receitas)}</Text>
                    <Text style={{ fontSize: 12, color: colors.error, marginRight: spacing.sm }}>-{formatBRL(l.despesas)}</Text>
                    <Text style={{ fontSize: 13, fontWeight: "700", color: l.saldo >= 0 ? colors.success : colors.error }}>{formatBRL(l.saldo)}</Text>
                  </View>
                ))}
              </View>

              {podeVerContasPagar ? (
                <View style={WEB_FILTER_CARD}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, flexWrap: "wrap" }}>
                    <Text style={labelStyle()}>Duplicatas à Pagar em Aberto ({relDuplicatasPagar.length})</Text>
                    {relDuplicatasPagar.length > 0 ? (
                      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.error }}>Total: {formatBRL(relDuplicatasPagar.reduce((s, d) => s + d.valor_em_aberto, 0))}</Text>
                    ) : null}
                    <Pressable onPress={() => navegarParaContasPagar("A")} testID="painel-financeiro-rel-ir-contas-pagar">
                      <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Abrir Contas a Pagar →</Text>
                    </Pressable>
                  </View>
                  {relDuplicatasPagar.length === 0 ? (
                    <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma duplicata em aberto.</Text>
                  ) : relDuplicatasPagar.slice(0, 30).map((d) => (
                    <Pressable key={d.codigo} onPress={() => navegarParaContasPagar("A")} style={itemRowStyle()}>
                      <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{d.fornecedor_nome || "(sem fornecedor)"}</Text>
                      <Text style={{ fontSize: 11, color: d.vencido ? colors.error : colors.muted, marginRight: spacing.sm }}>{d.proximo_vencimento ? formatDateBR(d.proximo_vencimento) : "-"}{d.vencido ? " · vencido" : ""}</Text>
                      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.error }}>{formatBRL(d.valor_em_aberto)}</Text>
                    </Pressable>
                  ))}
                  {relDuplicatasPagar.length > 30 ? <Text style={{ fontSize: 11, color: colors.muted, marginTop: spacing.xs }}>+{relDuplicatasPagar.length - 30} outra(s) — abra Contas a Pagar pra ver todas.</Text> : null}
                </View>
              ) : null}

              {podeVerContasReceber ? (
                <View style={WEB_FILTER_CARD}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, flexWrap: "wrap" }}>
                    <Text style={labelStyle()}>Duplicatas à Receber em Aberto ({relDuplicatasReceber.length})</Text>
                    {relDuplicatasReceber.length > 0 ? (
                      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.success }}>Total: {formatBRL(relDuplicatasReceber.reduce((s, d) => s + d.valor_em_aberto, 0))}</Text>
                    ) : null}
                    <Pressable onPress={() => navegarParaContasReceber("A")} testID="painel-financeiro-rel-ir-contas-receber">
                      <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Abrir Contas a Receber →</Text>
                    </Pressable>
                  </View>
                  {relDuplicatasReceber.length === 0 ? (
                    <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma duplicata em aberto.</Text>
                  ) : relDuplicatasReceber.slice(0, 30).map((d) => (
                    <Pressable key={d.codigo} onPress={() => navegarParaContasReceber("A")} style={itemRowStyle()}>
                      <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>{d.cliente_nome || "(sem cliente)"}</Text>
                      <Text style={{ fontSize: 11, color: d.vencido ? colors.error : colors.muted, marginRight: spacing.sm }}>{d.proximo_vencimento ? formatDateBR(d.proximo_vencimento) : "-"}{d.vencido ? " · vencido" : ""}</Text>
                      <Text style={{ fontSize: 13, fontWeight: "700", color: colors.success }}>{formatBRL(d.valor_em_aberto)}</Text>
                    </Pressable>
                  ))}
                  {relDuplicatasReceber.length > 30 ? <Text style={{ fontSize: 11, color: colors.muted, marginTop: spacing.xs }}>+{relDuplicatasReceber.length - 30} outra(s) — abra Contas a Receber pra ver todas.</Text> : null}
                </View>
              ) : null}

              {podeVerContasReceber ? (
                <View style={WEB_FILTER_CARD}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, flexWrap: "wrap" }}>
                    <Text style={labelStyle()}>Duplicatas Recebidas</Text>
                    <View style={{ flexDirection: "row", gap: spacing.sm }}>
                      <Pressable onPress={imprimirDuplicatasRecebidas} disabled={duRecItens.length === 0} testID="painel-financeiro-durec-imprimir">
                        <Text style={{ fontSize: 12, color: duRecItens.length === 0 ? colors.muted : colors.brandPrimary, fontWeight: "600" }}>Imprimir</Text>
                      </Pressable>
                      <Pressable onPress={exportarDuplicatasRecebidas} disabled={duRecItens.length === 0} testID="painel-financeiro-durec-exportar">
                        <Text style={{ fontSize: 12, color: duRecItens.length === 0 ? colors.muted : colors.brandPrimary, fontWeight: "600" }}>Gerar Planilha</Text>
                      </Pressable>
                    </View>
                  </View>
                  <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm }}>
                    Duplicatas já pagas no período — por vencimento ou data de pagamento, à escolha. Filtro por Cliente é
                    pelo código (busca por nome fica pra uma próxima rodada); Banco e Vendedor também ficam de fora por
                    ora.
                  </Text>
                  <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.sm }}>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>De</Text>
                      <WebDateField
                        value={duRecDataIni}
                        onChange={(v) => { setDuRecDataIni(v || null); if (v) setDuRecDataFim(v); }}
                        testID="painel-financeiro-durec-data-ini"
                      />
                    </View>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>Até</Text>
                      <WebDateField value={duRecDataFim} onChange={(v) => setDuRecDataFim(v || null)} testID="painel-financeiro-durec-data-fim" />
                    </View>
                    <View style={{ width: 170 }}>
                      <Text style={fieldLabel()}>Base do Período</Text>
                      <SelectField
                        value={duRecBase}
                        onChange={(v) => setDuRecBase((v as "vencimento" | "pagamento") || "vencimento")}
                        options={[{ value: "vencimento", label: "Vencimento" }, { value: "pagamento", label: "Data de Pagamento" }]}
                        compactWeb testID="painel-financeiro-durec-base"
                      />
                    </View>
                    <View style={{ width: 220 }}>
                      <Text style={fieldLabel()}>Cliente</Text>
                      <Pressable
                        onPress={() => { setDuRecClienteSearchOpen(true); setDuRecClienteTerm(""); }}
                        style={[inputStyle(), { justifyContent: "center", flexDirection: "row", alignItems: "center" }]}
                        testID="painel-financeiro-durec-cliente-abrir"
                      >
                        <Text style={{ flex: 1, color: duRecClienteNome ? colors.onSurface : colors.muted, fontSize: 14 }} numberOfLines={1}>
                          {duRecClienteNome || "Todos os clientes…"}
                        </Text>
                        {duRecClienteNome ? (
                          <Pressable onPress={() => { setDuRecClienteCod(null); setDuRecClienteNome(""); }} hitSlop={8}>
                            <Ionicons name="close-circle" size={16} color={colors.muted} />
                          </Pressable>
                        ) : (
                          <Ionicons name="search" size={16} color={colors.muted} />
                        )}
                      </Pressable>
                    </View>
                    <View style={{ width: 200 }}>
                      <Text style={fieldLabel()}>Forma de Pagamento</Text>
                      <SelectField value={duRecFormaPag} onChange={(v) => setDuRecFormaPag(v as string | null)} options={duRecFormaPagOpts} placeholder="Todas…" compactWeb allowClear testID="painel-financeiro-durec-formapag" />
                    </View>
                    <View style={{ width: 200 }}>
                      <Text style={fieldLabel()}>Banco</Text>
                      <SelectField value={duRecBancoCedente} onChange={(v) => setDuRecBancoCedente(v as number | null)} options={duRecBancoOpts} placeholder="Todos…" compactWeb allowClear testID="painel-financeiro-durec-banco" />
                    </View>
                    <View style={{ width: 200 }}>
                      <Text style={fieldLabel()}>Vendedor</Text>
                      <SelectField value={duRecVendedor} onChange={(v) => setDuRecVendedor(v as number | null)} options={duRecVendedorOpts} placeholder="Todos…" compactWeb allowClear testID="painel-financeiro-durec-vendedor" />
                    </View>
                  </View>
                  <View style={{ flexDirection: "row", gap: spacing.md, marginBottom: spacing.sm }}>
                    <CheckboxToggle checked={duRecComandas} onToggle={() => setDuRecComandas((v) => !v)} label="Comandas" testID="painel-financeiro-durec-comandas" />
                    <CheckboxToggle checked={duRecNotasFiscais} onToggle={() => setDuRecNotasFiscais((v) => !v)} label="NF's" testID="painel-financeiro-durec-nfs" />
                  </View>
                  <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm, marginTop: -spacing.xs }}>
                    Vendedor só encontra duplicatas originadas de Comanda vinculada a uma Nota Fiscal — uma duplicata
                    lançada direto por NF não tem vendedor rastreado nesse relatório (limitação do dado de origem, não
                    um filtro incompleto).
                  </Text>

                  {duRecBuscando ? <ActivityIndicator color={colors.brandPrimary} /> : duRecItens.length === 0 ? (
                    <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma duplicata recebida no período.</Text>
                  ) : (
                    <>
                      {duRecPorDia.map((g) => (
                        <View key={g.data}>
                          <View style={{ flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, marginTop: spacing.sm }}>
                            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurface }}>Total do Dia ({g.data === "-" ? "-" : formatDateBR(g.data)})</Text>
                            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.success }}>{formatBRL(g.total)}</Text>
                          </View>
                          {g.itens.map((it, i) => (
                            <View key={`${it.duplicata}-${it.desmembramento}-${i}`} style={itemRowStyle()}>
                              <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>
                                {it.duplicata}/{it.desmembramento} · {it.cliente_nome}
                              </Text>
                              <Text style={{ fontSize: 11, color: colors.muted, marginRight: spacing.sm }}>{it.forma_pagamento || "SEM FORMA CADASTRADA"}</Text>
                              <Text style={{ fontSize: 13, fontWeight: "700", color: colors.success }}>{formatBRL(it.valor_pag)}</Text>
                            </View>
                          ))}
                        </View>
                      ))}
                      <View style={{ marginTop: spacing.md, gap: 2 }}>
                        <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurface }}>Resumo por Forma de Pagamento</Text>
                        {duRecResumoFp.map((r) => (
                          <View key={r.forma_pagamento} style={{ flexDirection: "row", justifyContent: "space-between" }}>
                            <Text style={{ fontSize: 12, color: colors.muted }}>{r.forma_pagamento}</Text>
                            <Text style={{ fontSize: 12, color: colors.onSurface }}>{formatBRL(r.valor)}</Text>
                          </View>
                        ))}
                      </View>
                      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.xs }}>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>TOTAL GERAL</Text>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.success }}>{formatBRL(duRecTotal)}</Text>
                      </View>
                    </>
                  )}
                </View>
              ) : null}

              {podeVerContasPagar ? (
                <View style={WEB_FILTER_CARD}>
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, flexWrap: "wrap" }}>
                    <Text style={labelStyle()}>Duplicatas Pagas</Text>
                    <View style={{ flexDirection: "row", gap: spacing.sm }}>
                      <Pressable onPress={imprimirDuplicatasPagas} disabled={duPagItens.length === 0} testID="painel-financeiro-dupag-imprimir">
                        <Text style={{ fontSize: 12, color: duPagItens.length === 0 ? colors.muted : colors.brandPrimary, fontWeight: "600" }}>Imprimir</Text>
                      </Pressable>
                      <Pressable onPress={exportarDuplicatasPagas} disabled={duPagItens.length === 0} testID="painel-financeiro-dupag-exportar">
                        <Text style={{ fontSize: 12, color: duPagItens.length === 0 ? colors.muted : colors.brandPrimary, fontWeight: "600" }}>Gerar Planilha</Text>
                      </Pressable>
                    </View>
                  </View>
                  <Text style={{ fontSize: 11, color: colors.muted, marginBottom: spacing.sm }}>
                    Duplicatas já pagas no período — por vencimento ou data de pagamento, à escolha, com filtro
                    opcional por fornecedor.
                  </Text>
                  <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.sm }}>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>De</Text>
                      <WebDateField
                        value={duPagDataIni}
                        onChange={(v) => { setDuPagDataIni(v || null); if (v) setDuPagDataFim(v); }}
                        testID="painel-financeiro-dupag-data-ini"
                      />
                    </View>
                    <View style={{ width: 130 }}>
                      <Text style={fieldLabel()}>Até</Text>
                      <WebDateField value={duPagDataFim} onChange={(v) => setDuPagDataFim(v || null)} testID="painel-financeiro-dupag-data-fim" />
                    </View>
                    <View style={{ width: 170 }}>
                      <Text style={fieldLabel()}>Base do Período</Text>
                      <SelectField
                        value={duPagBase}
                        onChange={(v) => setDuPagBase((v as "vencimento" | "pagamento") || "vencimento")}
                        options={[{ value: "vencimento", label: "Vencimento" }, { value: "pagamento", label: "Data de Pagamento" }]}
                        compactWeb testID="painel-financeiro-dupag-base"
                      />
                    </View>
                    <View style={{ width: 220 }}>
                      <Text style={fieldLabel()}>Fornecedor</Text>
                      <Pressable
                        onPress={() => { setDuPagFornSearchOpen(true); setDuPagFornTerm(""); }}
                        style={[inputStyle(), { justifyContent: "center", flexDirection: "row", alignItems: "center" }]}
                        testID="painel-financeiro-dupag-fornecedor-abrir"
                      >
                        <Text style={{ flex: 1, color: duPagFornNome ? colors.onSurface : colors.muted, fontSize: 14 }} numberOfLines={1}>
                          {duPagFornNome || "Todos os fornecedores…"}
                        </Text>
                        {duPagFornNome ? (
                          <Pressable onPress={() => { setDuPagFornCod(null); setDuPagFornNome(""); }} hitSlop={8}>
                            <Ionicons name="close-circle" size={16} color={colors.muted} />
                          </Pressable>
                        ) : (
                          <Ionicons name="search" size={16} color={colors.muted} />
                        )}
                      </Pressable>
                    </View>
                  </View>

                  {duPagBuscando ? <ActivityIndicator color={colors.brandPrimary} /> : duPagItens.length === 0 ? (
                    <Text style={{ color: colors.muted, fontSize: 13 }}>Nenhuma duplicata paga no período.</Text>
                  ) : (
                    <>
                      {duPagPorDia.map((g) => (
                        <View key={g.data}>
                          <View style={{ flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm, marginTop: spacing.sm }}>
                            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.onSurface }}>Total do Dia ({g.data === "-" ? "-" : formatDateBR(g.data)})</Text>
                            <Text style={{ fontSize: 12, fontWeight: "700", color: colors.error }}>{formatBRL(g.total)}</Text>
                          </View>
                          {g.itens.map((it, i) => (
                            <View key={`${it.duplicata}-${it.desmembramento}-${i}`} style={itemRowStyle()}>
                              <Text style={{ flex: 1, fontSize: 13, color: colors.onSurface }}>
                                {it.duplicata}/{it.desmembramento} · {it.fornecedor_nome}
                              </Text>
                              <Text style={{ fontSize: 13, fontWeight: "700", color: colors.error }}>{formatBRL(it.valor_pag)}</Text>
                            </View>
                          ))}
                        </View>
                      ))}
                      <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.xs }}>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface }}>TOTAL GERAL</Text>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.error }}>{formatBRL(duPagTotal)}</Text>
                      </View>
                    </>
                  )}
                </View>
              ) : null}

              <Text style={{ fontSize: 11, color: colors.muted, textAlign: "center" }}>
                6 de ~20 relatórios do Fluxo de Caixa do legado — os demais (Cheques não compensados, Lançamentos por Classe/Centro de Custo/Documento, Movimentação por Favorecidos, Receitas x Despesas por Classe/Favorecido, etc.) ficam pra próxima rodada.
              </Text>
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Painel de Movimentações" itens={AJUDA_ITENS_PAINEL} />
      <AjudaPedidoModal visible={prevAjudaOpen} onClose={() => setPrevAjudaOpen(false)} titulo="Previsões" itens={AJUDA_ITENS_PREV} />

      <ClientSearchModal
        visible={duRecClienteSearchOpen} onClose={() => setDuRecClienteSearchOpen(false)}
        term={duRecClienteTerm} setTerm={setDuRecClienteTerm} loading={duRecClienteLoading} results={duRecClienteResults}
        onPick={(c: ClienteRow) => {
          setDuRecClienteCod(c.codigo); setDuRecClienteNome(c.nome || String(c.codigo));
          setDuRecClienteSearchOpen(false);
        }}
        onCreate={() => setDuRecClienteSearchOpen(false)}
      />

      <FornecedorSearchModal
        visible={duPagFornSearchOpen} onClose={() => setDuPagFornSearchOpen(false)}
        term={duPagFornTerm} setTerm={setDuPagFornTerm} loading={duPagFornLoading} results={duPagFornResults}
        onPick={(f: FornecedorRow) => {
          setDuPagFornCod(Number(f.codigo_int)); setDuPagFornNome(f.nome);
          setDuPagFornSearchOpen(false);
        }}
      />

      <AppModal visible={lancarOpen} transparent animationType="fade" onRequestClose={() => setLancarOpen(false)}>
        <View style={modalBgStyle()}>
          <View style={modalCardStyle()}>
            <View style={modalHeaderStyle()}>
              <Text style={modalTitleStyle()}>Lançamento — {TIPO_LABEL_LONGO[fTipo]}</Text>
              <Pressable onPress={() => setLancarOpen(false)} hitSlop={8}><Ionicons name="close" size={20} color={colors.onSurface} /></Pressable>
            </View>
            <ScrollView style={{ maxHeight: 480 }}>
              <View style={rowFieldsStyle()}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>{fTipo === 2 ? "Conta de Origem" : "Conta"}</Text>
                  <SelectField value={fConta} onChange={(v) => setFConta(v as number)} options={contas} compactWeb testID="painel-financeiro-form-conta" />
                </View>
                {fTipo === 2 ? (
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Conta de Destino</Text>
                    <SelectField value={fContaDestino} onChange={(v) => setFContaDestino(v as number)} options={contas.filter((c) => c.value !== fConta)} compactWeb testID="painel-financeiro-form-conta-destino" />
                  </View>
                ) : (
                  <>
                    <View style={{ flex: 1 }}>
                      <Text style={fieldLabel()}>Classe</Text>
                      <SelectField value={fClasse} onChange={(v) => { setFClasse(v as number | null); setFSubClasse(null); }} options={classeOptionsPara(fTipo === 1 ? "R" : "D")} placeholder="Selecione…" compactWeb allowClear testID="painel-financeiro-form-classe" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={fieldLabel()}>Sub-Classe</Text>
                      <SelectField value={fSubClasse} onChange={(v) => setFSubClasse(v as number | null)} options={subClasseOptionsPara(fClasse)} placeholder="Selecione…" compactWeb allowClear testID="painel-financeiro-form-sub-classe" />
                    </View>
                  </>
                )}
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Favorecido</Text>
                  <TextInput value={fFavorecido} onChangeText={setFFavorecido} style={inputStyle()} testID="painel-financeiro-form-favorecido" />
                </View>
                <View style={{ width: 130 }}>
                  <Text style={fieldLabel()}>Documento</Text>
                  <TextInput value={fDocumento} onChangeText={setFDocumento} style={inputStyle()} testID="painel-financeiro-form-documento" />
                </View>
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ width: 150 }}>
                  <Text style={fieldLabel()}>Data de Liquidação</Text>
                  <WebDateField value={fDataLiquidacao} onChange={setFDataLiquidacao} testID="painel-financeiro-form-data" />
                </View>
                <View style={{ width: 130 }}>
                  <Text style={fieldLabel()}>Valor</Text>
                  <TextInput value={fValor} onChangeText={setFValor} keyboardType="numeric" style={inputStyle()} testID="painel-financeiro-form-valor" />
                </View>
              </View>
              <View style={{ marginTop: spacing.xs }}>
                <Text style={fieldLabel()}>Memorando</Text>
                <TextInput value={fMemorando} onChangeText={setFMemorando} style={[inputStyle(), { minHeight: 50 }]} multiline testID="painel-financeiro-form-memorando" />
              </View>

              <View style={{ marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs }}>
                  <Text style={labelStyle()}>Centro de Custo (rateio opcional)</Text>
                  <Pressable onPress={adicionarLinhaRateio} style={miniBtnStyle()} testID="painel-financeiro-form-rateio-add">
                    <Text style={miniBtnLabelStyle()}>+ Linha</Text>
                  </Pressable>
                </View>
                {fRateio.map((r, idx) => (
                  <View key={idx} style={{ flexDirection: "row", gap: 6, alignItems: "center", marginBottom: 6 }}>
                    <TextInput
                      value={r.centro_custo != null ? String(r.centro_custo) : ""}
                      onChangeText={(v) => atualizarLinhaRateio(idx, { centro_custo: v ? parseInt(v, 10) : null })}
                      keyboardType="numeric" placeholder="Centro Custo" style={[inputStyle(), { width: 100 }]} testID={`painel-financeiro-form-rateio-cc-${idx}`}
                    />
                    <TextInput
                      value={String(r.valor)} onChangeText={(v) => atualizarLinhaRateio(idx, { valor: Number(v.replace(",", ".")) || 0 })}
                      keyboardType="numeric" placeholder="Valor" style={[inputStyle(), { width: 100 }]} testID={`painel-financeiro-form-rateio-valor-${idx}`}
                    />
                    <TextInput
                      value={r.memorando} onChangeText={(v) => atualizarLinhaRateio(idx, { memorando: v })}
                      placeholder="Memorando" style={[inputStyle(), { flex: 1 }]} testID={`painel-financeiro-form-rateio-memo-${idx}`}
                    />
                    <Pressable onPress={() => removerLinhaRateio(idx)} hitSlop={8}><Ionicons name="trash-outline" size={18} color={colors.error} /></Pressable>
                  </View>
                ))}
                {fRateio.length > 0 ? (
                  <Text style={{ fontSize: 12, color: somaRateio === valorNum ? colors.success : colors.error, marginTop: 4 }}>
                    Soma do rateio: {formatBRL(somaRateio)} {somaRateio === valorNum ? "✓ bate com o valor" : `(precisa bater com ${formatBRL(valorNum)})`}
                  </Text>
                ) : null}
              </View>
            </ScrollView>
            <View style={{ flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md }}>
              <Pressable onPress={() => setLancarOpen(false)} style={secondaryBtnStyle()} testID="painel-financeiro-form-cancelar"><Text style={secondaryBtnLabelStyle()}>Cancelar</Text></Pressable>
              <Pressable onPress={salvarLancamento} disabled={salvando} style={primaryBtnStyle()} testID="painel-financeiro-form-gravar">
                {salvando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Gravar</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </AppModal>

      <AppModal visible={formOpen} transparent animationType="fade" onRequestClose={() => setFormOpen(false)}>
        <View style={modalBgStyle()}>
          <View style={modalCardStyle()}>
            <View style={modalHeaderStyle()}>
              <Text style={modalTitleStyle()}>{codigoEditando ? `Previsão #${codigoEditando}` : "Nova Previsão"}</Text>
              <Pressable onPress={() => setFormOpen(false)} hitSlop={8}><Ionicons name="close" size={20} color={colors.onSurface} /></Pressable>
            </View>
            <ScrollView style={{ maxHeight: 480 }}>
              <View style={{ flexDirection: "row", gap: 6, marginBottom: spacing.sm }}>
                {[0, 1, 2].map((t) => (
                  <Pressable key={t} onPress={() => setPrevFTipo(t)} style={[chipStyle(), prevFTipo === t && chipSelStyle()]} testID={`previsoes-form-tipo-${t}`}>
                    <Text style={[chipTextStyle(), prevFTipo === t && chipTextSelStyle()]}>{TIPO_LABEL_PREV[t]}</Text>
                  </Pressable>
                ))}
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>{prevFTipo === 2 ? "Conta de Origem" : "Conta"}</Text>
                  <SelectField value={prevFConta} onChange={(v) => setPrevFConta(v as number)} options={contas} compactWeb testID="previsoes-form-conta" />
                </View>
                {prevFTipo === 2 ? (
                  <View style={{ flex: 1 }}>
                    <Text style={fieldLabel()}>Conta de Destino</Text>
                    <SelectField value={prevFContaDestino} onChange={(v) => setPrevFContaDestino(v as number)} options={contas.filter((c) => c.value !== prevFConta)} compactWeb testID="previsoes-form-conta-destino" />
                  </View>
                ) : (
                  <>
                    <View style={{ flex: 1 }}>
                      <Text style={fieldLabel()}>Classe</Text>
                      <SelectField value={prevFClasse} onChange={(v) => { setPrevFClasse(v as number | null); setPrevFSubClasse(null); }} options={classeOptionsPara(prevFTipo === 1 ? "R" : "D")} placeholder="Selecione…" compactWeb allowClear testID="previsoes-form-classe" />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={fieldLabel()}>Sub-Classe</Text>
                      <SelectField value={prevFSubClasse} onChange={(v) => setPrevFSubClasse(v as number | null)} options={subClasseOptionsPara(prevFClasse)} placeholder="Selecione…" compactWeb allowClear testID="previsoes-form-sub-classe" />
                    </View>
                  </>
                )}
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Favorecido</Text>
                  <TextInput value={prevFFavorecido} onChangeText={setPrevFFavorecido} style={inputStyle()} testID="previsoes-form-favorecido" />
                </View>
                {prevFTipo !== 2 ? (
                  <View style={{ width: 130 }}>
                    <Text style={fieldLabel()}>Documento</Text>
                    <TextInput value={prevFDocumento} onChangeText={setPrevFDocumento} style={inputStyle()} testID="previsoes-form-documento" />
                  </View>
                ) : null}
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ width: 150 }}>
                  <Text style={fieldLabel()}>Data do Documento</Text>
                  <WebDateField value={prevFDataDocumento} onChange={setPrevFDataDocumento} testID="previsoes-form-data-documento" />
                </View>
                <View style={{ width: 150 }}>
                  <Text style={fieldLabel()}>Data de Vencimento</Text>
                  <WebDateField value={prevFDataVencimento} onChange={setPrevFDataVencimento} testID="previsoes-form-data-vencimento" />
                </View>
                <View style={{ width: 130 }}>
                  <Text style={fieldLabel()}>Valor</Text>
                  <TextInput value={prevFValor} onChangeText={setPrevFValor} keyboardType="numeric" style={inputStyle()} testID="previsoes-form-valor" />
                </View>
              </View>
              <View style={rowFieldsStyle()}>
                <View style={{ flex: 1 }}>
                  <Text style={fieldLabel()}>Frequência</Text>
                  <SelectField value={prevFFrequencia} onChange={(v) => setPrevFFrequencia(v as number)} options={FREQUENCIAS} compactWeb testID="previsoes-form-frequencia" />
                </View>
                {!codigoEditando ? (
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>Parcelas</Text>
                    <TextInput value={prevFParcelas} onChangeText={setPrevFParcelas} keyboardType="numeric" style={inputStyle()} testID="previsoes-form-parcelas" />
                  </View>
                ) : null}
              </View>
              <View style={{ marginTop: spacing.xs }}>
                <Text style={fieldLabel()}>Memorando</Text>
                <TextInput value={prevFMemorando} onChangeText={setPrevFMemorando} style={[inputStyle(), { minHeight: 50 }]} multiline testID="previsoes-form-memorando" />
              </View>

              <View style={{ marginTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.xs }}>
                  <Text style={labelStyle()}>Centro de Custo (rateio opcional)</Text>
                  <Pressable onPress={adicionarLinhaRateioPrev} style={miniBtnStyle()} testID="previsoes-form-rateio-add">
                    <Text style={miniBtnLabelStyle()}>+ Linha</Text>
                  </Pressable>
                </View>
                {prevFRateio.map((r, idx) => (
                  <View key={idx} style={{ flexDirection: "row", gap: 6, alignItems: "center", marginBottom: 6 }}>
                    <TextInput
                      value={r.centro_custo != null ? String(r.centro_custo) : ""}
                      onChangeText={(v) => atualizarLinhaRateioPrev(idx, { centro_custo: v ? parseInt(v, 10) : null })}
                      keyboardType="numeric" placeholder="Centro Custo" style={[inputStyle(), { width: 100 }]} testID={`previsoes-form-rateio-cc-${idx}`}
                    />
                    <TextInput
                      value={String(r.valor)} onChangeText={(v) => atualizarLinhaRateioPrev(idx, { valor: Number(v.replace(",", ".")) || 0 })}
                      keyboardType="numeric" placeholder="Valor" style={[inputStyle(), { width: 100 }]} testID={`previsoes-form-rateio-valor-${idx}`}
                    />
                    <TextInput
                      value={r.memorando} onChangeText={(v) => atualizarLinhaRateioPrev(idx, { memorando: v })}
                      placeholder="Memorando" style={[inputStyle(), { flex: 1 }]} testID={`previsoes-form-rateio-memo-${idx}`}
                    />
                    <Pressable onPress={() => removerLinhaRateioPrev(idx)} hitSlop={8}><Ionicons name="trash-outline" size={18} color={colors.error} /></Pressable>
                  </View>
                ))}
                {prevFRateio.length > 0 ? (
                  <Text style={{ fontSize: 12, color: prevSomaRateio === prevValorNum ? colors.success : colors.error, marginTop: 4 }}>
                    Soma do rateio: {formatBRL(prevSomaRateio)} {prevSomaRateio === prevValorNum ? "✓ bate com o valor" : `(precisa bater com ${formatBRL(prevValorNum)})`}
                  </Text>
                ) : null}
              </View>
            </ScrollView>
            <View style={{ flexDirection: "row", justifyContent: "space-between", marginTop: spacing.md }}>
              {codigoEditando && can("PREVISOES.EXCLUIR") ? (
                <Pressable onPress={() => excluirPrevisao()} disabled={excluindo} style={dangerBtnStyle()} testID="previsoes-form-excluir">
                  {excluindo ? <ActivityIndicator color={colors.error} size="small" /> : <Text style={dangerBtnLabelStyle()}>Excluir</Text>}
                </Pressable>
              ) : <View />}
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Pressable onPress={() => setFormOpen(false)} style={secondaryBtnStyle()} testID="previsoes-form-cancelar"><Text style={secondaryBtnLabelStyle()}>Cancelar</Text></Pressable>
                {can("PREVISOES.GRAVAR") ? (
                  <Pressable onPress={salvarPrevisao} disabled={prevSalvando} style={primaryBtnStyle()} testID="previsoes-form-gravar">
                    {prevSalvando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Gravar</Text>}
                  </Pressable>
                ) : null}
              </View>
            </View>
          </View>
        </View>
      </AppModal>

      <AuthorizationSlide
        visible={autorizarOpen} conn={conn} title="Autorização de Gerente"
        message="Excluir esta previsão exige autorização de um gerente/supervisor."
        onClose={() => setAutorizarOpen(false)}
        onAuthorized={() => excluirPrevisao("autorizado")}
      />

      {/* "Transferência Para Movimentação" (FrmManPrev.frm, Frame5) — pede
          Data de Liquidação + Conta (opcional, sobrescreve a conta própria
          de cada previsão) antes de efetivar de verdade no Fluxo de Caixa.
          Tier "confirmação pontual" (360-480px), ver CLAUDE.md > "Padrões
          de UI" > 1. */}
      <AppModal visible={transfModalOpen} transparent animationType="fade" onRequestClose={() => setTransfModalOpen(false)}>
        <View style={modalBgStyle()}>
          <View style={[modalCardStyle(), { maxWidth: 420 }]}>
            <View style={modalHeaderStyle()}>
              <Text style={modalTitleStyle()}>Transferência Para Movimentação</Text>
              <Pressable onPress={() => setTransfModalOpen(false)} hitSlop={8}><Ionicons name="close" size={20} color={colors.onSurface} /></Pressable>
            </View>
            <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.sm }}>
              {selecionadosItens.length} previsão(ões) selecionada(s). Isso lança de verdade no Fluxo de Caixa e muda o saldo da conta.
            </Text>
            <View style={{ flexDirection: "row", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.sm, marginBottom: spacing.sm }}>
              <Text style={{ fontSize: 12, color: colors.success, fontWeight: "600" as const }}>Créditos: {formatBRL(transfTotalCreditos)}</Text>
              <Text style={{ fontSize: 12, color: colors.error, fontWeight: "600" as const }}>Débitos: {formatBRL(transfTotalDebitos)}</Text>
            </View>
            <View style={rowFieldsStyle()}>
              <View style={{ flex: 1 }}>
                <Text style={fieldLabel()}>Data de Liquidação</Text>
                <WebDateField value={transfDataLiq} onChange={setTransfDataLiq} testID="previsoes-transf-data-liquidacao" />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={fieldLabel()}>Conta</Text>
                <SelectField value={transfConta} onChange={(v) => setTransfConta(v as number | null)} options={contas} placeholder="Usar a conta de cada previsão" compactWeb allowClear testID="previsoes-transf-conta" />
              </View>
            </View>
            <Text style={{ fontSize: 11, color: colors.muted, marginTop: 2, marginBottom: spacing.sm }}>
              Deixe "Conta" em branco pra lançar cada previsão na conta em que ela já está cadastrada — só preencha se quiser redirecionar todo mundo pra outra conta.
            </Text>
            <View style={{ flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm }}>
              <Pressable onPress={() => setTransfModalOpen(false)} style={secondaryBtnStyle()} testID="previsoes-transf-cancelar"><Text style={secondaryBtnLabelStyle()}>Cancelar</Text></Pressable>
              <Pressable onPress={confirmarTransferencia} disabled={efetivando} style={primaryBtnStyle()} testID="previsoes-transf-iniciar">
                {efetivando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Iniciar Transferência</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </AppModal>

      {/* Situação do Vencimento (Normal/Jurídico/Protestado) — acionado ao
          selecionar 1+ itens bloqueados por serem de Contas a Receber
          (`FrmManDur.frm`, combo Situação). Não muda o fato de a previsão
          continuar bloqueada aqui (a baixa em si sempre é feita em Contas
          a Receber) — só corrige o filtro usado nos alertas de atraso
          ("Contas a Receber em Atraso/Hoje" já só considera Normal).
          Pedido do usuário 2026-08-31 — mostrar nome/data/valor de cada
          vencimento sendo alterado, em lote. */}
      <AppModal visible={situacaoVencModalOpen} transparent animationType="fade" onRequestClose={() => setSituacaoVencModalOpen(false)}>
        <View style={modalBgStyle()}>
          <View style={[modalCardStyle(), { maxWidth: 460 }]}>
            <View style={modalHeaderStyle()}>
              <Text style={modalTitleStyle()}>Situação do Vencimento</Text>
              <Pressable onPress={() => setSituacaoVencModalOpen(false)} hitSlop={8}><Ionicons name="close" size={20} color={colors.onSurface} /></Pressable>
            </View>
            <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.sm }}>
              A baixa continua sendo feita pelo Contas a Receber. Aqui você só corrige a Situação do vencimento (usada pelos alertas de atraso do Painel Financeiro) — {situacaoVencItens.length} vencimento(s) selecionado(s):
            </Text>
            <ScrollView style={{ maxHeight: 180, marginBottom: spacing.sm }}>
              {situacaoVencItens.map((it) => (
                <View key={it.codigo} style={{ flexDirection: "row", alignItems: "center", paddingVertical: 4, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                  <View style={{ flex: 1 }}>
                    <Text style={{ fontSize: 12, color: colors.onSurface }} numberOfLines={1}>{it.favorecido_nome || "(sem favorecido)"}</Text>
                    <Text style={{ fontSize: 10, color: colors.muted }}>Atual: {SITUACAO_VENCIMENTO_OPTIONS[it.situacao_duplicata_atual ?? 0]?.label}</Text>
                  </View>
                  <Text style={{ fontSize: 11, color: colors.muted, marginHorizontal: spacing.xs }}>{formatDateBR(it.data_vencimento)}</Text>
                  <Text style={{ fontSize: 12, fontWeight: "600" as const, color: colors.onSurface, minWidth: 70, textAlign: "right" }}>{formatBRL(it.valor)}</Text>
                </View>
              ))}
            </ScrollView>
            <View>
              <Text style={fieldLabel()}>Nova Situação</Text>
              <SelectField value={situacaoVencValor} onChange={(v) => setSituacaoVencValor((v as number) ?? 0)} options={SITUACAO_VENCIMENTO_OPTIONS} compactWeb testID="previsoes-situacao-venc-select" />
            </View>
            <View style={{ flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md }}>
              <Pressable onPress={() => setSituacaoVencModalOpen(false)} style={secondaryBtnStyle()} testID="previsoes-situacao-venc-cancelar"><Text style={secondaryBtnLabelStyle()}>Cancelar</Text></Pressable>
              <Pressable onPress={confirmarSituacaoVencimento} disabled={situacaoVencSalvando} style={primaryBtnStyle()} testID="previsoes-situacao-venc-gravar">
                {situacaoVencSalvando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Gravar</Text>}
              </Pressable>
            </View>
          </View>
        </View>
      </AppModal>
    </SafeAreaView>
  );
}

// Réplica dos 2 checkboxes do cabeçalho do Painel legado (`FrmPnlCon.frm`
// `pCheck5`/`pCheck6`) — mutuamente exclusivos, controlados no chamador.
function CheckboxToggle({ checked, onToggle, label, testID }: { checked: boolean; onToggle: () => void; label: string; testID: string }) {
  return (
    <Pressable onPress={onToggle} style={{ flexDirection: "row", alignItems: "center", gap: 4 }} testID={testID}>
      <Ionicons name={checked ? "checkbox" : "square-outline"} size={18} color={checked ? colors.brandPrimary : colors.muted} />
      <Text style={{ fontSize: 12, color: colors.onSurface }}>{label}</Text>
    </Pressable>
  );
}

// Tooltip no hover do rótulo — achado do usuário 2026-08-31 ("tem que
// ser autoexplicativo em tooltip"): os 6 KPIs do Painel não tinham
// nenhuma explicação visível sem abrir o modal de Ajuda inteiro. Mesmo
// padrão de hover/zIndex já usado em IconButtonWithTooltip.tsx (ver
// aquele arquivo pro raciocínio completo do zIndex).
function KpiBlock({ label, valor, cor, destaque, tooltip }: { label: string; valor: number; cor?: string; destaque?: boolean; tooltip?: string }) {
  const [hover, setHover] = useState(false);
  return (
    <Pressable
      style={{ minWidth: 150, position: "relative", zIndex: hover ? 1000 : 1 }}
      onHoverIn={isWeb && tooltip ? () => setHover(true) : undefined}
      onHoverOut={isWeb && tooltip ? () => setHover(false) : undefined}
      disabled
    >
      <View style={{ flexDirection: "row", alignItems: "center", gap: 3 }}>
        <Text style={{ fontSize: 11, color: colors.muted, fontWeight: "500" }}>{label}</Text>
        {tooltip ? <Ionicons name="help-circle-outline" size={11} color={colors.muted} /> : null}
      </View>
      <Text style={{ fontSize: destaque ? 18 : 15, fontWeight: "700", color: cor || colors.onSurface }}>{formatBRL(valor)}</Text>
      {hover && tooltip ? (
        <View
          style={{ position: "absolute", top: "100%", left: 0, marginTop: 4, maxWidth: 220, backgroundColor: "#1a1a1a", borderRadius: 6, paddingHorizontal: 8, paddingVertical: 6, zIndex: 1000 }}
          pointerEvents="none"
        >
          <Text style={{ color: "#fff", fontSize: 11 }}>{tooltip}</Text>
        </View>
      ) : null}
    </Pressable>
  );
}

// Gráfico de saldo — "recurso extra" do Carlos, sem precedente no legado
// (FrmPnlCon.frm não tem gráfico). Só saldo REALIZADO (nunca projeção) —
// ver AJUDA_ITENS_PAINEL acima e PENDENCIAS.md pro raciocínio completo.
// SVG intrínseco (build web, tela já é web-only) — mesmo padrão já usado
// em ChecklistVeiculoDiagrama.tsx, sem lib nova.
function SaldoChart({ pontos, saldoInicial }: { pontos: PontoSaldo[]; saldoInicial: number }) {
  if (pontos.length === 0) {
    return <Text style={{ color: colors.muted, fontSize: 12 }}>Sem movimentação no período pra plotar no gráfico.</Text>;
  }
  const W = 640, H = 90, PAD = 8;
  const valores = [saldoInicial, ...pontos.map((p) => p.saldo)];
  const min = Math.min(...valores);
  const max = Math.max(...valores);
  const range = max - min || 1;
  const passo = pontos.length > 1 ? (W - PAD * 2) / (pontos.length - 1) : 0;
  const y = (v: number) => H - PAD - ((v - min) / range) * (H - PAD * 2);
  const pontosXY = pontos.map((p, i) => ({ x: PAD + i * passo, y: y(p.saldo) }));
  const linePath = pontosXY.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${pontosXY[pontosXY.length - 1].x.toFixed(1)} ${H - PAD} L ${pontosXY[0].x.toFixed(1)} ${H - PAD} Z`;
  const ultimoSaldo = pontos[pontos.length - 1].saldo;
  const cor = ultimoSaldo >= saldoInicial ? colors.success : colors.error;

  return (
    <View>
      <View style={{ flexDirection: "row", justifyContent: "space-between", marginBottom: 4 }}>
        <Text style={{ fontSize: 11, color: colors.muted }}>{formatDateBR(pontos[0].data)}</Text>
        <Text style={{ fontSize: 11, color: colors.muted }}>{formatDateBR(pontos[pontos.length - 1].data)}</Text>
      </View>
      {/* eslint-disable react/no-unknown-property -- SVG intrínseco (build web), ver ChecklistVeiculoDiagrama.tsx pro mesmo padrão */}
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" data-testid="painel-financeiro-saldo-svg">
        <path d={areaPath} fill={cor} opacity={0.12} stroke="none" />
        <path d={linePath} fill="none" stroke={cor} strokeWidth={2} />
        {pontosXY.map((p, i) => (
          <g key={i}>
            {/* área de hover maior que o ponto visível — só ela carrega o
                tooltip nativo (data + valor), achado do usuário 2026-08-31:
                "o gráfico não traz evolução patrimonial, tem que trazer
                valores x data" — cada ponto precisa ser identificável. */}
            <circle cx={p.x} cy={p.y} r={7} fill="transparent" style={{ cursor: "pointer" }}>
              <title>{`${formatDateBR(pontos[i].data)}: ${formatBRL(pontos[i].saldo)}`}</title>
            </circle>
            <circle cx={p.x} cy={p.y} r={2.5} fill={cor} />
          </g>
        ))}
      </svg>
      {/* eslint-enable react/no-unknown-property */}
      <Text style={{ fontSize: 13, fontWeight: "700" as const, color: cor, textAlign: "center", marginTop: 4 }}>{formatBRL(ultimoSaldo)}</Text>
    </View>
  );
}

// Clicável quando `onPress` é passado — leva pra tela de Contas a Pagar/
// Receber já filtrada (Vencido/Aberto), pedido explícito do usuário
// 2026-08-31 ("do card de pagar e receber nos leve as suas respectivas
// lista, que nos levarão as suas respectivas duplicatas"). Sem `onPress`
// (usuário sem permissão na tela de destino), fica só informativo.
function AlertaCard({ icon, label, alerta, cor, onPress }: { icon: React.ComponentProps<typeof Ionicons>["name"]; label: string; alerta: Alerta; cor: string; onPress?: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        { flex: 1, minWidth: 180, flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.sm },
        pressed && onPress ? { opacity: 0.8 } : null,
      ]}
      testID={`painel-financeiro-alerta-${label}`}
    >
      <Ionicons name={icon} size={22} color={cor} />
      <View style={{ flex: 1 }}>
        <Text style={{ fontSize: 11, color: colors.muted }}>{label}</Text>
        <Text style={{ fontSize: 14, fontWeight: "700", color: cor }}>{formatBRL(alerta.total)}</Text>
        <Text style={{ fontSize: 11, color: colors.muted }}>{alerta.qtd} lançamento(s)</Text>
      </View>
      {onPress ? <Ionicons name="chevron-forward" size={16} color={colors.muted} /> : null}
    </Pressable>
  );
}

function headerStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary }; }
function headerTitleStyle() { return { flex: 1, fontSize: 17, fontWeight: "700" as const, color: colors.onBrandPrimary }; }
// Abas do Painel Financeiro movidas pro título do cabeçalho, centralizadas
// (pedido explícito do usuário, 2026-08-31) — pills translúcidas sobre o
// fundo colorido do header, mesmo princípio já usado no botão "Gravar"
// translúcido-branco de "Full CRUD Form Screen Standard" (CLAUDE.md),
// aqui invertido pra pill ATIVA (fundo branco sólido, texto brandPrimary).
function tabBtnHeaderStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, gap: 6, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 6, backgroundColor: "rgba(255,255,255,0.15)" } as const; }
function tabBtnHeaderSelStyle() { return { backgroundColor: colors.onBrandPrimary }; }
function tabBtnHeaderLabelStyle() { return { fontSize: 12, fontWeight: "600" as const, color: colors.onBrandPrimary }; }
function tabBtnHeaderLabelSelStyle() { return { color: colors.brandPrimary }; }
// "Nova Previsão" no cabeçalho (achado do usuário 2026-08-31, "arrumação
// para economizar espaço") — mesma pill translúcida das abas, mas com
// fundo sólido levemente destacado (branco 20%) por ser uma ação, não
// navegação.
function headerNovaPrevisaoBtnStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, gap: 4, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 6, backgroundColor: "rgba(255,255,255,0.2)" } as const; }
function labelStyle() { return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 }; }
function fieldLabel() { return { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const }; }
function rowFieldsStyle() { return { flexDirection: "row" as const, gap: spacing.sm, marginBottom: spacing.sm, flexWrap: "wrap" as const }; }
function inputStyle() { return { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 14, color: colors.onSurface, backgroundColor: colors.surfaceSecondary } as const; }
function chipStyle() { return { borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 6, backgroundColor: colors.surface } as const; }
function chipSelStyle() { return { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary }; }
function chipTextStyle() { return { fontSize: 12, color: colors.onSurface, fontWeight: "600" as const }; }
function chipTextSelStyle() { return { color: colors.onBrandPrimary }; }
function miniBtnStyle() { return { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 4 } as const; }
function miniBtnLabelStyle() { return { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" as const }; }
function itemRowStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border }; }
function flagBadgeStyle() { return { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill }; }
function flagBadgeTextStyle() { return { fontSize: 10, fontWeight: "700" as const }; }
function primaryBtnStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 100 }; }
function primaryBtnLabelStyle() { return { color: colors.onBrandPrimary, fontWeight: "600" as const, fontSize: 14 }; }
function secondaryBtnStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 90 }; }
function secondaryBtnLabelStyle() { return { color: colors.brandPrimary, fontWeight: "600" as const, fontSize: 14 }; }
function dangerBtnStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingHorizontal: spacing.lg, paddingVertical: 10 }; }
function dangerBtnLabelStyle() { return { color: colors.error, fontWeight: "600" as const, fontSize: 14 }; }
function modalBgStyle() { return { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center" as const, justifyContent: "center" as const, padding: spacing.lg }; }
function modalCardStyle() { return { width: "100%" as const, maxWidth: 640, alignSelf: "center" as const, backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg }; }
function modalHeaderStyle() { return { flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "space-between" as const, marginBottom: spacing.md }; }
function modalTitleStyle() { return { fontSize: 15, fontWeight: "700" as const, color: colors.onSurface }; }
