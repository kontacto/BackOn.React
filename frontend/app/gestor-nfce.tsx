// Gestor NFCe — migração de `Geral\FrmTraNFC.frm`, complementando a emissão
// automática já existente (Pedido Bar/Geral/O.S. faturados) com consulta de
// situação no SEFAZ, cancelamento do documento fiscal, inutilização de faixa
// de numeração, retransmissão de NFC-e ainda sem documento e validação de
// contingência — ver `backend/services/gestor_nfce_service.py` e
// PENDENCIAS.md > "Gestor NFCe" pro racional completo (achados da releitura
// da fonte, decisões confirmadas com o usuário).
//
// Seleção múltipla + ação em lote (novo padrão de UI nesta app — nenhuma
// outra tela "Gestor" hoje tem checkbox por linha): Cancelar/Consultar/
// Retransmitir/Validar Contingência operam sobre as comandas marcadas.
// Inutilizar Faixa é ação própria (números nunca usados, sem comanda
// associada — não faz sentido vir da seleção de linhas) com seu próprio
// modal, aberta pelo cabeçalho.
import { useCallback, useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";
import { AppModal } from "@/src/components/AppModal";
import WebDateField from "@/src/components/WebDateField";
import AccordionSection from "@/src/components/pedido/AccordionSection";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import { useClienteSearchModal } from "@/src/hooks/useClienteSearchModal";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_FILTER_CARD, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";
import { printHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader } from "@/src/utils/print-report-header";
import { buildDanfceHtml } from "@/src/utils/danfeFacsimile";
import { friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { formatBRL } from "@/src/utils/format";

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}
function brDate(iso: string | null): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-");
  return d ? `${d}/${m}/${y}` : iso;
}
function brDateTime(iso: string | null): string {
  if (!iso) return "";
  const [data, hora] = iso.split(/[T ]/);
  const dataFmt = brDate(data);
  return hora ? `${dataFmt} ${hora.slice(0, 5)}` : dataFmt;
}

type NfceItem = {
  comanda: number;
  data: string | null;
  valor_venda: number;
  cliente: number | null;
  cliente_nome: string;
  num_nfce: number | null;
  serie_nfce: string | null;
  situacao: string | null; // "G" | "F" | "C" | "I" | null (sem NFCe)
  dhemi: string | null;
  protocolo_sefaz: string | null;
  chave_acesso: string | null;
  vnf: number | null;
};
type GapItem = { serie: string; numero: number };
type ResultadoLinha = {
  comanda?: number;
  numero?: number;
  success: boolean;
  message?: string;
  protocolo_sefaz?: string;
  situacao_sefaz?: string;
  motivo_sefaz?: string;
  protocolo?: string;
};
// Apoio Fiscal BackOn — resumo agregado de uma operação em LOTE
// (2026-08-28, decisão "resumo agregado" via AskUserQuestion): 1 grupo
// por código de rejeição, nunca 1 tradução por item (evita repetir a
// mesma explicação N vezes numa lista longa).
type ApoioFiscalLoteGrupo = {
  codigo_rejeicao: string;
  titulo: string;
  explicacao_curta: string;
  quantidade: number;
  referencias: string[];
};
type ApoioFiscalLote = {
  total: number;
  grupos: ApoioFiscalLoteGrupo[];
  notificado_suporte: { email: boolean; whatsapp: boolean };
};
type ContingenciaStatus = {
  aberta: boolean;
  data_inicio?: string;
  hora_inicio?: string;
  motivo?: string;
  tipo_contingencia?: number;
};

const SITUACAO_LABEL: Record<string, string> = {
  G: "Aguardando Contingência",
  F: "Autorizada",
  C: "Cancelada",
  I: "Inutilizada",
};
const SITUACAO_COLOR: Record<string, string> = {
  G: colors.warning,
  F: colors.success,
  C: colors.error,
  I: colors.muted,
};
const SITUACAO_CHIPS: { value: string; label: string }[] = [
  { value: "G", label: "Aguardando" },
  { value: "F", label: "Autorizada" },
  { value: "C", label: "Cancelada" },
  { value: "I", label: "Inutilizada" },
];

function parseNumeros(texto: string): number[] {
  const nums = new Set<number>();
  texto
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .forEach((parte) => {
      const m = parte.match(/^(\d+)\s*-\s*(\d+)$/);
      if (m) {
        const a = parseInt(m[1], 10);
        const b = parseInt(m[2], 10);
        for (let n = Math.min(a, b); n <= Math.max(a, b); n++) nums.add(n);
      } else {
        const n = parseInt(parte, 10);
        if (Number.isFinite(n)) nums.add(n);
      }
    });
  return Array.from(nums).sort((a, b) => a - b);
}

// Modo Didático (CLAUDE.md > "Padrões de UI", regras 4-5) — ícone único "i"
// no cabeçalho reunindo a explicação de cada ação em linguagem de usuário
// final, em vez de tooltip espalhado.
const GESTOR_NFCE_AJUDA_ITENS: HelpItem[] = [
  {
    titulo: "Buscar e Filtrar",
    texto: "Filtra por período da venda, período de emissão da NFCe, número da comanda/NFCe, código do cliente e situação do documento. \"Incluir comandas sem NFCe\" também mostra vendas que ainda não têm nenhum documento emitido.",
    icon: { lib: "ion", name: "filter-outline" },
  },
  {
    titulo: "Selecionar linhas",
    texto: "Marque uma ou mais comandas na lista para liberar as ações em lote (Cancelar, Consultar, Retransmitir, Validar Contingência) na barra que aparece acima da lista.",
    icon: { lib: "ion", name: "checkbox-outline" },
  },
  {
    titulo: "Cancelar",
    texto: "Cancela só o documento fiscal (NFCe) das comandas selecionadas junto ao SEFAZ — não desfaz a venda, o estoque nem os pagamentos. Para reverter a venda inteira, use Alterar Comandas > Cancelar Comanda.",
    icon: { lib: "ion", name: "close-circle-outline" },
    cor: colors.error,
  },
  {
    titulo: "Consultar",
    texto: "Pergunta ao SEFAZ qual é a situação atual de cada NFCe selecionada — útil para conferir se uma nota realmente foi autorizada.",
    icon: { lib: "ion", name: "search-outline" },
  },
  {
    titulo: "Retransmitir",
    texto: "Emite a NFCe das comandas selecionadas que ainda não têm nenhum documento fiscal — só funciona quando TODAS as comandas marcadas estão nessa condição.",
    icon: { lib: "ion", name: "sync-outline" },
  },
  {
    titulo: "Validar Contingência",
    texto: "Transmite ao SEFAZ as NFCe que foram emitidas durante uma contingência e ainda estão aguardando — só funciona quando TODAS as comandas marcadas estão com situação \"Aguardando Contingência\".",
    icon: { lib: "ion", name: "shield-checkmark-outline" },
  },
  {
    titulo: "Contingência (cabeçalho)",
    texto: "Mostra se a emissão de NFCe está em contingência agora. Abrir contingência faz as próximas emissões ficarem aguardando (sem transmitir ao SEFAZ) até você fechar e usar \"Validar Contingência\". Use só quando o SEFAZ estiver fora do ar.",
    icon: { lib: "ion", name: "alert-circle-outline" },
    cor: colors.warning,
  },
  {
    titulo: "Inutilizar Numeração",
    texto: "Comunica ao SEFAZ que um ou mais números de NFCe nunca serão usados (ex.: um número pulado por engano) — diferente de Cancelar, que é para uma nota que já foi emitida.",
    icon: { lib: "ion", name: "ban-outline" },
  },
  {
    titulo: "Imprimir (em cada linha)",
    texto: "Mostra o fac-símile da NFCe já autorizada, a partir dos dados armazenados no sistema.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Ver XML (em cada linha)",
    texto: "Mostra o XML assinado já armazenado para aquela NFCe.",
    icon: { lib: "ion", name: "code-slash-outline" },
  },
  {
    titulo: "Excel",
    texto: "Exporta a lista encontrada para uma planilha.",
    icon: { lib: "ion", name: "download-outline" },
  },
];

export default function GestorNfceScreen() {
  const router = useRouter();
  const { can, isMaster, classe, usuarioCodigo } = usePermissions();
  const fb = useFeedback();
  const isWeb = Platform.OS === "web";

  if (!isWeb) {
    return <LockedView title="Disponível somente na versão web" message="Gestor NFCe está disponível apenas no web." testID="gestor-nfce-web-only" />;
  }

  const canAbrir = can("GESTOR_NFCE.ABRIR") || isMaster;
  const canCancelar = can("GESTOR_NFCE.CANCELAR") || isMaster;
  const canConsultar = can("GESTOR_NFCE.CONSULTAR") || isMaster;
  const canInutilizar = can("GESTOR_NFCE.INUTILIZAR") || isMaster;
  const canRetransmitir = can("GESTOR_NFCE.RETRANSMITIR") || isMaster;
  const canValidarCont = can("GESTOR_NFCE.VALIDAR_CONT") || isMaster;
  const canContingencia = can("GESTOR_NFCE.CONTINGENCIA") || isMaster;

  const [conn, setConn] = useState<Connection | null>(null);
  const [loading, setLoading] = useState(false);
  const [acaoEmAndamento, setAcaoEmAndamento] = useState<string | null>(null);

  const [dataVendaDe, setDataVendaDe] = useState<string | null>(todayIso());
  const [dataVendaAte, setDataVendaAte] = useState<string | null>(todayIso());
  const [dataNfceDe, setDataNfceDe] = useState<string | null>(null);
  const [dataNfceAte, setDataNfceAte] = useState<string | null>(null);
  const [comandaNum, setComandaNum] = useState("");
  const [numNfceNum, setNumNfceNum] = useState("");
  const [clienteCodigo, setClienteCodigo] = useState("");
  const clienteSearch = useClienteSearchModal(conn);
  const [situacoes, setSituacoes] = useState<string[]>([]);
  const [incluirSemNfce, setIncluirSemNfce] = useState(true);
  const [somenteGaps, setSomenteGaps] = useState(false);

  const [itens, setItens] = useState<NfceItem[]>([]);
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [selecionados, setSelecionados] = useState<Set<number>>(new Set());
  const [ajudaVisivel, setAjudaVisivel] = useState(false);

  const [contingencia, setContingencia] = useState<ContingenciaStatus>({ aberta: false });
  const [contingenciaModal, setContingenciaModal] = useState(false);
  const [motivoContingencia, setMotivoContingencia] = useState("");

  const [cancelarModal, setCancelarModal] = useState(false);
  const [motivoCancelamento, setMotivoCancelamento] = useState("");

  const [inutilizarModal, setInutilizarModal] = useState(false);
  const [inutilizarSerie, setInutilizarSerie] = useState("");
  const [inutilizarNumeros, setInutilizarNumeros] = useState("");
  const [motivoInutilizar, setMotivoInutilizar] = useState("");

  const [resultadoLote, setResultadoLote] = useState<{ titulo: string; linhas: ResultadoLinha[]; apoioFiscalLote?: ApoioFiscalLote | null } | null>(null);
  const [xmlVisualizado, setXmlVisualizado] = useState<{ comanda: number; xml: string } | null>(null);

  const apiUrl = useCallback((path: string) => `${(conn?.api || "").replace(/\/+$/, "")}${path}`, [conn]);
  const int_ = (s: string): number | undefined => (s.trim() ? parseInt(s.replace(/[^0-9]/g, ""), 10) || undefined : undefined);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa);
      if (!c) return;
      setConn(c);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  const carregarContingencia = useCallback(async () => {
    if (!conn) return;
    try {
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(apiUrl(`/api/contingencia-nfce/status?${qs}`));
      const j = await r.json();
      if (j?.success) setContingencia(j);
    } catch {
      // indicador fica no último estado conhecido — não é crítico o bastante pra um toast de erro
    }
  }, [conn, apiUrl]);

  const buscar = useCallback(async () => {
    if (!conn) return;
    setLoading(true);
    try {
      const body = {
        servidor: conn.servidor, banco: conn.banco,
        data_venda_de: dataVendaDe || undefined, data_venda_ate: dataVendaAte || undefined,
        data_nfce_de: dataNfceDe || undefined, data_nfce_ate: dataNfceAte || undefined,
        comanda: int_(comandaNum), num_nfce: int_(numNfceNum), cliente: int_(clienteCodigo),
        situacoes: situacoes.length ? situacoes : undefined,
        incluir_sem_nfce: incluirSemNfce, somente_gaps: somenteGaps,
        classe, master: isMaster,
      };
      const r = await fetch(apiUrl("/api/gestor-nfce"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        setItens(j.itens || []);
        setGaps(j.gaps || []);
        setSelecionados(new Set());
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível consultar as NFCe."));
        setItens([]);
        setGaps([]);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn, dataVendaDe, dataVendaAte, dataNfceDe, dataNfceAte, comandaNum, numNfceNum, clienteCodigo, situacoes, incluirSemNfce, somenteGaps, classe, isMaster, fb, apiUrl]);

  useEffect(() => {
    if (conn) { buscar(); carregarContingencia(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conn]);

  const toggleSituacao = (v: string) => {
    setSituacoes((cur) => (cur.includes(v) ? cur.filter((x) => x !== v) : [...cur, v]));
  };

  const toggleSelecionado = (comanda: number) => {
    setSelecionados((cur) => {
      const next = new Set(cur);
      if (next.has(comanda)) next.delete(comanda); else next.add(comanda);
      return next;
    });
  };
  const todosSelecionados = itens.length > 0 && selecionados.size === itens.length;
  const alternarTodos = () => {
    setSelecionados(todosSelecionados ? new Set() : new Set(itens.map((it) => it.comanda)));
  };

  const gapsAgrupados = useMemo(() => {
    const porSerie = new Map<string, number[]>();
    gaps.forEach((g) => {
      const lista = porSerie.get(g.serie) || [];
      lista.push(g.numero);
      porSerie.set(g.serie, lista);
    });
    return Array.from(porSerie.entries()).map(([serie, numeros]) => ({ serie, numeros }));
  }, [gaps]);

  const bodyBase = () => ({
    servidor: conn!.servidor, banco: conn!.banco,
    usuario_alteracao: usuarioCodigo, classe, plataforma: "web", master: isMaster,
  });

  const executarAcaoLote = async (
    acao: string, path: string, extraBody: Record<string, unknown>, tituloResultado: string,
    mensagemSucessoPadrao: string,
  ) => {
    if (!conn || selecionados.size === 0) return;
    setAcaoEmAndamento(acao);
    try {
      const body = { ...bodyBase(), comandas: Array.from(selecionados), ...extraBody };
      const r = await fetch(apiUrl(path), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (Array.isArray(j?.resultados)) {
        setResultadoLote({ titulo: tituloResultado, linhas: j.resultados, apoioFiscalLote: j?.apoio_fiscal_lote || null });
      }
      if (j?.success) {
        fb.showSuccess(j.message || mensagemSucessoPadrao, undefined, 5000);
        buscar();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível concluir a ação."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setAcaoEmAndamento(null);
    }
  };

  const confirmarCancelar = async () => {
    if (motivoCancelamento.trim().length < 15) {
      fb.showWarning("Informe um motivo com pelo menos 15 caracteres.");
      return;
    }
    await executarAcaoLote("cancelar", "/api/gestor-nfce/cancelar", { motivo: motivoCancelamento.trim() }, "Cancelamento de NFCe", "NFCe cancelada.");
    setCancelarModal(false);
  };

  const consultar = () => executarAcaoLote("consultar", "/api/gestor-nfce/consultar", {}, "Consulta de Situação", "Consulta concluída.");
  const retransmitir = () => executarAcaoLote("retransmitir", "/api/gestor-nfce/retransmitir", {}, "Retransmissão de NFCe", "NFCe retransmitida.");
  const validarContingencia = () => executarAcaoLote("validar", "/api/gestor-nfce/validar-contingencia", {}, "Validação de Contingência", "Contingência validada e transmitida.");

  const confirmarInutilizar = async () => {
    const numeros = parseNumeros(inutilizarNumeros);
    if (!numeros.length) { fb.showWarning("Informe pelo menos um número (ex.: 10, 12, 15-18)."); return; }
    if (!inutilizarSerie.trim()) { fb.showWarning("Informe a série."); return; }
    if (motivoInutilizar.trim().length < 15) { fb.showWarning("Informe um motivo com pelo menos 15 caracteres."); return; }
    if (!conn) return;
    setAcaoEmAndamento("inutilizar");
    try {
      const body = { ...bodyBase(), numeros, serie: inutilizarSerie.trim(), motivo: motivoInutilizar.trim() };
      const r = await fetch(apiUrl("/api/gestor-nfce/inutilizar"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (Array.isArray(j?.resultados)) setResultadoLote({ titulo: "Inutilização de Numeração", linhas: j.resultados });
      if (j?.success) {
        fb.showSuccess(j.message || "Numeração inutilizada.", undefined, 5000);
        setInutilizarModal(false);
        buscar();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível inutilizar a numeração."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setAcaoEmAndamento(null);
    }
  };

  const abrirContingencia = async () => {
    if (motivoContingencia.trim().length < 15) { fb.showWarning("Informe um motivo com pelo menos 15 caracteres."); return; }
    if (!conn) return;
    setAcaoEmAndamento("contingencia");
    try {
      const body = { ...bodyBase(), motivo: motivoContingencia.trim() };
      const r = await fetch(apiUrl("/api/contingencia-nfce/abrir"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Contingência aberta.", undefined, 5000);
        setMotivoContingencia("");
        carregarContingencia();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível abrir a contingência."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setAcaoEmAndamento(null);
    }
  };

  const fecharContingencia = async () => {
    if (!conn) return;
    setAcaoEmAndamento("contingencia");
    try {
      const r = await fetch(apiUrl("/api/contingencia-nfce/fechar"), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(bodyBase()),
      });
      const j = await r.json();
      if (j?.success) {
        fb.showSuccess(j.message || "Contingência fechada.", undefined, 5000);
        carregarContingencia();
      } else {
        fb.showError(friendlyApiError(j, "Não foi possível fechar a contingência."), undefined, 5000);
      }
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    } finally {
      setAcaoEmAndamento(null);
    }
  };

  const imprimirDanfce = async (it: NfceItem) => {
    if (!conn || !it.num_nfce) return;
    try {
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}`;
      const r = await fetch(apiUrl(`/api/comandas/${it.comanda}/doc-fiscal?${qs}`));
      const j = await r.json();
      if (!j?.success || j.tipo !== "NFCE") { fb.showWarning(friendlyApiError(j, "Nenhuma NFCe vinculada a esta comanda.")); return; }
      const empresa = await fetchEmpresaHeader(conn.api, conn.servidor, conn.banco);
      printHtml(buildDanfceHtml(empresa, it.comanda, j.detalhe), "DANFCe");
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  const verXml = async (it: NfceItem) => {
    if (!conn) return;
    try {
      const qs = `servidor=${encodeURIComponent(conn.servidor)}&banco=${encodeURIComponent(conn.banco)}&classe=${classe ?? ""}&master=${isMaster}`;
      const r = await fetch(apiUrl(`/api/gestor-nfce/${it.comanda}/xml?${qs}`));
      const j = await r.json();
      if (!j?.success) { fb.showWarning(friendlyApiError(j, "Comanda sem NFCe emitida.")); return; }
      setXmlVisualizado({ comanda: it.comanda, xml: j.xml });
    } catch (e) {
      fb.showError(friendlyCatchError(e));
    }
  };

  const exportarExcel = () => {
    if (!itens.length) { fb.showWarning("Consulte antes de exportar."); return; }
    exportSheetsToXlsx("gestor-nfce", [
      {
        name: "NFCe",
        rows: itens.map((it) => ({
          Comanda: it.comanda, Data: brDate(it.data), Cliente: it.cliente_nome, Valor: it.valor_venda,
          "Nº NFCe": it.num_nfce, Série: it.serie_nfce,
          Situação: it.situacao ? (SITUACAO_LABEL[it.situacao] || it.situacao) : "Sem NFCe",
          "Data Emissão": brDateTime(it.dhemi), Protocolo: it.protocolo_sefaz, "Chave de Acesso": it.chave_acesso,
        })),
      },
    ]);
  };

  if (!canAbrir) {
    return <LockedView title="Sem permissão" message="Você não tem permissão para acessar o Gestor NFCe." testID="gestor-nfce-no-perm" />;
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]} testID="gestor-nfce-screen">
      <View style={styles.header}>
        <IconButtonWithTooltip icon="chevron-back" label="Voltar" onPress={() => router.back()} size={22} color={colors.onBrandPrimary} style={styles.iconBtn} tooltipAlign="left" />
        <Text style={styles.headerTitle}>Gestor NFCe</Text>
        <View style={styles.headerActions}>
          <Pressable
            onPress={() => setContingenciaModal(true)}
            style={[styles.contingenciaPill, contingencia.aberta && styles.contingenciaPillAberta]}
            testID="gestor-nfce-contingencia-pill"
          >
            <Ionicons name={contingencia.aberta ? "alert-circle" : "shield-checkmark-outline"} size={16} color={colors.onBrandPrimary} />
            <Text style={styles.contingenciaPillText}>
              {contingencia.aberta ? `Contingência aberta ${contingencia.hora_inicio ? "às " + contingencia.hora_inicio.slice(0, 5) : ""}` : "Contingência fechada"}
            </Text>
          </Pressable>
          <IconButtonWithTooltip
            icon="information-circle-outline" label="Ajuda" onPress={() => setAjudaVisivel(true)}
            size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="gestor-nfce-ajuda"
          />
          {canInutilizar ? (
            <IconButtonWithTooltip
              icon="ban-outline" label="Inutilizar numeração"
              onPress={() => { setInutilizarSerie(""); setInutilizarNumeros(""); setMotivoInutilizar(""); setInutilizarModal(true); }}
              size={20} color={colors.onBrandPrimary} style={styles.iconBtn} testID="gestor-nfce-abrir-inutilizar"
            />
          ) : null}
          <Pressable onPress={exportarExcel} style={styles.saveBtn} hitSlop={8} testID="gestor-nfce-exportar">
            <Ionicons name="download-outline" size={18} color={colors.onBrandPrimary} />
            <Text style={styles.saveLabel}>Excel</Text>
          </Pressable>
        </View>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]} showsVerticalScrollIndicator={false}>
        <View style={styles.webShell}>
          <View style={styles.card}>
            <AccordionSection title="Buscar e Filtrar" defaultExpanded testID="gestor-nfce-filtros">
              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Data da venda, de</Text>
                  <WebDateField
                    value={dataVendaDe}
                    onChange={(v) => { setDataVendaDe(v || null); if (v) setDataVendaAte(v); }}
                    testID="gestor-nfce-data-venda-ini"
                    onSubmitEditing={() => document.querySelector<HTMLInputElement>('[data-testid="gestor-nfce-data-venda-fim"]')?.focus()}
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                  <WebDateField value={dataVendaAte} onChange={setDataVendaAte} testID="gestor-nfce-data-venda-fim" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Comanda</Text>
                  <TextInput value={comandaNum} onChangeText={(v) => setComandaNum(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-nfce-comanda" />
                </View>
                <View style={styles.colTiny}>
                  <Text style={styles.label}>Nº NFCe</Text>
                  <TextInput value={numNfceNum} onChangeText={(v) => setNumNfceNum(v.replace(/\D/g, ""))} style={styles.input} keyboardType="number-pad" testID="gestor-nfce-num-nfce" />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Cód. Cliente</Text>
                  <View style={{ flexDirection: "row", alignItems: "center", gap: spacing.xs }}>
                    <TextInput
                      value={clienteCodigo} onChangeText={(v) => setClienteCodigo(v.replace(/\D/g, ""))}
                      style={[styles.input, { flex: 1, minWidth: 0 }]} keyboardType="number-pad" testID="gestor-nfce-cliente"
                    />
                    <IconButtonWithTooltip
                      icon="search-outline" label="Buscar Cliente" onPress={clienteSearch.openModal}
                      size={18} color={colors.brandPrimary} testID="gestor-nfce-cliente-buscar"
                    />
                  </View>
                </View>
              </View>

              <View style={styles.rowFields}>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>Emissão NFCe, de</Text>
                  <WebDateField
                    value={dataNfceDe}
                    onChange={(v) => { setDataNfceDe(v || null); if (v) setDataNfceAte(v); }}
                    testID="gestor-nfce-data-nfce-ini"
                  />
                </View>
                <View style={styles.colNarrow}>
                  <Text style={styles.label}>até</Text>
                  <WebDateField value={dataNfceAte} onChange={setDataNfceAte} testID="gestor-nfce-data-nfce-fim" />
                </View>
                <View style={styles.colFlex}>
                  <Text style={styles.label}>Situação</Text>
                  <View style={styles.pillRow}>
                    {SITUACAO_CHIPS.map((c) => (
                      <Pressable
                        key={c.value} onPress={() => toggleSituacao(c.value)}
                        style={[styles.pillBtn, situacoes.includes(c.value) && styles.pillBtnSel]}
                        testID={`gestor-nfce-situacao-${c.value}`}
                      >
                        <Text style={[styles.pillBtnText, situacoes.includes(c.value) && styles.pillBtnTextSel]}>{c.label}</Text>
                      </Pressable>
                    ))}
                  </View>
                </View>
              </View>

              <View style={styles.rowFields}>
                <Pressable onPress={() => setIncluirSemNfce((v) => !v)} style={styles.checkRow} testID="gestor-nfce-incluir-sem-nfce">
                  <Ionicons name={incluirSemNfce ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Incluir comandas sem NFCe</Text>
                </Pressable>
                <Pressable onPress={() => setSomenteGaps((v) => !v)} style={styles.checkRow} testID="gestor-nfce-somente-gaps">
                  <Ionicons name={somenteGaps ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Somente números com falha na sequência</Text>
                </Pressable>
              </View>

              <View style={styles.modalActionsRow}>
                <Pressable onPress={buscar} disabled={loading} style={styles.primaryBtn} testID="gestor-nfce-buscar">
                  {loading ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Consultar</Text>}
                </Pressable>
              </View>
            </AccordionSection>
          </View>

          {somenteGaps && gapsAgrupados.length > 0 ? (
            <View style={[styles.card, { borderColor: colors.warning }]} testID="gestor-nfce-gaps-card">
              <Text style={[styles.totaisTitle, { color: colors.warning }]}>Falhas de sequência encontradas</Text>
              {gapsAgrupados.map((g) => (
                <Text key={g.serie} style={styles.hint}>
                  Série {g.serie}: números {g.numeros.join(", ")} nunca foram usados — considere Inutilizar essa numeração.
                </Text>
              ))}
            </View>
          ) : null}

          {selecionados.size > 0 ? (
            <View style={styles.bulkBar} testID="gestor-nfce-bulk-bar">
              <Text style={styles.bulkBarLabel}>{selecionados.size} selecionada{selecionados.size === 1 ? "" : "s"}</Text>
              <View style={styles.bulkBarActions}>
                {canCancelar ? (
                  <Pressable
                    onPress={() => { setMotivoCancelamento(""); setCancelarModal(true); }}
                    disabled={!!acaoEmAndamento} style={[styles.bulkBtn, { backgroundColor: colors.error }]} testID="gestor-nfce-bulk-cancelar"
                  >
                    {acaoEmAndamento === "cancelar" ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="close-circle-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Cancelar</Text></>
                    )}
                  </Pressable>
                ) : null}
                {canConsultar ? (
                  <Pressable onPress={consultar} disabled={!!acaoEmAndamento} style={styles.bulkBtn} testID="gestor-nfce-bulk-consultar">
                    {acaoEmAndamento === "consultar" ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="search-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Consultar</Text></>
                    )}
                  </Pressable>
                ) : null}
                {canRetransmitir ? (
                  <Pressable onPress={retransmitir} disabled={!!acaoEmAndamento} style={styles.bulkBtn} testID="gestor-nfce-bulk-retransmitir">
                    {acaoEmAndamento === "retransmitir" ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="sync-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Retransmitir</Text></>
                    )}
                  </Pressable>
                ) : null}
                {canValidarCont ? (
                  <Pressable onPress={validarContingencia} disabled={!!acaoEmAndamento} style={styles.bulkBtn} testID="gestor-nfce-bulk-validar">
                    {acaoEmAndamento === "validar" ? <ActivityIndicator color="#fff" size="small" /> : (
                      <><Ionicons name="shield-checkmark-outline" size={16} color="#fff" /><Text style={styles.bulkBtnText}>Validar Contingência</Text></>
                    )}
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : null}

          <View style={styles.card}>
            {loading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: 24 }} />
            ) : itens.length === 0 ? (
              <Text style={styles.hint}>Nenhuma comanda encontrada para os filtros selecionados.</Text>
            ) : (
              <>
                <Pressable onPress={alternarTodos} style={styles.selectAllRow} testID="gestor-nfce-selecionar-todos">
                  <Ionicons name={todosSelecionados ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                  <Text style={styles.checkLabel}>Selecionar todos ({itens.length})</Text>
                </Pressable>
                {itens.map((it, idx) => (
                  <View key={it.comanda} style={[styles.itemRow, { zIndex: itens.length - idx }]} testID={`gestor-nfce-item-${it.comanda}`}>
                    <Pressable onPress={() => toggleSelecionado(it.comanda)} hitSlop={8} testID={`gestor-nfce-check-${it.comanda}`}>
                      <Ionicons name={selecionados.has(it.comanda) ? "checkbox" : "square-outline"} size={20} color={colors.brandPrimary} />
                    </Pressable>
                    <View style={{ flex: 1 }}>
                      <Text style={styles.gridRowText}>
                        CMD #{it.comanda}
                        {" · "}{brDate(it.data)} · {it.cliente_nome} · <Text style={{ fontWeight: "700" }}>{formatBRL(it.valor_venda)}</Text>
                      </Text>
                      <Text style={styles.hint}>
                        <Text style={{ color: it.situacao ? SITUACAO_COLOR[it.situacao] : colors.muted, fontWeight: "600" }}>
                          {it.situacao ? (SITUACAO_LABEL[it.situacao] || it.situacao) : "Sem NFCe"}
                        </Text>
                        {it.num_nfce ? ` · NFCe ${it.num_nfce}${it.serie_nfce ? "/" + it.serie_nfce : ""}` : ""}
                        {it.dhemi ? ` · Emitida em ${brDateTime(it.dhemi)}` : ""}
                        {it.protocolo_sefaz ? ` · Protocolo ${it.protocolo_sefaz}` : ""}
                      </Text>
                    </View>
                    <View style={styles.itemActions}>
                      {it.num_nfce ? (
                        <IconButtonWithTooltip
                          icon="print-outline" label="Imprimir DANFCe" onPress={() => imprimirDanfce(it)}
                          style={styles.itemActionBtn} testID={`gestor-nfce-imprimir-${it.comanda}`}
                        />
                      ) : null}
                      {it.num_nfce ? (
                        <IconButtonWithTooltip
                          icon="code-slash-outline" label="Ver XML" onPress={() => verXml(it)}
                          style={styles.itemActionBtn} testID={`gestor-nfce-xml-${it.comanda}`}
                        />
                      ) : null}
                    </View>
                  </View>
                ))}
              </>
            )}
          </View>
        </View>
      </ScrollView>

      {/* Contingência — status + abrir/fechar. */}
      <AppModal visible={contingenciaModal} transparent animationType="fade" onRequestClose={() => setContingenciaModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setContingenciaModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Contingência NFCe</Text>
              <Pressable onPress={() => setContingenciaModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {contingencia.aberta ? (
              <>
                <Text style={styles.hint}>
                  Aberta em {brDate(contingencia.data_inicio || null)} às {(contingencia.hora_inicio || "").slice(0, 5)}.{"\n"}
                  Motivo: {contingencia.motivo}
                </Text>
                <Text style={[styles.hint, { marginTop: spacing.sm }]}>
                  Enquanto estiver aberta, novas NFCe ficam aguardando (situação "Aguardando Contingência") em vez de serem
                  transmitidas ao SEFAZ. Feche a contingência assim que o SEFAZ voltar e use "Validar Contingência" na lista
                  pra transmitir as notas que ficaram pendentes.
                </Text>
                {canContingencia ? (
                  <View style={styles.modalActionsRow}>
                    <Pressable onPress={fecharContingencia} disabled={!!acaoEmAndamento} style={[styles.primaryBtn, { backgroundColor: colors.success }]} testID="gestor-nfce-fechar-contingencia">
                      {acaoEmAndamento === "contingencia" ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Fechar Contingência</Text>}
                    </Pressable>
                  </View>
                ) : null}
              </>
            ) : (
              <>
                <Text style={styles.hint}>
                  Use somente quando o SEFAZ estiver fora do ar e não for possível emitir NFCe normalmente. As próximas
                  emissões ficarão aguardando até você fechar a contingência e validar cada uma.
                </Text>
                {canContingencia ? (
                  <>
                    <Text style={[styles.label, { marginTop: spacing.sm }]}>Motivo (mínimo 15 caracteres)</Text>
                    <TextInput
                      value={motivoContingencia} onChangeText={setMotivoContingencia}
                      style={[styles.input, { minHeight: 72 }]} multiline
                      placeholder="Ex.: Serviço do SEFAZ indisponível desde…" placeholderTextColor={colors.muted}
                      testID="gestor-nfce-motivo-contingencia"
                    />
                    <View style={styles.modalActionsRow}>
                      <Pressable
                        onPress={abrirContingencia} disabled={!!acaoEmAndamento || motivoContingencia.trim().length < 15}
                        style={[styles.primaryBtn, { backgroundColor: colors.warning }]} testID="gestor-nfce-abrir-contingencia-confirmar"
                      >
                        {acaoEmAndamento === "contingencia" ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Abrir Contingência</Text>}
                      </Pressable>
                    </View>
                  </>
                ) : null}
              </>
            )}
          </Pressable>
        </Pressable>
      </AppModal>

      {/* Cancelar — motivo obrigatório, aplicado a todas as comandas selecionadas. */}
      <AppModal visible={cancelarModal} transparent animationType="fade" onRequestClose={() => setCancelarModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setCancelarModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Cancelar NFCe ({selecionados.size})</Text>
              <Pressable onPress={() => setCancelarModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>
              Cancela só o documento fiscal junto ao SEFAZ — a venda, o estoque e os pagamentos não são alterados.
            </Text>
            <Text style={[styles.label, { marginTop: spacing.sm }]}>Motivo do cancelamento (mínimo 15 caracteres)</Text>
            <TextInput
              value={motivoCancelamento} onChangeText={setMotivoCancelamento}
              style={[styles.input, { minHeight: 72 }]} multiline
              placeholder="Descreva o motivo do cancelamento…" placeholderTextColor={colors.muted}
              testID="gestor-nfce-motivo-cancelamento"
            />
            <View style={styles.modalActionsRow}>
              <Pressable
                onPress={confirmarCancelar} disabled={!!acaoEmAndamento || motivoCancelamento.trim().length < 15}
                style={[styles.primaryBtn, { backgroundColor: colors.error }]} testID="gestor-nfce-confirmar-cancelar"
              >
                {acaoEmAndamento === "cancelar" ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Cancelar NFCe</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* Inutilizar Faixa — ação independente da seleção de linhas. */}
      <AppModal visible={inutilizarModal} transparent animationType="fade" onRequestClose={() => setInutilizarModal(false)}>
        <Pressable style={styles.modalBg} onPress={() => setInutilizarModal(false)}>
          <Pressable style={styles.modalCard} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Inutilizar Numeração</Text>
              <Pressable onPress={() => setInutilizarModal(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={styles.hint}>
              Use para números que nunca chegaram a ser usados numa venda (ex.: pulados por engano) — o SEFAZ é avisado
              que essa numeração fica definitivamente sem uso. Para uma NFCe que já foi emitida, use Cancelar.
            </Text>
            <View style={styles.rowFields}>
              <View style={styles.colTiny}>
                <Text style={styles.label}>Série</Text>
                <TextInput value={inutilizarSerie} onChangeText={setInutilizarSerie} style={styles.input} testID="gestor-nfce-inutilizar-serie" />
              </View>
              <View style={styles.colFlex}>
                <Text style={styles.label}>Números (ex.: 10, 12, 15-18)</Text>
                <TextInput value={inutilizarNumeros} onChangeText={setInutilizarNumeros} style={styles.input} testID="gestor-nfce-inutilizar-numeros" />
              </View>
            </View>
            <Text style={[styles.label, { marginTop: spacing.sm }]}>Motivo (mínimo 15 caracteres)</Text>
            <TextInput
              value={motivoInutilizar} onChangeText={setMotivoInutilizar}
              style={[styles.input, { minHeight: 72 }]} multiline
              placeholder="Descreva o motivo da inutilização…" placeholderTextColor={colors.muted}
              testID="gestor-nfce-motivo-inutilizar"
            />
            <View style={styles.modalActionsRow}>
              <Pressable
                onPress={confirmarInutilizar} disabled={!!acaoEmAndamento} style={[styles.primaryBtn, { backgroundColor: colors.error }]}
                testID="gestor-nfce-confirmar-inutilizar"
              >
                {acaoEmAndamento === "inutilizar" ? <ActivityIndicator color="#fff" size="small" /> : <Text style={styles.primaryBtnText}>Inutilizar</Text>}
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* Resultado de uma ação em lote — uma linha por comanda/número. */}
      <AppModal visible={!!resultadoLote} transparent animationType="fade" onRequestClose={() => setResultadoLote(null)}>
        <Pressable style={styles.modalBg} onPress={() => setResultadoLote(null)}>
          <Pressable style={[styles.modalCard, { maxHeight: "80%" }]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>{resultadoLote?.titulo}</Text>
              <Pressable onPress={() => setResultadoLote(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {resultadoLote?.apoioFiscalLote ? (
              <View
                style={{
                  backgroundColor: colors.brandTertiary, borderRadius: radius.md,
                  padding: spacing.sm, marginBottom: spacing.sm, gap: 6,
                }}
                testID="gestor-nfce-apoio-fiscal-lote"
              >
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <Ionicons name="shield-checkmark-outline" size={16} color={colors.brandPrimary} />
                  <Text style={{ fontSize: 13, fontWeight: "600", color: colors.onSurface }}>
                    Apoio Fiscal BackOn — {resultadoLote.apoioFiscalLote.total} item(ns) não processado(s)
                  </Text>
                </View>
                {resultadoLote.apoioFiscalLote.grupos.map((g) => (
                  <View key={g.codigo_rejeicao} style={{ gap: 2 }}>
                    <Text style={{ fontSize: 12, fontWeight: "600", color: colors.onSurface }}>
                      {g.codigo_rejeicao} — {g.titulo} ({g.quantidade}x)
                    </Text>
                    <Text style={{ fontSize: 12, color: colors.muted, lineHeight: 16 }}>{g.explicacao_curta}</Text>
                  </View>
                ))}
                <Text style={{ fontSize: 11, color: colors.muted, marginTop: 2 }}>
                  Nosso suporte já foi avisado automaticamente sobre este lote.
                </Text>
              </View>
            ) : null}
            <ScrollView style={{ maxHeight: 380 }}>
              {(resultadoLote?.linhas || []).map((l, idx) => (
                <View key={idx} style={styles.resultadoLinha}>
                  <Ionicons name={l.success ? "checkmark-circle" : "close-circle"} size={18} color={l.success ? colors.success : colors.error} />
                  <View style={{ flex: 1 }}>
                    <Text style={styles.gridRowText}>{l.comanda ? `Comanda #${l.comanda}` : l.numero ? `Número ${l.numero}` : ""}</Text>
                    <Text style={styles.hint}>
                      {l.message || (l.situacao_sefaz ? `Situação SEFAZ: ${l.situacao_sefaz}${l.motivo_sefaz ? " — " + l.motivo_sefaz : ""}` : "") || (l.protocolo_sefaz ? `Protocolo ${l.protocolo_sefaz}` : "") || (l.success ? "Concluído." : "")}
                    </Text>
                  </View>
                </View>
              ))}
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      {/* XML armazenado — só visualização/conferência. */}
      <AppModal visible={!!xmlVisualizado} transparent animationType="fade" onRequestClose={() => setXmlVisualizado(null)}>
        <Pressable style={styles.modalBg} onPress={() => setXmlVisualizado(null)}>
          <Pressable style={[styles.modalCard, styles.modalCardWide]} onPress={(e) => e.stopPropagation()}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>XML — Comanda #{xmlVisualizado?.comanda}</Text>
              <Pressable onPress={() => setXmlVisualizado(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <ScrollView style={{ maxHeight: 420 }}>
              <TextInput
                value={xmlVisualizado?.xml || ""} editable={false} multiline
                style={styles.xmlBox} testID="gestor-nfce-xml-conteudo"
              />
            </ScrollView>
          </Pressable>
        </Pressable>
      </AppModal>

      <AjudaPedidoModal visible={ajudaVisivel} onClose={() => setAjudaVisivel(false)} titulo="Gestor NFCe" itens={GESTOR_NFCE_AJUDA_ITENS} />

      <ClientSearchModal
        visible={clienteSearch.open}
        onClose={clienteSearch.closeModal}
        term={clienteSearch.term}
        setTerm={clienteSearch.setTerm}
        loading={clienteSearch.loading}
        results={clienteSearch.results}
        onPick={(c) => { setClienteCodigo(String(c.codigo)); clienteSearch.closeModal(); }}
        onCreate={clienteSearch.closeModal}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingTop: spacing.sm, paddingBottom: spacing.md, gap: spacing.sm, zIndex: 100 },
  iconBtn: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 16, fontWeight: "500" },
  headerActions: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  saveBtn: { flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 13 },

  contingenciaPill: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 8, backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill, borderWidth: 1, borderColor: "rgba(255,255,255,0.3)" },
  contingenciaPillAberta: { backgroundColor: "rgba(255,80,80,0.3)" },
  contingenciaPillText: { color: colors.onBrandPrimary, fontWeight: "500", fontSize: 12 },

  scroll: { paddingBottom: spacing.xxxl },
  scrollWeb: WEB_SCROLL_CENTER,
  webShell: WEB_CONTENT_SHELL,
  card: { ...WEB_FILTER_CARD, marginBottom: spacing.lg },
  label: { fontSize: 12, color: colors.muted, fontWeight: "500", marginTop: spacing.sm, marginBottom: 4 },
  input: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 11, fontSize: 14, color: colors.onSurface },
  hint: { fontSize: 11, color: colors.muted, marginTop: 4, fontStyle: "italic" },
  rowFields: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end", flexWrap: "wrap" },
  colFlex: { flex: 1, minWidth: 160 },
  colNarrow: { width: 170 },
  colTiny: { width: 100 },

  checkRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 11 },
  checkLabel: { fontSize: 13, color: colors.onSurface },
  selectAllRow: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border, marginBottom: 4 },

  pillRow: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  pillBtn: { paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface },
  pillBtnSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  pillBtnText: { fontSize: 13, color: colors.onSurface, fontWeight: "500" },
  pillBtnTextSel: { color: colors.onBrandPrimary },

  modalActionsRow: { flexDirection: "row", justifyContent: "flex-end", gap: spacing.sm, marginTop: spacing.md },
  primaryBtn: { paddingHorizontal: spacing.lg, paddingVertical: 11, borderRadius: radius.sm, backgroundColor: colors.brandPrimary, alignItems: "center", justifyContent: "center", minWidth: 130 },
  primaryBtnText: { color: "#fff", fontWeight: "600", fontSize: 13 },

  totaisTitle: { fontSize: 12, color: colors.brandPrimary, fontWeight: "600", marginBottom: spacing.sm },

  bulkBar: { ...WEB_FILTER_CARD, marginBottom: spacing.lg, flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm, backgroundColor: colors.surfaceSecondary },
  bulkBarLabel: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  bulkBarActions: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  bulkBtn: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: spacing.md, paddingVertical: 9, borderRadius: radius.sm, backgroundColor: colors.brandPrimary },
  bulkBtnText: { color: "#fff", fontWeight: "600", fontSize: 12 },

  itemRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: colors.border },
  gridRowText: { fontSize: 13, color: colors.onSurface },
  itemActions: { flexDirection: "row", alignItems: "center", gap: 4 },
  itemActionBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center", borderRadius: radius.sm, backgroundColor: colors.surfaceSecondary },

  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.45)", justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.xl },
  modalCard: { backgroundColor: colors.surface, borderRadius: radius.lg, padding: spacing.lg, width: "100%", maxWidth: 420, borderWidth: 1, borderColor: colors.border },
  modalCardWide: { maxWidth: 720 },
  modalHeader: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: spacing.sm },
  modalTitle: { fontSize: 15, fontWeight: "700", color: colors.onSurface },

  resultadoLinha: { flexDirection: "row", alignItems: "flex-start", gap: spacing.sm, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: colors.border },

  xmlBox: { fontFamily: Platform.OS === "web" ? "monospace" : undefined, fontSize: 11, color: colors.onSurface, backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.md, minHeight: 300 },
});
