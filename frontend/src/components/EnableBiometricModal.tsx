// Modal de ativação pós-login: "Deseja habilitar login por biometria neste dispositivo?"
import { ActivityIndicator, Modal, Pressable, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";

type Props = {
  visible: boolean;
  busy?: boolean;
  onAccept: () => void;
  onDecline: () => void;
};

export default function EnableBiometricModal({ visible, busy, onAccept, onDecline }: Props) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onDecline}>
      <View style={styles.bg}>
        <View style={styles.card} testID="enable-biometric-modal">
          <Ionicons name="finger-print" size={40} color={colors.brandPrimary} style={{ alignSelf: "center" }} />
          <Text style={styles.title}>Login por biometria</Text>
          <Text style={styles.msg}>Deseja habilitar login por biometria neste dispositivo?</Text>
          <Pressable onPress={onAccept} disabled={busy} style={[styles.primary, busy && { opacity: 0.6 }]} testID="enable-biometric-accept">
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.primaryText}>Habilitar</Text>}
          </Pressable>
          <Pressable onPress={onDecline} disabled={busy} style={styles.secondary} testID="enable-biometric-decline">
            <Text style={styles.secondaryText}>Agora não</Text>
          </Pressable>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", padding: spacing.lg },
  card: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  title: { fontSize: 17, fontWeight: "700", color: colors.onSurface, textAlign: "center" },
  msg: { fontSize: 14, color: colors.muted, textAlign: "center", marginBottom: spacing.sm },
  primary: { backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 14, alignItems: "center" },
  primaryText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  secondary: { paddingVertical: 12, alignItems: "center" },
  secondaryText: { color: colors.muted, fontWeight: "600", fontSize: 14 },
});
