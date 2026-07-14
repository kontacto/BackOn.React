// Grade de tiles dos módulos da Tela Principal.
import { Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";

// Pedido/O.S. Mobile x Completo são mutuamente exclusivos na árvore de
// permissões (ver permissoes.tsx > EXCLUSIVE_PAIRS), mas a LISTA
// (/pedidos, /os) é a mesma tela pras duas variantes — só o clique num
// item específico é que ainda não faz nada pra quem só tem a variante
// Completo, até essa tela existir (ver pedidos.tsx/os.tsx). Ver CLAUDE.md
// > "Transações Screens Strategy".
const TILES = [
  {
    label: "Pedidos",
    icon: "receipt-outline" as const,
    perms: ["PEDIDO.ABRIR", "PEDIDO_COMP.ABRIR"],
    route: "/pedidos" as const,
  },
  {
    label: "Ordem de Serviço",
    icon: "construct-outline" as const,
    perms: ["OS.ABRIR", "OS_COMP.ABRIR"],
    route: "/os" as const,
  },
];

export default function ModuleTiles() {
  const router = useRouter();
  const { can } = usePermissions();
  const visibleTiles = TILES.filter((t) => t.perms.some((p) => can(p))).sort((a, b) =>
    a.label.localeCompare(b.label, "pt-BR")
  );

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
    <View style={[styles.tilesGrid, Platform.OS === "web" && styles.tilesGridWeb]}>
      {visibleTiles.map((t) => (
        <Pressable
          key={t.label}
          onPress={() => t.route && router.push(t.route)}
          disabled={!t.route}
          style={({ pressed }) => [
            styles.tile,
            Platform.OS === "web" && { width: "calc(50% - 10px)", minHeight: 104 },
            pressed && t.route && { opacity: 0.8 },
          ]}
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
