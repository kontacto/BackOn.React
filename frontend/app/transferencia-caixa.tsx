// Transferência p/Fluxo de Caixa (Financeiro) — migração de
// `Geral\FrmTransfCaixa.frm` (caption real "Transferência para o Fluxo de
// Caixa..."). Tela IRMÃ de transferencia-contas.tsx, mas com papel bem
// diferente: aquela promove NF/Comanda pro Contas a Pagar/Receber; esta
// pega o que JÁ está em Contas a Pagar/Receber (Previsões ainda abertas,
// ou Movimentações já baixadas) e lança de fato no Fluxo de Caixa —
// Previsões não mexem no saldo da conta (é só um forecast), Movimentações
// e Entrada/Saída de Caixa mexem de verdade. Ver PENDENCIAS.md >
// "Transferência para o Fluxo de Caixa" pro rastreio completo (inclusive
// o que ficou de fora — Agrupamento de Comandas, Fase 2).
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { AppModal } from "@/src/components/AppModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import WebDateField from "@/src/components/WebDateField";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatBRL, formatDateBR } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

type Flag = "PrevisaoReceber" | "PrevisaoPagar" | "MovimentacaoReceber" | "MovimentacaoPagar" | "EntradaCaixa" | "SaidaCaixa";

type Pendente = {
  codigo: number; flag: Flag; nome: string;
  num_controle: number | string | null; data_doc: string | null; valor_total: number;
};

type PendenteAgrupada = {
  codigo: number; flag: "MovimentacaoReceberAgrupada"; nome: string;
  forma_pagamento: string; data_doc: string | null; valor_total: number;
};

type FormaPagamento = { codigo: string; descricao: string };

const FLAG_LABEL: Record<Flag, string> = {
  PrevisaoReceber: "Previsão a Receber",
  PrevisaoPagar: "Previsão a Pagar",
  MovimentacaoReceber: "Recebimento",
  MovimentacaoPagar: "Pagamento",
  EntradaCaixa: "Entrada de Caixa",
  SaidaCaixa: "Saída de Caixa",
};

function flagColor(flag: Flag) {
  if (flag === "PrevisaoReceber" || flag === "MovimentacaoReceber" || flag === "EntradaCaixa") return colors.success;
  return colors.error;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const AJUDA_ITENS: HelpItem[] = [
  { titulo: "O que esta tela faz", texto: "Pega o que já está lançado em Contas a Pagar/Receber (ou uma Entrada/Saída de Caixa já registrada) e transfere de fato pro Fluxo de Caixa. Marque os itens e clique em Transferir.", icon: { lib: "ion", name: "swap-horizontal-outline" } },
  { titulo: "Previsão (a Receber/a Pagar)", texto: "Título ainda em aberto (não pago). Transferir cria só um LEMBRETE no Fluxo de Caixa — não mexe no saldo da conta, é uma previsão do que ainda vai acontecer.", icon: { lib: "ion", name: "calendar-outline" } },
  { titulo: "Recebimento / Pagamento", texto: "Título já baixado (pago/recebido). Transferir lança o movimento real e MUDA o saldo da conta escolhida — este é o passo que faz o dinheiro aparecer/sair de verdade do Fluxo de Caixa.", icon: { lib: "ion", name: "cash-outline" } },
  { titulo: "Entrada / Saída de Caixa", texto: "Um lançamento manual de caixa já registrado (fora de Pedido/O.S.), ainda não transferido pro Fluxo de Caixa.", icon: { lib: "ion", name: "wallet-outline" } },
  { titulo: "Comandas Agrupadas", texto: "Aparece só quando o Agrupamento de Comandas está configurado (ícone de engrenagem no topo). Várias comandas do mesmo dia + mesma forma de pagamento (dinheiro, cartão, etc.) viram UM lançamento só no Fluxo de Caixa, em vez de um lançamento por comanda — mais fácil de conferir no extrato do banco/caixa.", icon: { lib: "ion", name: "layers-outline" } },
  { titulo: "Configurar Agrupamento (engrenagem)", texto: "Escolhe quais tipos de cliente (Consumidor sem cadastro específico, CPF, CNPJ, Clientes Diversos) e quais formas de pagamento entram no agrupamento. Sem nenhuma forma marcada, o agrupamento fica desligado e toda comanda aparece separada, como hoje.", icon: { lib: "ion", name: "options-outline" } },
  { titulo: "Todos em Aberto x Período", texto: "\"Todos em Aberto\" traz tudo que ainda não foi transferido, sem filtrar data. \"Período\" restringe pela data de vencimento (Previsões) ou de pagamento (Recebimento/Pagamento).", icon: { lib: "ion", name: "filter-outline" } },
  { titulo: "Depois de transferir", texto: "O item sai desta lista — não tem \"desfazer\" por aqui. Um erro só é corrigido direto no Fluxo de Caixa/Contas já lançado.", icon: { lib: "ion", name: "alert-circle-outline" } },
];

function resumirFalhas(falhas: { codigo: number; message: string }[]): string {
  const grupos = new Map<string, number[]>();
  for (const f of falhas) {
    const lista = grupos.get(f.message) || [];
    lista.push(f.codigo);
    grupos.set(f.message, lista);
  }
  return Array.from(grupos.entries())
    .map(([mensagem, codigos]) => `${codigos.length}x (${codigos.join(", ")}): ${mensagem}`)
    .join("\n\n");
}

export default function TransferenciaCaixaScreen() {
  const router = useRouter();
  const { can, isMaster: masterPerm, classe: classePerm } = usePermissions();
  const feedback = useFeedback();

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [loading, setLoading] = useState(true);
  const [buscando, setBuscando] = useState(false);
  const [transferindo, setTransferindo] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  const [periodo, setPeriodo] = useState(false);
  const [dataIni, setDataIni] = useState<string | null>(todayIso());
  const [dataFim, setDataFim] = useState<string | null>(todayIso());
  const [prevReceber, setPrevReceber] = useState(true);
  const [prevPagar, setPrevPagar] = useState(true);
  const [movReceber, setMovReceber] = useState(true);
  const [movPagar, setMovPagar] = useState(true);
  const [entradaCaixa, setEntradaCaixa] = useState(true);
  const [saidaCaixa, setSaidaCaixa] = useState(true);

  const [itens, setItens] = useState<Pendente[]>([]);
  const [selecionados, setSelecionados] = useState<Record<string, boolean>>({});

  // Fase 2 — Agrupamento de Comandas.
  const [agrupamentoAtivo, setAgrupamentoAtivo] = useState(false);
  const [agrupadas, setAgrupadas] = useState<PendenteAgrupada[]>([]);
  const [selecionadosAgrupadas, setSelecionadosAgrupadas] = useState<Record<number, boolean>>({});
  const [transferindoAgrupadas, setTransferindoAgrupadas] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

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

  const chave = (it: Pendente) => `${it.flag}-${it.codigo}`;

  const buscar = useCallback(async () => {
    if (!conn) return;
    if (!prevReceber && !prevPagar && !movReceber && !movPagar && !entradaCaixa && !saidaCaixa) {
      feedback.showWarning("Defina o que vai ser transferido.");
      return;
    }
    if (periodo && (!dataIni || !dataFim)) {
      feedback.showWarning("Defina o período corretamente.");
      return;
    }
    setBuscando(true);
    try {
      const qs = new URLSearchParams({
        servidor: conn.servidor, banco: conn.banco,
        periodo: String(periodo), data_ini: dataIni || "", data_fim: dataFim || "",
        prev_receber: String(prevReceber), prev_pagar: String(prevPagar),
        mov_receber: String(movReceber), mov_pagar: String(movPagar),
        entrada_caixa: String(entradaCaixa), saida_caixa: String(saidaCaixa),
      });
      const resp = await fetch(`${conn.api}/api/transferencia-caixa/pendentes?${qs.toString()}`);
      const j = await resp.json();
      if (j?.success) {
        const carregados: Pendente[] = j.items || [];
        setItens(carregados);
        const todosMarcados: Record<string, boolean> = {};
        for (const it of carregados) todosMarcados[chave(it)] = true;
        setSelecionados(todosMarcados);

        const carregadasAgrupadas: PendenteAgrupada[] = j.agrupadas || [];
        setAgrupamentoAtivo(!!j.agrupamento_ativo);
        setAgrupadas(carregadasAgrupadas);
        const todasAgrupadasMarcadas: Record<number, boolean> = {};
        for (const a of carregadasAgrupadas) todasAgrupadasMarcadas[a.codigo] = true;
        setSelecionadosAgrupadas(todasAgrupadasMarcadas);

        if (carregados.length === 0 && carregadasAgrupadas.length === 0) feedback.showWarning("Nenhum registro encontrado.");
      } else {
        setItens([]);
        setSelecionados({});
        setAgrupadas([]);
        setSelecionadosAgrupadas({});
        feedback.showError(friendlyApiError(j, "Não foi possível buscar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setBuscando(false);
    }
  }, [conn, periodo, dataIni, dataFim, prevReceber, prevPagar, movReceber, movPagar, entradaCaixa, saidaCaixa, feedback]);

  useEffect(() => {
    if (conn) buscar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const toggleItem = (it: Pendente) => {
    const k = chave(it);
    setSelecionados((prev) => ({ ...prev, [k]: !prev[k] }));
  };
  const marcarTodos = (valor: boolean) => {
    const next: Record<string, boolean> = {};
    for (const it of itens) next[chave(it)] = valor;
    setSelecionados(next);
  };

  const qtdSelecionados = Object.values(selecionados).filter(Boolean).length;
  const valorSelecionado = itens.filter((it) => selecionados[chave(it)]).reduce((s, it) => s + it.valor_total, 0);

  const transferir = useCallback(async () => {
    if (!conn) return;
    const marcados = itens.filter((it) => selecionados[chave(it)]);
    if (marcados.length === 0) {
      feedback.showError("Selecione ao menos um item para transferir.");
      return;
    }
    setTransferindo(true);
    try {
      const j = await apiSend(conn, "/api/transferencia-caixa/transferir", "POST", {
        itens: marcados.map((it) => ({ codigo: it.codigo, flag: it.flag })),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      const transferidos: number[] = j?.transferidos || [];
      const falhas: { codigo: number; message: string }[] = j?.falhas || [];
      if (transferidos.length > 0) {
        feedback.showSuccess(
          `${transferidos.length} item(ns) transferido(s) com sucesso.`
          + (falhas.length > 0 ? ` ${falhas.length} falharam.` : ""),
          undefined, 5000,
        );
      }
      if (falhas.length > 0) {
        const resumo = resumirFalhas(falhas);
        if (transferidos.length === 0) feedback.showError(resumo, undefined, 5000);
        else feedback.showWarning(`Falhas: ${resumo}`, undefined, 5000);
      }
      buscar();
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setTransferindo(false);
    }
  }, [conn, itens, selecionados, usuarioCod, classePerm, feedback, buscar]);

  const qtdSelecionadasAgrupadas = Object.values(selecionadosAgrupadas).filter(Boolean).length;
  const valorSelecionadoAgrupadas = agrupadas
    .filter((a) => selecionadosAgrupadas[a.codigo])
    .reduce((s, a) => s + a.valor_total, 0);
  const marcarTodasAgrupadas = (valor: boolean) => {
    const next: Record<number, boolean> = {};
    for (const a of agrupadas) next[a.codigo] = valor;
    setSelecionadosAgrupadas(next);
  };

  const transferirAgrupadas = useCallback(async () => {
    if (!conn) return;
    const marcadas = agrupadas.filter((a) => selecionadosAgrupadas[a.codigo]);
    if (marcadas.length === 0) {
      feedback.showError("Selecione ao menos uma comanda para transferir.");
      return;
    }
    setTransferindoAgrupadas(true);
    try {
      const j = await apiSend(conn, "/api/transferencia-caixa/transferir-agrupadas", "POST", {
        itens: marcadas.map((a) => a.codigo),
        usuario_alteracao: usuarioCod, classe: classePerm, plataforma: "web",
      });
      const transferidos: number[] = j?.transferidos || [];
      const falhas: { codigo: number; message: string }[] = j?.falhas || [];
      if (transferidos.length > 0) {
        feedback.showSuccess(
          `${transferidos.length} comanda(s) transferida(s) agrupadas com sucesso.`
          + (falhas.length > 0 ? ` ${falhas.length} falharam.` : ""),
          undefined, 5000,
        );
      }
      if (falhas.length > 0) {
        const resumo = resumirFalhas(falhas);
        if (transferidos.length === 0) feedback.showError(resumo, undefined, 5000);
        else feedback.showWarning(`Falhas: ${resumo}`, undefined, 5000);
      }
      buscar();
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setTransferindoAgrupadas(false);
    }
  }, [conn, agrupadas, selecionadosAgrupadas, usuarioCod, classePerm, feedback, buscar]);

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Transferência p/Fluxo de Caixa está disponível apenas no web." testID="transferencia-caixa-web-only" />;
  }
  if (!loading && !can("TRANSF_CAIXA.ABRIR") && !masterPerm) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar a Transferência p/Fluxo de Caixa." testID="transferencia-caixa-locked" />;
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.surface }} edges={["top"]} testID="transferencia-caixa-screen">
      <View style={headerStyle()}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={{ padding: 4 }}>
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={headerTitleStyle()} numberOfLines={1}>Transferência p/Fluxo de Caixa</Text>
        {can("TRANSF_CAIXA.CONFIG_AGRUP") || masterPerm ? (
          <IconButtonWithTooltip
            icon="options-outline" label="Configurar Agrupamento de Comandas" color={colors.onBrandPrimary}
            onPress={() => setConfigOpen(true)} testID="transferencia-caixa-config-agrupamento-btn"
          />
        ) : null}
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary}
          onPress={() => setAjudaOpen(true)} testID="transferencia-caixa-ajuda-btn"
        />
      </View>

      <ScrollView contentContainerStyle={[{ padding: spacing.lg }, WEB_SCROLL_CENTER]}>
        <View style={WEB_CONTENT_SHELL}>
          {loading ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
          ) : (
            <View style={{ gap: spacing.md }}>
              <View style={WEB_FILTER_CARD}>
                <View style={{ flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" }}>
                  <Pressable onPress={() => setPeriodo(false)} style={radioRowStyle()} testID="transferencia-caixa-todos-aberto">
                    <Ionicons name={!periodo ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={radioLabelStyle()}>Todos em Aberto</Text>
                  </Pressable>
                  <Pressable onPress={() => setPeriodo(true)} style={radioRowStyle()} testID="transferencia-caixa-por-periodo">
                    <Ionicons name={periodo ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={radioLabelStyle()}>Período</Text>
                  </Pressable>
                  {periodo ? (
                    <View style={{ flexDirection: "row", gap: spacing.sm, alignItems: "center" }}>
                      <View style={{ width: 150 }}>
                        <WebDateField value={dataIni} onChange={(v) => { setDataIni(v || null); if (v) setDataFim(v); }} testID="transferencia-caixa-data-ini" />
                      </View>
                      <Text style={{ color: colors.muted }}>até</Text>
                      <View style={{ width: 150 }}>
                        <WebDateField value={dataFim} onChange={(v) => setDataFim(v || null)} testID="transferencia-caixa-data-fim" />
                      </View>
                    </View>
                  ) : null}
                </View>

                <Text style={[labelStyle(), { marginTop: spacing.md, marginBottom: 6 }]}>Previsões</Text>
                <View style={{ flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" }}>
                  <CheckboxRow label="Contas a Receber" checked={prevReceber} onToggle={() => setPrevReceber((v) => !v)} testID="transferencia-caixa-check-prev-receber" />
                  <CheckboxRow label="Contas a Pagar" checked={prevPagar} onToggle={() => setPrevPagar((v) => !v)} testID="transferencia-caixa-check-prev-pagar" />
                </View>

                <Text style={[labelStyle(), { marginTop: spacing.md, marginBottom: 6 }]}>Movimentações</Text>
                <View style={{ flexDirection: "row", gap: spacing.lg, flexWrap: "wrap" }}>
                  <CheckboxRow label="Contas a Receber" checked={movReceber} onToggle={() => setMovReceber((v) => !v)} testID="transferencia-caixa-check-mov-receber" />
                  <CheckboxRow label="Contas a Pagar" checked={movPagar} onToggle={() => setMovPagar((v) => !v)} testID="transferencia-caixa-check-mov-pagar" />
                  <CheckboxRow label="Entradas de Caixa" checked={entradaCaixa} onToggle={() => setEntradaCaixa((v) => !v)} testID="transferencia-caixa-check-entrada" />
                  <CheckboxRow label="Saídas de Caixa" checked={saidaCaixa} onToggle={() => setSaidaCaixa((v) => !v)} testID="transferencia-caixa-check-saida" />
                </View>

                <Pressable onPress={buscar} disabled={buscando} style={[secondaryBtnStyle(), { alignSelf: "flex-start", marginTop: spacing.md }]} testID="transferencia-caixa-selecionar-btn">
                  {buscando ? <ActivityIndicator color={colors.brandPrimary} size="small" /> : (
                    <>
                      <Ionicons name="search-outline" size={16} color={colors.brandPrimary} />
                      <Text style={secondaryBtnLabelStyle()}>Selecionar</Text>
                    </>
                  )}
                </Pressable>
              </View>

              <View style={WEB_FILTER_CARD}>
                <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Registros para Transferência ({itens.length})</Text>
                {itens.length > 0 ? (
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.md, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Pressable onPress={() => marcarTodos(true)} style={miniBtnStyle()} testID="transferencia-caixa-marcar-todos">
                      <Text style={miniBtnLabelStyle()}>Marcar todos</Text>
                    </Pressable>
                    <Pressable onPress={() => marcarTodos(false)} style={miniBtnStyle()} testID="transferencia-caixa-desmarcar-todos">
                      <Text style={miniBtnLabelStyle()}>Desmarcar todos</Text>
                    </Pressable>
                    <View style={{ flex: 1 }} />
                    <Text style={{ fontSize: 13, color: colors.muted }}>{qtdSelecionados} selecionado(s)</Text>
                    <Text style={{ fontSize: 15, fontWeight: "700", color: colors.brandPrimary }}>Total: {formatBRL(valorSelecionado)}</Text>
                    {can("TRANSF_CAIXA.TRANSFERIR") ? (
                      <Pressable
                        onPress={transferir}
                        disabled={transferindo || qtdSelecionados === 0}
                        style={[primaryBtnStyle(), qtdSelecionados === 0 && { opacity: 0.5 }]}
                        testID="transferencia-caixa-transferir-btn"
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

                {itens.length === 0 ? (
                  <Text style={{ color: colors.muted, fontSize: 13, paddingVertical: spacing.sm }}>Nenhum registro pendente de transferência.</Text>
                ) : (
                  itens.map((it) => {
                    const k = chave(it);
                    const sel = !!selecionados[k];
                    return (
                      <Pressable key={k} onPress={() => toggleItem(it)} style={itemRowStyle()} testID={`transferencia-caixa-item-${k}`}>
                        <Ionicons name={sel ? "checkbox" : "square-outline"} size={22} color={sel ? colors.brandPrimary : colors.muted} />
                        <View style={{ flex: 1, marginLeft: spacing.sm }}>
                          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>
                            {it.nome || "(sem nome)"}
                            {it.num_controle != null ? `  ·  Nº ${it.num_controle}` : ""}
                          </Text>
                          <Text style={{ fontSize: 12, color: colors.muted }}>{formatDateBR(it.data_doc)}</Text>
                        </View>
                        <View style={[flagBadgeStyle(), { backgroundColor: flagColor(it.flag) + "22" }]}>
                          <Text style={[flagBadgeTextStyle(), { color: flagColor(it.flag) }]}>{FLAG_LABEL[it.flag]}</Text>
                        </View>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface, marginLeft: spacing.md, minWidth: 90, textAlign: "right" }}>
                          {formatBRL(it.valor_total)}
                        </Text>
                      </Pressable>
                    );
                  })
                )}
              </View>

              {agrupamentoAtivo && agrupadas.length > 0 ? (
                <View style={WEB_FILTER_CARD}>
                  <Text style={[labelStyle(), { marginBottom: spacing.sm }]}>Comandas Agrupadas ({agrupadas.length})</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap", marginBottom: spacing.md, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border }}>
                    <Pressable onPress={() => marcarTodasAgrupadas(true)} style={miniBtnStyle()} testID="transferencia-caixa-agrupadas-marcar-todos">
                      <Text style={miniBtnLabelStyle()}>Marcar todos</Text>
                    </Pressable>
                    <Pressable onPress={() => marcarTodasAgrupadas(false)} style={miniBtnStyle()} testID="transferencia-caixa-agrupadas-desmarcar-todos">
                      <Text style={miniBtnLabelStyle()}>Desmarcar todos</Text>
                    </Pressable>
                    <View style={{ flex: 1 }} />
                    <Text style={{ fontSize: 13, color: colors.muted }}>{qtdSelecionadasAgrupadas} selecionado(s)</Text>
                    <Text style={{ fontSize: 15, fontWeight: "700", color: colors.brandPrimary }}>Total: {formatBRL(valorSelecionadoAgrupadas)}</Text>
                    {can("TRANSF_CAIXA.TRANSFERIR") ? (
                      <Pressable
                        onPress={transferirAgrupadas}
                        disabled={transferindoAgrupadas || qtdSelecionadasAgrupadas === 0}
                        style={[primaryBtnStyle(), qtdSelecionadasAgrupadas === 0 && { opacity: 0.5 }]}
                        testID="transferencia-caixa-transferir-agrupadas-btn"
                      >
                        {transferindoAgrupadas ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : (
                          <>
                            <Ionicons name="layers-outline" size={16} color={colors.onBrandPrimary} />
                            <Text style={primaryBtnLabelStyle()}>Transferir Comandas Agrupadas</Text>
                          </>
                        )}
                      </Pressable>
                    ) : null}
                  </View>
                  {agrupadas.map((a) => {
                    const sel = !!selecionadosAgrupadas[a.codigo];
                    return (
                      <Pressable
                        key={a.codigo}
                        onPress={() => setSelecionadosAgrupadas((prev) => ({ ...prev, [a.codigo]: !prev[a.codigo] }))}
                        style={itemRowStyle()}
                        testID={`transferencia-caixa-agrupada-item-${a.codigo}`}
                      >
                        <Ionicons name={sel ? "checkbox" : "square-outline"} size={22} color={sel ? colors.brandPrimary : colors.muted} />
                        <View style={{ flex: 1, marginLeft: spacing.sm }}>
                          <Text style={{ fontSize: 14, fontWeight: "600", color: colors.onSurface }}>{a.nome || "(sem nome)"}</Text>
                          <Text style={{ fontSize: 12, color: colors.muted }}>{formatDateBR(a.data_doc)} · {a.forma_pagamento}</Text>
                        </View>
                        <Text style={{ fontSize: 14, fontWeight: "700", color: colors.onSurface, marginLeft: spacing.md, minWidth: 90, textAlign: "right" }}>
                          {formatBRL(a.valor_total)}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : null}
            </View>
          )}
        </View>
      </ScrollView>

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Transferência p/Fluxo de Caixa" itens={AJUDA_ITENS} />
      <AgrupamentoConfigModal visible={configOpen} onClose={() => setConfigOpen(false)} conn={conn} onSaved={buscar} />
    </SafeAreaView>
  );
}

function CheckboxRow({ label, checked, onToggle, testID }: { label: string; checked: boolean; onToggle: () => void; testID?: string }) {
  return (
    <Pressable onPress={onToggle} style={{ flexDirection: "row", alignItems: "center", gap: 6 }} testID={testID}>
      <Ionicons name={checked ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
      <Text style={{ fontSize: 13, color: colors.onSurface }}>{label}</Text>
    </Pressable>
  );
}

// Configuração do Agrupamento de Comandas (`FrmAgrCom.frm`) — quais tipos
// de cliente e formas de pagamento entram no agrupamento (Fase 2). Tier
// "seleção" (560px, mesmo padrão de Modal/Selector Standard) porque tem
// uma lista de formas de pagamento pra rolar, não é só confirmação.
function AgrupamentoConfigModal({ visible, onClose, conn, onSaved }: {
  visible: boolean; onClose: () => void; conn: Connection | null; onSaved: () => void;
}) {
  const feedback = useFeedback();
  const [carregando, setCarregando] = useState(false);
  const [salvando, setSalvando] = useState(false);
  const [clientesDiversos, setClientesDiversos] = useState(false);
  const [semDocumento, setSemDocumento] = useState(false);
  const [cpf, setCpf] = useState(false);
  const [cnpj, setCnpj] = useState(false);
  const [formasDisponiveis, setFormasDisponiveis] = useState<FormaPagamento[]>([]);
  const [formasSelecionadas, setFormasSelecionadas] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!visible || !conn) return;
    (async () => {
      setCarregando(true);
      try {
        const j = await apiGet(conn, "/api/transferencia-caixa/agrupamento/config");
        if (j?.success) {
          setClientesDiversos(!!j.clientes_diversos);
          setSemDocumento(!!j.sem_documento);
          setCpf(!!j.cpf);
          setCnpj(!!j.cnpj);
          setFormasDisponiveis(j.formas_disponiveis || []);
          setFormasSelecionadas(new Set<string>(j.formas || []));
        } else {
          feedback.showError(friendlyApiError(j, "Não foi possível carregar a configuração."));
        }
      } catch (e) {
        feedback.showError(friendlyCatchError(e));
      } finally {
        setCarregando(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, conn]);

  const toggleForma = (codigo: string) => {
    setFormasSelecionadas((prev) => {
      const next = new Set(prev);
      if (next.has(codigo)) next.delete(codigo); else next.add(codigo);
      return next;
    });
  };

  const salvar = async () => {
    if (!conn) return;
    setSalvando(true);
    try {
      const j = await apiSend(conn, "/api/transferencia-caixa/agrupamento/config", "POST", {
        clientes_diversos: clientesDiversos, sem_documento: semDocumento, cpf, cnpj,
        formas: Array.from(formasSelecionadas),
      });
      if (j?.success) {
        feedback.showSuccess("Configuração de Agrupamento de Comandas gravada.");
        onSaved();
        onClose();
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e));
    } finally {
      setSalvando(false);
    }
  };

  return (
    <AppModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={modalBgStyle()}>
        <View style={modalCardStyle()}>
          <View style={modalHeaderStyle()}>
            <Text style={modalTitleStyle()}>Configurar Agrupamento de Comandas</Text>
            <Pressable onPress={onClose} hitSlop={8} testID="transferencia-caixa-config-fechar">
              <Ionicons name="close" size={20} color={colors.onSurface} />
            </Pressable>
          </View>
          {carregando ? (
            <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />
          ) : (
            <ScrollView style={{ maxHeight: 420 }}>
              <Text style={{ fontSize: 12, color: colors.muted, marginBottom: spacing.md }}>
                Comandas destes tipos de cliente, pagas numa das formas marcadas abaixo, viram um único lançamento por dia+forma no Fluxo de Caixa, em vez de um por comanda. Sem nenhuma forma marcada, o agrupamento fica desligado.
              </Text>
              <Text style={[labelStyle(), { marginBottom: 6 }]}>Clientes</Text>
              <View style={{ gap: spacing.sm, marginBottom: spacing.md }}>
                <CheckboxRow label="Clientes Diversos" checked={clientesDiversos} onToggle={() => setClientesDiversos((v) => !v)} testID="transferencia-caixa-config-clientes-diversos" />
                <CheckboxRow label="Sem documento" checked={semDocumento} onToggle={() => setSemDocumento((v) => !v)} testID="transferencia-caixa-config-sem-documento" />
                <CheckboxRow label="CPF" checked={cpf} onToggle={() => setCpf((v) => !v)} testID="transferencia-caixa-config-cpf" />
                <CheckboxRow label="CNPJ" checked={cnpj} onToggle={() => setCnpj((v) => !v)} testID="transferencia-caixa-config-cnpj" />
              </View>
              <Text style={[labelStyle(), { marginBottom: 6 }]}>Formas de Pagamento</Text>
              <View style={{ gap: spacing.sm }}>
                {formasDisponiveis.map((f) => (
                  <CheckboxRow
                    key={f.codigo} label={f.descricao} checked={formasSelecionadas.has(f.codigo)}
                    onToggle={() => toggleForma(f.codigo)} testID={`transferencia-caixa-config-forma-${f.codigo}`}
                  />
                ))}
              </View>
            </ScrollView>
          )}
          <View style={{ flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md }}>
            <Pressable onPress={onClose} style={secondaryBtnStyle()} testID="transferencia-caixa-config-cancelar">
              <Text style={secondaryBtnLabelStyle()}>Cancelar</Text>
            </Pressable>
            <Pressable onPress={salvar} disabled={salvando || carregando} style={[primaryBtnStyle(), (salvando || carregando) && { opacity: 0.6 }]} testID="transferencia-caixa-config-gravar">
              {salvando ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={primaryBtnLabelStyle()}>Gravar</Text>}
            </Pressable>
          </View>
        </View>
      </View>
    </AppModal>
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
function labelStyle() {
  return { fontSize: 12, fontWeight: "700" as const, color: colors.muted, textTransform: "uppercase" as const, letterSpacing: 0.5 };
}
function radioRowStyle() {
  return { flexDirection: "row" as const, alignItems: "center" as const, gap: 6 };
}
function radioLabelStyle() {
  return { fontSize: 13, color: colors.onSurface };
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
function modalBgStyle() {
  return {
    flex: 1, backgroundColor: "rgba(0,0,0,0.45)", alignItems: "center" as const,
    justifyContent: "center" as const, padding: spacing.lg,
  };
}
function modalCardStyle() {
  return {
    width: "100%" as const, maxWidth: 560, alignSelf: "center" as const,
    backgroundColor: colors.surface, borderRadius: radius.lg, borderWidth: 1,
    borderColor: colors.border, padding: spacing.lg,
  };
}
function modalHeaderStyle() {
  return {
    flexDirection: "row" as const, alignItems: "center" as const,
    justifyContent: "space-between" as const, marginBottom: spacing.md,
  };
}
function modalTitleStyle() {
  return { fontSize: 15, fontWeight: "700" as const, color: colors.onSurface };
}
