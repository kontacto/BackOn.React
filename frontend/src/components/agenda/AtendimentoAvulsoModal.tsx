// Modal de Atendimento AVULSO — criado direto da grade semanal (sem vir de
// um item de Pedido). Superset do `AgendarModal.tsx` (item vinculado a um
// Pedido): aqui também entram Cliente (busca + cadastro rápido) e Serviço
// (busca), e Faturar ($) fica disponível (só quando o agendamento não está
// vinculado a nenhum Pedido/O.S — mesma regra do backend). Ver
// `agenda_service.py::_salvar_agendamento_sync`/`_faturar_avulso_sync` e
// PENDENCIAS.md > "Transações" > "Pedido Geral — Fase B: Clínica
// (Agendamento)".
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, ScrollView, Text, TextInput, View } from "react-native";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import SelectField from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import AgendaCalendarField from "@/src/components/agenda/AgendaCalendarField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import AnexosAgendamentoModal from "@/src/components/agenda/AnexosAgendamentoModal";
import LayoutPreenchimentoModal from "@/src/components/agenda/LayoutPreenchimentoModal";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { ClienteRow } from "@/src/components/pedido/types";
import { styles } from "@/src/components/pedido/styles";
import { SITUACOES_ATENDIMENTO } from "@/src/components/pedido/agendaConstants";
import { apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { formatBRL, parseNum } from "@/src/utils/format";
import { Connection } from "@/src/utils/storage/connections";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useDiasAtende } from "@/src/hooks/useDiasAtende";

const isWeb = Platform.OS === "web";

// Botão "Agendar"/"Salvar" no cabeçalho do modal (user-directed 2026-07-28:
// "colocar o botão agendar no topo da tela de novo atendimento") — pill
// sólida na cor da marca, já que (diferente de `PedidoHeader`) este
// cabeçalho fica sobre um card BRANCO, não sobre uma barra colorida (por
// isso não reaproveita `pedido/styles.ts`'s `saveBtn`, pensado pra um
// fundo escuro).
const headerSaveBtnStyle = {
  flexDirection: "row" as const, alignItems: "center" as const, gap: 4,
  paddingHorizontal: spacing.md, paddingVertical: 8,
  backgroundColor: colors.brandPrimary, borderRadius: 999, minWidth: 76, justifyContent: "center" as const,
};

type Servico = { codigo: string; descricao: string; valor: number };

type Props = {
  visible: boolean;
  onClose: () => void;
  conn: Connection | null;
  classe: number | null;
  master: boolean;
  usuarioCod: number;
  // Slot clicado na grade (novo atendimento) — null quando editando um
  // atendimento já existente (codagendaExistente informado).
  slotFuncionario: number | null;
  slotData: string | null;
  slotHoraIni: string | null;
  codagendaExistente: number | null;
  onSaved: () => void;
};

export default function AtendimentoAvulsoModal({
  visible, onClose, conn, classe, master, usuarioCod,
  slotFuncionario, slotData, slotHoraIni, codagendaExistente, onSaved,
}: Props) {
  const router = useRouter();
  const feedback = useFeedback();

  const [loadingInit, setLoadingInit] = useState(false);
  const [codagenda, setCodagenda] = useState<number | null>(null);
  const [codauto, setCodauto] = useState<number | null>(null); // vinculado a Pedido — bloqueia Faturar
  // Número do Pedido de Venda vinculado (não o codauto do item) — usado só
  // pelo ícone "visualizar Pré-venda" no cabeçalho.
  const [pedidoVinculado, setPedidoVinculado] = useState<number | null>(null);

  const [funcionario, setFuncionario] = useState<number | null>(null);
  const [data, setData] = useState<string | null>(null);
  const [horaIni, setHoraIni] = useState<string | null>(null);
  // Valor originalmente carregado (avulso já existente) — usado só pra manter
  // o horário atual na lista mesmo que a grade o marque como "ocupado" (ele
  // está ocupado por si mesmo). Não usar `horaIni` direto aqui porque esse
  // state muda a cada seleção do usuário, o que recalcularia a lista sem
  // necessidade.
  const [horaIniOriginal, setHoraIniOriginal] = useState<string | null>(null);
  const [situacao, setSituacao] = useState("Confirmado");
  const [revisao, setRevisao] = useState(false);
  const [garantiaInfo, setGarantiaInfo] = useState<{ dentro: boolean; expiraEm?: string; aviso?: string } | null>(null);
  const [descartavelValor, setDescartavelValor] = useState("");
  const [descartavelObs, setDescartavelObs] = useState("");
  const [horaChegada, setHoraChegada] = useState<string | null>(null);
  const [horaSaida, setHoraSaida] = useState<string | null>(null);

  const [clienteCodigo, setClienteCodigo] = useState<number | null>(null);
  const [clienteNome, setClienteNome] = useState("");
  const [clienteSearchOpen, setClienteSearchOpen] = useState(false);
  const [clienteTerm, setClienteTerm] = useState("");
  const [clienteResults, setClienteResults] = useState<ClienteRow[]>([]);
  const [clienteLoading, setClienteLoading] = useState(false);

  const [servicoCodigo, setServicoCodigo] = useState<string | null>(null);
  const [servicoDescricao, setServicoDescricao] = useState("");
  const [valor, setValor] = useState("0,00");
  const [servicoSearchOpen, setServicoSearchOpen] = useState(false);
  const [servicoTerm, setServicoTerm] = useState("");
  const [servicoResults, setServicoResults] = useState<Servico[]>([]);
  const [servicoLoading, setServicoLoading] = useState(false);

  const [profissionaisAgenda, setProfissionaisAgenda] = useState<{ codigo: number; nome_guerra: string }[]>([]);
  const [profissionaisLoading, setProfissionaisLoading] = useState(false);

  const [anexosOpen, setAnexosOpen] = useState(false);
  const [layoutsOpen, setLayoutsOpen] = useState(false);
  const [trocaMode, setTrocaMode] = useState(false);
  const [trocaFuncionario, setTrocaFuncionario] = useState<number | null>(null);
  const [authVisible, setAuthVisible] = useState(false);
  const [trocaSaving, setTrocaSaving] = useState(false);
  // Lista filtrada por elegibilidade (especialidade do Serviço x
  // especialidade do Profissional) — usada tanto no campo Profissional
  // PRINCIPAL (assim que um Serviço é escolhido) quanto em "Novo
  // profissional" (Trocar Profissional). Sem Serviço escolhido ainda, o
  // campo principal cai pra `profissionaisAgenda` (sem filtro, ver
  // comentário abaixo) — não dá pra filtrar por especialidade sem saber
  // qual serviço. User-directed 2026-07-28: "o profissional não pode ser
  // listado na combobox cuja a especialidade da marcação de agenda não faz
  // parte da especialidade do profissional" — reforça/generaliza o mesmo
  // fix já aplicado só em Trocar Profissional. Mesmo endpoint/filtro que
  // `usePedidoItens.ts` já usa pro Agendar vindo de um Pedido.
  const [profissionaisElegiveis, setProfissionaisElegiveis] = useState<{ codigo: number; nome_guerra: string }[]>([]);
  const [elegiveisLoading, setElegiveisLoading] = useState(false);
  useEffect(() => {
    if (!conn || !servicoCodigo) { setProfissionaisElegiveis([]); return; }
    setElegiveisLoading(true);
    apiGet(conn, "/api/agenda/profissionais", { servico: servicoCodigo })
      .then((j) => {
        if (j?.success) {
          const items = j.items || [];
          setProfissionaisElegiveis(items);
          // O profissional pré-preenchido (via slotFuncionario, ou já
          // selecionado antes de escolher o Serviço) pode não ter essa
          // especialidade — limpa e avisa, em vez de deixar alguém sem
          // relação nenhuma "grudado" no campo (bug real achado ao vivo
          // 2026-07-28).
          setFuncionario((atual) => {
            if (atual && !items.some((p: { codigo: number }) => p.codigo === atual)) {
              feedback.showWarning("O profissional selecionado não tem a especialidade deste serviço. Escolha outro.");
              return null;
            }
            return atual;
          });
        }
      })
      .catch(() => {})
      .finally(() => setElegiveisLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, servicoCodigo]);

  const [faturarOpen, setFaturarOpen] = useState(false);
  const [formasPagamento, setFormasPagamento] = useState<{ codigo: string; descricao: string }[]>([]);
  const [formaSel, setFormaSel] = useState<string | null>(null);
  const [faturarSaving, setFaturarSaving] = useState(false);

  const [saving, setSaving] = useState(false);

  // Carrega TODO profissional habilitado pra Agenda assim que o modal abre —
  // não filtrado por serviço (user-directed, 2026-07-28: "o filtro principal
  // é o Profissional, selecionado já na agenda... não precisa selecionar o
  // profissional novamente"). Mesmo endpoint/uso sem `servico` já usado pelo
  // seletor de profissional da própria tela Agenda (`app/agenda.tsx`) — o
  // profissional vem pré-preenchido via `slotFuncionario` (o mesmo já
  // selecionado no filtro da grade), então precisa estar disponível na lista
  // desde a abertura, antes de qualquer Serviço ser escolhido.
  useEffect(() => {
    if (!conn || !visible) { setProfissionaisAgenda([]); return; }
    setProfissionaisLoading(true);
    apiGet(conn, "/api/agenda/profissionais")
      .then((j) => { if (j?.success) setProfissionaisAgenda(j.items || []); })
      .catch(() => {})
      .finally(() => setProfissionaisLoading(false));
  }, [conn, visible]);

  useEffect(() => {
    if (!visible) return;
    // reset
    setCodagenda(codagendaExistente);
    setCodauto(null);
    setPedidoVinculado(null);
    setFuncionario(slotFuncionario);
    setData(slotData);
    setHoraIni(slotHoraIni);
    setHoraIniOriginal(slotHoraIni);
    setSituacao("Confirmado");
    setRevisao(false);
    setGarantiaInfo(null);
    setDescartavelValor(""); setDescartavelObs("");
    setHoraChegada(null); setHoraSaida(null);
    setClienteCodigo(null); setClienteNome("");
    setServicoCodigo(null); setServicoDescricao(""); setValor("0,00");
    setTrocaMode(false);

    if (codagendaExistente && conn) {
      setLoadingInit(true);
      apiGet(conn, `/api/agenda/avulso/${codagendaExistente}`)
        .then((j) => {
          if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao carregar agendamento.")); return; }
          const ag = j.agendamento;
          setCodauto(ag.codauto ?? null);
          setPedidoVinculado(ag.pedido ?? null);
          setFuncionario(ag.funcionario);
          setData(ag.data);
          setHoraIni(ag.hora_ini);
          setHoraIniOriginal(ag.hora_ini);
          setSituacao(ag.situacao_atendimento || "Confirmado");
          setRevisao(!!ag.revisao);
          setDescartavelValor(ag.descartavel_valor != null ? String(ag.descartavel_valor) : "");
          setDescartavelObs(ag.descartavel_obs || "");
          setHoraChegada(ag.hora_chegada || null);
          setHoraSaida(ag.hora_saida || null);
          setClienteCodigo(ag.cliente);
          setClienteNome(ag.cliente_nome || "");
          setServicoCodigo(ag.servico);
          setServicoDescricao(ag.servico_descricao || "");
          setValor(formatBRL(ag.valor).replace("R$", "").trim());
        })
        .finally(() => setLoadingInit(false));
    }
  }, [visible, codagendaExistente, slotFuncionario, slotData, slotHoraIni, conn, feedback]);

  const diasAtende = useDiasAtende(conn, funcionario);

  // Horários livres daquele dia específico — o campo Hora só oferece o que
  // realmente está disponível (user-directed, 2026-07-28: "no horário do
  // atendimento também. Listar somente os horários livres"), mesmo padrão
  // de `AgendarModal.tsx` (Pedido Geral).
  const [horaOptions, setHoraOptions] = useState<{ value: string; label: string }[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  useEffect(() => {
    if (!conn || !funcionario || !data) { setHoraOptions([]); return; }
    let ativo = true;
    setSlotsLoading(true);
    (async () => {
      const j = await apiGet(conn, "/api/agenda/grade", { funcionario, data_ini: data, data_fim: data });
      if (!ativo) return;
      setSlotsLoading(false);
      const dia = j?.success && Array.isArray(j.dias) ? j.dias[0] : null;
      if (!dia || !dia.atende) { setHoraOptions([]); return; }
      const livres: string[] = (dia.slots || [])
        .filter((s: { status: string }) => s.status === "livre")
        .map((s: { hora: string }) => s.hora);
      // Mantém o horário já agendado deste MESMO atendimento na lista, mesmo
      // que a grade o mostre como "ocupado" — ele está ocupado por si mesmo.
      const horaAtual = horaIniOriginal;
      const todos = horaAtual && !livres.includes(horaAtual) ? [...livres, horaAtual] : livres;
      todos.sort();
      setHoraOptions(todos.map((h) => ({ value: h, label: h })));
    })();
    return () => { ativo = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [funcionario, data, conn]);

  const buscarClientes = async (term: string) => {
    if (!conn || !term.trim()) { setClienteResults([]); return; }
    setClienteLoading(true);
    try {
      const j = await apiGet(conn, "/api/clientes/find/search", { term });
      setClienteResults(j?.items || []);
    } catch {
      setClienteResults([]);
    } finally {
      setClienteLoading(false);
    }
  };

  const buscarServicos = async (term: string) => {
    if (!conn || !term.trim()) { setServicoResults([]); return; }
    setServicoLoading(true);
    try {
      const j = await apiGet(conn, "/api/produtos-servicos", { search: term, page: 1, size: 20, tipo: "S" });
      setServicoResults((j?.items || []).map((p: { codigo: string; descricao: string; valor: number }) => ({
        codigo: p.codigo, descricao: p.descricao, valor: p.valor,
      })));
    } catch {
      setServicoResults([]);
    } finally {
      setServicoLoading(false);
    }
  };

  const verificarGarantia = async () => {
    if (!conn || !clienteCodigo || !servicoCodigo) return;
    const j = await apiGet(conn, "/api/agenda/garantia", { cliente: clienteCodigo, servico: servicoCodigo });
    if (j?.success) {
      setGarantiaInfo({ dentro: !!j.dentro_garantia, expiraEm: j.expira_em, aviso: j.aviso });
      if (j.dentro_garantia) setRevisao(true);
    }
  };

  const podeSalvar = !!funcionario && !!data && !!horaIni && !!clienteCodigo && !!servicoCodigo;

  const salvar = async () => {
    if (!conn || !podeSalvar) return;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/agenda/avulso", "POST", {
        codagenda,
        funcionario, data, hora_ini: horaIni,
        cliente: clienteCodigo, servico: servicoCodigo, valor: parseNum(valor),
        situacao_atendimento: situacao, revisao,
        descartavel_valor: descartavelValor ? parseNum(descartavelValor) : null,
        descartavel_obs: descartavelObs,
        hora_chegada: horaChegada, hora_saida: horaSaida,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao agendar.")); return; }
      feedback.showSuccess(`Agendamento #${j.agendamento?.codagenda} gravado.`);
      onSaved();
      onClose();
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao agendar."));
    } finally {
      setSaving(false);
    }
  };

  const cancelarAtendimento = async () => {
    if (!conn || !codagenda) return;
    setSaving(true);
    try {
      const j = await apiSend(conn, "/api/agenda/avulso", "POST", {
        codagenda, funcionario, data, hora_ini: horaIni,
        cliente: clienteCodigo, servico: servicoCodigo, valor: parseNum(valor),
        situacao_atendimento: "Desistência", revisao,
        descartavel_valor: descartavelValor ? parseNum(descartavelValor) : null,
        descartavel_obs: descartavelObs, hora_chegada: horaChegada, hora_saida: horaSaida,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao cancelar.")); return; }
      feedback.showSuccess("Atendimento marcado como Desistência.");
      onSaved();
      onClose();
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao cancelar."));
    } finally {
      setSaving(false);
    }
  };

  const trocarProfissional = async (usuario: string) => {
    if (!conn || !codagenda || !trocaFuncionario) return;
    setTrocaSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/${codagenda}/trocar-profissional`, "POST", {
        novo_funcionario: trocaFuncionario, autorizado_por: usuario,
        classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao trocar profissional.")); return; }
      feedback.showSuccess("Profissional trocado.");
      setFuncionario(trocaFuncionario);
      setTrocaMode(false);
      onSaved();
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao trocar profissional."));
    } finally {
      setTrocaSaving(false);
    }
  };

  const abrirFaturar = async () => {
    if (!conn) return;
    setFormaSel(null);
    setFaturarOpen(true);
    if (formasPagamento.length === 0) {
      const j = await apiGet(conn, "/api/forma-pagamento");
      if (j?.success) setFormasPagamento(j.items || []);
    }
  };

  const handleFaturar = async () => {
    if (!conn || !codagenda || !formaSel) return;
    setFaturarSaving(true);
    try {
      const j = await apiSend(conn, `/api/agenda/${codagenda}/faturar-avulso`, "POST", {
        forma_pag: formaSel, classe, master, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (!j?.success) { feedback.showError(friendlyApiError(j, "Falha ao faturar.")); return; }
      feedback.showSuccess(`Atendimento faturado (comanda ${j.comanda}).`);
      setFaturarOpen(false);
      onSaved();
      onClose();
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao faturar."));
    } finally {
      setFaturarSaving(false);
    }
  };

  const abrirCadastroClienteRapido = () => {
    setClienteSearchOpen(false);
    router.push({
      pathname: "/cliente-form",
      params: {
        ...clienteSearchParams(clienteTerm),
        criar_agendamento: "1",
        agenda_funcionario: funcionario ? String(funcionario) : "",
        agenda_data: data || "",
        agenda_hora: horaIni || "",
        agenda_servico: servicoCodigo || "",
      },
    });
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={onClose}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{codagenda ? "Atendimento" : "Novo Atendimento"}</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              {codagenda ? (
                <IconButtonWithTooltip icon="attach-outline" label="Anexos" onPress={() => setAnexosOpen(true)} testID="atendimento-avulso-anexos-btn" />
              ) : null}
              {codagenda ? (
                <IconButtonWithTooltip icon="document-text-outline" label="Formulários" onPress={() => setLayoutsOpen(true)} testID="atendimento-avulso-layouts-btn" />
              ) : null}
              {codagenda ? (
                <IconButtonWithTooltip icon="swap-horizontal-outline" label="Trocar profissional" onPress={() => setTrocaMode((v) => !v)} testID="atendimento-avulso-trocar-prof-btn" />
              ) : null}
              {codagenda && !codauto ? (
                <IconButtonWithTooltip icon="cash-outline" label="Faturar" color={colors.success} onPress={abrirFaturar} testID="atendimento-avulso-faturar-btn" />
              ) : null}
              {pedidoVinculado ? (
                <IconButtonWithTooltip
                  icon="receipt-outline"
                  label="Visualizar Pré-venda"
                  onPress={() => router.push({ pathname: "/pedido-geral", params: { pedido: String(pedidoVinculado) } } as never)}
                  testID="atendimento-avulso-ver-pre-venda-btn"
                />
              ) : null}
              <Pressable
                onPress={salvar}
                disabled={!podeSalvar || saving}
                style={({ pressed }) => [
                  headerSaveBtnStyle,
                  (pressed || !podeSalvar || saving) && { opacity: 0.7 },
                ]}
                testID="atendimento-avulso-save"
              >
                {saving ? (
                  <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                ) : (
                  <Text style={{ color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 }}>
                    {codagenda ? "Salvar" : "Agendar"}
                  </Text>
                )}
              </Pressable>
              <Pressable onPress={onClose} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
          </View>

          {loadingInit ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}

          {!loadingInit ? (
            <ScrollView style={{ maxHeight: 480 }} keyboardShouldPersistTaps="handled">
              <View style={{ gap: spacing.sm }}>
                {codauto ? (
                  <Text style={[styles.itensHintText, { color: colors.brandPrimary }]}>
                    Vinculado ao Pedido de Venda nº {codauto} — Faturar disponível apenas pelo próprio Pedido.
                  </Text>
                ) : null}

                <View>
                  <Text style={styles.fieldLabel}>Profissional</Text>
                  {(servicoCodigo ? elegiveisLoading : profissionaisLoading) ? (
                    <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                  ) : (
                    <SelectField
                      value={funcionario}
                      onChange={(v) => setFuncionario(v as number | null)}
                      options={(servicoCodigo ? profissionaisElegiveis : profissionaisAgenda).map((p) => ({ value: p.codigo, label: p.nome_guerra }))}
                      placeholder={
                        (servicoCodigo ? profissionaisElegiveis : profissionaisAgenda).length
                          ? "Selecione…"
                          : servicoCodigo
                          ? "Nenhum profissional com essa especialidade"
                          : "Nenhum profissional habilitado para Agenda"
                      }
                      disabled={(servicoCodigo ? profissionaisElegiveis : profissionaisAgenda).length === 0}
                      compactWeb
                      testID="atendimento-avulso-profissional"
                    />
                  )}
                  {servicoCodigo ? (
                    <Text style={styles.resultSub}>
                      Só mostra profissionais com a especialidade deste serviço.
                    </Text>
                  ) : null}
                </View>

                <View>
                  <Text style={styles.fieldLabel}>Serviço</Text>
                  <Pressable
                    onPress={() => setServicoSearchOpen(true)}
                    style={[styles.input, { justifyContent: "center" }]}
                    testID="atendimento-avulso-servico-campo"
                  >
                    <Text style={{ color: servicoCodigo ? colors.onSurface : colors.muted }}>
                      {servicoDescricao || "Buscar serviço…"}
                    </Text>
                  </Pressable>
                </View>

                <View>
                  <Text style={styles.fieldLabel}>Cliente</Text>
                  <Pressable
                    onPress={() => { if (servicoCodigo) setClienteSearchOpen(true); }}
                    disabled={!servicoCodigo}
                    style={[styles.input, { justifyContent: "center" }, !servicoCodigo && { opacity: 0.5 }]}
                    testID="atendimento-avulso-cliente-campo"
                  >
                    <Text style={{ color: clienteCodigo ? colors.onSurface : colors.muted }}>
                      {clienteNome || (servicoCodigo ? "Buscar cliente…" : "Escolha o serviço primeiro")}
                    </Text>
                  </Pressable>
                </View>

                {/* `zIndex` elevado — mesmo motivo documentado em
                    `AgendarModal.tsx`: o calendário escapa deste row via
                    `position:absolute`, precisa pintar por cima dos campos
                    seguintes (Valor, Situação, Hora Chegada/Saída, ...). */}
                <View style={[styles.qtdRow, { zIndex: 2 }]}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Data</Text>
                    <AgendaCalendarField value={data} onChange={(v) => setData(v || null)} diasAtende={diasAtende} testID="atendimento-avulso-data" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Hora</Text>
                    {slotsLoading ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                    ) : (
                      <SelectField
                        value={horaIni}
                        onChange={(v) => setHoraIni(v as string | null)}
                        options={horaOptions}
                        placeholder={
                          !funcionario || !data
                            ? "Escolha profissional e data"
                            : horaOptions.length
                            ? "Selecione…"
                            : "Nenhum horário livre"
                        }
                        disabled={!funcionario || !data || horaOptions.length === 0}
                        compactWeb
                        testID="atendimento-avulso-hora"
                      />
                    )}
                  </View>
                </View>

                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Valor (R$)</Text>
                    <TextInput
                      value={valor}
                      onChangeText={setValor}
                      style={styles.input}
                      keyboardType="decimal-pad"
                      testID="atendimento-avulso-valor"
                    />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Situação do Atendimento</Text>
                    <SelectField
                      value={situacao}
                      onChange={(v) => setSituacao(v as string)}
                      options={SITUACOES_ATENDIMENTO.map((s) => ({ value: s, label: s }))}
                      compactWeb
                      testID="atendimento-avulso-situacao"
                    />
                  </View>
                </View>

                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Hora Chegada</Text>
                    <WebDateField value={horaChegada} onChange={setHoraChegada} type="time" icon="time-outline" testID="atendimento-avulso-hora-chegada" />
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Hora Saída</Text>
                    <WebDateField value={horaSaida} onChange={setHoraSaida} type="time" icon="time-outline" testID="atendimento-avulso-hora-saida" />
                  </View>
                </View>

                <View style={styles.qtdRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.fieldLabel}>Descartáveis (R$)</Text>
                    <TextInput
                      value={descartavelValor}
                      onChangeText={setDescartavelValor}
                      style={styles.input}
                      keyboardType="decimal-pad"
                      placeholder="0,00"
                      placeholderTextColor={colors.muted}
                      testID="atendimento-avulso-descartavel-valor"
                    />
                  </View>
                  <View style={{ flex: 2 }}>
                    <Text style={styles.fieldLabel}>Obs. Descartáveis</Text>
                    <TextInput
                      value={descartavelObs}
                      onChangeText={setDescartavelObs}
                      style={styles.input}
                      placeholder="Luvas, agulhas…"
                      placeholderTextColor={colors.muted}
                      testID="atendimento-avulso-descartavel-obs"
                    />
                  </View>
                </View>

                <View style={{ gap: 4 }}>
                  <Pressable
                    onPress={() => setRevisao((v) => !v)}
                    style={{ flexDirection: "row", alignItems: "center", gap: 6 }}
                    testID="atendimento-avulso-revisao-checkbox"
                  >
                    <Ionicons name={revisao ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                    <Text style={{ fontSize: 13, color: colors.onSurface }}>Revisão/Garantia (grátis)</Text>
                  </Pressable>
                  {clienteCodigo && servicoCodigo ? (
                    <Pressable onPress={verificarGarantia} testID="atendimento-avulso-verificar-garantia">
                      <Text style={{ fontSize: 12, color: colors.brandPrimary, textDecorationLine: "underline" }}>
                        Verificar garantia/revisão deste serviço para este cliente
                      </Text>
                    </Pressable>
                  ) : null}
                  {garantiaInfo ? (
                    garantiaInfo.aviso ? (
                      <Text style={styles.resultSub}>{garantiaInfo.aviso}</Text>
                    ) : garantiaInfo.dentro ? (
                      <Text style={{ fontSize: 12, color: colors.success }}>Dentro da garantia/revisão até {garantiaInfo.expiraEm}.</Text>
                    ) : (
                      <Text style={styles.resultSub}>Fora do prazo de garantia/revisão (ou nunca atendido antes).</Text>
                    )
                  ) : null}
                </View>

                {trocaMode ? (
                  <View style={{ gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm }}>
                    <Text style={styles.fieldLabel}>Novo profissional</Text>
                    {elegiveisLoading ? (
                      <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                    ) : (
                      <SelectField
                        value={trocaFuncionario}
                        onChange={(v) => setTrocaFuncionario(v as number | null)}
                        options={profissionaisElegiveis.map((p) => ({ value: p.codigo, label: p.nome_guerra }))}
                        placeholder={profissionaisElegiveis.length ? "Selecione…" : "Nenhum profissional elegível para este serviço"}
                        disabled={profissionaisElegiveis.length === 0}
                        compactWeb
                        testID="atendimento-avulso-troca-profissional-select"
                      />
                    )}
                    <Pressable
                      onPress={() => setAuthVisible(true)}
                      disabled={!trocaFuncionario || trocaSaving}
                      style={({ pressed }) => [styles.primaryBtn, (pressed || !trocaFuncionario || trocaSaving) && { opacity: 0.8 }]}
                      testID="atendimento-avulso-confirmar-troca"
                    >
                      {trocaSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.primaryBtnText}>Confirmar troca (requer autorização)</Text>}
                    </Pressable>
                  </View>
                ) : null}

                {codagenda ? (
                  <View style={styles.modalBtns}>
                    <Pressable
                      onPress={cancelarAtendimento}
                      disabled={saving}
                      style={({ pressed }) => [styles.deleteBtn, { flex: 1, flexDirection: "row", gap: 6 }, (pressed || saving) && { opacity: 0.8 }]}
                      testID="atendimento-avulso-cancelar"
                    >
                      <Ionicons name="trash-outline" size={18} color={colors.error} />
                      <Text style={{ color: colors.error, fontWeight: "600", fontSize: 15 }}>Cancelar Atendimento</Text>
                    </Pressable>
                  </View>
                ) : null}
              </View>
            </ScrollView>
          ) : null}
        </Pressable>
      </Pressable>

      {/* -------- Busca de Serviço -------- */}
      <Modal visible={servicoSearchOpen} transparent animationType="slide" onRequestClose={() => setServicoSearchOpen(false)}>
        <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => setServicoSearchOpen(false)}>
          <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Buscar Serviço</Text>
              <Pressable onPress={() => setServicoSearchOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <View style={styles.searchWrap}>
              <Ionicons name="search" size={16} color={colors.muted} />
              <TextInput
                value={servicoTerm}
                onChangeText={(t) => { setServicoTerm(t); buscarServicos(t); }}
                placeholder="Nome do serviço…"
                placeholderTextColor={colors.muted}
                style={styles.searchInput}
                autoFocus
                testID="atendimento-avulso-servico-search-input"
              />
            </View>
            {servicoLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 12 }} /> : null}
            <ScrollView style={{ maxHeight: 380 }}>
              {servicoResults.map((s) => (
                <Pressable
                  key={s.codigo}
                  onPress={() => {
                    setServicoCodigo(s.codigo);
                    setServicoDescricao(s.descricao);
                    setValor(formatBRL(s.valor).replace("R$", "").trim());
                    setServicoSearchOpen(false);
                  }}
                  style={({ pressed }) => [styles.resultRow, pressed && { backgroundColor: colors.brandTertiary }]}
                  testID={`atendimento-avulso-servico-result-${s.codigo}`}
                >
                  <View style={{ flex: 1 }}>
                    <Text style={styles.resultNome}>{s.descricao}</Text>
                    <Text style={styles.resultSub}>#{s.codigo} · {formatBRL(s.valor)}</Text>
                  </View>
                </Pressable>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      {/* -------- Busca de Cliente -------- */}
      <ClientSearchModal
        visible={clienteSearchOpen}
        onClose={() => setClienteSearchOpen(false)}
        term={clienteTerm}
        setTerm={(t) => { setClienteTerm(t); buscarClientes(t); }}
        loading={clienteLoading}
        results={clienteResults}
        onPick={(c) => { setClienteCodigo(c.codigo); setClienteNome(c.nome); setClienteSearchOpen(false); }}
        onCreate={abrirCadastroClienteRapido}
      />

      {codagenda && clienteCodigo ? (
        <AnexosAgendamentoModal visible={anexosOpen} onClose={() => setAnexosOpen(false)} conn={conn} codagenda={codagenda} clienteCodigo={clienteCodigo} />
      ) : null}
      {codagenda ? (
        <LayoutPreenchimentoModal
          visible={layoutsOpen} onClose={() => setLayoutsOpen(false)} conn={conn}
          entidade={8} codentidade={codagenda} usuarioCod={usuarioCod} title="Formulários do Atendimento"
        />
      ) : null}

      <AuthorizationSlide
        visible={authVisible}
        conn={conn}
        title="Trocar Profissional"
        message="Trocar o profissional de um atendimento já agendado exige autorização de gerente, supervisor ou administrador."
        onClose={() => setAuthVisible(false)}
        onAuthorized={({ usuario }) => { setAuthVisible(false); trocarProfissional(usuario); }}
      />

      {/* -------- Faturar -------- */}
      <Modal visible={faturarOpen} transparent animationType="slide" onRequestClose={() => setFaturarOpen(false)}>
        <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => setFaturarOpen(false)}>
          <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Faturar Atendimento</Text>
              <Pressable onPress={() => setFaturarOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={[styles.resultNome, { textAlign: "center" }]}>{clienteNome}</Text>
            <Text style={{ fontSize: 24, fontWeight: "700", color: colors.brandPrimary, textAlign: "center", marginVertical: spacing.sm }}>
              {formatBRL(parseNum(valor))}
            </Text>
            <ScrollView style={{ maxHeight: 300 }}>
              {formasPagamento.map((f) => {
                const sel = formaSel === f.codigo;
                return (
                  <Pressable
                    key={f.codigo}
                    onPress={() => setFormaSel(f.codigo)}
                    style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingVertical: 10 }}
                    testID={`atendimento-avulso-faturar-forma-${f.codigo}`}
                  >
                    <Ionicons name={sel ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                    <Text style={{ fontSize: 14, color: colors.onSurface }}>{f.descricao}</Text>
                  </Pressable>
                );
              })}
            </ScrollView>
            <View style={styles.modalBtns}>
              <Pressable onPress={() => setFaturarOpen(false)} style={[styles.secondaryBtn, { flex: 1, alignItems: "center" }]}>
                <Text style={styles.secondaryBtnText}>Cancelar</Text>
              </Pressable>
              <Pressable
                onPress={handleFaturar}
                disabled={faturarSaving || !formaSel}
                style={[styles.primaryBtn, { flex: 1, opacity: !formaSel ? 0.6 : 1 }]}
                testID="atendimento-avulso-faturar-confirmar"
              >
                {faturarSaving ? <ActivityIndicator color={colors.onBrandPrimary} /> : <Text style={styles.primaryBtnText}>Faturar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </Modal>
  );
}
