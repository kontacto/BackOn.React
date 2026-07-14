// StyleSheet do Relatório de Pedidos. Mantido idêntico ao original.
import { StyleSheet } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

export const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "600", color: colors.onBrandPrimary },
  scroll: { padding: spacing.lg, gap: spacing.sm },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filtersWeb: WEB_FILTER_CARD,
  filters: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm },
  dateRow: { flexDirection: "row", gap: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4, marginTop: 4 },
  sitRow: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 12, color: colors.muted },
  chipTextSel: { color: colors.brandPrimary, fontWeight: "600" },
  btn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, borderRadius: radius.md, paddingVertical: 12, marginTop: spacing.sm,
  },
  btnText: { color: colors.onBrandPrimary, fontSize: 15, fontWeight: "600" },
  errorBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: "#FDE7E7", borderRadius: radius.md, padding: spacing.md,
  },
  errorText: { color: colors.error, fontSize: 13, flex: 1 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 13, marginTop: spacing.lg },
  totaisBox: { backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md, gap: spacing.sm, marginTop: spacing.sm },
  totaisTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary },
  totaisRow: { flexDirection: "row", gap: spacing.sm },
  tCard: { flex: 1, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.sm, borderLeftWidth: 3 },
  tLabel: { fontSize: 10, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.3 },
  tValue: { fontSize: 18, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  tSub: { fontSize: 11, fontWeight: "600", color: colors.success },
  count: { fontSize: 12, color: colors.muted, marginTop: spacing.sm, marginBottom: 2 },
  card: { backgroundColor: colors.surface, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, overflow: "hidden" },
  cardHead: { flexDirection: "row", alignItems: "center", gap: spacing.sm, padding: spacing.md },
  cardTopRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  cardPedido: { fontSize: 15, fontWeight: "700", color: colors.brandPrimary },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 10 },
  sitTagText: { fontSize: 11, fontWeight: "600" },
  cardCliente: { fontSize: 14, color: colors.onSurface, marginTop: 3 },
  cardMeta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardTotal: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginBottom: 2 },
  expand: { padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surfaceSecondary },
  expandTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.xs },
  margemGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  mItem: { minWidth: "45%", flexGrow: 1 },
  mLabel: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.3 },
  mVal: { fontSize: 14, fontWeight: "600", color: colors.onSurface, marginTop: 1 },
  muted: { fontSize: 13, color: colors.muted },
  descRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: colors.border,
  },
  descDesc: { fontSize: 13, color: colors.onSurface },
  descMeta: { fontSize: 11, color: colors.muted, marginTop: 1 },
  descVal: { fontSize: 13, fontWeight: "600" },
});
