// Tela/bloco exibido quando o usuário não tem permissão de acesso.
import { Text, View, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";

export default function LockedView({
  title = "Acesso restrito",
  message = "Você não tem permissão para acessar este recurso. Fale com o administrador.",
  testID,
}: {
  title?: string;
  message?: string;
  testID?: string;
}) {
  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID={testID ?? "locked-view"}>
      <View style={styles.center}>
        <Ionicons name="lock-closed-outline" size={48} color={colors.muted} />
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.msg}>{message}</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingHorizontal: spacing.xl,
  },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  msg: { fontSize: 14, color: colors.muted, textAlign: "center", lineHeight: 20 },
});
