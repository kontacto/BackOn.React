// Modal "Atendimento" — vincula um item de Serviço (módulo Clínica) a um
// profissional + data/hora, via `AGENDA`/`AGENDA_PEDIDO` (ver
// `agenda_service.py`). Ampliado 2026-07-28 (escopo completo, pedido
// explícito do usuário "faça ser completo então") a partir do núcleo enxuto
// original: Situação do Atendimento (13 estados), Revisão/Garantia,
// Descartáveis, Hora Chegada/Saída, Anexos (Gestor de Documentos), Layouts
// (Formulário Dinâmico) e Troca de Profissional (com autorização de
// gerente/supervisor/master via `AuthorizationSlide`). Faturar não aparece
// aqui — item vinculado a um Pedido sempre fatura pelo próprio Pedido (só
// o agendamento AVULSO, criado direto da grade semanal, tem Faturar — ver
// `agenda/AtendimentoAvulsoModal.tsx`). Ver PENDENCIAS.md > "Transações" >
// "Pedido Geral — Fase B: Clínica (Agendamento)".
import { useEffect, useState } from "react";
import { ActivityIndicator, Modal, Platform, Pressable, Text, TextInput, View } from "react-native";
import { Ionicons } from "@/src/components/Ionicons";

import { colors, spacing } from "@/src/theme/colors";
import SelectField from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import AnexosAgendamentoModal from "@/src/components/agenda/AnexosAgendamentoModal";
import LayoutPreenchimentoModal from "@/src/components/agenda/LayoutPreenchimentoModal";
import AgendaCalendarField from "@/src/components/agenda/AgendaCalendarField";
import { useDiasAtende } from "@/src/hooks/useDiasAtende";
import { apiGet } from "@/src/utils/api";
import { styles } from "./styles";
import { AgendaItens } from "./agendaTypes";
import { SITUACOES_ATENDIMENTO, DIA_SEMANA_LABEL } from "./agendaConstants";

const isWeb = Platform.OS === "web";

type Props = {
  // Superfície mínima (`AgendaItens`), não o hook inteiro — permite
  // reaproveitar este modal tanto no Pedido Geral (`usePedidoItens`) quanto
  // na O.S. Completa (`os/useOSItens`), ver `agendaTypes.ts`.
  it: AgendaItens;
  clienteCodigo?: number | null;
  usuarioCod: number;
};

export default function AgendarModal({ it, clienteCodigo, usuarioCod }: Props) {
  const { agendarItem } = it;
  const [funcionario, setFuncionario] = useState<number | null>(null);
  const [data, setData] = useState<string | null>(null);
  const [horaIni, setHoraIni] = useState<string | null>(null);
  const [situacao, setSituacao] = useState<string>("Confirmado");
  const [revisao, setRevisao] = useState(false);
  const [garantiaInfo, setGarantiaInfo] = useState<{ dentro: boolean; expiraEm?: string; aviso?: string } | null>(null);
  const [descartavelValor, setDescartavelValor] = useState("");
  const [descartavelObs, setDescartavelObs] = useState("");
  const [horaChegada, setHoraChegada] = useState<string | null>(null);
  const [horaSaida, setHoraSaida] = useState<string | null>(null);

  // Só exibir data/horário em que o profissional realmente atende — evita o
  // usuário perder tempo marcando um dia/hora que o backend só rejeitaria
  // depois de enviar (user-directed, 2026-07-28). `diasAtende` (dias da
  // semana, 0=Domingo) vem do hook compartilhado `useDiasAtende`;
  // `horaOptions` vem da grade daquele dia específico assim que Profissional
  // + Data estão escolhidos — reaproveita o mesmo `GET /agenda/grade` já
  // usado pela tela Agenda, sem endpoint novo.
  const [horaOptions, setHoraOptions] = useState<{ value: string; label: string }[]>([]);
  const [avisoDiaSemana, setAvisoDiaSemana] = useState<string | null>(null);
  const [slotsLoading, setSlotsLoading] = useState(false);

  const [anexosOpen, setAnexosOpen] = useState(false);
  const [layoutsOpen, setLayoutsOpen] = useState(false);
  const [trocaMode, setTrocaMode] = useState(false);
  const [authVisible, setAuthVisible] = useState(false);
  const [trocaFuncionario, setTrocaFuncionario] = useState<number | null>(null);
  const [trocaSaving, setTrocaSaving] = useState(false);

  useEffect(() => {
    if (!agendarItem) return;
    const ag = agendarItem.agendamento;
    setFuncionario(ag?.profissional ? it.profissionaisAgenda.find((p) => p.nome_guerra === ag.profissional)?.codigo ?? null : null);
    setData(ag?.data ?? null);
    setHoraIni(ag?.hora_ini ?? null);
    setSituacao(ag?.situacao || "Confirmado");
    setRevisao(false);
    setGarantiaInfo(null);
    setDescartavelValor("");
    setDescartavelObs("");
    setHoraChegada(null);
    setHoraSaida(null);
    setTrocaFuncionario(null);
    setTrocaMode(false);
  }, [agendarItem, it.profissionaisAgenda]);

  const diasAtende = useDiasAtende(it.conn, funcionario);

  // Horários livres daquele dia específico — some com o campo Hora até o
  // usuário escolher Profissional + Data, evitando digitar um horário que o
  // backend só rejeitaria depois de enviar.
  useEffect(() => {
    const conn = it.conn;
    if (!conn || !funcionario || !data) {
      setHoraOptions([]);
      setAvisoDiaSemana(null);
      return;
    }
    let ativo = true;
    setSlotsLoading(true);
    (async () => {
      const j = await apiGet(conn, "/api/agenda/grade", { funcionario, data_ini: data, data_fim: data });
      if (!ativo) return;
      setSlotsLoading(false);
      const dia = j?.success && Array.isArray(j.dias) ? j.dias[0] : null;
      if (!dia || !dia.atende) {
        setAvisoDiaSemana("Profissional não atende neste dia da semana.");
        setHoraOptions([]);
        return;
      }
      setAvisoDiaSemana(null);
      const livres: string[] = (dia.slots || [])
        .filter((s: { status: string }) => s.status === "livre")
        .map((s: { hora: string }) => s.hora);
      // Mantém o horário já agendado deste MESMO atendimento na lista, mesmo
      // que a grade o mostre como "ocupado" — ele está ocupado por si mesmo.
      const ag = agendarItem?.agendamento;
      const profissionalAtual = ag?.profissional
        ? it.profissionaisAgenda.find((p) => p.nome_guerra === ag.profissional)?.codigo
        : null;
      const horaAtual = ag && ag.data === data && profissionalAtual === funcionario ? ag.hora_ini : null;
      const todos = horaAtual && !livres.includes(horaAtual) ? [...livres, horaAtual] : livres;
      todos.sort();
      setHoraOptions(todos.map((h) => ({ value: h, label: h })));
    })();
    return () => {
      ativo = false;
    };
  }, [funcionario, data, it.conn]);

  const jaAgendado = !!agendarItem?.agendamento;
  const podeSalvar = !!funcionario && !!data && !!horaIni;
  const situacaoProtegida = agendarItem?.agendamento?.situacao === "Atendido" || agendarItem?.agendamento?.situacao === "Desistência";

  const verificarGarantia = async () => {
    if (!it.conn || !clienteCodigo || !agendarItem) return;
    const j = await apiGet(it.conn, "/api/agenda/garantia", { cliente: clienteCodigo, servico: agendarItem.produto });
    if (j?.success) {
      setGarantiaInfo({ dentro: !!j.dentro_garantia, expiraEm: j.expira_em, aviso: j.aviso });
      if (j.dentro_garantia) setRevisao(true);
    }
  };

  const confirmarSalvar = () => {
    if (!funcionario || !data || !horaIni) return;
    it.salvarAgendamento({
      funcionario, data, hora_ini: horaIni,
      situacao_atendimento: situacao, revisao,
      descartavel_valor: descartavelValor ? parseFloat(descartavelValor.replace(",", ".")) : null,
      descartavel_obs: descartavelObs,
      hora_chegada: horaChegada, hora_saida: horaSaida,
    });
  };

  return (
    <Modal visible={!!agendarItem} transparent animationType="slide" onRequestClose={() => it.setAgendarItem(null)}>
      <Pressable style={[styles.modalBg, isWeb && styles.modalBgWebCompact]} onPress={() => it.setAgendarItem(null)}>
        <Pressable style={[styles.modalCard, isWeb && styles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>{jaAgendado ? "Atendimento" : "Agendar"}</Text>
            <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.md }}>
              {jaAgendado && agendarItem?.agendamento ? (
                <IconButtonWithTooltip
                  icon="attach-outline"
                  label="Anexos"
                  onPress={() => setAnexosOpen(true)}
                  testID="agendar-modal-anexos-btn"
                />
              ) : null}
              {jaAgendado && agendarItem?.agendamento ? (
                <IconButtonWithTooltip
                  icon="document-text-outline"
                  label="Formulários"
                  onPress={() => setLayoutsOpen(true)}
                  testID="agendar-modal-layouts-btn"
                />
              ) : null}
              {jaAgendado ? (
                <IconButtonWithTooltip
                  icon="swap-horizontal-outline"
                  label="Trocar profissional"
                  onPress={() => setTrocaMode((v) => !v)}
                  testID="agendar-modal-trocar-prof-btn"
                />
              ) : null}
              <Pressable onPress={() => it.setAgendarItem(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
          </View>
          {agendarItem ? (
            <View style={{ gap: spacing.sm }}>
              <View style={styles.selProdBox}>
                <Text style={styles.itemDesc} numberOfLines={2}>{agendarItem.descricao || agendarItem.produto}</Text>
              </View>
              <Text style={styles.itensHintText}>
                Escolha o profissional e o horário do atendimento. O sistema confere automaticamente se o
                profissional atende nesse dia/horário e se ainda há vaga disponível.
              </Text>
              {situacaoProtegida ? (
                <Text style={[styles.itensHintText, { color: colors.error }]}>
                  Este atendimento já está &quot;{agendarItem.agendamento?.situacao}&quot; — alterar exige
                  autorização de gerente/supervisor (o campo &quot;autorizado_por&quot; é preenchido ao trocar de
                  profissional; para alterar outros campos deste atendimento finalizado, use Trocar Profissional
                  como forma de reabrir com autorização).
                </Text>
              ) : null}
              <View>
                <Text style={styles.fieldLabel}>Profissional</Text>
                {it.profissionaisLoading ? (
                  <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 8 }} />
                ) : (
                  <SelectField
                    value={funcionario}
                    onChange={(v) => setFuncionario(v as number | null)}
                    options={it.profissionaisAgenda.map((p) => ({ value: p.codigo, label: p.nome_guerra }))}
                    placeholder={it.profissionaisAgenda.length ? "Selecione…" : "Nenhum profissional habilitado para este serviço"}
                    disabled={it.profissionaisAgenda.length === 0}
                    compactWeb
                    testID="pedido-form-agendar-profissional"
                  />
                )}
                {funcionario && diasAtende ? (
                  <Text style={styles.resultSub} testID="pedido-form-agendar-dias-atende">
                    {diasAtende.size
                      ? `Atende: ${Array.from(diasAtende).sort().map((d) => DIA_SEMANA_LABEL[d]).join(", ")}`
                      : "Nenhum dia de atendimento configurado para este profissional (ver aba Horários no cadastro dele)."}
                  </Text>
                ) : null}
              </View>
              {/* `zIndex` elevado — o calendário escapa deste row via
                  `position:absolute` pra desenhar o popup por cima dos
                  campos seguintes (Situação, Hora Chegada/Saída, ...), que
                  são IRMÃOS deste `View`, não do wrapper interno do
                  calendário; sem isso o popup ficava misturado com o texto
                  desses campos por trás dele. Mesmo bug de stacking já
                  documentado em CLAUDE.md > "Modo Didático" > tooltip
                  sempre por cima. */}
              <View style={[styles.qtdRow, { zIndex: 2 }]}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Data</Text>
                  <AgendaCalendarField value={data} onChange={(v) => setData(v || null)} diasAtende={diasAtende} testID="pedido-form-agendar-data" />
                  {avisoDiaSemana ? (
                    <Text style={{ fontSize: 12, color: colors.error, marginTop: 4 }} testID="pedido-form-agendar-aviso-dia">
                      {avisoDiaSemana}
                    </Text>
                  ) : null}
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
                      testID="pedido-form-agendar-hora"
                    />
                  )}
                </View>
              </View>
              <View>
                <Text style={styles.fieldLabel}>Situação do Atendimento</Text>
                <SelectField
                  value={situacao}
                  onChange={(v) => setSituacao(v as string)}
                  options={SITUACOES_ATENDIMENTO.map((s) => ({ value: s, label: s }))}
                  compactWeb
                  testID="agendar-modal-situacao"
                />
              </View>
              <View style={styles.qtdRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Hora Chegada</Text>
                  <WebDateField value={horaChegada} onChange={setHoraChegada} type="time" icon="time-outline" testID="agendar-modal-hora-chegada" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.fieldLabel}>Hora Saída</Text>
                  <WebDateField value={horaSaida} onChange={setHoraSaida} type="time" icon="time-outline" testID="agendar-modal-hora-saida" />
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
                    testID="agendar-modal-descartavel-valor"
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
                    testID="agendar-modal-descartavel-obs"
                  />
                </View>
              </View>
              <View style={{ gap: 4 }}>
                <Pressable
                  onPress={() => setRevisao((v) => !v)}
                  style={{ flexDirection: "row", alignItems: "center", gap: 6 }}
                  testID="agendar-modal-revisao-checkbox"
                >
                  <Ionicons name={revisao ? "checkbox" : "square-outline"} size={18} color={colors.brandPrimary} />
                  <Text style={{ fontSize: 13, color: colors.onSurface }}>Revisão/Garantia (grátis)</Text>
                </Pressable>
                {clienteCodigo ? (
                  <Pressable onPress={verificarGarantia} testID="agendar-modal-verificar-garantia">
                    <Text style={{ fontSize: 12, color: colors.brandPrimary, textDecorationLine: "underline" }}>
                      Verificar garantia/revisão deste serviço para este cliente
                    </Text>
                  </Pressable>
                ) : null}
                {garantiaInfo ? (
                  garantiaInfo.aviso ? (
                    <Text style={styles.resultSub}>{garantiaInfo.aviso}</Text>
                  ) : garantiaInfo.dentro ? (
                    <Text style={{ fontSize: 12, color: colors.success }}>
                      Dentro da garantia/revisão até {garantiaInfo.expiraEm}.
                    </Text>
                  ) : (
                    <Text style={styles.resultSub}>Fora do prazo de garantia/revisão (ou nunca atendido antes).</Text>
                  )
                ) : null}
              </View>
              {trocaMode ? (
                <View style={{ gap: spacing.xs, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: spacing.sm }}>
                  <Text style={styles.fieldLabel}>Novo profissional</Text>
                  <SelectField
                    value={trocaFuncionario}
                    onChange={(v) => setTrocaFuncionario(v as number | null)}
                    options={it.profissionaisAgenda.map((p) => ({ value: p.codigo, label: p.nome_guerra }))}
                    compactWeb
                    testID="agendar-modal-troca-profissional-select"
                  />
                  <Pressable
                    onPress={() => setAuthVisible(true)}
                    disabled={!trocaFuncionario || trocaSaving}
                    style={({ pressed }) => [
                      styles.primaryBtn,
                      (pressed || !trocaFuncionario || trocaSaving) && { opacity: 0.8 },
                    ]}
                    testID="agendar-modal-confirmar-troca"
                  >
                    {trocaSaving
                      ? <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                      : <Text style={styles.primaryBtnText}>Confirmar troca (requer autorização)</Text>}
                  </Pressable>
                </View>
              ) : null}
              <View style={styles.modalBtns}>
                {jaAgendado ? (
                  <Pressable
                    onPress={it.cancelarAgendamento}
                    disabled={it.agendaSaving}
                    style={({ pressed }) => [styles.deleteBtn, (pressed || it.agendaSaving) && { opacity: 0.8 }]}
                    testID="pedido-form-agendar-cancelar"
                  >
                    <Ionicons name="trash-outline" size={18} color={colors.error} />
                  </Pressable>
                ) : null}
                <Pressable
                  onPress={confirmarSalvar}
                  disabled={!podeSalvar || it.agendaSaving}
                  style={({ pressed }) => [
                    styles.primaryBtn, { flex: 1 },
                    (pressed || !podeSalvar || it.agendaSaving) && { opacity: 0.8 },
                  ]}
                  testID="pedido-form-agendar-save"
                >
                  {it.agendaSaving
                    ? <ActivityIndicator color={colors.onBrandPrimary} size="small" />
                    : <Text style={styles.primaryBtnText}>{jaAgendado ? "Salvar" : "Agendar"}</Text>}
                </Pressable>
              </View>
            </View>
          ) : null}
        </Pressable>
      </Pressable>

      {jaAgendado && agendarItem?.agendamento && clienteCodigo ? (
        <AnexosAgendamentoModal
          visible={anexosOpen}
          onClose={() => setAnexosOpen(false)}
          conn={it.conn}
          codagenda={agendarItem.agendamento.codagenda}
          clienteCodigo={clienteCodigo}
        />
      ) : null}
      {jaAgendado && agendarItem?.agendamento ? (
        <LayoutPreenchimentoModal
          visible={layoutsOpen}
          onClose={() => setLayoutsOpen(false)}
          conn={it.conn}
          entidade={8}
          codentidade={agendarItem.agendamento.codagenda}
          usuarioCod={usuarioCod}
          title="Formulários do Atendimento"
        />
      ) : null}

      <AuthorizationSlide
        visible={authVisible}
        conn={it.conn}
        title="Trocar Profissional"
        message="Trocar o profissional de um atendimento já agendado exige autorização de gerente, supervisor ou administrador."
        onClose={() => setAuthVisible(false)}
        onAuthorized={async ({ usuario }) => {
          setAuthVisible(false);
          if (!trocaFuncionario) return;
          setTrocaSaving(true);
          const ok = await it.trocarProfissionalAgenda(trocaFuncionario, usuario);
          setTrocaSaving(false);
          if (ok) setTrocaMode(false);
        }}
      />
    </Modal>
  );
}
