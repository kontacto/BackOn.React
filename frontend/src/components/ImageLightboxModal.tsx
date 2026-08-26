import { Image, Platform, Pressable, StyleSheet, useWindowDimensions } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import { colors, radius, spacing } from "@/src/theme/colors";

// Regra [GLOBAL] 2026-08-26, user-directed: clicar em QUALQUER imagem de
// produto (busca/pré-venda, item do pedido, confirmar item, cadastro de
// fotos, identidade do produto — "onde exibir a imagem do produto") abre
// essa mesma imagem ampliada. Um componente único e reutilizável em vez de
// reimplementar em cada tela — ver CLAUDE.md > "Clicar em imagem de
// produto amplia (Lightbox)".

type Props = {
  visible: boolean;
  onClose: () => void;
  // null = nada pra mostrar (chamador ainda não resolveu a URL, ou
  // simplesmente não abriu) — o modal não renderiza a imagem nesse caso.
  imageUrl: string | null;
};

export default function ImageLightboxModal({ visible, onClose, imageUrl }: Props) {
  const { width, height } = useWindowDimensions();
  if (!imageUrl) return null;
  return (
    <AppModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.backdrop} onPress={onClose} testID="image-lightbox-backdrop">
        <Pressable style={styles.imageWrap} onPress={(e) => e.stopPropagation()}>
          <Pressable style={styles.closeBtn} onPress={onClose} hitSlop={10} testID="image-lightbox-close">
            <Ionicons name="close" size={24} color="#fff" />
          </Pressable>
          {Platform.OS === "web" ? (
            // eslint-disable-next-line jsx-a11y/alt-text
            <img
              src={imageUrl}
              style={{ maxWidth: "90vw", maxHeight: "85vh", objectFit: "contain", borderRadius: radius.md }}
            />
          ) : (
            <Image
              source={{ uri: imageUrl }}
              style={{ width: width * 0.9, height: height * 0.7, borderRadius: radius.md }}
              resizeMode="contain"
            />
          )}
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1, backgroundColor: "rgba(0,0,0,0.8)", alignItems: "center", justifyContent: "center",
    padding: spacing.xl,
  },
  imageWrap: { position: "relative", alignItems: "center", justifyContent: "center" },
  closeBtn: {
    position: "absolute", top: -40, right: -8, width: 32, height: 32, borderRadius: 16,
    backgroundColor: "rgba(255,255,255,0.15)", alignItems: "center", justifyContent: "center",
  },
});
