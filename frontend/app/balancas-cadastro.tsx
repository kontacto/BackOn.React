import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Alert, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = Connection;

type BalancaItem = {
  codigo: number;
  descricao: string;
  pasta_integracao: string;
  ativo: boolean;
};

// Cadastro de Balanças (Automação Comercial — pré-pesagem com etiqueta de
// peso variável). Tabela genuinamente NOVA (sem tela legada equivalente —
// balança nunca existiu no legado VB6), então segue a "Exception — compact
// single-view screens" do CLAUDE.md (mesmo padrão de cilindro-cadastro.tsx/
// fornecedores.tsx): lista+form no mesmo arquivo, sem abas.
//
// Este backend só GERA o arquivo ITENSMGV.TXT e grava na pasta de
// integração configurada — NUNCA fala com o MGV6/MGV7 nem com a balança
// diretamente (fluxo real confirmado com o fabricante Toledo, ver
// backend/services/balanca_service.py e PENDENCIAS.md > "KPDV" > "Balança
// Toledo + Pré-Pesagem"). Depois de "Exportar Carga", o operador ainda
// precisa abrir o MGV na loja e fazer Importação → Carga → Enviar.
export default function BalancasCadastroScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cadastro de Balanças está disponível apenas no web."
        testID="balancas-cadastro-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<BalancaItem[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [exportando, setExportando] = useState<number | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editingCodigo, setEditingCodigo] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const [descricao, setDescricao] = useState("");
  const [pastaIntegracao, setPastaIntegracao] = useState("");
  const [ativo, setAtivo] = useState(true);

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(search)}`;
      const r = await fetch(`${base}/api/balancas?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
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

  const resetForm = () => {
    setDescricao("");
    setPastaIntegracao("");
    setAtivo(true);
  };

  const openNew = () => {
    setEditingCodigo(null);
    resetForm();
    setFormOpen(true);
  };

  const openEdit = async (item: BalancaItem) => {
    if (!conn) return;
    setEditingCodigo(item.codigo);
    setFormOpen(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/balancas/${item.codigo}?${qs}`);
      const j = await r.json();
      if (!j?.success) { fb.showError(j?.message || "Erro ao carregar."); setFormOpen(false); return; }
      const d = j.item;
      setDescricao(d.descricao || "");
      setPastaIntegracao(d.pasta_integracao || "");
      setAtivo(d.ativo ?? true);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      setFormOpen(false);
    }
  };

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { fb.showWarning("Informe a Descrição."); return; }
    if (!pastaIntegracao.trim()) { fb.showWarning("Informe a Pasta de Integração."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/balancas`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          codigo: editingCodigo,
          dados: { descricao: descricao.trim(), pasta_integracao: pastaIntegracao.trim(), ativo },
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Balança gravada.");
        setEditingCodigo(j.codigo);
        load(conn);
      } else {
        fb.showError(j?.message || "Falha ao gravar.");
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSaving(false);
    }
  };

  const remove = (item: BalancaItem) => {
    if (!conn) return;
    Alert.alert("Excluir", `Confirma a exclusão da balança "${item.descricao}"?`, [
      { text: "Cancelar", style: "cancel" },
      {
        text: "Excluir",
        style: "destructive",
        onPress: async () => {
          try {
            const base = conn.api.replace(/\/+$/, "");
            const r = await fetch(`${base}/api/balancas/${item.codigo}/excluir`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
            });
            const j = await r.json();
            if (j?.success) {
              fb.showSuccess(j.message || "Excluída.");
              if (editingCodigo === item.codigo) setFormOpen(false);
              load(conn);
            } else {
              fb.showError(j?.message || "Falha ao excluir.");
            }
          } catch (e) {
            fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
          }
        },
      },
    ]);
  };

  // "Exportar Carga" — gera o ITENSMGV.TXT com os produtos vendidos por
  // peso e grava na pasta configurada. NÃO fala com o MGV nem com a balança
  // — ver o aviso no topo do arquivo. Feedback visual >3s (regra [GLOBAL]):
  // spinner no próprio botão enquanto processa.
  const exportarCarga = async (item: BalancaItem) => {
    if (!conn) return;
    setExportando(item.codigo);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/balancas/${item.codigo}/exportar-carga`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      if (j?.success) fb.showSuccess(j.message || "Carga exportada.", undefined, 5000);
      else fb.showError(j?.message || "Falha ao exportar.", undefined, 5000);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setExportando(null);
    }
  };

  const canSave = can("BALANCA.GRAVAR") || isMaster;
  const canDel = can("BALANCA.EXCLUIR") || isMaster;

  // ============================================================
  // Formulário (tela cheia, compacta — sem abas)
  // ============================================================
  if (formOpen) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="balancas-cadastro-form-screen">
        <View style={styles.header}>
          <Pressable onPress={() => setFormOpen(false)} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="balancas-cadastro-form-back-button">
            <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
          </Pressable>
          <Text style={styles.headerTitle} numberOfLines={1}>{editingCodigo ? `Balança #${editingCodigo}` : "Nova Balança"}</Text>
          {canSave ? (
            <Pressable onPress={save} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="balancas-cadastro-salvar">
              {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                <>
                  <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                  <Text style={styles.saveLabel}>Gravar</Text>
                </>
              )}
            </Pressable>
          ) : <View style={{ width: 40 }} />}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
          <View style={styles.webShell}>
            <View style={styles.card}>
              <Text style={styles.label}>Descrição *</Text>
              <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} maxLength={80} testID="balanca-descricao" />

              <Text style={styles.label}>Pasta de Integração *</Text>
              <TextInput
                value={pastaIntegracao}
                onChangeText={setPastaIntegracao}
                placeholder={"\\\\SERVIDOR\\Integracao\\Balanca ou C:\\MGV6\\Import"}
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={260}
                autoCapitalize="none"
                autoCorrect={false}
                testID="balanca-pasta-integracao"
              />
              <Text style={styles.hint}>
                Pasta (local ou de rede) que o MGV6/MGV7 desta balança fica monitorando pra importar
                produtos. Depois de "Exportar Carga", abra o MGV na loja e faça Importação → Itens →
                Importar, e depois Carga → Enviar — este sistema só gera o arquivo, quem fala com a
                balança de verdade é o MGV.
              </Text>

              <Text style={styles.label}>Ativa</Text>
              <View style={styles.switchInline}>
                <Switch value={ativo} onValueChange={setAtivo} trackColor={{ false: colors.border, true: colors.brandPrimary }} testID="balanca-ativo" />
              </View>
            </View>

            {editingCodigo && canDel ? (
              <View style={styles.toolbarRow}>
                <Pressable
                  onPress={() => remove({ codigo: editingCodigo, descricao, pasta_integracao: pastaIntegracao, ativo })}
                  style={[styles.secondaryBtn, styles.dangerBtn]}
                  testID="balanca-excluir"
                >
                  <Ionicons name="trash-outline" size={16} color={colors.error} />
                  <Text style={styles.dangerBtnText}>Excluir Balança</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ============================================================
  // Lista / Consulta
  // ============================================================
  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="balancas-cadastro-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Cadastro de Balanças</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.listShell}>
        <Text style={styles.intro}>
          Cada balança de pré-pesagem tem seu próprio MGV6/MGV7 monitorando uma pasta. "Exportar
          Carga" gera o arquivo com os produtos vendidos por peso — o restante (Importação e Envio)
          é feito manualmente no MGV, na loja.
        </Text>

        <View style={styles.filterBox}>
          <TextInput value={search} onChangeText={setSearch} placeholder="Buscar por descrição…" placeholderTextColor={colors.muted} style={styles.input} testID="balancas-search" />
        </View>

        <ScrollView contentContainerStyle={[styles.listScroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma balança cadastrada.</Text> : null}
          {items.map((it) => (
            <View key={it.codigo} style={styles.row} testID={`balanca-${it.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(it)}>
                <Text style={styles.rowTitle}>{it.descricao}{!it.ativo ? " (inativa)" : ""}</Text>
                <Text style={styles.rowSub} numberOfLines={1}>{it.pasta_integracao}</Text>
              </Pressable>
              <Pressable
                onPress={() => exportarCarga(it)}
                disabled={exportando === it.codigo}
                style={styles.exportBtn}
                hitSlop={8}
                testID={`balanca-exportar-${it.codigo}`}
              >
                {exportando === it.codigo ? (
                  <ActivityIndicator color={colors.brandPrimary} size="small" />
                ) : (
                  <Ionicons name="cloud-upload-outline" size={20} color={colors.brandPrimary} />
                )}
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(it)} hitSlop={8} testID={`balanca-del-${it.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="balancas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  listShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  intro: { paddingHorizontal: spacing.lg, paddingTop: spacing.md, color: colors.muted, fontSize: 12, lineHeight: 17 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  listScroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: { flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  exportBtn: { width: 36, height: 36, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border },
  empty: { textAlign: "center", color: colors.muted, marginTop: 8, marginBottom: 8, fontSize: 12 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },

  scroll: { paddingBottom: spacing.xxxl },
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, lineHeight: 15 },
  switchInline: { paddingVertical: 11, alignItems: "flex-start" },

  toolbarRow: { flexDirection: "row", justifyContent: "flex-end", marginBottom: spacing.lg },
  secondaryBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary },
  dangerBtn: { backgroundColor: colors.surface, borderColor: colors.error },
  dangerBtnText: { fontSize: 13, fontWeight: "600", color: colors.error },
});
