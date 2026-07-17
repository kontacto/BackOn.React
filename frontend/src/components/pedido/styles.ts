// StyleSheet compartilhado pela tela de pedido e seus modais/componentes.
// Mantido idêntico ao original para preservar 100% do visual.
import { StyleSheet } from "react-native";
import { Platform } from "react-native";
import { colors, radius, spacing } from "@/src/theme/colors";

export const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

export const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  sectionTitle: { fontSize: 12, color: colors.muted, marginTop: spacing.md, marginBottom: 4, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.5 },
  lockHint: { fontSize: 10, color: colors.muted, fontWeight: "400", textTransform: "none", letterSpacing: 0 },
  row: { flexDirection: "row", gap: 8, alignItems: "flex-end" },
  dateRow: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  headerMeta: { fontSize: 12, color: colors.muted },
  clienteBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  clienteNome: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  clienteSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  resumoBox: {
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 6,
  },
  resumoRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  resumoText: { fontSize: 13, color: colors.onSurface, flex: 1 },
  // Versão compacta do resumoBox — botão ao lado do card de nome do
  // cliente (em vez de abaixo, ocupando a largura toda); toque abre modal
  // "Dados Principais" com o conteúdo completo.
  resumoBoxCompact: { width: 340, marginTop: 0, justifyContent: "center" },
  readonlyBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    borderWidth: 1, borderColor: colors.border, minHeight: 42,
  },
  readonlyText: { fontSize: 14, color: colors.onSurface },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  // "Redução forte" (Modal/Selector Standard, CLAUDE.md) — mesmo padrão
  // canônico de SelectField.tsx/NiveisModal.tsx: no web, card centralizado,
  // largura máxima, raio de canto completo (não só topo) + borda.
  modalBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl,
    maxHeight: "88%",
  },
  modalCardWebCompact: {
    width: "100%",
    maxWidth: 560,
    alignSelf: "center",
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  // Tier "confirmação pontual sobre um único registro" (360–480px, CLAUDE.md
  // "Padrões de UI — Modais") — mais estreito que modalCardWebCompact
  // (560px, tier de seleção/busca) porque confirma 1 item (quantidade/
  // valor/desconto), não navega lista. Usado por AddItemModal/EditItemModal.
  modalCardWebCompactNarrow: {
    width: "100%",
    maxWidth: 420,
    alignSelf: "center",
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  resultRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultNome: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  quickAddBtn: {
    width: 32, height: 32, borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center", marginLeft: 4,
  },
  emptyBox: { alignItems: "center", padding: spacing.xl, gap: spacing.md },
  emptyText: { color: colors.muted, fontSize: 13 },
  createBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderRadius: radius.pill,
  },
  createBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },
  // Wrapper que centraliza o toast na tela inteira (nunca ancorado em canto,
  // nunca esticado de borda a borda) — ver CLAUDE.md > "Padrões de UI —
  // Modais, Mensagens e Formulários (Web)".
  toastWrap: { flex: 1, alignItems: "center", justifyContent: "center", padding: spacing.xl },
  toast: {
    maxWidth: 420,
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md,
    ...Platform.select({
      web: { boxShadow: "0 6px 12px rgba(0, 0, 0, 0.35)" },
      default: {
        shadowColor: "#000",
        shadowOpacity: 0.35,
        shadowRadius: 12,
        shadowOffset: { width: 0, height: 6 },
        elevation: 12,
      },
    }),
    alignItems: "center",
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
  // Botão de abrir/fechar "Dados Principais" — cartão de largura total
  // (antes era só texto+chevron, sem fundo/borda).
  itensHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    marginTop: spacing.lg, marginBottom: spacing.sm,
    width: "100%", alignSelf: "stretch",
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  addItemBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 4, height: 36,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md,
    borderRadius: radius.pill,
  },
  addItemBtnText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  itensHint: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border, marginTop: spacing.sm,
  },
  itensHintText: { color: colors.muted, fontSize: 13, flex: 1 },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  itemTipo: { width: 36, height: 36, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  tagTaxaServico: { backgroundColor: "#e6f4ea" },
  itemDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  itemSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  itemTotal: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  // Card do item do Pedido — tudo em UMA linha (nome, código/qtd/valor,
  // inclusão, total), pra reduzir a altura de cada card na lista.
  itemRowCompact: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingVertical: spacing.sm, paddingHorizontal: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  itemDescCompact: { fontSize: 14, fontWeight: "500", color: colors.onSurface, flexShrink: 1, minWidth: 0 },
  itemSubCompact: { fontSize: 12, color: colors.muted, flexShrink: 1, minWidth: 0 },
  itemIncluidoEmCompact: { fontSize: 11, color: colors.muted, fontStyle: "italic", flexShrink: 1, minWidth: 0 },
  itemTotalCompact: { marginLeft: "auto", flexShrink: 0 },
  // Etiqueta vermelha (só ícone) marcando item com desconto aplicado, na
  // linha compacta da lista de itens — valor do desconto vai no tooltip
  // (hover no web, toque no mobile), não no rótulo.
  descTagCompact: {
    alignItems: "center", justifyContent: "center", flexShrink: 0,
    width: 20, height: 20,
    backgroundColor: colors.error, borderRadius: radius.pill,
  },
  descTooltip: {
    position: "absolute", bottom: "100%", left: 0, marginBottom: 4,
    backgroundColor: "#1a1a1a", borderRadius: radius.sm,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
    zIndex: 10,
  },
  descTooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  // Botão "Imprimir Item" — mesmo formato/tamanho da etiqueta de desconto
  // acima, cor neutra (não é um alerta, é uma ação disponível sempre).
  imprimirItemTag: {
    alignItems: "center", justifyContent: "center", flexShrink: 0,
    width: 22, height: 22,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  subtotalRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, marginTop: 4,
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
  },
  subtotalLabel: { fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  subtotalValue: { fontSize: 18, fontWeight: "700", color: colors.brandPrimary },
  // Toolbar de ações secundárias (Analisar margem/Desconto geral) — pills
  // compactos acima da lista de itens, ver "Padrões de UI" em CLAUDE.md.
  itensToolbar: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.lg },
  toolbarPill: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  toolbarPillText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  // Estado "ativo" de um pill do toolbar (ex.: Tx Serviço já incluída) —
  // mesmo verde já usado no pill de Fechar Pedido.
  toolbarPillActive: { backgroundColor: colors.success, borderColor: colors.success },
  toolbarPillActiveText: { color: "#fff" },
  toolbarPillFechar: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, backgroundColor: colors.success,
  },
  toolbarPillFecharText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  toolbarPillFaturar: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, backgroundColor: colors.brandPrimary,
  },
  toolbarPillFaturarText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  toolbarPillImprimir: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  toolbarPillImprimirText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  // Anexo (Gestor de Documentos) — mesmo estilo outline do Imprimir, entre
  // Faturar e Imprimir/Cancelar na toolbar.
  toolbarPillAnexo: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.brandPrimary,
    backgroundColor: colors.brandTertiary,
  },
  toolbarPillAnexoText: { color: colors.brandPrimary, fontWeight: "600", fontSize: 13 },
  // Reabrir Pedido — cor amarela (pedido explícito do usuário, 2026-07-16),
  // usa o par semântico warning/onWarning já existente (mais próximo de
  // "amarelo" no design system atual — não existe token amarelo puro),
  // preenchido igual ao Faturar/Cancelar.
  toolbarPillReabrir: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, backgroundColor: colors.warning,
  },
  toolbarPillReabrirText: { color: colors.onWarning, fontWeight: "600", fontSize: 13 },
  // Cancelar Pedido — cor vermelha (pedido explícito do usuário, 2026-07-16),
  // preenchido igual ao Faturar (ação de destaque, não outline).
  toolbarPillCancelar: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md,
    borderRadius: radius.pill, backgroundColor: colors.error,
  },
  toolbarPillCancelarText: { color: "#fff", fontWeight: "600", fontSize: 13 },
  // Cabeçalho "Itens do Pedido (N)" + Subtotal + Descontos concedidos +
  // Adicionar, tudo em uma faixa acima da lista (flexWrap pra caber em
  // telas estreitas).
  itensSummaryRow: {
    flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between",
    gap: spacing.sm, marginTop: spacing.sm, marginBottom: spacing.sm,
  },
  itensSummaryLeft: { flexDirection: "row", flexWrap: "wrap", alignItems: "center", gap: spacing.sm, flex: 1 },
  itensSummaryRight: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  subtotalPill: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, height: 36,
    paddingHorizontal: spacing.md, borderRadius: radius.pill,
    backgroundColor: colors.brandTertiary,
  },
  subtotalPillLabel: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  subtotalPillValue: { fontSize: 18, color: colors.brandPrimary, fontWeight: "700" },
  descPill: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 5, height: 36,
    paddingHorizontal: spacing.md, borderRadius: radius.pill,
    backgroundColor: "#fdecea", borderWidth: 1, borderColor: "#f5c6cb",
  },
  descPillLabel: { fontSize: 12, color: colors.error, fontWeight: "500" },
  descPillValue: { fontSize: 12, color: colors.error, fontWeight: "700" },
  geralEquiv: { fontSize: 12, color: colors.muted, marginTop: -2 },
  deleteBtnWide: {
    paddingHorizontal: spacing.lg, borderRadius: radius.pill, paddingVertical: 13,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.error,
  },
  deleteBtnWideText: { color: colors.error, fontWeight: "600", fontSize: 15 },
  fecharBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginTop: spacing.md, paddingVertical: 14, borderRadius: radius.md,
    backgroundColor: colors.success,
  },
  fecharBtnText: { color: "#fff", fontWeight: "700", fontSize: 15 },
  descRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  selProdBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  qtdRow: { flexDirection: "row", gap: spacing.sm },
  qtdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  plusBtn: {
    width: 40, height: 42, borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  liquidoBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 2,
    borderWidth: 1, borderColor: colors.border,
  },
  liquidoRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  liquidoLabel: { fontSize: 12, color: colors.muted },
  liquidoVal: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  previewRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: spacing.sm, marginTop: 4,
  },
  modalBtns: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: {
    flex: 1, backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: "center", justifyContent: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  secondaryBtn: {
    paddingHorizontal: spacing.lg, borderRadius: radius.pill, paddingVertical: 13,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border,
  },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "500", fontSize: 15 },
  deleteBtn: {
    width: 50, borderRadius: radius.pill, paddingVertical: 13,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.error,
  },
  fullListBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginTop: spacing.sm, paddingVertical: 12, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  fullListText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 14 },
});
