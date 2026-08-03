// Tela/bloco exibido quando o usuário não tem permissão de acesso.
//
// Sempre mostra um jeito de voltar (2026-07-21, achado real do usuário:
// telas de rota isolada — não dentro de `(tabs)` — que gateiam acesso com
// `if (!can(...)) return <LockedView/>` nunca chegam a renderizar seu
// próprio cabeçalho/botão Voltar, prendendo o usuário aqui sem saída no
// web). `router.back()` só aparece quando `canGoBack()` confirma que há
// pra onde voltar (evita um botão que não faz nada em telas que já são a
// raiz da pilha).
import { Pressable, Text, View, StyleSheet } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";

export default function LockedView({
  title = "Acesso restrito",
  message = "Você não tem permissão para acessar este recurso. Fale com o administrador.",
  testID,
}: {
  title?: string;
  message?: string;
  testID?: string;
}) {
  const router = useRouter();
  const podeVoltar = router.canGoBack();
  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID={testID ?? "locked-view"}>
      <View style={styles.center}>
        <Ionicons name="lock-closed-outline" size={48} color={colors.muted} />
        <Text style={styles.title}>{title}</Text>
        <Text style={styles.msg}>{message}</Text>
        {podeVoltar ? (
          <Pressable onPress={() => router.back()} style={styles.backBtn} testID="locked-view-voltar">
            <Ionicons name="chevron-back" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.backLabel}>Voltar</Text>
          </Pressable>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    gap: 12,
    paddingHorizontal: spacing.xl,
  },
  title: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  msg: { fontSize: 14, color: colors.muted, textAlign: "center", lineHeight: 20 },
  backBtn: {
    flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.md,
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: 8,
    backgroundColor: colors.brandPrimary,
  },
  backLabel: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 14 },
});
