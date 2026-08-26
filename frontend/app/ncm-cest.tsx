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
import { apiBase, ConnLike, connQS, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = ConnLike;
type NcmItem = { ncm: string; descricao: string };
type CestItem = { ncm: string; cest: string; descricao: string };

// Cadastro/Consulta de NCM e CEST — Tabelas Auxiliares (fiscal). Legado:
// `Geral\FrmCesNCM.frm`. Diferente das outras tabelas auxiliares, `ncm`
// (10.343 linhas) e `ncm_cest` (1.285 linhas) já vêm populadas com dado
// oficial (Mercosul + Convênio ICMS 142/2018) — o uso real predominante é
// BUSCA, nunca "listar tudo". Um CEST pode se repetir em vários NCM (a
// chave real é o par ncm+cest, não o NCM sozinho) e pode existir sem NCM
// vinculado ainda (referência genérica).
export default function NcmCestScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="NCM/CEST está disponível apenas no web."
        testID="ncm-cest-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  // Busca por NCM
  const [searchNcm, setSearchNcm] = useState("");
  const [ncmItems, setNcmItems] = useState<NcmItem[]>([]);
  const [loadingNcm, setLoadingNcm] = useState(false);

  // Busca por CEST
  const [searchCest, setSearchCest] = useState("");
  const [cestItems, setCestItems] = useState<CestItem[]>([]);
  const [loadingCest, setLoadingCest] = useState(false);

  // Detalhe do NCM selecionado
  const [selNcm, setSelNcm] = useState<string | null>(null);
  const [selDescricao, setSelDescricao] = useState("");
  const [selCests, setSelCests] = useState<CestItem[]>([]);
  const [loadingDetalhe, setLoadingDetalhe] = useState(false);
  const [savingNcm, setSavingNcm] = useState(false);

  // Modal Novo NCM
  const [novoNcmOpen, setNovoNcmOpen] = useState(false);
  const [novoNcmCodigo, setNovoNcmCodigo] = useState("");
  const [novoNcmDescricao, setNovoNcmDescricao] = useState("");

  // Modal vínculo CEST (usado tanto a partir do detalhe do NCM quanto solto)
  const [cestFormOpen, setCestFormOpen] = useState(false);
  const [cestFormNcm, setCestFormNcm] = useState("");
  const [cestFormNcmLocked, setCestFormNcmLocked] = useState(false);
  const [cestFormCodigo, setCestFormCodigo] = useState("");
  const [cestFormDescricao, setCestFormDescricao] = useState("");
  const [savingCest, setSavingCest] = useState(false);

  const canSave = can("NCM_CEST.GRAVAR") || isMaster;
  const canDel = can("NCM_CEST.EXCLUIR") || isMaster;

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn({ servidor: c.servidor, banco: c.banco, api: c.api });
    })();
  }, [router]);

  const loadNcm = useCallback(async (c: Conn, q: string) => {
    if (!q.trim()) { setNcmItems([]); return; }
    setLoadingNcm(true);
    try {
      const r = await fetch(`${apiBase(c)}/api/ncm?${connQS(c, { search: q })}`);
      const j = await r.json();
      setNcmItems(j?.success ? j.items || [] : []);
    } catch { setNcmItems([]); } finally { setLoadingNcm(false); }
  }, []);

  const loadCest = useCallback(async (c: Conn, q: string) => {
    if (!q.trim()) { setCestItems([]); return; }
    setLoadingCest(true);
    try {
      const r = await fetch(`${apiBase(c)}/api/ncm-cest/buscar?${connQS(c, { search: q })}`);
      const j = await r.json();
      setCestItems(j?.success ? j.items || [] : []);
    } catch { setCestItems([]); } finally { setLoadingCest(false); }
  }, []);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => loadNcm(conn, searchNcm), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchNcm, conn]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => loadCest(conn, searchCest), 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchCest, conn]);

  const abrirDetalheNcm = async (ncm: string) => {
    if (!conn) return;
    setSelNcm(ncm);
    setLoadingDetalhe(true);
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm/${encodeURIComponent(ncm)}?${connQS(conn)}`);
      const j = await r.json();
      if (j?.success) {
        setSelDescricao(j.item?.descricao || "");
        setSelCests(j.cests || []);
      } else {
        showToast(friendlyApiError(j, "Falha ao consultar NCM."));
        setSelNcm(null);
      }
    } catch (e) {
      showToast(friendlyCatchError(e, "Falha ao consultar NCM."));
      setSelNcm(null);
    } finally {
      setLoadingDetalhe(false);
    }
  };

  const salvarDescricaoNcm = async () => {
    if (!conn || !selNcm) return;
    setSavingNcm(true);
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, ncm: selNcm, descricao: selDescricao.trim() }),
      });
      const j = await r.json();
      if (j?.success) { showToast("NCM gravado."); loadNcm(conn, searchNcm); }
      else showToast(friendlyApiError(j, "Falha ao gravar NCM."));
    } catch (e) { showToast(friendlyCatchError(e, "Falha ao gravar NCM.")); } finally { setSavingNcm(false); }
  };

  const criarNcm = async () => {
    if (!conn) return;
    if (!novoNcmCodigo.trim()) { showToast("Informe o código NCM."); return; }
    if (!novoNcmDescricao.trim()) { showToast("Informe a descrição."); return; }
    setSavingNcm(true);
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, ncm: novoNcmCodigo.trim(), descricao: novoNcmDescricao.trim() }),
      });
      const j = await r.json();
      if (j?.success) {
        showToast("NCM cadastrado.");
        setNovoNcmOpen(false);
        setSearchNcm(novoNcmCodigo.trim());
        loadNcm(conn, novoNcmCodigo.trim());
      } else showToast(friendlyApiError(j, "Falha ao cadastrar NCM."));
    } catch (e) { showToast(friendlyCatchError(e, "Falha ao cadastrar NCM.")); } finally { setSavingNcm(false); }
  };

  const excluirNcm = async (ncm: string) => {
    if (!conn) return;
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm/${encodeURIComponent(ncm)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.success ? "NCM excluído." : friendlyApiError(j, "Falha ao excluir NCM."));
      if (j?.success) {
        loadNcm(conn, searchNcm);
        if (selNcm === ncm) setSelNcm(null);
      }
    } catch (e) { showToast(friendlyCatchError(e, "Falha ao excluir NCM.")); }
  };

  const abrirNovoCest = (ncmPreenchido?: string) => {
    setCestFormNcm(ncmPreenchido || "");
    setCestFormNcmLocked(!!ncmPreenchido);
    setCestFormCodigo("");
    setCestFormDescricao("");
    setCestFormOpen(true);
  };

  const salvarCest = async () => {
    if (!conn) return;
    if (!cestFormCodigo.trim()) { showToast("Informe o código CEST."); return; }
    setSavingCest(true);
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm-cest`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          ncm: cestFormNcm.trim(), cest: cestFormCodigo.trim(), descricao: cestFormDescricao.trim(),
        }),
      });
      const j = await r.json();
      if (j?.success) {
        showToast("CEST vinculado.");
        setCestFormOpen(false);
        if (selNcm) abrirDetalheNcm(selNcm);
        if (searchCest.trim()) loadCest(conn, searchCest);
      } else showToast(friendlyApiError(j, "Falha ao vincular CEST."));
    } catch (e) { showToast(friendlyCatchError(e, "Falha ao vincular CEST.")); } finally { setSavingCest(false); }
  };

  const excluirCest = async (item: CestItem) => {
    if (!conn) return;
    try {
      const r = await fetch(`${apiBase(conn)}/api/ncm-cest/${encodeURIComponent(item.cest)}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, ncm: item.ncm }),
      });
      const j = await r.json();
      showToast(j?.success ? "Vínculo excluído." : friendlyApiError(j, "Falha ao excluir vínculo."));
      if (j?.success) {
        if (selNcm) abrirDetalheNcm(selNcm);
        if (searchCest.trim()) loadCest(conn, searchCest);
      }
    } catch (e) { showToast(friendlyCatchError(e, "Falha ao excluir vínculo.")); }
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="ncm-cest-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>NCM/CEST</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <Text style={styles.hint}>
            Consulta as tabelas oficiais de NCM (Nomenclatura Comum do Mercosul) e CEST
            (Código Especificador da Substituição Tributária). Um mesmo CEST pode se aplicar
            a vários NCM — a busca abaixo não substitui pesquisa em fonte oficial, é só o
            cadastro já usado pelo sistema.
          </Text>

          <View style={styles.cols}>
            {/* Coluna esquerda: busca NCM + resultado */}
            <View style={styles.col}>
              <View style={styles.panel}>
                <View style={styles.panelHeader}>
                  <Text style={styles.panelTitle}>Buscar NCM</Text>
                  {canSave ? (
                    <Pressable onPress={() => { setNovoNcmCodigo(""); setNovoNcmDescricao(""); setNovoNcmOpen(true); }} testID="ncm-cest-novo-ncm">
                      <Ionicons name="add-circle-outline" size={22} color={colors.brandPrimary} />
                    </Pressable>
                  ) : null}
                </View>
                <TextInput
                  value={searchNcm}
                  onChangeText={setSearchNcm}
                  placeholder="Código ou descrição do NCM…"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="ncm-cest-search-ncm"
                />
                {loadingNcm ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
                {!loadingNcm && searchNcm.trim() && ncmItems.length === 0 ? (
                  <Text style={styles.empty}>Nenhum NCM encontrado.</Text>
                ) : null}
                <View style={{ gap: spacing.xs, marginTop: spacing.sm }}>
                  {ncmItems.map((it) => (
                    <Pressable
                      key={it.ncm}
                      onPress={() => abrirDetalheNcm(it.ncm)}
                      style={[styles.row, selNcm === it.ncm && styles.rowSel]}
                      testID={`ncm-cest-ncm-${it.ncm}`}
                    >
                      <Text style={styles.rowCode}>{it.ncm}</Text>
                      <Text style={styles.rowDesc} numberOfLines={2}>{it.descricao}</Text>
                    </Pressable>
                  ))}
                </View>
              </View>

              <View style={styles.panel}>
                <Text style={styles.panelTitle}>Buscar CEST</Text>
                <TextInput
                  value={searchCest}
                  onChangeText={setSearchCest}
                  placeholder="Código ou descrição do CEST…"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="ncm-cest-search-cest"
                />
                {loadingCest ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
                {!loadingCest && searchCest.trim() && cestItems.length === 0 ? (
                  <Text style={styles.empty}>Nenhum CEST encontrado.</Text>
                ) : null}
                <View style={{ gap: spacing.xs, marginTop: spacing.sm }}>
                  {cestItems.map((it) => (
                    <View key={`${it.cest}-${it.ncm}`} style={styles.row} testID={`ncm-cest-cest-${it.cest}-${it.ncm || "sem-ncm"}`}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.rowCode}>{it.cest}{it.ncm ? ` · NCM ${it.ncm}` : " · sem NCM vinculado"}</Text>
                        {it.descricao ? <Text style={styles.rowDesc} numberOfLines={2}>{it.descricao}</Text> : null}
                      </View>
                      {it.ncm ? (
                        <Pressable onPress={() => { setSearchNcm(it.ncm); abrirDetalheNcm(it.ncm); }} hitSlop={8}>
                          <Ionicons name="open-outline" size={18} color={colors.brandPrimary} />
                        </Pressable>
                      ) : null}
                    </View>
                  ))}
                </View>
              </View>
            </View>

            {/* Coluna direita: detalhe do NCM selecionado */}
            <View style={styles.col}>
              <View style={styles.panel}>
                <Text style={styles.panelTitle}>Detalhe do NCM</Text>
                {!selNcm ? (
                  <Text style={styles.empty}>Selecione um NCM na busca ao lado.</Text>
                ) : loadingDetalhe ? (
                  <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} />
                ) : (
                  <>
                    <Text style={styles.label}>Código NCM</Text>
                    <Text style={styles.selCodigo}>{selNcm}</Text>
                    <Text style={styles.label}>Descrição</Text>
                    <TextInput
                      value={selDescricao}
                      onChangeText={setSelDescricao}
                      style={[styles.input, { minHeight: 60 }]}
                      multiline
                      editable={canSave}
                      testID="ncm-cest-descricao-ncm"
                    />
                    <View style={styles.actionsRow}>
                      {canSave ? (
                        <Pressable onPress={salvarDescricaoNcm} disabled={savingNcm} style={[styles.primaryBtn, savingNcm && { opacity: 0.6 }]} testID="ncm-cest-salvar-ncm">
                          {savingNcm ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                        </Pressable>
                      ) : null}
                      {canDel ? (
                        <Pressable onPress={() => excluirNcm(selNcm)} style={styles.secondaryBtn} testID="ncm-cest-excluir-ncm">
                          <Text style={styles.secondaryBtnText}>Excluir NCM</Text>
                        </Pressable>
                      ) : null}
                    </View>

                    <View style={styles.divider} />
                    <View style={styles.panelHeader}>
                      <Text style={styles.panelTitle}>CEST vinculados</Text>
                      {canSave ? (
                        <Pressable onPress={() => abrirNovoCest(selNcm)} testID="ncm-cest-novo-cest">
                          <Ionicons name="add-circle-outline" size={22} color={colors.brandPrimary} />
                        </Pressable>
                      ) : null}
                    </View>
                    {selCests.length === 0 ? <Text style={styles.empty}>Nenhum CEST vinculado a este NCM.</Text> : null}
                    <View style={{ gap: spacing.xs }}>
                      {selCests.map((c) => (
                        <View key={c.cest} style={styles.row} testID={`ncm-cest-vinculo-${c.cest}`}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.rowCode}>{c.cest}</Text>
                            {c.descricao ? <Text style={styles.rowDesc} numberOfLines={2}>{c.descricao}</Text> : null}
                          </View>
                          {canDel ? (
                            <Pressable onPress={() => excluirCest(c)} hitSlop={8} testID={`ncm-cest-del-vinculo-${c.cest}`}>
                              <Ionicons name="trash-outline" size={18} color={colors.error} />
                            </Pressable>
                          ) : null}
                        </View>
                      ))}
                    </View>
                  </>
                )}
              </View>
            </View>
          </View>
        </View>
      </ScrollView>

      {/* Modal Novo NCM */}
      <Modal visible={novoNcmOpen} transparent animationType="fade" onRequestClose={() => setNovoNcmOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setNovoNcmOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Novo NCM</Text>
            <Text style={styles.label}>Código NCM *</Text>
            <TextInput
              value={novoNcmCodigo}
              onChangeText={setNovoNcmCodigo}
              placeholder="Ex.: 84713012"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="ncm-cest-novo-ncm-codigo"
            />
            <Text style={styles.label}>Descrição *</Text>
            <TextInput
              value={novoNcmDescricao}
              onChangeText={setNovoNcmDescricao}
              style={[styles.input, { minHeight: 60 }]}
              multiline
              testID="ncm-cest-novo-ncm-descricao"
            />
            <Pressable onPress={criarNcm} disabled={savingNcm} style={[styles.primaryBtn, savingNcm && { opacity: 0.6 }, { marginTop: spacing.md }]} testID="ncm-cest-novo-ncm-gravar">
              {savingNcm ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal vincular CEST */}
      <Modal visible={cestFormOpen} transparent animationType="fade" onRequestClose={() => setCestFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCestFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.modalTitle}>Vincular CEST</Text>
            <Text style={styles.label}>NCM {cestFormNcmLocked ? "" : "(opcional)"}</Text>
            <TextInput
              value={cestFormNcm}
              onChangeText={setCestFormNcm}
              placeholder="Deixe em branco para CEST sem NCM específico"
              placeholderTextColor={colors.muted}
              style={[styles.input, cestFormNcmLocked && styles.inputDisabled]}
              editable={!cestFormNcmLocked}
              testID="ncm-cest-form-ncm"
            />
            <Text style={styles.label}>Código CEST *</Text>
            <TextInput
              value={cestFormCodigo}
              onChangeText={setCestFormCodigo}
              placeholder="Ex.: 2806100"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="ncm-cest-form-codigo"
            />
            <Text style={styles.label}>Descrição</Text>
            <TextInput
              value={cestFormDescricao}
              onChangeText={setCestFormDescricao}
              style={[styles.input, { minHeight: 60 }]}
              multiline
              testID="ncm-cest-form-descricao"
            />
            <Pressable onPress={salvarCest} disabled={savingCest} style={[styles.primaryBtn, savingCest && { opacity: 0.6 }, { marginTop: spacing.md }]} testID="ncm-cest-form-gravar">
              {savingCest ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
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
  scroll: { padding: spacing.lg, paddingBottom: 60 },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: { ...WEB_CONTENT_SHELL, maxWidth: 1100 },
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.md, lineHeight: 17 },
  cols: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  col: { flex: 1, minWidth: 340, gap: spacing.md },
  panel: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md },
  panelHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  panelTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 11, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 13, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  empty: { textAlign: "center", color: colors.muted, marginTop: 12, fontSize: 12 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, padding: spacing.sm },
  rowSel: { borderColor: colors.brandPrimary },
  rowCode: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  rowDesc: { fontSize: 11, color: colors.muted, marginTop: 2 },
  selCodigo: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  actionsRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 10, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center" },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  secondaryBtn: { borderRadius: radius.pill, paddingVertical: 10, paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.error },
  secondaryBtnText: { color: colors.error, fontWeight: "700", fontSize: 13 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", paddingHorizontal: spacing.xl, alignItems: "center" },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1, borderColor: colors.border, width: "100%", maxWidth: 420, padding: spacing.md },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill, maxWidth: "90%" },
  toastText: { color: colors.surface, fontSize: 13 },
});
