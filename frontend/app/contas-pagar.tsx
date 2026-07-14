import { Platform } from "react-native";

import LockedView from "@/src/components/LockedView";
import ComingSoonScreen from "@/src/components/ComingSoonScreen";

export default function ContasPagarScreen() {
  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contas a Pagar está disponível apenas no web."
        testID="contas-pagar-web-only"
      />
    );
  }

  return (
    <ComingSoonScreen
      title="Contas a Pagar"
      icon="arrow-up-circle-outline"
      message="O módulo de Contas a Pagar está em desenvolvimento e será liberado em breve."
      testID="contas-pagar-screen"
    />
  );
}
