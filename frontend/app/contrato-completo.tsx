import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR, fmtNum } from "@/src/utils/format";

// Contrato não é entidade principal do Gestor de Documentos — é gravado
// como anexo do CLIENTE (cod_grupo=1), filtrado por sub-grupo "Contratos"
// (cod_sub_grupo=5, já confirmado ao vivo em GERDELL/BARESTELA, ver
// CLAUDE.md > "Gestor de Documentos") + referencia = número do contrato.
// Mesmo padrão de AnexosPedidoModal.tsx (Pedido usa sub-grupo 2).
const GESTOR_DOC_SUBGRUPO_CONTRATO = 5;

type Conn = Connection;
type Lookup = { codigo: number; descricao: string };
type ClienteBusca = { codigo: number; nome: string; fantasia?: string; cgc_cpf?: string; telefone?: string; tipo_cliente_descricao?: string };
type ItemContrato = {
  codigo: number; produto: string; descricao: string; tipo: string | null;
  data_inicio: string | null; data_encerramento: string | null; preco: number; qtd: number; obs: string; situacao: string;
};
type CentroCustoContrato = { centro_custo: number; descricao: string; valor: number };
type PrecoHistorico = { codigo: number; data: string; preco_ant: number; preco_atual: number; percentual: number; descricao: string };
type CredDeb = { codigo: number; ano: number; mes: number; item: string; tipo: number; valor: number; compl_descr: string };

type FormState = {
  contrato: string; cliente: number | null; cliente_nome: string;
  servico_contrato: string; vendedor_contrato: number | null;
  assinatura: string | null; inicio: string | null; fim: string | null; renovado_ate: string | null; data_encerramento: string | null;
  dia_vencimento: string; mes_reajuste: string;
  valor_inicial: string; valor_atual: number; valor_ant: number; ultimo_reajuste: string | null;
  tipo_contrato: number | null; tipo_reajuste: number | null; indice_reajuste: number | null; tipo_cobranca: number | null; periodicidade: number | null;
  tarifa_cobranca: boolean; cobra_iss: boolean; agrupa_nf: boolean; fatura_os: boolean;
  descr_nf: string; msg_obs_nf: string; obs: string; historico: string;
  situacao: string;
  multa: string; mora_dia: string; desc_venc: string; dias_chave_renovacao: string;
};

const todayIso = () => new Date().toISOString().slice(0, 10);

const FORM_VAZIO: FormState = {
  contrato: "", cliente: null, cliente_nome: "",
  servico_contrato: "", vendedor_contrato: null,
  assinatura: todayIso(), inicio: todayIso(), fim: null, renovado_ate: null, data_encerramento: null,
  dia_vencimento: "", mes_reajuste: "",
  valor_inicial: "0,00", valor_atual: 0, valor_ant: 0, ultimo_reajuste: null,
  tipo_contrato: null, tipo_reajuste: null, indice_reajuste: null, tipo_cobranca: null, periodicidade: null,
  tarifa_cobranca: false, cobra_iss: false, agrupa_nf: false, fatura_os: false,
  descr_nf: "", msg_obs_nf: "", obs: "", historico: "",
  situacao: "A",
  multa: "0,00", mora_dia: "0,00", desc_venc: "0,00", dias_chave_renovacao: "0",
};

const ITEM_VAZIO: {
  codigo: number | null; produto: string; descricao: string; qtd: string; preco: string;
  data_inicio: string | null; data_encerramento: string | null; obs: string; situacao: string;
} = { codigo: null, produto: "", descricao: "", qtd: "1", preco: "0", data_inicio: todayIso(), data_encerramento: null, obs: "", situacao: "A" };
const CREDDEB_VAZIO = { codigo: null as number | null, ano: String(new Date().getFullYear()), mes: String(new Date().getMonth() + 1), item: "", tipo: 0, valor: "0", compl_descr: "" };

const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);
const int_ = (s: string): number => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || 0 : 0);
// Formata pra 2 casas decimais com vírgula (padrão BR) ao sair do campo —
// aplicado nos campos monetários/percentuais desta tela (Valor Inicial,
// Multa, Mora Diária, %Desc., Preço de Item, Reajuste, Acréscimo/Desconto,
// Centro de Custo). Pedido explícito do usuário, 2026-07-20.
const fmt2 = (s: string): string => num(s).toFixed(2).replace(".", ",");

// Transações > Contratos > Contratos (migração de FrmManContra.frm — Fase A,
// ver PENDENCIAS.md > "Contratos"). Tela cheia compacta (sem abas — o
// legado não tem TabStrip, usa Frames que aparecem/somem por botão, mesmo
// padrão já usado em Fornecedores/Cilindros: "Itens", "Centro de Custo",
// "Alteração de Preço" e "Acréscimo/Desconto" viram botão + slide modal).
// Itens/Centro de Custo/Reajuste/Acréscimo-Desconto exigem o contrato já
// gravado (regra global de "related record precisa do pai salvo primeiro").
export default function ContratoCompletoScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contratos está disponível apenas no web."
        testID="contrato-completo-web-only"
      />
    );
  }

  if (!moduleOn("contratos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Contratos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="contrato-completo-module-off"
      />
    );
  }

  const codigoParam = params.codigo ? Number(params.codigo) : null;

  const [conn, setConn] = useState<Conn | null>(null);
  const [codigo, setCodigo] = useState<number | null>(codigoParam);
  const [form, setForm] = useState<FormState>(FORM_VAZIO);
  const [itens, setItens] = useState<ItemContrato[]>([]);
  const [centroCusto, setCentroCusto] = useState<CentroCustoContrato[]>([]);
  const [precos, setPrecos] = useState<PrecoHistorico[]>([]);
  const [credDeb, setCredDeb] = useState<CredDeb[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [lookups, setLookups] = useState<{
    tipo_contrato: Lookup[]; tipo_reajuste: Lookup[]; indice_reajuste: Lookup[];
    tipo_cobranca: Lookup[]; periodicidade: Lookup[]; centro_custo: Lookup[]; vendedor: Lookup[];
  }>({ tipo_contrato: [], tipo_reajuste: [], indice_reajuste: [], tipo_cobranca: [], periodicidade: [], centro_custo: [], vendedor: [] });

  const patch = (p: Partial<FormState>) => setForm((f) => ({ ...f, ...p }));

  // ---- Boot ----
  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      fetch(`${base}/api/contratos/lookups?${qs}`).then((r) => r.json()).then((j) => { if (j?.success) setLookups(j); }).catch(() => {});
      if (codigoParam) await carregar(c, codigoParam);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const carregar = async (c: Conn, cod: number) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/contratos/${cod}?${qs}`);
      const j = await r.json();
      if (j?.success) {
        const ct = j.contrato;
        setForm({
          contrato: ct.contrato || "", cliente: ct.cliente, cliente_nome: ct.cliente_nome || "",
          servico_contrato: ct.servico_contrato || "", vendedor_contrato: ct.vendedor_contrato,
          assinatura: ct.assinatura, inicio: ct.inicio, fim: ct.fim, renovado_ate: ct.renovado_ate, data_encerramento: ct.data_encerramento,
          dia_vencimento: String(ct.dia_vencimento ?? ""), mes_reajuste: String(ct.mes_reajuste ?? ""),
          valor_inicial: fmt2(String(ct.valor_inicial ?? 0)), valor_atual: ct.valor_atual ?? 0, valor_ant: ct.valor_ant ?? 0, ultimo_reajuste: ct.ultimo_reajuste,
          tipo_contrato: ct.tipo_contrato, tipo_reajuste: ct.tipo_reajuste, indice_reajuste: ct.indice_reajuste, tipo_cobranca: ct.tipo_cobranca, periodicidade: ct.periodicidade,
          tarifa_cobranca: !!ct.tarifa_cobranca, cobra_iss: !!ct.cobra_iss, agrupa_nf: !!ct.agrupa_nf, fatura_os: !!ct.fatura_os,
          descr_nf: ct.descr_nf || "", msg_obs_nf: ct.msg_obs_nf || "", obs: ct.obs || "", historico: ct.historico || "",
          situacao: ct.situacao || "A",
          multa: fmt2(String(ct.multa ?? 0)), mora_dia: fmt2(String(ct.mora_dia ?? 0)), desc_venc: fmt2(String(ct.desc_venc ?? 0)), dias_chave_renovacao: String(ct.dias_chave_renovacao ?? 0),
        });
        setItens(ct.itens || []);
        setCentroCusto(ct.centro_custo || []);
        setPrecos(ct.precos || []);
        setCredDeb(ct.cred_deb || []);
        setCodigo(cod);
      } else {
        fb.showError(j?.message || "Contrato não encontrado.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  };

  const canSave = can("CONTRATO.GRAVAR") || isMaster;
  const canDel = can("CONTRATO.EXCLUIR") || isMaster;
  const canItens = can("CONTRATO.ITENS") || isMaster;
  const canCCusto = can("CONTRATO.CENTRO_CUSTO") || isMaster;
  const canReajuste = can("CONTRATO.REAJUSTE") || isMaster;
  const canCredDeb = can("CONTRATO.CRED_DEB") || isMaster;
  const canEncerrar = can("CONTRATO.ENCERRAR") || isMaster;

  const tipoContratoOpts = useMemo<SelectOption[]>(() => lookups.tipo_contrato.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.tipo_contrato]);
  const tipoReajusteOpts = useMemo<SelectOption[]>(() => lookups.tipo_reajuste.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.tipo_reajuste]);
  const indiceReajusteOpts = useMemo<SelectOption[]>(() => lookups.indice_reajuste.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.indice_reajuste]);
  const tipoCobrancaOpts = useMemo<SelectOption[]>(() => lookups.tipo_cobranca.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.tipo_cobranca]);
  const periodicidadeOpts = useMemo<SelectOption[]>(() => lookups.periodicidade.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.periodicidade]);
  const vendedorOpts = useMemo<SelectOption[]>(() => lookups.vendedor.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.vendedor]);
  const centroCustoOpts = useMemo<SelectOption[]>(() => lookups.centro_custo.map((l) => ({ value: l.codigo, label: l.descricao })), [lookups.centro_custo]);

  // ---- Cliente ----
  const [clienteBuscaOpen, setClienteBuscaOpen] = useState(false);
  const [clienteBuscaTerm, setClienteBuscaTerm] = useState("");
  const [clienteBuscaResults, setClienteBuscaResults] = useState<ClienteBusca[]>([]);
  const [clienteBuscaLoading, setClienteBuscaLoading] = useState(false);

  const buscarClientes = async (term: string) => {
    if (!conn || !term.trim()) { setClienteBuscaResults([]); return; }
    setClienteBuscaLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(term.trim())}`;
      const r = await fetch(`${base}/api/clientes/find/search?${qs}`);
      const j = await r.json();
      setClienteBuscaResults(j?.success ? j.items || [] : []);
    } catch { setClienteBuscaResults([]); } finally { setClienteBuscaLoading(false); }
  };

  const resolverClientePorCodigo = async (codStr: string) => {
    if (!conn || !codStr.trim() || !/^\d+$/.test(codStr.trim())) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/clientes/${codStr.trim()}/resumo?${qs}`);
      const j = await r.json();
      if (j?.success && j.cliente) {
        patch({ cliente: Number(codStr.trim()), cliente_nome: j.cliente.fantasia || j.cliente.nome });
      } else {
        fb.showError("Cliente não cadastrado!");
      }
    } catch { /* silencioso — busca manual continua disponível */ }
  };

  // ---- Gravar ----
  const save = async () => {
    if (!conn) return;
    if (!form.contrato.trim()) { fb.showError("O número do contrato não pode ficar em branco!"); return; }
    if (!form.cliente) { fb.showError("Informe o cliente do contrato!"); return; }
    if (!form.tipo_contrato || !form.tipo_reajuste || !form.indice_reajuste || !form.tipo_cobranca || !form.periodicidade) {
      fb.showError("Defina Tipo de Contrato, Reajuste, Índice, Cobrança e Periodicidade!"); return;
    }
    if (!form.descr_nf.trim()) { fb.showError("Preencha a Descrição da Nota Fiscal!"); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const body = {
        servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo,
        contrato: form.contrato.trim(), cliente: form.cliente,
        servico_contrato: form.servico_contrato || null, vendedor_contrato: form.vendedor_contrato,
        assinatura: form.assinatura, inicio: form.inicio, fim: form.fim, renovado_ate: form.renovado_ate, data_encerramento: form.data_encerramento,
        dia_vencimento: int_(form.dia_vencimento), mes_reajuste: int_(form.mes_reajuste),
        valor_inicial: num(form.valor_inicial),
        tipo_contrato: form.tipo_contrato, tipo_reajuste: form.tipo_reajuste, indice_reajuste: form.indice_reajuste,
        tipo_cobranca: form.tipo_cobranca, periodicidade: form.periodicidade,
        tarifa_cobranca: form.tarifa_cobranca, cobra_iss: form.cobra_iss, agrupa_nf: form.agrupa_nf, fatura_os: form.fatura_os,
        descr_nf: form.descr_nf, msg_obs_nf: form.msg_obs_nf, obs: form.obs, situacao: form.situacao,
        multa: num(form.multa), mora_dia: num(form.mora_dia), desc_venc: num(form.desc_venc), dias_chave_renovacao: int_(form.dias_chave_renovacao),
      };
      const r = await fetch(`${base}/api/contratos`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Contrato gravado.");
        if (!codigo) {
          router.replace({ pathname: "/contrato-completo", params: { codigo: String(j.codigo) } } as never);
        } else {
          await carregar(conn, codigo);
        }
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const excluirContrato = () => {
    if (!conn || !codigo) return;
    fb.showConfirm("Confirma Exclusão do Contrato?", async () => {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Contrato excluído."); router.back(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    });
  };

  const encerrarContrato = () => {
    if (!conn || !codigo) return;
    fb.showConfirm("Confirma Encerramento deste Contrato?", async () => {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/encerrar`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Contrato encerrado."); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao encerrar.");
    });
  };

  // ---- Itens ----
  const [itensOpen, setItensOpen] = useState(false);
  const [itemDraft, setItemDraft] = useState(ITEM_VAZIO);
  const [itemResolvendo, setItemResolvendo] = useState(false);
  const [itemSaving, setItemSaving] = useState(false);

  const resolverItemProduto = async () => {
    if (!conn || itemDraft.codigo != null || !itemDraft.produto.trim()) return;
    setItemResolvendo(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&termo=${encodeURIComponent(itemDraft.produto.trim())}`;
      const r = await fetch(`${base}/api/contratos/resolver-produto?${qs}`);
      const j = await r.json();
      if (j?.success) setItemDraft((p) => ({ ...p, produto: j.codigo, descricao: j.descricao }));
      else { setItemDraft((p) => ({ ...p, descricao: "" })); fb.showError(j?.message || "Não encontrado."); }
    } catch { setItemDraft((p) => ({ ...p, descricao: "" })); } finally { setItemResolvendo(false); }
  };

  const selecionarItem = (it: ItemContrato) => {
    setItemDraft({ codigo: it.codigo, produto: it.produto, descricao: it.descricao, qtd: String(it.qtd), preco: String(it.preco), data_inicio: it.data_inicio, data_encerramento: it.data_encerramento, obs: it.obs, situacao: it.situacao });
  };

  const salvarItem = async () => {
    if (!conn || !codigo) return;
    if (!itemDraft.produto.trim() || num(itemDraft.qtd) <= 0) { fb.showError("Defina o Item e a Quantidade corretamente!"); return; }
    setItemSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/itens`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: itemDraft.codigo,
          produto: itemDraft.produto.trim(), qtd: num(itemDraft.qtd), preco: num(itemDraft.preco),
          data_inicio: itemDraft.data_inicio, data_encerramento: itemDraft.data_encerramento, obs: itemDraft.obs, situacao: itemDraft.situacao,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Item gravado."); setItemDraft(ITEM_VAZIO); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao gravar item.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setItemSaving(false); }
  };

  const excluirItem = (it: ItemContrato) => {
    if (!conn || !codigo) return;
    fb.showConfirm(`Confirma exclusão do item "${it.descricao}"?`, async () => {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/itens/${it.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Item excluído."); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao excluir.");
    });
  };

  const itensTotal = itens.reduce((s, it) => s + it.preco * it.qtd, 0);

  // ---- Centro de Custo ----
  const [ccustoOpen, setCcustoOpen] = useState(false);
  const [ccustoSel, setCcustoSel] = useState<number | null>(null);
  const [ccustoValor, setCcustoValor] = useState("0");
  const [ccustoSaving, setCcustoSaving] = useState(false);

  const salvarCentroCusto = async () => {
    if (!conn || !codigo) return;
    if (!ccustoSel) { fb.showError("Defina o Centro de Custo!"); return; }
    if (num(ccustoValor) === 0) { fb.showError("Valor inválido!"); return; }
    setCcustoSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/centro-custo`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, centro_custo: ccustoSel, valor: num(ccustoValor) }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Centro de Custo gravado."); setCcustoSel(null); setCcustoValor("0"); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setCcustoSaving(false); }
  };

  const excluirCentroCusto = (cc: CentroCustoContrato) => {
    if (!conn || !codigo) return;
    fb.showConfirm(`Remover o centro de custo "${cc.descricao}"?`, async () => {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/centro-custo/${cc.centro_custo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Removido."); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao remover.");
    });
  };

  // Soma dos Centros de Custo lançados x valor atual do contrato — mesma
  // conferência do legado (FrmCustoContrato.Form_QueryUnload), aqui como
  // aviso em vez de bloqueio (ver contratos_service._rateio_centro_custo_sync).
  const ccustoTotal = centroCusto.reduce((s, cc) => s + cc.valor, 0);
  const ccustoDivergente = centroCusto.length > 0 && Math.round(ccustoTotal * 100) !== Math.round((form.valor_atual || 0) * 100);
  const [rateioSaving, setRateioSaving] = useState(false);

  const aplicarRateioCentroCusto = async () => {
    if (!conn || !codigo) return;
    setRateioSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/centro-custo/rateio`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Rateio aplicado."); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao ratear.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setRateioSaving(false); }
  };

  // ---- Reajuste de Valor ----
  const [reajusteOpen, setReajusteOpen] = useState(false);
  const [reajusteValor, setReajusteValor] = useState("0");
  const [reajustePercentual, setReajustePercentual] = useState("0");
  const [reajusteDescricao, setReajusteDescricao] = useState("");
  const [reajusteSaving, setReajusteSaving] = useState(false);
  const [reajusteConsultando, setReajusteConsultando] = useState(false);

  const abrirReajuste = () => {
    setReajusteValor(String(form.valor_atual));
    setReajustePercentual("0");
    setReajusteDescricao("");
    setReajusteOpen(true);
  };

  const consultarIndiceBacen = async () => {
    if (!conn || !codigo || !form.indice_reajuste) return;
    setReajusteConsultando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const dataInicial = form.ultimo_reajuste || form.inicio || todayIso();
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&data_inicial=${dataInicial}&data_fim=${todayIso()}`;
      const r = await fetch(`${base}/api/contratos/indice-reajuste/${form.indice_reajuste}/bacen?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setReajustePercentual(fmt2(String(j.percentual)));
        const novo = form.valor_atual * (1 + j.percentual / 100);
        setReajusteValor(fmt2(novo.toFixed(2)));
        // Mensagem tem números importantes pra conferir antes de gravar —
        // fica 5s na tela em vez do padrão de sucesso (600ms, curto demais
        // pra esse conteúdo). Pedido explícito do usuário, 2026-07-20.
        fb.showSuccess(`Índice ${j.indice}: ${j.percentual}% acumulado no período (${j.meses_considerados} mês(es) publicado(s)). Confira antes de gravar.`, undefined, 5000);
      } else {
        fb.showWarning(j?.message || "Não foi possível consultar o índice.");
      }
    } catch (e) {
      fb.showWarning("Não foi possível consultar o índice agora. Informe o percentual manualmente.");
    } finally {
      setReajusteConsultando(false);
    }
  };

  const salvarReajuste = async () => {
    if (!conn || !codigo) return;
    if (num(reajusteValor) === form.valor_atual) { fb.showError("Valor Reajustado igual ao Valor Atual — alteração não permitida!"); return; }
    setReajusteSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/reajuste`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, valor_novo: num(reajusteValor), percentual: num(reajustePercentual), descricao: reajusteDescricao }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Reajuste gravado."); setReajusteOpen(false); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao gravar reajuste.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setReajusteSaving(false); }
  };

  // ---- Acréscimo/Desconto ----
  const [credDebOpen, setCredDebOpen] = useState(false);
  const [credDebDraft, setCredDebDraft] = useState(CREDDEB_VAZIO);
  const [credDebSaving, setCredDebSaving] = useState(false);

  const selecionarCredDeb = (cd: CredDeb) => {
    setCredDebDraft({ codigo: cd.codigo, ano: String(cd.ano), mes: String(cd.mes), item: cd.item, tipo: cd.tipo, valor: String(cd.valor), compl_descr: cd.compl_descr });
  };

  const salvarCredDeb = async () => {
    if (!conn || !codigo) return;
    if (num(credDebDraft.valor) <= 0) { fb.showError("Valor inválido!"); return; }
    if (credDebDraft.tipo === 0 && !credDebDraft.item.trim()) { fb.showError("Código do Item inválido para Acréscimo!"); return; }
    setCredDebSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/cred-deb`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: credDebDraft.codigo,
          ano: int_(credDebDraft.ano), mes: int_(credDebDraft.mes), item: credDebDraft.item, tipo: credDebDraft.tipo,
          valor: num(credDebDraft.valor), compl_descr: credDebDraft.compl_descr,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Lançamento gravado."); setCredDebDraft(CREDDEB_VAZIO); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setCredDebSaving(false); }
  };

  const excluirCredDeb = (cd: CredDeb) => {
    if (!conn || !codigo) return;
    fb.showConfirm("Confirma exclusão deste lançamento?", async () => {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/${codigo}/cred-deb/${cd.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); await carregar(conn, codigo); }
      else fb.showError(j?.message || "Falha ao excluir.");
    });
  };

  // ---- Anexos (Gestor de Documentos) ----
  const [anexosOpen, setAnexosOpen] = useState(false);

  // Tooltip dos botões que são só ícone (sem texto ao lado) — hover no web,
  // um só de cada vez. "Modo Didático" — regra [GLOBAL] em CLAUDE.md >
  // "Padrões de UI", mesmo padrão de PainelPedidoCard.tsx.
  const [hoverBtn, setHoverBtn] = useState<string | null>(null);
  // `below`: os botões do cabeçalho ficam colados no topo da tela — um
  // tooltip "acima" do ícone (padrão de PainelPedidoCard.tsx) ficaria fora
  // da viewport, invisível. Nesses casos o tooltip precisa abrir pra BAIXO.
  const renderTooltip = (key: string, label: string, below = false) =>
    hoverBtn === key ? (
      <View style={[styles.tooltip, below && styles.tooltipBelow]} pointerEvents="none">
        <View style={styles.tooltipInner}>
          <Text style={styles.tooltipText}>{label}</Text>
        </View>
      </View>
    ) : null;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contrato-completo-screen">
      <View style={styles.header}>
        <View style={[styles.cardActionWrap, hoverBtn === "voltar" && styles.wrapHovered]}>
          <Pressable
            onPress={() => router.back()}
            onHoverIn={() => setHoverBtn("voltar")}
            onHoverOut={() => setHoverBtn(null)}
            style={styles.iconBtn}
            hitSlop={12}
            testID="contrato-completo-back"
          >
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          {renderTooltip("voltar", "Voltar", true)}
        </View>
        <Text style={styles.headerTitle} numberOfLines={1}>{codigo ? `Contrato ${form.contrato}` : "Novo Contrato"}</Text>
        {codigo && canEncerrar && form.situacao === "A" ? (
          <View style={[styles.cardActionWrap, hoverBtn === "encerrar" && styles.wrapHovered]}>
            <Pressable
              onPress={encerrarContrato}
              onHoverIn={() => setHoverBtn("encerrar")}
              onHoverOut={() => setHoverBtn(null)}
              style={styles.iconBtn}
              hitSlop={12}
              testID="contrato-completo-encerrar"
            >
              <Ionicons name="lock-closed-outline" size={20} color={colors.warning} />
            </Pressable>
            {renderTooltip("encerrar", "Encerrar contrato", true)}
          </View>
        ) : null}
        {codigo && canDel && form.situacao === "A" ? (
          <View style={[styles.cardActionWrap, hoverBtn === "excluir" && styles.wrapHovered]}>
            <Pressable
              onPress={excluirContrato}
              onHoverIn={() => setHoverBtn("excluir")}
              onHoverOut={() => setHoverBtn(null)}
              style={styles.iconBtn}
              hitSlop={12}
              testID="contrato-completo-excluir"
            >
              <Ionicons name="trash-outline" size={20} color={colors.error} />
            </Pressable>
            {renderTooltip("excluir", "Excluir contrato", true)}
          </View>
        ) : null}
        {canSave ? (
          <Pressable onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="contrato-completo-salvar">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
              <>
                <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.saveLabel}>Gravar</Text>
              </>
            )}
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : (
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            {/* ---- Ações relacionadas (exigem contrato já gravado) ---- */}
            {!codigo ? (
              <View style={styles.card}>
                <View style={styles.lockedRow}>
                  <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                  <Text style={styles.lockedText}>Grave os Dados do Contrato primeiro para lançar itens, centro de custo, reajuste e acréscimo/desconto.</Text>
                </View>
              </View>
            ) : (
              <View style={styles.actionsWrap}>
                {canItens ? (
                  <Pressable onPress={() => setItensOpen(true)} style={styles.secondaryActionBtn} testID="contrato-completo-abrir-itens">
                    <Ionicons name="cube-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Itens ({itens.length}) · {formatBRL(itensTotal)}</Text>
                  </Pressable>
                ) : null}
                {canCCusto ? (
                  <Pressable onPress={() => setCcustoOpen(true)} style={styles.secondaryActionBtn} testID="contrato-completo-abrir-ccusto">
                    <Ionicons name="pie-chart-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Centro de Custo ({centroCusto.length})</Text>
                  </Pressable>
                ) : null}
                {canReajuste ? (
                  <Pressable onPress={abrirReajuste} style={styles.secondaryActionBtn} testID="contrato-completo-abrir-reajuste">
                    <Ionicons name="trending-up-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Alteração de Preço</Text>
                  </Pressable>
                ) : null}
                {canCredDeb ? (
                  <Pressable onPress={() => setCredDebOpen(true)} style={styles.secondaryActionBtn} testID="contrato-completo-abrir-creddeb">
                    <Ionicons name="calculator-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Acréscimo/Desconto ({credDeb.length})</Text>
                  </Pressable>
                ) : null}
                {form.cliente ? (
                  <Pressable onPress={() => setAnexosOpen(true)} style={styles.secondaryActionBtn} testID="contrato-completo-abrir-anexos">
                    <Ionicons name="attach-outline" size={18} color={colors.brandPrimary} />
                    <Text style={styles.secondaryActionText}>Anexos</Text>
                  </Pressable>
                ) : null}
              </View>
            )}

            {/* ---- Identificação ---- */}
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Nº do Contrato *</Text>
                  <TextInput value={form.contrato} onChangeText={(v) => patch({ contrato: v })} style={styles.input} maxLength={20} testID="contrato-completo-numero" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cliente (código) *</Text>
                  <TextInput
                    value={form.cliente ? String(form.cliente) : ""}
                    onChangeText={(v) => patch({ cliente: v ? Number(v.replace(/\D/g, "")) : null, cliente_nome: "" })}
                    onBlur={() => form.cliente && resolverClientePorCodigo(String(form.cliente))}
                    keyboardType="number-pad"
                    style={styles.input}
                    testID="contrato-completo-cliente-codigo"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Nome do Cliente</Text>
                  <View style={styles.inputWithBtn}>
                    <Text style={[styles.input, { flex: 1 }]} numberOfLines={1}>{form.cliente_nome || "—"}</Text>
                    <View style={styles.cardActionWrap}>
                      <Pressable
                        onPress={() => setClienteBuscaOpen(true)}
                        onHoverIn={() => setHoverBtn("buscar-cliente")}
                        onHoverOut={() => setHoverBtn(null)}
                        style={styles.cepBtn}
                        testID="contrato-completo-cliente-buscar"
                      >
                        <Ionicons name="search" size={18} color="#fff" />
                      </Pressable>
                      {renderTooltip("buscar-cliente", "Buscar cliente")}
                    </View>
                  </View>
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Situação</Text>
                  <View style={[styles.input, { alignItems: "center", justifyContent: "center" }]}>
                    <Text style={{ color: form.situacao === "A" ? colors.brandPrimary : colors.muted, fontWeight: "700" }}>
                      {form.situacao === "A" ? "Ativo" : "Encerrado"}
                    </Text>
                  </View>
                </View>
              </View>
            </View>

            {/* ---- Dados do Contrato ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Dados do Contrato</Text></View>
            <View style={styles.card}>
              <Text style={styles.helpText}>
                O contrato é cobrado automaticamente todo mês na tela "Faturar Contratos", usando o
                valor atual abaixo. "Dia Venc." define em que dia do mês a cobrança vence; "Mês
                Reajuste" é o mês em que o valor pode ser reajustado (por índice ou manualmente,
                depois de gravar o contrato).
              </Text>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Assinatura</Text>
                  <WebDateField value={form.assinatura} onChange={(v) => patch({ assinatura: v || null })} testID="contrato-completo-assinatura" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Início</Text>
                  <WebDateField
                    value={form.inicio}
                    onChange={(v) => {
                      const mes = form.mes_reajuste || (v ? String(new Date(v).getMonth() + 1) : "");
                      patch({ inicio: v || null, mes_reajuste: mes });
                    }}
                    testID="contrato-completo-inicio"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Fim</Text>
                  <WebDateField value={form.fim} onChange={(v) => patch({ fim: v || null })} testID="contrato-completo-fim" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Prorrogado até</Text>
                  <WebDateField value={form.renovado_ate} onChange={(v) => patch({ renovado_ate: v || null })} testID="contrato-completo-renovado" />
                </View>
                {form.situacao !== "A" ? (
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Encerrado em</Text>
                    <Text style={styles.input}>{form.data_encerramento ? formatDateBR(form.data_encerramento) : "—"}</Text>
                  </View>
                ) : null}
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dia Venc. *</Text>
                  <TextInput value={form.dia_vencimento} onChangeText={(v) => patch({ dia_vencimento: v.replace(/\D/g, "") })} keyboardType="number-pad" maxLength={2} style={styles.input} testID="contrato-completo-dia-vencimento" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Mês Reajuste *</Text>
                  <TextInput value={form.mes_reajuste} onChangeText={(v) => patch({ mes_reajuste: v.replace(/\D/g, "") })} keyboardType="number-pad" maxLength={2} style={styles.input} testID="contrato-completo-mes-reajuste" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Vendedor</Text>
                  <SelectField value={form.vendedor_contrato} onChange={(v) => patch({ vendedor_contrato: v as number | null })} options={vendedorOpts} allowClear compactWeb testID="contrato-completo-vendedor" modalTitle="Vendedor" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Serviço do Contrato</Text>
                  <TextInput value={form.servico_contrato} onChangeText={(v) => patch({ servico_contrato: v.toUpperCase() })} style={styles.input} testID="contrato-completo-servico" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo de Contrato *</Text>
                  <SelectField value={form.tipo_contrato} onChange={(v) => patch({ tipo_contrato: v as number | null })} options={tipoContratoOpts} compactWeb testID="contrato-completo-tipo-contrato" modalTitle="Tipo de Contrato" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo de Reajuste *</Text>
                  <SelectField value={form.tipo_reajuste} onChange={(v) => patch({ tipo_reajuste: v as number | null })} options={tipoReajusteOpts} compactWeb testID="contrato-completo-tipo-reajuste" modalTitle="Tipo de Reajuste" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Índice *</Text>
                  <SelectField value={form.indice_reajuste} onChange={(v) => patch({ indice_reajuste: v as number | null })} options={indiceReajusteOpts} compactWeb testID="contrato-completo-indice" modalTitle="Índice de Reajuste" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Tipo de Cobrança *</Text>
                  <SelectField value={form.tipo_cobranca} onChange={(v) => patch({ tipo_cobranca: v as number | null })} options={tipoCobrancaOpts} compactWeb testID="contrato-completo-tipo-cobranca" modalTitle="Tipo de Cobrança" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Periodicidade *</Text>
                  <SelectField value={form.periodicidade} onChange={(v) => patch({ periodicidade: v as number | null })} options={periodicidadeOpts} compactWeb testID="contrato-completo-periodicidade" modalTitle="Periodicidade Contratual" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.switchField}>
                  <Switch value={form.tarifa_cobranca} onValueChange={(v) => patch({ tarifa_cobranca: v })} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="contrato-completo-tarifa" />
                  <Text style={styles.switchLabel}>Cobra Tarifa Bancária</Text>
                </View>
                <View style={styles.switchField}>
                  <Switch value={form.cobra_iss} onValueChange={(v) => patch({ cobra_iss: v })} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="contrato-completo-iss" />
                  <Text style={styles.switchLabel}>Cobra ISS</Text>
                </View>
                <View style={styles.switchField}>
                  <Switch value={form.agrupa_nf} onValueChange={(v) => patch({ agrupa_nf: v })} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="contrato-completo-agrupa-nf" />
                  <Text style={styles.switchLabel}>Agrupa para Faturar</Text>
                </View>
                <View style={styles.switchField}>
                  <Switch value={form.fatura_os} onValueChange={(v) => patch({ fatura_os: v })} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="contrato-completo-fatura-os" />
                  <Text style={styles.switchLabel}>Fatura O.S.'s</Text>
                </View>
              </View>
              <Text style={styles.helpText}>
                "Fatura O.S.'s" inclui automaticamente, na próxima cobrança deste cliente, o valor de
                Ordens de Serviço já concluídas e ainda não cobradas — útil quando o contrato também
                cobre manutenções avulsas. "Agrupa para Faturar" junta a cobrança deste contrato com a
                de outro cliente "principal" (matriz/filial), em vez de cobrar os dois separadamente.
              </Text>
            </View>

            {/* ---- Valores ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Valores</Text></View>
            <View style={styles.card}>
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor Inicial *</Text>
                  <TextInput value={form.valor_inicial} onChangeText={(v) => patch({ valor_inicial: v })} onBlur={() => patch({ valor_inicial: fmt2(form.valor_inicial) })} keyboardType="decimal-pad" style={styles.input} testID="contrato-completo-valor-inicial" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor Atual</Text>
                  <Text style={[styles.input, styles.readonlyStrong]}>{formatBRL(form.valor_atual)}</Text>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor Anterior</Text>
                  <Text style={styles.input}>{formatBRL(form.valor_ant)}</Text>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Último Reajuste</Text>
                  <Text style={styles.input}>{form.ultimo_reajuste ? formatDateBR(form.ultimo_reajuste) : "—"}</Text>
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Multa</Text>
                  <TextInput value={form.multa} onChangeText={(v) => patch({ multa: v })} onBlur={() => patch({ multa: fmt2(form.multa) })} keyboardType="decimal-pad" style={styles.input} testID="contrato-completo-multa" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Mora Diária</Text>
                  <TextInput value={form.mora_dia} onChangeText={(v) => patch({ mora_dia: v })} onBlur={() => patch({ mora_dia: fmt2(form.mora_dia) })} keyboardType="decimal-pad" style={styles.input} testID="contrato-completo-mora" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>%Desc. até Venc.</Text>
                  <TextInput value={form.desc_venc} onChangeText={(v) => patch({ desc_venc: v })} onBlur={() => patch({ desc_venc: fmt2(form.desc_venc) })} keyboardType="decimal-pad" style={styles.input} testID="contrato-completo-desc-venc" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Dias Renovação</Text>
                  <TextInput value={form.dias_chave_renovacao} onChangeText={(v) => patch({ dias_chave_renovacao: v.replace(/\D/g, "") })} keyboardType="number-pad" style={styles.input} testID="contrato-completo-dias-renovacao" />
                </View>
              </View>
              <Text style={styles.helpText}>
                "Multa" e "Mora Diária" são cobrados do cliente só se o pagamento atrasar. "%Desc. até
                Venc." é um desconto para quem paga em dia. "Dias Renovação" avisa com quantos dias de
                antecedência o contrato deve ser renovado antes de vencer de vez.
              </Text>
            </View>

            {/* ---- Descrição NF / Observações ---- */}
            <View style={styles.sectionHeader}><Text style={styles.sectionTitle}>Nota Fiscal / Observações</Text></View>
            <View style={styles.card}>
              <Text style={styles.label}>Descrição NF *</Text>
              <TextInput value={form.descr_nf} onChangeText={(v) => patch({ descr_nf: v })} style={styles.input} maxLength={40} testID="contrato-completo-descr-nf" />
              <Text style={styles.label}>Obs. NF</Text>
              <TextInput value={form.msg_obs_nf} onChangeText={(v) => patch({ msg_obs_nf: v })} style={styles.input} maxLength={40} testID="contrato-completo-obs-nf" />
              <Text style={styles.label}>Observação</Text>
              <TextInput value={form.obs} onChangeText={(v) => patch({ obs: v })} multiline style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]} testID="contrato-completo-obs" />
              {form.historico ? (
                <AccordionSection title="Histórico" testID="contrato-completo-historico" style={{ marginTop: spacing.sm }}>
                  <Text style={[styles.input, { minHeight: 60, marginTop: spacing.sm }]}>
                    {form.historico.split("\n").reverse().join("\n")}
                  </Text>
                </AccordionSection>
              ) : null}
            </View>

          </View>
        </ScrollView>
      )}

      {/* ==================== Modal: Buscar Cliente ==================== */}
      <Modal visible={clienteBuscaOpen} transparent animationType="slide" onRequestClose={() => setClienteBuscaOpen(false)}>
        <Pressable style={[styles.slideBg, styles.slideBgWebCompact]} onPress={() => setClienteBuscaOpen(false)}>
          <Pressable style={[styles.slideCard, styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Buscar Cliente</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setClienteBuscaOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-cliente")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-cliente-busca-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-cliente", "Fechar")}
              </View>
            </View>
            <TextInput
              value={clienteBuscaTerm}
              onChangeText={(v) => { setClienteBuscaTerm(v); buscarClientes(v); }}
              placeholder="Nome, CPF/CNPJ ou código…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              autoFocus
              testID="contrato-cliente-busca-termo"
            />
            <ScrollView style={{ marginTop: spacing.sm, maxHeight: 320 }}>
              {clienteBuscaLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
              {!clienteBuscaLoading && clienteBuscaResults.length === 0 ? <Text style={styles.hint}>Nenhum cliente encontrado.</Text> : null}
              {clienteBuscaResults.map((c) => (
                <Pressable
                  key={c.codigo}
                  onPress={() => { patch({ cliente: c.codigo, cliente_nome: c.fantasia || c.nome }); setClienteBuscaOpen(false); setClienteBuscaTerm(""); setClienteBuscaResults([]); }}
                  style={styles.gridRow}
                  testID={`contrato-cliente-busca-${c.codigo}`}
                >
                  <Text style={styles.gridRowText}>{c.codigo} · {c.fantasia || c.nome}{c.tipo_cliente_descricao ? ` — ${c.tipo_cliente_descricao}` : ""}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ==================== Modal: Itens do Contrato ==================== */}
      <Modal visible={itensOpen} transparent animationType="slide" onRequestClose={() => setItensOpen(false)}>
        <Pressable style={[styles.slideBg, styles.slideBgWebCompact]} onPress={() => setItensOpen(false)}>
          <Pressable style={[styles.slideCard, styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Itens do Contrato</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setItensOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-itens")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-itens-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-itens", "Fechar")}
              </View>
            </View>
            <Text style={styles.helpText}>
              Cada item é um produto, equipamento, serviço ou cilindro incluído no contrato — o valor
              deles compõe o total cobrado do cliente. Toque num item já lançado na lista para editar.
            </Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {itens.length === 0 ? <Text style={styles.hint}>Nenhum item incluído.</Text> : itens.map((it) => (
                <Pressable key={it.codigo} onPress={() => selecionarItem(it)} style={[styles.gridRow, itemDraft.codigo === it.codigo && styles.gridRowSel]} testID={`contrato-item-${it.codigo}`}>
                  <Text style={styles.gridRowText} numberOfLines={1}>{it.produto} · {it.descricao} — {fmtNum(it.qtd)} x {formatBRL(it.preco)}</Text>
                  <View style={styles.cardActionWrap}>
                    <Pressable
                      onPress={() => excluirItem(it)}
                      onHoverIn={() => setHoverBtn(`del-item-${it.codigo}`)}
                      onHoverOut={() => setHoverBtn(null)}
                      hitSlop={8}
                      testID={`contrato-item-excluir-${it.codigo}`}
                    >
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                    </Pressable>
                    {renderTooltip(`del-item-${it.codigo}`, "Excluir item")}
                  </View>
                </Pressable>
              ))}
            </ScrollView>
            <View style={styles.divider} />
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Produto/Equipamento/Serviço/Cilindro</Text>
                <TextInput
                  value={itemDraft.produto}
                  onChangeText={(v) => setItemDraft((p) => ({ ...p, produto: v, descricao: p.codigo != null ? p.descricao : "" }))}
                  onBlur={resolverItemProduto}
                  editable={itemDraft.codigo == null}
                  style={[styles.input, itemDraft.codigo != null && { opacity: 0.6 }]}
                  autoCapitalize="characters"
                  testID="contrato-item-produto"
                />
                {itemResolvendo ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
                {itemDraft.descricao ? <Text style={styles.descricaoResolvida}>{itemDraft.descricao}</Text> : null}
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Qtd</Text>
                <TextInput value={itemDraft.qtd} onChangeText={(v) => setItemDraft((p) => ({ ...p, qtd: v }))} keyboardType="decimal-pad" style={styles.input} testID="contrato-item-qtd" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Preço</Text>
                <TextInput value={itemDraft.preco} onChangeText={(v) => setItemDraft((p) => ({ ...p, preco: v }))} onBlur={() => setItemDraft((p) => ({ ...p, preco: fmt2(p.preco) }))} keyboardType="decimal-pad" style={styles.input} testID="contrato-item-preco" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Início</Text>
                <WebDateField value={itemDraft.data_inicio} onChange={(v) => setItemDraft((p) => ({ ...p, data_inicio: v || null }))} testID="contrato-item-data-inicio" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Encerramento</Text>
                <WebDateField value={itemDraft.data_encerramento} onChange={(v) => setItemDraft((p) => ({ ...p, data_encerramento: v || null }))} testID="contrato-item-data-fim" />
              </View>
            </View>
            <Text style={styles.label}>Observação</Text>
            <TextInput value={itemDraft.obs} onChangeText={(v) => setItemDraft((p) => ({ ...p, obs: v }))} style={styles.input} testID="contrato-item-obs" />
            <View style={styles.crudBtnRow}>
              <Pressable onPress={() => setItemDraft(ITEM_VAZIO)} style={styles.crudBtn} testID="contrato-item-novo"><Text style={styles.crudBtnText}>Novo</Text></Pressable>
              <Pressable onPress={salvarItem} disabled={itemSaving} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="contrato-item-salvar">
                {itemSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.crudBtnPrimaryText}>Gravar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ==================== Modal: Centro de Custo ==================== */}
      <Modal visible={ccustoOpen} transparent animationType="slide" onRequestClose={() => setCcustoOpen(false)}>
        <Pressable style={[styles.slideBg, styles.slideBgWebCompact]} onPress={() => setCcustoOpen(false)}>
          <Pressable style={[styles.slideCard, styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Centro de Custo</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setCcustoOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-ccusto")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-ccusto-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-ccusto", "Fechar")}
              </View>
            </View>
            <Text style={styles.helpText}>
              Centro de Custo divide o valor do contrato entre setores/departamentos da empresa, só
              para fins contábeis internos — não muda o que o cliente paga. A soma de todos os centros
              de custo lançados deve bater com o Valor Atual do contrato.
            </Text>
            <ScrollView style={{ maxHeight: 220 }}>
              {centroCusto.length === 0 ? <Text style={styles.hint}>Nenhum centro de custo lançado.</Text> : centroCusto.map((cc) => (
                <View key={cc.centro_custo} style={styles.gridRow} testID={`contrato-ccusto-${cc.centro_custo}`}>
                  <Text style={styles.gridRowText}>{cc.descricao} — {formatBRL(cc.valor)}</Text>
                  <View style={styles.cardActionWrap}>
                    <Pressable
                      onPress={() => excluirCentroCusto(cc)}
                      onHoverIn={() => setHoverBtn(`del-ccusto-${cc.centro_custo}`)}
                      onHoverOut={() => setHoverBtn(null)}
                      hitSlop={8}
                      testID={`contrato-ccusto-excluir-${cc.centro_custo}`}
                    >
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                    </Pressable>
                    {renderTooltip(`del-ccusto-${cc.centro_custo}`, "Remover")}
                  </View>
                </View>
              ))}
            </ScrollView>
            {ccustoDivergente && (
              <Text style={[styles.hint, { color: colors.warning, fontStyle: "normal" }]} testID="contrato-ccusto-divergencia">
                Total lançado ({formatBRL(ccustoTotal)}) diverge do valor atual do contrato ({formatBRL(form.valor_atual || 0)}). Use "Rateio Valor" para ajustar proporcionalmente.
              </Text>
            )}
            <View style={styles.divider} />
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Centro de Custo</Text>
                <SelectField value={ccustoSel} onChange={(v) => setCcustoSel(v as number | null)} options={centroCustoOpts} compactWeb testID="contrato-ccusto-select" modalTitle="Centro de Custo" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Valor</Text>
                <TextInput value={ccustoValor} onChangeText={setCcustoValor} onBlur={() => setCcustoValor(fmt2(ccustoValor))} keyboardType="decimal-pad" style={styles.input} testID="contrato-ccusto-valor" />
              </View>
            </View>
            <View style={styles.crudBtnRow}>
              <Pressable onPress={aplicarRateioCentroCusto} disabled={rateioSaving || centroCusto.length === 0} style={styles.crudBtn} testID="contrato-ccusto-rateio">
                {rateioSaving ? <ActivityIndicator size="small" /> : <Text style={styles.crudBtnText}>Rateio Valor</Text>}
              </Pressable>
              <Pressable onPress={salvarCentroCusto} disabled={ccustoSaving} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="contrato-ccusto-salvar">
                {ccustoSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.crudBtnPrimaryText}>Gravar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ==================== Modal: Alteração de Preço (Reajuste) ==================== */}
      <Modal visible={reajusteOpen} transparent animationType="slide" onRequestClose={() => setReajusteOpen(false)}>
        <Pressable style={[styles.slideBg, styles.slideBgWebCompact]} onPress={() => setReajusteOpen(false)}>
          <Pressable style={[styles.slideCard, styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Alteração de Preço</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setReajusteOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-reajuste")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-reajuste-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-reajuste", "Fechar")}
              </View>
            </View>
            <Text style={styles.hint}>Valor Atual: {formatBRL(form.valor_atual)}</Text>
            <Text style={styles.helpText}>
              "Consultar índice no Banco Central" busca automaticamente o percentual acumulado do
              índice escolhido no cadastro do contrato (ex.: IGP-M, IPCA) e já sugere o novo valor —
              nada é gravado sozinho, você confere e confirma clicando em "Gravar Reajuste".
            </Text>
            <Pressable onPress={consultarIndiceBacen} disabled={reajusteConsultando} style={[styles.crudBtn, styles.crudBtnInline, { alignSelf: "flex-start", marginTop: spacing.sm }]} testID="contrato-reajuste-consultar-indice">
              {reajusteConsultando ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : (
                <>
                  <Ionicons name="cloud-download-outline" size={14} color={colors.onSurface} />
                  <Text style={styles.crudBtnText}>Consultar índice no Banco Central</Text>
                </>
              )}
            </Pressable>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>% Reajuste</Text>
                <TextInput value={reajustePercentual} onChangeText={setReajustePercentual} onBlur={() => setReajustePercentual(fmt2(reajustePercentual))} keyboardType="decimal-pad" style={styles.input} testID="contrato-reajuste-percentual" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Novo Valor</Text>
                <TextInput value={reajusteValor} onChangeText={setReajusteValor} onBlur={() => setReajusteValor(fmt2(reajusteValor))} keyboardType="decimal-pad" style={styles.input} testID="contrato-reajuste-valor" />
              </View>
            </View>
            <Text style={styles.label}>Descrição/Motivo</Text>
            <TextInput value={reajusteDescricao} onChangeText={setReajusteDescricao} style={styles.input} testID="contrato-reajuste-descricao" />
            <Pressable onPress={salvarReajuste} disabled={reajusteSaving} style={[styles.crudBtn, styles.crudBtnPrimary, { marginTop: spacing.sm }]} testID="contrato-reajuste-salvar">
              {reajusteSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.crudBtnPrimaryText}>Gravar Reajuste</Text>}
            </Pressable>

            {precos.length > 0 ? (
              <>
                <View style={styles.divider} />
                <Text style={styles.label}>Histórico</Text>
                <ScrollView style={{ maxHeight: 160 }}>
                  {precos.map((p) => (
                    <View key={p.codigo} style={styles.gridRow}>
                      <Text style={styles.gridRowText}>
                        {formatDateBR(p.data)}: {formatBRL(p.preco_ant)} → {formatBRL(p.preco_atual)} ({fmtNum(p.percentual)}%){p.descricao ? ` — ${p.descricao}` : ""}
                      </Text>
                    </View>
                  ))}
                </ScrollView>
              </>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {/* ==================== Modal: Acréscimo/Desconto ==================== */}
      <Modal visible={credDebOpen} transparent animationType="slide" onRequestClose={() => setCredDebOpen(false)}>
        <Pressable style={[styles.slideBg, styles.slideBgWebCompact]} onPress={() => setCredDebOpen(false)}>
          <Pressable style={[styles.slideCard, styles.slideCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Acréscimo/Desconto</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setCredDebOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-creddeb")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-creddeb-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-creddeb", "Fechar")}
              </View>
            </View>
            <Text style={styles.helpText}>
              Lançamentos avulsos de um mês específico, à parte do valor mensal do contrato — um
              "Acréscimo" soma ao valor cobrado naquele mês (ex.: uma taxa extra), um "Desconto"
              subtrai (ex.: uma cortesia pontual).
            </Text>
            <ScrollView style={{ maxHeight: 200 }}>
              {credDeb.length === 0 ? <Text style={styles.hint}>Nenhum lançamento.</Text> : credDeb.map((cd) => (
                <Pressable key={cd.codigo} onPress={() => selecionarCredDeb(cd)} style={[styles.gridRow, credDebDraft.codigo === cd.codigo && styles.gridRowSel]} testID={`contrato-creddeb-${cd.codigo}`}>
                  <Text style={styles.gridRowText} numberOfLines={1}>
                    {cd.mes.toString().padStart(2, "0")}/{cd.ano} · {cd.tipo === 0 ? "Acréscimo" : "Desconto"} · {formatBRL(cd.valor)}{cd.item ? ` — ${cd.item}` : ""}
                  </Text>
                  <View style={styles.cardActionWrap}>
                    <Pressable
                      onPress={() => excluirCredDeb(cd)}
                      onHoverIn={() => setHoverBtn(`del-creddeb-${cd.codigo}`)}
                      onHoverOut={() => setHoverBtn(null)}
                      hitSlop={8}
                      testID={`contrato-creddeb-excluir-${cd.codigo}`}
                    >
                      <Ionicons name="trash-outline" size={16} color={colors.error} />
                    </Pressable>
                    {renderTooltip(`del-creddeb-${cd.codigo}`, "Excluir lançamento")}
                  </View>
                </Pressable>
              ))}
            </ScrollView>
            <View style={styles.divider} />
            <View style={styles.radioRow}>
              <Pressable onPress={() => setCredDebDraft((p) => ({ ...p, tipo: 0 }))} style={[styles.radioBtn, credDebDraft.tipo === 0 && styles.radioBtnSel]} testID="contrato-creddeb-tipo-acrescimo">
                <View style={[styles.radioCircle, credDebDraft.tipo === 0 && styles.radioCircleSel]}>{credDebDraft.tipo === 0 ? <View style={styles.radioDot} /> : null}</View>
                <Text style={styles.radioLabel}>Acréscimo</Text>
              </Pressable>
              <Pressable onPress={() => setCredDebDraft((p) => ({ ...p, tipo: 1 }))} style={[styles.radioBtn, credDebDraft.tipo === 1 && styles.radioBtnSel]} testID="contrato-creddeb-tipo-desconto">
                <View style={[styles.radioCircle, credDebDraft.tipo === 1 && styles.radioCircleSel]}>{credDebDraft.tipo === 1 ? <View style={styles.radioDot} /> : null}</View>
                <Text style={styles.radioLabel}>Desconto</Text>
              </Pressable>
            </View>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Ano</Text>
                <TextInput value={credDebDraft.ano} onChangeText={(v) => setCredDebDraft((p) => ({ ...p, ano: v.replace(/\D/g, "") }))} keyboardType="number-pad" maxLength={4} style={styles.input} testID="contrato-creddeb-ano" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Mês</Text>
                <TextInput value={credDebDraft.mes} onChangeText={(v) => setCredDebDraft((p) => ({ ...p, mes: v.replace(/\D/g, "") }))} keyboardType="number-pad" maxLength={2} style={styles.input} testID="contrato-creddeb-mes" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Item (peça/serviço)</Text>
                <TextInput value={credDebDraft.item} onChangeText={(v) => setCredDebDraft((p) => ({ ...p, item: v.toUpperCase() }))} style={styles.input} testID="contrato-creddeb-item" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Valor</Text>
                <TextInput value={credDebDraft.valor} onChangeText={(v) => setCredDebDraft((p) => ({ ...p, valor: v }))} onBlur={() => setCredDebDraft((p) => ({ ...p, valor: fmt2(p.valor) }))} keyboardType="decimal-pad" style={styles.input} testID="contrato-creddeb-valor" />
              </View>
            </View>
            <Text style={styles.label}>Descrição complementar (Nota Fiscal)</Text>
            <TextInput value={credDebDraft.compl_descr} onChangeText={(v) => setCredDebDraft((p) => ({ ...p, compl_descr: v }))} style={styles.input} testID="contrato-creddeb-compl" />
            <View style={styles.crudBtnRow}>
              <Pressable onPress={() => setCredDebDraft(CREDDEB_VAZIO)} style={styles.crudBtn} testID="contrato-creddeb-novo"><Text style={styles.crudBtnText}>Novo</Text></Pressable>
              <Pressable onPress={salvarCredDeb} disabled={credDebSaving} style={[styles.crudBtn, styles.crudBtnPrimary]} testID="contrato-creddeb-salvar">
                {credDebSaving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.crudBtnPrimaryText}>Gravar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* ==================== Modal: Anexos (Gestor de Documentos) ==================== */}
      <Modal visible={anexosOpen} transparent animationType="slide" onRequestClose={() => setAnexosOpen(false)}>
        <Pressable style={styles.anexosBg} onPress={() => setAnexosOpen(false)}>
          <Pressable style={styles.anexosCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.slideTitle}>Anexos do Contrato {form.contrato}</Text>
              <View style={styles.cardActionWrap}>
                <Pressable
                  onPress={() => setAnexosOpen(false)}
                  onHoverIn={() => setHoverBtn("fechar-anexos")}
                  onHoverOut={() => setHoverBtn(null)}
                  hitSlop={8}
                  testID="contrato-anexos-fechar"
                >
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
                {renderTooltip("fechar-anexos", "Fechar")}
              </View>
            </View>
            {conn && form.cliente ? (
              <ScrollView style={{ maxHeight: 560 }}>
                <GestorDocumentosSection
                  api={conn.api}
                  servidor={conn.servidor}
                  banco={conn.banco}
                  codGrupo={GESTOR_DOC_GRUPO_CLIENTE}
                  codigoEntidade={form.cliente}
                  codSubGrupo={GESTOR_DOC_SUBGRUPO_CONTRATO}
                  referencia={codigo ?? undefined}
                />
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  // Wrapper com position:relative pra ancorar o tooltip absoluto de um
  // botão-ícone — "Modo Didático", mesmo padrão de PainelPedidoCard.tsx.
  cardActionWrap: { position: "relative" },
  // Eleva o wrap (e seu tooltip absoluto) por cima dos irmãos seguintes no
  // cabeçalho (ex.: outro botão-ícone, o "Gravar") — sem isso, o tooltip
  // ficava visualmente atrás desses irmãos por causa da ordem no DOM.
  // Só aplicado enquanto o tooltip daquele botão está visível.
  wrapHovered: { zIndex: 20 },
  tooltip: {
    position: "absolute", bottom: "100%", left: 0, right: 0, marginBottom: 4,
    alignItems: "center", zIndex: 10,
  },
  // Variante pros botões do cabeçalho (colados no topo da tela — "acima"
  // ficaria fora da viewport). Some com `tooltip` (não substitui), por
  // isso só sobrescreve bottom/marginBottom/top/marginTop.
  tooltipBelow: { bottom: undefined, marginBottom: 0, top: "100%", marginTop: 4 },
  tooltipInner: {
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  tooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  // Texto de ajuda em linguagem de usuário final — "Modo Didático", regra
  // [GLOBAL] em CLAUDE.md > "Padrões de UI" > "Telas complexas".
  helpText: { fontSize: 11, color: colors.muted, lineHeight: 15, marginTop: 2, marginBottom: spacing.xs },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm, width: "100%", maxWidth: 1120, alignSelf: "center" },
  sectionTitle: { fontSize: 14, fontWeight: "500", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  readonlyStrong: { fontWeight: "700", color: colors.brandPrimary },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 160 },
  colTiny: { width: 100 },
  switchField: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 11 },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, fontStyle: "italic" },
  descricaoResolvida: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  divider: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: spacing.sm, marginBottom: spacing.md },
  gridRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 10, paddingHorizontal: spacing.sm, borderRadius: radius.sm, borderWidth: 1, borderColor: "transparent", marginBottom: 6 },
  gridRowSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  gridRowText: { fontSize: 13, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  crudBtnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  crudBtn: { paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  crudBtnInline: { flexDirection: "row", alignItems: "center", gap: 6 },
  crudBtnText: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  radioRow: { flexDirection: "row", flexWrap: "wrap", gap: 8, marginTop: spacing.sm },
  radioBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  radioBtnSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  radioCircle: { width: 16, height: 16, borderRadius: 8, borderWidth: 1.5, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  radioCircleSel: { borderColor: colors.brandPrimary },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.brandPrimary },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  inputWithBtn: { flexDirection: "row", alignItems: "center", minWidth: 0, gap: 8 },
  cepBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.brandPrimary },

  actionsWrap: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.lg },
  secondaryActionBtn: {
    flexDirection: "row", alignItems: "center", gap: 8, flexGrow: 1, minWidth: 200,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12,
  },
  secondaryActionText: { flex: 1, fontSize: 13, fontWeight: "600", color: colors.onSurface },

  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  slideBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  slideCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, padding: spacing.lg, maxHeight: "85%" },
  slideCardWebCompact: {
    width: "100%", maxWidth: 640, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  slideTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },

  // Anexos precisa de mais largura que o tier padrão de modal (lista +
  // painel de preview lado a lado, mesma ressalva de "Full CRUD Form
  // Screen Standard" no CLAUDE.md) — mesma largura de AnexosPedidoModal.tsx.
  anexosBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", padding: spacing.xl },
  anexosCard: {
    width: "100%", maxWidth: 920, maxHeight: "88%",
    backgroundColor: colors.surface, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
    padding: spacing.lg,
  },
});
