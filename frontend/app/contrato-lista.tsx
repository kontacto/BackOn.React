import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

type Conn = { servidor: string; banco: string; api: string };
type ContratoRow = {
  codigo: number; contrato: string; cliente_nome: string; valor_atual: number; situacao: string;
  inicio: string | null; fim: string | null; dia_vencimento: number | null;
};

const SITUACOES: { key: string; label: string }[] = [
  { key: "", label: "Todos" },
  { key: "A", label: "Ativo" },
  { key: "F", label: "Encerrado" },
];

// Transações > Contratos > Contratos (lista, migração de
// FrmManContra.frm's grid principal + Command21_Click "Consulta"). Abre
// contrato-completo.tsx pra criar/editar.
export default function ContratoListaScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Contratos está disponível apenas no web."
        testID="contrato-lista-web-only"
      />
    );
  }

  if (!moduleOn("contratos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Contratos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="contrato-lista-module-off"
      />
    );
  }

  const [conn, setConn] = useState<Conn | null>(null);
  const [items, setItems] = useState<ContratoRow[]>([]);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState("A");
  const [loading, setLoading] = useState(false);

  const load = useCallback(async (c: Conn, q: string, sit: string) => {
    setLoading(true);
    try {
      const base = c.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}&search=${encodeURIComponent(q)}&situacao=${encodeURIComponent(sit)}&size=100`;
      const r = await fetch(`${base}/api/contratos?${qs}`);
      const j = await r.json();
      setItems(j?.success ? j.items || [] : []);
    } catch { setItems([]); } finally { setLoading(false); }
  }, []);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      const cc = { servidor: c.servidor, banco: c.banco, api: c.api };
      setConn(cc);
      load(cc, "", "A");
    })();
  }, [router, load]);

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => load(conn, search, situacao), 300);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, situacao]);

  const canGravar = can("CONTRATO.GRAVAR");

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="contrato-lista-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.back}>
          <Ionicons name="chevron-back" size={24} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Contratos ({items.length})</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.webShell}>
        <View style={styles.filterBox}>
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por nº do contrato ou cliente…"
            placeholderTextColor={colors.muted}
            style={styles.input}
            testID="contrato-lista-search"
          />
          <View style={styles.chipsRow}>
            {SITUACOES.map((s) => (
              <Pressable
                key={s.key}
                onPress={() => setSituacao(s.key)}
                style={[styles.chip, situacao === s.key && styles.chipSel]}
                testID={`contrato-lista-sit-${s.key || "todos"}`}
              >
                <Text style={[styles.chipText, situacao === s.key && styles.chipTextSel]}>{s.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        {loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 24 }} /> : null}
        <FlatList
          data={items}
          keyExtractor={(i) => String(i.codigo)}
          contentContainerStyle={[styles.scroll, styles.scrollWeb]}
          ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum contrato encontrado.</Text> : null}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => router.push({ pathname: "/contrato-completo", params: { codigo: String(item.codigo) } } as never)}
              style={styles.row}
              testID={`contrato-lista-${item.codigo}`}
            >
              <View style={{ flex: 1 }}>
                <Text style={styles.rowTitle} numberOfLines={2}>#{item.contrato} · {item.cliente_nome}</Text>
                <Text style={styles.rowSub} numberOfLines={1}>
                  {item.inicio ? formatDateBR(item.inicio) : "—"} · Venc. dia {item.dia_vencimento ?? "—"} · {item.situacao === "A" ? "Ativo" : "Encerrado"}
                </Text>
              </View>
              <Text style={styles.rowValor}>{formatBRL(item.valor_atual)}</Text>
              <Ionicons name="chevron-forward" size={18} color={colors.muted} />
            </Pressable>
          )}
        />
      </View>

      {canGravar ? (
        <Pressable
          onPress={() => router.push("/contrato-completo" as never)}
          style={styles.fab}
          testID="contrato-lista-novo"
        >
          <Ionicons name="add" size={28} color="#fff" />
        </Pressable>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, textAlign: "center", fontSize: 17, fontWeight: "500", color: colors.onBrandPrimary },
  webShell: { width: "100%", maxWidth: 720, alignSelf: "center", flex: 1 },
  filterBox: { padding: spacing.lg, paddingBottom: spacing.sm, gap: spacing.sm },
  chipsRow: { flexDirection: "row", gap: spacing.sm },
  chip: { paddingHorizontal: spacing.md, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  chipSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { fontSize: 13, color: colors.onSurface },
  chipTextSel: { color: "#fff", fontWeight: "600" },
  scroll: { paddingHorizontal: spacing.lg, gap: spacing.sm, paddingBottom: 90 },
  scrollWeb: WEB_SCROLL_CENTER,
  row: {
    flexDirection: "row", alignItems: "center", alignSelf: "stretch", width: "100%", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, padding: spacing.md,
    // Altura padronizada por todos os cards — do tamanho do maior card
    // possível (título em 2 linhas, ex.: nome de cliente longo, + o
    // subtítulo abaixo), pra nenhum card ficar mais alto/baixo que os
    // outros na lista (pedido explícito do usuário, 2026-07-20).
    minHeight: 84,
  },
  rowTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  rowSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  rowValor: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  empty: { textAlign: "center", color: colors.muted, marginTop: 24 },
  fab: { position: "absolute", right: 20, bottom: 28, width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", elevation: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
});
