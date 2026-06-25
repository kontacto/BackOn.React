// Grade de tiles dos módulos da Tela Principal.
import { Pressable, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";

const TILES = [
  { label: "Pedidos", icon: "receipt-outline" as const, route: "/pedidos" as const, perm: "PEDIDO.ABRIR" },
  { label: "Ordem de Serviço", icon: "construct-outline" as const, route: "/os" as const, perm: "OS.ABRIR" },
];

export default function ModuleTiles() {
  const router = useRouter();
  const { can } = usePermissions();
  const visibleTiles = TILES.filter((t) => can(t.perm));

  if (visibleTiles.length === 0) {
    return (
      <View style={styles.tilesGrid}>
        <Text style={{ color: colors.muted, fontSize: 13, padding: 8 }}>
          Nenhum módulo liberado para o seu grupo.
        </Text>
      </View>
    );
  }

  return (
    <View style={styles.tilesGrid}>
      {visibleTiles.map((t) => (
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
