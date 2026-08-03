// Card de alertas de estoque na Tela Principal — só pra Gerente/Supervisor/
// Master (`isManagerFuncao`), só quando pelo menos um dos 3 toggles de
// Controle do Sistema > aba Diversos (Alertar produtos de Estoque Mínimo/
// Ressuprimento/Zerado ou Negativo) está ligado E tem produto de fato
// naquela situação (ou a Curva ABC está desatualizada — ver
// `curva_abc_desatualizada` abaixo, mesmo sem nenhum alerta ativo).
// Pedido explícito do usuário, 2026-07-20: "exibir... um card com esses
// alertas como se fosse uma rolagem na tela principal. Chamando a atenção
// dos produtos desses alertas". Rolagem horizontal (carrossel) de chips —
// um por tipo de alerta ativo — cada um navega pra "Gestão de Compras >
// Ressuprimento" já filtrado por aquele tipo (ver
// `gestao-compras-ressuprimento.tsx`'s leitura de `?tipo=`).
//
// `compact`: usado quando a tela principal (`principal.tsx`) exibe este
// card ao lado do `WelcomeHero` (mesma linha, cada um ocupando metade da
// largura) em vez de abaixo dele, largura cheia — pedido explícito do
// usuário, 2026-07-20 ("coloque ao lado desse card"). Nesse modo, este
// componente não aplica seu próprio limite de largura (o `View` pai, em
// `principal.tsx`, já cuida disso).
import { useState } from "react";
import { Platform, Pressable, Text, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as ps } from "./styles";
import { ResumoAlertasEstoque } from "./useDashboard";

type Props = {
  resumo: ResumoAlertasEstoque | null;
  compact?: boolean;
  // Quando os alertas foram buscados pela última vez, se está buscando
  // agora, e o disparo manual — a busca automática só acontece uma vez por
  // sessão do app (ver useDashboard.ts), então esses 3 props deixam
  // visível o quão "fresco" o alerta é e dão ao usuário um jeito de pedir
  // dado novo sem precisar recarregar a tela inteira. Pedido explícito do
  // usuário, 2026-07-21 ("retire o recarregamento automático... mas deixe
  // visível o último carregamento").
  atualizadoEm?: Date | null;
  carregando?: boolean;
  onAtualizar?: () => void;
};

const isWeb = Platform.OS === "web";

type Tipo = {
  key: "minimo" | "ressuprimento" | "zerado";
  label: string;
  hint: string;
  icon: keyof typeof Ionicons.glyphMap;
  color: string;
  bg: string;
};

// `bg` reaproveita os mesmos tons já usados em `statusFor()`
// (gestao-compras-ressuprimento.tsx) pro badge do ícone — não inventa uma
// nova paleta só pra este card.
const TIPOS: Tipo[] = [
  {
    key: "zerado",
    label: "Zerado ou Negativo",
    hint: "Sem estoque disponível — risco de não conseguir vender.",
    icon: "alert-circle",
    color: colors.error,
    bg: "#FBEAEA",
  },
  {
    key: "minimo",
    label: "Estoque Mínimo",
    hint: "Já está abaixo do mínimo cadastrado.",
    icon: "warning",
    color: colors.error,
    bg: "#FBEAEA",
  },
  {
    key: "ressuprimento",
    label: "Ressuprimento",
    hint: "Hora de iniciar a compra, antes de faltar.",
    icon: "trending-down",
    color: colors.warning,
    bg: "#FBF1E4",
  },
];

// Exportado pra `principal.tsx` decidir o layout (lado a lado com o
// WelcomeHero ou não) sem duplicar a regra de visibilidade aqui dentro.
export function hasAlertasEstoque(resumo: ResumoAlertasEstoque | null): boolean {
  if (!resumo || !resumo.ativo) return false;
  const algumAtivo = TIPOS.some((t) => (resumo[t.key]?.count ?? 0) > 0);
  return algumAtivo || resumo.curva_abc_desatualizada;
}

export default function EstoqueAlertasCard({ resumo, compact, atualizadoEm, carregando, onAtualizar }: Props) {
  const router = useRouter();
  const [showCurvaInfo, setShowCurvaInfo] = useState(false);
  const [hoverTipo, setHoverTipo] = useState<Tipo["key"] | null>(null);
  if (!hasAlertasEstoque(resumo)) return null;
  // hasAlertasEstoque já garantiu que resumo não é null/inativo.
  const r = resumo!;

  const ativos = TIPOS
    .map((t) => ({ tipo: t, count: r[t.key]?.count ?? null }))
    .filter((x): x is { tipo: Tipo; count: number } => x.count !== null && x.count > 0);

  return (
    <View style={[{ marginBottom: spacing.md }, compact && { flex: 1 }]} testID="principal-estoque-alertas">
      <View style={{ flexDirection: "row", alignItems: "center", gap: 4, position: "relative", zIndex: 20 }}>
        <Text style={[ps.sectionTitle, isWeb && !compact && ps.sectionTitleWeb, { marginTop: 0, marginBottom: spacing.xs }]}>
          Alertas de Estoque
        </Text>
        {r.curva_abc_desatualizada ? (
          <Pressable
            onPress={() => router.push("/curva-abc")}
            onHoverIn={() => setShowCurvaInfo(true)}
            onHoverOut={() => setShowCurvaInfo(false)}
            hitSlop={6}
            testID="principal-curva-abc-desatualizada"
          >
            <Ionicons name="information-circle-outline" size={15} color={colors.brandPrimary} />
          </Pressable>
        ) : null}
        {onAtualizar ? (
          <Pressable
            onPress={onAtualizar}
            disabled={carregando}
            hitSlop={8}
            style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: carregando ? 0.5 : 1 }}
            testID="principal-estoque-alertas-atualizar"
          >
            <Ionicons name="refresh-outline" size={13} color={colors.brandPrimary} />
            <Text style={{ fontSize: 10, color: colors.muted }}>
              {carregando
                ? "Atualizando…"
                : atualizadoEm
                  ? `Atualizado em ${atualizadoEm.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })} às ${atualizadoEm.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}`
                  : "Atualizar"}
            </Text>
          </Pressable>
        ) : null}
        {showCurvaInfo ? (
          <View
            style={{
              position: "absolute", top: 20, left: 0, zIndex: 10, width: 280,
              backgroundColor: colors.onSurface, borderRadius: radius.sm,
              paddingHorizontal: spacing.sm, paddingVertical: spacing.sm,
            }}
          >
            <Text style={{ color: "#fff", fontSize: 11, lineHeight: 15 }}>
              <Text style={{ fontWeight: "700" }}>
                {r.curva_abc_ultima_geracao ? "Curva ABC desatualizada. " : "Curva ABC nunca foi gerada. "}
              </Text>
              Ela recalcula o estoque mínimo, o ponto de ressuprimento e o consumo médio de cada produto com base
              nas vendas recentes — sem atualizar a cada poucos meses, os alertas abaixo podem estar usando
              números antigos. Toque para atualizar em Curva ABC e Estoques.
            </Text>
          </View>
        ) : null}
      </View>

      {ativos.length === 0 ? null : (
        // Uma linha só, sem rolagem — 3 chips compactos dividindo a
        // largura disponível igualmente. Reduzido de propósito (ícone/
        // fonte/padding menores, sem texto de dica) pra caber os 3 juntos
        // mesmo no modo `compact` (ao lado do WelcomeHero, metade da
        // largura da tela). Pedido explícito do usuário, 2026-07-20
        // ("coloque esses cards em uma única linha. Reduzindo o tamanho e
        // fonte dos Cards").
        // Mesma geometria E MESMA LARGURA dos tiles de módulo (160px web,
        // `ps.tileWeb` — radius.md, fundo surfaceSecondary, minHeight 76,
        // padding sm, badge de ícone) — padronizado com `ModuleTiles.tsx`,
        // pedido explícito do usuário, 2026-07-20 ("padronize os cards" /
        // "mesma largura dos cards da pré-venda"). O destaque de
        // severidade (borda esquerda + fundo do badge) é a única
        // diferença intencional, já que esse dado não existe nos tiles de
        // módulo. Container não estica mais pro resto da largura
        // disponível (largura fixa por card, como o `tilesGrid`).
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
          {ativos.map(({ tipo, count }) => (
            // "Modo Didático" — cada card conta o que representa no hover
            // (`tipo.hint`), pedido explícito do usuário, 2026-07-20
            // ("informando o que representa cada um no tooltip"). Wrapper
            // próprio com position:relative + zIndex condicional evita o
            // mesmo bug de empilhamento já corrigido no ícone da Curva ABC
            // acima (tooltip nascendo atrás do card vizinho).
            <View
              key={tipo.key}
              style={{ position: "relative", zIndex: hoverTipo === tipo.key ? 30 : 1 }}
            >
              <Pressable
                onPress={() => router.push({ pathname: "/gestao-compras-ressuprimento", params: { tipo: tipo.key } })}
                onHoverIn={() => setHoverTipo(tipo.key)}
                onHoverOut={() => setHoverTipo(null)}
                style={({ pressed }) => [
                  {
                    width: isWeb ? 160 : undefined,
                    flex: isWeb ? undefined : 1,
                    minWidth: 0,
                    minHeight: 76,
                    justifyContent: "center",
                    backgroundColor: colors.surfaceSecondary,
                    borderRadius: radius.md,
                    borderWidth: 1,
                    borderColor: colors.border,
                    borderLeftWidth: 3,
                    borderLeftColor: tipo.color,
                    padding: spacing.sm,
                  },
                  pressed && { opacity: 0.8 },
                ]}
                testID={`principal-estoque-alerta-${tipo.key}`}
              >
                <View
                  style={{
                    width: 26, height: 26, borderRadius: radius.sm,
                    backgroundColor: tipo.bg,
                    alignItems: "center", justifyContent: "center", marginBottom: 6,
                  }}
                >
                  <Ionicons name={tipo.icon} size={14} color={tipo.color} />
                </View>
                <Text style={{ fontSize: 15, fontWeight: "700", color: colors.onSurface }}>{count}</Text>
                <Text style={{ fontSize: 10, fontWeight: "600", color: colors.muted, marginTop: 1 }} numberOfLines={1}>
                  {tipo.label}
                </Text>
              </Pressable>
              {hoverTipo === tipo.key ? (
                <View
                  style={{
                    position: "absolute", top: 80, left: 0, width: 200,
                    backgroundColor: colors.onSurface, borderRadius: radius.sm,
                    paddingHorizontal: spacing.sm, paddingVertical: 6,
                  }}
                  testID={`principal-estoque-alerta-tooltip-${tipo.key}`}
                >
                  <Text style={{ color: "#fff", fontSize: 11, lineHeight: 15 }}>{tipo.hint}</Text>
                </View>
              ) : null}
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
