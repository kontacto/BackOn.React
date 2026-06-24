import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import {
  Session,
  clearSession,
  getSession,
  getSituacaoFiltro as getSituacaoPref,
  setSituacaoFiltro as setSituacaoPref,
} from "@/src/utils/storage/session";
import { listConnections } from "@/src/utils/storage/connections";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { colors, radius, spacing } from "@/src/theme/colors";

function pickFirst(obj: Record<string, unknown> | null | undefined, keys: string[]): string | null {
  if (!obj) return null;
  for (const k of keys) {
    const v = obj[k];
    if (v !== undefined && v !== null && String(v).trim() !== "") {
      return String(v);
    }
  }
  return null;
}

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

type DashboardTotals = { pedidos: number; produtos: number; servicos: number; descontos: number; margem: number; margem_pct: number };
type DashboardPedido = { pedido: number; cliente: string; valor: number };

const SITUACOES: { value: string; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];

export default function PrincipalScreen() {
  const router = useRouter();
  const [session, setSessionState] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  // Dashboard
  const [totais, setTotais] = useState<DashboardTotals>({ pedidos: 0, produtos: 0, servicos: 0, descontos: 0, margem: 0, margem_pct: 0 });
  const [pedidos, setPedidos] = useState<DashboardPedido[]>([]);
  const [dashLoading, setDashLoading] = useState(false);
  const [dashError, setDashError] = useState<string | null>(null);
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [vendedorFiltro, setVendedorFiltro] = useState<string | number | null>(null); // null = Todos
  const [situacaoFiltro, setSituacaoFiltro] = useState<string>(""); // "" = Todos
  const [fantasia, setFantasia] = useState<string | null>(null);

  // Persiste a escolha do filtro de situação e recarrega
  const handleSituacao = useCallback((value: string) => {
    setSituacaoFiltro(value);
    setSituacaoPref(value);
  }, []);

  const isManager = useMemo(() => {
    if ((session?.usuario as { master?: boolean } | undefined)?.master) return true;
    const cod = pickFirst(session?.funcionario, ["cod_funcao"]);
    const norm = cod ? cod.toString().padStart(2, "0") : "";
    return norm === "01" || norm === "02"; // gerente ou supervisor
  }, [session]);

  const loadSession = useCallback(async () => {
    setLoading(true);
    const s = await getSession();
    if (!s) {
      router.replace("/login");
      return;
    }
    setSessionState(s);
    setLoading(false);
  }, [router]);

  const loadVendedores = useCallback(async (s: Session) => {
    try {
      const conns = await listConnections();
      const conn = conns.find((c) => c.empresa === s.empresa);
      if (!conn) return;
      const apiBase = conn.api.replace(/\/+$/, "");
      const url =
        `${apiBase}/api/funcionarios` +
        `?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(url);
      const j = await r.json();
      const items: { codigo: number; nome: string; nome_guerra: string }[] = Array.isArray(j?.items)
        ? j.items
        : [];
      setVendedorOpts(
        items.map((f) => ({
          value: f.codigo,
          label: f.nome || f.nome_guerra || `#${f.codigo}`,
          sub: f.nome_guerra && f.nome_guerra !== f.nome ? `@${f.nome_guerra}` : undefined,
        }))
      );
    } catch {
      // silencioso — combobox apenas não popula
    }
  }, []);

  const loadEmpresa = useCallback(async (s: Session) => {
    try {
      const conns = await listConnections();
      const conn = conns.find((c) => c.empresa === s.empresa);
      if (!conn) return;
      const apiBase = conn.api.replace(/\/+$/, "");
      const url =
        `${apiBase}/api/controle/empresa` +
        `?servidor=${encodeURIComponent(conn.servidor)}` +
        `&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(url);
      const j = await r.json();
      if (j?.success) setFantasia(j.fantasia || j.rz_social || null);
    } catch {
      // silencioso — usa o nome da conexão como fallback
    }
  }, []);

  // Carrega o filtro de situação persistido (uma vez)
  useEffect(() => {
    (async () => {
      const saved = await getSituacaoPref();
      if (saved) setSituacaoFiltro(saved);
    })();
  }, []);

  const loadDashboard = useCallback(
    async (s: Session, vendedorOverride?: string | number | null, situacaoOverride?: string) => {
      setDashLoading(true);
      setDashError(null);
      try {
        const conns = await listConnections();
        const conn = conns.find((c) => c.empresa === s.empresa);
        if (!conn) {
          setDashError("Conexão não encontrada.");
          return;
        }
        // Gerente/Supervisor: respeita o filtro (null = todos). Vendedor comum: sempre o próprio.
        let vendedorParam: string;
        if (isManager) {
          vendedorParam =
            vendedorOverride === undefined || vendedorOverride === null
              ? "all"
              : String(vendedorOverride);
        } else {
          const own = s.funcionario?.codigo_int;
          if (own === undefined || own === null) {
            setDashError("Vendedor não identificado na sessão.");
            return;
          }
          vendedorParam = String(own);
        }
        const sit = situacaoOverride !== undefined ? situacaoOverride : situacaoFiltro;
        const apiBase = conn.api.replace(/\/+$/, "");
        const url =
          `${apiBase}/api/dashboard/me` +
          `?servidor=${encodeURIComponent(conn.servidor)}` +
          `&banco=${encodeURIComponent(conn.banco)}` +
          `&vendedor=${encodeURIComponent(vendedorParam)}` +
          (sit ? `&situacao=${encodeURIComponent(sit)}` : "");
        const r = await fetch(url);
        const j = await r.json();
        if (!j?.success) {
          setDashError(j?.message || "Não foi possível obter os totais.");
        }
        setTotais(j?.totais || { pedidos: 0, produtos: 0, servicos: 0, descontos: 0, margem: 0, margem_pct: 0 });
        setPedidos(Array.isArray(j?.pedidos) ? j.pedidos : []);
      } catch (e) {
        setDashError(`Falha de rede: ${e instanceof Error ? e.message : String(e)}`);
      } finally {
        setDashLoading(false);
      }
    },
    [isManager]
  );

  useFocusEffect(
    useCallback(() => {
      loadSession();
    }, [loadSession])
  );

  useEffect(() => {
    loadSession();
  }, [loadSession]);

  useEffect(() => {
    if (session) {
      loadDashboard(session, vendedorFiltro);
      loadEmpresa(session);
      if (isManager) loadVendedores(session);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session, isManager, loadDashboard, loadVendedores, loadEmpresa]);

  // Recarrega ao trocar qualquer filtro (vendedor — gerente/supervisor; situação — todos)
  useEffect(() => {
    if (session) loadDashboard(session, vendedorFiltro, situacaoFiltro);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendedorFiltro, situacaoFiltro]);

  const handleLogout = async () => {
    await clearSession();
    router.replace("/login");
  };

  const displayName = useMemo(() => {
    if (!session) return "";
    const funcName = pickFirst(session.funcionario, ["nome", "nome_guerra", "nome_completo", "apelido"]);
    const usrName = pickFirst(session.usuario, ["nome", "usuario"]);
    return funcName || usrName || "";
  }, [session]);

  const nomeGuerra = useMemo(
    () => pickFirst(session?.funcionario, ["nome_guerra"]) || null,
    [session]
  );

  const totalPedidos = useMemo(
    () => pedidos.reduce((s, p) => s + (p.valor || 0), 0),
    [pedidos]
  );

  const classe = useMemo(
    () => pickFirst(session?.usuario, ["classe_descricao", "classe_label", "classe"]) || null,
    [session]
  );

  // Mapeia funcionarios.cod_funcao para label fixo (somente p/ uso interno em
  // permissões de UI; não exibido na tela conforme regra de negócio).
  // 01 -> Gerente, 02 -> Supervisor, 03 -> Vendedor.
  const funcaoLabel = useMemo<"Gerente" | "Supervisor" | "Vendedor" | null>(() => {
    const cod = pickFirst(session?.funcionario, ["cod_funcao"]);
    if (!cod) return null;
    const norm = cod.toString().padStart(2, "0");
    if (norm === "01") return "Gerente";
    if (norm === "02") return "Supervisor";
    if (norm === "03") return "Vendedor";
    return null;
  }, [session]);
  // funcaoLabel disponível para futura lógica de permissão (ex.: esconder tiles).
  void funcaoLabel;

  if (loading || !session) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="principal-screen">
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.headerTitle}>Back-On</Text>
          <Text style={styles.headerSub} numberOfLines={1}>
            {fantasia || session.empresa}
          </Text>
        </View>
        <Pressable
          onPress={handleLogout}
          style={({ pressed }) => [styles.logoutBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="principal-logout-button"
        >
          <Ionicons name="log-out-outline" size={18} color={colors.onBrandPrimary} />
          <Text style={styles.logoutLabel}>Sair</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* ======== Boas-vindas com classe (grupo) do usuário ======== */}
        <View style={styles.hero} testID="principal-welcome">
          {session.logo ? (
            <Image source={{ uri: session.logo }} style={styles.avatar} resizeMode="cover" testID="principal-logo" />
          ) : (
            <View style={styles.avatar}>
              <Ionicons name="person" size={28} color={colors.onBrandPrimary} />
            </View>
          )}
          <View style={{ flex: 1 }}>
            <Text style={styles.welcome}>Bem-vindo à {session.empresa}</Text>
            <Text style={styles.heroName} numberOfLines={1}>
              {displayName || "Usuário"}
            </Text>
            {nomeGuerra && nomeGuerra !== displayName ? (
              <Text style={styles.heroSub}>@{nomeGuerra}</Text>
            ) : null}
            {classe ? (
              <Text style={styles.heroSub} testID="principal-classe">
                Grupo: {classe}
              </Text>
            ) : null}
          </View>
        </View>

        <Text style={styles.sectionTitle}>Tela Principal</Text>
        <Text style={styles.sectionSub}>Painel de controle. Os módulos do sistema são exibidos abaixo.</Text>

        {/* ======== Tiles dos módulos ======== */}
        <View style={styles.tilesGrid}>
          {[
            { label: "Clientes", icon: "people-outline" as const, route: "/clientes" as const },
            { label: "Produtos & Serviços", icon: "cube-outline" as const, route: "/produtos" as const },
            { label: "Pedidos", icon: "receipt-outline" as const, route: "/pedidos" as const },
          ].map((t) => (
            <Pressable
              key={t.label}
              onPress={() => t.route && router.push(t.route)}
              disabled={!t.route}
              style={({ pressed }) => [styles.tile, pressed && t.route && { opacity: 0.8 }]}
              testID={`principal-tile-${t.label.toLowerCase()}`}
            >
              <View style={styles.tileIcon}>
                <Ionicons name={t.icon} size={22} color={colors.brandPrimary} />
              </View>
              <Text style={styles.tileLabel}>{t.label}</Text>
              <Text style={styles.tileHint}>{t.route ? "Abrir" : "Em breve"}</Text>
            </Pressable>
          ))}
        </View>

        {/* ======== Filtro por vendedor (apenas Gerente/Supervisor) ======== */}
        {isManager ? (
          <View style={styles.filterRow} testID="principal-vendedor-filter">
            <SelectField
              label="Filtrar por vendedor"
              value={vendedorFiltro}
              onChange={setVendedorFiltro}
              options={vendedorOpts}
              placeholder="Todos os vendedores"
              modalTitle="Selecionar vendedor"
              allowClear
              testID="principal-vendedor-select"
            />
          </View>
        ) : null}

        {/* ======== Filtro por situação (todos os usuários) ======== */}
        <View style={styles.sitFilterRow} testID="principal-situacao-filter">
          {SITUACOES.map((s) => {
            const sel = situacaoFiltro === s.value;
            return (
              <Pressable
                key={s.value || "all"}
                onPress={() => handleSituacao(s.value)}
                style={[styles.sitChip, sel && styles.sitChipSel]}
                testID={`principal-sit-${s.value || "todos"}`}
              >
                <Text style={[styles.sitChipText, sel && styles.sitChipTextSel]}>{s.label}</Text>
              </Pressable>
            );
          })}
        </View>

        {/* ======== Totais do dia ======== */}
        <Text style={styles.sectionTitle}>Totais de Hoje</Text>
        <View style={styles.totalsRow} testID="principal-totals">
          <View style={[styles.totalCard, { borderLeftColor: colors.brandPrimary }]}>
            <Text style={styles.totalLabel}>Pedidos</Text>
            <Text style={styles.totalValue} testID="totals-pedidos">
              {dashLoading ? "…" : totais.pedidos}
            </Text>
          </View>
          <View style={[styles.totalCard, { borderLeftColor: colors.success }]}>
            <Text style={styles.totalLabel}>Produtos</Text>
            <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-produtos">
              {dashLoading ? "…" : formatBRL(totais.produtos)}
            </Text>
          </View>
          <View style={[styles.totalCard, { borderLeftColor: colors.warning }]}>
            <Text style={styles.totalLabel}>Serviços</Text>
            <Text style={[styles.totalValue, { fontSize: 16 }]} testID="totals-servicos">
              {dashLoading ? "…" : formatBRL(totais.servicos)}
            </Text>
          </View>
        </View>

        {/* ======== Margem média do dia ======== */}
        <View style={styles.margemCard} testID="principal-margem">
          <View style={styles.margemIcon}>
            <Ionicons name="trending-up" size={20} color={colors.onBrandPrimary} />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.margemLabel}>Margem média do dia</Text>
            <Text style={styles.margemHint}>Venda líquida − custo de reposição</Text>
            <Text style={styles.margemDesc} testID="totals-descontos">
              Descontos concedidos: {dashLoading ? "…" : formatBRL(totais.descontos)}
            </Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.margemValue} testID="totals-margem">
              {dashLoading ? "…" : formatBRL(totais.margem)}
            </Text>
            <Text style={styles.margemPct} testID="totals-margem-pct">
              {dashLoading ? "" : `${(totais.margem_pct || 0).toFixed(2).replace(".", ",")}%`}
            </Text>
          </View>
        </View>

        {/* ======== Listagem de Pedidos do dia ======== */}
        <View style={styles.pedidosHeader}>
          <Text style={styles.sectionTitle}>Pedidos de Hoje</Text>
          {dashLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
        </View>

        {dashError ? (
          <View style={styles.errorBox} testID="principal-dash-error">
            <Ionicons name="alert-circle-outline" size={16} color={colors.error} />
            <Text style={styles.errorText}>{dashError}</Text>
          </View>
        ) : null}

        <View style={styles.pedidosCard} testID="principal-pedidos-list">
          <View style={styles.pedidosHead}>
            <Text style={[styles.pedidoCell, { flex: 0.7 }]}>Pedido</Text>
            <Text style={[styles.pedidoCell, { flex: 2 }]}>Cliente</Text>
            <Text style={[styles.pedidoCell, { flex: 1.2, textAlign: "right" }]}>Valor</Text>
          </View>
          {pedidos.length === 0 && !dashLoading ? (
            <Text style={styles.empty}>Nenhum pedido hoje.</Text>
          ) : (
            pedidos.map((p) => (
              <Pressable
                key={p.pedido}
                onPress={() => router.push({ pathname: "/pedido-form", params: { pedido: String(p.pedido) } })}
                style={({ pressed }) => [styles.pedidoRow, pressed && { backgroundColor: colors.brandTertiary }]}
                testID={`pedido-${p.pedido}`}
              >
                <Text style={[styles.pedidoCellValue, { flex: 0.7 }]}>#{p.pedido}</Text>
                <Text style={[styles.pedidoCellValue, { flex: 2 }]} numberOfLines={1}>
                  {p.cliente || "—"}
                </Text>
                <Text style={[styles.pedidoCellValue, { flex: 1.2, textAlign: "right", fontWeight: "500" }]}>
                  {formatBRL(p.valor)}
                </Text>
              </Pressable>
            ))
          )}
          {pedidos.length > 0 ? (
            <View style={styles.pedidoTotalRow} testID="principal-pedidos-total">
              <Text style={[styles.pedidoTotalLabel, { flex: 2.7 }]}>Total ({pedidos.length})</Text>
              <Text style={[styles.pedidoTotalValue, { flex: 1.2, textAlign: "right" }]}>
                {formatBRL(totalPedidos)}
              </Text>
            </View>
          ) : null}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center",
    paddingHorizontal: spacing.xl, paddingTop: spacing.md, paddingBottom: spacing.md,
    backgroundColor: colors.brandPrimary, gap: spacing.md,
  },
  headerTitle: { fontSize: 20, fontWeight: "500", color: colors.onBrandPrimary, letterSpacing: -0.3 },
  headerSub: { fontSize: 12, color: "rgba(255,255,255,0.75)", marginTop: 2 },
  logoutBtn: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: "rgba(255,255,255,0.15)",
    borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.25)",
  },
  logoutLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl },
  hero: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    padding: spacing.lg, borderWidth: 1, borderColor: colors.border,
  },
  avatar: {
    width: 56, height: 56, borderRadius: 28,
    backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  welcome: { fontSize: 12, color: colors.muted },
  heroName: { fontSize: 18, fontWeight: "500", color: colors.onSurface, marginTop: 2 },
  heroSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  sectionTitle: {
    fontSize: 13, fontWeight: "500", color: colors.onSurface,
    marginTop: spacing.lg, marginBottom: spacing.sm,
    textTransform: "uppercase", letterSpacing: 0.5,
  },
  sectionSub: { fontSize: 13, color: colors.muted, marginBottom: spacing.md },
  tilesGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  tile: {
    width: "47%", backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border, minHeight: 92,
    justifyContent: "space-between",
  },
  tileIcon: {
    width: 36, height: 36, borderRadius: radius.md,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center", marginBottom: spacing.sm,
  },
  tileLabel: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  tileHint: { fontSize: 11, color: colors.muted, marginTop: 2 },
  totalsRow: { flexDirection: "row", gap: spacing.sm },
  filterRow: { flexDirection: "row", marginTop: spacing.md },
  sitFilterRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: spacing.sm, marginBottom: spacing.xs },
  sitChip: {
    paddingHorizontal: 10, paddingVertical: 5, borderRadius: 14,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface,
  },
  sitChipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  sitChipText: { fontSize: 12, color: colors.muted },
  sitChipTextSel: { color: colors.brandPrimary, fontWeight: "600" },
  margemCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.md, padding: spacing.md,
    marginTop: spacing.sm, borderLeftWidth: 4, borderLeftColor: colors.brandPrimary,
  },
  margemIcon: {
    width: 38, height: 38, borderRadius: 19, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  margemLabel: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  margemHint: { fontSize: 11, color: colors.muted, marginTop: 1 },
  margemDesc: { fontSize: 12, color: colors.error, fontWeight: "500", marginTop: 3 },
  margemValue: { fontSize: 17, fontWeight: "700", color: colors.brandPrimary },
  margemPct: { fontSize: 12, fontWeight: "600", color: colors.success },
  totalCard: {
    flex: 1, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
    borderLeftWidth: 4,
  },
  totalLabel: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5 },
  totalValue: { fontSize: 22, fontWeight: "600", color: colors.onSurface, marginTop: 4 },
  pedidosHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  pedidosCard: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
  },
  pedidosHead: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: colors.brandTertiary, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  pedidoCell: { fontSize: 11, color: colors.brandPrimary, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.4 },
  pedidoRow: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border, alignItems: "center",
  },
  pedidoCellValue: { fontSize: 13, color: colors.onSurface },
  pedidoTotalRow: {
    flexDirection: "row", paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    backgroundColor: colors.brandTertiary, alignItems: "center",
    borderTopWidth: 1, borderTopColor: colors.border,
  },
  pedidoTotalLabel: { fontSize: 13, fontWeight: "600", color: colors.brandPrimary },
  pedidoTotalValue: { fontSize: 15, fontWeight: "700", color: colors.brandPrimary },
  empty: { textAlign: "center", color: colors.muted, paddingVertical: spacing.lg, fontSize: 13 },
  errorBox: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: "#fdecea", padding: spacing.sm, borderRadius: radius.sm,
    marginBottom: spacing.sm,
  },
  errorText: { color: colors.error, fontSize: 12, flex: 1 },
});
