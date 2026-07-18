import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
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
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL } from "@/src/theme/webLayout";
import { usePedidoItens } from "@/src/components/pedido/usePedidoItens";
import AddItemModal from "@/src/components/pedido/AddItemModal";
import ReciboPedidoModal from "@/src/components/pedido/ReciboPedidoModal";
import { apiGet } from "@/src/utils/api";
import { PedidoData, ClienteRow } from "@/src/components/pedido/types";

const isWeb = Platform.OS === "web";

const TOAST_SHADOW_STYLE =
  Platform.OS === "web"
    ? { boxShadow: "0 4px 10px rgba(0, 0, 0, 0.3)" }
    : {
        shadowColor: "#000",
        shadowOpacity: 0.3,
        shadowRadius: 10,
        shadowOffset: { width: 0, height: 4 },
        elevation: 10,
      };

type Tipo = "all" | "P" | "S";
type Item = {
  tipo: "P" | "S";
  codigo: string;
  descricao: string;
  valor: number;
  estoque: number | null;
  qtd?: number | null;
  reservado?: number | null;
  reservado_os?: number | null;
  estoque_total?: number | null;
  cod_fab?: string;
  unidade?: string;
};

function formatBRL(v: number): string {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function parseNum(s: string): number {
  const n = parseFloat(String(s).replace(/\./g, "").replace(",", "."));
  return isNaN(n) ? 0 : n;
}

export default function ProdutosScreen() {
  const router = useRouter();
  const { can, moduleOn, classe } = usePermissions();
  const feedback = useFeedback();
  const servicosOn = moduleOn("servicos");
  const params = useLocalSearchParams<{ pedido?: string; tipo?: string; origem?: string }>();
  const selectPedido = params.pedido ? parseInt(String(params.pedido), 10) : null;
  const selecting = !!selectPedido;
  // Origem "completo" = aberta a partir do Pedido Completo (web) — grava via
  // /api/pedido-completo (resolução de produto mais rica + kits), não
  // /api/pedidos (pré-venda rápida). Mesma tabela, endpoint diferente.
  const completo = params.origem === "completo";
  const itensBasePath = completo ? "/api/pedido-completo" : "/api/pedidos";

  const [niveisTooltip, setNiveisTooltip] = useState(false);
  // Permissão de desconto do usuário logado
  const [funcaoCod, setFuncaoCod] = useState<number>(1); // 1=gerente,2=supervisor,3=vendedor
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [toast, setToast] = useState<string | null>(null);
  const [conn, setConn] = useState<Connection | null>(null);
  const [search, setSearch] = useState("");
  // Quando a tela é aberta a partir de um cadastro específico (Cadastros >
  // Produtos ou Cadastros > Serviços, ambos com `?tipo=` fixo na URL), o
  // tipo fica travado — sem chips pra trocar pra "Tudo"/o outro tipo. Só
  // quando aberta sem `tipo` (picker de item em Pedido/O.S., que precisa
  // buscar entre os dois) é que os chips de filtro aparecem.
  const tipoFixo = params.tipo === "P" || params.tipo === "S";
  const [tipo, setTipo] = useState<Tipo>(tipoFixo ? (params.tipo as Tipo) : "all");
  const [items, setItems] = useState<Item[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const aborter = useRef<AbortController | null>(null);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const conns = await listConnections();
      const c = conns.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      // Função/permissão de desconto do usuário logado
      const isMaster = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      const cf = (s?.funcionario as { cod_funcao?: string } | undefined)?.cod_funcao;
      const fc = cf ? parseInt(cf, 10) : NaN;
      const funcao = isMaster ? 1 : Number.isFinite(fc) && fc > 0 ? fc : 1;
      setFuncaoCod(funcao);
      const vCod = s?.funcionario?.codigo_int;
      setUsuarioCod(isMaster ? -2 : typeof vCod === "number" ? vCod : -2);
    })();
  }, []);

  const load = useCallback(
    async (term: string, pg: number, tp: Tipo, append: boolean) => {
      if (!conn) return;
      if (aborter.current) aborter.current.abort();
      const ac = new AbortController();
      aborter.current = ac;
      setLoading(true);
      try {
        const base = conn.api.replace(/\/+$/, "");
        const url =
          `${base}/api/produtos-servicos` +
          `?servidor=${encodeURIComponent(conn.servidor)}` +
          `&banco=${encodeURIComponent(conn.banco)}` +
          `&search=${encodeURIComponent(term)}` +
          `&page=${pg}&size=40&tipo=${servicosOn ? tp : "P"}`;
        const r = await fetch(url, { signal: ac.signal });
        const j = await r.json();
        if (!j?.success) {
          feedback.showError(j?.message || "Falha ao consultar.");
          if (!append) setItems([]);
        } else {
          const fetched: Item[] = j.items || [];
          setItems((prev) => (append ? [...prev, ...fetched] : fetched));
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
    [conn, servicosOn, feedback]
  );

  // Recarrega quando muda search / tipo (debounce 300ms na busca)
  useEffect(() => {
    if (!conn) return;
    const t = setTimeout(() => {
      setPage(1);
      load(search, 1, tipo, false);
    }, 300);
    return () => clearTimeout(t);
  }, [search, tipo, conn, load]);

  const loadMore = () => {
    if (loading || items.length >= total) return;
    const next = page + 1;
    setPage(next);
    load(search, next, tipo, true);
  };

  // Imagens dos produtos vêm da URL configurada na conexão (campo "Imagens Produtos").
  // Nome do arquivo = pecas.codigo_int (que é o item.codigo para produtos).
  // Tenta extensões em ordem (jpg → jpeg → png → webp); se nenhuma existir, cai no ícone.
  // Quando a URL não está configurada, retorna [] (ícone padrão direto, sem chamar backend).
  const fotoUrls = useCallback(
    (item: Item): string[] => {
      if (!conn || item.tipo === "S") return [];
      const base = (conn.imagensUrl || "").trim().replace(/\/+$/, "");
      if (!base) return [];
      const cod = encodeURIComponent(item.codigo);
      return ["jpg", "jpeg", "png", "webp"].map((ext) => `${base}/${cod}.${ext}`);
    },
    [conn]
  );

  const counts = useMemo(() => {
    const p = items.filter((i) => i.tipo === "P").length;
    const s = items.filter((i) => i.tipo === "S").length;
    return { p, s };
  }, [items]);

  const showToast = useCallback((m: string) => {
    setToast(m);
    setTimeout(() => setToast(null), 500);
  }, []);

  // Reaproveita o mesmo modal "Adicionar Item" do Pedido (AddItemModal.tsx +
  // usePedidoItens) em vez de uma implementação própria — evita duas telas
  // com campos/limites de desconto divergentes pra confirmar o mesmo item
  // (ver CLAUDE.md "Padrão Geral de Migração de Telas", seção 5). `isAberto:
  // true` porque este fluxo só grava (POST item), nunca edita/fecha o
  // pedido — o backend já valida a situação do pedido nesse endpoint.
  // Impressão automática de item por Finalidade (ver ReciboPedidoModal/
  // usePedidoItens) — Pedido Bar somente, mesmo recorte da permissão
  // IMPRIMIR_ITEM (não existe em ACOES_PEDIDO_COMP).
  const it = usePedidoItens({
    conn, editing: true, pedidoId: selectPedido, isAberto: true,
    usuarioCod, funcaoCod, classe, showToast, servicosOn, basePath: itensBasePath,
    printPorFinalidade: selecting && !completo,
  });

  // Dados mínimos do pedido/cliente pro ticket de impressão de item — esta
  // tela só tem o número do pedido via `?pedido=`, nunca carregou o cabeçalho
  // completo antes porque só grava itens, nunca exibe/edita dados do pedido.
  const [pedidoData, setPedidoData] = useState<PedidoData | null>(null);
  useEffect(() => {
    if (!conn || !selecting || completo) return;
    (async () => {
      const j = await apiGet(conn, `/api/pedidos/${selectPedido}`).catch(() => null);
      if (j?.success && j.pedido) setPedidoData(j.pedido);
    })();
  }, [conn, selecting, completo, selectPedido]);
  const pedidoCliente: ClienteRow | null = pedidoData?.cliente
    ? { codigo: pedidoData.cliente, nome: pedidoData.cliente_nome, cgc_cpf: pedidoData.cliente_cgc, telefone: "" }
    : null;

  const pickForOrder = (item: Item) => {
    it.setAddOpen(true);
    it.pickProduto(item);
  };

  // --- Reservas do produto (Pedidos Fechados / O.S. Abertas+Fechadas) ---
  const [resModal, setResModal] = useState<{ item: Item; tipo: "PED" | "OS" } | null>(null);
  const [resItems, setResItems] = useState<
    { doc: number; cliente: string; data: string | null; situacao_label: string; qtd: number }[]
  >([]);
  const [resLoading, setResLoading] = useState(false);

  const openReservas = useCallback(async (item: Item, tipo: "PED" | "OS") => {
    if (!conn) return;
    setResModal({ item, tipo });
    setResItems([]);
    setResLoading(true);
    try {
      const base = conn.api.replace(/\/+$/, "");
      const r = await fetch(
        `${base}/api/produtos/${encodeURIComponent(item.codigo)}/reservas` +
        `?servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&tipo=${tipo}`
      );
      const j = await r.json();
      setResItems(j?.success ? (j.items || []) : []);
    } catch {
      setResItems([]);
    } finally {
      setResLoading(false);
    }
  }, [conn]);

  const brDate = (iso: string | null) => {
    const [y, m, d] = (iso || "").split("-");
    return d ? `${d}/${m}/${y}` : "—";
  };

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="produtos-screen">
      {!(selecting ? (completo ? can("PEDIDO_COMP.ADD_ITEM") : can("PEDIDO.GRAVAR")) : can("PRODUTO.ABRIR")) ? (
        <LockedView testID="produtos-locked" />
      ) : (
      <>
      <View style={styles.header}>
        <Pressable
          onPress={() => router.back()}
          style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
          hitSlop={12}
        >
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Image source={require("../assets/images/kontacto-logo.png")} style={{ width: 56, height: 16, marginRight: 8 }} resizeMode="contain" />
        <Text style={styles.headerTitle}>
          {selecting
            ? `Adicionar ao Pedido #${selectPedido}`
            : tipoFixo
            ? `${tipo === "P" ? "Produtos" : "Serviços"} (${total})`
            : `Produtos & Serviços (${total})`}
        </Text>
        {Platform.OS === "web" && !selecting && can("PRODUTO_NIVEIS.ABRIR") ? (
          <View style={{ position: "relative" }}>
            <Pressable
              onPress={() => router.push("/produtos-niveis")}
              onHoverIn={() => setNiveisTooltip(true)}
              onHoverOut={() => setNiveisTooltip(false)}
              style={({ pressed }) => [styles.backBtn, pressed && { opacity: 0.7 }]}
              hitSlop={12}
              testID="produtos-niveis-open-button"
            >
              <Ionicons name="layers-outline" size={22} color={colors.onBrandPrimary} />
            </Pressable>
            {niveisTooltip ? (
              <View style={styles.niveisTooltip} pointerEvents="none">
                <Text style={styles.niveisTooltipText}>Alterações Cadastro de Produtos/Serviços Níveis</Text>
              </View>
            ) : null}
          </View>
        ) : (
          <View style={{ width: 40 }} />
        )}
      </View>

      {selecting ? (
        <View style={[styles.selectBanner, isWeb && styles.webShell]}>
          <Ionicons name="cart-outline" size={16} color={colors.brandPrimary} />
          <Text style={styles.selectBannerText}>Toque em um item para adicioná-lo ao pedido.</Text>
        </View>
      ) : null}

      <View style={[styles.searchWrap, isWeb && styles.webShell]}>
        <Ionicons name="search" size={16} color={colors.muted} />
        <TextInput
          value={search}
          onChangeText={setSearch}
          placeholder="Buscar por código ou descrição…"
          placeholderTextColor={colors.muted}
          style={styles.searchInput}
          testID="produtos-search-input"
        />
      </View>

      {/* Chips de tipo — ocultos quando o módulo Serviços está desligado OU
          quando o tipo veio fixo na URL (Cadastros > Produtos/Serviços) */}
      {servicosOn && !tipoFixo ? (
      <View style={[styles.chips, isWeb && styles.webShell]}>
        {([
          { key: "all" as const, label: "Tudo", count: counts.p + counts.s },
          { key: "P" as const, label: "Produtos", count: counts.p },
          { key: "S" as const, label: "Serviços", count: counts.s },
        ]).map((c) => {
          const sel = tipo === c.key;
          return (
            <Pressable
              key={c.key}
              onPress={() => setTipo(c.key)}
              style={({ pressed }) => [
                styles.chip,
                sel && styles.chipSel,
                pressed && { opacity: 0.7 },
              ]}
              testID={`produtos-chip-${c.key}`}
            >
              <Text style={[styles.chipText, sel && { color: colors.brandPrimary }]}>
                {c.label}
              </Text>
            </Pressable>
          );
        })}
      </View>
      ) : null}

      <FlatList
        data={items}
        keyExtractor={(i) => `${i.tipo}-${i.codigo}`}
        style={isWeb ? styles.webShell : undefined}
        contentContainerStyle={{ paddingHorizontal: spacing.lg, paddingBottom: spacing.xxl }}
        ItemSeparatorComponent={() => <View style={{ height: 8 }} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.6}
        ListEmptyComponent={
          !loading ? (
            <Text style={styles.empty}>Nenhum item encontrado.</Text>
          ) : null
        }
        ListFooterComponent={
          loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 16 }} />
          ) : null
        }
        renderItem={({ item }) => (
          <Pressable
            onPress={() => {
              if (selecting) {
                pickForOrder(item);
              } else if (isWeb && item.tipo === "P" && can("PRODUTO_COMP.ABRIR")) {
                // Fora do modo de seleção (aberta a partir de Cadastros), tocar
                // num produto abre o Cadastro de Produtos completo (web-only).
                router.push({ pathname: "/produto-completo", params: { codigo: item.codigo } });
              } else if (isWeb && item.tipo === "S" && can("SERVICO.ABRIR")) {
                // Mesmo padrão pro lado Serviços — servicos.tsx agora é só o
                // formulário, aberto com o código pra edição.
                router.push({ pathname: "/servicos", params: { codigo: item.codigo } });
              }
            }}
            disabled={
              !selecting &&
              !(isWeb && item.tipo === "P" && can("PRODUTO_COMP.ABRIR")) &&
              !(isWeb && item.tipo === "S" && can("SERVICO.ABRIR"))
            }
            style={({ pressed }) => [styles.card, (selecting || isWeb) && pressed && { opacity: 0.7 }]}
            testID={`item-${item.tipo}-${item.codigo}`}
          >
            {item.tipo === "P" ? (
              <ProdutoFoto urls={fotoUrls(item)} />
            ) : (
              <View style={[styles.thumb, styles.thumbServico]}>
                <Ionicons name="construct-outline" size={26} color={colors.brandPrimary} />
              </View>
            )}

            <View style={{ flex: 1 }}>
              <View style={styles.cardTitleRow}>
                <Text style={styles.cardTitle} numberOfLines={2}>
                  {item.descricao || "—"}
                </Text>
                <View
                  style={[
                    styles.tipoTag,
                    item.tipo === "P" ? styles.tagProd : styles.tagServ,
                  ]}
                >
                  <Text style={[styles.tipoTagText, item.tipo === "P" ? { color: colors.brandPrimary } : { color: colors.warning }]}>
                    {item.tipo === "P" ? "PRODUTO" : "SERVIÇO"}
                  </Text>
                </View>
              </View>
              <Text style={styles.cardSub}>
                Código: <Text style={styles.cardSubBold}>#{item.codigo}</Text>
              </Text>
              <View style={styles.cardFooter}>
                <Text style={styles.cardValor}>{formatBRL(item.valor)}</Text>
                {item.tipo === "P" ? (
                  <Text
                    style={[
                      styles.estoque,
                      (item.qtd ?? item.estoque ?? 0) <= 0 && { color: colors.error },
                    ]}
                  >
                    Disponível: {item.qtd ?? item.estoque ?? 0}
                  </Text>
                ) : (
                  <Text style={styles.estoque}>por hora</Text>
                )}
              </View>
              {item.tipo === "P" ? (
                <View style={styles.estoqueRow} testID={`estoque-detalhe-${item.codigo}`}>
                  <Pressable
                    onPress={() => openReservas(item, "PED")}
                    hitSlop={6}
                    style={({ pressed }) => [styles.estoqueChip, styles.estoqueChipBtn, pressed && { opacity: 0.6 }]}
                    testID={`reservado-pedido-${item.codigo}`}
                  >
                    <Text style={styles.estoqueChipText}>Res. Pedido: {item.reservado ?? 0}</Text>
                    <Ionicons name="chevron-forward" size={11} color={colors.brandPrimary} />
                  </Pressable>
                  <Pressable
                    onPress={() => openReservas(item, "OS")}
                    hitSlop={6}
                    style={({ pressed }) => [styles.estoqueChip, styles.estoqueChipBtn, pressed && { opacity: 0.6 }]}
                    testID={`reservado-os-${item.codigo}`}
                  >
                    <Text style={styles.estoqueChipText}>Res. O.S.: {item.reservado_os ?? 0}</Text>
                    <Ionicons name="chevron-forward" size={11} color={colors.brandPrimary} />
                  </Pressable>
                  <Text style={[styles.estoqueChip, styles.estoqueChipTotal]}>
                    Total: {item.estoque_total ?? ((item.qtd ?? 0) + (item.reservado ?? 0) + (item.reservado_os ?? 0))}
                  </Text>
                </View>
              ) : null}
            </View>
            {selecting ? (
              <Ionicons name="add-circle" size={26} color={colors.brandPrimary} />
            ) : null}
          </Pressable>
        )}
      />

      {!selecting && isWeb && tipo === "P" && can("PRODUTO_COMP.GRAVAR") ? (
        <Pressable
          onPress={() => router.push("/produto-completo")}
          style={({ pressed }) => [styles.fabNovoProduto, pressed && { opacity: 0.85 }]}
          hitSlop={8}
          testID="produtos-fab-novo"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}
      {!selecting && isWeb && tipo === "S" && can("SERVICO.GRAVAR") ? (
        <Pressable
          onPress={() => router.push("/servicos")}
          style={({ pressed }) => [styles.fabNovoProduto, pressed && { opacity: 0.85 }]}
          hitSlop={8}
          testID="produtos-fab-novo-servico"
        >
          <Ionicons name="add" size={28} color={colors.onBrandPrimary} />
        </Pressable>
      ) : null}

      {/* Mesmo modal "Adicionar Item" usado no Pedido — ver comentário
          acima de `it`/`pickForOrder`. */}
      {selecting ? (
        <AddItemModal
          it={it}
          onOpenProdutos={() => it.setAddOpen(false)}
          tela={completo ? "PEDIDO_COMP" : "PEDIDO"}
        />
      ) : null}

      {/* Ticket de impressão de item por Finalidade (Pedido Bar) — disparado
          automaticamente por `checkAutoPrintItem` dentro de `usePedidoItens`
          (ver `printPorFinalidade` acima); precisava do próprio modal aqui
          porque esta tela nunca renderizava `ReciboPedidoModal` antes,
          então o disparo automático ficava sem UI pra exibir o resultado. */}
      {selecting && !completo ? (
        <ReciboPedidoModal
          visible={!!it.printItem}
          onClose={() => it.setPrintItem(null)}
          conn={conn}
          pedido={pedidoData}
          cliente={pedidoCliente}
          clienteResumo={null}
          it={it}
          item={it.printItem}
        />
      ) : null}

      {/* Modal: reservas do produto (Pedidos Fechados / O.S. Abertas+Fechadas) */}
      <Modal visible={!!resModal} transparent animationType="slide" onRequestClose={() => setResModal(null)}>
        <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => setResModal(null)}>
          <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactList]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {resModal?.tipo === "OS" ? "Reservado para O.S." : "Reservado para Pedido"}
              </Text>
              <Pressable onPress={() => setResModal(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {resModal ? (
              <Text style={styles.cardSub}>
                #{resModal.item.codigo} · {resModal.item.descricao}
              </Text>
            ) : null}
            {resLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : resItems.length === 0 ? (
              <Text style={[styles.empty, { marginVertical: 24 }]} testID="reservas-empty">
                Nenhum documento reservando este produto.
              </Text>
            ) : (
              <ScrollView style={{ maxHeight: 380 }} testID="reservas-list">
                <View style={styles.resHeadRow}>
                  <Text style={[styles.resHead, { flex: 1 }]}>{resModal?.tipo === "OS" ? "O.S." : "Pedido"}</Text>
                  <Text style={[styles.resHead, { flex: 2 }]}>Cliente</Text>
                  <Text style={[styles.resHead, { flex: 1.1 }]}>Data</Text>
                  <Text style={[styles.resHead, { flex: 0.8, textAlign: "right" }]}>Qtd</Text>
                </View>
                {resItems.map((r) => (
                  <View key={r.doc} style={styles.resRow} testID={`reserva-doc-${r.doc}`}>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.resDoc}>#{r.doc}</Text>
                      <Text style={styles.resSit}>{r.situacao_label}</Text>
                    </View>
                    <Text style={[styles.resCell, { flex: 2 }]} numberOfLines={1}>{r.cliente}</Text>
                    <Text style={[styles.resCell, { flex: 1.1 }]}>{brDate(r.data)}</Text>
                    <Text style={[styles.resCell, { flex: 0.8, textAlign: "right", fontWeight: "700" }]}>{r.qtd}</Text>
                  </View>
                ))}
              </ScrollView>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {toast ? (
        <View style={[styles.toast, TOAST_SHADOW_STYLE]} testID="produtos-toast">
          <Text style={styles.toastText}>{toast}</Text>
        </View>
      ) : null}
      </>
      )}
    </SafeAreaView>
  );
}

// Foto do produto: tenta as URLs em ordem (extensões diferentes). Se todas falharem
// (ou a lista vier vazia, quando não há URL configurada), mostra o ícone padrão.
function ProdutoFoto({ urls }: { urls: string[] }) {
  const [idx, setIdx] = useState(0);
  const key = urls.join("|");
  useEffect(() => {
    setIdx(0);
  }, [key]);
  const current = urls[idx];
  if (!current) {
    return (
      <View style={[styles.thumb, styles.thumbProduto]}>
        <Ionicons name="cube-outline" size={26} color={colors.brandPrimary} />
      </View>
    );
  }
  return (
    <Image
      source={{ uri: current }}
      style={styles.thumb}
      onError={() => setIdx((i) => i + 1)}
      resizeMode="cover"
    />
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  webShell: WEB_CONTENT_SHELL,
  fabNovoProduto: {
    position: "absolute", right: spacing.lg, bottom: spacing.xl,
    width: 56, height: 56, borderRadius: 28, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: colors.brandPrimary,
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
    zIndex: 20,
    elevation: 20,
  },
  backBtn: {
    width: 40, height: 40, alignItems: "center", justifyContent: "center",
  },
  niveisTooltip: {
    position: "absolute", top: 46, right: 0, backgroundColor: colors.onSurface,
    paddingHorizontal: spacing.sm, paddingVertical: 6, borderRadius: radius.sm,
    maxWidth: 220, zIndex: 10,
  },
  niveisTooltipText: { color: colors.surface, fontSize: 11, textAlign: "center" },
  headerTitle: {
    flex: 1, color: colors.onBrandPrimary,
    fontSize: 17, fontWeight: "500",
  },
  searchWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 14 },
  chips: {
    flexDirection: "row", gap: 8,
    paddingHorizontal: spacing.lg,
    marginTop: spacing.md, marginBottom: spacing.sm,
    height: 56, alignItems: "center",
  },
  chip: {
    flexShrink: 0,
    paddingHorizontal: spacing.md,
    paddingVertical: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary,
    height: 36, justifyContent: "center",
  },
  chipSel: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.md, padding: spacing.md,
    borderWidth: 1, borderColor: colors.border,
  },
  thumb: {
    width: 64, height: 64, borderRadius: radius.sm,
    backgroundColor: colors.brandTertiary,
    alignItems: "center", justifyContent: "center",
  },
  thumbProduto: { backgroundColor: colors.brandTertiary },
  thumbServico: { backgroundColor: "#fff4e0" },
  cardTitleRow: { flexDirection: "row", alignItems: "flex-start", justifyContent: "space-between", gap: spacing.sm },
  cardTitle: { flex: 1, fontSize: 14, fontWeight: "500", color: colors.onSurface },
  cardSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  cardSubBold: { color: colors.onSurface, fontWeight: "500" },
  cardFooter: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: 6 },
  cardValor: { fontSize: 15, fontWeight: "600", color: colors.brandPrimary },
  estoque: { fontSize: 12, color: colors.muted, fontWeight: "500" },
  estoqueRow: { flexDirection: "row", flexWrap: "wrap", gap: 6, marginTop: 6 },
  estoqueChip: {
    fontSize: 10, color: colors.muted, backgroundColor: colors.surfaceSecondary,
    borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2, overflow: "hidden",
  },
  estoqueChipTotal: { color: colors.brandPrimary, fontWeight: "700" },
  estoqueChipBtn: {
    flexDirection: "row", alignItems: "center", gap: 2,
    borderWidth: 1, borderColor: colors.brandPrimary,
  },
  estoqueChipText: { fontSize: 10, color: colors.brandPrimary, fontWeight: "600" },
  resHeadRow: { flexDirection: "row", paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: colors.border, marginTop: 8 },
  resHead: { fontSize: 11, color: colors.muted, fontWeight: "600", textTransform: "uppercase" },
  resRow: { flexDirection: "row", alignItems: "center", paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  resDoc: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  resSit: { fontSize: 11, color: colors.brandPrimary, marginTop: 1 },
  resCell: { fontSize: 12, color: colors.onSurface },
  tipoTag: {
    paddingHorizontal: 8, paddingVertical: 2,
    borderRadius: 4, alignSelf: "flex-start",
  },
  tagProd: { backgroundColor: colors.brandTertiary },
  tagServ: { backgroundColor: "#fff4e0" },
  tipoTagText: { fontSize: 10, fontWeight: "600", letterSpacing: 0.4 },
  empty: { textAlign: "center", color: colors.muted, fontSize: 14, marginTop: 40 },
  selectBanner: {
    flexDirection: "row", alignItems: "center", gap: 8,
    backgroundColor: colors.brandTertiary, marginHorizontal: spacing.lg, marginTop: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: 10, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  selectBannerText: { color: colors.onSurface, fontSize: 13, flex: 1 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "flex-end" },
  modalCard: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radius.lg, borderTopRightRadius: radius.lg,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg, paddingBottom: spacing.xxl,
  },
  // "Redução forte" (Modal/Selector Standard, CLAUDE.md) no web — card
  // centralizado com raio completo nas 4 pontas + borda, mesmo padrão
  // canônico de SelectField.tsx. Usado pelo modal de reservas abaixo — o
  // modal de "Adicionar Item" em si agora é o `AddItemModal` compartilhado
  // (`src/components/pedido/AddItemModal.tsx`), que já tem seu próprio
  // tratamento web (`pedido/styles.ts`).
  modalBgWebCompact: { justifyContent: "center", paddingHorizontal: spacing.xl },
  // Modal de reservas (lista de Pedidos/O.S.) — tier de seleção/busca
  // normal (560px), por navegar uma lista em vez de confirmar 1 registro.
  modalCardWebCompactList: {
    width: "100%",
    maxWidth: 560,
    alignSelf: "center",
    borderBottomLeftRadius: radius.lg,
    borderBottomRightRadius: radius.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.md },
  modalTitle: { fontSize: 17, fontWeight: "600", color: colors.onSurface },
  itemDesc: { fontSize: 14, fontWeight: "500", color: colors.onSurface },
  selProdBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  qtdRow: { flexDirection: "row", gap: spacing.sm },
  descHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  modeToggle: { flexDirection: "row", borderWidth: 1, borderColor: colors.border, borderRadius: 8, overflow: "hidden" },
  modeBtn: { paddingHorizontal: 14, paddingVertical: 4, backgroundColor: colors.surface },
  modeBtnSel: { backgroundColor: colors.brandPrimary },
  modeBtnText: { fontSize: 13, fontWeight: "600", color: colors.muted },
  modeBtnTextSel: { color: colors.onBrandPrimary },
  qtdInputRow: { flexDirection: "row", alignItems: "center", gap: 6 },
  plusBtn: {
    width: 40, height: 40, borderRadius: radius.sm, backgroundColor: colors.brandPrimary,
    alignItems: "center", justifyContent: "center",
  },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  modalInput: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  previewRow: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingVertical: spacing.sm,
  },
  primaryBtn: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingVertical: 13, alignItems: "center", justifyContent: "center", marginTop: spacing.sm,
  },
  primaryBtnText: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 15 },
  toast: {
    position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.xxl,
    backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderRadius: radius.md,
    alignItems: "center",
  },
  toastText: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "500", textAlign: "center" },
});
