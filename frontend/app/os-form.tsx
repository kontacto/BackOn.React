import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable,
  ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, apiDelete } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, radius, spacing } from "@/src/theme/colors";
import { formatBRL, parseNum, fmtNum, fmtMoney2, calcDescUnit, formatDateBR, todayISO } from "@/src/utils/format";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import WhatsappButton from "@/src/components/WhatsappButton";
import { ClienteRow, ProdutoServico } from "@/src/components/pedido/types";

const SIT_COLOR: Record<string, string> = { A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935" };

// Combobox Status O.S. — grava o índice (os.status_os).
const STATUS_OS = [
  "Aguardando aprovação do Orçamento",
  "Aguardando Liberação de Execução",
  "Pendente",
  "Em execução",
  "Executado",
  "Cancelado",
];

const SITUACOES = [
  { value: "A", label: "Aberta" },
  { value: "F", label: "Fechada" },
  { value: "PG", label: "Faturada" },
  { value: "C", label: "Cancelada" },
];

const margemColor = (pct: number) => (pct >= 30 ? colors.success : pct >= 10 ? colors.warning : colors.error);

type OSData = {
  codigo: number; cliente: number | null; cliente_nome: string; cliente_cgc: string;
  data: string | null; hora: string; situacao: string; situacao_label: string; total: number;
  area_atuacao: number | null; area_descricao: string; descricao_cliente: string; obs: string;
  resumo: string; status_os: number | null; atendente: number | null; atendente_nome: string;
  placa: string; marca: string; modelo: string; km: number | null; ano: string;
  chassi: string; numero_de_serie: string;
};

type OSItem = {
  cod_os_prod: number; produto: string; tipo: "P" | "S" | "?";
  descricao: string; complemento: string; cod_fab: string; unidade: string;
  qtd: number; p_normal: number; valor_unitario: number; desconto: number; acrescimo: number; total: number;
  vendedor: number | null; vendedor_nome: string; executor: number | null; executor_nome: string;
};

type Toast = { msg: string; tone: "info" | "error" | "success" } | null;

export default function OSFormScreen() {
  const router = useRouter();
  const { can, moduleOn } = usePermissions();
  const params = useLocalSearchParams<{ os?: string }>();
  const editing = !!params.os;
  const osId = params.os ? parseInt(String(params.os), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [waUserId, setWaUserId] = useState<number | null>(null);
  const [waCompany, setWaCompany] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<Toast>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: "info" | "error" | "success" = "info") => {
    setToast({ msg: m, tone: t });
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), 3500);
  }, []);

  const [os, setOs] = useState<OSData | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [areaAtuacao, setAreaAtuacao] = useState<number | null>(null);
  const [descricaoCliente, setDescricaoCliente] = useState("");
  const [obs, setObs] = useState("");
  const [resumo, setResumo] = useState("");
  const [statusOs, setStatusOs] = useState<number | null>(null);
  const [atendente, setAtendente] = useState<number | null>(null);
  const [situacao, setSituacao] = useState("A");
  const [placa, setPlaca] = useState("");
  const [marca, setMarca] = useState("");
  const [modelo, setModelo] = useState("");
  const [km, setKm] = useState("");
  const [ano, setAno] = useState("");
  const [serie, setSerie] = useState("");  // chassi (Oficina) ou nº de série (Assistência)

  // bottom sheet de Veículo/Equipamento
  const [vehSheet, setVehSheet] = useState(false);
  // descontos concedidos
  const [descModal, setDescModal] = useState(false);
  const [descItems, setDescItems] = useState<{ cod: number; descricao: string; percentual: number; valor_unitario: number; qtd: number; valor_total: number }[]>([]);
  const [descTotal, setDescTotal] = useState(0);
  const [descLoading, setDescLoading] = useState(false);
  // análise de margem
  const [analiseModal, setAnaliseModal] = useState(false);
  const [analiseData, setAnaliseData] = useState<{ itens: { cod: number; descricao: string; venda: number; desconto: number; custo: number; margem: number; margem_pct: number }[]; totais: { venda: number; desconto: number; custo: number; margem: number; margem_pct: number; qtd_itens: number } } | null>(null);
  const [analiseLoading, setAnaliseLoading] = useState(false);
  // desconto geral
  const [descGeralModal, setDescGeralModal] = useState(false);
  const [descGeralVal, setDescGeralVal] = useState("");
  const [descGeralSaving, setDescGeralSaving] = useState(false);

  const [areas, setAreas] = useState<{ codigo: number; descricao: string }[]>([]);
  const [funcionarios, setFuncionarios] = useState<{ codigo: number; nome: string; nome_guerra: string }[]>([]);

  // itens
  const [itens, setItens] = useState<OSItem[]>([]);
  const [subtotal, setSubtotal] = useState(0);
  const [itensLoading, setItensLoading] = useState(false);

  // busca cliente
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // modal de item
  const [itemModal, setItemModal] = useState(false);
  const [editItem, setEditItem] = useState<OSItem | null>(null);
  const [selProd, setSelProd] = useState<ProdutoServico | null>(null);
  const [prodTerm, setProdTerm] = useState("");
  const [prodResults, setProdResults] = useState<ProdutoServico[]>([]);
  const [prodLoading, setProdLoading] = useState(false);
  const [fQtd, setFQtd] = useState("1");
  const [fValor, setFValor] = useState("0,00");
  const [fDescPct, setFDescPct] = useState("");
  const [fDescRs, setFDescRs] = useState("");
  const [fAcr, setFAcr] = useState("");
  const [fCompl, setFCompl] = useState("");
  const [fVendedor, setFVendedor] = useState<number | null>(null);
  const [fExecutor, setFExecutor] = useState<number | null>(null);
  const [itemSaving, setItemSaving] = useState(false);

  const isAberta = (os?.situacao || "A").toUpperCase() === "A";

  // -------- Init
  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      const fid = func?.codigo_int ?? func?.codigo;
      setWaUserId(fid != null ? parseInt(String(fid), 10) : null);
      setWaCompany(s?.empresa ?? null);
      if (c) {
        try {
          const [ra, rf] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
        } catch {
          // silencioso
        }
      }
      if (editing && osId && c) {
        await loadOS(c, osId);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadOS = async (c: Connection, id: number) => {
    try {
      const j = await apiGet(c, `/api/os/${id}`);
      if (j?.success && j.os) {
        const o: OSData = j.os;
        setOs(o);
        if (o.cliente) setCliente({ codigo: o.cliente, nome: o.cliente_nome, cgc_cpf: o.cliente_cgc, telefone: "" });
        setAreaAtuacao(o.area_atuacao ?? null);
        setDescricaoCliente(o.descricao_cliente || "");
        setObs(o.obs || "");
        setResumo(o.resumo || "");
        setStatusOs(o.status_os ?? null);
        setAtendente(o.atendente ?? null);
        setSituacao(o.situacao || "A");
        setPlaca(o.placa || "");
        setMarca(o.marca || "");
        setModelo(o.modelo || "");
        setKm(o.km != null ? String(o.km) : "");
        setAno(o.ano || "");
        setSerie(o.chassi || o.numero_de_serie || "");
      } else {
        showToast(j?.message || "Erro ao carregar OS.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    }
  };

  const loadItens = useCallback(async () => {
    if (!conn || !editing || !osId) return;
    setItensLoading(true);
    try {
      const j = await apiGet(conn, `/api/os/${osId}/itens`);
      if (j?.success) {
        setItens(j.items || []);
        setSubtotal(j.subtotal || 0);
      }
    } catch {
      // silencioso
    } finally {
      setItensLoading(false);
    }
  }, [conn, editing, osId]);

  useEffect(() => { loadItens(); }, [loadItens]);

  // busca cliente (debounce)
  useEffect(() => {
    if (!searchOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const j = await apiGet(conn, `/api/clientes/find/search`, { term: searchTerm });
        setSearchResults(j?.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, searchOpen, conn]);

  // busca produto (debounce)
  useEffect(() => {
    if (!itemModal || selProd || !conn) return;
    const t = setTimeout(async () => {
      setProdLoading(true);
      try {
        const j = await apiGet(conn, `/api/produtos-servicos`, { search: prodTerm, page: 1, size: 30, tipo: "all" });
        setProdResults(j?.items || []);
      } catch {
        setProdResults([]);
      } finally {
        setProdLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [prodTerm, itemModal, selProd, conn]);

  const handleSaveHeader = async () => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    setSaving(true);
    try {
      const isOficina = moduleOn("Oficina");
      const body: Record<string, unknown> = {
        cliente: cliente.codigo,
        area_atuacao: areaAtuacao,
        descricao_cliente: descricaoCliente,
        obs,
        resumo,
        status_os: statusOs,
        atendente: atendente,
        situacao,
        placa,
        marca,
        modelo,
        km: km.trim() ? parseInt(km, 10) || 0 : 0,
        ano,
        // Campo de descrição dupla: Oficina grava em chassi, Assistência em nº de série.
        chassi: isOficina ? serie : "",
        numero_de_serie: isOficina ? "" : serie,
      };
      const j = editing && osId
        ? await apiSend(conn, `/api/os/${osId}`, "PUT", body)
        : await apiSend(conn, `/api/os/create`, "POST", body);
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else if (editing) {
        showToast("OS atualizada.", "success");
        setTimeout(() => router.back(), 700);
      } else {
        showToast(`OS #${j.codigo} criada. Adicione os itens.`, "success");
        setTimeout(() => router.replace({ pathname: "/os-form", params: { os: String(j.codigo) } }), 700);
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setSaving(false); }
  };

  const openAddItem = () => {
    if (!isAberta) { showToast("OS não pode ser alterada.", "error"); return; }
    setEditItem(null);
    setSelProd(null);
    setProdTerm("");
    setProdResults([]);
    setFQtd("1"); setFValor("0,00"); setFDescPct(""); setFDescRs(""); setFAcr("");
    setFCompl(""); setFVendedor(null); setFExecutor(null);
    setItemModal(true);
  };

  const pickProduto = (p: ProdutoServico) => {
    setSelProd(p);
    setFQtd("1");
    setFValor(formatBRL(p.valor).replace("R$", "").trim());
    setFDescPct(""); setFDescRs(""); setFAcr(""); setFCompl("");
  };

  const openEditItem = (it: OSItem) => {
    if (!isAberta) { showToast("OS não pode ser alterada.", "error"); return; }
    setEditItem(it);
    setSelProd({ tipo: it.tipo === "S" ? "S" : "P", codigo: it.produto, descricao: it.descricao, valor: it.p_normal, estoque: null, cod_fab: it.cod_fab, unidade: it.unidade });
    setFQtd(fmtNum(it.qtd));
    setFValor(formatBRL(it.p_normal || it.valor_unitario).replace("R$", "").trim());
    setFDescPct("");
    setFDescRs(it.desconto > 0 ? fmtMoney2(it.desconto) : "");
    setFAcr(it.acrescimo > 0 ? fmtMoney2(it.acrescimo) : "");
    setFCompl(it.complemento || "");
    setFVendedor(it.vendedor);
    setFExecutor(it.executor);
    setItemModal(true);
  };

  const handleSaveItem = async () => {
    if (!conn || !osId || !selProd) return;
    const qtd = parseNum(fQtd);
    if (qtd <= 0) { showToast("Quantidade deve ser maior que zero.", "error"); return; }
    const pNormal = parseNum(fValor);
    const descUnit = calcDescUnit(pNormal, fDescPct, fDescRs);
    const acr = parseNum(fAcr);
    if (descUnit > pNormal + acr) { showToast("Desconto maior que o valor do item.", "error"); return; }
    setItemSaving(true);
    try {
      const body = {
        produto: selProd.codigo,
        qtd,
        valor_unitario: pNormal,
        desconto: descUnit,
        desconto_pct: parseNum(fDescPct),
        acrescimo: acr,
        complemento: fCompl,
        vendedor: fVendedor,
        executor: fExecutor,
      };
      const j = editItem
        ? await apiSend(conn, `/api/os/${osId}/itens/${editItem.cod_os_prod}`, "PUT", body)
        : await apiSend(conn, `/api/os/${osId}/itens`, "POST", body);
      if (!j?.success) { showToast(j?.message || "Falha ao salvar item.", "error"); }
      else {
        setItemModal(false);
        showToast(editItem ? "Item atualizado." : "Item adicionado.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setItemSaving(false); }
  };

  const handleDeleteItem = async () => {
    if (!conn || !osId || !editItem) return;
    setItemSaving(true);
    try {
      const j = await apiDelete(conn, `/api/os/${osId}/itens/${editItem.cod_os_prod}`);
      if (!j?.success) { showToast(j?.message || "Falha ao remover.", "error"); }
      else {
        setItemModal(false);
        showToast("Item removido.", "success");
        loadItens();
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setItemSaving(false); }
  };

  const openDescontos = async () => {
    if (!conn || !osId) return;
    setDescModal(true);
    setDescLoading(true);
    try {
      const j = await apiGet(conn, `/api/os/${osId}/descontos`);
      if (j?.success) { setDescItems(j.items || []); setDescTotal(j.total || 0); }
      else { setDescItems([]); setDescTotal(0); }
    } catch { setDescItems([]); setDescTotal(0); }
    finally { setDescLoading(false); }
  };

  const openAnalise = async () => {
    if (!conn || !osId) return;
    setAnaliseModal(true);
    setAnaliseLoading(true);
    try {
      const j = await apiGet(conn, `/api/os/${osId}/analise`);
      if (j?.success) setAnaliseData({ itens: j.itens || [], totais: j.totais });
      else setAnaliseData(null);
    } catch { setAnaliseData(null); }
    finally { setAnaliseLoading(false); }
  };

  const applyDescGeral = async () => {
    if (!conn || !osId) return;
    const valor = parseNum(descGeralVal);
    if (valor < 0) { showToast("Valor inválido.", "error"); return; }
    setDescGeralSaving(true);
    try {
      const j = await apiSend(conn, `/api/os/${osId}/desconto-geral`, "POST", {
        servidor: conn.servidor, banco: conn.banco,
        valor, usuario_codigo: waUserId ?? -2, funcao: 1,
      });
      if (j?.success) {
        setDescGeralModal(false);
        showToast(`Desconto geral aplicado (${(j.percentual || 0).toFixed(2)}%).`, "success");
        loadItens();
      } else {
        showToast(j?.message || "Falha ao aplicar desconto.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setDescGeralSaving(false); }
  };

  const areaOptions: SelectOption[] = useMemo(
    () => areas.map((a) => ({ value: a.codigo, label: a.descricao })),
    [areas]
  );
  const funcOptions: SelectOption[] = useMemo(
    () => funcionarios.map((f) => ({
      value: f.codigo,
      label: f.nome_guerra || f.nome,
      sub: `#${f.codigo}${f.nome_guerra && f.nome !== f.nome_guerra ? ` · ${f.nome}` : ""}`,
    })),
    [funcionarios]
  );

  const sit = os?.situacao || "A";
  const sitColor = SIT_COLOR[sit] || colors.muted;
  const isOficina = moduleOn("Oficina");
  const isAssist = moduleOn("Assistencia");
  const equipLabel = isOficina ? "Veículo" : isAssist ? "Equipamento" : "Veículo / Equipamento";
  const serieLabel = isOficina ? "Chassi" : isAssist ? "Nº de Série" : "Nº de Série / Chassi";
  const statusOptions: SelectOption[] = STATUS_OS.map((s, i) => ({ value: i, label: s }));
  const situacaoOptions: SelectOption[] = SITUACOES.map((s) => ({ value: s.value, label: s.label }));

  if (loading) return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
    </SafeAreaView>
  );

  if (!can("OS.ABRIR")) return (
    <SafeAreaView style={styles.safe} edges={["top"]}><LockedView /></SafeAreaView>
  );

  const canDesc = isAberta;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="os-form-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]} hitSlop={12} testID="os-form-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>{editing ? `OS #${osId}` : "Nova OS"}</Text>
        {can("OS.GRAVAR") ? (
          <Pressable onPress={handleSaveHeader} disabled={saving} style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]} testID="os-form-save">
            {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
          </Pressable>
        ) : <View style={{ width: 40 }} />}
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {editing && os ? (
            <View style={[styles.rowCenter, { marginBottom: 12 }]}>
              <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                <Text style={[styles.sitTagText, { color: sitColor }]}>{os.situacao_label}</Text>
              </View>
              <Text style={styles.headerMeta}>Aberta {formatDateBR(os.data)} {os.hora}</Text>
            </View>
          ) : null}

          {/* Cliente */}
          <Text style={styles.sectionTitle}>Cliente</Text>
          <Pressable
            onPress={() => { setSearchTerm(""); setSearchResults([]); setSearchOpen(true); }}
            style={({ pressed }) => [styles.selectBox, pressed && { opacity: 0.75 }]}
            testID="os-form-cliente"
          >
            <Ionicons name="person-outline" size={18} color={colors.muted} />
            <Text style={[styles.selectText, !cliente && { color: colors.muted }]} numberOfLines={1}>
              {cliente ? cliente.nome : "Selecionar cliente"}
            </Text>
            <Ionicons name="chevron-forward" size={16} color={colors.muted} />
          </Pressable>

          {/* Status O.S. */}
          <Text style={styles.sectionTitle}>Status O.S.</Text>
          <SelectField
            value={statusOs}
            onChange={(v) => setStatusOs(v == null ? null : Number(v))}
            options={statusOptions}
            placeholder="Selecione o status"
            modalTitle="Status da O.S."
            searchable={false}
            allowClear
            testID="os-form-status"
          />

          {/* Atendente e Situação */}
          <View style={styles.fieldRow}>
            <View style={{ flex: 1 }}>
              <Text style={styles.sectionTitle}>Atendente</Text>
              <SelectField
                value={atendente}
                onChange={(v) => setAtendente(v == null ? null : Number(v))}
                options={funcOptions}
                placeholder="Atendente"
                modalTitle="Selecionar Atendente"
                allowClear
                testID="os-form-atendente"
              />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={styles.sectionTitle}>Situação</Text>
              <SelectField
                value={situacao}
                onChange={(v) => setSituacao(v == null ? "A" : String(v))}
                options={situacaoOptions}
                placeholder="Situação"
                modalTitle="Situação da O.S."
                searchable={false}
                testID="os-form-situacao"
              />
            </View>
          </View>

          {/* Área de atuação */}
          <Text style={styles.sectionTitle}>Área de Atuação</Text>
          <SelectField
            value={areaAtuacao}
            onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
            options={areaOptions}
            placeholder="Selecione a área"
            modalTitle="Selecionar Área de Atuação"
            allowClear
            testID="os-form-area"
          />

          {/* Data */}
          <Text style={styles.sectionTitle}>Data de Entrada</Text>
          <View style={styles.readonlyBox}>
            <Ionicons name="calendar-outline" size={16} color={colors.muted} />
            <Text style={styles.readonlyText}>{editing ? formatDateBR(os?.data || null) : formatDateBR(todayISO())}</Text>
          </View>

          {/* Veículo / Equipamento — abre bottom sheet */}
          <Text style={styles.sectionTitle}>{equipLabel}</Text>
          <Pressable
            onPress={() => setVehSheet(true)}
            style={({ pressed }) => [styles.selectBox, pressed && { opacity: 0.75 }]}
            testID="os-form-veiculo-open"
          >
            <Ionicons name={isAssist ? "hardware-chip-outline" : "car-outline"} size={18} color={colors.muted} />
            <Text style={[styles.selectText, !(placa || marca || modelo || serie) && { color: colors.muted }]} numberOfLines={1}>
              {placa || marca || modelo || serie
                ? [placa, [marca, modelo].filter(Boolean).join(" "), serie].filter(Boolean).join(" · ")
                : `Informar ${equipLabel.toLowerCase()}`}
            </Text>
            <Ionicons name="chevron-forward" size={16} color={colors.muted} />
          </Pressable>

          {/* Cliente Descreva */}
          <Text style={styles.sectionTitle}>Cliente Descreva</Text>
          <TextInput
            value={descricaoCliente}
            onChangeText={setDescricaoCliente}
            placeholder="Descrição informada pelo cliente"
            placeholderTextColor={colors.muted}
            style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
            multiline
            testID="os-form-descricao"
          />

          {/* Serviço Executado */}
          <Text style={styles.sectionTitle}>Serviço Executado</Text>
          <TextInput
            value={resumo}
            onChangeText={setResumo}
            placeholder="Resumo do serviço executado"
            placeholderTextColor={colors.muted}
            style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
            multiline
            testID="os-form-resumo"
          />

          {/* Observação */}
          <Text style={styles.sectionTitle}>Observação</Text>
          <TextInput
            value={obs}
            onChangeText={setObs}
            placeholder="Observação da OS"
            placeholderTextColor={colors.muted}
            style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
            multiline
            testID="os-form-obs"
          />

          {/* Itens */}
          <View style={styles.itensHeader}>
            <Text style={styles.sectionTitle}>Itens da OS</Text>
            {editing && isAberta && can("OS.ADD_ITEM") ? (
              <TouchableOpacity onPress={openAddItem} activeOpacity={0.8} style={styles.addItemBtn} testID="os-form-add-item">
                <Ionicons name="add" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.addItemText}>Item</Text>
              </TouchableOpacity>
            ) : null}
          </View>

          {!editing ? (
            <Text style={styles.hintText}>Grave a OS para adicionar itens.</Text>
          ) : itensLoading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : itens.length === 0 ? (
            <Text style={styles.hintText}>Nenhum item adicionado.</Text>
          ) : (
            itens.map((it) => (
              <Pressable
                key={it.cod_os_prod}
                onPress={() => can("OS.EDIT_ITEM") && openEditItem(it)}
                style={({ pressed }) => [styles.itemCard, pressed && { opacity: 0.7 }]}
                testID={`os-item-${it.cod_os_prod}`}
              >
                <View style={[styles.itemTipo, it.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                  <Ionicons name={it.tipo === "P" ? "cube" : "construct"} size={16} color={it.tipo === "P" ? colors.brandPrimary : colors.warning} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.itemDesc} numberOfLines={1}>{it.descricao}</Text>
                  <Text style={styles.itemSub} numberOfLines={1}>
                    {fmtNum(it.qtd)} × {formatBRL(it.valor_unitario)}
                  </Text>
                  <Text style={styles.itemSub} numberOfLines={1}>
                    Vend.: {it.vendedor_nome || "—"} · Exec.: {it.executor_nome || "—"}
                  </Text>
                </View>
                <Text style={styles.itemTotal}>{formatBRL(it.total)}</Text>
              </Pressable>
            ))
          )}

          {editing && itens.length > 0 ? (
            <View style={styles.subtotalRow}>
              <Text style={styles.subtotalLabel}>Total da OS</Text>
              <Text style={styles.subtotalValue}>{formatBRL(subtotal)}</Text>
            </View>
          ) : null}

          {editing && osId && can("OS.DESC_ITEM") && itens.length > 0 ? (
            <TouchableOpacity onPress={() => { setDescGeralVal(""); setDescGeralModal(true); }} activeOpacity={0.85} style={styles.actionBtn} testID="os-form-desc-geral-btn">
              <Ionicons name="cash-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.actionBtnText}>Desconto geral</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}

          {editing && osId && can("OS.VER_DESCONTOS") ? (
            <TouchableOpacity onPress={openDescontos} activeOpacity={0.85} style={styles.actionBtn} testID="os-form-descontos-btn">
              <Ionicons name="pricetag-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.actionBtnText}>Descontos concedidos</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}

          {editing && osId && can("OS.ANALISE") ? (
            <TouchableOpacity onPress={openAnalise} activeOpacity={0.85} style={styles.actionBtn} testID="os-form-analise-btn">
              <Ionicons name="bar-chart-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.actionBtnText}>Analisar margem & descontos</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}

          {editing && osId && can("OS.WHATSAPP") ? (
            <WhatsappButton
              conn={conn}
              documentType="OS"
              documentId={osId}
              userId={waUserId}
              companyId={waCompany}
            />
          ) : null}

          <View style={{ height: 60 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      {/* Modal busca de cliente */}
      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => { setCliente(c); setSearchOpen(false); }}
        onCreate={() => {
          setSearchOpen(false);
          router.push({ pathname: "/cliente-form", params: { initial_nome: searchTerm } });
        }}
      />

      {/* Modal de item */}
      <Modal visible={itemModal} transparent animationType="slide" onRequestClose={() => setItemModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setItemModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{editItem ? "Editar Item" : selProd ? "Confirmar Item" : "Adicionar Item"}</Text>
              <Pressable onPress={() => setItemModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>

            {!selProd ? (
              <>
                <View style={styles.searchWrapModal}>
                  <Ionicons name="search" size={16} color={colors.muted} />
                  <TextInput
                    value={prodTerm}
                    onChangeText={setProdTerm}
                    placeholder="Buscar produto ou serviço…"
                    placeholderTextColor={colors.muted}
                    style={styles.searchInput}
                    autoFocus
                    testID="os-form-prod-search"
                  />
                </View>
                {prodLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
                <ScrollView style={{ maxHeight: 380 }} keyboardShouldPersistTaps="handled">
                  {prodResults.map((p) => (
                    <Pressable
                      key={`${p.tipo}-${p.codigo}`}
                      onPress={() => pickProduto(p)}
                      style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                      testID={`os-form-prod-${p.codigo}`}
                    >
                      <View style={[styles.itemTipo, p.tipo === "P" ? styles.tagProd : styles.tagServ]}>
                        <Ionicons name={p.tipo === "P" ? "cube" : "construct"} size={16} color={p.tipo === "P" ? colors.brandPrimary : colors.warning} />
                      </View>
                      <View style={{ flex: 1 }}>
                        <Text style={styles.itemDesc} numberOfLines={1}>{p.descricao}</Text>
                        <Text style={styles.itemSub} numberOfLines={1}>#{p.codigo}{p.cod_fab ? ` · ${p.cod_fab}` : ""}</Text>
                      </View>
                      <Text style={styles.itemTotal}>{formatBRL(p.valor)}</Text>
                    </Pressable>
                  ))}
                  {!prodLoading && prodResults.length === 0 ? (
                    <Text style={styles.hintText}>Nenhum produto/serviço encontrado.</Text>
                  ) : null}
                </ScrollView>
              </>
            ) : (
              <ScrollView style={{ maxHeight: 560 }} keyboardShouldPersistTaps="handled">
                <View style={{ gap: spacing.sm }}>
                  <View style={styles.selProdBox}>
                    <Text style={styles.itemDesc} numberOfLines={2}>{selProd.descricao}</Text>
                    <Text style={styles.itemSub}>#{selProd.codigo}{selProd.cod_fab ? ` · ${selProd.cod_fab}` : ""}</Text>
                  </View>

                  <View style={styles.fieldRow}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Quantidade</Text>
                      <View style={styles.qtdInputRow}>
                        <TextInput value={fQtd} onChangeText={setFQtd} keyboardType="decimal-pad" style={[styles.input, { flex: 1 }]} testID="os-form-item-qtd" />
                        <TouchableOpacity onPress={() => setFQtd(fmtNum(parseNum(fQtd) + 1))} activeOpacity={0.7} style={styles.plusBtn}>
                          <Ionicons name="add" size={20} color={colors.onBrandPrimary} />
                        </TouchableOpacity>
                      </View>
                    </View>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Valor unitário</Text>
                      <TextInput value={fValor} onChangeText={setFValor} keyboardType="decimal-pad" style={styles.input} testID="os-form-item-valor" />
                    </View>
                  </View>

                  <View style={styles.fieldRow}>
                    {canDesc ? (
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Desc. %</Text>
                        <TextInput
                          value={fDescPct}
                          onChangeText={(v) => { setFDescPct(v); if (parseNum(v) > 0) setFDescRs(""); }}
                          editable={parseNum(fDescRs) <= 0}
                          keyboardType="decimal-pad" placeholder="0" placeholderTextColor={colors.muted}
                          style={[styles.input, parseNum(fDescRs) > 0 && styles.inputDisabled]}
                          testID="os-form-item-descpct"
                        />
                      </View>
                    ) : null}
                    {canDesc ? (
                      <View style={{ flex: 1 }}>
                        <Text style={styles.fieldLabel}>Desc. R$ (unit.)</Text>
                        <TextInput
                          value={fDescRs}
                          onChangeText={(v) => { setFDescRs(v); if (parseNum(v) > 0) setFDescPct(""); }}
                          editable={parseNum(fDescPct) <= 0}
                          keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted}
                          style={[styles.input, parseNum(fDescPct) > 0 && styles.inputDisabled]}
                          testID="os-form-item-descrs"
                        />
                      </View>
                    ) : null}
                    <View style={{ flex: 1 }}>
                      <Text style={styles.fieldLabel}>Acrésc. R$</Text>
                      <TextInput value={fAcr} onChangeText={setFAcr} keyboardType="decimal-pad" placeholder="0,00" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-item-acr" />
                    </View>
                  </View>

                  {/* Vendedor e Executor — POR ITEM */}
                  <Text style={styles.fieldLabel}>Vendedor</Text>
                  <SelectField
                    value={fVendedor}
                    onChange={(v) => setFVendedor(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Selecionar vendedor"
                    modalTitle="Selecionar Vendedor"
                    allowClear
                    testID="os-form-item-vendedor"
                  />
                  <Text style={styles.fieldLabel}>Executor</Text>
                  <SelectField
                    value={fExecutor}
                    onChange={(v) => setFExecutor(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Selecionar executor"
                    modalTitle="Selecionar Executor"
                    allowClear
                    testID="os-form-item-executor"
                  />

                  <Text style={styles.fieldLabel}>Complemento (opcional)</Text>
                  <TextInput value={fCompl} onChangeText={setFCompl} placeholder="Descrição complementar" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-item-compl" />

                  {(() => {
                    const pNormal = parseNum(fValor);
                    const dUnit = calcDescUnit(pNormal, fDescPct, fDescRs);
                    const acr = parseNum(fAcr);
                    const pVenda = pNormal - dUnit + acr;
                    const qtd = parseNum(fQtd);
                    return (
                      <View style={styles.liquidoBox}>
                        <View style={styles.liquidoRow}>
                          <Text style={styles.liquidoLabel}>Preço líquido unit.</Text>
                          <Text style={styles.liquidoVal}>{formatBRL(pVenda)}</Text>
                        </View>
                        <View style={styles.previewRow}>
                          <Text style={styles.subtotalLabel}>Total do item</Text>
                          <Text style={styles.subtotalValue}>{formatBRL(qtd * pVenda)}</Text>
                        </View>
                      </View>
                    );
                  })()}

                  <View style={styles.modalBtns}>
                    {editItem && can("OS.DEL_ITEM") ? (
                      <Pressable onPress={handleDeleteItem} disabled={itemSaving} style={({ pressed }) => [styles.dangerBtn, pressed && { opacity: 0.8 }]} testID="os-form-item-delete">
                        <Ionicons name="trash-outline" size={18} color={colors.error} />
                      </Pressable>
                    ) : (
                      <Pressable onPress={() => setSelProd(null)} disabled={!!editItem} style={({ pressed }) => [styles.secondaryBtn, pressed && { opacity: 0.8 }, editItem && { opacity: 0.4 }]}>
                        <Text style={styles.secondaryBtnText}>Voltar</Text>
                      </Pressable>
                    )}
                    <Pressable onPress={handleSaveItem} disabled={itemSaving} style={({ pressed }) => [styles.primaryBtn, (pressed || itemSaving) && { opacity: 0.8 }]} testID="os-form-item-confirm">
                      {itemSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>{editItem ? "Salvar" : "Adicionar"}</Text>}
                    </Pressable>
                  </View>
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Bottom sheet: Veículo / Equipamento */}
      <Modal visible={vehSheet} transparent animationType="slide" onRequestClose={() => setVehSheet(false)}>
        <Pressable style={styles.modalBg} onPress={() => setVehSheet(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.sheetHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{equipLabel}</Text>
              <Pressable onPress={() => setVehSheet(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 460 }} keyboardShouldPersistTaps="handled">
              <View style={styles.fieldRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Placa</Text>
                  <TextInput value={placa} onChangeText={setPlaca} autoCapitalize="characters" maxLength={8} placeholder="ABC-1234" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-placa" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>KM</Text>
                  <TextInput value={km} onChangeText={setKm} keyboardType="number-pad" placeholder="0" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-km" />
                </View>
              </View>
              <View style={styles.fieldRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Marca</Text>
                  <TextInput value={marca} onChangeText={setMarca} maxLength={3} placeholder="Marca" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-marca" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Modelo</Text>
                  <TextInput value={modelo} onChangeText={setModelo} maxLength={3} placeholder="Modelo" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-modelo" />
                </View>
              </View>
              <View style={styles.fieldRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Ano</Text>
                  <TextInput value={ano} onChangeText={setAno} maxLength={9} placeholder="2025" placeholderTextColor={colors.muted} style={styles.input} testID="os-form-ano" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>{serieLabel}</Text>
                  <TextInput value={serie} onChangeText={setSerie} maxLength={20} placeholder={serieLabel} placeholderTextColor={colors.muted} style={styles.input} testID="os-form-serie" />
                </View>
              </View>
              <Pressable onPress={() => setVehSheet(false)} style={({ pressed }) => [styles.primaryBtn, { marginTop: spacing.lg }, pressed && { opacity: 0.85 }]} testID="os-form-veiculo-ok">
                <Text style={styles.primaryBtnText}>Concluir</Text>
              </Pressable>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal: Descontos concedidos */}
      <Modal visible={descModal} transparent animationType="slide" onRequestClose={() => setDescModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setDescModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Descontos Concedidos</Text>
              <Pressable onPress={() => setDescModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {descLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : descItems.length === 0 ? (
              <Text style={styles.hintText}>Nenhum desconto registrado.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 420 }}>
                {descItems.map((d) => (
                  <View key={d.cod} style={styles.descRow} testID={`os-form-desc-${d.cod}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemDesc} numberOfLines={1}>{d.descricao}</Text>
                      <Text style={styles.itemSub}>
                        {d.percentual > 0 ? `${fmtNum(d.percentual)}% · ` : ""}{fmtNum(d.qtd)}× {formatBRL(d.valor_unitario)}
                      </Text>
                    </View>
                    <Text style={[styles.itemTotal, { color: colors.error }]}>- {formatBRL(d.valor_total)}</Text>
                  </View>
                ))}
                <View style={styles.subtotalRow}>
                  <Text style={styles.subtotalLabel}>Total de descontos</Text>
                  <Text style={[styles.subtotalValue, { color: colors.error }]}>- {formatBRL(descTotal)}</Text>
                </View>
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal: Analisar margem & descontos */}
      <Modal visible={analiseModal} transparent animationType="slide" onRequestClose={() => setAnaliseModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setAnaliseModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Margem & Descontos</Text>
              <Pressable onPress={() => setAnaliseModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {analiseLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : !analiseData ? (
              <Text style={styles.hintText}>Sem dados para análise.</Text>
            ) : (
              <ScrollView style={{ maxHeight: 480 }}>
                <View style={styles.totaisCard}>
                  <View style={styles.totaisGrid}>
                    <View style={styles.totItem}><Text style={styles.totLbl}>Vendas</Text><Text style={styles.totVal}>{formatBRL(analiseData.totais.venda)}</Text></View>
                    <View style={styles.totItem}><Text style={styles.totLbl}>Descontos</Text><Text style={[styles.totVal, { color: colors.error }]}>{formatBRL(analiseData.totais.desconto)}</Text></View>
                    <View style={styles.totItem}><Text style={styles.totLbl}>Custo</Text><Text style={styles.totVal}>{formatBRL(analiseData.totais.custo)}</Text></View>
                    <View style={styles.totItem}>
                      <Text style={styles.totLbl}>Margem</Text>
                      <Text style={[styles.totVal, { color: margemColor(analiseData.totais.margem_pct) }]}>{formatBRL(analiseData.totais.margem)} · {analiseData.totais.margem_pct}%</Text>
                    </View>
                  </View>
                </View>
                {analiseData.itens.map((it) => (
                  <View key={it.cod} style={styles.descRow} testID={`os-form-analise-${it.cod}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.itemDesc} numberOfLines={1}>{it.descricao}</Text>
                      <Text style={styles.itemSub}>Venda {formatBRL(it.venda)} · Custo {formatBRL(it.custo)}</Text>
                    </View>
                    <View style={{ alignItems: "flex-end" }}>
                      <Text style={[styles.itemTotal, { color: margemColor(it.margem_pct) }]}>{formatBRL(it.margem)}</Text>
                      <Text style={[styles.itemSub, { color: margemColor(it.margem_pct) }]}>{it.margem_pct}%</Text>
                    </View>
                  </View>
                ))}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* Modal: Desconto geral */}
      <Modal visible={descGeralModal} transparent animationType="slide" onRequestClose={() => setDescGeralModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setDescGeralModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.sheetHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Desconto Geral</Text>
              <Pressable onPress={() => setDescGeralModal(false)} hitSlop={8}><Ionicons name="close" size={22} color={colors.muted} /></Pressable>
            </View>
            <Text style={styles.hintText}>O valor é distribuído proporcionalmente entre os itens da OS. Use 0 para zerar os descontos.</Text>
            <Text style={styles.fieldLabel}>Valor do desconto (R$)</Text>
            <TextInput
              value={descGeralVal}
              onChangeText={setDescGeralVal}
              keyboardType="decimal-pad"
              placeholder="0,00"
              placeholderTextColor={colors.muted}
              style={styles.input}
              testID="os-desc-geral-input"
            />
            <Pressable
              onPress={applyDescGeral}
              disabled={descGeralSaving}
              style={({ pressed }) => [styles.primaryBtn, { marginTop: spacing.lg }, (pressed || descGeralSaving) && { opacity: 0.85 }]}
              testID="os-desc-geral-apply"
            >
              {descGeralSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Aplicar</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? (
        <View style={[styles.toast, toast.tone === "error" && { backgroundColor: colors.error }, toast.tone === "success" && { backgroundColor: colors.success }]} testID="os-form-toast">
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
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: { paddingHorizontal: spacing.md, height: 40, alignItems: "center", justifyContent: "center", borderRadius: radius.md, backgroundColor: "rgba(255,255,255,0.2)" },
  saveLabel: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "600" },
  scroll: { padding: spacing.lg },
  rowCenter: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  headerMeta: { fontSize: 12, color: colors.muted },
  sectionTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface, marginTop: spacing.md, marginBottom: 6, textTransform: "uppercase", letterSpacing: 0.4 },
  groupTitle: { fontSize: 14, fontWeight: "700", color: colors.brandPrimary, marginTop: spacing.lg, marginBottom: 4 },
  selectBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 12, borderWidth: 1, borderColor: colors.border,
  },
  selectText: { flex: 1, fontSize: 14, color: colors.onSurface },
  readonlyBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 12, borderWidth: 1, borderColor: colors.border,
  },
  readonlyText: { fontSize: 14, color: colors.onSurface },
  input: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderWidth: 1, borderColor: colors.border,
    color: colors.onSurface, fontSize: 14,
  },
  inputDisabled: { opacity: 0.5 },
  itensHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  addItemBtn: { flexDirection: "row", alignItems: "center", gap: 4, backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.md, marginTop: spacing.md },
  addItemText: { color: colors.onBrandPrimary, fontSize: 13, fontWeight: "600" },
  hintText: { color: colors.muted, fontSize: 13, marginVertical: spacing.md },
  itemCard: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border, marginBottom: 8,
  },
  itemTipo: { width: 32, height: 32, borderRadius: 8, alignItems: "center", justifyContent: "center" },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  itemDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  itemSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  itemTotal: { fontSize: 14, fontWeight: "600", color: colors.brandPrimary },
  subtotalRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border },
  subtotalLabel: { fontSize: 14, color: colors.onSurface, fontWeight: "500" },
  subtotalValue: { fontSize: 18, fontWeight: "700", color: colors.brandPrimary },
  actionBtn: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandTertiary, borderRadius: radius.md,
    paddingHorizontal: spacing.md, paddingVertical: 14, marginTop: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  actionBtnText: { flex: 1, fontSize: 14, fontWeight: "600", color: colors.brandPrimary },
  sheetHandle: { alignSelf: "center", width: 40, height: 4, borderRadius: 2, backgroundColor: colors.border, marginBottom: spacing.sm },
  descRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  totaisCard: {
    backgroundColor: colors.brandTertiary, borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md,
  },
  totaisGrid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  totItem: { width: "47%" },
  totLbl: { fontSize: 11, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.4 },
  totVal: { fontSize: 15, fontWeight: "700", color: colors.onSurface, marginTop: 2 },
  // modal
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl, minHeight: 420,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  searchWrapModal: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, marginBottom: spacing.md,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  resultRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  selProdBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, borderWidth: 1, borderColor: colors.border },
  fieldRow: { flexDirection: "row", gap: 8 },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, marginTop: 6, fontWeight: "500", textTransform: "uppercase", letterSpacing: 0.5 },
  qtdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  plusBtn: { width: 42, height: 42, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center" },
  liquidoBox: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.md, padding: spacing.md, marginTop: spacing.sm },
  liquidoRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  liquidoLabel: { fontSize: 13, color: colors.muted },
  liquidoVal: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  previewRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 8, paddingTop: 8, borderTopWidth: 1, borderTopColor: colors.border },
  modalBtns: { flexDirection: "row", gap: spacing.sm, marginTop: spacing.lg, alignItems: "center" },
  secondaryBtn: { flex: 1, paddingVertical: 14, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, alignItems: "center" },
  secondaryBtnText: { color: colors.onSurface, fontSize: 14, fontWeight: "600" },
  dangerBtn: { width: 52, paddingVertical: 14, borderRadius: radius.md, borderWidth: 1, borderColor: colors.error, alignItems: "center" },
  primaryBtn: { flex: 1, paddingVertical: 14, borderRadius: radius.md, backgroundColor: colors.brandPrimary, alignItems: "center" },
  primaryBtnText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "600" },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  sitTagText: { fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  toast: { position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.xl, backgroundColor: colors.onSurface, borderRadius: radius.md, padding: spacing.md },
  toastText: { color: "#fff", fontSize: 13, textAlign: "center" },
});
