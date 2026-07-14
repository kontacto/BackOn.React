import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Funcao = {
  codigo: string;
  descricao: string;
  permite_altera_caixa: boolean;
  cancelar_os: boolean;
  alterar_tecnico_responsavel: boolean;
  funcao_vendedor: boolean;
  funcao_executor: boolean;
  funcao_atendente: boolean;
  libera_cliente_debito: boolean;
};

// Cadastro/Tabelas Auxiliares > Funções (tabela `funcoes`). Legado: FrmManFun.
// Código é digitado pelo usuário (numérico, formatado com zero à esquerda até
// 2 dígitos — mesma regra do VB6 `Format(Campo(0), "00")`) — upsert-by-codigo,
// travado depois de criado, mesmo padrão de Icms/Situação/Centro de Custo.
// `funcionarios.cod_funcao` referencia este código de verdade (soft FK, sem
// constraint de banco) — usado para gating de gerente/supervisor
// (isManagerFuncao) — por isso a exclusão bloqueia se houver funcionário
// vinculado.
export default function FuncoesScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Funções está disponível apenas no web."
        testID="funcoes-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Funcao[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [permiteAlteraCaixa, setPermiteAlteraCaixa] = useState(false);
  const [liberaClienteDebito, setLiberaClienteDebito] = useState(false);
  const [cancelarOs, setCancelarOs] = useState(false);
  const [alterarTecnicoResponsavel, setAlterarTecnicoResponsavel] = useState(false);
  const [funcaoExecutor, setFuncaoExecutor] = useState(false);
  const [funcaoVendedor, setFuncaoVendedor] = useState(false);
  const [funcaoAtendente, setFuncaoAtendente] = useState(false);
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/funcoes?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
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
    })();
  }, [router, load]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditCod(null); setCodigo(""); setDescricao("");
    setPermiteAlteraCaixa(false); setLiberaClienteDebito(false);
    setCancelarOs(false); setAlterarTecnicoResponsavel(false);
    setFuncaoExecutor(false); setFuncaoVendedor(false); setFuncaoAtendente(false);
    setFormOpen(true);
  };
  const openEdit = (f: Funcao) => {
    setEditCod(f.codigo); setCodigo(f.codigo); setDescricao(f.descricao);
    setPermiteAlteraCaixa(f.permite_altera_caixa); setLiberaClienteDebito(f.libera_cliente_debito);
    setCancelarOs(f.cancelar_os); setAlterarTecnicoResponsavel(f.alterar_tecnico_responsavel);
    setFuncaoExecutor(f.funcao_executor); setFuncaoVendedor(f.funcao_vendedor); setFuncaoAtendente(f.funcao_atendente);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    if (!codigo.trim()) { showToast("Informe o código."); return; }
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/funcoes`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: codigo.trim(), descricao: descricao.trim(),
          permite_altera_caixa: permiteAlteraCaixa,
          libera_cliente_debito: liberaClienteDebito,
          cancelar_os: cancelarOs,
          alterar_tecnico_responsavel: alterarTecnicoResponsavel,
          funcao_executor: funcaoExecutor,
          funcao_vendedor: funcaoVendedor,
          funcao_atendente: funcaoAtendente,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Função gravada."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (f: Funcao) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/funcoes/${encodeURIComponent(f.codigo)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("FUNCOES.GRAVAR") || isMaster;
  const canDel = can("FUNCOES.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="funcoes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Funções</Text>
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
            testID="funcoes-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma função cadastrada.</Text> : null}
          {items.map((f) => (
            <View key={f.codigo} style={styles.row} testID={`funcoes-${f.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(f)}>
                <Text style={styles.rowTitle}>{f.codigo} · {f.descricao}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(f)} hitSlop={8} testID={`funcoes-del-${f.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="funcoes-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod ? `Função ${editCod}` : "Nova função"}</Text>

              <Text style={styles.label}>Código *</Text>
              <TextInput
                value={codigo}
                onChangeText={(v) => setCodigo(v.toUpperCase())}
                placeholder="Ex.: 01"
                placeholderTextColor={colors.muted}
                style={[styles.input, editCod != null && styles.inputDisabled]}
                editable={editCod == null}
                maxLength={3}
                autoCapitalize="characters"
                testID="funcoes-codigo"
              />

              <Text style={styles.label}>Descrição *</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: GERENTE"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={30}
                autoCapitalize="characters"
                testID="funcoes-descricao"
              />

              <Text style={styles.sectionLabel}>Permissões Financeiro</Text>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Permite Alterações no Fluxo de Caixa?</Text>
                <Switch value={permiteAlteraCaixa} onValueChange={setPermiteAlteraCaixa} testID="funcoes-altera-caixa-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Libera Cliente com Débito</Text>
                <Switch value={liberaClienteDebito} onValueChange={setLiberaClienteDebito} testID="funcoes-libera-debito-switch" />
              </View>

              <Text style={styles.sectionLabel}>Permissões Ordens de Serviço</Text>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Cancelar O.S</Text>
                <Switch value={cancelarOs} onValueChange={setCancelarOs} testID="funcoes-cancelar-os-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Alterar Técnico Responsável</Text>
                <Switch value={alterarTecnicoResponsavel} onValueChange={setAlterarTecnicoResponsavel} testID="funcoes-altera-tecnico-switch" />
              </View>

              <Text style={styles.sectionLabel}>Função de</Text>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Executor</Text>
                <Switch value={funcaoExecutor} onValueChange={setFuncaoExecutor} testID="funcoes-executor-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Vendedor</Text>
                <Switch value={funcaoVendedor} onValueChange={setFuncaoVendedor} testID="funcoes-vendedor-switch" />
              </View>
              <View style={styles.switchRow}>
                <Text style={styles.label}>Atendente</Text>
                <Switch value={funcaoAtendente} onValueChange={setFuncaoAtendente} testID="funcoes-atendente-switch" />
              </View>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="funcoes-salvar">
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
  webShell: { width: "100%", maxWidth: 560, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
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
    maxWidth: Platform.OS === "web" ? 480 : undefined,
    maxHeight: "85%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionLabel: { fontSize: 12, color: colors.brandPrimary, fontWeight: "700", marginTop: spacing.md, textTransform: "uppercase" },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4, flex: 1, marginRight: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  switchRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
