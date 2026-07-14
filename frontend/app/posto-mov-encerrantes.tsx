// Posto de Combustível > Mov. Encerrantes — migração de `frmmovbomba.frm`
// ("Movimentação de Bombas", pasta VB6 Posto). Lançamento diário do
// encerrante (Contador Inicial/Final + Aferição) por bomba/turno — o
// volume vendido é calculado e cascateia pra Bomba/Estoque/Custo
// Combustível (consumo FIFO). Ver backend/services/mov_encerrante_service.py
// pro que foi deliberadamente simplificado (sem Excluir; sem os truques
// de VB6 replicados — script de correção hardcoded, patch cross-turno
// silencioso, limpeza de lotes de custo).
//
// "DATESIST" do legado é a `data_movimento` retornada por
// `/posto/mov-encerrantes/opcoes` — usada aqui só como valor padrão do
// campo Data (a validação de verdade é sempre no backend).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Image, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
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
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER, WEB_FILTER_CARD } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type BombaOpt = { codigo: number; combustivel_descricao: string };
type Item = {
  data: string; turno: number; bomba: number; combustivel_descricao: string;
  funcionario: number | null; funcionario_nome: string;
  contador_inicial: number; contador_final: number; afericao: number;
};

function fmt(v: number) { return v.toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }); }
function parseNum(s: string): number { const n = parseFloat(s.replace(/\./g, "").replace(",", ".")); return isNaN(n) ? 0 : n; }

export default function PostoMovEncerrantesScreen() {
  const router = useRouter();
  const { can, isMaster, moduleOn } = usePermissions();
  const auditCtx = useAuditContext();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Mov. Encerrantes está disponível apenas no web." testID="posto-mov-encerrantes-web-only" />;
  }
  if (!moduleOn("Posto")) {
    return <LockedView title="Módulo desativado" message="O módulo Posto de Combustível está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo." testID="posto-mov-encerrantes-module-off" />;
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [bombas, setBombas] = useState<BombaOpt[]>([]);
  const [turnos, setTurnos] = useState<number[]>([]);
  const [funcionarios, setFuncionarios] = useState<{ codigo: number; nome: string }[]>([]);
  const [itens, setItens] = useState<Item[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const [data, setData] = useState("");
  const [turno, setTurno] = useState<number | null>(null);
  const [bomba, setBomba] = useState<number | null>(null);
  const [funcionario, setFuncionario] = useState<number | null>(null);
  const [contadorInicial, setContadorInicial] = useState("");
  const [contadorFinal, setContadorFinal] = useState("");
  const [afericao, setAfericao] = useState("0");

  const showToast = (m: string) => { setToast(m); setTimeout(() => setToast(null), 2500); };

  const loadOpcoes = useCallback(async (c: Conn) => {
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      const [ro, rb] = await Promise.all([
        fetch(`${base}/api/posto/mov-encerrantes/opcoes?${qs}`),
        fetch(`${base}/api/posto/bombas?${qs}`),
      ]);
      const jo = await ro.json();
      const jb = await rb.json();
      if (jo?.success) {
        setTurnos(jo.turnos || []);
        setFuncionarios(jo.funcionarios || []);
        if (jo.data_movimento) setData(jo.data_movimento);
      } else if (jo?.message) showToast(jo.message);
      setBombas(jb?.success ? jb.items || [] : []);
    } catch { /* ignore */ }
  }, []);

  const loadItens = useCallback(async (c: Conn, d: string) => {
    if (!d) return;
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&data=${encodeURIComponent(d)}`;
      const r = await fetch(`${base}/api/posto/mov-encerrantes?${qs}`);
      const j = await r.json();
      setItens(j?.success ? j.items || [] : []);
    } catch { setItens([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      loadOpcoes(cc);
    })();
  }, [router, loadOpcoes]);

  useEffect(() => {
    if (conn && data) loadItens(conn, data);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, conn]);

  const limpar = () => { setBomba(null); setFuncionario(null); setContadorInicial(""); setContadorFinal(""); setAfericao("0"); };

  const abrirEdicao = (it: Item) => {
    setTurno(it.turno); setBomba(it.bomba); setFuncionario(it.funcionario);
    setContadorInicial(fmt(it.contador_inicial)); setContadorFinal(fmt(it.contador_final)); setAfericao(fmt(it.afericao));
  };

  const gravar = async () => {
    if (!conn) return;
    if (!data) { showToast("Selecione a data."); return; }
    if (turno == null) { showToast("Selecione o turno."); return; }
    if (bomba == null) { showToast("Selecione a bomba."); return; }
    if (funcionario == null) { showToast("Selecione o funcionário."); return; }
    if (!contadorFinal.trim()) { showToast("Informe o contador final."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/posto/mov-encerrantes`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          data, turno, bomba, funcionario,
          contador_inicial: parseNum(contadorInicial || "0"),
          contador_final: parseNum(contadorFinal),
          afericao: parseNum(afericao || "0"),
        }),
      });
      const j = await r.json();
      if (j?.success) { showToast(j.message || "Gravado."); limpar(); loadItens(conn, data); }
      else showToast(j?.message || "Falha ao gravar.");
    } catch (e) { showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const bombaOptions: SelectOption[] = bombas.map((b) => ({ value: b.codigo, label: `Bomba ${b.codigo} (${b.combustivel_descricao})` }));
  const turnoOptions: SelectOption[] = turnos.map((t) => ({ value: t, label: `Turno ${t}` }));
  const funcOptions: SelectOption[] = funcionarios.map((f) => ({ value: f.codigo, label: f.nome }));
  const canSave = can("POSTO_ENCERR.GRAVAR") || isMaster;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="posto-mov-encerrantes-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Mov. Encerrantes</Text>
        {canSave ? (
          <Pressable onPress={gravar} disabled={saving} style={styles.saveBtn} testID="posto-mov-encerrantes-gravar">
            {saving ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]}>
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Lançamento de Encerrante</Text>
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Data *</Text>
                <WebDateField value={data} onChange={(v) => setData(v || data)} type="date" testID="posto-mov-encerrantes-data" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Turno *</Text>
                <SelectField value={turno} onChange={(v) => setTurno(v == null ? null : Number(v))} options={turnoOptions} placeholder="…" compactWeb testID="posto-mov-encerrantes-turno" />
              </View>
            </View>
            <Text style={styles.label}>Bomba *</Text>
            <SelectField value={bomba} onChange={(v) => setBomba(v == null ? null : Number(v))} options={bombaOptions} placeholder="Selecione…" compactWeb searchable testID="posto-mov-encerrantes-bomba" />
            <Text style={styles.label}>Funcionário *</Text>
            <SelectField value={funcionario} onChange={(v) => setFuncionario(v == null ? null : Number(v))} options={funcOptions} placeholder="Selecione…" compactWeb searchable testID="posto-mov-encerrantes-funcionario" />
            <View style={styles.rowFields}>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Contador Inicial</Text>
                <TextInput value={contadorInicial} onChangeText={(v) => setContadorInicial(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-mov-encerrantes-inicial" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Contador Final *</Text>
                <TextInput value={contadorFinal} onChangeText={(v) => setContadorFinal(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-mov-encerrantes-final" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Aferição</Text>
                <TextInput value={afericao} onChangeText={(v) => setAfericao(v.replace(/[^0-9.,]/g, ""))} placeholder="0,000" placeholderTextColor={colors.muted} style={styles.input} keyboardType="decimal-pad" testID="posto-mov-encerrantes-afericao" />
              </View>
            </View>
          </View>

          <View style={[styles.card, isWeb && styles.cardWeb]}>
            <Text style={styles.sectionTitle}>Encerrantes em {data}</Text>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 12 }} /> : null}
            {!loading && itens.length === 0 ? <Text style={styles.empty}>Nenhum encerrante lançado nesta data.</Text> : null}
            {itens.map((it) => (
              <Pressable key={`${it.turno}-${it.bomba}`} style={styles.row} onPress={() => canSave && abrirEdicao(it)} testID={`posto-mov-encerrantes-row-${it.turno}-${it.bomba}`}>
                <Text style={styles.rowTitle}>Bomba {it.bomba} · Turno {it.turno} · {it.combustivel_descricao}</Text>
                <Text style={styles.rowSub}>
                  {it.funcionario_nome || `Func. #${it.funcionario}`} · Inicial {fmt(it.contador_inicial)} · Final {fmt(it.contador_final)} · Aferição {fmt(it.afericao)}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      </ScrollView>

      {toast ? <View style={styles.toast}><Text style={styles.toastText}>{toast}</Text></View> : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  saveBtn: { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, backgroundColor: "rgba(255,255,255,0.2)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 14 },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.md, gap: spacing.sm },
  cardWeb: {},
  sectionTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: spacing.xs },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.xs },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-start" },
  colNarrow: { width: 110 },
  colFlex: { flex: 1 },
  row: {
    alignSelf: "stretch", width: "100%", gap: 4,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, marginTop: spacing.sm,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  empty: { textAlign: "center", color: colors.muted, marginTop: 16 },
  toast: { position: "absolute", bottom: 40, alignSelf: "center", backgroundColor: colors.onSurface, paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.pill },
  toastText: { color: colors.surface, fontSize: 13 },
});
