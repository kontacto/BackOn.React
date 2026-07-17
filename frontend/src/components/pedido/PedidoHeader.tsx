// Barra de cabeçalho da tela de pedido (voltar + título + gravar).
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

type Props = {
  title: string;
  saving: boolean;
  onBack: () => void;
  onSave: () => void;
  canSave?: boolean;
  // Conteúdo extra ao lado do título (ex.: seletor de Vendedor) — ainda
  // dentro da barra, na cor de fundo da barra.
  titleExtra?: React.ReactNode;
};

export default function PedidoHeader({ title, saving, onBack, onSave, canSave = true, titleExtra }: Props) {
  return (
    <View style={styles.header}>
      <Pressable onPress={onBack} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12}>
        <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
      </Pressable>
      <Text style={styles.headerTitle} numberOfLines={1}>{title}</Text>
      {titleExtra}
      {canSave ? (
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
      ) : (
        <View style={{ width: 40 }} />
      )}
    </View>
  );
}
