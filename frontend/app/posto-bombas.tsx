// Posto de Combustível > Bombas — migração de `frmcadbom.frm` ("Cadastro
// de Bombas", pasta VB6 Posto). Ver backend/services/bomba_service.py
// pro achado sobre o botão "Excluir" do legado, que existe visualmente
// mas não tem nenhum código associado (dead button) — Excluir foi
// implementado aqui como melhoria, com guards de integridade.
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type Combustivel = { codigo: number; descricao: string };
type TanqueOpt = { tanque: number; combustivel_descricao: string };
type BombaItem = { codigo: number; ilha: number | null; ponto: number | null; posicao: number | null; tanque: number | null; combustivel: number | null; combustivel_descricao: string };

export default function PostoBombasScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Bombas está disponível apenas no web." testID="posto-bombas-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-bombas-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<BombaItem[]>([]);
  const [combustiveis, setCombustiveis] = useState<Combustivel[]>([]);
  const [tanques, setTanques] = useState<TanqueOpt[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [formOpen, setFormOpen] = useState(false);
  const [editCod, setEditCod] = useState<number | null>(null);
  const [codigo, setCodigo] = useState("");
  const [ilha, setIlha] = useState("");
  const [ponto, setPonto] = useState("");
  const [posicao, setPosicao] = useState("");
  const [tanque, setTanque] = useState<number | null>(null);
  const [combustivel, setCombustivel] = useState<number | null>(null);
  const [contadorFinal, setContadorFinal] = useState("");
  const [dataUltMov, setDataUltMov] = useState("");
  const [serie, setSerie] = useState("");
  const [fabricante, setFabricante] = useState("");
  const [modelo, setModelo] = useState("");
  const [tipoMedicao, setTipoMedicao] = useState("");
  const [numeroLacre, setNumeroLacre] = useState("");
  const [dtLacre, setDtLacre] = useState("");
  const [saving, setSaving] = useState(false);

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const load = useCallback(async (c: Conn) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const [rb, rc, rt] = await Promise.all([
        fetch(`${base}/api/posto/bombas?${qs}`),
        fetch(`${base}/api/posto/combustiveis?${qs}`),
        fetch(`${base}/api/posto/tanques?${qs}`),
      ]);
      const jb = await rb.json();
      const jc = await rc.json();
      const jt = await rt.json();
      setItems(jb?.success ? jb.items || [] : []);
      setCombustiveis(jc?.success ? jc.items || [] : []);
      setTanques(jt?.success ? jt.items || [] : []);
      if (!jb?.success && jb?.message) showToast(jb.message);
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
      load(cc);
    })();
  }, [router, load]);

  const openNew = () => {
    setEditCod(null); setCodigo(""); setIlha(""); setPonto(""); setPosicao(""); setTanque(null); setCombustivel(null);
    setContadorFinal(""); setDataUltMov(""); setSerie(""); setFabricante(""); setModelo(""); setTipoMedicao("");
    setNumeroLacre(""); setDtLacre("");
    setFormOpen(true);
  };

  const openEdit = async (b: BombaItem) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/posto/bombas/${b.codigo}?${qs}`);
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao carregar."); return; }
      const it = j.item;
      setEditCod(it.codigo); setCodigo(String(it.codigo));
      setIlha(String(it.ilha ?? "")); setPonto(String(it.ponto ?? "")); setPosicao(String(it.posicao ?? ""));
      setTanque(it.tanque); setCombustivel(it.combustivel);
      setContadorFinal(it.contador_final ? String(it.contador_final) : "");
      setDataUltMov(it.data_ult_mov || "");
      setSerie(it.serie || ""); setFabricante(it.fabricante || ""); setModelo(it.modelo || "");
      setTipoMedicao(it.tipo_medicao != null ? String(it.tipo_medicao) : "");
      setNumeroLacre(it.numero_lacre || ""); setDtLacre(it.dt_lacre || "");
      setFormOpen(true);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const save = async () => {
    if (!conn) return;
    const cod = parseInt(codigo, 10);
    if (!codigo.trim() || isNaN(cod) || cod < 0 || cod > 255) { showToast("Código deve estar entre 0 e 255."); return; }
    const il = parseInt(ilha, 10);
    if (!ilha.trim() || isNaN(il)) { showToast("Informe a ilha."); return; }
    const pt = parseInt(ponto, 10);
    if (!ponto.trim() || isNaN(pt)) { showToast("Informe o ponto."); return; }
    const ps = parseInt(posicao, 10);
    if (!posicao.trim() || isNaN(ps) || ps < 1 || ps > 3) { showToast("Posição deve estar entre 1 e 3."); return; }
    if (tanque == null) { showToast("Selecione o tanque."); return; }
    if (combustivel == null) { showToast("Selecione o combustível."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/bombas`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx, codigo: cod,
          dados: {
            ilha: il, ponto: pt, posicao: ps, tanque, combustivel,
            contador_final: contadorFinal ? parseFloat(contadorFinal.replace(",", ".")) : 0,
            data_ult_mov: dataUltMov || null,
            serie: serie.trim() || null, fabricante: fabricante.trim() || null, modelo: modelo.trim() || null,
            tipo_medicao: tipoMedicao.trim() ? parseInt(tipoMedicao, 10) : null,
            numero_lacre: numeroLacre.trim() || null, dt_lacre: dtLacre || null,
          },
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Bomba gravada."); setFormOpen(false); load(conn); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const remove = async (b: BombaItem) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/bombas/${b.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx }),
      });
      const j = await r.json();
      showToast(j?.message || (j?.success ? "Excluída." : "Falha."));
      if (j?.success) load(conn);
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const combustivelOptions: SelectOption[] = combustiveis.map((c) => ({ value: c.codigo, label: `${c.codigo} · ${c.descricao}` }));
  const tanqueOptions: SelectOption[] = tanques.map((t) => ({ value: t.tanque, label: `Tanque ${t.tanque} (${t.combustivel_descricao})` }));
  const canSave = can("POSTO_BOMBA.GRAVAR") || isMaster;
  const canDel = can("POSTO_BOMBA.EXCLUIR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-bombas-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Bombas</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          {!loading && items.length === 0 ? <Text style={styles.empty}>Nenhuma bomba cadastrada.</Text> : null}
          {items.map((b) => (
            <View key={b.codigo} style={styles.row} testID={`posto-bombas-${b.codigo}`}>
              <Pressable style={{ flex: 1 }} onPress={() => canSave && openEdit(b)}>
                <Text style={styles.rowTitle}>Bomba {b.codigo} · Ilha {b.ilha}</Text>
                <Text style={styles.rowSub}>Ponto {b.ponto}/{b.posicao} · {b.combustivel_descricao || `Combustível #${b.combustivel}`}</Text>
              </Pressable>
              {canDel ? (
                <Pressable onPress={() => remove(b)} hitSlop={8} testID={`posto-bombas-del-${b.codigo}`}>
                  <Ionicons name="trash-outline" size={20} color={colors.error} />
                </Pressable>
              ) : null}
            </View>
          ))}
        </ScrollView>
      </View>

      {canSave ? (
        <Pressable onPress={openNew} style={styles.fab} testID="posto-bombas-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}

      <Modal visible={formOpen} transparent animationType="slide" onRequestClose={() => setFormOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setFormOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <ScrollView>
              <Text style={styles.modalTitle}>{editCod != null ? `Bomba ${editCod}` : "Nova Bomba"}</Text>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Código *</Text>
                  <TextInput value={codigo} onChangeText={(v) => setCodigo(v.replace(/[^0-9]/g, "").slice(0, 3))} placeholder="0-255" placeholderTextColor={colors.muted} style={[styles.input, editCod != null && styles.inputDisabled]} editable={editCod == null} keyboardType="number-pad" testID="posto-bombas-codigo" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Ilha *</Text>
                  <TextInput value={ilha} onChangeText={(v) => setIlha(v.replace(/[^0-9]/g, "").slice(0, 3))} placeholder="0-255" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-bombas-ilha" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Ponto *</Text>
                  <TextInput value={ponto} onChangeText={(v) => setPonto(v.replace(/[^0-9]/g, "").slice(0, 3))} placeholder="0-255" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-bombas-ponto" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Posição *</Text>
                  <TextInput value={posicao} onChangeText={(v) => setPosicao(v.replace(/[^0-9]/g, "").slice(0, 1))} placeholder="1-3" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-bombas-posicao" />
                </View>
              </View>

              <Text style={styles.label}>Tanque *</Text>
              <SelectField value={tanque} onChange={(v) => setTanque(v == null ? null : Number(v))} options={tanqueOptions} placeholder="Selecione…" compactWeb searchable testID="posto-bombas-tanque" />
              <Text style={styles.label}>Combustível *</Text>
              <SelectField value={combustivel} onChange={(v) => setCombustivel(v == null ? null : Number(v))} options={combustivelOptions} placeholder="Selecione…" compactWeb searchable testID="posto-bombas-combustivel" />

              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Contador Final</Text>
                  <TextInput value={contadorFinal} onChangeText={(v) => setContadorFinal(v.replace(/[^0-9.,]/g, ""))} placeholder="0" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-bombas-contador" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Último Movimento</Text>
                  <WebDateField value={dataUltMov || null} onChange={(v) => setDataUltMov(v || "")} type="date" testID="posto-bombas-data-mov" />
                </View>
              </View>

              <Text style={styles.sectionTitle}>Identificação do Equipamento</Text>
              <View style={styles.rowFields}>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Fabricante</Text>
                  <TextInput value={fabricante} onChangeText={setFabricante} placeholder="Ex.: WAYNE" placeholderTextColor={colors.muted} style={styles.input} maxLength={60} testID="posto-bombas-fabricante" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Modelo</Text>
                  <TextInput value={modelo} onChangeText={setModelo} placeholder="Ex.: FUSION" placeholderTextColor={colors.muted} style={styles.input} maxLength={60} testID="posto-bombas-modelo" />
                </View>
              </View>
              <Text style={styles.label}>Número de Série</Text>
              <TextInput value={serie} onChangeText={setSerie} placeholder="Opcional" placeholderTextColor={colors.muted} style={styles.input} maxLength={60} testID="posto-bombas-serie" />
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Medição</Text>
                  <TextInput value={tipoMedicao} onChangeText={(v) => setTipoMedicao(v.replace(/[^01]/g, "").slice(0, 1))} placeholder="0/1" placeholderTextColor={colors.muted} style={styles.input} keyboardType="number-pad" testID="posto-bombas-medicao" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Número Lacre</Text>
                  <TextInput value={numeroLacre} onChangeText={setNumeroLacre} placeholder="Opcional" placeholderTextColor={colors.muted} style={styles.input} maxLength={20} testID="posto-bombas-lacre" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Data Lacre</Text>
                  <WebDateField value={dtLacre || null} onChange={(v) => setDtLacre(v || "")} type="date" testID="posto-bombas-data-lacre" />
                </View>
              </View>

              <Pressable onPress={save} disabled={saving} style={[styles.primaryBtn, saving && { opacity: 0.6 }]} testID="posto-bombas-salvar">
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
    flex: 1, backgroundColor: "rgba(0,0,0,0.4)",
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
    maxWidth: Platform.OS === "web" ? 520 : undefined,
    alignSelf: Platform.OS === "web" ? "center" : undefined,
    padding: Platform.OS === "web" ? spacing.md : spacing.lg,
    maxHeight: "88%",
    gap: spacing.sm,
  },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.sm },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.onSurface, marginTop: spacing.md },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  colNarrow: { width: 74 },
  colFlex: { flex: 1 },
  primaryBtn: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center", marginTop: spacing.md },
  primaryBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
