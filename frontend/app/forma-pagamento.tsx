import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField from "@/src/components/SelectField";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type LookupItem = { codigo: number | string; descricao: string };
type PrazoItem = { prazo: number; percentual: number };
type FormaPagamento = {
  codigo: string;
  descricao: string;
  tipo: string | null;
  taxa_adm: number;
  prazo: number | null;
  prazo_rec: number | null;
  situacao: string | null;
  periodo: number | null;
  faturar_para: string | null;
  forma_pag_garantia: boolean;
  exige_documentos: boolean;
  vale_devolucao: boolean;
  nao_totaliza_caixa: boolean;
  parcelador: string | null;
  parcela_max: number | null;
  cod_mov: string | null;
  perc_desc_comissao: number;
  valor_desc_comissao: number;
  perc_acres_comissao: number;
  valor_acres_comissao: number;
  transf_caixa: string | null;
  conta_transf_caixa: number | null;
  classe_caixa: number | null;
  sub_classe_caixa: number | null;
  prazos: PrazoItem[];
};

// Tipo de pagamento — enum fixo do legado (Combo1 do FrmManForPag), não é lookup do banco.
const TIPO_OPTIONS = [
  { value: "CH", label: "CH - Cheque" },
  { value: "DI", label: "DI - Dinheiro" },
  { value: "CC", label: "CC - Cartão de Crédito" },
  { value: "DU", label: "DU - Duplicata" },
  { value: "CD", label: "CD - Cartão de Débito" },
  { value: "VA", label: "VA - Vale" },
  { value: "TI", label: "TI - Tícket/PIX" },
];

// Período — mesmos índices do legado (List1), gravados como smallint. O índice 2
// (item em branco no VB6) fica de fora da UI, mas é preservado se já vier de um registro antigo.
const PERIODO_OPTIONS = [
  { value: "0", label: "Todos" },
  { value: "1", label: "Decenal" },
  { value: "3", label: "Mensal" },
  { value: "4", label: "Quinzenal" },
  { value: "5", label: "Semanal" },
  { value: "6", label: "Diário" },
];

const FATURAR_PARA_OPTIONS = [
  { value: "C", label: "Cliente" },
  { value: "A", label: "Administradora" },
];

const PARCELADOR_OPTIONS = [
  { value: "L", label: "Loja" },
  { value: "A", label: "Administradora" },
];

// "" (Não Transfere) é um valor válido no banco, mas o SelectField trata "" como
// "nada selecionado" — por isso usamos o sentinel "N" só na UI e convertemos ao salvar/carregar.
const TRANSF_CAIXA_OPTIONS = [
  { value: "N", label: "Não Transfere" },
  { value: "P", label: "Previsão" },
  { value: "M", label: "Movimentação" },
];

const tipoLabel = (tipo: string | null) => TIPO_OPTIONS.find((t) => t.value === tipo)?.label || tipo || "-";

const toFloat = (s: string): number => {
  const v = parseFloat((s || "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};

const toIntOrNull = (s: string): number | null => {
  const v = parseInt(s, 10);
  return Number.isFinite(v) ? v : null;
};

export default function FormaPagamentoScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Forma de Pagamento está disponível apenas no web."
        testID="forma-pagamento-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<FormaPagamento[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [tiposMov, setTiposMov] = useState<LookupItem[]>([]);
  const [contas, setContas] = useState<LookupItem[]>([]);
  const [classes, setClasses] = useState<LookupItem[]>([]);
  const [subClasses, setSubClasses] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Dados Principais
  const [descricao, setDescricao] = useState("");
  const [tipo, setTipo] = useState<string | null>(null);
  const [taxaAdm, setTaxaAdm] = useState("0");
  const [prazo, setPrazo] = useState("0");
  const [prazoRec, setPrazoRec] = useState("0");
  const [situacao, setSituacao] = useState("A");
  const [periodo, setPeriodo] = useState<string | null>("0");
  const [faturarPara, setFaturarPara] = useState<string | null>("C");
  const [formaPagGarantia, setFormaPagGarantia] = useState(false);
  const [exigeDocumentos, setExigeDocumentos] = useState(false);
  const [valeDevolucao, setValeDevolucao] = useState(false);
  const [naoTotalizaCaixa, setNaoTotalizaCaixa] = useState(false);
  const [parcelador, setParcelador] = useState<string | null>("L");
  const [parcelaMax, setParcelaMax] = useState("1");
  const [codMov, setCodMov] = useState<string | null>(null);

  // Comissão
  const [percDescComissao, setPercDescComissao] = useState("0");
  const [valorDescComissao, setValorDescComissao] = useState("0");
  const [percAcresComissao, setPercAcresComissao] = useState("0");
  const [valorAcresComissao, setValorAcresComissao] = useState("0");

  // Fluxo de Caixa
  const [transfCaixa, setTransfCaixa] = useState<string | null>("N");
  const [contaTransfCaixa, setContaTransfCaixa] = useState<string | null>(null);
  const [classeCaixa, setClasseCaixa] = useState<string | null>(null);
  const [subClasseCaixa, setSubClasseCaixa] = useState<string | null>(null);

  // Parcelamento por Prazo
  const [prazos, setPrazos] = useState<PrazoItem[]>([]);
  const [novoPrazo, setNovoPrazo] = useState("");
  const [novoPercentual, setNovoPercentual] = useState("");

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/forma-pagamento?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const fetchLookup = async (path: string, setter: (items: LookupItem[]) => void) => {
      try {
        const r = await fetch(`${base}/api/${path}?${qs}`);
        const j = await r.json();
        if (j?.success && Array.isArray(j.items)) setter(j.items);
      } catch { /* silencioso — lookup opcional */ }
    };
    await Promise.all([
      fetchLookup("tipo-mov", setTiposMov),
      fetchLookup("contas", setContas),
      fetchLookup("classes", setClasses),
      fetchLookup("sub-classes", setSubClasses),
    ]);
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc, "");
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditCod(null);
    setDescricao(""); setTipo(null); setTaxaAdm("0"); setPrazo("0"); setPrazoRec("0");
    setSituacao("A"); setPeriodo("0"); setFaturarPara("C");
    setFormaPagGarantia(false); setExigeDocumentos(false); setValeDevolucao(false); setNaoTotalizaCaixa(false);
    setParcelador("L"); setParcelaMax("1"); setCodMov(null);
    setPercDescComissao("0"); setValorDescComissao("0"); setPercAcresComissao("0"); setValorAcresComissao("0");
    setTransfCaixa("N"); setContaTransfCaixa(null); setClasseCaixa(null); setSubClasseCaixa(null);
    setPrazos([]); setNovoPrazo(""); setNovoPercentual("");
    setFormOpen(true);
  };

  const openEdit = (f: FormaPagamento) => {
    setEditCod(f.codigo);
    setDescricao(f.descricao); setTipo(f.tipo); setTaxaAdm(String(f.taxa_adm ?? 0));
    setPrazo(String(f.prazo ?? 0)); setPrazoRec(String(f.prazo_rec ?? 0));
    setSituacao(f.situacao || "A"); setPeriodo(f.periodo != null ? String(f.periodo) : "0");
    setFaturarPara(f.faturar_para || "C");
    setFormaPagGarantia(f.forma_pag_garantia); setExigeDocumentos(f.exige_documentos);
    setValeDevolucao(f.vale_devolucao); setNaoTotalizaCaixa(f.nao_totaliza_caixa);
    setParcelador(f.parcelador || "L"); setParcelaMax(String(f.parcela_max ?? 1));
    setCodMov(f.cod_mov);
    setPercDescComissao(String(f.perc_desc_comissao ?? 0)); setValorDescComissao(String(f.valor_desc_comissao ?? 0));
    setPercAcresComissao(String(f.perc_acres_comissao ?? 0)); setValorAcresComissao(String(f.valor_acres_comissao ?? 0));
    setTransfCaixa(f.transf_caixa || "N");
    setContaTransfCaixa(f.conta_transf_caixa != null ? String(f.conta_transf_caixa) : null);
    setClasseCaixa(f.classe_caixa != null ? String(f.classe_caixa) : null);
    setSubClasseCaixa(f.sub_classe_caixa != null ? String(f.sub_classe_caixa) : null);
    setPrazos(f.prazos || []); setNovoPrazo(""); setNovoPercentual("");
    setFormOpen(true);
  };

  const addPrazo = () => {
    const p = toIntOrNull(novoPrazo);
    if (p == null) { showToast("Informe o prazo em dias."); return; }
    if (prazos.some((x) => x.prazo === p)) { showToast("Já existe um percentual para esse prazo."); return; }
    setPrazos([...prazos, { prazo: p, percentual: toFloat(novoPercentual) }].sort((a, b) => a.prazo - b.prazo));
    setNovoPrazo(""); setNovoPercentual("");
  };

  const removePrazo = (p: number) => setPrazos(prazos.filter((x) => x.prazo !== p));

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    if (!tipo) { showToast("Selecione o tipo."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/forma-pagamento`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: editCod,
          descricao: descricao.trim(), tipo,
          taxa_adm: toFloat(taxaAdm), prazo: toIntOrNull(prazo) ?? 0, prazo_rec: toIntOrNull(prazoRec) ?? 0,
          situacao: (situacao || "A").trim().toUpperCase().slice(0, 2), periodo: toIntOrNull(periodo || "0") ?? 0,
          faturar_para: faturarPara, forma_pag_garantia: formaPagGarantia, exige_documentos: exigeDocumentos,
          vale_devolucao: valeDevolucao, nao_totaliza_caixa: naoTotalizaCaixa,
          parcelador, parcela_max: toIntOrNull(parcelaMax) ?? 1, cod_mov: codMov,
          perc_desc_comissao: toFloat(percDescComissao), valor_desc_comissao: toFloat(valorDescComissao),
          perc_acres_comissao: toFloat(percAcresComissao), valor_acres_comissao: toFloat(valorAcresComissao),
          transf_caixa: transfCaixa === "N" ? "" : transfCaixa,
          conta_transf_caixa: contaTransfCaixa ? toIntOrNull(contaTransfCaixa) : null,
          classe_caixa: classeCaixa ? toIntOrNull(classeCaixa) : null,
          sub_classe_caixa: subClasseCaixa ? toIntOrNull(subClasseCaixa) : null,
          prazos,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Forma de pagamento gravada."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (f: FormaPagamento) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/forma-pagamento/${encodeURIComponent(f.codigo)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("FORMA_PAGAMENTO.GRAVAR") || isMaster;
  const canDel = can("FORMA_PAGAMENTO.EXCLUIR") || isMaster;

  const tipoMovOpts = tiposMov.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));
  const contasOpts = contas.map((i) => ({ value: i.codigo, label: i.descricao }));
  const classesOpts = classes.map((i) => ({ value: i.codigo, label: i.descricao }));
  const subClassesOpts = subClasses.map((i) => ({ value: i.codigo, label: i.descricao }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="forma-pagamento-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Forma de Pagamento</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por código ou descrição…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="forma-pagamento-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma forma de pagamento cadastrada.</Text> : null}
          {items.map((f) => (
            <View key={f.codigo} style={styles.row} testID={`forma-pagamento-${f.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(f)}>
                <Text style={styles.rowTitle}>{f.codigo} · {f.descricao}</Text>
                <Text style={styles.rowSub}>{tipoLabel(f.tipo)} · Situação: {f.situacao || "-"}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(f)} hitSlop={8} testID={`forma-pagamento-del-${f.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="forma-pagamento-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod ? `Forma de Pagamento ${editCod}` : "Nova forma de pagamento"}</Text>

              <Text style={styles.sectionTitle}>Dados Principais</Text>

              <Text style={styles.label}>Descrição *</Text>
              <TextInput value={descricao} onChangeText={setDescricao} placeholder="Ex.: Dinheiro" placeholderTextColor={colors.muted} style={styles.input} maxLength={50} testID="fp-descricao" />

              <Text style={styles.label}>Tipo *</Text>
              <SelectField value={tipo} onChange={(v) => setTipo(v == null ? null : String(v))} options={TIPO_OPTIONS} placeholder="Selecione…" compactWeb testID="fp-tipo" modalTitle="Tipo" />

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Taxa Adm. %</Text>
                  <TextInput value={taxaAdm} onChangeText={setTaxaAdm} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-taxa-adm" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Situação</Text>
                  <TextInput value={situacao} onChangeText={(v) => setSituacao(v.toUpperCase())} maxLength={2} autoCapitalize="characters" style={styles.input} testID="fp-situacao" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Prazo (dias)</Text>
                  <TextInput value={prazo} onChangeText={(v) => setPrazo(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="fp-prazo" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Recebimento (dias)</Text>
                  <TextInput value={prazoRec} onChangeText={(v) => setPrazoRec(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="fp-prazo-rec" />
                </View>
              </View>

              <Text style={styles.label}>Período</Text>
              <SelectField value={periodo} onChange={(v) => setPeriodo(v == null ? null : String(v))} options={PERIODO_OPTIONS} placeholder="Selecione…" compactWeb testID="fp-periodo" modalTitle="Período" />

              <Text style={styles.label}>Faturar Para</Text>
              <SelectField value={faturarPara} onChange={(v) => setFaturarPara(v == null ? null : String(v))} options={FATURAR_PARA_OPTIONS} placeholder="Selecione…" compactWeb testID="fp-faturar-para" modalTitle="Faturar Para" />

              <View style={styles.switchRow}>
                <Text style={styles.label}>Garantia O.S.</Text>
                <Switch value={formaPagGarantia} onValueChange={setFormaPagGarantia} testID="fp-garantia-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Exigir lançamento dos documentos</Text>
                <Switch value={exigeDocumentos} onValueChange={setExigeDocumentos} testID="fp-exige-documentos-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Exige Vale de devolução</Text>
                <Switch value={valeDevolucao} onValueChange={setValeDevolucao} testID="fp-vale-devolucao-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Não totaliza no Fechamento de Caixa</Text>
                <Switch value={naoTotalizaCaixa} onValueChange={setNaoTotalizaCaixa} testID="fp-nao-totaliza-switch" />
              </View>

              <Text style={styles.label}>Parcelador</Text>
              <SelectField value={parcelador} onChange={(v) => setParcelador(v == null ? null : String(v))} options={PARCELADOR_OPTIONS} placeholder="Selecione…" compactWeb testID="fp-parcelador" modalTitle="Parcelador" />

              <Text style={styles.label}>Máximo de Parcelas</Text>
              <TextInput value={parcelaMax} onChangeText={(v) => setParcelaMax(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="fp-parcela-max" />

              <Text style={styles.label}>Movimentação</Text>
              <SelectField value={codMov} onChange={(v) => setCodMov(v == null ? null : String(v))} options={tipoMovOpts} placeholder="Selecione…" allowClear compactWeb testID="fp-cod-mov" modalTitle="Tipo de Movimentação" />

              <Text style={styles.sectionTitle}>Comissão</Text>

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>% Desconto Comissão</Text>
                  <TextInput value={percDescComissao} onChangeText={setPercDescComissao} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-perc-desc-comissao" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Valor Desconto Comissão</Text>
                  <TextInput value={valorDescComissao} onChangeText={setValorDescComissao} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-valor-desc-comissao" />
                </View>
              </View>
              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>% Acréscimo Comissão</Text>
                  <TextInput value={percAcresComissao} onChangeText={setPercAcresComissao} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-perc-acres-comissao" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Valor Acréscimo Comissão</Text>
                  <TextInput value={valorAcresComissao} onChangeText={setValorAcresComissao} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-valor-acres-comissao" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Fluxo de Caixa</Text>

              <Text style={styles.label}>Caixa</Text>
              <SelectField value={transfCaixa} onChange={(v) => setTransfCaixa(v == null ? "N" : String(v))} options={TRANSF_CAIXA_OPTIONS} placeholder="Selecione…" compactWeb testID="fp-transf-caixa" modalTitle="Caixa" />

              <Text style={styles.label}>Conta Fluxo de Caixa</Text>
              <SelectField value={contaTransfCaixa} onChange={(v) => setContaTransfCaixa(v == null ? null : String(v))} options={contasOpts} placeholder="Selecione…" allowClear compactWeb testID="fp-conta" modalTitle="Conta" />

              <Text style={styles.label}>Classe</Text>
              <SelectField value={classeCaixa} onChange={(v) => setClasseCaixa(v == null ? null : String(v))} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="fp-classe" modalTitle="Classe" />

              <Text style={styles.label}>Sub Classe</Text>
              <SelectField value={subClasseCaixa} onChange={(v) => setSubClasseCaixa(v == null ? null : String(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb testID="fp-sub-classe" modalTitle="Sub Classe" />

              <Text style={styles.sectionTitle}>Parcelamento por Prazo</Text>

              {prazos.map((p) => (
                <View key={p.prazo} style={styles.prazoRow} testID={`fp-prazo-item-${p.prazo}`}>
                  <Text style={styles.prazoText}>{p.prazo} dias — {p.percentual.toFixed(2)}%</Text>
                  <Pressable onPress={() => removePrazo(p.prazo)} hitSlop={8} testID={`fp-prazo-del-${p.prazo}`}>
                    <Ionicons name="close-circle-outline" size={20} color={colors.error} />
                  </Pressable>
                </View>
              ))}

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Prazo (dias)</Text>
                  <TextInput value={novoPrazo} onChangeText={(v) => setNovoPrazo(v.replace(/[^0-9]/g, ""))} keyboardType="number-pad" style={styles.input} testID="fp-novo-prazo" />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Percentual</Text>
                  <TextInput value={novoPercentual} onChangeText={setNovoPercentual} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="fp-novo-percentual" />
                </View>
              </View>
              <Pressable onPress={addPrazo} style={styles.secondaryBtn} testID="fp-add-prazo">
                <Text style={styles.secondaryBtnText}>Adicionar prazo</Text>
              </Pressable>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="fp-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? <View style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.4)",
    justifyContent: Platform.OS === "web" ? "center" : "flex-end",
    paddingHorizontal: Platform.OS === "web" ? spacing.xl : 0,
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
    maxWidth: Platform.OS === "web" ? 640 : undefined,
    maxHeight: "88%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: 4, textTransform: "uppercase" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colHalf: { flex: 1 },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  prazoRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, marginTop: spacing.xs },
  prazoText: { fontSize: 13, color: colors.onSurface },
  secondaryBtn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 10, alignItems: "center", marginTop: spacing.sm },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
