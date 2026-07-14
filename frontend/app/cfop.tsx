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
type Cfop = {
  codigo: string;
  descricao: string;
  descricao_nf: string;
  aplicacao: string;
  cod_contabil: number | null;
};
type CfopXml = { cfop_xml: string; cfop: string };

// Cadastro/Tabelas Auxiliares > Código Fiscal de Operações (tabela `cfops`).
// Legado: FrmManCFO. `cfop` é o código padronizado da legislação fiscal,
// digitado pelo usuário — upsert-by-codigo, travado depois de criado (mesmo
// padrão de Icms/Situação/Origem).
//
// A mesma tela do legado embute um segundo cadastro independente — "Vínculos
// de CFOP das NFe's importadas por XML" (tabela `cfop_xml`): um dicionário
// simples "CFOP do XML -> CFOP de entrada" usado na importação de NF-e, sem
// tela/formulário próprio (só adicionar/remover linhas). Reproduzido aqui como
// um modal próprio, aberto por um link no topo da lista principal — a lista
// de CFOPs costuma ter centenas de linhas, então embutir os vínculos direto
// no final do scroll (1ª versão desta tela) ficava de fato inacessível.
export default function CfopScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Código Fiscal de Operações está disponível apenas no web."
        testID="cfop-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<Cfop[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [codigosContabil, setCodigosContabil] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<string | null>(null);
  const [codigo, setCodigo] = useState("");
  const [descricao, setDescricao] = useState("");
  const [descricaoNf, setDescricaoNf] = useState("");
  const [aplicacao, setAplicacao] = useState("");
  const [codContabil, setCodContabil] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [vinculosOpen, setVinculosOpen] = useState(false);
  const [vinculos, setVinculos] = useState<CfopXml[]>([]);
  const [novoCfopXml, setNovoCfopXml] = useState("");
  const [novoCfopEntrada, setNovoCfopEntrada] = useState("");
  const [vinculando, setVinculando] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/cfop?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  const loadVinculos = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/tabelas/cfop-xml?${qs}`);
      const j = await r.json();
      setVinculos(j?.success ? j.items || [] : []);
    } catch { setVinculos([]); }
  }, []);

  const loadLookups = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const r = await fetch(`${base}/api/codigo-contabil?${qs}`);
      const j = await r.json();
      if (j?.success && Array.isArray(j.items)) setCodigosContabil(j.items);
    } catch { /* silencioso — lookup opcional */ }
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
      loadVinculos(cc);
      loadLookups(cc);
    })();
  }, [router, load, loadVinculos, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditCod(null);
    setCodigo(""); setDescricao(""); setDescricaoNf(""); setAplicacao(""); setCodContabil(null);
    setFormOpen(true);
  };

  const openEdit = (c: Cfop) => {
    setEditCod(c.codigo);
    setCodigo(c.codigo); setDescricao(c.descricao); setDescricaoNf(c.descricao_nf); setAplicacao(c.aplicacao);
    setCodContabil(c.cod_contabil ? String(c.cod_contabil) : null);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    if (!codigo.trim()) { showToast("Informe o código."); return; }
    if (!descricao.trim()) { showToast("Informe a descrição."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: codigo.trim(),
          descricao: descricao.trim(), descricao_nf: descricaoNf.trim(), aplicacao: aplicacao.trim(),
          cod_contabil: codContabil ? parseInt(codContabil, 10) : null,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "CFOP gravado."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (c: Cfop) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop/${encodeURIComponent(c.codigo)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const vincular = async () => {
    if (!conn) return;
    if (!novoCfopXml.trim() || !novoCfopEntrada.trim()) { showToast("Informe o CFOP no XML e o CFOP de entrada."); return; }
    setVinculando(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop-xml`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          cfop_xml: novoCfopXml.trim(), cfop: novoCfopEntrada.trim(),
        }),
      });
      const j = await r.json();
      if (j?.success) {
        showToast(j.message || "Vínculo gravado.");
        setNovoCfopXml(""); setNovoCfopEntrada("");
        loadVinculos(conn);
      } else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setVinculando(false); }
  };

  const removeVinculo = async (v: CfopXml) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop-xml/${encodeURIComponent(v.cfop_xml)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Removido." : "Falha."));
      if (j?.success) loadVinculos(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("CFOP.GRAVAR") || isMaster;
  const canDel = can("CFOP.EXCLUIR") || isMaster;
  const canVinculos = can("CFOP.VINCULOS_XML") || isMaster;

  const codigosContabilOpts = codigosContabil.map((i) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cfop-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Código Fiscal de Operações</Text>
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
            testID="cfop-search"
          />
          {canVinculos ? (
            <Pressable onPress={() => setVinculosOpen(true)} style={styles.linkBtn} testID="cfop-abrir-vinculos">
              <Ionicons name="git-merge-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.linkBtnText}>Vínculos de CFOP das NFe's importadas por XML</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </Pressable>
          ) : null}
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum CFOP cadastrado.</Text> : null}
          {items.map((c) => (
            <View key={c.codigo} style={styles.row} testID={`cfop-${c.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(c)}>
                <Text style={styles.rowTitle}>{c.codigo} · {c.descricao}</Text>
                {c.descricao_nf ? <Text style={styles.rowSub}>N.F.: {c.descricao_nf}</Text> : null}
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(c)} hitSlop={8} testID={`cfop-del-${c.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="cfop-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editCod ? `CFOP ${editCod}` : "Novo CFOP"}</Text>

              <Text style={styles.label}>Código *</Text>
              <TextInput
                value={codigo}
                onChangeText={(v) => setCodigo(v.replace(/[^0-9]/g, ""))}
                placeholder="Ex.: 1102, 5102"
                placeholderTextColor={colors.muted}
                style={[styles.input, editCod != null && styles.inputDisabled]}
                editable={editCod == null}
                keyboardType="number-pad"
                maxLength={4}
                testID="cfop-codigo"
              />

              <Text style={styles.label}>Código Contábil</Text>
              <SelectField
                value={codContabil}
                onChange={(v) => setCodContabil(v == null ? null : String(v))}
                options={codigosContabilOpts}
                placeholder="Selecione…"
                allowClear
                compactWeb
                testID="cfop-cod-contabil"
                modalTitle="Código Contábil"
              />

              <Text style={styles.label}>Descrição N.F.</Text>
              <TextInput
                value={descricaoNf}
                onChangeText={setDescricaoNf}
                placeholder="Descrição resumida para a nota fiscal"
                placeholderTextColor={colors.muted}
                style={styles.input}
                maxLength={20}
                testID="cfop-descricao-nf"
              />

              <Text style={styles.label}>Descrição</Text>
              <TextInput
                value={descricao}
                onChangeText={setDescricao}
                placeholder="Descrição completa do CFOP"
                placeholderTextColor={colors.muted}
                style={[styles.input, styles.textArea]}
                multiline
                numberOfLines={3}
                testID="cfop-descricao"
              />

              <Text style={styles.label}>Aplicação</Text>
              <TextInput
                value={aplicacao}
                onChangeText={setAplicacao}
                placeholder="Notas de aplicação/classificação do CFOP"
                placeholderTextColor={colors.muted}
                style={[styles.input, styles.textArea]}
                multiline
                numberOfLines={4}
                testID="cfop-aplicacao"
              />

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="cfop-salvar">
                {saving ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={vinculosOpen} transparent animationType="slide" onRequestClose={() => setVinculosOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setVinculosOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Vínculos de CFOP das NFe's importadas por XML</Text>
            <ScrollView showsVerticalScrollIndicator={false}>
              {vinculos.length === 0 ? <Text style={styles.empty}>Nenhum vínculo cadastrado.</Text> : null}
              {vinculos.map((v) => (
                <View key={v.cfop_xml} style={styles.vinculoRow} testID={`cfop-xml-${v.cfop_xml}`}>
                  <Text style={styles.vinculoText}>XML {v.cfop_xml} → Entrada {v.cfop}</Text>
                  {canDel ? (
                    <Pressable onPress={() => removeVinculo(v)} hitSlop={8} testID={`cfop-xml-del-${v.cfop_xml}`}>
                      <Ionicons name="close-circle-outline" size={20} color={colors.error} />
                    </Pressable>
                  ) : null}
                </View>
              ))}

              {canSave ? (
                <>
                  <View style={styles.rowFields}>
                    <View style={styles.colHalf}>
                      <Text style={styles.label}>CFOP no XML</Text>
                      <TextInput
                        value={novoCfopXml}
                        onChangeText={(v) => setNovoCfopXml(v.replace(/[^0-9]/g, ""))}
                        keyboardType="number-pad"
                        maxLength={4}
                        style={styles.input}
                        testID="cfop-xml-novo"
                      />
                    </View>
                    <View style={styles.colHalf}>
                      <Text style={styles.label}>CFOP de Entrada</Text>
                      <TextInput
                        value={novoCfopEntrada}
                        onChangeText={(v) => setNovoCfopEntrada(v.replace(/[^0-9]/g, ""))}
                        keyboardType="number-pad"
                        maxLength={4}
                        style={styles.input}
                        testID="cfop-xml-entrada"
                      />
                    </View>
                  </View>
                  <Pressable onPress={vincular} disabled={vinculando} style={[styles.secondaryBtn, vinculando && { opacity: 0.6 }]} testID="cfop-xml-vincular">
                    {vinculando ? <ActivityIndicator color={colors.brandPrimary} /> : <Text style={styles.secondaryBtnText}>Vincular</Text>}
                  </Pressable>
                </>
              ) : null}
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
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: spacing.sm },
  linkBtn: { flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" },
  linkBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 12, marginBottom: 12 },
  vinculoRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", alignSelf: "stretch", width: "100%", backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, marginBottom: spacing.xs },
  vinculoText: { fontSize: 13, color: colors.onSurface },
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
    maxHeight: "88%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  textArea: { minHeight: 80, textAlignVertical: "top" },
  rowFields: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  colHalf: { flex: 1 },
  secondaryBtn: { borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 10, alignItems: "center", marginTop: spacing.sm },
  secondaryBtnText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
