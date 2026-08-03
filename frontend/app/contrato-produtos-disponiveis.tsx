import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
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
import { formatBRL, fmtNum } from "@/src/utils/format";

type Conn = { servidor: string; banco: string; api: string };
type ProdutoDisp = {
  produto: string; descricao: string | null; preco: number; qtd: number; qtd_alocada: number; situacao: string; obs: string;
};

// Transações > Contratos > Produtos Disponíveis (tabela
// `contratos_produtos_disponiveis`, migração de FrmConPDI.frm) — catálogo
// de produto/equipamento/serviço/cilindro liberado pra uso em Contratos,
// com quantidade total e quantidade já alocada. `qtd=0` = ilimitado (mesma
// regra do legado, ver contratos_service.py `_checar_disponibilidade_sync`).
export default function ContratoProdutosDisponiveisScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Produtos Disponíveis está disponível apenas no web."
        testID="contrato-prod-disp-web-only"
      />
    );
  }

  if (!moduleOn("contratos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Contratos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="contrato-prod-disp-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<ProdutoDisp[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editando, setEditando] = useState(false);
  const [produto, setProduto] = useState("");
  const [descricao, setDescricao] = useState("");
  const [resolvendo, setResolvendo] = useState(false);
  const [preco, setPreco] = useState("0");
  const [qtd, setQtd] = useState("0");
  const [situacao, setSituacao] = useState("A");
  const [obs, setObs] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 800); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/contratos/produtos-disponiveis?${qs}`);
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
    setEditando(false); setProduto(""); setDescricao(""); setPreco("0"); setQtd("0"); setSituacao("A"); setObs("");
    setFormOpen(true);
  };
  const openEdit = (p: ProdutoDisp) => {
    setEditando(true); setProduto(p.produto); setDescricao(p.descricao || "");
    setPreco(String(p.preco)); setQtd(String(p.qtd)); setSituacao(p.situacao); setObs(p.obs);
    setFormOpen(true);
  };

  const resolverProduto = async () => {
    if (!conn || editando || !produto.trim()) return;
    setResolvendo(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&termo=${encodeURIComponent(produto.trim())}`;
      const r = await fetch(`${base}/api/contratos/resolver-produto?${qs}`);
      const j = await r.json();
      if (j?.success) { setDescricao(j.descricao); setProduto(j.codigo); }
      else { setDescricao(""); showToast(j?.message || "Não encontrado."); }
    } catch { setDescricao(""); } finally { setResolvendo(false); }
  };

  const save = async () => {
    if (!conn) return;
    if (!produto.trim()) { showToast("Informe o Produto/Equipamento."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/produtos-disponiveis`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          produto: produto.trim(), preco: Number(preco) || 0, qtd: Number(qtd) || 0, situacao, obs,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Registro gravado."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (p: ProdutoDisp) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/contratos/produtos-disponiveis/${encodeURIComponent(p.produto)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("CONTR_PROD_DISP.GRAVAR") || isMaster;
  const canDel = can("CONTR_PROD_DISP.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contrato-prod-disp-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Produtos Disponíveis</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por código do produto…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="contrato-prod-disp-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum produto disponível cadastrado.</Text> : null}
          {items.map((p) => (
            <View key={p.produto} style={styles.row} testID={`contrato-prod-disp-${p.produto}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(p)}>
                <Text style={styles.rowTitle}>{p.produto} · {p.descricao || "(não encontrado)"}</Text>
                <Text style={styles.rowSub}>
                  {formatBRL(p.preco)} · Qtd {p.qtd === 0 ? "ilimitada" : fmtNum(p.qtd)} · Alocada {fmtNum(p.qtd_alocada)} · {p.situacao === "A" ? "Ativo" : p.situacao}
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(p)} hitSlop={8} testID={`contrato-prod-disp-del-${p.produto}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="contrato-prod-disp-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>{editando ? `Produto ${produto}` : "Novo Produto Disponível"}</Text>

            <Text style={styles.label}>Produto / Equipamento / Serviço / Cilindro</Text>
            <TextInput
              value={produto}
              onChangeText={(v) => { setProduto(v); setDescricao(""); }}
              onBlur={resolverProduto}
              editable={!editando}
              placeholder="Código"
              placeholderTextColor={colors.muted}
              style={[styles.input, editando && { opacity: 0.6 }]}
              autoCapitalize="characters"
              testID="contrato-prod-disp-codigo"
            />
            {resolvendo ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
            {descricao ? <Text style={styles.descricaoResolvida}>{descricao}</Text> : null}

            <View style={styles.rowFields}>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Preço</Text>
                <TextInput
                  value={preco} onChangeText={setPreco} keyboardType="decimal-pad"
                  style={styles.input} testID="contrato-prod-disp-preco"
                />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={styles.label}>Quantidade (0 = ilimitada)</Text>
                <TextInput
                  value={qtd} onChangeText={setQtd} keyboardType="decimal-pad"
                  style={styles.input} testID="contrato-prod-disp-qtd"
                />
              </View>
              <View style={{ width: 90 }}>
                <Text style={styles.label}>Situação</Text>
                <TextInput
                  value={situacao} onChangeText={(v) => setSituacao(v.toUpperCase().slice(0, 1))}
                  maxLength={1} style={styles.input} testID="contrato-prod-disp-situacao"
                />
              </View>
            </View>

            <Text style={styles.label}>Observação</Text>
            <TextInput
              value={obs} onChangeText={setObs} multiline
              style={[styles.input, { minHeight: 60, textAlignVertical: "top" }]}
              testID="contrato-prod-disp-obs"
            />

            <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="contrato-prod-disp-salvar">
              {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
            </Pressable>
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
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
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
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
    gap: spacing.sm,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  descricaoResolvida: { fontSize: 13, color: colors.brandPrimary, fontWeight: "600" },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
