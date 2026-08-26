// Modal de busca do "Código Complementar Municipal" (servicos.
// cod_servico_municipio) contra a tabela oficial real `Tributacao_
// MUnicipio` (herdada do legado, crosswalk item LC116 → código
// complementar) — mesmo princípio de "Campos de Identidade Precisam de
// Mecanismo de Busca" já aplicado a Fabricante/Fornecedor, ver CLAUDE.md.
// Nunca autofill: um mesmo item LC116 tem vários códigos possíveis
// (ex.: "Manutenção de aparelhos" vs. "Manutenção de equipamentos"), só o
// usuário sabe qual bate com o serviço real — por isso é busca, não
// preenchimento automático. Mesmo padrão visual de FornecedorSearchModal.tsx.
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";

import { colors, radius, spacing } from "@/src/theme/colors";
import { apiGet, ConnLike } from "@/src/utils/api";

const isCompactWeb = Platform.OS === "web";

export type TributacaoMunicipioRow = {
  cod_trib_nac_mun: string;
  cod_trib_nac: string;
  cod_trib_mun: string;
  descricao: string;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: ConnLike | null;
  /** cod_lista_servico já digitado no formulário (opcional) — usado pra
   * pré-filtrar sugestões relevantes assim que o modal abre. */
  codListaServico?: string;
  onPick: (item: TributacaoMunicipioRow) => void;
};

export default function TributacaoMunicipioSearchModal({ visible, onClose, conn, codListaServico, onPick }: Props) {
  const [term, setTerm] = useState("");
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<TributacaoMunicipioRow[]>([]);

  useEffect(() => {
    if (!visible) return;
    setTerm("");
    setResults([]);
  }, [visible]);

  useEffect(() => {
    if (!visible || !conn) return;
    const connAtiva = conn;
    let cancelled = false;
    const termo = term.trim();
    if (termo.length < 2 && !codListaServico) {
      setResults([]);
      return;
    }
    setLoading(true);
    const params = termo.length >= 2 ? { search: termo } : { cod_lista_servico: codListaServico || "" };
    const t = setTimeout(() => {
      apiGet(connAtiva, "/api/servicos/tributacao-municipio", params)
        .then((r: any) => {
          if (cancelled) return;
          setResults(r?.success ? r.items || [] : []);
        })
        .catch(() => { if (!cancelled) setResults([]); })
        .finally(() => { if (!cancelled) setLoading(false); });
    }, 300);
    return () => { cancelled = true; clearTimeout(t); };
  }, [visible, term, codListaServico, conn]);

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>Código Complementar Municipal</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>
          <Text style={styles.hint}>
            Busca na tabela oficial de Códigos de Tributação Municipal. Escolha a descrição que melhor
            representa este serviço — o código é gravado, a descrição não.
          </Text>

          <View style={styles.searchWrap}>
            <Ionicons name="search" size={16} color={colors.muted} />
            <TextInput
              value={term}
              onChangeText={setTerm}
              placeholder="Buscar por descrição…"
              placeholderTextColor={colors.muted}
              style={styles.searchInput}
              autoFocus
              testID="tributacao-municipio-search-input"
              autoComplete="off"
              autoCorrect={false}
              textContentType="none"
              importantForAutofill="no"
            />
          </View>

          {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          <ScrollView style={{ maxHeight: 380 }}>
            {results.map((item) => (
              <Pressable
                key={item.cod_trib_nac_mun}
                onPress={() => onPick(item)}
                style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`tributacao-municipio-result-${item.cod_trib_mun}`}
              >
                <View style={{ flex: 1 }}>
                  <Text style={styles.rowNome} numberOfLines={2}>{item.descricao}</Text>
                  <Text style={styles.rowSub} numberOfLines={1}>
                    código {item.cod_trib_mun} · item {item.cod_trib_nac_mun}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={colors.muted} />
              </Pressable>
            ))}
            {!loading && (term.trim().length >= 2 || codListaServico) && results.length === 0 ? (
              <Text style={styles.vazio}>
                Nenhum código encontrado{codListaServico ? " pra este Código de Tributação Nacional" : ""} — tente
                buscar por outro termo.
              </Text>
            ) : null}
            {!loading && !term.trim() && !codListaServico ? (
              <Text style={styles.vazio}>Digite pra buscar, ou preencha o Código de Tributação Nacional primeiro.</Text>
            ) : null}
          </ScrollView>
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
});
