// Sistema GLOBAL de feedback (erros, avisos, sucesso) exibido SEMPRE no CENTRO da tela.
// Padrão do projeto: toda mensagem de erro/aviso deve usar useFeedback() em vez de
// renderizar texto inline (que pode ficar fora da área visível ao rolar).
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Modal, Platform, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";

type FeedbackType = "error" | "warning" | "success" | "info";

type ConfirmOptions = {
  title?: string;
  confirmText?: string;
  cancelText?: string;
  destructive?: boolean;
};

type ConfirmState = {
  message: string;
  title?: string;
  confirmText: string;
  cancelText: string;
  destructive: boolean;
  onConfirm: () => void;
};

type FeedbackApi = {
  showError: (message: string, title?: string) => void;
  showWarning: (message: string, title?: string) => void;
  showSuccess: (message: string, title?: string) => void;
  showInfo: (message: string, title?: string) => void;
  hide: () => void;
  // Diálogo de confirmação (Sim/Não) centralizado, funciona igual em web e
  // mobile — NUNCA usar `Alert.alert` do react-native pra confirmação:
  // no react-native-web ele é um no-op silencioso (Alert.alert = função
  // vazia), então o botão simplesmente parece não fazer nada no browser.
  showConfirm: (message: string, onConfirm: () => void, options?: ConfirmOptions) => void;
};

const FeedbackContext = createContext<FeedbackApi | null>(null);

const META: Record<FeedbackType, { icon: keyof typeof Ionicons.glyphMap; color: string; title: string }> = {
  error: { icon: "alert-circle", color: colors.error, title: "Erro" },
  warning: { icon: "warning", color: "#E6A23C", title: "Atenção" },
  success: { icon: "checkmark-circle", color: "#2E9E5B", title: "Sucesso" },
  info: { icon: "information-circle", color: colors.brandPrimary, title: "Aviso" },
};

export function FeedbackProvider({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  const [type, setType] = useState<FeedbackType>("info");
  const [message, setMessage] = useState("");
  const [title, setTitle] = useState<string | undefined>(undefined);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [confirm, setConfirm] = useState<ConfirmState | null>(null);

  const clearTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  };

  const hide = useCallback(() => {
    clearTimer();
    setVisible(false);
  }, []);

  const notify = useCallback((t: FeedbackType, msg: string, ttl?: string) => {
    clearTimer();
    setType(t);
    setMessage(msg);
    setTitle(ttl);
    setVisible(true);
    // Sucesso/aviso informativo fecham sozinhos; erro/atenção exigem confirmação.
    if (t === "success" || t === "info") {
      timerRef.current = setTimeout(() => setVisible(false), 2600);
    }
  }, []);

  useEffect(() => () => clearTimer(), []);

  const showConfirm = useCallback((msg: string, onConfirm: () => void, options?: ConfirmOptions) => {
    setConfirm({
      message: msg,
      title: options?.title,
      confirmText: options?.confirmText || "Confirmar",
      cancelText: options?.cancelText || "Cancelar",
      destructive: options?.destructive || false,
      onConfirm,
    });
  }, []);

  const hideConfirm = useCallback(() => setConfirm(null), []);

  const api: FeedbackApi = {
    showError: useCallback((m, t) => notify("error", m, t), [notify]),
    showWarning: useCallback((m, t) => notify("warning", m, t), [notify]),
    showSuccess: useCallback((m, t) => notify("success", m, t), [notify]),
    showInfo: useCallback((m, t) => notify("info", m, t), [notify]),
    hide,
    showConfirm,
  };

  const meta = META[type];

  return (
    <FeedbackContext.Provider value={api}>
      {children}
      {visible ? (
        // Renderizado condicionalmente (não `<Modal visible={visible}>` sempre
        // montado) de propósito: no react-native-web, o Modal cria seu <div>
        // de portal (anexado a document.body) assim que o COMPONENTE MONTA,
        // não quando `visible` vira true — e não tem z-index próprio, então
        // quem manda é a ordem de inserção no DOM. Como o FeedbackProvider
        // fica montado desde o boot do app (bem antes de qualquer Modal local
        // de tela), seu portal sempre nascia primeiro no <body> e ficava por
        // baixo de modais de tela abertos depois (ex.: "Editar Taxa" em
        // taxas.tsx, `EspecialidadesCadastroModal` em funcionario-completo).
        // Só montando o <Modal> aqui quando `visible` é true, o portal nasce
        // na hora do alerta — sempre depois de qualquer modal de tela já
        // aberta — e por isso sempre por cima. Bug sistêmico, não só de Taxas.
        <Modal visible transparent animationType="fade" onRequestClose={hide}>
          <Pressable style={styles.backdrop} onPress={hide}>
            <Pressable style={styles.card} onPress={(e) => e.stopPropagation()} testID="feedback-card">
              <Ionicons name={meta.icon} size={44} color={meta.color} />
              <Text style={styles.title}>{title || meta.title}</Text>
              <Text style={styles.message}>{message}</Text>
              <Pressable
                onPress={hide}
                style={({ pressed }) => [styles.btn, { backgroundColor: meta.color }, pressed && { opacity: 0.85 }]}
                testID="feedback-ok"
              >
                <Text style={styles.btnText}>OK</Text>
              </Pressable>
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}
      {confirm ? (
        // Mesmo padrão de montagem condicional do alerta acima (z-index).
        <Modal visible transparent animationType="fade" onRequestClose={hideConfirm}>
          <Pressable style={styles.backdrop} onPress={hideConfirm}>
            <Pressable style={styles.card} onPress={(e) => e.stopPropagation()} testID="feedback-confirm-card">
              <Ionicons
                name={confirm.destructive ? "alert-circle" : "help-circle"}
                size={44}
                color={confirm.destructive ? colors.error : colors.brandPrimary}
              />
              {confirm.title ? <Text style={styles.title}>{confirm.title}</Text> : null}
              <Text style={styles.message}>{confirm.message}</Text>
              <View style={styles.confirmBtnRow}>
                <Pressable
                  onPress={hideConfirm}
                  style={({ pressed }) => [styles.confirmBtn, styles.confirmBtnCancel, pressed && { opacity: 0.85 }]}
                  testID="feedback-confirm-cancel"
                >
                  <Text style={styles.confirmBtnCancelText}>{confirm.cancelText}</Text>
                </Pressable>
                <Pressable
                  onPress={() => {
                    const onConfirm = confirm.onConfirm;
                    setConfirm(null);
                    onConfirm();
                  }}
                  style={({ pressed }) => [
                    styles.confirmBtn,
                    { backgroundColor: confirm.destructive ? colors.error : colors.brandPrimary },
                    pressed && { opacity: 0.85 },
                  ]}
                  testID="feedback-confirm-ok"
                >
                  <Text style={styles.btnText}>{confirm.confirmText}</Text>
                </Pressable>
              </View>
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}
    </FeedbackContext.Provider>
  );
}

export function useFeedback(): FeedbackApi {
  const ctx = useContext(FeedbackContext);
  if (!ctx) {
    throw new Error("useFeedback deve ser usado dentro de <FeedbackProvider>.");
  }
  return ctx;
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.45)",
    alignItems: "center",
    justifyContent: "center",
    padding: spacing.xl,
  },
  card: {
    width: "100%",
    maxWidth: 360,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: "center",
    gap: spacing.sm,
    ...Platform.select({
      web: { boxShadow: "0 6px 16px rgba(0, 0, 0, 0.2)" },
      default: {
        shadowColor: "#000",
        shadowOpacity: 0.2,
        shadowRadius: 16,
        shadowOffset: { width: 0, height: 6 },
        elevation: 8,
      },
    }),
  },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: spacing.xs },
  message: { fontSize: 15, color: colors.onSurface, textAlign: "center", lineHeight: 21 },
  btn: {
    marginTop: spacing.md,
    minWidth: 120,
    borderRadius: radius.pill,
    paddingVertical: 12,
    alignItems: "center",
  },
  btnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  confirmBtnRow: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.md, width: "100%" },
  confirmBtn: {
    flex: 1,
    borderRadius: radius.pill,
    paddingVertical: 12,
    alignItems: "center",
  },
  confirmBtnCancel: { backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border },
  confirmBtnCancelText: { color: colors.onSurface, fontWeight: "600", fontSize: 15 },
});
