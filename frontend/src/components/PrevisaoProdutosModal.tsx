// Previsão de Produtos (composição de materiais de um serviço) — legado:
// FrmManReceita.frm ("Produtos Compostos / Previsão de produtos por
// serviço"), aberto como sub-tela a partir do botão "Previsão de Produtos"
// em Serviços. Backend: services/produtos_compostos_service.py.
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useAuditContext } from "@/src/hooks/useAuditContext";

import { Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

const isCompactWeb = Platform.OS === "web";

type ItemComposicao = {
  codigo: number;
  vinculado: string;
  cod_fab: string;
  descricao: string;
  qtd: number;
  valor_no_kit: number;
  unidade: string;
};

type ProdutoOpt = { codigo: string; descricao: string; cod_fab: string; valor: number; unidade: string };

type Props = {
  visible: boolean;
  conn: Connection | null;
  principal: string;
  principalLabel?: string;
  onClose: () => void;
  canEdit: boolean;
};

export default function PrevisaoProdutosModal({ visible, conn, principal, principalLabel, onClose, canEdit }: Props) {
  const fb = useFeedback();
  const auditCtx = useAuditContext();
  const [items, setItems] = useState<ItemComposicao[]>([]);
  const [loading, setLoading] = useState(false);

  const [busca, setBusca] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [opcoes, setOpcoes] = useState<ProdutoOpt[]>([]);
  const [selecionado, setSelecionado] = useState<ProdutoOpt | null>(null);
  const [qtd, setQtd] = useState("");
  const [valor, setValor] = useState("");
  const [descricao, setDescricao] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!conn || !principal) return;
    setLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `principal=${encodeURIComponent(principal)}&servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/produtos-compostos?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, [conn, principal]);

  useEffect(() => {
    if (visible) {
      load();
      setBusca(""); setOpcoes([]); setSelecionado(null); setQtd(""); setValor(""); setDescricao("");
    }
  }, [visible, load]);

  useEffect(() => {
    if (!conn || !visible || !busca.trim() || selecionado) { setOpcoes([]); return; }
    const t = setTimeout(async () => {
      setBuscando(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const qs = `search=${encodeURIComponent(busca.trim())}&tipo=P&size=20&servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
        const r = await fetch(`${base}/api/produtos-servicos?${qs}`);
        const j = await r.json();
        setOpcoes(j?.success ? (j.items || []).map((i: any) => ({
          codigo: i.codigo, descricao: i.descricao, cod_fab: i.cod_fab || "", valor: i.valor || 0, unidade: i.unidade || "",
        })) : []);
      } catch { setOpcoes([]); } finally { setBuscando(false); }
    }, 350);
    return () => clearTimeout(t);
  }, [busca, conn, visible, selecionado]);

  const escolherProduto = (p: ProdutoOpt) => {
    setSelecionado(p);
    setBusca(`${p.cod_fab ? p.cod_fab + " — " : ""}${p.descricao}`);
    setOpcoes([]);
    if (!valor.trim()) setValor(String(p.valor ?? ""));
  };

  const limparSelecao = () => {
    setSelecionado(null);
    setBusca("");
    setOpcoes([]);
  };

  const num = (s: string): number => (s.trim() ? parseFloat(s.replace(",", ".")) || 0 : 0);

  const adicionar = async () => {
    if (!conn) return;
    if (!selecionado) { fb.showWarning("Busque e selecione um produto."); return; }
    if (!qtd.trim() || num(qtd) <= 0) { fb.showWarning("Informe uma Quantidade maior que zero."); return; }
    setSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/produtos-compostos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco, ...auditCtx,
          principal, vinculado: selecionado.codigo, qtd: num(qtd), valor_no_kit: num(valor), descricao_no_kit: descricao.trim(),
        }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Item adicionado.");
        limparSelecao(); setQtd(""); setValor(""); setDescricao("");
        load();
      } else fb.showError(j?.message || "Falha ao adicionar.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); } finally { setSaving(false); }
  };

  const excluir = async (item: ItemComposicao) => {
    if (!conn) return;
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/produtos-compostos/${item.codigo}/excluir`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: conn.servidor, banco: conn.banco, ...auditCtx, principal }),
      });
      const j = await r.json();
      if (j?.success) { fb.showSuccess(j.message || "Item removido."); load(); }
      else fb.showError(j?.message || "Falha ao excluir.");
    } catch (e) { fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); }
  };

  const totalComposicao = useMemo(
    () => items.reduce((acc, i) => acc + i.qtd * (i.valor_no_kit || 0), 0),
    [items]
  );

  return (
    <AppModal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.bg, isCompactWeb && styles.bgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.card, isCompactWeb && styles.cardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.header}>
            <View style={{ flex: 1 }}>
              <Text style={styles.title}>Previsão de Produtos</Text>
              <Text style={styles.subtitle} numberOfLines={1}>{principalLabel || principal}</Text>
            </View>
            <Pressable onPress={onClose} hitSlop={8}>
              <Ionicons name="close" size={22} color={colors.muted} />
            </Pressable>
          </View>

          {canEdit ? (
            <View style={styles.form}>
              <Text style={styles.label}>Produto</Text>
              <View style={styles.searchWrap}>
                <Ionicons name="search" size={16} color={colors.muted} />
                <TextInput
                  value={busca}
                  onChangeText={(v) => { setBusca(v); if (selecionado) setSelecionado(null); }}
                  placeholder="Buscar por código ou descrição…"
                  placeholderTextColor={colors.muted}
                  style={styles.searchInput}
                  testID="prev-produtos-busca"
                />
                {selecionado ? (
                  <Pressable onPress={limparSelecao} hitSlop={6}>
                    <Ionicons name="close-circle" size={18} color={colors.muted} />
                  </Pressable>
                ) : null}
              </View>
              {buscando ? <ActivityIndicator size="small" color={colors.brandPrimary} style={{ marginTop: 4 }} /> : null}
              {opcoes.length > 0 && !selecionado ? (
                <View style={styles.opcoesBox}>
                  {opcoes.map((o) => (
                    <Pressable key={o.codigo} onPress={() => escolherProduto(o)} style={styles.opcaoRow} testID={`prev-produtos-opt-${o.codigo}`}>
                      <Text style={styles.opcaoDesc} numberOfLines={1}>{o.descricao}</Text>
                      <Text style={styles.opcaoCod}>{o.cod_fab || o.codigo}</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}

              <View style={styles.rowFields}>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Quantidade *</Text>
                  <TextInput value={qtd} onChangeText={setQtd} style={styles.input} keyboardType="decimal-pad" testID="prev-produtos-qtd" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Valor</Text>
                  <TextInput value={valor} onChangeText={setValor} style={styles.input} keyboardType="decimal-pad" testID="prev-produtos-valor" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Descrição no kit</Text>
                  <TextInput value={descricao} onChangeText={setDescricao} style={styles.input} placeholder="Opcional" placeholderTextColor={colors.muted} testID="prev-produtos-descricao" />
                </View>
              </View>

              <Pressable onPress={adicionar} disabled={saving} style={[styles.addBtn, saving && { opacity: 0.6 }]} testID="prev-produtos-adicionar">
                {saving ? <ActivityIndicator color="#fff" size="small" /> : (
                  <>
                    <Ionicons name="add" size={18} color="#fff" />
                    <Text style={styles.addBtnText}>Adicionar</Text>
                  </>
                )}
              </Pressable>
            </View>
          ) : null}

          <Text style={styles.sectionTitle}>Itens da Composição</Text>
          <ScrollView style={{ maxHeight: 280 }}>
            {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
            {!loading && items.length === 0 ? <Text style={styles.vazio}>Nenhum item na composição.</Text> : null}
            {items.map((i) => (
              <View key={i.codigo} style={styles.itemRow} testID={`prev-produtos-item-${i.codigo}`}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemDesc} numberOfLines={1}>{i.descricao}</Text>
                  <Text style={styles.itemSub}>
                    {i.cod_fab || i.vinculado} · Qtd {i.qtd} {i.unidade}{i.valor_no_kit ? ` · R$ ${i.valor_no_kit.toFixed(2)}` : ""}
                  </Text>
                </View>
                {canEdit ? (
                  <Pressable onPress={() => excluir(i)} hitSlop={8} testID={`prev-produtos-del-${i.codigo}`}>
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                ) : null}
              </View>
            ))}
          </ScrollView>
          {items.length > 0 ? (
            <Text style={styles.total}>Total estimado: R$ {totalComposicao.toFixed(2)}</Text>
          ) : null}
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
    width: "100%", maxWidth: 640, alignSelf: "center", maxHeight: "85%",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
  header: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", marginBottom: spacing.md },
  title: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
  subtitle: { fontSize: 12, color: colors.muted, marginTop: 2 },
  form: { borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: spacing.md, marginBottom: spacing.md, backgroundColor: colors.surfaceSecondary },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginBottom: 4 },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: 8,
    borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  opcoesBox: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, marginTop: 4, maxHeight: 160, overflow: "hidden" },
  opcaoRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  opcaoDesc: { fontSize: 13, color: colors.onSurface, flex: 1, marginRight: spacing.sm },
  opcaoCod: { fontSize: 11, color: colors.muted },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", marginTop: spacing.sm },
  colTiny: { width: 90 },
  colNarrow: { width: 110 },
  colFlex: { flex: 1, minWidth: 0 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 9, fontSize: 14, color: colors.onSurface },
  addBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 6, backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingVertical: 10, marginTop: spacing.md },
  addBtnText: { color: "#fff", fontWeight: "700", fontSize: 13 },
  sectionTitle: { fontSize: 13, fontWeight: "700", color: colors.brandPrimary, marginBottom: spacing.xs },
  vazio: { color: colors.muted, fontSize: 13, textAlign: "center", padding: spacing.md },
  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },
  itemDesc: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  itemSub: { fontSize: 11, color: colors.muted, marginTop: 2 },
  total: { fontSize: 12, color: colors.onSurface, fontWeight: "700", textAlign: "right", marginTop: spacing.sm },
});
