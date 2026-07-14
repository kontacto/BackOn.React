import { Platform } from "react-native";

import LockedView from "@/src/components/LockedView";
import ComingSoonScreen from "@/src/components/ComingSoonScreen";

export default function ContasReceberScreen() {
  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contas a Receber está disponível apenas no web."
        testID="contas-receber-web-only"
      />
    );
  }

  return (
    <ComingSoonScreen
      title="Contas a Receber"
      icon="arrow-down-circle-outline"
      message="O módulo de Contas a Receber está em desenvolvimento e será liberado em breve."
      testID="contas-receber-screen"
    />
  );
}
