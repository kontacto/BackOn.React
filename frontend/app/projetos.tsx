// Lista do Gestor de Projetos — mesmo padrão de `os-lista.tsx`/
// `pedido-lista.tsx`: busca + chips de situação + lista paginada, FAB
// "novo" quando o usuário tem permissão de Gravar. Ver PENDENCIAS.md >
// "Gestor de Projetos" pro rastreio completo (migração de
// `Geral\frmgespro.frm`, Fase 1 — núcleo).
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = Connection;
type ProjetoRow = {
  codigo: number; cliente_nome: string; responsavel_nome: string;
  data_abertura: string | null; data_prevista: string | null;
  situacao: string; situacao_label: string;
  valor_produtos: number; valor_servicos: number; valor_projeto: number;
  ultimo_vinculo: string | null;
};

// "Projeto parado" — Gestor de Projetos Fase 4 (recurso extra, sem
// equivalente no legado: lá só existe o campo de data, nunca um alerta).
// Um Projeto Aberto é destacado quando o prazo previsto já venceu, OU
// quando não recebe um novo documento vinculado há muito tempo (usa a
// data de abertura como referência enquanto nenhum documento foi
// vinculado ainda). Limiar de 15 dias — mais longo que o 1 dia usado no
// Painel de Pedidos (`pedidos.tsx`), já que Projeto é uma entidade de
// ciclo de vida bem mais longo (semanas/meses), não um atendimento do dia.
const PROJETO_PARADO_DIAS = 15;
function isProjetoParado(item: ProjetoRow): boolean {
  if (item.situacao !== "A") return false;
  const hoje = new Date().toISOString().slice(0, 10);
  if (item.data_prevista && item.data_prevista < hoje) return true;
  const base = item.ultimo_vinculo || item.data_abertura;
  if (!base) return false;
  const dias = (Date.now() - new Date(base).getTime()) / 86400000;
  return dias > PROJETO_PARADO_DIAS;
}

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Abertos" },
  { value: "F", label: "Finalizados" },
  { value: "C", label: "Cancelados" },
];

export default function ProjetosScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const feedback = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="O Gestor de Projetos está disponível apenas no web." testID="projetos-web-only" />;
  }

  if (!moduleOn("gestor_projetos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Gestor de Projetos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="projetos-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [items, setItems] = useState<ProjetoRow[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      setLoadingConn(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(async (c: Conn, term: string, sit: string, pg: number, append: boolean) => {
    if (aborter.current) aborter.current.abort();
    const ac = new AbortController();
    aborter.current = ac;
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/projetos`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ servidor: c.servidor, banco: c.banco, search: term, situacao: sit, page: pg, size: 20 }),
        signal: ac.signal,
      });
      const j = await r.json();
      if (!j?.success) {
        feedback.showError(j?.message || "Falha na consulta.");
        if (!append) setItems([]);
      } else {
        setItems((prev) => (append ? [...prev, ...j.items] : j.items));
        setTotal(j.total || 0);
      }
    } catch (e) {
      if ((e as { name?: string })?.name !== "AbortError") {
        feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
      }
    } finally {
      if (aborter.current === ac) setLoading(false);
    }
  }, [feedback]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => { setPage(1); load(conn, search, situacao, 1, false); }, 350);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, search, situacao]);

  const loadMore = () => {
    if (!conn || loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(conn, search, situacao, next, true);
  };

  const abrirProjeto = (item: ProjetoRow) => {
    router.push({ pathname: "/projeto-form", params: { codigo: String(item.codigo) } } as never);
  };

  const canGravar = can("PROJETOS.GRAVAR");

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="projetos-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="projetos-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>Gestor de Projetos ({total})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.shellOuter}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={search}
                onChangeText={setSearch}
                placeholder="Buscar por cliente…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="projetos-search"
              />
            </View>
            <View style={styles.chipsRow}>
              {SITUACOES.map((s) => {
                const sel = situacao === s.value;
                return (
                  <Pressable
                    key={s.value || "all"}
                    onPress={() => setSituacao(s.value)}
                    style={[styles.chip, sel && styles.chipSel]}
                    testID={`projetos-chip-${s.value || "all"}`}
                  >
                    <Text style={[styles.chipText, sel && styles.chipTextSel]}>{s.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {loading && items.length === 0 ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
          <FlatList
            data={items}
            keyExtractor={(i) => String(i.codigo)}
            contentContainerStyle={styles.listContent}
            onEndReached={loadMore}
            onEndReachedThreshold={0.4}
            ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum projeto encontrado.</Text> : null}
            renderItem={({ item }) => {
              const parado = isProjetoParado(item);
              return (
                <Pressable
                  onPress={() => abrirProjeto(item)}
                  style={[styles.row, parado && styles.rowParado]}
                  testID={`projetos-${item.codigo}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={[styles.rowTitle, parado && styles.textParado]} numberOfLines={1}>
                      #{item.codigo} · {item.cliente_nome || "(sem cliente)"}
                    </Text>
                    <Text style={[styles.rowSub, parado && styles.textParado]} numberOfLines={1}>
                      {item.data_abertura ? formatDateBR(item.data_abertura) : "—"} · {item.responsavel_nome || "—"} · {item.situacao_label}
                      {parado ? " · Parado" : ""}
                    </Text>
                  </View>
                  <Text style={[styles.rowValor, parado && styles.textParado]}>{formatBRL(item.valor_produtos + item.valor_servicos)}</Text>
                  <Ionicons name="chevron-forward" size={18} color={parado ? colors.error : colors.muted} />
                </Pressable>
              );
            }}
          />
        </View>
      </View>

      {canGravar ? (
        <Pressable onPress={() => router.push("/projeto-form" as never)} style={styles.fab} testID="projetos-novo">
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  shellOuter: { flex: 1, alignItems: "center" },
  shell: { ...WEB_CONTENT_SHELL, flex: 1 },
  scrollWeb: WEB_SCROLL_CENTER,
  filterCard: { ...WEB_FILTER_CARD, marginTop: spacing.md, marginBottom: spacing.sm, gap: spacing.sm },
  searchWrap: { flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 10 },
  searchInput: { flex: 1, fontSize: 14, color: colors.onSurface },
  chipsRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  listContent: { paddingHorizontal: spacing.lg, paddingBottom: 100, gap: spacing.sm },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, minHeight: 72,
  },
  rowParado: { borderColor: colors.error, borderLeftWidth: 3 },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  textParado: { color: colors.error },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
});
