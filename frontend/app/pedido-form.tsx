import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, KeyboardAvoidingView, Modal, Platform, Pressable, ScrollView, Text, TextInput, TouchableOpacity, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { colors, spacing } from "@/src/theme/colors";
import { formatDateBR, todayISO } from "@/src/utils/format";
import DateField from "@/src/components/DateField";
import WebDateField from "@/src/components/WebDateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import { styles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo, AreaAtuacao, Funcionario, PedidoData, ToastTone } from "@/src/components/pedido/types";
import { usePedidoItens } from "@/src/components/pedido/usePedidoItens";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import PedidoHeader from "@/src/components/pedido/PedidoHeader";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import ItemList from "@/src/components/pedido/ItemList";
import ReciboPedidoModal from "@/src/components/pedido/ReciboPedidoModal";
import AddItemModal from "@/src/components/pedido/AddItemModal";
import EditItemModal from "@/src/components/pedido/EditItemModal";
import GeneralDiscountModal from "@/src/components/pedido/GeneralDiscountModal";
import DiscountsReportModal from "@/src/components/pedido/DiscountsReportModal";
import PedidoTotalizadoModal from "@/src/components/pedido/PedidoTotalizadoModal";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import FormaPagamentoField from "@/src/components/pedido/FormaPagamentoField";
import AnexosPedidoModal from "@/src/components/pedido/AnexosPedidoModal";
import WhatsappButton from "@/src/components/WhatsappButton";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";

// Funções que podem alterar vendedor: 01 (Administrador) e 02 (Gerente)
const VENDEDOR_EDIT_FUNCOES = ["01", "02"];
const isWeb = Platform.OS === "web";
export default function PedidoFormScreen() {
  const router = useRouter();
  const { can, isMaster, classe, moduleOn } = usePermissions();
  const feedback = useFeedback();
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
  const [formaPag, setFormaPag] = useState<string>("");
  const [formasPag, setFormasPag] = useState<{ codigo: string; descricao: string }[]>([]);
  const handleFormaPagModalChanged = useCallback(async () => {
    if (!conn || !pedidoId) return;
    const j = await apiGet(conn, `/api/pedidos/${pedidoId}`);
    if (j?.success && j.pedido) {
      setPedido(j.pedido);
      setFormaPag(j.pedido.forma_pag || "");
    }
  }, [conn, pedidoId]);
  const [previsaoEntrega, setPrevisaoEntrega] = useState<string | null>(null);
  const [horaEntrega, setHoraEntrega] = useState("");
  const [pedidoEntregue, setPedidoEntregue] = useState(false);
  const [entregueSaving, setEntregueSaving] = useState(false);
  const [dadosOpen, setDadosOpen] = useState(false);

  const [areas, setAreas] = useState<AreaAtuacao[]>([]);
  const [funcionarios, setFuncionarios] = useState<Funcionario[]>([]);

  // Modal de busca de cliente
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  // Busca rápida direto no campo Cliente (sem abrir o modal, exceto quando
  // há 0 ou 2+ resultados — ver resolveClienteQuickTerm)
  const [clienteQuickTerm, setClienteQuickTerm] = useState("");
  const [clienteQuickLoading, setClienteQuickLoading] = useState(false);

  // Código do usuário logado p/ log de descontos (-2 = KONTACTO master)
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [funcaoCod, setFuncaoCod] = useState<number>(1); // 1=gerente,2=supervisor,3=vendedor
  const [waCompany, setWaCompany] = useState<string | null>(null);

  const isAberto = (pedido?.situacao || "A").toUpperCase() === "A";
  const it = usePedidoItens({
    conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, showToast,
    servicosOn: moduleOn("servicos"), printPorFinalidade: true,
  });

  // -------- Init
  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      setWaCompany(s?.empresa ?? null);
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
          const [ra, rf, rfp] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
            apiGet(c, `/api/forma-pagamento`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            // se houver apenas 1 área de atuação, seleciona automaticamente
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
          if (rfp?.success) setFormasPag(rfp.items || []);
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
            setPrevisaoEntrega(p.previsao_entrega || null);
            setHoraEntrega((p.hora_entrega || "").slice(0, 5));
            setPedidoEntregue(!!p.pedido_entregue);
            setFormaPag(p.forma_pag || "");
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

  // Mantém o campo de busca sempre mostrando o nome do cliente atualmente
  // selecionado (o campo continua editável por cima — mesmo comportamento
  // do Campo(6) do Pedido Bar legado). Cobre todos os pontos que chamam
  // setCliente (pré-seleção por rota, carregar pedido em edição, escolha
  // rápida, escolha no modal) sem precisar duplicar a sincronização em
  // cada um deles.
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
          router.replace({ pathname: "/pedido-form", params: { pedido: String(j.pedido) } });
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
        validade: validade || null,
        obs,
        area_atuacao: areaAtuacao,
        previsao_entrega: previsaoEntrega || null,
        hora_entrega: horaEntrega || null,
        forma_pag: formaPag || null,
        usuario_alteracao: usuarioCod,
        classe,
        plataforma: Platform.OS,
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

  // Checkbox "Pedido Entregue" — grava direto no toque, fora do fluxo
  // normal de Gravar (FrmManPedBar.frm, Check88_Click). Só disponível pra
  // pedido já salvo (mesmo gate `AlteraEntrega` do legado).
  const handleToggleEntregue = async () => {
    if (!conn || !editing || !pedidoId) return;
    const novo = !pedidoEntregue;
    setEntregueSaving(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/entregue`, "POST", {
        entregue: novo, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (j?.success) {
        setPedidoEntregue(novo);
        showToast(novo ? "Pedido marcado como entregue." : "Marcação de entrega removida.", "success");
      } else {
        showToast(j?.message || "Falha ao gravar entrega.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setEntregueSaving(false); }
  };

  const sit = pedido?.situacao || "A";
  const sitColor = useMemo(() => SIT_COLOR[sit] || colors.muted, [sit]);
  const isFechado = sit.toUpperCase() === "F";

  const [fechando, setFechando] = useState(false);
  const handleFechar = useCallback(async () => {
    if (!conn || !pedidoId) return;
    if (!it.itens.length) { showToast("Inclua pelo menos um produto ou serviço.", "error"); return; }
    setFechando(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/fechar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pré-venda Fechada.", "success");
        setPedido((p) => (p ? { ...p, situacao: "F", situacao_label: "Fechado" } : p));
      } else {
        showToast(j?.message || "Não foi possível fechar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFechando(false); }
  }, [conn, pedidoId, it.itens.length, classe, isMaster, showToast]);

  // Faturar Pedido (FrmManPedBar.frm, Command111_Click) — gera a Comanda e
  // marca situação PG. Só a parte não-fiscal (sem emissão de NFC-e — ver
  // PENDENCIAS.md > "Pedido Bar").
  const [faturando, setFaturando] = useState(false);
  const handleFaturar = useCallback(async () => {
    if (!conn || !pedidoId) return;
    if (!it.itens.length) { showToast("Inclua pelo menos um produto ou serviço.", "error"); return; }
    setFaturando(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/faturar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pedido faturado.", "success");
        setPedido((p) => (p ? { ...p, situacao: "PG", situacao_label: "Faturado" } : p));
        // Reaproveita a impressão pra emitir o pedido logo após faturar
        // (pedido explícito do usuário) — abre o preview automaticamente;
        // o clique em "Imprimir" dentro dele é que dispara window.print().
        setReciboOpen(true);
      } else {
        showToast(j?.message || "Não foi possível faturar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFaturando(false); }
  }, [conn, pedidoId, it.itens.length, classe, isMaster, showToast]);

  // Reabrir Pedido (FrmManPedBar.frm, cmdReabrir_Click) — situação F -> A.
  // Pill amarelo entre "Faturar Pedido" e "Anexo" (pedido explícito do
  // usuário, 2026-07-16). Legado não exige confirmação/senha aqui
  // (diferente do Cancelar) — mesmo comportamento replicado.
  const [reabrindo, setReabrindo] = useState(false);
  const handleReabrir = useCallback(async () => {
    if (!conn || !pedidoId) return;
    setReabrindo(true);
    try {
      const j = await apiSend(conn, `/api/pedidos/${pedidoId}/reabrir`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pedido Reaberto!", "success");
        setPedido((p) => (p ? { ...p, situacao: "A", situacao_label: "Aberto" } : p));
      } else {
        showToast(j?.message || "Não foi possível reabrir.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setReabrindo(false); }
  }, [conn, pedidoId, classe, isMaster, usuarioCod, showToast]);

  // Cancelar Pedido (FrmManPedBar.frm, Command9_Click) — situação -> C, só
  // Aberto/Fechado (backend bloqueia Faturado). Pill vermelho ao lado de
  // "Reabrir" (pedido explícito do usuário, 2026-07-16).
  const [cancelando, setCancelando] = useState(false);
  const handleCancelar = useCallback(() => {
    if (!conn || !pedidoId) return;
    feedback.showConfirm(`Cancelar o Pedido nº ${pedidoId}? Esta ação não pode ser desfeita.`, async () => {
      setCancelando(true);
      try {
        const j = await apiSend(conn, `/api/pedidos/${pedidoId}/cancelar`, "POST", {
          classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
        });
        if (j?.success) {
          showToast(j.message || "Pedido Cancelado!", "success");
          setPedido((p) => (p ? { ...p, situacao: "C", situacao_label: "Cancelado" } : p));
        } else {
          showToast(j?.message || "Não foi possível cancelar.", "error");
        }
      } catch (e) {
        showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
      } finally { setCancelando(false); }
    });
  }, [conn, pedidoId, classe, isMaster, usuarioCod, showToast, feedback]);

  // Anexos do Pedido (Gestor de Documentos) — pill entre "Faturar Pedido" e
  // "Imprimir"/"Cancelar" (pedido explícito do usuário, 2026-07-16). Grava
  // como anexo do Cliente (ver AnexosPedidoModal.tsx) — precisa do cliente
  // já selecionado, que sempre existe num pedido já salvo (Cliente é
  // obrigatório pra gravar).
  const [anexosOpen, setAnexosOpen] = useState(false);

  // Preview/impressão do pedido (Pedido_48_COL) — botão "Imprimir" ao lado
  // de "Faturar Pedido", e auto-aberto após faturar com sucesso (acima).
  const [reciboOpen, setReciboOpen] = useState(false);

  // Opções dos comboboxes
  const areaOptions: SelectOption[] = useMemo(
    () => areas.map((a) => ({ value: a.codigo, label: a.descricao })),
    [areas]
  );
  const formaPagOptions: SelectOption[] = useMemo(
    () => formasPag.map((f) => ({ value: f.codigo, label: f.descricao })),
    [formasPag]
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
        canSave={can("PEDIDO.GRAVAR") && isAberto}
        titleExtra={
          <View style={{ width: 110, marginRight: 8 }}>
            <SelectField
              value={vendedor}
              onChange={(v) => setVendedor(v == null ? null : Number(v))}
              options={vendedorOptionsWithGhost}
              placeholder="Selecione"
              disabled={!vendedorCanEdit}
              modalTitle="Selecionar Vendedor"
              variant="onDark"
              hideSub
              compactWeb
              testID="pedido-form-vendedor"
            />
          </View>
        }
      />

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <ScrollView contentContainerStyle={styles.scroll} keyboardShouldPersistTaps="handled">
          {/* Cabeçalho do pedido: situação/data à esquerda, Entrega à
              direita, tudo na mesma linha (sem quebrar). */}
          {editing && pedido ? (
            <View style={[styles.row, { marginBottom: 12, alignItems: "center", justifyContent: "space-between", flexWrap: "nowrap" }]}>
              <View style={{ flexDirection: "row", alignItems: "center", gap: 8, flexShrink: 1, minWidth: 0 }}>
                <View style={[styles.sitTag, { backgroundColor: sitColor + "22", flexShrink: 0 }]}>
                  <Text style={[styles.sitTagText, { color: sitColor }]}>{pedido.situacao_label}</Text>
                </View>
                <Text style={styles.headerMeta} numberOfLines={1}>Aberto {formatDateBR(pedido.data)} {pedido.hora_aberto}</Text>
              </View>

              {/* Forma de Pagamento — combobox simples (1 forma) sempre
                  visível no topo da tela, botão ao lado abre o modal
                  completo pra 2+ formas (pedido explícito do usuário).
                  Só web — mobile mantém o cabeçalho como já era (situação +
                  Entrega), sem espaço pra um terceiro grupo sem quebrar. */}
              {isWeb ? (
                <View style={{ flexDirection: "column", gap: 2, flexShrink: 0 }}>
                  <Text style={[styles.headerMeta, { textTransform: "uppercase", fontSize: 10, letterSpacing: 0.5 }]}>Forma de Pagamento</Text>
                  <FormaPagamentoField
                    conn={conn}
                    tipoDav="PED"
                    documento={pedidoId}
                    tela="PEDIDO"
                    valorTotal={pedido?.total || 0}
                    formaPag={formaPag}
                    onFormaPagChange={setFormaPag}
                    formaPagOptions={formaPagOptions}
                    onChanged={handleFormaPagModalChanged}
                    compactWeb
                    fieldWidth={200}
                    testIDPrefix="pedido-form-forma-pag"
                  />
                </View>
              ) : null}

              {/* Grupo Entrega nunca encolhe/corta — a prioridade é o
                  checkbox "Pedido Entregue" ficar sempre visível; se faltar
                  espaço, quem cede é o texto de situação à esquerda. */}
              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexShrink: 0 }}>
                <Text style={styles.headerMeta}>Entrega</Text>
                <View style={{ width: 150 }}>
                  {Platform.OS === "web" ? (
                    <WebDateField
                      value={previsaoEntrega}
                      onChange={setPrevisaoEntrega}
                      type="date"
                      icon="calendar-outline"
                      testID="pedido-form-previsao-entrega"
                    />
                  ) : (
                    <DateField
                      value={previsaoEntrega}
                      onChange={setPrevisaoEntrega}
                      placeholder="DD/MM/AAAA"
                      testID="pedido-form-previsao-entrega"
                    />
                  )}
                </View>
                <View style={{ width: 120 }}>
                  {Platform.OS === "web" ? (
                    <WebDateField
                      value={horaEntrega || null}
                      onChange={setHoraEntrega}
                      type="time"
                      icon="time-outline"
                      testID="pedido-form-hora-entrega"
                    />
                  ) : (
                    <TextInput
                      value={horaEntrega}
                      onChangeText={setHoraEntrega}
                      placeholder="HH:MM"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="pedido-form-hora-entrega"
                    />
                  )}
                </View>
                {pedidoId && can("PEDIDO.ENTREGUE") ? (
                  <TouchableOpacity
                    onPress={handleToggleEntregue}
                    disabled={entregueSaving}
                    activeOpacity={0.7}
                    style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: entregueSaving ? 0.6 : 1 }}
                    testID="pedido-form-entregue-checkbox"
                  >
                    <Ionicons name={pedidoEntregue ? "checkbox" : "square-outline"} size={16} color={colors.brandPrimary} />
                    <Text style={[styles.headerMeta, { fontSize: 11 }]} numberOfLines={1}>Entregue</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            </View>
          ) : null}

          {/* Cliente: seletor + resumo (toque no resumo abre "Dados Principais") */}
          <ClienteSection
            hasCliente={!!cliente}
            clienteResumo={clienteResumo}
            loadingResumo={loadingResumo}
            onOpenSearch={() => { setSearchTerm(clienteQuickTerm); setSearchResults([]); setSearchOpen(true); }}
            onOpenDados={() => setDadosOpen(true)}
            quickTerm={clienteQuickTerm}
            onQuickTermChange={handleClienteQuickChange}
            quickLoading={clienteQuickLoading}
            onSubmitTerm={resolveClienteQuickTerm}
          />

          <Modal visible={dadosOpen} transparent animationType="slide" onRequestClose={() => setDadosOpen(false)}>
            <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => setDadosOpen(false)}>
              <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
                <View style={styles.modalHeader}>
                  <Text style={styles.modalTitle}>Dados Principais</Text>
                  <Pressable onPress={() => setDadosOpen(false)} hitSlop={8}>
                    <Ionicons name="close" size={22} color={colors.muted} />
                  </Pressable>
                </View>
                <ScrollView style={{ maxHeight: 480 }} keyboardShouldPersistTaps="handled">
                  {cliente ? (
                    loadingResumo ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginBottom: spacing.md }} />
                    ) : clienteResumo ? (
                      <View style={{ gap: 6, marginBottom: spacing.md }}>
                        <View style={styles.resumoRow}>
                          <Ionicons name="call-outline" size={16} color={colors.brandPrimary} />
                          <Text style={[styles.resumoText, { fontSize: 14 }]}>{clienteResumo.telefone || "Sem telefone"}</Text>
                        </View>
                        <View style={styles.resumoRow}>
                          <Ionicons name="location-outline" size={16} color={colors.brandPrimary} />
                          <Text style={[styles.resumoText, { fontSize: 14 }]}>{clienteResumo.endereco || "Sem endereço cadastrado"}</Text>
                        </View>
                        <View style={styles.resumoRow}>
                          <Ionicons name="mail-outline" size={16} color={colors.brandPrimary} />
                          <Text style={[styles.resumoText, { fontSize: 14 }]}>{clienteResumo.e_mail || "Sem e-mail"}</Text>
                        </View>
                      </View>
                    ) : null
                  ) : null}

                  {/* Área de atuação */}
                  <Text style={styles.sectionTitle}>Área de Atuação</Text>
                  <SelectField
                    value={areaAtuacao}
                    onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
                    options={areaOptions}
                    placeholder="Selecione a área"
                    modalTitle="Selecionar Área de Atuação"
                    allowClear
                    compactWeb
                    testID="pedido-form-area"
                  />

                  {/* Forma de Pagamento — só mobile aqui (web mostra no
                      topo da tela, junto de situação/Entrega). */}
                  {!isWeb ? (
                    <>
                      <Text style={styles.sectionTitle}>Forma de Pagamento</Text>
                      <FormaPagamentoField
                        conn={conn}
                        tipoDav="PED"
                        documento={pedidoId}
                        tela="PEDIDO"
                        valorTotal={pedido?.total || 0}
                        formaPag={formaPag}
                        onFormaPagChange={setFormaPag}
                        formaPagOptions={formaPagOptions}
                        onChanged={handleFormaPagModalChanged}
                        testIDPrefix="pedido-form-forma-pag-mobile"
                      />
                    </>
                  ) : null}

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
                </ScrollView>
              </Pressable>
            </Pressable>
          </Modal>

          {/* Itens do Pedido */}
          <ItemList
            editing={editing}
            isAberto={isAberto}
            it={it}
            onAnalisar={
              editing && pedidoId
                ? () => router.push({ pathname: "/relatorio-descontos", params: { pedido: String(pedidoId) } })
                : undefined
            }
            onFechar={editing && pedidoId ? handleFechar : undefined}
            fechando={fechando}
            onFaturar={editing && pedidoId ? handleFaturar : undefined}
            faturando={faturando}
            isFechado={isFechado}
            onReabrir={editing && pedidoId ? handleReabrir : undefined}
            reabrindo={reabrindo}
            onCancelar={editing && pedidoId ? handleCancelar : undefined}
            cancelando={cancelando}
            onAnexos={editing && pedidoId && cliente ? () => setAnexosOpen(true) : undefined}
            onImprimir={editing && pedidoId ? () => setReciboOpen(true) : undefined}
          />

          {editing && pedidoId && can("PEDIDO.WHATSAPP") ? (
            <WhatsappButton
              conn={conn}
              documentType="PED"
              documentId={pedidoId}
              userId={usuarioCod}
              companyId={waCompany}
            />
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
      <PedidoTotalizadoModal it={it} />
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
      {cliente ? (
        <AnexosPedidoModal
          visible={anexosOpen}
          onClose={() => setAnexosOpen(false)}
          conn={conn}
          pedido={pedidoId || 0}
          clienteCodigo={cliente.codigo}
        />
      ) : null}
      <ReciboPedidoModal
        visible={reciboOpen}
        onClose={() => setReciboOpen(false)}
        conn={conn}
        pedido={pedido}
        cliente={cliente}
        clienteResumo={clienteResumo}
        it={it}
      />
      <ReciboPedidoModal
        visible={!!it.printItem}
        onClose={() => it.setPrintItem(null)}
        conn={conn}
        pedido={pedido}
        cliente={cliente}
        clienteResumo={clienteResumo}
        it={it}
        item={it.printItem}
      />
      <ScreenToast toast={toast} testID="pedido-form-toast" />
    </SafeAreaView>
  );
}
