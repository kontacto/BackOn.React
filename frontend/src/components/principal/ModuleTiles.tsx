// Grade de tiles dos módulos da Tela Principal.
import { Platform, Pressable, Text, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { useRouter } from "expo-router";

import { colors } from "@/src/theme/colors";
import { usePermissions } from "@/src/permissions";
import { styles } from "./styles";

// Pedido/O.S. Mobile x Geral(Completo) são mutuamente exclusivos na árvore
// de permissões (ver permissoes.tsx > EXCLUSIVE_PAIRS). Nenhuma das duas
// listas é compartilhada entre as variantes: quem tem PEDIDO.ABRIR (Bar) vai
// pra `/pedidos` (exclusiva do Bar), quem só tem PEDIDO_COMP.ABRIR (Geral)
// vai pra `/pedido-lista`; mesma lógica pra O.S. desde 2026-07-31 — OS.ABRIR
// (Mobile) vai pra `/os`, OS_COMP.ABRIR (Completa) vai pra `/os-lista`. Ver
// CLAUDE.md > "Transações Screens Strategy".
const TILES = [
  {
    label: "Pedidos",
    icon: "receipt-outline" as const,
    perms: ["PEDIDO.ABRIR", "PEDIDO_COMP.ABRIR"],
    route: (can: (p: string) => boolean) => (can("PEDIDO.ABRIR") ? "/pedidos" : "/pedido-lista"),
  },
  {
    label: "Ordem de Serviço",
    icon: "construct-outline" as const,
    perms: ["OS.ABRIR", "OS_COMP.ABRIR"],
    route: (can: (p: string) => boolean) => (can("OS.ABRIR") ? "/os" : "/os-lista"),
  },
];

type Props = {
  // Usado quando a Tela Principal mostra este grid ao lado do card de
  // Alertas de Estoque (mesma linha) em vez de sozinho em largura cheia —
  // pedido explícito do usuário, 2026-07-20 ("colocar o card ao lado do
  // card de Pedidos"). Nesse modo, o grid não aplica seu próprio
  // `width:100%/maxWidth:920` (o `View` pai, em `principal.tsx`, já
  // decide a largura total da linha) — só encolhe pro tamanho do
  // conteúdo, deixando espaço pro card ao lado.
  compact?: boolean;
};

export default function ModuleTiles({ compact }: Props) {
  const router = useRouter();
  const { can } = usePermissions();
  const visibleTiles = TILES.filter((t) => t.perms.some((p) => can(p)))
    .map((t) => ({ ...t, route: t.route(can) }))
    .sort((a, b) => a.label.localeCompare(b.label, "pt-BR"));

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
    <View style={[styles.tilesGrid, Platform.OS === "web" && !compact && styles.tilesGridWeb]}>
      {visibleTiles.map((t) => (
        <Pressable
          key={t.label}
          onPress={() => t.route && router.push(t.route)}
          disabled={!t.route}
          style={({ pressed }) => [
            styles.tile,
            // Formatação reduzida (pedido explícito do usuário, 2026-07-20:
            // "diminua esses cards... para diminuir sua largura") — tile
            // com largura fixa e compacta em vez de ~metade da tela, pra
            // caber mais de um por linha e não esticar sem necessidade
            // (mesmo princípio de "Field Width Standard"/"Compact Size
            // Variant" do CLAUDE.md, aplicado aqui aos tiles de módulo).
            Platform.OS === "web" && styles.tileWeb,
            pressed && t.route && { opacity: 0.8 },
          ]}
          testID={`principal-tile-${t.label.toLowerCase()}`}
        >
          <View style={[styles.tileIcon, Platform.OS === "web" && styles.tileIconWeb]}>
            <Ionicons name={t.icon} size={Platform.OS === "web" ? 16 : 22} color={colors.brandPrimary} />
          </View>
          <Text style={[styles.tileLabel, Platform.OS === "web" && styles.tileLabelWeb]} numberOfLines={1}>{t.label}</Text>
          <Text style={[styles.tileHint, Platform.OS === "web" && styles.tileHintWeb]}>{t.route ? "Abrir" : "Em breve"}</Text>
        </Pressable>
      ))}
    </View>
  );
}
