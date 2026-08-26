// Modal de busca de NCM + CEST — reaproveitável por qualquer tela que
// referencie esses códigos (hoje: Produto Completo). Ver CLAUDE.md >
// "Campos de Identidade Precisam de Mecanismo de Busca" e
// [[project_ncm_cest]] pro cadastro que esta busca consulta.
//
// Fluxo em 2 passos, mesma ideia já usada pro fluxo de Número de Série em
// Pedido Completo ("resolve automático quando só há 1 opção, pergunta
// quando há mais de uma"): busca NCM → ao escolher um NCM, busca os CEST
// que se aplicam a ele (endpoint já resolve por PREFIXO — um CEST pode
// valer pra um capítulo/posição inteiro, não só o NCM completo). Zero CEST
// → volta só o NCM. Exatamente 1 → preenche os dois de uma vez. 2+ → pede
// pra escolher, com opção de ficar só com o NCM.
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { colors, radius, spacing } from "@/src/theme/colors";
import { apiGet, ConnLike } from "@/src/utils/api";

const isCompactWeb = Platform.OS === "web";

export type NcmRow = { ncm: string; descricao: string };
export type CestRow = { ncm: string; cest: string; descricao: string };

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: ConnLike | null;
  onPick: (ncm: string, cest: string | null) => void;
};

export default function NcmCestSearchModal({ visible, onClose, conn, onPick }: Props) {
  const [step, setStep] = useState<"ncm" | "cest">("ncm");
  const [term, setTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<NcmRow[]>([]);

  const [selNcm, setSelNcm] = useState<string | null>(null);
  const [cestOptions, setCestOptions] = useState<CestRow[]>([]);
  const [loadingCest, setLoadingCest] = useState(false);

  useEffect(() => {
    if (!visible) return;
    setStep("ncm");
    setTerm("");
    setResults([]);
    setSelNcm(null);
    setCestOptions([]);
  }, [visible]);

  useEffect(() => {
    if (!visible || !conn || step !== "ncm") return;
    const connAtiva = conn;
    let cancelled = false;
    const termo = term.trim();
    if (termo.length < 2) { setResults([]); return; }
    setLoading(true);
    const t = setTimeout(() => {
      apiGet(connAtiva, "/api/ncm", { search: termo })
        .then((r: any) => { if (!cancelled) setResults(r?.success ? r.items || [] : []); })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [visible, term, step, conn]);

  const pickNcm = async (row: NcmRow) => {
    if (!conn) { onPick(row.ncm, null); return; }
    setSelNcm(row.ncm);
    setLoadingCest(true);
    try {
      const j = await apiGet(conn, `/api/ncm/${encodeURIComponent(row.ncm)}`);
      const cests: CestRow[] = j?.success ? j.cests || [] : [];
      if (cests.length === 0) {
        onPick(row.ncm, null);
      } else if (cests.length === 1) {
        onPick(row.ncm, cests[0].cest);
      } else {
        setCestOptions(cests);
        setStep("cest");
      }
    } catch {
      onPick(row.ncm, null);
    } finally {
      setLoadingCest(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          {step === "ncm" ? (
            <>
              <View style={styles.header}>
                <Text style={styles.title}>Buscar NCM</Text>
                <Pressable onPress={onClose} hitSlop={8}>
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
              </View>
              <Text style={styles.hint}>
                Busca na tabela oficial de NCM (Nomenclatura Comum do Mercosul). Ao escolher, o
                CEST aplicável é sugerido automaticamente quando houver só uma opção.
              </Text>

              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={term}
                  onChangeText={setTerm}
                  placeholder="Código ou descrição do NCM…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  autoFocus
                  testID="ncm-cest-picker-search"
                  autoComplete="off"
                  autoCorrect={false}
                  textContentType="none"
                  importantForAutofill="no"
                />
              </View>

              {loading || loadingCest ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

              <ScrollView style={{ maxHeight: 380 }}>
                {results.map((row) => (
                  <Pressable
                    key={row.ncm}
                    onPress={() => pickNcm(row)}
                    style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`ncm-cest-picker-result-${row.ncm}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowNome} numberOfLines={1}>{row.ncm}</Text>
                      <Text style={styles.rowSub} numberOfLines={2}>{row.descricao}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                  </Pressable>
                ))}
                {!loading && term.trim().length >= 2 && results.length === 0 ? (
                  <Text style={styles.vazio}>Nenhum NCM encontrado.</Text>
                ) : null}
                {!term.trim() ? <Text style={styles.vazio}>Digite pra buscar.</Text> : null}
              </ScrollView>
            </>
          ) : (
            <>
              <View style={styles.header}>
                <Text style={styles.title}>Escolha o CEST</Text>
                <Pressable onPress={onClose} hitSlop={8}>
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
              </View>
              <Text style={styles.hint}>
                NCM {selNcm} tem mais de um CEST aplicável — escolha o que melhor descreve este
                produto, ou continue sem CEST.
              </Text>
              <ScrollView style={{ maxHeight: 380 }}>
                {cestOptions.map((c) => (
                  <Pressable
                    key={c.cest}
                    onPress={() => onPick(selNcm as string, c.cest)}
                    style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`ncm-cest-picker-cest-${c.cest}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowNome} numberOfLines={1}>{c.cest}</Text>
                      {c.descricao ? <Text style={styles.rowSub} numberOfLines={2}>{c.descricao}</Text> : null}
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                  </Pressable>
                ))}
              </ScrollView>
              <Pressable
                onPress={() => onPick(selNcm as string, null)}
                style={styles.semCestBtn}
                testID="ncm-cest-picker-sem-cest"
              >
                <Text style={styles.semCestBtnText}>Continuar sem CEST</Text>
              </Pressable>
              <Pressable onPress={() => setStep("ncm")} style={styles.voltarBtn} testID="ncm-cest-picker-voltar">
                <Ionicons name="arrow-back" size={16} color={colors.muted} />
                <Text style={styles.voltarBtnText}>Buscar outro NCM</Text>
              </Pressable>
            </>
          )}
        </Pressable>
      </Pressable>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  bg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end" },
  bgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  card: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.lg, maxHeight: "85%",
  },
  cardWebCompact: {
    width: "100%", maxWidth: 560, alignSelf: "center", maxHeight: "80%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  hint: { fontSize: 11.5, color: colors.muted, marginBottom: spacing.sm, fontStyle: "italic" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  row: {
    flexDirection: "row", alignItems: "center", paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: colors.border, gap: spacing.sm,
  },
  rowNome: { fontSize: 14, color: colors.onSurface, fontWeight: "600" },
  rowSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  vazio: { color: colors.muted, fontSize: 13, padding: spacing.md, textAlign: "center" },
  semCestBtn: { alignItems: "center", paddingVertical: 10, marginTop: spacing.xs },
  semCestBtnText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  voltarBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, paddingVertical: 8 },
  voltarBtnText: { color: colors.muted, fontSize: 12 },
});
