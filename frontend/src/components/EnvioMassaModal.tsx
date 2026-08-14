// Envio em Massa (WhatsApp/E-mail) — modal reutilizável (pedido explícito
// do usuário, 2026-08-07: "esse recurso de envio vai ser introduzido em
// consulta de clientes entre outros"). Reaproveita o mecanismo já
// existente de envio (WhatsApp document_type=CLI, e-mail SMTP de
// Cobrança) via `POST /api/envio-massa/whatsapp|email` — este componente
// só monta a lista de destinatários + template de mensagem e mostra o
// resultado por destinatário. Usado hoje por Mala Direta e Inatividade de
// Clientes; qualquer outra tela com uma lista de {codigo,nome,email?}
// pode abrir o mesmo modal sem mudança nenhuma aqui.
import { useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import { colors, radius, spacing } from "@/src/theme/colors";

const isCompactWeb = Platform.OS === "web";

export type DestinatarioEnvio = {
  codigo: number; nome: string; email?: string | null; tem_telefone?: boolean;
  tipo?: "cliente" | "fornecedor";
};

type Conn = { servidor: string; banco: string; api: string };

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Conn | null;
  destinatarios: DestinatarioEnvio[];
  canalWhatsapp?: boolean;
  canalEmail?: boolean;
  usuarioId?: number | null;
};

type Resultado = { codigo: number; nome: string; success: boolean; message?: string };

const TEMPLATE_PADRAO_WHATSAPP = "Olá {nome}! Temos novidades especiais pra você. Fale com a gente!";
const TEMPLATE_PADRAO_EMAIL_ASSUNTO = "Novidades para você";
const TEMPLATE_PADRAO_EMAIL_CORPO = "Olá {nome},<br/><br/>Temos novidades especiais pra você. Entre em contato conosco!";

export default function EnvioMassaModal({
  visible, onClose, conn, destinatarios, canalWhatsapp = true, canalEmail = true, usuarioId,
}: Props) {
  const [canal, setCanal] = useState<"whatsapp" | "email">(canalWhatsapp ? "whatsapp" : "email");
  const [mensagem, setMensagem] = useState(TEMPLATE_PADRAO_WHATSAPP);
  const [assunto, setAssunto] = useState(TEMPLATE_PADRAO_EMAIL_ASSUNTO);
  const [corpo, setCorpo] = useState(TEMPLATE_PADRAO_EMAIL_CORPO);
  const [enviando, setEnviando] = useState(false);
  const [resultados, setResultados] = useState<Resultado[] | null>(null);

  const elegiveis = useMemo(() => {
    if (canal === "whatsapp") return destinatarios.filter((d) => d.tem_telefone !== false);
    return destinatarios.filter((d) => !!d.email);
  }, [destinatarios, canal]);

  const fechar = () => {
    setResultados(null);
    onClose();
  };

  const enviar = async () => {
    if (!conn || elegiveis.length === 0) return;
    setEnviando(true);
    setResultados(null);
    try {
      const base = conn.api.replace(/\/+$/, "");
      if (canal === "whatsapp") {
        const r = await fetch(`${base}/api/envio-massa/whatsapp`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: conn.servidor, banco: conn.banco,
            destinatarios: elegiveis.map((d) => ({ codigo: d.codigo, nome: d.nome })),
            mensagem, usuario: usuarioId ?? null,
          }),
        });
        const j = await r.json();
        setResultados(j.resultados || []);
      } else {
        const r = await fetch(`${base}/api/envio-massa/email`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: conn.servidor, banco: conn.banco,
            destinatarios: elegiveis.map((d) => ({ codigo: d.codigo, nome: d.nome, email: d.email })),
            assunto, corpo, usuario: usuarioId ?? null,
          }),
        });
        const j = await r.json();
        setResultados(j.resultados || []);
      }
    } catch (e) {
      setResultados([{ codigo: 0, nome: "", success: false, message: e instanceof Error ? e.message : "Falha de conexão." }]);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={fechar}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={fechar}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Enviar em Massa</Text>
            <Pressable onPress={fechar} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {!resultados ? (
            <ScrollView>
              <Text style={styles.subMeta}>{destinatarios.length} destinatário(s) selecionado(s)</Text>

              <View style={styles.chipRow}>
                {canalWhatsapp ? (
                  <Pressable onPress={() => setCanal("whatsapp")} style={[styles.chip, canal === "whatsapp" && styles.chipSel]} testID="envmassa-canal-whatsapp">
                    <Ionicons name="logo-whatsapp" size={14} color={canal === "whatsapp" ? colors.onBrandPrimary : colors.onSurface} />
                    <Text style={[styles.chipText, canal === "whatsapp" && styles.chipTextSel]}>WhatsApp</Text>
                  </Pressable>
                ) : null}
                {canalEmail ? (
                  <Pressable onPress={() => setCanal("email")} style={[styles.chip, canal === "email" && styles.chipSel]} testID="envmassa-canal-email">
                    <Ionicons name="mail-outline" size={14} color={canal === "email" ? colors.onBrandPrimary : colors.onSurface} />
                    <Text style={[styles.chipText, canal === "email" && styles.chipTextSel]}>E-mail</Text>
                  </Pressable>
                ) : null}
              </View>

              <Text style={styles.subMeta}>
                {elegiveis.length} de {destinatarios.length} têm {canal === "whatsapp" ? "telefone" : "e-mail"} cadastrado
              </Text>

              {canal === "whatsapp" ? (
                <>
                  <Text style={styles.fieldLabel}>Mensagem (use {"{nome}"} pra personalizar)</Text>
                  <TextInput
                    value={mensagem} onChangeText={setMensagem} multiline numberOfLines={4}
                    style={[styles.input, styles.textArea]} testID="envmassa-mensagem"
                  />
                </>
              ) : (
                <>
                  <Text style={styles.fieldLabel}>Assunto</Text>
                  <TextInput value={assunto} onChangeText={setAssunto} style={styles.input} testID="envmassa-assunto" />
                  <Text style={styles.fieldLabel}>Corpo (HTML simples, use {"{nome}"} pra personalizar)</Text>
                  <TextInput
                    value={corpo} onChangeText={setCorpo} multiline numberOfLines={5}
                    style={[styles.input, styles.textArea]} testID="envmassa-corpo"
                  />
                </>
              )}

              <Pressable
                onPress={enviar} disabled={enviando || elegiveis.length === 0}
                style={[styles.sendBtn, (enviando || elegiveis.length === 0) && { opacity: 0.6 }]}
                testID="envmassa-enviar"
              >
                {enviando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                  <>
                    <Ionicons name="send-outline" size={15} color={colors.onBrandPrimary} />
                    <Text style={styles.sendBtnText}>Enviar para {elegiveis.length}</Text>
                  </>
                )}
              </Pressable>
            </ScrollView>
          ) : (
            <ScrollView>
              <Text style={styles.subMeta}>
                {resultados.filter((r) => r.success).length} enviado(s), {resultados.filter((r) => !r.success).length} falha(s)
              </Text>
              {resultados.map((r, idx) => (
                <View key={idx} style={styles.resultRow}>
                  <Ionicons name={r.success ? "checkmark-circle" : "close-circle"} size={16} color={r.success ? colors.success : colors.error} />
                  <Text style={styles.resultNome} numberOfLines={1}>{r.nome || `#${r.codigo}`}</Text>
                  {!r.success ? <Text style={styles.resultMsg} numberOfLines={1}>{r.message}</Text> : null}
                </View>
              ))}
              <Pressable onPress={fechar} style={styles.sendBtn} testID="envmassa-fechar">
                <Text style={styles.sendBtnText}>Concluir</Text>
              </Pressable>
            </ScrollView>
          )}
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  bgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  card: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  cardWebCompact: {
    width: "100%", maxWidth: 480, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  subMeta: { fontSize: 12, color: colors.muted, marginBottom: spacing.sm },
  chipRow: { flexDirection: "row", gap: spacing.sm, marginBottom: spacing.sm },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6, height: 34, paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
  },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipTextSel: { color: colors.onBrandPrimary },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, marginTop: spacing.sm, fontWeight: "500" },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  sendBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6,
    height: 40, borderRadius: radius.pill, backgroundColor: colors.brandPrimary, marginTop: spacing.md,
  },
  sendBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13 },
  resultRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: colors.border },
  resultNome: { fontSize: 12, color: colors.onSurface, flex: 1 },
  resultMsg: { fontSize: 11, color: colors.error, flexShrink: 1 },
});
