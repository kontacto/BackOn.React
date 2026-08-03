// Cadastro de Layout — templates de formulário dinâmico (motor de
// "Formulário Dinâmico", ficha de anamnese/checklist/etc.), reaproveitáveis
// por qualquer entidade (Cliente, Fornecedor, Funcionário, Produto, Serviço,
// Pedido, O.S., Profissional, Contrato — colunas boolean de `layout` — e
// Agenda, associada por serviço/profissional em vez de flag direto). Tela
// COMPACTA sem abas — mesmo padrão de `fornecedores.tsx`/`cilindro-cadastro.tsx`
// ("Exception — compact single-view screens" no CLAUDE.md). Ver
// `backend/services/layout_service.py` e PENDENCIAS.md > "Motor de Layout".
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, apiDelete, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

const isWeb = Platform.OS === "web";

type LayoutItem = {
  codigo: number; descricao: string;
  cliente: boolean; fornecedor: boolean; funcionario: boolean; produto: boolean;
  servico: boolean; pedido_venda: boolean; os: boolean; profissional: boolean; contrato: boolean;
};
type Campo = {
  codigo: number; campo1: string; campo2: string; tipo: number; tipo_descricao: string;
  calculado: boolean; unidade_medida: string; decimais: number; tamanho: number; campo_agrupado: boolean;
};

const ENTIDADES: { key: keyof Omit<LayoutItem, "codigo" | "descricao">; label: string }[] = [
  { key: "cliente", label: "Cliente" },
  { key: "fornecedor", label: "Fornecedor" },
  { key: "funcionario", label: "Funcionário" },
  { key: "produto", label: "Produto" },
  { key: "servico", label: "Serviço" },
  { key: "pedido_venda", label: "Pedido de Venda" },
  { key: "os", label: "O.S." },
  { key: "profissional", label: "Profissional" },
  { key: "contrato", label: "Contrato" },
];

export default function LayoutCadastroScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Cadastro de Layout está disponível apenas no web." testID="layout-cadastro-web-only" />;
  }
  if (!can("LAYOUT.ABRIR")) {
    return <LockedView title="Acesso restrito" message="Você não tem permissão para acessar o Cadastro de Layout." testID="layout-cadastro-sem-permissao" />;
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [items, setItems] = useState<LayoutItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [tiposCampo, setTiposCampo] = useState<SelectOption[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LayoutItem | null>(null);
  const [descricao, setDescricao] = useState("");
  const [flags, setFlags] = useState<Record<string, boolean>>({});
  const [saving, setSaving] = useState(false);

  const [campos, setCampos] = useState<Campo[]>([]);
  const [camposLoading, setCamposLoading] = useState(false);
  const [campoFormOpen, setCampoFormOpen] = useState(false);
  const [editingCampo, setEditingCampo] = useState<Campo | null>(null);
  const [campo1, setCampo1] = useState("");
  const [campo2, setCampo2] = useState("");
  const [tipoCampo, setTipoCampo] = useState<number | null>(null);
  const [unidadeMedida, setUnidadeMedida] = useState("");
  const [decimais, setDecimais] = useState("0");
  const [campoSaving, setCampoSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
    })();
  }, [router]);

  const carregar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const [jl, jt] = await Promise.all([
        apiGet(conn, "/api/layout"),
        apiGet(conn, "/api/layout/tipos-campo"),
      ]);
      if (jl?.success) setItems(jl.items || []);
      if (jt?.success) setTiposCampo((jt.items || []).map((t: { codigo: number; tipo: string }) => ({ value: t.codigo, label: t.tipo })));
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao carregar layouts."));
    } finally {
      setLoading(false);
    }
  }, [conn, fb]);

  useEffect(() => { carregar(); }, [carregar]);

  const abrirNovo = () => {
    setEditing(null);
    setDescricao("");
    setFlags({});
    setCampos([]);
    setFormOpen(true);
  };

  const abrirEdicao = async (item: LayoutItem) => {
    setEditing(item);
    setDescricao(item.descricao);
    setFlags({
      cliente: item.cliente, fornecedor: item.fornecedor, funcionario: item.funcionario,
      produto: item.produto, servico: item.servico, pedido_venda: item.pedido_venda,
      os: item.os, profissional: item.profissional, contrato: item.contrato,
    });
    setFormOpen(true);
    setCamposLoading(true);
    try {
      const j = await apiGet(conn!, "/api/layout/campos", { layout: item.codigo });
      setCampos(j?.success ? j.items || [] : []);
    } finally {
      setCamposLoading(false);
    }
  };

  const salvarLayout = async () => {
    if (!conn) return;
    if (!descricao.trim()) { fb.showWarning("Informe a descrição do layout."); return; }
    setSaving(true);
    try {
      const body = { descricao: descricao.trim(), ...flags, ...auditCtx };
      const j = editing
        ? await apiSend(conn, `/api/layout/${editing.codigo}`, "PUT", body)
        : await apiSend(conn, "/api/layout", "POST", body);
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao gravar layout.")); return; }
      fb.showSuccess("Layout gravado.");
      const jl = await apiGet(conn, "/api/layout");
      const novosItems: LayoutItem[] = jl?.success ? jl.items || [] : [];
      setItems(novosItems);
      const codigoGravado = editing ? editing.codigo : j.codigo;
      const atualizado = novosItems.find((it) => it.codigo === codigoGravado);
      if (atualizado) setEditing(atualizado);
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar layout."));
    } finally {
      setSaving(false);
    }
  };

  const excluirLayout = async (item: LayoutItem) => {
    if (!conn) return;
    fb.showConfirm(`Excluir o layout "${item.descricao}"?`, async () => {
      try {
        const j = await apiDelete(conn, `/api/layout/${item.codigo}`, auditCtx as unknown as Record<string, string | number>);
        if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao excluir.")); return; }
        fb.showSuccess("Layout excluído.");
        setFormOpen(false);
        carregar();
      } catch (e) {
        fb.showError(friendlyCatchError(e, "Falha ao excluir."));
      }
    });
  };

  const abrirNovoCampo = () => {
    setEditingCampo(null);
    setCampo1(""); setCampo2(""); setTipoCampo(null); setUnidadeMedida(""); setDecimais("0");
    setCampoFormOpen(true);
  };

  const abrirEdicaoCampo = (c: Campo) => {
    setEditingCampo(c);
    setCampo1(c.campo1); setCampo2(c.campo2); setTipoCampo(c.tipo);
    setUnidadeMedida(c.unidade_medida); setDecimais(String(c.decimais));
    setCampoFormOpen(true);
  };

  const salvarCampo = async () => {
    if (!conn || !editing) return;
    if (!campo1.trim() || !tipoCampo) { fb.showWarning("Informe o nome do campo e o tipo."); return; }
    setCampoSaving(true);
    try {
      const body = {
        layout: editing.codigo, campo1: campo1.trim(), campo2: campo2.trim(), tipo: tipoCampo,
        unidade_medida: unidadeMedida.trim(), decimais: parseInt(decimais, 10) || 0,
        ...auditCtx,
      };
      const j = editingCampo
        ? await apiSend(conn, `/api/layout/campos/${editingCampo.codigo}`, "PUT", body)
        : await apiSend(conn, "/api/layout/campos", "POST", body);
      if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao gravar campo.")); return; }
      fb.showSuccess("Campo gravado.");
      setCampoFormOpen(false);
      const jc = await apiGet(conn, "/api/layout/campos", { layout: editing.codigo });
      setCampos(jc?.success ? jc.items || [] : []);
    } catch (e) {
      fb.showError(friendlyCatchError(e, "Falha ao gravar campo."));
    } finally {
      setCampoSaving(false);
    }
  };

  const excluirCampo = async (c: Campo) => {
    if (!conn || !editing) return;
    fb.showConfirm(`Excluir o campo "${c.campo1}"?`, async () => {
      try {
        const j = await apiDelete(conn, `/api/layout/campos/${c.codigo}`, auditCtx as unknown as Record<string, string | number>);
        if (!j?.success) { fb.showError(friendlyApiError(j, "Falha ao excluir campo.")); return; }
        fb.showSuccess("Campo excluído.");
        const jc = await apiGet(conn, "/api/layout/campos", { layout: editing.codigo });
        setCampos(jc?.success ? jc.items || [] : []);
      } catch (e) {
        fb.showError(friendlyCatchError(e, "Falha ao excluir campo."));
      }
    });
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="layout-cadastro-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12} testID="layout-cadastro-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Cadastro de Layout</Text>
        {can("LAYOUT.GRAVAR") ? (
          <Pressable onPress={abrirNovo} style={styles.headerAddBtn} testID="layout-cadastro-novo">
            <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} /> : null}
          {!loading && items.length === 0 ? (
            <Text style={styles.emptyText}>Nenhum layout cadastrado ainda.</Text>
          ) : null}
          {items.map((it) => (
            <Pressable key={it.codigo} onPress={() => abrirEdicao(it)} style={styles.card} testID={`layout-cadastro-item-${it.codigo}`}>
              <Ionicons name="document-text-outline" size={20} color={colors.brandPrimary} />
              <View style={{ flex: 1 }}>
                <Text style={styles.cardTitle}>{it.descricao}</Text>
                <Text style={styles.cardSub}>
                  {ENTIDADES.filter((e) => it[e.key]).map((e) => e.label).join(", ") || "Sem entidade associada (ou Agenda, por serviço/profissional)"}
                </Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          ))}
        </View>
      </ScrollView>

      {/* -------- Form de Layout -------- */}
      <AppModal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={mstyles.bg} onPress={() => setFormOpen(false)}>
          <Pressable style={mstyles.card} onPress={(e) => e.stopPropagation()}>
            <View style={mstyles.header}>
              <Text style={mstyles.title}>{editing ? "Editar Layout" : "Novo Layout"}</Text>
              <Pressable onPress={() => setFormOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 560 }}>
              <Text style={mstyles.fieldLabel}>Descrição</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                style={mstyles.input}
                placeholder="Ex.: Ficha de Anamnese"
                placeholderTextColor={colors.muted}
                testID="layout-cadastro-descricao"
              />
              <Text style={[mstyles.fieldLabel, { marginTop: spacing.md }]}>Entidades onde este layout aparece</Text>
              <Text style={mstyles.hint}>
                Agenda não tem opção aqui — ela associa layouts por Serviço/Profissional (ver botão "Formulários" no atendimento).
              </Text>
              <View style={mstyles.flagsGrid}>
                {ENTIDADES.map((e) => (
                  <Pressable
                    key={e.key}
                    onPress={() => setFlags((prev) => ({ ...prev, [e.key]: !prev[e.key] }))}
                    style={mstyles.flagRow}
                    testID={`layout-cadastro-flag-${e.key}`}
                  >
                    <Ionicons name={flags[e.key] ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={mstyles.flagLabel}>{e.label}</Text>
                  </Pressable>
                ))}
              </View>

              <View style={mstyles.btnRow}>
                {editing && can("LAYOUT.EXCLUIR") ? (
                  <Pressable onPress={() => excluirLayout(editing)} style={mstyles.deleteBtn} testID="layout-cadastro-excluir">
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                ) : null}
                <Pressable onPress={salvarLayout} disabled={saving} style={[mstyles.primaryBtn, { flex: 1 }, saving && { opacity: 0.7 }]} testID="layout-cadastro-salvar">
                  {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={mstyles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              </View>

              {editing ? (
                <>
                  <View style={mstyles.divider} />
                  <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
                    <Text style={mstyles.sectionTitle}>Campos do layout</Text>
                    <Pressable onPress={abrirNovoCampo} style={mstyles.addBtnSmall} testID="layout-cadastro-novo-campo">
                      <Ionicons name="add" size={16} color={colors.brandPrimary} />
                      <Text style={mstyles.addBtnSmallText}>Campo</Text>
                    </Pressable>
                  </View>
                  {camposLoading ? <ActivityIndicator color={colors.brandPrimary} /> : null}
                  {!camposLoading && campos.length === 0 ? (
                    <Text style={mstyles.hint}>Nenhum campo cadastrado ainda.</Text>
                  ) : null}
                  {campos.map((c) => (
                    <Pressable key={c.codigo} onPress={() => abrirEdicaoCampo(c)} style={mstyles.campoRow} testID={`layout-cadastro-campo-${c.codigo}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={mstyles.campoNome}>{c.campo1}{c.campo2 ? ` — ${c.campo2}` : ""}</Text>
                        <Text style={mstyles.hint}>{c.tipo_descricao}{c.unidade_medida ? ` (${c.unidade_medida})` : ""}</Text>
                      </View>
                      <Pressable onPress={() => excluirCampo(c)} hitSlop={8} testID={`layout-cadastro-campo-excluir-${c.codigo}`}>
                        <Ionicons name="trash-outline" size={16} color={colors.error} />
                      </Pressable>
                    </Pressable>
                  ))}
                </>
              ) : (
                <Text style={[mstyles.hint, { marginTop: spacing.md }]}>Grave o layout primeiro para poder adicionar campos.</Text>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* -------- Form de Campo -------- */}
      <AppModal visible={campoFormOpen} transparent animationType="slide" onRequestClose={() => setCampoFormOpen(false)}>
        <Pressable style={mstyles.bg} onPress={() => setCampoFormOpen(false)}>
          <Pressable style={mstyles.cardNarrow} onPress={(e) => e.stopPropagation()}>
            <View style={mstyles.header}>
              <Text style={mstyles.title}>{editingCampo ? "Editar Campo" : "Novo Campo"}</Text>
              <Pressable onPress={() => setCampoFormOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={mstyles.fieldLabel}>Nome do campo</Text>
            <TextInput value={campo1} onChangeText={setCampo1} style={mstyles.input} placeholder="Ex.: Peso" placeholderTextColor={colors.muted} testID="layout-campo-campo1" />
            <Text style={[mstyles.fieldLabel, { marginTop: spacing.sm }]}>Subcampo (opcional)</Text>
            <TextInput value={campo2} onChangeText={setCampo2} style={mstyles.input} placeholder="Ex.: Kg" placeholderTextColor={colors.muted} testID="layout-campo-campo2" />
            <Text style={[mstyles.fieldLabel, { marginTop: spacing.sm }]}>Tipo</Text>
            <SelectField value={tipoCampo} onChange={(v) => setTipoCampo(v as number | null)} options={tiposCampo} compactWeb testID="layout-campo-tipo" />
            <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
              <View style={{ flex: 1 }}>
                <Text style={mstyles.fieldLabel}>Unidade</Text>
                <TextInput value={unidadeMedida} onChangeText={setUnidadeMedida} style={mstyles.input} placeholder="Kg, cm…" placeholderTextColor={colors.muted} testID="layout-campo-unidade" />
              </View>
              <View style={{ width: 90 }}>
                <Text style={mstyles.fieldLabel}>Decimais</Text>
                <TextInput value={decimais} onChangeText={setDecimais} style={mstyles.input} keyboardType="number-pad" testID="layout-campo-decimais" />
              </View>
            </View>
            <View style={mstyles.btnRow}>
              <Pressable onPress={() => setCampoFormOpen(false)} style={mstyles.secondaryBtn}>
                <Text style={mstyles.secondaryBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable onPress={salvarCampo} disabled={campoSaving} style={[mstyles.primaryBtn, { flex: 1 }, campoSaving && { opacity: 0.7 }]} testID="layout-campo-salvar">
                {campoSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={mstyles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md,
    paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  headerAddBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
    borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.18)",
  },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  emptyText: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: spacing.xl },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm,
  },
  cardTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
});

const mstyles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: isWeb ? "center" : "flex-end", alignItems: "center", padding: isWeb ? spacing.xl : 0 },
  card: {
    width: "100%", maxWidth: 560, maxHeight: "88%",
    backgroundColor: colors.surface, padding: spacing.lg,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    ...(isWeb ? { borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg, borderWidth: 1, borderColor: colors.border } : {}),
  },
  cardNarrow: {
    width: "100%", maxWidth: 420,
    backgroundColor: colors.surface, padding: spacing.lg,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    ...(isWeb ? { borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg, borderWidth: 1, borderColor: colors.border } : {}),
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 16, fontWeight: "600", color: colors.onSurface },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.sm },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  flagsGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginBottom: spacing.md },
  flagRow: { flexDirection: "row", alignItems: "center", gap: 6, width: "48%" },
  flagLabel: { fontSize: 13, color: colors.onSurface },
  btnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: { paddingVertical: 12, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 14 },
  secondaryBtn: { flex: 1, paddingVertical: 12, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "500", fontSize: 14 },
  deleteBtn: { width: 44, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  sectionTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  addBtnSmall: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary },
  addBtnSmallText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 12 },
  campoRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  campoNome: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
});
