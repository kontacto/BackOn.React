// Sistema GLOBAL de feedback (erros, avisos, sucesso) exibido SEMPRE no CENTRO da tela.
// Padrão do projeto: toda mensagem de erro/aviso deve usar useFeedback() em vez de
// renderizar texto inline (que pode ficar fora da área visível ao rolar).
import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing } from "@/src/theme/colors";

type FeedbackType = "error" | "warning" | "success" | "info";

type FeedbackApi = {
  showError: (message: string, title?: string) => void;
  showWarning: (message: string, title?: string) => void;
  showSuccess: (message: string, title?: string) => void;
  showInfo: (message: string, title?: string) => void;
  hide: () => void;
};

const FeedbackContext = createContext<FeedbackApi | null>(null);

const META: Record<FeedbackType, { icon: keyof typeof Ionicons.glyphMap; color: string; title: string }> = {
  error: { icon: "alert-circle", color: colors.danger, title: "Erro" },
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

  const api: FeedbackApi = {
    showError: useCallback((m, t) => notify("error", m, t), [notify]),
    showWarning: useCallback((m, t) => notify("warning", m, t), [notify]),
    showSuccess: useCallback((m, t) => notify("success", m, t), [notify]),
    showInfo: useCallback((m, t) => notify("info", m, t), [notify]),
    hide,
  };

  const meta = META[type];

  return (
    <FeedbackContext.Provider value={api}>
      {children}
      <Modal visible={visible} transparent animationType="fade" onRequestClose={hide}>
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
    shadowColor: "#000",
    shadowOpacity: 0.2,
    shadowRadius: 16,
    shadowOffset: { width: 0, height: 6 },
    elevation: 8,
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
});
