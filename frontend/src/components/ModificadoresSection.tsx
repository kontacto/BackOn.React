// Modificadores — associação "pelo outro lado" (a partir do cadastro de
// Produto Completo/Serviços), reaproveitando os MESMOS endpoints já usados
// pela tela principal de Modificadores (Cadastros > Tabelas Auxiliares).
// Componente genérico (mesmo espírito de GestorDocumentosSection.tsx) pra
// não duplicar a lógica de associação entre as duas telas que precisam
// dela. Ver backend/services/modificadores_service.py e PENDENCIAS.md >
// "Modificadores".
//
// Só pode ser usado com o registro (produto/serviço) já salvo — mesma
// regra "relacionados travados até o pai existir" já documentada em
// CLAUDE.md > "Global Entity Rules" pra telefones/endereços/anexos.
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";

import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import ModificadorCategoriaModal from "@/src/components/ModificadorCategoriaModal";
import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { friendlyApiError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { styles as pedidoStyles } from "@/src/components/pedido/styles";

const isWeb = Platform.OS === "web";

type CategoriaAssociada = { codigo: number; nome: string };
type CategoriaResumo = { codigo: number; nome: string; obrigatorio: boolean; selecao_multipla: boolean };

// Mesmo padrão de props de GestorDocumentosSection.tsx (api/servidor/banco
// separados, não um objeto `Connection` — o chamador aqui é uma tela
// "Completo" que já guarda a conexão nesse formato mais simples).
type Props = {
  api: string;
  servidor: string;
  banco: string;
  tipo: "P" | "S";
  codigo: string | null;
  podeGravar: boolean;
};

export default function ModificadoresSection({ api, servidor, banco, tipo, codigo, podeGravar }: Props) {
  const fb = useFeedback();
  const { can } = usePermissions();
  const podeIncluirModificador = can("MODIFICADORES.GRAVAR");
  const base = api.replace(/\/+$/, "");
  const qsConn = `servidor=${encodeURIComponent(servidor)}&banco=${encodeURIComponent(banco)}`;

  const [carregando, setCarregando] = useState(false);
  const [associadas, setAssociadas] = useState<CategoriaAssociada[]>([]);
  const [modalOpen, setModalOpen] = useState(false);
  const [todasCategorias, setTodasCategorias] = useState<CategoriaResumo[]>([]);
  const [busca, setBusca] = useState("");
  const [selecionadas, setSelecionadas] = useState<Set<number>>(new Set());
  const [salvando, setSalvando] = useState(false);
  const [novaCategoriaOpen, setNovaCategoriaOpen] = useState(false);

  const carregar = useCallback(async () => {
    if (!codigo) { setAssociadas([]); return; }
    setCarregando(true);
    try {
      const r = await fetch(`${base}/api/modificadores/por-item/${tipo}/${encodeURIComponent(codigo)}?${qsConn}`);
      const j = await r.json();
      if (j?.success) setAssociadas(j.items || []);
    } catch {
      setAssociadas([]);
    } finally {
      setCarregando(false);
    }
  }, [base, qsConn, tipo, codigo]);

  useEffect(() => { carregar(); }, [carregar]);

  const abrirModal = useCallback(async () => {
    try {
      const r = await fetch(`${base}/api/modificadores/categorias?${qsConn}`);
      const j = await r.json();
      if (j?.success) setTodasCategorias(j.items || []);
    } catch {
      setTodasCategorias([]);
    }
    setSelecionadas(new Set(associadas.map((c) => c.codigo)));
    setBusca("");
    setModalOpen(true);
  }, [base, qsConn, associadas]);

  const toggle = useCallback((cod: number) => {
    setSelecionadas((prev) => {
      const next = new Set(prev);
      if (next.has(cod)) next.delete(cod);
      else next.add(cod);
      return next;
    });
  }, []);

  const salvar = useCallback(async () => {
    if (!codigo) return;
    setSalvando(true);
    try {
      const r = await fetch(`${base}/api/modificadores/por-item/${tipo}/${encodeURIComponent(codigo)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor, banco, categorias: Array.from(selecionadas) }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess("Modificadores associados.");
        setModalOpen(false);
        carregar();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível associar os modificadores."));
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setSalvando(false);
    }
  }, [base, servidor, banco, tipo, codigo, selecionadas, fb, carregar]);

  // Cria uma categoria nova (modal compartilhado com Tabelas Auxiliares >
  // Modificadores) e já associa ao item atual — pedido explícito do
  // usuário (2026-07-23): "assim não precisamos abrir o cadastro do
  // modificador em tabelas auxiliares toda vez que precisarmos incluir um
  // novo". Botão gated pela MESMA permissão MODIFICADORES.GRAVAR (não a
  // permissão do produto/serviço, que só controla "Gerenciar").
  const handleNovaCategoriaSaved = useCallback(async (categoria: { codigo: number; nome: string }) => {
    setNovaCategoriaOpen(false);
    if (!codigo) return;
    try {
      const novasCategorias = [...associadas.map((a) => a.codigo), categoria.codigo];
      const r = await fetch(`${base}/api/modificadores/por-item/${tipo}/${encodeURIComponent(codigo)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor, banco, categorias: novasCategorias }),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(`Categoria "${categoria.nome}" criada e associada.`);
        carregar();
      } else {
        fb.showError(friendlyApiError(j, "Categoria criada, mas não foi possível associá-la automaticamente."));
      }
    } catch (e) {
      fb.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    }
  }, [base, servidor, banco, tipo, codigo, associadas, fb, carregar]);

  const categoriasFiltradas = todasCategorias.filter((c) => c.nome.toUpperCase().includes(busca.toUpperCase()));

  if (!codigo) {
    return (
      <Text style={styles.hint}>Grave o cadastro pelo menos uma vez pra poder associar modificadores.</Text>
    );
  }

  return (
    <View>
      <View style={styles.headerRow}>
        <Text style={styles.title}>Modificadores associados ({associadas.length})</Text>
        <View style={styles.headerBtns}>
          {podeIncluirModificador ? (
            <Pressable style={styles.manageBtn} onPress={() => setNovaCategoriaOpen(true)} testID={`modificadores-section-adicionar-${tipo}`}>
              <Ionicons name="add" size={14} color={colors.onSurface} />
              <Text style={styles.manageBtnText}>Adicionar</Text>
            </Pressable>
          ) : null}
          {podeGravar ? (
            <Pressable style={styles.manageBtn} onPress={abrirModal} testID={`modificadores-section-gerenciar-${tipo}`}>
              <Ionicons name="options-outline" size={14} color={colors.onSurface} />
              <Text style={styles.manageBtnText}>Gerenciar</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
      {carregando ? (
        <ActivityIndicator size="small" color={colors.brandPrimary} />
      ) : associadas.length === 0 ? (
        <Text style={styles.hint}>Nenhuma categoria de modificador associada.</Text>
      ) : (
        <View style={styles.chipsRow}>
          {associadas.map((c) => (
            <View key={c.codigo} style={styles.chip}>
              <Text style={styles.chipText}>{c.nome}</Text>
            </View>
          ))}
        </View>
      )}

      <AppModal visible={modalOpen} transparent animationType="fade" onRequestClose={() => setModalOpen(false)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setModalOpen(false)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Categorias de Modificador</Text>
              <Pressable onPress={() => setModalOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <TextInput
              style={styles.searchInput}
              value={busca}
              onChangeText={setBusca}
              placeholder="Buscar categoria..."
              autoFocus={isWeb}
              testID="modificadores-section-busca"
            />
            <ScrollView style={{ maxHeight: 360, marginTop: spacing.sm }}>
              {categoriasFiltradas.length === 0 ? (
                <Text style={styles.hint}>Nenhuma categoria de modificador cadastrada.</Text>
              ) : (
                categoriasFiltradas.map((c) => {
                  const sel = selecionadas.has(c.codigo);
                  return (
                    <Pressable
                      key={c.codigo}
                      style={styles.catRow}
                      onPress={() => toggle(c.codigo)}
                      testID={`modificadores-section-cat-${c.codigo}`}
                    >
                      <Ionicons name={sel ? "checkbox" : "square-outline"} size={18} color={sel ? colors.brandPrimary : colors.muted} />
                      <Text style={styles.catText}>{c.nome}</Text>
                    </Pressable>
                  );
                })
              )}
            </ScrollView>
            <Pressable
              style={[styles.saveBtn, salvando && { opacity: 0.6 }]}
              onPress={salvar}
              disabled={salvando}
              testID="modificadores-section-salvar"
            >
              {salvando ? <ActivityIndicator size="small" color={colors.onBrandPrimary} /> : <Ionicons name="save-outline" size={16} color={colors.onBrandPrimary} />}
              <Text style={styles.saveBtnText}>Gravar ({selecionadas.size})</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </AppModal>

      <ModificadorCategoriaModal
        visible={novaCategoriaOpen}
        api={api}
        servidor={servidor}
        banco={banco}
        codigo={null}
        onClose={() => setNovaCategoriaOpen(false)}
        onSaved={handleNovaCategoriaSaved}
        podeGravar={podeIncluirModificador}
        podeExcluir={false}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  headerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  headerBtns: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  title: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  hint: { fontSize: 12, color: colors.muted },
  manageBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.surface, borderRadius: radius.pill,
    borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: 6,
  },
  manageBtnText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  chipsRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.xs },
  chip: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.pill,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  },
  chipText: { fontSize: 12, fontWeight: "600", color: colors.brandPrimary },
  searchInput: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 8, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  catRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: 8, borderTopWidth: 1, borderTopColor: colors.border,
  },
  catText: { fontSize: 13, color: colors.onSurface },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-end", marginTop: spacing.md,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  saveBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
});
