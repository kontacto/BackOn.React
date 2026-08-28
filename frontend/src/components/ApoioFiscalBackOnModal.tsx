// Apoio Fiscal BackOn — tradução em tempo real de uma rejeição fiscal
// (SEFAZ/ADN) pro lojista, em linguagem sem jargão. Aberto sempre que uma
// resposta de emissão/cancelamento fiscal traz a chave `apoio_fiscal`
// (ver backend/services/apoio_fiscal_service.py e
// frontend/src/utils/apoioFiscal.ts::showApoioFiscalError).
//
// Papel "Apoio Fisco" do Protocolo Gauntlet (CLAUDE.md): formato de 2
// níveis (explicação curta sempre visível, detalhada só se pedido) — nunca
// despeja o texto técnico completo de cara, mesmo já validado por Kelvin.
//
// Tier de modal "confirmação pontual" (360-480px, ver CLAUDE.md > "Padrões
// de UI" > 1) — é sobre UM evento (uma rejeição), não uma lista/busca.
import { useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as ps } from "@/src/components/pedido/styles";

const isWeb = Platform.OS === "web";

export type ApoioFiscalInfo = {
  titulo: string;
  explicacao_curta: string;
  explicacao_detalhada: string;
  acao_usuario: string | null;
  notificado_suporte?: { email: boolean; whatsapp: boolean };
};

type Props = {
  visible: boolean;
  onClose: () => void;
  info: ApoioFiscalInfo | null;
};

export default function ApoioFiscalBackOnModal({ visible, onClose, info }: Props) {
  const [expandido, setExpandido] = useState(false);
  if (!visible || !info) return null;

  return (
    <View
      style={{
        position: "absolute", top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: "rgba(0,0,0,0.45)",
        alignItems: "center", justifyContent: isWeb ? "center" : "flex-end",
        paddingHorizontal: isWeb ? spacing.xl : 0,
        zIndex: 1000,
      }}
    >
      <Pressable
        style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 }}
        onPress={onClose}
      />
      <View style={[ps.modalCard, isWeb && ps.modalCardWebCompactNarrow]}>
        <View style={ps.modalHeader}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flex: 1 }}>
            <Ionicons name="shield-checkmark-outline" size={20} color={colors.brandPrimary} />
            <Text style={ps.modalTitle}>Apoio Fiscal BackOn</Text>
          </View>
          <Pressable onPress={onClose} hitSlop={8} testID="apoio-fiscal-backon-fechar">
            <Ionicons name="close" size={22} color={colors.muted} />
          </Pressable>
        </View>

        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, marginBottom: 6 }}>
          {info.titulo}
        </Text>
        <Text style={{ fontSize: 13, color: colors.onSurface, lineHeight: 19, marginBottom: spacing.sm }}>
          {info.explicacao_curta}
        </Text>

        {!expandido ? (
          <Pressable onPress={() => setExpandido(true)} testID="apoio-fiscal-backon-entender-melhor">
            <Text style={{ fontSize: 13, color: colors.brandPrimary, fontWeight: "600" }}>
              Quero entender melhor
            </Text>
          </Pressable>
        ) : (
          <View style={{ gap: spacing.sm }}>
            <Text style={{ fontSize: 13, color: colors.muted, lineHeight: 19 }}>
              {info.explicacao_detalhada}
            </Text>
            {info.acao_usuario ? (
              <View
                style={{
                  backgroundColor: colors.brandTertiary, borderRadius: radius.md,
                  padding: spacing.sm,
                }}
              >
                <Text style={{ fontSize: 12, fontWeight: "600", color: colors.onSurface, marginBottom: 2 }}>
                  O que você pode tentar:
                </Text>
                <Text style={{ fontSize: 12, color: colors.onSurface, lineHeight: 17 }}>
                  {info.acao_usuario}
                </Text>
              </View>
            ) : null}
          </View>
        )}

        <Text style={{ fontSize: 11, color: colors.muted, marginTop: spacing.md }}>
          Nosso suporte já foi avisado automaticamente sobre esta rejeição.
        </Text>

        <Pressable
          onPress={onClose}
          style={[ps.primaryBtn, { marginTop: spacing.md }]}
          testID="apoio-fiscal-backon-ok"
        >
          <Text style={ps.primaryBtnText}>Entendi</Text>
        </Pressable>
      </View>
    </View>
  );
}
