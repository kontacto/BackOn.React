// Grade de tiles dos módulos (Clientes, Produtos & Serviços, Pedidos).
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { styles } from "./styles";

const TILES = [
  { label: "Clientes", icon: "people-outline" as const, route: "/clientes" as const },
  { label: "Produtos & Serviços", icon: "cube-outline" as const, route: "/produtos" as const },
  { label: "Pedidos", icon: "receipt-outline" as const, route: "/pedidos" as const },
];

export default function ModuleTiles() {
  const router = useRouter();
  return (
    <View style={styles.tilesGrid}>
      {TILES.map((t) => (
        <Pressable
          key={t.label}
          onPress={() => t.route && router.push(t.route)}
          disabled={!t.route}
          style={({ pressed }) => [styles.tile, pressed && t.route && { opacity: 0.8 }]}
          testID={`principal-tile-${t.label.toLowerCase()}`}
        >
          <View style={styles.tileIcon}>
            <Ionicons name={t.icon} size={22} color={colors.brandPrimary} />
          </View>
          <Text style={styles.tileLabel}>{t.label}</Text>
          <Text style={styles.tileHint}>{t.route ? "Abrir" : "Em breve"}</Text>
        </Pressable>
      ))}
    </View>
  );
}
