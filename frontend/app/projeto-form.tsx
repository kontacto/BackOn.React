// Gestor de Projetos — cabeçalho + documentos vinculados (Pedido/O.S./
// Requisição) + itens agregados + anexos. Migração de `Geral\frmgespro.frm`,
// Fase 1 (núcleo) — ver PENDENCIAS.md > "Gestor de Projetos" pro rastreio
// completo e plano de fases. Segue o "Full CRUD Form Screen Standard" do
// CLAUDE.md: tela cheia (não modal), Gravar no canto superior direito,
// identidade (Cliente) sempre visível acima de qualquer seção secundária.
import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator, Modal, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useLocalSearchParams, useRouter } from "expo-router";
import { Ionicons } from "@/src/components/Ionicons";

import { usePermissions } from "@/src/permissions";
import { useFeedback } from "@/src/components/feedback/FeedbackProvider";
import LockedView from "@/src/components/LockedView";
import IconButtonWithTooltip from "@/src/components/IconButtonWithTooltip";
import SelectField, { SelectOption } from "@/src/components/SelectField";
import WebDateField from "@/src/components/WebDateField";
import GestorDocumentosSection, { GESTOR_DOC_GRUPO_CLIENTE } from "@/src/components/GestorDocumentosSection";
import ClienteSection from "@/src/components/pedido/ClienteSection";
import ClientSearchModal from "@/src/components/pedido/ClientSearchModal";
import AjudaPedidoModal, { HelpItem } from "@/src/components/pedido/AjudaPedidoModal";
import { styles as pedidoStyles, SIT_COLOR } from "@/src/components/pedido/styles";
import { ClienteRow, ClienteResumo } from "@/src/components/pedido/types";
import { clienteSearchParams } from "@/src/hooks/useClienteForm";

import { colors, radius, spacing } from "@/src/theme/colors";
import { WEB_CONTENT_SHELL, WEB_SCROLL_CENTER } from "@/src/theme/webLayout";
import { apiBase, apiGet, apiSend, friendlyApiError, friendlyCatchError } from "@/src/utils/api";
import { getSession } from "@/src/utils/storage/session";
import { listConnections, Connection } from "@/src/utils/storage/connections";
import { formatBRL, formatDateBR } from "@/src/utils/format";
import { printHtml, escHtml } from "@/src/utils/printHtml";
import { fetchEmpresaHeader, buildReportHeaderHtml, REPORT_HEADER_CSS } from "@/src/utils/print-report-header";
import { exportSheetsToXlsx } from "@/src/utils/export-xlsx";

type DocumentoRow = {
  tipo_doc: "PED" | "OSS" | "REQ";
  tipo_doc_label: string;
  num_doc: number;
  data_inclusao: string | null;
  situacao: string;
  total: number;
};

type ItensAgregados = {
  produtos: { codigo_fab: string; descricao: string; qtd: number; preco_custo: number; preco_venda: number; total_custo: number; total_venda: number }[];
  servicos: { codigo_fab: string; descricao: string; qtd: number; preco_custo: number; preco_venda: number; total_custo: number; total_venda: number }[];
  total_custo_produtos: number; total_venda_produtos: number;
  total_custo_servicos: number; total_venda_servicos: number;
  total_custo_geral: number; total_venda_geral: number;
};

type AjusteDocumento = {
  tipo_doc: "PED" | "OSS";
  tipo_doc_label: string;
  num_doc: number;
  situacao: string;
  total_produtos: number;
  total_servicos: number;
  total: number;
};

type AjustePreview = {
  estimado: { produtos: number; servicos: number; geral: number };
  faturado: { produtos: number; servicos: number; geral: number };
  pendente: { produtos: number; servicos: number; geral: number };
  saldo_orcamento: { produtos: number; servicos: number };
  documentos: AjusteDocumento[];
};

const numToInput = (n: number) => (n || 0).toFixed(2).replace(".", ",");
const inputToNum = (s: string): number => {
  const v = parseFloat(String(s ?? "0").replace(",", "."));
  return Number.isFinite(v) ? v : 0;
};

const TIPOS_VINCULO: { tipo: "PED" | "OSS" | "REQ"; label: string; acao: string; icon: keyof typeof Ionicons.glyphMap }[] = [
  { tipo: "PED", label: "Pedido", acao: "ADD_PEDIDO", icon: "receipt-outline" },
  { tipo: "OSS", label: "O.S.", acao: "ADD_OS", icon: "construct-outline" },
  { tipo: "REQ", label: "Requisição", acao: "ADD_REQUISICAO", icon: "swap-horizontal-outline" },
];

const AJUDA_PROJETO_ITENS: HelpItem[] = [
  {
    titulo: "Vincular Pedido/O.S./Requisição",
    texto: "Um documento (Pedido de Venda, O.S. ou Requisição) já existente pode ser vinculado a um Projeto — informe o número do documento e confirme. Cada documento só pode pertencer a um Projeto no sistema inteiro. Não existe um tipo separado de \"Orçamento\": um Pedido ainda Aberto já cumpre esse papel.",
    icon: { lib: "ion", name: "link-outline" },
  },
  {
    titulo: "Itens do Projeto",
    texto: "Soma automática de todos os Produtos e Serviços de todos os documentos vinculados — atualiza sozinha, sem precisar copiar nada manualmente.",
    icon: { lib: "ion", name: "cube-outline" },
  },
  {
    titulo: "Faturado / Saldo a Faturar",
    texto: "Faturado é a soma dos documentos vinculados que já foram faturados; Saldo a Faturar é o restante, ainda pendente.",
    icon: { lib: "ion", name: "cash-outline" },
  },
  {
    titulo: "Finalizar / Reabrir / Cancelar",
    texto: "Finalizar encerra o Projeto (pode ser reaberto depois). Cancelar é definitivo e desvincula todos os documentos (ficam livres para entrar em outro Projeto). Só é possível vincular ou remover documentos enquanto o Projeto estiver Aberto.",
    icon: { lib: "ion", name: "flag-outline" },
  },
  {
    titulo: "Valor Estimado (Produtos/Serviços)",
    texto: "Orçamento estimado do Projeto, informado manualmente — usado só como referência de acompanhamento (comparado com o que já foi faturado e o que ainda está pendente nos documentos vinculados). Não trava nem impede a inclusão de itens além desse valor.",
    icon: { lib: "ion", name: "cash-outline" },
  },
  {
    titulo: "Ajustar Valores",
    texto: "Redistribui o valor de Produtos ou de Serviços entre os itens dos documentos (Pedido/O.S.) vinculados e ainda não faturados, para bater um novo valor-alvo — útil quando o cliente negocia um valor fechado diferente da soma dos itens. Sempre recalcula a partir do preço cheio, sem acumular ajustes anteriores.",
    icon: { lib: "ion", name: "calculator-outline" },
  },
  {
    titulo: "Detalhar Itens / Custo e Margem",
    texto: "\"Detalhar itens\" mostra Produtos e Serviços um a um, com quantidade e valor de venda. Custo e margem só aparecem para quem tem a permissão \"Visualizar Custos do Projeto\" — quem não tem só vê os valores de venda.",
    icon: { lib: "ion", name: "list-outline" },
  },
  {
    titulo: "Imprimir",
    texto: "Gera uma impressão do Projeto com os dados da empresa, documentos vinculados e itens — sem o filtro da tela, só o conteúdo do Projeto em si.",
    icon: { lib: "ion", name: "print-outline" },
  },
  {
    titulo: "Exportar Excel",
    texto: "Baixa uma planilha (.xlsx) com 3 abas: Documentos Vinculados, Produtos e Serviços — útil para conferência ou envio a quem não usa o sistema.",
    icon: { lib: "ion", name: "download-outline" },
  },
  {
    titulo: "Ver Logs",
    texto: "Abre o Log de Auditoria já filtrado por este Projeto — mostra quem gravou, vinculou documento, ajustou valores ou mudou a situação, e quando.",
    icon: { lib: "ion", name: "time-outline" },
  },
];

export default function ProjetoFormScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ codigo?: string }>();
  const { can, moduleOn } = usePermissions();
  const feedback = useFeedback();

  if (Platform.OS !== "web") {
    return <LockedView title="Disponível somente na versão web" message="O Gestor de Projetos está disponível apenas no web." testID="projeto-form-web-only" />;
  }
  if (!moduleOn("gestor_projetos")) {
    return (
      <LockedView
        title="Módulo desativado"
        message="O módulo Gestor de Projetos está desligado em Configurações > Módulos e Recursos. Fale com o administrador para habilitá-lo."
        testID="projeto-form-module-off"
      />
    );
  }

  const codigoParam = params.codigo ? parseInt(String(params.codigo), 10) : null;

  const [conn, setConn] = useState<Connection | null>(null);
  const [usuarioCod, setUsuarioCod] = useState<number>(-2);
  const [classe, setClasse] = useState<number | null>(null);
  const [isMaster, setIsMaster] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const [projetoId, setProjetoId] = useState<number | null>(codigoParam);
  const editing = projetoId != null;
  const [situacao, setSituacao] = useState("A");
  const [situacaoLabel, setSituacaoLabel] = useState("Aberto");
  const [dataAbertura, setDataAbertura] = useState<string | null>(null);
  const camposTravados = editing && situacao !== "A";

  const [cliente, setCliente] = useState<ClienteRow | null>(null);
  const [clienteResumo, setClienteResumo] = useState<ClienteResumo | null>(null);
  const [loadingResumo, setLoadingResumo] = useState(false);
  const [clienteQuickTerm, setClienteQuickTerm] = useState("");
  const [clienteQuickLoading, setClienteQuickLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState("");
  const [searchResults, setSearchResults] = useState<ClienteRow[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);

  const [funcOptions, setFuncOptions] = useState<SelectOption[]>([]);
  const [responsavel, setResponsavel] = useState<number | null>(null);
  const [dataInicio, setDataInicio] = useState<string | null>(null);
  const [dataPrevista, setDataPrevista] = useState<string | null>(null);
  const [detalhes, setDetalhes] = useState("");
  const [valorProdutos, setValorProdutos] = useState("0,00");
  const [valorServicos, setValorServicos] = useState("0,00");

  const [documentos, setDocumentos] = useState<DocumentoRow[]>([]);
  const [itens, setItens] = useState<ItensAgregados | null>(null);
  const [detalheItensOpen, setDetalheItensOpen] = useState(false);
  const [faturado, setFaturado] = useState(0);
  const [saldoAFaturar, setSaldoAFaturar] = useState(0);
  const [removendoDoc, setRemovendoDoc] = useState<string | null>(null);

  const [vincularTipo, setVincularTipo] = useState<"PED" | "OSS" | "REQ" | null>(null);
  const [vincularNum, setVincularNum] = useState("");
  const [vincularPreview, setVincularPreview] = useState<{ cliente_nome: string; situacao_label: string; total: number } | null>(null);
  const [vincularLoading, setVincularLoading] = useState(false);
  const [vincularSaving, setVincularSaving] = useState(false);

  const [anexosOpen, setAnexosOpen] = useState(false);
  const [ajudaOpen, setAjudaOpen] = useState(false);
  const [imprimindo, setImprimindo] = useState(false);
  const [finalizando, setFinalizando] = useState(false);
  const [reabrindo, setReabrindo] = useState(false);
  const [cancelando, setCancelando] = useState(false);

  const [ajustarOpen, setAjustarOpen] = useState(false);
  const [ajustarLoading, setAjustarLoading] = useState(false);
  const [ajustarSaving, setAjustarSaving] = useState(false);
  const [ajustarPreview, setAjustarPreview] = useState<AjustePreview | null>(null);
  const [ajustarTipo, setAjustarTipo] = useState<"P" | "S">("P");
  const [ajustarSelecionados, setAjustarSelecionados] = useState<Set<string>>(new Set());
  const [ajustarNovoValor, setAjustarNovoValor] = useState("");

  const loadProjeto = useCallback(async (c: Connection, id: number) => {
    try {
      const j = await apiGet(c, `/api/projetos/${id}`);
      if (j?.success && j.projeto) {
        const p = j.projeto;
        setProjetoId(p.codigo);
        setSituacao(p.situacao);
        setSituacaoLabel(p.situacao_label);
        setDataAbertura(p.data_abertura);
        setCliente(p.cliente ? { codigo: p.cliente, nome: p.cliente_nome, cgc_cpf: "", telefone: "" } : null);
        setClienteQuickTerm(p.cliente_nome || "");
        setResponsavel(p.responsavel ?? null);
        setDataInicio(p.data_inicio);
        setDataPrevista(p.data_prevista);
        setDetalhes(p.detalhes || "");
        setValorProdutos(numToInput(p.valor_produtos || 0));
        setValorServicos(numToInput(p.valor_servicos || 0));
        setDocumentos(p.documentos || []);
        setItens(p.itens || null);
        setFaturado(p.faturado || 0);
        setSaldoAFaturar(p.saldo_a_faturar || 0);
      } else {
        feedback.showError(j?.message || "Erro ao carregar Projeto.");
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Erro ao carregar Projeto."));
    }
  }, [feedback]);

  useEffect(() => {
    (async () => {
      const s = await getSession();
      if (!s) { router.replace("/login"); return; }
      const c = (await listConnections()).find((x) => x.empresa === s.empresa) || null;
      setConn(c);
      const func = (s?.funcionario as Record<string, unknown> | null) || null;
      const fid = func?.codigo_int ?? func?.codigo;
      const uid = fid != null ? parseInt(String(fid), 10) : null;
      const masterFlag = !!(s?.usuario as { master?: boolean } | undefined)?.master;
      setIsMaster(masterFlag);
      setUsuarioCod(masterFlag ? -2 : (uid ?? -2));
      const cf = func?.funcao;
      const fc = cf != null ? parseInt(String(cf), 10) : NaN;
      setClasse(masterFlag ? 1 : (Number.isFinite(fc) && fc > 0 ? fc : 1));
      if (!editing && uid != null) setResponsavel(uid);

      if (c) {
        try {
          const rf = await apiGet(c, `/api/funcionarios`);
          if (rf?.success) {
            setFuncOptions((rf.items || []).map((f: { codigo_int: number; nome_guerra?: string; nome?: string }) => ({
              value: f.codigo_int, label: f.nome_guerra || f.nome || String(f.codigo_int),
            })));
          }
        } catch {
          // combo fica vazio
        }
      }
      if (editing && codigoParam && c) {
        await loadProjeto(c, codigoParam);
      }
      setLoading(false);
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!conn || !cliente?.codigo) { setClienteResumo(null); return; }
    let cancelled = false;
    setLoadingResumo(true);
    apiGet(conn, `/api/clientes/${cliente.codigo}/resumo`)
      .then((j) => { if (!cancelled) setClienteResumo(j?.success && j.cliente ? j.cliente : null); })
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

  const handleSave = async () => {
    if (!conn) return;
    if (!cliente) { feedback.showError("Selecione um cliente."); return; }
    setSaving(true);
    try {
      const body = {
        cliente: cliente.codigo, responsavel, data_inicio: dataInicio, data_prevista: dataPrevista,
        detalhes, valor_produtos: inputToNum(valorProdutos), valor_servicos: inputToNum(valorServicos),
        master: isMaster, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      };
      const j = projetoId
        ? await apiSend(conn, `/api/projetos/${projetoId}`, "PUT", body)
        : await apiSend(conn, `/api/projetos/create`, "POST", body);
      if (j?.success) {
        feedback.showSuccess(projetoId ? "Projeto atualizado." : "Projeto criado.");
        if (!projetoId) {
          router.replace({ pathname: "/projeto-form", params: { codigo: String(j.codigo) } } as never);
        } else {
          await loadProjeto(conn, projetoId);
        }
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao gravar."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao gravar."));
    } finally {
      setSaving(false);
    }
  };

  const handleTransicao = async (acao: "finalizar" | "reabrir" | "cancelar", setFlag: (v: boolean) => void) => {
    if (!conn || !projetoId) return;
    setFlag(true);
    try {
      const j = await apiSend(conn, `/api/projetos/${projetoId}/${acao}`, "POST", {
        classe, master: isMaster, usuario_alteracao: usuarioCod, plataforma: Platform.OS,
      });
      if (j?.success) {
        feedback.showSuccess(j.message || "Situação atualizada.");
        await loadProjeto(conn, projetoId);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao atualizar situação."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao atualizar situação."));
    } finally {
      setFlag(false);
    }
  };

  const openVincular = (tipo: "PED" | "OSS" | "REQ") => {
    setVincularTipo(tipo);
    setVincularNum("");
    setVincularPreview(null);
  };

  const buscarVincular = async () => {
    if (!conn || !vincularTipo || !vincularNum.trim()) return;
    const num = parseInt(vincularNum, 10);
    if (!num) { feedback.showError("Informe um número válido."); return; }
    setVincularLoading(true);
    setVincularPreview(null);
    try {
      const url = vincularTipo === "PED" ? `/api/pedidos/${num}` : vincularTipo === "OSS" ? `/api/os/${num}` : `/api/requisicoes/${num}`;
      const j = await apiGet(conn, url);
      if (!j?.success) {
        feedback.showError(j?.message || "Documento não encontrado.");
        return;
      }
      const doc = vincularTipo === "PED" ? j.pedido : vincularTipo === "OSS" ? j.os : j.item;
      setVincularPreview({
        cliente_nome: doc?.cliente_nome || "—",
        situacao_label: doc?.situacao_label || doc?.situacao || "—",
        total: Number(doc?.total ?? 0),
      });
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Erro ao buscar documento."));
    } finally {
      setVincularLoading(false);
    }
  };

  const confirmarVincular = async () => {
    if (!conn || !projetoId || !vincularTipo) return;
    setVincularSaving(true);
    try {
      const j = await apiSend(conn, `/api/projetos/${projetoId}/documentos`, "POST", {
        tipo_doc: vincularTipo, num_doc: parseInt(vincularNum, 10),
        master: isMaster, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (j?.success) {
        feedback.showSuccess(j.message || "Documento vinculado.");
        setVincularTipo(null);
        await loadProjeto(conn, projetoId);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao vincular."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao vincular."));
    } finally {
      setVincularSaving(false);
    }
  };

  const removerDocumento = (doc: DocumentoRow) => {
    if (!conn || !projetoId) return;
    feedback.showConfirm(`Remover ${doc.tipo_doc_label} nº ${doc.num_doc} deste Projeto?`, async () => {
      setRemovendoDoc(`${doc.tipo_doc}-${doc.num_doc}`);
      try {
        const j = await apiSend(conn, `/api/projetos/${projetoId}/documentos/remover`, "POST", {
          tipo_doc: doc.tipo_doc, num_doc: doc.num_doc,
          master: isMaster, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
        });
        if (j?.success) {
          feedback.showSuccess("Documento removido.");
          await loadProjeto(conn, projetoId);
        } else {
          feedback.showError(friendlyApiError(j, "Falha ao remover."));
        }
      } catch (e) {
        feedback.showError(friendlyCatchError(e, "Falha ao remover."));
      } finally {
        setRemovendoDoc(null);
      }
    });
  };

  const openAjustarValores = async () => {
    if (!conn || !projetoId) return;
    setAjustarOpen(true);
    setAjustarLoading(true);
    setAjustarPreview(null);
    setAjustarTipo("P");
    try {
      const j = await apiGet(conn, `/api/projetos/${projetoId}/ajustar-valores`);
      if (j?.success) {
        const preview: AjustePreview = { estimado: j.estimado, faturado: j.faturado, pendente: j.pendente, saldo_orcamento: j.saldo_orcamento, documentos: j.documentos || [] };
        setAjustarPreview(preview);
        setAjustarSelecionados(new Set(preview.documentos.map((d) => `${d.tipo_doc}-${d.num_doc}`)));
        const totalP = preview.documentos.reduce((s, d) => s + d.total_produtos, 0);
        setAjustarNovoValor(numToInput(totalP));
      } else {
        feedback.showError(j?.message || "Erro ao carregar dados de ajuste.");
        setAjustarOpen(false);
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Erro ao carregar dados de ajuste."));
      setAjustarOpen(false);
    } finally {
      setAjustarLoading(false);
    }
  };

  const trocarAjustarTipo = (tipo: "P" | "S") => {
    setAjustarTipo(tipo);
    if (!ajustarPreview) return;
    const total = ajustarPreview.documentos
      .filter((d) => ajustarSelecionados.has(`${d.tipo_doc}-${d.num_doc}`))
      .reduce((s, d) => s + (tipo === "P" ? d.total_produtos : d.total_servicos), 0);
    setAjustarNovoValor(numToInput(total));
  };

  const toggleAjustarDoc = (key: string) => {
    setAjustarSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      return next;
    });
  };

  const ajustarTotalAtual = ajustarPreview
    ? ajustarPreview.documentos
        .filter((d) => ajustarSelecionados.has(`${d.tipo_doc}-${d.num_doc}`))
        .reduce((s, d) => s + (ajustarTipo === "P" ? d.total_produtos : d.total_servicos), 0)
    : 0;

  const confirmarAjustarValores = async () => {
    if (!conn || !projetoId || !ajustarPreview) return;
    const novoValor = inputToNum(ajustarNovoValor);
    if (!novoValor || novoValor <= 0) { feedback.showError("Informe um valor válido para o ajuste."); return; }
    const documentosSel = ajustarPreview.documentos
      .filter((d) => ajustarSelecionados.has(`${d.tipo_doc}-${d.num_doc}`))
      .map((d) => ({ tipo_doc: d.tipo_doc, num_doc: d.num_doc }));
    if (documentosSel.length === 0) { feedback.showError("Selecione ao menos um documento para reprocessar."); return; }
    setAjustarSaving(true);
    try {
      const j = await apiSend(conn, `/api/projetos/${projetoId}/ajustar-valores`, "POST", {
        tipo: ajustarTipo, novo_valor: novoValor, documentos: documentosSel,
        master: isMaster, usuario_alteracao: usuarioCod, classe, plataforma: Platform.OS,
      });
      if (j?.success) {
        feedback.showSuccess(j.message || "Valores ajustados com sucesso.", undefined, 5000);
        setAjustarOpen(false);
        await loadProjeto(conn, projetoId);
      } else {
        feedback.showError(friendlyApiError(j, "Falha ao ajustar valores."));
      }
    } catch (e) {
      feedback.showError(friendlyCatchError(e, "Falha ao ajustar valores."));
    } finally {
      setAjustarSaving(false);
    }
  };

  const handleImprimir = async () => {
    if (!conn || !projetoId) return;
    setImprimindo(true);
    try {
      const empresa = await fetchEmpresaHeader(apiBase(conn), conn.servidor, conn.banco);
      const responsavelNome = funcOptions.find((o) => o.value === responsavel)?.label || "—";

      const linhaItem = (it: { codigo_fab: string; descricao: string; qtd: number; preco_custo: number; preco_venda: number; total_custo: number; total_venda: number }) => {
        const margem = it.preco_custo > 0 ? (((it.preco_venda - it.preco_custo) / it.preco_custo) * 100).toFixed(1) : "—";
        return `
        <div class="row3">
          <span>${escHtml(it.codigo_fab)} — ${escHtml(it.descricao)} (Qtd ${it.qtd})</span>
          <span>${canVerCustos ? `Custo: ${formatBRL(it.total_custo)}${it.preco_custo > 0 ? ` (Marg. ${margem}%)` : ""}` : ""}</span>
          <span>${formatBRL(it.total_venda)}</span>
        </div>`;
      };

      const documentosHtml = documentos.length
        ? documentos.map((d) => `
          <div class="row">
            <span>${escHtml(d.tipo_doc_label)} nº ${d.num_doc} — ${escHtml(d.data_inclusao ? formatDateBR(d.data_inclusao) : "—")} · ${escHtml(d.situacao || "—")}</span>
            <span>${formatBRL(d.total)}</span>
          </div>`).join("")
        : `<div class="mb">Nenhum documento vinculado.</div>`;

      const produtosHtml = itens?.produtos.length ? itens.produtos.map(linhaItem).join("") : `<div class="mb">Nenhum produto.</div>`;
      const servicosHtml = itens?.servicos.length ? itens.servicos.map(linhaItem).join("") : `<div class="mb">Nenhum serviço.</div>`;

      const html = `
        <style>${REPORT_HEADER_CSS}</style>
        ${buildReportHeaderHtml(empresa, `Projeto nº ${projetoId}`)}
        <div class="hr"></div>
        <div class="mb"><b>Cliente:</b> ${escHtml(cliente?.nome || "—")}</div>
        <div class="mb"><b>Responsável:</b> ${escHtml(responsavelNome)} &nbsp; <b>Situação:</b> ${escHtml(situacaoLabel)}</div>
        <div class="mb"><b>Aberto em:</b> ${escHtml(dataAbertura ? formatDateBR(dataAbertura) : "—")} &nbsp;
          <b>Início:</b> ${escHtml(dataInicio ? formatDateBR(dataInicio) : "—")} &nbsp;
          <b>Prev. Término:</b> ${escHtml(dataPrevista ? formatDateBR(dataPrevista) : "—")}</div>
        ${detalhes ? `<div class="mb"><b>Detalhes:</b> ${escHtml(detalhes)}</div>` : ""}
        <div class="mb"><b>Valor Estimado:</b> Produtos ${formatBRL(inputToNum(valorProdutos))} · Serviços ${formatBRL(inputToNum(valorServicos))}</div>

        <div class="hr"></div>
        <div class="big mb">Documentos Vinculados</div>
        ${documentosHtml}

        <div class="hr"></div>
        <div class="big mb">Produtos</div>
        ${produtosHtml}
        <div class="row"><span><b>Total Produtos</b></span><span><b>${formatBRL(itens?.total_venda_produtos || 0)}</b></span></div>

        <div class="hr"></div>
        <div class="big mb">Serviços</div>
        ${servicosHtml}
        <div class="row"><span><b>Total Serviços</b></span><span><b>${formatBRL(itens?.total_venda_servicos || 0)}</b></span></div>

        <div class="hr"></div>
        <div class="row"><span><b>Total Geral</b></span><span><b>${formatBRL(itens?.total_venda_geral || 0)}</b></span></div>
        ${canVerCustos ? `<div class="row"><span>Custo Geral</span><span>${formatBRL(itens?.total_custo_geral || 0)}</span></div>` : ""}
        <div class="row"><span>Faturado</span><span>${formatBRL(faturado)}</span></div>
        <div class="row"><span>Saldo a Faturar</span><span>${formatBRL(saldoAFaturar)}</span></div>
      `;
      printHtml(html, `Projeto nº ${projetoId}`);
    } finally {
      setImprimindo(false);
    }
  };

  const handleExportarExcel = () => {
    if (!projetoId) return;
    const sheetsDocumentos = documentos.map((d) => ({
      Tipo: d.tipo_doc_label, Número: d.num_doc,
      Data: d.data_inclusao ? formatDateBR(d.data_inclusao) : "—",
      Situação: d.situacao || "—", Total: d.total,
    }));
    const linhaItem = (it: { codigo_fab: string; descricao: string; qtd: number; preco_custo: number; preco_venda: number; total_custo: number; total_venda: number }) => {
      const base: Record<string, unknown> = {
        Código: it.codigo_fab, Descrição: it.descricao, Qtd: it.qtd,
        "Preço Venda (un)": it.preco_venda, "Total Venda": it.total_venda,
      };
      if (canVerCustos) {
        base["Custo (un)"] = it.preco_custo;
        base["Total Custo"] = it.total_custo;
        base["Margem %"] = it.preco_custo > 0 ? Number((((it.preco_venda - it.preco_custo) / it.preco_custo) * 100).toFixed(1)) : null;
      }
      return base;
    };
    exportSheetsToXlsx(`projeto-${projetoId}`, [
      { name: "Documentos", rows: sheetsDocumentos },
      { name: "Produtos", rows: (itens?.produtos || []).map(linhaItem) },
      { name: "Serviços", rows: (itens?.servicos || []).map(linhaItem) },
    ]);
  };

  const canVerCustos = can("PROJETOS.VER_CUSTOS");
  const sitColor = SIT_COLOR[situacao] || colors.muted;

  if (loading) {
    return (
      <SafeAreaView style={styles.safe}>
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: 40 }} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe} edges={["top"]} testID="projeto-form-screen">
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} hitSlop={12} style={styles.iconBtn} testID="projeto-form-back">
          <Ionicons name="chevron-back" size={22} color={colors.onBrandPrimary} />
        </Pressable>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {editing ? `Projeto nº ${projetoId}` : "Novo Projeto"}
        </Text>
        {editing ? (
          <IconButtonWithTooltip
            icon="attach-outline" label="Anexos" color={colors.onBrandPrimary}
            onPress={() => setAnexosOpen(true)} testID="projeto-form-anexos-btn"
          />
        ) : null}
        {editing ? (
          <IconButtonWithTooltip
            icon="print-outline" label={imprimindo ? "Imprimindo…" : "Imprimir"} color={colors.onBrandPrimary}
            onPress={handleImprimir} disabled={imprimindo} testID="projeto-form-imprimir-btn"
          />
        ) : null}
        {editing ? (
          <IconButtonWithTooltip
            icon="download-outline" label="Exportar Excel" color={colors.onBrandPrimary}
            onPress={handleExportarExcel} testID="projeto-form-exportar-excel-btn"
          />
        ) : null}
        {editing && can("LOG_AUDITORIA.ABRIR") ? (
          <IconButtonWithTooltip
            icon="time-outline" label="Ver Logs" color={colors.onBrandPrimary}
            onPress={() => router.push({ pathname: "/log-auditoria", params: { tela: "PROJETOS", referencia: String(projetoId) } } as never)}
            testID="projeto-form-logs-btn"
          />
        ) : null}
        <IconButtonWithTooltip
          icon="information-circle-outline" label="Ajuda" color={colors.onBrandPrimary}
          onPress={() => setAjudaOpen(true)} testID="projeto-form-ajuda-btn"
          style={{ marginLeft: spacing.sm }}
        />
        <Pressable onPress={handleSave} disabled={saving || camposTravados} style={[styles.saveBtn, (saving || camposTravados) && { opacity: 0.6 }]} testID="projeto-form-gravar">
          {saving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Gravar</Text>}
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={[styles.scroll, styles.scrollWeb]}>
        <View style={styles.shell}>
          {editing ? (
            <View style={[styles.card, { flexDirection: "row", alignItems: "center", gap: spacing.md, flexWrap: "wrap" }]} testID="projeto-form-situacao">
              <View style={[styles.sitTag, { backgroundColor: sitColor + "22" }]}>
                <Text style={[styles.sitTagText, { color: sitColor }]}>{situacaoLabel}</Text>
              </View>
              <Text style={styles.headerMeta}>Aberto {dataAbertura ? formatDateBR(dataAbertura) : "—"}</Text>
              <View style={{ flexDirection: "row", gap: spacing.md, marginLeft: "auto", flexWrap: "wrap" }}>
                {situacao === "A" && can("PROJETOS.SITUACAO") ? (
                  <Pressable onPress={() => handleTransicao("finalizar", setFinalizando)} disabled={finalizando} style={styles.actionBtn} testID="projeto-form-finalizar">
                    {finalizando ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Ionicons name="flag-outline" size={16} color={colors.brandPrimary} />}
                    <Text style={styles.actionBtnText}>{finalizando ? "Finalizando…" : "Finalizar"}</Text>
                  </Pressable>
                ) : null}
                {situacao === "F" && can("PROJETOS.SITUACAO") ? (
                  <Pressable onPress={() => handleTransicao("reabrir", setReabrindo)} disabled={reabrindo} style={styles.actionBtn} testID="projeto-form-reabrir">
                    {reabrindo ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Ionicons name="lock-open-outline" size={16} color={colors.brandPrimary} />}
                    <Text style={styles.actionBtnText}>{reabrindo ? "Reabrindo…" : "Reabrir"}</Text>
                  </Pressable>
                ) : null}
                {situacao === "A" && can("PROJETOS.SITUACAO") ? (
                  <Pressable
                    onPress={() => feedback.showConfirm("Cancelar este Projeto? Esta ação não pode ser desfeita.", () => handleTransicao("cancelar", setCancelando))}
                    disabled={cancelando}
                    style={styles.actionBtn}
                    testID="projeto-form-cancelar"
                  >
                    {cancelando ? <ActivityIndicator size="small" color={colors.error} /> : <Ionicons name="close-circle-outline" size={16} color={colors.error} />}
                    <Text style={[styles.actionBtnText, { color: colors.error }]}>{cancelando ? "Cancelando…" : "Cancelar"}</Text>
                  </Pressable>
                ) : null}
              </View>
            </View>
          ) : null}

          <View style={styles.card} testID="projeto-form-cliente">
            <ClienteSection
              hasCliente={!!cliente}
              clienteResumo={clienteResumo}
              loadingResumo={loadingResumo}
              onOpenSearch={() => {
                if (camposTravados) return;
                setSearchTerm(clienteQuickTerm); setSearchResults([]); setSearchOpen(true);
              }}
              onEditCliente={
                cliente?.codigo
                  ? () => router.push({ pathname: "/cliente-form", params: { codigo: String(cliente.codigo) } } as never)
                  : undefined
              }
              quickTerm={clienteQuickTerm}
              onQuickTermChange={handleClienteQuickChange}
              quickLoading={clienteQuickLoading}
              onSubmitTerm={resolveClienteQuickTerm}
              disabled={camposTravados}
            />
          </View>

          <View style={styles.card}>
            <Text style={styles.sectionTitle}>Dados do Projeto</Text>
            <View style={styles.rowFields}>
              <View style={{ flex: 1, minWidth: 220 }}>
                <Text style={pedidoStyles.fieldLabel}>Responsável</Text>
                <SelectField
                  value={responsavel}
                  onChange={(v) => setResponsavel(v == null ? null : Number(v))}
                  options={funcOptions}
                  placeholder="Selecione o responsável"
                  modalTitle="Responsável pelo Projeto"
                  disabled={camposTravados}
                  allowClear
                  compactWeb
                  testID="projeto-form-responsavel"
                />
              </View>
              <View style={{ flex: 1, minWidth: 160 }}>
                <Text style={pedidoStyles.fieldLabel}>Início Previsto</Text>
                <WebDateField value={dataInicio} onChange={(v) => setDataInicio(v || null)} disabled={camposTravados} testID="projeto-form-data-inicio" />
              </View>
              <View style={{ flex: 1, minWidth: 160 }}>
                <Text style={pedidoStyles.fieldLabel}>Prev. Término</Text>
                <WebDateField value={dataPrevista} onChange={(v) => setDataPrevista(v || null)} disabled={camposTravados} testID="projeto-form-data-prevista" />
              </View>
            </View>
            <View style={styles.rowFields}>
              <View style={{ width: 170 }}>
                <Text style={pedidoStyles.fieldLabel}>Valor Estimado (Produtos)</Text>
                <TextInput
                  value={valorProdutos}
                  onChangeText={setValorProdutos}
                  onBlur={() => setValorProdutos(numToInput(inputToNum(valorProdutos)))}
                  editable={!camposTravados}
                  keyboardType="decimal-pad"
                  style={styles.input}
                  testID="projeto-form-valor-produtos"
                />
              </View>
              <View style={{ width: 170 }}>
                <Text style={pedidoStyles.fieldLabel}>Valor Estimado (Serviços)</Text>
                <TextInput
                  value={valorServicos}
                  onChangeText={setValorServicos}
                  onBlur={() => setValorServicos(numToInput(inputToNum(valorServicos)))}
                  editable={!camposTravados}
                  keyboardType="decimal-pad"
                  style={styles.input}
                  testID="projeto-form-valor-servicos"
                />
              </View>
              <View style={{ width: 170 }}>
                <Text style={pedidoStyles.fieldLabel}>Valor Estimado (Total)</Text>
                <Text style={[styles.docValor, { paddingVertical: 10 }]}>
                  {formatBRL(inputToNum(valorProdutos) + inputToNum(valorServicos))}
                </Text>
              </View>
            </View>
            <Text style={pedidoStyles.fieldLabel}>Detalhes</Text>
            <TextInput
              value={detalhes}
              onChangeText={setDetalhes}
              editable={!camposTravados}
              multiline
              numberOfLines={4}
              placeholder="Escopo, observações do projeto…"
              placeholderTextColor={colors.muted}
              style={[styles.input, { minHeight: 90, textAlignVertical: "top" }]}
              testID="projeto-form-detalhes"
            />
          </View>

          {!editing ? (
            <View style={styles.card}>
              <View style={styles.lockedRow}>
                <Ionicons name="lock-closed-outline" size={18} color={colors.muted} />
                <Text style={styles.lockedText}>Grave o Projeto primeiro para vincular documentos.</Text>
              </View>
            </View>
          ) : (
            <>
              <View style={styles.card}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm }}>
                  <Text style={styles.sectionTitle}>Documentos Vinculados</Text>
                  {situacao === "A" ? (
                    <View style={{ flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" }}>
                      {TIPOS_VINCULO.filter((t) => can(`PROJETOS.${t.acao}`)).map((t) => (
                        <Pressable key={t.tipo} onPress={() => openVincular(t.tipo)} style={styles.linkBtn} testID={`projeto-form-vincular-${t.tipo}`}>
                          <Ionicons name={t.icon} size={15} color={colors.brandPrimary} />
                          <Text style={styles.linkBtnText}>Vincular {t.label}</Text>
                        </Pressable>
                      ))}
                    </View>
                  ) : null}
                </View>
                {documentos.length === 0 ? (
                  <Text style={pedidoStyles.emptyText}>Nenhum documento vinculado ainda.</Text>
                ) : (
                  documentos.map((d) => {
                    const key = `${d.tipo_doc}-${d.num_doc}`;
                    return (
                      <View key={key} style={styles.docRow} testID={`projeto-form-doc-${key}`}>
                        <View style={{ flex: 1 }}>
                          <Text style={styles.docTitle}>{d.tipo_doc_label} nº {d.num_doc}</Text>
                          <Text style={styles.docSub}>
                            {d.data_inclusao ? formatDateBR(d.data_inclusao) : "—"} · {d.situacao || "—"}
                          </Text>
                        </View>
                        <Text style={styles.docValor}>{formatBRL(d.total)}</Text>
                        {situacao === "A" && can("PROJETOS.REMOVER_DOC") ? (
                          <Pressable onPress={() => removerDocumento(d)} disabled={removendoDoc === key} hitSlop={8} testID={`projeto-form-remover-${key}`}>
                            {removendoDoc === key ? (
                              <ActivityIndicator size="small" color={colors.error} />
                            ) : (
                              <Ionicons name="trash-outline" size={18} color={colors.error} />
                            )}
                          </Pressable>
                        ) : null}
                      </View>
                    );
                  })
                )}
              </View>

              <View style={styles.card}>
                <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: spacing.sm }}>
                  <Text style={styles.sectionTitle}>Itens do Projeto</Text>
                  {situacao === "A" && can("PROJETOS.AJUSTAR_VALORES") ? (
                    <Pressable onPress={openAjustarValores} style={styles.linkBtn} testID="projeto-form-ajustar-valores-btn">
                      <Ionicons name="calculator-outline" size={15} color={colors.brandPrimary} />
                      <Text style={styles.linkBtnText}>Ajustar Valores</Text>
                    </Pressable>
                  ) : null}
                </View>
                <View style={styles.resumoRow}>
                  <Text style={styles.resumoLabel}>Produtos</Text>
                  <Text style={styles.resumoValor}>{formatBRL(itens?.total_venda_produtos || 0)}</Text>
                </View>
                <View style={styles.resumoRow}>
                  <Text style={styles.resumoLabel}>Serviços</Text>
                  <Text style={styles.resumoValor}>{formatBRL(itens?.total_venda_servicos || 0)}</Text>
                </View>
                {canVerCustos ? (
                  <View style={styles.resumoRow}>
                    <Text style={styles.resumoLabel}>Custo Geral</Text>
                    <Text style={styles.resumoValor}>{formatBRL(itens?.total_custo_geral || 0)}</Text>
                  </View>
                ) : null}
                <View style={[styles.resumoRow, styles.resumoRowTotal]}>
                  <Text style={styles.resumoLabelTotal}>Total Geral</Text>
                  <Text style={styles.resumoValorTotal}>{formatBRL(itens?.total_venda_geral || 0)}</Text>
                </View>
                <View style={styles.resumoRow}>
                  <Text style={[styles.resumoLabel, { color: colors.success }]}>Faturado</Text>
                  <Text style={[styles.resumoValor, { color: colors.success }]}>{formatBRL(faturado)}</Text>
                </View>
                <View style={styles.resumoRow}>
                  <Text style={[styles.resumoLabel, { color: colors.warning }]}>Saldo a Faturar</Text>
                  <Text style={[styles.resumoValor, { color: colors.warning }]}>{formatBRL(saldoAFaturar)}</Text>
                </View>

                <Pressable onPress={() => setDetalheItensOpen((v) => !v)} style={styles.detalharBtn} testID="projeto-form-detalhar-itens">
                  <Ionicons name={detalheItensOpen ? "chevron-up" : "chevron-down"} size={14} color={colors.brandPrimary} />
                  <Text style={styles.linkBtnText}>{detalheItensOpen ? "Ocultar itens" : "Detalhar itens"}</Text>
                </Pressable>

                {detalheItensOpen ? (
                  <>
                    <Text style={[styles.sectionTitle, { marginTop: spacing.sm }]}>Produtos</Text>
                    {!itens?.produtos.length ? (
                      <Text style={pedidoStyles.emptyText}>Nenhum produto.</Text>
                    ) : (
                      itens.produtos.map((it, idx) => (
                        <View key={`p-${it.codigo_fab}-${idx}`} style={styles.docRow}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.docTitle}>{it.codigo_fab} — {it.descricao}</Text>
                            <Text style={styles.docSub}>
                              Qtd {it.qtd} · {formatBRL(it.preco_venda)}/un
                              {canVerCustos ? ` · Custo ${formatBRL(it.preco_custo)}/un${it.preco_custo > 0 ? ` (Marg. ${(((it.preco_venda - it.preco_custo) / it.preco_custo) * 100).toFixed(1)}%)` : ""}` : ""}
                            </Text>
                          </View>
                          <Text style={styles.docValor}>{formatBRL(it.total_venda)}</Text>
                        </View>
                      ))
                    )}

                    <Text style={[styles.sectionTitle, { marginTop: spacing.md }]}>Serviços</Text>
                    {!itens?.servicos.length ? (
                      <Text style={pedidoStyles.emptyText}>Nenhum serviço.</Text>
                    ) : (
                      itens.servicos.map((it, idx) => (
                        <View key={`s-${it.codigo_fab}-${idx}`} style={styles.docRow}>
                          <View style={{ flex: 1 }}>
                            <Text style={styles.docTitle}>{it.codigo_fab} — {it.descricao}</Text>
                            <Text style={styles.docSub}>
                              Qtd {it.qtd} · {formatBRL(it.preco_venda)}/un
                              {canVerCustos ? ` · Custo ${formatBRL(it.preco_custo)}/un${it.preco_custo > 0 ? ` (Marg. ${(((it.preco_venda - it.preco_custo) / it.preco_custo) * 100).toFixed(1)}%)` : ""}` : ""}
                            </Text>
                          </View>
                          <Text style={styles.docValor}>{formatBRL(it.total_venda)}</Text>
                        </View>
                      ))
                    )}
                  </>
                ) : null}
              </View>
            </>
          )}

          <View style={{ height: 40 }} />
        </View>
      </ScrollView>

      <ClientSearchModal
        visible={searchOpen}
        onClose={() => setSearchOpen(false)}
        term={searchTerm}
        setTerm={setSearchTerm}
        loading={searchLoading}
        results={searchResults}
        onPick={(c) => { setCliente(c); setSearchOpen(false); }}
        onCreate={() => { setSearchOpen(false); router.push({ pathname: "/cliente-form", params: clienteSearchParams(searchTerm) } as never); }}
      />

      <Modal visible={vincularTipo != null} transparent animationType="slide" onRequestClose={() => setVincularTipo(null)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setVincularTipo(null)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompactNarrow]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Vincular {TIPOS_VINCULO.find((t) => t.tipo === vincularTipo)?.label}</Text>
              <Pressable onPress={() => setVincularTipo(null)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            <Text style={pedidoStyles.fieldLabel}>Número do documento</Text>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <TextInput
                value={vincularNum}
                onChangeText={(v) => { setVincularNum(v.replace(/\D/g, "")); setVincularPreview(null); }}
                keyboardType="number-pad"
                placeholder="Nº"
                placeholderTextColor={colors.muted}
                style={[styles.input, { flex: 1 }]}
                testID="projeto-form-vincular-num"
                onSubmitEditing={buscarVincular}
              />
              <Pressable onPress={buscarVincular} disabled={vincularLoading || !vincularNum.trim()} style={styles.linkBtn} testID="projeto-form-vincular-buscar">
                {vincularLoading ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : <Ionicons name="search" size={16} color={colors.brandPrimary} />}
                <Text style={styles.linkBtnText}>Buscar</Text>
              </Pressable>
            </View>
            {vincularPreview ? (
              <View style={styles.previewBox}>
                <Text style={styles.docTitle}>{vincularPreview.cliente_nome}</Text>
                <Text style={styles.docSub}>{vincularPreview.situacao_label}</Text>
                <Text style={styles.docValor}>{formatBRL(vincularPreview.total)}</Text>
              </View>
            ) : null}
            <Pressable
              onPress={confirmarVincular}
              disabled={!vincularPreview || vincularSaving}
              style={[styles.saveBtnFull, (!vincularPreview || vincularSaving) && { opacity: 0.5 }]}
              testID="projeto-form-vincular-confirmar"
            >
              {vincularSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Vincular</Text>}
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      <Modal visible={ajustarOpen} transparent animationType="slide" onRequestClose={() => setAjustarOpen(false)}>
        <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setAjustarOpen(false)}>
          <Pressable style={[pedidoStyles.modalCard, pedidoStyles.modalCardWebCompact]} onPress={(e) => e.stopPropagation()}>
            <View style={pedidoStyles.modalHeader}>
              <Text style={pedidoStyles.modalTitle}>Ajustar Valores</Text>
              <Pressable onPress={() => setAjustarOpen(false)} hitSlop={8}>
                <Ionicons name="close" size={22} color={colors.muted} />
              </Pressable>
            </View>
            {ajustarLoading ? (
              <ActivityIndicator color={colors.brandPrimary} style={{ marginVertical: spacing.lg }} />
            ) : ajustarPreview ? (
              <ScrollView style={{ maxHeight: 480 }}>
                <Text style={styles.ajustarHint}>
                  Redistribui desconto/acréscimo entre os itens dos documentos selecionados para bater um novo
                  valor-alvo de Produtos ou Serviços — sempre reiniciando do preço cheio antes de aplicar o ajuste.
                </Text>

                <View style={{ flexDirection: "row", gap: spacing.sm, marginTop: spacing.sm }}>
                  <Pressable
                    onPress={() => trocarAjustarTipo("P")}
                    style={[styles.tipoTab, ajustarTipo === "P" && styles.tipoTabSel]}
                    testID="projeto-form-ajustar-tipo-produtos"
                  >
                    <Text style={[styles.tipoTabText, ajustarTipo === "P" && styles.tipoTabTextSel]}>Produtos</Text>
                  </Pressable>
                  <Pressable
                    onPress={() => trocarAjustarTipo("S")}
                    style={[styles.tipoTab, ajustarTipo === "S" && styles.tipoTabSel]}
                    testID="projeto-form-ajustar-tipo-servicos"
                  >
                    <Text style={[styles.tipoTabText, ajustarTipo === "S" && styles.tipoTabTextSel]}>Serviços</Text>
                  </Pressable>
                </View>

                <View style={styles.resumoRow}>
                  <Text style={styles.resumoLabel}>Estimado</Text>
                  <Text style={styles.resumoValor}>
                    {formatBRL(ajustarTipo === "P" ? ajustarPreview.estimado.produtos : ajustarPreview.estimado.servicos)}
                  </Text>
                </View>
                <View style={styles.resumoRow}>
                  <Text style={[styles.resumoLabel, { color: colors.success }]}>Já Faturado</Text>
                  <Text style={[styles.resumoValor, { color: colors.success }]}>
                    {formatBRL(ajustarTipo === "P" ? ajustarPreview.faturado.produtos : ajustarPreview.faturado.servicos)}
                  </Text>
                </View>
                <View style={styles.resumoRow}>
                  <Text style={styles.resumoLabel}>Saldo do Orçamento</Text>
                  <Text style={styles.resumoValor}>
                    {formatBRL(ajustarTipo === "P" ? ajustarPreview.saldo_orcamento.produtos : ajustarPreview.saldo_orcamento.servicos)}
                  </Text>
                </View>

                <Text style={[pedidoStyles.fieldLabel, { marginTop: spacing.md }]}>Documentos a reprocessar</Text>
                {ajustarPreview.documentos.filter((d) => (ajustarTipo === "P" ? d.total_produtos : d.total_servicos) > 0).length === 0 ? (
                  <Text style={pedidoStyles.emptyText}>Nenhum documento pendente com itens de {ajustarTipo === "P" ? "Produtos" : "Serviços"}.</Text>
                ) : (
                  ajustarPreview.documentos.map((d) => {
                    const valorTipo = ajustarTipo === "P" ? d.total_produtos : d.total_servicos;
                    if (valorTipo <= 0) return null;
                    const key = `${d.tipo_doc}-${d.num_doc}`;
                    const sel = ajustarSelecionados.has(key);
                    return (
                      <Pressable key={key} onPress={() => toggleAjustarDoc(key)} style={styles.docCheckRow} testID={`projeto-form-ajustar-doc-${key}`}>
                        <Ionicons name={sel ? "checkbox" : "square-outline"} size={20} color={sel ? colors.brandPrimary : colors.muted} />
                        <View style={{ flex: 1 }}>
                          <Text style={styles.docTitle}>{d.tipo_doc_label} nº {d.num_doc}</Text>
                        </View>
                        <Text style={styles.docValor}>{formatBRL(valorTipo)}</Text>
                      </Pressable>
                    );
                  })
                )}

                <View style={[styles.resumoRow, styles.resumoRowTotal]}>
                  <Text style={styles.resumoLabelTotal}>Total Atual (seleção)</Text>
                  <Text style={styles.resumoValorTotal}>{formatBRL(ajustarTotalAtual)}</Text>
                </View>

                <Text style={pedidoStyles.fieldLabel}>Novo Valor</Text>
                <TextInput
                  value={ajustarNovoValor}
                  onChangeText={setAjustarNovoValor}
                  onBlur={() => setAjustarNovoValor(numToInput(inputToNum(ajustarNovoValor)))}
                  keyboardType="decimal-pad"
                  style={styles.input}
                  testID="projeto-form-ajustar-novo-valor"
                />

                <Pressable
                  onPress={confirmarAjustarValores}
                  disabled={ajustarSaving}
                  style={[styles.saveBtnFull, ajustarSaving && { opacity: 0.6 }]}
                  testID="projeto-form-ajustar-confirmar"
                >
                  {ajustarSaving ? <ActivityIndicator color={colors.onBrandPrimary} size="small" /> : <Text style={styles.saveLabel}>Aplicar Ajuste</Text>}
                </Pressable>
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {editing && conn ? (
        <Modal visible={anexosOpen} transparent animationType="slide" onRequestClose={() => setAnexosOpen(false)}>
          <Pressable style={[pedidoStyles.modalBg, pedidoStyles.modalBgWebCompact]} onPress={() => setAnexosOpen(false)}>
            <Pressable style={[pedidoStyles.modalCard, styles.modalCardWebWide]} onPress={(e) => e.stopPropagation()}>
              <View style={pedidoStyles.modalHeader}>
                <Text style={pedidoStyles.modalTitle}>Anexos do Projeto nº {projetoId}</Text>
                <Pressable onPress={() => setAnexosOpen(false)} hitSlop={8}>
                  <Ionicons name="close" size={22} color={colors.muted} />
                </Pressable>
              </View>
              <ScrollView style={{ maxHeight: 560 }}>
                <GestorDocumentosSection
                  api={conn.api}
                  servidor={conn.servidor}
                  banco={conn.banco}
                  codGrupo={GESTOR_DOC_GRUPO_CLIENTE}
                  codigoEntidade={cliente?.codigo ?? 0}
                  referencia={projetoId ?? undefined}
                />
              </ScrollView>
            </Pressable>
          </Pressable>
        </Modal>
      ) : null}

      <AjudaPedidoModal visible={ajudaOpen} onClose={() => setAjudaOpen(false)} titulo="Gestor de Projetos" itens={AJUDA_PROJETO_ITENS} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.brandPrimary, paddingHorizontal: spacing.md, paddingVertical: spacing.md,
  },
  iconBtn: { width: 32, height: 32, alignItems: "center", justifyContent: "center" },
  headerTitle: { flex: 1, color: colors.onBrandPrimary, fontSize: 17, fontWeight: "500" },
  headerMeta: { fontSize: 12, color: colors.muted },
  saveBtn: {
    backgroundColor: "rgba(255,255,255,0.18)", borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: 8, marginLeft: spacing.sm, minWidth: 76, alignItems: "center",
  },
  saveBtnFull: {
    backgroundColor: colors.brandPrimary, borderRadius: radius.sm,
    paddingVertical: 10, alignItems: "center", marginTop: spacing.md,
  },
  saveLabel: { color: colors.onBrandPrimary, fontWeight: "600", fontSize: 13 },
  scroll: { paddingBottom: spacing.xxl },
  scrollWeb: WEB_SCROLL_CENTER,
  shell: WEB_CONTENT_SHELL,
  card: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg,
    padding: spacing.lg, marginTop: spacing.md, gap: spacing.sm,
  },
  sectionTitle: { fontSize: 12, color: colors.muted, fontWeight: "600", textTransform: "uppercase", letterSpacing: 0.5 },
  sitTag: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 4 },
  sitTagText: { fontSize: 11, fontWeight: "700", letterSpacing: 0.4 },
  rowFields: { flexDirection: "row", gap: spacing.md, flexWrap: "wrap" },
  input: {
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.sm,
    paddingHorizontal: spacing.md, paddingVertical: 10, fontSize: 14, color: colors.onSurface,
  },
  lockedRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  lockedText: { color: colors.muted, fontSize: 13 },
  linkBtn: {
    flexDirection: "row", alignItems: "center", gap: 6, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.sm, paddingHorizontal: spacing.md, paddingVertical: 8,
  },
  linkBtnText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },
  actionBtn: { flexDirection: "row", alignItems: "center", gap: 6 },
  actionBtnText: { color: colors.brandPrimary, fontSize: 12, fontWeight: "600" },
  docRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: spacing.sm,
  },
  docTitle: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  docSub: { fontSize: 12, color: colors.muted, marginTop: 2 },
  docValor: { fontSize: 13, fontWeight: "700", color: colors.onSurface },
  previewBox: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.sm, padding: spacing.md, marginTop: spacing.sm, gap: 2,
  },
  resumoRow: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 4 },
  resumoRowTotal: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: 4, paddingTop: 8 },
  resumoLabel: { fontSize: 13, color: colors.muted },
  resumoValor: { fontSize: 13, fontWeight: "600", color: colors.onSurface },
  resumoLabelTotal: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  resumoValorTotal: { fontSize: 14, fontWeight: "700", color: colors.onSurface },
  detalharBtn: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.sm, alignSelf: "flex-start" },
  ajustarHint: { fontSize: 12, color: colors.muted, lineHeight: 17 },
  tipoTab: {
    borderWidth: 1, borderColor: colors.border, borderRadius: radius.pill,
    paddingHorizontal: spacing.md, paddingVertical: 6,
  },
  tipoTabSel: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  tipoTabText: { fontSize: 12, fontWeight: "600", color: colors.onSurface },
  tipoTabTextSel: { color: colors.onBrandPrimary },
  docCheckRow: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: spacing.sm,
  },
  // Tier "largo" (960px) — o painel lista+preview do GestorDocumentosSection
  // fica cramped no tier compacto padrão (560px), mesma ressalva já
  // documentada em CLAUDE.md > "Anexos" (produto-completo.tsx's
  // modalCardWebWide) — replicado aqui localmente porque ainda não existe
  // uma versão compartilhada em pedido/styles.ts.
  modalCardWebWide: {
    width: "100%", maxWidth: 960, alignSelf: "center",
    borderBottomLeftRadius: radius.lg, borderBottomRightRadius: radius.lg,
    borderWidth: 1, borderColor: colors.border,
  },
});
