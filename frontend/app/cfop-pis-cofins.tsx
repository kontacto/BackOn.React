import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View,
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
type CfopPisCofins = {
  cod_auto: number;
  cfop: string;
  grupo_pis_cofins: number | null;
  grupo_descricao: string | null;
  tributacao_qtd: boolean;
  tributacao_pis: number | null;
  perc_valor_pis: number;
  tributacao_cofins: number | null;
  perc_valor_cofins: number;
  acatar_nfe: boolean;
};

const pad = (v: number | null | undefined, len: number) => (v == null ? null : String(v).padStart(len, "0"));

const toFloat = (s: string): number => {
  const v = parseFloat((s || "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};

// Cadastro/Tabelas Auxiliares > Cfop x Pis/Cofins (tabela `cfop_pis_cofins`).
// Legado: FrmCfoPis ("CFOP´s x Pis e Cofins"). Chave natural é o par
// (cfop, grupo_pis_cofins) — sem unique constraint no banco, mas o legado
// sempre faz upsert por esse par ao gravar (mesmo comportamento replicado
// no backend).
//
// As 3 lupas do formulário legado (Grupo / CST Pis / CST Cofins) só abriam
// telas somente-leitura para escolher um valor já cadastrado — substituídas
// aqui pelo componente padrão deste projeto para esse caso (`SelectField`,
// dropdown pesquisável), sem necessidade de telas de busca separadas.
export default function CfopPisCofinsScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Cfop x Pis/Cofins está disponível apenas no web."
        testID="cfop-pis-cofins-web-only"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<CfopPisCofins[]>([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [grupos, setGrupos] = useState<LookupItem[]>([]);
  const [cstPis, setCstPis] = useState<LookupItem[]>([]);
  const [cstCofins, setCstCofins] = useState<LookupItem[]>([]);

  const [formOpen, setFormOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  const [cfop, setCfop] = useState("");
  const [grupo, setGrupo] = useState<string | null>(null);
  const [tributacaoQtd, setTributacaoQtd] = useState(false);
  const [cstPisSel, setCstPisSel] = useState<string | null>(null);
  const [aliquotaPis, setAliquotaPis] = useState("0");
  const [cstCofinsSel, setCstCofinsSel] = useState<string | null>(null);
  const [aliquotaCofins, setAliquotaCofins] = useState("0");
  const [acatarNfe, setAcatarNfe] = useState(true);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn, q: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}`;
      const r = await fetch(`${base}/api/tabelas/cfop-pis-cofins?${qs}`);
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
      fetchLookup("tabelas/grupo-pis-cofins", setGrupos),
      fetchLookup("cst-pis", setCstPis),
      fetchLookup("cst-cofins", setCstCofins),
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
      load(cc, "");
      loadLookups(cc);
    })();
  }, [router, load, loadLookups]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const openNew = () => {
    setEditId(null);
    setCfop(""); setGrupo(null); setTributacaoQtd(false);
    setCstPisSel(null); setAliquotaPis("0"); setCstCofinsSel(null); setAliquotaCofins("0");
    setAcatarNfe(true);
    setFormOpen(true);
  };

  const openEdit = (c: CfopPisCofins) => {
    setEditId(c.cod_auto);
    setCfop(c.cfop); setGrupo(pad(c.grupo_pis_cofins, 3)); setTributacaoQtd(c.tributacao_qtd);
    setCstPisSel(pad(c.tributacao_pis, 2)); setAliquotaPis(String(c.perc_valor_pis ?? 0));
    setCstCofinsSel(pad(c.tributacao_cofins, 2)); setAliquotaCofins(String(c.perc_valor_cofins ?? 0));
    setAcatarNfe(c.acatar_nfe);
    setFormOpen(true);
  };

  const save = async () => {
    if (!conn) return;
    if (!cfop.trim()) { showToast("Informe o CFOP."); return; }
    if (!grupo) { showToast("Selecione o grupo de Pis/Cofins."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop-pis-cofins`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, cod_auto: editId,
          cfop: cfop.trim().toUpperCase(), grupo_pis_cofins: parseInt(grupo, 10),
          tributacao_qtd: tributacaoQtd,
          tributacao_pis: cstPisSel ? parseInt(cstPisSel, 10) : null, perc_valor_pis: toFloat(aliquotaPis),
          tributacao_cofins: cstCofinsSel ? parseInt(cstCofinsSel, 10) : null, perc_valor_cofins: toFloat(aliquotaCofins),
          acatar_nfe: acatarNfe,
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Registro gravado."); setFormOpen(false); load(conn, search); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (c: CfopPisCofins) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/tabelas/cfop-pis-cofins/${c.cod_auto}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluído." : "Falha."));
      if (j?.success) load(conn, search);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const canSave = can("CFOP_PISCOF.GRAVAR") || isMaster;
  const canDel = can("CFOP_PISCOF.EXCLUIR") || isMaster;

  const gruposOpts = grupos.map((g) => ({ value: g.codigo, label: `${g.codigo} - ${g.descricao}` }));
  const cstPisOpts = cstPis.map((c) => ({ value: c.codigo, label: `${c.codigo} - ${c.descricao}` }));
  const cstCofinsOpts = cstCofins.map((c) => ({ value: c.codigo, label: `${c.codigo} - ${c.descricao}` }));

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="cfop-pis-cofins-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Cfop x Pis/Cofins</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por CFOP…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="cfop-pis-cofins-search"
          />
        </View>

        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhum registro cadastrado.</Text> : null}
          {items.map((c) => (
            <View key={c.cod_auto} style={styles.row} testID={`cfop-pis-cofins-${c.cod_auto}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(c)}>
                <Text style={styles.rowTitle}>
                  {c.cfop} · Grupo {c.grupo_descricao ? `${pad(c.grupo_pis_cofins, 3)} - ${c.grupo_descricao}` : pad(c.grupo_pis_cofins, 3)}
                </Text>
                <Text style={styles.rowSub}>
                  PIS {pad(c.tributacao_pis, 2)}: {c.perc_valor_pis.toFixed(2)}% · COFINS {pad(c.tributacao_cofins, 2)}: {c.perc_valor_cofins.toFixed(2)}%
                </Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(c)} hitSlop={8} testID={`cfop-pis-cofins-del-${c.cod_auto}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="cfop-pis-cofins-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView showsVerticalScrollIndicator={false}>
              <Text style={styles.modalTitle}>{editId ? "Editar tributação" : "Nova tributação"}</Text>

              <Text style={styles.label}>CFOP *</Text>
              <TextInput
                value={cfop}
                onChangeText={(v) => setCfop(v.replace(/[^0-9]/g, ""))}
                placeholder="Ex.: 1102, 5102"
                placeholderTextColor={colors.muted}
                style={styles.input}
                keyboardType="number-pad"
                maxLength={4}
                testID="cpc-cfop"
              />

              <Text style={styles.label}>Grupo de Pis/Cofins *</Text>
              <SelectField
                value={grupo}
                onChange={(v) => setGrupo(v == null ? null : String(v))}
                options={gruposOpts}
                placeholder="Selecione…"
                compactWeb
                testID="cpc-grupo"
                modalTitle="Grupo de Pis/Cofins"
              />

              <View style={styles.switchRow}>
                <Text style={styles.label}>Tributado pela quantidade</Text>
                <Switch value={tributacaoQtd} onValueChange={setTributacaoQtd} testID="cpc-trib-qtd-switch" />
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>CST Pis</Text>
                  <SelectField
                    value={cstPisSel}
                    onChange={(v) => setCstPisSel(v == null ? null : String(v))}
                    options={cstPisOpts}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cpc-cst-pis"
                    modalTitle="CST Pis"
                  />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Alíquota Pis %</Text>
                  <TextInput value={aliquotaPis} onChangeText={setAliquotaPis} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="cpc-aliquota-pis" />
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>CST Cofins</Text>
                  <SelectField
                    value={cstCofinsSel}
                    onChange={(v) => setCstCofinsSel(v == null ? null : String(v))}
                    options={cstCofinsOpts}
                    placeholder="Selecione…"
                    allowClear
                    compactWeb
                    testID="cpc-cst-cofins"
                    modalTitle="CST Cofins"
                  />
                </View>
                <View style={styles.colHalf}>
                  <Text style={styles.label}>Alíquota Cofins %</Text>
                  <TextInput value={aliquotaCofins} onChangeText={setAliquotaCofins} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="cpc-aliquota-cofins" />
                </View>
              </View>

              <View style={styles.switchRow}>
                <Text style={styles.label}>Acatar Base, Alíquota e valor da NFe</Text>
                <Switch value={acatarNfe} onValueChange={setAcatarNfe} testID="cpc-acatar-nfe-switch" />
              </View>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="cpc-salvar">
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
  webShell: { width: "100%", maxWidth: 640, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: 0, gap: 4 },
  scroll: { padding: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
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
    maxHeight: "88%",
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm },
  colHalf: { flex: 1 },
  switchRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
