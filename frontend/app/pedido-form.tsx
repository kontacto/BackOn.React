import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView, Text, TextInput, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@expo/vector-icons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors } from "@/src/theme/colors";
import { formatDateBR, todayISO } from "@/src/utils/format";
import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { styles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo, AreaAtuacao, Funcionario, PedidoData, ToastTone } from "@/src/components/pedido/types";
import { usePedidoItens } from "@/src/components/pedido/usePedidoItens";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import PedidoHeader from "@/src/components/pedido/PedidoHeader";
import ItemList from "@/src/components/pedido/ItemList";
import AddItemModal from "@/src/components/pedido/AddItemModal";
import EditItemModal from "@/src/components/pedido/EditItemModal";
import GeneralDiscountModal from "@/src/components/pedido/GeneralDiscountModal";
import DiscountsReportModal from "@/src/components/pedido/DiscountsReportModal";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";

// Funções que podem alterar vendedor: 01 (Administrador) e 02 (Gerente)
const VENDEDOR_EDIT_FUNCOES = ["01", "02"];
export default function PedidoFormScreen() {
  const router = useRouter();
  const { can } = usePermissions();
  const params = useLocalSearchParams<{ pedido?: string; cliente?: string; cliente_nome?: string }>();
  const editing = !!params.pedido;
  const pedidoId = params.pedido ? parseInt(String(params.pedido), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [vendedor, setVendedor] = useState<number | null>(null);
  const [vendedorNome, setVendedorNome] = useState("");
  const [vendedorCanEdit, setVendedorCanEdit] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: ToastTone = "info") => {
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

  // Código do usuário logado p/ log de descontos (-2 = KONTACTO master)
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [funcaoCod, setFuncaoCod] = useState<number>(1); // 1=gerente,2=supervisor,3=vendedor

  const isAberto = (pedido?.situacao || "A").toUpperCase() === "A";
  const it = usePedidoItens({ conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, showToast });

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
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = cf ? parseInt(cf, 10) : NaN;
      setFuncaoCod(isMaster ? 1 : (Number.isFinite(fc) && fc > 0 ? fc : 1));
      const fnome = (s?.funcionario?.nome_guerra || s?.funcionario?.nome || "") as string;
      setVendedorNome(fnome);

      // Quem pode alterar o vendedor: master (KONTACTO) ou cod_funcao 01/02 (gerente/supervisor)
      const codFuncao = String(s?.funcionario?.cod_funcao || "").trim().padStart(2, "0");
      setVendedorCanEdit(isMaster || VENDEDOR_EDIT_FUNCOES.includes(codFuncao));

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
        try {
          const [ra, rf] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            // se houver apenas 1 área de atuação, seleciona automaticamente
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
        } catch {
          // silencioso — combobox vazio
        }
      }

      // Carrega pedido em modo edição
      if (editing && pedidoId && c) {
        try {
          const j = await apiGet(c, `/api/pedidos/${pedidoId}`);
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
    apiGet(conn, `/api/clientes/${cliente.codigo}/resumo`)
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

  const handleSave = async () => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    if (vendedor == null) { showToast("Vendedor não identificado.", "error"); return; }
    setSaving(true);
    try {
      const body = {
        cliente: cliente.codigo,
        vendedor,
        validade: validade || null,
        obs,
        area_atuacao: areaAtuacao,
      };
      const j = editing && pedidoId
        ? await apiSend(conn, `/api/pedidos/${pedidoId}`, "PUT", body)
        : await apiSend(conn, `/api/pedidos/create`, "POST", body);
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
      <PedidoHeader
        title={editing ? `Pedido #${pedidoId}` : "Novo Pedido"}
        saving={saving}
        onBack={() => router.back()}
        onSave={handleSave}
        canSave={can("PEDIDO.GRAVAR")}
      />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {/* Cabeçalho do pedido */}
          {editing && pedido ? (
            <View style={[styles.row, { marginBottom: 12 }]}>
              <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                <Text style={[styles.sitTagText, { color: sitColor }]}>{pedido.situacao_label}</Text>
              </View>
              <Text style={styles.headerMeta}>Aberto {formatDateBR(pedido.data)} {pedido.hora_aberto}</Text>
            </View>
          ) : null}

          {/* Cliente: seletor + resumo */}
          <ClienteSection
            cliente={cliente}
            clienteResumo={clienteResumo}
            loadingResumo={loadingResumo}
            onOpenSearch={() => { setSearchTerm(""); setSearchResults([]); setSearchOpen(true); }}
          />

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
          <ItemList editing={editing} isAberto={isAberto} it={it} />

          {editing && pedidoId ? (
            <TouchableOpacity
              onPress={() => router.push({ pathname: "/relatorio-descontos", params: { pedido: String(pedidoId) } })}
              activeOpacity={0.85}
              style={styles.analiseBtn}
              testID="pedido-form-analise-btn"
            >
              <Ionicons name="bar-chart-outline" size={18} color={colors.brandPrimary} />
              <Text style={styles.analiseBtnText}>Analisar margem & descontos</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.brandPrimary} />
            </TouchableOpacity>
          ) : null}

          <View style={{ height: 80 }} />
        </ScrollView>
      </KeyboardAvoidingView>

      <AddItemModal
        it={it}
        onOpenProdutos={() => {
          it.setAddOpen(false);
          router.push({ pathname: "/produtos", params: { pedido: String(pedidoId) } });
        }}
      />
      <EditItemModal it={it} />
      <GeneralDiscountModal it={it} />
      <DiscountsReportModal it={it} />
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

      {toast ? (
        <View style={[styles.toast, toast.tone === "error" && { backgroundColor: colors.error }, toast.tone === "success" && { backgroundColor: colors.success }]} testID="pedido-form-toast">
          <Text style={styles.toastText}>{toast.msg}</Text>
        </View>
      ) : null}
    </SafeAreaView>
  );
}
