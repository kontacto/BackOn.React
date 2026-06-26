import { useEffect, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView,
  StyleSheet, Switch, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";

type Provider = "twilio" | "meta" | "evolution";

const PROVIDERS: { value: Provider; label: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { value: "twilio", label: "Twilio", icon: "call-outline" },
  { value: "meta", label: "Meta Cloud API", icon: "logo-facebook" },
  { value: "evolution", label: "Evolution API", icon: "server-outline" },
];

const DOCS: Record<Provider, { intro: string; steps: string[] }> = {
  twilio: {
    intro: "Use a conta da Twilio com WhatsApp habilitado.",
    steps: [
      "Crie/acesse sua conta em twilio.com e ative o WhatsApp (Messaging).",
      "Copie o Account SID e o Auth Token no Console da Twilio.",
      "Informe o número WhatsApp de origem (ex.: +14155238886 do sandbox ou seu número aprovado).",
      "Para produção, registre seu número e modelos de mensagem na Twilio.",
    ],
  },
  meta: {
    intro: "Use a WhatsApp Cloud API da Meta (Graph API).",
    steps: [
      "Crie um app em developers.facebook.com e adicione o produto WhatsApp.",
      "Copie o Phone Number ID e gere um Access Token (permanente de preferência).",
      "Mensagens fora da janela de 24h exigem template aprovado pela Meta.",
      "Adicione o número de destino aos testes enquanto não estiver em produção.",
    ],
  },
  evolution: {
    intro: "Use uma instância self-hosted da Evolution API.",
    steps: [
      "Suba a Evolution API (Docker) e crie uma instância conectada ao WhatsApp.",
      "Informe a URL base (ex.: https://seu-servidor:8080).",
      "Informe o nome da instância e a API Key (apikey) configurada.",
      "Garanta que o servidor da API esteja acessível pela internet.",
    ],
  },
};

const SECRET = "__SECRET_KEPT__"; // valor sentinela: mantém segredo já salvo

export default function WhatsappConfigScreen() {
  const router = useRouter();
  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState<{ text: string; ok: boolean } | null>(null);

  const [provider, setProvider] = useState<Provider>("twilio");
  const [enabled, setEnabled] = useState(false);
  const [signature, setSignature] = useState("");
  const [template, setTemplate] = useState("");
  const [fromNumber, setFromNumber] = useState("");
  const [twilioSid, setTwilioSid] = useState("");
  const [twilioToken, setTwilioToken] = useState("");
  const [metaPhone, setMetaPhone] = useState("");
  const [metaToken, setMetaToken] = useState("");
  const [evoUrl, setEvoUrl] = useState("");
  const [evoInstance, setEvoInstance] = useState("");
  const [evoKey, setEvoKey] = useState("");
  // controla se segredos já existem (mostra placeholder)
  const [sets, setSets] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      if (c) {
        try {
          const j = await apiGet(c, "/api/whatsapp/config");
          const cfg = j?.config || {};
          if (cfg.provider) setProvider(cfg.provider);
          setEnabled(!!cfg.enabled);
          setSignature(cfg.signature || "");
          setTemplate(cfg.message_template || "");
          setFromNumber(cfg.from_number || "");
          setEvoUrl(cfg.evolution_url || "");
          setEvoInstance(cfg.evolution_instance || "");
          setSets({
            twilio_sid: !!cfg.twilio_sid_set,
            twilio_token: !!cfg.twilio_token_set,
            meta_phone_id: !!cfg.meta_phone_id_set,
            meta_token: !!cfg.meta_token_set,
            evolution_apikey: !!cfg.evolution_apikey_set,
          });
          // pré-preenche segredos com sentinela quando já existem
          if (cfg.twilio_sid_set) setTwilioSid(SECRET);
          if (cfg.twilio_token_set) setTwilioToken(SECRET);
          if (cfg.meta_phone_id_set) setMetaPhone(SECRET);
          if (cfg.meta_token_set) setMetaToken(SECRET);
          if (cfg.evolution_apikey_set) setEvoKey(SECRET);
        } catch {
          // silencioso
        }
      }
      setLoading(false);
    })();
  }, []);

  const clean = (v: string) => (v === SECRET ? "" : v.trim());

  const handleSave = async () => {
    if (!conn) return;
    setSaving(true);
    setMsg(null);
    try {
      const body = {
        servidor: conn.servidor,
        banco: conn.banco,
        provider,
        enabled,
        signature: signature.trim(),
        from_number: fromNumber.trim(),
        // segredos: vazio = mantém o que já estava salvo (backend preserva)
        twilio_sid: clean(twilioSid),
        twilio_token: clean(twilioToken),
        meta_phone_id: clean(metaPhone),
        meta_token: clean(metaToken),
        evolution_url: evoUrl.trim(),
        evolution_instance: evoInstance.trim(),
        evolution_apikey: clean(evoKey),
        message_template: template.trim(),
      };
      const j = await apiSend(conn, "/api/whatsapp/config", "POST", body);
      if (j?.success) setMsg({ text: "Configuração salva com sucesso.", ok: true });
      else setMsg({ text: j?.message || "Falha ao salvar.", ok: false });
    } catch (e) {
      setMsg({ text: `Erro: ${e instanceof Error ? e.message : String(e)}`, ok: false });
    } finally {
      setSaving(false);
    }
  };

  const Field = ({ label, value, onChange, placeholder, secure, keyboardType }: {
    label: string; value: string; onChange: (v: string) => void; placeholder?: string;
    secure?: boolean; keyboardType?: "default" | "url" | "phone-pad";
  }) => (
    <View style={{ marginBottom: spacing.sm }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      <TextInput
        value={value === SECRET ? "" : value}
        onChangeText={onChange}
        placeholder={value === SECRET ? "•••••• (mantém o salvo — digite p/ alterar)" : placeholder}
        placeholderTextColor={colors.muted}
        style={styles.input}
        secureTextEntry={secure && value !== SECRET}
        autoCapitalize="none"
        keyboardType={keyboardType || "default"}
      />
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  const doc = DOCS[provider];

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="whatsapp-config-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backBtn} hitSlop={12} testID="wa-config-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>WhatsApp</Text>
        <Pressable onPress={handleSave} disabled={saving} style={styles.saveBtn} testID="wa-config-save">
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Salvar</Text>}
        </Pressable>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          <View style={styles.rowBetween}>
            <View style={{ flex: 1 }}>
              <Text style={styles.switchLabel}>Ativar envio por WhatsApp</Text>
              <Text style={styles.switchHint}>Habilita o botão nas telas de Pedido e OS</Text>
            </View>
            <Switch value={enabled} onValueChange={setEnabled} testID="wa-config-enabled" />
          </View>

          <Text style={styles.sectionTitle}>Provedor</Text>
          <View style={styles.providerRow}>
            {PROVIDERS.map((p) => {
              const sel = provider === p.value;
              return (
                <Pressable
                  key={p.value}
                  onPress={() => setProvider(p.value)}
                  style={[styles.providerChip, sel && styles.providerChipSel]}
                  testID={`wa-provider-${p.value}`}
                >
                  <Ionicons name={p.icon} size={18} color={sel ? colors.onBrandPrimary : colors.brandPrimary} />
                  <Text style={[styles.providerText, sel && { color: colors.onBrandPrimary }]}>{p.label}</Text>
                </Pressable>
              );
            })}
          </View>

          {/* Documentação embutida */}
          <View style={styles.docCard} testID="wa-config-docs">
            <View style={{ flexDirection: "row", alignItems: "center", gap: 6, marginBottom: 6 }}>
              <Ionicons name="information-circle-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.docTitle}>Como configurar</Text>
            </View>
            <Text style={styles.docIntro}>{doc.intro}</Text>
            {doc.steps.map((s, i) => (
              <View key={i} style={styles.docStep}>
                <Text style={styles.docNum}>{i + 1}.</Text>
                <Text style={styles.docStepText}>{s}</Text>
              </View>
            ))}
          </View>

          <Text style={styles.sectionTitle}>Credenciais</Text>
          {provider === "twilio" ? (
            <>
              <Field label="Account SID" value={twilioSid} onChange={setTwilioSid} placeholder="ACxxxxxxxx" secure />
              <Field label="Auth Token" value={twilioToken} onChange={setTwilioToken} placeholder="token" secure />
              <Field label="Número de origem (From)" value={fromNumber} onChange={setFromNumber} placeholder="+14155238886" keyboardType="phone-pad" />
            </>
          ) : provider === "meta" ? (
            <>
              <Field label="Phone Number ID" value={metaPhone} onChange={setMetaPhone} placeholder="1234567890" secure />
              <Field label="Access Token" value={metaToken} onChange={setMetaToken} placeholder="EAAB..." secure />
            </>
          ) : (
            <>
              <Field label="URL da API" value={evoUrl} onChange={setEvoUrl} placeholder="https://seu-servidor:8080" keyboardType="url" />
              <Field label="Instância" value={evoInstance} onChange={setEvoInstance} placeholder="instancia1" />
              <Field label="API Key" value={evoKey} onChange={setEvoKey} placeholder="apikey" secure />
            </>
          )}

          <Text style={styles.sectionTitle}>Mensagem</Text>
          <Field label="Assinatura (rodapé da mensagem)" value={signature} onChange={setSignature} placeholder="Ex.: Equipe KONTACTO" />

          <Text style={styles.fieldLabel}>Modelo de mensagem (opcional)</Text>
          <TextInput
            value={template}
            onChangeText={setTemplate}
            placeholder={"Deixe vazio para usar o modelo padrão.\nEx.: Olá {primeiro_nome}! Segue seu {tipo} nº {numero}. Valor: {valor}. {assinatura}"}
            placeholderTextColor={colors.muted}
            style={[styles.input, { minHeight: 120, textAlignVertical: "top", paddingTop: 12 }]}
            multiline
            testID="wa-config-template"
          />
          <View style={styles.varsCard}>
            <Text style={styles.varsTitle}>Variáveis disponíveis:</Text>
            <Text style={styles.varsText}>
              {"{cliente}, {primeiro_nome}, {numero}, {tipo}, {data}, {valor}, {status}, {assinatura}"}
            </Text>
            <Text style={styles.varsText}>
              {"OS: {veiculo}, {serie}, {relato}, {servico_executado}, {obs}"}
            </Text>
          </View>

          {msg ? (
            <View style={[styles.msgBox, { backgroundColor: msg.ok ? "#E7F6EC" : "#FDE7E7" }]} testID="wa-config-msg">
              <Ionicons name={msg.ok ? "checkmark-circle" : "alert-circle"} size={18} color={msg.ok ? colors.success : colors.error} />
              <Text style={[styles.msgText, { color: msg.ok ? colors.success : colors.error }]}>{msg.text}</Text>
            </View>
          ) : null}

          <View style={{ height: 40 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { paddingHorizontal: spacing.md, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.2)" },
  saveLabel: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "600" },
  scroll: { padding: spacing.lg },
  rowBetween: { flexDirection: "row", alignItems: "center", backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.md },
  switchLabel: { fontSize: 15, fontWeight: "600", color: colors.onSurface },
  switchHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sectionTitle: { fontSize: 12, fontWeight: "600", color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4, marginTop: spacing.lg, marginBottom: spacing.xs },
  providerRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  providerChip: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  providerChipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  providerText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  docCard: { backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md, borderWidth: 1, borderColor: colors.border },
  docTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  docIntro: { fontSize: 13, color: colors.onSurface, marginBottom: spacing.sm },
  docStep: { flexDirection: "row", gap: 6, marginBottom: 4 },
  docNum: { fontSize: 13, color: colors.brandPrimary, fontWeight: "700" },
  docStepText: { flex: 1, fontSize: 13, color: colors.onSurface, lineHeight: 18 },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4 },
  input: { backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 12, borderWidth: 1, borderColor: colors.border, color: colors.onSurface, fontSize: 14 },
  msgBox: { flexDirection: "row", alignItems: "center", gap: 8, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.md },
  msgText: { flex: 1, fontSize: 13, fontWeight: "500" },
  varsCard: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm, borderWidth: 1, borderColor: colors.border },
  varsTitle: { fontSize: 12, fontWeight: "700", color: colors.brandPrimary, marginBottom: 4 },
  varsText: { fontSize: 12, color: colors.onSurface, lineHeight: 18 },
});
