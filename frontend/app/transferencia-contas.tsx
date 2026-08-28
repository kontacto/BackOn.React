// Transferência p/Contas Pagar/Receber (Financeiro) — migração de
// `Geral\FrmTransfContas.frm` (caption real "Transferência para o Contas
// a Pagar / Receber..."). NÃO é a tela de mover saldo entre Contas de
// caixa/banco (isso é FrmTransfCaixa, tela irmã e diferente no legado,
// fora de escopo aqui) — esta promove Notas Fiscais já emitidas e
// Comandas já pagas, ainda não lançadas no livro-razão formal, pro
// Contas a Pagar/Receber de verdade. Sem digitação manual nenhuma no
// legado — o usuário só marca linhas e confirma; a mesma simplicidade foi
// mantida aqui (sem filtro de período — a fonte real também não tem um).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type Pendente = {
  codnota: number; flag: "Contas a Receber" | "Contas a Pagar" | "Comanda";
  valor_total: number; num_nf: number | null; serie_nf: string; data_mov: string | null;
  vencimento: string | null; tipo_mov_descricao: string; tipo_mov_codigo: string; cliforn: string;
};

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que esta tela faz", texto: "Lista Notas Fiscais já emitidas e Comandas já pagas que ainda não foram lançadas no Contas a Pagar/Receber \"de verdade\". Marque as linhas e clique em Transferir — o sistema faz o lançamento sozinho, sem precisar digitar nada.", icon: { lib: "ion", name: "swap-horizontal-outline" } },
  { titulo: "Contas a Receber", texto: "Notas Fiscais de Saída (vendas) — viram um título a receber do cliente.", icon: { lib: "ion", name: "arrow-down-circle-outline" } },
  { titulo: "Contas a Pagar", texto: "Notas Fiscais de Entrada (compras) — viram um título a pagar ao fornecedor.", icon: { lib: "ion", name: "arrow-up-circle-outline" } },
  { titulo: "Comanda", texto: "Uma comanda do Bar já fechada e paga, ainda não lançada no Contas a Receber.", icon: { lib: "ion", name: "receipt-outline" } },
  { titulo: "Depois de transferir", texto: "O item sai desta lista — não tem \"desfazer\" por aqui. Se algo foi transferido por engano, é preciso ajustar direto no Contas a Pagar/Receber já lançado.", icon: { lib: "ion", name: "alert-circle-outline" } },
];

export default function TransferenciaContasScreen() {
  const router = useRouter();
  const { can, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [transferindo, setTransferindo] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [busca, setBusca] = useState("");
  const [itens, setItens] = useState<Pendente[]>([]);
  const [selecionados, setSelecionados] = useState<Record<string, boolean>>({});

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const cod = s?.funcionario?.codigo_int;
      const vCod = typeof cod === "number" ? cod : (typeof cod === "string" && /^\d+$/.test(cod) ? parseInt(cod, 10) : null);
      const master = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(master ? -2 : (typeof vCod === "number" ? vCod : -2));
      setLoading(false);
    })();
  }, []);

  const chave = (it: Pendente) => `${it.flag}-${it.codnota}`;

  const buscar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    try {
      const j = await apiGet(conn, "/api/transferencia-contas/pendentes");
      if (j?.success) {
        const carregados: Pendente[] = j.items || [];
        setItens(carregados);
        // Carrega com tudo marcado por padrão — pedido explícito do
        // usuário, 2026-08-28 ("carregar a tela com todos marcados").
        const todosMarcados: Record<string, boolean> = {};
        for (const it of carregados) todosMarcados[chave(it)] = true;
        setSelecionados(todosMarcados);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, feedback]);

  useEffect(() => {
    if (conn) buscar();
  }, [conn, buscar]);

  const itensFiltrados = busca.trim()
    ? itens.filter((it) => {
        const termo = busca.trim().toLowerCase();
        return it.cliforn.toLowerCase().includes(termo) || String(it.num_nf ?? it.codnota).includes(termo);
      })
    : itens;

  const toggleItem = (it: Pendente) => {
    const k = chave(it);
    setSelecionados((prev) => ({ ...prev, [k]: !prev[k] }));
  };

  const marcarTodos = (valor: boolean) => {
    const next: Record<string, boolean> = {};
    for (const it of itensFiltrados) next[chave(it)] = valor;
    setSelecionados(next);
  };

  const qtdSelecionados = Object.values(selecionados).filter(Boolean).length;
  const valorSelecionado = itens
    .filter((it) => selecionados[chave(it)])
    .reduce((s, it) => s + it.valor_total, 0);

  const transferir = useCallback(async () => {
    if (!conn) return;
    const marcados = itens.filter((it) => selecionados[chave(it)]);
    if (marcados.length === 0) {
      feedback.showError("Selecione ao menos um item para transferir.");
      return;
    }
    setTransferindo(true);
    try {
      const j = await apiSend(conn, "/api/transferencia-contas/transferir", "POST", {
        itens: marcados.map((it) => ({ codnota: it.codnota, flag: it.flag })),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      const transferidos: number[] = j?.transferidos || [];
      const falhas: { codnota: number; message: string }[] = j?.falhas || [];
      if (transferidos.length > 0) {
        feedback.showSuccess(
          `${transferidos.length} item(ns) transferido(s) com sucesso.`
          + (falhas.length > 0 ? ` ${falhas.length} falharam.` : ""),
          undefined, 5000,
        );
      }
      if (falhas.length > 0 && transferidos.length === 0) {
        feedback.showError(falhas.map((f) => f.message).join("\n"));
      } else if (falhas.length > 0) {
        feedback.showWarning(`Falhas: ${falhas.map((f) => f.message).join("; ")}`, undefined, 5000);
      }
      buscar();
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setTransferindo(false);
    }
  }, [conn, itens, selecionados, usuarioCod, classePerm, feedback, buscar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Transferência p/Contas Pagar/Receber está disponível apenas no web." testID="transferencia-contas-web-only" />;
  }
  if (!loading && !can("TRANSF_CONTAS.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar a Transferência p/Contas Pagar/Receber." testID="transferencia-contas-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="transferencia-contas-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Transferência p/Contas Pagar/Receber</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary}
          onPress={() => setAjudaOpen(true)} testID="transferencia-contas-ajuda-btn"
        />
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : (
            <View style={{ gap: spacing.md }}>
              <View style={WEB_FILTER_CARD}>
                <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" }}>
                  <View style={{ flex: 1, minWidth: 220 }}>
                    <Text style={fieldLabel()}>Buscar por cliente/fornecedor ou nº</Text>
                    <TextInput value={busca} onChangeText={setBusca} style={inputStyle()} testID="transferencia-contas-busca" />
                  </View>
                  <Pressable onPress={buscar} disabled={buscando} style={[secondaryBtnStyle(), { alignSelf: "flex-end" }]} testID="transferencia-contas-atualizar-btn">
                    {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                      <>
                        <Ionicons name="refresh" size={16} color={colors.brandPrimary} />
                        <Text style={secondaryBtnLabelStyle()}>Atualizar</Text>
                      </>
                    )}
                  </Pressable>
                </View>
              </View>

              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Pendentes de Transferência ({itensFiltrados.length})</Text>
                {/* Totais e botões de ação de lista sempre na PARTE DE
                    CIMA — regra `[GLOBAL]` de design, pedido explícito do
                    usuário, 2026-08-28 ("O totais e botões de listas
                    sempre na parte de cima"). Marcar/Desmarcar Todos +
                    contagem selecionada + Total + Transferir, tudo nesta
                    mesma linha (quebra em várias se não couber). */}
                {itensFiltrados.length > 0 ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.md, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Pressable onPress={() => marcarTodos(true)} style={miniBtnStyle()} testID="transferencia-contas-marcar-todos">
                      <Text style={miniBtnLabelStyle()}>Marcar todos</Text>
                    </Pressable>
                    <Pressable onPress={() => marcarTodos(false)} style={miniBtnStyle()} testID="transferencia-contas-desmarcar-todos">
                      <Text style={miniBtnLabelStyle()}>Desmarcar todos</Text>
                    </Pressable>
                    <View style={{ flex: 1 }} />
                    <Text style={{ fontSize: 13, color: colors.muted }}>
                      {qtdSelecionados} selecionado(s)
                    </Text>
                    <Text style={{ fontSize: 15, fontWeight: "700", color: colors.brandPrimary }}>
                      Total: {formatBRL(valorSelecionado)}
                    </Text>
                    {can("TRANSF_CONTAS.TRANSFERIR") ? (
                      <Pressable
                        onPress={transferir}
                        disabled={transferindo || qtdSelecionados === 0}
                        style={[primaryBtnStyle(), qtdSelecionados === 0 && { opacity: 0.5 }]}
                        testID="transferencia-contas-transferir-btn"
                      >
                        {transferindo ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                          <>
                            <Ionicons name="swap-horizontal-outline" size={16} color={colors.onBrandPrimary} />
                            <Text style={primaryBtnLabelStyle()}>Transferir</Text>
                          </>
                        )}
                      </Pressable>
                    ) : null}
                  </View>
                ) : null}

                {itensFiltrados.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>
                    Nenhum item pendente de transferência.
                  </Text>
                ) : (
                  itensFiltrados.map((it) => {
                    const k = chave(it);
                    const sel = !!selecionados[k];
                    return (
                      <Pressable key={k} onPress={() => toggleItem(it)} style={itemRowStyle()} testID={`transferencia-contas-item-${k}`}>
                        <Ionicons name={sel ? "checkbox" : "square-outline"} size={22} color={sel ? colors.brandPrimary : colors.muted} />
                        <View style={{ flex: 1, marginLeft: spacing.sm }}>
                          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>
                            {it.flag === "Comanda" ? `Comanda #${it.codnota}` : `NF ${it.num_nf}${it.serie_nf ? `/${it.serie_nf}` : ""}`}
                            {"  ·  "}{it.cliforn || "(sem cliente/fornecedor)"}
                          </Text>
                          <Text style={{ fontSize: 12, color: colors.muted }}>
                            {formatDateBR(it.data_mov)}
                            {it.vencimento ? ` · Venc. ${formatDateBR(it.vencimento)}` : ""}
                            {" · "}{it.tipo_mov_descricao}
                          </Text>
                        </View>
                        <View style={[flagBadgeStyle(), { backgroundColor: flagColor(it.flag) + "22" }]}>
                          <Text style={[flagBadgeTextStyle(), { color: flagColor(it.flag) }]}>{it.flag}</Text>
                        </View>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface, marginLeft: spacing.md, minWidth: 90, textAlign: "right" }}>
                          {formatBRL(it.valor_total)}
                        </Text>
                      </Pressable>
                    );
                  })
                )}
              </View>
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Transferência p/Contas Pagar/Receber" itens={AJUDA_ITENS} />
    </SafeAreaView>
  );
}

function flagColor(flag: Pendente["flag"]) {
  if (flag === "Contas a Receber") return colors.success;
  if (flag === "Contas a Pagar") return colors.error;
  return colors.brandPrimary;
}

function headerStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm,
    paddingHorizontal: spacing.md, paddingVertical: spacing.md, backgroundColor: colors.brandPrimary,
  };
}
function headerTitleStyle() {
  return { flex: 1, fontSize: 17, fontWeight: "700" as const, color: colors.onBrandPrimary };
}
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 };
}
function fieldLabel() {
  return { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const };
}
function miniBtnStyle() {
  return {
    borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.sm, paddingVertical: 4,
  } as const;
}
function miniBtnLabelStyle() {
  return { fontSize: 12, color: colors.brandPrimary, fontWeight: "600" as const };
}
function inputStyle() {
  return {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
    backgroundColor: colors.surfaceSecondary,
  } as const;
}
function itemRowStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  };
}
function flagBadgeStyle() {
  return { paddingHorizontal: 8, paddingVertical: 3, borderRadius: radius.pill };
}
function flagBadgeTextStyle() {
  return { fontSize: 10, fontWeight: "700" as const };
}
function primaryBtnStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6,
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 100,
  };
}
function primaryBtnLabelStyle() {
  return { color: colors.onBrandPrimary, fontWeight: "600" as const, fontSize: 14 };
}
function secondaryBtnStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const, justifyContent: "center" as const, gap: 6,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.brandPrimary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, paddingVertical: 10, minWidth: 100,
  };
}
function secondaryBtnLabelStyle() {
  return { color: colors.brandPrimary, fontWeight: "600" as const, fontSize: 14 };
}
