import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";

type ClienteRow = { codigo: number; nome: string; cgc_cpf: string; telefone: string };
type ClienteResumo = {
  codigo: number; nome: string; cgc_cpf: string; e_mail: string;
  telefone: string; endereco: string;
};
type AreaAtuacao = { codigo: number; descricao: string };
type Funcionario = { codigo: number; nome: string; nome_guerra: string; cod_funcao: string };
type PedidoData = {
  pedido: number; cliente: number | null; cliente_nome: string; cliente_cgc: string;
  data: string | null; validade: string | null;
  vendedor: number | null; vendedor_nome: string;
  hora_aberto: string; obs: string; situacao: string; situacao_label: string; total: number;
  area_atuacao: number | null; area_descricao: string;
};
type ItemRow = {
  codauto: number; produto: string; tipo: "P" | "S" | "?";
  descricao: string; complemento: string; cod_fab: string; unidade: string;
  qtd: number; p_normal: number; valor_unitario: number; desconto: number; acrescimo: number; total: number;
};
type ProdutoServico = {
  tipo: "P" | "S"; codigo: string; descricao: string; valor: number;
  estoque: number | null; cod_fab?: string; unidade?: string;
};
type DescontoRow = {
  cod: number; tipo_desconto: string; tipo_label: string; descricao: string;
  percentual: number; valor_unitario: number; qtd: number; valor_total: number; usuario: number;
};

function formatBRL(v: number): string {
  return (v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function parseNum(s: string): number {
  const n = parseFloat(String(s).replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}
function round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100;
}
function fmtNum(n: number): string {
  return String(Math.round((n + Number.EPSILON) * 1000) / 1000).replace(".", ",");
}
// Desconto unitário em R$: se % preenchido usa p_normal*%/100, senão usa o valor em R$.
function calcDescUnit(pNormal: number, pctStr: string, rsStr: string): number {
  const pct = parseNum(pctStr);
  if (pct > 0) return round2((pNormal * pct) / 100);
  return parseNum(rsStr);
}

const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

// Funções que podem alterar vendedor: 01 (Administrador) e 02 (Gerente)
const VENDEDOR_EDIT_FUNCOES = ["01", "02"];

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
  const [vendedorCanEdit, setVendedorCanEdit] = useState(false);
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
  const [clienteResumo, setClienteResumo] = useState<ClienteResumo | null>(null);
  const [loadingResumo, setLoadingResumo] = useState(false);
  const [validade, setValidade] = useState<string | null>(null);
  const [obs, setObs] = useState("");
  const [areaAtuacao, setAreaAtuacao] = useState<number | null>(null);

  const [areas, setAreas] = useState<AreaAtuacao[]>([]);
  const [funcionarios, setFuncionarios] = useState<Funcionario[]>([]);

  // Modal de busca de cliente
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // -------- Itens do pedido
  const [itens, setItens] = useState<ItemRow[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [itensLoading, setItensLoading] = useState(false);

  // Modal de adicionar item (busca produto/serviço)
  const [addOpen, setAddOpen] = useState(false);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoServico[]>([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [selProd, setSelProd] = useState<ProdutoServico | null>(null);
  const [addQtd, setAddQtd] = useState("1");
  const [addValor, setAddValor] = useState("0,00");
  const [addDescPct, setAddDescPct] = useState("");
  const [addDescRs, setAddDescRs] = useState("");
  const [addAcr, setAddAcr] = useState("");
  const [addCompl, setAddCompl] = useState("");
  const [addSaving, setAddSaving] = useState(false);

  // Modal de editar item existente
  const [editItem, setEditItem] = useState<ItemRow | null>(null);
  const [editQtd, setEditQtd] = useState("1");
  const [editValor, setEditValor] = useState("0,00");
  const [editDescPct, setEditDescPct] = useState("");
  const [editDescRs, setEditDescRs] = useState("");
  const [editAcr, setEditAcr] = useState("");
  const [editCompl, setEditCompl] = useState("");
  const [editSaving, setEditSaving] = useState(false);

  // Código do usuário logado p/ log de descontos (-2 = KONTACTO master)
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);

  // Modal relatório de descontos
  const [descModalOpen, setDescModalOpen] = useState(false);
  const [descItems, setDescItems] = useState<DescontoRow[]>([]);
  const [descTotalApi, setDescTotalApi] = useState(0);
  const [descLoading, setDescLoading] = useState(false);

  const isAberto = (pedido?.situacao || "A").toUpperCase() === "A";

  const descTotalItens = useMemo(
    () => itens.reduce((s, it) => s + (it.desconto || 0) * (it.qtd || 0), 0),
    [itens]
  );

  // -------- Init
  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);

      // Vendedor da sessão
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number"
        ? cod
        : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      setVendedor(vCod);
      const isMaster = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(isMaster ? -2 : (typeof vCod === "number" ? vCod : -2));
      const fnome = (s?.funcionario?.nome_guerra || s?.funcionario?.nome || "") as string;
      setVendedorNome(fnome);

      // Quem pode alterar o vendedor: cod_funcao 01 ou 02
      const codFuncao = String(s?.funcionario?.cod_funcao || "").trim().padStart(2, "0");
      setVendedorCanEdit(VENDEDOR_EDIT_FUNCOES.includes(codFuncao));

      // Pré-seleciona cliente vindo da rota
      if (!editing && params.cliente && params.cliente_nome) {
        setCliente({
          codigo: parseInt(String(params.cliente), 10),
          nome: String(params.cliente_nome),
          cgc_cpf: "", telefone: "",
        });
      }

      // Carrega listas (áreas e funcionários) em paralelo
      if (c) {
        const base = c.api.replace(/\/+$/, "");
        const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
        try {
          const [ra, rf] = await Promise.all([
            fetch(`${base}/api/area-atuacao?${qs}`).then((r) => r.json()).catch(() => null),
            fetch(`${base}/api/funcionarios?${qs}`).then((r) => r.json()).catch(() => null),
          ]);
          if (ra?.success) setAreas(ra.items || []);
          if (rf?.success) setFuncionarios(rf.items || []);
        } catch {
          // silencioso — combobox vazio
        }
      }

      // Carrega pedido em modo edição
      if (editing && pedidoId && c) {
        try {
          const r = await fetch(
            `${c.api.replace(/\/+$/, "")}/api/pedidos/${pedidoId}?servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`
          );
          const j = await r.json();
          if (j?.success && j.pedido) {
            const p: PedidoData = j.pedido;
            setPedido(p);
            if (p.cliente) setCliente({ codigo: p.cliente, nome: p.cliente_nome, cgc_cpf: p.cliente_cgc, telefone: "" });
            setValidade(p.validade || null);
            setObs(p.obs || "");
            setAreaAtuacao(p.area_atuacao ?? null);
            if (p.vendedor != null) setVendedor(p.vendedor);
            if (p.vendedor_nome) setVendedorNome(p.vendedor_nome);
          } else {
            showToast(j?.message || "Erro ao carregar pedido.", "error");
          }
        } catch (e) {
          showToast(`Erro ao carregar: ${e instanceof Error ? e.message : String(e)}`, "error");
        }
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // -------- Carrega resumo do cliente sempre que muda
  useEffect(() => {
    if (!conn || !cliente?.codigo) {
      setClienteResumo(null);
      return;
    }
    let cancelled = false;
    setLoadingResumo(true);
    const base = conn.api.replace(/\/+$/, "");
    const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
    fetch(`${base}/api/clientes/${cliente.codigo}/resumo?${qs}`)
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        if (j?.success && j.cliente) setClienteResumo(j.cliente);
        else setClienteResumo(null);
      })
      .catch(() => { if (!cancelled) setClienteResumo(null); })
      .finally(() => { if (!cancelled) setLoadingResumo(false); });
    return () => { cancelled = true; };
  }, [conn, cliente?.codigo]);

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

  // -------- Itens do pedido (carrega só em modo edição)
  const loadItens = useCallback(async () => {
    if (!conn || !editing || !pedidoId) return;
    setItensLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/pedidos/${pedidoId}/itens?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setItens(j.items || []);
        setSubtotal(j.subtotal || 0);
      }
    } catch {
      // silencioso
    } finally {
      setItensLoading(false);
    }
  }, [conn, editing, pedidoId]);

  // Recarrega itens ao focar a tela (ex.: voltar da lista de produtos)
  useFocusEffect(
    useCallback(() => {
      loadItens();
    }, [loadItens])
  );

  // -------- Busca produto/serviço (debounce) dentro do modal de adicionar
  useEffect(() => {
    if (!addOpen || !conn) return;
    const t = setTimeout(async () => {
      setProdLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const url = `${base}/api/produtos-servicos?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&search=${encodeURIComponent(prodTerm)}&page=1&size=30&tipo=all`;
        const r = await fetch(url);
        const j = await r.json();
        setProdResults(j?.items || []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [prodTerm, addOpen, conn]);

  const openAddModal = () => {
    setSelProd(null);
    setProdTerm("");
    setProdResults([]);
    setAddQtd("1");
    setAddValor("0,00");
    setAddCompl("");
    setAddOpen(true);
  };

  const pickProduto = (p: ProdutoServico) => {
    setSelProd(p);
    setAddQtd("1");
    setAddValor(formatBRL(p.valor).replace("R$", "").trim());
    setAddDescPct(""); setAddDescRs(""); setAddAcr("");
    setAddCompl("");
  };

  const handleAddItem = async () => {
    if (!conn || !pedidoId || !selProd) return;
    const qtd = parseNum(addQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(addValor);
    const descUnit = calcDescUnit(pNormal, addDescPct, addDescRs);
    const acr = parseNum(addAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setAddSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/pedidos/${pedidoId}/itens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco,
          produto: selProd.codigo,
          qtd,
          valor_unitario: pNormal,
          desconto: descUnit,
          desconto_pct: parseNum(addDescPct),
          acrescimo: acr,
          usuario_codigo: usuarioCod,
          complemento: addCompl,
        }),
      });
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao adicionar.", "error"); }
      else {
        setAddOpen(false);
        showToast("Item adicionado.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setAddSaving(false); }
  };

  const openEditModal = (it: ItemRow) => {
    if (!isAberto) { showToast("Pedido não pode ser alterado.", "error"); return; }
    setEditItem(it);
    setEditQtd(fmtNum(it.qtd));
    setEditValor(formatBRL(it.p_normal || it.valor_unitario).replace("R$", "").trim());
    setEditDescPct("");
    setEditDescRs(it.desconto > 0 ? fmtNum(it.desconto) : "");
    setEditAcr(it.acrescimo > 0 ? fmtNum(it.acrescimo) : "");
    setEditCompl(it.complemento || "");
  };

  const handleUpdateItem = async () => {
    if (!conn || !pedidoId || !editItem) return;
    const qtd = parseNum(editQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(editValor);
    const descUnit = calcDescUnit(pNormal, editDescPct, editDescRs);
    const acr = parseNum(editAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setEditSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(`${base}/api/pedidos/${pedidoId}/itens/${editItem.codauto}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          servidor: conn.servidor, banco: conn.banco,
          qtd,
          valor_unitario: pNormal,
          complemento: editCompl,
          desconto: descUnit,
          desconto_pct: parseNum(editDescPct),
          acrescimo: acr,
          usuario_codigo: usuarioCod,
        }),
      });
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao salvar.", "error"); }
      else {
        setEditItem(null);
        showToast("Item atualizado.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  const handleDeleteItem = async (it: ItemRow) => {
    if (!conn || !pedidoId) return;
    setEditSaving(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/pedidos/${pedidoId}/itens/${it.codauto}?${qs}`, { method: "DELETE" });
      const j = await r.json();
      if (!j?.success) { showToast(j?.message || "Falha ao remover.", "error"); }
      else {
        setEditItem(null);
        showToast("Item removido.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEditSaving(false); }
  };

  const openDescontos = async () => {
    if (!conn || !pedidoId) return;
    setDescModalOpen(true);
    setDescLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(`${base}/api/pedidos/${pedidoId}/descontos?${qs}`);
      const j = await r.json();
      if (j?.success) {
        setDescItems(j.items || []);
        setDescTotalApi(j.total || 0);
      }
    } catch {
      // silencioso
    } finally { setDescLoading(false); }
  };


  const handleSave = async () => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    if (vendedor == null) { showToast("Vendedor não identificado.", "error"); return; }
    setSaving(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        cliente: cliente.codigo,
        vendedor,
        validade: validade || null,
        obs,
        area_atuacao: areaAtuacao,
      };
      const base = conn.api.replace(/\/+$/, "");
      const url = editing && pedidoId ? `${base}/api/pedidos/${pedidoId}` : `${base}/api/pedidos/create`;
      const r = await fetch(url, {
        method: editing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else {
        if (editing) {
          showToast("Pedido atualizado.", "success");
          setTimeout(() => router.back(), 700);
        } else {
          showToast(`Pedido #${j.pedido} criado. Adicione os itens.`, "success");
          setTimeout(
            () => router.replace({ pathname: "/pedido-form", params: { pedido: String(j.pedido) } }),
            700
          );
        }
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setSaving(false); }
  };

  const sit = pedido?.situacao || "A";
  const sitColor = useMemo(() => SIT_COLOR[sit] || colors.muted, [sit]);

  // Opções dos comboboxes
  const areaOptions: SelectOption[] = useMemo(
    () => areas.map((a) => ({ value: a.codigo, label: a.descricao })),
    [areas]
  );
  const vendedorOptions: SelectOption[] = useMemo(
    () => funcionarios.map((f) => ({
      value: f.codigo,
      label: f.nome_guerra || f.nome,
      sub: `#${f.codigo}${f.nome_guerra && f.nome !== f.nome_guerra ? ` · ${f.nome}` : ""}`,
    })),
    [funcionarios]
  );

  // Se o vendedor atual não estiver na lista de ativos (ex.: usuário inativo),
  // adiciona uma opção "ghost" para que seja exibido o label corretamente.
  const vendedorOptionsWithGhost: SelectOption[] = useMemo(() => {
    if (vendedor == null) return vendedorOptions;
    const exists = vendedorOptions.some((o) => Number(o.value) === vendedor);
    if (exists) return vendedorOptions;
    return [
      { value: vendedor, label: vendedorNome || `Funcionário #${vendedor}`, sub: `#${vendedor}` },
      ...vendedorOptions,
    ];
  }, [vendedor, vendedorNome, vendedorOptions]);

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
                  #{cliente.codigo}{cliente.cgc_cpf ? ` · ${cliente.cgc_cpf}` : ""}
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

          {/* Resumo do cliente: telefone + endereço */}
          {cliente ? (
            <View style={styles.resumoBox} testID="pedido-form-cliente-resumo">
              {loadingResumo ? (
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <ActivityIndicator size="small" color={colors.brandPrimary} />
                  <Text style={styles.resumoText}>Carregando dados…</Text>
                </View>
              ) : clienteResumo ? (
                <>
                  <View style={styles.resumoRow}>
                    <Ionicons name="call-outline" size={14} color={colors.brandPrimary} />
                    <Text style={styles.resumoText} numberOfLines={1}>
                      {clienteResumo.telefone || "Sem telefone"}
                    </Text>
                  </View>
                  <View style={styles.resumoRow}>
                    <Ionicons name="location-outline" size={14} color={colors.brandPrimary} />
                    <Text style={styles.resumoText} numberOfLines={2}>
                      {clienteResumo.endereco || "Sem endereço cadastrado"}
                    </Text>
                  </View>
                  {clienteResumo.e_mail ? (
                    <View style={styles.resumoRow}>
                      <Ionicons name="mail-outline" size={14} color={colors.brandPrimary} />
                      <Text style={styles.resumoText} numberOfLines={1}>{clienteResumo.e_mail}</Text>
                    </View>
                  ) : null}
                </>
              ) : (
                <Text style={styles.resumoText}>Dados do cliente indisponíveis.</Text>
              )}
            </View>
          ) : null}

          {/* Vendedor */}
          <Text style={styles.sectionTitle}>
            Vendedor {!vendedorCanEdit ? <Text style={styles.lockHint}>(sem permissão para alterar)</Text> : null}
          </Text>
          <SelectField
            value={vendedor}
            onChange={(v) => setVendedor(v == null ? null : Number(v))}
            options={vendedorOptionsWithGhost}
            placeholder="Selecione o vendedor"
            disabled={!vendedorCanEdit}
            modalTitle="Selecionar Vendedor"
            testID="pedido-form-vendedor"
          />

          {/* Área de atuação */}
          <Text style={styles.sectionTitle}>Área de Atuação</Text>
          <SelectField
            value={areaAtuacao}
            onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
            options={areaOptions}
            placeholder="Selecione a área"
            modalTitle="Selecionar Área de Atuação"
            allowClear
            testID="pedido-form-area"
          />

          {/* Datas */}
          <View style={styles.dateRow}>
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
              <DateField
                value={validade}
                onChange={setValidade}
                placeholder="DD/MM/AAAA"
                testID="pedido-form-validade"
                minimumDate={new Date()}
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

          {/* Itens do Pedido */}
          <View style={styles.itensHeader}>
            <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>
              Itens do Pedido {itens.length ? `(${itens.length})` : ""}
            </Text>
            {editing && isAberto ? (
              <Pressable
                onPress={openAddModal}
                style={({ pressed }) => [styles.addItemBtn, pressed && { opacity: 0.8 }]}
                testID="pedido-form-add-item"
              >
                <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.addItemBtnText}>Adicionar</Text>
              </Pressable>
            ) : null}
          </View>

          {!editing ? (
            <View style={styles.itensHint}>
              <Ionicons name="information-circle-outline" size={18} color={colors.muted} />
              <Text style={styles.itensHintText}>Grave o pedido para adicionar itens.</Text>
            </View>
          ) : itensLoading && itens.length === 0 ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : itens.length === 0 ? (
            <View style={styles.itensHint}>
              <Ionicons name="cube-outline" size={18} color={colors.muted} />
              <Text style={styles.itensHintText}>Nenhum item adicionado.</Text>
            </View>
          ) : (
            <View style={{ gap: 8 }}>
              {itens.map((it) => (
                <Pressable
                  key={it.codauto}
                  onPress={() => openEditModal(it)}
                  style={({ pressed }) => [styles.itemRow, pressed && { opacity: 0.8 }]}
                  testID={`pedido-form-item-${it.codauto}`}
                >
                  <View style={[styles.itemTipo, it.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                    <Ionicons
                      name={it.tipo === "P" ? "cube" : "construct"}
                      size={16}
                      color={it.tipo === "P" ? colors.brandPrimary : colors.warning}
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.itemDesc} numberOfLines={1}>{it.descricao || it.produto}</Text>
                    {it.complemento ? (
                      <Text style={styles.itemCompl} numberOfLines={1}>{it.complemento}</Text>
                    ) : null}
                    <Text style={styles.itemSub}>
                      {it.cod_fab ? `${it.cod_fab} · ` : ""}{it.qtd.toLocaleString("pt-BR")} {it.unidade} × {formatBRL(it.valor_unitario)}
                    </Text>
                  </View>
                  <Text style={styles.itemTotal}>{formatBRL(it.total)}</Text>
                </Pressable>
              ))}

              {descTotalItens > 0 ? (
                <TouchableOpacity
                  onPress={openDescontos}
                  activeOpacity={0.8}
                  style={styles.descBtn}
                  testID="pedido-form-descontos-btn"
                >
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <Ionicons name="pricetag" size={15} color={colors.error} />
                    <Text style={styles.descBtnLabel}>Descontos concedidos</Text>
                  </View>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Text style={styles.descBtnValue}>- {formatBRL(descTotalItens)}</Text>
                    <Ionicons name="chevron-forward" size={16} color={colors.error} />
                  </View>
                </TouchableOpacity>
              ) : null}

              <View style={styles.subtotalRow}>
                <Text style={styles.subtotalLabel}>Subtotal</Text>
                <Text style={styles.subtotalValue}>{formatBRL(subtotal)}</Text>
              </View>
            </View>
          )}

          <View style={{ height: 80 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Modal adicionar item */}
      <Modal visible={addOpen} transparent animationType="slide" onRequestClose={() => setAddOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setAddOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{selProd ? "Confirmar Item" : "Adicionar Item"}</Text>
              <Pressable onPress={() => setAddOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>

            {!selProd ? (
              <>
                <View style={styles.searchWrap}>
                  <Ionicons name="search" size={16} color={colors.muted} />
                  <TextInput
                    value={prodTerm}
                    onChangeText={setProdTerm}
                    placeholder="Buscar produto ou serviço…"
                    placeholderTextColor={colors.muted}
                    style={styles.searchInput}
                    autoFocus
                    testID="pedido-form-prod-search"
                  />
                </View>
                {prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
                <ScrollView style={{ maxHeight: 360 }} keyboardShouldPersistTaps="handled">
                  {prodResults.map((p) => (
                    <Pressable
                      key={`${p.tipo}-${p.codigo}`}
                      onPress={() => pickProduto(p)}
                      style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                      testID={`pedido-form-prod-${p.codigo}`}
                    >
                      <View style={[styles.itemTipo, p.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                        <Ionicons name={p.tipo === "P" ? "cube" : "construct"} size={16} color={p.tipo === "P" ? colors.brandPrimary : colors.warning} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.resultNome} numberOfLines={1}>{p.descricao}</Text>
                        <Text style={styles.resultSub} numberOfLines={1}>
                          #{p.codigo}{p.cod_fab ? ` · ${p.cod_fab}` : ""}
                        </Text>
                      </View>
                      <Text style={styles.itemTotal}>{formatBRL(p.valor)}</Text>
                    </Pressable>
                  ))}
                  {!prodLoading && prodResults.length === 0 ? (
                    <Text style={styles.emptyText}>Nenhum produto/serviço encontrado.</Text>
                  ) : null}
                </ScrollView>
                <Pressable
                  onPress={() => {
                    setAddOpen(false);
                    router.push({ pathname: "/produtos", params: { pedido: String(pedidoId) } });
                  }}
                  style={({ pressed }) => [styles.fullListBtn, pressed && { opacity: 0.8 }]}
                  testID="pedido-form-open-produtos"
                >
                  <Ionicons name="grid-outline" size={16} color={colors.brandPrimary} />
                  <Text style={styles.fullListText}>Abrir lista completa de produtos</Text>
                </Pressable>
              </>
            ) : (
              <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
                <View style={{ gap: spacing.sm }}>
                  <View style={styles.selProdBox}>
                    <Text style={styles.itemDesc} numberOfLines={2}>{selProd.descricao}</Text>
                    <Text style={styles.resultSub}>#{selProd.codigo}{selProd.cod_fab ? ` · ${selProd.cod_fab}` : ""}</Text>
                  </View>
                  <View style={styles.qtdRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Quantidade</Text>
                      <View style={styles.qtdInputRow}>
                        <TextInput
                          value={addQtd}
                          onChangeText={setAddQtd}
                          keyboardType="decimal-pad"
                          style={[styles.input, { flex: 1 }]}
                          testID="pedido-form-add-qtd"
                        />
                        <TouchableOpacity
                          onPress={() => setAddQtd(fmtNum(parseNum(addQtd) + 1))}
                          activeOpacity={0.7}
                          style={styles.plusBtn}
                          testID="pedido-form-add-qtd-plus"
                        >
                          <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                        </TouchableOpacity>
                      </View>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Valor unitário</Text>
                      <TextInput
                        value={addValor}
                        onChangeText={setAddValor}
                        keyboardType="decimal-pad"
                        style={styles.input}
                        testID="pedido-form-add-valor"
                      />
                    </View>
                  </View>
                  <View style={styles.qtdRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. %</Text>
                      <TextInput
                        value={addDescPct}
                        onChangeText={(v) => { setAddDescPct(v); if (parseNum(v) > 0) setAddDescRs(""); }}
                        editable={parseNum(addDescRs) <= 0}
                        keyboardType="decimal-pad"
                        placeholder="0"
                        placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(addDescRs) > 0 && styles.inputDisabled]}
                        testID="pedido-form-add-descpct"
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                      <TextInput
                        value={addDescRs}
                        onChangeText={(v) => { setAddDescRs(v); if (parseNum(v) > 0) setAddDescPct(""); }}
                        editable={parseNum(addDescPct) <= 0}
                        keyboardType="decimal-pad"
                        placeholder="0,00"
                        placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(addDescPct) > 0 && styles.inputDisabled]}
                        testID="pedido-form-add-descrs"
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Acrésc. R$ (unit.)</Text>
                      <TextInput
                        value={addAcr}
                        onChangeText={setAddAcr}
                        keyboardType="decimal-pad"
                        placeholder="0,00"
                        placeholderTextColor={colors.muted}
                        style={styles.input}
                        testID="pedido-form-add-acr"
                      />
                    </View>
                  </View>
                  <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                  <TextInput
                    value={addCompl}
                    onChangeText={setAddCompl}
                    placeholder="Descrição complementar"
                    placeholderTextColor={colors.muted}
                    style={styles.input}
                    testID="pedido-form-add-compl"
                  />
                  {(() => {
                    const pNormal = parseNum(addValor);
                    const dUnit = calcDescUnit(pNormal, addDescPct, addDescRs);
                    const acr = parseNum(addAcr);
                    const pVenda = pNormal - dUnit + acr;
                    const qtd = parseNum(addQtd);
                    return (
                      <View style={styles.liquidoBox}>
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                          <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                        </View>
                        {dUnit > 0 ? (
                          <View style={styles.liquidoRow}>
                            <Text style={styles.liquidoLabel}>Desconto total ({fmtNum(qtd)}×)</Text>
                            <Text style={[styles.liquidoVal, { color: colors.error }]}>- {formatBRL(dUnit * qtd)}</Text>
                          </View>
                        ) : null}
                        <View style={styles.previewRow}>
                          <Text style={styles.subtotalLabel}>Total do item</Text>
                          <Text style={styles.subtotalValue}>{formatBRL(qtd * pVenda)}</Text>
                        </View>
                      </View>
                    );
                  })()}
                  <View style={styles.modalBtns}>
                    <Pressable
                      onPress={() => setSelProd(null)}
                      style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }]}
                    >
                      <Text style={styles.secondaryBtnText}>Voltar</Text>
                    </Pressable>
                    <Pressable
                      onPress={handleAddItem}
                      disabled={addSaving}
                      style={({ pressed }) => [styles.primaryBtn, (pressed || addSaving) && { opacity: 0.8 }]}
                      testID="pedido-form-add-confirm"
                    >
                      {addSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Adicionar</Text>}
                    </Pressable>
                  </View>
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal editar item */}
      <Modal visible={!!editItem} transparent animationType="slide" onRequestClose={() => setEditItem(null)}>
        <Pressable style={styles.modalBg} onPress={() => setEditItem(null)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Editar Item</Text>
              <Pressable onPress={() => setEditItem(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {editItem ? (
              <ScrollView style={{ maxHeight: 520 }} keyboardShouldPersistTaps="handled">
                <View style={{ gap: spacing.sm }}>
                  <View style={styles.selProdBox}>
                    <Text style={styles.itemDesc} numberOfLines={2}>{editItem.descricao || editItem.produto}</Text>
                    <Text style={styles.resultSub}>#{editItem.produto}{editItem.cod_fab ? ` · ${editItem.cod_fab}` : ""}</Text>
                  </View>
                  <View style={styles.qtdRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Quantidade</Text>
                      <View style={styles.qtdInputRow}>
                        <TextInput value={editQtd} onChangeText={setEditQtd} keyboardType="decimal-pad" style={[styles.input, { flex: 1 }]} testID="pedido-form-edit-qtd" />
                        <TouchableOpacity
                          onPress={() => setEditQtd(fmtNum(parseNum(editQtd) + 1))}
                          activeOpacity={0.7}
                          style={styles.plusBtn}
                          testID="pedido-form-edit-qtd-plus"
                        >
                          <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                        </TouchableOpacity>
                      </View>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Valor unitário</Text>
                      <TextInput value={editValor} onChangeText={setEditValor} keyboardType="decimal-pad" style={styles.input} testID="pedido-form-edit-valor" />
                    </View>
                  </View>
                  <View style={styles.qtdRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. %</Text>
                      <TextInput
                        value={editDescPct}
                        onChangeText={(v) => { setEditDescPct(v); if (parseNum(v) > 0) setEditDescRs(""); }}
                        editable={parseNum(editDescRs) <= 0}
                        keyboardType="decimal-pad"
                        placeholder="0"
                        placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(editDescRs) > 0 && styles.inputDisabled]}
                        testID="pedido-form-edit-descpct"
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                      <TextInput
                        value={editDescRs}
                        onChangeText={(v) => { setEditDescRs(v); if (parseNum(v) > 0) setEditDescPct(""); }}
                        editable={parseNum(editDescPct) <= 0}
                        keyboardType="decimal-pad"
                        placeholder="0,00"
                        placeholderTextColor={colors.muted}
                        style={[styles.input, parseNum(editDescPct) > 0 && styles.inputDisabled]}
                        testID="pedido-form-edit-descrs"
                      />
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Acrésc. R$ (unit.)</Text>
                      <TextInput
                        value={editAcr}
                        onChangeText={setEditAcr}
                        keyboardType="decimal-pad"
                        placeholder="0,00"
                        placeholderTextColor={colors.muted}
                        style={styles.input}
                        testID="pedido-form-edit-acr"
                      />
                    </View>
                  </View>
                  <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                  <TextInput value={editCompl} onChangeText={setEditCompl} placeholder="Descrição complementar" placeholderTextColor={colors.muted} style={styles.input} testID="pedido-form-edit-compl" />
                  {(() => {
                    const pNormal = parseNum(editValor);
                    const dUnit = calcDescUnit(pNormal, editDescPct, editDescRs);
                    const acr = parseNum(editAcr);
                    const pVenda = pNormal - dUnit + acr;
                    const qtd = parseNum(editQtd);
                    return (
                      <View style={styles.liquidoBox}>
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                          <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                        </View>
                        {dUnit > 0 ? (
                          <View style={styles.liquidoRow}>
                            <Text style={styles.liquidoLabel}>Desconto total ({fmtNum(qtd)}×)</Text>
                            <Text style={[styles.liquidoVal, { color: colors.error }]}>- {formatBRL(dUnit * qtd)}</Text>
                          </View>
                        ) : null}
                        <View style={styles.previewRow}>
                          <Text style={styles.subtotalLabel}>Total do item</Text>
                          <Text style={styles.subtotalValue}>{formatBRL(qtd * pVenda)}</Text>
                        </View>
                      </View>
                    );
                  })()}
                  <View style={styles.modalBtns}>
                    <Pressable
                      onPress={() => handleDeleteItem(editItem)}
                      disabled={editSaving}
                      style={({ pressed }) => [styles.deleteBtn, (pressed || editSaving) && { opacity: 0.8 }]}
                      testID="pedido-form-edit-delete"
                    >
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                    </Pressable>
                    <Pressable
                      onPress={handleUpdateItem}
                      disabled={editSaving}
                      style={({ pressed }) => [styles.primaryBtn, { flex: 1 }, (pressed || editSaving) && { opacity: 0.8 }]}
                      testID="pedido-form-edit-save"
                    >
                      {editSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Salvar</Text>}
                    </Pressable>
                  </View>
                </View>
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal relatório de descontos concedidos */}
      <Modal visible={descModalOpen} transparent animationType="slide" onRequestClose={() => setDescModalOpen(false)}>
        <Pressable style={styles.modalBg} onPress={() => setDescModalOpen(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Descontos Concedidos</Text>
              <Pressable onPress={() => setDescModalOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {descLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : descItems.length === 0 ? (
              <Text style={styles.emptyText}>Nenhum desconto registrado.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 420 }}>
                {descItems.map((d) => (
                  <View key={d.cod} style={styles.descRow} testID={`pedido-form-desc-${d.cod}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemDesc} numberOfLines={1}>{d.descricao}</Text>
                      <Text style={styles.itemSub}>
                        {d.tipo_label}{d.percentual > 0 ? ` · ${fmtNum(d.percentual)}%` : ""}
                        {d.qtd > 0 ? ` · ${fmtNum(d.qtd)}× ${formatBRL(d.valor_unitario)}` : ""}
                        {` · usuário ${d.usuario}`}
                      </Text>
                    </View>
                    <Text style={[styles.itemTotal, { color: colors.error }]}>- {formatBRL(d.valor_total)}</Text>
                  </View>
                ))}
                <View style={styles.subtotalRow}>
                  <Text style={styles.subtotalLabel}>Total de descontos</Text>
                  <Text style={[styles.subtotalValue, { color: colors.error }]}>- {formatBRL(descTotalApi)}</Text>
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>


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
  lockHint: { fontSize: 10, color: colors.muted, fontWeight: "400", textTransform: "none", letterSpacing: 0 },
  row: { flexDirection: "row", gap: 8, alignItems: "flex-end" },
  dateRow: { flexDirection: "row", gap: 8, alignItems: "flex-start" },
  headerMeta: { fontSize: 12, color: colors.muted },
  clienteBox: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  clienteNome: { fontSize: 15, fontWeight: "500", color: colors.onSurface },
  clienteSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  resumoBox: {
    backgroundColor: colors.brandTertiary,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    marginTop: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 6,
  },
  resumoRow: { flexDirection: "row", alignItems: "center", gap: 8 },
  resumoText: { fontSize: 13, color: colors.onSurface, flex: 1 },
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
    maxHeight: "88%",
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
  itensHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addItemBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 7,
    borderRadius: radius.pill, marginTop: spacing.lg,
  },
  addItemBtnText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  itensHint: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border, marginTop: spacing.sm,
  },
  itensHintText: { color: colors.muted, fontSize: 13, flex: 1 },
  itemRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  itemTipo: { width: 36, height: 36, borderRadius: radius.sm, alignItems: "center", justifyContent: "center" },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  itemDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  itemCompl: { fontSize: 12, color: colors.brandPrimary, marginTop: 1, fontStyle: "italic" },
  itemSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  itemTotal: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  subtotalRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, marginTop: 4,
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
  },
  subtotalLabel: { fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  subtotalValue: { fontSize: 18, fontWeight: "700", color: colors.brandPrimary },
  descBtn: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md,
    backgroundColor: "#fdecea", borderWidth: 1, borderColor: "#f5c6cb",
  },
  descBtnLabel: { fontSize: 13, color: colors.error, fontWeight: "500" },
  descBtnValue: { fontSize: 14, color: colors.error, fontWeight: "700" },
  descRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  selProdBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  qtdRow: { flexDirection: "row", gap: spacing.sm },
  qtdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  plusBtn: {
    width: 40, height: 42, borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  inputDisabled: { backgroundColor: colors.surfaceSecondary, color: colors.muted },
  liquidoBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, gap: 2,
    borderWidth: 1, borderColor: colors.border,
  },
  liquidoRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  liquidoLabel: { fontSize: 12, color: colors.muted },
  liquidoVal: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  previewRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: spacing.sm, marginTop: 4,
  },
  modalBtns: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm },
  primaryBtn: {
    flex: 1, backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: "center", justifyContent: "center",
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  secondaryBtn: {
    paddingHorizontal: spacing.lg, borderRadius: radius.pill, paddingVertical: 13,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border,
  },
  secondaryBtnText: { color: colors.onSurface, fontWeight: "500", fontSize: 15 },
  deleteBtn: {
    width: 50, borderRadius: radius.pill, paddingVertical: 13,
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.error,
  },
  fullListBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    marginTop: spacing.sm, paddingVertical: 12, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
  },
  fullListText: { color: colors.brandPrimary, fontWeight: "500", fontSize: 14 },
});
