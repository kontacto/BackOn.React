import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";

type ClienteRow = { codigo: number; nome: string; cgc_cpf: string; telefone: string };
type ClienteResumo = { codigo: number; nome: string; cgc_cpf: string; e_mail: string; telefone: string; endereco: string };
type AreaAtuacao = { codigo: number; descricao: string };
type Funcionario = { codigo: number; nome: string; nome_guerra: string; cod_funcao: string };
type PedidoData = {
  pedido: number; cliente: number | null; cliente_nome: string; cliente_cgc: string;
  data: string | null; validade: string | null;
  vendedor: number | null; vendedor_nome: string;
  hora_aberto: string; obs: string; situacao: string; situacao_label: string; total: number;
  area_atuacao: number | null; area_descricao: string;
};

const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

function formatDateBR(iso: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}
function todayISO() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export default function PedidoFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ pedido?: string; cliente?: string; cliente_nome?: string }>();
  const editing = !!params.pedido;
  const pedidoId = params.pedido ? parseInt(String(params.pedido), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [vendedor, setVendedor] = useState<number | null>(null);
  const [vendedorNome, setVendedorNome] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone: "info" | "error" | "success" } | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: "info" | "error" | "success" = "info") => {
    setToast({ msg: m, tone: t });
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), 3500);
  }, []);

  const [pedido, setPedido] = useState<PedidoData | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [validade, setValidade] = useState("");
  const [obs, setObs] = useState("");

  // Modal de busca de cliente
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // -------- Init
  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const cod = s?.funcionario?.codigo_int;
      if (typeof cod === "number") setVendedor(cod);
      else if (typeof cod === "string" && /^\d+$/.test(cod)) setVendedor(parseInt(cod, 10));
      const fnome = (s?.funcionario?.nome_guerra || s?.funcionario?.nome || "") as string;
      setVendedorNome(fnome);

      // Pré-seleciona cliente vindo da rota (criação direto da lista de clientes)
      if (!editing && params.cliente && params.cliente_nome) {
        setCliente({
          codigo: parseInt(String(params.cliente), 10),
          nome: String(params.cliente_nome),
          cgc_cpf: "", telefone: "",
        });
      }

      if (editing && pedidoId && c) {
        const r = await fetch(
          `${c.api.replace(/\/+$/, "")}/api/pedidos/${pedidoId}?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`
        );
        const j = await r.json();
        if (j?.success && j.pedido) {
          const p: PedidoData = j.pedido;
          setPedido(p);
          if (p.cliente) setCliente({ codigo: p.cliente, nome: p.cliente_nome, cgc_cpf: p.cliente_cgc, telefone: "" });
          setValidade(p.validade || "");
          setObs(p.obs || "");
        } else {
          showToast(j?.message || "Erro ao carregar pedido.", "error");
        }
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------- Busca cliente (debounce)
  useEffect(() => {
    if (!searchOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const url = `${conn.api.replace(/\/+$/, "")}/api/clientes/find/search?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&term=${encodeURIComponent(searchTerm)}`;
        const r = await fetch(url);
        const j = await r.json();
        setSearchResults(j?.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, searchOpen, conn]);

  const handleSave = async () => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    if (vendedor == null) { showToast("Vendedor não identificado na sessão.", "error"); return; }
    setSaving(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        cliente: cliente.codigo, vendedor,
        validade: validade || null, obs,
      };
      const base = conn.api.replace(/\/+$/, "");
      const url = editing && pedidoId ? `${base}/api/pedidos/${pedidoId}` : `${base}/api/pedidos/create`;
      const r = await fetch(url, { method: editing ? "PUT" : "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else {
        showToast(editing ? "Pedido atualizado." : `Pedido #${j.pedido} criado.`, "success");
        setTimeout(() => router.back(), 700);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setSaving(false); }
  };

  const sit = pedido?.situacao || "A";
  const sitColor = useMemo(() => SIT_COLOR[sit] || colors.muted, [sit]);

  if (loading) return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="pedido-form-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]} hitSlop={12}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>{editing ? `Pedido #${pedidoId}` : "Novo Pedido"}</Text>
        <Pressable onPress={handleSave} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} hitSlop={8} testID="pedido-form-save">
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <><Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} /><Text style={styles.saveLabel}>Gravar</Text></>}
        </Pressable>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {/* Cabeçalho do pedido */}
          {editing && pedido ? (
            <View style={[styles.row, { marginBottom: spacing.md }]}>
              <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                <Text style={[styles.sitTagText, { color: sitColor }]}>{pedido.situacao_label}</Text>
              </View>
              <Text style={styles.headerMeta}>Aberto {formatDateBR(pedido.data)} {pedido.hora_aberto}</Text>
            </View>
          ) : null}

          {/* Cliente */}
          <Text style={styles.sectionTitle}>Cliente</Text>
          <Pressable
            onPress={() => { setSearchTerm(""); setSearchResults([]); setSearchOpen(true); }}
            style={({ pressed }) => [styles.clienteBox, pressed && { opacity: 0.8 }]}
            testID="pedido-form-cliente-select"
          >
            {cliente ? (
              <View style={{ flex: 1 }}>
                <Text style={styles.clienteNome} numberOfLines={1}>{cliente.nome}</Text>
                <Text style={styles.clienteSub} numberOfLines={1}>
                  #{cliente.codigo}{cliente.cgc_cpf ? ` · ${cliente.cgc_cpf}` : ""}{cliente.telefone ? ` · ${cliente.telefone}` : ""}
                </Text>
              </View>
            ) : (
              <View style={{ flex: 1, flexDirection: "row", alignItems: "center", gap: 8 }}>
                <Ionicons name="search" size={18} color={colors.muted} />
                <Text style={[styles.clienteSub, { fontSize: 14 }]}>Buscar cliente por nome, CPF ou telefone…</Text>
              </View>
            )}
            <Ionicons name="chevron-forward" size={18} color={colors.muted} />
          </Pressable>

          {/* Vendedor (readonly da sessão) */}
          <Text style={styles.sectionTitle}>Vendedor</Text>
          <View style={styles.readonlyBox} testID="pedido-form-vendedor">
            <Ionicons name="person-circle-outline" size={18} color={colors.brandPrimary} />
            <Text style={styles.readonlyText}>
              {vendedor != null ? `${vendedorNome || "Funcionário"} (#${vendedor})` : "Não identificado na sessão"}
            </Text>
          </View>

          {/* Datas */}
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.sectionTitle}>Data</Text>
              <View style={styles.readonlyBox}>
                <Ionicons name="calendar-outline" size={16} color={colors.muted} />
                <Text style={styles.readonlyText}>
                  {editing ? formatDateBR(pedido?.data || null) : formatDateBR(todayISO())}
                </Text>
              </View>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.sectionTitle}>Validade</Text>
              <TextInput
                value={validade}
                onChangeText={(v) => setValidade(v.replace(/[^\d-]/g, "").slice(0, 10))}
                placeholder="AAAA-MM-DD"
                placeholderTextColor={colors.muted}
                style={styles.input}
                keyboardType="numbers-and-punctuation"
                testID="pedido-form-validade"
              />
            </View>
          </View>

          {/* Observação */}
          <Text style={styles.sectionTitle}>Observação</Text>
          <TextInput
            value={obs}
            onChangeText={setObs}
            placeholder="Observação do pedido"
            placeholderTextColor={colors.muted}
            style={[styles.input, { minHeight: 100, textAlignVertical: "top", paddingTop: 12 }]}
            multiline
            testID="pedido-form-obs"
          />

          <View style={{ height: 80 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Modal busca de cliente */}
      <Modal visible={searchOpen} transparent animationType="slide" onRequestClose={() => setSearchOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setSearchOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Buscar Cliente</Text>
              <Pressable onPress={() => setSearchOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={searchTerm}
                onChangeText={setSearchTerm}
                placeholder="Nome, CPF/CNPJ ou telefone…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                autoFocus
                testID="pedido-form-search-input"
              />
            </View>
            {searchLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
            <ScrollView style={{ maxHeight: 380 }}>
              {searchResults.map((c) => (
                <Pressable
                  key={c.codigo}
                  onPress={() => { setCliente(c); setSearchOpen(false); }}
                  style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                  testID={`pedido-form-result-${c.codigo}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultNome} numberOfLines={1}>{c.nome}</Text>
                    <Text style={styles.resultSub} numberOfLines={1}>
                      #{c.codigo}{c.cgc_cpf ? ` · ${c.cgc_cpf}` : ""}{c.telefone ? ` · ${c.telefone}` : ""}
                    </Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={colors.muted} />
                </Pressable>
              ))}
              {!searchLoading && searchTerm.length >= 2 && searchResults.length === 0 ? (
                <View style={styles.emptyBox}>
                  <Text style={styles.emptyText}>Nenhum cliente encontrado.</Text>
                  <Pressable
                    onPress={() => {
                      setSearchOpen(false);
                      router.push({ pathname: "/cliente-form", params: { initial_nome: searchTerm } });
                    }}
                    style={({ pressed }) => [styles.createBtn, pressed && { opacity: 0.8 }]}
                    testID="pedido-form-criar-cliente"
                  >
                    <Ionicons name="person-add-outline" size={18} color={colors.onBrandPrimary} />
                    <Text style={styles.createBtnText}>Cadastrar novo cliente</Text>
                  </Pressable>
                </View>
              ) : null}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? (
        <View style={[styles.toast, toast.tone === "error" && { backgroundColor: colors.error }, toast.tone === "success" && { backgroundColor: colors.success }]} testID="pedido-form-toast">
          <Text style={styles.toastText}>{toast.msg}</Text>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  sectionTitle: { fontSize: 12, color: colors.muted, marginTop: spacing.md, marginBottom: 4, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.5 },
  row: { flexDirection: "row", gap: 8, alignItems: "center" },
  headerMeta: { fontSize: 12, color: colors.muted },
  clienteBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  clienteNome: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  clienteSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  readonlyBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    borderWidth: 1, borderColor: colors.border, minHeight: 42,
  },
  readonlyText: { fontSize: 14, color: colors.onSurface },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl,
    minHeight: 460,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  resultRow: {
    flexDirection: "row", alignItems: "center", gap: 8,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  resultNome: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  resultSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  emptyBox: { alignItems: "center", padding: spacing.xl, gap: spacing.md },
  emptyText: { color: colors.muted, fontSize: 13 },
  createBtn: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.lg, paddingVertical: 12,
    borderRadius: radius.pill,
  },
  createBtnText: { color: colors.onBrandPrimary, fontWeight: "500" },
  toast: {
    position: "absolute", left: spacing.lg, right: spacing.lg, top: "45%",
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md,
    shadowColor: "#000", shadowOpacity: 0.35, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 12,
    alignItems: "center",
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
});
