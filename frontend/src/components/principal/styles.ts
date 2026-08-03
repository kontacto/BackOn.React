// StyleSheet da tela principal (Dashboard). Mantido idêntico ao original.
import { StyleSheet } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";

export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.md,
    backgroundColor: colors.brandPrimary, gap: spacing.md,
  },
  headerLeft: {
    width: 150,
    justifyContent: "center",
  },
  headerLogo: {
    width: 170,
    height: 38,
  },
  headerCenter: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },
  headerRight: {
    width: 150,
    alignItems: "flex-end",
    justifyContent: "center",
  },
  headerTitle: { fontSize: 20, fontWeight: "500", color: colors.onBrandPrimary, letterSpacing: -0.3 },
  headerSub: { fontSize: 16, color: colors.onBrandPrimary, fontWeight: "600", textAlign: "center" },
  headerSubWeb: { fontSize: 18 },
  logoutBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.25)",
  },
  logoutLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl },
  scrollWeb: {
    alignItems: "center",
    flexGrow: 1,
    paddingHorizontal: spacing.xl,
    paddingTop: spacing.xl,
    paddingBottom: spacing.xl,
  },
  webFrame: {
    width: "100%",
    maxWidth: 1000,
  },
  webGrid: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: spacing.xl,
  },
  webColLeft: {
    flex: 1.05,
    minWidth: 0,
  },
  webColRight: {
    flex: 0.95,
    minWidth: 0,
    gap: spacing.md,
  },
  hero: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
  },
  heroWeb: {
    width: "100%",
    maxWidth: 920,
    alignSelf: "center",
  },
  avatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  welcome: { fontSize: 12, color: colors.muted },
  heroName: { fontSize: 18, fontWeight: "500", color: colors.onSurface, marginTop: 2 },
  heroSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sectionTitle: {
    fontSize: 13, fontWeight: "500", color: colors.onSurface,
    marginTop: spacing.lg, marginBottom: spacing.sm,
    textTransform: "uppercase", letterSpacing: 0.5,
  },
  sectionTitleWeb: { width: "100%", maxWidth: 920, alignSelf: "center" },
  tilesGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  tilesGridWeb: { gap: spacing.lg, marginBottom: spacing.sm, width: "100%", maxWidth: 920, alignSelf: "center" },
  tile: {
    width: "47%", backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border, minHeight: 92,
    justifyContent: "space-between",
  },
  // Formatação reduzida do tile no web (pedido explícito do usuário,
  // 2026-07-20) — largura fixa e compacta em vez de ~metade da tela,
  // cabe mais de um por linha sem esticar. Sem `calc()` (não é um
  // `DimensionValue` válido pro React Native — gerava erro de tipo;
  // `gap` no `tilesGridWeb` já cuida do espaçamento entre tiles).
  tileWeb: { width: 160, minHeight: 76, padding: spacing.sm },
  tileIcon: {
    width: 36, height: 36, borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center", marginBottom: spacing.sm,
  },
  tileIconWeb: { width: 26, height: 26, borderRadius: radius.sm, marginBottom: 6 },
  tileLabel: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  tileHint: { fontSize: 11, color: colors.muted, marginTop: 2 },
  tileLabelWeb: { fontSize: 12.5 },
  tileHintWeb: { fontSize: 10 },
  totalsRow: { flexDirection: "row", gap: spacing.sm },
  totalsRowWeb: { flexDirection: "row", gap: 12, width: "100%", maxWidth: 920, alignSelf: "center" },
  filterRow: { flexDirection: "row", marginTop: spacing.md },
  sitFilterRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.sm, marginBottom: spacing.xs },
  sitFilterRowWeb: { width: "100%", maxWidth: 920, alignSelf: "center" },
  sitChip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  sitChipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  sitChipText: { fontSize: 12, color: colors.muted },
  sitChipTextSel: { color: colors.brandPrimary, fontWeight: "600" },
  margemCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md,
    marginTop: spacing.sm, borderLeftWidth: 4, borderLeftColor: colors.brandPrimary,
  },
  margemCardWeb: { width: "100%", maxWidth: 920, alignSelf: "center", marginTop: 16, padding: 18 },
  margemIcon: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  margemLabel: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  margemHint: { fontSize: 11, color: colors.muted, marginTop: 1 },
  margemDesc: { fontSize: 12, color: colors.error, fontWeight: "500", marginTop: 3 },
  margemValue: { fontSize: 17, fontWeight: "700", color: colors.brandPrimary },
  margemPct: { fontSize: 12, fontWeight: "600", color: colors.success },
  totalCard: {
    flex: 1, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
    borderLeftWidth: 4,
  },
  totalCardWeb: { minHeight: 92 },
  // Formatação reduzida — os 4 cards de "Totais de Hoje" em uma única
  // linha (pedido explícito do usuário, 2026-07-20), padding/fonte
  // menores pra caber os 4 sem quebrar.
  totalCardWebCompact: { minHeight: 62, padding: spacing.sm },
  totalLabelWebCompact: { fontSize: 9.5 },
  totalValueWebCompact: { fontSize: 16, marginTop: 2 },
  totalLabel: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  totalValue: { fontSize: 22, fontWeight: "600", color: colors.onSurface, marginTop: 4 },
  pedidosHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pedidosHeaderWeb: { width: "100%", maxWidth: 920, alignSelf: "center" },
  pedidosCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
  },
  pedidosCardWeb: {
    borderRadius: radius.lg,
    width: "100%",
    maxWidth: 920,
    alignSelf: "center",
  },
  pedidosHead: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.brandTertiary, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  pedidoCell: { fontSize: 11, color: colors.brandPrimary, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4 },
  pedidoRow: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border, alignItems: "center",
  },
  pedidoCellValue: { fontSize: 13, color: colors.onSurface },
  pedidoTotalRow: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    backgroundColor: colors.brandTertiary, alignItems: "center",
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  pedidoTotalLabel: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  pedidoTotalValue: { fontSize: 15, fontWeight: "700", color: colors.brandPrimary },
  empty: { textAlign: "center", color: colors.muted, paddingVertical: spacing.lg, fontSize: 13 },
});
