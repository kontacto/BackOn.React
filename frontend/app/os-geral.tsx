// O.S. Completa (`FrmTraOsNew.frm`) — Fase 1, núcleo, módulo Assistência
// Técnica. Web-only (mesmo padrão de `pedido-geral.tsx`) — segue o mesmo
// esqueleto: `PedidoHeader` + `ItemList` (agora com `tela="OS_COMP"`, ver
// CLAUDE.md/ItemList.tsx) + `ClienteSection`/`ClientSearchModal`
// reaproveitados sem alteração (a regra de busca de cliente já é
// documentada como válida pra O.S. também). Itens/Forma de Pagamento/
// Desconto Geral/Descontos/Análise reaproveitam as MESMAS regras de
// negócio de `os_service.py`/`os_itens_service.py` (chamadas via
// `/api/os-completo/...`/`/api/os/{codigo}/formas-pagamento`) — nada
// duplicado aqui, só orquestração de tela.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActivityIndicator, Linking, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, TouchableOpacity, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { apiGet, apiSend, friendlyCatchError } from "@/src/utils/api";
import { usePermissions } from "@/src/permissions";
import LockedView from "@/src/components/LockedView";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import InfoTooltip from "@/src/components/InfoTooltip";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { formatDateBR, todayISO } from "@/src/utils/format";
import { styles as pedidoStyles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo, AreaAtuacao, Funcionario, ToastTone } from "@/src/components/pedido/types";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import PedidoHeader from "@/src/components/pedido/PedidoHeader";
import ItemList from "@/src/components/pedido/ItemList";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import FormaPagamentoField from "@/src/components/pedido/FormaPagamentoField";
import GeneralDiscountModal from "@/src/components/pedido/GeneralDiscountModal";
import DiscountsReportModal from "@/src/components/pedido/DiscountsReportModal";
import ScreenToast from "@/src/components/pedido/ScreenToast";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import { useEmitirNotaFiscal } from "@/src/hooks/useEmitirNotaFiscal";
import NotaFiscalCard from "@/src/components/fiscal/NotaFiscalCard";
import EquipamentoSearchModal, { EquipamentoRow } from "@/src/components/EquipamentoSearchModal";
import { OSData } from "@/src/components/os/types";
import { useOSItens } from "@/src/components/os/useOSItens";
import { useOSEquipamentos } from "@/src/components/os/useOSEquipamentos";
import OSEquipamentoCard from "@/src/components/os/OSEquipamentoCard";
import OSItemModal from "@/src/components/os/OSItemModal";
import OSTotaisResumo from "@/src/components/os/OSTotaisResumo";
import PontuacaoModal from "@/src/components/os/PontuacaoModal";
import AlterarExecutorModal from "@/src/components/os/AlterarExecutorModal";
import FaturarBucketModal from "@/src/components/os/FaturarBucketModal";
import AgendarModal from "@/src/components/pedido/AgendarModal";
import AuthorizationSlide from "@/src/components/AuthorizationSlide";
import AutorizacaoItensModal from "@/src/components/os/AutorizacaoItensModal";
import TempoGastoModal from "@/src/components/os/TempoGastoModal";
import RequisicoesVinculadasModal from "@/src/components/os/RequisicoesVinculadasModal";
import AnexosOSModal from "@/src/components/os/AnexosOSModal";
import ReciboOSModal from "@/src/components/os/ReciboOSModal";
import LayoutPreenchimentoModal from "@/src/components/agenda/LayoutPreenchimentoModal";

// entidade=7 ("os") no Motor de Layout — ver _ENTIDADE_COLUNA em
// backend/services/layout_service.py.
const LAYOUT_ENTIDADE_OS = 7;

const AJUDA_OS_ITENS: HelpItem[] = [
  {
    titulo: "Status O.S.",
    texto: "Etapa atual do atendimento (ex.: Aguardando aprovação do orçamento, Em execução, Executado) — puramente informativo, não altera nenhuma regra de negócio.",
    icon: { lib: "ion", name: "flag-outline" },
  },
  {
    titulo: "Tipo O.S.",
    texto: "Classificação do tipo de atendimento (ex.: Suporte, Desenvolvimento, Venda) — usada em relatórios e filtros.",
    icon: { lib: "ion", name: "pricetags-outline" },
  },
  {
    titulo: "Técnico Responsável",
    texto: "Funcionário responsável geral pela O.S. — diferente do Vendedor/Executor de cada item, que pode variar linha a linha.",
    icon: { lib: "ion", name: "person-circle-outline" },
  },
  {
    titulo: "Equipamentos",
    texto: "No módulo Assistência Técnica, uma O.S. pode ter vários equipamentos vinculados (ex.: mais de um ar-condicionado atendido na mesma visita) — toque em \"Adicionar equipamento\" para buscar (ou cadastrar) e vincular; cada equipamento tem seu próprio Defeito Reclamado, Serviço Executado, Serviço a Executar, Diagnóstico e Status, gravados com o botão \"Salvar\" do próprio card. \"Cancelar\" um equipamento remove o atendimento daquele item específico sem cancelar a O.S. inteira. Só disponível depois de gravar a O.S. pela primeira vez. No módulo Oficina, em vez disso aparecem os dados do veículo (Placa, Marca, Modelo, Ano, KM, Chassi) — Marca e Modelo vêm das tabelas auxiliares já usadas em outras telas.",
    icon: { lib: "ion", name: "hardware-chip-outline" },
  },
  {
    titulo: "Vendedor / Executor / Situação do item",
    texto: "Cada item da O.S. tem seu próprio Vendedor e Executor (diferente do Pedido, que tem só um vendedor no cabeçalho). \"Situação\" define quem paga aquele item: Cliente paga, Garantia, Interno ou Contrato — usada nos totais por situação, logo acima da lista de itens.",
    icon: { lib: "ion", name: "people-outline" },
  },
  {
    titulo: "Fechar O.S.",
    texto: "Bloqueia novas alterações na O.S. e exige a Forma de Pagamento definida. Pode ser reaberta enquanto não for faturada.",
    icon: { lib: "ion", name: "lock-closed-outline" },
  },
  {
    titulo: "Faturar O.S.",
    texto: "Gera a Comanda de venda a partir da O.S. já Fechada — só disponível depois de Fechar (diferente do Pedido Bar, que fecha e fatura junto).",
    icon: { lib: "ion", name: "cash-outline" },
  },
  {
    titulo: "Reabrir",
    texto: "Volta uma O.S. Fechada para Aberta, permitindo alterar itens novamente.",
    icon: { lib: "ion", name: "lock-open-outline" },
  },
  {
    titulo: "Cancelar",
    texto: "Cancela a O.S. (Aberta ou Fechada) e devolve ao estoque a reserva de peças já feita pelos itens incluídos.",
    icon: { lib: "ion", name: "close-circle-outline" },
  },
  {
    titulo: "Pontuação de Técnicos",
    texto: "Avalie de 0 a 999 o desempenho do Técnico (Executor), do Vendedor e do Atendente de cada item — só aparece quando a O.S. já tem itens incluídos, logo acima da lista.",
    icon: { lib: "ion", name: "star-outline" },
  },
  {
    titulo: "Autorização de Itens",
    texto: "Só aparece quando a empresa exige Autorização e/ou Expedição de itens da O.S. (configurado em Controle do Sistema). Marque os itens e toque em Autorizar para liberar a saída do estoque — enquanto não autorizado, o item ainda não reservou o estoque. Se a Expedição também for exigida, o item precisa ser expedido (separado fisicamente) antes de poder ser autorizado.",
    icon: { lib: "ion", name: "shield-checkmark-outline" },
  },
  {
    titulo: "Tempo Gasto por Serviço",
    texto: "Registre o horário de início e fim do atendimento de cada serviço, por técnico — o tempo gasto é calculado automaticamente. Só é possível incluir, alterar ou excluir enquanto a O.S. estiver Aberta; com a O.S. Fechada, Faturada ou Cancelada dá pra consultar os lançamentos já feitos.",
    icon: { lib: "ion", name: "time-outline" },
  },
  {
    titulo: "Requisições Vinculadas",
    texto: "Mostra os produtos requisitados do estoque (Transações > Movimentações > Requisição) que estão vinculados a esta O.S. — somente consulta, não é possível incluir, alterar ou excluir requisições por aqui.",
    icon: { lib: "ion", name: "clipboard-outline" },
  },
  {
    titulo: "Agendar item de Serviço",
    texto: "Aparece nos itens de Serviço quando o módulo Assistência Técnica está ligado — escolha um profissional e um horário para o atendimento. O sistema confere automaticamente se o profissional atende naquele dia/horário e se ainda há vaga disponível.",
    icon: { lib: "ion", name: "calendar-outline" },
  },
  {
    titulo: "Criar Cópia",
    texto: "Cria uma nova O.S. Aberta com os mesmos dados do cliente, equipamento, técnico e itens desta O.S. — só produtos/serviços ainda ativos no cadastro são copiados, com preço atualizado pelo cadastro atual e sem desconto/acréscimo. Anexos, agendamentos e histórico não são copiados. Disponível em qualquer situação da O.S.",
    icon: { lib: "ion", name: "copy-outline" },
  },
  {
    titulo: "Revisão Programada / Doc. Origem",
    texto: "\"Revisões\" gera datas futuras (a cada 30 dias) para o cliente voltar numa manutenção periódica. Quando o Tipo O.S. escolhido for Revisão ou Garantia (e a empresa exigir), aparece o campo \"Doc. Origem\": informe a O.S. (ou Pedido) de origem para vincular esta O.S. a uma manutenção/venda anterior — o sistema confere se é do mesmo cliente e se já está faturada, e uma O.S. de Revisão precisa de uma data programada disponível na O.S. de origem. Se a conferência falhar, é possível prosseguir mesmo assim com autorização de um gerente/supervisor.",
    icon: { lib: "ion", name: "repeat-outline" },
  },
  {
    titulo: "Alteração de Executor",
    texto: "Com a O.S. já Fechada ou Faturada, corrige quem foi o Vendedor e/ou o Executor (técnico) de um item já lançado, sem precisar reabrir a O.S. — preço, quantidade e desconto continuam bloqueados nessa situação. Opcionalmente, aplica a mesma troca a todos os demais itens que tinham o mesmo Vendedor/Executor.",
    icon: { lib: "ion", name: "person-outline" },
  },
  {
    titulo: "Forma de Pag. Garantia / Faturamento em blocos",
    texto: "Cada item da O.S. tem uma Situação (Cliente paga, Garantia, Interno ou Contrato). Ao Faturar, itens de Cliente paga viram uma Comanda; itens de Garantia/Interno/Contrato viram OUTRA Comanda, com sua própria forma de pagamento (\"Forma de Pag. Garantia\", precisa estar definida antes de faturar esse bloco). Se a O.S. tiver os dois tipos de item pendentes ao mesmo tempo, a tela pergunta o que faturar agora — dá pra faturar só um bloco e voltar depois pra faturar o outro, mesmo com a O.S. já Faturada.",
    icon: { lib: "ion", name: "git-branch-outline" },
  },
  {
    titulo: "Formulários (Layouts)",
    texto: "Abre os checklists/formulários dinâmicos disponíveis para esta O.S. (ex.: um relatório de visita técnica cadastrado em Configurações > Cadastro de Layout) — permite preencher um novo ou consultar preenchimentos anteriores. Só aparece com a O.S. já gravada.",
    icon: { lib: "ion", name: "document-text-outline" },
  },
];

// Funções que podem alterar o Atendente/Técnico: 01 (Administrador) e 02
// (Gerente) — mesma regra já usada no Pedido/O.S. Mobile.
const GESTOR_FUNCOES = ["01", "02"];

// "2026-08-14T13:33:45.667000" → "14/08/2026 13:33" — `formatDateBR` (utils/
// format.ts) só trata data pura (split por "-"), quebra com o "T..." colado
// no dia. Usado só nesta tela pra exibir check-in/check-out.
function formatCheckinDateTime(iso: string | null): string {
  if (!iso) return "";
  const [datePart, timePart] = iso.split("T");
  const [y, m, d] = (datePart || "").split("-");
  const hm = (timePart || "").slice(0, 5);
  return d ? `${d}/${m}/${y}${hm ? ` ${hm}` : ""}` : iso;
}

function mapsUrl(lat: number | null, lng: number | null): string | null {
  if (lat == null || lng == null) return null;
  return `https://www.google.com/maps?q=${lat},${lng}`;
}

export default function OSGeralScreen() {
  const router = useRouter();

  if (Platform.OS !== "web") {
    return (
      <LockedView
        title="Disponível somente na versão web"
        message="A O.S. Completa está disponível apenas no web. Use a pré-venda rápida (O.S. Mobile) pelo app."
        testID="os-geral-web-only"
      />
    );
  }

  return <OSGeralWebScreen router={router} />;
}

function OSGeralWebScreen({ router }: { router: ReturnType<typeof useRouter> }) {
  const { can, isMaster, classe, moduleOn } = usePermissions();
  const params = useLocalSearchParams<{ os?: string }>();
  const editing = !!params.os;
  const osId = params.os ? parseInt(String(params.os), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<{ msg: string; tone: ToastTone } | null>(null);
  const tref = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((m: string, t: ToastTone = "info") => {
    setToast({ msg: m, tone: t });
    if (tref.current) clearTimeout(tref.current);
    tref.current = setTimeout(() => setToast(null), 1500);
  }, []);

  const [os, setOs] = useState<OSData | null>(null);
  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [clienteResumo, setClienteResumo] = useState<ClienteResumo | null>(null);
  const [loadingResumo, setLoadingResumo] = useState(false);
  const [vinculoProjeto, setVinculoProjeto] = useState<{ codigo: number } | null>(null);

  const [areaAtuacao, setAreaAtuacao] = useState<number | null>(null);
  const [descricaoCliente, setDescricaoCliente] = useState("");
  const [obs, setObs] = useState("");
  const [resumo, setResumo] = useState("");
  const [statusOs, setStatusOs] = useState<number | null>(null);
  const [atendente, setAtendente] = useState<number | null>(null);
  const [formaPagamento, setFormaPagamento] = useState("");
  // Forma de Pagamento de Garantia — usada só pra faturar o bloco de itens
  // Garantia/Interno/Contrato (situação<>0) quando bifurcado do bloco
  // Cliente paga (situação=0); ver "Bifurcação de faturamento
  // Garantia×Cliente" no PENDENCIAS.md.
  const [formaPagamentoGarantia, setFormaPagamentoGarantia] = useState("");
  const handleFormaPagModalChanged = useCallback(async () => {
    if (!conn || !osId) return;
    const j = await apiGet(conn, `/api/os-completo/${osId}`);
    if (j?.success && j.os) setFormaPagamento(j.os.forma_pagamento || "");
  }, [conn, osId]);
  const [situacao, setSituacao] = useState("A");

  // Veículo (Oficina — Placa/Marca/Modelo/Ano/KM/Chassi, mesmos campos e
  // mesmas tabelas auxiliares Marcas/Modelos já usados em `os-form.tsx`,
  // ver "Oficina (2ª etapa)" no PENDENCIAS.md) x Equipamento (Assistência,
  // busca real — ver CLAUDE.md > "Campos de Identidade Precisam de
  // Mecanismo de Busca").
  const [placa, setPlaca] = useState("");
  const [marca, setMarca] = useState("");
  const [modelo, setModelo] = useState("");
  const [km, setKm] = useState("");
  const [ano, setAno] = useState("");
  const [chassi, setChassi] = useState("");
  // `controle.exige_chassi_os` — Chassi obrigatório na O.S. Oficina. Só mostra
  // asterisco/pré-valida; o backend é quem reforça de verdade (os_completo_service.py).
  const [exigeChassiOs, setExigeChassiOs] = useState(false);
  const [marcasList, setMarcasList] = useState<{ codigo: string; descricao: string }[]>([]);
  const [modelosList, setModelosList] = useState<{ codigo: string; descricao: string }[]>([]);
  const [equipModalOpen, setEquipModalOpen] = useState(false);
  const [equipTerm, setEquipTerm] = useState("");
  const [equipResults, setEquipResults] = useState<EquipamentoRow[]>([]);
  const [equipLoading, setEquipLoading] = useState(false);

  // Campos extras da O.S. Completa.
  const [referenciaOs, setReferenciaOs] = useState("");
  const [tecnicoResponsavel, setTecnicoResponsavel] = useState<number | null>(null);
  // Auxiliar do técnico (opcional, regra 11 do AssistenciaTecnicaCampo.md)
  // — só o cadastro nesta rodada, sem o fluxo de "auxiliar edita com a
  // credencial do titular".
  const [auxiliarTecnico, setAuxiliarTecnico] = useState<number | null>(null);
  const [posicaoOs, setPosicaoOs] = useState<number | null>(null);
  const [previsaoTermino, setPrevisaoTermino] = useState<string | null>(null);
  const [dataTermino, setDataTermino] = useState<string | null>(null);
  const [horaFechamento, setHoraFechamento] = useState("");
  // Data/Hora do Atendimento Agendado (regra 2, AssistenciaTecnicaCampo.md
  // — "quando o atendimento foi agendado, não só quando foi executado").
  // Colunas LEGADAS (os.data_agendamento/hora_agendamento) reativadas
  // 2026-08-15 pra alimentar a Lista de Atendimento por Calendário
  // (frontend/app/atendimento-lista.tsx) — é aqui, na retaguarda, que
  // alguém marca a data/hora do atendimento do técnico.
  const [dataAgendamento, setDataAgendamento] = useState<string | null>(null);
  const [horaAgendamento, setHoraAgendamento] = useState("");
  // Agendar um ITEM (AgendarModal, dentro de `it`/useOSItens abaixo) agora
  // TAMBÉM alimenta esses campos no backend (user-directed 2026-08-15) —
  // recarrega só o cabeçalho pra refletir isso na tela sem precisar sair e
  // voltar, mesmo padrão de `handleFormaPagModalChanged` acima.
  const handleAgendamentoItemChanged = useCallback(async () => {
    if (!conn || !osId) return;
    const j = await apiGet(conn, `/api/os-completo/${osId}`);
    if (j?.success && j.os) {
      setDataAgendamento(j.os.data_agendamento || null);
      setHoraAgendamento((j.os.hora_agendamento || "").slice(0, 5));
    }
  }, [conn, osId]);

  // Doc. Origem / Revisão Programada (migração de `Campo(150)`/`Campo(151)`/
  // `Option9`/`Option10` em `FrmTraOsNew.frm`) — ver PENDENCIAS.md > "O.S.
  // Completa" > "Doc. Origem / Revisão Programada".
  const [docOrigem, setDocOrigem] = useState("");
  const [docOrigemTipo, setDocOrigemTipo] = useState<"O" | "P">("O");
  const [qtdRevisoes, setQtdRevisoes] = useState("");
  const [docOrigemAuthVisible, setDocOrigemAuthVisible] = useState(false);

  const [areas, setAreas] = useState<AreaAtuacao[]>([]);
  const [funcionarios, setFuncionarios] = useState<Funcionario[]>([]);
  const [formasPag, setFormasPag] = useState<{ codigo: string; descricao: string }[]>([]);
  const [statusOsList, setStatusOsList] = useState<{ codigo: number; descricao: string }[]>([]);
  const [tipoOsList, setTipoOsList] = useState<{ codigo: number; descricao: string }[]>([]);
  const [userFuncao, setUserFuncao] = useState<number | null>(null);
  const canChangeGestores = isMaster || GESTOR_FUNCOES.includes(String(userFuncao ?? "").padStart(2, "0"));

  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [clienteQuickTerm, setClienteQuickTerm] = useState("");
  const [clienteQuickLoading, setClienteQuickLoading] = useState(false);

  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [funcaoCod, setFuncaoCod] = useState<number>(1);

  const sit = (os?.situacao || "A").toUpperCase();
  const isAberto = !editing || sit === "A";
  const isFechado = sit === "F";
  const camposTravados = editing && !isAberto && !isFechado;

  const sitColor = useMemo(() => SIT_COLOR[sit] || colors.muted, [sit]);

  const it = useOSItens({
    conn, editing, osId, isAberto, usuarioCod, funcaoCod, classe, master: isMaster, showToast,
    servicosOn: moduleOn("servicos"), onAgendamentoAlterado: handleAgendamentoItemChanged,
  });
  const eq = useOSEquipamentos({ conn, editing, osId, usuarioCod, classe, showToast });

  useEffect(() => {
    (async () => {
      const s = await getSession();
      const cs = await listConnections();
      const c = cs.find((x) => x.empresa === s?.empresa) || null;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      const fid = func?.codigo_int ?? func?.codigo;
      const uid = fid != null ? parseInt(String(fid), 10) : null;
      const masterFlag = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setUsuarioCod(masterFlag ? -2 : (uid ?? -2));
      const cf = func?.funcao;
      const fc = cf != null ? parseInt(String(cf), 10) : NaN;
      setFuncaoCod(masterFlag ? 1 : (Number.isFinite(fc) && fc > 0 ? fc : 1));
      setUserFuncao(Number.isFinite(fc) ? fc : null);
      if (!editing && uid != null) setAtendente(uid);

      if (c) {
        try {
          const [ra, rf, rfp, rso, rto, rm, rctrl] = await Promise.all([
            apiGet(c, `/api/area-atuacao`).catch(() => null),
            apiGet(c, `/api/funcionarios`).catch(() => null),
            apiGet(c, `/api/forma-pagamento`).catch(() => null),
            apiGet(c, `/api/status-os`).catch(() => null),
            apiGet(c, `/api/tipo-os`).catch(() => null),
            apiGet(c, `/api/tabelas/marcas`, { marca_produto: "false" }).catch(() => null),
            apiGet(c, `/api/controle/empresa`).catch(() => null),
          ]);
          if (ra?.success) {
            const arr = ra.items || [];
            setAreas(arr);
            if (arr.length === 1) setAreaAtuacao((prev) => (prev == null ? arr[0].codigo : prev));
          }
          if (rf?.success) setFuncionarios(rf.items || []);
          if (rfp?.success) setFormasPag(rfp.items || []);
          if (rso?.success) setStatusOsList(rso.items || []);
          if (rto?.success) setTipoOsList(rto.items || []);
          if (rm?.success) setMarcasList(rm.items || []);
          if (rctrl?.success) setExigeChassiOs(!!rctrl.exige_chassi_os);
        } catch {
          // combos ficam vazios
        }
      }

      if (editing && osId && c) {
        try {
          const j = await apiGet(c, `/api/os-completo/${osId}`);
          if (j?.success && j.os) {
            const o: OSData = j.os;
            setOs(o);
            if (o.cliente) setCliente({ codigo: o.cliente, nome: o.cliente_nome, cgc_cpf: o.cliente_cgc, telefone: "" });
            setAreaAtuacao(o.area_atuacao ?? null);
            setDescricaoCliente(o.descricao_cliente || "");
            setObs(o.obs || "");
            setResumo(o.resumo || "");
            setStatusOs(o.status_os ?? null);
            setAtendente(o.atendente ?? null);
            setFormaPagamento(o.forma_pagamento || "");
            setFormaPagamentoGarantia(o.forma_pagamento_garantia || "");
            setSituacao(o.situacao || "A");
            setPlaca(o.placa || "");
            setMarca(o.marca || "");
            setModelo(o.modelo || "");
            setKm(o.km != null ? String(o.km) : "");
            setAno(o.ano || "");
            setChassi(o.chassi || "");
            setReferenciaOs(o.referencia_os || "");
            setTecnicoResponsavel(o.tecnico_responsavel ?? null);
            setAuxiliarTecnico(o.auxiliar_tecnico ?? null);
            setPosicaoOs(o.posicao_os ?? null);
            setPrevisaoTermino(o.previsao_termino || null);
            setDataTermino(o.data_termino || null);
            setHoraFechamento((o.hora_fechamento || "").slice(0, 5));
            setDataAgendamento(o.data_agendamento || null);
            setHoraAgendamento((o.hora_agendamento || "").slice(0, 5));
            setDocOrigem(o.os_original != null ? String(o.os_original) : "");
            setDocOrigemTipo(o.tipo_doc_original === "P" ? "P" : "O");
            setQtdRevisoes(o.qtd_revisoes != null ? String(o.qtd_revisoes) : "");
          } else {
            showToast(j?.message || "Erro ao carregar OS.", "error");
          }
        } catch (e) {
          showToast(`Erro ao carregar: ${e instanceof Error ? e.message : String(e)}`, "error");
        }
        try {
          const jv = await apiGet(c, `/api/projetos-vinculo`, { tipo_doc: "OSS", num_doc: osId });
          if (jv?.success && jv.projeto) setVinculoProjeto({ codigo: jv.projeto.codigo });
        } catch {
          // chip é só um atalho de descoberta — falha silenciosa não impede o resto da tela
        }
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Modelos da marca selecionada (Veículo, módulo Oficina) — mesmo padrão
  // reativo de `os-form.tsx`.
  useEffect(() => {
    if (!conn || !marca) { setModelosList([]); return; }
    apiGet(conn, `/api/tabelas/modelos`, { cod_marca: marca })
      .then((j) => setModelosList(j?.success ? j.items || [] : []))
      .catch(() => setModelosList([]));
  }, [conn, marca]);

  useEffect(() => {
    if (!conn || !cliente?.codigo) { setClienteResumo(null); return; }
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

  useEffect(() => {
    if (cliente) setClienteQuickTerm(cliente.nome);
  }, [cliente]);

  useEffect(() => {
    if (!equipModalOpen || !conn || !cliente?.codigo) { setEquipResults([]); return; }
    const t = setTimeout(async () => {
      setEquipLoading(true);
      try {
        const j = await apiGet(conn, `/api/equipamentos`, { cliente: cliente.codigo, busca: equipTerm });
        setEquipResults(j?.success ? (j.items || []) : []);
      } catch {
        setEquipResults([]);
      } finally {
        setEquipLoading(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [equipTerm, equipModalOpen, conn, cliente?.codigo]);

  const handleClienteQuickChange = (v: string) => {
    setClienteQuickTerm(v);
    if (cliente) setCliente(null);
  };

  const resolveClienteQuickTerm = async (term: string) => {
    const t = term.trim();
    if (!t || !conn) return;
    setClienteQuickLoading(true);
    try {
      const j = await apiGet(conn, `/api/clientes/find/search`, { term: t });
      const items: ClienteRow[] = j?.items || [];
      if (items.length === 1) {
        setCliente(items[0]);
      } else {
        setSearchTerm(t);
        setSearchResults([]);
        setSearchOpen(true);
      }
    } catch {
      // silencioso
    } finally {
      setClienteQuickLoading(false);
    }
  };

  const handleCreateClienteFromQuick = (term: string) => {
    router.push({ pathname: "/cliente-form", params: clienteSearchParams(term) });
  };

  const isOficina = moduleOn("Oficina");
  const isAssist = moduleOn("Assistencia");

  const handleSave = async (autorizadoPor?: string) => {
    if (!conn) return;
    if (!cliente) { showToast("Selecione um cliente.", "error"); return; }
    if (atendente == null) { showToast("A O.S. precisa de um atendente.", "error"); return; }
    if (isOficina && !isAssist && exigeChassiOs && !chassi.trim()) {
      showToast("Chassi é obrigatório para O.S. do segmento Oficina.", "error");
      return;
    }
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        cliente: cliente.codigo,
        area_atuacao: areaAtuacao,
        descricao_cliente: descricaoCliente,
        obs, resumo,
        status_os: statusOs,
        atendente,
        forma_pagamento: formaPagamento || null,
        forma_pagamento_garantia: formaPagamentoGarantia || null,
        situacao,
        placa, marca, modelo,
        km: km.trim() ? parseInt(km, 10) || 0 : 0,
        ano,
        chassi: isOficina ? chassi : "",
        // os.numero_de_serie fica histórico — código novo lê/grava só
        // `os_equipamento` (Assistência Técnica, regra 14 — ver
        // AssistenciaTecnicaCampo.md seção 5), nunca mais escrito por aqui.
        numero_de_serie: "",
        referencia_os: referenciaOs,
        tecnico_responsavel: tecnicoResponsavel,
        auxiliar_tecnico: auxiliarTecnico,
        posicao_os: posicaoOs,
        previsao_termino: previsaoTermino,
        data_termino: dataTermino,
        data_agendamento: dataAgendamento,
        hora_agendamento: horaAgendamento,
        os_original: docOrigem.trim() ? parseInt(docOrigem, 10) || null : null,
        tipo_doc_original: docOrigemTipo,
        qtd_revisoes: qtdRevisoes.trim() ? parseInt(qtdRevisoes, 10) || null : null,
        autorizado_por: autorizadoPor || null,
        usuario_alteracao: usuarioCod,
        classe,
        plataforma: Platform.OS,
      };
      const j = editing && osId
        ? await apiSend(conn, `/api/os-completo/${osId}`, "PUT", body)
        : await apiSend(conn, `/api/os-completo/create`, "POST", body);
      if (!j?.success) {
        if (j?.requer_autorizacao) {
          feedback.showConfirm(
            `${j.message}\n\nDeseja entrar com senha superior para autorização?`,
            () => setDocOrigemAuthVisible(true),
          );
        } else {
          showToast(j?.message || "Falha ao gravar.", "error");
        }
      } else if (editing) {
        showToast("O.S. atualizada.", "success");
        // Recarrega o cabeçalho: `qtd_revisoes`/Doc. Origem podem ter
        // disparado regravação de `revisoes_programadas` no backend
        // (consumo de data/regeneração), a tela precisa refletir o estado
        // novo sem esperar o usuário sair e voltar.
        apiGet(conn, `/api/os-completo/${osId}`).then((jj) => {
          if (jj?.success && jj.os) setOs(jj.os);
        }).catch(() => {});
      } else {
        showToast(`O.S. #${j.codigo} criada. Adicione os itens.`, "success");
        setTimeout(() => router.replace({ pathname: "/os-geral", params: { os: String(j.codigo) } }), 500);
      }
    } catch (e) {
      // Linguagem não-técnica (CLAUDE.md > "Mensagens de Erro"), nunca o
      // texto cru de exceção JS — achado ao vivo 2026-08-13: um erro real
      // de serialização ("Converting circular structure to JSON") chegou
      // a vazar aqui pro usuário final antes desta correção.
      showToast(friendlyCatchError(e, "Falha ao gravar a O.S."), "error");
    } finally { setSaving(false); }
  };

  const [fechando, setFechando] = useState(false);
  const handleFechar = useCallback(async () => {
    if (!conn || !osId) return;
    if (!it.itens.length) { showToast("Inclua pelo menos um produto ou serviço.", "error"); return; }
    setFechando(true);
    try {
      const j = await apiSend(conn, `/api/os-completo/${osId}/fechar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "O.S. Fechada.", "success");
        setOs((o) => (o ? { ...o, situacao: "F", situacao_label: "Fechado" } : o));
      } else {
        showToast(j?.message || "Não foi possível fechar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFechando(false); }
  }, [conn, osId, it.itens.length, classe, isMaster, usuarioCod, showToast]);

  const [faturando, setFaturando] = useState(false);
  const [reciboOpen, setReciboOpen] = useState(false);
  // Bifurcação de faturamento Garantia×Cliente: quando a O.S. tem os 2
  // blocos pendentes (Cliente paga + Garantia/Interno/Contrato), o backend
  // devolve `needs_choice` em vez de faturar — abre o modal de escolha em
  // vez de tratar como erro.
  const [faturarBucketOpen, setFaturarBucketOpen] = useState(false);
  const [faturarBucketTotais, setFaturarBucketTotais] = useState({ cliente: 0, garantia: 0 });
  // Comanda gerada ao faturar o bloco CLIENTE — só esse bloco mostra
  // NotaFiscalCard. **Decisão confirmada pelo usuário 2026-08-19**: a
  // comanda de Garantia/Interno/Contrato (as 3 situações do bucket
  // "garantia", ver comentário acima) NUNCA emite nota fiscal nesta
  // migração — nenhuma das 3 mostra o card, mesmo faturada. Se precisar
  // diferenciar Contrato das outras duas no futuro, é pedido novo, não
  // presumir a partir daqui.
  const [comandaFaturadaCliente, setComandaFaturadaCliente] = useState<number | null>(null);
  const handleFaturar = useCallback(async (bucket?: "cliente" | "garantia" | "ambos") => {
    if (!conn || !osId) return;
    setFaturando(true);
    try {
      const j = await apiSend(conn, `/api/os-completo/${osId}/faturar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
        faturar_bucket: bucket || null,
      });
      if (j?.success) {
        showToast(j.message || "O.S. faturada.", "success");
        setOs((o) => (o ? { ...o, situacao: "PG", situacao_label: "Faturado" } : o));
        setFaturarBucketOpen(false);
        setReciboOpen(true);
        if (typeof j.comanda === "number") setComandaFaturadaCliente(j.comanda);
      } else if (j?.needs_choice) {
        setFaturarBucketTotais({ cliente: j.total_cliente || 0, garantia: j.total_garantia || 0 });
        setFaturarBucketOpen(true);
      } else {
        showToast(j?.message || "Não foi possível faturar.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setFaturando(false); }
  }, [conn, osId, classe, isMaster, usuarioCod, showToast]);

  const notaFiscalCliente = useEmitirNotaFiscal({
    conn, session: { usuarioCodigo: usuarioCod, classe }, comanda: comandaFaturadaCliente, isMaster,
  });

  const [reabrindo, setReabrindo] = useState(false);
  const handleReabrir = useCallback(async () => {
    if (!conn || !osId) return;
    setReabrindo(true);
    try {
      const j = await apiSend(conn, `/api/os-completo/${osId}/reabrir`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(j.message || "O.S. Reaberta.", "success");
        setOs((o) => (o ? { ...o, situacao: "A", situacao_label: "Aberto" } : o));
      } else {
        showToast(j?.message || "Não foi possível reabrir.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setReabrindo(false); }
  }, [conn, osId, classe, isMaster, usuarioCod, showToast]);

  const feedback = useFeedback();

  // Remover localização (LGPD) — ferramenta de conformidade, não política
  // de retenção automática. Ver AssistenciaTecnicaCampo.md seção 7.
  const [limpandoLocalizacao, setLimpandoLocalizacao] = useState(false);
  const handleLimparLocalizacao = useCallback(() => {
    if (!conn || !osId) return;
    feedback.showConfirm(
      "Remove as coordenadas de GPS registradas no check-in/check-out (mantém só os horários). Ação irreversível.",
      async () => {
        setLimpandoLocalizacao(true);
        try {
          const j = await apiSend(conn, `/api/os/${osId}/limpar-localizacao`, "POST", {
            classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
          });
          if (j?.success) {
            showToast("Localização removida.", "success");
            setOs((o) => (o ? { ...o, checkin_lat: null, checkin_lng: null, checkout_lat: null, checkout_lng: null } : o));
          } else {
            showToast(j?.message || "Não foi possível remover a localização.", "error");
          }
        } catch (e) {
          showToast(friendlyCatchError(e, "Falha ao remover localização."), "error");
        } finally {
          setLimpandoLocalizacao(false);
        }
      },
      { title: "Remover localização", confirmText: "Remover", destructive: true },
    );
  }, [conn, osId, classe, isMaster, usuarioCod, showToast, feedback]);

  const [cancelando, setCancelando] = useState(false);
  const handleCancelar = useCallback(() => {
    if (!conn || !osId) return;
    feedback.showConfirm(`Cancelar a O.S. nº ${osId}? Esta ação não pode ser desfeita.`, async () => {
      setCancelando(true);
      try {
        const j = await apiSend(conn, `/api/os-completo/${osId}/cancelar`, "POST", {
          classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
        });
        if (j?.success) {
          showToast(j.message || "O.S. Cancelada.", "success");
          setOs((o) => (o ? { ...o, situacao: "C", situacao_label: "Cancelado" } : o));
        } else {
          showToast(j?.message || "Não foi possível cancelar.", "error");
        }
      } catch (e) {
        showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
      } finally { setCancelando(false); }
    });
  }, [conn, osId, classe, isMaster, usuarioCod, showToast, feedback]);

  // Criar Cópia (Command49_Click, FrmTraOsNew.frm) — cria uma O.S. nova
  // Aberta a partir do cabeçalho+itens desta O.S., disponível em QUALQUER
  // Situação (mesmo comportamento do legado — nenhuma restrição). Sem
  // confirmação prévia (o legado também não pede), navega direto pra
  // O.S. recém-criada — mesmo efeito de `CARREGAOS Cod_OS` no legado.
  const [copiando, setCopiando] = useState(false);
  const handleCriarCopia = useCallback(async () => {
    if (!conn || !osId) return;
    setCopiando(true);
    try {
      const j = await apiSend(conn, `/api/os-completo/${osId}/copiar`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        showToast(`O.S. copiada com sucesso — nova O.S. #${j.codigo}.`, "success");
        setTimeout(() => router.replace({ pathname: "/os-geral", params: { os: String(j.codigo) } }), 500);
      } else {
        showToast(j?.message || "Não foi possível criar a cópia.", "error");
      }
    } catch (e) {
      showToast(`Erro: ${e instanceof Error ? e.message : String(e)}`, "error");
    } finally { setCopiando(false); }
  }, [conn, osId, classe, isMaster, usuarioCod, showToast, router]);

  const [anexosOpen, setAnexosOpen] = useState(false);
  const [formulariosOpen, setFormulariosOpen] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [dadosOpen, setDadosOpen] = useState(false);
  const [tempoModalOpen, setTempoModalOpen] = useState(false);
  // Serviço pré-selecionado ao abrir via ícone da linha (2026-08-13,
  // user-directed) — null quando aberto pelo fluxo antigo (sem preseleção).
  const [tempoGastoPreselect, setTempoGastoPreselect] = useState<string | null>(null);
  const [requisicoesModalOpen, setRequisicoesModalOpen] = useState(false);

  const areaOptions: SelectOption[] = useMemo(() => areas.map((a) => ({ value: a.codigo, label: a.descricao })), [areas]);
  const funcOptions: SelectOption[] = useMemo(
    () => funcionarios.map((f) => ({
      value: f.codigo, label: f.nome_guerra || f.nome,
      sub: `#${f.codigo}${f.nome_guerra && f.nome !== f.nome_guerra ? ` · ${f.nome}` : ""}`,
    })),
    [funcionarios]
  );
  const servicosDaOSOptions: SelectOption[] = useMemo(
    () => {
      const vistos = new Set<string>();
      return it.itens
        .filter((i) => i.tipo === "S" && !vistos.has(i.produto) && vistos.add(i.produto))
        .map((i) => ({ value: i.produto, label: i.descricao }));
    },
    [it.itens]
  );
  const formaPagOptions: SelectOption[] = useMemo(() => formasPag.map((f) => ({ value: f.codigo, label: f.descricao })), [formasPag]);
  const statusOsOptions: SelectOption[] = useMemo(() => statusOsList.map((s) => ({ value: s.codigo, label: s.descricao })), [statusOsList]);
  const tipoOsOptions: SelectOption[] = useMemo(() => tipoOsList.map((t) => ({ value: t.codigo, label: t.descricao })), [tipoOsList]);

  // Doc. Origem / Revisão Programada — visibilidade/regra decidida pelo
  // texto do Tipo O.S. escolhido (mesmo critério do legado, sem acento —
  // o cadastro `tipo_os` é livre, não dá pra usar um código fixo) mais os
  // 2 flags de empresa. Réplica de `TipoOS_Click`, `FrmTraOsNew.frm`
  // linhas 16107-16128 — o backend faz a MESMA checagem de novo no Gravar
  // (`pedido_common._validar_doc_origem`), isto aqui só decide o que
  // mostrar/habilitar na tela.
  const tipoOsDescSelecionado = (tipoOsOptions.find((o) => o.value === posicaoOs)?.label || "").toUpperCase();
  const ehTipoRevisao = tipoOsDescSelecionado.includes("REVIS");
  const ehTipoGarantia = tipoOsDescSelecionado.includes("GARANTIA");
  const ramoRevisao = ehTipoRevisao && !!os?.controla_revisao_os;
  const ramoGarantia = !ramoRevisao && (ehTipoGarantia || ehTipoRevisao) && !!os?.exige_os_original_garantia;
  const mostrarDocOrigem = ramoRevisao || ramoGarantia;
  const apenasOSComoOrigem = ramoRevisao; // Revisão nunca aceita Pedido

  // Extraído uma vez pra ser reaproveitado em 2 lugares no render (dentro
  // do card do topo quando a OS já existe, ou num card avulso quando
  // ainda não — ver "os-geral-cliente" mais abaixo), sem duplicar as
  // ~15 linhas de props.
  const clienteSectionEl = (
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
  );

  if (loading) {
    return (
      <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} /></View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="os-geral-screen">
      <PedidoHeader
        title={editing ? `O.S. #${osId}` : "Nova O.S."}
        saving={saving}
        onBack={() => router.back()}
        // Bug real corrigido 2026-08-13, achado ao vivo pelo botão Gravar
        // de verdade no navegador: `Pressable.onPress` do cabeçalho SEMPRE
        // chama a função com o evento de clique — `onSave={handleSave}`
        // direto fazia esse evento (um nó do DOM) virar o 1º argumento de
        // `handleSave(autorizadoPor?: string)`, que ia parar dentro do
        // corpo JSON gravado (`autorizado_por: autorizadoPor || null`) —
        // "Converting circular structure to JSON" ao tentar serializar.
        // `() => handleSave()` garante zero argumentos passados adiante.
        onSave={() => handleSave()}
        canSave={can("OS_COMP.GRAVAR") && !camposTravados}
        onAnexos={editing && osId && cliente ? () => setAnexosOpen(true) : undefined}
        onFormularios={editing && osId && can("OS_COMP.FORMULARIOS") ? () => setFormulariosOpen(true) : undefined}
        onHelp={() => setAjudaOpen(true)}
        vinculoProjeto={vinculoProjeto ? { codigo: vinculoProjeto.codigo, onPress: () => router.push({ pathname: "/projeto-form", params: { codigo: String(vinculoProjeto.codigo) } } as never) } : undefined}
      />

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          {editing && os ? (
            <View style={[styles.card, { gap: spacing.sm }]} testID="os-geral-topo">
              <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.sm, flexWrap: "wrap" }}>
                <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                  <Text style={[styles.sitTagText, { color: sitColor }]}>{os.situacao_label}</Text>
                </View>
                <Text style={styles.headerMeta}>Aberta {formatDateBR(os.data)} {os.hora}</Text>
                {camposTravados ? (
                  <Text style={[styles.headerMeta, { color: colors.warning }]}>
                    O.S. "{os.situacao_label}" não pode ser alterada.
                  </Text>
                ) : null}
              </View>

              <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "flex-end", gap: spacing.md }}>
                <View style={{ minWidth: 200 }}>
                  <Text style={styles.topLabel}>Forma de Pagamento</Text>
                  <FormaPagamentoField
                    conn={conn}
                    tipoDav="OS"
                    documento={osId}
                    tela="OS_COMP"
                    valorTotal={os?.total || 0}
                    formaPag={formaPagamento}
                    onFormaPagChange={setFormaPagamento}
                    formaPagOptions={formaPagOptions}
                    onChanged={handleFormaPagModalChanged}
                    compactWeb
                    fieldWidth={200}
                    disabled={isFechado ? false : camposTravados}
                    testIDPrefix="os-geral-forma-pag"
                  />
                </View>
                <View style={{ minWidth: 200 }}>
                  <Text style={styles.topLabel}>Forma de Pag. Garantia</Text>
                  <SelectField
                    value={formaPagamentoGarantia || null}
                    onChange={(v) => setFormaPagamentoGarantia(v == null ? "" : String(v))}
                    options={formaPagOptions}
                    placeholder="Só p/ itens de Garantia"
                    disabled={camposTravados && !isFechado}
                    allowClear
                    compactWeb
                    modalTitle="Forma de Pagamento de Garantia"
                    testID="os-geral-forma-pag-garantia"
                  />
                </View>
                <View style={{ minWidth: 160 }}>
                  <Text style={styles.topLabel}>Referência</Text>
                  <TextInput
                    value={referenciaOs}
                    onChangeText={setReferenciaOs}
                    editable={!camposTravados}
                    placeholder="Referência livre"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, { width: 160, height: 36, paddingVertical: 6 }]}
                    testID="os-geral-referencia"
                  />
                </View>
                <View style={{ minWidth: 180 }}>
                  <Text style={styles.topLabel}>Técnico Responsável</Text>
                  <SelectField
                    value={tecnicoResponsavel}
                    onChange={(v) => setTecnicoResponsavel(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Técnico"
                    disabled={!canChangeGestores || camposTravados}
                    modalTitle="Selecionar Técnico Responsável"
                    allowClear
                    compactWeb
                    testID="os-geral-tecnico"
                  />
                </View>
                <View style={{ minWidth: 180 }}>
                  <Text style={styles.topLabel}>Auxiliar (opcional)</Text>
                  <SelectField
                    value={auxiliarTecnico}
                    onChange={(v) => setAuxiliarTecnico(v == null ? null : Number(v))}
                    options={funcOptions}
                    placeholder="Auxiliar"
                    disabled={!canChangeGestores || camposTravados}
                    modalTitle="Selecionar Auxiliar do Técnico"
                    allowClear
                    compactWeb
                    testID="os-geral-auxiliar"
                  />
                </View>
                <View style={{ minWidth: 160 }}>
                  <Text style={styles.topLabel}>Tipo O.S.</Text>
                  <SelectField
                    value={posicaoOs}
                    onChange={(v) => setPosicaoOs(v == null ? null : Number(v))}
                    options={tipoOsOptions}
                    placeholder="Tipo"
                    allowClear
                    compactWeb
                    disabled={camposTravados}
                    modalTitle="Selecionar Tipo O.S."
                    testID="os-geral-tipo-os"
                  />
                </View>
              </View>

              {/* Término (Previsto/Real) — campos existiam no backend
                  (OSCompletoSaveRequest.previsao_termino/data_termino/
                  hora_fechamento, carregados e gravados) mas nunca tinham
                  campo de tela — mesma faixa do cabeçalho da OS no VB6
                  (FrmTraOsNew.frm: "Término Prev./Término/Hora", ao lado
                  de Entrada/Hora). Adicionado 2026-08-13, user-directed.
                  "Revisão Programada"/Doc. Origem entraram nesta mesma
                  linha (ao lado de Hora de Fechamento) a pedido do
                  usuário, no mesmo dia — antes era um card à parte. */}
              <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "flex-end", gap: spacing.md }}>
                <View style={{ width: 160 }}>
                  <Text style={styles.topLabel}>Previsão de Término</Text>
                  <WebDateField
                    value={previsaoTermino}
                    onChange={setPrevisaoTermino}
                    disabled={camposTravados}
                    testID="os-geral-previsao-termino"
                  />
                </View>
                <View style={{ width: 160 }}>
                  <Text style={styles.topLabel}>Data de Término</Text>
                  <WebDateField
                    value={dataTermino}
                    onChange={setDataTermino}
                    disabled={camposTravados}
                    testID="os-geral-data-termino"
                  />
                </View>
                <View style={{ width: 120 }}>
                  <Text style={styles.topLabel}>Hora de Fechamento</Text>
                  <WebDateField
                    type="time"
                    value={horaFechamento || null}
                    onChange={(v) => setHoraFechamento(v || "")}
                    disabled={camposTravados}
                    testID="os-geral-hora-fechamento"
                  />
                </View>
                <View style={{ width: 160 }}>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Text style={styles.topLabel}>Data Agendada</Text>
                    <InfoTooltip
                      testID="os-geral-data-agendada-info"
                      text="Data em que o atendimento foi marcado com o cliente (diferente da data em que ele de fato acontecer) — usada pela Lista de Atendimento por Calendário do técnico em campo. Ao gravar, o sistema reserva de verdade esse horário na Agenda do Técnico Responsável — se ele não atender nesse dia/hora, ou já tiver outro compromisso, a gravação é bloqueada com o motivo."
                    />
                  </View>
                  <WebDateField
                    value={dataAgendamento}
                    onChange={setDataAgendamento}
                    disabled={camposTravados}
                    testID="os-geral-data-agendada"
                  />
                </View>
                <View style={{ width: 120 }}>
                  <Text style={styles.topLabel}>Hora Agendada</Text>
                  <WebDateField
                    type="time"
                    value={horaAgendamento || null}
                    onChange={(v) => setHoraAgendamento(v || "")}
                    disabled={camposTravados}
                    testID="os-geral-hora-agendada"
                  />
                </View>
                <View style={{ width: 110 }} testID="os-geral-doc-origem">
                  <View style={{ flexDirection: "row", alignItems: "center", gap: 4 }}>
                    <Text style={styles.topLabel}>Revisão Programada</Text>
                    <InfoTooltip
                      testID="os-geral-revisao-programada-info"
                      text={
                        "Quantas revisões futuras esta O.S. deve programar (uma a cada 30 dias) — usado quando o "
                        + "cliente costuma voltar para manutenções periódicas."
                        + (mostrarDocOrigem
                          ? ramoRevisao
                            ? " Esta O.S. é do tipo Revisão: informe a O.S. de origem para vincular a uma data já programada."
                            : " Esta O.S. exige um Documento de Origem (O.S. ou Pedido) da garantia/revisão."
                          : "")
                      }
                    />
                  </View>
                  <TextInput
                    value={qtdRevisoes}
                    onChangeText={(v) => setQtdRevisoes(v.replace(/\D/g, ""))}
                    editable={!camposTravados}
                    keyboardType="number-pad"
                    placeholder="0"
                    placeholderTextColor={colors.muted}
                    style={[styles.input, { width: 110, height: 36, paddingVertical: 6 }]}
                    testID="os-geral-qtd-revisoes"
                  />
                </View>
                {mostrarDocOrigem ? (
                  <>
                    <View style={{ width: 150 }}>
                      <Text style={styles.topLabel}>Doc. Origem</Text>
                      <TextInput
                        value={docOrigem}
                        onChangeText={(v) => setDocOrigem(v.replace(/\D/g, ""))}
                        editable={!camposTravados}
                        keyboardType="number-pad"
                        placeholder={ramoRevisao ? "Nº da O.S." : "Nº do documento"}
                        placeholderTextColor={colors.muted}
                        style={[styles.input, { width: 150, height: 36, paddingVertical: 6 }]}
                        testID="os-geral-doc-origem-numero"
                      />
                    </View>
                    <View style={{ flexDirection: "row", gap: spacing.md, height: 36, alignItems: "center" }}>
                      <Pressable
                        onPress={() => setDocOrigemTipo("O")}
                        disabled={camposTravados}
                        style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
                        testID="os-geral-doc-origem-tipo-os"
                      >
                        <Ionicons name={docOrigemTipo === "O" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                        <Text style={{ fontSize: 13, color: colors.onSurface }}>O.S.</Text>
                      </Pressable>
                      {!apenasOSComoOrigem ? (
                        <Pressable
                          onPress={() => setDocOrigemTipo("P")}
                          disabled={camposTravados}
                          style={{ flexDirection: "row", alignItems: "center", gap: 4 }}
                          testID="os-geral-doc-origem-tipo-pedido"
                        >
                          <Ionicons name={docOrigemTipo === "P" ? "radio-button-on" : "radio-button-off"} size={18} color={colors.brandPrimary} />
                          <Text style={{ fontSize: 13, color: colors.onSurface }}>Pedido</Text>
                        </Pressable>
                      ) : null}
                    </View>
                  </>
                ) : null}
              </View>
              {(os.revisoes_programadas || []).length > 0 ? (
                <View style={{ gap: 2, marginTop: spacing.xs }}>
                  <Text style={styles.topLabel}>Datas programadas por esta O.S.</Text>
                  {os.revisoes_programadas.map((r) => (
                    <Text key={r.sequencia} style={{ fontSize: 12, color: colors.muted }}>
                      {formatDateBR(r.data)}
                      {r.consumida_por ? ` — consumida pela O.S. #${r.consumida_por}` : " — disponível"}
                    </Text>
                  ))}
                </View>
              ) : null}

              {/* Requisições Vinculadas / Criar Cópia movidos pro 1º card
                  (user-directed, 2026-08-13) — antes ficavam soltos abaixo
                  dos totais, junto dos itens; são ações de nível OS, não
                  de item, fazem mais sentido aqui perto do resto do
                  cabeçalho. */}
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                {can("OS_COMP.VER_REQUISICOES") ? (
                  <Pressable
                    onPress={() => setRequisicoesModalOpen(true)}
                    style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" }}
                    testID="os-geral-requisicoes-btn"
                  >
                    <Ionicons name="clipboard-outline" size={16} color={colors.brandPrimary} />
                    <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Requisições Vinculadas</Text>
                  </Pressable>
                ) : null}
                {can("OS_COMP.COPIAR") ? (
                  <Pressable
                    onPress={handleCriarCopia}
                    disabled={copiando}
                    style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", opacity: copiando ? 0.6 : 1 }}
                    testID="os-geral-criar-copia-btn"
                  >
                    {copiando ? (
                      <ActivityIndicator size="small" color={colors.brandPrimary} />
                    ) : (
                      <Ionicons name="copy-outline" size={16} color={colors.brandPrimary} />
                    )}
                    <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>
                      {copiando ? "Copiando…" : "Criar Cópia"}
                    </Text>
                  </Pressable>
                ) : null}
              </View>

              {/* Cliente movido pro final deste card pra economizar espaço
                  (user-directed, 2026-08-13) — só nesta situação (OS já
                  gravada, `editing && os`); numa OS nova este card ainda
                  nem existe, então o fallback abaixo continua cobrindo
                  esse caso (senão não haveria como escolher cliente pra
                  criar a 1ª vez). Sem `marginTop` próprio — o `gap` do
                  card do topo já espaça este bloco dos anteriores. */}
              {clienteSectionEl}
            </View>
          ) : (
            <View style={styles.card} testID="os-geral-cliente">
              {clienteSectionEl}
            </View>
          )}

          {cliente && isOficina && !isAssist ? (
            <View style={styles.card} testID="os-geral-veiculo">
              <Text style={styles.sectionTitle}>Veículo</Text>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Field label="Placa">
                    <TextInput
                      value={placa}
                      onChangeText={setPlaca}
                      autoCapitalize="characters"
                      maxLength={8}
                      editable={!camposTravados}
                      placeholder="ABC-1234"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="os-geral-placa"
                    />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="KM">
                    <TextInput
                      value={km}
                      onChangeText={setKm}
                      keyboardType="number-pad"
                      editable={!camposTravados}
                      placeholder="0"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="os-geral-km"
                    />
                  </Field>
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Field label="Marca">
                    <SelectField
                      value={marca || null}
                      onChange={(v) => { setMarca(v == null ? "" : String(v)); setModelo(""); }}
                      options={marcasList.map((m) => ({ value: m.codigo, label: m.descricao }))}
                      placeholder="Selecione a marca"
                      modalTitle="Marca do veículo"
                      disabled={camposTravados}
                      allowClear
                      compactWeb
                      testID="os-geral-marca"
                    />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Modelo">
                    <SelectField
                      value={modelo || null}
                      onChange={(v) => setModelo(v == null ? "" : String(v))}
                      options={modelosList.map((m) => ({ value: m.codigo, label: m.descricao }))}
                      placeholder={marca ? "Selecione o modelo" : "Escolha a marca primeiro"}
                      modalTitle="Modelo do veículo"
                      disabled={!marca || camposTravados}
                      allowClear
                      compactWeb
                      testID="os-geral-modelo"
                    />
                  </Field>
                </View>
              </View>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                <View style={{ flex: 1 }}>
                  <Field label="Ano">
                    <TextInput
                      value={ano}
                      onChangeText={setAno}
                      maxLength={9}
                      editable={!camposTravados}
                      placeholder="2025"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="os-geral-ano"
                    />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label={exigeChassiOs ? "Chassi *" : "Chassi"}>
                    <TextInput
                      value={chassi}
                      onChangeText={setChassi}
                      maxLength={20}
                      editable={!camposTravados}
                      placeholder="Chassi"
                      placeholderTextColor={colors.muted}
                      style={styles.input}
                      testID="os-geral-chassi"
                    />
                  </Field>
                </View>
              </View>
            </View>
          ) : null}

          {/* Equipamentos vinculados à O.S. (Assistência Técnica — uma OS
              pode ter vários equipamentos, ver AssistenciaTecnicaCampo.md
              seção 5/regra 14). Vincular um novo é exclusivo desta tela
              (retaguarda) — sem equivalente mobile. Só disponível depois
              do primeiro Gravar (precisa do código da OS). */}
          {cliente && !(isOficina && !isAssist) && editing && osId ? (
            <View style={styles.card}>
              <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm }}>
                <Text style={styles.sectionTitle}>Equipamentos</Text>
                {can("OS_COMP.EQUIP_ADD") && isAberto ? (
                  <Pressable
                    onPress={() => { setEquipTerm(""); setEquipResults([]); setEquipModalOpen(true); }}
                    disabled={eq.adding}
                    style={{ flexDirection: "row", alignItems: "center", gap: 4, opacity: eq.adding ? 0.6 : 1 }}
                    testID="os-geral-equipamento-add"
                  >
                    {eq.adding ? (
                      <ActivityIndicator color={colors.brandPrimary} size="small" />
                    ) : (
                      <Ionicons name="add-circle-outline" size={16} color={colors.brandPrimary} />
                    )}
                    <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Adicionar equipamento</Text>
                  </Pressable>
                ) : null}
              </View>
              {eq.equipamentosLoading ? <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.sm }} /> : null}
              {!eq.equipamentosLoading && eq.equipamentos.length === 0 ? (
                <Text style={styles.lockedText}>Nenhum equipamento vinculado ainda.</Text>
              ) : null}
              {eq.equipamentos.map((item) => (
                <OSEquipamentoCard
                  key={item.codigo}
                  item={item}
                  statusOptions={statusOsOptions}
                  editavel={isAberto}
                  canCancelar={can("OS_COMP.EQUIP_CANC")}
                  saving={eq.savingCodigo === item.codigo}
                  canceling={eq.cancelingCodigo === item.codigo}
                  onSalvar={(draft) => eq.handleUpdate(item.codigo, draft)}
                  onCancelar={() => eq.handleCancelar(item.codigo)}
                />
              ))}
            </View>
          ) : null}

          {/* Check-in/Check-out do Atendimento de Campo (regra 2 do
              AssistenciaTecnicaCampo.md) — read-only aqui, gravado só pela
              tela mobile os-atendimento.tsx. Horário + link "Ver no mapa"
              a partir do lat/lng capturado no momento do check-in/out. */}
          {cliente && !(isOficina && !isAssist) && editing && osId && os ? (
            <View style={styles.card}>
              <Text style={styles.sectionTitle}>Check-in / Check-out</Text>
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md }}>
                <View style={{ minWidth: 200 }}>
                  <Text style={styles.checkinLabel}>Check-in</Text>
                  {os.checkin_em ? (
                    <>
                      <Text style={styles.checkinValue}>{formatCheckinDateTime(os.checkin_em)}</Text>
                      {mapsUrl(os.checkin_lat, os.checkin_lng) ? (
                        <Pressable onPress={() => Linking.openURL(mapsUrl(os.checkin_lat, os.checkin_lng)!)} testID="os-geral-checkin-mapa">
                          <Text style={styles.checkinMapaLink}>Ver no mapa</Text>
                        </Pressable>
                      ) : null}
                    </>
                  ) : (
                    <Text style={styles.checkinEmpty}>Ainda não registrado.</Text>
                  )}
                </View>
                <View style={{ minWidth: 200 }}>
                  <Text style={styles.checkinLabel}>Check-out</Text>
                  {os.checkout_em ? (
                    <>
                      <Text style={styles.checkinValue}>{formatCheckinDateTime(os.checkout_em)}</Text>
                      {mapsUrl(os.checkout_lat, os.checkout_lng) ? (
                        <Pressable onPress={() => Linking.openURL(mapsUrl(os.checkout_lat, os.checkout_lng)!)} testID="os-geral-checkout-mapa">
                          <Text style={styles.checkinMapaLink}>Ver no mapa</Text>
                        </Pressable>
                      ) : null}
                    </>
                  ) : (
                    <Text style={styles.checkinEmpty}>Ainda não registrado.</Text>
                  )}
                </View>
              </View>
              {can("OS_COMP.LIMPAR_GEO") && (os.checkin_lat != null || os.checkout_lat != null) ? (
                <Pressable
                  onPress={handleLimparLocalizacao}
                  disabled={limpandoLocalizacao}
                  style={[styles.limparLocalizacaoBtn, limpandoLocalizacao && { opacity: 0.6 }]}
                  testID="os-geral-limpar-localizacao"
                >
                  {limpandoLocalizacao ? (
                    <ActivityIndicator color={colors.error} size="small" />
                  ) : (
                    <Ionicons name="trash-outline" size={14} color={colors.error} />
                  )}
                  <Text style={styles.limparLocalizacaoText}>
                    {limpandoLocalizacao ? "Removendo…" : "Remover coordenadas de GPS (LGPD)"}
                  </Text>
                </Pressable>
              ) : null}
            </View>
          ) : null}

          {!editing || !osId ? (
            <View style={styles.card}>
              <View style={styles.lockedRow}>
                <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                <Text style={styles.lockedText}>Grave o cabeçalho primeiro para incluir itens na O.S.</Text>
              </View>
            </View>
          ) : (
            <>
              {it.itens.length > 0 ? (
                <View style={[styles.card, { marginBottom: spacing.sm }]}>
                  <OSTotaisResumo itens={it.itens} />
                  {can("OS_COMP.PONTUACAO") ? (
                    <Pressable
                      onPress={() => it.setPontuacaoModalOpen(true)}
                      style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginTop: spacing.sm }}
                      testID="os-geral-pontuacao-btn"
                    >
                      <Ionicons name="star-outline" size={16} color={colors.brandPrimary} />
                      <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Pontuação de Técnicos</Text>
                    </Pressable>
                  ) : null}
                  {(os?.exige_aprovacao_itens_os || os?.exige_expedicao_itens_os) &&
                  (can("OS_COMP.AUTORIZAR") || can("OS_COMP.EXPEDIR")) ? (
                    <Pressable
                      onPress={() => it.setAutorizacaoModalOpen(true)}
                      style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginTop: spacing.sm }}
                      testID="os-geral-autorizacao-btn"
                    >
                      <Ionicons name="shield-checkmark-outline" size={16} color={colors.brandPrimary} />
                      <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Autorização de Itens</Text>
                    </Pressable>
                  ) : null}
                </View>
              ) : null}
              <View style={{ flexDirection: "row", flexWrap: "wrap", gap: spacing.md, marginBottom: spacing.sm }}>
                {can("OS_COMP.ALT_EXECUTOR") && (sit === "F" || sit === "PG") ? (
                  <Pressable
                    onPress={() => it.setAltExecutorModalOpen(true)}
                    style={{ flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start" }}
                    testID="os-geral-alt-executor-btn"
                  >
                    <Ionicons name="person-outline" size={16} color={colors.brandPrimary} />
                    <Text style={{ fontSize: 12, color: colors.brandPrimary, fontWeight: "600" }}>Alteração de Executor</Text>
                  </Pressable>
                ) : null}
              </View>
              <ItemList
                editing={editing}
                isAberto={isAberto}
                it={it}
                tela="OS_COMP"
                onAnalisar={() => router.push({ pathname: "/relatorio-os-descontos", params: { os: String(osId) } })}
                onFechar={handleFechar}
                fechando={fechando}
                onFaturar={handleFaturar}
                faturando={faturando}
                isFechado={isFechado}
                onReabrir={handleReabrir}
                reabrindo={reabrindo}
                onCancelar={handleCancelar}
                cancelando={cancelando}
                onImprimir={() => setReciboOpen(true)}
                onTempoGastoItem={(item) => {
                  setTempoGastoPreselect(item.produto);
                  setTempoModalOpen(true);
                }}
              />
              {comandaFaturadaCliente ? (
                <NotaFiscalCard
                  docFiscal={notaFiscalCliente.docFiscal} emitindoNfce={notaFiscalCliente.emitindoNfce} emitindoNfse={notaFiscalCliente.emitindoNfse}
                  onEmitirNfce={notaFiscalCliente.emitirNfce} onEmitirNfse={notaFiscalCliente.emitirNfse}
                  canEmitirNfce={can("ALTERAR_COMANDA.EMITIR_NF") || isMaster}
                  canEmitirNfse={can("ALTERAR_COMANDA.EMITIR_NFSE") || isMaster}
                  testIDPrefix="os-geral-cliente"
                />
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
                  </View>
                ) : null
              ) : null}

              <Field label="Status O.S.">
                <SelectField
                  value={statusOs}
                  onChange={(v) => setStatusOs(v == null ? null : Number(v))}
                  options={statusOsOptions}
                  placeholder="Selecione o status"
                  allowClear
                  compactWeb
                  disabled={camposTravados}
                  modalTitle="Status da O.S."
                  testID="os-geral-status"
                />
              </Field>

              <View style={pedidoStyles.dateRow}>
                <View style={{ flex: 1 }}>
                  <Field label="Atendente">
                    <SelectField
                      value={atendente}
                      onChange={(v) => setAtendente(v == null ? null : Number(v))}
                      options={funcOptions}
                      placeholder="Atendente"
                      disabled={!canChangeGestores || camposTravados}
                      compactWeb
                      modalTitle="Selecionar Atendente"
                      testID="os-geral-atendente"
                    />
                  </Field>
                </View>
                <View style={{ flex: 1 }}>
                  <Field label="Área de Atuação">
                    <SelectField
                      value={areaAtuacao}
                      onChange={(v) => setAreaAtuacao(v == null ? null : Number(v))}
                      options={areaOptions}
                      placeholder="Área"
                      allowClear
                      compactWeb
                      disabled={camposTravados}
                      modalTitle="Selecionar Área de Atuação"
                      testID="os-geral-area"
                    />
                  </Field>
                </View>
              </View>

              <Field label="Cliente Descreva">
                <TextInput
                  value={descricaoCliente}
                  onChangeText={setDescricaoCliente}
                  editable={!camposTravados}
                  placeholder="Descrição informada pelo cliente"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
                  multiline
                  testID="os-geral-descricao"
                />
              </Field>

              <Field label="Serviço Executado">
                <TextInput
                  value={resumo}
                  onChangeText={setResumo}
                  editable={!camposTravados}
                  placeholder="Resumo do serviço executado"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
                  multiline
                  testID="os-geral-resumo"
                />
              </Field>

              <Field label="Observação">
                <TextInput
                  value={obs}
                  onChangeText={setObs}
                  editable={!camposTravados}
                  placeholder="Observação da OS"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, { minHeight: 80, textAlignVertical: "top", paddingTop: 12 }]}
                  multiline
                  testID="os-geral-obs"
                />
              </Field>
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>

      <OSItemModal it={it} funcOptions={funcOptions} tela="OS_COMP" />
      <AgendarModal it={it} clienteCodigo={cliente?.codigo} usuarioCod={usuarioCod} />
      <AuthorizationSlide
        visible={docOrigemAuthVisible}
        conn={conn}
        title="Autorização — Doc. Origem"
        message="Validar o Documento de Origem informado exige autorização de gerente, supervisor ou administrador."
        onClose={() => setDocOrigemAuthVisible(false)}
        onAuthorized={({ usuario }) => { setDocOrigemAuthVisible(false); handleSave(usuario); }}
      />
      <PontuacaoModal
        visible={it.pontuacaoModalOpen}
        onClose={() => it.setPontuacaoModalOpen(false)}
        itens={it.itens}
        atendenteNome={os?.atendente_nome || ""}
        saving={it.pontuacaoSaving}
        onSave={it.savePontuacao}
      />
      <AlterarExecutorModal
        visible={it.altExecutorModalOpen}
        onClose={() => it.setAltExecutorModalOpen(false)}
        itens={it.itens}
        funcOptions={funcOptions}
        saving={it.altExecutorSaving}
        onSave={it.salvarAlterarExecutor}
      />
      <FaturarBucketModal
        visible={faturarBucketOpen}
        onClose={() => setFaturarBucketOpen(false)}
        totalCliente={faturarBucketTotais.cliente}
        totalGarantia={faturarBucketTotais.garantia}
        saving={faturando}
        onEscolher={(bucket) => handleFaturar(bucket)}
      />
      <AutorizacaoItensModal
        visible={it.autorizacaoModalOpen}
        onClose={() => { it.setAutorizacaoModalOpen(false); it.setAutorizacaoSelecionados([]); }}
        itens={it.itens}
        selecionados={it.autorizacaoSelecionados}
        onToggle={it.toggleAutorizacaoSelecionado}
        saving={it.autorizacaoSaving}
        exigeAprovacao={!!os?.exige_aprovacao_itens_os}
        exigeExpedicao={!!os?.exige_expedicao_itens_os}
        canAutorizar={can("OS_COMP.AUTORIZAR")}
        canExpedir={can("OS_COMP.EXPEDIR")}
        onAutorizar={it.autorizarItens}
        onRemoverAutorizacao={it.removerAutorizacaoItens}
        onExpedir={it.expedirItens}
        onRemoverExpedicao={it.removerExpedicaoItens}
      />
      <TempoGastoModal
        visible={tempoModalOpen}
        onClose={() => { setTempoModalOpen(false); setTempoGastoPreselect(null); }}
        conn={conn}
        osId={osId || 0}
        isAberto={isAberto}
        funcOptions={funcOptions}
        servicosDaOS={servicosDaOSOptions}
        classe={classe}
        usuarioCod={usuarioCod}
        onToast={showToast}
        preselectCodigoInterno={tempoGastoPreselect}
      />
      <RequisicoesVinculadasModal
        visible={requisicoesModalOpen}
        onClose={() => setRequisicoesModalOpen(false)}
        conn={conn}
        osId={osId || 0}
      />
      <GeneralDiscountModal it={it} />
      <DiscountsReportModal it={it} />
      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => { setCliente(c); setSearchOpen(false); }}
        onCreate={() => { setSearchOpen(false); handleCreateClienteFromQuick(searchTerm); }}
      />
      <EquipamentoSearchModal
        visible={equipModalOpen}
        onClose={() => setEquipModalOpen(false)}
        conn={conn}
        cliente={cliente?.codigo ?? null}
        term={equipTerm}
        setTerm={setEquipTerm}
        loading={equipLoading}
        results={equipResults}
        onPick={(e) => {
          setEquipModalOpen(false);
          eq.handleAdd(e);
        }}
      />
      {cliente && osId ? (
        <AnexosOSModal visible={anexosOpen} onClose={() => setAnexosOpen(false)} conn={conn} os={osId} clienteCodigo={cliente.codigo} />
      ) : null}
      {osId ? (
        <LayoutPreenchimentoModal
          visible={formulariosOpen}
          onClose={() => setFormulariosOpen(false)}
          conn={conn}
          entidade={LAYOUT_ENTIDADE_OS}
          codentidade={osId}
          usuarioCod={usuarioCod}
          title="Formulários (Layouts) da O.S."
          dadosExtras={[
            { label: "Cliente", valor: cliente?.nome || os?.cliente_nome || "" },
            { label: "CPF/CNPJ", valor: cliente?.cgc_cpf || os?.cliente_cgc || "" },
            { label: "Telefone", valor: cliente?.telefone || "" },
            { label: "Técnico Responsável", valor: os?.tecnico_responsavel_nome || "" },
            { label: "Data/Hora do Atendimento", valor: os?.data ? `${formatDateBR(os.data)}${os?.hora ? ` ${os.hora}` : ""}` : "" },
          ]}
        />
      ) : null}
      <ReciboOSModal
        visible={reciboOpen}
        onClose={() => setReciboOpen(false)}
        conn={conn}
        os={os}
        cliente={cliente}
        clienteResumo={clienteResumo}
        itens={it.itens}
      />
      <ScreenToast toast={toast} testID="os-geral-toast" />
      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="O.S. Completa" itens={AJUDA_OS_ITENS} />
    </SafeAreaView>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={{ marginBottom: spacing.md }}>
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
  // Design Desktop (CLAUDE.md): espaçamento reduzido — padding/marginBottom
  // menores que o padrão WEB_FILTER_CARD (pensado pra card único
  // centralizado, não pra várias seções empilhadas na mesma tela).
  // Achado ao vivo 2026-08-13, user-directed ("diminua o espaçamento").
  card: { ...WEB_FILTER_CARD, padding: spacing.md, marginBottom: spacing.sm },
  fieldLabel: { fontSize: 12, color: colors.muted, marginBottom: 4, fontWeight: "500" },
  sectionTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface, marginBottom: 6 },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  selectBox: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 12,
  },
  selectText: { flex: 1, fontSize: 14, color: colors.onSurface },
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  headerMeta: { fontSize: 12, color: colors.muted },
  topLabel: { fontSize: 10, color: colors.muted, textTransform: "uppercase", letterSpacing: 0.5, marginBottom: 4 },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { flex: 1, fontSize: 13, color: colors.muted, fontStyle: "italic" },
  checkinLabel: { fontSize: 11, color: colors.muted, marginBottom: 2 },
  checkinValue: { fontSize: 14, fontWeight: "600", color: colors.onSurface },
  checkinEmpty: { fontSize: 13, color: colors.muted, fontStyle: "italic" },
  checkinMapaLink: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginTop: 2 },
  limparLocalizacaoBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, alignSelf: "flex-start", marginTop: spacing.sm,
  },
  limparLocalizacaoText: { fontSize: 12, color: colors.error, fontWeight: "600" },
});
