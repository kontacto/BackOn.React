// Botão reutilizável "Entrar com Biometria".
import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors, radius, spacing } from "@/src/theme/colors";

type Props = {
  onPress: () => void;
  busy?: boolean;
  label?: string;
  testID?: string;
};

export default function BiometricButton({ onPress, busy, label = "Entrar com Biometria", testID }: Props) {
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      style={({ pressed }) => [styles.btn, (pressed || busy) && { opacity: 0.7 }]}
      testID={testID || "biometric-login-btn"}
    >
      {busy ? (
        <ActivityIndicator size="small" color={colors.brandPrimary} />
      ) : (
        <Ionicons name="finger-print" size={20} color={colors.brandPrimary} />
      )}
      <Text style={styles.text}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  btn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    borderWidth: 1.5, borderColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 13, marginTop: spacing.md,
  },
  text: { color: colors.brandPrimary, fontWeight: "700", fontSize: 15 },
});
