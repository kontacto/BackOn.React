// Modificadores (Cadastros > Tabelas Auxiliares) — cadastro novo, sem
// tabela/tela equivalente no legado VB6 (pedido explícito do usuário,
// 2026-07-23). Uma Categoria de Modificador (ex.: "Ponto da Carne") agrupa
// vários Modificadores (ex.: "Mal passado"/"Bem passado"), cada um podendo
// lançar um acréscimo e/ou desconto (valor fixo em R$) no item da
// pré-venda. Categoria tem condição (Obrigatório/Opcional) e modo de
// seleção (um único modificador ou vários) — ambos só terão efeito quando
// a tela de venda (Fase 2, ainda não implementada) abrir o seletor de
// modificadores ao incluir um item associado. Ver
// backend/services/modificadores_service.py e PENDENCIAS.md >
// "Modificadores" pro desenho completo.
//
// Padrão de tela: lista + modal de edição com itens aninhados (mesmo
// formato já usado em Forma de Pagamento pros "Prazos") — não é um cadastro
// "completo" no sentido de app/cliente-completo.tsx (sem abas, sem Anexos),
// é uma tabela auxiliar com uma lista filha (Modificadores) e uma
// associação N:N (Produtos/Serviços).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ModificadorCategoriaModal from "@/src/components/ModificadorCategoriaModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, friendlyApiError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";

type CategoriaResumo = {
  codigo: number;
  nome: string;
  obrigatorio: boolean;
  selecao_multipla: boolean;
  qtd_modificadores: number;
  qtd_associados: number;
};

export default function ModificadoresScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Modificadores está disponível apenas no web."
        testID="modificadores-web-only"
      />
    );
  }

  // Modificadores só faz sentido pro Pedido Bar (único lugar com o seletor
  // de modificador na venda) — pedido explícito do usuário, 2026-07-23:
  // "colocar o modificador ligado ao módulo de Pedido Bar. Só aparecerá
  // para esse módulo ativo em configurações". Reforçado no backend também
  // (modificadores_service.py, `_modulo_bar_ativo`).
  if (!moduleOn("Bar")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Bar está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="modificadores-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [categorias, setCategorias] = useState<CategoriaResumo[]>([]);
  const [busca, setBusca] = useState("");
  const [carregando, setCarregando] = useState(true);

  const podeAbrir = can("MODIFICADORES.ABRIR");
  const podeGravar = can("MODIFICADORES.GRAVAR");
  const podeExcluir = can("MODIFICADORES.EXCLUIR");

  // ---- Editor (modal compartilhado — ModificadorCategoriaModal.tsx) ----
  const [editorOpen, setEditorOpen] = useState(false);
  const [editandoCodigo, setEditandoCodigo] = useState<number | null>(null);

  const bootConn = useCallback(async () => {
    if (conn) return conn;
    const s = await getSession();
    if (!s) { router.replace("/login"); return null; }
    const c = (await listConnections()).find((x) => x.empresa === s.empresa);
    if (c) setConn(c);
    return c || null;
  }, [conn, router]);

  const carregarCategorias = useCallback(async (c: Connection, termo?: string) => {
    setCarregando(true);
    try {
      const r = await apiGet(c, "/api/modificadores/categorias", { busca: termo || undefined });
      if (r?.success) setCategorias(r.items || []);
      else fb.showError(friendlyApiError(r, "Não foi possível carregar os modificadores."));
    } finally {
      setCarregando(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    (async () => {
      const c = await bootConn();
      if (c) carregarCategorias(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => carregarCategorias(conn, busca), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [busca]);

  const abrirNova = useCallback(() => {
    setEditandoCodigo(null);
    setEditorOpen(true);
  }, []);

  const abrirEdicao = useCallback((categoria: CategoriaResumo) => {
    setEditandoCodigo(categoria.codigo);
    setEditorOpen(true);
  }, []);

  const recarregar = useCallback(() => {
    if (conn) carregarCategorias(conn, busca);
  }, [conn, carregarCategorias, busca]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="modificadores-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back} testID="modificadores-voltar">
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Modificadores</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline"
          label="Ajuda"
          onPress={() => fb.showConfirm(
            "Modificadores são categorias (ex.: \"Ponto da Carne\") associáveis a Produtos e/ou Serviços. Cada categoria pode ser Obrigatória ou Opcional na hora da venda, e permitir escolher um único modificador ou vários. Cada modificador dentro da categoria pode lançar um acréscimo e/ou desconto (valor fixo em R$) no item vendido. A associação pode ser feita aqui ou dentro do próprio cadastro de Produto/Serviço.",
            () => {},
          )}
          color={colors.onBrandPrimary}
          size={22}
          testID="modificadores-ajuda"
        />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.webShell}>
          <View style={styles.filterCard}>
            <View style={styles.searchRow}>
              <TextInput
                style={styles.searchInput}
                value={busca}
                onChangeText={setBusca}
                placeholder="Buscar categoria de modificador..."
                testID="modificadores-busca"
              />
              {podeGravar ? (
                <Pressable style={styles.primaryBtn} onPress={abrirNova} testID="modificadores-nova">
                  <Ionicons name="add" size={16} color={colors.onBrandPrimary} />
                  <Text style={styles.primaryBtnText}>Nova Categoria</Text>
                </Pressable>
              ) : null}
            </View>
          </View>

          <View style={[styles.filterCard, { marginTop: spacing.md }]}>
            {carregando ? (
              <ActivityIndicator size="small" color={colors.brandPrimary} />
            ) : categorias.length === 0 ? (
              <Text style={styles.muted}>Nenhuma categoria de modificador cadastrada.</Text>
            ) : (
              categorias.map((cat) => (
                <Pressable
                  key={cat.codigo}
                  style={styles.catRow}
                  onPress={() => abrirEdicao(cat)}
                  testID={`modificadores-cat-${cat.codigo}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.catNome}>{cat.nome}</Text>
                    <Text style={styles.catHint}>
                      {cat.obrigatorio ? "Obrigatório" : "Opcional"} · {cat.selecao_multipla ? "Vários" : "Apenas um"} ·{" "}
                      {cat.qtd_modificadores} {cat.qtd_modificadores === 1 ? "modificador" : "modificadores"} ·{" "}
                      {cat.qtd_associados} {cat.qtd_associados === 1 ? "associado" : "associados"}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))
            )}
          </View>
        </View>
      </ScrollView>

      {conn ? (
        <ModificadorCategoriaModal
          visible={editorOpen}
          api={conn.api}
          servidor={conn.servidor}
          banco={conn.banco}
          codigo={editandoCodigo}
          onClose={() => setEditorOpen(false)}
          onSaved={() => { setEditorOpen(false); recarregar(); }}
          onDeleted={() => { setEditorOpen(false); recarregar(); }}
          podeGravar={podeGravar}
          podeExcluir={podeExcluir}
        />
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500", textAlign: "center" },
  scroll: { padding: spacing.lg, gap: spacing.md },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  filterCard: { ...WEB_FILTER_CARD, gap: spacing.sm },
  searchRow: { flexDirection: "row", gap: spacing.sm, alignItems: "center" },
  searchInput: {
    flex: 1, minWidth: 0, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 9, fontSize: 13, color: colors.onSurface, backgroundColor: colors.surface,
  },
  muted: { fontSize: 13, color: colors.muted, textAlign: "center", paddingVertical: spacing.sm },
  catRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, borderTopWidth: 1, borderTopColor: colors.border,
  },
  catNome: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  catHint: { fontSize: 12, color: colors.muted, marginTop: 2 },
  primaryBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
});
