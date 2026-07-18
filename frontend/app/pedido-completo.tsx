import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatDateBR, todayISO } from "@/src/utils/format";
import { styles as pedidoStyles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo, AreaAtuacao, Funcionario, PedidoData, ToastTone } from "@/src/components/pedido/types";
import { usePedidoItens } from "@/src/components/pedido/usePedidoItens";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import ItemList from "@/src/components/pedido/ItemList";
import AddItemModal from "@/src/components/pedido/AddItemModal";
import EditItemModal from "@/src/components/pedido/EditItemModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import GeneralDiscountModal from "@/src/components/pedido/GeneralDiscountModal";
import DiscountsReportModal from "@/src/components/pedido/DiscountsReportModal";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import FormaPagamentoField from "@/src/components/pedido/FormaPagamentoField";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import WhatsappButton from "@/src/components/WhatsappButton";

// Funções que podem alterar vendedor: 01 (Administrador) e 02 (Gerente) — mesma
// regra do Pedido rápido (pedido-form.tsx).
const VENDEDOR_EDIT_FUNCOES = ["01", "02"];

type FormaPag = { codigo: string; descricao: string };

type PedidoCompletoData = PedidoData & {
  forma_pag: string;
  forma_pag_descricao: string;
  local_entrega: string;
  previsao_entrega: string | null;
  num_ped_cliente: string;
  infoentrega: string;
  editavel: boolean;
};

// ============================================================
// Tela — Pedido Completo (web-only). Fase A (núcleo) do plano faseado em
// PENDENCIAS.md > "Transações" > "Pedido Completo": cabeçalho com o
// conjunto real de campos de frmmanpedfor.frm (Frame2) + grade de itens
// (resolução rica + kits, ver pedido_completo_service.py) + Fechar/Cancelar.
// O legado não usa abas nesta tela (achado estrutural confirmado no
// rastreio) — segue a exceção "compact single-view screens" do CLAUDE.md,
// mesmo padrão de fornecedores.tsx/cilindro-cadastro.tsx.
// ============================================================
export default function PedidoCompletoScreen() {
  const router = useRouter();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="O Pedido Completo está disponível apenas no web. Use a pré-venda rápida pelo app."
        testID="pedido-completo-web-only"
      />
    );
  }

  return <PedidoCompletoWebScreen router={router} />;
}

function PedidoCompletoWebScreen({ router }: { router: ReturnType<typeof useRouter> }) {
  const { can, isMaster, classe, moduleOn } = usePermissions();
  const params = useLocalSearchParams<{ pedido?: string }>();
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
    tref.current = setTimeout(() => setToast(null), 1500);
  }, []);

  const [pedido, setPedido] = useState<PedidoCompletoData | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [clienteResumo, setClienteResumo] = useState<ClienteResumo | null>(null);
  const [loadingResumo, setLoadingResumo] = useState(false);

  const [validade, setValidade] = useState<string | null>(null);
  const [obs, setObs] = useState("");
  const [areaAtuacao, setAreaAtuacao] = useState<number | null>(null);
  const [formaPag, setFormaPag] = useState<string>("");
  const handleFormaPagModalChanged = useCallback(async () => {
    if (!conn || !pedidoId) return;
    const j = await apiGet(conn, `/api/pedido-completo/${pedidoId}`);
    if (j?.success && j.pedido) setFormaPag(j.pedido.forma_pag || "");
  }, [conn, pedidoId]);
  const [localEntrega, setLocalEntrega] = useState("");
  const [previsaoEntrega, setPrevisaoEntrega] = useState<string | null>(null);
  const [numPedCliente, setNumPedCliente] = useState("");
  const [infoEntrega, setInfoEntrega] = useState("");

  const [areas, setAreas] = useState<AreaAtuacao[]>([]);
  const [funcionarios, setFuncionarios] = useState<Funcionario[]>([]);
  const [formasPag, setFormasPag] = useState<FormaPag[]>([]);

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Busca rápida direto no campo Cliente (sem abrir o modal, exceto quando
  // há 0 ou 2+ resultados — ver resolveClienteQuickTerm)
  const [clienteQuickTerm, setClienteQuickTerm] = useState("");
  const [clienteQuickLoading, setClienteQuickLoading] = useState(false);

  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [funcaoCod, setFuncaoCod] = useState<number>(1);
  const [waCompany, setWaCompany] = useState<string | null>(null);

  const sit = (pedido?.situacao || "A").toUpperCase();
  const isAberto = !editing || sit === "A";
  const isFechado = sit === "F";
  // Regra real (frmmanpedfor.frm): pedido Fechado só permite editar
  // vendedor/forma de pagamento; Aberto permite editar tudo; Faturado/
  // Cancelado não permite editar nada.
  const camposTravados = editing && !isAberto && !isFechado;

  const it = usePedidoItens({
    conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, showToast,
    servicosOn: moduleOn("servicos"), basePath: "/api/pedido-completo",
  });

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      setWaCompany(s?.empresa ?? null);
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number"
        ? cod
        : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      setVendedor(vCod);
      const masterFlag = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(masterFlag ? -2 : (typeof vCod === "number" ? vCod : -2));
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = cf ? parseInt(cf, 10) : NaN;
      setFuncaoCod(masterFlag ? 1 : (Number.isFinite(fc) && fc > 0 ? fc : 1));
      setVendedorNome((s?.funcionario?.nome_guerra || s?.funcionario?.nome || "") as string);
      const codFuncao = String(s?.funcionario?.cod_funcao || "").trim().padStart(2, "0");
      setVendedorCanEdit(masterFlag || VENDEDOR_EDIT_FUNCOES.includes(codFuncao));

      if (c) {
        try {
          const [ra, rf, rfp] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
            apiGet(c, `/api/forma-pagamento`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
          if (rfp?.success) setFormasPag(rfp.items || []);
        } catch {
          // combos ficam vazios
        }
      }

      if (editing && pedidoId && c) {
        try {
          const j = await apiGet(c, `/api/pedido-completo/${pedidoId}`);
          if (j?.success && j.pedido) {
            const p: PedidoCompletoData = j.pedido;
            setPedido(p);
            if (p.cliente) setCliente({ codigo: p.cliente, nome: p.cliente_nome, cgc_cpf: p.cliente_cgc, telefone: "" });
            setValidade(p.validade || null);
            setObs(p.obs || "");
            setAreaAtuacao(p.area_atuacao ?? null);
            setFormaPag(p.forma_pag || "");
            setLocalEntrega(p.local_entrega || "");
            setPrevisaoEntrega(p.previsao_entrega || null);
            setNumPedCliente(p.num_ped_cliente || "");
            setInfoEntrega(p.infoentrega || "");
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

  // Ao voltar de "Alterar dados do cliente" (cadastro rápido), o código do
  // cliente não muda — então o efeito acima não refaz a busca sozinho.
  // Refaz o resumo (e sincroniza nome/CPF-CNPJ exibidos no topo) sempre que
  // a tela reganha foco com um cliente já selecionado. Pedido explícito do
  // usuário, 2026-07-17.
  useFocusEffect(
    useCallback(() => {
      if (!conn || !cliente?.codigo) return;
      const codigo = cliente.codigo;
      apiGet(conn, `/api/clientes/${codigo}/resumo`)
        .then((j) => {
          if (j?.success && j.cliente) {
            setClienteResumo(j.cliente);
            setCliente((prev) =>
              prev && prev.codigo === codigo
                ? { ...prev, nome: j.cliente.nome, cgc_cpf: j.cliente.cgc_cpf, telefone: j.cliente.telefone }
                : prev
            );
          }
        })
        .catch(() => {});
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [conn, cliente?.codigo])
  );

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

  // Mantém o campo de busca sempre mostrando o nome do cliente atualmente
  // selecionado (o campo continua editável por cima — mesmo comportamento
  // do Campo(6) do Pedido Bar legado). Cobre todos os pontos que chamam
  // setCliente sem precisar duplicar a sincronização em cada um deles.
  useEffect(() => {
    if (cliente) setClienteQuickTerm(cliente.nome);
  }, [cliente]);

  // Termo digitado no padrão "C<número>" (ex. C1, C15) = Comanda. Só faz
  // sentido resolver a comanda relacionada quando ainda não há um pedido
  // carregado (Novo Pedido) — trocar o cliente de um pedido já aberto não
  // deve pular pra outro pedido.
  const COMANDA_TERM_RE = /^C\d+$/i;

  const handlePickClienteQuick = async (c: ClienteRow, typedTerm?: string) => {
    setCliente(c);
    if (!editing && conn && typedTerm && COMANDA_TERM_RE.test(typedTerm.trim())) {
      try {
        const j = await apiGet(conn, `/api/pedidos/aberto-por-cliente`, { cliente: c.codigo });
        if (j?.success && j.pedido) {
          router.replace({ pathname: "/pedido-completo", params: { pedido: String(j.pedido) } });
        }
      } catch {
        // silencioso — segue como pedido novo pra esse cliente
      }
    }
  };

  const handleCreateClienteFromQuick = (term: string) => {
    router.push({ pathname: "/cliente-form", params: clienteSearchParams(term) });
  };

  // Resolve o termo digitado no campo rápido de Cliente: 1 resultado carrega
  // o cliente direto na tela (e, se o termo digitado for "C<número>" —
  // Comanda —, reabre o pedido em aberto dessa comanda em vez de um pedido
  // novo); 0 ou 2+ resultados abrem o modal de busca completo
  // (`ClientSearchModal`), que já cobre tanto a lista pra escolher quanto
  // o "Cadastrar novo cliente" quando não encontra nada.
  const resolveClienteQuickTerm = async (term: string) => {
    const t = term.trim();
    if (!t || !conn) return;
    setClienteQuickLoading(true);
    try {
      const j = await apiGet(conn, `/api/clientes/find/search`, { term: t });
      const items: ClienteRow[] = j?.items || [];
      if (items.length === 1) {
        await handlePickClienteQuick(items[0], t);
      } else {
        setSearchTerm(t);
        setSearchResults([]);
        setSearchOpen(true);
      }
    } catch {
      // silencioso — usuário pode tentar de novo ou usar o botão de busca
    } finally {
      setClienteQuickLoading(false);
    }
  };

  // Só busca com Enter (onSubmitTerm) — digitar sozinho não dispara nada,
  // só limpa o cliente já selecionado (campo volta a ficar "em busca").
  const handleClienteQuickChange = (v: string) => {
    setClienteQuickTerm(v);
    if (cliente) setCliente(null);
  };

  const handleSave = async () => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    if (vendedor == null) { showToast("Vendedor não identificado.", "error"); return; }
    setSaving(true);
    try {
      const body = {
        cliente: cliente.codigo,
        vendedor,
        forma_pag: formaPag,
        validade: validade || null,
        previsao_entrega: previsaoEntrega || null,
        local_entrega: localEntrega,
        infoentrega: infoEntrega,
        num_ped_cliente: numPedCliente,
        obs,
        area_atuacao: areaAtuacao,
        usuario_alteracao: usuarioCod,
        classe,
        plataforma: Platform.OS,
      };
      const j = editing && pedidoId
        ? await apiSend(conn, `/api/pedido-completo/${pedidoId}`, "PUT", body)
        : await apiSend(conn, `/api/pedido-completo/create`, "POST", body);
      if (!j?.success) {
        showToast(j?.message || "Falha ao gravar.", "error");
      } else if (editing) {
        showToast("Pedido atualizado.", "success");
      } else {
        showToast(`Pedido #${j.pedido} criado. Adicione os itens.`, "success");
        setTimeout(
          () => router.replace({ pathname: "/pedido-completo", params: { pedido: String(j.pedido) } }),
          500
        );
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setSaving(false); }
  };

  const sitColor = useMemo(() => SIT_COLOR[sit] || colors.muted, [sit]);

  const [fechando, setFechando] = useState(false);
  const handleFechar = useCallback(async () => {
    if (!conn || !pedidoId) return;
    if (!it.itens.length) { showToast("Inclua pelo menos um produto ou serviço.", "error"); return; }
    setFechando(true);
    try {
      const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/fechar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pedido Fechado.", "success");
        setPedido((p) => (p ? { ...p, situacao: "F", situacao_label: "Fechado" } : p));
      } else {
        showToast(j?.message || "Não foi possível fechar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFechando(false); }
  }, [conn, pedidoId, it.itens.length, classe, isMaster, usuarioCod, showToast]);

  const [cancelando, setCancelando] = useState(false);
  const handleCancelar = useCallback(async () => {
    if (!conn || !pedidoId) return;
    setCancelando(true);
    try {
      const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/cancelar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pedido Cancelado.", "success");
        setPedido((p) => (p ? { ...p, situacao: "C", situacao_label: "Cancelado" } : p));
      } else {
        showToast(j?.message || "Não foi possível cancelar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setCancelando(false); }
  }, [conn, pedidoId, classe, isMaster, usuarioCod, showToast]);

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
  const vendedorOptionsWithGhost: SelectOption[] = useMemo(() => {
    if (vendedor == null) return vendedorOptions;
    const exists = vendedorOptions.some((o) => Number(o.value) === vendedor);
    if (exists) return vendedorOptions;
    return [
      { value: vendedor, label: vendedorNome || `Funcionário #${vendedor}`, sub: `#${vendedor}` },
      ...vendedorOptions,
    ];
  }, [vendedor, vendedorNome, vendedorOptions]);
  const formaPagOptions: SelectOption[] = useMemo(
    () => formasPag.map((f) => ({ value: f.codigo, label: f.descricao })),
    [formasPag]
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="pedido-completo-screen">
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.iconBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="pedido-completo-back-button"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={styles.headerLogo} resizeMode="contain" />
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Pedido #${pedidoId} — Completo` : "Novo Pedido — Completo"}
        </Text>
        {can("PEDIDO_COMP.GRAVAR") && !camposTravados ? (
          <Pressable
            onPress={handleSave}
            disabled={saving}
            style={({ pressed }) => [styles.saveBtn, (pressed || saving) && { opacity: 0.7 }]}
            hitSlop={8}
            testID="pedido-completo-save-button"
          >
            {saving ? (
              <ActivityIndicator color={colors.onBrandPrimary} size="small" />
            ) : (
              <>
                <Ionicons name="checkmark" size={18} color={colors.onBrandPrimary} />
                <Text style={styles.saveLabel}>Gravar</Text>
              </>
            )}
          </Pressable>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {editing && pedido ? (
            <View style={styles.sitRow}>
              <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                <Text style={[styles.sitTagText, { color: sitColor }]}>{pedido.situacao_label}</Text>
              </View>
              <Text style={styles.headerMeta}>Aberto {formatDateBR(pedido.data)} {pedido.hora_aberto}</Text>
              {camposTravados ? (
                <Text style={[styles.headerMeta, { color: colors.warning }]}>
                  Pedido "{pedido.situacao_label}" não pode ser alterado.
                </Text>
              ) : null}
            </View>
          ) : null}

          <View style={styles.card} testID="pedido-completo-cliente">
            <ClienteSection
              hasCliente={!!cliente}
              clienteResumo={clienteResumo}
              loadingResumo={loadingResumo}
              onOpenSearch={() => {
                if (camposTravados) return;
                setSearchTerm(clienteQuickTerm); setSearchResults([]); setSearchOpen(true);
              }}
              onEditCliente={
                cliente?.codigo
                  ? () => router.push({ pathname: "/cliente-form", params: { codigo: String(cliente.codigo) } })
                  : undefined
              }
              quickTerm={clienteQuickTerm}
              onQuickTermChange={handleClienteQuickChange}
              quickLoading={clienteQuickLoading}
              onSubmitTerm={resolveClienteQuickTerm}
              disabled={camposTravados}
            />
          </View>

          <View style={styles.card} testID="pedido-completo-dados">
            <AccordionSection title="Dados Principais" testID="pedido-completo-dados-principais">
            <View style={styles.formGrid}>
              <Field label="Vendedor" style={styles.colHalf}>
                <SelectField
                  value={vendedor}
                  onChange={(v) => setVendedor(v == null ? null : Number(v))}
                  options={vendedorOptionsWithGhost}
                  placeholder="Selecione o vendedor"
                  disabled={!vendedorCanEdit || camposTravados}
                  compactWeb
                  modalTitle="Selecionar Vendedor"
                  testID="pedido-completo-vendedor"
                />
              </Field>

              <Field label="Forma de Pagamento" style={styles.colHalf}>
                <FormaPagamentoField
                  conn={conn}
                  tipoDav="PED"
                  documento={pedidoId}
                  tela="PEDIDO_COMP"
                  valorTotal={pedido?.total || 0}
                  formaPag={formaPag}
                  onFormaPagChange={setFormaPag}
                  formaPagOptions={formaPagOptions}
                  onChanged={handleFormaPagModalChanged}
                  compactWeb
                  disabled={isFechado ? false : camposTravados}
                  testIDPrefix="pedido-completo-forma-pag"
                />
              </Field>

              <Field label="Área de Atuação" style={styles.colHalf}>
                <SelectField
                  value={areaAtuacao}
                  onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
                  options={areaOptions}
                  placeholder="Selecione a área"
                  allowClear
                  compactWeb
                  disabled={camposTravados}
                  modalTitle="Selecionar Área de Atuação"
                  testID="pedido-completo-area"
                />
              </Field>

              <Field label="Validade" style={styles.colHalf}>
                {camposTravados ? (
                  <View style={pedidoStyles.readonlyBox}>
                    <Text style={pedidoStyles.readonlyText}>{formatDateBR(validade)}</Text>
                  </View>
                ) : (
                  <WebDateField value={validade} onChange={setValidade} testID="pedido-completo-validade" />
                )}
              </Field>

              <Field label="Previsão de Entrega" style={styles.colHalf}>
                {camposTravados ? (
                  <View style={pedidoStyles.readonlyBox}>
                    <Text style={pedidoStyles.readonlyText}>{formatDateBR(previsaoEntrega)}</Text>
                  </View>
                ) : (
                  <WebDateField value={previsaoEntrega} onChange={setPrevisaoEntrega} testID="pedido-completo-previsao" />
                )}
              </Field>

              <Field label="Local de Entrega" style={styles.colHalf}>
                <TextInput
                  value={localEntrega}
                  onChangeText={setLocalEntrega}
                  editable={!camposTravados}
                  placeholder="Local de entrega"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-completo-local-entrega"
                />
              </Field>

              <Field label="Nº Pedido do Cliente" style={styles.colHalf}>
                <TextInput
                  value={numPedCliente}
                  onChangeText={setNumPedCliente}
                  editable={!camposTravados}
                  placeholder="Referência do cliente"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-completo-num-ped-cliente"
                />
              </Field>

              <Field label="Informações de Entrega" style={styles.colHalf}>
                <TextInput
                  value={infoEntrega}
                  onChangeText={setInfoEntrega}
                  editable={!camposTravados}
                  placeholder="Instruções de entrega"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-completo-info-entrega"
                />
              </Field>

              <View style={styles.fullWidth}>
                <Field label="Data">
                  <View style={pedidoStyles.readonlyBox}>
                    <Ionicons name="calendar-outline" size={16} color={colors.muted} />
                    <Text style={pedidoStyles.readonlyText}>
                      {editing ? formatDateBR(pedido?.data || null) : formatDateBR(todayISO())}
                    </Text>
                  </View>
                </Field>
              </View>

              <View style={styles.fullWidth}>
                <Field label="Observação">
                  <TextInput
                    value={obs}
                    onChangeText={setObs}
                    editable={!camposTravados}
                    placeholder="Observação do pedido"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, styles.textArea]}
                    multiline
                    numberOfLines={4}
                    testID="pedido-completo-obs"
                  />
                </Field>
              </View>
            </View>
            </AccordionSection>
          </View>

          {!editing || !pedidoId ? (
            <View style={styles.card}>
              <View style={styles.lockedRow}>
                <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                <Text style={styles.lockedText}>
                  Grave o cabeçalho primeiro para incluir itens no pedido.
                </Text>
              </View>
            </View>
          ) : (
            <>
              <ItemList
                editing={editing}
                isAberto={isAberto}
                it={it}
                tela="PEDIDO_COMP"
                onAnalisar={() => router.push({ pathname: "/relatorio-descontos", params: { pedido: String(pedidoId) } })}
              />

              <View style={styles.actionsRow}>
                {isAberto && can("PEDIDO_COMP.SITUACAO") ? (
                  <Pressable
                    onPress={handleFechar}
                    disabled={fechando || it.itens.length === 0}
                    style={({ pressed }) => [
                      pedidoStyles.fecharBtn, { flex: 1 },
                      (pressed || fechando || it.itens.length === 0) && { opacity: 0.6 },
                    ]}
                    testID="pedido-completo-fechar-btn"
                  >
                    {fechando ? (
                      <ActivityIndicator size="small" color="#fff" />
                    ) : (
                      <Ionicons name="lock-closed-outline" size={18} color="#fff" />
                    )}
                    <Text style={pedidoStyles.fecharBtnText}>Fechar Pedido</Text>
                  </Pressable>
                ) : null}

                {(sit === "A" || sit === "F") && can("PEDIDO_COMP.SITUACAO") ? (
                  <Pressable
                    onPress={handleCancelar}
                    disabled={cancelando}
                    style={({ pressed }) => [
                      styles.cancelBtn, { flex: 1 },
                      (pressed || cancelando) && { opacity: 0.6 },
                    ]}
                    testID="pedido-completo-cancelar-btn"
                  >
                    {cancelando ? (
                      <ActivityIndicator size="small" color={colors.error} />
                    ) : (
                      <Ionicons name="close-circle-outline" size={18} color={colors.error} />
                    )}
                    <Text style={styles.cancelBtnText}>Cancelar Pedido</Text>
                  </Pressable>
                ) : null}
              </View>

              {can("PEDIDO_COMP.WHATSAPP") ? (
                <WhatsappButton
                  conn={conn}
                  documentType="PED"
                  documentId={pedidoId}
                  userId={usuarioCod}
                  companyId={waCompany}
                />
              ) : null}
            </>
          )}

          <View style={{ height: 40 }} />
        </View>
      </ScrollView>

      <AddItemModal
        it={it}
        tela="PEDIDO_COMP"
        onOpenProdutos={() => {
          it.setAddOpen(false);
          router.push({ pathname: "/produtos", params: { pedido: String(pedidoId), origem: "completo" } });
        }}
      />
      <EditItemModal it={it} tela="PEDIDO_COMP" />
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
          handleCreateClienteFromQuick(searchTerm);
        }}
      />

      <ScreenToast toast={toast} testID="pedido-completo-toast" />
    </SafeAreaView>
  );
}

function Field({ label, children, style }: { label: string; children: React.ReactNode; style?: object }) {
  return (
    <View style={[{ marginBottom: spacing.md }, style]}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
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
  headerLogo: { width: 56, height: 16, marginRight: 8 },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  saveBtn: {
    flexDirection: "row", alignItems: "center", gap: 4,
    paddingHorizontal: spacing.md, paddingVertical: 8,
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    borderWidth: 1, borderColor: "rgba(255,255,255,0.3)", minWidth: 90, justifyContent: "center",
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  formGrid: { flexDirection: "row", flexWrap: "wrap", columnGap: spacing.md },
  colHalf: { width: "49%" },
  fullWidth: { width: "100%" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  textArea: { minHeight: 90, textAlignVertical: "top" },
  sitRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginBottom: spacing.md },
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  headerMeta: { fontSize: 12, color: colors.muted },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  actionsRow: { flexDirection: "row", gap: spacing.md, marginTop: spacing.md },
  cancelBtn: {
    flexDirection: "row", alignItems: "center", justifyContent: "center", gap: 8,
    paddingVertical: 14, borderRadius: radius.md, borderWidth: 1, borderColor: colors.error,
  },
  cancelBtnText: { color: colors.error, fontWeight: "700", fontSize: 15 },
});
