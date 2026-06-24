// Barra de cabeçalho da tela de pedido (voltar + título + gravar).
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

type Props = {
  title: string;
  saving: boolean;
  onBack: () => void;
  onSave: () => void;
};

export default function PedidoHeader({ title, saving, onBack, onSave }: Props) {
  return (
    <View style={styles.header}>
      <Pressable onPress={onBack} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12}>
        <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
      </Pressable>
      <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
      <Pressable
        onPress={onSave}
        disabled={saving}
        style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]}
        hitSlop={8}
        testID="pedido-form-save"
      >
        {saving ? (
          <ActivityIndicator color={colors.onBrandPrimary} size="small" />
        ) : (
          <>
            <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.saveLabel}>Gravar</Text>
          </>
        )}
      </Pressable>
    </View>
  );
}
