import type { ReactNode } from "react";
import { Modal, Platform, StyleSheet, View, type ModalProps } from "react-native";

type AppModalProps = Pick<ModalProps, "visible" | "transparent" | "animationType" | "onRequestClose"> & {
  children: ReactNode;
};

// react-native-windows' <Modal> opens a real separate OS window sized to fit
// its content (WindowsModalHostViewComponentView.cpp: AdjustWindowSize),
// unlike the full-screen overlay every other platform gives you -- content
// built assuming a full-bleed backdrop (StyleSheet.absoluteFillObject,
// flex: 1 centering, bottom sheets) collapses to a narrow content-sized
// column instead. On Windows this renders as a plain absolutely-positioned
// overlay View on top of the current screen instead, which behaves like the
// full-screen overlay the content already expects.
export function AppModal({ visible, transparent, animationType, onRequestClose, children }: AppModalProps) {
  if (Platform.OS === "windows") {
    if (!visible) return null;
    return (
      <View style={styles.overlay} pointerEvents="box-none">
        {children}
      </View>
    );
  }

  return (
    <Modal visible={visible} transparent={transparent} animationType={animationType} onRequestClose={onRequestClose}>
      {children}
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    zIndex: 1000,
    elevation: 1000,
  },
});
