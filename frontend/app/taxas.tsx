import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, Alert, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };

// Duas variantes da mesma tela/rotina (pedido explícito do usuário: não criar
// duas telas) — "nfe" grava em `taxas`, "nfce" em `taxas_nfce`. Permissão e
// log de auditoria são separados por variante (TAXAS.* / TAXAS_NFCE.*), mas
// o formulário e a lista são os mesmos componentes; campos que não existem na
// tabela `taxas_nfce` (Simples Nacional/Consumidor Final — 2 dos 6 campos da
// chave de negócio de `taxas` —, Protocolo ST, Tipo IPI, Alíq. Créd. Simples
// Nac., o grupo inteiro de PIS/COFINS atual e o bloco de DIFAL) ficam fora do
// formulário quando variante="nfce" (`{variante === "nfe" ? ... : null}` nos
// pontos correspondentes) — não é preferência visual, é porque a coluna não
// existe na tabela (ver nota grande em `tabelas_aux_service.CAMPOS_TAXAS_NFCE`
// no backend).
type Variante = "nfe" | "nfce";

type TaxaItem = {
  sequencia: number;
  destino: string;
  cfop: string;
  cod_icms: string;
  cod_icms_descricao: string;
  tipo_mov: string;
  tipo_mov_descricao: string;
  tributacao: string;
  icms: number;
  simples_nacional: boolean;
  consumidor_final: boolean;
  protocolo_st: boolean;
};

type LookupItem = { codigo: string; descricao: string };

// Lista de UF's do Brasil (não existe tabela própria no banco — legado usa
// um combo hardcoded no próprio `.frm`).
const UF_OPTS: SelectOption[] = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
  "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
].map((uf) => ({ value: uf, label: uf }));

// Motivos de desoneração de ICMS (tabela NFe padrão — não é uma tabela do
// banco, o legado usa um ListBox com itens hardcoded no próprio `.frm`).
const MOTIVO_DESONERADO_OPTS: SelectOption[] = [
  { value: "", label: "Sem Desoneração" },
  { value: "1", label: "1 - Táxi" },
  { value: "3", label: "3 - Produtor Agropecuário" },
  { value: "4", label: "4 - Frotista/Locadora" },
  { value: "5", label: "5 - Diplomático/Consular" },
  { value: "6", label: "6 - Utilitários e Motocicletas da Amazônia Ocidental e ALC" },
  { value: "7", label: "7 - SUFRAMA" },
  { value: "8", label: "8 - Venda a Órgãos Públicos" },
  { value: "9", label: "9 - Outros" },
  { value: "10", label: "10 - Deficiente Condutor" },
  { value: "11", label: "11 - Deficiente Não Condutor" },
  { value: "12", label: "12 - Táxi" },
  { value: "14", label: "14 - Combustíveis" },
  { value: "15", label: "15 - ZFM/ALC" },
  { value: "16", label: "16 - Olimpíadas Rio 2016" },
  { value: "90", label: "90 - Outros" },
];

const BOOL_FIELDS = [
  "Simples_Nacional", "consumidor_final", "protocolo_st", "tipo_ipi", "INFORMA_BENEFICIO_FISCAL",
  "REDUCAO_BASE_PIS_COFINS", "PIS_COFINS_CUSTO_X_VENDA", "INFORMA_CBS_IBS",
  "GRUPO_DIFERIMENTO_IBS_ESTADO", "GRUPO_REDUCAO_IBS_ESTADO",
  "GRUPO_DIFERIMENTO_IBS_MUNICIPIO", "GRUPO_REDUCAO_IBS_MUNICIPIO",
  "GRUPO_DIFERIMENTO_CBS_ESTADO", "GRUPO_REDUCAO_CBS_ESTADO",
  "GTRIBREGULAR", "gMonoPadrao", "gMonoReten", "gMonoRet", "gMonoDif",
] as const;

const NUM_FIELDS = [
  "icms", "reducao_base_icms", "icms_substituicao", "margem_icms_substituicao", "reducao_base_retido",
  "ALQT_FCP", "ALQT_FCP_RETIDO", "ALQT_FCP_ST", "ALQT_CF", "ALQT_CRED_SN",
  "ALQT_TRIB_PIS", "ALQT_TRIB_COFINS",
  "ICMS_SUBSTITUTO", "ALQT_ICMS_EFETIVO", "MARGEM_ICMS_EFETIVO", "REDUCAO_ICMS_EFETIVO",
  "dif_icms_bens", "ALQT_ICMS_DESONERADO",
  "aliquota_interestadual", "aliquota_interna_destino", "percentual_origem", "fundo_pobreza",
  "ALQT_IS", "ALQT_IBS_ESTADO", "PERC_DIFERIMENTO_IBS_ESTADO", "PERC_REDUCAO_IBS_ESTADO", "ALQT_EFETIVA_REDUCAO_IBS_ESTADO",
  "ALQT_IBS_MUNICIPIO", "PERC_DIFERIMENTO_IBS_MUNICIPIO", "PERC_REDUCAO_IBS_MUNICIPIO", "ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO",
  "ALQT_CBS_ESTADO", "PERC_DIFERIMENTO_CBS_ESTADO", "PERC_REDUCAO_CBS_ESTADO", "ALQT_EFETIVA_REDUCAO_CBS_ESTADO",
  "ALQT_ADREM_PADRAO_IBS", "ALQT_ADREM_PADRAO_CBS", "ALQT_ADREM_RETENCAO_IBS", "ALQT_ADREM_RETENCAO_CBS",
  "ALQT_ADREM_RETIDO_IBS", "ALQT_ADREM_RETIDO_CBS", "ALQT_ADREM_DIFERIMENTO_IBS", "ALQT_ADREM_DIFERIMENTO_CBS",
] as const;

const TEXT_FIELDS = [
  "CST_TRIB_PIS", "CST_TRIB_COFINS", "MOTIVO_ICMS_DESONERADO",
  "CST_IS", "CCLASSTRIB_IS", "CST_IBS", "CCLASSTRIB_IBS",
] as const;

type TaxaForm = Record<string, string | boolean>;

const emptyForm = (): TaxaForm => {
  const f: TaxaForm = { destino: "", cfop: "", cod_icms: "", tipo_mov: "", tributacao: "" };
  for (const k of BOOL_FIELDS) f[k] = false;
  for (const k of NUM_FIELDS) f[k] = "";
  for (const k of TEXT_FIELDS) f[k] = "";
  return f;
};

const toFloat = (s: string | boolean): number => {
  const v = parseFloat(String(s ?? "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};

type FieldProps = { form: TaxaForm; setField: (k: string, v: string | boolean) => void };

// Componentes de campo definidos FORA de TaxasScreen (nível de módulo) —
// se ficassem declarados dentro do corpo do componente, cada re-render
// (ex.: a cada tecla digitada) criaria uma NOVA referência de função pra
// cada um, e o React trataria isso como um componente de tipo diferente,
// desmontando e remontando toda a subárvore (TextInput perde o foco, o
// scroll pula) a cada caractere digitado. `form`/`setField` chegam via
// props em vez de closure por isso mesmo.
function NumField({ form, setField, campo, label, decimais = 2, placeholder, disabled = false }: FieldProps & { campo: string; label: string; decimais?: number; placeholder?: string; disabled?: boolean }) {
  return (
    <View style={styles.colThird}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={String(form[campo] ?? "")}
        onChangeText={(v) => setField(campo, v.replace(/[^0-9,.-]/g, ""))}
        keyboardType="decimal-pad"
        placeholder={placeholder ?? (decimais === 4 ? "0,0000" : "0,00")}
        placeholderTextColor={colors.muted}
        editable={!disabled}
        style={[styles.input, disabled && styles.inputDisabled]}
        testID={`taxas-${campo}`}
      />
    </View>
  );
}

function Chk({ form, setField, campo, label }: FieldProps & { campo: string; label: string }) {
  return (
    <View style={styles.switchRow}>
      <Switch value={!!form[campo]} onValueChange={(v) => setField(campo, v)} testID={`taxas-${campo}-switch`} />
      <Text style={styles.switchLabel}>{label}</Text>
    </View>
  );
}

// Checkbox + campo(s) numéricos diretamente relacionados, lado a lado e
// próximos na mesma linha (ex.: "Monofásico Padrão" + Alíquotas AdRem
// IBS/CBS, ou "Grupo Diferimento" + "% Diferimento") — pedido explícito
// do usuário pra não separar visualmente controles que têm relação entre
// si. Os campos filhos só ficam editáveis quando o checkbox está marcado
// (também pedido explícito: "só ativar os campos pra preenchimento
// quando sua checkbox correlacionada for check true"), e ao DESMARCAR o
// checkbox os campos filhos são limpos (zerados) — não basta desabilitar
// visualmente, o valor antigo não pode continuar "escondido" no form e
// ser gravado do mesmo jeito. Regra pra seguir também em seções futuras
// do formulário.
function ChkRow({ form, setField, campo, label, children }: FieldProps & { campo: string; label: string; children?: React.ReactNode }) {
  const checked = !!form[campo];
  const handleToggle = (v: boolean) => {
    setField(campo, v);
    if (!v) {
      React.Children.forEach(children, (child) => {
        if (React.isValidElement(child)) {
          const childCampo = (child.props as { campo?: string }).campo;
          if (childCampo) setField(childCampo, "");
        }
      });
    }
  };
  return (
    <View style={styles.chkRow}>
      <View style={styles.chkRowLabel}>
        <Switch value={checked} onValueChange={handleToggle} testID={`taxas-${campo}-switch`} />
        <Text style={styles.switchLabel}>{label}</Text>
      </View>
      <View style={styles.chkRowFields}>
        {React.Children.map(children, (child) =>
          React.isValidElement(child) ? React.cloneElement(child as React.ReactElement<{ disabled?: boolean }>, { disabled: !checked }) : child
        )}
      </View>
    </View>
  );
}

function SectionTitle({ children }: { children: string }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

// Cadastro/Tabelas Auxiliares > Taxas (tabela `taxas`). Legado: FrmManTaxas
// ("Manutenção de Taxas"). A tabela mais complexa desta leva: ~80 campos de
// alíquotas/regras fiscais, chave de negócio (destino+cfop+cod_icms+tipo_mov+
// Simples_Nacional+consumidor_final) sem unique constraint no banco — igual
// ao legado, é o app que impede duplicidade (ver `_save_taxa_sync`).
//
// **Achado importante**: o checkbox rotulado "Não Contribuinte" no legado
// (`Check1`) na verdade grava/lê sempre a coluna `Simples_Nacional` — não
// existe coluna "não contribuinte" na tabela. Confirmado direto no
// `FrmManTaxas.frm` (INSERT/UPDATE/SELECT usam `IIf(Check1.Value=1,1,0)` →
// sempre a coluna simples_nacional). Por isso este campo aparece aqui já
// rotulado como "Simples Nacional" — mesma categoria de bug de
// legado/coluna já documentada em Cliente (credita_icms/nao_contribuinte).
//
// Campos do legado deliberadamente fora de escopo (por já estarem com
// `Visible = 0 'False` no `.frm` atual, confirmado controle a controle):
// tipo_destino (auto-derivado de tipo_mov.origem_destino no save),
// tributacao_livro (sempre gravado 1), cfop_livro (sempre = cfop),
// cod_contabil e icms_operacao (campo e rótulo ocultos),
// margem_icms_recolher/icms_operacao_recolher/icms_recolher (ocultos).
// `CST_CBS` (coluna existe mas nunca é gravada por este form — a seção
// Reforma Tributária usa um único par CST/ClassTrib pra IBS e CBS) e
// `gIBSCBSMono`/`ADREM_ICMS` (colunas existentes no banco mas nunca
// referenciadas neste `.frm`) também ficam de fora.
export default function TaxasScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Taxas está disponível apenas no web."
        testID="taxas-web-only"
      />
    );
  }

  const canAbrirNfe = can("TAXAS.ABRIR") || isMaster;
  const canAbrirNfce = can("TAXAS_NFCE.ABRIR") || isMaster;
  const [variante, setVariante] = useState<Variante>(canAbrirNfe ? "nfe" : "nfce");

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<TaxaItem[]>([]);
  const [loading, setLoading] = useState(false);

  const [tipoMovOptions, setTipoMovOptions] = useState<LookupItem[]>([]);
  const [dscrIcmsOptions, setDscrIcmsOptions] = useState<LookupItem[]>([]);
  const [tributacaoOptions, setTributacaoOptions] = useState<LookupItem[]>([]);

  // Combos em cascata de CST/ClassTrib do IBS/CBS (tabela nacional
  // `classtrib`) — pedido explícito do usuário pra facilitar o
  // preenchimento: escolher o CST filtra as opções de ClassTrib.
  const [classtribCstOptions, setClasstribCstOptions] = useState<{ cst: string; descricao: string }[]>([]);
  const [classtribOptions, setClasstribOptions] = useState<{ cclasstrib: string; nome: string }[]>([]);

  // Opções dos combos de FILTRO da grade (distinto de tipoMovOptions/
  // dscrIcmsOptions acima, usados no formulário) — só trazem valores que
  // realmente têm ao menos uma taxa cadastrada, em cascata Tipo Mov → UF →
  // Código de ICMS. Pedido explícito do usuário: não obrigar a pesquisar
  // "VENDA", "DEVOLUÇÃO" etc. numa lista cheia de tipo_mov sem relação com
  // o que já está cadastrado.
  const [filtroOpcoes, setFiltroOpcoes] = useState<{ tipoMov: LookupItem[]; destino: string[]; codIcms: LookupItem[] }>({ tipoMov: [], destino: [], codIcms: [] });
  const [companyUf, setCompanyUf] = useState<string | null>(null);
  const ufDefaultAppliedRef = useRef(false);

  const [filtroTipoMov, setFiltroTipoMov] = useState<string | null>(null);
  const [filtroDestino, setFiltroDestino] = useState<string | null>(null);
  const [filtroCodIcms, setFiltroCodIcms] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editSequencia, setEditSequencia] = useState<number | null>(null);
  const [form, setForm] = useState<TaxaForm>(emptyForm());
  const [saving, setSaving] = useState(false);
  const [consultandoClasstrib, setConsultandoClasstrib] = useState(false);

  const setField = (k: string, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));

  const base = conn ? conn.api.replace(/\/+$/, "") : "";
  const qsBase = conn ? `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` : "";

  const load = useCallback(async (c: Conn, variante: Variante, tipoMov: string | null, destino: string | null, codIcms: string | null) => {
    setLoading(true);
    try {
      const b = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&variante=${variante}` +
        `&tipo_mov=${encodeURIComponent(tipoMov || "")}&destino=${encodeURIComponent(destino || "")}&cod_icms=${encodeURIComponent(codIcms || "")}`;
      const r = await fetch(`${b}/api/tabelas/taxas?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const b = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const fetchLookup = async (path: string, setter: (items: LookupItem[]) => void) => {
      try {
        const r = await fetch(`${b}${path}?${qs}`);
        const j = await r.json();
        if (j?.success && Array.isArray(j.items)) setter(j.items);
      } catch { /* silencioso — lookup opcional */ }
    };
    await Promise.all([
      fetchLookup("/api/tabelas/tipo-mov", setTipoMovOptions),
      fetchLookup("/api/tabelas/dscr-icms", setDscrIcmsOptions),
      fetchLookup("/api/tabelas/tributacao", setTributacaoOptions),
    ]);
  }, []);

  const loadFiltroOpcoes = useCallback(async (c: Conn, variante: Variante, tipoMov: string | null, destino: string | null) => {
    try {
      const b = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&variante=${variante}` +
        `&tipo_mov=${encodeURIComponent(tipoMov || "")}&destino=${encodeURIComponent(destino || "")}`;
      const r = await fetch(`${b}/api/tabelas/taxas-opcoes-filtro?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setFiltroOpcoes({ tipoMov: j.tipo_mov || [], destino: j.destino || [], codIcms: j.cod_icms || [] });
        return j;
      }
    } catch { /* silencioso */ }
    return null;
  }, []);

  const loadClasstribOpcoes = useCallback(async (c: Conn, cst: string) => {
    try {
      const b = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&cst=${encodeURIComponent(cst)}`;
      const r = await fetch(`${b}/api/tabelas/classtrib/opcoes?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setClasstribCstOptions(j.cst || []);
        setClasstribOptions(j.classtrib || []);
      }
    } catch { /* silencioso */ }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc, variante, null, null, null);
      loadLookups(cc);
      loadClasstribOpcoes(cc, "");

      const b = cc.api.replace(/\/+$/, "");
      const qsEmpresa = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
      fetch(`${b}/api/controle/empresa?${qsEmpresa}`)
        .then((r) => r.json())
        .then((j) => { if (j?.success) setCompanyUf(j.uf || null); })
        .catch(() => {});

      // Default pedido pelo usuário: Tipo de Movimentação já vem marcado
      // como "VENDA" (S01) ao abrir a tela — só se essa opção realmente
      // existir entre as que têm taxa cadastrada.
      const opts = await loadFiltroOpcoes(cc, variante, null, null);
      if (opts?.success) {
        const temVenda = (opts.tipo_mov || []).some((o: LookupItem) => o.codigo === "S01");
        if (temVenda) setFiltroTipoMov("S01");
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, load, loadLookups, loadFiltroOpcoes, loadClasstribOpcoes]);

  // Reconsulta as opções de ClassTrib sempre que o CST do IBS/CBS muda —
  // relação real 1-CST-pra-N-ClassTrib na tabela nacional `classtrib`.
  useEffect(() => {
    if (!conn || !formOpen) return;
    loadClasstribOpcoes(conn, String(form.CST_IBS || ""));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, formOpen, form.CST_IBS]);

  // Recarrega as opções de filtro em cascata (Tipo Mov → UF → Cód. ICMS) e
  // limpa seleções que deixaram de existir na combinação atual. O default
  // de UF (UF cadastrada da empresa) só é aplicado uma vez, na primeira
  // carga — depois disso, escolhas manuais do usuário não são sobrescritas.
  useEffect(() => {
    if (!conn) return;
    (async () => {
      const opts = await loadFiltroOpcoes(conn, variante, filtroTipoMov, filtroDestino);
      if (!opts?.success) return;
      const destinoList: string[] = opts.destino || [];
      if (filtroDestino && !destinoList.includes(filtroDestino)) {
        setFiltroDestino(null);
        return;
      }
      if (!ufDefaultAppliedRef.current && !filtroDestino && companyUf && destinoList.includes(companyUf)) {
        ufDefaultAppliedRef.current = true;
        setFiltroDestino(companyUf);
        return;
      }
      const codIcmsList = (opts.cod_icms || []).map((i: LookupItem) => i.codigo);
      if (filtroCodIcms && !codIcmsList.includes(filtroCodIcms)) setFiltroCodIcms(null);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variante, filtroTipoMov, filtroDestino, companyUf]);

  useEffect(() => {
    if (!conn) return;
    load(conn, variante, filtroTipoMov, filtroDestino, filtroCodIcms);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variante, filtroTipoMov, filtroDestino, filtroCodIcms]);

  // Troca de variante (NFe/NFSe <-> NFCe) — mesma tela, outra tabela: limpa
  // filtros e fecha o formulário aberto, pra não deixar o usuário editando um
  // registro de uma variante enquanto olha a grade da outra.
  const switchVariante = async (v: Variante) => {
    if (v === variante) return;
    setVariante(v);
    setFiltroTipoMov(null);
    setFiltroDestino(null);
    setFiltroCodIcms(null);
    ufDefaultAppliedRef.current = false;
    setFormOpen(false);

    // Mesmo default aplicado na primeira carga da tela (ver efeito de
    // montagem acima): Tipo de Movimentação já vem marcado como "VENDA"
    // (S01), se essa opção existir entre as que têm taxa cadastrada pra
    // tabela da variante escolhida. Sem isso o combo ficava em "Todos" ao
    // trocar de aba e continuava assim ao voltar pra variante original.
    if (!conn) return;
    const opts = await loadFiltroOpcoes(conn, v, null, null);
    if (opts?.success) {
      const temVenda = (opts.tipo_mov || []).some((o: LookupItem) => o.codigo === "S01");
      if (temVenda) setFiltroTipoMov("S01");
    }
  };

  const openNew = () => {
    setEditSequencia(null);
    setForm(emptyForm());
    setFormOpen(true);
  };

  const openEdit = async (item: TaxaItem) => {
    if (!conn) return;
    setEditSequencia(item.sequencia);
    setFormOpen(true);
    try {
      const r = await fetch(`${base}/api/tabelas/taxas/${item.sequencia}?${qsBase}&variante=${variante}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d = j.taxa;
      const f = emptyForm();
      f.destino = d.destino || ""; f.cfop = d.cfop || ""; f.cod_icms = d.cod_icms || ""; f.tipo_mov = d.tipo_mov || "";
      f.tributacao = d.tributacao || "";
      for (const k of BOOL_FIELDS) f[k] = !!d[k];
      for (const k of NUM_FIELDS) f[k] = String(d[k] ?? 0);
      for (const k of TEXT_FIELDS) f[k] = d[k] || "";
      setForm(f);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const consultarClasstrib = async () => {
    if (!conn) return;
    const cst = String(form.CST_IBS || "").trim();
    const cclasstrib = String(form.CCLASSTRIB_IBS || "").trim();
    if (!cst || !cclasstrib) { fb.showWarning("Informe CST e ClassTrib do IBS/CBS antes de consultar."); return; }
    setConsultandoClasstrib(true);
    try {
      const qs = `${qsBase}&cst=${encodeURIComponent(cst)}&cclasstrib=${encodeURIComponent(cclasstrib)}`;
      const r = await fetch(`${base}/api/tabelas/classtrib/lookup?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Combinação não encontrada."); return; }
      setForm((f) => ({
        ...f,
        PERC_REDUCAO_IBS_ESTADO: String(j.pred_ibs ?? 0),
        PERC_REDUCAO_CBS_ESTADO: String(j.pred_cbs ?? 0),
        GTRIBREGULAR: !!j.g_trib_regular,
        gMonoPadrao: !!j.g_mono_padrao,
        gMonoReten: !!j.g_mono_reten,
        gMonoRet: !!j.g_mono_ret,
        gMonoDif: !!j.g_mono_dif,
      }));
      fb.showSuccess("Percentuais e grupos de tributação preenchidos.");
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setConsultandoClasstrib(false);
    }
  };

  const save = async () => {
    if (!conn) return;
    if (!form.destino) { fb.showWarning("Selecione a UF."); return; }
    if (!String(form.cfop).trim()) { fb.showWarning("Preenchimento Obrigatório: CFOP"); return; }
    if (!form.cod_icms) { fb.showWarning("Defina o Código de ICMS."); return; }
    if (!form.tipo_mov) { fb.showWarning("Preenchimento Obrigatório: Movimentação"); return; }
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        servidor: conn.servidor, banco: conn.banco, ...auditCtx,
        variante,
        sequencia: editSequencia,
        destino: form.destino, cfop: form.cfop, cod_icms: form.cod_icms, tipo_mov: form.tipo_mov,
        tributacao: form.tributacao || null,
      };
      for (const k of BOOL_FIELDS) payload[k] = !!form[k];
      for (const k of NUM_FIELDS) payload[k] = toFloat(form[k]);
      for (const k of TEXT_FIELDS) payload[k] = form[k] || null;

      const r = await fetch(`${base}/api/tabelas/taxas`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Registro gravado.");
        setFormOpen(false);
        load(conn, variante, filtroTipoMov, filtroDestino, filtroCodIcms);
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: TaxaItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão da taxa ${item.destino}/${item.cfop}/${item.cod_icms}/${item.tipo_mov}?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir", style: "destructive",
        onPress: async () => {
          try {
            const r = await fetch(`${base}/api/tabelas/taxas/${item.sequencia}/excluir`, {
              method: "POST", headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, variante, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn, variante, filtroTipoMov, filtroDestino, filtroCodIcms); }
            else fb.showError(j?.message || "Falha ao excluir.");
          } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
        },
      },
    ]);
  };

  const canSave = variante === "nfe" ? (can("TAXAS.GRAVAR") || isMaster) : (can("TAXAS_NFCE.GRAVAR") || isMaster);
  const canDel = variante === "nfe" ? (can("TAXAS.EXCLUIR") || isMaster) : (can("TAXAS_NFCE.EXCLUIR") || isMaster);

  const tipoMovOpts = useMemo<SelectOption[]>(
    () => tipoMovOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
    [tipoMovOptions]
  );
  const dscrIcmsOpts = useMemo<SelectOption[]>(
    () => dscrIcmsOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
    [dscrIcmsOptions]
  );
  const tributacaoOpts = useMemo<SelectOption[]>(
    () => tributacaoOptions.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
    [tributacaoOptions]
  );

  const filtroTipoMovOpts = useMemo<SelectOption[]>(
    () => filtroOpcoes.tipoMov.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
    [filtroOpcoes.tipoMov]
  );
  const filtroDestinoOpts = useMemo<SelectOption[]>(
    () => filtroOpcoes.destino.map((uf) => ({ value: uf, label: uf })),
    [filtroOpcoes.destino]
  );
  const filtroCodIcmsOpts = useMemo<SelectOption[]>(
    () => filtroOpcoes.codIcms.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
    [filtroOpcoes.codIcms]
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="taxas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Taxas</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={WEB_CONTENT_SHELL}>
          {canAbrirNfe && canAbrirNfce ? (
            <View style={styles.varTabs} testID="taxas-variante-tabs">
              <Pressable
                onPress={() => switchVariante("nfe")}
                style={[styles.varTab, variante === "nfe" && styles.varTabActive]}
                testID="taxas-variante-nfe"
              >
                <Text style={[styles.varTabText, variante === "nfe" && styles.varTabTextActive]}>Taxas NFe/NFSe</Text>
              </Pressable>
              <Pressable
                onPress={() => switchVariante("nfce")}
                style={[styles.varTab, variante === "nfce" && styles.varTabActive]}
                testID="taxas-variante-nfce"
              >
                <Text style={[styles.varTabText, variante === "nfce" && styles.varTabTextActive]}>Taxas NFCe</Text>
              </Pressable>
            </View>
          ) : null}

          <View style={[WEB_FILTER_CARD, { marginBottom: spacing.md }]}>
            <Text style={styles.filterTitle}>Filtros{variante === "nfce" ? " — Taxas NFCe" : " — Taxas NFe/NFSe"}</Text>
            <View style={styles.rowFields}>
              <View style={styles.colThird}>
                <Text style={styles.label}>Tipo de Movimentação</Text>
                <SelectField value={filtroTipoMov} onChange={(v) => setFiltroTipoMov(v == null ? null : String(v))} options={filtroTipoMovOpts} placeholder="Todos" allowClear compactWeb testID="taxas-filtro-tipo-mov" modalTitle="Tipo de Movimentação" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>UF</Text>
                <SelectField value={filtroDestino} onChange={(v) => setFiltroDestino(v == null ? null : String(v))} options={filtroDestinoOpts} placeholder="Todas" allowClear compactWeb testID="taxas-filtro-uf" modalTitle="UF" />
              </View>
              <View style={styles.colThird}>
                <Text style={styles.label}>Código de ICMS</Text>
                <SelectField value={filtroCodIcms} onChange={(v) => setFiltroCodIcms(v == null ? null : String(v))} options={filtroCodIcmsOpts} placeholder="Todos" allowClear compactWeb testID="taxas-filtro-cod-icms" modalTitle="Código de ICMS" />
              </View>
            </View>
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma taxa cadastrada para esse filtro.</Text> : null}
          {!loading ? items.map((it) => (
            <View key={it.sequencia} style={styles.row} testID={`taxas-item-${it.sequencia}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <Text style={styles.rowTitle}>
                  {it.destino} · CFOP {it.cfop} · ICMS {it.cod_icms}{it.cod_icms_descricao ? ` (${it.cod_icms_descricao})` : ""}
                </Text>
                <Text style={styles.rowSub}>
                  {it.tipo_mov_descricao || it.tipo_mov} · Tributação {it.tributacao || "—"} · ICMS {it.icms.toFixed(2)}%
                  {it.simples_nacional ? " · Simples Nacional" : ""}{it.consumidor_final ? " · Consumidor Final" : ""}
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`taxas-del-${it.sequencia}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          )) : null}
        </View>
      </ScrollView>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="taxas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>
              {editSequencia ? "Editar Taxa" : "Nova Taxa"}{variante === "nfce" ? " (NFCe)" : " (NFe/NFSe)"}
            </Text>
            <ScrollView showsVerticalScrollIndicator={false}>

              <SectionTitle>Identificação</SectionTitle>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>UF *</Text>
                  <SelectField value={form.destino as string} onChange={(v) => setField("destino", v ? String(v) : "")} options={UF_OPTS} placeholder="Selecione a UF" compactWeb testID="taxas-destino" modalTitle="UF" />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>CFOP *</Text>
                  <TextInput value={form.cfop as string} onChangeText={(v) => setField("cfop", v.replace(/[^0-9]/g, ""))} placeholder="Ex.: 5102" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" maxLength={4} testID="taxas-cfop" />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Código de ICMS *</Text>
                  <SelectField value={form.cod_icms as string} onChange={(v) => setField("cod_icms", v ? String(v) : "")} options={dscrIcmsOpts} placeholder="Selecione o Código de ICMS" compactWeb testID="taxas-cod-icms" modalTitle="Código de ICMS" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tipo de Movimentação *</Text>
                  <SelectField value={form.tipo_mov as string} onChange={(v) => setField("tipo_mov", v ? String(v) : "")} options={tipoMovOpts} placeholder="Selecione o Tipo de Movimentação" compactWeb testID="taxas-tipo-mov" modalTitle="Tipo de Movimentação" />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>Tributação</Text>
                  <SelectField value={form.tributacao as string} onChange={(v) => setField("tributacao", v ? String(v) : "")} options={tributacaoOpts} placeholder="Selecione a Tributação (opcional)" allowClear compactWeb testID="taxas-tributacao" modalTitle="Tributação" />
                </View>
              </View>
              {variante === "nfe" ? (
                <>
                  <Chk form={form} setField={setField} campo="Simples_Nacional" label="Simples Nacional" />
                  <Chk form={form} setField={setField} campo="consumidor_final" label="Consumidor Final" />
                </>
              ) : null}

              <SectionTitle>Principais ICMS</SectionTitle>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="icms" label="Alíquota ICMS %" placeholder="Ex.: 18,00" />
                <NumField form={form} setField={setField} campo="reducao_base_icms" label="Redução Base %" />
                <NumField form={form} setField={setField} campo="icms_substituicao" label="Alíquota ICMS ST %" decimais={4} />
              </View>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="margem_icms_substituicao" label="Margem ST %" />
                <NumField form={form} setField={setField} campo="reducao_base_retido" label="Redução Base Retido %" />
                <NumField form={form} setField={setField} campo="ALQT_FCP" label="Alíquota FCP %" />
              </View>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="ALQT_FCP_RETIDO" label="Alíquota FCP Retido %" />
                <NumField form={form} setField={setField} campo="ALQT_FCP_ST" label="Alíquota FCP ST %" />
                <NumField form={form} setField={setField} campo="ALQT_CF" label="Alíquota CF %" />
              </View>
              {variante === "nfe" ? (
                <View style={styles.rowFields}>
                  <NumField form={form} setField={setField} campo="ALQT_CRED_SN" label="Alíq. Créd. Simples Nac. (201/900)" />
                </View>
              ) : null}
              {variante === "nfe" ? (
                <>
                  <Chk form={form} setField={setField} campo="protocolo_st" label="Protocolo ST" />
                  <Chk form={form} setField={setField} campo="tipo_ipi" label="Tipo IPI (Produtor/Fabricante)" />
                </>
              ) : null}
              <Chk form={form} setField={setField} campo="INFORMA_BENEFICIO_FISCAL" label="Informa Benefício Fiscal" />

              {variante === "nfe" ? (
                <>
                  <SectionTitle>Grupo PIS/COFINS</SectionTitle>
                  <Chk form={form} setField={setField} campo="REDUCAO_BASE_PIS_COFINS" label="Redução Base PIS/COFINS" />
                  <View style={styles.rowFields}>
                    <View style={styles.colThird}>
                      <Text style={styles.label}>CST PIS</Text>
                      <TextInput value={form.CST_TRIB_PIS as string} onChangeText={(v) => setField("CST_TRIB_PIS", v)} placeholder="Ex.: 01" placeholderTextColor={colors.muted} style={styles.input} maxLength={2} keyboardType="number-pad" testID="taxas-cst-pis" />
                    </View>
                    <NumField form={form} setField={setField} campo="ALQT_TRIB_PIS" label="Alíquota PIS %" decimais={4} placeholder="Ex.: 1,65" />
                    <View style={styles.colThird}>
                      <Text style={styles.label}>CST COFINS</Text>
                      <TextInput value={form.CST_TRIB_COFINS as string} onChangeText={(v) => setField("CST_TRIB_COFINS", v)} placeholder="Ex.: 01" placeholderTextColor={colors.muted} style={styles.input} maxLength={2} keyboardType="number-pad" testID="taxas-cst-cofins" />
                    </View>
                  </View>
                  <View style={styles.rowFields}>
                    <NumField form={form} setField={setField} campo="ALQT_TRIB_COFINS" label="Alíquota COFINS %" decimais={4} placeholder="Ex.: 7,60" />
                  </View>
                  <Chk form={form} setField={setField} campo="PIS_COFINS_CUSTO_X_VENDA" label="PIS/COFINS Custo x Venda" />
                </>
              ) : null}

              <SectionTitle>ICMS Substituto / Efetivo / Desonerado</SectionTitle>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="ICMS_SUBSTITUTO" label="ICMS Substituto %" />
                <NumField form={form} setField={setField} campo="ALQT_ICMS_EFETIVO" label="Alíquota ICMS Efetivo %" />
                <NumField form={form} setField={setField} campo="MARGEM_ICMS_EFETIVO" label="Margem ICMS Efetivo %" />
              </View>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="REDUCAO_ICMS_EFETIVO" label="Redução ICMS Efetivo %" />
                <NumField form={form} setField={setField} campo="dif_icms_bens" label="Diferimento ICMS Bens %" />
                <NumField form={form} setField={setField} campo="ALQT_ICMS_DESONERADO" label="Alíquota ICMS Desonerado %" />
              </View>
              <Text style={styles.label}>Motivo da Desoneração</Text>
              <SelectField value={(form.MOTIVO_ICMS_DESONERADO as string) || ""} onChange={(v) => setField("MOTIVO_ICMS_DESONERADO", v ? String(v) : "")} options={MOTIVO_DESONERADO_OPTS} placeholder="Selecione o motivo (se houver desoneração)" compactWeb testID="taxas-motivo-desonerado" modalTitle="Motivo da Desoneração" />

              {variante === "nfe" ? (
                <>
                  <SectionTitle>Grupo de ICMS para UF de Destino (DIFAL)</SectionTitle>
                  <View style={styles.rowFields}>
                    <NumField form={form} setField={setField} campo="aliquota_interestadual" label="Alíquota Interestadual %" placeholder="Ex.: 12,00" />
                    <NumField form={form} setField={setField} campo="aliquota_interna_destino" label="Alíquota Interna Destino %" placeholder="Ex.: 18,00" />
                  </View>
                  <View style={styles.rowFields}>
                    <NumField form={form} setField={setField} campo="percentual_origem" label="% Partilha Origem" />
                    <NumField form={form} setField={setField} campo="fundo_pobreza" label="Fundo de Pobreza %" placeholder="Ex.: 2,00" />
                  </View>
                </>
              ) : null}

              <SectionTitle>Reforma Tributária (IBS / CBS / IS)</SectionTitle>
              <Chk form={form} setField={setField} campo="INFORMA_CBS_IBS" label="Informa CBS/IBS" />

              <Text style={styles.subSectionTitle}>Imposto Seletivo (IS)</Text>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>CST IS</Text>
                  <TextInput value={form.CST_IS as string} onChangeText={(v) => setField("CST_IS", v)} placeholder="Ex.: 000" placeholderTextColor={colors.muted} style={styles.input} maxLength={3} testID="taxas-cst-is" />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>ClassTrib IS</Text>
                  <TextInput value={form.CCLASSTRIB_IS as string} onChangeText={(v) => setField("CCLASSTRIB_IS", v)} placeholder="Ex.: 000001" placeholderTextColor={colors.muted} style={styles.input} maxLength={6} testID="taxas-classtrib-is" />
                </View>
                <NumField form={form} setField={setField} campo="ALQT_IS" label="Alíquota IS %" decimais={4} />
              </View>

              <Text style={styles.subSectionTitle}>IBS / CBS — CST e ClassTrib</Text>
              <View style={styles.rowFields}>
                <View style={styles.colThird}>
                  <Text style={styles.label}>CST IBS/CBS</Text>
                  <SelectField
                    value={(form.CST_IBS as string) || ""}
                    onChange={(v) => {
                      setField("CST_IBS", v ? String(v) : "");
                      setField("CCLASSTRIB_IBS", "");
                    }}
                    options={classtribCstOptions.map((o) => ({ value: o.cst, label: `${o.cst} - ${o.descricao}` }))}
                    allowClear
                    placeholder="Selecione o CST"
                    compactWeb
                    testID="taxas-cst-ibs"
                    modalTitle="CST IBS/CBS"
                  />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}>ClassTrib IBS/CBS</Text>
                  <SelectField
                    value={(form.CCLASSTRIB_IBS as string) || ""}
                    onChange={(v) => setField("CCLASSTRIB_IBS", v ? String(v) : "")}
                    options={classtribOptions.map((o) => ({ value: o.cclasstrib, label: `${o.cclasstrib} - ${o.nome}` }))}
                    allowClear
                    disabled={!form.CST_IBS}
                    placeholder={form.CST_IBS ? "Selecione o ClassTrib" : "Selecione o CST primeiro"}
                    compactWeb
                    testID="taxas-classtrib-ibs"
                    modalTitle="ClassTrib IBS/CBS"
                  />
                </View>
                <View style={styles.colThird}>
                  <Text style={styles.label}> </Text>
                  <Pressable onPress={consultarClasstrib} disabled={consultandoClasstrib} style={[styles.secondaryBtn, consultandoClasstrib && { opacity: 0.6 }]} testID="taxas-consultar-classtrib">
                    {consultandoClasstrib ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.secondaryBtnText}>Consultar ClassTrib</Text>}
                  </Pressable>
                </View>
              </View>

              <Text style={styles.subSectionTitle}>Grupo Tributação (Monofásica) e Alíquotas AdRem</Text>
              <ChkRow form={form} setField={setField} campo="GTRIBREGULAR" label="Tributação Regular" />
              <ChkRow form={form} setField={setField} campo="gMonoPadrao" label="Monofásico Padrão">
                <NumField form={form} setField={setField} campo="ALQT_ADREM_PADRAO_IBS" label="AdRem IBS %" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_ADREM_PADRAO_CBS" label="AdRem CBS %" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="gMonoReten" label="Monofásico Retenção">
                <NumField form={form} setField={setField} campo="ALQT_ADREM_RETENCAO_IBS" label="AdRem IBS %" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_ADREM_RETENCAO_CBS" label="AdRem CBS %" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="gMonoRet" label="Monofásico Retido">
                <NumField form={form} setField={setField} campo="ALQT_ADREM_RETIDO_IBS" label="AdRem IBS %" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_ADREM_RETIDO_CBS" label="AdRem CBS %" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="gMonoDif" label="Monofásico Diferimento">
                <NumField form={form} setField={setField} campo="ALQT_ADREM_DIFERIMENTO_IBS" label="AdRem IBS %" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_ADREM_DIFERIMENTO_CBS" label="AdRem CBS %" decimais={4} />
              </ChkRow>

              <Text style={styles.subSectionTitle}>IBS Estado</Text>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="ALQT_IBS_ESTADO" label="Alíquota %" decimais={4} />
              </View>
              <ChkRow form={form} setField={setField} campo="GRUPO_DIFERIMENTO_IBS_ESTADO" label="Grupo Diferimento">
                <NumField form={form} setField={setField} campo="PERC_DIFERIMENTO_IBS_ESTADO" label="% Diferimento" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="GRUPO_REDUCAO_IBS_ESTADO" label="Grupo Redução">
                <NumField form={form} setField={setField} campo="PERC_REDUCAO_IBS_ESTADO" label="% Redução" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_EFETIVA_REDUCAO_IBS_ESTADO" label="Alíq. Efetiva Redução %" decimais={4} />
              </ChkRow>

              <Text style={styles.subSectionTitle}>IBS Município</Text>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="ALQT_IBS_MUNICIPIO" label="Alíquota %" decimais={4} />
              </View>
              <ChkRow form={form} setField={setField} campo="GRUPO_DIFERIMENTO_IBS_MUNICIPIO" label="Grupo Diferimento">
                <NumField form={form} setField={setField} campo="PERC_DIFERIMENTO_IBS_MUNICIPIO" label="% Diferimento" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="GRUPO_REDUCAO_IBS_MUNICIPIO" label="Grupo Redução">
                <NumField form={form} setField={setField} campo="PERC_REDUCAO_IBS_MUNICIPIO" label="% Redução" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_EFETIVA_REDUCAO_IBS_MUNICIPIO" label="Alíq. Efetiva Redução %" decimais={4} />
              </ChkRow>

              <Text style={styles.subSectionTitle}>CBS Estado</Text>
              <View style={styles.rowFields}>
                <NumField form={form} setField={setField} campo="ALQT_CBS_ESTADO" label="Alíquota %" decimais={4} />
              </View>
              <ChkRow form={form} setField={setField} campo="GRUPO_DIFERIMENTO_CBS_ESTADO" label="Grupo Diferimento">
                <NumField form={form} setField={setField} campo="PERC_DIFERIMENTO_CBS_ESTADO" label="% Diferimento" decimais={4} />
              </ChkRow>
              <ChkRow form={form} setField={setField} campo="GRUPO_REDUCAO_CBS_ESTADO" label="Grupo Redução">
                <NumField form={form} setField={setField} campo="PERC_REDUCAO_CBS_ESTADO" label="% Redução" decimais={4} />
                <NumField form={form} setField={setField} campo="ALQT_EFETIVA_REDUCAO_CBS_ESTADO" label="Alíq. Efetiva Redução %" decimais={4} />
              </ChkRow>

              {canSave ? (
                <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="taxas-salvar">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  filterTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  varTabs: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.md },
  varTab: { paddingVertical: 8, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  varTabActive: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  varTabText: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  varTabTextActive: { color: colors.onBrandPrimary },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginBottom: spacing.sm,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
    paddingVertical: Platform.OS === "web" ? spacing.xl : 0,
  },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: Platform.OS === "web" ? radius.lg : 18,
    borderTopRightRadius: Platform.OS === "web" ? radius.lg : 18,
    borderBottomLeftRadius: Platform.OS === "web" ? radius.lg : 0,
    borderBottomRightRadius: Platform.OS === "web" ? radius.lg : 0,
    borderWidth: Platform.OS === "web" ? 1 : 0,
    borderColor: colors.border,
    width: "100%",
    maxWidth: Platform.OS === "web" ? 860 : undefined,
    maxHeight: "94%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: spacing.xs, textTransform: "uppercase" },
  subSectionTitle: { fontSize: 12, fontWeight: "700", color: colors.onSurface, marginTop: spacing.md, marginBottom: 2 },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colThird: { flex: 1 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 4 },
  switchLabel: { fontSize: 13, color: colors.onSurface },
  chkRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, paddingVertical: 4 },
  chkRowLabel: { flexDirection: "row", alignItems: "center", gap: spacing.xs, width: 190 },
  chkRowFields: { flexDirection: "row", gap: spacing.sm, flex: 1 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  secondaryBtn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.sm, paddingVertical: 11, alignItems: "center", justifyContent: "center" },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
});
