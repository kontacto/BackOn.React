// Card "Projetos" na Tela Principal — Gestor de Projetos Fase 4 (recurso
// extra, sem equivalente no legado, implementado 2026-08-02 só sob
// confirmação explícita do usuário, mesmo critério já usado antes pro
// card de Alertas de Estoque). Mostra total de Projetos Abertos + saldo a
// faturar agregado, só pra Gerente/Supervisor/Master — mesmo gating
// (`isManagerFuncao`) e mesmo padrão visual (chip 160px, borda esquerda
// colorida) do `EstoqueAlertasCard.tsx`, mas sem a complexidade de cache
// compartilhado/botão "Atualizar": a consulta aqui é barata (2 agregados
// sobre tabelas pequenas), então recarrega junto com o resto do dashboard
// a cada visita, sem precisar do mecanismo de "só 1x por sessão" que o
// card de estoque usa pra evitar repetir um cálculo caro.
import { Platform, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL } from "@/src/utils/format";

export type ResumoProjetos = {
  ativo: boolean;
  total_abertos: number;
  saldo_a_faturar: number;
};

type Props = {
  resumo: ResumoProjetos | null;
  compact?: boolean;
};

const isWeb = Platform.OS === "web";

export default function ProjetosResumoCard({ resumo, compact }: Props) {
  const router = useRouter();
  if (!resumo || !resumo.ativo) return null;

  return (
    <View style={[{ marginBottom: spacing.md }, compact && { flex: 1 }]} testID="principal-projetos-resumo">
      <Pressable
        onPress={() => router.push({ pathname: "/projetos", params: { situacao: "A" } } as never)}
        style={({ pressed }) => [
          {
            width: isWeb ? 160 : undefined,
            minHeight: 76,
            justifyContent: "center",
            backgroundColor: colors.surfaceSecondary,
            borderRadius: radius.md,
            borderWidth: 1,
            borderColor: colors.border,
            borderLeftWidth: 3,
            borderLeftColor: colors.brandPrimary,
            padding: spacing.sm,
          },
          pressed && { opacity: 0.8 },
        ]}
        testID="principal-projetos-resumo-card"
      >
        <View
          style={{
            width: 26, height: 26, borderRadius: radius.sm,
            backgroundColor: colors.surface,
            alignItems: "center", justifyContent: "center", marginBottom: 6,
          }}
        >
          <Ionicons name="briefcase-outline" size={14} color={colors.brandPrimary} />
        </View>
        <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{resumo.total_abertos}</Text>
        <Text style={{ fontSize: 10, fontWeight: "600", color: colors.muted, marginTop: 1 }} numberOfLines={1}>
          Projeto(s) Aberto(s)
        </Text>
        <Text style={{ fontSize: 11, fontWeight: "700", color: colors.warning, marginTop: 4 }} numberOfLines={1}>
          {formatBRL(resumo.saldo_a_faturar)}
        </Text>
        <Text style={{ fontSize: 9, color: colors.muted }} numberOfLines={1}>Saldo a faturar</Text>
      </Pressable>
    </View>
  );
}
