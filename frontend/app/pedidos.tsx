import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
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
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";
import DateField from "@/src/components/DateField";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import { ClienteRow } from "@/src/components/pedido/types";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import PainelPedidoCard from "@/src/components/pedido/PainelPedidoCard";
import { ORDEM_COLUNAS_TIPO, TIPO_COLOR, normalizaDescricao, tipoClienteKey } from "@/src/components/pedido/painelTipos";
import { loadPedidosFiltros, pedidosFiltrosKey, savePedidosFiltros } from "@/src/utils/storage/pedidosFilters";

const FAB_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 4px 8px rgba(0, 0, 0, 0.25)" }
    : {
        shadowColor: "#000",
        shadowOpacity: 0.25,
        shadowRadius: 8,
        shadowOffset: { width: 0, height: 4 },
        elevation: 8,
      };

type Pedido = {
  pedido: number;
  data: string | null;
  validade: string | null;
  situacao: string;
  situacao_label: string;
  total: number;
  cliente: number | null;
  cliente_nome: string;
  vendedor: number | null;
  vendedor_nome: string;
  hora_aberto: string;
  tipo_cliente_descricao: string;
  localizacao_descricao: string;
  qtd_pessoas: number | null;
  taxa_servico_incluida: boolean;
  tem_itens: boolean;
};

const SITUACOES = [
  { value: "", label: "Todos" },
  { value: "A", label: "Aberto" },
  { value: "F", label: "Fechado" },
  { value: "PG", label: "Faturado" },
  { value: "C", label: "Cancelado" },
];

const SIT_COLOR: Record<string, string> = {
  A: "#1e88e5", F: "#43a047", PG: "#8e24aa", C: "#e53935",
};

function formatBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function formatDate(iso: string | null) {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return d && m && y ? `${d}/${m}/${y}` : iso;
}

// Painel "Pedidos Abertos" do Pedido Bar (FrmManPedBar.frm) — filtros por
// tipo do CLIENTE (cliente.cliente_forn), data-driven: só existem se
// cadastrados em tipo_cliente com essas descrições exatas.
const TIPOS_CLIENTE_BAR = ["MESA", "BALCÃO", "BALCAO", "COMANDA", "ENTREGA", "FIADO"];

function todayISO(): string {
  const d = new Date();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${d.getFullYear()}-${mm}-${dd}`;
}

// Cor de "pedido parado" — aberto há mais de um dia (ver seção "2 colunas de
// cards" em CLAUDE.md/pedido explícito do usuário, 2026-07-17).
const STALE_COLOR = "#e53935";

const ORDENAR_POR_OPCOES: { value: string; label: string }[] = [
  { value: "abertura", label: "Abertura" },
  { value: "tipo", label: "Tipo" },
  { value: "cliente", label: "Cliente" },
];

export default function PedidosScreen() {
  const router = useRouter();
  const { can, isManagerFuncao, moduleOn, isMaster, classe, usuarioCodigo } = usePermissions();
  const feedback = useFeedback();
  // `situacao` na URL (ex.: vindo do botão "Voltar" do Pedido, que sempre
  // quer cair direto na lista de Abertos) sobrescreve o default — pedido
  // explícito do usuário, 2026-07-17.
  const params = useLocalSearchParams<{ situacao?: string }>();
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  const [situacao, setSituacao] = useState(params.situacao || "A");
  const [vendedor, setVendedor] = useState<string | number | null>(null);
  const [vendedorOpts, setVendedorOpts] = useState<SelectOption[]>([]);
  const [ownVendedor, setOwnVendedor] = useState<number | null>(null);
  // Sempre nasce com o filtro de data do dia atual — não é restaurado do
  // último filtro salvo (diferente de situação/tipos/vendedor, que
  // continuam lembrados por empresa+banco) — pedido explícito do usuário,
  // 2026-07-18: reabrir a tela num dia novo não deve arrastar um filtro de
  // data de um dia anterior. Pedido tipo FIADO ainda Aberto tem exceção a
  // esse filtro no backend (`_list_pedidos_sync`), pra nunca sumir da
  // lista por causa dele.
  const [dataIni, setDataIni] = useState<string | null>(() => todayISO());
  const [dataFim, setDataFim] = useState<string | null>(() => todayISO());
  const [showFilters, setShowFilters] = useState(false);
  const [items, setItems] = useState<Pedido[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);
  // Persistência da última seleção de filtros (por empresa+banco) — ver
  // src/utils/storage/pedidosFilters.ts. `filtrosRestauradosRef` evita que
  // o efeito de salvar dispare com os valores padrão antes da restauração
  // terminar, sobrescrevendo o que estava salvo.
  const storageKeyRef = useRef<string | null>(null);
  const filtrosRestauradosRef = useRef(false);

  // Filtros do painel "Pedidos Abertos" (só no segmento Bar)
  const [tiposClienteOpts, setTiposClienteOpts] = useState<{ codigo: number; label: string }[]>([]);
  const [tiposClienteSel, setTiposClienteSel] = useState<number[]>([]);
  const [dataEntrega, setDataEntrega] = useState<string | null>(null);
  const [ordenarPor, setOrdenarPor] = useState<string | null>(null);

  // Painel de Pedidos (ações rápidas direto do card — adicionar item,
  // faturar, imprimir, novo pedido por coluna) — pedido explícito do
  // usuário, 2026-07-17.
  const [funcaoCod, setFuncaoCod] = useState<number>(3); // 1=gerente,2=supervisor,3=vendedor
  const [formasPagamento, setFormasPagamento] = useState<{ codigo: string; descricao: string }[]>([]);
  const [nowMs, setNowMs] = useState(() => Date.now());
  const usuarioCod = isMaster ? -2 : (usuarioCodigo ?? -2);
  // Largura real da linha de chips (Situação + Tipo) — medida via
  // `onContentSizeChange` do ScrollView horizontal — aplicada tanto no
  // campo de busca quanto no acordeon inteiro, pra nenhum dos dois ocupar
  // a tela toda além do necessário. Pedido explícito do usuário,
  // 2026-07-17.
  const [chipsRowWidth, setChipsRowWidth] = useState<number | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const own = (s?.funcionario as { codigo_int?: number } | null)?.codigo_int;
      setOwnVendedor(own ?? null);
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = parseInt(String(cf || ""), 10);
      setFuncaoCod(Number.isFinite(fc) && fc > 0 ? fc : 3);

      // Restaura a última seleção de filtros salva pra essa empresa+banco —
      // só uma vez, e só quando não veio uma `situacao` explícita na URL
      // (ex.: botão "Voltar" do Pedido, que sempre quer cair em Abertos).
      // `saved === null` (nunca salvou antes, primeira visita) é diferente
      // de "salvou com tipos vazios" (usuário limpou o filtro de propósito)
      // — só o primeiro caso aciona o default abaixo.
      let saved: Awaited<ReturnType<typeof loadPedidosFiltros>> = null;
      if (c && !filtrosRestauradosRef.current) {
        filtrosRestauradosRef.current = true;
        const key = pedidosFiltrosKey(c.empresa, c.banco);
        storageKeyRef.current = key;
        saved = await loadPedidosFiltros(key);
        if (saved) {
          if (!params.situacao) setSituacao(saved.situacao || "A");
          if (saved.vendedor != null) setVendedor(saved.vendedor);
          // dataIni/dataFim NÃO são restaurados do filtro salvo — sempre
          // ficam no default "hoje" do useState acima, mesmo em visitas
          // seguintes. Pedido explícito do usuário, 2026-07-18.
          setTiposClienteSel(saved.tiposClienteSel || []);
          setDataEntrega(saved.dataEntrega ?? null);
          setOrdenarPor(saved.ordenarPor ?? null);
        }
      }
      // Gerentes (cod_funcao 01/02) e KONTACTO podem filtrar por vendedor.
      if (c && isManagerFuncao) {
        try {
          const base = c.api.replace(/\/+$/, "");
          const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const j = await fetch(`${base}/api/funcionarios?${qs}`).then((r) => r.json());
          const fs: { codigo: number; nome: string; nome_guerra: string }[] = Array.isArray(j?.items) ? j.items : [];
          setVendedorOpts(
            fs.map((f) => ({
              value: f.codigo,
              label: f.nome || f.nome_guerra || `#${f.codigo}`,
              sub: f.nome_guerra && f.nome_guerra !== f.nome ? `@${f.nome_guerra}` : undefined,
            }))
          );
        } catch {
          // silencioso
        }
      }
      // Painel "Pedidos Abertos" (Bar) — Mesa/Balcão/Comanda/Entrega são
      // linhas específicas em tipo_cliente; só aparecem se cadastradas
      // (mesmo comportamento data-driven do legado, CataTipoCliente()).
      if (c && moduleOn("Bar")) {
        try {
          const base = c.api.replace(/\/+$/, "");
          const qs = `servidor=${encodeURIComponent(c.servidor)}&banco=${encodeURIComponent(c.banco)}`;
          const j = await fetch(`${base}/api/tipo-cliente?${qs}`).then((r) => r.json());
          const tipos: { codigo: number; descricao: string }[] = Array.isArray(j?.items) ? j.items : [];
          const opts = tipos
            .filter((t) => TIPOS_CLIENTE_BAR.includes(normalizaDescricao(t.descricao || "")))
            .map((t) => ({ codigo: t.codigo, label: (t.descricao || "").trim() }));
          setTiposClienteOpts(opts);
          // Primeira visita (nunca salvou filtro antes) — painel de colunas
          // já nasce com todos os tipos marcados (Balcão/Comanda/Entrega/
          // Mesa), em vez de exigir seleção manual toda vez. Pedido
          // explícito do usuário, 2026-07-17. Visitas seguintes respeitam a
          // última seleção salva (inclusive vazia, se o usuário limpou de
          // propósito).
          if (saved === null) setTiposClienteSel(opts.map((t) => t.codigo));
        } catch {
          // silencioso
        }
        // Formas de pagamento (Painel de Pedidos > Faturar rápido).
        try {
          const j = await apiGet(c, "/api/forma-pagamento");
          if (j?.success && Array.isArray(j.items)) setFormasPagamento(j.items);
        } catch {
          // silencioso
        }
      }
    })();
  }, [isManagerFuncao, moduleOn]);

  // "Tempo aberto" do Painel de Pedidos — um relógio compartilhado por
  // todos os cards em vez de um `setInterval` por card (poderiam ser
  // dezenas simultâneos). 10s é granularidade suficiente pra um contador
  // que só precisa "parecer" vivo.
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 10000);
    return () => clearInterval(t);
  }, []);

  const effVendedor = isManagerFuncao
    ? vendedor == null
      ? "all"
      : String(vendedor)
    : ownVendedor != null
    ? String(ownVendedor)
    : "-1";

  const load = useCallback(
    async (
      term: string, sit: string, vend: string, di: string | null, df: string | null,
      pg: number, append: boolean,
      tiposCliente: number[], dataEntregaFiltro: string | null, ordenar: string | null,
    ) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        // Visão em colunas por tipo (Mesa/Balcão/Comanda/Entrega, segmento
        // Bar) busca tudo de uma vez em vez de paginar — as colunas
        // precisam do conjunto completo pra totalizar/ordenar corretamente.
        // Vale pra qualquer Situação (não só Aberto), mesma regra repetida
        // pra Fechado/Faturado/Cancelado/Todos — pedido explícito do
        // usuário, 2026-07-17.
        const isColunas = moduleOn("Bar");
        const r = await fetch(`${base}/api/pedidos`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            servidor: conn.servidor, banco: conn.banco,
            search: term, situacao: sit, vendedor: vend,
            data_ini: di, data_fim: df,
            page: pg, size: isColunas ? 200 : 20,
            tipos_cliente: tiposCliente.length ? tiposCliente : null,
            data_entrega: dataEntregaFiltro,
            ordenar_por: ordenar,
          }),
          signal: ac.signal,
        });
        const j = await r.json();
        if (!j?.success) {
          feedback.showError(j?.message || "Falha na consulta.");
          if (!append) setItems([]);
        } else {
          setItems((prev) => (append ? [...prev, ...j.items] : j.items));
          setTotal(j.total || 0);
        }
      } catch (e: unknown) {
        if ((e as { name?: string })?.name !== "AbortError") {
          feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
        }
      } finally {
        if (aborter.current === ac) {
          setLoading(false);
          aborter.current = null;
        }
      }
    },
    [conn, feedback, moduleOn]
  );

  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => {
      setPage(1);
      load(search, situacao, effVendedor, dataIni, dataFim, 1, false, tiposClienteSel, dataEntrega, ordenarPor);
    }, 350);
    return () => clearTimeout(t);
  }, [search, situacao, effVendedor, dataIni, dataFim, conn, load, tiposClienteSel, dataEntrega, ordenarPor]);

  useFocusEffect(useCallback(() => {
    if (conn) load(search, situacao, effVendedor, dataIni, dataFim, 1, false, tiposClienteSel, dataEntrega, ordenarPor);
  }, [conn, search, situacao, effVendedor, dataIni, dataFim, load, tiposClienteSel, dataEntrega, ordenarPor]));

  // Grava a última seleção de filtros (não o texto de busca, que é uma
  // consulta pontual, não um filtro persistente) — pedido explícito do
  // usuário, 2026-07-17. Só grava depois que a restauração inicial já
  // rodou, senão os valores padrão sobrescreveriam o que estava salvo.
  useEffect(() => {
    if (!filtrosRestauradosRef.current || !storageKeyRef.current) return;
    savePedidosFiltros(storageKeyRef.current, {
      situacao, vendedor, dataIni, dataFim, tiposClienteSel, dataEntrega, ordenarPor,
    });
  }, [situacao, vendedor, dataIni, dataFim, tiposClienteSel, dataEntrega, ordenarPor]);

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, situacao, effVendedor, dataIni, dataFim, next, true, tiposClienteSel, dataEntrega, ordenarPor);
  };

  // Painel de Pedidos — recarrega a página atual depois de uma ação rápida
  // no card (item adicionado, faturado, qtd. de pessoas alterada, novo
  // pedido criado por coluna).
  const refreshList = useCallback(() => {
    load(search, situacao, effVendedor, dataIni, dataFim, 1, false, tiposClienteSel, dataEntrega, ordenarPor);
  }, [load, search, situacao, effVendedor, dataIni, dataFim, tiposClienteSel, dataEntrega, ordenarPor]);

  // "Novo Pedido" por coluna — botão dedicado abre a busca de cliente pra
  // criar o pedido direto, sem passar pela tela cheia. `novoPedidoCodigoTipo`
  // só decide QUAL coluna abriu o modal (visibilidade) — a busca em si NÃO
  // filtra por tipo (correção 2026-07-18, user-directed: filtrar escondia
  // clientes de outros tipos que já existiam, ex. buscar "MESA" estando na
  // coluna Comanda voltava "Nenhum cliente encontrado" mesmo com várias
  // "MESA N" cadastradas, arriscando cadastro duplicado). A busca sempre
  // traz todos os tipos (com `tipo_cliente_descricao` mostrado em cada
  // resultado, ver ClientSearchModal.tsx) — quem decide em qual coluna o
  // pedido aparece é a lista, depois de criado, não a busca.
  const [novoPedidoCodigoTipo, setNovoPedidoCodigoTipo] = useState<number | null>(null);
  const [novoPedidoTerm, setNovoPedidoTerm] = useState("");
  const [novoPedidoResults, setNovoPedidoResults] = useState<ClienteRow[]>([]);
  const [novoPedidoLoading, setNovoPedidoLoading] = useState(false);
  const [novoPedidoCreating, setNovoPedidoCreating] = useState(false);

  useEffect(() => {
    if (novoPedidoCodigoTipo == null || !conn || !novoPedidoTerm.trim()) {
      setNovoPedidoResults([]);
      return;
    }
    const t = setTimeout(async () => {
      setNovoPedidoLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term: novoPedidoTerm });
        setNovoPedidoResults(j?.items || []);
      } catch {
        setNovoPedidoResults([]);
      } finally {
        setNovoPedidoLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [novoPedidoTerm, novoPedidoCodigoTipo, conn]);

  const handleCriarPedido = async (c: ClienteRow) => {
    if (!conn || novoPedidoCreating) return;
    setNovoPedidoCreating(true);
    try {
      const j = await apiSend(conn, "/api/pedidos/create", "POST", {
        cliente: c.codigo, vendedor: ownVendedor || usuarioCod,
        // Tipo do PEDIDO = coluna que abriu o "Novo Pedido" — mesmo que o
        // cliente seja de outro tipo, o pedido nasce nessa coluna (backend
        // só sobrescreve se o cliente for Mesa/Comanda/Balcão reservado,
        // que sempre trava no próprio tipo). Pedido explícito do usuário,
        // 2026-07-18.
        tipo: novoPedidoCodigoTipo,
        usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (!j?.success) {
        feedback.showError(j?.message || "Falha ao criar pedido.");
      } else {
        feedback.showSuccess(`Pedido ${j.pedido} criado para ${c.nome}.`);
        setNovoPedidoCodigoTipo(null);
        refreshList();
      }
    } catch (e) {
      feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setNovoPedidoCreating(false);
    }
  };

  const toggleTipoCliente = (codigo: number) => {
    setTiposClienteSel((prev) => (prev.includes(codigo) ? prev.filter((c) => c !== codigo) : [...prev, codigo]));
  };

  const hasBarFilter = tiposClienteSel.length > 0 || !!dataEntrega || !!ordenarPor;

  const clearDateFilters = () => {
    setDataIni(null);
    setDataFim(null);
  };

  const hasDateFilter = !!(dataIni || dataFim);

  // Quem tem a pré-venda rápida (PEDIDO) continua indo pro formulário
  // rápido, sem mudança de comportamento — quem só tem PEDIDO_COMP abre o
  // Pedido Completo (web). Ver CLAUDE.md > "Transações Screens Strategy".
  // Compartilhado entre o card padrão (FlatList) e o card compacto das "2
  // colunas" abaixo, pra não duplicar a regra de navegação.
  const abrirPedido = useCallback((item: Pedido) => {
    if (can("PEDIDO.ABRIR")) {
      router.push({ pathname: "/pedido-form", params: { pedido: String(item.pedido) } });
    } else if (can("PEDIDO_COMP.ABRIR")) {
      router.push({ pathname: "/pedido-completo", params: { pedido: String(item.pedido) } });
    }
  }, [can, router]);

  // Visão "Pedidos" em colunas (totalizadores + colunas por tipo) — vale
  // pra qualquer Situação (Aberto/Fechado/Faturado/Cancelado/Todos) no
  // segmento Bar, não só Aberto — mesma regra repetida pra todas as
  // situações, pedido explícito do usuário, 2026-07-17.
  const barColunasView = moduleOn("Bar");

  // "Divida a lista no total de tipo selecionado" — o nº de colunas segue o
  // nº de tipos marcados no filtro (0 selecionado = sem divisão, lista
  // única; 1 = 1 coluna; 2 = 2 colunas; etc.), não mais um par fixo Mesa/
  // Outros. Pedido explícito do usuário, 2026-07-17.
  const colunasAtivas = barColunasView && tiposClienteSel.length > 0;

  const isStale = useCallback((item: Pedido) => item.situacao === "A" && !!item.data && item.data < todayISO(), []);

  // Ordena estável: não-parados primeiro, parados (>1 dia aberto) no fim —
  // `Array.prototype.sort` é estável (spec ES2019+), então preserva a ordem
  // relativa já vinda do backend dentro de cada grupo.
  const partitioned = useMemo(() => {
    if (!colunasAtivas) return null;
    const ordenar = (arr: Pedido[]) => [...arr].sort((a, b) => Number(isStale(a)) - Number(isStale(b)));
    // Uma coluna por tipo selecionado, sempre na ordem fixa
    // ORDEM_COLUNAS_TIPO (Mesa, Comanda, Balcão, Entrega) — não na ordem em
    // que os tipos foram marcados no filtro. Pedido explícito do usuário,
    // 2026-07-17.
    return tiposClienteOpts
      .filter((t) => tiposClienteSel.includes(t.codigo))
      .map((t) => {
        const key = tipoClienteKey(t.label);
        return {
          codigo: t.codigo,
          label: t.label,
          key,
          itens: ordenar(items.filter((item) => tipoClienteKey(item.tipo_cliente_descricao) === key)),
        };
      })
      .sort((a, b) => {
        const ia = ORDEM_COLUNAS_TIPO.indexOf(a.key);
        const ib = ORDEM_COLUNAS_TIPO.indexOf(b.key);
        return (ia === -1 ? ORDEM_COLUNAS_TIPO.length : ia) - (ib === -1 ? ORDEM_COLUNAS_TIPO.length : ib);
      });
  }, [colunasAtivas, items, isStale, tiposClienteOpts, tiposClienteSel]);

  // Totalizadores por tipo de cliente (Mesa/Balcão/Comanda/Entrega) — qtd. e
  // valor de cada tipo, mais o valor total somado dos tipos — sempre
  // relativos à situação atualmente filtrada, independente de quais tipos
  // estão selecionados no filtro. Pedido explícito do usuário, 2026-07-17
  // ("totalizar no topo da lista os pedidos por situação nos seus tipos" +
  // "totalizar valor e qtd de cada tipo + valor total dos tipos").
  const totaisPorTipo = useMemo(() => {
    const porTipo: Record<string, { qtd: number; valor: number }> = {
      MESA: { qtd: 0, valor: 0 }, "BALCÃO": { qtd: 0, valor: 0 },
      COMANDA: { qtd: 0, valor: 0 }, ENTREGA: { qtd: 0, valor: 0 },
      FIADO: { qtd: 0, valor: 0 },
    };
    for (const item of items) {
      const k = tipoClienteKey(item.tipo_cliente_descricao);
      if (k in porTipo) {
        porTipo[k].qtd += 1;
        porTipo[k].valor += item.total;
      }
    }
    const totalGeral = ORDEM_COLUNAS_TIPO.reduce((acc, k) => acc + porTipo[k].valor, 0);
    return { porTipo, totalGeral };
  }, [items]);

  const listHeader = (
    <View style={styles.headerBlock}>
      {/* Busca + Situação + tipo de cliente (Mesa/Balcão/Comanda/Entrega),
          tudo num acordeon no topo da lista — pedido explícito do usuário,
          2026-07-17. Aberto por padrão (são os filtros mais usados), mas
          recolhível pra dar mais espaço vertical à lista/colunas. */}
      <AccordionSection
        title="Buscar e Filtrar"
        defaultExpanded
        testID="pedidos-filtros-topo"
        style={chipsRowWidth ? { alignSelf: "flex-start", width: chipsRowWidth, maxWidth: "100%" } : undefined}
      >
        <View style={[styles.searchWrap, chipsRowWidth ? { width: chipsRowWidth, maxWidth: "100%" } : null]}>
          <Ionicons name="search" size={16} color={colors.muted} />
          <TextInput
            value={search}
            onChangeText={setSearch}
            placeholder="Buscar por cliente, CPF, telefone ou nº do pedido…"
            placeholderTextColor={colors.muted}
            style={styles.searchInput}
            testID="pedidos-search-input"
          />
        </View>

        <ScrollView
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.chipsScroll}
          contentContainerStyle={styles.chipsRow}
          keyboardShouldPersistTaps="handled"
          onContentSizeChange={(w) => setChipsRowWidth(w)}
        >
          {SITUACOES.map((s) => {
            const sel = situacao === s.value;
            return (
              <Pressable
                key={s.value || "all"}
                onPress={() => setSituacao(s.value)}
                style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.7 }]}
                testID={`pedidos-chip-${s.value || "all"}`}
              >
                <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>{s.label}</Text>
              </Pressable>
            );
          })}

          {/* Filtro por tipo de cliente (Mesa/Balcão/Comanda/Entrega, painel
              "Pedidos Abertos" do FrmManPedBar.frm) — ao lado da situação,
              dentro do mesmo acordeon. Pedido explícito do usuário,
              2026-07-17. */}
          {moduleOn("Bar") && tiposClienteOpts.length > 0 ? (
            <>
              <View style={styles.chipsDivider} />
              {tiposClienteOpts.map((t) => {
                const sel = tiposClienteSel.includes(t.codigo);
                return (
                  <Pressable
                    key={`tipo-${t.codigo}`}
                    onPress={() => toggleTipoCliente(t.codigo)}
                    style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.7 }]}
                    testID={`pedidos-tipo-cliente-inline-${t.codigo}`}
                  >
                    <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>{t.label}</Text>
                  </Pressable>
                );
              })}
            </>
          ) : null}
        </ScrollView>
      </AccordionSection>

      {barColunasView ? (
        <View testID="pedidos-totais-tipo">
          <View style={styles.totaisRow}>
            {ORDEM_COLUNAS_TIPO.map((k) => (
              <View key={k} style={styles.totalPill} testID={`pedidos-total-${k}`}>
                <Text style={styles.totalPillLabel}>{k}</Text>
                <Text style={styles.totalPillValue}>{totaisPorTipo.porTipo[k].qtd}</Text>
                <Text style={styles.totalPillMoney}>{formatBRL(totaisPorTipo.porTipo[k].valor)}</Text>
              </View>
            ))}
            <View style={[styles.totalPill, styles.totalPillGeral]} testID="pedidos-total-geral">
              <Text style={[styles.totalPillLabel, styles.totalPillLabelGeral]}>Total</Text>
              <Text style={[styles.totalPillMoney, styles.totalPillMoneyGeral]}>{formatBRL(totaisPorTipo.totalGeral)}</Text>
            </View>
          </View>
        </View>
      ) : null}

      {showFilters ? (
        <View style={styles.filterCard} testID="pedidos-filter-card">
          <View style={styles.filterHeader}>
            <Text style={styles.filterTitle}>Filtrar por data</Text>
            {hasDateFilter ? (
              <Pressable
                onPress={clearDateFilters}
                style={({ pressed }) => [styles.clearBtn, pressed && { opacity: 0.7 }]}
                testID="pedidos-clear-dates"
                hitSlop={6}
              >
                <Ionicons name="close-circle-outline" size={14} color={colors.brandPrimary} />
                <Text style={styles.clearBtnText}>Limpar</Text>
              </Pressable>
            ) : null}
          </View>
          <View style={styles.filterRow}>
            <DateField
              label="De"
              value={dataIni}
              onChange={setDataIni}
              testID="pedidos-data-ini"
              maximumDate={dataFim ? new Date(dataFim) : undefined}
            />
            <DateField
              label="Até"
              value={dataFim}
              onChange={setDataFim}
              testID="pedidos-data-fim"
              minimumDate={dataIni ? new Date(dataIni) : undefined}
            />
          </View>
          {isManagerFuncao ? (
            <View style={{ marginTop: spacing.md }} testID="pedidos-vendedor-filter">
              <SelectField
                label="Vendedor"
                value={vendedor}
                onChange={setVendedor}
                options={vendedorOpts}
                placeholder="Todos os vendedores"
                modalTitle="Selecionar vendedor"
                allowClear
                testID="pedidos-vendedor-select"
              />
            </View>
          ) : null}

          {/* Painel "Pedidos Abertos" (FrmManPedBar.frm) — só no segmento
              Bar. O filtro por tipo (Mesa/Balcão/Comanda/Entrega) mudou pra
              ficar ao lado da situação, sempre visível (ver chips acima) —
              aqui ficam só "Ordenar por"/"Data de Entrega", que continuam
              dependendo de "Filtros" aberto. */}
          {moduleOn("Bar") ? (
            <View style={{ marginTop: spacing.md }} testID="pedidos-bar-filters">
              <View style={styles.filterHeader}>
                <Text style={styles.filterTitle}>Pedidos Abertos</Text>
                {hasBarFilter ? (
                  <Pressable
                    onPress={() => { setTiposClienteSel([]); setDataEntrega(null); setOrdenarPor(null); }}
                    style={({ pressed }) => [styles.clearBtn, pressed && { opacity: 0.7 }]}
                    testID="pedidos-clear-bar-filters"
                    hitSlop={6}
                  >
                    <Ionicons name="close-circle-outline" size={14} color={colors.brandPrimary} />
                    <Text style={styles.clearBtnText}>Limpar</Text>
                  </Pressable>
                ) : null}
              </View>

              <Text style={[styles.filterTitle, { marginTop: spacing.sm, marginBottom: 4 }]}>Ordenar por</Text>
              <View style={styles.chipsRowWrap}>
                {ORDENAR_POR_OPCOES.map((o) => {
                  const sel = ordenarPor === o.value;
                  return (
                    <Pressable
                      key={o.value}
                      onPress={() => setOrdenarPor(sel ? null : o.value)}
                      style={({ pressed }) => [styles.chip, sel && styles.chipSel, pressed && { opacity: 0.7 }]}
                      testID={`pedidos-ordenar-${o.value}`}
                    >
                      <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>{o.label}</Text>
                    </Pressable>
                  );
                })}
              </View>

              <View style={{ marginTop: spacing.sm }}>
                <DateField
                  label="Data de Entrega em"
                  value={dataEntrega}
                  onChange={setDataEntrega}
                  testID="pedidos-data-entrega"
                />
              </View>
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="pedidos-screen">
      {!(can("PEDIDO.ABRIR") || can("PEDIDO_COMP.ABRIR")) ? (
        <LockedView testID="pedidos-locked" />
      ) : (
      <>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="pedidos-back"
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>Pedidos ({total})</Text>
        <Pressable
          onPress={() => setShowFilters((v) => !v)}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
          testID="pedidos-toggle-filters"
        >
          <Ionicons
            name={showFilters ? "options" : "options-outline"}
            size={22}
            color={colors.onBrandPrimary}
          />
          {hasDateFilter || hasBarFilter ? <View style={styles.filterDot} /> : null}
        </Pressable>
      </View>

      {colunasAtivas && partitioned ? (
        // Uma coluna por tipo selecionado no filtro (BALCÃO/COMANDA/
        // ENTREGA/MESA) — 2 tipos marcados = 2 colunas, e assim por diante.
        // Busca tudo de uma vez (ver `isColunas` em `load`), então aqui é
        // rolagem simples, sem paginação incremental. Pedido explícito do
        // usuário, 2026-07-17.
        <ScrollView
          style={styles.list}
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 100, paddingTop: spacing.sm }}
          testID="pedidos-colunas-scroll"
        >
          {listHeader}
          {loading && items.length === 0 ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : (
            <View style={styles.colsRow}>
              {partitioned.map((col) => (
                <View key={col.codigo} style={styles.col} testID={`pedidos-col-${col.codigo}`}>
                  <View style={[styles.colHeader, { borderBottomColor: TIPO_COLOR[col.key] || colors.border }]}>
                    <Text style={[styles.colTitle, { color: TIPO_COLOR[col.key] || colors.muted }]}>
                      {col.label.toUpperCase()} ({col.itens.length})
                    </Text>
                    {can("PEDIDO.GRAVAR") ? (
                      <Pressable
                        onPress={() => { setNovoPedidoTerm(""); setNovoPedidoResults([]); setNovoPedidoCodigoTipo(col.codigo); }}
                        hitSlop={6}
                        testID={`pedidos-col-novo-${col.codigo}`}
                      >
                        <Ionicons name="add-circle" size={20} color={TIPO_COLOR[col.key] || colors.brandPrimary} />
                      </Pressable>
                    ) : null}
                  </View>
                  {col.itens.length === 0 ? (
                    <Text style={styles.emptyCol}>Nenhum pedido.</Text>
                  ) : (
                    col.itens.map((item) => (
                      <PainelPedidoCard
                        key={item.pedido}
                        item={item}
                        tipoKey={col.key}
                        stale={isStale(item)}
                        nowMs={nowMs}
                        conn={conn as Connection}
                        usuarioCod={usuarioCod}
                        funcaoCod={funcaoCod}
                        classe={classe}
                        isMaster={isMaster}
                        canAddItem={can("PEDIDO.ADD_ITEM")}
                        canFaturar={can("PEDIDO.FATURAR")}
                        canImprimir={can("PEDIDO.IMPRIMIR")}
                        canTaxaServico={can("PEDIDO.TX_SERVICO")}
                        formasPagamento={formasPagamento}
                        onAbrir={() => abrirPedido(item)}
                        onChanged={refreshList}
                      />
                    ))
                  )}
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      ) : (
        <FlatList
          data={items}
          style={styles.list}
          keyExtractor={(p) => String(p.pedido)}
          keyboardShouldPersistTaps="handled"
          ListHeaderComponent={listHeader}
          contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: 100, paddingTop: spacing.sm }}
          ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
          onEndReached={loadMore}
          onEndReachedThreshold={0.6}
          ListEmptyComponent={!loading ? <Text style={styles.empty}>Nenhum pedido.</Text> : null}
          ListFooterComponent={loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} /> : null}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => abrirPedido(item)}
              style={({ pressed }) => [styles.card, pressed && { opacity: 0.7 }]}
              testID={`pedido-${item.pedido}`}
            >
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8 }}>
                  <Text style={styles.cardTitle}>#{item.pedido}</Text>
                  <View style={[styles.sitTag, { backgroundColor: (SIT_COLOR[item.situacao] || colors.muted) + "22" }]}>
                    <Text style={[styles.sitTagText, { color: SIT_COLOR[item.situacao] || colors.muted }]}>{item.situacao_label}</Text>
                  </View>
                </View>
                <Text style={styles.cardCliente} numberOfLines={1}>{item.cliente_nome || "(sem cliente)"}</Text>
                <Text style={styles.cardMeta}>
                  {formatDate(item.data)} · {item.vendedor_nome || "—"}
                </Text>
              </View>
              <Text style={styles.cardValor}>{formatBRL(item.total)}</Text>
            </Pressable>
          )}
        />
      )}

      {can("PEDIDO.GRAVAR") || can("PEDIDO_COMP.GRAVAR") ? (
        <Pressable
          onPress={() => router.push(can("PEDIDO.GRAVAR") ? "/pedido-form" : "/pedido-completo")}
          style={({ pressed }) => [styles.fab, FAB_SHADOW_STYLE, pressed && { opacity: 0.85 }]}
          hitSlop={8}
          testID="pedidos-fab-new"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}

      <ClientSearchModal
        visible={novoPedidoCodigoTipo != null}
        onClose={() => setNovoPedidoCodigoTipo(null)}
        term={novoPedidoTerm}
        setTerm={setNovoPedidoTerm}
        loading={novoPedidoLoading || novoPedidoCreating}
        results={novoPedidoResults}
        onPick={handleCriarPedido}
        onCreate={() => {
          // Mesa/Comanda/Balcão nova, ainda não cadastrada como cliente —
          // caso raro (configuração inicial). `criar_pedido=1` avisa
          // cliente-form.tsx que, ao Gravar, deve criar o pedido pro
          // cliente recém-cadastrado direto (em vez de só voltar) e
          // retornar pro painel — pedido explícito do usuário, 2026-07-18
          // ("ao clicar em gravar sai da tela de cliente e cria o
          // pedido").
          setNovoPedidoCodigoTipo(null);
          router.push({
            pathname: "/cliente-form",
            params: { ...clienteSearchParams(novoPedidoTerm), criar_pedido: "1" },
          });
        }}
      />
      </>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm,
  },
  backBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  filterDot: {
    position: "absolute", top: 8, right: 8,
    width: 8, height: 8, borderRadius: 4, backgroundColor: "#ff5252",
  },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  headerBlock: { marginBottom: spacing.xs },
  chipsRow: {
    gap: 8,
    paddingVertical: spacing.md,
  },
  chipsScroll: { flexGrow: 0, flexShrink: 0 },
  list: { flex: 1 },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: 8,
    borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, height: 36, justifyContent: "center", flexShrink: 0,
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  filterCard: {
    marginHorizontal: spacing.lg,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
    marginBottom: spacing.sm,
  },
  filterHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    marginBottom: spacing.sm,
  },
  filterTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  clearBtn: { flexDirection: "row", alignItems: "center", gap: 4 },
  clearBtnText: { fontSize: 12, color: colors.brandPrimary, fontWeight: "500" },
  filterRow: { flexDirection: "row", gap: 8 },
  chipsRowWrap: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  chipsDivider: { width: 1, height: 22, backgroundColor: colors.border, alignSelf: "center", marginHorizontal: 2 },
  // Totalizadores por tipo (Balcão/Comanda/Entrega/Mesa), topo da lista —
  // só na visão "2 colunas" (Aberto + segmento Bar).
  totaisRow: {
    flexDirection: "row", flexWrap: "wrap", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginBottom: spacing.sm,
  },
  totalPill: {
    flexDirection: "row", alignItems: "center", gap: 6,
    paddingHorizontal: spacing.md, paddingVertical: 6,
    borderRadius: radius.pill, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  totalPillLabel: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  totalPillValue: { fontSize: 13, color: colors.onSurface, fontWeight: "700" },
  totalPillMoney: { fontSize: 12, color: colors.brandPrimary, fontWeight: "700" },
  totalPillGeral: { backgroundColor: colors.brandTertiary, borderColor: colors.brandPrimary },
  totalPillLabelGeral: { color: colors.onSurface, fontWeight: "700" },
  totalPillMoneyGeral: { fontSize: 13 },
  // Layout "2 colunas" (Mesa | Outros)
  colsRow: { flexDirection: "row", gap: spacing.sm },
  col: { flex: 1, gap: 8, minWidth: 0 },
  colHeader: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    borderBottomWidth: 2, paddingBottom: 4, marginBottom: 2,
  },
  colTitle: { fontSize: 12, fontWeight: "700", color: colors.muted, letterSpacing: 0.3 },
  compactCard: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 8, borderWidth: 1, borderColor: colors.border,
  },
  compactLine1: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  compactLine2: { fontSize: 12, color: colors.muted, marginTop: 1 },
  emptyCol: { fontSize: 12, color: colors.muted, fontStyle: "italic" },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  cardTitle: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  cardCliente: { fontSize: 14, color: colors.onSurface, marginTop: 4 },
  cardMeta: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardValor: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  sitTag: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 4 },
  sitTagText: { fontSize: 10, fontWeight: "700", letterSpacing: 0.4 },
  fab: {
    position: "absolute", right: spacing.lg, bottom: spacing.xl,
    width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40 },
});
