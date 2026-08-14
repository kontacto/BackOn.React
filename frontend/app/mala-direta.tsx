// Mala Direta — migração de Geral\FrmMalDir2.FRM (Painel de Relatórios >
// Clientes). Decisão do usuário (2026-08-07, AskUserQuestion): substituir
// a impressão de etiqueta de endereço por envio em massa via WhatsApp/
// E-mail, reaproveitando EnvioMassaModal (mesmo recurso usado em
// Inatividade de Clientes) — ver docstring de mala_direta_service.py pro
// raciocínio completo.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import EnvioMassaModal, { DestinatarioEnvio } from "@/src/components/EnvioMassaModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type Conn = { servidor: string; banco: string; api: string };
type SubModo = "todos" | "aniversario" | "cadastro" | "tipo";

export default function MalaDiretaScreen() {
  const router = useRouter();
  const isWeb = Platform.OS === "web";
  const feedback = useFeedback();
  const [conn, setConn] = useState<Conn | null>(null);

  const [incluirClientes, setIncluirClientes] = useState(true);
  const [incluirFornecedores, setIncluirFornecedores] = useState(false);
  const [subModo, setSubModo] = useState<SubModo>("todos");
  const [tipoOpts, setTipoOpts] = useState<SelectOption[]>([]);
  const [tipoCliente, setTipoCliente] = useState<string | number | null>(null);
  const [aniversarioIni, setAniversarioIni] = useState("");
  const [aniversarioFim, setAniversarioFim] = useState("");
  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);

  const [loading, setLoading] = useState(false);
  const [destinatarios, setDestinatarios] = useState<DestinatarioEnvio[]>([]);
  const [envioOpen, setEnvioOpen] = useState(false);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s.empresa);
      if (!c) { feedback.showError("Conexão não encontrada."); return; }
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      try {
        const base = cc.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(cc.servidor)}&banco=${encodeURIComponent(cc.banco)}`;
        const r = await fetch(`${base}/api/tabelas/tipo-cliente?${qs}`);
        const j = await r.json();
        if (j?.success) setTipoOpts((j.items || []).map((t: { codigo: number; descricao: string }) => ({ value: t.codigo, label: t.descricao })));
      } catch { /* sem lista */ }
    })();
  }, [router]);

  const selecionar = useCallback(async () => {
    if (!conn) return;
    if (!incluirClientes && !incluirFornecedores) { feedback.showWarning("Selecione Clientes e/ou Fornecedores."); return; }
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      let url = `${base}/api/mala-direta/destinatarios?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}&incluir_clientes=${incluirClientes}&incluir_fornecedores=${incluirFornecedores}` +
        `&sub_modo_cliente=${subModo}`;
      if (subModo === "tipo" && tipoCliente) url += `&termo=${encodeURIComponent(String(tipoCliente))}`;
      if (subModo === "aniversario" && aniversarioIni && aniversarioFim) url += `&data_ini=${aniversarioIni}&data_fim=${aniversarioFim}`;
      if (subModo === "cadastro" && dataIni && dataFim) url += `&data_ini=${dataIni}&data_fim=${dataFim}`;
      const r = await fetch(url);
      const j = await r.json();
      if (!j?.success) { feedback.showError(j?.message || "Falha ao selecionar destinatários."); return; }
      setDestinatarios(j.destinatarios || []);
      if ((j.destinatarios || []).length === 0) feedback.showWarning("Nenhum destinatário encontrado.");
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
  }, [conn, incluirClientes, incluirFornecedores, subModo, tipoCliente, aniversarioIni, aniversarioFim, dataIni, dataFim, feedback]);

  const somenteClientes = incluirClientes && !incluirFornecedores;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="mala-direta-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.backBtn} testID="maladireta-back">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Mala Direta</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, isWeb && styles.scrollWeb]} keyboardShouldPersistTaps="handled">
        <View style={isWeb ? styles.webShell : undefined}>
          <View style={[styles.filters, isWeb && styles.filtersWeb]}>
            <Text style={styles.hint}>
              Selecione o público-alvo e envie uma mensagem em massa por WhatsApp ou E-mail. Sem impressão de etiqueta — o envio é sempre digital.
            </Text>

            <View style={styles.chipRow}>
              <Pressable onPress={() => setIncluirClientes((v) => !v)} style={styles.checkRow} testID="maladireta-clientes">
                <Ionicons name={incluirClientes ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Clientes</Text>
              </Pressable>
              <Pressable onPress={() => setIncluirFornecedores((v) => !v)} style={styles.checkRow} testID="maladireta-fornecedores">
                <Ionicons name={incluirFornecedores ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                <Text style={styles.checkLabel}>Fornecedores</Text>
              </Pressable>
            </View>

            {incluirClientes ? (
              <>
                <Text style={styles.fieldLabel}>Selecionar clientes por</Text>
                <View style={styles.chipRow}>
                  {([{ k: "todos" as const, l: "Todos" }, { k: "aniversario" as const, l: "Aniversário" }, { k: "cadastro" as const, l: "Data de Cadastro" }, { k: "tipo" as const, l: "Tipo Cliente" }]).map((o) => (
                    <Pressable key={o.k} onPress={() => setSubModo(o.k)} style={[styles.chip, subModo === o.k && styles.chipSel]} testID={`maladireta-submodo-${o.k}`}>
                      <Text style={[styles.chipText, subModo === o.k && styles.chipTextSel]}>{o.l}</Text>
                    </Pressable>
                  ))}
                </View>

                {subModo === "aniversario" ? (
                  <View style={styles.rowFields}>
                    <View style={{ width: 110 }}>
                      <Text style={styles.fieldLabel}>De (MM-DD)</Text>
                      <TextInput value={aniversarioIni} onChangeText={setAniversarioIni} placeholder="03-01" style={styles.input} testID="maladireta-aniv-ini" />
                    </View>
                    <View style={{ width: 110 }}>
                      <Text style={styles.fieldLabel}>Até (MM-DD)</Text>
                      <TextInput value={aniversarioFim} onChangeText={setAniversarioFim} placeholder="03-31" style={styles.input} testID="maladireta-aniv-fim" />
                    </View>
                  </View>
                ) : subModo === "cadastro" ? (
                  <View style={styles.rowFields}>
                    <View style={{ flex: 1, minWidth: 140 }}>
                      <Text style={styles.fieldLabel}>De</Text>
                      {isWeb ? <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="maladireta-cad-ini" /> : <DateField value={dataIni} onChange={setDataIni} testID="maladireta-cad-ini" />}
                    </View>
                    <View style={{ flex: 1, minWidth: 140 }}>
                      <Text style={styles.fieldLabel}>Até</Text>
                      {isWeb ? <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="maladireta-cad-fim" /> : <DateField value={dataFim} onChange={setDataFim} testID="maladireta-cad-fim" />}
                    </View>
                  </View>
                ) : subModo === "tipo" ? (
                  <View style={{ maxWidth: 280 }}>
                    <Text style={styles.fieldLabel}>Tipo Cliente</Text>
                    <SelectField value={tipoCliente} onChange={setTipoCliente} options={tipoOpts} placeholder="Selecione" compactWeb testID="maladireta-tipo" />
                  </View>
                ) : null}
              </>
            ) : null}

            <View style={styles.actionsRow}>
              <Pressable onPress={selecionar} disabled={loading} style={[styles.searchBtn, loading && { opacity: 0.85 }]} testID="maladireta-selecionar">
                {loading ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="search" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.searchBtnText}>Selecionar Destinatários</Text>
                  </>
                )}
              </Pressable>
              {destinatarios.length > 0 ? (
                <Pressable onPress={() => setEnvioOpen(true)} style={styles.waBtn} testID="maladireta-enviar">
                  <Ionicons name="send-outline" size={15} color={colors.onBrandPrimary} />
                  <Text style={styles.searchBtnText}>Enviar para {destinatarios.length}</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          {destinatarios.length > 0 ? (
            <View style={styles.card}>
              <Text style={styles.subMeta}>{destinatarios.length} destinatário(s) selecionado(s)</Text>
              {destinatarios.slice(0, 50).map((d, idx) => (
                <View key={`${d.codigo}-${idx}`} style={styles.row}>
                  <Ionicons name={d.tipo === "fornecedor" ? "briefcase-outline" : "person-outline"} size={14} color={colors.muted} />
                  <Text style={styles.rowLabel} numberOfLines={1}>{d.nome}</Text>
                  {d.email ? <Ionicons name="mail-outline" size={13} color={colors.success} /> : null}
                  {d.tem_telefone ? <Ionicons name="logo-whatsapp" size={13} color={colors.success} /> : null}
                </View>
              ))}
              {destinatarios.length > 50 ? <Text style={styles.subMeta}>... e mais {destinatarios.length - 50}</Text> : null}
            </View>
          ) : null}
        </View>
      </ScrollView>

      <EnvioMassaModal
        visible={envioOpen} onClose={() => setEnvioOpen(false)} conn={conn}
        destinatarios={destinatarios}
        canalWhatsapp={somenteClientes}
        canalEmail
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 16, fontWeight: "500", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filters: { gap: spacing.sm, marginBottom: spacing.sm },
  filtersWeb: WEB_FILTER_CARD,
  hint: { fontSize: 12, color: colors.muted, marginBottom: spacing.xs },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  rowFields: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  input: {
    height: 40, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  chipRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    height: 32, paddingHorizontal: spacing.md, borderRadius: radius.pill, borderWidth: 1,
    borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  checkRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
  searchBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
  },
  searchBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  waBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 36, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: colors.success,
  },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.sm },
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md,
  },
  subMeta: { fontSize: 11, color: colors.muted, marginBottom: 6 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  rowLabel: { fontSize: 12, color: colors.onSurface, flex: 1 },
});
