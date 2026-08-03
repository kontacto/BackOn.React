// Financeiro > Fluxo de Caixa > Contas (FrmManConta.frm, "Conta") —
// cadastro de contas de caixa/banco. Web-only, tela única compacta sem
// abas (mesmo padrão de fornecedores.tsx/bancos.tsx — o .frm legado
// também não tem controle de aba). Ver PENDENCIAS.md > "Contas".
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { AppModal } from "@/src/components/AppModal";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_MAX_WIDTH, WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

type ContaListItem = {
  codigo: number; descricao: string; saldo_atual: number; tipo: number;
  situacao: string; conta_principal_painel: boolean;
};

type ContaForm = {
  descricao: string; bancoNome: string; agencia: string; numero: string;
  saldoInicial: string; moeda: string; tipo: number; situacao: string; contaPrincipalPainel: boolean;
};

const FORM_VAZIO: ContaForm = {
  descricao: "", bancoNome: "", agencia: "", numero: "",
  saldoInicial: "0", moeda: "Real", tipo: 0, situacao: "A", contaPrincipalPainel: false,
};

function fmtMoeda(v: number) {
  return (v || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function num(v: string) {
  const n = Number((v || "0").replace(/\./g, "").replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

export default function ContasScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const auditCtx = useAuditContext();

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Contas está disponível apenas no web." testID="contas-web-only" />;
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [items, setItems] = useState<ContaListItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCod, setEditingCod] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [saldoAtualAtual, setSaldoAtualAtual] = useState<number | null>(null);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [form, setForm] = useState<ContaForm>(FORM_VAZIO);
  const setField = <K extends keyof ContaForm>(key: K, value: ContaForm[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const load = useCallback(async (c: Connection) => {
    setLoading(true);
    try {
      const j = await apiGet(c, "/api/contas-caixa", { busca: search });
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [search]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      load(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (conn) load(conn);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditingCod(null);
    setSaldoAtualAtual(null);
    setForm(FORM_VAZIO);
    setFormOpen(true);
  };

  const openEdit = async (item: ContaListItem) => {
    if (!conn) return;
    setEditingCod(item.codigo);
    setFormOpen(true);
    try {
      const j = await apiGet(conn, `/api/contas-caixa/${item.codigo}`);
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      setForm({
        descricao: j.descricao || "", bancoNome: j.banco || "", agencia: j.agencia || "", numero: j.numero || "",
        saldoInicial: String(j.saldo_inicial ?? 0), moeda: j.moeda || "Real", tipo: j.tipo ?? 0,
        situacao: j.situacao || "A", contaPrincipalPainel: !!j.conta_principal_painel,
      });
      setSaldoAtualAtual(j.saldo_atual ?? 0);
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao carregar conta."));
      setFormOpen(false);
    }
  };

  const save = async () => {
    if (!conn) return;
    if (!form.descricao.trim()) { fb.showWarning("Informe a descrição da conta."); return; }
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/contas-caixa", "POST", {
        ...auditCtx,
        codigo: editingCod,
        descricao: form.descricao.trim(), banco_nome: form.bancoNome.trim(),
        agencia: form.agencia.trim(), numero: form.numero.trim(),
        saldo_inicial: num(form.saldoInicial), moeda: form.moeda.trim() || "Real",
        tipo: form.tipo, situacao: (form.situacao || "A").toUpperCase(),
        conta_principal_painel: form.contaPrincipalPainel,
      });
      if (j?.success) {
        fb.showSuccess(
          j.ajuste_saldo
            ? `Conta gravada. Saldo atual recalculado para ${fmtMoeda(j.saldo_atual_novo)} (saldo inicial alterado).`
            : "Conta gravada.",
          undefined, j.ajuste_saldo ? 5000 : undefined,
        );
        setEditingCod(j.codigo);
        load(conn);
      } else fb.showError(friendlyApiError(j, "Falha ao gravar."));
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar."));
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: ContaListItem) => {
    if (!conn) return;
    fb.showConfirm(`Confirma a exclusão da conta "${item.descricao}"?`, async () => {
      try {
        const j = await apiSend(conn, `/api/contas-caixa/${item.codigo}`, "DELETE", { ...auditCtx, codigo: item.codigo });
        if (j?.success) { fb.showSuccess("Conta excluída."); load(conn); }
        else fb.showError(friendlyApiError(j, "Falha ao excluir."));
      } catch (e) {
        fb.showError(friendlyCatchError(e, "Falha ao excluir."));
      }
    }, { destructive: true, confirmText: "Excluir" });
  };

  const canSave = can("CONTAS.GRAVAR") || isMaster;
  const canDel = can("CONTAS.EXCLUIR") || isMaster;

  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contas-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setFormOpen(false)} hitSlop={12} style={styles.back}>
            <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
          </Pressable>
          <Text style={styles.headerTitle} numberOfLines={1}>{editingCod ? `Conta ${editingCod}` : "Nova Conta"}</Text>
          <IconButtonWithTooltip icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaOpen(true)} color={colors.onBrandPrimary} />
          {canSave ? (
            <Pressable onPress={save} disabled={saving} style={[styles.saveBtn, saving && { opacity: 0.8 }]} testID="contas-gravar">
              {saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={styles.saveLabel}>Gravar</Text>}
            </Pressable>
          ) : null}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <Text style={styles.label}>Descrição *</Text>
              <TextInput value={form.descricao} onChangeText={(v) => setField("descricao", v)} style={styles.input} maxLength={30} testID="contas-descricao" />

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Tipo</Text>
                  <View style={styles.radioRow}>
                    <Pressable onPress={() => setField("tipo", 0)} style={styles.radioOpt} testID="contas-tipo-especie">
                      <Ionicons name={form.tipo === 0 ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                      <Text style={styles.radioLabel}>Espécie</Text>
                    </Pressable>
                    <Pressable onPress={() => setField("tipo", 1)} style={styles.radioOpt} testID="contas-tipo-banco">
                      <Ionicons name={form.tipo === 1 ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                      <Text style={styles.radioLabel}>Banco</Text>
                    </Pressable>
                  </View>
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Situação</Text>
                  <Pressable onPress={() => setField("situacao", form.situacao === "A" ? "I" : "A")} style={styles.radioOpt} testID="contas-situacao">
                    <Ionicons name={form.situacao === "A" ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.radioLabel}>{form.situacao === "A" ? "Ativo" : "Inativo"}</Text>
                  </Pressable>
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Moeda</Text>
                  <TextInput value={form.moeda} onChangeText={(v) => setField("moeda", v)} style={styles.input} testID="contas-moeda" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Banco</Text>
                  <TextInput value={form.bancoNome} onChangeText={(v) => setField("bancoNome", v)} style={styles.input} testID="contas-banco" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Agência</Text>
                  <TextInput value={form.agencia} onChangeText={(v) => setField("agencia", v)} style={styles.input} testID="contas-agencia" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Número</Text>
                  <TextInput value={form.numero} onChangeText={(v) => setField("numero", v)} style={styles.input} testID="contas-numero" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Saldo Inicial</Text>
                  <TextInput value={form.saldoInicial} onChangeText={(v) => setField("saldoInicial", v.replace(/[^0-9.,]/g, ""))} keyboardType="decimal-pad" style={styles.input} testID="contas-saldo-inicial" />
                </View>
                {editingCod && saldoAtualAtual != null ? (
                  <View style={styles.colNarrow}>
                    <Text style={styles.label}>Saldo Atual</Text>
                    <View style={[styles.input, styles.inputDisabled]}>
                      <Text style={styles.inputDisabledText}>{fmtMoeda(saldoAtualAtual)}</Text>
                    </View>
                  </View>
                ) : null}
              </View>

              <View style={styles.rowFields}>
                <Pressable onPress={() => setField("contaPrincipalPainel", !form.contaPrincipalPainel)} style={styles.radioOpt} testID="contas-principal-painel">
                  <Switch value={form.contaPrincipalPainel} onValueChange={(v) => setField("contaPrincipalPainel", v)} />
                  <Text style={styles.radioLabel}>Conta Padrão no Painel</Text>
                </Pressable>
              </View>
            </View>
          </View>
        </ScrollView>

        <AppModal visible={ajudaOpen} transparent animationType="fade" onRequestClose={() => setAjudaOpen(false)}>
          <Pressable style={styles.helpBg} onPress={() => setAjudaOpen(false)}>
            <Pressable style={styles.helpCard} onPress={(e) => e.stopPropagation()}>
              <View style={styles.helpHeader}>
                <Text style={styles.helpTitle}>Ajuda — Contas</Text>
                <Pressable onPress={() => setAjudaOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
              </View>
              <Text style={styles.helpItem}>
                <Text style={styles.helpItemTitle}>Saldo Inicial / Saldo Atual{"\n"}</Text>
                O Saldo Atual não é editado diretamente — ele reflete o Saldo Inicial mais tudo que já foi
                movimentado nesta conta. Se você alterar o Saldo Inicial de uma conta já existente, o Saldo
                Atual é ajustado na mesma proporção, preservando as movimentações já lançadas.
              </Text>
              <Text style={styles.helpItem}>
                <Text style={styles.helpItemTitle}>Conta Padrão no Painel{"\n"}</Text>
                Marca esta conta como a sugestão automática em telas que pedem uma conta de caixa/banco
                (ex.: baixa de títulos na Importação de Retorno).
              </Text>
              <Text style={styles.helpItem}>
                <Text style={styles.helpItemTitle}>Tipo{"\n"}</Text>
                "Espécie" é uma conta de caixa físico (dinheiro); "Banco" é uma conta bancária de verdade —
                use os campos Banco/Agência/Número só nesse segundo caso.
              </Text>
            </Pressable>
          </Pressable>
        </AppModal>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Contas</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={[styles.filters, styles.filtersWeb]}>
            <TextInput
              value={search}
              onChangeText={setSearch}
              placeholder="Buscar por código ou descrição…"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="contas-search"
            />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma conta cadastrada.</Text> : null}
          {items.map((it) => (
            <Pressable key={it.codigo} onPress={() => canSave && openEdit(it)} style={styles.row} testID={`contas-${it.codigo}`}>
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle}>
                  {it.codigo} · {it.descricao}
                  {it.conta_principal_painel ? " ★" : ""}
                  {it.situacao !== "A" ? " · Inativo" : ""}
                </Text>
                <Text style={styles.rowSub}>{it.tipo === 1 ? "Banco" : "Espécie"} · Saldo atual: {fmtMoeda(it.saldo_atual)}</Text>
              </View>
              {canDel ? (
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`contas-del-${it.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </Pressable>
          ))}
        </View>
      </ScrollView>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="contas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, gap: spacing.sm,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  saveBtn: {
    backgroundColor: "rgba(255,255,255,0.18)", borderWidth: 1, borderColor: "rgba(255,255,255,0.3)",
    borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  saveLabel: { color: "#fff", fontWeight: "700", fontSize: 13 },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  card: { padding: spacing.lg, borderRadius: radius.lg, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, gap: 4, maxWidth: WEB_CONTENT_MAX_WIDTH },
  rowFields: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 180 },
  colNarrow: { width: 150 },
  colTiny: { width: 120 },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "600", marginTop: spacing.sm },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, justifyContent: "center" },
  inputDisabledText: { fontSize: 13, color: colors.muted },
  radioRow: { flexDirection: "row", gap: spacing.md },
  radioOpt: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8 },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, marginTop: spacing.xl },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginTop: spacing.sm,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  helpBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center" },
  helpCard: { width: "100%", maxWidth: 560, maxHeight: "80%", backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, padding: spacing.lg },
  helpHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginBottom: spacing.sm },
  helpTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },
  helpItem: { fontSize: 13, color: colors.onSurfaceSecondary, marginBottom: spacing.sm, lineHeight: 19 },
  helpItemTitle: { fontWeight: "700", color: colors.onSurface },
});
