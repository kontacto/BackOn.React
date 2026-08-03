// Agenda — Lista de horários de um dia específico, por profissional
// (módulo Clínica OU Assistência — mesma tela pros dois, user-directed
// 2026-07-28). Web-only, `moduleOn("CLINICA") || moduleOn("Assistencia")`
// gateado no card de `transacoes.tsx` que traz o usuário até aqui.
//
// Redesenhada 2026-07-28 (user-directed): antes era uma grade semanal (7
// colunas, navegação por "semana anterior/Hoje/próxima semana"); agora é
// Data (calendário) + lista vertical dos horários daquele dia só —
// "a troca de data é feita por um calendar, selecionando o dia disponível
// do Profissional e na lista de horário de agenda daquele dia
// selecionado". A tela também não seleciona mais um profissional
// automaticamente ao carregar (antes escolhia o primeiro da lista) e ganhou
// um filtro por Especialidade pra estreitar a combobox de Profissional —
// filtro OPCIONAL: sem Especialidade escolhida, a combobox lista todo
// profissional habilitado pra Agenda, sem filtro nenhum.
//
// Clique num horário livre abre `AtendimentoAvulsoModal` pra criar um
// atendimento avulso direto naquele profissional/dia/hora; clique num
// horário ocupado abre o mesmo modal em modo edição. Ver
// `agenda_service._list_grade_sync`/`_list_profissionais_agenda_sync` e
// PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
// (Agendamento)".
import { useEffect, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter, useLocalSearchParams } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import AgendaCalendarField from "@/src/components/agenda/AgendaCalendarField";
import { useDiasAtende } from "@/src/hooks/useDiasAtende";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet } from "@/src/utils/api";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import AtendimentoAvulsoModal from "@/src/components/agenda/AtendimentoAvulsoModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import { DIA_SEMANA_LABEL } from "@/src/components/pedido/agendaConstants";
import { formatDateBR } from "@/src/utils/format";

const isWeb = Platform.OS === "web";

// Campos extra (2026-07-28, user-directed — a partir de uma tela de
// referência em VB.NET colada pelo usuário: telefone, "Marcado Por", data
// da marcação, situação do pagamento/Revisão, Encaixe) — já existiam na
// tabela AGENDA, só não eram lidos/exibidos. Ver `agenda_service.
// _list_grade_sync` (backend) pra origem de cada campo.
type SlotAtendimento = {
  codagenda: number; situacao: string; cliente: string; servico: string;
  encaixe: boolean; revisao: boolean; pago: boolean;
  marcado_por: string; data_marcacao: string | null; hora_marcacao: string;
  telefone: string; pedido: number | null;
};
type Slot = { hora: string; status: "livre" | "ocupado" | "pausa" | "ausente"; atendimentos: SlotAtendimento[] | null };
type ResumoDia = { marcados: number; encaixe: number; desistencia: number };

const SITUACAO_COLOR: Record<string, string> = {
  Atendido: colors.success,
  Desistência: colors.error,
  "Não Confirmado": colors.warning,
  Confirmado: colors.brandAccent,
};
// Cor de fallback pras demais das 13 situações de atendimento (Aguardando,
// Em Atendimento, Avaliação, ...) sem entrada própria acima — `brandAccent`
// (azul mais claro), não `brandPrimary` (o mesmo azul-marinho escuro já
// usado na etiqueta "Em Aberto" de Situação do Pagamento — as duas
// etiquetas ficavam idênticas/confundindo lado a lado, user-directed
// 2026-07-28: "troque a cor de fundo da situação").
const SITUACAO_COLOR_FALLBACK = colors.brandAccent;

const AGENDA_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Especialidade",
    texto: "Filtro opcional pra estreitar a lista de Profissional — só mostra quem tem essa especialidade cadastrada. Sem nada escolhido aqui, a combobox de Profissional lista todo mundo habilitado pra Agenda.",
    icon: { lib: "ion", name: "ribbon-outline" },
  },
  {
    titulo: "Profissional",
    texto: "Escolha de quem você quer ver a agenda do dia. Cada profissional tem sua própria grade de horários.",
    icon: { lib: "ion", name: "person-outline" },
  },
  {
    titulo: "Data",
    texto: "Escolha o dia que você quer ver. Só é possível escolher um dia em que o profissional atende — os demais são recusados automaticamente.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Horários Disponíveis",
    texto: "Em vez da lista de um dia só, mostra todo horário livre do profissional nos próximos meses a partir da Data escolhida (quantidade de meses ajustável ao lado). Útil pra achar rápido a primeira vaga livre, sem navegar dia a dia.",
    icon: { lib: "ion", name: "search-outline" },
  },
  {
    titulo: "Horário livre",
    texto: "Clique para marcar um novo atendimento naquele profissional, dia e horário.",
    icon: { lib: "ion", name: "add-circle-outline" },
    cor: colors.success,
  },
  {
    titulo: "Horário ocupado",
    texto: "Mostra o cliente e o serviço já agendados. Clique para abrir o atendimento — ver detalhes, trocar profissional, faturar, etc.",
    icon: { lib: "ion", name: "person-circle-outline" },
  },
  {
    titulo: "Ícone de calendário (junto ao Cliente)",
    texto: "Abre o Pedido de Venda vinculado a este atendimento, quando ele foi marcado a partir de um item de Pedido/Pré-venda.",
    icon: { lib: "ion", name: "receipt-outline" },
  },
  {
    titulo: "Adicionar encaixe neste horário",
    texto: "Marca um atendimento extra no mesmo horário de um já existente, além da capacidade normal do profissional (respeita o limite de encaixe configurado no cadastro dele).",
    icon: { lib: "ion", name: "add-circle-outline" },
    cor: colors.success,
  },
  {
    titulo: "Etiquetas Encaixe / Pago / Revisão",
    texto: "Encaixe: este atendimento foi marcado além da vaga normal daquele horário. Pago: já foi faturado. Revisão: atendimento de garantia/revisão, sem cobrança.",
    icon: { lib: "ion", name: "pricetag-outline" },
  },
  {
    titulo: "Resumo do Dia",
    texto: "Total de atendimentos marcados, quantos são encaixe, e quantos foram cancelados (Desistência) neste dia, para este profissional.",
    icon: { lib: "ion", name: "stats-chart-outline" },
  },
  {
    titulo: "Pausa / Ausente",
    texto: "Horário em que o profissional não atende (intervalo cadastrado ou ausência registrada) — não é possível marcar atendimento nesse horário.",
    icon: { lib: "ion", name: "close-circle-outline" },
    cor: colors.muted,
  },
];

const hojeIso = () => new Date().toISOString().slice(0, 10);

// Etiqueta colorida com tooltip no hover (web) — mesmo padrão visual de
// `IconButtonWithTooltip`, mas pra uma pílula de texto (Situação do
// Atendimento / Situação do Pagamento) em vez de um ícone. Precisa ser um
// componente próprio (não inline dentro do `.map()`) pra poder ter seu
// próprio estado de hover — hooks não podem ser chamados dentro de um
// callback. `onPress` só existe pra dar `stopPropagation`: a etiqueta fica
// dentro do card inteiro, que também é clicável (abre o atendimento).
function BadgeTooltip({ texto, cor, descricao, testID }: { texto: string; cor: string; descricao: string; testID?: string }) {
  const [hover, setHover] = useState(false);
  return (
    <View style={{ position: "relative", zIndex: hover ? 1000 : 1, flexShrink: 0 }}>
      <Pressable
        onPress={(e) => e.stopPropagation()}
        onHoverIn={isWeb ? () => setHover(true) : undefined}
        onHoverOut={isWeb ? () => setHover(false) : undefined}
        style={[styles.badge, { backgroundColor: cor }]}
        testID={testID}
      >
        <Text style={styles.badgeText}>{texto}</Text>
      </Pressable>
      {hover ? (
        <View style={styles.badgeTooltip} pointerEvents="none">
          <Text style={styles.badgeTooltipText}>{descricao}</Text>
        </View>
      ) : null}
    </View>
  );
}

export default function AgendaScreen() {
  const router = useRouter();
  // Abertura direta vinda de um item do Pedido com agendamento vinculado
  // (`ItemList.tsx`'s ícone "Ver na Agenda") — pré-seleciona profissional/
  // data em vez de abrir vazio. User-directed 2026-07-28: "preciso ser
  // levado do pedido para a agenda do profissional na data através de um
  // clique em um item que possui agendamento".
  const params = useLocalSearchParams<{ funcionario?: string; data?: string }>();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const feedback = useFeedback();

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="A Agenda está disponível apenas no web." testID="agenda-web-only" />;
  }
  if (!can("AGENDA.ABRIR")) {
    return <LockedView title="Acesso restrito" message="Você não tem permissão para acessar a Agenda." testID="agenda-sem-permissao" />;
  }

  const [conn, setConn] = useState<Connection | null>(null);
  const [loadingConn, setLoadingConn] = useState(true);

  const [especialidadeOptions, setEspecialidadeOptions] = useState<SelectOption[]>([]);
  const [especialidade, setEspecialidade] = useState<number | null>(null);

  const [profissionais, setProfissionais] = useState<{ codigo: number; nome_guerra: string }[]>([]);
  const [profissionaisLoading, setProfissionaisLoading] = useState(false);
  const [funcionario, setFuncionario] = useState<number | null>(() => {
    const n = params.funcionario ? parseInt(params.funcionario, 10) : NaN;
    return Number.isFinite(n) ? n : null;
  });

  const [data, setData] = useState<string | null>(() => params.data || hojeIso());
  const [diaSlots, setDiaSlots] = useState<Slot[]>([]);
  const [diaAtende, setDiaAtende] = useState(true);
  const [resumoDia, setResumoDia] = useState<ResumoDia | null>(null);
  const [loading, setLoading] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);

  // "Horários Disponíveis" (checkbox + campo Meses, referência VB.NET
  // colada pelo usuário 2026-07-28) — em vez da lista de um dia só, lista
  // achatada de TODO slot livre do profissional nos próximos N meses a
  // partir da Data escolhida.
  const [horDisponiveis, setHorDisponiveis] = useState(false);
  const [mesesQtd, setMesesQtd] = useState("1");
  const [disponiveisItems, setDisponiveisItems] = useState<{ data: string; hora: string; dia_semana: string }[]>([]);
  const [disponiveisLoading, setDisponiveisLoading] = useState(false);

  const [modalOpen, setModalOpen] = useState(false);
  const [slotFuncionario, setSlotFuncionario] = useState<number | null>(null);
  const [slotData, setSlotData] = useState<string | null>(null);
  const [slotHora, setSlotHora] = useState<string | null>(null);
  const [codagendaExistente, setCodagendaExistente] = useState<number | null>(null);

  const usuarioCod = isMaster ? -2 : (usuarioCodigo ?? -2);

  const diasAtende = useDiasAtende(conn, funcionario);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      setLoadingConn(false);
    })();
  }, [router]);

  useEffect(() => {
    if (!conn) return;
    apiGet(conn, "/api/especialidades")
      .then((j) => {
        if (j?.success) setEspecialidadeOptions((j.items || []).map((i: { codigo: number; descricao: string }) => ({ value: i.codigo, label: i.descricao })));
      })
      .catch(() => {});
  }, [conn]);

  // Lista de profissionais — SEM filtro por padrão (Especialidade é
  // opcional, user-directed: "só filtra se selecionar a especialidade,
  // caso contrário a combobox Profissional lista todos os profissionais").
  // Não seleciona nenhum automaticamente (também user-directed: "ao
  // carregar a tela, não selecionar o profissional").
  useEffect(() => {
    if (!conn) return;
    setProfissionaisLoading(true);
    apiGet(conn, "/api/agenda/profissionais", especialidade ? { especialidade } : {})
      .then((j) => {
        if (j?.success) {
          const items = j.items || [];
          setProfissionais(items);
          setFuncionario((atual) => (atual && items.some((p: { codigo: number }) => p.codigo === atual) ? atual : null));
        }
      })
      .catch(() => {})
      .finally(() => setProfissionaisLoading(false));
  }, [conn, especialidade]);

  useEffect(() => {
    if (horDisponiveis || !conn || !funcionario || !data) { setDiaSlots([]); setDiaAtende(true); setResumoDia(null); return; }
    let ativo = true;
    setLoading(true);
    apiGet(conn, "/api/agenda/grade", { funcionario, data_ini: data, data_fim: data })
      .then((j) => {
        if (!ativo) return;
        if (j?.success && Array.isArray(j.dias) && j.dias[0]) {
          setDiaSlots(j.dias[0].slots || []);
          setDiaAtende(!!j.dias[0].atende);
          setResumoDia(j.dias[0].resumo || null);
        } else {
          feedback.showError(j?.message || "Falha ao carregar a agenda do dia.");
          setDiaSlots([]);
          setDiaAtende(true);
          setResumoDia(null);
        }
      })
      .catch((e) => { if (ativo) feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); })
      .finally(() => { if (ativo) setLoading(false); });
    return () => { ativo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [horDisponiveis, conn, funcionario, data]);

  useEffect(() => {
    if (!horDisponiveis || !conn || !funcionario || !data) { setDisponiveisItems([]); return; }
    let ativo = true;
    setDisponiveisLoading(true);
    const meses = Math.max(1, parseInt(mesesQtd, 10) || 1);
    apiGet(conn, "/api/agenda/disponiveis", { funcionario, data_ini: data, meses })
      .then((j) => {
        if (!ativo) return;
        if (j?.success) setDisponiveisItems(j.items || []);
        else { feedback.showError(j?.message || "Falha ao buscar horários disponíveis."); setDisponiveisItems([]); }
      })
      .catch((e) => { if (ativo) feedback.showError(`Erro: ${e instanceof Error ? e.message : String(e)}`); })
      .finally(() => { if (ativo) setDisponiveisLoading(false); });
    return () => { ativo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [horDisponiveis, conn, funcionario, data, mesesQtd]);

  const recarregarDia = () => {
    if (!conn || !funcionario || !data) return;
    apiGet(conn, "/api/agenda/grade", { funcionario, data_ini: data, data_fim: data }).then((j) => {
      if (j?.success && Array.isArray(j.dias) && j.dias[0]) {
        setDiaSlots(j.dias[0].slots || []);
        setDiaAtende(!!j.dias[0].atende);
        setResumoDia(j.dias[0].resumo || null);
      }
    });
  };

  const abrirNovo = (hora: string, dataOverride?: string) => {
    const dataAlvo = dataOverride || data;
    if (!funcionario || !dataAlvo) return;
    setSlotFuncionario(funcionario);
    setSlotData(dataAlvo);
    setSlotHora(hora);
    setCodagendaExistente(null);
    setModalOpen(true);
  };

  const abrirExistente = (codagenda: number) => {
    setSlotFuncionario(null);
    setSlotData(null);
    setSlotHora(null);
    setCodagendaExistente(codagenda);
    setModalOpen(true);
  };

  if (loadingConn) {
    return (
      <SafeAreaView style={styles.safe} edges={["top"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="agenda-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.iconBtn} hitSlop={12} testID="agenda-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle}>Agenda</Text>
        <Pressable onPress={() => setAjudaOpen(true)} style={styles.iconBtn} hitSlop={12} testID="agenda-ajuda">
          <Ionicons name="information-circle-outline" size={22} color={colors.onBrandPrimary} />
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          <View style={styles.filterCard}>
            <View style={styles.filterRow}>
              <View style={{ flex: 1, minWidth: 200 }}>
                <Text style={styles.fieldLabel}>Especialidade</Text>
                <SelectField
                  value={especialidade}
                  onChange={(v) => setEspecialidade(v as number | null)}
                  options={especialidadeOptions}
                  placeholder="Todas"
                  allowClear
                  compactWeb
                  testID="agenda-especialidade-select"
                />
              </View>
              <View style={{ flex: 1, minWidth: 200 }}>
                <Text style={styles.fieldLabel}>Profissional</Text>
                {profissionaisLoading ? (
                  <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                ) : (
                  <SelectField
                    value={funcionario}
                    onChange={(v) => setFuncionario(v as number | null)}
                    options={profissionais.map((p) => ({ value: p.codigo, label: p.nome_guerra }))}
                    placeholder={profissionais.length ? "Selecione…" : "Nenhum profissional habilitado para Agenda"}
                    disabled={profissionais.length === 0}
                    compactWeb
                    testID="agenda-profissional-select"
                  />
                )}
                {funcionario && diasAtende ? (
                  <Text style={styles.diasAtendeHint} testID="agenda-dias-atende">
                    {diasAtende.size
                      ? `Atende: ${Array.from(diasAtende).sort().map((d) => DIA_SEMANA_LABEL[d]).join(", ")}`
                      : "Nenhum dia de atendimento configurado (ver aba Horários no cadastro dele)."}
                  </Text>
                ) : null}
              </View>
              <View style={{ minWidth: 170 }}>
                <Text style={styles.fieldLabel}>Data</Text>
                <AgendaCalendarField
                  value={data}
                  onChange={(v) => setData(v || null)}
                  diasAtende={diasAtende}
                  testID="agenda-data"
                />
              </View>
              <View style={{ justifyContent: "flex-end", paddingBottom: 2 }}>
                <Pressable
                  onPress={() => setHorDisponiveis((v) => !v)}
                  style={{ flexDirection: "row", alignItems: "center", gap: 6, minHeight: 42 }}
                  testID="agenda-hor-disponiveis-checkbox"
                >
                  <Ionicons name={horDisponiveis ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                  <Text style={{ fontSize: 13, color: colors.onSurface }}>Horários Disponíveis</Text>
                </Pressable>
              </View>
              {horDisponiveis ? (
                <View style={{ width: 90 }}>
                  <Text style={styles.fieldLabel}>Meses</Text>
                  <TextInput
                    value={mesesQtd}
                    onChangeText={(v) => setMesesQtd(v.replace(/[^0-9]/g, ""))}
                    style={styles.mesesInput}
                    keyboardType="number-pad"
                    testID="agenda-hor-disponiveis-meses"
                  />
                </View>
              ) : null}
            </View>
          </View>

          {resumoDia && !horDisponiveis ? (
            <View style={styles.resumoRow} testID="agenda-resumo-dia">
              <View style={styles.resumoItem}>
                <Text style={styles.resumoValor}>{resumoDia.marcados}</Text>
                <Text style={styles.resumoLabel}>Marcados</Text>
              </View>
              <View style={styles.resumoItem}>
                <Text style={styles.resumoValor}>{resumoDia.encaixe}</Text>
                <Text style={styles.resumoLabel}>Encaixe</Text>
              </View>
              <View style={styles.resumoItem}>
                <Text style={[styles.resumoValor, { color: colors.error }]}>{resumoDia.desistencia}</Text>
                <Text style={styles.resumoLabel}>Desistência</Text>
              </View>
            </View>
          ) : null}

          {horDisponiveis ? (
            <>
              {disponiveisLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} /> : null}
              {!disponiveisLoading && !funcionario ? (
                <Text style={styles.semHorario}>Escolha um profissional para ver os horários disponíveis.</Text>
              ) : null}
              {!disponiveisLoading && funcionario && disponiveisItems.length === 0 ? (
                <Text style={styles.semHorario}>Nenhum horário disponível neste período.</Text>
              ) : null}
              {!disponiveisLoading && disponiveisItems.length > 0 ? (
                <View style={styles.lista}>
                  <View style={[styles.linha, styles.disponiveisHeadRow]}>
                    <Text style={[styles.disponiveisHeadText, { width: 90 }]}>Data</Text>
                    <Text style={[styles.disponiveisHeadText, { width: 56 }]}>Hora</Text>
                    <Text style={[styles.disponiveisHeadText, { flex: 1 }]}>Dia</Text>
                    <Text style={styles.disponiveisHeadText}>Situação</Text>
                  </View>
                  {disponiveisItems.map((it, idx) => (
                    <Pressable
                      key={`${it.data}-${it.hora}`}
                      onPress={() => abrirNovo(it.hora, it.data)}
                      style={({ pressed }) => [
                        styles.linha,
                        { zIndex: disponiveisItems.length - idx },
                        pressed && { opacity: 0.7 },
                      ]}
                      testID={`agenda-disponivel-${it.data}-${it.hora}`}
                    >
                      <Text style={{ width: 90, fontSize: 12, color: colors.onSurface }}>{formatDateBR(it.data)}</Text>
                      <Text style={{ width: 56, fontSize: 12, color: colors.onSurface }}>{it.hora}</Text>
                      <Text style={{ flex: 1, fontSize: 12, color: colors.onSurface }}>{it.dia_semana}</Text>
                      <Text style={{ fontSize: 12, color: colors.success, fontWeight: "700" }}>DISPONÍVEL</Text>
                    </Pressable>
                  ))}
                </View>
              ) : null}
            </>
          ) : null}

          {!horDisponiveis && loading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing.lg }} /> : null}

          {!horDisponiveis && !loading && !funcionario ? (
            <Text style={styles.semHorario}>Escolha um profissional para ver a agenda.</Text>
          ) : null}

          {!horDisponiveis && !loading && funcionario && !diaAtende ? (
            <Text style={styles.semHorario}>Profissional não atende neste dia da semana.</Text>
          ) : null}

          {!horDisponiveis && !loading && funcionario && diaAtende ? (
            diaSlots.length === 0 ? (
              <Text style={styles.semHorario}>Nenhum horário de atendimento cadastrado para este profissional.</Text>
            ) : (
              <View style={styles.lista}>
                {diaSlots.map((slot, idx) => {
                  // zIndex decrescente por linha — garante que a tooltip de
                  // uma linha de cima sempre pinte por cima do conteúdo da
                  // linha de baixo (irmãs no mesmo pai `styles.lista`; a
                  // tooltip só eleva o zIndex do SEU wrapper interno, não
                  // da linha inteira, então sem isso a linha seguinte
                  // "ganhava" por vir depois no DOM). Mesmo princípio já
                  // documentado em CLAUDE.md > "Modo Didático" > tooltip
                  // sempre por cima.
                  const zLinha = diaSlots.length - idx;
                  if (slot.status === "livre") {
                    return (
                      <Pressable
                        key={slot.hora}
                        onPress={() => abrirNovo(slot.hora)}
                        style={({ pressed }) => [styles.linha, styles.linhaLivre, { zIndex: zLinha }, pressed && { opacity: 0.7 }]}
                        testID={`agenda-slot-livre-${slot.hora}`}
                      >
                        <Text style={styles.horaText}>{slot.hora}</Text>
                        <View style={styles.linhaLivreConteudo}>
                          <Ionicons name="add-circle-outline" size={18} color={colors.success} />
                          <Text style={styles.linhaLivreTexto}>Marcar atendimento</Text>
                        </View>
                      </Pressable>
                    );
                  }
                  if (slot.status === "pausa" || slot.status === "ausente") {
                    return (
                      <View key={slot.hora} style={[styles.linha, styles.linhaIndisponivel, { zIndex: zLinha }]}>
                        <Text style={styles.horaText}>{slot.hora}</Text>
                        <Text style={styles.slotIndisponivelText}>{slot.status === "pausa" ? "Pausa" : "Ausente"}</Text>
                      </View>
                    );
                  }
                  return (
                    <View key={slot.hora} style={[styles.linha, { alignItems: "flex-start", zIndex: zLinha }]}>
                      <View style={{ marginTop: 10, flexDirection: "row", alignItems: "center", flexShrink: 0 }}>
                        <Text style={styles.horaText}>{slot.hora}</Text>
                        <IconButtonWithTooltip
                          icon="add-circle-outline"
                          label="Adicionar encaixe"
                          size={16}
                          color={colors.success}
                          tooltipAlign="left"
                          onPress={() => abrirNovo(slot.hora)}
                          testID={`agenda-slot-encaixe-${slot.hora}`}
                        />
                      </View>
                      <View style={{ flex: 1, gap: 6 }}>
                        {(slot.atendimentos || []).map((a) => {
                          const linha2 = [
                            a.servico,
                            a.marcado_por ? `Marcado por ${a.marcado_por}` : "",
                          ].filter(Boolean).join(" · ");
                          // Situação do pagamento — SEMPRE uma das 3, nunca
                          // omitida (user-directed: "faltou a situação do
                          // pagto" — antes só aparecia a etiqueta "Pago",
                          // ficando em branco no caso mais comum de "ainda
                          // não pago").
                          const situacaoPagto = a.revisao
                            ? { texto: "Revisão", cor: colors.muted, descricao: "Atendimento de garantia/revisão, sem cobrança." }
                            : a.pago
                            ? { texto: "Pago", cor: colors.success, descricao: "Este atendimento já foi faturado." }
                            : { texto: "Em Aberto", cor: colors.brandPrimary, descricao: "Ainda não foi faturado." };
                          return (
                            <Pressable
                              key={a.codagenda}
                              onPress={() => abrirExistente(a.codagenda)}
                              style={({ pressed }) => [
                                styles.slotOcupado,
                                { borderLeftColor: SITUACAO_COLOR[a.situacao] || SITUACAO_COLOR_FALLBACK },
                                pressed && { opacity: 0.8 },
                              ]}
                              testID={`agenda-slot-ocupado-${a.codagenda}`}
                            >
                              {/* `zIndex` elevado — esta linha (Cliente/telefone/
                                  etiquetas) precisa pintar por cima da linha
                                  seguinte (Serviço · Marcado por, `slotServico`
                                  logo abaixo) quando uma tooltip de etiqueta
                                  escapa pra baixo via `position:absolute`; as
                                  duas são IRMÃS do mesmo card, e sem isso a
                                  linha de baixo "ganhava" por vir depois no
                                  DOM — achado ao vivo 2026-07-28 (tooltip
                                  aparecendo atrás do texto "Marcado por
                                  CARLOS"). Mesmo princípio já documentado em
                                  CLAUDE.md > "Modo Didático" > tooltip sempre
                                  por cima. */}
                              <View style={{ flexDirection: "row", alignItems: "center", gap: 6, flexWrap: "wrap", zIndex: 2 }}>
                                <Text style={styles.slotCliente} numberOfLines={1}>{a.cliente || "(sem cliente)"}</Text>
                                {a.telefone ? (
                                  <Text style={styles.slotTelefone} numberOfLines={1}>{a.telefone}</Text>
                                ) : null}
                                {a.encaixe ? (
                                  <BadgeTooltip
                                    texto="Encaixe"
                                    cor={colors.warning}
                                    descricao="Marcado além da vaga normal deste horário."
                                    testID={`agenda-slot-badge-encaixe-${a.codagenda}`}
                                  />
                                ) : null}
                                <BadgeTooltip
                                  texto={a.situacao}
                                  cor={SITUACAO_COLOR[a.situacao] || SITUACAO_COLOR_FALLBACK}
                                  descricao={`Situação do atendimento: ${a.situacao}.`}
                                  testID={`agenda-slot-badge-situacao-${a.codagenda}`}
                                />
                                <BadgeTooltip
                                  texto={situacaoPagto.texto}
                                  cor={situacaoPagto.cor}
                                  descricao={situacaoPagto.descricao}
                                  testID={`agenda-slot-badge-pagto-${a.codagenda}`}
                                />
                                {a.pedido ? (
                                  <IconButtonWithTooltip
                                    icon="receipt-outline"
                                    label="Visualizar Pré-venda"
                                    size={14}
                                    onPress={(e) => {
                                      e.stopPropagation();
                                      router.push({ pathname: "/pedido-geral", params: { pedido: String(a.pedido) } } as never);
                                    }}
                                    testID={`agenda-slot-ver-pre-venda-${a.codagenda}`}
                                  />
                                ) : null}
                              </View>
                              <Text style={styles.slotServico} numberOfLines={1}>{linha2}</Text>
                            </Pressable>
                          );
                        })}
                      </View>
                    </View>
                  );
                })}
              </View>
            )
          ) : null}
        </View>
      </ScrollView>

      <AtendimentoAvulsoModal
        visible={modalOpen}
        onClose={() => setModalOpen(false)}
        conn={conn}
        classe={classe}
        master={isMaster}
        usuarioCod={usuarioCod}
        slotFuncionario={slotFuncionario}
        slotData={slotData}
        slotHoraIni={slotHora}
        codagendaExistente={codagendaExistente}
        onSaved={recarregarDia}
      />

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Agenda" itens={AGENDA_AJUDA_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center" },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md,
    paddingTop: spacing.sm, paddingBottom: spacing.md,
  },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "600", textAlign: "center" },
  scroll: { padding: spacing.lg },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  filterCard: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.md,
    // `zIndex` sempre elevado (não só quando o calendário está aberto) —
    // `AgendaCalendarField`/`SelectField` escapam deste card via
    // `position:absolute` pra desenhar o popup por cima da lista de
    // horários logo abaixo; os dois são IRMÃOS no mesmo pai (`shell`), e a
    // lista não tem fundo opaco em toda a linha, então sem isso o popup
    // ficava "atrás"/misturado com o texto da lista por trás dele (visual
    // de "calendário transparente" — mesmo bug de stacking já documentado
    // em CLAUDE.md > "Modo Didático" > tooltip sempre por cima, aqui
    // aplicado a um popup em vez de um tooltip).
    zIndex: 2,
  },
  filterRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md, alignItems: "flex-start" },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  diasAtendeHint: { fontSize: 11, color: colors.muted, marginTop: 4 },
  mesesInput: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.md,
    backgroundColor: colors.surfaceSecondary, paddingHorizontal: 10, paddingVertical: 10,
    fontSize: 14, color: colors.onSurface, textAlign: "center",
  },
  disponiveisHeadRow: { backgroundColor: colors.surfaceSecondary },
  disponiveisHeadText: { fontSize: 11, fontWeight: "700", color: colors.muted, textTransform: "uppercase" },
  // Sem `overflow: "hidden"` de propósito — cortaria qualquer tooltip que
  // escape de uma linha perto da borda do card (visual "raspado"/cortado
  // reportado ao vivo, 2026-07-28). Custo aceito: o cantinho quadrado da
  // primeira/última linha pode aparecer levemente por fora do raio da
  // borda deste container — cosmético, não afeta leitura.
  lista: { marginTop: spacing.md, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  linha: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  linhaLivre: {},
  linhaLivreConteudo: { flexDirection: "row", alignItems: "center", gap: 6 },
  linhaLivreTexto: { fontSize: 13, color: colors.success },
  linhaIndisponivel: { backgroundColor: colors.surfaceSecondary },
  horaText: { fontSize: 13, fontWeight: "600", color: colors.onSurface, width: 56 },
  slotIndisponivelText: { fontSize: 12, color: colors.muted },
  slotOcupado: {
    backgroundColor: colors.brandTertiary, borderRadius: 6, borderLeftWidth: 3,
    paddingHorizontal: spacing.sm, paddingVertical: 6,
  },
  slotCliente: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  slotTelefone: { fontSize: 11, color: colors.muted },
  slotServico: { fontSize: 11, color: colors.muted },
  badge: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: radius.pill },
  badgeText: { fontSize: 9, fontWeight: "700", color: "#fff" },
  badgeTooltip: {
    position: "absolute", top: "100%", left: 0, marginTop: 4, minWidth: 140, maxWidth: 240,
    backgroundColor: "#1a1a1a", borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6, zIndex: 1000,
  },
  badgeTooltipText: { color: "#fff", fontSize: 11, fontWeight: "600" },
  semHorario: { color: colors.muted, fontSize: 13, textAlign: "center", marginTop: spacing.xl },
  // Resumo do Dia (Marcados/Encaixe/Desistência) — mesmos 3 contadores da
  // tela de referência em VB.NET colada pelo usuário, 2026-07-28.
  resumoRow: {
    flexDirection: "row", justifyContent: "space-around", marginTop: spacing.sm,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingVertical: spacing.sm,
  },
  resumoItem: { alignItems: "center" },
  resumoValor: { fontSize: 18, fontWeight: "700", color: colors.onSurface },
  resumoLabel: { fontSize: 11, color: colors.muted },
});
