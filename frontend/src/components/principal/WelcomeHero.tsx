// Cartão de boas-vindas (avatar/logo, nome, grupo) da tela principal.
import { Image, Platform, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

type Props = {
  empresa: string;
  logo?: string | null;
  displayName: string;
  nomeGuerra: string | null;
  classe: string | null;
  // Usado quando a Tela Principal mostra este card ao lado do card de
  // Alertas de Estoque (`EstoqueAlertasCard`, mesma linha) em vez de
  // sozinho em largura cheia — o `View` pai (`principal.tsx`) já limita a
  // largura total nesse caso, então aqui só cede espaço (`flex: 1`) em vez
  // de repetir o próprio `maxWidth: 920`. Pedido explícito do usuário,
  // 2026-07-20 ("coloque ao lado desse card").
  compact?: boolean;
};

export default function WelcomeHero({ empresa, logo, displayName, nomeGuerra, classe, compact }: Props) {
  return (
    <View
      style={[styles.hero, Platform.OS === "web" && (compact ? { flex: 1 } : styles.heroWeb)]}
      testID="principal-welcome"
    >
      {logo ? (
        <Image source={{ uri: logo }} style={styles.avatar} resizeMode="cover" testID="principal-logo" />
      ) : (
        <View style={styles.avatar}>
          <Ionicons name="person" size={28} color={colors.onBrandPrimary} />
        </View>
      )}
      <View style={{ flex: 1 }}>
        <Text style={styles.welcome}>Bem-vindo à {empresa}</Text>
        <Text style={styles.heroName} numberOfLines={1}>{displayName || "Usuário"}</Text>
        {nomeGuerra && nomeGuerra !== displayName ? <Text style={styles.heroSub}>@{nomeGuerra}</Text> : null}
        {classe ? <Text style={styles.heroSub} testID="principal-classe">Grupo: {classe}</Text> : null}
      </View>
    </View>
  );
}
