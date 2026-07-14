import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator, Image, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import SelectField, { SelectOption } from "@/src/components/SelectField";
import DateField from "@/src/components/DateField";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { CatNode, flatten } from "@/src/utils/permissoesTree";

type LogItem = {
  id: number;
  data_hora: string | null;
  tela: string;
  comando: string;
  referencia: string | null;
  descricao: string | null;
  campos_alterados: { campo: string; antes?: string; depois?: string; valor?: string }[] | null;
  usuario: number | null;
  usuario_nome: string | null;
  classe: number | null;
  ip_origem: string | null;
  plataforma: string | null;
};

const PAGE_SIZE = 40;

function formatDataHora(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

// Log de Auditoria — visualização das ações gravadas em `log_auditoria`
// (não confundir com as tabelas legadas `logs`/`tipo_log`/`log_sistema`, que
// continuam sendo gravadas pelo VB6 e não têm relação com esta tela). Web-only.
export default function LogAuditoriaScreen() {
  const router = useRouter();
  const { can, isMaster, classe } = usePermissions();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="Log de Auditoria está disponível apenas no web."
        testID="log-auditoria-web-only"
      />
    );
  }
  if (!can("LOG_AUDITORIA.ABRIR")) {
    return <LockedView testID="log-auditoria-locked" />;
  }

  return <LogAuditoriaWebScreen router={router} isMaster={isMaster} classe={classe} />;
}

function LogAuditoriaWebScreen({
  router, isMaster, classe,
}: {
  router: ReturnType<typeof useRouter>;
  isMaster: boolean;
  classe: number | null;
}) {
  const [conn, setConn] = useState<Connection | null>(null);
  const [catalogo, setCatalogo] = useState<CatNode[]>([]);
  const [funcionarioOptions, setFuncionarioOptions] = useState<SelectOption[]>([]);

  const [filtroNode, setFiltroNode] = useState<CatNode | null>(null);
  const [catalogoModalVisible, setCatalogoModalVisible] = useState(false);
  const [catalogoExpanded, setCatalogoExpanded] = useState<Set<string>>(new Set());
  const [catalogoSearch, setCatalogoSearch] = useState("");

  const [dataDe, setDataDe] = useState<string | null>(null);
  const [dataAte, setDataAte] = useState<string | null>(null);
  const [usuarioSel, setUsuarioSel] = useState<string | number | null>(null);
  const [referencia, setReferencia] = useState("");
  const [descricaoLike, setDescricaoLike] = useState("");

  const [items, setItems] = useState<LogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);

      const catR = await apiGet(c, "/api/permissoes/catalogo");
      if (catR?.catalogo) setCatalogo(catR.catalogo);

      const funcR = await apiGet(c, "/api/funcionarios");
      if (funcR?.success && Array.isArray(funcR.items)) {
        setFuncionarioOptions(funcR.items.map((f: { codigo: number; nome: string }) => ({ value: f.codigo, label: f.nome })));
      }
    })();
  }, [router]);

  // remove os nós BOTAO "Abrir Tela" — não faz sentido filtrar log por abertura de tela
  const catalogoSemAbrir = useMemo(() => {
    const strip = (nodes: CatNode[]): CatNode[] =>
      nodes
        .filter((n) => !(n.tipo === "BOTAO" && n.comando === "ABRIR"))
        .map((n) => ({ ...n, children: strip(n.children) }));
    return strip(catalogo);
  }, [catalogo]);

  const flatMap = useMemo(() => flatten(catalogo), [catalogo]);
  const nomeTela = useCallback((tela: string) => flatMap[`TELA|${tela}|`]?.nome || tela, [flatMap]);
  const nomeComando = useCallback(
    (tela: string, comando: string) => flatMap[`BOTAO|${tela}|${comando}`]?.nome || comando,
    [flatMap]
  );

  const catalogoTerm = catalogoSearch.trim().toLowerCase();
  const matchesCatalogoSearch = useCallback((n: CatNode): boolean =>
    n.nome.toLowerCase().includes(catalogoTerm) || n.children.some(matchesCatalogoSearch), [catalogoTerm]);
  const visibleCatalogo = catalogoTerm ? catalogoSemAbrir.filter(matchesCatalogoSearch) : catalogoSemAbrir;

  useEffect(() => {
    if (!catalogoTerm) return;
    setCatalogoExpanded((prev) => {
      const next = new Set(prev);
      const walk = (nodes: CatNode[]) => {
        for (const n of nodes) {
          if (matchesCatalogoSearch(n)) next.add(`${n.tipo}|${n.tela}|${n.comando || ""}`);
          walk(n.children);
        }
      };
      walk(catalogoSemAbrir);
      return next;
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catalogoTerm]);

  const toggleCatalogoExpand = (k: string) => {
    setCatalogoExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k); else next.add(k);
      return next;
    });
  };

  const abrirCatalogoModal = () => {
    setCatalogoExpanded((prev) => {
      const next = new Set(prev);
      catalogoSemAbrir.forEach((n) => next.add(`${n.tipo}|${n.tela}|${n.comando || ""}`));
      return next;
    });
    setCatalogoModalVisible(true);
  };

  const buscar = useCallback(async (pg: number) => {
    if (!conn) return;
    setLoading(true);
    try {
      const j = await apiGet(conn, "/api/log-auditoria", {
        tela: filtroNode?.tela || undefined,
        comando: filtroNode?.tipo === "BOTAO" ? filtroNode.comando : undefined,
        usuario: usuarioSel || undefined,
        data_de: dataDe || undefined,
        data_ate: dataAte || undefined,
        referencia: referencia.trim() || undefined,
        descricao_like: descricaoLike.trim() || undefined,
        page: pg,
        size: PAGE_SIZE,
        classe: classe ?? undefined,
        master: isMaster,
      });
      if (j?.success) {
        setItems(j.items || []);
        setTotal(j.total || 0);
        setPage(pg);
      } else {
        setItems([]);
        setTotal(0);
      }
    } finally {
      setLoading(false);
    }
  }, [conn, filtroNode, usuarioSel, dataDe, dataAte, referencia, descricaoLike, classe, isMaster]);

  useEffect(() => {
    if (conn) buscar(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const toggleRow = (id: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const renderCatalogoNode = (n: CatNode, depth: number): React.ReactNode => {
    const k = `${n.tipo}|${n.tela}|${n.comando || ""}`;
    const isOpen = catalogoExpanded.has(k);
    const hasChildren = n.children.length > 0;
    const selectable = n.tipo === "TELA" || n.tipo === "BOTAO";
    const isSel = selectable && filtroNode
      && filtroNode.tela === n.tela
      && (n.tipo === "TELA" ? filtroNode.tipo === "TELA" : filtroNode.comando === n.comando);

    return (
      <View key={k} style={{ marginLeft: depth * spacing.lg }}>
        <View style={[styles.nivelRow, isSel && styles.nivelRowSel]}>
          <Pressable onPress={() => hasChildren && toggleCatalogoExpand(k)} hitSlop={8} style={{ opacity: hasChildren ? 1 : 0.25 }}>
            <Ionicons name={isOpen ? "chevron-down" : "chevron-forward"} size={14} color={colors.muted} />
          </Pressable>
          <Pressable
            style={{ flex: 1 }}
            onPress={() => {
              if (!selectable) return;
              setFiltroNode(n);
              setCatalogoModalVisible(false);
              setCatalogoSearch("");
            }}
          >
            <Text style={[
              styles.nivelRowText,
              n.tipo === "MENU" && styles.menuLabel,
              n.tipo === "TELA" && styles.telaLabel,
              isSel && styles.nivelRowTextSel,
            ]}>
              {n.nome}
            </Text>
          </Pressable>
        </View>
        {isOpen ? n.children.map((c) => renderCatalogoNode(c, depth + 1)) : null}
      </View>
    );
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="log-auditoria-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="log-auditoria-back-button">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>Log de Auditoria</Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card} testID="log-auditoria-filtro-card">
            <Text style={styles.sectionTitle}>Filtro</Text>

            <Pressable onPress={abrirCatalogoModal} style={styles.selectorBtn} testID="log-auditoria-abrir-catalogo">
              <Ionicons name="layers-outline" size={16} color={colors.brandPrimary} />
              <Text style={styles.selectorBtnText} numberOfLines={1}>
                {filtroNode ? `${nomeTela(filtroNode.tela)}${filtroNode.tipo === "BOTAO" ? ` — ${filtroNode.nome}` : " (todas as ações)"}` : "Tela / Ação (todas)…"}
              </Text>
              {filtroNode ? (
                <Pressable onPress={() => setFiltroNode(null)} hitSlop={8}>
                  <Ionicons name="close-circle" size={16} color={colors.muted} />
                </Pressable>
              ) : null}
              <Ionicons name="chevron-forward" size={16} color={colors.muted} />
            </Pressable>

            <View style={styles.formGrid}>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Data de</Text>
                <DateField value={dataDe} onChange={setDataDe} allowClear testID="log-auditoria-data-de" />
              </View>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Data até</Text>
                <DateField value={dataAte} onChange={setDataAte} allowClear testID="log-auditoria-data-ate" />
              </View>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Usuário</Text>
                <SelectField value={usuarioSel} onChange={setUsuarioSel} options={funcionarioOptions} allowClear compactWeb testID="log-auditoria-usuario" />
              </View>
              <View style={styles.colHalf}>
                <Text style={styles.fieldLabel}>Referência</Text>
                <TextInput value={referencia} onChangeText={setReferencia} style={styles.input} placeholder="Nº pedido/O.S./comanda…" placeholderTextColor={colors.muted} testID="log-auditoria-referencia" />
              </View>
              <View style={styles.colFull}>
                <Text style={styles.fieldLabel}>Descrição (contém)</Text>
                <TextInput value={descricaoLike} onChangeText={setDescricaoLike} style={styles.input} placeholderTextColor={colors.muted} testID="log-auditoria-descricao" />
              </View>
            </View>

            <Pressable onPress={() => buscar(1)} disabled={loading} style={[styles.crudBtn, styles.crudBtnPrimary, loading && { opacity: 0.6 }]} testID="log-auditoria-buscar-button">
              {loading ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.crudBtnPrimaryText}>Buscar</Text>}
            </Pressable>
          </View>

          <View style={styles.card} testID="log-auditoria-resultados">
            <Text style={styles.sectionTitle}>{total} registro(s)</Text>
            {items.length === 0 && !loading ? <Text style={styles.hint}>Nenhum registro encontrado.</Text> : null}
            {items.map((it) => {
              const isOpen = expandedRows.has(it.id);
              return (
                <Pressable key={it.id} onPress={() => toggleRow(it.id)} style={styles.logRow} testID={`log-auditoria-row-${it.id}`}>
                  <View style={styles.logRowHeader}>
                    <Text style={styles.logDataHora}>{formatDataHora(it.data_hora)}</Text>
                    <View style={styles.logTagBox}>
                      <Text style={styles.logTagText}>{nomeTela(it.tela)} — {nomeComando(it.tela, it.comando)}</Text>
                    </View>
                  </View>
                  <Text style={styles.logDescricao}>{it.descricao || "—"}</Text>
                  <View style={styles.logMetaRow}>
                    {it.referencia ? <Text style={styles.logMeta}>Ref.: {it.referencia}</Text> : null}
                    <Text style={styles.logMeta}>Usuário: {it.usuario_nome || it.usuario || "—"}</Text>
                    {it.plataforma ? <Text style={styles.logMeta}>{it.plataforma}</Text> : null}
                    {it.ip_origem ? <Text style={styles.logMeta}>IP: {it.ip_origem}</Text> : null}
                  </View>
                  {isOpen && it.campos_alterados && it.campos_alterados.length > 0 ? (
                    <View style={styles.logCamposBox}>
                      {it.campos_alterados.map((c, idx) => (
                        <Text key={idx} style={styles.logCampoLine}>
                          {c.campo}: {c.antes !== undefined || c.depois !== undefined
                            ? `${c.antes ?? "—"} → ${c.depois ?? "—"}`
                            : c.valor ?? "—"}
                        </Text>
                      ))}
                    </View>
                  ) : null}
                </Pressable>
              );
            })}

            {total > PAGE_SIZE ? (
              <View style={styles.pagerRow}>
                <Pressable onPress={() => buscar(page - 1)} disabled={page <= 1 || loading} style={[styles.crudBtn, (page <= 1 || loading) && { opacity: 0.5 }]}>
                  <Text style={styles.crudBtnText}>Anterior</Text>
                </Pressable>
                <Text style={styles.hint}>Página {page} de {totalPages}</Text>
                <Pressable onPress={() => buscar(page + 1)} disabled={page >= totalPages || loading} style={[styles.crudBtn, (page >= totalPages || loading) && { opacity: 0.5 }]}>
                  <Text style={styles.crudBtnText}>Próxima</Text>
                </Pressable>
              </View>
            ) : null}
          </View>
        </View>
      </ScrollView>

      <Modal visible={catalogoModalVisible} transparent animationType="slide" onRequestClose={() => setCatalogoModalVisible(false)} testID="log-auditoria-catalogo-modal">
        <Pressable style={styles.slideBg} onPress={() => setCatalogoModalVisible(false)}>
          <Pressable style={styles.slideCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.slideHeader}>
              <Text style={styles.modalTitle}>Selecionar Tela / Ação</Text>
              <Pressable onPress={() => setCatalogoModalVisible(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={catalogoSearch}
                onChangeText={setCatalogoSearch}
                placeholder="Buscar…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                testID="log-auditoria-catalogo-search"
              />
            </View>
            <ScrollView style={styles.slideScroll} showsVerticalScrollIndicator={false}>
              {visibleCatalogo.length === 0 ? (
                <Text style={styles.hint}>Nenhuma tela encontrada.</Text>
              ) : visibleCatalogo.map((n) => renderCatalogoNode(n, 0))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 15, fontWeight: "500" },
  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  sectionTitle: { fontSize: 14, fontWeight: "700", color: colors.onSurface, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: spacing.sm },
  hint: { fontSize: 12, color: colors.muted, marginTop: 4, marginBottom: spacing.sm, fontStyle: "italic" },
  formGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.md, marginTop: spacing.sm },
  colHalf: { width: "49%", marginBottom: spacing.md },
  colFull: { width: "100%", marginBottom: spacing.md },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface, minHeight: 40,
  },
  selectorBtn: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: 11,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    marginBottom: spacing.sm,
  },
  selectorBtnText: { flex: 1, fontSize: 14, color: colors.onSurface },
  crudBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: 10, borderRadius: radius.sm, borderWidth: 1,
    borderColor: colors.border, backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center",
  },
  crudBtnText: { fontSize: 13, fontWeight: "500", color: colors.onSurface },
  crudBtnPrimary: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary, marginTop: spacing.md },
  crudBtnPrimaryText: { fontSize: 13, fontWeight: "600", color: colors.onBrandPrimary },
  logRow: {
    paddingVertical: spacing.sm, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  logRowHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: spacing.sm },
  logDataHora: { fontSize: 12, color: colors.muted, fontWeight: "600" },
  logTagBox: { backgroundColor: colors.brandTertiary, borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  logTagText: { fontSize: 10, fontWeight: "700", color: colors.brandPrimary },
  logDescricao: { fontSize: 13, color: colors.onSurface, marginTop: 4 },
  logMetaRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginTop: 4 },
  logMeta: { fontSize: 11, color: colors.muted },
  logCamposBox: { marginTop: spacing.sm, padding: spacing.sm, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm },
  logCampoLine: { fontSize: 12, color: colors.onSurface, marginBottom: 2 },
  pagerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginTop: spacing.md },
  nivelRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.sm, paddingHorizontal: spacing.sm,
    borderRadius: radius.sm, marginBottom: 2,
  },
  nivelRowSel: { backgroundColor: colors.brandTertiary },
  nivelRowText: { fontSize: 13, color: colors.onSurface },
  nivelRowTextSel: { fontWeight: "700", color: colors.brandPrimary },
  menuLabel: { fontWeight: "700", color: colors.brandPrimary },
  telaLabel: { fontWeight: "600" },
  slideBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.4)", justifyContent: "flex-end", alignItems: "center" },
  slideCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    padding: spacing.md, maxHeight: "85%", width: "100%", maxWidth: 560, alignSelf: "center",
  },
  slideHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  slideScroll: { maxHeight: 420 },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, paddingHorizontal: spacing.sm, paddingVertical: spacing.sm, borderWidth: 1, borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  modalTitle: { fontSize: 16, fontWeight: "700", color: colors.onSurface },
});
