// Toast leve, local à tela (não bloqueia interação, some sozinho) — usado por
// pedido-form.tsx/pedido-completo.tsx. Renderizado dentro de um <Modal> só pra
// herdar o portal do react-native-web (document.body) e sempre desenhar por
// cima de qualquer <Modal> de tela já aberto (ex.: AddItemModal) — mesma causa
// raiz já documentada em FeedbackProvider.tsx: o Modal do react-native-web não
// tem z-index próprio, quem decide o empilhamento é a ordem de inserção no
// DOM; como antes o toast era um <View> comum (nunca portalizado), ficava
// sempre atrás de qualquer Modal aberto. Montar o <Modal> só quando há toast
// garante que o portal nasce depois de qualquer modal de tela já aberto.
import { Modal, Text, View } from "react-native";
import { colors } from "@/src/theme/colors";
import { styles } from "./styles";
import { ToastTone } from "./types";

type Props = {
  toast: { msg: string; tone: ToastTone } | null;
  testID?: string;
};

export default function ScreenToast({ toast, testID }: Props) {
  if (!toast) return null;
  return (
    <Modal visible transparent animationType="fade">
      <View style={styles.toastWrap} pointerEvents="box-none">
        <View
          style={[
            styles.toast,
            toast.tone === "error" && { backgroundColor: colors.error },
            toast.tone === "success" && { backgroundColor: colors.success },
          ]}
          testID={testID}
        >
          <Text style={styles.toastText}>{toast.msg}</Text>
        </View>
      </View>
    </Modal>
  );
}
