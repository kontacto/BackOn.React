// Card de emissão de Nota Fiscal (NFC-e/NFS-e) por comanda — extraído do
// JSX de `app/alterar-comanda.tsx` como parte do ecossistema fiscal
// (Web + KPDV, ver `useEmitirNotaFiscal.ts` pro racional completo da
// extração). Reaproveitado por Pedido Bar/Geral e O.S. Mobile/Completa
// depois de faturar (sempre emissão MANUAL), e retrofitado no próprio
// `alterar-comanda.tsx` em vez de manter a lógica duplicada.
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { colors, radius, spacing } from "@/src/theme/colors";
import type { DocFiscal } from "@/src/hooks/useEmitirNotaFiscal";

export default function NotaFiscalCard(props: {
  docFiscal: DocFiscal | null;
  emitindoNfce: boolean;
  emitindoNfse: boolean;
  onEmitirNfce: () => void;
  onEmitirNfse: () => void;
  canEmitirNfce: boolean;
  canEmitirNfse: boolean;
  testIDPrefix?: string;
}) {
  const {
    docFiscal, emitindoNfce, emitindoNfse, onEmitirNfce, onEmitirNfse,
    canEmitirNfce, canEmitirNfse, testIDPrefix = "nota-fiscal",
  } = props;

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Nota Fiscal</Text>
      {docFiscal ? (
        <Text style={styles.docText}>
          {docFiscal.tipo === "NFCE" ? "NFC-e" : docFiscal.tipo === "NFSE" ? "NFS-e" : docFiscal.tipo === "NF" ? "Nota Fiscal" : "Cupom"}
          {docFiscal.numero != null ? ` nº ${docFiscal.numero}` : ""}
          {docFiscal.protocolo ? ` · Protocolo ${docFiscal.protocolo}` : ""}
          {docFiscal.chave_acesso ? ` · Chave ${docFiscal.chave_acesso}` : ""}
        </Text>
      ) : (
        <Text style={styles.hint}>Nenhuma nota fiscal emitida para esta comanda ainda.</Text>
      )}
      {/* Comanda pode misturar item de produto e de serviço — cada
          documento (NFC-e/NFS-e) é independente; `docFiscal` só reflete o
          PRIMEIRO já emitido (NFC-e > NFS-e), então os botões continuam
          disponíveis mesmo com um dos dois já emitido, exceto quando é
          justamente esse tipo que já foi emitido — mesma limitação
          conhecida já registrada em PENDENCIAS.md > "Emissão Fiscal Real"
          (exibição mostra só 1 doc). */}
      <View style={styles.actionsRow}>
        {canEmitirNfce && docFiscal?.tipo !== "NFCE" ? (
          <Pressable onPress={onEmitirNfce} disabled={emitindoNfce} style={styles.primaryBtn} testID={`${testIDPrefix}-emitir-nfce`}>
            {emitindoNfce ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Emitir NFC-e</Text>}
          </Pressable>
        ) : null}
        {canEmitirNfse && docFiscal?.tipo !== "NFSE" ? (
          <Pressable onPress={onEmitirNfse} disabled={emitindoNfse} style={styles.primaryBtn} testID={`${testIDPrefix}-emitir-nfse`}>
            {emitindoNfse ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Emitir NFS-e</Text>}
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, gap: spacing.sm,
  },
  title: { fontSize: 14, fontWeight: "700", color: colors.onSurfaceSecondary },
  docText: { fontSize: 13, color: colors.onSurfaceSecondary },
  hint: { fontSize: 12, color: colors.muted },
  actionsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm, marginTop: spacing.xs },
  primaryBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 8, paddingHorizontal: spacing.lg,
    alignItems: "center", justifyContent: "center", minHeight: 36,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "700", fontSize: 13 },
});
