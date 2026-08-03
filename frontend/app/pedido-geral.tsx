import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  Modal,
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
import { formatDateBR, formatBRL, todayISO } from "@/src/utils/format";
import { styles as pedidoStyles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo, AreaAtuacao, Funcionario, PedidoData, ToastTone } from "@/src/components/pedido/types";
import { usePedidoItens } from "@/src/components/pedido/usePedidoItens";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import PedidoHeader from "@/src/components/pedido/PedidoHeader";
import ItemList from "@/src/components/pedido/ItemList";
import AddItemModal from "@/src/components/pedido/AddItemModal";
import EditItemModal from "@/src/components/pedido/EditItemModal";
import AgendarModal from "@/src/components/pedido/AgendarModal";
import GeneralDiscountModal from "@/src/components/pedido/GeneralDiscountModal";
import DiscountsReportModal from "@/src/components/pedido/DiscountsReportModal";
import PedidoTotalizadoModal from "@/src/components/pedido/PedidoTotalizadoModal";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import FormaPagamentoField from "@/src/components/pedido/FormaPagamentoField";
import AnexosPedidoModal from "@/src/components/pedido/AnexosPedidoModal";
import DividirPedidoModal from "@/src/components/pedido/DividirPedidoModal";
import ReciboPedidoModal from "@/src/components/pedido/ReciboPedidoModal";
import AjudaPedidoModal, { PEDIDO_BAR_AJUDA_ITENS, HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import WhatsappButton from "@/src/components/WhatsappButton";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";

// Funções que podem alterar vendedor: 01 (Administrador) e 02 (Gerente) — mesma
// regra do Pedido Bar (pedido-form.tsx).
const VENDEDOR_EDIT_FUNCOES = ["01", "02"];

type FormaPag = { codigo: string; descricao: string };

type PedidoGeralData = PedidoData & {
  forma_pag: string;
  forma_pag_descricao: string;
  local_entrega: string;
  previsao_entrega: string | null;
  num_ped_cliente: string;
  infoentrega: string;
  editavel: boolean;
};

// Modal de Ajuda do Pedido Geral — reaproveita a lista do Pedido Bar (mesmo
// componente `AjudaPedidoModal`, mesma ideia de "Modo Didático"), removendo
// só o que é exclusivo do segmento Bar (Tx Serviço, e o campo "Referência"
// que no Bar é a mesma coluna `num_ped_cliente` já explicada abaixo como
// "Nº Pedido do Cliente" — não faz sentido duas entradas pro mesmo campo) e
// acrescentando os campos que só existem no cabeçalho do Pedido Geral
// (frmmanpedfor.frm). Pedido explícito do usuário, 2026-07-20 ("tente usar
// as mesmas funções para não replicar o mesmo código entre telas").
const AJUDA_PEDIDO_GERAL_ITENS: HelpItem[] = [
  ...PEDIDO_BAR_AJUDA_ITENS.filter((i) => i.titulo !== "Tx Serviço" && i.titulo !== "Campo Referência"),
  {
    titulo: "Nº Pedido do Cliente",
    texto: "Campo livre para anotar o número de pedido/referência que o próprio cliente usa. Quando este pedido vem de uma divisão (Distribuir), mostra o número do pedido de origem e fica travado — só o pedido original mantém seu próprio número de referência.",
    icon: { lib: "ion", name: "bookmark-outline" },
  },
  {
    titulo: "Local de Entrega",
    texto: "Endereço ou ponto de entrega deste pedido, quando for diferente do endereço já cadastrado do cliente.",
    icon: { lib: "ion", name: "location-outline" },
  },
  {
    titulo: "Informações de Entrega",
    texto: "Instruções adicionais para quem for entregar o pedido (ex.: ponto de referência, horário preferido).",
    icon: { lib: "ion", name: "document-text-outline" },
  },
  {
    titulo: "Número de Série",
    texto: "Alguns produtos exigem escolher um número de série específico (ex.: equipamento com garantia individual) antes de incluir o item — a quantidade fica travada em 1 e a lista mostra só os números ainda disponíveis para aquele produto.",
    icon: { lib: "ion", name: "barcode-outline" },
  },
  {
    titulo: "Agendar",
    texto: "Quando o módulo Clínica está ativo, cada unidade de um serviço vira uma sessão própria (uma linha por unidade), e cada uma pode ser agendada individualmente: escolha o profissional e o horário do atendimento, e o sistema confere sozinho se há vaga disponível.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Ver na Agenda",
    texto: "Leva direto pra tela Agenda, já mostrando o profissional e o dia deste agendamento — só aparece em item que já foi agendado.",
    icon: { lib: "ion", name: "open-outline" },
  },
  {
    titulo: "Tipo de Preço / Comprimento / Largura",
    texto: "Produtos vendidos por metro quadrado (m²), metro linear (ml) ou metro cúbico (m³) pedem o tipo de preço e as dimensões da peça antes de incluir o item — o sistema calcula a área sozinho (respeitando piso de área mínima quando configurado) e já mostra o valor final antes de confirmar.",
    icon: { lib: "ion", name: "resize-outline" },
  },
];

// ============================================================
// Tela — Pedido Geral (web-only), ex-"Pedido Completo" — renomeado
// 2026-07-20, user-directed ("Ao longo desse projeto vamos ter 2 ou mais
// versões de tela de Pedido... Pedido Geral = PedidoGeral.tsx"): o segmento
// GERAL de Pedido, distinto do segmento Bar (`pedido-form.tsx`/
// `pedidos.tsx`). Aberto a partir da lista compartilhada `pedido-lista.tsx`
// (não mais `pedidos.tsx`, que agora é exclusiva do Pedido Bar). Rota/
// arquivo renomeados; a permissão (`PEDIDO_COMP`) e os endpoints de backend
// (`/api/pedido-completo/...`) continuam com o nome antigo por enquanto —
// mudar isso é uma decisão à parte, não pedida ainda.
//
// Fase A (núcleo) do plano faseado em PENDENCIAS.md > "Transações" >
// "Pedido Completo": cabeçalho com o conjunto real de campos de
// frmmanpedfor.frm (Frame2) + grade de itens (resolução rica + kits, ver
// pedido_completo_service.py) + Fechar/Cancelar. O legado não usa abas
// nesta tela (achado estrutural confirmado no rastreio) — segue a exceção
// "compact single-view screens" do CLAUDE.md, mesmo padrão de
// fornecedores.tsx/cilindro-cadastro.tsx.
//
// 2026-07-20: trazidas as funções do Pedido Bar (com exceção da Taxa de
// Serviço) — Faturar/Reabrir/Distribuir/Anexo/Imprimir/Imprimir Item/Pedido
// Totalizado/Pedido Entregue/campo Tipo, mais o ícone único de Ajuda ("Modo
// Didático") — pedido explícito do usuário. Nenhuma dessas regras foi
// reimplementada aqui: `pedido_completo_service.py` reaproveita
// literalmente as mesmas funções de `pedidos_service.py` (mesma tabela
// `pedido_venda`), e o frontend reaproveita `ItemList`/`PedidoHeader`/
// `AjudaPedidoModal`/`DividirPedidoModal` já existentes, só passando
// `tela="PEDIDO_COMP"`/`basePath="/api/pedido-completo"`.
// ============================================================
export default function PedidoGeralScreen() {
  const router = useRouter();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="O Pedido de Venda está disponível apenas no web. Use a pré-venda rápida pelo app."
        testID="pedido-geral-web-only"
      />
    );
  }

  return <PedidoGeralWebScreen router={router} />;
}

function PedidoGeralWebScreen({ router }: { router: ReturnType<typeof useRouter> }) {
  const { can, isMaster, classe, moduleOn } = usePermissions();
  const feedback = useFeedback();
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

  const [pedido, setPedido] = useState<PedidoGeralData | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [clienteResumo, setClienteResumo] = useState<ClienteResumo | null>(null);
  const [loadingResumo, setLoadingResumo] = useState(false);
  const [vinculoProjeto, setVinculoProjeto] = useState<{ codigo: number } | null>(null);

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
  const [horaEntrega, setHoraEntrega] = useState("");
  const [pedidoEntregue, setPedidoEntregue] = useState(false);
  const [entregueSaving, setEntregueSaving] = useState(false);
  const [numPedCliente, setNumPedCliente] = useState("");
  const [infoEntrega, setInfoEntrega] = useState("");
  // Combobox "Tipo" (Mesa/Comanda/Balcão/Entrega, pedido_venda.tipo) —
  // trazido do Pedido Bar 2026-07-20, mesma regra (ver CLAUDE.md > "Campo
  // 'Tipo' do Pedido Bar" — inclusive a exceção de cliente reservado Mesa/
  // Comanda/Balcão, que sempre sobrescreve no backend).
  const [tipoPedido, setTipoPedido] = useState<number | null>(null);
  const [tiposClienteOpts, setTiposClienteOpts] = useState<{ codigo: number; descricao: string }[]>([]);

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
  const [waEnabled, setWaEnabled] = useState<boolean | null>(null);

  const sit = (pedido?.situacao || "A").toUpperCase();
  const isAberto = !editing || sit === "A";
  const isFechado = sit === "F";
  // Regra real (frmmanpedfor.frm): pedido Fechado só permite editar
  // vendedor/forma de pagamento; Aberto permite editar tudo.
  const camposTravados = editing && !isAberto && !isFechado;
  // Pedido filho de uma divisão (Distribuir Pedido) — `num_ped_cliente`
  // numérico aponta pro pedido original, mesmo teste usado no Pedido Bar
  // (`isPedidoFilho`) pra resolver a raiz e travar o campo na tela (não
  // perder o vínculo com a divisão por engano). Trazido junto com Distribuir
  // Pedido, 2026-07-20.
  const isPedidoFilho = /^\d+$/.test((numPedCliente || "").trim());
  const relacionadoDotColor = useCallback(
    (situacaoRel: string) =>
      situacaoRel === "A" ? colors.success : situacaoRel === "PG" ? colors.error : SIT_COLOR[situacaoRel] || colors.muted,
    []
  );

  const it = usePedidoItens({
    conn, editing, pedidoId, isAberto, usuarioCod, funcaoCod, classe, master: isMaster, showToast,
    servicosOn: moduleOn("servicos"), basePath: "/api/pedido-completo", printPorFinalidade: true,
    buscaProdutoSoEnter: true,
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
          const [ra, rf, rfp, rtc] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
            apiGet(c, `/api/forma-pagamento`).catch(() => null),
            apiGet(c, `/api/tipo-cliente`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
          if (rfp?.success) setFormasPag(rfp.items || []);
          if (rtc?.success) setTiposClienteOpts(rtc.items || []);
        } catch {
          // combos ficam vazios
        }
      }

      if (editing && pedidoId && c) {
        try {
          const j = await apiGet(c, `/api/pedido-completo/${pedidoId}`);
          if (j?.success && j.pedido) {
            const p: PedidoGeralData = j.pedido;
            setPedido(p);
            if (p.cliente) setCliente({ codigo: p.cliente, nome: p.cliente_nome, cgc_cpf: p.cliente_cgc, telefone: "" });
            setValidade(p.validade || null);
            setObs(p.obs || "");
            setAreaAtuacao(p.area_atuacao ?? null);
            setFormaPag(p.forma_pag || "");
            setLocalEntrega(p.local_entrega || "");
            setPrevisaoEntrega(p.previsao_entrega || null);
            setHoraEntrega((p.hora_entrega || "").slice(0, 5));
            setPedidoEntregue(!!p.pedido_entregue);
            setNumPedCliente(p.num_ped_cliente || "");
            setInfoEntrega(p.infoentrega || "");
            setTipoPedido(p.tipo ?? null);
            if (p.vendedor != null) setVendedor(p.vendedor);
            if (p.vendedor_nome) setVendedorNome(p.vendedor_nome);
          } else {
            showToast(j?.message || "Erro ao carregar pedido.", "error");
          }
        } catch (e) {
          showToast(`Erro ao carregar: ${e instanceof Error ? e.message : String(e)}`, "error");
        }
        try {
          const jv = await apiGet(c, `/api/projetos-vinculo`, { tipo_doc: "PED", num_doc: pedidoId });
          if (jv?.success && jv.projeto) setVinculoProjeto({ codigo: jv.projeto.codigo });
        } catch {
          // chip é só um atalho de descoberta — falha silenciosa não impede o resto da tela
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
    // Ao carregar um cliente no pedido, o tipo do CLIENTE (cliente_forn)
    // pré-preenche o combobox "Tipo" do PEDIDO — mesma regra do Pedido Bar,
    // continua editável depois. Pedido explícito do usuário, 2026-07-20.
    setTipoPedido(c.tipo_cliente_codigo ?? null);
    if (!editing && conn && typedTerm && COMANDA_TERM_RE.test(typedTerm.trim())) {
      try {
        const j = await apiGet(conn, `/api/pedidos/aberto-por-cliente`, { cliente: c.codigo });
        if (j?.success && j.pedido) {
          router.replace({ pathname: "/pedido-geral", params: { pedido: String(j.pedido) } });
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
        hora_entrega: horaEntrega || null,
        local_entrega: localEntrega,
        infoentrega: infoEntrega,
        num_ped_cliente: numPedCliente,
        tipo: tipoPedido,
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
          () => router.replace({ pathname: "/pedido-geral", params: { pedido: String(j.pedido) } }),
          500
        );
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setSaving(false); }
  };

  // Checkbox "Pedido Entregue" — grava direto no toque, fora do fluxo
  // normal de Gravar (mesmo padrão do Pedido Bar, `FrmManPedBar.frm`
  // Check88_Click). Trazido 2026-07-20.
  const handleToggleEntregue = async () => {
    if (!conn || !editing || !pedidoId) return;
    const novo = !pedidoEntregue;
    setEntregueSaving(true);
    try {
      const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/entregue`, "POST", {
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

  // Faturar Pedido — mesma função/regra do Pedido Bar (gera Comanda, sem
  // NFC-e), reaproveitada via `pedido_completo_service.faturar_pedido_completo`
  // (que só chama `pedidos_service.faturar_pedido` com tela="PEDIDO_COMP").
  // Trazido 2026-07-20.
  const [faturando, setFaturando] = useState(false);
  const handleFaturar = useCallback(async () => {
    if (!conn || !pedidoId) return;
    if (!it.itens.length) { showToast("Inclua pelo menos um produto ou serviço.", "error"); return; }
    setFaturando(true);
    try {
      const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/faturar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "Pedido faturado.", "success");
        setPedido((p) => (p ? { ...p, situacao: "PG", situacao_label: "Faturado" } : p));
        // Reaproveita a impressão pra emitir o pedido logo após faturar,
        // mesmo comportamento do Pedido Bar.
        setReciboOpen(true);
      } else {
        showToast(j?.message || "Não foi possível faturar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFaturando(false); }
  }, [conn, pedidoId, it.itens.length, classe, isMaster, usuarioCod, showToast]);

  // Reabrir Pedido (situação F -> A) — mesma função/regra do Pedido Bar.
  // Trazido 2026-07-20.
  const [reabrindo, setReabrindo] = useState(false);
  const handleReabrir = useCallback(async () => {
    if (!conn || !pedidoId) return;
    setReabrindo(true);
    try {
      const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/reabrir`, "POST", {
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

  // Distribuir Pedido — mesmo DividirPedidoModal do Pedido Bar, só com
  // basePath="/api/pedido-completo". Trazido 2026-07-20.
  const [dividirOpen, setDividirOpen] = useState(false);
  const handleDivided = useCallback(async (novosPedidos: number[]) => {
    if (novosPedidos.length) {
      showToast(`Pedido(s) criado(s): ${novosPedidos.join(", ")}`, "success");
    }
    await it.loadItens();
    if (conn && pedidoId) {
      const j = await apiGet(conn, `/api/pedido-completo/${pedidoId}`);
      if (j?.success && j.pedido) setPedido(j.pedido);
    }
  }, [conn, pedidoId, it, showToast]);

  const [cancelando, setCancelando] = useState(false);
  const handleCancelar = useCallback(() => {
    if (!conn || !pedidoId) return;
    feedback.showConfirm(`Cancelar o Pedido nº ${pedidoId}? Esta ação não pode ser desfeita.`, async () => {
      setCancelando(true);
      try {
        const j = await apiSend(conn, `/api/pedido-completo/${pedidoId}/cancelar`, "POST", {
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

  // Anexos (Gestor de Documentos) — mesmo AnexosPedidoModal do Pedido Bar,
  // grava como anexo do Cliente. Trazido 2026-07-20.
  const [anexosOpen, setAnexosOpen] = useState(false);
  // Preview/impressão do pedido (ReciboPedidoModal) — mesmo componente do
  // Pedido Bar, reaberto automaticamente após Faturar. Trazido 2026-07-20.
  const [reciboOpen, setReciboOpen] = useState(false);
  // Ícone único de Ajuda ("Modo Didático") — mesmo padrão do Pedido Bar.
  const [ajudaOpen, setAjudaOpen] = useState(false);
  // "Dados Principais" — mesmo padrão do Pedido Bar: modal aberto ao tocar
  // no resumo do cliente (telefone/endereço), em vez de um card sempre
  // aberto na tela. Corrigido 2026-07-20, user-directed ("assim como no
  // pedido bar, dados principais fica em um modal ao lado do campo
  // cliente"). Área de Atuação/Validade/Local de Entrega/Informações de
  // Entrega/Data/Observação moraram aqui — Forma de Pagamento/Nº Pedido do
  // Cliente/Tipo/Entrega já subiram pro cabeçalho fixo (ver acima).
  const [dadosOpen, setDadosOpen] = useState(false);

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
  const tipoOptions: SelectOption[] = useMemo(
    () => tiposClienteOpts.map((t) => ({ value: t.codigo, label: t.descricao })),
    [tiposClienteOpts]
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
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="pedido-geral-screen">
      <PedidoHeader
        title={editing ? `Pedido de Venda #${pedidoId}` : "Novo Pedido de Venda"}
        saving={saving}
        onBack={() => router.back()}
        onSave={handleSave}
        canSave={can("PEDIDO_COMP.GRAVAR") && !camposTravados}
        onAnexos={editing && pedidoId && cliente ? () => setAnexosOpen(true) : undefined}
        onHelp={() => setAjudaOpen(true)}
        vinculoProjeto={vinculoProjeto ? { codigo: vinculoProjeto.codigo, onPress: () => router.push({ pathname: "/projeto-form", params: { codigo: String(vinculoProjeto.codigo) } } as never) } : undefined}
        titleExtra={
          <View style={{ width: 110, marginRight: 8 }}>
            <SelectField
              value={vendedor}
              onChange={(v) => setVendedor(v == null ? null : Number(v))}
              options={vendedorOptionsWithGhost}
              placeholder="Selecione"
              disabled={!vendedorCanEdit || camposTravados}
              modalTitle="Selecionar Vendedor"
              variant="onDark"
              hideSub
              compactWeb
              testID="pedido-geral-vendedor"
            />
          </View>
        }
      />

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {/* Cabeçalho do pedido — situação + Forma de Pagamento + Nº
              Pedido do Cliente + Tipo + Entrega, tudo sempre visível (não
              escondido dentro do accordion "Dados Principais"), mesmo
              layout do Pedido Bar. Trazido 2026-07-20, pedido explícito do
              usuário ("falta botões e campos do topo"). */}
          {editing && pedido ? (
            <View style={[styles.card, { gap: spacing.md }]} testID="pedido-geral-topo">
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
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

              <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "flex-end", gap: spacing.md }}>
                <View style={{ minWidth: 200 }}>
                  <Text style={styles.topLabel}>Forma de Pagamento</Text>
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
                    fieldWidth={200}
                    disabled={isFechado ? false : camposTravados}
                    testIDPrefix="pedido-geral-forma-pag"
                  />
                </View>

                <View style={{ minWidth: 160 }}>
                  <Text style={styles.topLabel}>Nº Pedido do Cliente</Text>
                  <TextInput
                    value={numPedCliente}
                    onChangeText={setNumPedCliente}
                    editable={!camposTravados && !isPedidoFilho}
                    placeholder="Referência do cliente"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, { width: 160, height: 36, paddingVertical: 6 }, isPedidoFilho && { color: colors.muted }]}
                    testID="pedido-geral-num-ped-cliente"
                  />
                </View>

                <View style={{ minWidth: 180 }}>
                  <Text style={styles.topLabel}>Tipo</Text>
                  <SelectField
                    value={tipoPedido}
                    onChange={(v) => setTipoPedido(v == null ? null : Number(v))}
                    options={tipoOptions}
                    placeholder="Tipo do pedido"
                    allowClear
                    compactWeb
                    disabled={camposTravados}
                    modalTitle="Selecionar Tipo"
                    testID="pedido-geral-tipo"
                  />
                </View>

                <View style={{ flexShrink: 0 }}>
                  <Text style={styles.topLabel}>Previsão de Entrega</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                    <View style={{ width: 150 }}>
                      <WebDateField
                        value={previsaoEntrega}
                        onChange={setPrevisaoEntrega}
                        type="date"
                        icon="calendar-outline"
                        disabled={camposTravados}
                        testID="pedido-geral-previsao"
                      />
                    </View>
                    <View style={{ width: 120 }}>
                      <WebDateField
                        value={horaEntrega || null}
                        onChange={(v) => setHoraEntrega(v || "")}
                        type="time"
                        icon="time-outline"
                        disabled={camposTravados}
                        testID="pedido-geral-hora-entrega"
                      />
                    </View>
                    {pedidoId && can("PEDIDO_COMP.ENTREGUE") ? (
                      <TouchableOpacity
                        onPress={handleToggleEntregue}
                        disabled={entregueSaving}
                        activeOpacity={0.7}
                        style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: entregueSaving ? 0.6 : 1 }}
                        testID="pedido-geral-entregue-checkbox"
                      >
                        <Ionicons name={pedidoEntregue ? "checkbox" : "square-outline"} size={16} color={colors.brandPrimary} />
                        <Text style={{ fontSize: 11, color: colors.muted }}>Entregue</Text>
                      </TouchableOpacity>
                    ) : null}
                  </View>
                </View>
              </View>
            </View>
          ) : null}

          {/* Pedidos da mesma divisão (Distribuir Pedido) — mesmo bloco do
              Pedido Bar, trazido 2026-07-20 junto com Distribuir. */}
          {editing && pedido && pedido.pedidos_relacionados?.length > 0 ? (
            <View style={styles.card}>
              <Text style={[styles.headerMeta, { textTransform: "uppercase", fontSize: 10, letterSpacing: 0.5, marginBottom: 4 }]}>
                Pedidos da mesma distribuição
              </Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
                {!isPedidoFilho ? (
                  <View style={[pedidoStyles.filhoChip, pedidoStyles.filhoChipOriginal]} testID="pedido-geral-original-self">
                    <View style={[pedidoStyles.filhoDot, { backgroundColor: relacionadoDotColor(sit) }]} />
                    <Text style={[pedidoStyles.filhoText, pedidoStyles.filhoTextOriginal]}>
                      Original nº {pedido.pedido} (este pedido)
                    </Text>
                  </View>
                ) : null}
                {pedido.pedidos_relacionados.map((f) => {
                  const isOriginal = isPedidoFilho && String(f.pedido) === numPedCliente.trim();
                  return (
                    <TouchableOpacity
                      key={f.pedido}
                      onPress={() => router.push({ pathname: "/pedido-geral", params: { pedido: String(f.pedido) } })}
                      style={[pedidoStyles.filhoChip, isOriginal && pedidoStyles.filhoChipOriginal]}
                      testID={`pedido-geral-relacionado-${f.pedido}`}
                    >
                      <View style={[pedidoStyles.filhoDot, { backgroundColor: relacionadoDotColor(f.situacao) }]} />
                      <Text style={[pedidoStyles.filhoText, isOriginal && pedidoStyles.filhoTextOriginal]}>
                        {isOriginal ? "Original" : "Pedido"} nº {f.pedido} · {f.situacao_label} · {formatBRL(f.total)}
                      </Text>
                      <Ionicons name="chevron-forward" size={14} color={isOriginal ? colors.onBrandPrimary : colors.muted} />
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          ) : null}

          <View style={styles.card} testID="pedido-geral-cliente">
            <ClienteSection
              hasCliente={!!cliente}
              clienteResumo={clienteResumo}
              loadingResumo={loadingResumo}
              onOpenSearch={() => {
                if (camposTravados) return;
                setSearchTerm(clienteQuickTerm); setSearchResults([]); setSearchOpen(true);
              }}
              onOpenDados={() => setDadosOpen(true)}
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
                onFechar={handleFechar}
                fechando={fechando}
                onDividir={!isPedidoFilho ? () => setDividirOpen(true) : undefined}
                onFaturar={handleFaturar}
                faturando={faturando}
                isFechado={isFechado}
                onReabrir={handleReabrir}
                reabrindo={reabrindo}
                onCancelar={handleCancelar}
                cancelando={cancelando}
                onImprimir={() => setReciboOpen(true)}
                footerRight={
                  can("PEDIDO_COMP.WHATSAPP") ? (
                    <WhatsappButton
                      conn={conn}
                      documentType="PED"
                      documentId={pedidoId}
                      userId={usuarioCod}
                      companyId={waCompany}
                      pill
                      onStatusChange={setWaEnabled}
                    />
                  ) : undefined
                }
              />
              {waEnabled === false ? (
                <Text style={pedidoStyles.whatsappDisabledHint}>
                  O envio por WhatsApp está desativado em Configurações.
                </Text>
              ) : null}
            </>
          )}

          <View style={{ height: 40 }} />
        </View>
      </ScrollView>

      <Modal visible={dadosOpen} transparent animationType="slide" onRequestClose={() => setDadosOpen(false)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setDadosOpen(false)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Dados Principais</Text>
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
                    <View style={pedidoStyles.resumoRow}>
                      <Ionicons name="call-outline" size={16} color={colors.brandPrimary} />
                      <Text style={[pedidoStyles.resumoText, { fontSize: 14 }]}>{clienteResumo.telefone || "Sem telefone"}</Text>
                    </View>
                    <View style={pedidoStyles.resumoRow}>
                      <Ionicons name="location-outline" size={16} color={colors.brandPrimary} />
                      <Text style={[pedidoStyles.resumoText, { fontSize: 14 }]}>{clienteResumo.endereco || "Sem endereço cadastrado"}</Text>
                    </View>
                    <View style={pedidoStyles.resumoRow}>
                      <Ionicons name="mail-outline" size={16} color={colors.brandPrimary} />
                      <Text style={[pedidoStyles.resumoText, { fontSize: 14 }]}>{clienteResumo.e_mail || "Sem e-mail"}</Text>
                    </View>
                  </View>
                ) : null
              ) : null}

              <Field label="Área de Atuação">
                <SelectField
                  value={areaAtuacao}
                  onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
                  options={areaOptions}
                  placeholder="Selecione a área"
                  allowClear
                  compactWeb
                  disabled={camposTravados}
                  modalTitle="Selecionar Área de Atuação"
                  testID="pedido-geral-area"
                />
              </Field>

              <View style={pedidoStyles.dateRow}>
                <View style={{ flex: 1 }}>
                  <Field label="Data">
                    <View style={pedidoStyles.readonlyBox}>
                      <Ionicons name="calendar-outline" size={16} color={colors.muted} />
                      <Text style={pedidoStyles.readonlyText}>
                        {editing ? formatDateBR(pedido?.data || null) : formatDateBR(todayISO())}
                      </Text>
                    </View>
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Validade">
                    {camposTravados ? (
                      <View style={pedidoStyles.readonlyBox}>
                        <Text style={pedidoStyles.readonlyText}>{formatDateBR(validade)}</Text>
                      </View>
                    ) : (
                      <WebDateField value={validade} onChange={setValidade} testID="pedido-geral-validade" />
                    )}
                  </Field>
                </View>
              </View>

              <Field label="Local de Entrega">
                <TextInput
                  value={localEntrega}
                  onChangeText={setLocalEntrega}
                  editable={!camposTravados}
                  placeholder="Local de entrega"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-geral-local-entrega"
                />
              </Field>

              <Field label="Informações de Entrega">
                <TextInput
                  value={infoEntrega}
                  onChangeText={setInfoEntrega}
                  editable={!camposTravados}
                  placeholder="Instruções de entrega"
                  placeholderTextColor={colors.muted}
                  style={styles.input}
                  testID="pedido-geral-info-entrega"
                />
              </Field>

              <Field label="Observação">
                <TextInput
                  value={obs}
                  onChangeText={setObs}
                  editable={!camposTravados}
                  placeholder="Observação do pedido"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, { minHeight: 100, textAlignVertical: "top", paddingTop: 12 }]}
                  multiline
                  testID="pedido-geral-obs"
                />
              </Field>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <AddItemModal
        it={it}
        tela="PEDIDO_COMP"
        onOpenProdutos={() => {
          it.setAddOpen(false);
          router.push({ pathname: "/produtos", params: { pedido: String(pedidoId), origem: "completo" } });
        }}
      />
      <EditItemModal it={it} tela="PEDIDO_COMP" />
      <AgendarModal it={it} clienteCodigo={cliente?.codigo ?? null} usuarioCod={usuarioCod} />
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
        onPick={(c) => { setCliente(c); setTipoPedido(c.tipo_cliente_codigo ?? null); setSearchOpen(false); }}
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
      <DividirPedidoModal
        visible={dividirOpen}
        onClose={() => setDividirOpen(false)}
        conn={conn}
        pedido={pedidoId || 0}
        itens={it.itens}
        basePath="/api/pedido-completo"
        onDivided={handleDivided}
      />
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
      <ScreenToast toast={toast} testID="pedido-geral-toast" />
      <AjudaPedidoModal
        visible={ajudaOpen}
        onClose={() => setAjudaOpen(false)}
        titulo="Pedido de Venda"
        itens={AJUDA_PEDIDO_GERAL_ITENS}
      />
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
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  headerMeta: { fontSize: 12, color: colors.muted },
  // Rótulo compacto acima dos campos do cabeçalho do pedido (Forma de
  // Pagamento/Nº Pedido do Cliente/Tipo/Entrega) — mesmo estilo do Pedido
  // Bar (`headerMeta` com transform uppercase), trazido 2026-07-20.
  topLabel: { fontSize: 10, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
});
