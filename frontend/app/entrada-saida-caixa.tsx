import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;
type Tipo = "E" | "S";

type Lancamento = {
  tipo: Tipo;
  codigo: number;
  data: string | null;
  atendente: number | null;
  atendente_nome: string | null;
  valor: number;
  descricao: string;
  forma_pag: string | null;
  conta: number | null;
  centro_custo: number | null;
  classe: number | null;
  sub_classe: number | null;
  favorecido: number | null;
  transferencia: string | null;
  cod_movimentacao: number | null;
};

const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};
const isoToBR = (iso: string | null) => {
  if (!iso) return "-";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
};
const fmtMoney = (v: number) => `R$ ${v.toFixed(2).replace(".", ",")}`;

// Cadastros > Entrada/Saída de Caixa (tabelas `entrada_caixa`/`saida_caixa`)
// — caixa OPERACIONAL da loja, não o caixa financeiro (fica em Cadastros e
// não em Financeiro por pedido explícito do usuário). Legado: FrmManESC.frm
// ("Entrada/Saída de Caixa") — tela
// única, compacta, sem abas (mesma exceção já usada em Fornecedores: o
// formulário original não tem controle de abas). Ver memória de projeto
// "Entrada/Saída de Caixa" para o mapeamento completo de campos e pendências
// (turno, transf_caixa, rotina de transferência pro financeiro — nenhum dos
// três é tocado por este form legado, ficam fora de escopo aqui também).
export default function EntradaSaidaCaixaScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Entrada/Saída de Caixa está disponível apenas no web."
        testID="entrada-saida-caixa-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Lancamento[]>([]);
  const [loading, setLoading] = useState(false);
  const [transfAtivo, setTransfAtivo] = useState(false);

  // Filtros (mesmos da tela legada: período + Entradas/Saídas + botão de busca).
  const [dataDe, setDataDe] = useState(todayISO());
  const [dataAte, setDataAte] = useState(todayISO());
  const [showEntradas, setShowEntradas] = useState(true);
  const [showSaidas, setShowSaidas] = useState(true);

  const [contasOpts, setContasOpts] = useState<SelectOption[]>([]);
  const [centroCustoOpts, setCentroCustoOpts] = useState<SelectOption[]>([]);
  const [formaPagOpts, setFormaPagOpts] = useState<SelectOption[]>([]);
  const [favorecidos, setFavorecidos] = useState<{ codigo: number; descricao: string }[]>([]);
  const [planoContas, setPlanoContas] = useState<{ codigo: number; descricao: string; sub_classes: { codigo: number; descricao: string }[] }[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<Lancamento | null>(null);
  const [saving, setSaving] = useState(false);

  const [tipo, setTipo] = useState<Tipo>("E");
  const [valor, setValor] = useState("");
  const [descricao, setDescricao] = useState("");
  const [formaPag, setFormaPag] = useState<string | null>(null);
  const [contaOrigem, setContaOrigem] = useState<number | null>(null);
  const [contaDestino, setContaDestino] = useState<number | null>(null);
  const [favorecidoTexto, setFavorecidoTexto] = useState("");
  const [classe, setClasse] = useState<number | null>(null);
  const [subClasse, setSubClasse] = useState<number | null>(null);
  const [centroCusto, setCentroCusto] = useState<number | null>(null);

  const load = useCallback(async (c: Conn, de: string, ate: string, ent: boolean, sai: boolean) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}` +
        `&data_de=${encodeURIComponent(de)}&data_ate=${encodeURIComponent(ate)}` +
        `&entradas=${ent}&saidas=${sai}`;
      const r = await fetch(`${base}/api/entrada-saida-caixa?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    const base = c.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
    const fetchLookup = async (path: string) => {
      try {
        const r = await fetch(`${base}/api/${path}?${qs}`);
        const j = await r.json();
        return j?.success && Array.isArray(j.items) ? j.items : [];
      } catch { return []; }
    };
    const [contas, centroCustoItems, formaPagItems, favs, planoRes] = await Promise.all([
      fetchLookup("contas"),
      fetchLookup("centro-custo"),
      fetchLookup("forma-pagamento"),
      fetchLookup("favorecidos"),
      (async () => {
        try {
          const r = await fetch(`${base}/api/financeiro/plano-contas?${qs}`);
          const j = await r.json();
          return j?.success ? j.items || [] : [];
        } catch { return []; }
      })(),
    ]);
    setContasOpts(contas.map((i: any) => ({ value: i.codigo, label: i.descricao })));
    setCentroCustoOpts(centroCustoItems.map((i: any) => ({ value: i.codigo, label: i.descricao })));
    setFormaPagOpts(formaPagItems.map((i: any) => ({ value: i.codigo, label: i.descricao })));
    setFavorecidos(favs);
    setPlanoContas(planoRes);

    try {
      const r = await fetch(`${base}/api/entrada-saida-caixa/config?${qs}`);
      const j = await r.json();
      setTransfAtivo(!!j?.transf_ent_sai_caixa);
    } catch { setTransfAtivo(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c, todayISO(), todayISO(), true, true);
      loadLookups(c);
    })();
  }, [router, load, loadLookups]);

  const buscar = () => {
    if (!conn) return;
    let ent = showEntradas, sai = showSaidas;
    // Mesma regra do legado: nunca deixa a listagem vazia por checkbox zerado.
    if (!ent && !sai) { ent = true; sai = true; setShowEntradas(true); setShowSaidas(true); }
    load(conn, dataDe, dataAte, ent, sai);
  };

  const contaLabel = (cod: number | null) => (cod == null ? "-" : contasOpts.find((c) => c.value === cod)?.label || String(cod));
  const favorecidoLabel = (cod: number | null) => (cod == null ? "-" : favorecidos.find((f) => f.codigo === cod)?.descricao || String(cod));

  const classesOpts: SelectOption[] = planoContas.map((c) => ({ value: c.codigo, label: c.descricao }));
  const subClassesOpts: SelectOption[] = useMemo(() => {
    const found = planoContas.find((c) => c.codigo === classe);
    return (found?.sub_classes || []).map((s) => ({ value: s.codigo, label: s.descricao }));
  }, [planoContas, classe]);

  const resetForm = () => {
    setEditing(null); setTipo("E"); setValor(""); setDescricao(""); setFormaPag(null);
    setContaOrigem(null); setContaDestino(null); setFavorecidoTexto(""); setClasse(null);
    setSubClasse(null); setCentroCusto(null);
  };

  const openNew = () => { resetForm(); setFormOpen(true); };
  const openEdit = (it: Lancamento) => {
    setEditing(it);
    setTipo(it.tipo);
    setValor(String(it.valor).replace(".", ","));
    setDescricao(it.descricao);
    setFormaPag(it.forma_pag);
    setContaOrigem(it.conta);
    setContaDestino(it.transferencia === "2" ? it.classe : null);
    setFavorecidoTexto(favorecidoLabel(it.favorecido) === "-" ? "" : favorecidoLabel(it.favorecido));
    setClasse(it.transferencia === "2" ? null : it.classe);
    setSubClasse(it.transferencia === "2" ? null : it.sub_classe);
    setCentroCusto(it.centro_custo);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    const valorNum = parseFloat(valor.replace(/\./g, "").replace(",", "."));
    if (!Number.isFinite(valorNum) || valorNum <= 0) { fb.showError("Defina o valor da Entrada/Saída de Caixa."); return; }
    if (!descricao.trim()) { fb.showError("Defina a descrição da Entrada/Saída de Caixa."); return; }
    if (transfAtivo) {
      if (!contaOrigem) { fb.showError("Defina a conta do lançamento."); return; }
      if (!favorecidoTexto.trim()) { fb.showError("Defina o favorecido do lançamento."); return; }
    }
    if (contaDestino && contaOrigem && contaDestino === contaOrigem) {
      fb.showError("Conta origem e destino não podem ser a mesma."); return;
    }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/entrada-saida-caixa`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: editing?.codigo ?? null, tipo,
          valor: valorNum, descricao: descricao.trim(), forma_pag: formaPag,
          conta: contaOrigem, conta_destino: contaDestino,
          favorecido_descricao: favorecidoTexto.trim() || null,
          classe, sub_classe: subClasse, centro_custo: centroCusto,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Lançamento gravado.");
        setFormOpen(false);
        load(conn, dataDe, dataAte, showEntradas, showSaidas);
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setSaving(false); }
  };

  const remove = async (it: Lancamento) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/entrada-saida-caixa/${it.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, tipo: it.tipo }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Excluído."); load(conn, dataDe, dataAte, showEntradas, showSaidas); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  // Recibo simplificado (cabeçalho fantasia/razão social + valor/data/descrição
  // + assinatura) — impressão térmica de POS ainda não existe no projeto (ver
  // memória "Impressão automática por Finalidade"), então aqui é impressão de
  // navegador (window.print numa janela dedicada), não impressão direta na
  // impressora de caixa.
  const imprimir = (it: Lancamento) => {
    if (typeof window === "undefined") return;
    const tipoLabel = it.tipo === "E" ? "ENTRADA DE CAIXA/SUPRIMENTO" : "SAÍDA DE CAIXA/SANGRIA";
    const win = window.open("", "_blank", "width=420,height=600");
    if (!win) return;
    win.document.write(`<!DOCTYPE html><html><head><title>Recibo #${it.codigo}</title><style>
      body{font-family:'Courier New',monospace;font-size:12px;padding:16px;}
      .center{text-align:center}
      hr{border:none;border-top:1px dashed #000;margin:8px 0}
    </style></head><body>
      <div class="center"><strong>${tipoLabel} Nº ${String(it.codigo).padStart(6, "0")}</strong></div>
      <hr/>
      <div>ATENDENTE: ${it.atendente_nome || "-"}</div>
      <hr/>
      <div>VALOR: ${fmtMoney(it.valor)}&nbsp;&nbsp;&nbsp;&nbsp;DATA: ${isoToBR(it.data)}</div>
      <hr/>
      <div>DESCRIÇÃO:</div>
      <div>${it.descricao}</div>
      <hr/><br/><br/>
      <div class="center">_____________________________________</div>
      <div class="center">Assinatura</div>
    </body></html>`);
    win.document.close();
    win.focus();
    win.print();
  };

  const canSave = can("MOV_CAIXA.GRAVAR") || isMaster;
  const canDel = can("MOV_CAIXA.EXCLUIR") || isMaster;
  const canPrint = can("MOV_CAIXA.IMPRIMIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="entrada-saida-caixa-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Entrada/Saída de Caixa</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <View style={styles.filterRow}>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>De</Text>
              <WebDateField value={dataDe} onChange={setDataDe} testID="esc-filtro-data-de" />
            </View>
            <View style={styles.colNarrow}>
              <Text style={styles.label}>Até</Text>
              <WebDateField value={dataAte} onChange={setDataAte} testID="esc-filtro-data-ate" />
            </View>
            <Pressable onPress={() => setShowEntradas((v) => !v)} style={styles.checkRow} testID="filtro-entradas">
              <Ionicons name={showEntradas ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Entradas</Text>
            </Pressable>
            <Pressable onPress={() => setShowSaidas((v) => !v)} style={styles.checkRow} testID="filtro-saidas">
              <Ionicons name={showSaidas ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
              <Text style={styles.checkLabel}>Saídas</Text>
            </Pressable>
            <Pressable onPress={buscar} style={styles.searchBtn} testID="buscar-lancamentos">
              <Ionicons name="search" size={18} color="#fff" />
            </Pressable>
          </View>
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum lançamento no período.</Text> : null}
          {items.map((it) => (
            <View key={`${it.tipo}-${it.codigo}`} style={styles.row} testID={`lancamento-${it.tipo}-${it.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <View style={styles.rowTop}>
                  <View style={[styles.badge, it.tipo === "E" ? styles.badgeEntrada : styles.badgeSaida]}>
                    <Text style={styles.badgeText}>{it.tipo === "E" ? "Entrada" : "Saída"}</Text>
                  </View>
                  <Text style={styles.rowValor}>{fmtMoney(it.valor)}</Text>
                  <Text style={styles.rowData}>{isoToBR(it.data)}</Text>
                </View>
                <Text style={styles.rowDesc}>{it.descricao}</Text>
                <Text style={styles.rowSub}>Atendente: {it.atendente_nome || "-"}{it.cod_movimentacao ? " · Já transferido p/ Financeiro" : ""}</Text>
              </Pressable>
              <View style={styles.rowActions}>
                {canPrint ? (
                  <Pressable onPress={() => imprimir(it)} hitSlop={8} testID={`imprimir-${it.tipo}-${it.codigo}`}>
                    <Ionicons name="print-outline" size={20} color={colors.muted} />
                  </Pressable>
                ) : null}
                {canDel ? (
                  <Pressable onPress={() => remove(it)} hitSlop={8} testID={`excluir-${it.tipo}-${it.codigo}`}>
                    <Ionicons name="trash-outline" size={20} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="novo-lancamento">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <AppModal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editing ? `Lançamento #${editing.codigo}` : "Novo lançamento"}</Text>

              <View style={styles.tipoRow}>
                <Pressable
                  disabled={!!editing}
                  onPress={() => setTipo("E")}
                  style={[styles.tipoBtn, tipo === "E" && styles.tipoBtnSel, !!editing && { opacity: 0.6 }]}
                  testID="tipo-entrada"
                >
                  <Text style={[styles.tipoBtnText, tipo === "E" && styles.tipoBtnTextSel]}>Entrada de Caixa/Suprimento</Text>
                </Pressable>
                <Pressable
                  disabled={!!editing}
                  onPress={() => setTipo("S")}
                  style={[styles.tipoBtn, tipo === "S" && styles.tipoBtnSel, !!editing && { opacity: 0.6 }]}
                  testID="tipo-saida"
                >
                  <Text style={[styles.tipoBtnText, tipo === "S" && styles.tipoBtnTextSel]}>Saída de Caixa/Sangria</Text>
                </Pressable>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor *</Text>
                  <TextInput
                    value={valor}
                    onChangeText={setValor}
                    placeholder="0,00"
                    placeholderTextColor={colors.muted}
                    keyboardType="decimal-pad"
                    style={styles.input}
                    testID="lancamento-valor"
                  />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Forma de Pagamento</Text>
                  <SelectField value={formaPag} onChange={(v) => setFormaPag(v == null ? null : String(v))} options={formaPagOpts} placeholder="Selecione…" allowClear compactWeb testID="lancamento-forma-pag" modalTitle="Forma de Pagamento" />
                </View>
              </View>

              <Text style={styles.label}>Descrição *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: Compra de café"
                placeholderTextColor={colors.muted}
                style={[styles.input, styles.inputMultiline]}
                multiline
                testID="lancamento-descricao"
              />

              {transfAtivo ? (
                <>
                  <Text style={styles.sectionTitle}>Transferência p/ Fluxo de Caixa Financeiro</Text>

                  <View style={styles.rowFields}>
                    <View style={styles.colFlex}>
                      <Text style={styles.label}>Conta *</Text>
                      <SelectField value={contaOrigem} onChange={(v) => setContaOrigem(v == null ? null : Number(v))} options={contasOpts} placeholder="Selecione…" allowClear compactWeb testID="lancamento-conta" modalTitle="Conta" />
                    </View>
                    <View style={styles.colFlex}>
                      <Text style={styles.label}>Conta Destino</Text>
                      <SelectField value={contaDestino} onChange={(v) => setContaDestino(v == null ? null : Number(v))} options={contasOpts} placeholder="Só p/ transferência entre contas" allowClear compactWeb testID="lancamento-conta-destino" modalTitle="Conta Destino" />
                    </View>
                  </View>

                  <Text style={styles.label}>Favorecido *</Text>
                  <TextInput
                    value={favorecidoTexto}
                    onChangeText={setFavorecidoTexto}
                    placeholder="Digite o nome — se não existir, é cadastrado ao gravar"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, !!contaDestino && styles.inputDisabled]}
                    editable={!contaDestino}
                    testID="lancamento-favorecido"
                  />

                  {!contaDestino ? (
                    <View style={styles.rowFields}>
                      <View style={styles.colFlex}>
                        <Text style={styles.label}>Classe</Text>
                        <SelectField value={classe} onChange={(v) => { setClasse(v == null ? null : Number(v)); setSubClasse(null); }} options={classesOpts} placeholder="Selecione…" allowClear compactWeb testID="lancamento-classe" modalTitle="Classe" />
                      </View>
                      <View style={styles.colFlex}>
                        <Text style={styles.label}>Sub Classe</Text>
                        <SelectField value={subClasse} onChange={(v) => setSubClasse(v == null ? null : Number(v))} options={subClassesOpts} placeholder="Selecione…" allowClear compactWeb disabled={!classe} testID="lancamento-subclasse" modalTitle="Sub Classe" />
                      </View>
                    </View>
                  ) : null}

                  <Text style={styles.label}>Centro de Custo</Text>
                  <SelectField value={centroCusto} onChange={(v) => setCentroCusto(v == null ? null : Number(v))} options={centroCustoOpts} placeholder="Selecione…" allowClear compactWeb testID="lancamento-centro-custo" modalTitle="Centro de Custo" />
                </>
              ) : null}

              {editing?.cod_movimentacao ? (
                <Text style={styles.warnText}>
                  Este lançamento já foi transferido para a movimentação financeira — não é possível alterar
                  valor/descrição. Exclua-o primeiro no Financeiro, se precisar corrigir.
                </Text>
              ) : null}

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="lancamento-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}


const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 760, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0 },
  filterRow: { flexDirection: "row", alignItems: "flex-end", gap: spacing.sm, flexWrap: "wrap" },
  colNarrow: { width: 150 },
  colFlex: { flex: 1 },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 10 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
  searchBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.md, width: 42, height: 42, alignItems: "center", justifyContent: "center" },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTop: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  badge: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: radius.pill },
  badgeEntrada: { backgroundColor: "#DCFCE7" },
  badgeSaida: { backgroundColor: "#FEE2E2" },
  badgeText: { fontSize: 11, fontWeight: "700", color: colors.onSurface },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  rowData: { fontSize: 12, color: colors.muted, marginLeft: "auto" },
  rowDesc: { fontSize: 13, color: colors.onSurface, marginTop: 4 },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  rowActions: { flexDirection: "row", gap: spacing.md },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  modalBg: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
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
    width: "100%", maxWidth: Platform.OS === "web" ? 560 : undefined, maxHeight: "88%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  tipoRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  tipoBtn: { flex: 1, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingVertical: 10, alignItems: "center" },
  tipoBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoBtnText: { fontSize: 12, fontWeight: "600", color: colors.onSurface, textAlign: "center" },
  tipoBtnTextSel: { color: colors.onBrandPrimary },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: 4, textTransform: "uppercase" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputMultiline: { minHeight: 70, textAlignVertical: "top" },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  warnText: { fontSize: 12, color: colors.error, marginTop: spacing.md },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
});
