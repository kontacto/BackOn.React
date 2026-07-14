import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, View,
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
import { buildTree, NivelFlat, NivelNode } from "@/src/utils/nivelTree";

type Conn = { servidor: string; banco: string; api: string };

// Cadastro/Tabelas Auxiliares > Executor Padrão OS (tabela `executor_padrao`,
// PK composta nivel1..nivel5 + `executor` -> funcionarios.codigo_int). Legado:
// FrmExePad ("Executor Padrão..."). Reaproveita a mesma árvore de níveis de
// Grupo Mercadológico (`nivelTree.ts`/`GET /api/tabelas/grupos-mercadologicos`)
// em vez de duplicar a lógica. Só folhas da árvore podem receber um executor
// padrão (mesma regra do legado — "Devem ser Selecionados todos os Níveis
// Possíveis"). Ainda não consumido por nenhuma tela: é metadado pra uso
// futuro da tela de O.S., que vai sugerir o(s) executor(es) ao selecionar um
// produto/serviço daquele nível.
export default function ExecutorPadraoScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Executor Padrão OS está disponível apenas no web."
        testID="executor-padrao-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [flat, setFlat] = useState<NivelFlat[]>([]);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const [funcionarioOptions, setFuncionarioOptions] = useState<SelectOption[]>([]);
  const [selecionado, setSelecionado] = useState<NivelNode | null>(null);
  const [executor, setExecutor] = useState<number | null>(null);
  const [loadingExecutor, setLoadingExecutor] = useState(false);
  const [saving, setSaving] = useState(false);

  const tree = useMemo(() => buildTree(flat), [flat]);
  const canSave = can("EXECUTOR_PADRAO.GRAVAR") || isMaster;
  const canDel = can("EXECUTOR_PADRAO.EXCLUIR") || isMaster;

  const loadNiveis = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/grupos-mercadologicos?${qs}`);
      const j = await r.json();
      setFlat(j?.success ? j.items || [] : []);
    } catch { setFlat([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      loadNiveis(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
        const r = await fetch(`${base}/api/funcionarios?${qs}`);
        const j = await r.json();
        if (j?.success) {
          setFuncionarioOptions((j.items || []).map((f: any) => ({
            value: f.codigo, label: f.nome_guerra || f.nome, sub: `#${f.codigo}`,
          })));
        }
      } catch {
        // silencioso
      }
    })();
  }, [router, loadNiveis]);

  const toggleExpand = (cod: number) => {
    const next = new Set(expanded);
    if (next.has(cod)) next.delete(cod); else next.add(cod);
    setExpanded(next);
  };

  const selectLeaf = async (n: NivelNode) => {
    if (!conn) return;
    setSelecionado(n);
    setExecutor(null);
    setLoadingExecutor(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}` +
        `&nivel1=${encodeURIComponent(n.nivel1)}&nivel2=${encodeURIComponent(n.nivel2)}` +
        `&nivel3=${encodeURIComponent(n.nivel3)}&nivel4=${encodeURIComponent(n.nivel4)}&nivel5=${encodeURIComponent(n.nivel5)}`;
      const r = await fetch(`${base}/api/tabelas/executor-padrao?${qs}`);
      const j = await r.json();
      if (j?.success) setExecutor(j.executor ?? null);
    } catch {
      // silencioso
    } finally { setLoadingExecutor(false); }
  };

  const save = async () => {
    if (!conn || !selecionado) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/executor-padrao`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          nivel1: selecionado.nivel1, nivel2: selecionado.nivel2, nivel3: selecionado.nivel3,
          nivel4: selecionado.nivel4, nivel5: selecionado.nivel5, executor,
        }),
      });
      const j = await r.json();
      if (j?.success) fb.showSuccess(j.message || "Registro gravado.");
      else fb.showError(j?.message || "Falha ao gravar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async () => {
    if (!conn || !selecionado) return;
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/executor-padrao/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          nivel1: selecionado.nivel1, nivel2: selecionado.nivel2, nivel3: selecionado.nivel3,
          nivel4: selecionado.nivel4, nivel5: selecionado.nivel5,
        }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Registro excluído."); setExecutor(null); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const renderNode = (n: NivelNode) => {
    const isOpen = expanded.has(n.cod_nivel);
    const hasChildren = n.children.length > 0;
    const isSelected = selecionado?.cod_nivel === n.cod_nivel;
    return (
      <View key={n.cod_nivel} style={{ marginLeft: (n.depth - 1) * spacing.lg }}>
        <View style={[styles.row, isSelected && styles.rowSelected]} testID={`executor-padrao-nivel-${n.cod_nivel}`}>
          <Pressable onPress={() => hasChildren && toggleExpand(n.cod_nivel)} hitSlop={8} style={{ opacity: hasChildren ? 1 : 0.25 }}>
            <Ionicons name={isOpen ? "chevron-down" : "chevron-forward"} size={16} color={colors.muted} />
          </Pressable>
          <Ionicons name={hasChildren ? "folder-outline" : "person-outline"} size={16} color={colors.brandPrimary} />
          <Pressable style={{ flex: 1 }} onPress={() => (hasChildren ? toggleExpand(n.cod_nivel) : selectLeaf(n))}>
            <Text style={[styles.rowTitle, isSelected && styles.rowTitleSelected]}>{n.descricao}</Text>
          </Pressable>
        </View>
        {isOpen ? n.children.map(renderNode) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="executor-padrao-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Executor Padrão OS</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.colTree}>
          <Text style={styles.colTitulo}>Selecione o Nível</Text>
          <ScrollView contentContainerStyle={styles.treeScroll}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
            {!loading && tree.length === 0 ? <Text style={styles.empty}>Nenhum nível cadastrado.</Text> : null}
            {tree.map(renderNode)}
          </ScrollView>
        </View>

        <View style={styles.colForm}>
          <Text style={styles.colTitulo}>Executor Padrão</Text>
          {!selecionado ? (
            <Text style={styles.empty}>Selecione uma folha da árvore ao lado.</Text>
          ) : (
            <>
              <Text style={styles.selecionadoDesc}>{selecionado.descricao}</Text>
              {loadingExecutor ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.sm }} /> : (
                <SelectField
                  value={executor}
                  onChange={(v) => setExecutor(v as number | null)}
                  options={funcionarioOptions}
                  placeholder="Nenhum"
                  allowClear
                  testID="executor-padrao-funcionario"
                  modalTitle="Executor Padrão"
                  compactWeb
                />
              )}

              {canSave ? (
                <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="executor-padrao-gravar">
                  {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              ) : null}
              {canDel ? (
                <Pressable onPress={remove} disabled={saving} style={[styles.dangerBtn, saving && { opacity: 0.6 }]} testID="executor-padrao-excluir">
                  <Text style={styles.dangerBtnText}>Excluir</Text>
                </Pressable>
              ) : null}
            </>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { flex: 1, flexDirection: "row", gap: spacing.md, padding: spacing.lg, maxWidth: 900, width: "100%", alignSelf: "center" },
  colTree: { flex: 2, gap: spacing.xs },
  colForm: { flex: 1, gap: spacing.xs, borderLeftWidth: 1, borderLeftColor: colors.border, paddingLeft: spacing.md },
  colTitulo: { fontSize: 14, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  treeScroll: { paddingBottom: 40 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24, fontSize: 12 },
  row: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 8, paddingHorizontal: spacing.xs, borderRadius: radius.sm,
  },
  rowSelected: { backgroundColor: colors.brandPrimary },
  rowTitle: { fontSize: 13, color: colors.onSurface },
  rowTitleSelected: { color: "#fff", fontWeight: "700" },
  selecionadoDesc: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary, marginBottom: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 14 },
  dangerBtn: { borderWidth: 1, borderColor: colors.error, borderRadius: radius.pill, paddingVertical: 12, alignItems: "center", marginTop: spacing.sm },
  dangerBtnText: { color: colors.error, fontWeight: "700", fontSize: 14 },
});
