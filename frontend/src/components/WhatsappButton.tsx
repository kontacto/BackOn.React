import { useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { apiGet, apiSend } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type Props = {
  conn: Connection | null;
  documentType: "PED" | "OS";
  documentId: number;
  userId?: number | null;
  companyId?: string | null;
};

type LogItem = {
  id: number; phone_number: string; status: string; error_message: string;
  provider: string; sent_at: string | null; user_nome: string;
};

export default function WhatsappButton({ conn, documentType, documentId, userId, companyId }: Props) {
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"send" | "history">("send");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [phone, setPhone] = useState("");
  const [phoneValid, setPhoneValid] = useState(false);
  const [message, setMessage] = useState("");
  const [cfgEnabled, setCfgEnabled] = useState(true);
  const [cfgProvider, setCfgProvider] = useState("");
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [logsLoading, setLogsLoading] = useState(false);
  // Status global do envio por WhatsApp (flag "enabled" em Configurações).
  // null = carregando; false = desativado → botão fica desabilitado.
  const [globalEnabled, setGlobalEnabled] = useState<boolean | null>(null);

  useEffect(() => {
    if (!conn) return;
    let active = true;
    (async () => {
      try {
        const j = await apiGet(conn, "/api/whatsapp/config");
        if (active) setGlobalEnabled(!!j?.config?.enabled);
      } catch {
        if (active) setGlobalEnabled(false);
      }
    })();
    return () => { active = false; };
  }, [conn]);

  const loadPreview = async () => {
    if (!conn) return;
    setLoading(true);
    setResult(null);
    try {
      const j = await apiGet(conn, "/api/whatsapp/preview", { document_type: documentType, document_id: documentId });
      if (j?.success) {
        setPhone(j.phone || "");
        setPhoneValid(!!j.phone_valid);
        setMessage(j.message || "");
        setCfgEnabled(!!j.enabled);
        setCfgProvider(j.provider || "");
      } else {
        setResult({ ok: false, text: j?.message || "Falha ao preparar mensagem." });
      }
    } catch (e) {
      setResult({ ok: false, text: `Erro: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setLoading(false);
    }
  };

  const loadLogs = async () => {
    if (!conn) return;
    setLogsLoading(true);
    try {
      const j = await apiGet(conn, "/api/whatsapp/logs", { document_type: documentType, document_id: documentId });
      setLogs(j?.items || []);
    } catch {
      setLogs([]);
    } finally {
      setLogsLoading(false);
    }
  };

  const handleOpen = () => {
    setOpen(true);
    setTab("send");
    loadPreview();
  };

  const switchTab = (t: "send" | "history") => {
    setTab(t);
    if (t === "history") loadLogs();
  };

  const phoneDigitsValid = () => /^\+[1-9]\d{7,14}$/.test(phone.trim());

  const handleSend = async () => {
    if (!conn) return;
    if (!cfgEnabled) { setResult({ ok: false, text: "WhatsApp desativado. Ative em Configurações → WhatsApp." }); return; }
    if (!phoneDigitsValid()) { setResult({ ok: false, text: "Número inválido. Use o formato internacional (+55...)." }); return; }
    if (!message.trim()) { setResult({ ok: false, text: "A mensagem não pode estar vazia." }); return; }
    setSending(true);
    setResult(null);
    try {
      const j = await apiSend(conn, "/api/whatsapp/send", "POST", {
        servidor: conn.servidor, banco: conn.banco,
        document_type: documentType, document_id: documentId,
        phone: phone.trim(), message, user_id: userId ?? null, company_id: companyId ?? null,
      });
      if (j?.success) setResult({ ok: true, text: "Mensagem enviada com sucesso!" });
      else setResult({ ok: false, text: j?.message || "Falha no envio." });
    } catch (e) {
      setResult({ ok: false, text: `Erro: ${e instanceof Error ? e.message : String(e)}` });
    } finally {
      setSending(false);
    }
  };

  return (
    <>
      <Pressable
        onPress={handleOpen}
        disabled={globalEnabled === false}
        style={({ pressed }) => [
          styles.btn,
          globalEnabled === false && styles.btnDisabled,
          pressed && globalEnabled !== false && { opacity: 0.85 },
        ]}
        testID={`whatsapp-btn-${documentType}`}
      >
        <Ionicons name="logo-whatsapp" size={18} color="#fff" />
        <Text style={styles.btnText}>
          {globalEnabled === false ? "WhatsApp desativado" : "Enviar por WhatsApp"}
        </Text>
      </Pressable>
      {globalEnabled === false ? (
        <Text style={styles.disabledHint} testID={`whatsapp-disabled-${documentType}`}>
          O envio por WhatsApp está desativado em Configurações.
        </Text>
      ) : null}

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.handle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>WhatsApp</Text>
              <Pressable onPress={() => setOpen(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>

            <View style={styles.tabs}>
              <Pressable onPress={() => switchTab("send")} style={[styles.tab, tab === "send" && styles.tabSel]} testID="wa-tab-send">
                <Text style={[styles.tabText, tab === "send" && styles.tabTextSel]}>Enviar</Text>
              </Pressable>
              <Pressable onPress={() => switchTab("history")} style={[styles.tab, tab === "history" && styles.tabSel]} testID="wa-tab-history">
                <Text style={[styles.tabText, tab === "history" && styles.tabTextSel]}>Histórico</Text>
              </Pressable>
            </View>

            {tab === "send" ? (
              loading ? (
                <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 30 }} />
              ) : (
                <ScrollView style={{ maxHeight: 460 }} keyboardShouldPersistTaps="handled">
                  {!cfgEnabled ? (
                    <View style={styles.warn}>
                      <Ionicons name="alert-circle" size={16} color={colors.error} />
                      <Text style={styles.warnText}>WhatsApp não está ativado. Vá em Configurações → WhatsApp.</Text>
                    </View>
                  ) : null}

                  <Text style={styles.label}>Número do destinatário</Text>
                  <TextInput
                    value={phone}
                    onChangeText={(v) => { setPhone(v); }}
                    placeholder="+5511999999999"
                    placeholderTextColor={colors.muted}
                    keyboardType="phone-pad"
                    style={[styles.input, !phoneDigitsValid() && phone.length > 0 && { borderColor: colors.error }]}
                    testID="wa-phone"
                  />
                  {!phoneValid && phone.length === 0 ? (
                    <Text style={styles.hintErr}>Cliente sem celular cadastrado — informe o número.</Text>
                  ) : null}

                  <Text style={styles.label}>Mensagem (pré-visualização)</Text>
                  <TextInput
                    value={message}
                    onChangeText={setMessage}
                    multiline
                    style={[styles.input, { minHeight: 200, textAlignVertical: "top" }]}
                    testID="wa-message"
                  />
                  {cfgProvider ? <Text style={styles.providerHint}>Provedor: {cfgProvider}</Text> : null}

                  {result ? (
                    <View style={[styles.resultBox, { backgroundColor: result.ok ? "#E7F6EC" : "#FDE7E7" }]} testID="wa-result">
                      <Ionicons name={result.ok ? "checkmark-circle" : "alert-circle"} size={18} color={result.ok ? colors.success : colors.error} />
                      <Text style={[styles.resultText, { color: result.ok ? colors.success : colors.error }]}>{result.text}</Text>
                    </View>
                  ) : null}

                  <Pressable
                    onPress={handleSend}
                    disabled={sending}
                    style={({ pressed }) => [styles.sendBtn, (pressed || sending) && { opacity: 0.85 }]}
                    testID="wa-send"
                  >
                    {sending ? <ActivityIndicator color="#fff" size="small" /> : (
                      <>
                        <Ionicons name="send" size={16} color="#fff" />
                        <Text style={styles.sendBtnText}>Enviar agora</Text>
                      </>
                    )}
                  </Pressable>
                  <View style={{ height: 20 }} />
                </ScrollView>
              )
            ) : (
              logsLoading ? (
                <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 30 }} />
              ) : logs.length === 0 ? (
                <Text style={styles.empty}>Nenhum envio registrado.</Text>
              ) : (
                <ScrollView style={{ maxHeight: 460 }}>
                  {logs.map((l) => (
                    <View key={l.id} style={styles.logRow} testID={`wa-log-${l.id}`}>
                      <View style={[styles.logDot, { backgroundColor: l.status === "SUCCESS" ? colors.success : colors.error }]} />
                      <View style={{ flex: 1 }}>
                        <Text style={styles.logTop}>
                          {l.status === "SUCCESS" ? "Enviado" : "Falhou"} · {l.phone_number}
                        </Text>
                        <Text style={styles.logSub}>
                          {(l.sent_at || "").replace("T", " ").slice(0, 16)}{l.user_nome ? ` · ${l.user_nome}` : ""}{l.provider ? ` · ${l.provider}` : ""}
                        </Text>
                        {l.status !== "SUCCESS" && l.error_message ? (
                          <Text style={styles.logErr} numberOfLines={2}>{l.error_message}</Text>
                        ) : null}
                      </View>
                    </View>
                  ))}
                  <View style={{ height: 20 }} />
                </ScrollView>
              )
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  btn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: "#25D366", borderRadius: radius.md, paddingVertical: 14, marginTop: spacing.md },
  btnDisabled: { backgroundColor: colors.muted, opacity: 0.6 },
  disabledHint: { fontSize: 12, color: colors.muted, textAlign: "center", marginTop: spacing.xs },
  btnText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: { backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg, paddingHorizontal: spacing.lg, paddingTop: spacing.sm, paddingBottom: spacing.xxl, minHeight: 360 },
  handle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.sm },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  tabs: { flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: 3, marginBottom: spacing.md },
  tab: { flex: 1, paddingVertical: 8, alignItems: "center", borderRadius: radius.sm },
  tabSel: { backgroundColor: colors.surface },
  tabText: { fontSize: 13, fontWeight: "600", color: colors.muted },
  tabTextSel: { color: colors.brandPrimary },
  label: { fontSize: 12, color: colors.muted, marginBottom: 4, marginTop: spacing.sm, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4 },
  input: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, borderWidth: 1, borderColor: colors.border, color: colors.onSurface, fontSize: 14 },
  hintErr: { fontSize: 12, color: colors.error, marginTop: 4 },
  providerHint: { fontSize: 12, color: colors.muted, marginTop: 6 },
  warn: { flexDirection: "row", alignItems: "center", gap: 8, backgroundColor: "#FDE7E7", borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.sm },
  warnText: { flex: 1, fontSize: 12, color: colors.error },
  resultBox: { flexDirection: "row", alignItems: "center", gap: 8, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md },
  resultText: { flex: 1, fontSize: 13, fontWeight: "500" },
  sendBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, backgroundColor: "#25D366", borderRadius: radius.md, paddingVertical: 14, marginTop: spacing.lg },
  sendBtnText: { color: "#fff", fontSize: 15, fontWeight: "700" },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginVertical: 30 },
  logRow: { flexDirection: "row", gap: spacing.sm, paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border },
  logDot: { width: 10, height: 10, borderRadius: 5, marginTop: 5 },
  logTop: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  logSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  logErr: { fontSize: 12, color: colors.error, marginTop: 4 },
});
