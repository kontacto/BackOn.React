import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
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
type AreaAtuacao = {
  codigo: number;
  descricao: string;
  centro_custo: number | null;
  tipo_mov: string | null;
  modelo_os: number | null;
  modelo_pedido: number | null;
  intermediador: number | null;
  intermediador_identificacao: string | null;
};

// ============================================================
// Tela — Manutenção de Áreas de Atuação (web-only), tabela `area_atuacao`
// (classificação de Pedidos/O.S. — pedido_venda.area_atuacao / os.area_atuacao).
// Não confundir com `area` (Loja/Depósito, tela "Área" em Tabelas Auxiliares).
// ============================================================
export default function AreaAtuacaoScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Áreas de Atuação está disponível apenas no web."
        testID="area-atuacao-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<AreaAtuacao[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [centrosCusto, setCentrosCusto] = useState<LookupItem[]>([]);
  const [tiposMov, setTiposMov] = useState<LookupItem[]>([]);
  const [modelosOS, setModelosOS] = useState<LookupItem[]>([]);
  const [modelosPedido, setModelosPedido] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [descricao, setDescricao] = useState("");
  const [centroCusto, setCentroCusto] = useState<string>("");
  const [tipoMov, setTipoMov] = useState<string>("");
  const [modeloOS, setModeloOS] = useState<string>("");
  const [modeloPedido, setModeloPedido] = useState<string>("");
  const [intermediador, setIntermediador] = useState("");
  const [intermediadorId, setIntermediadorId] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/area-atuacao?${qs}`);
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
      fetchLookup("centro-custo", setCentrosCusto),
      fetchLookup("tipo-mov", setTiposMov),
      fetchLookup("modelo-os", setModelosOS),
      fetchLookup("modelo-pedido", setModelosPedido),
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
      load(cc);
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  const openNew = () => {
    setEditCod(null);
    setDescricao("");
    setCentroCusto("");
    setTipoMov("");
    setModeloOS("");
    setModeloPedido("");
    setIntermediador("");
    setIntermediadorId("");
    setFormOpen(true);
  };

  const openEdit = (a: AreaAtuacao) => {
    setEditCod(a.codigo);
    setDescricao(a.descricao);
    setCentroCusto(a.centro_custo != null ? String(a.centro_custo) : "");
    setTipoMov(a.tipo_mov || "");
    setModeloOS(a.modelo_os != null ? String(a.modelo_os) : "");
    setModeloPedido(a.modelo_pedido != null ? String(a.modelo_pedido) : "");
    setIntermediador(a.intermediador != null ? String(a.intermediador) : "");
    setIntermediadorId(a.intermediador_identificacao || "");
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/area-atuacao`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor,
          banco: conn.banco,
          ...auditCtx,
          codigo: editCod,
          descricao: descricao.trim(),
          centro_custo: centroCusto ? parseInt(centroCusto, 10) : null,
          tipo_mov: tipoMov || null,
          modelo_os: modeloOS ? parseInt(modeloOS, 10) : null,
          modelo_pedido: modeloPedido ? parseInt(modeloPedido, 10) : null,
          intermediador: intermediador ? parseInt(intermediador, 10) : null,
          intermediador_identificacao: intermediadorId.trim() || null,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Área de atuação gravada."); setFormOpen(false); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (a: AreaAtuacao) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/area-atuacao/${a.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("AREA_ATUACAO.GRAVAR") || isMaster;
  const canDel = can("AREA_ATUACAO.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="area-atuacao-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Áreas de Atuação</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma área de atuação cadastrada.</Text> : null}
          {items.map((a) => (
            <View key={a.codigo} style={styles.row} testID={`area-atuacao-${a.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(a)}>
                <Text style={styles.rowTitle}>{a.codigo} · {a.descricao}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(a)} hitSlop={8} testID={`area-atuacao-del-${a.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </View>
      </ScrollView>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="area-atuacao-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod != null ? `Área de Atuação ${editCod}` : "Nova área de atuação"}</Text>

              <Text style={styles.label}>Descrição</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Ex.: Loja"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={50}
                testID="area-atuacao-descricao"
              />

              <Text style={styles.label}>Centro Custo</Text>
              <SelectField
                value={centroCusto || null}
                onChange={(v) => setCentroCusto(v == null ? "" : String(v))}
                options={centrosCusto.map((i) => ({ value: i.codigo, label: i.descricao }))}
                placeholder="Selecione…"
                allowClear
                compactWeb
                testID="area-atuacao-centro-custo"
                modalTitle="Centro Custo"
              />

              <Text style={styles.label}>Tipo de Movimentação</Text>
              <SelectField
                value={tipoMov || null}
                onChange={(v) => setTipoMov(v == null ? "" : String(v))}
                options={tiposMov.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }))}
                placeholder="Selecione…"
                allowClear
                compactWeb
                testID="area-atuacao-tipo-mov"
                modalTitle="Tipo de Movimentação"
              />

              <Text style={styles.label}>Modelo Pedido (Pedido Venda)</Text>
              <SelectField
                value={modeloPedido || null}
                onChange={(v) => setModeloPedido(v == null ? "" : String(v))}
                options={modelosPedido.map((i) => ({ value: i.codigo, label: i.descricao }))}
                placeholder="Selecione…"
                allowClear
                compactWeb
                testID="area-atuacao-modelo-pedido"
                modalTitle="Modelo Pedido"
              />

              <Text style={styles.label}>Modelo O.S.</Text>
              <SelectField
                value={modeloOS || null}
                onChange={(v) => setModeloOS(v == null ? "" : String(v))}
                options={modelosOS.map((i) => ({ value: i.codigo, label: i.descricao }))}
                placeholder="Selecione…"
                allowClear
                compactWeb
                testID="area-atuacao-modelo-os"
                modalTitle="Modelo O.S."
              />

              <Text style={styles.label}>Intermediador de operações não presenciais</Text>
              <TextInput
                value={intermediador}
                onChangeText={(v) => setIntermediador(v.replace(/\D/g, ""))}
                placeholder="Código"
                placeholderTextColor={colors.muted}
                style={styles.input}
                keyboardType="number-pad"
                testID="area-atuacao-intermediador"
              />

              <Text style={styles.label}>Identificação do Intermediador</Text>
              <TextInput
                value={intermediadorId}
                onChangeText={setIntermediadorId}
                placeholder="CNPJ/identificação"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={60}
                testID="area-atuacao-intermediador-id"
              />

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="area-atuacao-salvar">
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
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: { width: "100%", maxWidth: 560, alignSelf: "center", gap: spacing.sm },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
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
    maxWidth: Platform.OS === "web" ? 560 : undefined,
    maxHeight: "85%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
