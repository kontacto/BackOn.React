import { colors, radius, spacing } from "@/src/theme/colors";

export const WEB_CONTENT_MAX_WIDTH = 1120;

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
