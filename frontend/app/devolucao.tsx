// Gestor de Devolução (Transações) — Fase 1 enxuta, migração de
// Geral\FrmManDev.frm. Busca itens de uma venda já PAGA (mesma base do
// Gestor de Comandas) elegíveis pra devolução, registra a devolução e
// opcionalmente emite um Vale de Devolução (crédito ao cliente).
//
// Fora de escopo nesta fase (decisão via AskUserQuestion, ver
// PENDENCIAS.md > "Gestor de Devolução"): emissão de NF de devolução (o
// próprio legado delega isso a um subsistema fiscal à parte) e reposição
// física de estoque (o legado também não faz isso por este caminho).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import WebDateField from "@/src/components/WebDateField";
import SelectField from "@/src/components/SelectField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { ClienteRow } from "@/src/components/pedido/types";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type ItemVenda = {
  id_mov: number; comanda: number; data: string; cliente: number | null; cliente_nome: string;
  codigo: string; descricao: string; qtd: number; qtd_disponivel: number; p_unit: number;
};
type Motivo = { codigo: number; descricao: string };
type DevolucaoRow = {
  id_devolucao: number; id_mov: number; comanda: number; data: string; cliente_nome: string;
  descricao: string; qtd_devolvida: number; valor: number; motivo: string;
  vale_devolucao: number | null; vale_situacao: string | null;
};

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "Buscar", texto: "Procura itens de vendas já PAGAS que ainda podem ser devolvidos (com saldo disponível). Filtre por data, cupom, NFC-e, NF, comanda, cliente ou produto.", icon: { lib: "ion", name: "search" } },
  { titulo: "Selecionar item", texto: "Marque o item, informe a quantidade a devolver (não pode passar do saldo disponível) e o motivo (Normal ou Defeito).", icon: { lib: "ion", name: "checkbox-outline" } },
  { titulo: "Emitir Vale de Devolução", texto: "Gera um crédito no valor total devolvido, em nome do cliente escolhido — pode ser usado como forma de pagamento numa venda futura.", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Registrar Devolução", texto: "Grava a devolução dos itens marcados. Não emite Nota Fiscal de devolução nem devolve estoque automaticamente — isso continua sendo feito à parte, no Recebimento de Mercadoria.", icon: { lib: "ion", name: "checkmark-done-outline" } },
  { titulo: "Consulta", texto: "Lista devoluções já registradas. Cancelar uma devolução também cancela o Vale vinculado, se houver — só é possível enquanto não tiver NF de devolução vinculada.", icon: { lib: "ion", name: "list-outline" } },
];

export default function DevolucaoScreen() {
  const router = useRouter();
  const { can, moduleOn, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [aba, setAba] = useState<"buscar" | "consulta">("buscar");
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [motivos, setMotivos] = useState<Motivo[]>([]);

  const [dataIni, setDataIni] = useState<string | null>(null);
  const [dataFim, setDataFim] = useState<string | null>(null);
  const [comanda, setComanda] = useState("");
  const [cupom, setCupom] = useState("");
  const [nfce, setNfce] = useState("");
  const [nf, setNf] = useState("");
  const [cliente, setCliente] = useState("");
  const [produto, setProduto] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [itensEncontrados, setItensEncontrados] = useState<ItemVenda[]>([]);

  const [selecao, setSelecao] = useState<Record<number, { qtd: string; motivo: number }>>({});
  const [emitirVale, setEmitirVale] = useState(false);
  const [clienteVale, setClienteVale] = useState<{ codigo: number; nome: string } | null>(null);
  const [buscarClienteOpen, setBuscarClienteOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [registrando, setRegistrando] = useState(false);

  const [consultaDataIni, setConsultaDataIni] = useState<string | null>(null);
  const [consultaDataFim, setConsultaDataFim] = useState<string | null>(null);
  const [consultaCliente, setConsultaCliente] = useState("");
  const [consultaComanda, setConsultaComanda] = useState("");
  const [buscandoConsulta, setBuscandoConsulta] = useState(false);
  const [devolucoes, setDevolucoes] = useState<DevolucaoRow[]>([]);

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

  useEffect(() => {
    if (!conn) return;
    apiGet(conn, "/api/devolucao/motivos").then((j) => { if (j?.success) setMotivos(j.items || []); }).catch(() => {});
  }, [conn]);

  useEffect(() => {
    if (!buscarClienteOpen || !conn) return;
    const t = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const j = await apiGet(conn, "/api/clientes/find/search", { term: searchTerm });
        setSearchResults(j?.items || []);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [searchTerm, buscarClienteOpen, conn]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setBuscando(true);
    try {
      const j = await apiSend(conn, "/api/devolucao/buscar-itens", "POST", {
        data_ini: dataIni, data_fim: dataFim,
        comanda: comanda ? parseInt(comanda, 10) : null,
        cupom: cupom ? parseInt(cupom, 10) : null,
        nfce: nfce ? parseInt(nfce, 10) : null,
        nf: nf ? parseInt(nf, 10) : null,
        cliente: cliente.trim() || null, produto: produto.trim() || null,
      });
      if (j?.success) {
        setItensEncontrados(j.items || []);
        setSelecao({});
        if ((j.items || []).length === 0) feedback.showInfo("Nenhum item elegível para devolução encontrado.");
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, dataIni, dataFim, comanda, cupom, nfce, nf, cliente, produto, feedback]);

  const toggleItem = useCallback((it: ItemVenda) => {
    setSelecao((prev) => {
      const next = { ...prev };
      if (next[it.id_mov]) {
        delete next[it.id_mov];
      } else {
        next[it.id_mov] = { qtd: String(it.qtd_disponivel), motivo: motivos[0]?.codigo ?? 1 };
        if (!clienteVale && it.cliente) setClienteVale({ codigo: it.cliente, nome: it.cliente_nome });
      }
      return next;
    });
  }, [motivos, clienteVale]);

  const valorTotalSelecionado = itensEncontrados.reduce((s, it) => {
    const sel = selecao[it.id_mov];
    if (!sel) return s;
    const qtd = parseFloat(sel.qtd.replace(",", ".")) || 0;
    return s + qtd * it.p_unit;
  }, 0);

  const registrar = useCallback(async () => {
    if (!conn) return;
    const idsSelecionados = Object.keys(selecao).map((k) => parseInt(k, 10));
    if (idsSelecionados.length === 0) {
      feedback.showError("Selecione ao menos um item para devolver.");
      return;
    }
    if (emitirVale && !clienteVale) {
      feedback.showError("Escolha o cliente que vai receber o Vale de Devolução.");
      return;
    }
    setRegistrando(true);
    try {
      const itens = idsSelecionados.map((id_mov) => ({
        id_mov,
        qtd_devolvida: parseFloat((selecao[id_mov].qtd || "0").replace(",", ".")) || 0,
        motivo: selecao[id_mov].motivo,
      }));
      const j = await apiSend(conn, "/api/devolucao/registrar", "POST", {
        itens, emitir_vale: emitirVale, cliente: emitirVale ? clienteVale?.codigo : null,
        master: masterPerm, classe: classePerm, usuario_alteracao: usuarioCod, plataforma: "web",
      });
      if (j?.success) {
        feedback.showSuccess(
          `Devolução registrada — valor total ${formatBRL(j.valor_total)}.`
          + (j.vale_devolucao ? ` Vale de Devolução #${j.vale_devolucao} emitido.` : ""),
          undefined, 5000,
        );
        setItensEncontrados([]);
        setSelecao({});
        setEmitirVale(false);
        setClienteVale(null);
      } else {
        feedback.showError(friendlyApiError(j, "Não foi possível registrar a devolução."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setRegistrando(false);
    }
  }, [conn, selecao, emitirVale, clienteVale, masterPerm, classePerm, usuarioCod, feedback]);

  const buscarConsulta = useCallback(async () => {
    if (!conn) return;
    setBuscandoConsulta(true);
    try {
      const j = await apiSend(conn, "/api/devolucao/consulta", "POST", {
        data_ini: consultaDataIni, data_fim: consultaDataFim,
        cliente: consultaCliente.trim() || null,
        comanda: consultaComanda ? parseInt(consultaComanda, 10) : null,
      });
      if (j?.success) setDevolucoes(j.items || []);
      else feedback.showError(friendlyApiError(j, "Não foi possível consultar."));
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscandoConsulta(false);
    }
  }, [conn, consultaDataIni, consultaDataFim, consultaCliente, consultaComanda, feedback]);

  const cancelarDevolucao = useCallback((row: DevolucaoRow) => {
    if (!conn) return;
    feedback.showConfirm(
      `Cancelar a devolução do item "${row.descricao}"?` + (row.vale_devolucao ? " O Vale de Devolução vinculado também será cancelado." : ""),
      async () => {
        try {
          const j = await apiSend(conn, `/api/devolucao/${row.id_devolucao}/cancelar`, "POST", {
            master: masterPerm, classe: classePerm, usuario_alteracao: usuarioCod, plataforma: "web",
          });
          if (j?.success) {
            feedback.showSuccess("Devolução cancelada.");
            buscarConsulta();
          } else {
            feedback.showError(friendlyApiError(j, "Não foi possível cancelar."));
          }
        } catch (e) {
          feedback.showError(friendlyCatchError(e));
        }
      },
    );
  }, [conn, masterPerm, classePerm, usuarioCod, feedback, buscarConsulta]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gestor de Devolução está disponível apenas no web." testID="devolucao-web-only" />;
  }
  if (!loading && !can("DEVOLUCAO.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Gestor de Devolução." testID="devolucao-locked" />;
  }
  if (!loading && !moduleOn("devolucao")) {
    return <LockedView title="Módulo desativado" message="Módulo Gestor de Devolução está desativado em Configurações do Sistema > Módulos e Recursos." testID="devolucao-module-off" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="devolucao-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Gestor de Devolução</Text>
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary}
          onPress={() => setAjudaOpen(true)} testID="devolucao-ajuda-btn"
        />
      </View>

      <View style={{ flexDirection: "row", gap: spacing.sm, padding: spacing.md, backgroundColor: colors.surface, borderBottomWidth: 1, borderBottomColor: colors.border }}>
        <Pressable onPress={() => setAba("buscar")} style={[tabBtnStyle(), aba === "buscar" && tabBtnSelStyle()]} testID="devolucao-tab-buscar">
          <Text style={[tabLabelStyle(), aba === "buscar" && tabLabelSelStyle()]}>Buscar e Registrar</Text>
        </Pressable>
        <Pressable
          onPress={() => { setAba("consulta"); if (devolucoes.length === 0) buscarConsulta(); }}
          style={[tabBtnStyle(), aba === "consulta" && tabBtnSelStyle()]} testID="devolucao-tab-consulta"
        >
          <Text style={[tabLabelStyle(), aba === "consulta" && tabLabelSelStyle()]}>Consulta</Text>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : aba === "buscar" ? (
            <View style={{ gap: spacing.md }}>
              <View style={WEB_FILTER_CARD}>
                <Text style={labelStyle()}>Filtros</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                  <View style={{ width: 160 }}>
                    <Text style={fieldLabel()}>Data De</Text>
                    <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="devolucao-data-ini" />
                  </View>
                  <View style={{ width: 160 }}>
                    <Text style={fieldLabel()}>Data Até</Text>
                    <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="devolucao-data-fim" />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>Comanda</Text>
                    <TextInput value={comanda} onChangeText={setComanda} keyboardType="numeric" style={inputStyle()} testID="devolucao-comanda" />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>Cupom</Text>
                    <TextInput value={cupom} onChangeText={setCupom} keyboardType="numeric" style={inputStyle()} testID="devolucao-cupom" />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>NFC-e</Text>
                    <TextInput value={nfce} onChangeText={setNfce} keyboardType="numeric" style={inputStyle()} testID="devolucao-nfce" />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>NF</Text>
                    <TextInput value={nf} onChangeText={setNf} keyboardType="numeric" style={inputStyle()} testID="devolucao-nf" />
                  </View>
                  <View style={{ width: 200 }}>
                    <Text style={fieldLabel()}>Cliente (código, CNPJ ou nome)</Text>
                    <TextInput value={cliente} onChangeText={setCliente} style={inputStyle()} testID="devolucao-cliente" />
                  </View>
                  <View style={{ width: 200 }}>
                    <Text style={fieldLabel()}>Produto (código ou descrição)</Text>
                    <TextInput value={produto} onChangeText={setProduto} style={inputStyle()} testID="devolucao-produto" />
                  </View>
                  <Pressable onPress={buscar} disabled={buscando} style={[primaryBtnStyle(), { alignSelf: "flex-end" }]} testID="devolucao-buscar-btn">
                    {buscando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                      <>
                        <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                        <Text style={primaryBtnLabelStyle()}>Buscar</Text>
                      </>
                    )}
                  </Pressable>
                </View>
              </View>

              {itensEncontrados.length > 0 ? (
                <View style={WEB_FILTER_CARD}>
                  <Text style={labelStyle()}>Itens Encontrados ({itensEncontrados.length})</Text>
                  {itensEncontrados.map((it) => {
                    const sel = selecao[it.id_mov];
                    return (
                      <View key={it.id_mov} style={itemRowStyle()}>
                        <Pressable onPress={() => toggleItem(it)} hitSlop={8} style={{ paddingRight: spacing.sm }} testID={`devolucao-item-check-${it.id_mov}`}>
                          <Ionicons name={sel ? "checkbox" : "square-outline"} size={22} color={sel ? colors.brandPrimary : colors.muted} />
                        </Pressable>
                        <View style={{ flex: 1 }}>
                          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{it.descricao}</Text>
                          <Text style={{ fontSize: 12, color: colors.muted }}>
                            Comanda {it.comanda} · {formatDateBR(it.data)} · {it.cliente_nome} · disponível: {it.qtd_disponivel} × {formatBRL(it.p_unit)}
                          </Text>
                        </View>
                        {sel ? (
                          <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                            <View style={{ width: 80 }}>
                              <Text style={fieldLabel()}>Qtd Dev.</Text>
                              <TextInput
                                value={sel.qtd}
                                onChangeText={(v) => setSelecao((prev) => ({ ...prev, [it.id_mov]: { ...prev[it.id_mov], qtd: v } }))}
                                keyboardType="numeric"
                                style={inputStyle()}
                                testID={`devolucao-item-qtd-${it.id_mov}`}
                              />
                            </View>
                            <View style={{ width: 160 }}>
                              <Text style={fieldLabel()}>Motivo</Text>
                              <SelectField
                                value={sel.motivo}
                                onChange={(v) => setSelecao((prev) => ({ ...prev, [it.id_mov]: { ...prev[it.id_mov], motivo: Number(v) } }))}
                                options={motivos.map((m) => ({ value: m.codigo, label: m.descricao }))}
                                compactWeb
                                searchable={false}
                                testID={`devolucao-item-motivo-${it.id_mov}`}
                              />
                            </View>
                          </View>
                        ) : null}
                      </View>
                    );
                  })}

                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.md, paddingTop: spacing.md, borderTopWidth: 1, borderTopColor: colors.border }}>
                    <Pressable onPress={() => setEmitirVale((v) => !v)} hitSlop={8} style={{ flexDirection: "row", alignItems: "center", gap: 6 }} testID="devolucao-emitir-vale-toggle">
                      <Ionicons name={emitirVale ? "checkbox" : "square-outline"} size={20} color={emitirVale ? colors.brandPrimary : colors.muted} />
                      <Text style={{ fontSize: 13, color: colors.onSurface }}>Emitir Vale de Devolução</Text>
                    </Pressable>
                    {emitirVale ? (
                      <Pressable onPress={() => { setSearchTerm(""); setSearchResults([]); setBuscarClienteOpen(true); }} style={{ flexDirection: "row", alignItems: "center", gap: 4 }} testID="devolucao-cliente-vale-btn">
                        <Ionicons name="person-outline" size={16} color={colors.brandPrimary} />
                        <Text style={{ fontSize: 13, color: colors.brandPrimary, fontWeight: "600" }}>
                          {clienteVale ? clienteVale.nome : "Escolher cliente"}
                        </Text>
                      </Pressable>
                    ) : null}
                    <View style={{ flex: 1 }} />
                    <Text style={{ fontSize: 15, fontWeight: "700", color: colors.brandPrimary }}>
                      Total: {formatBRL(valorTotalSelecionado)}
                    </Text>
                  </View>

                  {can("DEVOLUCAO.REGISTRAR") ? (
                    <Pressable
                      onPress={registrar}
                      disabled={registrando || Object.keys(selecao).length === 0}
                      style={[primaryBtnStyle(), { alignSelf: "flex-start", marginTop: spacing.sm }, Object.keys(selecao).length === 0 && { opacity: 0.5 }]}
                      testID="devolucao-registrar-btn"
                    >
                      {registrando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                        <>
                          <Ionicons name="checkmark-done-outline" size={16} color={colors.onBrandPrimary} />
                          <Text style={primaryBtnLabelStyle()}>Registrar Devolução</Text>
                        </>
                      )}
                    </Pressable>
                  ) : null}
                </View>
              ) : null}
            </View>
          ) : (
            <View style={{ gap: spacing.md }}>
              <View style={WEB_FILTER_CARD}>
                <Text style={labelStyle()}>Filtros</Text>
                <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                  <View style={{ width: 160 }}>
                    <Text style={fieldLabel()}>Data De</Text>
                    <WebDateField value={consultaDataIni} onChange={(v) => { setConsultaDataIni(v || null); if (v) setConsultaDataFim(v); }} testID="devolucao-consulta-data-ini" />
                  </View>
                  <View style={{ width: 160 }}>
                    <Text style={fieldLabel()}>Data Até</Text>
                    <WebDateField value={consultaDataFim} onChange={(v) => setConsultaDataFim(v || null)} testID="devolucao-consulta-data-fim" />
                  </View>
                  <View style={{ width: 110 }}>
                    <Text style={fieldLabel()}>Comanda</Text>
                    <TextInput value={consultaComanda} onChangeText={setConsultaComanda} keyboardType="numeric" style={inputStyle()} testID="devolucao-consulta-comanda" />
                  </View>
                  <View style={{ width: 200 }}>
                    <Text style={fieldLabel()}>Cliente</Text>
                    <TextInput value={consultaCliente} onChangeText={setConsultaCliente} style={inputStyle()} testID="devolucao-consulta-cliente" />
                  </View>
                  <Pressable onPress={buscarConsulta} disabled={buscandoConsulta} style={[primaryBtnStyle(), { alignSelf: "flex-end" }]} testID="devolucao-consulta-buscar-btn">
                    {buscandoConsulta ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                      <>
                        <Ionicons name="search" size={16} color={colors.onBrandPrimary} />
                        <Text style={primaryBtnLabelStyle()}>Buscar</Text>
                      </>
                    )}
                  </Pressable>
                </View>
              </View>

              <View style={WEB_FILTER_CARD}>
                <Text style={labelStyle()}>Devoluções ({devolucoes.length})</Text>
                {devolucoes.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhuma devolução encontrada.</Text>
                ) : (
                  devolucoes.map((row) => (
                    <View key={row.id_devolucao} style={itemRowStyle()}>
                      <View style={{ flex: 1 }}>
                        <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{row.descricao}</Text>
                        <Text style={{ fontSize: 12, color: colors.muted }}>
                          Comanda {row.comanda} · {formatDateBR(row.data)} · {row.cliente_nome} · {row.motivo} · Qtd {row.qtd_devolvida}
                          {row.vale_devolucao ? ` · Vale #${row.vale_devolucao} (${row.vale_situacao === "C" ? "Cancelado" : "Ativo"})` : ""}
                        </Text>
                      </View>
                      <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface, marginRight: spacing.sm }}>{formatBRL(row.valor)}</Text>
                      {can("DEVOLUCAO.CANCELAR") ? (
                        <IconButtonWithTooltip
                          icon="close-circle-outline" label="Cancelar devolução" size={20} color={colors.error}
                          onPress={() => cancelarDevolucao(row)} testID={`devolucao-cancelar-${row.id_devolucao}`}
                        />
                      ) : null}
                    </View>
                  ))
                )}
              </View>
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Gestor de Devolução" itens={AJUDA_ITENS} />
      <ClientSearchModal
        visible={buscarClienteOpen}
        onClose={() => setBuscarClienteOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => { if (c) setClienteVale({ codigo: c.codigo, nome: c.nome }); setBuscarClienteOpen(false); }}
        onCreate={() => setBuscarClienteOpen(false)}
      />
    </SafeAreaView>
  );
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
function tabBtnStyle() {
  return { paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border };
}
function tabBtnSelStyle() {
  return { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary };
}
function tabLabelStyle() {
  return { fontSize: 13, fontWeight: "700" as const, color: colors.onSurface };
}
function tabLabelSelStyle() {
  return { color: colors.onBrandPrimary };
}
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5, marginBottom: spacing.xs };
}
function fieldLabel() {
  return { fontSize: 11, color: colors.muted, marginBottom: 4, fontWeight: "500" as const };
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
    flexDirection: "row" as const, alignItems: "center" as const, gap: spacing.sm,
    paddingVertical: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border,
  };
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
