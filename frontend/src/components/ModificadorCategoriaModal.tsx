// Modal de edição de uma Categoria de Modificador — extraído de
// app/modificadores.tsx pra ser reaproveitado também a partir do botão
// "Adicionar" de ModificadoresSection.tsx (retrofit em Produto Completo/
// Serviços), evitando ter 2 telas diferentes pra criar/editar a mesma
// categoria. Ver PENDENCIAS.md > "Modificadores".
//
// Mesmo padrão de props "api/servidor/banco separados" já usado em
// ModificadoresSection.tsx/GestorDocumentosSection.tsx — usa fetch() cru,
// não apiGet/apiSend, pra funcionar com os dois formatos de conexão que os
// chamadores guardam (Connection completo em app/modificadores.tsx, objeto
// simples nas telas "Completo").
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useAuditContext } from "@/src/hooks/useAuditContext";
import { friendlyApiError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as pedidoStyles } from "@/src/components/pedido/styles";

const isWeb = Platform.OS === "web";

type ModificadorItem = {
  codigo?: number | null;
  nome: string;
  acrescimo: string;
  desconto: string;
  situacao: "A" | "D";
};

type ItemAssociado = { tipo: "P" | "S"; codigo: string; descricao: string };

type Props = {
  visible: boolean;
  api: string;
  servidor: string;
  banco: string;
  codigo: number | null; // categoria sendo editada; null = nova
  onClose: () => void;
  onSaved: (categoria: { codigo: number; nome: string }) => void;
  onDeleted?: () => void;
  podeGravar: boolean;
  podeExcluir: boolean;
};

export default function ModificadorCategoriaModal({
  visible, api, servidor, banco, codigo, onClose, onSaved, onDeleted, podeGravar, podeExcluir,
}: Props) {
  const fb = useFeedback();
  const auditCtx = useAuditContext();
  const base = api.replace(/\/+$/, "");
  const qsConn = `servidor=${encodeURIComponent(servidor)}&banco=${encodeURIComponent(banco)}`;

  const [carregandoDetalhe, setCarregandoDetalhe] = useState(false);
  const [nome, setNome] = useState("");
  const [obrigatorio, setObrigatorio] = useState(true);
  const [selecaoMultipla, setSelecaoMultipla] = useState(false);
  const [modificadores, setModificadores] = useState<ModificadorItem[]>([]);
  const [itensAssociados, setItensAssociados] = useState<ItemAssociado[]>([]);
  const [salvando, setSalvando] = useState(false);
  const [excluindo, setExcluindo] = useState(false);

  const [associarOpen, setAssociarOpen] = useState(false);
  const [buscaItem, setBuscaItem] = useState("");
  const [resultadosBusca, setResultadosBusca] = useState<{ tipo: "P" | "S"; codigo: string; descricao: string }[]>([]);
  const [buscandoItem, setBuscandoItem] = useState(false);

  useEffect(() => {
    if (!visible) return;
    if (codigo == null) {
      setNome(""); setObrigatorio(true); setSelecaoMultipla(false);
      setModificadores([]); setItensAssociados([]);
      return;
    }
    (async () => {
      setCarregandoDetalhe(true);
      try {
        const r = await fetch(`${base}/api/modificadores/categorias/${codigo}?${qsConn}`);
        const j = await r.json();
        if (j?.success) {
          setNome(j.nome);
          setObrigatorio(j.obrigatorio);
          setSelecaoMultipla(j.selecao_multipla);
          setModificadores((j.modificadores || []).map((m: any) => ({
            codigo: m.codigo, nome: m.nome, acrescimo: String(m.acrescimo ?? 0).replace(".", ","),
            desconto: String(m.desconto ?? 0).replace(".", ","), situacao: m.situacao === "D" ? "D" : "A",
          })));
          setItensAssociados(j.itens_associados || []);
        } else {
          fb.showError(friendlyApiError(j, "Não foi possível abrir esta categoria."));
        }
      } catch (e) {
        fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setCarregandoDetalhe(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, codigo, base, qsConn]);

  const addModificador = useCallback(() => {
    setModificadores((prev) => [...prev, { nome: "", acrescimo: "0", desconto: "0", situacao: "A" }]);
  }, []);

  const removeModificador = useCallback((idx: number) => {
    setModificadores((prev) => prev.filter((_, i) => i !== idx));
  }, []);

  const updateModificador = useCallback((idx: number, patch: Partial<ModificadorItem>) => {
    setModificadores((prev) => prev.map((m, i) => (i === idx ? { ...m, ...patch } : m)));
  }, []);

  const salvar = useCallback(async () => {
    if (!nome.trim()) { fb.showError("Informe o nome da categoria."); return; }
    if (modificadores.some((m) => !m.nome.trim())) { fb.showError("Todo modificador precisa de um nome."); return; }
    setSalvando(true);
    try {
      const r = await fetch(`${base}/api/modificadores/categorias`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor, banco,
          codigo,
          nome: nome.trim(),
          obrigatorio,
          selecao_multipla: selecaoMultipla,
          modificadores: modificadores.map((m) => ({
            codigo: m.codigo ?? null,
            nome: m.nome.trim(),
            acrescimo: parseFloat((m.acrescimo || "0").replace(",", ".")) || 0,
            desconto: parseFloat((m.desconto || "0").replace(",", ".")) || 0,
            situacao: m.situacao,
          })),
          itens_associados: itensAssociados.map((i) => ({ tipo: i.tipo, codigo: i.codigo })),
          ...auditCtx,
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Categoria de modificador gravada.");
        onSaved({ codigo: j.codigo ?? codigo, nome: nome.trim() });
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível gravar a categoria."));
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSalvando(false);
    }
  }, [base, servidor, banco, codigo, nome, obrigatorio, selecaoMultipla, modificadores, itensAssociados, auditCtx, fb, onSaved]);

  const excluir = useCallback(() => {
    if (!codigo) return;
    fb.showConfirm(
      `Confirma excluir a categoria "${nome}"? Os ${modificadores.length} modificador(es) e todas as associações com produtos/serviços serão excluídos junto.`,
      async () => {
        setExcluindo(true);
        try {
          const r = await fetch(`${base}/api/modificadores/categorias/${codigo}`, {
            method: "DELETE",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ servidor, banco, ...auditCtx }),
          });
          const j = await r.json();
          if (j?.success) {
            fb.showSuccess(j.message || "Categoria excluída.");
            onDeleted?.();
          } else {
            fb.showError(friendlyApiError(j, "Não foi possível excluir a categoria."));
          }
        } catch (e) {
          fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        } finally {
          setExcluindo(false);
        }
      },
    );
  }, [codigo, nome, modificadores.length, base, servidor, banco, auditCtx, fb, onDeleted]);

  const buscarItens = useCallback(async (termo: string) => {
    setBuscandoItem(true);
    try {
      const r = await fetch(`${base}/api/produtos-servicos?${qsConn}&search=${encodeURIComponent(termo)}&tipo=all&size=30`);
      const j = await r.json();
      if (j?.success) setResultadosBusca((j.items || []).map((it: any) => ({ tipo: it.tipo, codigo: it.codigo, descricao: it.descricao })));
    } catch {
      setResultadosBusca([]);
    } finally {
      setBuscandoItem(false);
    }
  }, [base, qsConn]);

  useEffect(() => {
    if (!associarOpen) return;
    const t = setTimeout(() => buscarItens(buscaItem), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [associarOpen, buscaItem]);

  const jaAssociado = useCallback(
    (tipo: string, codigo2: string) => itensAssociados.some((i) => i.tipo === tipo && i.codigo === codigo2),
    [itensAssociados],
  );

  const toggleAssociado = useCallback((item: { tipo: "P" | "S"; codigo: string; descricao: string }) => {
    setItensAssociados((prev) => {
      if (prev.some((i) => i.tipo === item.tipo && i.codigo === item.codigo)) {
        return prev.filter((i) => !(i.tipo === item.tipo && i.codigo === item.codigo));
      }
      return [...prev, item];
    });
  }, []);

  const removerAssociado = useCallback((tipo: string, codigo2: string) => {
    setItensAssociados((prev) => prev.filter((i) => !(i.tipo === tipo && i.codigo === codigo2)));
  }, []);

  return (
    <>
      <AppModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={onClose}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact, styles.editorCard]} onPress={(e) => e.stopPropagation()}>
            {carregandoDetalhe ? (
              <ActivityIndicator size="small" color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />
            ) : (
              <ScrollView>
                <View style={pedidoStyles.modalHeader}>
                  <Text style={pedidoStyles.modalTitle}>{codigo ? "Editar Categoria" : "Nova Categoria"}</Text>
                  <Pressable onPress={onClose} hitSlop={8} testID="modificadores-editor-fechar">
                    <Ionicons name="close" size={22} color={colors.muted} />
                  </Pressable>
                </View>

                <Text style={styles.fieldLabel}>Nome da categoria</Text>
                <TextInput
                  style={styles.input}
                  value={nome}
                  onChangeText={setNome}
                  maxLength={150}
                  placeholder="Ex.: Ponto da Carne"
                  testID="modificadores-nome"
                />

                <Text style={styles.fieldLabel}>Condição</Text>
                <View style={styles.radioRow}>
                  <Pressable style={styles.radioOpt} onPress={() => setObrigatorio(true)} testID="modificadores-obrigatorio">
                    <Ionicons name={obrigatorio ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.radioLabel}>Obrigatório</Text>
                  </Pressable>
                  <Pressable style={styles.radioOpt} onPress={() => setObrigatorio(false)} testID="modificadores-opcional">
                    <Ionicons name={!obrigatorio ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.radioLabel}>Opcional</Text>
                  </Pressable>
                </View>

                <Text style={styles.fieldLabel}>Nessa categoria, o cliente pode selecionar</Text>
                <View style={styles.radioRow}>
                  <Pressable style={styles.radioOpt} onPress={() => setSelecaoMultipla(false)} testID="modificadores-selecao-unica">
                    <Ionicons name={!selecaoMultipla ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.radioLabel}>Apenas um modificador</Text>
                  </Pressable>
                  <Pressable style={styles.radioOpt} onPress={() => setSelecaoMultipla(true)} testID="modificadores-selecao-varios">
                    <Ionicons name={selecaoMultipla ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={styles.radioLabel}>Vários</Text>
                  </Pressable>
                </View>

                <View style={styles.sectionSep} />
                <Text style={styles.fieldLabel}>Modificadores desta categoria ({modificadores.length})</Text>
                {modificadores.map((m, idx) => (
                  <View key={idx} style={styles.modRow}>
                    <View style={styles.modRowFields}>
                      <View style={styles.colFlex}>
                        <Text style={styles.miniLabel}>Nome do modificador</Text>
                        <TextInput
                          style={styles.input}
                          value={m.nome}
                          onChangeText={(v) => updateModificador(idx, { nome: v })}
                          testID={`modificadores-mod-nome-${idx}`}
                        />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.miniLabel}>Acréscimo R$</Text>
                        <TextInput
                          style={styles.input}
                          value={m.acrescimo}
                          onChangeText={(v) => updateModificador(idx, { acrescimo: v })}
                          keyboardType="numeric"
                          testID={`modificadores-mod-acrescimo-${idx}`}
                        />
                      </View>
                      <View style={styles.colTiny}>
                        <Text style={styles.miniLabel}>Desconto R$</Text>
                        <TextInput
                          style={styles.input}
                          value={m.desconto}
                          onChangeText={(v) => updateModificador(idx, { desconto: v })}
                          keyboardType="numeric"
                          testID={`modificadores-mod-desconto-${idx}`}
                        />
                      </View>
                      <Pressable
                        style={styles.situacaoBtn}
                        onPress={() => updateModificador(idx, { situacao: m.situacao === "A" ? "D" : "A" })}
                        testID={`modificadores-mod-situacao-${idx}`}
                      >
                        <Ionicons
                          name={m.situacao === "A" ? "checkmark-circle" : "close-circle-outline"}
                          size={22}
                          color={m.situacao === "A" ? colors.success : colors.muted}
                        />
                      </Pressable>
                      <Pressable onPress={() => removeModificador(idx)} hitSlop={8} testID={`modificadores-mod-remover-${idx}`}>
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    </View>
                  </View>
                ))}
                <Pressable style={styles.addModBtn} onPress={addModificador} testID="modificadores-mod-adicionar">
                  <Ionicons name="add" size={16} color={colors.brandPrimary} />
                  <Text style={styles.addModBtnText}>Adicionar modificador</Text>
                </Pressable>

                <View style={styles.sectionSep} />
                <View style={styles.rowFieldsBetween}>
                  <Text style={styles.fieldLabel}>Produtos/Serviços associados ({itensAssociados.length})</Text>
                  <Pressable style={styles.secondaryBtnSm} onPress={() => setAssociarOpen(true)} testID="modificadores-associar-abrir">
                    <Ionicons name="link-outline" size={14} color={colors.onSurface} />
                    <Text style={styles.secondaryBtnSmText}>Associar</Text>
                  </Pressable>
                </View>
                {itensAssociados.length === 0 ? (
                  <Text style={styles.muted}>Nenhum produto/serviço associado ainda.</Text>
                ) : (
                  itensAssociados.map((it) => (
                    <View key={`${it.tipo}-${it.codigo}`} style={styles.itemAssocRow}>
                      <Text style={styles.itemAssocTipo}>{it.tipo === "P" ? "Produto" : "Serviço"}</Text>
                      <Text style={styles.itemAssocDesc} numberOfLines={1}>{it.codigo} — {it.descricao}</Text>
                      <Pressable onPress={() => removerAssociado(it.tipo, it.codigo)} hitSlop={8} testID={`modificadores-associado-remover-${it.tipo}-${it.codigo}`}>
                        <Ionicons name="close" size={16} color={colors.error} />
                      </Pressable>
                    </View>
                  ))
                )}

                <View style={styles.editorActions}>
                  {codigo && podeExcluir ? (
                    <Pressable style={[styles.dangerBtn, excluindo && styles.btnDisabled]} onPress={excluir} disabled={excluindo} testID="modificadores-excluir">
                      {excluindo ? <ActivityIndicator size="small" color={colors.error} /> : <Ionicons name="trash-outline" size={16} color={colors.error} />}
                      <Text style={styles.dangerBtnText}>Excluir</Text>
                    </Pressable>
                  ) : <View />}
                  {podeGravar ? (
                    <Pressable style={[styles.primaryBtn, salvando && styles.btnDisabled]} onPress={salvar} disabled={salvando} testID="modificadores-gravar">
                      {salvando ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : <Ionicons name="save-outline" size={16} color={colors.onBrandPrimary} />}
                      <Text style={styles.primaryBtnText}>{salvando ? "Gravando…" : "Gravar"}</Text>
                    </Pressable>
                  ) : null}
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </AppModal>

      <AppModal visible={associarOpen} transparent animationType="fade" onRequestClose={() => setAssociarOpen(false)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setAssociarOpen(false)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Associar Produto/Serviço</Text>
              <Pressable onPress={() => setAssociarOpen(false)} hitSlop={8} testID="modificadores-associar-fechar">
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <TextInput
              style={styles.input}
              value={buscaItem}
              onChangeText={setBuscaItem}
              placeholder="Buscar produto ou serviço..."
              autoFocus={isWeb}
              testID="modificadores-associar-busca"
            />
            <ScrollView style={{ maxHeight: 360, marginTop: spacing.sm }}>
              {buscandoItem ? (
                <ActivityIndicator size="small" color={colors.brandPrimary} style={{ marginTop: spacing.md }} />
              ) : resultadosBusca.length === 0 ? (
                <Text style={styles.muted}>Nenhum resultado.</Text>
              ) : (
                resultadosBusca.map((it) => {
                  const sel = jaAssociado(it.tipo, it.codigo);
                  return (
                    <Pressable
                      key={`${it.tipo}-${it.codigo}`}
                      style={styles.buscaItemRow}
                      onPress={() => toggleAssociado(it)}
                      testID={`modificadores-associar-item-${it.tipo}-${it.codigo}`}
                    >
                      <Ionicons name={sel ? "checkbox" : "square-outline"} size={18} color={sel ? colors.brandPrimary : colors.muted} />
                      <Text style={styles.itemAssocTipo}>{it.tipo === "P" ? "Produto" : "Serviço"}</Text>
                      <Text style={styles.itemAssocDesc} numberOfLines={1}>{it.codigo} — {it.descricao}</Text>
                    </Pressable>
                  );
                })
              )}
            </ScrollView>
            <Pressable style={[styles.primaryBtn, { alignSelf: "flex-end", marginTop: spacing.md }]} onPress={() => setAssociarOpen(false)} testID="modificadores-associar-concluir">
              <Text style={styles.primaryBtnText}>Concluído ({itensAssociados.length})</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>
    </>
  );
}

const styles = StyleSheet.create({
  editorCard: { maxHeight: "88%" },
  muted: { fontSize: 13, color: colors.muted, textAlign: "center", paddingVertical: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, fontWeight: "600", marginTop: spacing.sm, marginBottom: 4 },
  miniLabel: { fontSize: 10, color: colors.muted, marginBottom: 2 },
  input: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  radioRow: { flexDirection: "row", gap: spacing.lg },
  radioOpt: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 4 },
  radioLabel: { fontSize: 13, color: colors.onSurface },
  sectionSep: { height: 1, backgroundColor: colors.border, marginVertical: spacing.md },
  modRow: { marginBottom: spacing.sm },
  modRowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  colFlex: { flex: 1, minWidth: 0 },
  colTiny: { width: 90 },
  situacaoBtn: { paddingBottom: 8 },
  addModBtn: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4, alignSelf: "flex-start" },
  addModBtnText: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  rowFieldsBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  itemAssocRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 6, borderTopWidth: 1, borderTopColor: colors.border,
  },
  itemAssocTipo: {
    fontSize: 10, fontWeight: "700", color: colors.brandPrimary, textTransform: "uppercase",
    backgroundColor: colors.brandTertiary, borderRadius: radius.sm, paddingHorizontal: 6, paddingVertical: 2,
  },
  itemAssocDesc: { flex: 1, fontSize: 13, color: colors.onSurface },
  editorActions: { flexDirection: "row", justifyContent: "space-between", marginTop: spacing.lg, marginBottom: spacing.sm },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  secondaryBtnSm: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: 6,
  },
  secondaryBtnSmText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  dangerBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.error,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  dangerBtnText: { color: colors.error, fontSize: 13, fontWeight: "600" },
  btnDisabled: { opacity: 0.6 },
  buscaItemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border,
  },
});
