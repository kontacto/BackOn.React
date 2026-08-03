// Modal de busca de Equipamento (por número de série, descrição, portador
// ou local) — usado pelo bloco "Dados do Equipamento" da O.S. Completa
// (ver CLAUDE.md > "Campos de Identidade Precisam de Mecanismo de Busca").
// Mesmo padrão de `FornecedorSearchModal.tsx`, com uma diferença
// importante: `GET /api/equipamentos` é sempre escopado por `cliente`
// (`equipamentos.cliente`, mesma tabela de "Cadastro de Equipamentos do
// Cliente") — não existe busca global de equipamento entre clientes
// diferentes, então este modal exige um `cliente` já selecionado na tela
// que o abre (mesmo princípio de "related record precisa do pai salvo
// primeiro" já usado em Cliente/Fornecedor).
//
// Cadastro rápido INLINE (2026-08-02, user-directed — "implante Cadastro
// de equipamento inline"): quando a busca não encontra nada, o formulário
// mínimo (Número de Série + Marca + Modelo, os 3 únicos campos realmente
// exigidos pelo backend — Portador opcional) aparece dentro do PRÓPRIO
// modal, sem navegar pra `/equipamentos` (que continua existindo como
// cadastro completo, agora só alcançável por fora deste fluxo de O.S.).
// Ao gravar, auto-seleciona o equipamento recém-criado (`onPick`), sem
// round-trip de busca — os dados pra montar a linha já estão todos em
// mãos (código retornado + o que foi digitado/escolhido).
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import SelectField, { SelectOption } from "@/src/components/SelectField";

import { colors, radius, spacing } from "@/src/theme/colors";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { Connection } from "@/src/utils/storage/connections";
import { useAuditContext } from "@/src/hooks/useAuditContext";

const isCompactWeb = Platform.OS === "web";

export type EquipamentoRow = {
  codigo: number;
  cliente: number;
  numero_de_serie: string;
  numero_de_serie_int?: string | null;
  marca?: string | null;
  marca_descricao?: string | null;
  modelo?: string | null;
  modelo_descricao?: string | null;
  portador?: string | null;
  local?: string | null;
  tipo_equipamento: "A" | "C";
  detalhe_equipamento?: string | null;
  situacao_equipamento: string;
  descricao_equipamento?: string | null;
  valor?: number;
  revisao?: string | null;
};

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  cliente: number | null;
  term: string;
  setTerm: (v: string) => void;
  loading: boolean;
  results: EquipamentoRow[];
  onPick: (e: EquipamentoRow) => void;
};

export default function EquipamentoSearchModal({
  visible, onClose, conn, cliente, term, setTerm, loading, results, onPick,
}: Props) {
  const auditCtx = useAuditContext();
  const [criarOpen, setCriarOpen] = useState(false);
  const [marcasOpts, setMarcasOpts] = useState<SelectOption[]>([]);
  const [modelosOpts, setModelosOpts] = useState<SelectOption[]>([]);
  const [novoNumeroSerie, setNovoNumeroSerie] = useState("");
  const [novoMarca, setNovoMarca] = useState<string | null>(null);
  const [novoModelo, setNovoModelo] = useState<string | null>(null);
  const [novoPortador, setNovoPortador] = useState("");
  const [criarSaving, setCriarSaving] = useState(false);
  const [criarErro, setCriarErro] = useState<string | null>(null);

  useEffect(() => {
    if (!visible) { setCriarOpen(false); }
  }, [visible]);

  const abrirCriar = () => {
    setNovoNumeroSerie(term.trim());
    setNovoMarca(null);
    setNovoModelo(null);
    setNovoPortador("");
    setCriarErro(null);
    setCriarOpen(true);
    if (conn && marcasOpts.length === 0) {
      apiGet(conn, "/api/tabelas/marcas")
        .then((j) => { if (j?.success) setMarcasOpts((j.items || []).map((i: { codigo: string; descricao: string }) => ({ value: i.codigo, label: i.descricao }))); })
        .catch(() => {});
    }
  };

  useEffect(() => {
    if (!conn || !novoMarca) { setModelosOpts([]); return; }
    let ativo = true;
    apiGet(conn, "/api/tabelas/modelos", { cod_marca: novoMarca })
      .then((j) => {
        if (!ativo) return;
        setModelosOpts(j?.success ? (j.items || []).map((i: { codigo: string; descricao: string }) => ({ value: i.codigo, label: i.descricao })) : []);
      })
      .catch(() => { if (ativo) setModelosOpts([]); });
    return () => { ativo = false; };
  }, [conn, novoMarca]);

  const salvarNovo = async () => {
    if (!conn || !cliente) return;
    if (!novoNumeroSerie.trim()) { setCriarErro("Insira o Número de Série."); return; }
    if (!novoMarca) { setCriarErro("Defina a Marca."); return; }
    if (!novoModelo) { setCriarErro("Defina o Modelo."); return; }
    setCriarSaving(true);
    setCriarErro(null);
    try {
      const j = await apiSend(conn, "/api/equipamentos", "POST", {
        ...auditCtx,
        cliente,
        numero_de_serie: novoNumeroSerie.trim(),
        marca: novoMarca,
        modelo: novoModelo,
        portador: novoPortador.trim() || null,
      });
      if (!j?.success) {
        setCriarErro(friendlyApiError(j, "Não foi possível cadastrar o equipamento."));
        return;
      }
      onPick({
        codigo: j.codigo,
        cliente,
        numero_de_serie: novoNumeroSerie.trim(),
        marca: novoMarca,
        marca_descricao: marcasOpts.find((o) => o.value === novoMarca)?.label || null,
        modelo: novoModelo,
        modelo_descricao: modelosOpts.find((o) => o.value === novoModelo)?.label || null,
        portador: novoPortador.trim() || null,
        tipo_equipamento: "A",
        situacao_equipamento: "A",
      });
      setCriarOpen(false);
    } catch (e) {
      setCriarErro(friendlyCatchError(e, "Não foi possível cadastrar o equipamento."));
    } finally {
      setCriarSaving(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <Text style={styles.title}>{criarOpen ? "Novo Equipamento" : "Buscar Equipamento"}</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {criarOpen ? (
            <View style={{ gap: spacing.sm }}>
              <View>
                <Text style={styles.fieldLabel}>Número de Série *</Text>
                <TextInput
                  value={novoNumeroSerie}
                  onChangeText={setNovoNumeroSerie}
                  placeholder="Número de série"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  autoFocus
                  testID="equipamento-criar-numero-serie"
                />
              </View>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Marca *</Text>
                  <SelectField
                    value={novoMarca}
                    onChange={(v) => { setNovoMarca(v == null ? null : String(v)); setNovoModelo(null); }}
                    options={marcasOpts}
                    placeholder="Selecione…"
                    modalTitle="Marca"
                    compactWeb
                    testID="equipamento-criar-marca"
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Modelo *</Text>
                  <SelectField
                    value={novoModelo}
                    onChange={(v) => setNovoModelo(v == null ? null : String(v))}
                    options={modelosOpts}
                    placeholder="Selecione…"
                    modalTitle="Modelo"
                    disabled={!novoMarca}
                    compactWeb
                    testID="equipamento-criar-modelo"
                  />
                </View>
              </View>
              <View>
                <Text style={styles.fieldLabel}>Portador (opcional)</Text>
                <TextInput
                  value={novoPortador}
                  onChangeText={setNovoPortador}
                  placeholder="Quem está com o equipamento"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="equipamento-criar-portador"
                />
              </View>
              <Text style={styles.hint}>
                Cadastro rápido — Local, Data de Revisão e demais campos podem ser preenchidos depois em
                Cadastros &gt; Equipamentos.
              </Text>
              {criarErro ? <Text style={styles.erro}>{criarErro}</Text> : null}
              <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.xs }}>
                <Pressable style={styles.secondaryBtn} onPress={() => setCriarOpen(false)} disabled={criarSaving} testID="equipamento-criar-voltar">
                  <Text style={styles.secondaryBtnText}>Voltar</Text>
                </Pressable>
                <Pressable
                  style={[styles.primaryBtn, { flex: 1 }, criarSaving && { opacity: 0.7 }]}
                  onPress={salvarNovo}
                  disabled={criarSaving}
                  testID="equipamento-criar-salvar"
                >
                  {criarSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Gravar</Text>}
                </Pressable>
              </View>
            </View>
          ) : (
            <>
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={term}
                  onChangeText={setTerm}
                  placeholder="Nº de série, descrição, portador ou local…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  autoFocus
                  testID="equipamento-search-input"
                  autoComplete="off"
                  autoCorrect={false}
                  textContentType="none"
                  importantForAutofill="no"
                />
              </View>

              {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

              <ScrollView style={{ maxHeight: 380 }}>
                {results.map((e) => (
                  <Pressable
                    key={e.codigo}
                    onPress={() => onPick(e)}
                    style={({ pressed }) => [styles.row, pressed && { backgroundColor: colors.brandTertiary }]}
                    testID={`equipamento-search-result-${e.codigo}`}
                  >
                    <View style={{ flex: 1 }}>
                      <Text style={styles.rowNome} numberOfLines={1}>{e.numero_de_serie}</Text>
                      <Text style={styles.rowSub} numberOfLines={1}>
                        {[e.marca_descricao, e.modelo_descricao, e.descricao_equipamento].filter(Boolean).join(" · ") || "—"}
                      </Text>
                    </View>
                    <View style={[styles.badge, e.tipo_equipamento === "C" ? styles.badgeContrato : styles.badgeAvulso]}>
                      <Text style={styles.badgeText}>{e.tipo_equipamento === "C" ? "Contrato" : "Avulso"}</Text>
                    </View>
                    <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                  </Pressable>
                ))}
                {!loading && term.trim().length >= 2 && results.length === 0 ? (
                  <View style={{ padding: spacing.md }}>
                    <Text style={styles.vazio}>Nenhum equipamento encontrado para este cliente.</Text>
                    <Pressable style={styles.cadastrarBtn} onPress={abrirCriar} testID="equipamento-cadastrar-novo">
                      <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                      <Text style={styles.cadastrarBtnText}>Cadastrar novo equipamento</Text>
                    </Pressable>
                  </View>
                ) : null}
              </ScrollView>
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
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
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
  badge: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.sm },
  badgeAvulso: { backgroundColor: "#DCFCE7" },
  badgeContrato: { backgroundColor: "#DBEAFE" },
  badgeText: { fontSize: 10, fontWeight: "700", color: "#1F2933" },
  vazio: { color: colors.muted, fontSize: 13, textAlign: "center" },
  cadastrarBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.xs,
    marginTop: spacing.sm, paddingVertical: 10,
  },
  cadastrarBtnText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "600" },
  fieldLabel: { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "600" },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  hint: { fontSize: 11, color: colors.muted, fontStyle: "italic" },
  erro: { fontSize: 12, color: colors.error },
  primaryBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm, paddingVertical: 12,
    alignItems: "center", justifyContent: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "700" },
  secondaryBtn: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingVertical: 12,
    paddingHorizontal: spacing.lg, alignItems: "center", justifyContent: "center",
  },
  secondaryBtnText: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },
});
