import { colors, radius, spacing } from "@/src/theme/colors";

// App Web = substituto do VB6 Desktop, não "app mobile esticado" (ver
// CLAUDE.md > "App Web como Substituto do Desktop VB6"). 1120 deixava
// muito espaço vazio em monitor grande — alargado pra usar a tela de
// verdade, mesmo espírito de densidade do VB6.
export const WEB_CONTENT_MAX_WIDTH = 1600;

export const WEB_SCROLL_CENTER = {
  alignItems: "center" as const,
  paddingHorizontal: spacing.xl,
  paddingVertical: spacing.xl,
};

export const WEB_CONTENT_SHELL = {
  width: "100%" as const,
  maxWidth: WEB_CONTENT_MAX_WIDTH,
  alignSelf: "center" as const,
};

export const WEB_FILTER_CARD = {
  width: "100%" as const,
  maxWidth: WEB_CONTENT_MAX_WIDTH,
  alignSelf: "center" as const,
  backgroundColor: colors.surface,
  borderWidth: 1,
  borderColor: colors.border,
  borderRadius: radius.lg,
  padding: spacing.lg,
};

// Colunas de campo pra "Design Desktop" (ver CLAUDE.md > "'Design Desktop'
// — App Web como Substituto do Desktop VB6"). Substituem o padrão antigo
// `width: "49%"` (percentual do container — some field's width scales com
// o container inteiro, então em telas largas um campo curto tipo "Sexo"
// ou "UF" ficava absurdamente esticado). `flexBasis`+`maxWidth` faz o
// campo crescer só até um teto sensato e, combinado com `flexWrap: "wrap"`
// no container (`formGrid`/`rowFields`), several campos cabem lado a lado
// automaticamente — 2, 3 ou 4 por linha dependendo da largura disponível,
// sem precisar calcular percentual manualmente.
export const WEB_FIELD_COL_TINY = { flexGrow: 0, flexShrink: 0, flexBasis: 110, maxWidth: 140 };
export const WEB_FIELD_COL_NARROW = { flexGrow: 0, flexShrink: 0, flexBasis: 190, maxWidth: 240 };
export const WEB_FIELD_COL_HALF = { flexGrow: 1, flexShrink: 1, flexBasis: 320, maxWidth: 420 };
export const WEB_FIELD_COL_FLEX = { flexGrow: 1, flexShrink: 1, flexBasis: 320 };
