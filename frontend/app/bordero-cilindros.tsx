// Borderô de Cilindros (Fase 3c do módulo Cilindros) — relatório de
// consulta sobre Viagem/Viagem_Cilindro/Viagem_Retorno (populadas pela
// tela de Manutenção de Viagens). Legado: FrmManCil.frm, Frame11 "Bordero
// de Cilindros". Ver PENDENCIAS.md > "Cilindros" > "Fase 3c".
//
// Confirmado com o usuário via pergunta direta: consulta em tela +
// exportação Excel — SEM impressão formatada (diferente do restante do
// legado). Tela só-leitura (nenhuma ação de gravação), web-only (mesmo
// padrão do resto do módulo Cilindros).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import WebDateField from "@/src/components/WebDateField";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";

type Conn = Connection;

const int_ = (s: string): number | undefined => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || undefined : undefined);

const STATUS_CODES = ["AP", "APT", "DP", "DPT", "DT", "RT"];

type BorderoItem = {
  codigo: number; ordem: number; status_saida: string; status_retorno: string | null;
  os_saida: string | null; os_retorno: string | null; nf_retorno: number | null;
  cliente: number; viagem_codigo: number; tipo_viagem: number; saida: string | null; retorno: string | null;
  cil_codigo: string | null; capacidade: number | null; pressao: number | null; padrao: string | null;
  descricao: string | null; grupo_gas: string | null; nds_retorno: string | null; em_aberto: number;
};

type BorderoGrupo = { cliente: string; itens: BorderoItem[]; saida: number; retorno: number; em_aberto: number };
type BorderoTotal = { saida: number; retorno: number; em_aberto: number };
type ResumoItem = { grupo_gas: string | null; capacidade: number | null; pressao: number | null; padrao: string | null; descricao: string | null; status: string | null; total: number };

export default function BorderoCilindrosScreen() {
  const router = useRouter();
  const { can, isMaster } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Borderô de Cilindros está disponível apenas no web." testID="bordero-web-only" />;
  }

  const canOpen = can("BORDERO_CIL.ABRIR") || isMaster;
  const canExportar = can("BORDERO_CIL.EXPORTAR") || isMaster;

  const [conn, setConn] = useState<Conn | null>(null);
  const [segmentoOptions, setSegmentoOptions] = useState<SelectOption[]>([]);
  const [statusOptions, setStatusOptions] = useState<{ value: string; label: string }[]>([]);

  const [tipoViagem, setTipoViagem] = useState<0 | 1 | null>(null);
  const [statusSel, setStatusSel] = useState<string[]>([]);
  const [saidaDe, setSaidaDe] = useState<string | null>(null);
  const [saidaAte, setSaidaAte] = useState<string | null>(null);
  const [retornoDe, setRetornoDe] = useState<string | null>(null);
  const [retornoAte, setRetornoAte] = useState<string | null>(null);
  const [grupoGas, setGrupoGas] = useState("");
  const [capacidade, setCapacidade] = useState("");
  const [pressao, setPressao] = useState("");
  const [padrao, setPadrao] = useState("");
  const [documento, setDocumento] = useState("");
  const [segmento, setSegmento] = useState<string | null>(null);
  const [soContratoAtivo, setSoContratoAtivo] = useState(false);
  const [emAberto, setEmAberto] = useState<"aberto" | "todos">("todos");

  const [loading, setLoading] = useState(false);
  const [grupos, setGrupos] = useState<BorderoGrupo[]>([]);
  const [total, setTotal] = useState<BorderoTotal>({ saida: 0, retorno: 0, em_aberto: 0 });
  const [resumo, setResumo] = useState<ResumoItem[]>([]);
  const [mostrarResumo, setMostrarResumo] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
      try {
        const [rSeg, rSit] = await Promise.all([
          fetch(`${base}/api/segmentos?${qs}`).then((r) => r.json()).catch(() => null),
          fetch(`${base}/api/cilindro-situacao?${qs}`).then((r) => r.json()).catch(() => null),
        ]);
        if (rSeg?.success) setSegmentoOptions(rSeg.items.map((i: any) => ({ value: i.codigo, label: i.descricao })));
        if (rSit?.success) {
          setStatusOptions(
            rSit.items
              .filter((i: any) => STATUS_CODES.includes(i.codigo))
              .map((i: any) => ({ value: i.codigo, label: `${i.codigo} - ${i.descricao}` })),
          );
        }
      } catch {
        // silencioso — combos ficam vazios
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const toggleStatus = (v: string) => {
    setStatusSel((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));
  };

  const buildQs = useCallback((c: Conn) => {
    const params = new URLSearchParams();
    params.set("servidor", c.servidor);
    params.set("banco", c.banco);
    if (tipoViagem !== null) params.set("tipo_viagem", String(tipoViagem));
    if (statusSel.length) params.set("status", statusSel.join(","));
    if (saidaDe) params.set("saida_de", saidaDe);
    if (saidaAte) params.set("saida_ate", saidaAte);
    if (retornoDe) params.set("retorno_de", retornoDe);
    if (retornoAte) params.set("retorno_ate", retornoAte);
    if (grupoGas.trim()) params.set("grupo_gas", grupoGas.trim());
    if (int_(capacidade) !== undefined) params.set("capacidade", String(int_(capacidade)));
    if (int_(pressao) !== undefined) params.set("pressao", String(int_(pressao)));
    if (padrao.trim()) params.set("padrao", padrao.trim());
    if (documento.trim()) params.set("documento", documento.trim());
    if (segmento) params.set("segmento", segmento);
    if (soContratoAtivo) params.set("situacao_contrato", "A");
    if (emAberto === "aberto") params.set("em_aberto", "true");
    return params.toString();
  }, [tipoViagem, statusSel, saidaDe, saidaAte, retornoDe, retornoAte, grupoGas, capacidade, pressao, padrao, documento, segmento, soContratoAtivo, emAberto]);

  const consultar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = buildQs(conn);
      const [rList, rResumo] = await Promise.all([
        fetch(`${base}/api/bordero-cilindros?${qs}`).then((r) => r.json()),
        fetch(`${base}/api/bordero-cilindros/resumo?${qs}`).then((r) => r.json()),
      ]);
      if (rList?.success) { setGrupos(rList.grupos || []); setTotal(rList.total || { saida: 0, retorno: 0, em_aberto: 0 }); }
      else { fb.showError(rList?.message || "Erro ao consultar."); setGrupos([]); }
      if (rResumo?.success) setResumo(rResumo.items || []);
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setLoading(false);
    }
  }, [conn, buildQs, fb]);

  const exportarExcel = () => {
    if (!grupos.length) { fb.showWarning("Consulte antes de exportar."); return; }
    const detalhe = grupos.flatMap((g) =>
      g.itens.map((it) => ({
        Cliente: g.cliente, Viagem: it.viagem_codigo, Ordem: it.ordem,
        Cilindro: it.cil_codigo, Capacidade: it.capacidade, Pressão: it.pressao, Padrão: it.padrao,
        Descrição: it.descricao, "Grupo Gás": it.grupo_gas,
        "Status Saída": it.status_saida, "Status Retorno": it.status_retorno,
        "O.S. Saída": it.os_saida, "O.S. Retorno": it.os_retorno, "NF Retorno": it.nf_retorno,
        "Nº Série Retorno": it.nds_retorno, Saída: it.saida, Retorno: it.retorno,
        "Em Aberto": it.em_aberto ? "Sim" : "Não",
      })),
    );
    const subtotais = grupos.map((g) => ({ Cliente: g.cliente, Saída: g.saida, Retorno: g.retorno, "Em Aberto": g.em_aberto }));
    const resumoRows = resumo.map((r) => ({
      "Grupo Gás": r.grupo_gas, Capacidade: r.capacidade, Pressão: r.pressao, Padrão: r.padrao,
      Descrição: r.descricao, Status: r.status, Total: r.total,
    }));
    exportSheetsToXlsx("bordero-cilindros", [
      { name: "Detalhe", rows: detalhe },
      { name: "Subtotais por Cliente", rows: subtotais },
      { name: "Resumo por Status", rows: resumoRows },
    ]);
  };

  if (!canOpen) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Borderô de Cilindros." testID="bordero-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="bordero-cilindros-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Borderô de Cilindros</Text>
        {canExportar ? (
          <Pressable onPress={exportarExcel} style={styles.saveBtn} hitSlop={8} testID="bordero-exportar">
            <Ionicons name="download-outline" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.saveLabel}>Excel</Text>
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Tipo de Viagem</Text>
                <View style={styles.pillRow}>
                  <Pressable onPress={() => setTipoViagem(null)} style={[styles.pillBtn, tipoViagem === null && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, tipoViagem === null && styles.pillBtnTextSel]}>Todas</Text>
                  </Pressable>
                  <Pressable onPress={() => setTipoViagem(0)} style={[styles.pillBtn, tipoViagem === 0 && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, tipoViagem === 0 && styles.pillBtnTextSel]}>Normal</Text>
                  </Pressable>
                  <Pressable onPress={() => setTipoViagem(1)} style={[styles.pillBtn, tipoViagem === 1 && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, tipoViagem === 1 && styles.pillBtnTextSel]}>Fábrica</Text>
                  </Pressable>
                </View>
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Situação</Text>
                <View style={styles.pillRow}>
                  <Pressable onPress={() => setEmAberto("todos")} style={[styles.pillBtn, emAberto === "todos" && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, emAberto === "todos" && styles.pillBtnTextSel]}>Todos</Text>
                  </Pressable>
                  <Pressable onPress={() => setEmAberto("aberto")} style={[styles.pillBtn, emAberto === "aberto" && styles.pillBtnSel]}>
                    <Text style={[styles.pillBtnText, emAberto === "aberto" && styles.pillBtnTextSel]}>Em Aberto</Text>
                  </Pressable>
                </View>
              </View>
              <View style={styles.colNarrow}>
                <Pressable onPress={() => setSoContratoAtivo((v) => !v)} style={styles.checkRow} testID="bordero-so-contrato-ativo">
                  <Ionicons name={soContratoAtivo ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Só contrato ativo</Text>
                </Pressable>
              </View>
            </View>

            <Text style={styles.label}>Status (deixe em branco para todos)</Text>
            <View style={styles.pillRow}>
              {statusOptions.map((o) => (
                <Pressable key={o.value} onPress={() => toggleStatus(o.value)} style={[styles.pillBtn, statusSel.includes(o.value) && styles.pillBtnSel]} testID={`bordero-status-${o.value}`}>
                  <Text style={[styles.pillBtnText, statusSel.includes(o.value) && styles.pillBtnTextSel]}>{o.value}</Text>
                </Pressable>
              ))}
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Saída de</Text>
                <WebDateField value={saidaDe} onChange={setSaidaDe} testID="bordero-saida-de" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Saída até</Text>
                <WebDateField value={saidaAte} onChange={setSaidaAte} testID="bordero-saida-ate" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Retorno de</Text>
                <WebDateField value={retornoDe} onChange={setRetornoDe} testID="bordero-retorno-de" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Retorno até</Text>
                <WebDateField value={retornoAte} onChange={setRetornoAte} testID="bordero-retorno-ate" />
              </View>
            </View>

            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Grupo Gás</Text>
                <TextInput value={grupoGas} onChangeText={setGrupoGas} style={styles.input} autoCapitalize="characters" testID="bordero-grupo-gas" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Capacidade</Text>
                <TextInput value={capacidade} onChangeText={(v) => setCapacidade(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="bordero-capacidade" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Pressão</Text>
                <TextInput value={pressao} onChangeText={(v) => setPressao(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="bordero-pressao" />
              </View>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Padrão</Text>
                <TextInput value={padrao} onChangeText={setPadrao} style={styles.input} testID="bordero-padrao" />
              </View>
              <View style={styles.colNarrow}>
                <Text style={styles.label}>Documento (O.S./NF/Nº Série)</Text>
                <TextInput value={documento} onChangeText={setDocumento} style={styles.input} testID="bordero-documento" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Segmento do Cliente</Text>
                <SelectField value={segmento} onChange={(v) => setSegmento(v as string)} options={segmentoOptions} testID="bordero-segmento" modalTitle="Segmento" compactWeb />
              </View>
            </View>

            <View style={styles.modalActionsRow}>
              <Pressable onPress={consultar} disabled={loading} style={styles.primaryBtn} testID="bordero-consultar">
                {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Consultar</Text>}
              </Pressable>
            </View>
          </View>

          {grupos.length > 0 ? (
            <View style={styles.card}>
              <View style={styles.totalRow}>
                <Text style={styles.sectionTitle}>Resultado</Text>
                <Text style={styles.hint}>Saída: {total.saida} · Retorno: {total.retorno} · Em Aberto: {total.em_aberto}</Text>
              </View>
              {grupos.map((g) => (
                <View key={g.cliente} style={styles.grupoBox}>
                  <Text style={styles.grupoTitle}>{g.cliente}</Text>
                  {g.itens.map((it) => (
                    <View key={it.codigo} style={styles.itemRow}>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.gridRowText}>
                          Viagem #{it.viagem_codigo} · Ordem {it.ordem} · {it.cil_codigo} · Cap.{it.capacidade} · Pressão {it.pressao} · Padrão {it.padrao}
                        </Text>
                        <Text style={styles.hint}>
                          Saída: {it.status_saida}{it.status_retorno ? ` · Retorno: ${it.status_retorno}` : " · Retorno pendente"}
                          {it.os_retorno ? ` · O.S. ${it.os_retorno}` : ""}{it.em_aberto ? " · Em Aberto" : ""}
                        </Text>
                      </View>
                    </View>
                  ))}
                  <Text style={styles.subtotalText}>Subtotal — Saída: {g.saida} · Retorno: {g.retorno} · Em Aberto: {g.em_aberto}</Text>
                </View>
              ))}
            </View>
          ) : !loading ? (
            <Text style={styles.hint}>Ajuste os filtros e toque em Consultar.</Text>
          ) : null}

          {resumo.length > 0 ? (
            <View style={styles.card}>
              <Pressable onPress={() => setMostrarResumo((v) => !v)} style={styles.itensHeaderRow} testID="bordero-toggle-resumo">
                <Text style={styles.sectionTitle}>Resumo por Status</Text>
                <Ionicons name={mostrarResumo ? "chevron-up" : "chevron-down"} size={18} color={colors.muted} />
              </Pressable>
              {mostrarResumo ? resumo.map((r, idx) => (
                <View key={idx} style={styles.itemRow}>
                  <Text style={styles.gridRowText}>
                    {r.grupo_gas} · Cap.{r.capacidade} · Pressão {r.pressao} · Padrão {r.padrao} · {r.descricao}
                  </Text>
                  <Text style={styles.hint}>{r.status}: {r.total}</Text>
                </View>
              )) : null}
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 170 },
  colTiny: { width: 100 },

  checkRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 11 },
  checkLabel: { fontSize: 13, color: colors.onSurface },

  pillRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },

  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  totalRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  itensHeaderRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  grupoBox: { marginBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: spacing.sm },
  grupoTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: 4 },
  itemRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm, paddingVertical: 6 },
  gridRowText: { fontSize: 13, color: colors.onSurface },
  subtotalText: { fontSize: 12, color: colors.muted, fontWeight: "600", marginTop: 4, textAlign: "right" },
});
